"""Server-owned Actual-Dia conversion projection for versioned cloth execution."""

from collections import defaultdict
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import frappe
from frappe import _
from frappe.utils import flt
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_variant_attributes

from essdee_yrp.cloth_execution import (
	get_row_execution_parameters,
	get_supported_execution_route,
	has_fabric_execution_key,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import (
	get_colour_attribute,
	get_dia_attribute,
)
from essdee_yrp.fabric_chain import get_fabric_steps

QTY_TOLERANCE = 0.000001


def get_planned_knitting_output_totals(lot_doc, production_detail, cloth_item):
	"""Sum the saved Cloth Program by physical Knitting output Item."""
	fabric_matches = [
		row
		for row in lot_doc.get("lot_fabric_details") or []
		if row.get("production_detail") == production_detail
		and row.get("cloth_item") == cloth_item
	]
	if not fabric_matches:
		return {}

	from yrp.attribute_links import value as attribute_value

	from essdee_yrp.api.work_order import _resolve_variant
	from essdee_yrp.fabric_program import get_fabric_routes, get_knitting_output_colour

	ipd = frappe.get_cached_doc("YRP Item Production Detail", production_detail)
	routes = get_fabric_routes(ipd)
	totals = defaultdict(float)
	for row in lot_doc.get("lot_fabric_programs") or []:
		if row.get("cloth_item") != cloth_item or flt(row.get("weight"), 6) <= 0:
			continue
		final_attrs = (
			get_variant_attributes(row.reference_item_variant)
			if row.get("reference_item_variant")
			else {}
		)
		final_dia = final_attrs.get(get_dia_attribute()) or attribute_value(row.get("dia"))
		final_colour = final_attrs.get(get_colour_attribute()) or attribute_value(row.get("colour"))
		route = next(
			(
				candidate
				for candidate in routes
				if candidate["finished_dia"] == final_dia
				and candidate["finished_colour"] == final_colour
			),
			None,
		)
		physical_dia = (route and route.get("knitting_output_dia")) or final_dia
		colour = (route and route.get("knitting_output_colour")) or get_knitting_output_colour(
			ipd, final_colour, final_dia
		)
		attrs = {get_dia_attribute(): physical_dia}
		if colour:
			attrs[get_colour_attribute()] = colour
		variant = _resolve_variant(cloth_item, attrs)
		totals[variant] += flt(row.get("weight"), 6)
	return {
		variant: flt(quantity, 6)
		for variant, quantity in totals.items()
		if flt(quantity, 6) > QTY_TOLERANCE
	}


def allocate_route_quantity(route_qty, factors, precision=3):
	"""Allocate one route through fractional Dia factors without losing residue."""
	unit = Decimal(1).scaleb(-precision)
	planned = Decimal(str(route_qty or 0))
	working = []
	for index, factor_row in enumerate(factors or []):
		factor = Decimal(str(factor_row.get("factor") or 0))
		if factor <= 0:
			continue
		raw = planned * factor
		floor = raw.quantize(unit, rounding=ROUND_DOWN)
		working.append(
			{
				"index": index,
				"actual_item": factor_row.get("actual_item"),
				"factor": factor,
				"raw": raw,
				"quantity": floor,
				"remainder": raw - floor,
			}
		)
	target = sum((row["raw"] for row in working), Decimal(0)).quantize(
		unit, rounding=ROUND_HALF_UP
	)
	missing_units = int(
		(target - sum((row["quantity"] for row in working), Decimal(0))) / unit
	)
	for row in sorted(
		working,
		key=lambda value: (
			-value["remainder"],
			str(value["actual_item"] or ""),
			value["index"],
		),
	)[:missing_units]:
		row["quantity"] += unit
	return [
		{
			"actual_item": row["actual_item"],
			"factor": float(row["factor"]),
			"quantity": float(row["quantity"]),
		}
		for row in sorted(working, key=lambda value: value["index"])
	]


def build_actual_dia_factors(rows, planned_qty):
	"""Return uncapped physical Actual-Dia factors for one planned Item."""
	planned_qty = flt(planned_qty, 6)
	if planned_qty <= QTY_TOLERANCE:
		raise ValueError("planned_qty must be greater than zero")
	totals = defaultdict(float)
	for row in rows or []:
		item = row.get("actual_item")
		quantity = flt(row.get("actual_quantity"), 6)
		if item and quantity > QTY_TOLERANCE:
			totals[item] += quantity
	return [
		{
			"actual_item": item,
			"actual_quantity": flt(quantity, 6),
			"factor": flt(quantity / planned_qty, 6),
		}
		for item, quantity in sorted(totals.items())
	]


def get_default_knitting_grn_context(grn):
	"""Resolve the Lot and IPD for a standard Default Knitting GRN."""
	if grn.get("against") != "YRP Work Order" or not grn.get("against_id"):
		return None
	if any(
		grn.get(fieldname)
		for fieldname in ("is_return", "is_rework", "additional_grn", "includes_packing")
	):
		return None
	if not frappe.db.exists("YRP Work Order", grn.against_id):
		return None
	work_order = frappe.get_cached_doc("YRP Work Order", grn.against_id)
	if not (
		work_order.get("lot")
		and work_order.get("production_detail")
	):
		return None
	if not work_order.get("process_name") or work_order.process_name != _default_knitting_process():
		return None
	return frappe._dict(
		lot=work_order.lot,
		process_name=work_order.process_name,
		production_detail=work_order.production_detail,
		cloth_item=work_order.item,
		work_order=work_order.name,
	)


def lock_lot_for_default_knitting_grn(grn):
	"""Lock the qualifying Lot before Frappe locks the GRN parent."""
	context = get_default_knitting_grn_context(grn)
	if not context:
		return None
	locked_lot = grn.flags.get("cloth_execution_lot_locked")
	if locked_lot:
		if locked_lot != context.lot:
			frappe.throw(_("The locked cloth execution Lot no longer matches this GRN."))
		return context
	_lock_lot(context.lot)
	grn.flags.cloth_execution_lot_locked = context.lot
	return context


def _lock_lot(lot):
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE",
		(lot,),
	)


