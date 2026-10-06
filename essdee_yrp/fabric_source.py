"""Transaction-backed quantity filling for fabric Work Orders.

The Lot owns only the cloth program.  Actual availability is derived on demand
from submitted GRNs of an earlier IPD process and reservations are the
calculated deliverables of other live Work Orders.  Nothing in this module
writes receipt totals back to the Lot.
"""

from collections import Counter, defaultdict
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.attribute_links import value as _attribute_value

from essdee_yrp.cloth_execution import (
	get_row_execution_parameters,
	has_fabric_execution_key,
	is_versioned_cloth_work_order,
)
from essdee_yrp.fabric_chain import get_fabric_steps
from essdee_yrp.fabric_ipd import FABRIC_DIA_ATTRIBUTE
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	scale_reference_allocations,
)

QTY_TOLERANCE = 0.001
ZERO_QTY_EPSILON = 1e-9


def _exceeds_available(requested, available):
	return flt(requested) - flt(available) > ZERO_QTY_EPSILON


def _floor_source_quantity(value, precision=3):
	unit = Decimal(1).scaleb(-precision)
	return float(Decimal(str(max(flt(value), 0))).quantize(unit, rounding=ROUND_DOWN))


def process_step_key(step):
	return f"{int(step['position'])}::{step['process_name']}"


