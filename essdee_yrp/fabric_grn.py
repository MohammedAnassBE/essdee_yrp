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
from frappe.utils import cint, flt
from yrp.attribute_links import value as _attribute_value
from yrp.stock.shortage import get_stock_qty_precision, get_stock_shortage
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import get_dia_attribute
from essdee_yrp.fabric_chain import get_fabric_step
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	scale_reference_allocations,
)

QTY_TOLERANCE = 0.000001


@frappe.whitelist()
def get_actual_dia_context(work_order):
	"""Return the server-owned Actual Dia choices for Default Knitting."""
	if not work_order or not frappe.db.exists("YRP Work Order", work_order):
		return {"enabled": False, "dia_options": []}
	wo = frappe.get_doc("YRP Work Order", work_order)
	wo.check_permission("read")
	default_knitting = frappe.db.get_single_value(
		"SD YRP IPD Settings", "default_knitting_process"
	)
	enabled = bool(
		wo.get("production_detail")
		and wo.get("process_name")
		and wo.get("process_name") == default_knitting
	)
	return {
		"enabled": enabled,
		"attribute": get_dia_attribute(),
		"dia_options": _configured_dia_values() if enabled else [],
	}


def _configured_dia_values():
	return frappe.get_all(
		"Item Attribute Value",
		filters={"parent": get_dia_attribute()},
		order_by="idx asc, name asc",
		pluck="attribute_value",
	)


def get_saved_actual_dia_rows(grn, work_order, *, planned_rows=()):
	"""Restore saved physical quantities and their UOM basis for draft display."""
	receivables = {row.name: row for row in work_order.get("receivables") or []}
	planned = {
		(row.get("ref_docname"), row.get("received_type")): row for row in planned_rows
	}
	rows = []
	for row in grn.get("items") or []:
		source = receivables.get(row.get("ref_docname"))
		if not source or row.get("item_variant") == source.item_variant:
			continue
		payload = row.as_dict() if callable(getattr(row, "as_dict", None)) else dict(row)
		display = planned.get((row.get("ref_docname"), row.get("received_type")))
		if not payload.get("secondary_uom"):
			payload["secondary_uom"] = (display if display is not None else source).get("secondary_uom")
		elif display is not None and not display.get("secondary_uom") and not flt(payload.get("secondary_qty")):
			# Base draft rows omit secondary UOM. Hide an unused saved label to
			# match them, but retain the UOM of any entered secondary quantity.
			payload["secondary_uom"] = display.get("secondary_uom")
		payload["pending_quantity"] = flt(source.pending_quantity)
		payload["max_receivable_quantity"] = None
		payload["rate"] = flt(source.cost)
		rows.append(payload)
	return rows


def validate_actual_dia_rows(grn):
	"""Permit only Dia to vary from a Default Knitting receivable."""
	if (
		grn.get("against") != "YRP Work Order"
		or not grn.get("against_id")
		or not frappe.db.exists("YRP Work Order", grn.against_id)
	):
		return
	wo = frappe.get_doc("YRP Work Order", grn.against_id)
	receivables = {row.name: row for row in wo.get("receivables") or []}
	default_knitting = frappe.db.get_single_value(
		"SD YRP IPD Settings", "default_knitting_process"
	)
	actual_dia_enabled = bool(
		wo.get("production_detail")
		and is_calculable_fabric_grn(grn)
		and wo.get("process_name") == default_knitting
	)
	for row in grn.get("items") or []:
		source = receivables.get(row.get("ref_docname"))
		if not source or row.get("item_variant") == source.item_variant:
			continue
		if not actual_dia_enabled:
			frappe.throw(
				_(
					"Row {0}: Actual Dia variance is allowed only on a standard GRN "
					"for the Default Knitting Process."
				).format(row.idx)
			)
		validate_actual_dia_variant(source.item_variant, row.item_variant, row.idx)
	if actual_dia_enabled:
		_normalize_actual_dia_row_indexes(grn, receivables)


