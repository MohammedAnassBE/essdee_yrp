# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt

from essdee_yrp.ipd_validations import is_cloth_ipd

FABRIC_DIA_ATTRIBUTE = "Dia"
FABRIC_COLOUR_ATTRIBUTE = "Colour"

# (ipd process-link fieldname, kind)
FABRIC_PROCESS_FIELDS = (
	("knitting_process", "knitting"),
	("dyeing_process", "dyeing"),
	("compacting_process", "compacting"),
)


# The transformation SHAPE each fabric tab expects from its Process master
# (2026-06-25 design: the Process owns the reusable shape, the IPD supplies
# the values). conversion -> Process.is_item_conversion; swap -> the attribute
# in Process.value_change_attributes.
FABRIC_KIND_SHAPES = {
	"knitting": {"is_item_conversion": 1},
	"dyeing": {"swap_attribute": FABRIC_COLOUR_ATTRIBUTE},
	"compacting": {"swap_attribute": FABRIC_DIA_ATTRIBUTE},
}


def get_fabric_process_kind(ipd_doc, process_name):
	"""Which fabric process (knitting/dyeing/compacting) `process_name` is on this IPD, or None."""
	if not process_name:
		return None
	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		if ipd_doc.get(fieldname) == process_name:
			return kind
	return None


def get_process_shape(process_name):
	"""The transformation shape the Process MASTER declares:
	("conversion", None) | ("swap", <attribute>) | ("multi_swap", [attrs]) |
	(None, None) when nothing is maintained (identity, or metadata unfilled).
	multi_swap = one process changing SEVERAL attributes at once (Dye-Compact:
	colour AND dia change in the same trip)."""
	if not process_name:
		return (None, None)
	doc = frappe.get_cached_doc("Process", process_name)
	if doc.get("is_item_conversion"):
		return ("conversion", None)
	swaps = [r.attribute for r in doc.get("value_change_attributes") or []]
	if len(swaps) > 1:
		return ("multi_swap", swaps)
	if swaps:
		return ("swap", swaps[0])
	return (None, None)


@frappe.whitelist()
def get_process_transform(process):
	"""Client helper for the generic Fabric Processes entry table: read the
	transformation SHAPE the Process MASTER declares and return a display-ready
	payload the IPD form uses to show "what changes" per process row.

	The shape is the single source of truth (get_process_shape) — one of:
	item conversion (item A -> B), attribute swap (a value flips, possibly
	several at once), or identity (nothing maintained). Mirrors the 3-shape
	model in conventions (2026-07-07)."""
	shape, attribute = get_process_shape(process)
	if shape == "conversion":
		return {
			"shape": "conversion",
			"label": frappe._("Item Conversion"),
			"is_item_conversion": True,
			"change_attributes": [],
		}
	if shape == "swap":
		return {
			"shape": "swap",
			"label": frappe._("Attribute Swap"),
			"is_item_conversion": False,
			"change_attributes": [attribute],
		}
	if shape == "multi_swap":
		return {
			"shape": "multi_swap",
			"label": frappe._("Attribute Swap"),
			"is_item_conversion": False,
			"change_attributes": list(attribute or []),
		}
	return {
		"shape": "identity",
		"label": frappe._("Identity"),
		"is_item_conversion": False,
		"change_attributes": [],
	}


@frappe.whitelist()
def get_item_attributes(item):
	"""Client helper: the attribute names on an Item's own `attributes` child
	table — feeds the Fabric Processes editor's Consume dropdown (the consumed
	attribute lives on the INPUT item, which need not share the IPD item's
	attribute names)."""
	# [] for missing item AND for no-permission alike — a permission-less caller
	# must not be able to distinguish existing from non-existing Item names.
	if not item or not frappe.db.exists("Item", item):
		return []
	if not frappe.has_permission("Item", doc=item, ptype="read"):
		return []
	doc = frappe.get_cached_doc("Item", item)
	return [a.attribute for a in (doc.get("attributes") or [])]


