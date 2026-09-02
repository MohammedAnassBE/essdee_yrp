# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Lot Fabric Program: dia-wise program quantity + the production ledger.

Two child tables per Lot fabric (cloth):
  - Lot Fabric Program:        dia + weight -> what knitting must produce
                               (user-entered; received_weight = knitting GRNs)
  - Lot Fabric Colour Program: pure LEDGER, fully server-owned — rows appear as
                               GRNs land: received_weight = dyed kgs,
                               compacted_weight = compacted kgs (user decision
                               2026-07-04: no planned "dyeing split" entry).

Tracking columns are written only by essdee_yrp.fabric_tracking — client
payloads never touch them.

Spec: apps/essdee_yrp/docs/design/2026-07-04-lot-fabric-program-design.md
"""

import frappe
from frappe import _
from frappe.utils import escape_html, flt

from essdee_yrp.fabric_ipd import FABRIC_COLOUR_ATTRIBUTE, FABRIC_DIA_ATTRIBUTE
from essdee_yrp.ipd_validations import get_ipd_attribute_values


def fetch_fabric_program_details(lot_doc):
	"""Onload payload for the FabricProgram Vue island: one entry per Lot fabric."""
	entries = []
	program_rows = lot_doc.get("lot_fabric_programs") or []
	requirement_rows = lot_doc.get("lot_fabric_requirements") or []
	ledger_rows = lot_doc.get("lot_fabric_step_ledger") or []
	for fabric in lot_doc.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc('YRP Item Production Detail', fabric.production_detail)
		entries.append({
			"cloth_item": fabric.cloth_item,
			"production_detail": fabric.production_detail,
			"dias": _ipd_dias(ipd),
			"colours": _ipd_target_colours(ipd),
			"greige_colour": get_greige_colour(ipd),
			"knitting_output_colours": get_knitting_output_colour_map(ipd),
			"fabric_routes": get_fabric_routes(ipd),
			"plan_status": fabric.get("plan_status") or "",
			"plan_built_on": str(fabric.get("plan_built_on") or ""),
			"ipd_approved": (ipd.get("approval_status") == "Approved"),
			"final_options": _final_options(ipd),
			"requirement": [
				{"dia": r.dia, "colour": r.colour, "weight": flt(r.weight)}
				for r in requirement_rows if r.cloth_item == fabric.cloth_item
			],
			"steps": _ledger_steps(ipd, fabric.cloth_item, ledger_rows),
			"program": [
				_program_row_payload(ipd, r)
				for r in program_rows if r.cloth_item == fabric.cloth_item
			],
		})
	return entries


def _program_row_payload(ipd, row):
	"""Display/persistence payload for one exact knitting route.

	The child row stores the physical output Dia/Colour plus a stable final
	reference. Resolve both sides server-side so Desk and /web never have to
	guess that a physical 18 Dia AMEL row belongs to finished 22 Dia AMEL.
	"""
	reference = row.get("reference_item_variant")
	final_attrs = {}
	if reference:
		variant = frappe.get_cached_doc('YRP Item Variant', reference)
		final_attrs = {
			value.attribute: value.attribute_value
			for value in variant.get("attributes") or []
		}
	final_dia = final_attrs.get(FABRIC_DIA_ATTRIBUTE) or row.dia
	final_colour = final_attrs.get(FABRIC_COLOUR_ATTRIBUTE) or row.get("colour")
	route = next((
		candidate for candidate in get_fabric_routes(ipd)
		if candidate["finished_dia"] == final_dia
		and candidate["finished_colour"] == final_colour
	), None)
	return {
		"dia": row.dia,
		"colour": row.get("colour") or (
			route and route["knitting_output_colour"]
		),
		"reference_item_variant": reference,
		"finished_dia": final_dia,
		"finished_colour": final_colour,
		"knitting_output_dia": (
			route and route["knitting_output_dia"]
		) or row.dia,
		"knitting_output_colour": (
			route and route["knitting_output_colour"]
		) or row.get("colour"),
		"weight": flt(row.weight),
		"received_weight": flt(row.received_weight),
	}


def _final_options(ipd):
	"""Reachable finished-cloth choices for the Requirement grid — only what the
	chain can actually produce is offered (fast-entry rule)."""
	from essdee_yrp.fabric_chain import final_combos

	dias, colours = [], []
	for combo in final_combos(ipd):
		attrs = dict(combo)
		if attrs.get(FABRIC_DIA_ATTRIBUTE):
			dias.append(attrs[FABRIC_DIA_ATTRIBUTE])
		if attrs.get(FABRIC_COLOUR_ATTRIBUTE):
			colours.append(attrs[FABRIC_COLOUR_ATTRIBUTE])
	return {
		"dias": sorted(set(dias)),
		"colours": sorted(set(colours)),
	}


def _ledger_steps(ipd, cloth_item, ledger_rows):
	"""Ordered per-step ledger sections for the island: each step's Output rows
	(planned / received / balance) + the first step's Input (yarn/procurement)."""
	from essdee_yrp.fabric_chain import get_fabric_steps

	sections = []
	for step in get_fabric_steps(ipd):
		rows = [
			{
				"side": r.side or "Output", "dia": r.dia, "colour": r.colour,
				"planned_weight": flt(r.planned_weight),
				"received_weight": flt(r.received_weight),
			}
			for r in ledger_rows
			if r.cloth_item == cloth_item and r.process_name == step["process_name"]
				and (flt(r.planned_weight) or flt(r.received_weight))
		]
		sections.append({
			"process_name": step["process_name"],
			"shape": step["shape"],
			"rows": rows,
		})
	return sections