def validate_actual_dia_variant(planned_item, actual_item, row_index):
	"""Keep the template and every non-Dia attribute fixed."""
	expected_parent = get_parent_item(planned_item)
	actual_parent = get_parent_item(actual_item)
	if not expected_parent or actual_parent != expected_parent:
		frappe.throw(
			_("Row {0}: Actual Dia must remain on item template {1}.").format(
				row_index, expected_parent
			)
		)
	expected_attrs = _variant_attrs(planned_item)
	actual_attrs = _variant_attrs(actual_item)
	if not actual_attrs.get(get_dia_attribute()):
		frappe.throw(_("Row {0}: Actual Dia is required.").format(row_index))
	_validate_non_dia_attributes(expected_attrs, actual_attrs, row_index)
	valid_dias = set(_configured_dia_values())
	if actual_attrs[get_dia_attribute()] not in valid_dias:
		frappe.throw(
			_("Row {0}: {1} is not a valid Dia value.").format(
				row_index, actual_attrs[get_dia_attribute()]
			)
		)
	if not expected_attrs.get(get_dia_attribute()):
		frappe.throw(_("Row {0}: planned Item has no Dia.").format(row_index))


def _validate_non_dia_attributes(expected_attrs, actual_attrs, row_index):
	for attribute in set(expected_attrs) | set(actual_attrs):
		if attribute == get_dia_attribute():
			continue
		if expected_attrs.get(attribute) != actual_attrs.get(attribute):
			frappe.throw(
				_(
					"Row {0}: only Dia may differ from the Work Order receivable; {1} changed."
				).format(row_index, attribute)
			)


def _normalize_actual_dia_row_indexes(grn, receivables):
	"""Give each receivable/physical Item pair a stable Desk grouping row."""
	rows = grn.get("items") or []
	reserved = {
		str(row.get("row_index"))
		for row in rows
		if (
			row.get("ref_docname") not in receivables or not row.get("item_variant")
		)
		and row.get("row_index") not in (None, "")
	}
	indexes = {}
	next_index = 0
	for row in rows:
		if row.get("ref_docname") not in receivables or not row.get("item_variant"):
			continue
		key = (row.ref_docname, row.item_variant)
		if key not in indexes:
			while str(next_index) in reserved:
				next_index += 1
			indexes[key] = str(next_index)
			reserved.add(str(next_index))
			next_index += 1
		row.row_index = indexes[key]


def before_validate(doc, method=None):
	"""Keep a draft preview; submit recalculates under the Work Order lock."""
	if not is_calculable_fabric_grn(doc):
		return
	populate_grn_deliverables(doc, calculate_consumption_plan(doc))


def on_submit(doc, method=None):
	_apply_consumption(doc, cancel=False)
	from essdee_yrp.fabric_substitution import rebuild_lot_fabric_conversions_for_grn

	rebuild_lot_fabric_conversions_for_grn(doc)


def on_cancel(doc, method=None):
	_apply_consumption(doc, cancel=True)
	from essdee_yrp.fabric_substitution import rebuild_lot_fabric_conversions_for_grn

	rebuild_lot_fabric_conversions_for_grn(doc)


def is_calculable_fabric_grn(grn):
	# A Cutting LaySheet supplies its actual cloth/accessory consumption. Replacing
	# those rows with the standard IPD matrix would lose the weighed cutting data.
	if grn.flags.get("from_cls") or grn.get("cutting_laysheet"):
		return False
	if grn.get("against") != "YRP Work Order" or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
	):
		return False
	if not frappe.db.exists("YRP Work Order", grn.against_id):
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
	wo = frappe.get_cached_doc("YRP Work Order", grn.against_id)
	return bool(wo.get("production_detail") and wo.get("process_name"))


# Backwards-compatible import used by the existing focused tests.
_is_calculable_fabric_grn = is_calculable_fabric_grn