def validate_fabric_process_shapes(doc):
	"""Non-blocking: each fabric tab's process should DECLARE the matching shape
	on its Process master — the master is the reusable template, the IPD only
	supplies values. Warns (never blocks) so unmaintained masters keep working."""
	problems = []
	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		process_name = doc.get(fieldname)
		if not process_name:
			continue
		shape, attribute = get_process_shape(process_name)
		expected = FABRIC_KIND_SHAPES[kind]
		if expected.get("is_item_conversion") and shape != "conversion":
			problems.append(frappe._(
				"{0}: tick Item Conversion on the Process master (yarn → cloth)."
			).format(frappe.utils.escape_html(process_name)))
		elif expected.get("swap_attribute") and (shape, attribute) != ("swap", expected["swap_attribute"]):
			problems.append(frappe._(
				"{0}: add {1} to Value Change Attributes on the Process master."
			).format(frappe.utils.escape_html(process_name), expected["swap_attribute"]))
	if problems:
		frappe.msgprint(
			"<br>".join(problems),
			title=frappe._("Process master metadata incomplete"),
			indicator="orange",
		)


def validate_consume_mappings(doc):
	"""Consume-role shape rules over the generic fabric rows (called from
	validate_cloth_ipd — the sibling tables carry no other server-side
	role/from/to checks). Consume = INPUT-side-only stamp, the exact mirror of
	Introduce:
	  * from_value is REQUIRED — Consume always names the concrete consumed
	    value, it never wildcards;
	  * one mapping group may not both Consume and Change the SAME attribute
	    (ambiguous input-side stamp);
	  * Consume/Introduce entries need DIFFERING input/output items — the same
	    item cannot gain or lose attributes (use Change/Pin). A BLANK input_item
	    stays allowed (legacy knitting with blank yarn)."""
	for row in get_fabric_process_rows(doc):
		process = frappe.utils.escape_html(row.get("fabric_process") or "")
		in_item, out_item = row.get("input_item"), row.get("output_item")
		same_item = bool(in_item and out_item and in_item == out_item)
		for mapping_index, entries in _group_by_mapping_index(_entries(row)):
			consumed, changed = set(), set()
			for entry in entries:
				role = entry.get("role")
				attribute = frappe.utils.escape_html(entry.get("attribute") or "")
				if same_item and role in ("Consume", "Introduce"):
					frappe.throw(frappe._(
						"Fabric process {0}: {1} entries need differing input and output "
						"items — the same item ({2}) cannot gain or lose an attribute. "
						"Use Change or Pin instead."
					).format(process, role, frappe.utils.escape_html(in_item or "")))
				if role == "Consume":
					# A blank input_item normalizes to the IPD item at build time —
					# which is exactly the same-item gain/loss case above. Only the
					# legacy knitting Introduce may leave the input blank.
					if not in_item:
						frappe.throw(frappe._(
							"Fabric process {0}: Consume entries need an explicit Input "
							"Item — a blank input falls back to the IPD's own item, which "
							"cannot lose an attribute."
						).format(process))
					if not entry.get("from_value"):
						frappe.throw(frappe._(
							"Fabric process {0}: the Consume entry for attribute {1} needs a "
							"From Value — Consume always names the concrete consumed value "
							"(no wildcards)."
						).format(process, attribute))
					if entry.get("to_value"):
						frappe.throw(frappe._(
							"Fabric process {0}: the Consume entry for attribute {1} must "
							"leave To Value empty — Consume stamps the input side only "
							"(pair it with an Introduce entry to produce something)."
						).format(process, attribute))
					consumed.add(attribute)
				elif role == "Change":
					changed.add(attribute)
			for attribute in sorted(consumed & changed):
				frappe.throw(frappe._(
					"Fabric process {0}: mapping group {1} both Consumes and Changes "
					"attribute {2} — ambiguous. Use one role per attribute in a group."
				).format(process, mapping_index, attribute))


def get_identity_process_row(ipd_doc, process_name):
	"""A cloth process that neither converts the item nor swaps an attribute treats
	its item 1:1 — deliverable = receivable, no matrix (e.g. in-chain Washing).

	Two sources, both cloth-IPD-only (garment IPDs also carry ipd_processes rows —
	stitching etc. — and must never enter the fabric path via a mis-pointed Lot
	fabric row):
	  * legacy tab IPDs: a row on `ipd_processes` (carries its own process_item);
	  * generic IPDs: an identity-shaped row on `fabric_processes` (process_item is
	    absent, so the popup treats the cloth as the treated item).
	Returns None for conversion/swap processes — those are resolved by
	get_fabric_step BEFORE this is consulted."""
	if not process_name or get_fabric_process_kind(ipd_doc, process_name):
		return None
	if not is_cloth_ipd(ipd_doc):
		return None
	for row in ipd_doc.get("ipd_processes") or []:
		if row.process_name == process_name:
			return row
	for row in get_fabric_process_rows(ipd_doc):
		if row.get("fabric_process") != process_name:
			continue
		shape, _attribute = get_process_shape(process_name)
		has_transition = any(
			m.get("role") in ("Change", "Introduce", "Consume")
			for m in (row.get("value_mappings") or [])
		)
		# Agree with fabric_chain._step_shape: a mapping-less row that CHANGES the
		# item (input != output) is a conversion, not identity — never treat it 1:1.
		in_item, out_item = row.get("input_item"), row.get("output_item")
		is_item_conversion = in_item and out_item and in_item != out_item
		if not shape and not has_transition and not is_item_conversion:
			return row
	return None