def _ipd_dias(ipd):
	dias = [r.dia for r in ipd.get("knitting_dia_details") or [] if r.dia]
	if not dias:
		dias = get_ipd_attribute_values(ipd, FABRIC_DIA_ATTRIBUTE)
	return list(dict.fromkeys(dias))


def _ipd_target_colours(ipd):
	colours = [r.to_colour for r in ipd.get("dyeing_colour_details") or [] if r.to_colour]
	if not colours:
		colours = get_ipd_attribute_values(ipd, FABRIC_COLOUR_ATTRIBUTE)
	return list(dict.fromkeys(colours))


def get_greige_colour(ipd):
	"""The knitted (undyed) colour. Generic-aware: the distinct Colour value(s)
	flowing INTO the first Colour-swap (dyeing) step — a single value is the greige,
	several are ambiguous (None -> user picks in the popup). Works for BOTH generic
	fabric_processes IPDs and legacy tab IPDs (the adapter feeds get_fabric_steps /
	values_entering the same rows). No dyeing step -> None."""
	colours = _greige_colour_options(ipd)
	if len(colours) == 1:
		return colours[0]
	return None


def _first_colour_change_rows(ipd):
	"""Return ``(has_colour_change, rows)`` for the first Colour-changing step.

	Each row is ``{from_colour, to_colour, dia}``.  It is read from the generic
	Fabric Process mappings, so manually-authored F16 cloth IPDs and CPDs created
	by Build Cloth Program use the same source of truth.
	"""
	from essdee_yrp.fabric_ipd import get_fabric_process_rows

	for process_row in get_fabric_process_rows(ipd):
		grouped = {}
		for mapping in process_row.get("value_mappings") or []:
			grouped.setdefault(mapping.get("mapping_index"), []).append(mapping)
		has_colour_change = any(
			mapping.get("role") == "Change"
			and mapping.get("attribute") == FABRIC_COLOUR_ATTRIBUTE
			for mappings in grouped.values()
			for mapping in mappings
		)
		if not has_colour_change:
			continue

		rows = []
		for mappings in grouped.values():
			change = next((
				mapping for mapping in mappings
				if mapping.get("role") == "Change"
				and mapping.get("attribute") == FABRIC_COLOUR_ATTRIBUTE
			), None)
			if not change:
				continue
			dia = next((
				mapping.get("from_value") for mapping in mappings
				if mapping.get("role") == "Pin"
				and mapping.get("attribute") == FABRIC_DIA_ATTRIBUTE
				and mapping.get("from_value")
			), None)
			rows.append({
				"from_colour": change.get("from_value"),
				"to_colour": change.get("to_value"),
				"dia": dia,
			})
		return True, rows
	return False, []


