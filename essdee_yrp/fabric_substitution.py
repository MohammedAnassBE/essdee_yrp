# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Default-Knitting GRN driven physical Actual-Dia projection.

The Lot table stores only planned physical Knitting item, actual physical item,
and effective Accepted quantity. Colour routes are applied on demand by later
Work Order calculations; exact GRN/SLE rows remain authoritative for stock,
warehouse, valuation and Inspection lineage.
"""

from collections import defaultdict
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_steps
from essdee_yrp.fabric_ipd import FABRIC_DIA_ATTRIBUTE
QTY_TOLERANCE = 0.000001
ELIGIBLE_RECEIVED_TYPE = "Accepted"


def get_planned_knitting_output_totals(
	lot_doc, production_detail, cloth_item
):
	"""Sum the saved Cloth Program by physical Knitting output variant.

	Colour routes remain separate in the program because later processes need
	them, but routes with the same Knitting Dia/Colour share one physical output
	and therefore one denominator for Actual-Dia factors.
	"""
	fabric_matches = [
		row for row in lot_doc.get("lot_fabric_details") or []
		if row.get("production_detail") == production_detail
		and row.get("cloth_item") == cloth_item
	]
	if not fabric_matches:
		return {}

	from essdee_yrp.api.work_order import _resolve_variant
	from essdee_yrp.fabric_program import (
		get_fabric_routes,
		get_knitting_output_colour,
	)

	ipd = frappe.get_cached_doc("Item Production Detail", production_detail)
	routes = get_fabric_routes(ipd)
	totals = defaultdict(float)
	for row in lot_doc.get("lot_fabric_programs") or []:
		if row.get("cloth_item") != cloth_item or flt(row.get("weight")) <= 0:
			continue
		final_attrs = {}
		if row.get("reference_item_variant"):
			final_attrs = _variant_state(row.reference_item_variant)["attrs"]
		final_dia = final_attrs.get(FABRIC_DIA_ATTRIBUTE) or row.get("dia")
		final_colour = final_attrs.get("Colour") or row.get("colour")
		route = next((
			candidate for candidate in routes
			if candidate["finished_dia"] == final_dia
			and candidate["finished_colour"] == final_colour
		), None)
		physical_dia = (
			route and route.get("knitting_output_dia")
		) or row.get("dia")
		colour = (
			route and route.get("knitting_output_colour")
		) or get_knitting_output_colour(ipd, final_colour, final_dia)
		attrs = {FABRIC_DIA_ATTRIBUTE: physical_dia}
		if colour:
			attrs["Colour"] = colour
		variant = _resolve_variant(cloth_item, attrs)
		totals[variant] += flt(row.get("weight"), 6)
	return {
		variant: flt(qty, 6)
		for variant, qty in totals.items()
		if flt(qty) > QTY_TOLERANCE
	}


def get_default_knitting_grn_context(grn):
	"""Return the exact Lot/IPD context when ``grn`` owns this projection."""
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return None
	if any(
		grn.get(fieldname)
		for fieldname in ("is_return", "is_rework", "includes_packing")
	):
		return None
	default_process = frappe.db.get_single_value(
		"IPD Settings", "default_knitting_process"
	)
	if not default_process:
		return None
	work_order = frappe.db.get_value(
		"Work Order",
		grn.against_id,
		["name", "lot", "process_name", "production_detail", "item"],
		as_dict=True,
	)
	if not work_order or not work_order.lot:
		return None
	if work_order.process_name != default_process:
		return None
	production_detail = work_order.production_detail
	if not production_detail:
		candidates = frappe.get_all(
			"Lot Fabric Detail",
			filters={
				"parent": work_order.lot,
				"parenttype": "Lot",
				"parentfield": "lot_fabric_details",
				"cloth_item": work_order.item,
				"production_detail": ["is", "set"],
			},
			pluck="production_detail",
		)
		candidates = list(dict.fromkeys(candidates))
		if len(candidates) != 1:
			return None
		production_detail = candidates[0]
	return frappe._dict({
		"lot": work_order.lot,
		"process_name": default_process,
		"production_detail": production_detail,
		"cloth_item": work_order.item,
	})


def lock_lot_for_fabric_grn(grn):
	"""Match fabric tracking's gate and lock its Lot before the GRN parent."""
	if grn.flags.get("essdee_fabric_tracking_lot"):
		return grn.flags.essdee_fabric_tracking_lot
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return None
	if grn.get("is_rework") or grn.get("is_return"):
		return None
	work_order = frappe.db.get_value(
		"Work Order", grn.against_id, ["lot"], as_dict=True
	)
	if not work_order or not work_order.lot:
		return None
	frappe.db.sql(
		"SELECT name FROM `tabLot` WHERE name = %s FOR UPDATE",
		(work_order.lot,),
	)
	grn.flags.essdee_fabric_tracking_lot = work_order.lot
	return work_order.lot


