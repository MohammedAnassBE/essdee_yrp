# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe

from essdee_yrp.ipd_validations import is_cloth_ipd

FABRIC_DIA_ATTRIBUTE = "Dia"
FABRIC_COLOUR_ATTRIBUTE = "Colour"

# (ipd process-link fieldname, kind)
FABRIC_PROCESS_FIELDS = (
	("knitting_process", "knitting"),
	("dyeing_process", "dyeing"),
	("compacting_process", "compacting"),
)


def get_fabric_process_kind(ipd_doc, process_name):
	"""Which fabric process (knitting/dyeing/compacting) `process_name` is on this IPD, or None."""
	if not process_name:
		return None
	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		if ipd_doc.get(fieldname) == process_name:
			return kind
	return None


def get_identity_process_row(ipd_doc, process_name):
	"""A process declared in `ipd_processes` that is NOT one of the three
	conversion tabs treats its `process_item` (blank = the IPD's item) 1:1 —
	deliverable = receivable, no matrix (e.g. Washing). Cloth IPDs only:
	garment IPDs also carry ipd_processes rows (stitching etc.) and must
	never enter the fabric path, even via a mis-pointed Lot fabric row."""
	if not process_name or get_fabric_process_kind(ipd_doc, process_name):
		return None
	if not is_cloth_ipd(ipd_doc):
		return None
	for row in ipd_doc.get("ipd_processes") or []:
		if row.process_name == process_name:
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


def sync_fabric_process_matrices(doc, method=None):
	"""Regenerate the IPD Process Matrix docs for a cloth IPD's fabric processes.

	Idempotent: existing matrices for (ipd, process) are deleted and rebuilt
	from the IPD tab tables on every IPD save. Matrices stay draft — the
	fabric WO calculation owns how they are read. Never hand-authored
	(standing 2026-06-25 rule).
	"""
	if not is_cloth_ipd(doc):
		return

	uom = frappe.db.get_value("Item", doc.item, "default_unit_of_measure")

	# Matrices are NEVER hand-authored (2026-06-25 rule), so wiping every
	# matrix of this IPD is safe and also clears orphans left behind when a
	# process link is changed or removed.
	_delete_all_matrices(doc.name)

	for fieldname, kind in FABRIC_PROCESS_FIELDS:
		process = doc.get(fieldname)
		if not process:
			continue
		builder = {
			"knitting": _build_knitting_matrix,
			"dyeing": _build_dyeing_matrix,
			"compacting": _build_compacting_matrix,
		}[kind]
		matrix = builder(doc, process, uom)
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


def _build_knitting_matrix(doc, process, uom):
	"""One group per Dia row: Input = 1 kg yarn (the IPD's yarn_item; the yarn
	VARIANT is still chosen per WO, so the input combo carries no attributes),
	Output = `cloth_per_kg_yarn` kgs of cloth at that dia. This is what gives
	the WO the yarn->cloth quantity relationship."""
	from frappe.utils import flt

	rows = doc.get("knitting_dia_details") or []
	if not rows:
		return None
	matrix = _new_matrix(doc, process)
	yarn_uom = uom
	if doc.get("yarn_item"):
		matrix.input_item = doc.yarn_item
		yarn_uom = frappe.db.get_value("Item", doc.yarn_item, "default_unit_of_measure") or uom
	output_qty = flt(doc.get("cloth_per_kg_yarn")) or 1
	matrix.append("output_attributes", {"attribute": FABRIC_DIA_ATTRIBUTE})
	for idx, row in enumerate(rows):
		matrix.append("combinations", {
			"group_index": idx, "group_name": row.dia, "side": "Input",
			"combo_index": 0, "quantity": 1, "uom": yarn_uom, "wastage_pct": 0,
		})
		matrix.append("combinations", {
			"group_index": idx, "group_name": row.dia, "side": "Output",
			"combo_index": 0, "quantity": output_qty, "uom": uom, "wastage_pct": 0,
		})
		matrix.append("combination_attributes", {
			"group_index": idx, "side": "Output", "combo_index": 0,
			"attribute": FABRIC_DIA_ATTRIBUTE, "attribute_value": row.dia,
		})
	return matrix


