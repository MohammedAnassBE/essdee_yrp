"""Calculate Essdee inputs for base YRP's mapped production-GRN contract.

Every newly calculated input remains mapped to the exact received GRN row whose
valuation it contributes. Base YRP owns physical stock posting, actual FIFO or
Moving Average valuation, persisted production lineage, and cancellation. This
module owns only Essdee's IPD/BOM calculation and Work Order ``stock_update``
bookkeeping. Historical all-unmapped rows retain the explicit legacy hook at
the bottom of this module.
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
	"""Keep a draft preview; submit recalculates under the Work Order lock."""
	if not is_calculable_fabric_grn(doc):
		return
	populate_grn_deliverables(doc, calculate_consumption_plan(doc))


def on_submit(doc, method=None):
	_apply_consumption(doc, cancel=False)


def on_cancel(doc, method=None):
	_apply_consumption(doc, cancel=True)


def is_calculable_fabric_grn(grn):
	# A Cutting LaySheet supplies its actual cloth/accessory consumption. Replacing
	# those rows with the standard IPD matrix would lose the weighed cutting data.
	if grn.flags.get("from_cls") or grn.get("cutting_laysheet"):
		return False
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
	# Identity garment processes have their own exact 1:1 planner. Letting the
	# generic fabric hook run first performs a second calculation and briefly
	# writes a plan that the identity hook immediately replaces.
	from essdee_yrp.garment_grn import (
		_is_identity_garment_grn,
		_is_stitching_garment_grn,
	)

	if _is_identity_garment_grn(grn) or _is_stitching_garment_grn(grn):
		return False
	wo = frappe.get_cached_doc("Work Order", grn.against_id)
	return bool(wo.get("production_detail") and wo.get("process_name"))


# Backwards-compatible import used by the existing focused tests.
_is_calculable_fabric_grn = is_calculable_fabric_grn


def calculate_consumption_plan(grn):
	"""Return exact, stock-UOM-normalized inputs for each positive output row."""
	if not is_calculable_fabric_grn(grn):
		return []

	wo = frappe.get_doc("Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	step = get_fabric_step(ipd, wo.process_name)

	from essdee_yrp.fabric_ipd import get_identity_process_row

	identity_row = None if step else get_identity_process_row(ipd, wo.process_name)
	if not step and not identity_row:
		return []

	demands = _get_output_demands(grn, wo)
	if not demands:
		return []
	rows = _calculate_consumed_rows(
		ipd,
		wo.process_name,
		demands,
		identity=bool(identity_row),
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
			# Calculate each output separately. Combining demands before calling the
			# IPD engine loses the output identity required by mapped valuation.
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

		# Item BOM calculation is deliberately per output/reference demand. That
		# preserves both route mapping and exact output valuation lineage.
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


def _allocate_to_work_order_deliverables(
	rows, wo, grn, *, exact_business_key=False
):
	"""Allocate each exact output demand to available Work Order input rows."""
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
			item
			for item in available
			if item["row"].item_variant == required["item_variant"]
		]
		if required.get("uom"):
			candidates = [
				item for item in candidates if item["row"].uom == required["uom"]
			]
		if "set_combination" in required:
			from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

			required_combination = _normal_json(required.get("set_combination"))
			candidates = [
				item
				for item in candidates
				if _normal_json(item["row"].get("set_combination"))
				== required_combination
			]
		if exact_business_key and len(candidates) != 1:
			frappe.throw(
				_(
					"Calculated input {0} matches {1} Work Order Deliverables in {2}; expected exactly one."
				).format(required["item_variant"], len(candidates), wo.name)
			)
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
					"set_combination": row.get("set_combination") or {},
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
	"""Persist a plan using base YRP's optional mapped valuation schema."""
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
				"set_combination": item.get("set_combination") or {},
			},
		)


