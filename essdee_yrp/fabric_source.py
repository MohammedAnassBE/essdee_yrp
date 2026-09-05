"""Transaction-backed quantity filling for fabric Work Orders.

The Lot owns only the cloth program.  Actual availability is derived on demand
from submitted GRNs of an earlier IPD process and reservations are the
calculated deliverables of other live Work Orders.  Nothing in this module
writes receipt totals back to the Lot.
"""

from collections import Counter

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_steps


QTY_TOLERANCE = 0.001


def process_step_key(step):
	return f"{int(step['position'])}::{step['process_name']}"


def get_source_process_options(ipd, current_process):
	"""Earlier configured steps, immediate predecessor first."""
	steps = get_fabric_steps(ipd)
	current = next(
		(step for step in steps if step["process_name"] == current_process), None
	)
	if not current:
		return []
	name_counts = Counter(step["process_name"] for step in steps)
	return [
		{
			"value": process_step_key(step),
			"label": (
				_('{0} (Step {1})').format(step["process_name"], step["position"] + 1)
				if name_counts[step["process_name"]] > 1
				else step["process_name"]
			),
			"process_name": step["process_name"],
			"position": step["position"],
		}
		for step in reversed(steps[: current["position"]])
	]


def resolve_source_process(ipd, current_process, source_process):
	options = get_source_process_options(ipd, current_process)
	match = next(
		(option for option in options if option["value"] == source_process), None
	)
	# Process-name fallback keeps API callers created before step keys working,
	# but only when the name identifies exactly one eligible earlier step.
	if not match:
		by_name = [
			option for option in options
			if option["process_name"] == source_process
		]
		match = by_name[0] if len(by_name) == 1 else None
	if not match:
		frappe.throw(
			_('{0} is not an earlier process of {1} on IPD {2}.').format(
				source_process, current_process, ipd.name
			)
		)
	return match


def fill_from_source_grns(
	qty_rows, *, lot, ipd, current_process, current_work_order, source_process
):
	"""Mutate popup rows with fillable output quantities from source GRNs.

	One physical source variant can feed several output rules (Greige -> Red and
	Greige -> Navy).  Those rows receive the same shared availability but stay at
	zero so the operator explicitly allocates the pool.
	"""
	selected = resolve_source_process(ipd, current_process, source_process)
	availability = get_source_availability(
		lot=lot,
		ipd=ipd.name,
		cloth_item=ipd.item,
		source_process=selected["process_name"],
		source_step=selected["value"],
		current_process=current_process,
		current_work_order=current_work_order,
	)
	net = availability["net"]
	positive = {variant: qty for variant, qty in net.items() if qty > QTY_TOLERANCE}
	if not positive:
		frappe.throw(
			_('No unallocated submitted GRN quantity is available from process {0}.').format(
				selected["process_name"]
			)
		)

	variant_info = _variant_info(positive)
	row_matches = []
	match_counts = Counter()
	all_matched = set()
	for qty_row in qty_rows:
		output_qty = flt(qty_row.get("output_qty")) or 1
		capacities = []
		matched = set()
		for spec in qty_row.get("input_specs") or []:
			required = flt(spec.get("qty"))
			if required <= 0 or not spec.get("item"):
				continue
			spec_matches = {
				variant for variant, info in variant_info.items()
				if _matches_input(info, spec)
			}
			matched.update(spec_matches)
			available = sum(positive[variant] for variant in spec_matches)
			capacities.append(available * output_qty / required)
		capacity = min(capacities) if capacities else 0
		row_matches.append((qty_row, matched, capacity))
		all_matched.update(matched)
		match_counts.update(matched)

	if not all_matched:
		labels = ", ".join(
			_variant_label(variant, variant_info[variant])
			for variant in sorted(positive)
		)
		frappe.throw(
			_(
				'Process {0} received {1}, but the current {2} popup has no compatible input row. '
				'Check the IPD process mapping or select another source process.'
			).format(selected["process_name"], labels, current_process)
		)

	for qty_row, matched, capacity in row_matches:
		shared = any(match_counts[variant] > 1 for variant in matched)
		qty_row.update({
			"source_process": selected["process_name"],
			"source_process_step": selected["value"],
			"source_available": flt(capacity, 3),
			"source_shared": shared,
			"source_pool_key": "|".join(sorted(matched)),
			# Never guess a split when several target rules consume the same
			# physical GRN variant. Unique matches can be filled completely.
			"prefill": 0 if shared else flt(capacity, 3),
		})

	unmatched = [
		_variant_label(variant, variant_info[variant])
		for variant in sorted(set(positive) - all_matched)
	]
	return {
		"value": selected["value"],
		"process_name": selected["process_name"],
		"label": selected["label"],
		"received": flt(sum(availability["received"].values()), 3),
		"reserved": flt(sum(availability["reserved"].values()), 3),
		"available": flt(sum(positive.values()), 3),
		"unmatched": unmatched,
	}