def lock_lot_for_default_knitting_grn(grn):
	"""Lock tracking for every fabric GRN and mark conversion-owned Lots."""
	lot = lock_lot_for_fabric_grn(grn)
	if not lot:
		return None
	if grn.flags.get("essdee_fabric_conversion_lot"):
		return grn.flags.essdee_fabric_conversion_lot
	context = get_default_knitting_grn_context(grn)
	if not context:
		return None
	grn.flags.essdee_fabric_conversion_lot = context.lot
	return context.lot


def lock_lots_for_default_knitting_grns(grn_names):
	"""Lock affected conversion Lots before Inspection touches source GRNs."""
	grn_names = sorted(set(grn_names or []))
	if not grn_names:
		return []
	default_process = frappe.db.get_single_value(
		"IPD Settings", "default_knitting_process"
	)
	if not default_process:
		return []
	optional_conditions = []
	for fieldname in ("is_return", "is_rework", "includes_packing"):
		if frappe.db.has_column("Goods Received Note", fieldname):
			optional_conditions.append(f"AND IFNULL(grn.`{fieldname}`, 0) = 0")
	lots = frappe.db.sql(
		f"""
		SELECT DISTINCT wo.lot
		FROM `tabGoods Received Note` grn
		JOIN `tabWork Order` wo ON wo.name = grn.against_id
		WHERE grn.name IN %(grn_names)s
			AND grn.docstatus = 1
			AND grn.against = 'Work Order'
			AND wo.process_name = %(process)s
			AND IFNULL(wo.lot, '') != ''
			{' '.join(optional_conditions)}
		ORDER BY wo.lot
		""",
		{"grn_names": tuple(grn_names), "process": default_process},
		pluck="lot",
	)
	if lots:
		frappe.db.sql(
			"SELECT name FROM `tabLot` WHERE name IN %(lots)s "
			"ORDER BY name FOR UPDATE",
			{"lots": tuple(lots)},
		)
	return lots


def rebuild_lot_fabric_conversions_for_grn(grn):
	"""Rebuild after a qualifying GRN completed submit/cancel lifecycle."""
	lot = grn.flags.get("essdee_fabric_conversion_lot")
	already_locked = bool(lot)
	if not lot:
		context = get_default_knitting_grn_context(grn)
		lot = context.lot if context else None
	if not lot:
		return None
	return _rebuild_lot_fabric_conversions(lot, already_locked=already_locked)


@frappe.whitelist()
def rebuild_lot_fabric_conversions(lot):
	"""Permission-checked repair/backfill endpoint for one Lot."""
	lot_doc = frappe.get_doc("Lot", lot)
	lot_doc.check_permission("write")
	return _rebuild_lot_fabric_conversions(lot_doc.name)


def _rebuild_lot_fabric_conversions(lot, *, already_locked=False):
	if not already_locked:
		frappe.db.sql(
			"SELECT name FROM `tabLot` WHERE name = %s FOR UPDATE",
			(lot,),
		)
	default_process = frappe.db.get_single_value(
		"IPD Settings", "default_knitting_process"
	)
	receipts = (
		_fetch_default_knitting_receipts(lot, default_process)
		if default_process else []
	)
	conversion_rows = build_conversion_rows(receipts, default_process)
	_replace_conversion_rows(lot, conversion_rows)
	return {
		"lot": lot,
		"source_receipts": len(receipts),
		"conversions": len(conversion_rows),
	}