def ensure_cloth_item_attributes(doc, method=None):
	"""Cloth IPDs must list every attribute their fabric tabs use in
	`item_attributes` — base IPDProcessMatrix.validate_attributes_belong_to_ipd
	rejects matrix attributes missing from that table (the garment UI copies
	them via client JS; cloth mode ensures them server-side). Hooked on
	before_validate so the rows persist with the save."""
	if not is_cloth_ipd(doc):
		return
	needed = []
	if doc.get("knitting_process") or doc.get("compacting_process"):
		needed.append(FABRIC_DIA_ATTRIBUTE)
	if doc.get("dyeing_process"):
		needed.append(FABRIC_COLOUR_ATTRIBUTE)
	# Dia-wise dyeing rows reference Dia; colour-wise compacting rows reference Colour.
	if doc.get("dia_wise_colour_change") or any(row.get("dia") for row in doc.get("dyeing_colour_details") or []):
		needed.append(FABRIC_DIA_ATTRIBUTE)
	if doc.get("colour_wise_dia_change") or any(
		row.get("colour") for row in doc.get("compacting_dia_details") or []
	):
		needed.append(FABRIC_COLOUR_ATTRIBUTE)
	have = {row.attribute for row in doc.get("item_attributes") or []}
	for attribute in needed:
		if attribute not in have:
			doc.append("item_attributes", {"attribute": attribute})
			have.add(attribute)


# ---------------------------------------------------------------------------
# Generic fabric-process model (2026-07-07 commonization).
#
# TWO sibling tables on the IPD describe ANY fabric step as CONFIGURATION:
#   `fabric_processes`       -> child `IPD Fabric Process`      (one row per step)
#   `fabric_value_mappings`  -> child `IPD Fabric Value Mapping`(the from->to /
#                               introduce / pin entries, each keyed to its step
#                               by `sequence`).
# They are SIBLINGS, not parent/grandchild: Frappe's ORM does not persist a
# child-of-child table, so nesting the mappings under IPD Fabric Process silently
# saved 0 rows and wiped the matrices on re-save. Keying the mappings to their
# step by `sequence` gives the same per-step grouping while persisting natively.
# The 3 legacy tabs are still read through an in-memory adapter so today's IPDs
# build the SAME matrices before any row is persisted. See spec
# docs/superpowers/specs/2026-07-07-fabric-process-commonization-design.md.
# ---------------------------------------------------------------------------


def get_fabric_process_rows(doc):
	"""The ordered generic fabric-process rows to build/read from.

	Prefers the persisted `fabric_processes` table when populated (re-attaching
	each step's mappings from the sibling `fabric_value_mappings` table by
	`sequence`); otherwise synthesizes the equivalent rows IN MEMORY from the
	legacy knitting/dyeing/compacting tabs (the adapter, spec §5). Ordered by
	`sequence` so every consumer sees the chain first -> last. Both paths return
	the SAME row shape (a `value_mappings` list per row) so tab IPDs and persisted
	IPDs behave identically downstream."""
	rows = doc.get("fabric_processes")
	if rows:
		rows = _attach_persisted_mappings(doc, rows)
	else:
		rows = synthesize_fabric_processes_from_tabs(doc)
	return sorted(rows, key=lambda r: flt(r.get("sequence")))


