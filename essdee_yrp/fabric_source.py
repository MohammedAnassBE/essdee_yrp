"""Transaction-backed quantity filling for fabric Work Orders.

The Lot conversion table selects planned-to-actual Item substitutions. Actual
availability is derived from submitted GRN rows. Draft Work Orders do not
reserve stock; only material already dispatched/consumed is deducted, while
the Stock module remains the submission-time availability authority.
"""

from collections import Counter, defaultdict
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_steps
from essdee_yrp.fabric_ipd import FABRIC_DIA_ATTRIBUTE
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	scale_reference_allocations,
)


ZERO_QTY_EPSILON = 1e-9
# Backward-compatible import for inspection allocation. This is floating-point
# noise tolerance, not one whole 0.001 kg stock quantum.
QTY_TOLERANCE = ZERO_QTY_EPSILON
ELIGIBLE_RECEIVED_TYPE = "Accepted"


def _exceeds_available(requested, available):
	"""Reject every material over-allocation, ignoring only float noise."""
	return flt(requested) - flt(available) > ZERO_QTY_EPSILON


def process_step_key(step):
	return f"{int(step['position'])}::{step['process_name']}"


def get_source_process_options(ipd, current_process):
	"""Earlier physical steps, with the immediate predecessor selected first."""
	steps = get_fabric_steps(ipd)
	name_counts = Counter(row["process_name"] for row in steps)
	if name_counts[current_process] > 1:
		frappe.throw(_(
			"IPD {0} repeats process {1}; exact GRN lineage requires unique fabric "
			"process names."
		).format(ipd.name, current_process))
	current = next(
		(step for step in steps if step["process_name"] == current_process), None
	)
	if not current:
		return []
	prior_steps = steps[: current["position"]]
	for step in prior_steps:
		if name_counts[step["process_name"]] > 1:
			frappe.throw(_(
				"IPD {0} repeats predecessor process {1}; submitted GRNs cannot be "
				"assigned to an exact repeated step."
			).format(ipd.name, step["process_name"]))
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
		for step in reversed(prior_steps)
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
	qty_rows, *, lot, ipd, current_process, current_work_order, source_process,
	allow_empty=False,
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
	positive = {variant: qty for variant, qty in net.items() if qty > ZERO_QTY_EPSILON}
	if not positive:
		if allow_empty:
			for qty_row in qty_rows:
				qty_row["prefill"] = 0
				qty_row["source_available"] = 0
			return {
				"value": selected["value"],
				"process_name": selected["process_name"],
				"label": selected["label"],
				"received": flt(sum(availability["received"].values()), 3),
				"reserved": flt(sum(availability["reserved"].values()), 3),
				"available": 0,
				"unavailable": True,
				"unmatched": [],
				"sources": [],
			}
		frappe.throw(
			_('No unallocated submitted GRN quantity is available from process {0}.').format(
				selected["process_name"]
			)
		)

	variant_info = _variant_info(positive)
	if availability.get("buckets"):
		from essdee_yrp.fabric_substitution import get_process_conversion_index

		route_targets = None
		options = get_source_process_options(ipd, current_process)
		default_knitting = frappe.db.get_single_value(
			"IPD Settings", "default_knitting_process"
		)
		if (
			default_knitting
			and selected["process_name"] == default_knitting
			and options
			and options[0]["value"] == selected["value"]
		):
			route_targets = _knitting_factor_targets(qty_rows, lot, ipd)
		conversion_index = get_process_conversion_index(
			lot, ipd.name, current_process
		)
		unmatched = _project_receipt_buckets(
			qty_rows, availability["buckets"], variant_info,
			conversion_index=conversion_index,
			route_targets=route_targets,
		)
		return {
			"value": selected["value"],
			"process_name": selected["process_name"],
			"label": selected["label"],
			"received": flt(sum(availability["received"].values()), 3),
			"reserved": flt(sum(availability["reserved"].values()), 3),
			"available": flt(sum(positive.values()), 3),
			"unmatched": unmatched,
			"sources": _source_breakdown(availability["buckets"]),
		}

	# Compatibility fallback for pre-feature tests/sites whose availability
	# provider only returns variant totals. New production calls always include
	# receipt buckets and take the branch above.
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