def _fetch_default_knitting_receipts(lot, default_process):
	"""Current-read all eligible source rows after deterministic parent locks."""
	if not default_process:
		return []

	optional_conditions = []
	for fieldname in ("is_return", "is_rework", "includes_packing"):
		if frappe.db.has_column("Goods Received Note", fieldname):
			optional_conditions.append(f"AND IFNULL(grn.`{fieldname}`, 0) = 0")
	conditions = "\n".join(optional_conditions)
	# Use current locking reads after the Lot serializer. A request may have
	# waited for a previous conversion writer after an earlier plain read created
	# an old RR snapshot; every value feeding the replacement must see that
	# writer's commit.
	work_orders = frappe.db.sql(
		"""
		SELECT name, production_detail, item
		FROM `tabWork Order`
		WHERE lot = %(lot)s AND process_name = %(process)s
		ORDER BY name
		FOR UPDATE
		""",
		{"lot": lot, "process": default_process},
		as_dict=True,
	)
	fabric_ipds = defaultdict(set)
	for fabric in frappe.db.sql(
		"""
		SELECT cloth_item, production_detail
		FROM `tabLot Fabric Detail`
		WHERE parent = %(lot)s
			AND parenttype = 'Lot'
			AND parentfield = 'lot_fabric_details'
		ORDER BY idx, name
		FOR UPDATE
		""",
		{"lot": lot},
		as_dict=True,
	):
		if fabric.cloth_item and fabric.production_detail:
			fabric_ipds[fabric.cloth_item].add(fabric.production_detail)
	work_order_ipds = {}
	for work_order in work_orders:
		production_detail = work_order.production_detail
		if not production_detail:
			# Resolve legacy WOs created before production_detail when the Lot has
			# one unambiguous cloth IPD. Unrouteable historical rows are skipped;
			# they must not abort current GRNs or the backfill for the whole Lot.
			candidates = fabric_ipds.get(work_order.item) or set()
			if len(candidates) == 1:
				production_detail = next(iter(candidates))
		if production_detail:
			work_order_ipds[work_order.name] = production_detail
	work_order_names = sorted(work_order_ipds)
	if not work_order_names:
		return []
	grn_names = frappe.db.sql(
		f"""
		SELECT grn.name
		FROM `tabGoods Received Note` grn
		WHERE grn.docstatus = 1
			AND grn.against = 'Work Order'
			AND grn.against_id IN %(work_orders)s
			{conditions}
		ORDER BY grn.name
		FOR UPDATE
		""",
		{"work_orders": tuple(work_order_names)},
		pluck="name",
	)
	if not grn_names:
		return []

	has_received_type = frappe.db.has_column(
		"Goods Received Note Item", "received_type"
	)
	has_reference = frappe.db.has_column(
		"Work Order Receivables", "fabric_reference_variant"
	)
	has_allocations = frappe.db.has_column(
		"Work Order Receivables", "fabric_reference_allocations"
	)
	received_type_select = (
		"item.received_type" if has_received_type else "NULL AS received_type"
	)
	reference_select = (
		"receivable.fabric_reference_variant"
		if has_reference else "NULL AS fabric_reference_variant"
	)
	allocation_select = (
		"receivable.fabric_reference_allocations"
		if has_allocations else "NULL AS fabric_reference_allocations"
	)
	rows = frappe.db.sql(
		f"""
		SELECT grn.name AS source_grn,
			item.name AS source_grn_item,
			item.item_variant AS actual_item_variant,
			item.stock_qty,
			item.quantity,
			item.conversion_factor,
			item.uom,
			item.stock_uom,
			{received_type_select},
			wo.name AS source_work_order,
			wo.production_detail,
			wo.item AS cloth_item,
			receivable.item_variant AS planned_item_variant,
			receivable.qty AS planned_qty,
			{reference_select},
			{allocation_select}
		FROM `tabGoods Received Note` grn
		JOIN `tabWork Order` wo ON wo.name = grn.against_id
		JOIN `tabGoods Received Note Item` item
			ON item.parent = grn.name
			AND item.parenttype = 'Goods Received Note'
		JOIN `tabWork Order Receivables` receivable
			ON receivable.name = item.ref_docname
			AND receivable.parent = wo.name
		WHERE grn.name IN %(grn_names)s
			AND item.ref_doctype = 'Work Order Receivables'
		ORDER BY grn.posting_date, grn.posting_time, grn.name, item.idx
		FOR UPDATE
		""",
		{"grn_names": tuple(grn_names)},
		as_dict=True,
	)
	for row in rows:
		row.production_detail = work_order_ipds.get(row.source_work_order)

	from essdee_yrp.fabric_source import _accepted_inspection_adjustments

	inspection_adjustments = _accepted_inspection_adjustments(rows)
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	receipts = []
	for row in rows:
		received_type = row.received_type or default_received_type
		original_stock_qty = flt(row.stock_qty, 6)
		if original_stock_qty <= QTY_TOLERANCE:
			original_stock_qty = (
				flt(row.quantity, 6) * (flt(row.conversion_factor, 6) or 1)
			)
		stock_qty = (
			original_stock_qty
			if received_type == ELIGIBLE_RECEIVED_TYPE else 0
		)
		stock_qty = max(
			stock_qty + flt(
				inspection_adjustments.get(row.source_grn_item), 6
			),
			0,
		)
		if stock_qty <= QTY_TOLERANCE:
			continue
		receipts.append(frappe._dict({
			"source_grn": row.source_grn,
			"source_grn_item": row.source_grn_item,
			"source_work_order": row.source_work_order,
			"production_detail": row.production_detail,
			"cloth_item": row.cloth_item,
			"planned_item_variant": row.planned_item_variant,
			"actual_item_variant": row.actual_item_variant,
			"received_type": ELIGIBLE_RECEIVED_TYPE,
			"stock_uom": row.stock_uom or row.uom,
			"stock_qty": flt(stock_qty, 6),
		}))
	return receipts