def validate_source_demands(
	demands, *, lot, ipd, cloth_item, current_process, current_work_order,
	source_process,
):
	"""Recheck source availability during Calculate; the popup may be stale."""
	selected = resolve_source_process(ipd, current_process, source_process)
	# Serialize calculations for the same Lot and hold every currently submitted
	# source receipt until this request commits.  The second concurrent Work Order
	# therefore sees the first one's saved reservation; a source GRN cannot be
	# cancelled between this availability check and the Work Order save.
	_lock_source_transactions(lot, cloth_item, selected["process_name"])
	availability = get_source_availability(
		lot=lot,
		ipd=ipd.name,
		cloth_item=cloth_item,
		source_process=selected["process_name"],
		source_step=selected["value"],
		current_process=current_process,
		current_work_order=current_work_order,
	)
	requested = _rows_in_stock_uom(demands)
	for variant, qty in requested.items():
		available = max(flt(availability["net"].get(variant)), 0)
		if qty > available + QTY_TOLERANCE:
			frappe.throw(
				_(
					'{0}: requested {1} Kg from {2}, but only {3} Kg remains available '
					'in submitted GRNs. Reopen Fill Quantity.'
				).format(variant, flt(qty, 3), selected["process_name"], flt(available, 3))
			)
	return selected


def get_source_availability(
	*, lot, ipd, cloth_item, source_process, source_step, current_process,
	current_work_order,
):
	"""Physical Item Variant quantities: submitted source GRNs minus reservations."""
	received_rows = frappe.db.sql(
		"""
		SELECT item.item_variant, item.stock_qty, item.quantity, item.uom
		FROM `tabGoods Received Note Item` item
		JOIN `tabGoods Received Note` grn ON grn.name = item.parent
		JOIN `tabWork Order` source_wo ON source_wo.name = grn.against_id
		WHERE item.parenttype = 'Goods Received Note'
			AND grn.docstatus = 1
			AND grn.against = 'Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND item.ref_doctype = 'Work Order Receivables'
			AND source_wo.lot = %(lot)s
			AND source_wo.item = %(cloth_item)s
			AND source_wo.process_name = %(source_process)s
		""",
		{
			"lot": lot,
			"ipd": ipd,
			"cloth_item": cloth_item,
			"source_process": source_process,
		},
		as_dict=True,
	)
	received = _rows_in_stock_uom(received_rows, quantity_field="quantity")

	params = {
		"lot": lot,
		"ipd": ipd,
		"cloth_item": cloth_item,
		"current_process": current_process,
		"current_work_order": current_work_order,
		"source_process": source_process,
		"source_step": source_step,
	}
	has_source_process = frappe.db.has_column("Work Order", "fabric_source_process")
	has_source_step = frappe.db.has_column("Work Order", "fabric_source_process_step")
	if has_source_process and has_source_step:
		# New Work Orders reserve a physical source pool regardless of which later
		# process consumes it.  Legacy rows have no lineage, so count only the same
		# target process as a conservative compatibility fallback.
		source_filter = """
			AND (
				(
					target_wo.fabric_source_process = %(source_process)s
					AND target_wo.fabric_source_process_step = %(source_step)s
				)
				OR (
					IFNULL(target_wo.fabric_source_process, '') = ''
					AND IFNULL(target_wo.fabric_source_process_step, '') = ''
					AND target_wo.process_name = %(current_process)s
				)
			)
		"""
	elif has_source_process:
		source_filter = """
			AND (
				target_wo.fabric_source_process = %(source_process)s
				OR (
					IFNULL(target_wo.fabric_source_process, '') = ''
					AND target_wo.process_name = %(current_process)s
				)
			)
		"""
	else:
		source_filter = "AND target_wo.process_name = %(current_process)s"
	reserved_rows = frappe.db.sql(
		f"""
		SELECT item.item_variant, item.qty, item.uom
		FROM `tabWork Order Deliverables` item
		JOIN `tabWork Order` target_wo ON target_wo.name = item.parent
		WHERE item.parenttype = 'Work Order'
			AND target_wo.docstatus < 2
			AND target_wo.name != %(current_work_order)s
			AND target_wo.lot = %(lot)s
			AND target_wo.item = %(cloth_item)s
			AND IFNULL(item.is_calculated, 0) = 1
			{source_filter}
		""",
		params,
		as_dict=True,
	)
	reserved = _rows_in_stock_uom(reserved_rows)
	variants = set(received) | set(reserved)
	return {
		"received": received,
		"reserved": reserved,
		"net": {
			variant: flt(
				flt(received.get(variant)) - flt(reserved.get(variant)), 3
			)
			for variant in variants
		},
	}