def _project_receipt_buckets(
	qty_rows, buckets, variant_info, conversion_index=None, route_targets=None
):
	"""Replace planned rows with actual receipt -> projected-output rows.

	The source GRN item is the physical truth. Matrix rows remain the legal
	transformation rules, but Dia equality is relaxed on their principal input;
	all other declared attributes must still match. A same-value attribute is
	carried from the physical input, while a configured change keeps its planned
	target value.
	"""
	projected = []
	unmatched = []
	remaining_targets = dict(route_targets or {})
	from essdee_yrp.api.work_order import _resolve_variant, _variant_attrs
	from essdee_yrp.fabric_substitution import resolve_process_conversion

	for bucket in buckets:
		if flt(bucket.get("available_stock_qty")) <= ZERO_QTY_EPSILON:
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
		remaining_stock_qty = flt(bucket["available_stock_qty"])
		for qty_row, input_index, spec in matches:
			output_qty = flt(qty_row.get("output_qty")) or 1
			required = flt(spec.get("qty")) * (
				1 + flt(spec.get("wastage_pct")) / 100.0
			)
			if required <= 0:
				continue
			factor = _conversion_factor(bucket["item_variant"], spec.get("uom"))
			available_input_qty = remaining_stock_qty / factor
			capacity = flt(available_input_qty * output_qty / required, 3)
			matrix_key = qty_row.get("matrix_key") or qty_row.get("key")
			if route_targets is not None:
				target_key = (matrix_key, bucket["item_variant"])
				target_qty = flt(remaining_targets.get(target_key), 3)
				if target_qty <= ZERO_QTY_EPSILON:
					continue
				prefill = min(capacity, target_qty)
				remaining_targets[target_key] = flt(
					max(target_qty - prefill, 0), 3
				)
			else:
				prefill = 0 if shared else capacity
			if prefill > ZERO_QTY_EPSILON:
				consumed_stock_qty = prefill * required / output_qty * factor
				remaining_stock_qty = flt(
					max(remaining_stock_qty - consumed_stock_qty, 0), 6
				)
			elif route_targets is not None:
				continue
			actual_attrs = variant.get("attrs") or {}
			projected_attrs = project_output_attributes(
				actual_attrs,
				spec.get("attrs") or {},
				qty_row.get("out_attrs") or {},
			)
			output_item = qty_row.get("output_item") or spec.get("item")
			planned_output_variant = _resolve_variant(
				output_item, qty_row.get("out_attrs") or {}
			)
			projected_item_variant = _resolve_variant(
				output_item, projected_attrs
			)
			projected_item_variant = resolve_process_conversion(
				conversion_index,
				route_item=bucket.get("reference_item_variant"),
				from_item=planned_output_variant,
				projected_item=projected_item_variant,
			)
			projected_attrs = _variant_attrs(projected_item_variant)
			row = deepcopy(qty_row)
			execution_key = _execution_key(
				bucket["key"], matrix_key, bucket.get("reference_item_variant")
			)
			row.update({
				"key": execution_key,
				"matrix_key": matrix_key,
				"execution_key": execution_key,
				"label": _projection_label(actual_attrs, projected_attrs),
				"section": projected_attrs.get("Colour")
					or actual_attrs.get("Colour")
					or row.get("section"),
				"row_label": projected_attrs.get(FABRIC_DIA_ATTRIBUTE)
					or row.get("row_label"),
				"in_attrs": actual_attrs,
				"out_attrs": projected_attrs,
				"projected_item_variant": projected_item_variant,
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
				"source_stock_available": flt(
					bucket.get("available_stock_qty"), 6
				),
				"source_stock_per_output": flt(
					required * factor / output_qty, 9
				),
				"source_shared": shared and route_targets is None,
				"source_pool_key": bucket["key"],
				"source_input_index": input_index,
				"prefill": prefill,
			})
			projected.append(row)

	qty_rows[:] = projected
	return unmatched


def _knitting_factor_targets(qty_rows, lot, ipd):
	"""Target each colour route using the Lot's physical Actual-Dia factors."""
	from essdee_yrp.api.work_order import _resolve_variant
	from essdee_yrp.fabric_substitution import (
		allocate_route_quantity,
		get_actual_dia_factors,
	)

	targets = defaultdict(float)
	for qty_row in qty_rows:
		principal = next((
			spec for spec in qty_row.get("input_specs") or []
			if spec.get("item") == ipd.item and flt(spec.get("qty")) > 0
		), None)
		if not principal:
			continue
		planned_variant = _resolve_variant(
			principal["item"], principal.get("attrs") or {}
		)
		factors = get_actual_dia_factors(
			lot, ipd.name, planned_variant
		)
		planned_route_qty = flt(
			qty_row.get("plan")
			or qty_row.get("program")
			or qty_row.get("prefill")
		)
		matrix_key = qty_row.get("matrix_key") or qty_row.get("key")
		for allocation in allocate_route_quantity(planned_route_qty, factors):
			targets[(matrix_key, allocation["item_variant"])] += flt(
				allocation["qty"], 3
			)
	return dict(targets)