def build_conversion_rows(receipts, default_process):
	"""Aggregate the physical planned-Dia -> actual-Dia Accepted projection."""
	grouped = {}
	for row in receipts:
		if (
			(row.received_type or ELIGIBLE_RECEIVED_TYPE) != ELIGIBLE_RECEIVED_TYPE
			or flt(row.stock_qty, 6) <= QTY_TOLERANCE
		):
			continue
		key = (
			row.production_detail,
			row.planned_item_variant,
			row.actual_item_variant,
			ELIGIBLE_RECEIVED_TYPE,
			row.stock_uom or "",
		)
		group = grouped.setdefault(key, {
			"production_detail": row.production_detail,
			"process_name": default_process,
			"from_item": row.planned_item_variant,
			"to_item": row.actual_item_variant,
			"received_type": ELIGIBLE_RECEIVED_TYPE,
			"stock_uom": row.stock_uom,
			"to_qty": 0.0,
			"source_grns": set(),
		})
		group["to_qty"] += flt(row.stock_qty, 6)
		group["source_grns"].add(row.source_grn)

	rows = []
	for value in grouped.values():
		value["to_qty"] = flt(value["to_qty"], 3)
		value["source_grn_count"] = len(value.pop("source_grns"))
		rows.append(value)
	return sorted(rows, key=lambda row: (
		row["production_detail"], row["from_item"], row["to_item"],
	))


