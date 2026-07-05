# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Requirement -> chain back-computation ("the common function").

The Lot states WHAT it finally needs (colour + dia + kg of finished cloth);
this module walks the IPD's fabric chain BACKWARD through the auto-generated
IPD Process Matrix docs and computes, per step, what must be produced and fed —
down to the yarn kgs. Matrices are the ONLY quantity source (user rule
2026-07-04), so wastage later is a data change, never a solver change.

Results land in `Lot Fabric Step Ledger` (planned_weight, server-owned) and
pre-seed untouched knitting-program rows. Triggered from IPD approval
(rebuild_fabric_plans_for_ipd) and from Lot requirement saves when the IPD is
already Approved. Plan state never blocks WOs/GRNs (warn-only doctrine).

Spec: docs/design/2026-07-04-fabric-chain-plan.md
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt, now_datetime

from essdee_yrp.fabric_chain import get_fabric_steps
from essdee_yrp.fabric_ipd import FABRIC_COLOUR_ATTRIBUTE, FABRIC_DIA_ATTRIBUTE
from essdee_yrp.ipd_validations import is_cloth_ipd


class FabricPlanError(frappe.ValidationError):
	pass


def solve_chain_backward(ipd_doc, requirement):
	"""requirement: {frozenset({(attr, value), ...}): kg} keyed by finished-cloth
	attrs. Returns (step_plans FIRST->LAST, unreachable list).

	step_plans rows: {process_name, position, shape,
	  outputs: {attrs_frozenset: kg},   # what the step must produce
	  inputs:  {attrs_frozenset: kg}}   # what must be fed to it
	The conversion step's input key is frozenset() (attr-less yarn).

	Scale rule is byte-identical to calculate_fabric_deliverables:
	in_kg = out_kg × in_qty/out_qty × (1 + wastage_pct/100)."""
	steps = get_fabric_steps(ipd_doc)
	demand = dict(requirement)
	step_plans, unreachable = [], []

	for step in reversed(steps):
		groups, declared_attrs = _load_output_indexed_groups(ipd_doc.name, step["process_name"])
		outputs, inputs, next_demand = {}, {}, {}
		for combo, kg in demand.items():
			# project onto the attrs this matrix declares; attrs the matrix
			# does not know (e.g. Dia through an unpinned colour swap) are
			# CARRIED unchanged to the next demand — dropping them would
			# merge per-dia demand and report false unreachables.
			projected = frozenset((a, v) for a, v in combo if a in declared_attrs)
			carried = frozenset((a, v) for a, v in combo if a not in declared_attrs)
			matched = groups.get(projected)
			if matched == "AMBIGUOUS":
				frappe.throw(
					_("IPD {0} / {1}: two matrix groups produce the same output {2} — "
					"pin the mapping rows (dia-wise / colour-wise) to make the plan "
					"deterministic.").format(ipd_doc.name, step["process_name"], dict(projected)),
					FabricPlanError,
				)
			if not matched:
				unreachable.append({
					"position": step["position"], "process_name": step["process_name"],
					"attrs": dict(combo), "kg": kg,
				})
				continue
			out_qty = flt((matched.get("output") or [{}])[0].get("qty"))
			if out_qty <= 0:
				continue
			scale = kg / out_qty
			outputs[combo] = outputs.get(combo, 0) + kg
			for inp in matched.get("input") or []:
				in_kg = flt(inp.get("qty")) * scale * (1 + flt(inp.get("wastage_pct")) / 100.0)
				in_key = frozenset((inp.get("attrs") or {}).items())
				if step["shape"] != "conversion":
					# carried attrs ride along BETWEEN cloth stages; the
					# conversion input is a DIFFERENT item (yarn) — its key
					# stays clean (frozenset()) so the yarn figure aggregates
					in_key = in_key | carried
				inputs[in_key] = inputs.get(in_key, 0) + in_kg
				next_demand[in_key] = next_demand.get(in_key, 0) + in_kg
		step_plans.append({
			"process_name": step["process_name"], "position": step["position"],
			"shape": step["shape"], "outputs": outputs, "inputs": inputs,
		})
		demand = next_demand

	return list(reversed(step_plans)), unreachable


