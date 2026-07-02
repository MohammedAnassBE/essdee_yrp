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
	have = {row.attribute for row in doc.get("item_attributes") or []}
	for attribute in needed:
		if attribute not in have:
			doc.append("item_attributes", {"attribute": attribute})


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
	"""Output combos = cloth x each Dia row. Input (yarn) is lot-specific and
	stamped at WO-calculation time, so the input side stays empty here."""
	rows = doc.get("knitting_dia_details") or []
	if not rows:
		return None
	matrix = _new_matrix(doc, process)
	matrix.append("output_attributes", {"attribute": FABRIC_DIA_ATTRIBUTE})
	for idx, row in enumerate(rows):
		matrix.append("combinations", {
			"group_index": idx, "group_name": row.dia, "side": "Output",
			"combo_index": 0, "quantity": 1, "uom": uom, "wastage_pct": 0,
		})
		matrix.append("combination_attributes", {
			"group_index": idx, "side": "Output", "combo_index": 0,
			"attribute": FABRIC_DIA_ATTRIBUTE, "attribute_value": row.dia,
		})
	return matrix


def _build_value_swap_matrix(doc, process, uom, rows, attribute, from_field, to_field):
	"""Shared shape for dyeing (Colour swap) and compacting (Dia swap):
	one group per mapping row; Input combo carries the from-value,
	Output combo the to-value. Quantities 1:1 (v1)."""
	if not rows:
		return None
	matrix = _new_matrix(doc, process)
	matrix.input_item = doc.item
	matrix.append("input_attributes", {"attribute": attribute})
	matrix.append("output_attributes", {"attribute": attribute})
	for idx, row in enumerate(rows):
		for side, value in (("Input", row.get(from_field)), ("Output", row.get(to_field))):
			matrix.append("combinations", {
				"group_index": idx, "group_name": f"{row.get(from_field)} -> {row.get(to_field)}",
				"side": side, "combo_index": 0, "quantity": 1, "uom": uom, "wastage_pct": 0,
			})
			matrix.append("combination_attributes", {
				"group_index": idx, "side": side, "combo_index": 0,
				"attribute": attribute, "attribute_value": value,
			})
	return matrix


def _build_dyeing_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("dyeing_colour_details") or [],
		FABRIC_COLOUR_ATTRIBUTE, "from_colour", "to_colour",
	)


def _build_compacting_matrix(doc, process, uom):
	return _build_value_swap_matrix(
		doc, process, uom, doc.get("compacting_dia_details") or [],
		FABRIC_DIA_ATTRIBUTE, "from_dia", "to_dia",
	)