def build_actual_dia_factors(rows, planned_qty):
	"""Return uncapped Actual-Dia factors for one planned physical variant."""
	planned_qty = flt(planned_qty, 6)
	if planned_qty <= QTY_TOLERANCE:
		raise ValueError("planned_qty must be greater than zero")
	totals = defaultdict(float)
	for row in rows or []:
		to_item = row.get("to_item")
		qty = flt(row.get("to_qty"), 6)
		if to_item and qty > QTY_TOLERANCE:
			totals[to_item] += qty
	return {
		item: flt(qty / planned_qty, 6)
		for item, qty in sorted(totals.items())
	}


def allocate_route_quantity(planned_route_qty, dia_factors, precision=3):
	"""Multiply one colour route by Dia factors with stable remainder rounding."""
	unit = Decimal(1).scaleb(-precision)
	planned = Decimal(str(planned_route_qty or 0))
	raw = []
	for index, row in enumerate(dia_factors or []):
		factor = Decimal(str(row.get("factor") or 0))
		if factor <= 0:
			continue
		quantity = planned * factor
		floor = quantity.quantize(unit, rounding=ROUND_DOWN)
		raw.append({
			"index": index,
			"item_variant": row.get("item_variant"),
			"factor": factor,
			"raw": quantity,
			"qty": floor,
			"remainder": quantity - floor,
		})
	target = sum((row["raw"] for row in raw), Decimal(0)).quantize(
		unit, rounding=ROUND_HALF_UP
	)
	missing_units = int(
		(target - sum((row["qty"] for row in raw), Decimal(0))) / unit
	)
	for row in sorted(
		raw,
		key=lambda value: (
			-value["remainder"],
			str(value["item_variant"] or ""),
			value["index"],
		),
	)[:missing_units]:
		row["qty"] += unit
	return [
		{
			"item_variant": row["item_variant"],
			"factor": float(row["factor"]),
			"qty": float(row["qty"]),
		}
		for row in sorted(raw, key=lambda value: value["index"])
	]


def get_actual_dia_factors(lot, production_detail, planned_item_variant):
	"""Read the physical projection and divide it by the saved Lot program."""
	lot_doc = frappe.get_doc("Lot", lot) if isinstance(lot, str) else lot
	cloth_item = frappe.db.get_value(
		"Item Variant", planned_item_variant, "item"
	)
	planned_totals = get_planned_knitting_output_totals(
		lot_doc, production_detail, cloth_item
	)
	planned_qty = flt(planned_totals.get(planned_item_variant), 6)
	if planned_qty <= QTY_TOLERANCE:
		frappe.throw(_(
			"Lot {0} has no saved Cloth Program quantity for planned Knitting "
			"item {1}. Rebuild the Cloth Program before calculating the next process."
		).format(lot_doc.name, planned_item_variant))
	rows = [
		row for row in lot_doc.get("lot_fabric_conversions") or []
		if row.get("production_detail") == production_detail
		and row.get("process_name") == frappe.db.get_single_value(
			"IPD Settings", "default_knitting_process"
		)
		and row.get("from_item") == planned_item_variant
		and (row.get("received_type") or ELIGIBLE_RECEIVED_TYPE)
			== ELIGIBLE_RECEIVED_TYPE
	]
	factors = build_actual_dia_factors(rows, planned_qty)
	return [
		{"item_variant": item, "qty": flt(factor * planned_qty, 6), "factor": factor}
		for item, factor in factors.items()
	]