def get_knitting_output_colour_map(ipd):
	"""``{finished_colour: knitting_output_colour}`` where unambiguous.

	The first Colour-changing process owns this relationship: its ``from`` value
	is what Knitting returns and its ``to`` value is the finished/required colour.
	When no Colour-changing process exists, a cloth is already knitted in its
	finished colour.
	"""
	exact_routes = get_fabric_routes(ipd)
	if exact_routes:
		sources = {}
		for route in exact_routes:
			sources.setdefault(route["finished_colour"], set()).add(
				route["knitting_output_colour"]
			)
		return {
			colour: next(iter(values))
			for colour, values in sources.items()
			if len(values) == 1
		}

	has_colour_change, rows = _first_colour_change_rows(ipd)
	sources = {}
	for row in rows:
		if row["from_colour"] and row["to_colour"]:
			sources.setdefault(row["to_colour"], set()).add(row["from_colour"])
	result = {
		to_colour: next(iter(from_colours))
		for to_colour, from_colours in sources.items()
		if len(from_colours) == 1
	}
	# A recipe colour with no Colour-change route is already final when it
	# leaves knitting.  This also covers an all-direct CPD with no dyeing
	# process.  Auto-built mixed CPDs persist explicit AMEL -> AMEL / GMEL ->
	# GMEL rows, but the fallback keeps manually-authored profiles concise.
	recipe_colours = {
		row.colour for row in ipd.get("colour_yarn_recipes") or []
		if row.cloth_item == ipd.item and row.colour
	}
	mapped_targets = {
		row["to_colour"] for row in rows if row["to_colour"]
	}
	for colour in recipe_colours - mapped_targets:
		result[colour] = colour
	if result or has_colour_change:
		return result
	return {
		row.colour: row.colour
		for row in ipd.get("colour_yarn_recipes") or []
		if row.cloth_item == ipd.item and row.colour
	}


def get_knitting_output_colour(ipd, finished_colour, dia=None):
	"""Resolve the colour physically received from Knitting for one route."""
	if dia:
		route = next((
			row for row in get_fabric_routes(ipd)
			if row["finished_colour"] == finished_colour
			and row["finished_dia"] == dia
		), None)
		if route:
			return route["knitting_output_colour"]
	has_colour_change, rows = _first_colour_change_rows(ipd)
	target_rows = [
		row for row in rows
		if row["to_colour"] == finished_colour
	]
	if dia:
		exact = [row for row in target_rows if row["dia"] == dia]
		wildcard = [row for row in target_rows if not row["dia"]]
		target_rows = exact or wildcard
	sources = {
		row["from_colour"] for row in target_rows if row["from_colour"]
	}
	if len(sources) == 1:
		return next(iter(sources))
	recipe_colours = {
		row.colour for row in ipd.get("colour_yarn_recipes") or []
		if row.cloth_item == ipd.item and row.colour
	}
	if not target_rows and finished_colour in recipe_colours:
		return finished_colour
	if not has_colour_change:
		return finished_colour
	# Backward compatibility for old one-greige profiles whose first swap can be
	# represented only as one global incoming colour.
	return get_greige_colour(ipd) if len(sources) == 0 else None


def get_knitting_output_dia(ipd, finished_colour, finished_dia):
	"""Physical Dia received from knitting for one exact finished route."""
	route = next((
		row for row in get_fabric_routes(ipd)
		if row["finished_colour"] == finished_colour
		and row["finished_dia"] == finished_dia
	), None)
	return route["knitting_output_dia"] if route else finished_dia