def _lock_source_transactions(lot, cloth_item, source_process):
	"""Lock the shared pool during Calculate, never during popup reads."""
	frappe.db.sql(
		"SELECT name FROM `tabLot` WHERE name = %s FOR UPDATE",
		lot,
	)
	frappe.db.sql(
		"""
		SELECT grn.name
		FROM `tabGoods Received Note` grn
		JOIN `tabWork Order` source_wo ON source_wo.name = grn.against_id
		WHERE grn.docstatus = 1
			AND grn.against = 'Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND source_wo.lot = %(lot)s
			AND source_wo.item = %(cloth_item)s
			AND source_wo.process_name = %(source_process)s
		FOR UPDATE
		""",
		{
			"lot": lot,
			"cloth_item": cloth_item,
			"source_process": source_process,
		},
	)


def _rows_in_stock_uom(rows, quantity_field="qty"):
	from yrp.stock.utils import get_conversion_factor

	result = {}
	for row in rows or []:
		variant = row.get("item_variant")
		if not variant:
			continue
		stock_qty = flt(row.get("stock_qty"))
		if not stock_qty:
			qty = flt(row.get(quantity_field))
			factor = flt(
				(get_conversion_factor(variant, row.get("uom")) or {}).get(
					"conversion_factor"
				)
			) or 1
			stock_qty = qty * factor
		result[variant] = result.get(variant, 0) + stock_qty
	return {variant: flt(qty, 6) for variant, qty in result.items()}


def _variant_info(variants):
	variants = list(variants)
	if not variants:
		return {}
	result = {
		row.name: {"item": row.item, "attrs": {}}
		for row in frappe.get_all(
			"Item Variant",
			filters={"name": ["in", variants]},
			fields=["name", "item"],
		)
	}
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", variants], "parenttype": "Item Variant"},
		fields=["parent", "attribute", "attribute_value"],
	):
		if row.parent in result:
			result[row.parent]["attrs"][row.attribute] = row.attribute_value
	return result


def _matches_input(variant, spec):
	if variant.get("item") != spec.get("item"):
		return False
	expected = {key: value for key, value in (spec.get("attrs") or {}).items() if value}
	actual = variant.get("attrs") or {}
	return all(actual.get(key) == value for key, value in expected.items())


def _variant_label(name, info):
	attrs = info.get("attrs") or {}
	details = " · ".join(attrs[key] for key in sorted(attrs))
	return f"{name} ({details})" if details else name