def _load_output_indexed_groups(ipd_name, process_name):
	"""Matrix groups of (ipd, process) indexed by their OUTPUT attr frozenset.
	A duplicate output projection marks the key "AMBIGUOUS" — the solver throws
	only if demand actually hits it (protects grandfathered IPDs)."""
	matrix_names = frappe.get_all(
		"IPD Process Matrix",
		filters={"ipd": ipd_name, "process_name": process_name, "docstatus": ["<", 2]},
		pluck="name",
	)
	indexed, declared = {}, set()
	for name in matrix_names:
		matrix = frappe.get_doc("IPD Process Matrix", name)
		for row in matrix.get("output_attributes") or []:
			declared.add(row.attribute)
		for _idx, group in matrix.get_combinations_grouped().items():
			out = (group.get("output") or [{}])[0]
			key = frozenset((out.get("attrs") or {}).items())
			indexed[key] = "AMBIGUOUS" if key in indexed else group
	return indexed, declared


def build_fabric_plan(lot_doc, fabric_row, raise_on_unreachable=True, ipd_doc=None):
	"""Solve one (lot, cloth) requirement and persist: ledger planned rows +
	knitting-program pre-seed + plan_status on the fabric row. Direct row-level
	writes under the per-lot lock (same discipline as GRN tracking).

	`ipd_doc`: pass the in-save IPD document when called from its own on_update —
	the document cache is only cleared AFTER on_update, so a fresh fetch there
	would solve against the PRE-save chain."""
	requirement_rows = [
		r for r in lot_doc.get("lot_fabric_requirements") or []
		if r.cloth_item == fabric_row.cloth_item and flt(r.weight) > 0
	]
	if not fabric_row.production_detail:
		return None
	if not requirement_rows:
		_clear_plan(lot_doc, fabric_row)
		return None

	ipd = ipd_doc if (ipd_doc and ipd_doc.name == fabric_row.production_detail) \
		else frappe.get_cached_doc("Item Production Detail", fabric_row.production_detail)
	requirement = {}
	for row in requirement_rows:
		attrs = {FABRIC_DIA_ATTRIBUTE: row.dia}
		if row.colour:
			attrs[FABRIC_COLOUR_ATTRIBUTE] = row.colour
		key = frozenset(attrs.items())
		requirement[key] = requirement.get(key, 0) + flt(row.weight)

	step_plans, unreachable = solve_chain_backward(ipd, requirement)
	if not step_plans:
		# zero-step chain (fully bought cloth): nothing to plan
		_clear_plan(lot_doc, fabric_row)
		return None
	if unreachable:
		message = _("No chain path produces:") + "<br>" + "<br>".join(
			f"{escape_html(str(u['attrs']))} — {flt(u['kg'], 3)} kg "
			f"({escape_html(u['process_name'])})"
			for u in unreachable[:8]
		) + "<br>" + _("Add mapping rows on IPD {0} or correct the requirement.").format(
			escape_html(ipd.name))
		if raise_on_unreachable:
			frappe.throw(message, FabricPlanError)
		_set_plan_status(fabric_row, "Error", frappe.utils.strip_html(message)[:200])
		return None

	_write_plan_rows(lot_doc, fabric_row.cloth_item, step_plans)
	_preseed_knitting_program(lot_doc, fabric_row.cloth_item, step_plans)
	_set_plan_status(fabric_row, "Built", None)
	return step_plans