def get_default_knitting_lots_for_grn_items(grn_item_names, *, for_update=False):
	"""Resolve Lot projections from the exact keyed GRN children being inspected."""
	grn_item_names = sorted(set(grn_item_names or []))
	if not grn_item_names:
		return []
	process_name = _default_knitting_process()
	if not process_name:
		return []
	lock_clause = "FOR UPDATE" if for_update else ""
	rows = frappe.db.sql(
		f"""
		SELECT item.name AS source_grn_item,
			wo.lot,
			wo.cloth_execution_version,
			receivable.additional_parameters
		FROM `tabYRP Goods Received Note Item` item
		JOIN `tabYRP Goods Received Note` grn
			ON grn.name = item.parent
			AND item.parenttype = 'YRP Goods Received Note'
		JOIN `tabYRP Work Order` wo ON wo.name = grn.against_id
		JOIN `tabYRP Work Order Receivables` receivable
			ON receivable.name = item.ref_docname
			AND receivable.parent = wo.name
			AND receivable.parenttype = 'YRP Work Order'
		WHERE item.name IN %(grn_items)s
			AND item.ref_doctype = 'YRP Work Order Receivables'
			AND grn.docstatus = 1
			AND grn.against = 'YRP Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND IFNULL(grn.is_rework, 0) = 0
			AND IFNULL(grn.additional_grn, 0) = 0
			AND IFNULL(grn.includes_packing, 0) = 0
			AND wo.process_name = %(process_name)s
			AND IFNULL(wo.production_detail, '') != ''
			AND IFNULL(wo.lot, '') != ''
		ORDER BY item.name
		{lock_clause}
		""",
		{
			"grn_items": tuple(grn_item_names),
			"process_name": process_name,
		},
		as_dict=True,
	)
	return sorted({row.lot for row in rows if row.lot and _is_eligible_knitting_receipt(row)})


def lock_lots_for_default_knitting_grn_items(grn_item_names):
	"""Lock only Lots reached through the exact keyed GRN children."""
	lots = get_default_knitting_lots_for_grn_items(grn_item_names)
	if lots:
		frappe.db.sql(
			"SELECT name FROM `tabSD YRP Lot` "
			"WHERE name IN %(lots)s ORDER BY name FOR UPDATE",
			{"lots": tuple(lots)},
		)
	return lots