def get_fabric_routes(ipd):
	"""Serialisable exact route rows stored on a cloth IPD."""
	return [
		{
			"finished_colour": row.finished_colour,
			"finished_dia": row.finished_dia,
			"knitting_output_colour": row.knitting_output_colour,
			"knitting_output_dia": row.knitting_output_dia,
		}
		for row in ipd.get("fabric_routes") or []
		if row.finished_colour
		and row.finished_dia
		and row.knitting_output_colour
		and row.knitting_output_dia
	]


def _greige_colour_options(ipd):
	"""Distinct greige (pre-dye) Colour values the chain can knit — the colours
	entering the first Colour-swap step. Empty when the IPD has no dyeing step."""
	from essdee_yrp.fabric_chain import get_fabric_steps
	from essdee_yrp.fabric_ipd import values_entering

	dye_pos = _first_colour_swap_position(get_fabric_steps(ipd))
	if dye_pos is None:
		return []
	# dye_pos is a filtered-step index (identity steps excluded); values_entering
	# slices the FULL row list [:dye_pos]. Safe because every step before the first
	# Colour swap is a Colour no-op in the walk (identity/knitting/dia-swap all pass
	# Colour through unchanged), so the short slice yields the same seed set.
	return list(dict.fromkeys(values_entering(ipd, dye_pos, FABRIC_COLOUR_ATTRIBUTE)))


def _first_colour_swap_position(steps):
	for step in steps:
		if step["shape"] in ("swap", "multi_swap"):
			attrs = step["attribute"]
			attrs = attrs if isinstance(attrs, (list, tuple)) else [attrs]
			if FABRIC_COLOUR_ATTRIBUTE in attrs:
				return step["position"]
	return None


def validate_unique_fabric_cloths(lot_doc):
	"""Program rows are keyed by cloth_item, so one fabric row per cloth. A cloth
	with received kgs on record cannot be removed — that would orphan tracking."""
	seen = set()
	for fabric in lot_doc.get("lot_fabric_details") or []:
		if fabric.cloth_item in seen:
			frappe.throw(
				_("Cloth {0} appears twice in Fabric Details — one row per cloth.").format(fabric.cloth_item)
			)
		seen.add(fabric.cloth_item)

	if lot_doc.is_new():
		return
	tracked = frappe.get_all(
		'SD YRP Lot Fabric Program',
		filters={"parent": lot_doc.name, "parenttype": 'SD YRP Lot', "received_weight": ["!=", 0]},
		pluck="cloth_item",
	)
	tracked += frappe.get_all(
		'SD YRP Lot Fabric Colour Program',
		filters={"parent": lot_doc.name, "parenttype": 'SD YRP Lot'},
		or_filters={"received_weight": ["!=", 0], "compacted_weight": ["!=", 0]},
		pluck="cloth_item",
	)
	removed = set(tracked) - seen
	if removed:
		frappe.throw(
			_("Cannot remove fabric {0} — fabric receipts are already tracked against it.").format(
				", ".join(sorted(removed))
			)
		)