def project_output_attributes(actual_attrs, planned_input_attrs, planned_output_attrs):
	"""Project a physical source through one concrete matrix transformation."""
	result = {}
	keys = set(actual_attrs) | set(planned_input_attrs) | set(planned_output_attrs)
	for attribute in keys:
		actual = actual_attrs.get(attribute)
		planned_input = planned_input_attrs.get(attribute)
		planned_output = planned_output_attrs.get(attribute)
		if planned_output:
			# Identity/carry: preserve the physical value (notably Actual Dia).
			if planned_input and planned_input == planned_output and actual:
				result[attribute] = actual
			else:
				result[attribute] = planned_output
		elif actual:
			result[attribute] = actual
	return result


def prepare_source_pool(
	*, lot, ipd, cloth_item, current_process, current_work_order, source_process,
	target_location=None,
):
	"""Lock, reload and return exact receipt buckets for Calculate/Apply."""
	selected = resolve_source_process(ipd, current_process, source_process)
	_lock_source_transactions(lot, cloth_item, selected["process_name"])
	availability = get_source_availability(
		lot=lot,
		ipd=ipd.name,
		cloth_item=cloth_item,
		source_process=selected["process_name"],
		source_step=selected["value"],
		current_process=current_process,
		current_work_order=current_work_order,
		target_location=target_location,
	)
	from essdee_yrp.fabric_substitution import get_process_conversion_index

	return {
		"selected": selected,
		"physical_knitting_source": selected["process_name"]
			== frappe.db.get_single_value(
				"IPD Settings", "default_knitting_process"
			),
		"conversion_index": get_process_conversion_index(
			lot, ipd.name, current_process
		),
		"buckets": {
			bucket["key"]: {**bucket, "remaining_stock_qty": flt(bucket["available_stock_qty"])}
			for bucket in availability.get("buckets") or []
		},
	}