def rebuild_lot_fabric_conversions_for_grn(grn):
	context = get_default_knitting_grn_context(grn)
	if not context:
		return None
	locked_lot = grn.flags.get("cloth_execution_lot_locked")
	if not locked_lot:
		frappe.throw(
			_(
				"Cloth execution must lock the Lot before the GRN submit or cancel lifecycle begins."
			)
		)
	if locked_lot != context.lot:
		frappe.throw(_("The locked cloth execution Lot no longer matches this GRN."))
	return _rebuild_lot_fabric_conversions(
		locked_lot, already_locked=True
	)


@frappe.whitelist()
def rebuild_lot_fabric_conversions(lot):
	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("write")
	return _rebuild_lot_fabric_conversions(lot_doc.name)


def _rebuild_lot_fabric_conversions(lot, *, already_locked=False):
	if not already_locked:
		_lock_lot(lot)
	receipts = _fetch_default_knitting_receipts(lot)
	rows = build_conversion_rows(receipts, _default_knitting_process())
	_replace_conversion_rows(lot, rows)
	return {"lot": lot, "source_receipts": len(receipts), "conversions": len(rows)}


def _default_knitting_process():
	return frappe.db.get_single_value("SD YRP IPD Settings", "default_knitting_process")


def _default_received_type():
	return frappe.db.get_single_value("YRP Stock Settings", "default_received_type")


def _fetch_default_knitting_receipts(lot):
	"""Current-read eligible keyed physical receipt rows after the Lot lock."""
	process_name = _default_knitting_process()
	if not process_name:
		return []
	work_orders = frappe.db.sql(
		"""
		SELECT name, production_detail, item
		FROM `tabYRP Work Order`
		WHERE lot = %(lot)s
			AND process_name = %(process_name)s
			AND IFNULL(production_detail, '') != ''
		ORDER BY name
		FOR UPDATE
		""",
		{"lot": lot, "process_name": process_name},
		as_dict=True,
	)
	work_order_names = [row.name for row in work_orders]
	if not work_order_names:
		return []
	grn_names = frappe.db.sql(
		"""
		SELECT name
		FROM `tabYRP Goods Received Note`
		WHERE docstatus = 1
			AND against = 'YRP Work Order'
			AND against_id IN %(work_orders)s
			AND IFNULL(is_return, 0) = 0
			AND IFNULL(is_rework, 0) = 0
			AND IFNULL(additional_grn, 0) = 0
			AND IFNULL(includes_packing, 0) = 0
		ORDER BY name
		FOR UPDATE
		""",
		{"work_orders": tuple(work_order_names)},
		pluck="name",
	)
	if not grn_names:
		return []
	rows = frappe.db.sql(
		"""
		SELECT grn.name AS source_grn,
			item.name AS source_grn_item,
			item.item_variant AS actual_item,
			item.stock_qty,
			item.quantity,
			item.conversion_factor,
			item.uom,
			item.stock_uom,
			item.received_type,
			wo.production_detail,
			wo.cloth_execution_version,
			wo.item AS cloth_item,
			receivable.item_variant AS planned_item,
			receivable.qty AS planned_qty,
			receivable.fabric_reference_variant AS route_item,
			receivable.additional_parameters
		FROM `tabYRP Goods Received Note` grn
		JOIN `tabYRP Work Order` wo ON wo.name = grn.against_id
		JOIN `tabYRP Goods Received Note Item` item
			ON item.parent = grn.name
			AND item.parenttype = 'YRP Goods Received Note'
		JOIN `tabYRP Work Order Receivables` receivable
			ON receivable.name = item.ref_docname
			AND receivable.parent = wo.name
		WHERE grn.name IN %(grn_names)s
			AND item.ref_doctype = 'YRP Work Order Receivables'
		ORDER BY grn.name, item.idx, item.name
		FOR UPDATE
		""",
		{"grn_names": tuple(grn_names)},
		as_dict=True,
	)
	default_received_type = _default_received_type()
	from essdee_yrp.fabric_source import (
		_accepted_inspection_adjustments,
		_normalise_accepted_receipts,
	)

	keyed_rows = [row for row in rows if _is_eligible_knitting_receipt(row)]
	rows = _normalise_accepted_receipts(
		keyed_rows,
		_accepted_inspection_adjustments(keyed_rows, for_update=True),
		default_received_type=default_received_type,
	)
	result = []
	for row in rows:
		parameters = get_row_execution_parameters(row)
		execution_key = parameters.get("fabric_execution_key")
		quantity = flt(row.stock_qty, 6)
		if quantity <= QTY_TOLERANCE:
			continue
		row.fabric_execution_key = execution_key
		row.received_type = default_received_type
		row.stock_qty = quantity
		result.append(row)
	return result