def calculate_consumption_plan(grn, work_order_doc=None):
	"""Return exact, stock-UOM-normalized inputs for each positive output row."""
	if not is_calculable_fabric_grn(grn):
		return []

	wo = work_order_doc or frappe.get_doc("YRP Work Order", grn.against_id)
	ipd = frappe.get_cached_doc("YRP Item Production Detail", wo.production_detail)
	step = get_fabric_step(ipd, wo.process_name)

	from essdee_yrp.fabric_ipd import get_identity_process_row

	identity_row = None if step else get_identity_process_row(ipd, wo.process_name)
	if not step and not identity_row:
		return []

	demands = _get_output_demands(grn, wo)
	if not demands:
		return []
	rows = _calculate_saved_execution_inputs(wo, demands)
	if rows is None and step and cint(wo.get("cloth_execution_version")) == 1:
		from essdee_yrp.api.work_order import _step_kind

		if _step_kind(ipd, step) == "knitting":
			rows = _calculate_saved_work_order_inputs(wo, demands)
	if rows is None:
		rows = _calculate_consumed_rows(
			ipd,
			wo.process_name,
			demands,
			identity=bool(identity_row or (step and step.get("shape") == "identity")),
		)
		rows = _align_cloth_input_rounding(
			rows,
			wo,
			ipd,
			identity=bool(identity_row or (step and step.get("shape") == "identity")),
		)
	return _allocate_to_work_order_deliverables(rows, wo, grn)


def _align_cloth_input_rounding(rows, wo, ipd, *, identity=False):
	"""Use the WO's three-decimal input allocation for fractional cloth recipes.

	Only reconcile rounding-sized differences against the full planned output.
	Never clamp to stock currently available: genuine under-deliveries must
	still fail allocation. Scaling by the full plan also makes partial GRNs
	consume the same total as a single full receipt.
	"""
	if not ipd.get("is_cloth_item"):
		return rows
	planned_grn = frappe._dict(
		items=[
			frappe._dict(
				name=row.name,
				ref_docname=row.name,
				item_variant=row.item_variant,
				quantity=row.qty,
			)
			for row in wo.get("receivables") or []
		]
	)
	full_rows = _calculate_consumed_rows(
		ipd,
		wo.process_name,
		_get_output_demands(planned_grn, wo),
		identity=identity,
	)

	def key(row, reference):
		return (row.get("item_variant"), row.get("uom"), reference or "")

	expected, counts, planned = {}, {}, {}
	for row in full_rows:
		k = key(row, row.get("reference_item_variant"))
		expected[k] = expected.get(k, 0) + flt(row.get("qty"))
		counts[k] = counts.get(k, 0) + 1
	for row in wo.get("deliverables") or []:
		if not row.get("is_calculated"):
			continue
		allocations = get_reference_allocations(row, row.qty) or {"": flt(row.qty)}
		for reference, qty in allocations.items():
			k = key(row, reference)
			planned[k] = planned.get(k, 0) + flt(qty)
	result = []
	for row in rows:
		k = key(row, row.get("reference_item_variant"))
		full = expected.get(k, 0)
		target = planned.get(k)
		if full > 0 and target is not None and target > 0 and abs(target - full) <= counts[k] * 0.000500001:
			row = {**row, "qty": flt(flt(row["qty"]) * target / full, 6)}
		result.append(row)
	return result


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
		from essdee_yrp.cloth_execution import get_row_execution_parameters

		reference = (
			next(iter(actual_allocations))
			if len(actual_allocations) == 1
			else source.get("fabric_reference_variant")
		)
		demands.append(
			{
				"goods_received_note_item": row.name,
				"received_item_variant": row.item_variant,
				"attrs": physical_attrs,
				"qty": actual_qty,
				"item_variant": row.item_variant,
				"reference_item_variant": reference,
				"reference_allocations": actual_allocations,
				"execution_key": get_row_execution_parameters(source).get(
					"fabric_execution_key"
				),
			}
		)
	return demands