def load_submitted_consumption_plan(grn):
	"""Load persisted lineage; cancellation must never recalculate an IPD."""
	plan = []
	for row in grn.get("grn_deliverables") or []:
		raw_dimensions = row.get("stock_dimensions") or {}
		if isinstance(raw_dimensions, str):
			raw_dimensions = frappe.parse_json(raw_dimensions)
		plan.append(
			{
				"goods_received_note_item": row.get("goods_received_note_item"),
				"received_item_variant": row.get("received_item_variant"),
				"work_order_deliverable": row.get("work_order_deliverable"),
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
	"""Apply mapped input quantities exactly once to their Work Order rows."""
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
		row_name = item.get("work_order_deliverable")
		if not row_name:
			frappe.throw(_("A new mapped GRN input is missing its Work Order Deliverable."))
		qty_by_row[row_name] += flt(item["quantity"])

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


def _apply_consumption(grn, cancel=False):
	if grn.get("against") != "Work Order" or not grn.get("against_id") or not grn.get("grn_deliverables"):
		return
	from yrp.yrp.doctype.goods_received_note.goods_received_note import (
		has_mapped_grn_deliverables,
	)

	if has_mapped_grn_deliverables(grn):
		return

	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.stock.stock_ledger import make_sl_entries
	from yrp.stock.utils import get_stock_balance
	from yrp.yrp.doctype.delivery_challan.delivery_challan import (
		_update_work_order_status,
	)

	frappe.db.get_value("Work Order", grn.against_id, "name", for_update=True)
	wo = frappe.get_doc("Work Order", grn.against_id)
	deliverables = {row.name: row for row in wo.get("deliverables") or []}
	dimension_fields = get_dimension_fieldnames()
	entries = []
	updates = {}
	# Rows generated by the F16 fabric engine carry an explicit deliverable link
	# and must remain strict. Historical production_api rows (notably packing
	# GRNs) predate that link and can legitimately consume stock variants that
	# are not themselves Work Order Deliverables; those are stock-only rows.
	has_explicit_links = any(
		row.get("work_order_deliverable") for row in grn.grn_deliverables
	)

	for row in grn.grn_deliverables:
		qty = flt(row.stock_qty) or flt(row.quantity)
		if qty <= 0:
			continue
		source = _resolve_deliverable_source(row, deliverables, wo)
		if not source and has_explicit_links:
			frappe.throw(
				_("Consumed row {0} no longer matches a Deliverable in Work Order {1}.").format(
					row.item_variant, wo.name
				)
			)
		dimensions = {}
		for fieldname in dimension_fields:
			value = row.get(fieldname) if row.meta.get_field(fieldname) else None
			if not value and source and source.meta.get_field(fieldname):
				value = source.get(fieldname)
			if not value and wo.meta.get_field(fieldname):
				value = wo.get(fieldname)
			dimensions[fieldname] = value
		if "lot" in dimensions and not dimensions.get("lot"):
			dimensions["lot"] = row.get("lot") or wo.get("lot")
		if "received_type" in dimensions and not dimensions.get("received_type"):
			dimensions["received_type"] = row.get("received_type") or frappe.db.get_single_value(
				"YRP Stock Settings", "default_received_type"
			)

		valuation_rate = flt(row.valuation_rate)
		if not valuation_rate:
			_balance, valuation_rate = get_stock_balance(
				row.item_variant,
				grn.from_warehouse,
				with_valuation_rate=True,
				**dimensions,
			)
		entries.append(
			{
				"item": row.item_variant,
				"warehouse": grn.from_warehouse,
				"uom": row.stock_uom or row.uom,
				"voucher_type": grn.doctype,
				"voucher_no": grn.name,
				"voucher_detail_no": row.name,
				"posting_date": grn.posting_date,
				"posting_time": grn.posting_time,
				"qty": -qty,
				"rate": 0,
				"outgoing_rate": valuation_rate,
				"is_cancelled": 1 if cancel else 0,
				**dimensions,
			}
		)
		if source:
			updates[source.name] = updates.get(source.name, 0) + flt(row.quantity)

	make_sl_entries(entries, cancel=cancel)
	for source_name, qty in updates.items():
		source = deliverables[source_name]
		stock_update = flt(source.stock_update)
		source.db_set(
			"stock_update",
			flt(stock_update - qty if cancel else stock_update + qty, 3),
			update_modified=False,
		)
	_update_work_order_status(wo.name)


def _resolve_deliverable_source(row, deliverables, work_order):
	"""Resolve both current and migrated F15 GRN consumption rows.

	Current rows carry ``work_order_deliverable``. Historical production_api
	rows predate that link, so their immutable business key is reconstructed from
	the consumed variant/UOM and, only when needed, the stored combination and
	stock dimensions. Ambiguous legacy rows fail loudly instead of updating an
	arbitrary Work Order line.
	"""
	linked = deliverables.get(row.get("work_order_deliverable"))
	if linked:
		_validate_legacy_deliverable_match(row, linked, work_order)
		return linked

	candidates = [
		source
		for source in deliverables.values()
		if source.item_variant == row.item_variant
		and (not row.get("uom") or source.uom == row.uom)
	]
	if len(candidates) == 1:
		return candidates[0]

	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

	row_combination = _normal_json(row.get("set_combination"))
	if row_combination not in (None, "", "{}", {}):
		candidates = [
			source
			for source in candidates
			if _normal_json(source.get("set_combination")) == row_combination
		]

	for fieldname in ("lot", "received_type"):
		value = row.get(fieldname)
		if not value:
			continue
		candidates = [
			source for source in candidates if source.get(fieldname) == value
		]

	if len(candidates) == 1:
		return candidates[0]
	if len(candidates) > 1:
		frappe.throw(
			_(
				"Migrated consumed row {0} matches multiple Deliverables in Work "
				"Order {1}; add its Work Order Deliverable link before reversal."
			).format(row.item_variant, work_order.name)
		)
	return None


def _validate_legacy_deliverable_match(row, source, work_order):
	"""Reject a saved legacy child identity that contradicts its business key."""
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json
	from yrp.yrp.doctype.work_order.work_order import _stock_dimension_values

	mismatched = []
	if source.item_variant != row.item_variant:
		mismatched.append("item_variant")
	if row.get("uom") and source.uom != row.uom:
		mismatched.append("uom")
	row_combination = _normal_json(row.get("set_combination"))
	if (
		row_combination not in (None, "", "{}", {})
		and _normal_json(source.get("set_combination")) != row_combination
	):
		mismatched.append("set_combination")
	raw_dimensions = row.get("stock_dimensions") or {}
	if isinstance(raw_dimensions, str):
		try:
			raw_dimensions = frappe.parse_json(raw_dimensions)
		except (TypeError, ValueError):
			frappe.throw(_("Migrated consumed row has invalid Stock Dimensions."))
	if not isinstance(raw_dimensions, dict):
		frappe.throw(_("Migrated consumed row has invalid Stock Dimensions."))
	expected_dimensions = _stock_dimension_values(work_order, source)
	for fieldname in get_dimension_fieldnames():
		value = row.get(fieldname) or raw_dimensions.get(fieldname)
		if value and (expected_dimensions.get(fieldname) or None) != value:
			mismatched.append(fieldname)
	if mismatched:
		frappe.throw(
			_(
				"Migrated consumed row {0} does not match linked Work Order Deliverable {1}: {2}."
			).format(row.item_variant, source.name, ", ".join(mismatched))
		)


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
