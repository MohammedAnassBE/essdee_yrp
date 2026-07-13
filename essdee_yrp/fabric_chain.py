# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""The ordered fabric process chain of a cloth IPD.

One normalizer (get_fabric_steps) feeds every consumer (matrix sync, WO popup,
tracking, the backward planner). It reads the GENERIC fabric-process rows
(get_fabric_process_rows) — persisted `fabric_processes`, or the legacy tabs
synthesized into the same rows by the adapter — so tab and generic IPDs share one
path. Each step's shape is the Process master's declared shape
(get_process_shape): item conversion (yarn -> cloth), attribute swap (Colour /
Dia), or multi_swap (several attrs at once); the row's own mapping roles are the
fallback when a master is unmaintained. Identity steps (no transition, e.g.
in-chain Washing) are excluded from the chain and handled by the WO popup's
identity path.

Spec: docs/design/2026-07-04-fabric-chain-plan.md;
generic model: docs/superpowers/specs/2026-07-07-fabric-process-commonization-design.md
"""

import frappe
from frappe import _

from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
)


def get_fabric_steps(ipd_doc):
	"""Ordered chain steps, first -> last. Each step:
	{position, process_name, shape ("conversion"|"swap"|"multi_swap"),
	 attribute (swap attr, list of attrs for multi_swap, or None)}.

	Built from the GENERIC fabric_processes rows (get_fabric_process_rows) so one
	entry point serves BOTH persisted-generic and legacy-tab IPDs: the adapter
	synthesizes the 3 tab processes into the same rows, giving byte-identical steps
	(knitting=conversion, dyeing=Colour swap, compacting=Dia swap). Identity steps
	(no conversion/swap — e.g. in-chain Washing) carry no attribute transition and
	are excluded here; the WO popup handles them via get_identity_process_row."""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	steps = []
	for row in get_fabric_process_rows(ipd_doc):
		process_name = row.get("fabric_process")
		if not process_name:
			continue
		shape, attribute = _step_shape(row)
		if shape is None:
			continue
		steps.append({"process_name": process_name, "shape": shape, "attribute": attribute})

	for position, step in enumerate(steps):
		step["position"] = position
	return steps


def _step_shape(row):
	"""(shape, attribute) for a generic fabric-process row. Prefer the Process
	master's declared shape (the reusable template owns it — 2026-06-25 rule); fall
	back to the row's own value-mapping roles so an unmaintained master still
	resolves. Returns (None, None) for an identity step (no conversion/swap)."""
	from essdee_yrp.fabric_ipd import get_process_shape

	shape, attribute = get_process_shape(row.get("fabric_process"))
	if shape:
		return shape, attribute
	# Fallback (master metadata unfilled): a Change entry => swap; an item-changing
	# row with no Change => conversion; anything else => identity.
	changed = list(dict.fromkeys(
		m.get("attribute") for m in (row.get("value_mappings") or [])
		if m.get("role") == "Change"
	))
	if len(changed) > 1:
		return "multi_swap", changed
	if changed:
		return "swap", changed[0]
	in_item, out_item = row.get("input_item"), row.get("output_item")
	# Consume(+Introduce) rows resolve here too: differing items -> conversion;
	# a same-item Consume/Introduce row can never slip through to identity because
	# validate_consume_mappings blocks it at save time.
	if in_item and out_item and in_item != out_item:
		return "conversion", None
	return None, None


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