def _project_receipt_group(group, default_process):
	planned = _variant_state(group["planned_item_variant"])
	actual = _variant_state(group["actual_item_variant"])
	_validate_knitting_variance(planned, actual)
	ipd = frappe.get_cached_doc("Item Production Detail", group["production_detail"])
	steps = get_fabric_steps(ipd)
	knitting_index = next(
		(
			index for index, step in enumerate(steps)
			if step["process_name"] == default_process
		),
		None,
	)
	if knitting_index is None:
		frappe.throw(_(
			"IPD {0} does not contain its configured Default Knitting Process {1}."
		).format(ipd.name, default_process))

	base = {
		"production_detail": ipd.name,
		"route_item": group.get("route_item"),
		"source_from_item": planned["variant"],
		"source_to_item": actual["variant"],
		"received_type": group.get("received_type"),
		"stock_uom": group.get("stock_uom"),
		"to_qty": group["stock_qty"],
		"source_grns": group["source_grns"],
	}
	rows = [{
		**base,
		"stage_index": knitting_index,
		"process_name": default_process,
		"from_item": planned["variant"],
		"to_item": actual["variant"],
	}]
	states = [(planned, actual)]
	for stage_index, step in enumerate(
		steps[knitting_index + 1:], knitting_index + 1
	):
		next_states = []
		for planned_state, actual_state in states:
			advanced = _advance_route_state(
				ipd, step, group.get("route_item"), planned_state, actual_state
			)
			if not advanced:
				from essdee_yrp.fabric_plan import _route_bypasses_step

				if _route_bypasses_step(
					ipd,
					step,
					group.get("route_item"),
					planned_state["attrs"].items(),
				):
					# An authored direct-colour route can deliberately skip a
					# transformation. Only the canonical route solver may declare it.
					next_states.append((planned_state, actual_state))
					continue
				frappe.throw(_(
					"IPD {0} route {1} cannot map {2} through process {3}. "
					"Save the IPD to rebuild its process matrices."
				).format(
					ipd.name,
					group.get("route_item") or _("Generic"),
					planned_state["variant"],
					step["process_name"],
				))
			for planned_output, actual_output in advanced:
				rows.append({
					**base,
					"stage_index": stage_index,
					"process_name": step["process_name"],
					"from_item": planned_output["variant"],
					"to_item": actual_output["variant"],
				})
				next_states.append((planned_output, actual_output))
		states = _deduplicate_states(next_states)
	return rows


def _advance_route_state(ipd, step, route_item, planned_state, actual_state):
	from essdee_yrp.api.work_order import (
		_matrix_qty_rows,
		_resolve_variant,
		_step_kind,
	)
	from essdee_yrp.fabric_ipd import get_identity_process_row
	from essdee_yrp.fabric_source import _matches_input, project_output_attributes

	kind = _step_kind(ipd, step)
	identity_row = get_identity_process_row(ipd, step["process_name"])
	if kind == "identity" or (not kind and identity_row):
		treated_item = (
			(identity_row.get("process_item") if identity_row else None)
			or planned_state["item"]
		)
		if treated_item != planned_state["item"]:
			frappe.throw(_(
				"IPD {0} identity process {1} treats {2}, but route item {3} "
				"uses template {4}."
			).format(
				ipd.name, step["process_name"], treated_item,
				planned_state["variant"], planned_state["item"],
			))
		# Identity means no item or attribute change. Carry the complete variant
		# states directly so GSM/composition and future fabric attributes survive.
		return [(planned_state, actual_state)]
	else:
		if not kind:
			frappe.throw(_(
				"IPD {0} process {1} has no supported fabric process shape."
			).format(ipd.name, step["process_name"]))
		qty_rows = _matrix_qty_rows(ipd, step["process_name"], kind)

	exact_rows = [
		row for row in qty_rows
		if (row.get("reference_item_variant") or "") == (route_item or "")
	]
	generic_rows = [
		row for row in qty_rows if not row.get("reference_item_variant")
	]
	if route_item:
		qty_rows = exact_rows or generic_rows
	else:
		qty_rows = generic_rows or qty_rows

	results = []
	seen = set()
	for qty_row in qty_rows:
		matches = [
			spec for spec in (qty_row.get("input_specs") or [])
			if _matches_input(
				{"item": planned_state["item"], "attrs": planned_state["attrs"]},
				spec,
			)
		]
		if not matches:
			continue
		output_item = qty_row.get("output_item") or (
			matches[0].get("item") if kind == "identity" else ipd.item
		)
		planned_attrs = dict(qty_row.get("out_attrs") or {})
		actual_attrs = project_output_attributes(
			actual_state["attrs"],
			matches[0].get("attrs") or {},
			planned_attrs,
		)
		planned_variant = _resolve_variant(output_item, planned_attrs)
		actual_variant = _resolve_variant(output_item, actual_attrs)
		key = (planned_variant, actual_variant)
		if key in seen:
			continue
		seen.add(key)
		results.append((
			_variant_state(planned_variant),
			_variant_state(actual_variant),
		))
	if len(results) > 1:
		frappe.throw(_(
			"IPD {0} route {1} maps {2} to more than one output in process {3}. "
			"Make the process matrix route-specific."
		).format(
			ipd.name,
			route_item or _("Generic"),
			planned_state["variant"],
			step["process_name"],
		))
	return results