def _attach_persisted_mappings(doc, process_rows):
	"""Rebuild the in-memory generic rows from the PERSISTED sibling tables.

	Each persisted `IPD Fabric Process` row gets its `value_mappings` list back by
	matching the IPD's own `fabric_value_mappings` rows on `sequence`. The result
	is shaped exactly like the adapter's synthesized rows (frappe._dict with a
	`value_mappings` list), so build_fabric_matrix / values_entering are UNCHANGED
	— only the source of the mappings differs."""
	by_seq = {}
	for m in doc.get("fabric_value_mappings") or []:
		by_seq.setdefault(flt(m.get("sequence")), []).append(m)
	rows = []
	for row in process_rows:
		seq = flt(row.get("sequence"))
		# Stable sort by mapping_index keeps each group's entries contiguous while
		# preserving the user's intra-group order (multi_swap group_name / side
		# value stamp order both depend on it).
		step_maps = sorted(by_seq.get(seq, []), key=lambda m: flt(m.get("mapping_index")))
		mappings = [frappe._dict({
			"mapping_index": m.get("mapping_index"),
			"attribute": m.get("attribute"),
			"role": m.get("role"),
			"from_value": m.get("from_value") or None,
			"to_value": m.get("to_value") or None,
		}) for m in step_maps]
		rows.append(frappe._dict({
			"sequence": row.get("sequence"),
			"fabric_process": row.get("fabric_process"),
			"input_item": row.get("input_item") or None,
			"output_item": row.get("output_item") or None,
			"quantity_ratio": row.get("quantity_ratio"),
			"value_mappings": mappings,
		}))
	return rows


def synthesize_fabric_processes_from_tabs(doc):
	"""In-memory generic view of the 3 legacy fabric tabs (adapter + migration
	body, spec §5). Each returned row is a frappe._dict shaped like an
	`IPD Fabric Process` (with a `value_mappings` list of `IPD Fabric Value
	Mapping`-shaped _dicts). Behavior-preserving: the matrices these rows build
	are field-for-field identical to the 3 hardcoded builders.

	  Knitting   -> conversion that INTRODUCES Dia (one row per knitting dia).
	  Dyeing     -> Colour CHANGE + Dia PIN (blank dia = wildcard Pin).
	  Compacting -> Dia CHANGE + Colour PIN (blank colour = wildcard Pin)."""
	rows = []

	if doc.get("knitting_process"):
		mappings = []
		for idx, row in enumerate(doc.get("knitting_dia_details") or []):
			mappings.append(frappe._dict({
				"mapping_index": idx,
				"attribute": FABRIC_DIA_ATTRIBUTE,
				"role": "Introduce",
				"from_value": None,
				"to_value": row.get("dia"),
			}))
		rows.append(frappe._dict({
			"sequence": 10,
			"fabric_process": doc.knitting_process,
			"input_item": doc.get("yarn_item"),
			"output_item": doc.item,
			"quantity_ratio": flt(doc.get("cloth_per_kg_yarn")) or 1,
			"value_mappings": mappings,
		}))

	if doc.get("dyeing_process"):
		mappings = []
		for idx, row in enumerate(doc.get("dyeing_colour_details") or []):
			mappings.append(frappe._dict({
				"mapping_index": idx,
				"attribute": FABRIC_COLOUR_ATTRIBUTE,
				"role": "Change",
				"from_value": row.get("from_colour"),
				"to_value": row.get("to_colour"),
			}))
			# CRITIQUE FIX (b): ALWAYS emit the Dia pin, even when blank. A blank
			# from_value marks a WILDCARD pin that build_fabric_matrix expands into
			# one group per derived dia — reproducing the old wildcard-row
			# expansion. Omitting it would collapse the swap into a single
			# dia-less group and lose the per-dia matrices.
			dia = row.get("dia") or None
			mappings.append(frappe._dict({
				"mapping_index": idx,
				"attribute": FABRIC_DIA_ATTRIBUTE,
				"role": "Pin",
				"from_value": dia,
				"to_value": dia,
			}))
		rows.append(frappe._dict({
			"sequence": 20,
			"fabric_process": doc.dyeing_process,
			"input_item": doc.item,
			"output_item": doc.item,
			"quantity_ratio": 1,
			"value_mappings": mappings,
		}))

	if doc.get("compacting_process"):
		mappings = []
		for idx, row in enumerate(doc.get("compacting_dia_details") or []):
			mappings.append(frappe._dict({
				"mapping_index": idx,
				"attribute": FABRIC_DIA_ATTRIBUTE,
				"role": "Change",
				"from_value": row.get("from_dia"),
				"to_value": row.get("to_dia"),
			}))
			# CRITIQUE FIX (b): wildcard Colour pin (blank colour) — see dyeing.
			colour = row.get("colour") or None
			mappings.append(frappe._dict({
				"mapping_index": idx,
				"attribute": FABRIC_COLOUR_ATTRIBUTE,
				"role": "Pin",
				"from_value": colour,
				"to_value": colour,
			}))
		rows.append(frappe._dict({
			"sequence": 30,
			"fabric_process": doc.compacting_process,
			"input_item": doc.item,
			"output_item": doc.item,
			"quantity_ratio": 1,
			"value_mappings": mappings,
		}))

	return rows