def _is_eligible_knitting_receipt(row):
	return row.get("cloth_execution_version") != 1 or bool(row.get("fabric_execution_key")) or has_fabric_execution_key(row)


def build_conversion_rows(receipts, default_process):
	"""Project keyed physical Knitting receipts through Dyeing and Washing."""
	groups = {}
	for row in receipts or []:
		if not _is_eligible_knitting_receipt(row) or flt(row.get("stock_qty"), 6) <= QTY_TOLERANCE:
			continue
		is_stage_projection = bool(row.get("cloth_execution_version") == 1 and row.get("fabric_execution_key"))
		key = (
			is_stage_projection,
			row.get("production_detail"),
			row.get("route_item") or "",
			row.get("planned_item"),
			row.get("actual_item"),
			row.get("received_type") or "",
			row.get("stock_uom") or row.get("uom") or "",
		)
		group = groups.setdefault(
			key,
			frappe._dict(
				is_stage_projection=is_stage_projection,
				default_process=default_process,
				production_detail=row.get("production_detail"),
				route_item=row.get("route_item"),
				planned_item=row.get("planned_item"),
				actual_item=row.get("actual_item"),
				received_type=row.get("received_type"),
				stock_uom=row.get("stock_uom") or row.get("uom"),
				stock_qty=0.0,
				source_grns=set(),
			),
		)
		group.stock_qty += flt(row.get("stock_qty"), 6)
		if row.get("source_grn"):
			group.source_grns.add(row.source_grn)

	projected = []
	for group in groups.values():
		ipd = frappe.get_cached_doc("YRP Item Production Detail", group.production_detail)
		for row in _project_receipt_group(group, ipd):
			row["source_grn_count"] = len(group.source_grns)
			projected.append(row)
	return _aggregate_conversion_rows(projected, default_process)


def _project_receipt_group(group, ipd):
	route = get_supported_execution_route(ipd)
	_validate_knitting_variance(group.planned_item, group.actual_item)
	base = {
		"production_detail": group.production_detail,
		"route_item": group.get("route_item"),
		"knitting_planned_item": group.planned_item,
		"knitting_actual_item": group.actual_item,
		"received_type": group.get("received_type"),
		"stock_uom": group.get("stock_uom"),
		"actual_quantity": flt(group.stock_qty, 6),
	}
	if not route or not group.get("is_stage_projection"):
		return [{
			**base,
			"process_name": group.get("default_process") or _default_knitting_process(),
			"process_stage_index": 0,
			"planned_item": group.planned_item,
			"actual_item": group.actual_item,
		}]
	planned_item = group.planned_item
	actual_item = group.actual_item
	rows = []
	for role, step in sorted(route.items(), key=lambda value: value[1]["position"]):
		if role != "knitting":
			planned_item, actual_item = _project_stage_items(
				ipd,
				step,
				group.get("route_item"),
				planned_item,
				actual_item,
			)
		rows.append(
			{
				**base,
				"process_name": step["process_name"],
				"process_stage_index": step["position"],
				"planned_item": planned_item,
				"actual_item": actual_item,
			}
		)
	return rows