def _build_value_swap_matrix(doc, process, uom, rows, attribute, from_field, to_field, passthrough_attribute, passthrough_field):
	"""Shared shape for dyeing (Colour swap) and compacting (Dia swap):
	one group per mapping row; Input combo carries the from-value,
	Output combo the to-value. Quantities 1:1 (v1).

	A row may pin the OTHER attribute (dyeing row.dia / compacting row.colour):
	that passthrough value is stamped unchanged on BOTH sides, narrowing the
	swap to just that dia/colour. Blank = the swap applies to every value.

	Wildcard rows (blank dia/colour) are EXPANDED into one concrete group per
	derived passthrough value — the engine's get_or_create_variant needs every
	attribute the item declares, so the matrix must be fully explicit. Pinned
	rows come first and exclude their (pin, from) key from the expansion, so a
	specific mapping always wins over an applies-to-all one."""
	if not rows:
		return None
	rows = _expand_wildcard_rows(doc, rows, passthrough_field, from_field)
	matrix = _new_matrix(doc, process)
	matrix.input_item = doc.item
	matrix.append("input_attributes", {"attribute": attribute})
	matrix.append("output_attributes", {"attribute": attribute})
	if any(row.get(passthrough_field) for row in rows):
		matrix.append("input_attributes", {"attribute": passthrough_attribute})
		matrix.append("output_attributes", {"attribute": passthrough_attribute})
	for idx, row in enumerate(rows):
		passthrough_value = row.get(passthrough_field)
		group_name = f"{row.get(from_field)} -> {row.get(to_field)}"
		if passthrough_value:
			group_name = f"{passthrough_value}: {group_name}"
		for side, value in (("Input", row.get(from_field)), ("Output", row.get(to_field))):
			matrix.append("combinations", {
				"group_index": idx, "group_name": group_name,
				"side": side, "combo_index": 0, "quantity": 1, "uom": uom, "wastage_pct": 0,
			})
			matrix.append("combination_attributes", {
				"group_index": idx, "side": side, "combo_index": 0,
				"attribute": attribute, "attribute_value": value,
			})
			if passthrough_value:
				matrix.append("combination_attributes", {
					"group_index": idx, "side": side, "combo_index": 0,
					"attribute": passthrough_attribute, "attribute_value": passthrough_value,
				})
	return matrix


def _expand_wildcard_rows(doc, rows, passthrough_field, from_field):
	"""Pinned rows first, then each wildcard row cloned per derived passthrough
	value (skipping keys a pinned row already covers). If no values can be
	derived, the wildcard rows pass through unchanged."""
	pinned = [r for r in rows if r.get(passthrough_field)]
	wildcards = [r for r in rows if not r.get(passthrough_field)]
	if not wildcards:
		return pinned
	values = derive_passthrough_values(doc, passthrough_field)
	if not values:
		return pinned + wildcards
	covered = {(r.get(passthrough_field), r.get(from_field)) for r in pinned}
	expanded = []
	for row in wildcards:
		for value in values:
			if (value, row.get(from_field)) in covered:
				continue
			clone = frappe._dict(row.as_dict() if hasattr(row, "as_dict") else dict(row))
			clone[passthrough_field] = value
			expanded.append(clone)
	return pinned + expanded


def derive_passthrough_values(doc, passthrough_field):
	"""Dyeing needs 'all dias': knitting-tab dias, else the IPD's Dia mapping
	values (bought-greige cloth). Compacting needs 'all colours': dyeing
	to-colours, else the IPD's Colour mapping values."""
	from essdee_yrp.ipd_validations import get_ipd_attribute_values

	if passthrough_field == "dia":
		values = [r.dia for r in doc.get("knitting_dia_details") or [] if r.dia]
		if not values:
			values = get_ipd_attribute_values(doc, FABRIC_DIA_ATTRIBUTE)
	else:
		values = [r.to_colour for r in doc.get("dyeing_colour_details") or [] if r.to_colour]
		if not values:
			values = get_ipd_attribute_values(doc, FABRIC_COLOUR_ATTRIBUTE)
	return list(dict.fromkeys(values))


def _build_dyeing_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("dyeing_colour_details") or [],
		FABRIC_COLOUR_ATTRIBUTE, "from_colour", "to_colour",
		FABRIC_DIA_ATTRIBUTE, "dia",
	)


def _build_compacting_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("compacting_dia_details") or [],
		FABRIC_DIA_ATTRIBUTE, "from_dia", "to_dia",
		FABRIC_COLOUR_ATTRIBUTE, "colour",
	)