def values_entering(doc, position, attribute):
	"""Distinct values of `attribute` flowing INTO the chain step at index
	`position`, walked forward over the generic fabric_processes rows. Drives
	wildcard Pin expansion in build_fabric_matrix (the generalized derive).

	CRITIQUE FIX (a): the SEED is keyed on the PRODUCING step per attribute — the
	first row (chain order) that Introduces or Changes the attribute (Colour <-
	the dyeing step's from-values, Dia <- the knitting step's introduced dias) —
	NOT literally step 0. Seeding from step 0 would leave Colour unseeded on a
	knit->dye chain and fall back to the IPD's FULL Colour mapping, over-reporting
	colours. Falls back to the IPD's attribute-mapping values when no step
	produces the attribute (bought-greige cloth)."""
	from essdee_yrp.ipd_validations import get_ipd_attribute_values

	rows = get_fabric_process_rows(doc)
	values = _seed_entering_values(rows, attribute)
	if not values:
		values = get_ipd_attribute_values(doc, attribute)
	values = list(dict.fromkeys(value for value in values if value))

	for row in rows[:position]:
		swaps = _swap_rows(row, attribute)
		if not swaps:
			continue
		next_values = []
		for value in values:
			matched = [m for m in swaps if m["from_value"] == value]
			if not matched:
				next_values.append(value)
				continue
			next_values.extend(m["to_value"] for m in matched if m["to_value"])
			# A value mapped ONLY by pinned rows still passes through unchanged at
			# every other pin, so it stays alive downstream (mirrors the classic
			# fabric_chain.values_entering rule).
			if all(m["pin_value"] for m in matched):
				next_values.append(value)
		values = list(dict.fromkeys(next_values))
	return values


def _entries(row):
	return row.get("value_mappings") or []


def _group_by_mapping_index(mappings):
	"""Ordered [(mapping_index, [entries])] preserving first-seen index order."""
	groups = {}
	order = []
	for entry in mappings or []:
		mapping_index = entry.get("mapping_index")
		if mapping_index not in groups:
			groups[mapping_index] = []
			order.append(mapping_index)
		groups[mapping_index].append(entry)
	return [(mapping_index, groups[mapping_index]) for mapping_index in order]


def _seed_entering_values(rows, attribute):
	"""The values `attribute` takes as PRODUCED by its producing step — the first
	row (chain order) that Introduces it (-> its introduced to-values) or Changes
	it (-> its from-values). Empty when no step produces it."""
	for row in rows:
		introduced = [m.get("to_value") for m in _entries(row)
			if m.get("role") == "Introduce" and m.get("attribute") == attribute and m.get("to_value")]
		if introduced:
			return introduced
		changed_from = [m.get("from_value") for m in _entries(row)
			if m.get("role") == "Change" and m.get("attribute") == attribute and m.get("from_value")]
		if changed_from:
			return changed_from
	return []


def _swap_rows(row, attribute):
	"""The {pin_value, from_value, to_value} triples of a step's Change entries
	for `attribute` (one per mapping_index group that changes it), carrying the
	group's pinned value for the passthrough rule."""
	swaps = []
	for _idx, entries in _group_by_mapping_index(_entries(row)):
		change = next((e for e in entries
			if e.get("role") == "Change" and e.get("attribute") == attribute), None)
		if not change:
			continue
		pin = next((e.get("from_value") for e in entries
			if e.get("role") == "Pin" and e.get("from_value")), None)
		swaps.append({
			"pin_value": pin,
			"from_value": change.get("from_value"),
			"to_value": change.get("to_value"),
		})
	return swaps