def _route_demands(demand):
	"""Expose costing routes without multiplying the physical GRN output."""
	allocations = demand.get("reference_allocations") or {}
	if not allocations:
		return [demand]
	return [
		{
			**demand,
			"qty": flt(qty),
			"reference_item_variant": reference,
		}
		for reference, qty in allocations.items()
		if flt(qty) > 0
	]


def _calculate_saved_execution_inputs(wo, demands):
	"""Scale the exact saved execution inputs for each physical output row."""
	from essdee_yrp.cloth_execution import get_row_execution_parameters

	outputs = defaultdict(float)
	for row in wo.get("receivables") or []:
		key = get_row_execution_parameters(row).get("fabric_execution_key")
		if key:
			outputs[key] += flt(row.qty)
	inputs = defaultdict(list)
	for row in wo.get("deliverables") or []:
		key = get_row_execution_parameters(row).get("fabric_execution_key")
		if key and row.get("is_calculated"):
			inputs[key].append(
				{
					"work_order_deliverable": row.name,
					"item_variant": row.item_variant,
					"qty": flt(row.qty),
					"remaining_qty": max(flt(row.qty) - flt(row.stock_update), 0),
					"uom": row.uom,
				}
			)
	if not demands:
		return []
	for demand in demands:
		key = demand.get("execution_key")
		if not key or flt(outputs.get(key)) <= 0 or not inputs.get(key):
			return None
	rows = []
	for demand in demands:
		key = demand["execution_key"]
		factor = flt(demand["qty"]) / flt(outputs[key])
		for source in inputs[key]:
			quantity = min(
				flt(source["qty"] * factor, 6), flt(source["remaining_qty"])
			)
			if quantity <= QTY_TOLERANCE:
				continue
			source["remaining_qty"] -= quantity
			rows.append(
				{
					"goods_received_note_item": demand["goods_received_note_item"],
					"received_item_variant": demand["received_item_variant"],
					"reference_item_variant": demand.get("reference_item_variant"),
					"work_order_deliverable": source["work_order_deliverable"],
					"item_variant": source["item_variant"],
					"qty": flt(quantity, 6),
					"uom": source["uom"],
				}
			)
	return _aggregate_rows(rows)


def _calculate_saved_work_order_inputs(wo, demands):
	"""Scale a saved Knitting WO route contract for partial Actual-Dia GRNs."""
	outputs = defaultdict(float)
	for row in wo.get("receivables") or []:
		for reference, qty in get_reference_allocations(row, row.qty).items():
			outputs[reference] += flt(qty)
	inputs = defaultdict(list)
	for row in wo.get("deliverables") or []:
		if not row.get("is_calculated"):
			continue
		for reference, qty in get_reference_allocations(row, row.qty).items():
			if flt(qty) > 0:
				inputs[reference].append(
					{
						"work_order_deliverable": row.name,
						"item_variant": row.item_variant,
						"qty": flt(qty),
						"remaining_qty": max(
							flt(qty)
							- flt(row.stock_update)
							* flt(qty)
							/ (flt(row.qty) or flt(qty)),
							0,
						),
						"uom": row.uom,
					}
				)
	if not demands:
		return []
	for physical in demands:
		for demand in _route_demands(physical):
			reference = demand.get("reference_item_variant")
			if not reference or flt(outputs.get(reference)) <= 0 or not inputs.get(reference):
				return None
	rows = []
	for physical in demands:
		for demand in _route_demands(physical):
			reference = demand["reference_item_variant"]
			factor = flt(demand["qty"]) / flt(outputs[reference])
			for source in inputs[reference]:
				quantity = min(
					flt(source["qty"] * factor, 6), flt(source["remaining_qty"])
				)
				if quantity <= QTY_TOLERANCE:
					continue
				source["remaining_qty"] -= quantity
				rows.append(
					{
						"goods_received_note_item": demand["goods_received_note_item"],
						"received_item_variant": demand["received_item_variant"],
						"reference_item_variant": reference,
						"work_order_deliverable": source["work_order_deliverable"],
						"item_variant": source["item_variant"],
						"qty": flt(quantity, 6),
						"uom": source["uom"],
					}
				)
	return _aggregate_rows(rows)