def save_fabric_program_details(lot_doc):
	"""before_validate: rebuild the PROGRAM table from the Vue island's transient
	JSON (`fabric_program_details`), carrying received_weight forward. The colour
	ledger (`lot_colour_programs`) is never client-writable — GRN tracking owns it.

	Rows the user removed but that already have received kgs are re-added with
	weight 0 — tracking data is never silently dropped."""
	raw = lot_doc.get("fabric_program_details")
	if not raw:
		return
	data = frappe.parse_json(raw) if isinstance(raw, str) else raw

	fabric_cloths = {f.cloth_item for f in lot_doc.get("lot_fabric_details") or []}
	# received_weight carry-forward reads the DB, NOT the incoming doc: the GRN
	# hook writes rows at the DB level without bumping Lot.modified, so a form
	# that was open across a receipt would otherwise save stale (or missing) rows.
	# The per-lot lock serializes this rebuild against a GRN submit in flight.
	if not lot_doc.is_new():
		frappe.db.get_value('SD YRP Lot', lot_doc.name, "name", for_update=True)
	prev_program = _db_received(lot_doc.name, 'SD YRP Lot Fabric Program')

	attr_cache = {}
	program_rows = []
	seen_program = set()

	for entry in data or []:
		cloth = entry.get("cloth_item")
		if cloth not in fabric_cloths:
			# Fabric row removed after the island loaded — its program dies with it
			# (received-bearing resurrection below is likewise gated on fabric_cloths).
			continue

		for row in entry.get("program") or []:
			dia = row.get("dia")
			colour = row.get("colour") or None
			reference_item_variant = row.get("reference_item_variant") or None
			weight = flt(row.get("weight"))
			if not dia:
				continue
			if weight < 0:
				frappe.throw(_("Fabric program: negative weight for {0} / {1}.").format(cloth, dia))
			_validate_attribute_value(attr_cache, dia, FABRIC_DIA_ATTRIBUTE)
			if not reference_item_variant and colour:
				from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant
				reference_item_variant = get_or_create_variant(
					cloth,
					{FABRIC_DIA_ATTRIBUTE: dia, FABRIC_COLOUR_ATTRIBUTE: colour},
				)
			key = (cloth, dia, reference_item_variant or "")
			if key in seen_program:
				frappe.throw(_("Fabric program: duplicate dia {0} for {1}.").format(dia, cloth))
			seen_program.add(key)
			received = prev_program.get(key, 0)
			if weight <= 0 and not received:
				continue
			program_rows.append({
				"cloth_item": cloth, "dia": dia, "colour": colour,
				"reference_item_variant": reference_item_variant,
				"weight": weight, "received_weight": received,
			})

	# Tracking survives row removal: resurrect received-bearing rows at weight 0.
	for (cloth, dia, reference_item_variant), received in prev_program.items():
		if (
			received
			and (cloth, dia, reference_item_variant) not in seen_program
			and cloth in fabric_cloths
		):
			colour = None
			if reference_item_variant:
				ref = frappe.get_cached_doc('YRP Item Variant', reference_item_variant)
				colour = next((
					a.attribute_value for a in ref.get("attributes") or []
					if a.attribute == FABRIC_COLOUR_ATTRIBUTE
				), None)
			program_rows.append({
				"cloth_item": cloth, "dia": dia, "colour": colour,
				"reference_item_variant": reference_item_variant or None,
				"weight": 0, "received_weight": received,
			})

	lot_doc.set("lot_fabric_programs", program_rows)
	_drop_orphan_ledger_rows(lot_doc, fabric_cloths)
	_warn_program_below_ordered(lot_doc)