def validate_work_order_source_allocations(wo):
	"""Re-resolve every exact source row when a source-aware WO is saved.

	This closes the gap between Calculate and a later draft edit/API write. Older
	submitted documents without execution metadata remain readable; a draft with
	material rows must be recalculated before it can proceed.
	"""
	if wo.get("is_rework"):
		managed = bool(wo.get("fabric_source_process")) or any(
			_fabric_execution_key(row)
			for table in ("deliverables", "receivables")
			for row in (wo.get(table) or [])
		)
		if managed:
			frappe.throw(_(
				"A calculated fabric execution contract cannot be converted to Rework. "
				"Create Rework from the submitted source receipt instead."
			))
		# Genuine base-YRP rework rows intentionally use their own source receipt
		# and reservation contract, without fabric execution keys. On insertion,
		# prove that contract came from the authoritative rework source picker;
		# Work Order immutability protects it after insertion.
		if wo.is_new():
			_validate_new_rework_source_contract(wo)
		return
	if (
		wo.docstatus == 2
		or not wo.get("lot")
		or not wo.get("production_detail")
		or not wo.get("process_name")
	):
		return
	# Frappe invokes validate before updating the parent row. Lock an existing
	# target first so ordinary Save and Calculate use the same target -> Lot ->
	# source-GRN order and cannot deadlock each other.
	if not wo.is_new():
		frappe.db.sql(
			"SELECT name FROM `tabWork Order` WHERE name = %s FOR UPDATE",
			(wo.name,),
		)
	ipd = frappe.get_cached_doc("Item Production Detail", wo.production_detail)
	if not get_source_process_options(ipd, wo.process_name):
		return

	def execution_key(row):
		return _fabric_execution_key(row)

	receivable_keys = {
		execution_key(row) for row in wo.get("receivables") or []
		if execution_key(row)
	}
	material_rows = [
		row for row in wo.get("deliverables") or [] if flt(row.get("qty")) > 0
	]
	if not receivable_keys:
		if material_rows:
			db_docstatus = frappe.db.get_value("Work Order", wo.name, "docstatus")
			if wo.docstatus == 0 or db_docstatus != 1:
				frappe.throw(_(
					"This fabric process must use exact earlier-process GRN stock. "
					"Reopen Calculate and rebuild its deliverables before saving."
				))
		return

	source_step = wo.get("fabric_source_process_step")
	if not source_step:
		frappe.throw(_(
			"This fabric process has no exact source-process step. Reopen Calculate."
		))
	pool = prepare_source_pool(
		lot=wo.lot,
		ipd=ipd,
		cloth_item=ipd.item,
		current_process=wo.process_name,
		current_work_order=wo.name,
		source_process=source_step,
		target_location=wo.get("delivery_location"),
	)
	selected = pool["selected"]
	physical_knitting_source = bool(pool.get("physical_knitting_source"))
	if wo.get("fabric_source_process") and (
		wo.fabric_source_process != selected["process_name"]
	):
		frappe.throw(_("The saved fabric source process changed. Reopen Calculate."))

	linked_by_execution = defaultdict(list)
	for row in material_rows:
		key = execution_key(row)
		if row.get("source_grn_item"):
			if not key:
				frappe.throw(_("An exact source row is missing its execution identity."))
			linked_by_execution[key].append(row)
	for key in receivable_keys:
		if not linked_by_execution.get(key):
			frappe.throw(_(
				"A calculated fabric output is missing its exact source GRN row. "
				"Reopen Calculate."
			))

	for key, rows in linked_by_execution.items():
		if key not in receivable_keys:
			frappe.throw(_("An exact source row has no matching fabric output."))
		for row in rows:
			effective_qty = flt(row.qty)
			if wo.get("open_status") == "Close":
				effective_qty = max(
					flt(row.qty) - flt(row.get("pending_quantity")),
					flt(row.get("stock_update")),
					0,
				)
			if effective_qty <= ZERO_QTY_EPSILON:
				continue
			stock_qty = effective_qty * _conversion_factor(row.item_variant, row.uom)
			allocations = get_reference_allocations(row, row.qty)
			stock_allocations = scale_reference_allocations(allocations, stock_qty)
			if not stock_allocations:
				stock_allocations = {None: stock_qty}
			for reference, qty in stock_allocations.items():
				bucket_key = _bucket_key(
					row.source_grn_item,
					None if physical_knitting_source else reference,
				)
				bucket = consume_source_bucket(pool, bucket_key, qty)
				if (
					bucket.get("source_grn") != row.get("source_grn")
					or bucket.get("source_grn_item") != row.get("source_grn_item")
					or bucket.get("item_variant") != row.get("item_variant")
				):
					frappe.throw(_(
						"The exact source GRN lineage changed. Reopen Calculate."
					))
				if frappe.parse_json(row.get("set_combination") or "{}") != frappe.parse_json(
					bucket.get("set_combination") or "{}"
				):
					frappe.throw(_(
						"The exact source set combination changed. Reopen Calculate."
					))
				for fieldname, expected in (bucket.get("stock_dimensions") or {}).items():
					if (row.get(fieldname) or None) != (expected or None):
						frappe.throw(_(
							"The exact source stock dimensions changed. Reopen Calculate."
						))


def _fabric_execution_key(row):
	value = row.get("additional_parameters") or {}
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			value = {}
	return value.get("fabric_execution_key") if isinstance(value, dict) else None


