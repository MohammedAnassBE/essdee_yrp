# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Fabric Work Order Calculate: popup context + calculation.

The popup derives EVERYTHING from the IPD's auto-generated matrices; the user
only enters quantities — one row per matrix group (user-locked 2026-07-03).
Entered rows become `output_demand` for the base engine (`get_process_io`):
deliverables are the engine's scaled inputs; receivables are the entered rows
themselves (1:1 v1 — the Process master's waste/excess applies later)."""

import json
import re

import frappe
from frappe import _
from frappe.utils import cstr, flt

from essdee_yrp.fabric_chain import get_fabric_step, get_fabric_steps
from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
	get_identity_process_row,
	get_yarn_ratio_inputs,
)
from essdee_yrp.fabric_program import (
	get_greige_colour,
	get_knitting_output_colour,
)
from essdee_yrp.fabric_reference import (
	get_reference_allocations,
	serialise_reference_allocations,
)
from essdee_yrp.ipd_validations import get_attribute_mapping, get_ipd_attribute_values


def _guard_not_modified(doc, modified):
	"""Reject a stale write, mirroring the standard REST PUT's check_if_latest().

	These whitelisted methods load a FRESH doc (`frappe.get_doc`) then `.save()`,
	which bypasses Frappe's built-in stale-write guard — a freshly-loaded
	`modified` always equals the DB value, so check_if_latest() never fires. The
	`/web` client passes the `modified` it originally loaded; if the document has
	changed since, raise the same error the REST path would (TimestampMismatchError,
	HTTP 417) so the SPA shows its "Refresh" conflict banner instead of clobbering.
	"""
	if modified and cstr(doc.modified) != cstr(modified):
		frappe.throw(
			_("{0} was modified after you opened it. Please refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _step_kind(ipd, step):
	"""Legacy kind alias for a chain step — keeps every existing popup branch
	(labels, colour columns, yarn field, overshoot rules) working for NEW
	processes: any Colour swap renders like dyeing, any Dia swap (Re-Compacting)
	like compacting. A multi_swap (Dye-Compact: Colour AND Dia change together)
	renders as dyeing when it touches Colour — the matrix already carries the
	full combo transition so the labels/qty rows stay correct.

	Conversions split in two (2026-07-08): a conversion whose row CONSUMES input
	attributes (Consume-role rules — Printing TT-CLOTH-CC -> TT-CLOTH) is kind
	"conversion": each matrix group is one in->out rule, the deliverable is the
	attributed input variant, and the receivable colour comes from the rule's
	Introduce — NO greige-colour pick, NO Colour overwrite, NO yarn aggregation.
	Only an attr-less-input conversion (knitting's aggregated yarn) stays kind
	"knitting" with its colour pick + yarn override."""
	if not step:
		return None
	if step["shape"] == "conversion":
		return "conversion" if _conversion_consumes(ipd, step["process_name"]) else "knitting"
	if step["shape"] in ("swap", "multi_swap"):
		attrs = step["attribute"]
		attrs = attrs if isinstance(attrs, (list, tuple)) else [attrs]
		return "dyeing" if FABRIC_COLOUR_ATTRIBUTE in attrs else "compacting"
	return None


def _conversion_consumes(ipd, process_name):
	"""True when the conversion's generic fabric row carries Consume entries —
	its matrix INPUT side is attributed (rule-based), unlike knitting's attr-less
	yarn. The row is the source of truth; the matrix merely mirrors it."""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	for row in get_fabric_process_rows(ipd):
		if row.get("fabric_process") == process_name:
			return any(m.get("role") == "Consume" for m in row.get("value_mappings") or [])
	return False


def _selected_lot_fabrics(wo, lot):
	"""Return only the Lot fabric selected on this Work Order.

	`production_detail` identifies the exact Lot Fabric Detail selection. Item is
	only a fallback for legacy Work Orders that predate that field; an entirely
	unselected legacy Work Order retains the old all-fabrics behaviour.
	"""
	fabrics = list(lot.get("lot_fabric_details") or [])
	if wo.get("production_detail"):
		return [
			fabric for fabric in fabrics
			if fabric.get("production_detail") == wo.get("production_detail")
		]
	if wo.get("item"):
		return [
			fabric for fabric in fabrics
			if fabric.get("cloth_item") == wo.get("item")
		]
	return fabrics


_CHILD_SYSTEM_FIELDS = {
	"doctype", "name", "owner", "creation", "modified", "modified_by",
	"docstatus", "idx", "parent", "parentfield", "parenttype",
	"table_index", "row_index",
}
_CHILD_ADDITIVE_FIELDS = {
	"qty", "pending_quantity", "secondary_qty", "stock_update",
	"cancelled_quantity", "total_cost",
}


def _consolidate_fabric_rows(rows, child_doctype, supports_allocations=None):
	"""Persist one row per physical Item Variant while retaining route splits.

	The popup has one line per finished-colour route, but several routes can
	consume/produce the same physical variant (all colours knit as the same
	Greige Dia, or all routes consume the same yarn). Store that physical row
	once and keep the finished-route quantities in hidden JSON metadata.
	"""
	if not rows:
		return []
	if supports_allocations is None:
		supports_allocations = frappe.db.has_column(
			child_doctype, "fabric_reference_allocations"
		)
	if not supports_allocations:
		# A pre-migrate site cannot safely collapse rows because the legacy Link
		# can represent only one route.
		return [
			row.as_dict() if hasattr(row, "as_dict") else dict(row)
			for row in rows
		]

	grouped = []
	by_identity = {}
	allocations_by_identity = {}

	for row in rows:
		source = row.as_dict() if hasattr(row, "as_dict") else dict(row)
		payload = {
			key: value
			for key, value in source.items()
			if key not in _CHILD_SYSTEM_FIELDS
		}
		allocations = get_reference_allocations(payload, payload.get("qty"))
		payload.pop("fabric_reference_variant", None)
		payload.pop("fabric_reference_allocations", None)

		identity_payload = {
			key: value
			for key, value in payload.items()
			if key not in _CHILD_ADDITIVE_FIELDS
		}
		identity = json.dumps(
			identity_payload, sort_keys=True, default=str, separators=(",", ":")
		)
		target = by_identity.get(identity)
		if target is None:
			target = payload
			by_identity[identity] = target
			allocations_by_identity[identity] = {}
			grouped.append(target)
		else:
			for fieldname in _CHILD_ADDITIVE_FIELDS:
				if fieldname in target or fieldname in payload:
					target[fieldname] = flt(target.get(fieldname)) + flt(payload.get(fieldname))

		target_allocations = allocations_by_identity[identity]
		for reference, qty in allocations.items():
			target_allocations[reference] = target_allocations.get(reference, 0) + flt(qty)

	for identity, target in by_identity.items():
		for fieldname in ("qty", "pending_quantity", "secondary_qty", "stock_update", "cancelled_quantity"):
			if fieldname in target:
				target[fieldname] = round(flt(target.get(fieldname)), 3)
		allocations = allocations_by_identity[identity]
		target["fabric_reference_allocations"] = serialise_reference_allocations(
			allocations, target.get("qty")
		)
		target["fabric_reference_variant"] = (
			next(iter(allocations)) if len(allocations) == 1 else None
		)
	return grouped


@frappe.whitelist()
def get_fabric_deliverable_context(work_order):
	"""Popup context for this WO's selected Lot fabric and process."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	lot = _get_lot(wo)

	rows = []
	warnings = []
	kind = None
	for fabric in _selected_lot_fabrics(wo, lot):
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		step = get_fabric_step(ipd, wo.process_name)
		row_kind = _step_kind(ipd, step)
		identity_row = None
		if not row_kind:
			identity_row = get_identity_process_row(ipd, wo.process_name)
			if identity_row:
				row_kind = "identity"
		if not row_kind:
			continue
		kind = row_kind
		treated_item = (identity_row.process_item if identity_row else None) or fabric.cloth_item
		try:
			if row_kind == "identity":
				qty_rows = _identity_qty_rows(ipd, treated_item, identity_row)
			else:
				qty_rows = _matrix_qty_rows(ipd, wo.process_name, row_kind)
		except frappe.ValidationError as e:
			# One stale IPD must not block the other fabrics' calculation.
			warnings.append(str(e))
			continue
		has_colour = _item_has_attribute(fabric.cloth_item, FABRIC_COLOUR_ATTRIBUTE)
		if step:
			_add_planning_data(qty_rows, row_kind, lot, wo, fabric, ipd, step)
		reference_routed = (
			row_kind == "knitting"
			and any(row.get("reference_item_variant") for row in qty_rows)
		)
		if reference_routed:
			for qty_row in qty_rows:
				target_attrs = qty_row.get("target_attrs") or {}
				target_colour = target_attrs.get(FABRIC_COLOUR_ATTRIBUTE)
				target_dia = target_attrs.get(FABRIC_DIA_ATTRIBUTE)
				# Knitting output colour is route-specific: the first Colour
				# change's input for this final (Colour, Dia).  No colour-changing
				# process means the helper returns the target colour itself.
				qty_row["knit_colour"] = get_knitting_output_colour(
					ipd, target_colour, target_dia
				)
				qty_row["knit_dia"] = (
					qty_row.get("out_attrs") or {}
				).get(FABRIC_DIA_ATTRIBUTE)
		# Knitting yarn + cloth-per-kg-yarn come from the matched generic row (its
		# input_item / quantity_ratio) so a generic IPD with blank tab yarn_item /
		# cloth_per_kg_yarn still resolves. The adapter fills the same values from
		# the tabs for legacy IPDs, so this is behaviour-preserving. A "conversion"
		# row reuses the same lookup only to tell the popup which item is consumed.
		kn_row = _knitting_row(ipd, wo.process_name) if row_kind in ("knitting", "conversion") else None
		rows.append({
			"input_item": (kn_row and kn_row.get("input_item")) if row_kind == "conversion" else None,
			"fabric_row": fabric.name,
			"yarn_item": (kn_row and kn_row.get("input_item")) or ipd.get("yarn_item"),
			"yarns": [] if reference_routed else [
				{"yarn_item": yarn.item, "ratio": flt(yarn.ratio)}
				for yarn in get_yarn_ratio_inputs(ipd)
			] if row_kind == "knitting" else [],
			"cloth_item": fabric.cloth_item,
			"treated_item": treated_item,
			"production_detail": fabric.production_detail,
			"kind": row_kind,
			"reference_routed": reference_routed,
			"ratio": (flt(kn_row.get("quantity_ratio")) if kn_row else flt(ipd.get("cloth_per_kg_yarn"))) or 1,
			"has_colour": has_colour,
			"greige_colour": get_greige_colour(ipd) if row_kind == "knitting" else None,
			"colour_options": _knit_colour_options(ipd) if (row_kind == "knitting" and has_colour) else [],
			"colour_mapping": (
				get_attribute_mapping(ipd, FABRIC_COLOUR_ATTRIBUTE)
				if (row_kind == "knitting" and has_colour)
				else None
			),
			"qty_rows": qty_rows,
		})

	return {"is_fabric_process": bool(rows) or bool(warnings), "kind": kind, "rows": rows, "warnings": warnings}


def _add_planning_data(qty_rows, kind, lot, wo, fabric, ipd, step):
	"""Stamp program/plan/ordered/available/prefill onto each popup qty row.

	Semantics: production against the program/plan reads other WOs'
	RECEIVABLES; consumption of available cloth reads other WOs' calculated
	DELIVERABLES (deliverable variants carry the input-side attrs — no matrix
	inversion needed). "Available" at any step = the PREVIOUS step's ledger
	receipts minus this step's consumption — generic for any chain length.
	Prefill comes from the back-computed PLAN when one exists (else 0 for
	swaps, per the 2026-07-04 decision). Rework WOs excluded; the current WO's
	own calculated rows excluded (they get replaced)."""
	from essdee_yrp.fabric_plan import _route_bypasses_step
	from essdee_yrp.fabric_tracking import (
		get_consumed_by_dia_colour,
		get_produced_by_dia_colour,
		get_produced_by_reference,
		get_step_planned,
		get_step_received,
	)

	cloth = fabric.cloth_item

	if kind == "knitting":
		program_rows = {
			(r.dia, r.get("reference_item_variant") or ""): r
			for r in lot.get("lot_fabric_programs") or [] if r.cloth_item == cloth
		}
		ordered = get_produced_by_reference(
			lot.name, wo.process_name, cloth, exclude_wo=wo.name
		)
		for qr in qty_rows:
			dia = (qr.get("out_attrs") or {}).get(FABRIC_DIA_ATTRIBUTE)
			reference = qr.get("reference_item_variant") or ""
			row = program_rows.get((dia, reference))
			if not row and not reference:
				row = next(
					(r for (row_dia, _ref), r in program_rows.items() if row_dia == dia),
					None,
				)
			program = flt(row.weight) if row else 0
			already = flt(ordered.get(reference))
			qr.update({
				"program": program,
				"received": flt(row.received_weight) if row else 0,
				"ordered": already,
				"balance": max(program - already, 0),
				"prefill": max(program - already, 0),
			})
		return

	# any swap/identity step, at any chain depth (dyeing, compacting,
	# re-compacting, in-chain washing)
	steps = get_fabric_steps(ipd)
	position = step["position"]
	# A Consume-rule conversion consumes/produces NON-cloth items whose attrs may
	# not be Dia/Colour — the cloth-keyed ledger would over-report via the
	# blank-matches-any rule. Show no `available` until tracking is item-aware.
	reference_aware = any(
		qr.get("reference_item_variant") for qr in qty_rows
	)
	received_cache = {}
	planned_cache = {}
	ordered_cache = {}
	consumed_cache = {}

	for qr in qty_rows:
		in_attrs = qr.get("in_attrs") or {}
		out_attrs = qr.get("out_attrs") or {}
		reference = qr.get("reference_item_variant") or ""
		reference_filter = reference if reference_aware else None
		route_attrs = qr.get("target_attrs") or out_attrs

		# Exact routes can bypass a middle process. AMEL/GMEL may leave knitting
		# already in final Colour, so a later Dia-changing step must read
		# knitting receipts—not a Dyeing step that this route never visits.
		prev_step = None
		if kind != "conversion":
			for candidate in reversed(steps[:position]):
				if reference and _route_bypasses_step(
					ipd, candidate, reference, frozenset(route_attrs.items())
				):
					continue
				prev_step = candidate
				break
		received_key = (
			prev_step["process_name"] if prev_step else "",
			reference_filter,
		)
		if received_key not in received_cache:
			received_cache[received_key] = (
				get_step_received(
					lot.name,
					cloth,
					prev_step["process_name"],
					reference_filter,
				)
				if prev_step
				else None
			)
		prev_received = received_cache[received_key]

		if reference_filter not in planned_cache:
			planned_cache[reference_filter] = get_step_planned(
				lot.name, cloth, wo.process_name, reference_filter
			)
			ordered_cache[reference_filter] = get_produced_by_dia_colour(
				lot.name,
				wo.process_name,
				cloth,
				exclude_wo=wo.name,
				reference_item_variant=reference_filter,
			)
			consumed_cache[reference_filter] = get_consumed_by_dia_colour(
				lot.name,
				wo.process_name,
				cloth,
				exclude_wo=wo.name,
				reference_item_variant=reference_filter,
			)
		planned = planned_cache[reference_filter]
		ordered_out = ordered_cache[reference_filter]
		consumed_in = consumed_cache[reference_filter]

		in_key = (in_attrs.get(FABRIC_DIA_ATTRIBUTE) or "", in_attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
		out_key = (out_attrs.get(FABRIC_DIA_ATTRIBUTE) or "", out_attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
		available = None
		if prev_received is not None:
			produced = _lookup_attr_sum(prev_received, in_key)
			consumed = _lookup_attr_sum(
				{(k[0] or "", k[1] or ""): v for k, v in consumed_in.items()}, in_key)
			# NOTE (fan-out, 2026-07-21): piece-dyed rows may SHARE in_attrs (one
			# greige at one dia fanned into several to_colours), so this per-row
			# figure repeats the same input balance on every sibling row — it is
			# per-INPUT availability, not a per-row allocation. Advisory only;
			# consumption math aggregates per variant at calculate time.
			available = flt(produced - consumed, 3)
		plan = flt(planned.get(out_key))
		already = flt(ordered_out.get((out_key[0] or None, out_key[1] or None))
			or ordered_out.get(out_key))
		qr.update({
			"plan": plan,
			"ordered": already,
			"available": available,  # None = previous stage not managed here
			"prefill": max(plan - already, 0) if plan else 0,
		})


def _lookup_attr_sum(keyed, wanted):
	"""Sum a {(dia, colour): kg} dict for `wanted`, treating a blank side of the
	wanted key as 'any' — a colour-blind input (dia-only) matches every colour."""
	total = 0
	for (dia, colour), kg in keyed.items():
		if wanted[0] and dia and wanted[0] != dia:
			continue
		if wanted[1] and colour and wanted[1] != colour:
			continue
		total += flt(kg)
	return total


def _matrix_qty_rows(ipd, process_name, kind):
	"""One qty row per matrix group: {key, label, out_attrs}. The matrices are
	fully concrete (wildcards expanded at build time), so out_attrs is complete
	for every route. Legacy knitting matrices may still receive their Colour from
	the route-specific calculation fallback."""
	matrix_names = frappe.get_all(
		"IPD Process Matrix",
		filters={"ipd": ipd.name, "process_name": process_name, "docstatus": ["<", 2]},
		pluck="name",
	)
	if not matrix_names:
		frappe.throw(
			_("No IPD Process Matrix found for IPD {0} / process {1}. Save the IPD to regenerate it.").format(
				ipd.name, process_name
			)
		)

	qty_rows = []
	for name in matrix_names:
		matrix = frappe.get_doc("IPD Process Matrix", name)
		reference_attrs = {}
		if matrix.reference_item_variant:
			reference = frappe.get_cached_doc(
				"Item Variant", matrix.reference_item_variant
			)
			reference_attrs = {
				row.attribute: row.attribute_value
				for row in reference.get("attributes") or []
			}
		for group_index, group in sorted(matrix.get_combinations_grouped().items()):
			out = (group.get("output") or [{}])[0]
			inp = (group.get("input") or [{}])[0]
			out_attrs = out.get("attrs") or {}
			in_attrs = inp.get("attrs") or {}
			label = _group_label(kind, in_attrs, out_attrs)
			section, row_label = _section_and_row_label(in_attrs, out_attrs, label)
			if kind == "knitting" and reference_attrs:
				section = reference_attrs.get(FABRIC_COLOUR_ATTRIBUTE)
				row_label = reference_attrs.get(FABRIC_DIA_ATTRIBUTE) or label
				label = " · ".join(value for value in (section, row_label) if value)
			inputs = group.get("input") or []
			input_total = sum(flt(row.get("qty")) for row in inputs) or 1
			qty_rows.append({
				"key": f"{name}:{group_index}",
				"label": label,
				# section/row_label split the label for the popup's colour-section
				# layout; `label` itself stays untouched (server API compat).
				"section": section,
				"row_label": row_label,
				"out_attrs": out_attrs,
				# input-side attrs carry (from_dia, colour) for compacting and
				# (dia, from_colour) for dyeing — availability is keyed on them.
				"in_attrs": in_attrs,
				"reference_item_variant": matrix.reference_item_variant,
				"target_attrs": reference_attrs,
				"yarns": [
					{
						"yarn_item": row.get("item") or matrix.input_item,
						"ratio": flt(row.get("qty")) / input_total * 100,
					}
					for row in inputs
				] if kind == "knitting" else [],
			})
	return qty_rows


def _identity_qty_rows(ipd, treated_item, identity_row=None):
	"""No-conversion process (e.g. Washing): one qty row per variant combo of
	the treated item. Deliverable = receivable, so out_attrs is the full
	variant spec.

	PRIMARY derivation (identity row carries a `sequence`, i.e. a generic
	fabric_processes row): the DISTINCT output combos of the LAST transforming
	step before it — Washing after Re-Compacting offers exactly what
	Re-Compacting can produce (25 real rows), not every Dia x Colour the IPD
	ever mentions (128). FALLBACK to the IPD-wide union when the position is
	unknowable (legacy tab row without a sequence), there is no prior
	transforming step / matrix, or the prior step's output doesn't line up with
	the treated item. Both the popup and calculate's allowed-set validation call
	this same function, so entry and acceptance always agree."""
	declared = _item_attribute_names(treated_item)

	# An identity process on a NON-IPD item (e.g. the yarn) can only be 1:1 on
	# the item itself — the IPD's dia/colour values describe the CLOTH, and
	# stamping them onto another item would mint wrong variants.
	if treated_item != ipd.item and declared:
		frappe.throw(
			_("IPD {0}: identity process on {1} needs an attribute-less item — its attributes "
			"({2}) cannot be derived from this IPD.").format(ipd.name, treated_item, ", ".join(declared))
		)
	unsupported = [a for a in declared if a not in (FABRIC_DIA_ATTRIBUTE, FABRIC_COLOUR_ATTRIBUTE)]
	if unsupported:
		frappe.throw(
			_("IPD {0}: cannot derive values for attribute(s) {1} of {2} — identity processes "
			"support Dia/Colour items only.").format(ipd.name, ", ".join(unsupported), treated_item)
		)

	combos = _identity_combos_from_prev_step(ipd, treated_item, identity_row, declared)
	if combos is None:
		has_dia = FABRIC_DIA_ATTRIBUTE in declared
		has_colour = FABRIC_COLOUR_ATTRIBUTE in declared
		# UNION derivation: without a chain position, offer every dia/colour the
		# IPD knows (extra rows are harmless blanks; missing rows are a hard stop).
		dias = _identity_attr_values(ipd, FABRIC_DIA_ATTRIBUTE) if has_dia else []
		colours = _identity_attr_values(ipd, FABRIC_COLOUR_ATTRIBUTE) if has_colour else []
		if (has_dia and not dias) or (has_colour and not colours):
			frappe.throw(
				_("IPD {0}: cannot derive the {1} values for {2} — maintain the fabric tabs or "
				"the IPD's attribute mapping values.").format(
					ipd.name, FABRIC_DIA_ATTRIBUTE if (has_dia and not dias) else FABRIC_COLOUR_ATTRIBUTE, treated_item)
			)

		if dias and colours:
			combos = [{FABRIC_DIA_ATTRIBUTE: d, FABRIC_COLOUR_ATTRIBUTE: c} for d in dias for c in colours]
		elif dias:
			combos = [{FABRIC_DIA_ATTRIBUTE: d} for d in dias]
		elif colours:
			combos = [{FABRIC_COLOUR_ATTRIBUTE: c} for c in colours]
		else:
			combos = [{}]

	# Floor-friendly order: colour groups together, dias numerically inside.
	combos.sort(key=lambda c: (
		c.get(FABRIC_COLOUR_ATTRIBUTE) or "",
		_dia_sort_key(c.get(FABRIC_DIA_ATTRIBUTE)),
	))

	rows = []
	for i, combo in enumerate(combos):
		combo = _ordered_combo(combo)
		label = " · ".join(v or "?" for v in combo.values()) or treated_item
		section, row_label = _section_and_row_label(combo, combo, label)
		rows.append({
			"key": f"identity:{i}",
			"label": label,
			"section": section,
			"row_label": row_label,
			"out_attrs": combo,
		})
	return rows


def _identity_combos_from_prev_step(ipd, treated_item, identity_row, declared):
	"""Distinct output-side attr combos of the LAST transforming fabric step
	before this identity row, or None when the caller must fall back to the
	IPD-wide union. Transforming = the row changes something (a Change /
	Introduce / Consume mapping, or an item-changing conversion) — a Pin-only
	or mapping-less identity sibling is transparent and never wins the slot."""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	sequence = identity_row.get("sequence") if identity_row is not None else None
	if sequence is None:
		return None  # legacy ipd_processes row — no chain position

	prior = [
		row for row in get_fabric_process_rows(ipd)  # already sequence-ordered
		if flt(row.get("sequence")) < flt(sequence) and _is_transforming_row(row)
	]
	if not prior:
		return None
	prev = prior[-1]

	matrix_names = frappe.get_all(
		"IPD Process Matrix",
		filters={"ipd": ipd.name, "process_name": prev.get("fabric_process"), "docstatus": ["<", 2]},
		pluck="name",
	)
	combos, seen = [], set()
	for name in matrix_names:
		matrix = frappe.get_doc("IPD Process Matrix", name)
		if (matrix.output_item or ipd.item) != treated_item:
			continue  # the prior step produces a different item — not our input
		for _group_index, group in sorted(matrix.get_combinations_grouped().items()):
			for out in group.get("output") or []:
				attrs = out.get("attrs") or {}
				if set(attrs) != set(declared):
					# e.g. Washing straight after Knitting: knitting outputs carry
					# Dia only (Colour merged at calc) — the combos would mint
					# colour-less variants. Union fallback is the safe answer.
					return None
				key = frozenset(attrs.items())
				if key not in seen:
					seen.add(key)
					combos.append(dict(attrs))
	return combos or None


def _is_transforming_row(row):
	if any(
		m.get("role") in ("Change", "Introduce", "Consume")
		for m in row.get("value_mappings") or []
	):
		return True
	in_item, out_item = row.get("input_item"), row.get("output_item")
	return bool(in_item and out_item and in_item != out_item)


def _dia_sort_key(value):
	"""Numeric-first Dia ordering: parse the leading float ("16.25 Dia" -> 16.25);
	non-numeric values sort last, by string."""
	match = re.match(r"\s*(\d+(?:\.\d+)?)", str(value or ""))
	if match:
		return (0, float(match.group(1)), str(value))
	return (1, 0.0, str(value or ""))


def _ordered_combo(attrs):
	"""Stable display order for a variant combo: Dia, then Colour, then the rest
	alphabetically — keeps identity labels ("14 Dia · Black") byte-identical to
	the pre-fix union derivation."""
	rank = {FABRIC_DIA_ATTRIBUTE: 0, FABRIC_COLOUR_ATTRIBUTE: 1}
	return {a: attrs[a] for a in sorted(attrs, key=lambda a: (rank.get(a, 2), a))}


def _identity_attr_values(ipd, attribute):
	"""Union of every value the IPD's fabric processes mention for `attribute`
	(the generic mappings' from/to values, which the adapter also synthesizes from
	the legacy tabs), falling back to the IPD's attribute-mapping values. Generic
	and tab IPDs both flow through get_fabric_process_rows so the derivation is
	identical for either source."""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	values = []
	for row in get_fabric_process_rows(ipd):
		for mapping in row.get("value_mappings") or []:
			if mapping.get("attribute") != attribute:
				continue
			for value in (mapping.get("from_value"), mapping.get("to_value")):
				if value:
					values.append(value)
	if not values:
		values = get_ipd_attribute_values(ipd, attribute)
	return list(dict.fromkeys(values))


def _group_label(kind, in_attrs, out_attrs):
	if kind == "knitting":
		return out_attrs.get(FABRIC_DIA_ATTRIBUTE) or "?"
	if kind == "conversion":
		# One rule per group: consumed combo -> produced combo (the two sides carry
		# different attribute vocabularies — Consume/Introduce). A pair identical
		# on BOTH sides is noise for the floor user and drops off the LEFT:
		# knitting's "Navy → Navy · 14 Dia" reads as "Navy · 14 Dia"; a rule that
		# actually changes the pair ("Greige → Navy") is untouched.
		left_attrs = {a: v for a, v in in_attrs.items() if out_attrs.get(a) != v}
		left = " · ".join(left_attrs.get(a) or "?" for a in sorted(left_attrs))
		right = " · ".join(out_attrs.get(a) or "?" for a in sorted(out_attrs))
		if not right:
			# Consume-only rule (attribute dropped, nothing introduced): the
			# consumed combo alone reads better than a dangling "→ ?".
			return left or "?"
		return f"{left} → {right}" if left else right
	if in_attrs == out_attrs:
		# in-chain identity step: nothing changes — plain variant label
		return " · ".join(v or "?" for v in out_attrs.values()) or "?"
	changed = [a for a in out_attrs if in_attrs.get(a) != out_attrs.get(a)]
	if len(changed) > 1:
		# multi_swap (Dye-Compact): show the full combo transition
		return (" · ".join(in_attrs.get(a) or "?" for a in sorted(in_attrs))
			+ " → " + " · ".join(out_attrs.get(a) or "?" for a in sorted(out_attrs)))
	if kind == "dyeing":
		dia = out_attrs.get(FABRIC_DIA_ATTRIBUTE)
		swap = f"{in_attrs.get(FABRIC_COLOUR_ATTRIBUTE)} → {out_attrs.get(FABRIC_COLOUR_ATTRIBUTE)}"
		return f"{dia}: {swap}" if dia else swap
	colour = out_attrs.get(FABRIC_COLOUR_ATTRIBUTE)
	swap = f"{in_attrs.get(FABRIC_DIA_ATTRIBUTE)} → {out_attrs.get(FABRIC_DIA_ATTRIBUTE)}"
	return f"{colour}: {swap}" if colour else swap


def _sided_label(in_attrs, out_attrs, attributes):
	"""'<in side> → <out side>' across `attributes` (values joined ' · ' per
	side, attribute names sorted like _group_label). Applies the fix-3 collapse:
	a pair identical on both sides drops off the LEFT so an unchanged value
	shows once. One side empty -> the other side alone; both empty -> None."""
	attributes = sorted(attributes)
	left = " · ".join(
		in_attrs[a] or "?" for a in attributes
		if a in in_attrs and in_attrs.get(a) != out_attrs.get(a)
	)
	right = " · ".join(out_attrs[a] or "?" for a in attributes if a in out_attrs)
	if left and right:
		return f"{left} → {right}"
	return right or left or None


def _section_and_row_label(in_attrs, out_attrs, label):
	"""Generic Colour/rest split of a qty row's transition for the popup's
	sectioned layout. section = the Colour part (None when neither side carries
	Colour); row_label = the remaining attributes' part (typically Dia), falling
	back to the full label when nothing remains. Derived purely from the attr
	dicts — no process names involved."""
	names = set(in_attrs) | set(out_attrs)
	section = (
		_sided_label(in_attrs, out_attrs, [FABRIC_COLOUR_ATTRIBUTE])
		if FABRIC_COLOUR_ATTRIBUTE in names
		else None
	)
	row_label = _sided_label(in_attrs, out_attrs, names - {FABRIC_COLOUR_ATTRIBUTE})
	return section, row_label or label


def _knit_colour_options(ipd):
	"""Valid physical knitting-output colour choices.

	Generic-aware: these are the Colour values entering the first dyeing
	(Colour-swap) step.  They can differ route by route (Greige, Anthracite
	Melange, ...).  Derived from the generic fabric_processes rows; fall back to
	the recipe colours, then the IPD Colour mapping and finally all Colour values.
	"""
	from essdee_yrp.fabric_program import _greige_colour_options

	options = _greige_colour_options(ipd)
	if options:
		return options
	recipe_colours = [
		row.colour for row in ipd.get("colour_yarn_recipes") or []
		if row.cloth_item == ipd.item and row.colour
	]
	if recipe_colours:
		return list(dict.fromkeys(recipe_colours))
	values = get_ipd_attribute_values(ipd, FABRIC_COLOUR_ATTRIBUTE)
	if values:
		return values
	return frappe.get_all(
		"Item Attribute Value",
		filters={"attribute_name": FABRIC_COLOUR_ATTRIBUTE},
		pluck="name",
		order_by="name asc",
	)


@frappe.whitelist()
def get_lot_fabric_items(lot):
	"""Cloth items on the Lot's fabric table — used by the WO form to filter
	the Item link for cloth processes (client get_list can't query child tables)."""
	lot_doc = frappe.get_doc("Lot", lot)
	lot_doc.check_permission("read")
	return sorted({f.cloth_item for f in lot_doc.get("lot_fabric_details") or [] if f.cloth_item})


@frappe.whitelist()
def get_work_order_selection_context(lot, process_name):
	"""Return the only valid Item/IPD choices for a Work Order header.

	For a cloth process, a Lot fabric row is selectable only when its linked
	cloth IPD actually contains ``process_name``.  For every other process the
	Lot's garment Item/IPD is the single choice.  Desk, /web and server-side
	validation all use this response so their filtering/autofill cannot drift.
	"""
	return _get_work_order_selection_context(lot, process_name, check_permission=True)


def _get_work_order_selection_context(lot, process_name, check_permission=False):
	if not lot or not process_name:
		return {
			"is_cloth_process": False,
			"options": [],
			"item_options": [],
			"auto_item": None,
			"auto_production_detail": None,
		}

	lot_doc = frappe.get_doc("Lot", lot)
	if check_permission:
		lot_doc.check_permission("read")

	configured_cloth_process = bool(
		frappe.db.get_value("Process", process_name, "is_cloth_process")
	)
	cloth_options = []
	for fabric in lot_doc.get("lot_fabric_details") or []:
		if not fabric.cloth_item or not fabric.production_detail:
			continue
		try:
			ipd = frappe.get_cached_doc(
				"Item Production Detail", fabric.production_detail
			)
		except frappe.DoesNotExistError:
			continue
		if not (
			get_fabric_step(ipd, process_name)
			or get_identity_process_row(ipd, process_name)
		):
			continue
		cloth_options.append({
			"item": fabric.cloth_item,
			"production_detail": fabric.production_detail,
			"fabric_row": fabric.name,
		})

	# The IPD chain is authoritative. The Process flag still says that a
	# configured cloth process with no matching IPD must NOT fall through to the
	# garment Item, while older valid IPDs keep working if their flag is stale.
	is_cloth_process = configured_cloth_process or bool(cloth_options)
	options = cloth_options
	if not is_cloth_process:
		if lot_doc.get("item") and lot_doc.get("production_detail"):
			options.append({
				"item": lot_doc.item,
				"production_detail": lot_doc.production_detail,
				"fabric_row": None,
			})

	# Preserve Lot row order while removing accidental duplicate pairs.
	unique_options = []
	seen = set()
	for option in options:
		key = (option["item"], option["production_detail"])
		if key in seen:
			continue
		seen.add(key)
		unique_options.append(option)
	options = unique_options
	item_options = list(dict.fromkeys(option["item"] for option in options))

	auto = options[0] if len(options) == 1 else {}
	return {
		"is_cloth_process": is_cloth_process,
		"options": options,
		"item_options": item_options,
		"auto_item": auto.get("item"),
		"auto_production_detail": auto.get("production_detail"),
	}


@frappe.whitelist()
def calculate_fabric_deliverables(work_order, rows, modified=None):
	"""rows = [{fabric_row, colour?, yarn_qty?, entries: [{out_attrs, qty}]}].

	knitting:   entries = cloth kgs per dia; yarn deliverable computed by the
	            engine via cloth_per_kg_yarn, overridable with yarn_qty.
	dyeing:     entries = kgs per (dia, from->to colour) group, 1:1.
	compacting: entries = kgs per (colour, from->to dia) group, 1:1.
	Each entry carries the matrix group `key` ("<matrix>:<group_index>") the
	popup row came from — group resolution is BY KEY, never by attrs: two legal
	mappings can share identical output attrs (White→Black and Ecru→Black at
	the same dia), and an attrs-based first-match would misroute the quantity
	through the wrong group.

	The entered qty is the OUTPUT program demand. Knitting program excess is already
	included when Build Cloth Programs creates that qty, so Knitting ignores the
	Process default_excess here. Other processes scale RECEIVABLE by their Process
	wastage/excess. The DELIVERABLE (consumed input) is untouched by these values.

	Receivables are minted on the STEP's real output item (matrix.output_item,
	falling back to the Lot's cloth item) in that item's default UOM — a mid-chain
	conversion (grey yarn -> dyed yarn) must receive the DYED YARN, not the cloth.
	For knitting/dyeing/compacting the matrix output_item IS the cloth item, so
	their behaviour is unchanged."""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("write")
	_guard_not_modified(wo, modified)
	if wo.docstatus != 0:
		frappe.throw(_("Calculate can only update a draft Work Order."))

	lot = _get_lot(wo)
	fabric_rows = {f.name: f for f in _selected_lot_fabrics(wo, lot)}
	all_fabric_rows = {f.name for f in lot.get("lot_fabric_details") or []}
	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))

	# Knitting excess is already baked into the Lot program. Ignore the Process
	# default_excess for that step so it is never added twice. Other processes
	# retain their existing receivable wastage/excess calculation.
	proc = frappe.get_cached_value(
		"Process", wo.process_name, ["default_wastage", "default_excess"], as_dict=True) or {}
	recv_wastage = flt(proc.get("default_wastage"))
	process_excess = flt(proc.get("default_excess"))

	deliverables, receivables = [], []
	matrix_cache = {}
	uom_cache = {}

	def _default_uom(item):
		if item not in uom_cache:
			uom_cache[item] = frappe.db.get_value("Item", item, "default_unit_of_measure")
		return uom_cache[item]
	for entry in rows:
		fabric = fabric_rows.get(entry.get("fabric_row"))
		if not fabric:
			if entry.get("fabric_row") in all_fabric_rows:
				frappe.throw(
					_("Lot fabric row {0} is not selected on this Work Order.").format(
						entry.get("fabric_row")
					)
				)
			frappe.throw(_("Unknown Lot fabric row {0}.").format(entry.get("fabric_row")))
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		kind = _step_kind(ipd, get_fabric_step(ipd, wo.process_name))
		identity_row = None
		if not kind:
			identity_row = get_identity_process_row(ipd, wo.process_name)
			if identity_row:
				kind = "identity"
		if not kind:
			frappe.throw(_("{0} is not a fabric process on IPD {1}.").format(wo.process_name, ipd.name))
		recv_excess = 0 if kind == "knitting" else process_excess
		recv_factor = 1 - recv_wastage / 100.0 + recv_excess / 100.0
		if recv_factor <= 0:
			frappe.throw(_(
				"Process {0}: wastage {1}% / excess {2}% give a non-positive "
				"receivable factor ({3}). Check the Process percentages."
			).format(wo.process_name, recv_wastage, recv_excess, flt(recv_factor, 4)))

		if kind == "identity":
			# No conversion: deliverable = receivable, same variant, same qty.
			# out_attrs are client-sent: accept only combos this IPD derives.
			treated_item = identity_row.process_item or fabric.cloth_item
			treated_uom = frappe.db.get_value("Item", treated_item, "default_unit_of_measure")
			allowed = {frozenset((r["out_attrs"] or {}).items()) for r in _identity_qty_rows(ipd, treated_item, identity_row)}
			identity_bom_demands = []
			for line in entry.get("entries") or []:
				qty = flt(line.get("qty"))
				if qty <= 0:
					continue
				out_attrs = dict(line.get("out_attrs") or {})
				if frozenset(out_attrs.items()) not in allowed:
					frappe.throw(
						_("Combination {0} is not derived from IPD {1} — reopen the Calculate popup.").format(
							out_attrs or treated_item, ipd.name))
				variant = _resolve_variant(treated_item, out_attrs)
				deliverables.append({
					"item_variant": variant,
					"qty": qty,
					"uom": treated_uom,
					"pending_quantity": qty,
					"received_type": default_received_type,
					"is_calculated": 1,
				})
				recv_qty = flt(qty * recv_factor, 3)
				receivables.append({
					"item_variant": variant,
					"qty": recv_qty,
					"uom": treated_uom,
					"pending_quantity": recv_qty,
				})
				identity_bom_demands.append({
					"attrs": out_attrs,
					"qty": qty,
					"reference_item_variant": variant,
				})
			_append_bom_deliverables(
				deliverables,
				ipd,
				wo.process_name,
				identity_bom_demands,
				default_received_type,
			)
			continue

		has_colour = _item_has_attribute(fabric.cloth_item, FABRIC_COLOUR_ATTRIBUTE)
		colour = entry.get("colour")
		valid_colours = None
		if kind == "knitting":
			if not ((_knitting_row(ipd, wo.process_name) or {}).get("input_item") or ipd.get("yarn_item")):
				frappe.throw(_("Set the Yarn (Knitting input item) on IPD {0} first.").format(ipd.name))
			# colours are client-sent (entry-level for old payloads, line-level
			# for multi-colour knitting) — enforce the same restriction the UI
			# shows (greige = dyeing from-colours), else a crafted call could
			# mint variants that poison the (dia, colour) tracking keys
			valid_colours = set(_knit_colour_options(ipd))

		# Aggregate scaled inputs by variant; receivables per entered row.
		aggregated = {}
		fabric_receivables = []
		bom_demands = []
		for line in entry.get("entries") or []:
			qty = flt(line.get("qty"))
			if qty <= 0:
				continue
			line_colour = line.get("colour") or colour
			matrix, group = _resolve_matrix_group(
				matrix_cache, line.get("key"), ipd, wo.process_name
			)
			if kind == "knitting" and has_colour:
				if matrix.reference_item_variant:
					reference = frappe.get_cached_doc(
						"Item Variant", matrix.reference_item_variant
					)
					target_attrs = {
						row.attribute: row.attribute_value
						for row in reference.get("attributes") or []
					}
					expected_colour = get_knitting_output_colour(
						ipd,
						target_attrs.get(FABRIC_COLOUR_ATTRIBUTE),
						target_attrs.get(FABRIC_DIA_ATTRIBUTE),
					)
					if line_colour and line_colour != expected_colour:
						frappe.throw(_(
							"Knitting route {0} / {1} must receive colour {2}, "
							"not {3}. Reopen the Calculate popup."
						).format(
							target_attrs.get(FABRIC_COLOUR_ATTRIBUTE),
							target_attrs.get(FABRIC_DIA_ATTRIBUTE),
							expected_colour,
							line_colour,
						))
					line_colour = expected_colour
				if not line_colour:
					frappe.throw(_("Select the cloth Colour for {0}.").format(fabric.cloth_item))
				if line_colour not in valid_colours:
					frappe.throw(
						_("{0} is not a valid knitting-output colour for IPD {1}.").format(
							line_colour, ipd.name
						)
					)
			reference_item_variant = matrix.reference_item_variant
			out_combo = (group.get("output") or [{}])[0]
			out_qty = flt(out_combo.get("qty"))
			if out_qty <= 0:
				frappe.throw(_("Matrix group {0} has no positive output quantity.").format(line.get("key")))
			scale = qty / out_qty
			out_attrs = dict(out_combo.get("attrs") or {})
			if kind == "knitting" and line_colour and has_colour:
				out_attrs[FABRIC_COLOUR_ATTRIBUTE] = line_colour
			recv_item = matrix.output_item or fabric.cloth_item
			if not reference_item_variant:
				reference_item_variant = _resolve_variant(recv_item, out_attrs)
			reference_attrs = (
				_variant_attrs(reference_item_variant)
				if reference_item_variant
				else out_attrs
			)
			bom_demands.append({
				"attrs": reference_attrs,
				"qty": qty,
				"reference_item_variant": reference_item_variant,
			})

			for inp in group.get("input") or []:
				input_item = inp.get("item") or matrix.input_item or ipd.item
				inp_qty = flt(inp.get("qty")) * scale * (1 + flt(inp.get("wastage_pct")) / 100.0)
				variant = _resolve_variant(input_item, inp.get("attrs") or {})
				key = (variant, inp.get("uom"), reference_item_variant or "")
				aggregated.setdefault(key, {"item": input_item, "qty": 0.0})
				aggregated[key]["qty"] += inp_qty

			# The receivable is the STEP's output item (a mid-chain conversion —
			# grey yarn -> dyed yarn — produces the dyed yarn, NOT the Lot's cloth).
			# For knitting/dyeing/compacting matrices output_item IS the cloth item.
			recv_qty = flt(qty * recv_factor, 3)
			fabric_receivables.append({
				"item_variant": _resolve_variant(recv_item, out_attrs),
				"qty": recv_qty,
				"uom": _default_uom(recv_item),
				"pending_quantity": recv_qty,
				"fabric_reference_variant": reference_item_variant,
			})
		if not fabric_receivables:
			continue

		# Knitting: the popup's editable yarn figure overrides the computed
		# input. Valid while knitting matrices have exactly ONE resolved input
		# variant; with more inputs the override is ignored.
		yarn_override = flt(entry.get("yarn_qty"))
		if kind == "knitting" and yarn_override > 0 and len(aggregated) == 1:
			next(iter(aggregated.values()))["qty"] = yarn_override

		for (variant, uom, reference_item_variant), data in aggregated.items():
			qty = flt(data["qty"], 3)
			deliverables.append({
				"item_variant": variant,
				"qty": qty,
				"uom": uom or _default_uom(data["item"]),
				"pending_quantity": qty,
				"received_type": default_received_type,
				"is_calculated": 1,
				"fabric_reference_variant": reference_item_variant or None,
			})

		# Item BOM rows are process consumables in addition to the matrix's
		# principal input. Calculate them per finished-route demand so hidden
		# allocation metadata remains available when several routes consolidate
		# into one physical Work Order Deliverable row.
		_append_bom_deliverables(
			deliverables,
			ipd,
			wo.process_name,
			bom_demands,
			default_received_type,
		)
		receivables.extend(fabric_receivables)

	if not deliverables:
		frappe.throw(_("Enter a quantity greater than zero for at least one row."))

	# Base YRP now treats transaction UOM as Item master data. Preserve the
	# engine's physical stock quantity before Work Order validation overwrites
	# each row's UOM (for example, 20 Pieces -> 2 Boxes at factor 10).
	_normalize_generated_uom_rows(deliverables)
	_normalize_generated_uom_rows(receivables)

	deliverables = _consolidate_fabric_rows(
		deliverables, "Work Order Deliverables"
	)
	receivables = _consolidate_fabric_rows(
		receivables, "Work Order Receivables"
	)

	# Every calculated row is its OWN logical row for the Vue item editors —
	# group_items_for_ui buckets by row_index, and rows without one collapse
	# into a single rendered entry (the "only one dia shows" bug). The "fc-"
	# prefix keeps them clear of manual rows' numeric indices.
	for i, row in enumerate(deliverables):
		row["table_index"] = 0
		row["row_index"] = f"fc-{i}"
	for i, row in enumerate(receivables):
		row["table_index"] = 0
		row["row_index"] = f"fc-{i}"

	# Idempotent rewrite: drop prior calculated deliverables,
	# replace receivables wholesale, clear the grouped-JSON so sync_vue_item_details
	# doesn't resurrect stale rows.
	kept = [d for d in wo.get("deliverables") or [] if not d.get("is_calculated")]
	wo.set("deliverables", kept)
	for d in deliverables:
		wo.append("deliverables", d)
	wo.set("receivables", [])
	for r in receivables:
		wo.append("receivables", r)
	wo.deliverable_details = ""
	wo.receivable_details = ""
	wo.save()

	return {"deliverables": len(deliverables), "receivables": len(receivables)}


def _normalize_generated_uom_rows(rows):
	from yrp.stock.uom import resolve_item_uom
	from yrp.stock.utils import get_conversion_factor

	for row in rows or []:
		item_variant = row.get("item_variant")
		if not item_variant:
			continue
		authoritative = resolve_item_uom(item_variant)
		source_uom = row.get("uom") or authoritative.stock_uom
		source = get_conversion_factor(item_variant, source_uom)
		source_factor = flt(source.get("conversion_factor")) or 1
		target_factor = flt(authoritative.conversion_factor) or 1
		for fieldname in (
			"qty",
			"pending_quantity",
			"stock_update",
			"cancelled_quantity",
		):
			if fieldname in row:
				row[fieldname] = flt(
					flt(row.get(fieldname)) * source_factor / target_factor,
					6,
				)
		row["uom"] = authoritative.uom


def _append_bom_deliverables(
	deliverables,
	ipd,
	process_name,
	demands,
	default_received_type,
):
	"""Append Item BOM requirements using the same per-route demand contract."""
	from yrp.yrp.utils.ipd_engine import get_consumables

	for demand in demands:
		for bom_row in get_consumables(
			ipd.name,
			demand["qty"],
			variants=[{"attrs": demand["attrs"], "qty": demand["qty"]}],
			process_name=process_name,
		):
			bom_item = bom_row.get("item")
			if not bom_item or flt(bom_row.get("qty")) <= 0:
				continue
			deliverables.append({
				"item_variant": _resolve_variant(
					bom_item, bom_row.get("attrs") or {}
				),
				"qty": flt(bom_row.get("qty"), 3),
				"uom": bom_row.get("uom")
				or frappe.db.get_value(
					"Item", bom_item, "default_unit_of_measure"
				),
				"pending_quantity": flt(bom_row.get("qty"), 3),
				"received_type": default_received_type,
				"is_calculated": 1,
				"fabric_reference_variant": (
					demand.get("reference_item_variant") or None
				),
			})


def _resolve_matrix_group(matrix_cache, key, ipd, process_name):
	"""Resolve "<matrix>:<group_index>" and verify the matrix really belongs to
	this IPD + process — the key comes from the client."""
	if not key or ":" not in str(key):
		frappe.throw(_("Missing matrix group key on a calculation row."))
	if str(key).startswith("identity:"):
		# The IPD changed between popup open and Calculate (identity -> tab).
		frappe.throw(_("The IPD's processes changed — reopen the Calculate popup."))
	matrix_name, group_index = str(key).rsplit(":", 1)
	if not group_index.isdigit():
		frappe.throw(_("Malformed matrix group key {0} — reopen the Calculate popup.").format(key))
	if matrix_name not in matrix_cache:
		try:
			matrix = frappe.get_doc("IPD Process Matrix", matrix_name)
		except frappe.DoesNotExistError:
			# the IPD was re-saved between popup open and Calculate — matrices
			# are wiped and rebuilt under new names on every IPD save
			frappe.throw(_("The IPD's matrices changed — reopen the Calculate popup."))
		matrix_cache[matrix_name] = (matrix, matrix.get_combinations_grouped())
	matrix, groups = matrix_cache[matrix_name]
	if matrix.ipd != ipd.name or matrix.process_name != process_name:
		frappe.throw(_("Matrix {0} does not belong to IPD {1} / process {2}.").format(
			matrix_name, ipd.name, process_name))
	group = groups.get(int(group_index))
	if group is None:
		frappe.throw(_("Matrix group {0} no longer exists — reopen the Calculate popup.").format(key))
	return matrix, group


def _resolve_variant(item, attrs):
	"""Resolve the Item Variant for a minted deliverable/receivable, stamping
	ONLY the attributes the target Item actually declares.

	The IPD matrix combo defines each minted row's intended attribute set. New
	colour-wise yarn recipes provide the exact Yarn Colour and therefore take the
	full variant path. Older matrices may omit attributes even when the Item master
	declares them, so the partial-set fallback remains for compatibility. Relative
	to the base resolver:

	- attrs the Item does NOT declare are dropped — create_variant would
	  silently ignore them anyway, but they poison the tuple lookup (the args
	  tuple never matches any stored variant tuple), which routes to a
	  create whose autoname collides with the existing variant;
	- attrs the Item DOES declare are always kept, never dropped;
	- declared attributes ABSENT from attrs are simply not stamped: the
	  variant is looked up / created with the partial set (an attr-less yarn
	  resolves to the bare item-named variant) instead of throwing.

	Items with a dependent attribute (garment stages) keep the base resolver
	untouched — the stage machinery owns which attributes apply there."""
	from yrp.yrp.doctype.item.item import get_or_create_variant

	attrs = {k: v for k, v in (attrs or {}).items() if v}
	item_doc = frappe.get_cached_doc("Item", item)
	if item_doc.get("dependent_attribute"):
		return get_or_create_variant(item, attrs)

	declared = _item_attribute_names(item)
	filtered = {k: v for k, v in attrs.items() if k in declared}
	if all(a in filtered for a in declared):
		return get_or_create_variant(item, filtered)

	# Partial set: base create_variant would throw "Please mention <attr>".
	# Mirror its shape (display_name = value, sorted tuple hash) so the base
	# tuple lookup finds this variant on later full-machinery passes too.
	variant = frappe.new_doc("Item Variant")
	variant.item = item_doc.name
	variant.set("attributes", [
		{"attribute": a, "attribute_value": filtered[a], "display_name": filtered[a]}
		for a in declared if a in filtered
	])
	if filtered:
		variant.item_tuple_attribute = str(tuple(sorted(filtered.items())))
	# Dedupe scoped to THIS item: variant names are hyphen-joins (item +
	# values) and live items are themselves hyphen-named (TT-YARN + "GREY"
	# aliases item TT-YARN-GREY), so a name-only lookup could silently link
	# ANOTHER item's variant. A cross-item name collision instead fails
	# loudly at insert (review follow-up).
	existing = frappe.db.exists(
		"Item Variant", {"name": variant.get_name(), "item": item_doc.name})
	if existing:
		return existing
	variant.insert()
	return variant.name


def _item_has_attribute(item, attribute):
	return attribute in _item_attribute_names(item)


def _variant_attrs(item_variant):
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


def _item_attribute_names(item):
	item_doc = frappe.get_cached_doc("Item", item)
	return [row.attribute for row in item_doc.get("attributes") or []]


def _get_lot(wo):
	if not wo.get("lot"):
		frappe.throw(_("Select a Lot on the Work Order first."))
	lot = frappe.get_doc("Lot", wo.lot)
	lot.check_permission("read")
	return lot


def _knitting_row(ipd, process_name):
	"""The generic fabric-process row for this knitting (conversion) step — the
	source of the consumed yarn (input_item) and cloth-per-kg-yarn (quantity_ratio).
	Works for BOTH generic and tab IPDs (the adapter synthesizes the tab knitting
	row with input_item = yarn_item and quantity_ratio = cloth_per_kg_yarn). Called
	only for knitting-kind steps, so the matched row is the conversion. None when no
	row matches (blank tab yarn_item on a tab IPD -> callers fall back to it)."""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	for row in get_fabric_process_rows(ipd):
		if row.get("fabric_process") == process_name:
			return row
	return None