def _deduplicate_states(states):
	result = []
	seen = set()
	for planned, actual in states:
		key = (planned["variant"], actual["variant"])
		if key in seen:
			continue
		seen.add(key)
		result.append((planned, actual))
	return result


def _variant_state(item_variant):
	variant = frappe.get_cached_doc("Item Variant", item_variant)
	return {
		"variant": variant.name,
		"item": variant.item,
		"attrs": {
			row.attribute: row.attribute_value
			for row in variant.get("attributes") or []
		},
	}


def _validate_knitting_variance(planned, actual):
	if planned["item"] != actual["item"]:
		frappe.throw(_(
			"Actual knitting item {0} must use the planned item template {1}."
		).format(actual["variant"], planned["item"]))
	if not planned["attrs"].get(FABRIC_DIA_ATTRIBUTE):
		frappe.throw(_("Planned knitting item {0} has no Dia.").format(planned["variant"]))
	if not actual["attrs"].get(FABRIC_DIA_ATTRIBUTE):
		frappe.throw(_("Actual knitting item {0} has no Dia.").format(actual["variant"]))
	for attribute in set(planned["attrs"]) | set(actual["attrs"]):
		if attribute == FABRIC_DIA_ATTRIBUTE:
			continue
		if planned["attrs"].get(attribute) != actual["attrs"].get(attribute):
			frappe.throw(_(
				"Knitting conversion {0} -> {1} changes {2}; only Dia may vary."
			).format(planned["variant"], actual["variant"], attribute))


def _replace_conversion_rows(lot, rows):
	frappe.db.delete("Lot Fabric Conversion", {
		"parent": lot,
		"parenttype": "Lot",
		"parentfield": "lot_fabric_conversions",
	})
	for index, values in enumerate(rows, 1):
		row = frappe.new_doc("Lot Fabric Conversion")
		row.parent = lot
		row.parenttype = "Lot"
		row.parentfield = "lot_fabric_conversions"
		row.idx = index
		row.update(values)
		row.db_insert()


def get_process_conversion_index(lot, production_detail, process_name):
	"""Return route-aware downstream substitutions for one process.

	The values are weights, not live stock availability. Exact GRN buckets still
	own availability and reservations.
	"""
	rows = frappe.get_all(
		"Lot Fabric Conversion",
		filters={
			"parent": lot,
			"parenttype": "Lot",
			"parentfield": "lot_fabric_conversions",
			"production_detail": production_detail,
			"process_name": process_name,
			"received_type": ELIGIBLE_RECEIVED_TYPE,
		},
		fields=["route_item", "from_item", "to_item", "to_qty"],
	)
	index = defaultdict(dict)
	for row in rows:
		key = (row.route_item or "", row.from_item)
		index[key][row.to_item] = (
			index[key].get(row.to_item, 0) + flt(row.to_qty)
		)
	return dict(index)


def resolve_process_conversion(
	index, *, route_item, from_item, projected_item
):
	"""Select the exact precomputed item matching a matrix projection."""
	if not index or not from_item:
		return projected_item
	targets = index.get((route_item or "", from_item))
	if not targets and route_item:
		targets = index.get(("", from_item))
	if not targets:
		return projected_item
	if projected_item in targets:
		return projected_item
	frappe.throw(_(
		"Lot fabric conversion is out of date for {0}: calculated {1}, but the "
		"Lot table contains {2}. Rebuild the Lot conversion table and reopen "
		"Calculate."
	).format(from_item, projected_item, ", ".join(sorted(targets))))