def _validate_new_rework_source_contract(wo):
	if not wo.get("parent_wo"):
		frappe.throw(_("Rework Work Orders require a submitted Parent Work Order."))
	from yrp.stock.dimensions import get_dimension_fieldnames
	from yrp.yrp.doctype.delivery_challan.delivery_challan import (
		_get_warehouse_for_supplier,
	)
	from yrp.yrp.doctype.work_order.work_order import get_rework_source_rows

	dimension_fields = get_dimension_fieldnames()
	sources = get_rework_source_rows(wo.parent_wo)
	by_reference = defaultdict(list)
	for source in sources:
		by_reference[source.get("source_grn_item")].append(source)

	def normalized(value):
		return frappe.parse_json(value or "{}")

	def bucket_key(item_variant, uom, set_combination, dimensions):
		return (
			item_variant,
			uom,
			tuple(sorted(normalized(set_combination).items())),
			tuple((fieldname, dimensions.get(fieldname) or None) for fieldname in dimension_fields),
		)

	available_by_bucket = defaultdict(float)
	for source in sources:
		dimensions = source.get("dimensions") or {
			fieldname: source.get(fieldname) for fieldname in dimension_fields
		}
		available_by_bucket[bucket_key(
			source.get("item_variant"), source.get("uom"),
			source.get("set_combination"), dimensions,
		)] += flt(source.get("available_qty"))

	requested_by_bucket = defaultdict(float)
	expected_warehouse = _get_warehouse_for_supplier(wo.get("delivery_location"))
	for row in wo.get("deliverables") or []:
		candidates = by_reference.get(row.get("source_grn_item")) or []
		match = next((
			source for source in candidates
			if source.get("source_grn") == row.get("source_grn")
			and source.get("item_variant") == row.get("item_variant")
			and source.get("uom") == row.get("uom")
			and (source.get("received_type") or None)
				== (row.get("received_type") or None)
			and normalized(source.get("set_combination"))
				== normalized(row.get("set_combination"))
			and all(
				((source.get("dimensions") or {}).get(fieldname) or source.get(fieldname) or None)
				== (row.get(fieldname) or None)
				for fieldname in dimension_fields
			)
		), None)
		if not match:
			frappe.throw(_(
				"Row {0}: rework source is not an eligible row from Parent Work Order {1}. "
				"Create Rework from the source picker."
			).format(row.idx, wo.parent_wo))
		if expected_warehouse and match.get("warehouse") != expected_warehouse:
			frappe.throw(_(
				"Row {0}: rework source warehouse does not match the Parent Work Order location."
			).format(row.idx))
		dimensions = {
			fieldname: row.get(fieldname) for fieldname in dimension_fields
		}
		key = bucket_key(
			row.item_variant, row.uom, row.get("set_combination"), dimensions
		)
		requested_by_bucket[key] += flt(row.qty)

	for key, quantity in requested_by_bucket.items():
		available = flt(available_by_bucket.get(key))
		if _exceeds_available(quantity, available):
			frappe.throw(_(
				"Rework quantity {0} exceeds eligible source quantity {1}. "
				"Reopen the Rework source picker."
			).format(flt(quantity, 3), flt(available, 3)))


def consume_source_bucket(pool, bucket_key, required_stock_qty):
	"""Consume one plan's exact-source capacity without reserving it globally."""
	bucket = (pool.get("buckets") or {}).get(bucket_key)
	if not bucket:
		frappe.throw(_("The selected source GRN row is no longer available. Reopen Calculate."))
	required_stock_qty = flt(required_stock_qty)
	available = flt(bucket.get("remaining_stock_qty"))
	if _exceeds_available(required_stock_qty, available):
		frappe.throw(_(
			"The exact source GRN row {0} / {1} has only {2} Kg available; "
			"{3} Kg was requested. Reopen Calculate."
		).format(
			bucket.get("source_grn") or _("(unknown GRN)"),
			bucket.get("source_grn_item") or bucket_key,
			flt(available, 3),
			flt(required_stock_qty, 3),
		))
	# This mutates only the request-local pool. Other draft Work Orders are not
	# deducted by get_source_availability; only quantities actually dispatched
	# by a submitted DC reduce a later request's available capacity.
	bucket["remaining_stock_qty"] = flt(available - required_stock_qty, 6)
	return bucket


def validate_source_demands(
	demands, *, lot, ipd, cloth_item, current_process, current_work_order,
	source_process,
):
	"""Resolve the predecessor identity without reserving or capping stock."""
	selected = resolve_source_process(ipd, current_process, source_process)
	return selected