def sync_fabric_process_matrices(doc, method=None):
	"""Regenerate the IPD Process Matrix docs for a cloth IPD's fabric processes.

	Idempotent: every save wipes ALL of the IPD's matrices and rebuilds them from
	the generic fabric_processes rows (persisted, or synthesized from the legacy
	tabs by the adapter). Matrices stay draft — the fabric WO calculation owns how
	they are read. Never hand-authored (standing 2026-06-25 rule).
	"""
	if not is_cloth_ipd(doc):
		return

	uom = frappe.db.get_value("Item", doc.item, "default_unit_of_measure")

	# Matrices are NEVER hand-authored (2026-06-25 rule), so wiping every
	# matrix of this IPD is safe and also clears orphans left behind when a
	# process is changed or removed.
	_delete_all_matrices(doc.name)

	for row in get_fabric_process_rows(doc):
		matrix = build_fabric_matrix(doc, row, uom)
		if matrix:
			matrix.insert(ignore_permissions=True)


def _delete_all_matrices(ipd_name):
	for name in frappe.get_all("IPD Process Matrix", filters={"ipd": ipd_name}, pluck="name"):
		frappe.delete_doc("IPD Process Matrix", name, force=1, ignore_permissions=True)


def _new_matrix(doc, process):
	return frappe.get_doc({
		"doctype": "IPD Process Matrix",
		"ipd": doc.name,
		"process_name": process,
		"output_item": doc.item,
	})


def build_fabric_matrix(doc, row, uom):
	"""Build the ONE draft IPD Process Matrix for a generic fabric-process row —
	the single builder that replaces _build_knitting/_dyeing/_compacting/
	_value_swap (spec §2). Returns None when the row carries no value mappings.

	Shape-agnostic: Change = value swap (attr on both sides, from->to); Introduce
	= new attribute (output side only — keeps a conversion's input attr-less);
	Pin = passthrough (same value both sides, blank from = wildcard expanded into
	one group per derived value); Consume = consumed attribute (input side only,
	from_value — the exact mirror of Introduce; never wildcards). Consume pairs
	with Introduce entries in the SAME mapping group to convert between items
	whose attribute NAMES differ (the group IS the correspondence: Consume stamps
	the input combo, Introduce the output combo), or drops an attribute outright
	when nothing re-introduces it. For the adapter's synthesized rows the emitted
	combinations & combination_attributes are field-for-field identical to the 3
	old builders."""
	entries = _entries(row)
	if not entries:
		return None

	input_item = row.get("input_item")
	output_item = row.get("output_item") or doc.item
	# input uom = the consumed item's uom (yarn for knitting); output uom = the
	# IPD item's uom (= `uom`). Blank input_item -> the IPD item.
	input_uom = frappe.db.get_value(
		"Item", input_item, "default_unit_of_measure") if input_item else None
	input_uom = input_uom or uom
	output_uom = uom
	output_qty = flt(row.get("quantity_ratio")) or 1

	position = _row_position(doc, row)
	groups = _group_by_mapping_index(entries)
	groups = _add_carry_pins(doc, row, groups)
	expanded = _expand_mapping_indexes(doc, position, groups)

	matrix = _new_matrix(doc, row.get("fabric_process"))
	matrix.output_item = output_item
	# Only stamp input_item when the row carries one — a conversion with a blank
	# input leaves it unset so the engine falls back to the IPD item (old
	# knitting-with-blank-yarn behavior).
	if input_item:
		matrix.input_item = input_item

	input_attributes, output_attributes = _attribute_sets(expanded)
	for attribute in input_attributes:
		matrix.append("input_attributes", {"attribute": attribute})
	for attribute in output_attributes:
		matrix.append("output_attributes", {"attribute": attribute})

	for group_index, group in enumerate(expanded):
		group_name = _group_name(group)
		matrix.append("combinations", {
			"group_index": group_index, "group_name": group_name, "side": "Input",
			"combo_index": 0, "quantity": 1, "uom": input_uom, "wastage_pct": 0,
		})
		matrix.append("combinations", {
			"group_index": group_index, "group_name": group_name, "side": "Output",
			"combo_index": 0, "quantity": output_qty, "uom": output_uom, "wastage_pct": 0,
		})
		for attribute, value in _side_values(group, "Input"):
			matrix.append("combination_attributes", {
				"group_index": group_index, "side": "Input", "combo_index": 0,
				"attribute": attribute, "attribute_value": value,
			})
		for attribute, value in _side_values(group, "Output"):
			matrix.append("combination_attributes", {
				"group_index": group_index, "side": "Output", "combo_index": 0,
				"attribute": attribute, "attribute_value": value,
			})
	return matrix