@frappe.whitelist()
def get_lot_fabric_substitutions(lot, process_name=None, production_detail=None):
	lot_doc = frappe.get_doc("Lot", lot)
	lot_doc.check_permission("read")
	return build_lot_fabric_substitutions(
		lot_doc,
		process_name=process_name,
		production_detail=production_detail,
	)


def build_lot_fabric_substitutions(
	lot, *, process_name=None, production_detail=None
):
	lot_doc = frappe.get_doc("Lot", lot) if isinstance(lot, str) else lot
	selected = _selected_terminal_steps(
		lot_doc,
		process_name=process_name,
		production_detail=production_detail,
	)
	selected_keys = {
		(row["production_detail"], row["process_name"])
		for row in selected
	}
	groups = {}
	for row in lot_doc.get("lot_fabric_conversions") or []:
		key = (row.get("production_detail"), row.get("process_name"))
		if key not in selected_keys:
			continue
		if (
			row.get("received_type") or ELIGIBLE_RECEIVED_TYPE
		) != ELIGIBLE_RECEIVED_TYPE:
			continue
		from_item = row.get("from_item")
		to_item = row.get("to_item")
		if (
			not from_item
			or not to_item
			or flt(row.get("to_qty")) <= QTY_TOLERANCE
		):
			continue
		group_key = (row.get("production_detail"), from_item)
		group = groups.setdefault(group_key, {
			"from_item_variant": from_item,
			"production_detail": row.get("production_detail"),
			"processes": set(),
			"actual": defaultdict(float),
		})
		group["processes"].add(row.get("process_name"))
		group["actual"][to_item] += flt(row.get("to_qty"))

	mappings = []
	for (_ipd, from_item), group in sorted(groups.items()):
		actual_rows = []
		for to_item, quantity in sorted(group["actual"].items()):
			state = _variant_state(to_item)
			actual_rows.append({
				"item_variant": to_item,
				"dia": state["attrs"].get(FABRIC_DIA_ATTRIBUTE),
				"colour": state["attrs"].get("Colour"),
				"received_qty": flt(quantity, 3),
			})
		actual_variants = {row["item_variant"] for row in actual_rows}
		mappings.append({
			"from_item_variant": from_item,
			"production_detail": group["production_detail"],
			"process_name": ", ".join(
				sorted(p for p in group["processes"] if p)
			),
			"planned": [],
			"actual": actual_rows,
			"planned_qty": flt(
				sum(row["received_qty"] for row in actual_rows), 3
			),
			"received_qty": flt(
				sum(row["received_qty"] for row in actual_rows), 3
			),
			"is_substituted": (
				actual_variants != {from_item} or len(actual_rows) > 1
			),
		})
	return {
		"lot": lot_doc.name,
		"process_name": process_name,
		"production_detail": production_detail,
		"mappings": mappings,
		"unmapped_receipts": [],
	}


def substitution_index(lot, *, process_name=None, production_detail=None):
	result = build_lot_fabric_substitutions(
		lot,
		process_name=process_name,
		production_detail=production_detail,
	)
	return {
		row["from_item_variant"]: row
		for row in result["mappings"]
		if row.get("actual")
	}


def _selected_terminal_steps(lot_doc, *, process_name=None, production_detail=None):
	selected = []
	for fabric in lot_doc.get("lot_fabric_details") or []:
		if (
			production_detail
			and fabric.get("production_detail") != production_detail
		):
			continue
		if not fabric.get("production_detail"):
			continue
		ipd = frappe.get_cached_doc(
			"Item Production Detail", fabric.production_detail
		)
		steps = get_fabric_steps(ipd)
		if not steps:
			continue
		step = (
			next(
				(row for row in steps if row["process_name"] == process_name),
				None,
			)
			if process_name else steps[-1]
		)
		if not step:
			continue
		selected.append({
			"production_detail": fabric.production_detail,
			"process_name": step["process_name"],
		})
	return selected
