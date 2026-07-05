# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""The ordered fabric process chain of a cloth IPD.

One normalizer feeds every consumer (matrix sync, WO popup, tracking, the
backward planner): the three fabric processes (knitting -> dyeing -> compacting)
are synthesized into ordered steps from their tabs. Shapes are fixed:
knitting = item conversion (yarn -> cloth), dyeing = Colour swap, compacting =
Dia swap. Each process's template (is_item_conversion / value_change_attributes
on its Process master) is validated by validate_fabric_process_shapes.

Spec: docs/design/2026-07-04-fabric-chain-plan.md
"""

import frappe
from frappe import _

from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
)


def get_fabric_steps(ipd_doc):
	"""Ordered chain steps, first -> last. Each step:
	{position, process_name, shape ("conversion"|"swap"),
	 attribute (swap attr or None)}."""
	steps = []
	if ipd_doc.get("knitting_process"):
		steps.append({
			"process_name": ipd_doc.knitting_process, "shape": "conversion",
			"attribute": None,
		})
	if ipd_doc.get("dyeing_process"):
		steps.append({
			"process_name": ipd_doc.dyeing_process, "shape": "swap",
			"attribute": FABRIC_COLOUR_ATTRIBUTE,
		})
	if ipd_doc.get("compacting_process"):
		steps.append({
			"process_name": ipd_doc.compacting_process, "shape": "swap",
			"attribute": FABRIC_DIA_ATTRIBUTE,
		})

	for position, step in enumerate(steps):
		step["position"] = position
	return steps


def get_fabric_step(ipd_doc, process_name):
	"""The chain step for `process_name` on this IPD, or None."""
	if not process_name:
		return None
	for step in get_fabric_steps(ipd_doc):
		if step["process_name"] == process_name:
			return step
	return None


def values_entering(ipd_doc, position, attribute):
	"""Values of `attribute` flowing INTO the step at `position` — the chain
	state walked forward from the knitting dias / greige colours through every
	upstream swap. This one primitive drives wildcard/pin expansion for any
	step (the user's stage-to-stage "combination")."""
	from essdee_yrp.ipd_validations import get_ipd_attribute_values

	steps = get_fabric_steps(ipd_doc)

	if attribute == FABRIC_DIA_ATTRIBUTE:
		values = [r.dia for r in ipd_doc.get("knitting_dia_details") or [] if r.dia]
	else:
		values = [r.from_colour for r in ipd_doc.get("dyeing_colour_details") or [] if r.from_colour]
	if not values:
		values = get_ipd_attribute_values(ipd_doc, attribute)
	values = list(dict.fromkeys(values))

	for step in steps[:position]:
		if step["shape"] != "swap" or step["attribute"] != attribute:
			continue
		mappings = _step_swap_rows(ipd_doc, step)
		next_values = []
		for value in values:
			rows = [m for m in mappings if m["from_value"] == value]
			if not rows:
				next_values.append(value)
				continue
			next_values.extend(m["to_value"] for m in rows if m["to_value"])
			if all(m["pin_value"] for m in rows):
				# only PINNED rows map this value — at every other pin it
				# passes through unchanged, so it stays alive downstream
				next_values.append(value)
		values = list(dict.fromkeys(next_values))
	return values


def _step_swap_rows(ipd_doc, step):
	"""from/to (+pin) rows of a swap step, from its classic tab table."""
	if step["attribute"] == FABRIC_COLOUR_ATTRIBUTE:
		return [
			{"pin_value": r.dia, "from_value": r.from_colour, "to_value": r.to_colour}
			for r in ipd_doc.get("dyeing_colour_details") or []
		]
	return [
		{"pin_value": r.colour, "from_value": r.from_dia, "to_value": r.to_dia}
		for r in ipd_doc.get("compacting_dia_details") or []
	]


def final_combos(ipd_doc, has_colour=True):
	"""The (dia, colour) combos the FULL chain can produce — the reachable
	finished-cloth space the Lot requirement is validated against. Derived from
	the LAST step's matrix groups (fully expanded at build time); falls back to
	the walked chain state when no matrices exist yet."""
	steps = get_fabric_steps(ipd_doc)
	if steps:
		last = steps[-1]
		matrix_names = frappe.get_all(
			"IPD Process Matrix",
			filters={"ipd": ipd_doc.name, "process_name": last["process_name"], "docstatus": ["<", 2]},
			pluck="name",
		)
		combos = set()
		for name in matrix_names:
			matrix = frappe.get_doc("IPD Process Matrix", name)
			for _idx, group in matrix.get_combinations_grouped().items():
				out = (group.get("output") or [{}])[0]
				attrs = out.get("attrs") or {}
				combos.add(frozenset(attrs.items()))
		if combos:
			return combos

	position = len(steps)
	dias = values_entering(ipd_doc, position, FABRIC_DIA_ATTRIBUTE)
	colours = values_entering(ipd_doc, position, FABRIC_COLOUR_ATTRIBUTE) if has_colour else [None]
	combos = set()
	for dia in dias:
		for colour in colours:
			attrs = {FABRIC_DIA_ATTRIBUTE: dia}
			if colour:
				attrs[FABRIC_COLOUR_ATTRIBUTE] = colour
			combos.add(frozenset(attrs.items()))
	return combos


def validate_fabric_chain(doc):
	"""Called from validate_cloth_ipd: the fabric processes must each use a
	DISTINCT Process master (matrix, WO and ledger keys all resolve per
	process_name), so knitting/dyeing/compacting can't share one Process."""
	steps = get_fabric_steps(doc)
	names = [s["process_name"] for s in steps]
	if len(names) != len(set(names)):
		frappe.throw(_("Knitting, dyeing and compacting must each use a DIFFERENT "
			"Process master."))