def _project_stage_items(ipd, step, route_item, planned_item, actual_item):
	if step.get("shape") == "identity":
		return planned_item, actual_item
	from essdee_yrp.api.work_order import _matrix_qty_rows, _resolve_variant, _step_kind
	from essdee_yrp.fabric_source import _matches_input

	kind = _step_kind(ipd, step)
	rows = _matrix_qty_rows(ipd, step["process_name"], kind)
	exact = [row for row in rows if (row.get("reference_item_variant") or "") == (route_item or "")]
	generic = [row for row in rows if not row.get("reference_item_variant")]
	rows = (exact or generic) if route_item else (generic or rows)
	planned_state = _item_state(planned_item)
	actual_state = _item_state(actual_item)
	outputs = []
	for row in rows:
		matches = [spec for spec in row.get("input_specs") or [] if _matches_input(planned_state, spec)]
		if not matches:
			continue
		planned_attrs = dict(row.get("out_attrs") or {})
		actual_attrs = _project_output_attributes(
			actual_state["attrs"], matches[0].get("attrs") or {}, planned_attrs
		)
		output_item = row.get("output_item") or planned_state["item"]
		outputs.append(
			(_resolve_variant(output_item, planned_attrs), _resolve_variant(output_item, actual_attrs))
		)
	outputs = list(dict.fromkeys(outputs))
	if not outputs:
		from essdee_yrp.fabric_plan import _route_bypasses_step

		if _route_bypasses_step(
			ipd,
			step,
			route_item,
			planned_state["attrs"].items(),
		):
			return planned_item, actual_item
	if len(outputs) != 1:
		frappe.throw(
			_("IPD {0} route cannot uniquely project {1} through process {2}.").format(
				ipd.name, planned_item, step["process_name"]
			)
		)
	return outputs[0]


def _project_output_attributes(actual_attrs, planned_input_attrs, planned_output_attrs):
	result = dict(planned_output_attrs or {})
	for attribute, actual_value in (actual_attrs or {}).items():
		if attribute not in planned_input_attrs:
			if attribute not in result:
				result[attribute] = actual_value
			continue
		if planned_output_attrs.get(attribute) == planned_input_attrs.get(attribute):
			result[attribute] = actual_value
	return result


def _item_state(item_code):
	return {
		"variant": item_code,
		"item": get_parent_item(item_code),
		"attrs": get_variant_attributes(item_code),
	}


def _validate_knitting_variance(planned_item, actual_item):
	planned = _item_state(planned_item)
	actual = _item_state(actual_item)
	if planned["item"] != actual["item"]:
		frappe.throw(
			_("Actual knitting Item {0} must use planned Item template {1}.").format(
				actual_item, planned["item"]
			)
		)
	if not planned["attrs"].get(get_dia_attribute()):
		frappe.throw(_("Planned knitting Item {0} has no Dia.").format(planned_item))
	if not actual["attrs"].get(get_dia_attribute()):
		frappe.throw(_("Actual knitting Item {0} has no Dia.").format(actual_item))
	for attribute in set(planned["attrs"]) | set(actual["attrs"]):
		if attribute == get_dia_attribute():
			continue
		if planned["attrs"].get(attribute) != actual["attrs"].get(attribute):
			frappe.throw(
				_("Knitting conversion {0} -> {1} changes {2}; only Dia may vary.").format(
					planned_item, actual_item, attribute
				)
			)


def _aggregate_conversion_rows(rows, default_process):
	grouped = {}
	for row in rows:
		key = tuple(
			row.get(fieldname) or ""
			for fieldname in (
				"process_name",
				"planned_item",
				"actual_item",
				"production_detail",
				"route_item",
				"knitting_planned_item",
				"knitting_actual_item",
				"process_stage_index",
				"received_type",
				"stock_uom",
			)
		)
		value = grouped.setdefault(key, {**row, "actual_quantity": 0.0, "source_grn_count": 0})
		value["actual_quantity"] += flt(row.get("actual_quantity"), 6)
		value["source_grn_count"] += int(row.get("source_grn_count") or 0)
	return sorted(
		grouped.values(),
		key=lambda row: (
			row.get("production_detail") or "",
			row.get("process_stage_index") or 0,
			row.get("planned_item") or "",
			row.get("actual_item") or "",
		),
	)


def _replace_conversion_rows(lot, rows):
	frappe.db.delete(
		"SD YRP Lot Fabric Conversion",
		{
			"parent": lot,
			"parenttype": "SD YRP Lot",
			"parentfield": "lot_fabric_conversions",
		},
	)
	for index, values in enumerate(rows, 1):
		row = frappe.new_doc("SD YRP Lot Fabric Conversion")
		row.parent = lot
		row.parenttype = "SD YRP Lot"
		row.parentfield = "lot_fabric_conversions"
		row.idx = index
		row.update(values)
		row.db_insert()