def _add_carry_pins(doc, row, groups):
	"""SAME-ITEM (swap) rows carry the item's OTHER attributes through UNCHANGED
	by default: every IPD item attribute a Change group does not mention gets an
	implicit WILDCARD Pin (blank from -> expanded per derived value), exactly like
	the old dyeing/compacting builders always emitting the sibling attribute.
	Without it an unpinned swap builds combos that cannot mint a variant of a
	multi-attribute item ("Please mention Colour attribute in TT-CLOTH" at WO
	calc). The user never has to say "this attribute doesn't change" — an explicit
	Hold entry only NARROWS the group to one value (mentioned -> no implicit pin).
	Conversion rows are untouched: their input/output attribute sets differ by
	design (Consume/Introduce own the sides)."""
	in_item = row.get("input_item") or doc.item
	out_item = row.get("output_item") or doc.item
	# Same-item AND the IPD's own item: the pins come from doc.item_attributes,
	# which describe the IPD item — pinning the cloth's attributes onto a swap
	# modelled on another item (e.g. a yarn-side Colour swap) would fail matrix
	# validation against that item's own attribute set.
	if in_item != out_item or in_item != doc.item:
		return groups
	attributes = [r.attribute for r in doc.get("item_attributes") or []]
	dependent = doc.get("dependent_attribute")
	carried = []
	for idx, group in groups:
		if any(e.get("role") == "Change" for e in group):
			mentioned = {e.get("attribute") for e in group}
			for attribute in attributes:
				if attribute in mentioned or attribute == dependent:
					continue
				# Appended AFTER the group's own entries so explicit entry order
				# (group_name / side value stamps) is untouched.
				group = group + [frappe._dict({
					"mapping_index": idx,
					"attribute": attribute,
					"role": "Pin",
					"from_value": None,
					"to_value": None,
				})]
		carried.append((idx, group))
	return carried


def _row_position(doc, row):
	"""The 0-based chain index of `row` among the ordered fabric-process rows
	(matched by its distinct Process). Feeds values_entering's forward walk."""
	target = row.get("fabric_process")
	for index, candidate in enumerate(get_fabric_process_rows(doc)):
		if candidate.get("fabric_process") == target:
			return index
	return 0


def _attribute_sets(expanded):
	"""Ordered (input_attributes, output_attributes) across all groups. Change ->
	both sides; Introduce -> output only; Consume -> input only; Pin -> both sides
	ONLY when it carries a concrete value (a blank/unexpanded wildcard pin
	contributes nothing, matching the old `any(row.get(passthrough_field))` rule)."""
	input_attrs, output_attrs = {}, {}
	for group in expanded:
		for entry in group:
			role = entry.get("role")
			attribute = entry.get("attribute")
			if role == "Change":
				input_attrs.setdefault(attribute)
				output_attrs.setdefault(attribute)
			elif role == "Introduce":
				output_attrs.setdefault(attribute)
			elif role == "Consume":
				input_attrs.setdefault(attribute)
			elif role == "Pin" and entry.get("from_value"):
				input_attrs.setdefault(attribute)
				output_attrs.setdefault(attribute)
	return list(input_attrs), list(output_attrs)


def _side_values(group, side):
	"""The (attribute, value) entries stamped on one side of a group's combo, in
	entry order. Change -> from/to; Introduce -> to (output only, ALWAYS, to match
	knitting's unconditional Dia stamp); Consume -> from (input only — the mirror
	of Introduce); Pin -> the pinned value (both sides) when concrete, else
	dropped."""
	values = []
	for entry in group:
		role = entry.get("role")
		if role == "Change":
			values.append((entry.get("attribute"),
				entry.get("from_value") if side == "Input" else entry.get("to_value")))
		elif role == "Introduce":
			if side == "Output":
				values.append((entry.get("attribute"), entry.get("to_value")))
		elif role == "Consume":
			if side == "Input":
				values.append((entry.get("attribute"), entry.get("from_value")))
		elif role == "Pin":
			pin = entry.get("from_value")
			if pin:
				values.append((entry.get("attribute"), pin))
	return values