def _write_plan_rows(lot_doc, cloth_item, step_plans):
	"""planned_weight is solver-owned: rewrite it on every build; receipt-bearing
	rows survive at planned 0; planned-only rows that lost their plan die."""
	existing = {}
	for row in lot_doc.get("lot_fabric_step_ledger") or []:
		if row.cloth_item != cloth_item:
			continue
		existing[(row.process_name or "", row.side or "Output", row.dia or "", row.colour or "")] = row

	wanted = {}
	for plan in step_plans:
		for combo, kg in plan["outputs"].items():
			attrs = dict(combo)
			key = (plan["process_name"], "Output",
				attrs.get(FABRIC_DIA_ATTRIBUTE) or "", attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
			wanted[key] = wanted.get(key, 0) + kg
	# the FIRST step's inputs = yarn / procurement figure
	if step_plans:
		first = step_plans[0]
		for combo, kg in first["inputs"].items():
			attrs = dict(combo)
			key = (first["process_name"], "Input",
				attrs.get(FABRIC_DIA_ATTRIBUTE) or "", attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
			wanted[key] = wanted.get(key, 0) + kg

	inserted = 0
	for key, kg in wanted.items():
		process_name, side, dia, colour = key
		row = existing.pop(key, None)
		if row:
			frappe.db.set_value("Lot Fabric Step Ledger", row.name, "planned_weight",
				flt(kg, 3), update_modified=False)
		else:
			inserted += 1
			new_row = frappe.new_doc("Lot Fabric Step Ledger")
			new_row.parenttype = "Lot"
			new_row.parent = lot_doc.name
			new_row.parentfield = "lot_fabric_step_ledger"
			new_row.idx = len(lot_doc.get("lot_fabric_step_ledger") or []) + inserted
			new_row.cloth_item = cloth_item
			new_row.process_name = process_name
			new_row.side = side
			new_row.dia = dia or None
			new_row.colour = colour or None
			new_row.planned_weight = flt(kg, 3)
			new_row.received_weight = 0
			new_row.save(ignore_permissions=True)

	for key, row in existing.items():
		if flt(row.received_weight):
			frappe.db.set_value("Lot Fabric Step Ledger", row.name, "planned_weight", 0,
				update_modified=False)
		else:
			frappe.delete_doc("Lot Fabric Step Ledger", row.name,
				ignore_permissions=True, force=True)


def _preseed_knitting_program(lot_doc, cloth_item, step_plans):
	"""The knitting program stays USER-OWNED (the WO driver): pre-seed missing
	or untouched rows from the conversion step's per-dia output sums; leave
	edited rows alone and warn about the drift."""
	conversion = next((p for p in step_plans if p["shape"] == "conversion"), None)
	if not conversion:
		return
	per_dia = {}
	for combo, kg in conversion["outputs"].items():
		dia = dict(combo).get(FABRIC_DIA_ATTRIBUTE)
		if dia:
			per_dia[dia] = per_dia.get(dia, 0) + kg

	program_rows = {
		r.dia: r for r in lot_doc.get("lot_fabric_programs") or []
		if r.cloth_item == cloth_item
	}
	drift = []
	inserted = 0
	for dia, kg in per_dia.items():
		kg = flt(kg, 3)
		row = program_rows.get(dia)
		if row is None:
			inserted += 1
			new_row = frappe.new_doc("Lot Fabric Program")
			new_row.parenttype = "Lot"
			new_row.parent = lot_doc.name
			new_row.parentfield = "lot_fabric_programs"
			new_row.idx = len(lot_doc.get("lot_fabric_programs") or []) + inserted
			new_row.cloth_item = cloth_item
			new_row.dia = dia
			new_row.weight = kg
			new_row.received_weight = 0
			new_row.save(ignore_permissions=True)
		elif not flt(row.weight):
			frappe.db.set_value("Lot Fabric Program", row.name, "weight", kg,
				update_modified=False)
		elif abs(flt(row.weight) - kg) > 0.001:
			drift.append(f"{escape_html(cloth_item)} · {escape_html(dia)}: "
				f"program {flt(row.weight)} kg vs plan {kg} kg")
	if drift:
		frappe.msgprint("<br>".join(drift),
			title=_("Knitting program differs from the plan"), indicator="orange")


def _set_plan_status(fabric_row, status, error):
	frappe.db.set_value("Lot Fabric Detail", fabric_row.name, {
		"plan_status": status,
		"plan_error": error,
		"plan_built_on": now_datetime() if status == "Built" else None,
	}, update_modified=False)


def _clear_plan(lot_doc, fabric_row):
	for row in list(lot_doc.get("lot_fabric_step_ledger") or []):
		if row.cloth_item != fabric_row.cloth_item:
			continue
		if flt(row.received_weight):
			frappe.db.set_value("Lot Fabric Step Ledger", row.name, "planned_weight", 0,
				update_modified=False)
		else:
			frappe.delete_doc("Lot Fabric Step Ledger", row.name,
				ignore_permissions=True, force=True)
	_set_plan_status(fabric_row, "", None)


def rebuild_fabric_plans_for_ipd(ipd_doc):
	"""IPD-approval hook body: rebuild the plan of every open Lot referencing
	this IPD. Per-lot try/except — one lot's bad requirement never blocks the
	approval or the other lots; failures aggregate into ONE msgprint."""
	fabric_rows = frappe.get_all(
		"Lot Fabric Detail",
		filters={"production_detail": ipd_doc.name, "parenttype": "Lot"},
		fields=["name", "parent", "cloth_item", "production_detail"],
	)
	built, failed = [], []
	for ref in fabric_rows:
		lot_status = frappe.db.get_value("Lot", ref.parent, "status")
		if lot_status and lot_status != "Open":
			continue
		try:
			frappe.db.get_value("Lot", ref.parent, "name", for_update=True)
			lot_doc = frappe.get_doc("Lot", ref.parent)
			fabric_row = next(
				(r for r in lot_doc.get("lot_fabric_details") or [] if r.name == ref.name), None)
			if not fabric_row:
				continue
			plans = build_fabric_plan(lot_doc, fabric_row, raise_on_unreachable=False,
				ipd_doc=ipd_doc)
			if plans:
				built.append((ref.parent, plans))
		except Exception as e:
			frappe.clear_last_message()  # the aggregate below is the one dialog
			failed.append(f"{escape_html(ref.parent)}: {escape_html(str(e)[:120])}")
			frappe.db.set_value("Lot Fabric Detail", ref.name,
				{"plan_status": "Error", "plan_error": str(e)[:200]}, update_modified=False)

	if built or failed:
		parts = []
		for lot_name, plans in built[:5]:
			figures = _plan_headline(plans)
			parts.append(f"{escape_html(lot_name)}: {figures}")
		if failed:
			parts.append(_("FAILED — fix the lot's requirement:") + "<br>" + "<br>".join(failed[:5]))
		frappe.msgprint("<br>".join(parts), title=_("Fabric plans rebuilt"), indicator="blue")


def _plan_headline(step_plans):
	"""'102.04 kg yarn · D22 100 kg, D18 60 kg' — the approval confirmation."""
	if not step_plans:
		return ""
	first = step_plans[0]
	parts = []
	attrless = flt(first["inputs"].get(frozenset()), 2)
	if attrless:
		parts.append(_("{0} kg input").format(attrless))
	per_dia = {}
	for combo, kg in first["outputs"].items():
		dia = dict(combo).get(FABRIC_DIA_ATTRIBUTE)
		if dia:
			per_dia[dia] = per_dia.get(dia, 0) + kg
	parts.extend(f"{escape_html(d)} {flt(kg, 2)} kg" for d, kg in list(per_dia.items())[:6])
	return " · ".join(parts)


def on_ipd_update(doc, method=None):
	"""hooks.py on_update, AFTER sync_fabric_process_matrices (the solver must
	read the matrices just rebuilt in this same save). Plans rebuild only on
	APPROVED cloth IPDs; edits to a non-approved IPD mark referencing plans
	Stale instead."""
	if not is_cloth_ipd(doc):
		return
	if doc.approval_status == "Approved":
		rebuild_fabric_plans_for_ipd(doc)
	else:
		frappe.db.sql(
			"""
			UPDATE `tabLot Fabric Detail`
			SET plan_status = 'Stale'
			WHERE production_detail = %s AND parenttype = 'Lot' AND plan_status = 'Built'
			""",
			(doc.name,),
		)