def get_source_availability(
	*, lot, ipd, cloth_item, source_process, source_step, current_process,
	current_work_order, target_location=None,
):
	"""Submitted Accepted GRN rows minus exact downstream reservations.

	Returns both the legacy per-variant totals and receipt/reference-level FIFO
	buckets. The exact bucket is the allocation authority; totals exist for
	backward-compatible callers and summary display only.
	"""
	from yrp.stock.dimensions import assert_safe_fieldname, get_dimension_fieldnames

	dimension_fields = get_dimension_fieldnames()
	for fieldname in dimension_fields:
		assert_safe_fieldname(fieldname)
	dimension_select = "".join(
		f", item.`{fieldname}` AS `{fieldname}`" for fieldname in dimension_fields
	)
	received_rows = frappe.db.sql(
		f"""
		SELECT item.name AS source_grn_item,
			item.parent AS source_grn,
			item.idx AS source_grn_row,
			item.item_variant,
			item.stock_qty,
			item.quantity,
			item.uom,
			item.received_type,
			item.ref_docname,
			grn.posting_date,
			grn.posting_time,
			grn.creation,
			grn.supplier,
			grn.to_warehouse AS source_warehouse,
			source_wo.name AS source_work_order,
			item.set_combination
			{dimension_select}
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
			AND source_wo.production_detail = %(ipd)s
			AND source_wo.process_name = %(source_process)s
		ORDER BY grn.posting_date, grn.posting_time, grn.creation, grn.name, item.idx
		FOR UPDATE
		""",
		{
			"lot": lot,
			"ipd": ipd,
			"cloth_item": cloth_item,
			"source_process": source_process,
		},
		as_dict=True,
	)
	inspection_adjustments = _accepted_inspection_adjustments(received_rows)
	receivable_names = list({row.ref_docname for row in received_rows if row.ref_docname})
	receivables = {
		row.name: row
		for row in frappe.get_all(
			"Work Order Receivables",
			filters={"name": ["in", receivable_names]},
			fields=[
				"name", "qty", "fabric_reference_variant",
				"fabric_reference_allocations",
			],
		)
	} if receivable_names else {}
	default_knitting = frappe.db.get_single_value(
		"IPD Settings", "default_knitting_process"
	)
	physical_knitting_source = bool(
		default_knitting and source_process == default_knitting
	)

	buckets = []
	for row in received_rows:
		original_stock_qty = flt(row.stock_qty)
		if not original_stock_qty:
			original_stock_qty = flt(row.quantity) * _conversion_factor(
				row.item_variant, row.uom
			)
		stock_qty = (
			original_stock_qty
			if row.received_type == ELIGIBLE_RECEIVED_TYPE
			else 0
		)
		stock_qty = max(
			stock_qty + flt(inspection_adjustments.get(row.source_grn_item)),
			0,
		)
		if stock_qty <= ZERO_QTY_EPSILON:
			continue
		receivable = receivables.get(row.ref_docname)
		if physical_knitting_source:
			references = {None: stock_qty}
		else:
			allocations = get_reference_allocations(
				receivable, receivable.qty if receivable else stock_qty
			) if receivable else {}
			references = scale_reference_allocations(allocations, stock_qty)
			if not references:
				references = {None: stock_qty}
		for reference, reference_qty in references.items():
			buckets.append({
				"key": _bucket_key(row.source_grn_item, reference),
				"source_grn": row.source_grn,
				"source_grn_item": row.source_grn_item,
				"source_grn_row": row.source_grn_row,
				"source_work_order": row.source_work_order,
				"source_process": source_process,
				"source_process_step": source_step,
				"supplier": row.supplier,
				"source_warehouse": row.source_warehouse,
				"posting_date": row.posting_date,
				"posting_time": row.posting_time,
				"item_variant": row.item_variant,
				"uom": row.uom,
				"received_type": ELIGIBLE_RECEIVED_TYPE,
				"set_combination": row.set_combination,
				"stock_dimensions": {
					fieldname: (
						ELIGIBLE_RECEIVED_TYPE
						if fieldname == "received_type"
						else row.get(fieldname)
					)
					for fieldname in dimension_fields
				},
				"reference_item_variant": reference,
				"received_stock_qty": flt(reference_qty, 6),
				"reserved_stock_qty": 0.0,
				"available_stock_qty": flt(reference_qty, 6),
			})

	# A Delivery Challan has one origin warehouse. Do not combine physical
	# receipts from another warehouse into that Work Order's source pool.
	if target_location is None and current_work_order:
		target_location = frappe.db.get_value(
			"Work Order", current_work_order, "delivery_location"
		)
	if not buckets:
		return {"received": {}, "reserved": {}, "net": {}, "buckets": []}
	if current_work_order and not target_location:
		frappe.throw(_(
			"Select a Delivery Location on Work Order {0} before allocating "
			"predecessor GRN stock."
		).format(current_work_order))
	if target_location:
		from yrp.yrp.doctype.delivery_challan.delivery_challan import (
			_get_warehouse_for_supplier,
		)

		target_warehouse = _get_warehouse_for_supplier(target_location)
		if not target_warehouse:
			frappe.throw(_(
				"Delivery Location {0} must map to exactly one active Warehouse "
				"before fabric source stock can be allocated."
			).format(target_location))
		unfiltered_buckets = buckets
		buckets = [
			bucket for bucket in buckets
			if bucket.get("source_warehouse") == target_warehouse
		]
		if unfiltered_buckets and not buckets:
			warehouses = ", ".join(sorted({
				bucket.get("source_warehouse") or _("(blank)")
				for bucket in unfiltered_buckets
			}))
			frappe.throw(_(
				"Available source GRNs are in {0}, but this Work Order dispatches "
				"from {1}. Transfer the stock or create a separate Work Order."
			).format(warehouses, target_warehouse))

	if not buckets:
		return {"received": {}, "reserved": {}, "net": {}, "buckets": []}

	source_items = list({bucket["source_grn_item"] for bucket in buckets})
	reserved_rows = frappe.db.sql(
		"""
		SELECT item.name, item.parent, item.source_grn_item,
			item.item_variant, item.qty, item.pending_quantity,
			item.stock_update, item.uom, item.fabric_reference_variant,
			item.fabric_reference_allocations
		FROM `tabWork Order Deliverables` item
		WHERE item.parenttype = 'Work Order'
			AND item.source_grn_item IN %(source_items)s
			AND item.parent != %(current_work_order)s
		ORDER BY item.parent, item.idx
		FOR UPDATE
		""",
		{
			"source_items": tuple(source_items),
			"current_work_order": current_work_order,
		},
		as_dict=True,
	)
	parent_status = {
		row.name: row
		for row in frappe.get_all(
			"Work Order",
			filters={"name": ["in", list({row.parent for row in reserved_rows})]},
			fields=["name", "docstatus", "open_status"],
		)
	} if reserved_rows else {}
	reserved_by_bucket = defaultdict(float)
	for row in reserved_rows:
		status = parent_status.get(row.parent)
		if not status or status.docstatus == 2:
			continue
		planned_qty = max(flt(row.qty), 0)
		delivered_qty = max(planned_qty - flt(row.pending_quantity), 0)
		consumed_qty = max(flt(row.stock_update), 0)
		executed_qty = max(delivered_qty, consumed_qty)
		# A draft/calculated Work Order is a plan, not a reservation. Only actual
		# dispatched/consumed quantity reduces what the popup reports. The Stock
		# module performs the authoritative balance check when a DC is submitted.
		reserved_qty = executed_qty
		stock_qty = reserved_qty * _conversion_factor(row.item_variant, row.uom)
		allocations = get_reference_allocations(row, row.qty)
		stock_allocations = scale_reference_allocations(allocations, stock_qty)
		if not stock_allocations:
			stock_allocations = {None: stock_qty}
		for reference, qty in stock_allocations.items():
			reserved_by_bucket[_bucket_key(
				row.source_grn_item,
				None if physical_knitting_source else reference,
			)] += flt(qty)

	for bucket in buckets:
		reserved_qty = flt(reserved_by_bucket.get(bucket["key"]), 6)
		bucket["reserved_stock_qty"] = reserved_qty
		bucket["available_stock_qty"] = flt(
			max(bucket["received_stock_qty"] - reserved_qty, 0), 6
		)

	# Legacy calculated rows have no exact source receipt. Reserve their variant
	# totals FIFO, releasing only an unexecuted closed plan.
	legacy_rows = _legacy_reserved_rows(
		lot=lot,
		ipd=ipd,
		cloth_item=cloth_item,
		current_process=current_process,
		current_work_order=current_work_order,
		source_process=source_process,
		source_step=source_step,
	)
	legacy_by_variant = _rows_in_stock_uom(legacy_rows)
	for variant, qty in legacy_by_variant.items():
		remaining = flt(qty)
		for bucket in buckets:
			if bucket["item_variant"] != variant or remaining <= ZERO_QTY_EPSILON:
				continue
			take = min(remaining, flt(bucket["available_stock_qty"]))
			bucket["reserved_stock_qty"] += take
			bucket["available_stock_qty"] -= take
			remaining -= take

	received = defaultdict(float)
	reserved = defaultdict(float)
	for bucket in buckets:
		received[bucket["item_variant"]] += flt(bucket["received_stock_qty"])
		reserved[bucket["item_variant"]] += flt(bucket["reserved_stock_qty"])
	variants = set(received) | set(reserved)
	return {
		"received": {variant: flt(qty, 6) for variant, qty in received.items()},
		"reserved": {variant: flt(qty, 6) for variant, qty in reserved.items()},
		"net": {
			variant: flt(max(received[variant] - reserved[variant], 0), 6)
			for variant in variants
		},
		"buckets": buckets,
	}