def _group_name(group):
	"""Preserve the classic matrix labels: swap -> "from -> to" (pin-prefixed
	"pin: from -> to"); conversion introduce -> the introduced value(s). Groups
	WITHOUT a Change: Consume+Introduce -> "consumed value(s) -> introduced
	value(s)" (the cross-item correspondence); Consume-only (dropped attribute)
	-> the consumed value(s). Groups WITH a Change keep the classic label."""
	changes = [e for e in group if e.get("role") == "Change"]
	introduces = [e for e in group if e.get("role") == "Introduce"]
	consumes = [e for e in group if e.get("role") == "Consume"]
	pins = [e.get("from_value") for e in group
		if e.get("role") == "Pin" and e.get("from_value")]
	if changes:
		froms = [e.get("from_value") for e in changes]
		tos = [e.get("to_value") for e in changes]
		core = (f"{froms[0]} -> {tos[0]}" if len(changes) == 1
			else " · ".join(map(str, froms)) + " -> " + " · ".join(map(str, tos)))
	elif consumes and introduces:
		core = (" · ".join(str(e.get("from_value")) for e in consumes)
			+ " -> " + " · ".join(str(e.get("to_value")) for e in introduces))
	elif consumes:
		froms = [e.get("from_value") for e in consumes]
		core = froms[0] if len(consumes) == 1 else " · ".join(map(str, froms))
	elif introduces:
		tos = [e.get("to_value") for e in introduces]
		core = tos[0] if len(introduces) == 1 else " · ".join(map(str, tos))
	else:
		core = None
	if pins:
		prefix = pins[0] if len(pins) == 1 else " · ".join(map(str, pins))
		core = f"{prefix}: {core}" if core else prefix
	return core


def _is_wildcard_pin(entry):
	return entry.get("role") == "Pin" and not entry.get("from_value")


def _change_from_key(group):
	return tuple(sorted(e.get("from_value") for e in group
		if e.get("role") == "Change" and e.get("from_value")))


def _expand_mapping_indexes(doc, position, groups):
	"""Expand wildcard Pin groups into concrete ones, mirroring the classic
	_expand_wildcard_rows: concrete groups first, then each wildcard group cloned
	per derived value of its blank-from Pin(s) (cross-product for several), while
	EXCLUDING (pin_value, change_from) keys a concrete group already covers — a
	specific mapping always wins over applies-to-all. No derivable values -> the
	wildcard group passes through unchanged (its blank pin is dropped at emit)."""
	import itertools

	concrete, wildcard = [], []
	for _idx, group in groups:
		(wildcard if any(_is_wildcard_pin(e) for e in group) else concrete).append(group)
	if not wildcard:
		return concrete

	covered = set()
	for group in concrete:
		change_from = _change_from_key(group)
		for entry in group:
			if entry.get("role") == "Pin" and entry.get("from_value"):
				covered.add((entry.get("attribute"), entry.get("from_value"), change_from))

	expanded = list(concrete)
	for group in wildcard:
		wild_attrs = [e.get("attribute") for e in group if _is_wildcard_pin(e)]
		value_lists = [values_entering(doc, position, attribute) for attribute in wild_attrs]
		if not all(value_lists):
			# nothing derivable for at least one wildcard attr -> pass through
			expanded.append(group)
			continue
		change_from = _change_from_key(group)
		for combo in itertools.product(*value_lists):
			# NOTE: specific-beats-wildcard dedup only handles the single-wildcard
			# case. On a 3+-attribute IPD, _add_carry_pins can inject >=2 implicit
			# wildcard pins into one Change group and a concrete explicitly-held
			# sibling would then be DUPLICATED by this cross-product (same input
			# combo in two groups). Unreachable with Dia/Colour data — extend the
			# covered-key to tuples before a third fabric attribute arrives.
			if len(wild_attrs) == 1 and (wild_attrs[0], combo[0], change_from) in covered:
				continue
			expanded.append(_clone_group(group, dict(zip(wild_attrs, combo))))
	return expanded


def _clone_group(group, assignment):
	"""Clone a mapping group, stamping each wildcard Pin's blank value with its
	assigned concrete value. Preserves the frappe._dict clone quirk: on a
	frappe._dict `row.as_dict` is a MISSING KEY (None) so hasattr() lies — branch
	on the real type instead."""
	clones = []
	for entry in group:
		clone = frappe._dict(dict(entry) if isinstance(entry, dict) else entry.as_dict())
		if _is_wildcard_pin(entry) and clone.get("attribute") in assignment:
			value = assignment[clone["attribute"]]
			clone["from_value"] = value
			clone["to_value"] = value
		clones.append(clone)
	return clones