def save_fabric_requirement_details(lot_doc):
	"""before_validate: rebuild `lot_fabric_requirements` from the island's
	transient JSON (`fabric_requirement_details`). Unreachable combos hard-block
	(data error, not a balance). When the IPD is Approved, the plan rebuilds in
	the same save; otherwise the fabric row is marked Pending Approval."""
	raw = lot_doc.get("fabric_requirement_details")
	if raw is None or raw == "":
		return
	data = frappe.parse_json(raw) if isinstance(raw, str) else raw

	from essdee_yrp.fabric_chain import final_combos

	fabric_by_cloth = {
		f.cloth_item: f for f in lot_doc.get("lot_fabric_details") or [] if f.production_detail
	}
	attr_cache = {}
	rows, seen, unreachable = [], set(), []

	for entry in data or []:
		cloth = entry.get("cloth_item")
		fabric = fabric_by_cloth.get(cloth)
		if not fabric:
			continue
		ipd = frappe.get_cached_doc('YRP Item Production Detail', fabric.production_detail)
		reachable = final_combos(ipd)
		for row in entry.get("requirement") or []:
			dia = row.get("dia")
			colour = row.get("colour") or None
			weight = flt(row.get("weight"))
			if not dia or weight <= 0:
				continue
			if weight < 0:
				frappe.throw(_("Requirement: negative weight for {0} / {1}.").format(cloth, dia))
			_validate_attribute_value(attr_cache, dia, FABRIC_DIA_ATTRIBUTE)
			if colour:
				_validate_attribute_value(attr_cache, colour, FABRIC_COLOUR_ATTRIBUTE)
			key = (cloth, dia, colour or "")
			if key in seen:
				frappe.throw(_("Requirement: duplicate row {0} / {1} / {2}.").format(
					cloth, dia, colour or ""))
			seen.add(key)
			attrs = {FABRIC_DIA_ATTRIBUTE: dia}
			if colour:
				attrs[FABRIC_COLOUR_ATTRIBUTE] = colour
			if reachable and frozenset(attrs.items()) not in reachable:
				unreachable.append(f"{escape_html(cloth)}: "
					f"{escape_html(colour or '')} / {escape_html(dia)}")
				continue
			rows.append({
				"cloth_item": cloth, "dia": dia, "colour": colour, "weight": weight,
			})

	if unreachable:
		frappe.throw(
			_("No chain path produces:") + "<br>" + "<br>".join(unreachable[:8])
			+ "<br>" + _("Add mapping rows on the cloth IPD or correct the requirement."),
		)

	existing = [
		{"cloth_item": r.cloth_item, "dia": r.dia, "colour": r.colour or None,
			"weight": flt(r.weight)}
		for r in lot_doc.get("lot_fabric_requirements") or []
	]
	lot_doc.set("lot_fabric_requirements", rows)
	# rebuild only when the requirement actually changed (or a plan is missing/
	# stale) — an unrelated Lot save must never re-run or re-warn the solver
	changed = sorted(existing, key=str) != sorted(
		[{**r, "weight": flt(r["weight"])} for r in rows], key=str)
	needs_build = any(
		(f.get("plan_status") or "") in ("", "Stale", "Pending Approval")
		for f in lot_doc.get("lot_fabric_details") or []
	) and bool(rows)
	lot_doc.flags.rebuild_fabric_plans = (
		changed or needs_build or lot_doc.flags.get("force_fabric_plan_rebuild")
	)


def rebuild_plans_after_save(lot_doc):
	"""on_update companion for save_fabric_requirement_details: fabric rows now
	have names, ledger writes can attach. Approved IPD -> build; else Pending."""
	if not lot_doc.flags.get("rebuild_fabric_plans"):
		return
	from essdee_yrp.fabric_plan import build_fabric_plan

	for fabric in lot_doc.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		approved = frappe.db.get_value(
			'YRP Item Production Detail', fabric.production_detail, "approval_status") == "Approved"
		if approved:
			# never hard-block the Lot save on solver trouble — reachability was
			# already gated at requirement entry; residual failures surface as
			# plan_status Error on the fabric row
			build_fabric_plan(lot_doc, fabric, raise_on_unreachable=False)
		else:
			has_requirement = any(
				r.cloth_item == fabric.cloth_item
				for r in lot_doc.get("lot_fabric_requirements") or []
			)
			frappe.db.set_value('SD YRP Lot Fabric Detail', fabric.name, "plan_status",
				"Pending Approval" if has_requirement else "", update_modified=False)

	# the plan/pre-seed wrote rows at the DB level — refresh the in-memory doc so
	# the save RESPONSE carries them (else the open form's next save deletes them)
	refresh_server_owned_tables(lot_doc)
	program_rows = frappe.get_all(
		'SD YRP Lot Fabric Program',
		filters={"parent": lot_doc.name, "parenttype": 'SD YRP Lot'},
		fields=["*"],
		order_by="idx asc, creation asc",
	)
	lot_doc.set("lot_fabric_programs", [])
	for r in program_rows:
		row = lot_doc.append("lot_fabric_programs", {})
		row.update(r)


SERVER_OWNED_TABLES = (
	("lot_fabric_step_ledger", 'SD YRP Lot Fabric Step Ledger'),
	("lot_colour_programs", 'SD YRP Lot Fabric Colour Program'),  # legacy, frozen
)


