"""Calculate Essdee fabric inputs for base YRP's mapped GRN contract.

Every calculated input remains mapped to the exact received GRN row whose
valuation it contributes. Base YRP posts and values the physical stock; this
module only owns Essdee's IPD/BOM calculation and Work Order ``stock_update``
bookkeeping.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_step
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	scale_reference_allocations,
)


QTY_TOLERANCE = 0.000001


def before_validate(doc, method=None):
	"""Keep a draft preview; the controller recalculates under lock on submit."""
	if not is_calculable_fabric_grn(doc):
		return
	populate_grn_deliverables(doc, calculate_consumption_plan(doc))


def is_calculable_fabric_grn(grn):
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
	):
		return False
	if not frappe.db.exists("Work Order", grn.against_id):
		return False
	wo = frappe.get_cached_doc("Work Order", grn.against_id)
	return bool(wo.get("production_detail") and wo.get("process_name"))


def calculate_consumption_plan(grn):
	"""Return exact, UOM-normalized inputs for each positive received row."""
	if not is_calculable_fabric_grn(grn):
		return []

	wo = frappe.get_doc("Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	step = get_fabric_step(ipd, wo.process_name)

	from essdee_yrp.fabric_ipd import get_identity_process_row

	identity_row = get_identity_process_row(ipd, wo.process_name)
	if not step and not identity_row:
		return []

	demands = _get_output_demands(grn, wo)
	if not demands:
		return []
	rows = _calculate_consumed_rows(
		ipd,
		wo.process_name,
		demands,
		identity=bool(identity_row or (step and step.get("shape") == "identity")),
	)
	return _allocate_to_work_order_deliverables(rows, wo, grn)


def _get_output_demands(grn, wo):
	receivables = {row.name: row for row in wo.get("receivables") or []}
	by_variant = {}
	for row in receivables.values():
		by_variant.setdefault(row.item_variant, []).append(row)

	demands = []
	for row in grn.get("items") or []:
		actual_qty = flt(row.get("quantity"))
		if actual_qty <= 0:
			continue
		source = receivables.get(row.get("ref_docname"))
		if not source:
			candidates = by_variant.get(row.get("item_variant")) or []
			if len(candidates) == 1:
				source = candidates[0]
		if not source:
			frappe.throw(
				_(
					"GRN row {0} is not linked to a Work Order Receivable. "
					"Reload the Goods Received Note from Work Order {1}."
				).format(row.get("item_variant"), wo.name)
			)

		planned_allocations = get_reference_allocations(source, source.qty)
		actual_allocations = scale_reference_allocations(planned_allocations, actual_qty)
		physical_attrs = _variant_attrs(row.item_variant)
		if actual_allocations:
			for reference, qty in actual_allocations.items():
				demands.append(
					{
						"goods_received_note_item": row.name,
						"received_item_variant": row.item_variant,
						"attrs": physical_attrs,
						"qty": qty,
						"item_variant": row.item_variant,
						"reference_item_variant": reference,
					}
				)
			continue

		reference = source.get("fabric_reference_variant")
		demands.append(
			{
				"goods_received_note_item": row.name,
				"received_item_variant": row.item_variant,
				"attrs": physical_attrs,
				"qty": actual_qty,
				"item_variant": row.item_variant,
				"reference_item_variant": reference,
			}
		)
	return demands


def _calculate_consumed_rows(ipd, process_name, demands, identity=False):
	"""Return matrix principal inputs plus Item BOM process consumables."""
	from yrp.yrp.utils.ipd_engine import get_consumables, get_process_io

	rows = []
	for demand in demands:
		mapping = {
			"goods_received_note_item": demand["goods_received_note_item"],
			"received_item_variant": demand["received_item_variant"],
			"reference_item_variant": demand.get("reference_item_variant"),
		}
		if identity:
			parent_item = frappe.db.get_value("Item Variant", demand["item_variant"], "item")
			rows.append(
				{
					**mapping,
					"item_variant": demand["item_variant"],
					"qty": demand["qty"],
					"uom": frappe.db.get_value("Item", parent_item, "default_unit_of_measure"),
				}
			)
		else:
			for input_row in get_process_io(ipd.name, process_name, [demand])["inputs"]:
				rows.append(
					{
						**mapping,
						"item_variant": _resolve_variant(
							input_row["item"], input_row.get("attrs") or {}
						),
						"qty": input_row["qty"],
						"uom": input_row.get("uom"),
					}
				)

		# Item BOM calculation is deliberately per reference demand. That
		# retains route mapping when physical inputs are consolidated.
		reference = demand.get("reference_item_variant")
		bom_attrs = _variant_attrs(reference) if reference else demand["attrs"]
		for bom_row in get_consumables(
			ipd.name,
			demand["qty"],
			variants=[{"attrs": bom_attrs, "qty": demand["qty"]}],
			process_name=process_name,
		):
			if not bom_row.get("item") or flt(bom_row.get("qty")) <= 0:
				continue
			rows.append(
				{
					**mapping,
					"item_variant": _resolve_variant(bom_row["item"], bom_row.get("attrs") or {}),
					"qty": bom_row["qty"],
					"uom": bom_row.get("uom")
					or frappe.db.get_value("Item", bom_row["item"], "default_unit_of_measure"),
				}
			)
	return _aggregate_rows(rows)


def _aggregate_rows(rows):
	aggregated = {}
	for row in rows:
		key = (
			row["goods_received_note_item"],
			row["item_variant"],
			row.get("uom"),
			row.get("reference_item_variant"),
		)
		if key not in aggregated:
			aggregated[key] = {
				"goods_received_note_item": row["goods_received_note_item"],
				"received_item_variant": row["received_item_variant"],
				"item_variant": row["item_variant"],
				"qty": 0.0,
				"uom": row.get("uom"),
				"reference_item_variant": row.get("reference_item_variant"),
			}
		aggregated[key]["qty"] += flt(row.get("qty"))
	return [
		{
			**row,
			"qty": flt(row["qty"], 6),
		}
		for row in aggregated.values()
		if flt(row["qty"]) > 0
	]


def _allocate_to_work_order_deliverables(rows, wo, grn):
	from essdee_yrp.fabric_reference import get_reference_allocations
	from yrp.stock.utils import get_conversion_factor, get_stock_balance
	from yrp.yrp.doctype.work_order.work_order import _stock_dimension_values

	available = []
	for deliverable in wo.get("deliverables") or []:
		if not deliverable.get("is_calculated"):
			continue
		conversion = get_conversion_factor(deliverable.item_variant, deliverable.uom)
		factor = flt(conversion.get("conversion_factor")) or 1
		delivered_qty = flt(deliverable.qty) - flt(deliverable.pending_quantity)
		available_qty = max(delivered_qty - flt(deliverable.stock_update), 0)
		available.append(
			{
				"row": deliverable,
				"factor": factor,
				"stock_uom": conversion.get("stock_uom") or deliverable.uom,
				"available_stock_qty": available_qty * factor,
				"dimensions": _stock_dimension_values(wo, deliverable),
				"references": set(
					get_reference_allocations(deliverable, deliverable.qty)
				),
			}
		)

	valuation_cache = {}
	plan = []
	for required in rows:
		conversion = get_conversion_factor(required["item_variant"], required.get("uom"))
		required_stock_qty = flt(required["qty"]) * (
			flt(conversion.get("conversion_factor")) or 1
		)
		remaining_stock_qty = required_stock_qty
		reference = required.get("reference_item_variant")
		candidates = [
			item for item in available
			if item["row"].item_variant == required["item_variant"]
		]
		candidates.sort(
			key=lambda item: (
				0 if reference and reference in item["references"] else 1,
				item["row"].idx or 0,
				item["row"].name or "",
			)
		)
		for source in candidates:
			available_stock_qty = flt(source["available_stock_qty"])
			if available_stock_qty <= QTY_TOLERANCE:
				continue
			take_stock_qty = min(remaining_stock_qty, available_stock_qty)
			row = source["row"]
			dimensions = source["dimensions"]
			valuation_key = (
				required["item_variant"],
				grn.from_warehouse,
				tuple(sorted(dimensions.items())),
			)
			if valuation_key not in valuation_cache:
				_balance, valuation_cache[valuation_key] = get_stock_balance(
					required["item_variant"],
					grn.from_warehouse,
					posting_date=grn.posting_date,
					posting_time=grn.posting_time,
					with_valuation_rate=True,
					**dimensions,
				)
			plan.append(
				{
					"goods_received_note_item": required["goods_received_note_item"],
					"received_item_variant": required["received_item_variant"],
					"work_order_deliverable": row.name,
					"item_variant": required["item_variant"],
					"quantity": take_stock_qty / source["factor"],
					"stock_qty": take_stock_qty,
					"uom": row.uom,
					"stock_uom": source["stock_uom"],
					"conversion_factor": source["factor"],
					"valuation_rate": flt(
						row.valuation_rate
						or row.rate
						or valuation_cache[valuation_key]
					),
					"dimensions": dimensions,
				}
			)
			source["available_stock_qty"] = available_stock_qty - take_stock_qty
			remaining_stock_qty -= take_stock_qty
			if remaining_stock_qty <= QTY_TOLERANCE:
				break

		if remaining_stock_qty > QTY_TOLERANCE:
			frappe.throw(
				_(
					"Work Order {0} has only {1} stock available for calculated input {2}, "
					"but received row {3} requires {4}. Deliver the remaining input first."
				).format(
					wo.name,
					flt(required_stock_qty - remaining_stock_qty, 6),
					required["item_variant"],
					required["goods_received_note_item"],
					flt(required_stock_qty, 6),
				)
			)
	return plan


def populate_grn_deliverables(grn, plan):
	"""Persist Essdee's plan using base YRP's mapped valuation schema."""
	grn.set("grn_deliverables", [])
	for item in plan:
		dimensions = item.get("dimensions") or {}
		grn.append(
			"grn_deliverables",
			{
				"goods_received_note_item": item["goods_received_note_item"],
				"received_item_variant": item["received_item_variant"],
				"item_variant": item["item_variant"],
				"quantity": flt(item["quantity"], 6),
				"uom": item["uom"],
				"stock_qty": flt(item["stock_qty"], 6),
				"stock_uom": item["stock_uom"],
				"conversion_factor": item["conversion_factor"],
				"valuation_rate": item["valuation_rate"],
				"work_order_deliverable": item["work_order_deliverable"],
				"stock_dimensions": frappe.as_json(dimensions),
				"lot": dimensions.get("lot"),
				"received_type": dimensions.get("received_type"),
				"set_combination": {},
			},
		)


def load_submitted_consumption_plan(grn):
	"""Load the persisted plan; cancellation never recalculates an IPD matrix."""
	plan = []
	for row in grn.get("grn_deliverables") or []:
		raw_dimensions = row.get("stock_dimensions") or {}
		if isinstance(raw_dimensions, str):
			raw_dimensions = frappe.parse_json(raw_dimensions)
		plan.append(
			{
				"goods_received_note_item": row.get("goods_received_note_item"),
				"received_item_variant": row.get("received_item_variant"),
				"work_order_deliverable": row.work_order_deliverable,
				"item_variant": row.item_variant,
				"quantity": flt(row.quantity),
				"stock_qty": flt(row.stock_qty) or flt(row.quantity),
				"uom": row.uom,
				"stock_uom": row.stock_uom or row.uom,
				"conversion_factor": flt(row.conversion_factor) or 1,
				"valuation_rate": flt(row.valuation_rate),
				"dimensions": raw_dimensions if isinstance(raw_dimensions, dict) else {},
			}
		)
	return plan


def apply_work_order_stock_update(work_order, plan, cancel=False):
	"""Increment/decrement only the mapped Work Order deliverable rows."""
	if not plan:
		return
	from yrp.yrp.doctype.delivery_challan.delivery_challan import (
		_update_work_order_status,
	)

	rows = {
		row.name: row
		for row in frappe.get_doc("Work Order", work_order).get("deliverables") or []
	}
	qty_by_row = defaultdict(float)
	for item in plan:
		qty_by_row[item["work_order_deliverable"]] += flt(item["quantity"])

	for row_name, qty in qty_by_row.items():
		row = rows.get(row_name)
		if not row:
			frappe.throw(
				_("Work Order Deliverable {0} no longer exists on {1}.").format(
					row_name, work_order
				)
			)
		current = flt(row.stock_update)
		if cancel and current + QTY_TOLERANCE < qty:
			frappe.throw(
				_("Consumed stock audit mismatch for Work Order Deliverable {0}.").format(
					row_name
				)
			)
		new_value = current - qty if cancel else current + qty
		frappe.db.set_value(
			"Work Order Deliverables",
			row_name,
			"stock_update",
			flt(max(new_value, 0), 6),
			update_modified=False,
		)
	_update_work_order_status(work_order)


def _variant_attrs(item_variant):
	if not item_variant:
		return {}
	return {
		row.attribute: row.attribute_value
		for row in frappe.get_all(
			"Item Variant Attribute",
			filters={
				"parent": item_variant,
				"parenttype": "Item Variant",
			},
			fields=["attribute", "attribute_value"],
		)
	}


def _resolve_variant(item, attrs):
	from essdee_yrp.api.work_order import _resolve_variant

	return _resolve_variant(item, attrs)