def _calculate_consumed_rows(ipd, process_name, demands, identity=False):
	"""Return matrix principal inputs plus Item BOM process consumables."""
	from yrp.yrp.utils.ipd_engine import get_consumables, get_process_io

	rows = []
	for physical_demand in demands:
		for demand in _route_demands(physical_demand):
			mapping = {
				"goods_received_note_item": demand["goods_received_note_item"],
				"received_item_variant": demand["received_item_variant"],
				"reference_item_variant": demand.get("reference_item_variant"),
			}
			if identity:
				parent_item = get_parent_item(demand["item_variant"])
				rows.append(
					{
						**mapping,
						"item_variant": demand["item_variant"],
						"qty": demand["qty"],
						"uom": frappe.db.get_value("Item", parent_item, "stock_uom"),
					}
				)
			else:
				# Calculate each output separately so exact valuation lineage survives.
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

			# BOM calculation is per route demand without duplicating physical stock.
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
						"item_variant": _resolve_variant(
							bom_row["item"], bom_row.get("attrs") or {}
						),
						"qty": bom_row["qty"],
						"uom": bom_row.get("uom")
						or frappe.db.get_value("Item", bom_row["item"], "stock_uom"),
					}
				)
	return _aggregate_rows(rows)


def _aggregate_rows(rows):
	aggregated = {}
	for row in rows:
		key = (
			row["goods_received_note_item"],
			row.get("work_order_deliverable"),
			row["item_variant"],
			row.get("uom"),
			row.get("reference_item_variant"),
		)
		if key not in aggregated:
			aggregated[key] = {
				"goods_received_note_item": row["goods_received_note_item"],
				"received_item_variant": row["received_item_variant"],
				"work_order_deliverable": row.get("work_order_deliverable"),
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


def _allocate_to_work_order_deliverables(rows, wo, grn, *, exact_business_key=False):
	"""Allocate each exact input demand to its Work Order input rows.

	Delivered-and-unconsumed quantity is taken first. Like Production API, any
	remainder is still consumed from the preferred matching row; the gate is the
	supplier's stock balance, checked once for the whole GRN.
	"""
	from yrp.stock.utils import get_conversion_factor

	sources = _work_order_input_sources(wo)
	stock_cache = {}
	plan = []
	missing = []
	for required in rows:
		conversion = get_conversion_factor(required["item_variant"], required.get("uom"))
		remaining_stock_qty = flt(required["qty"]) * (flt(conversion.get("conversion_factor")) or 1)
		candidates = _matching_input_sources(sources, required, wo, exact_business_key)
		if not candidates:
			missing.append(required["item_variant"])
			continue
		for source in candidates:
			take_stock_qty = min(remaining_stock_qty, flt(source["available_stock_qty"]))
			if take_stock_qty <= QTY_TOLERANCE:
				continue
			plan.append(_input_plan_row(required, source, take_stock_qty, grn, stock_cache))
			source["available_stock_qty"] -= take_stock_qty
			remaining_stock_qty -= take_stock_qty
		if remaining_stock_qty > QTY_TOLERANCE:
			plan.append(_input_plan_row(required, candidates[0], remaining_stock_qty, grn, stock_cache))
	if missing:
		frappe.throw(
			_("Work Order {0} has no input row for {1}, which the Item Production Detail requires.").format(
				wo.name, ", ".join(sorted(set(missing)))
			),
			title=_("Input Not On Work Order"),
		)
	if not (getattr(grn, "flags", None) or {}).get("skip_input_stock_check"):
		validate_supplier_input_stock(wo, grn, plan, stock_cache)
	return plan


def _work_order_input_sources(wo):
	from yrp.stock.utils import get_conversion_factor
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

	from essdee_yrp.fabric_reference import get_reference_allocations

	sources = []
	for deliverable in wo.get("deliverables") or []:
		if not deliverable.get("is_calculated"):
			continue
		conversion = get_conversion_factor(deliverable.item_variant, deliverable.uom)
		factor = flt(conversion.get("conversion_factor")) or 1
		delivered_qty = flt(deliverable.qty) - flt(deliverable.pending_quantity)
		available_qty = max(delivered_qty - flt(deliverable.stock_update), 0)
		sources.append(
			{
				"row": deliverable,
				"factor": factor,
				"stock_uom": conversion.get("stock_uom") or deliverable.uom,
				"available_stock_qty": available_qty * factor,
				"dimensions": _stock_dimension_values(wo, deliverable),
				"references": set(get_reference_allocations(deliverable, deliverable.qty)),
			}
		)
	return sources


def _matching_input_sources(sources, required, wo, exact_business_key):
	"""Return the Work Order input rows for one demand, preferred row first."""
	reference = required.get("reference_item_variant")
	exact_deliverable = required.get("work_order_deliverable")
	candidates = [
		item
		for item in sources
		if item["row"].item_variant == required["item_variant"]
		and (not exact_deliverable or item["row"].name == exact_deliverable)
	]
	if required.get("uom"):
		candidates = [item for item in candidates if item["row"].uom == required["uom"]]
	if "set_combination" in required:
		from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

		required_combination = _normal_json(required.get("set_combination"))
		candidates = [
			item
			for item in candidates
			if _normal_json(item["row"].get("set_combination")) == required_combination
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
	return candidates


def _input_plan_row(required, source, stock_qty, grn, stock_cache):
	row = source["row"]
	dimensions = source["dimensions"]
	_balance, valuation_rate = _supplier_stock(required["item_variant"], dimensions, grn, stock_cache)
	return {
		"goods_received_note_item": required["goods_received_note_item"],
		"received_item_variant": required["received_item_variant"],
		"work_order_deliverable": row.name,
		"item_variant": required["item_variant"],
		"quantity": stock_qty / source["factor"],
		"stock_qty": stock_qty,
		"uom": row.uom,
		"stock_uom": source["stock_uom"],
		"conversion_factor": source["factor"],
		"valuation_rate": flt(row.valuation_rate or row.rate or valuation_rate),
		"dimensions": dimensions,
		"set_combination": row.get("set_combination") or {},
	}


def _supplier_stock(item_variant, dimensions, grn, stock_cache):
	"""Return the cached supplier (balance, valuation rate) for one bucket."""
	from yrp.stock.utils import get_stock_balance

	key = (item_variant, grn.from_warehouse, tuple(sorted(dimensions.items())))
	if key not in stock_cache:
		stock_cache[key] = get_stock_balance(
			item_variant,
			grn.from_warehouse,
			posting_date=grn.posting_date,
			posting_time=grn.posting_time,
			with_valuation_rate=True,
			**dimensions,
		)
	return stock_cache[key]


def validate_supplier_input_stock(wo, grn, plan, stock_cache):
	"""Reject the GRN when the supplier lacks stock for its consumed inputs.

	Mirrors Production API's ``validate_deliverable_stock``: one line per
	short item and stock bucket.
	"""
	need = defaultdict(float)
	for item in plan:
		key = (item["item_variant"], tuple(sorted(item["dimensions"].items())))
		need[key] += flt(item["stock_qty"])
	precision = get_stock_qty_precision()
	lines = []
	for key, required_qty in need.items():
		item_variant, dimensions = key
		balance = flt(_supplier_stock(item_variant, dict(dimensions), grn, stock_cache)[0])
		shortage = get_stock_shortage(balance, required_qty, precision)
		if not shortage:
			continue
		lines.append(
			_("{0} - Need: {1}, Stock: {2}, Short: {3}").format(
				item_variant,
				f"{flt(required_qty, precision):g}",
				f"{flt(balance, precision):g}",
				f"{shortage:g}",
			)
		)
	if lines:
		frappe.throw("<br>".join(lines), title=_("Not enough stock"))


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


def apply_work_order_stock_update(work_order, plan, cancel=False, work_order_doc=None):
	"""Apply mapped input quantities exactly once to their Work Order rows."""
	if not plan:
		return
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		_update_work_order_status,
	)

	rows = {
		row.name: row
		for row in (work_order_doc or frappe.get_doc("YRP Work Order", work_order)).get("deliverables") or []
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
				_("Work Order Deliverable {0} no longer exists on {1}.").format(row_name, work_order)
			)
		current = flt(row.stock_update)
		if cancel and current + QTY_TOLERANCE < qty:
			frappe.throw(_("Consumed stock audit mismatch for Work Order Deliverable {0}.").format(row_name))
		new_value = current - qty if cancel else current + qty
		frappe.db.set_value(
			"YRP Work Order Deliverables",
			row_name,
			"stock_update",
			flt(max(new_value, 0), 6),
			update_modified=False,
		)
	_update_work_order_status(work_order)


def _apply_consumption(grn, cancel=False):
	if grn.get("against") != "YRP Work Order" or not grn.get("against_id") or not grn.get("grn_deliverables"):
		return
	from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
		has_mapped_grn_deliverables,
	)

	if has_mapped_grn_deliverables(grn):
		return

	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.stock.stock_ledger import make_sl_entries
	from yrp.stock.utils import get_stock_balance
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		_update_work_order_status,
	)

	frappe.db.get_value("YRP Work Order", grn.against_id, "name", for_update=True)
	wo = frappe.get_doc("YRP Work Order", grn.against_id)
	deliverables = {row.name: row for row in wo.get("deliverables") or []}
	dimension_fields = get_dimension_fieldnames()
	entries = []
	updates = {}
	# Rows generated by the F16 fabric engine carry an explicit deliverable link
	# and must remain strict. Historical production_api rows (notably packing
	# GRNs) predate that link and can legitimately consume stock variants that
	# are not themselves Work Order Deliverables; those are stock-only rows.
	has_explicit_links = any(row.get("work_order_deliverable") for row in grn.grn_deliverables)

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
		if source.item_variant == row.item_variant and (not row.get("uom") or source.uom == row.uom)
	]
	if len(candidates) == 1:
		return candidates[0]

	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json

	row_combination = _normal_json(row.get("set_combination"))
	if row_combination not in (None, "", "{}", {}):
		candidates = [
			source for source in candidates if _normal_json(source.get("set_combination")) == row_combination
		]

	for fieldname in ("lot", "received_type"):
		value = row.get(fieldname)
		if not value:
			continue
		candidates = [source for source in candidates if source.get(fieldname) == value]

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
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _normal_json
	from yrp.yrp.doctype.yrp_work_order.yrp_work_order import _stock_dimension_values

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
		except TypeError, ValueError:
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
			_("Migrated consumed row {0} does not match linked Work Order Deliverable {1}: {2}.").format(
				row.item_variant, source.name, ", ".join(mismatched)
			)
		)


def _variant_attrs(item_variant):
	if not item_variant:
		return {}
	return {
		row.attribute: _attribute_value(row.attribute_value)
		for row in frappe.get_all(
			"Item Variant Attribute",
			filters={
				"parent": item_variant,
				"parenttype": "Item",
			},
			fields=["attribute", "attribute_value"],
		)
	}


def _resolve_variant(item, attrs):
	from essdee_yrp.api.work_order import _resolve_variant

	return _resolve_variant(item, attrs)