def get_source_process_options(ipd, current_process):
	"""Earlier configured steps, immediate predecessor first."""
	steps = get_fabric_steps(ipd)
	current = next((step for step in steps if step["process_name"] == current_process), None)
	if not current:
		return []
	name_counts = Counter(step["process_name"] for step in steps)
	return [
		{
			"value": process_step_key(step),
			"label": (
				_("{0} (Step {1})").format(step["process_name"], step["position"] + 1)
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
	match = next((option for option in options if option["value"] == source_process), None)
	# Process-name fallback keeps API callers created before step keys working,
	# but only when the name identifies exactly one eligible earlier step.
	if not match:
		by_name = [option for option in options if option["process_name"] == source_process]
		match = by_name[0] if len(by_name) == 1 else None
	if not match:
		frappe.throw(
			_("{0} is not an earlier process of {1} on IPD {2}.").format(
				source_process, current_process, ipd.name
			)
		)
	return match


def _require_immediate_source(ipd, current_process, selected):
	options = get_source_process_options(ipd, current_process)
	if not options or selected.get("value") != options[0].get("value"):
		frappe.throw(
			_("Versioned cloth execution must use the immediate predecessor process.")
		)
	return selected


def fill_from_source_grns(qty_rows, *, lot, ipd, current_process, current_work_order, source_process):
	"""Mutate popup rows with fillable output quantities from source GRNs.

	One physical source variant can feed several output rules (Greige -> Red and
	Greige -> Navy).  Those rows receive the same shared availability but stay at
	zero so the operator explicitly allocates the pool.
	"""
	selected = resolve_source_process(ipd, current_process, source_process)
	versioned_target = _uses_exact_source_pool(current_work_order)
	availability = get_source_availability(
		lot=lot,
		ipd=ipd.name,
		cloth_item=ipd.item,
		source_process=selected["process_name"],
		source_step=selected["value"],
		current_process=current_process,
		current_work_order=current_work_order,
	)
	mode = availability.get("source_mode")
	legacy_availability = availability.get("legacy_availability")
	if versioned_target and mode == "exact":
		_require_immediate_source(ipd, current_process, selected)
	elif versioned_target and mode == "mixed":
		options = get_source_process_options(ipd, current_process)
		if not options or selected.get("value") != options[0].get("value"):
			# Earlier legacy steps remain selectable for the one allowed downgrade;
			# exact keyed stock is only legal from the immediate predecessor.
			availability = legacy_availability or availability
			legacy_availability = None
			mode = "legacy"
		else:
			_require_immediate_source(ipd, current_process, selected)
	net = availability["net"]
	positive = {variant: qty for variant, qty in net.items() if qty > QTY_TOLERANCE}
	legacy_positive = {
		variant: qty
		for variant, qty in ((legacy_availability or {}).get("net") or {}).items()
		if qty > QTY_TOLERANCE
	}
	if not positive and not legacy_positive:
		frappe.throw(
			_("No unallocated submitted GRN quantity is available from process {0}.").format(
				selected["process_name"]
			)
		)

	if availability.get("buckets"):
		from essdee_yrp.fabric_substitution import get_process_conversion_index

		original_rows = deepcopy(qty_rows)
		variant_info = _variant_info(positive)
		route_targets = None
		options = get_source_process_options(ipd, current_process)
		default_knitting = frappe.db.get_single_value(
			"SD YRP IPD Settings", "default_knitting_process"
		)
		if (
			default_knitting
			and selected["process_name"] == default_knitting
			and options
			and options[0]["value"] == selected["value"]
		):
			route_targets = _knitting_factor_targets(qty_rows, lot, ipd)
		conversion_index = get_process_conversion_index(
			lot,
			process_name=current_process,
			production_detail=ipd.name,
		)
		unmatched = _project_receipt_buckets(
			qty_rows,
			availability["buckets"],
			variant_info,
			conversion_index=conversion_index,
			route_targets=route_targets,
		)
		for row in qty_rows:
			row["source_mode"] = "exact"
		if legacy_positive:
			legacy_rows = deepcopy(original_rows)
			legacy_unmatched = _fill_legacy_variant_rows(
				legacy_rows,
				legacy_positive,
				_variant_info(legacy_positive),
				current_process,
				selected,
				mark_mode=True,
			)
			qty_rows.extend(legacy_rows)
			unmatched.extend(legacy_unmatched)
		received_total = sum(availability["received"].values()) + sum(
			(legacy_availability or {}).get("received", {}).values()
		)
		reserved_total = sum(availability["reserved"].values()) + sum(
			(legacy_availability or {}).get("reserved", {}).values()
		)
		return {
			"value": selected["value"],
			"process_name": selected["process_name"],
			"label": selected["label"],
			"received": flt(received_total, 3),
			"reserved": flt(reserved_total, 3),
			"available": flt(sum(positive.values()) + sum(legacy_positive.values()), 3),
			"unmatched": unmatched,
			"sources": _source_breakdown(availability["buckets"]),
			"source_mode": "mixed" if legacy_positive else "exact",
		}
	variant_info = _variant_info(positive)
	unmatched = _fill_legacy_variant_rows(
		qty_rows,
		positive,
		variant_info,
		current_process,
		selected,
		mark_mode=versioned_target,
	)
	return {
		"value": selected["value"],
		"process_name": selected["process_name"],
		"label": selected["label"],
		"received": flt(sum(availability["received"].values()), 3),
		"reserved": flt(sum(availability["reserved"].values()), 3),
		"available": flt(sum(positive.values()), 3),
		"unmatched": unmatched,
		"source_mode": "legacy" if versioned_target else None,
	}


def _fill_legacy_variant_rows(
	qty_rows,
	positive,
	variant_info,
	current_process,
	selected,
	*,
	mark_mode=False,
):
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
			spec_matches = {variant for variant, info in variant_info.items() if _matches_input(info, spec)}
			matched.update(spec_matches)
			available = sum(positive[variant] for variant in spec_matches)
			capacities.append(available * output_qty / required)
		capacity = min(capacities) if capacities else 0
		row_matches.append((qty_row, matched, capacity))
		all_matched.update(matched)
		match_counts.update(matched)

	if not all_matched:
		labels = ", ".join(_variant_label(variant, variant_info[variant]) for variant in sorted(positive))
		frappe.throw(
			_(
				"Process {0} received {1}, but the current {2} popup has no compatible input row. "
				"Check the IPD process mapping or select another source process."
			).format(selected["process_name"], labels, current_process)
		)

	for qty_row, matched, capacity in row_matches:
		shared = any(match_counts[variant] > 1 for variant in matched)
		qty_row.update(
			{
				"source_process": selected["process_name"],
				"source_process_step": selected["value"],
				"source_available": flt(capacity, 3),
				"source_shared": shared,
				"source_pool_key": "|".join(sorted(matched)),
				# Never guess a split when several target rules consume the same
				# physical GRN variant. Unique matches can be filled completely.
				"prefill": 0 if shared else flt(capacity, 3),
			}
		)
		if mark_mode:
			qty_row["source_mode"] = "legacy"

	return [
		_variant_label(variant, variant_info[variant]) for variant in sorted(set(positive) - all_matched)
	]


def validate_source_demands(
	demands,
	*,
	lot,
	ipd,
	cloth_item,
	current_process,
	current_work_order,
	source_process,
):
	"""Recheck source availability during Calculate; the popup may be stale."""
	selected = resolve_source_process(ipd, current_process, source_process)
	if _uses_exact_source_pool(current_work_order):
		selected_rows = [row for row in demands or [] if flt(row.get("qty")) > ZERO_QTY_EPSILON]
		bucket_keys = [_row_source_bucket_key(row) for row in selected_rows]
		if any(bucket_keys) and not all(bucket_keys):
			frappe.throw(
				_("Cloth source selection cannot contain mixed keyed and legacy rows.")
			)
		if bucket_keys and all(bucket_keys):
			_require_immediate_source(ipd, current_process, selected)
			pool = prepare_source_pool(
				lot,
				ipd.name,
				selected["process_name"],
				for_update=True,
				exclude_work_order=current_work_order,
			)
			if pool.get("source_mode") == "invalid":
				_throw_source_mode_error("invalid")
			return {**selected, "source_mode": "exact", "pool": pool}
		# No submitted row selected an exact bucket. Use the unchanged legacy
		# validation; Task 4 persists the one allowed first-calculation downgrade.
	# Serialize calculations for the same Lot and hold every currently submitted
	# source receipt until this request commits.  The second concurrent Work Order
	# therefore sees the first one's saved reservation; a source GRN cannot be
	# cancelled between this availability check and the Work Order save.
	_lock_source_transactions(lot, cloth_item, selected["process_name"], ipd=ipd)
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
					"{0}: requested {1} Kg from {2}, but only {3} Kg remains available "
					"in submitted GRNs. Reopen Fill Quantity."
				).format(variant, flt(qty, 3), selected["process_name"], flt(available, 3))
			)
	return {**selected, "source_mode": "legacy"}


def _row_source_bucket_key(row):
	return row.get("source_bucket_key") or get_row_execution_parameters(row).get(
		"source_bucket_key"
	)


def get_source_availability(
	*,
	lot,
	ipd,
	cloth_item,
	source_process,
	source_step,
	current_process,
	current_work_order,
):
	"""Keep legacy Item totals unchanged; version 1 uses exact physical rows."""
	if not _uses_exact_source_pool(current_work_order):
		return _get_legacy_source_availability(
			lot=lot,
			ipd=ipd,
			cloth_item=cloth_item,
			source_process=source_process,
			source_step=source_step,
			current_process=current_process,
			current_work_order=current_work_order,
		)
	pool = prepare_source_pool(
		lot,
		ipd,
		source_process,
		for_update=False,
	)
	mode = pool.get("source_mode")
	if mode == "invalid":
		_throw_source_mode_error(mode)
	legacy = None
	if mode in {"legacy", "mixed"}:
		legacy = _get_legacy_source_availability(
			lot=lot,
			ipd=ipd,
			cloth_item=cloth_item,
			source_process=source_process,
			source_step=source_step,
			current_process=current_process,
			current_work_order=current_work_order,
		)
	buckets = []
	for bucket in (pool.get("buckets") or {}).values():
		bucket = {**bucket, "source_process_step": source_step}
		buckets.append(bucket)
	received = defaultdict(float)
	reserved = defaultdict(float)
	for bucket in buckets:
		received[bucket["item_variant"]] += flt(bucket.get("received_stock_qty"), 6)
		reserved[bucket["item_variant"]] += flt(bucket.get("reserved_stock_qty"), 6)
	variants = set(received) | set(reserved)
	exact_result = {
		"received": {item: flt(quantity, 6) for item, quantity in received.items()},
		"reserved": {item: flt(quantity, 6) for item, quantity in reserved.items()},
		"net": {
			item: flt(max(received[item] - reserved[item], 0), 6)
			for item in variants
		},
		"buckets": buckets,
		"default_received_type": pool.get("default_received_type"),
	}
	exact_available = any(
		flt(quantity, 6) > ZERO_QTY_EPSILON
		for quantity in exact_result["net"].values()
	)
	legacy_available = any(
		flt(quantity, 6) > QTY_TOLERANCE
		for quantity in ((legacy or {}).get("net") or {}).values()
	)
	if exact_available and legacy_available:
		return {
			**exact_result,
			"source_mode": "mixed",
			"legacy_availability": legacy,
		}
	if legacy_available:
		return {**legacy, "source_mode": "legacy"}
	return {
		**exact_result,
		"source_mode": "exact" if exact_available else "none",
	}


def _throw_source_mode_error(mode):
	if mode == "mixed":
		frappe.throw(
			_("Cloth source selection cannot contain mixed keyed and legacy receipts.")
		)
	frappe.throw(
		_("A versioned cloth source receipt is missing its execution identity.")
	)


def _uses_exact_source_pool(work_order):
	return bool(
		work_order
		and frappe.db.has_column("YRP Work Order", "cloth_execution_version")
		and is_versioned_cloth_work_order(work_order)
	)


def prepare_source_pool(
	lot,
	production_detail,
	source_process,
	*,
	for_update=False,
	exclude_work_order=None,
):
	"""Return exact keyed receipt buckets, optionally under current row locks."""
	from yrp.stock.dimensions import assert_safe_fieldname, get_dimension_fieldnames

	dimension_fields = get_dimension_fieldnames()
	for fieldname in dimension_fields:
		assert_safe_fieldname(fieldname)
	default_received_type = frappe.db.get_single_value(
		"YRP Stock Settings", "default_received_type"
	)
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings."))
	default_knitting = frappe.db.get_single_value(
		"SD YRP IPD Settings", "default_knitting_process"
	)
	physical_knitting_source = bool(
		default_knitting and source_process == default_knitting
	)

	locking = "FOR UPDATE" if for_update else ""
	if for_update:
		frappe.db.sql(
			"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE",
			(lot,),
		)

	grn_names = frappe.db.sql(
		f"""
		SELECT grn.name
		FROM `tabYRP Goods Received Note` grn
		JOIN `tabYRP Work Order` source_wo ON source_wo.name = grn.against_id
		WHERE grn.docstatus = 1
			AND grn.against = 'YRP Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND IFNULL(grn.is_rework, 0) = 0
			AND IFNULL(grn.includes_packing, 0) = 0
			AND source_wo.lot = %(lot)s
			AND source_wo.production_detail = %(production_detail)s
			AND source_wo.process_name = %(source_process)s
		ORDER BY grn.name
		{locking}
		""",
		{
			"lot": lot,
			"production_detail": production_detail,
			"source_process": source_process,
		},
		pluck=True,
	)
	if not grn_names:
		return {
			"lot": lot,
			"production_detail": production_detail,
			"source_process": source_process,
			"default_received_type": default_received_type,
			"dimension_fields": dimension_fields,
			"physical_knitting_source": physical_knitting_source,
			"source_mode": "none",
			"rows": [],
			"buckets": {},
		}

	dimension_select = "".join(
		f", item.`{fieldname}` AS `{fieldname}`" for fieldname in dimension_fields
	)
	receipt_rows = frappe.db.sql(
		f"""
		SELECT grn.name AS source_grn,
			item.name AS source_grn_item,
			item.idx AS source_grn_row,
			item.item_variant,
			item.stock_qty,
			item.quantity,
			item.uom,
			item.stock_uom,
			item.conversion_factor,
			item.set_combination,
			grn.posting_date,
			grn.posting_time,
			grn.creation,
			grn.supplier,
			grn.to_warehouse AS source_warehouse,
			wo.name AS source_work_order,
			wo.process_name AS source_process,
			wo.cloth_execution_version,
			receivable.qty AS planned_qty,
			receivable.fabric_reference_variant AS reference_item_variant,
			receivable.fabric_reference_allocations,
			receivable.additional_parameters
			{dimension_select}
		FROM `tabYRP Goods Received Note Item` item
		JOIN `tabYRP Goods Received Note` grn ON grn.name = item.parent
		JOIN `tabYRP Work Order` wo ON wo.name = grn.against_id
		JOIN `tabYRP Work Order Receivables` receivable
			ON receivable.name = item.ref_docname
			AND receivable.parent = wo.name
		WHERE grn.name IN %(grn_names)s
			AND item.parenttype = 'YRP Goods Received Note'
			AND item.ref_doctype = 'YRP Work Order Receivables'
		ORDER BY grn.name, item.idx, item.name
		{locking}
		""",
		{"grn_names": tuple(grn_names)},
		as_dict=True,
	)
	source_mode = _classify_source_receipts(
		receipt_rows, default_received_type
	)
	keyed_receipts = [
		row
		for row in receipt_rows
		if _is_eligible_exact_receipt(row, default_received_type)
	]
	source_items = sorted(
		{
			row.source_grn_item
			for row in keyed_receipts
			if row.get("source_grn_item")
		}
	)
	consumption_rows = []
	if source_items:
		exclude_condition = "AND item.parent != %(exclude_work_order)s" if exclude_work_order else ""
		consumption_rows = frappe.db.sql(
			f"""
			SELECT item.name,
				item.parent,
				item.source_grn_item,
				item.item_variant,
				item.qty,
				item.pending_quantity,
				item.stock_update,
				item.uom,
				item.additional_parameters,
				item.fabric_reference_variant,
				item.fabric_reference_allocations,
				item.docstatus
			FROM `tabYRP Work Order Deliverables` item
			WHERE item.parenttype = 'YRP Work Order'
				AND item.source_grn_item IN %(source_items)s
				{exclude_condition}
			ORDER BY item.parent, item.idx, item.name
			{locking}
			""",
			{
				"source_items": tuple(source_items),
				"exclude_work_order": exclude_work_order,
			},
			as_dict=True,
		)
		_mark_rework_consumption_rows(consumption_rows, for_update=for_update)

	bucket_rows = _build_source_buckets(
		keyed_receipts,
		consumption_rows,
		default_received_type=default_received_type,
		dimension_fields=dimension_fields,
		physical_knitting_source=physical_knitting_source,
	)
	return {
		"lot": lot,
		"production_detail": production_detail,
		"source_process": source_process,
		"default_received_type": default_received_type,
		"dimension_fields": dimension_fields,
		"physical_knitting_source": physical_knitting_source,
		"source_mode": source_mode,
		"rows": keyed_receipts,
		"buckets": {
			row["key"]: {
				**row,
				"remaining_stock_qty": flt(row["available_stock_qty"], 6),
			}
			for row in bucket_rows
		},
	}


def _is_eligible_exact_receipt(row, default_received_type):
	return bool(
		cint(row.get("cloth_execution_version")) == 1
		and has_fabric_execution_key(row)
		and (row.get("received_type") or default_received_type)
		== default_received_type
	)


def _classify_source_receipts(receipt_rows, default_received_type):
	modes = set()
	for row in receipt_rows or []:
		if (row.get("received_type") or default_received_type) != default_received_type:
			continue
		stock_qty = flt(row.get("stock_qty"), 6)
		if stock_qty <= ZERO_QTY_EPSILON:
			stock_qty = flt(row.get("quantity"), 6) * _conversion_factor(
				row.get("item_variant"), row.get("uom")
			)
		if stock_qty <= ZERO_QTY_EPSILON:
			continue
		versioned = cint(row.get("cloth_execution_version")) == 1
		keyed = has_fabric_execution_key(row)
		if versioned and keyed:
			modes.add("exact")
		elif not versioned and not keyed:
			modes.add("legacy")
		else:
			modes.add("invalid")
	if "invalid" in modes:
		return "invalid"
	if modes == {"exact", "legacy"}:
		return "mixed"
	return next(iter(modes), "none")


def _mark_rework_consumption_rows(consumption_rows, *, for_update=False):
	parents = {
		row.get("parent")
		for row in consumption_rows or []
		if (
			row.get("parent")
			and int(row.get("docstatus") or 0) == 1
			and not _row_source_bucket_key(row)
			and max(
				flt(row.get("qty")) - flt(row.get("pending_quantity")),
				flt(row.get("stock_update")),
			) > ZERO_QTY_EPSILON
		)
	}
	if not parents:
		return
	if for_update:
		rows = frappe.db.sql(
			"""
			SELECT name, is_rework
			FROM `tabYRP Work Order`
			WHERE name IN %(parents)s
			ORDER BY name
			FOR UPDATE
			""",
			{"parents": tuple(sorted(parents))},
			as_dict=True,
		)
		rework_parents = {row.name for row in rows if row.get("is_rework")}
	else:
		rework_parents = set(
			frappe.get_all(
				"YRP Work Order",
				filters={"name": ["in", sorted(parents)], "is_rework": 1},
				pluck="name",
			)
		)
	for row in consumption_rows or []:
		row["is_rework"] = row.get("parent") in rework_parents


def _get_legacy_source_availability(
	*,
	lot,
	ipd,
	cloth_item,
	source_process,
	source_step,
	current_process,
	current_work_order,
):
	"""Physical Item Variant quantities: submitted source GRNs minus reservations."""
	version_filter = (
		"AND IFNULL(source_wo.cloth_execution_version, 0) = 0"
		if (
			frappe.db.has_column("YRP Work Order", "cloth_execution_version")
			and not _legacy_source_allows_versioned_washing(ipd, source_process)
		)
		else ""
	)
	target_version_filter = (
		"AND IFNULL(target_wo.cloth_execution_version, 0) = 0"
		if frappe.db.has_column("YRP Work Order", "cloth_execution_version")
		else ""
	)
	received_rows = frappe.db.sql(
		f"""
		SELECT item.item_variant, item.stock_qty, item.quantity, item.uom
		FROM `tabYRP Goods Received Note Item` item
		JOIN `tabYRP Goods Received Note` grn ON grn.name = item.parent
		JOIN `tabYRP Work Order` source_wo ON source_wo.name = grn.against_id
		WHERE item.parenttype = 'YRP Goods Received Note'
			AND grn.docstatus = 1
			AND grn.against = 'YRP Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND item.ref_doctype = 'YRP Work Order Receivables'
			AND source_wo.lot = %(lot)s
			AND source_wo.item = %(cloth_item)s
			AND source_wo.process_name = %(source_process)s
			{version_filter}
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
	has_source_process = frappe.db.has_column("YRP Work Order", "fabric_source_process")
	has_source_step = frappe.db.has_column("YRP Work Order", "fabric_source_process_step")
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
		FROM `tabYRP Work Order Deliverables` item
		JOIN `tabYRP Work Order` target_wo ON target_wo.name = item.parent
		WHERE item.parenttype = 'YRP Work Order'
			AND target_wo.docstatus < 2
			AND target_wo.name != %(current_work_order)s
			AND target_wo.lot = %(lot)s
			AND target_wo.item = %(cloth_item)s
			AND IFNULL(item.is_calculated, 0) = 1
			{target_version_filter}
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
			variant: flt(flt(received.get(variant)) - flt(reserved.get(variant)), 3) for variant in variants
		},
	}


def _legacy_source_allows_versioned_washing(ipd, source_process):
	if not ipd:
		return False
	try:
		from essdee_yrp.cloth_execution import get_supported_execution_route

		ipd_doc = (
			ipd
			if not isinstance(ipd, str)
			else frappe.get_cached_doc("YRP Item Production Detail", ipd)
		)
		route = get_supported_execution_route(ipd_doc)
	except (frappe.DoesNotExistError, frappe.ValidationError, ImportError):
		return False
	return bool(
		route and source_process == route["washing"].get("process_name")
	)


def _lock_source_transactions(lot, cloth_item, source_process, *, ipd=None):
	"""Lock the shared pool during Calculate, never during popup reads."""
	version_filter = (
		"AND IFNULL(source_wo.cloth_execution_version, 0) = 0"
		if (
			frappe.db.has_column("YRP Work Order", "cloth_execution_version")
			and not _legacy_source_allows_versioned_washing(ipd, source_process)
		)
		else ""
	)
	frappe.db.sql(
		"SELECT name FROM `tabSD YRP Lot` WHERE name = %s FOR UPDATE",
		lot,
	)
	frappe.db.sql(
		f"""
		SELECT grn.name
		FROM `tabYRP Goods Received Note` grn
		JOIN `tabYRP Work Order` source_wo ON source_wo.name = grn.against_id
		WHERE grn.docstatus = 1
			AND grn.against = 'YRP Work Order'
			AND IFNULL(grn.is_return, 0) = 0
			AND source_wo.lot = %(lot)s
			AND source_wo.item = %(cloth_item)s
			AND source_wo.process_name = %(source_process)s
			{version_filter}
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
			factor = flt((get_conversion_factor(variant, row.get("uom")) or {}).get("conversion_factor")) or 1
			stock_qty = qty * factor
		result[variant] = result.get(variant, 0) + stock_qty
	return {variant: flt(qty, 6) for variant, qty in result.items()}


def _variant_info(variants):
	variants = list(variants)
	if not variants:
		return {}
	result = {
		row.name: {"item": row.variant_of or row.name, "attrs": {}}
		for row in frappe.get_all(
			"Item",
			filters={"name": ["in", variants]},
			fields=["name", "variant_of"],
		)
	}
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", variants], "parenttype": "Item"},
		fields=["parent", "attribute", "attribute_value"],
	):
		if row.parent in result:
			result[row.parent]["attrs"][row.attribute] = _attribute_value(row.attribute_value)
	return result


def _matches_input(variant, spec, allow_dia_variance=False):
	if variant.get("item") != spec.get("item"):
		return False
	expected = {key: value for key, value in (spec.get("attrs") or {}).items() if value}
	actual = variant.get("attrs") or {}
	if allow_dia_variance:
		expected.pop(FABRIC_DIA_ATTRIBUTE, None)
	return all(actual.get(key) == value for key, value in expected.items())


def _variant_label(name, info):
	attrs = info.get("attrs") or {}
	details = " · ".join(attrs[key] for key in sorted(attrs))
	return f"{name} ({details})" if details else name


def project_output_attributes(actual_attrs, planned_input_attrs, planned_output_attrs):
	"""Project an exact physical Item through one authored matrix transform."""
	result = {}
	keys = set(actual_attrs or {}) | set(planned_input_attrs or {}) | set(planned_output_attrs or {})
	for attribute in keys:
		actual = (actual_attrs or {}).get(attribute)
		planned_input = (planned_input_attrs or {}).get(attribute)
		planned_output = (planned_output_attrs or {}).get(attribute)
		if planned_output:
			if planned_input and planned_input == planned_output and actual:
				result[attribute] = actual
			else:
				result[attribute] = planned_output
		elif actual:
			result[attribute] = actual
	return result


def _normalise_json(value):
	if isinstance(value, dict):
		return value
	try:
		return frappe.parse_json(value or "{}") or {}
	except (TypeError, ValueError):
		return {}


def _bucket_key(
	source_grn_item,
	reference=None,
	*,
	item_variant=None,
	received_type=None,
	warehouse=None,
	set_combination=None,
	dimensions=None,
):
	payload = {
		"source_grn_item": source_grn_item,
		"reference": reference or None,
		"item_variant": item_variant,
		"received_type": received_type,
		"warehouse": warehouse,
		"set_combination": _normalise_json(set_combination),
		"dimensions": {
			fieldname: value or None
			for fieldname, value in sorted((dimensions or {}).items())
		},
	}
	raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
	return f"fabric-source-{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


def _conversion_factor(item_variant, uom):
	from yrp.stock.utils import get_conversion_factor

	return flt(
		(get_conversion_factor(item_variant, uom) or {}).get("conversion_factor")
	) or 1


def _build_source_buckets(
	receipt_rows,
	consumption_rows,
	*,
	default_received_type,
	dimension_fields,
	physical_knitting_source,
):
	"""Build exact request-local buckets from current receipt/dispatch rows."""
	buckets = []
	buckets_by_key = {}
	for row in receipt_rows or []:
		received_type = row.get("received_type") or default_received_type
		if received_type != default_received_type:
			continue
		stock_qty = flt(row.get("stock_qty"), 6)
		if stock_qty <= ZERO_QTY_EPSILON:
			stock_qty = flt(row.get("quantity"), 6) * _conversion_factor(
				row.get("item_variant"), row.get("uom")
			)
		if stock_qty <= ZERO_QTY_EPSILON:
			continue
		dimensions = {
			fieldname: (
				received_type
				if fieldname == "received_type"
				else row.get(fieldname)
			)
			for fieldname in dimension_fields
		}
		if physical_knitting_source:
			references = {None: stock_qty}
		else:
			allocations = get_reference_allocations(
				row, row.get("planned_qty") or stock_qty
			)
			references = scale_reference_allocations(allocations, stock_qty)
			if not references:
				references = {row.get("reference_item_variant") or None: stock_qty}
		for reference, reference_qty in references.items():
			if flt(reference_qty, 6) <= ZERO_QTY_EPSILON:
				continue
			key = _bucket_key(
				row.get("source_grn_item"),
				reference,
				item_variant=row.get("item_variant"),
				received_type=received_type,
				warehouse=row.get("source_warehouse"),
				set_combination=row.get("set_combination"),
				dimensions=dimensions,
			)
			bucket = {
				"key": key,
				"source_grn": row.get("source_grn"),
				"source_grn_item": row.get("source_grn_item"),
				"source_grn_row": row.get("source_grn_row"),
				"source_work_order": row.get("source_work_order"),
				"source_process": row.get("source_process"),
				"supplier": row.get("supplier"),
				"source_warehouse": row.get("source_warehouse"),
				"posting_date": row.get("posting_date"),
				"posting_time": row.get("posting_time"),
				"item_variant": row.get("item_variant"),
				"uom": row.get("uom") or row.get("stock_uom"),
				"received_type": received_type,
				"set_combination": row.get("set_combination"),
				"stock_dimensions": dimensions,
				"reference_item_variant": reference,
				"received_stock_qty": flt(reference_qty, 6),
				"reserved_stock_qty": 0.0,
				"available_stock_qty": flt(reference_qty, 6),
			}
			buckets.append(bucket)
			buckets_by_key[key] = bucket

	for row in consumption_rows or []:
		if int(row.get("docstatus") or 0) in (0, 2):
			continue
		planned_qty = max(flt(row.get("qty")), 0)
		delivered_qty = max(planned_qty - flt(row.get("pending_quantity")), 0)
		consumed_qty = max(flt(row.get("stock_update")), 0)
		executed_qty = max(delivered_qty, consumed_qty)
		if executed_qty <= ZERO_QTY_EPSILON:
			continue
		bucket_key = get_row_execution_parameters(row).get("source_bucket_key")
		if not bucket_key:
			if row.get("is_rework"):
				# Base-YRP inspection rework points back to the original GRN row but
				# intentionally owns a separate Received-Type/rework contract.
				continue
			frappe.throw(
				_("Submitted cloth usage is missing its exact source bucket identity.")
			)
		bucket = buckets_by_key.get(bucket_key)
		if not bucket:
			frappe.throw(
				_("Submitted cloth usage references an unavailable source bucket identity.")
			)
		if (
			row.get("source_grn_item") != bucket.get("source_grn_item")
			or row.get("item_variant") != bucket.get("item_variant")
		):
			frappe.throw(
				_("Submitted cloth usage changed its exact source bucket identity.")
			)
		stock_qty = executed_qty * _conversion_factor(
			row.get("item_variant"), row.get("uom")
		)
		bucket["reserved_stock_qty"] += flt(stock_qty, 6)

	result = []
	for bucket in buckets:
		available = flt(
			bucket["received_stock_qty"] - bucket["reserved_stock_qty"], 6
		)
		bucket["available_stock_qty"] = 0 if abs(available) < ZERO_QTY_EPSILON else max(available, 0)
		if bucket["available_stock_qty"] > ZERO_QTY_EPSILON:
			result.append(bucket)
	return result


def consume_source_bucket(pool, bucket_key, required_stock_qty):
	bucket = (pool.get("buckets") or {}).get(bucket_key)
	if not bucket:
		frappe.throw(_("The selected source GRN row is no longer available. Reopen Calculate."))
	required_stock_qty = flt(required_stock_qty, 6)
	available = flt(bucket.get("remaining_stock_qty"), 6)
	if _exceeds_available(required_stock_qty, available):
		frappe.throw(
			_(
				"The exact source GRN row {0} / {1} has only {2} Kg available; "
				"{3} Kg was requested. Reopen Calculate."
			).format(
				bucket.get("source_grn") or _("(unknown GRN)"),
				bucket.get("source_grn_item") or bucket_key,
				flt(available, 3),
				flt(required_stock_qty, 3),
			)
		)
	bucket["remaining_stock_qty"] = flt(available - required_stock_qty, 6)
	return bucket


def _validate_source_bucket_identity(row, bucket, dimension_fields):
	if row.get("source_grn") != bucket.get("source_grn") or row.get(
		"source_grn_item"
	) != bucket.get("source_grn_item"):
		frappe.throw(_("The exact source GRN lineage changed. Reopen Calculate."))
	if row.get("item_variant") != bucket.get("item_variant"):
		frappe.throw(_("The exact source Item changed. Reopen Calculate."))
	if _normalise_json(row.get("set_combination")) != _normalise_json(
		bucket.get("set_combination")
	):
		frappe.throw(_("The exact source set combination changed. Reopen Calculate."))
	for fieldname in dimension_fields:
		expected = (bucket.get("stock_dimensions") or {}).get(fieldname)
		if (row.get(fieldname) or None) != (expected or None):
			frappe.throw(
				_("The exact source stock dimension {0} changed. Reopen Calculate.").format(
					fieldname
				)
			)


def _project_receipt_buckets(
	qty_rows, buckets, variant_info, conversion_index=None, route_targets=None
):
	projected = []
	unmatched = []
	remaining_targets = dict(route_targets or {})
	from essdee_yrp.api.work_order import _resolve_variant, _variant_attrs
	from essdee_yrp.fabric_substitution import resolve_process_conversion

	for bucket in buckets:
		if flt(bucket.get("available_stock_qty"), 6) <= ZERO_QTY_EPSILON:
			continue
		variant = variant_info.get(bucket.get("item_variant"))
		if not variant:
			unmatched.append(bucket.get("item_variant"))
			continue
		matches = []
		for qty_row in qty_rows:
			row_reference = qty_row.get("reference_item_variant") or None
			bucket_reference = bucket.get("reference_item_variant") or None
			if bucket_reference and row_reference != bucket_reference:
				continue
			for input_index, spec in enumerate(qty_row.get("input_specs") or []):
				if _matches_input(variant, spec, allow_dia_variance=True):
					matches.append((qty_row, input_index, spec))
		if not matches:
			unmatched.append(_variant_label(bucket["item_variant"], variant))
			continue

		shared = len(matches) > 1
		remaining_stock_qty = flt(bucket["available_stock_qty"], 6)
		for qty_row, input_index, spec in matches:
			output_qty = flt(qty_row.get("output_qty")) or 1
			required = flt(spec.get("qty")) * (1 + flt(spec.get("wastage_pct")) / 100)
			if required <= 0:
				continue
			factor = _conversion_factor(bucket["item_variant"], spec.get("uom"))
			capacity = _floor_source_quantity(
				(remaining_stock_qty / factor) * output_qty / required, 3
			)
			matrix_key = qty_row.get("matrix_key") or qty_row.get("key")
			if route_targets is not None:
				target_key = (matrix_key, bucket["item_variant"])
				target_qty = flt(remaining_targets.get(target_key), 3)
				if target_qty <= ZERO_QTY_EPSILON:
					continue
				prefill = _floor_source_quantity(min(capacity, target_qty), 3)
				remaining_targets[target_key] = flt(max(target_qty - prefill, 0), 3)
			else:
				prefill = 0 if shared else capacity
			if prefill > ZERO_QTY_EPSILON:
				remaining_stock_qty = flt(
					max(remaining_stock_qty - prefill * required / output_qty * factor, 0),
					6,
				)
			elif route_targets is not None:
				continue

			actual_attrs = variant.get("attrs") or {}
			projected_attrs = project_output_attributes(
				actual_attrs, spec.get("attrs") or {}, qty_row.get("out_attrs") or {}
			)
			output_item = qty_row.get("output_item") or spec.get("item")
			planned_item = _resolve_variant(output_item, qty_row.get("out_attrs") or {})
			projected_item = _resolve_variant(output_item, projected_attrs)
			projected_item = resolve_process_conversion(
				conversion_index,
				route_item=bucket.get("reference_item_variant"),
				planned_item=planned_item,
				projected_item=projected_item,
			)
			projected_attrs = _variant_attrs(projected_item)
			row = deepcopy(qty_row)
			execution_key = _execution_key(
				bucket["key"], matrix_key, bucket.get("reference_item_variant")
			)
			row.update(
				{
					"key": execution_key,
					"matrix_key": matrix_key,
					"execution_key": execution_key,
					"in_attrs": actual_attrs,
					"out_attrs": projected_attrs,
					"projected_item_variant": projected_item,
					"source_process": bucket.get("source_process"),
					"source_process_step": bucket.get("source_process_step"),
					"source_bucket_key": bucket["key"],
					"source_grn": bucket.get("source_grn"),
					"source_grn_item": bucket.get("source_grn_item"),
					"source_grn_row": bucket.get("source_grn_row"),
					"source_work_order": bucket.get("source_work_order"),
					"source_supplier": bucket.get("supplier"),
					"source_item_variant": bucket.get("item_variant"),
					"source_received": flt(bucket.get("received_stock_qty"), 3),
					"source_reserved": flt(bucket.get("reserved_stock_qty"), 3),
					"source_available": capacity,
					"source_stock_available": flt(bucket.get("available_stock_qty"), 6),
					"source_stock_per_output": flt(required * factor / output_qty, 9),
					"source_shared": shared and route_targets is None,
					"source_pool_key": bucket["key"],
					"source_input_index": input_index,
					"prefill": prefill,
				}
			)
			projected.append(row)

	qty_rows[:] = projected
	return unmatched


def _execution_key(bucket_key, matrix_key, reference):
	raw = f"{bucket_key}|{matrix_key}|{reference or ''}"
	return f"fabric-{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


def _knitting_factor_targets(qty_rows, lot, ipd):
	from essdee_yrp.api.work_order import _resolve_variant
	from essdee_yrp.fabric_substitution import (
		allocate_route_quantity,
		get_actual_dia_factors,
	)

	targets = defaultdict(float)
	for qty_row in qty_rows:
		principal = next(
			(
				spec
				for spec in qty_row.get("input_specs") or []
				if spec.get("item") == ipd.item and flt(spec.get("qty")) > 0
			),
			None,
		)
		if not principal:
			continue
		planned_item = _resolve_variant(
			principal["item"], principal.get("attrs") or {}
		)
		factors = get_actual_dia_factors(lot, ipd.name, planned_item)
		planned_route_qty = flt(
			qty_row.get("plan") or qty_row.get("program") or qty_row.get("prefill")
		)
		matrix_key = qty_row.get("matrix_key") or qty_row.get("key")
		for allocation in allocate_route_quantity(planned_route_qty, factors):
			targets[(matrix_key, allocation["actual_item"])] += flt(
				allocation["quantity"], 3
			)
	return dict(targets)


def _source_breakdown(buckets):
	return [
		{
			"key": row["key"],
			"grn": row.get("source_grn"),
			"grn_item": row.get("source_grn_item"),
			"work_order": row.get("source_work_order"),
			"supplier": row.get("supplier"),
			"warehouse": row.get("source_warehouse"),
			"item_variant": row.get("item_variant"),
			"reference_item_variant": row.get("reference_item_variant"),
			"received_type": row.get("received_type"),
			"stock_dimensions": row.get("stock_dimensions") or {},
			"received": flt(row.get("received_stock_qty"), 3),
			"reserved": flt(row.get("reserved_stock_qty"), 3),
			"available": flt(row.get("available_stock_qty"), 3),
		}
		for row in buckets
		if flt(row.get("available_stock_qty"), 6) > ZERO_QTY_EPSILON
	]


def validate_work_order_source_allocations(work_order):
	"""Revalidate version-1 exact-source rows whenever the Work Order saves."""
	if not work_order:
		return
	all_rows = list(work_order.get("deliverables") or []) + list(
		work_order.get("receivables") or []
	)
	has_execution_contract = any(_row_has_execution_contract(row) for row in all_rows)
	if work_order.get("is_rework"):
		if has_execution_contract:
			frappe.throw(
				_("A versioned fabric execution contract cannot be converted to Rework.")
			)
		return
	if not is_versioned_cloth_work_order(work_order):
		if has_execution_contract:
			frappe.throw(_("A legacy Work Order cannot consume keyed cloth stock."))
		return
	if (
		int(work_order.get("docstatus") or 0) == 2
		or not work_order.get("lot")
		or not work_order.get("production_detail")
		or not work_order.get("process_name")
	):
		return
	ipd = frappe.get_cached_doc(
		"YRP Item Production Detail", work_order.production_detail
	)
	if not get_source_process_options(ipd, work_order.process_name):
		return
	if not has_execution_contract and not any(
		row.get("is_calculated") for row in work_order.get("deliverables") or []
	):
		# A newly inserted downstream draft is allowed to exist before its first
		# Calculate. No source identity exists yet, so there is nothing to lock or
		# revalidate and the one-time legacy downgrade remains reachable.
		return
	source_step = work_order.get("fabric_source_process_step")
	if not source_step:
		frappe.throw(
			_("This fabric process has no exact source-process step. Reopen Calculate.")
		)
	selected = resolve_source_process(ipd, work_order.process_name, source_step)
	_require_immediate_source(ipd, work_order.process_name, selected)
	if work_order.get("fabric_source_process") and work_order.fabric_source_process != selected[
		"process_name"
	]:
		frappe.throw(_("The saved fabric source process changed. Reopen Calculate."))
	pool = prepare_source_pool(
		work_order.lot,
		work_order.production_detail,
		selected["process_name"],
		for_update=True,
		exclude_work_order=work_order.name,
	)
	if pool.get("source_mode") == "invalid":
		_throw_source_mode_error("invalid")
	receivable_keys = {
		get_row_execution_parameters(row).get("fabric_execution_key")
		for row in work_order.get("receivables") or []
		if (
			_item_belongs_to_template(row.get("item_variant"), ipd.item)
			and get_row_execution_parameters(row).get("fabric_execution_key")
		)
	}
	calculated_rows = [
		row
		for row in work_order.get("deliverables") or []
		if row.get("is_calculated") and flt(row.get("qty")) > ZERO_QTY_EPSILON
	]
	material_rows = []
	for row in calculated_rows:
		if _item_belongs_to_template(row.get("item_variant"), ipd.item):
			material_rows.append(row)
		elif _row_has_execution_contract(row) or row.get("source_grn_item"):
			frappe.throw(
				_("A non-cloth consumable cannot carry exact fabric source lineage.")
			)
	linked_keys = set()
	for row in material_rows:
		parameters = get_row_execution_parameters(row)
		execution_key = parameters.get("fabric_execution_key")
		bucket_key = parameters.get("source_bucket_key")
		if not row.get("source_grn_item"):
			frappe.throw(
				_("A calculated fabric input is missing its exact source GRN row.")
			)
		if not execution_key or not bucket_key:
			frappe.throw(_("An exact source row is missing its execution identity."))
		stock_qty = flt(row.get("qty"), 6) * _conversion_factor(
			row.get("item_variant"), row.get("uom")
		)
		bucket = consume_source_bucket(pool, bucket_key, stock_qty)
		expected_execution_key = _execution_key(
			bucket_key,
			parameters.get("matrix_key"),
			bucket.get("reference_item_variant"),
		)
		if execution_key != expected_execution_key:
			frappe.throw(
				_("The exact source route identity changed. Reopen Calculate.")
			)
		linked_keys.add(execution_key)
		_validate_source_bucket_identity(
			row, bucket, pool.get("dimension_fields") or []
		)
	if receivable_keys != linked_keys:
		frappe.throw(
			_(
				"The calculated fabric outputs and exact source rows no longer match. "
				"Reopen Calculate."
			)
		)


def _row_has_execution_contract(row):
	parameters = get_row_execution_parameters(row)
	return bool(
		parameters.get("fabric_execution_key")
		or parameters.get("source_bucket_key")
	)


def _item_belongs_to_template(item_code, template):
	if not item_code or not template:
		return False
	if item_code == template:
		return True
	return frappe.get_cached_value("Item", item_code, "variant_of") == template