def refresh_server_owned_tables(lot_doc):
	"""Reload the server-owned child tables from the DB (before_validate).

	Frappe's child-table sync DELETES rows missing from the incoming doc — and
	GRN tracking / the plan builder insert ledger rows at the DB level without
	bumping Lot.modified, so a form opened before a receipt would silently
	revert them on save. The client can never write these tables, so the DB is
	always the truth."""
	if lot_doc.is_new():
		return
	for parentfield, doctype in SERVER_OWNED_TABLES:
		rows = frappe.get_all(
			doctype,
			filters={"parent": lot_doc.name, "parenttype": 'SD YRP Lot'},
			fields=["*"],
			order_by="idx asc, creation asc",
		)
		lot_doc.set(parentfield, [])
		for r in rows:
			row = lot_doc.append(parentfield, {})
			row.update(r)


def _drop_orphan_ledger_rows(lot_doc, fabric_cloths):
	"""Ledger rows of a removed cloth with NO receipts are dead — delete them.
	(Receipt-bearing rows can't get here: validate_unique_fabric_cloths throws.)"""
	if lot_doc.is_new():
		return
	orphans = [
		r for r in lot_doc.get("lot_colour_programs") or []
		if r.cloth_item not in fabric_cloths
			and not flt(r.received_weight) and not flt(r.get("compacted_weight"))
	]
	for row in orphans:
		frappe.delete_doc('SD YRP Lot Fabric Colour Program', row.name,
			ignore_permissions=True, force=True)
	if orphans:
		lot_doc.set("lot_colour_programs", [
			r for r in lot_doc.get("lot_colour_programs") or []
			if r.cloth_item in fabric_cloths
		])


def _db_received(lot_name, child_doctype):
	"""Stored received_weight keyed by (cloth, dia[, colour]) — fresh from the DB."""
	if not lot_name or not frappe.db.exists('SD YRP Lot', lot_name):
		return {}
	fields = ["cloth_item", "dia", "received_weight"]
	if child_doctype == 'SD YRP Lot Fabric Colour Program':
		fields.insert(2, "colour")
	else:
		fields.insert(2, "reference_item_variant")
	result = {}
	for r in frappe.get_all(
		child_doctype,
		filters={"parent": lot_name, "parenttype": 'SD YRP Lot'},
		fields=fields,
	):
		key = (
			(r.cloth_item, r.dia, r.get("reference_item_variant") or "")
			if child_doctype == 'SD YRP Lot Fabric Program'
			else (r.cloth_item, r.dia, r.colour)
		)
		result[key] = flt(r.received_weight)
	return result


def _validate_attribute_value(cache, value, attribute):
	if value not in cache:
		cache[value] = frappe.db.get_value('YRP Item Attribute Value', value, "attribute_name")
	if cache[value] != attribute:
		frappe.throw(_("{0} is not a value of the {1} attribute.").format(value, attribute))


def _warn_program_below_ordered(lot_doc):
	"""Non-blocking: shrinking the program below what knitting WOs already ordered
	strands the over-order — surface it, don't block."""
	if lot_doc.is_new():
		return
	from essdee_yrp.fabric_tracking import get_produced_by_reference

	ipd_by_cloth = {
		f.cloth_item: f.production_detail
		for f in lot_doc.get("lot_fabric_details") or [] if f.production_detail
	}
	warnings = []
	for cloth, ipd_name in ipd_by_cloth.items():
		ipd = frappe.get_cached_doc('YRP Item Production Detail', ipd_name)
		if not ipd.get("knitting_process"):
			continue
		ordered = get_produced_by_reference(lot_doc.name, ipd.knitting_process, cloth)
		if not ordered:
			continue
		for row in lot_doc.get("lot_fabric_programs") or []:
			if row.cloth_item != cloth:
				continue
			already = flt(ordered.get(row.get("reference_item_variant") or ""))
			if already and flt(row.weight) < already - 0.001:
				warnings.append(
					_("{0} · {1}: program {2} kg is below the {3} kg already on knitting Work Orders").format(
						escape_html(cloth), escape_html(row.dia), flt(row.weight), already)
				)
	if warnings:
		frappe.msgprint(
			"<br>".join(warnings),
			title=_("Program below ordered quantity"),
			indicator="orange",
		)