def _accepted_inspection_adjustments(received_rows):
	"""Authoritative Accepted-bin SLE delta from converted inspections."""
	if not received_rows or not frappe.db.exists("DocType", "Inspection Entry"):
		return {}
	source_items = list({row.source_grn_item for row in received_rows})
	rows = frappe.db.sql(
		"""
		SELECT iei.ref_docname AS source_grn_item, SUM(sle.qty) AS accepted_delta
		FROM `tabStock Ledger Entry` sle
		JOIN `tabInspection Entry Item` iei
			ON iei.name = sle.voucher_detail_no
		JOIN `tabInspection Entry` ie
			ON ie.name = iei.parent
			AND ie.name = sle.voucher_no
		WHERE sle.voucher_type = 'Inspection Entry'
			AND IFNULL(sle.is_cancelled, 0) = 0
			AND sle.received_type = %(eligible_received_type)s
			AND sle.item = iei.item_variant
			AND sle.warehouse = iei.warehouse
			AND ie.docstatus = 1
			AND IFNULL(ie.is_converted, 0) = 1
			AND iei.parenttype = 'Inspection Entry'
			AND iei.ref_doctype = 'Goods Received Note Item'
			AND iei.ref_docname IN %(source_items)s
		GROUP BY iei.ref_docname
		FOR UPDATE
		""",
		{
			"eligible_received_type": ELIGIBLE_RECEIVED_TYPE,
			"source_items": tuple(source_items),
		},
		as_dict=True,
	)
	return {
		row.source_grn_item: flt(row.accepted_delta, 6)
		for row in rows
	}


