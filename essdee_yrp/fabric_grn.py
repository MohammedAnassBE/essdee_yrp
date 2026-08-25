"""Fabric GRN consumption calculated from the IPD matrix and Item BOM.

The production controller already owns the stock lifecycle:

* submit reduces ``grn_deliverables`` from the supplier warehouse and adds the
  same quantities to Work Order Deliverable ``stock_update``;
* cancel recreates that stock and subtracts the quantities from
  ``stock_update``.

This hook supplies the missing fabric-specific ``grn_deliverables`` rows before
those controller methods run. Physical cloth rows may represent several final
colour routes, so their hidden Work Order Receivable allocations are scaled to
the actual receipt before the IPD engine is called.
"""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_step
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	scale_reference_allocations,
)


def before_validate(doc, method=None):
	"""Replace the generic same-item calculation for an eligible fabric GRN."""
	if not _is_calculable_fabric_grn(doc):
		return

	wo = frappe.get_cached_doc("Work Order", doc.against_id)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	step = get_fabric_step(ipd, wo.process_name)

	from essdee_yrp.fabric_ipd import get_identity_process_row

	identity_row = None if step else get_identity_process_row(ipd, wo.process_name)
	if not step and not identity_row:
		return

	demands = _get_output_demands(doc, wo)
	if not demands:
		doc.set("grn_deliverables", [])
		return

	rows = _calculate_consumed_rows(
		ipd,
		wo.process_name,
		demands,
		identity=bool(identity_row),
	)
	doc.set("grn_deliverables", _to_grn_deliverables(rows, wo))


def on_submit(doc, method=None):
	_apply_consumption(doc, cancel=False)


def on_cancel(doc, method=None):
	_apply_consumption(doc, cancel=True)


def _is_calculable_fabric_grn(grn):
	# A Cutting LaySheet supplies its actual cloth/accessory consumption. Replacing
	# those rows with the standard IPD matrix would lose the weighed cutting data.
	if grn.flags.get("from_cls"):
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
	wo = frappe.get_cached_doc("Work Order", grn.against_id)
	return bool(wo.get("production_detail") and wo.get("process_name"))


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
				"attrs": physical_attrs,
				"qty": actual_qty,
				"item_variant": row.item_variant,
				"reference_item_variant": reference,
			}
		)
	return demands


def _calculate_consumed_rows(ipd, process_name, demands, identity=False):
	"""Return matrix principal inputs plus Item BOM process consumables."""
	rows = []
	if identity:
		for demand in demands:
			parent_item = frappe.db.get_value("Item Variant", demand["item_variant"], "item")
			rows.append(
				{
					"item_variant": demand["item_variant"],
					"qty": demand["qty"],
					"uom": frappe.db.get_value("Item", parent_item, "default_unit_of_measure"),
					"reference_item_variant": demand.get("reference_item_variant"),
				}
			)
	else:
		from yrp.yrp.utils.ipd_engine import get_process_io

		for input_row in get_process_io(ipd.name, process_name, demands)["inputs"]:
			rows.append(
				{
					"item_variant": _resolve_variant(input_row["item"], input_row.get("attrs") or {}),
					"qty": input_row["qty"],
					"uom": input_row.get("uom"),
					"reference_item_variant": input_row.get("reference_item_variant"),
				}
			)

	# Item BOM calculation is deliberately per reference demand. That retains
	# the route split for attribute-mapped BOM rows and for consolidated
	# physical inputs shared by several finished colours.
	from yrp.yrp.utils.ipd_engine import get_consumables

	for demand in demands:
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
					"item_variant": _resolve_variant(bom_row["item"], bom_row.get("attrs") or {}),
					"qty": bom_row["qty"],
					"uom": bom_row.get("uom")
					or frappe.db.get_value("Item", bom_row["item"], "default_unit_of_measure"),
					"reference_item_variant": reference,
				}
			)
	return _aggregate_rows(rows)


def _aggregate_rows(rows):
	aggregated = {}
	for row in rows:
		key = (row["item_variant"], row.get("uom"))
		if key not in aggregated:
			aggregated[key] = {
				"item_variant": row["item_variant"],
				"qty": 0.0,
				"uom": row.get("uom"),
			}
		aggregated[key]["qty"] += flt(row.get("qty"))
	return [
		{
			**row,
			"qty": flt(row["qty"], 3),
		}
		for row in aggregated.values()
		if flt(row["qty"]) > 0
	]


def _to_grn_deliverables(rows, wo):
	planned = {}
	for row in wo.get("deliverables") or []:
		if not row.get("is_calculated"):
			continue
		planned.setdefault((row.item_variant, row.uom), row)

	result = []
	for row in rows:
		source = planned.get((row["item_variant"], row.get("uom")))
		if not source:
			frappe.throw(
				_(
					"Calculated consumed item {0} ({1}) is not present in Work "
					"Order {2} Deliverables. Recalculate the draft Work Order "
					"from its fabric program before creating this GRN."
				).format(row["item_variant"], row.get("uom") or "", wo.name)
			)
		result.append(
			{
				"item_variant": row["item_variant"],
				"quantity": row["qty"],
				"uom": row.get("uom"),
				"work_order_deliverable": source.name,
				"lot": source.get("lot") or wo.get("lot"),
				"received_type": source.get("received_type")
				or frappe.db.get_single_value("YRP Stock Settings", "default_received_type"),
				"valuation_rate": flt(source.get("valuation_rate") or source.get("rate")),
				"set_combination": {},
				**_stock_uom_values(row["item_variant"], row.get("uom"), row["qty"]),
			}
		)
	return result


def _stock_uom_values(item_variant, uom, qty):
	from yrp.stock.utils import get_conversion_factor

	values = get_conversion_factor(item_variant, uom)
	conversion_factor = flt(values.get("conversion_factor")) or 1
	return {
		"conversion_factor": conversion_factor,
		"stock_uom": values.get("stock_uom") or uom,
		"stock_qty": flt(flt(qty) * conversion_factor, 3),
	}


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
		combined = [
			source
			for source in candidates
			if _normal_json(source.get("set_combination")) == row_combination
		]
		if combined:
			candidates = combined

	for fieldname in ("lot", "received_type"):
		value = row.get(fieldname)
		if not value:
			continue
		dimension_matches = [
			source for source in candidates if source.get(fieldname) == value
		]
		if dimension_matches:
			candidates = dimension_matches

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