def get_actual_dia_factors(lot, production_detail, planned_item):
	lot_doc = frappe.get_doc("SD YRP Lot", lot) if isinstance(lot, str) else lot
	cloth_item = get_parent_item(planned_item)
	planned_totals = get_planned_knitting_output_totals(
		lot_doc, production_detail, cloth_item
	)
	planned_qty = flt(planned_totals.get(planned_item), 6)
	if planned_qty <= QTY_TOLERANCE:
		frappe.throw(
			_(
				"Lot {0} has no saved Cloth Program quantity for planned Knitting "
				"Item {1}. Rebuild the Cloth Program before calculating the next process."
			).format(lot_doc.name, planned_item)
		)
	rows = [
		row
		for row in lot_doc.get("lot_fabric_conversions") or []
		if row.get("production_detail") == production_detail
		and row.get("process_stage_index") == 0
		and row.get("planned_item") == planned_item
		and row.get("received_type") == _default_received_type()
	]
	return build_actual_dia_factors(rows, planned_qty)


def get_process_conversion_index(
	lot, process_name=None, production_detail=None, *, for_update=False
):
	filters = {
		"parent": lot,
		"parenttype": "SD YRP Lot",
		"parentfield": "lot_fabric_conversions",
	}
	if process_name:
		filters["process_name"] = process_name
	if production_detail:
		filters["production_detail"] = production_detail
	if for_update:
		conditions = [
			"parent = %(parent)s",
			"parenttype = %(parenttype)s",
			"parentfield = %(parentfield)s",
		]
		if process_name:
			conditions.append("process_name = %(process_name)s")
		if production_detail:
			conditions.append("production_detail = %(production_detail)s")
		rows = frappe.db.sql(
			f"""
			SELECT route_item, planned_item, actual_item, actual_quantity
			FROM `tabSD YRP Lot Fabric Conversion`
			WHERE {' AND '.join(conditions)}
			ORDER BY name
			FOR UPDATE
			""",
			filters,
			as_dict=True,
		)
	else:
		rows = frappe.get_all(
			"SD YRP Lot Fabric Conversion",
			filters=filters,
			fields=["route_item", "planned_item", "actual_item", "actual_quantity"],
		)
	index = defaultdict(dict)
	for row in rows:
		key = (row.route_item or "", row.planned_item)
		index[key][row.actual_item] = index[key].get(row.actual_item, 0) + flt(
			row.actual_quantity, 6
		)
	return dict(index)


def resolve_process_conversion(index, *, route_item, planned_item, projected_item):
	if not index or not planned_item:
		return projected_item
	targets = index.get((route_item or "", planned_item))
	if not targets and route_item:
		targets = index.get(("", planned_item))
	if not targets or projected_item in targets:
		return projected_item
	frappe.throw(
		_(
			"Lot fabric conversion is out of date for {0}: calculated {1}, but the Lot contains {2}."
		).format(planned_item, projected_item, ", ".join(sorted(targets)))
	)


def substitution_index(lot):
	"""Index default receipts from each cloth IPD's terminal conversion stage."""
	rows = frappe.get_all(
		"SD YRP Lot Fabric Conversion",
		filters={"parent": lot, "parenttype": "SD YRP Lot", "parentfield": "lot_fabric_conversions"},
		fields=["production_detail", "process_stage_index", "planned_item", "actual_item", "actual_quantity", "received_type"],
	)
	terminal = {}
	for row in rows:
		ipd = row["production_detail"]
		if ipd not in terminal:
			steps = get_fabric_steps(frappe.get_cached_doc("YRP Item Production Detail", ipd))
			terminal[ipd] = steps[-1]["position"] if steps else 0
	quantities = defaultdict(lambda: defaultdict(float))
	received_type = _default_received_type()
	for row in rows:
		if (row["process_stage_index"] != terminal[row["production_detail"]]
			or row["received_type"] != received_type
			or flt(row["actual_quantity"]) <= QTY_TOLERANCE):
			continue
		quantities[row["planned_item"]][row["actual_item"]] += flt(row["actual_quantity"])
	return {
		planned: {"actual": [
			{"item_variant": item, "dia": get_variant_attributes(item).get(get_dia_attribute()),
				"received_qty": flt(quantity, 6)}
			for item, quantity in sorted(actual.items())
		]}
		for planned, actual in quantities.items()
	}