def _legacy_reserved_rows(
	*, lot, ipd, cloth_item, current_process, current_work_order, source_process,
	source_step,
):
	params = {
		"lot": lot,
		"ipd": ipd,
		"cloth_item": cloth_item,
		"current_process": current_process,
		"current_work_order": current_work_order,
		"source_process": source_process,
		"source_step": source_step,
	}
	return frappe.db.sql(
		"""
		SELECT item.item_variant,
			GREATEST(
				IFNULL(item.qty, 0) - IFNULL(item.pending_quantity, 0),
				IFNULL(item.stock_update, 0),
				0
			) AS qty,
			item.uom
		FROM `tabWork Order Deliverables` item
		JOIN `tabWork Order` target_wo ON target_wo.name = item.parent
		WHERE item.parenttype = 'Work Order'
			AND target_wo.docstatus < 2
			AND target_wo.name != %(current_work_order)s
			AND target_wo.lot = %(lot)s
			AND target_wo.item = %(cloth_item)s
			AND target_wo.production_detail = %(ipd)s
			AND IFNULL(item.is_calculated, 0) = 1
			AND IFNULL(item.source_grn_item, '') = ''
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
		""",
		params,
		as_dict=True,
	)


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


def _bucket_key(source_grn_item, reference):
	return f"{source_grn_item}::{reference or '-'}"


def _conversion_factor(item_variant, uom):
	from yrp.stock.utils import get_conversion_factor

	return flt(
		(get_conversion_factor(item_variant, uom) or {}).get("conversion_factor")
	) or 1


def _execution_key(bucket_key, matrix_key, reference):
	import hashlib

	raw = f"{bucket_key}|{matrix_key}|{reference or ''}"
	return f"fabric-{hashlib.sha1(raw.encode()).hexdigest()[:24]}"


def _projection_label(actual_attrs, projected_attrs):
	def label(attrs):
		return " · ".join(
			str(value) for _key, value in sorted((attrs or {}).items()) if value
		) or _("No attributes")

	return _("{0} → {1}").format(label(actual_attrs), label(projected_attrs))


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
			"received": flt(row.get("received_stock_qty"), 3),
			"reserved": flt(row.get("reserved_stock_qty"), 3),
			"available": flt(row.get("available_stock_qty"), 3),
		}
		for row in buckets
		if flt(row.get("available_stock_qty")) > ZERO_QTY_EPSILON
	]
