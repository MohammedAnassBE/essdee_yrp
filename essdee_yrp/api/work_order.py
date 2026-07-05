# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""Fabric Work Order Calculate: popup context + calculation.

The popup derives EVERYTHING from the IPD's auto-generated matrices; the user
only enters quantities — one row per matrix group (user-locked 2026-07-03).
Entered rows become `output_demand` for the base engine (`get_process_io`):
deliverables are the engine's scaled inputs; receivables are the entered rows
themselves (1:1 v1 — the Process master's waste/excess applies later)."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_chain import get_fabric_step, get_fabric_steps
from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
	get_identity_process_row,
)
from essdee_yrp.fabric_program import get_greige_colour


def _step_kind(step):
	"""Legacy kind alias for a chain step — keeps every existing popup branch
	(labels, colour columns, yarn field, overshoot rules) working for NEW
	processes: any Colour swap renders like dyeing, any Dia swap (Re-Compacting)
	like compacting, any conversion like knitting."""
	if not step:
		return None
	if step["shape"] == "conversion":
		return "knitting"
	# swap: dyeing (Colour) or compacting (Dia)
	return "dyeing" if step["attribute"] == FABRIC_COLOUR_ATTRIBUTE else "compacting"
from essdee_yrp.ipd_validations import get_attribute_mapping, get_ipd_attribute_values


@frappe.whitelist()
def get_fabric_deliverable_context(work_order):
	"""Popup context: one entry per Lot Fabric Detail whose IPD maps this WO's
	process to knitting/dyeing/compacting. Empty rows => not a fabric process."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	lot = _get_lot(wo)

	rows = []
	warnings = []
	kind = None
	for fabric in lot.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		step = get_fabric_step(ipd, wo.process_name)
		row_kind = _step_kind(step)
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
				qty_rows = _identity_qty_rows(ipd, treated_item)
			else:
				qty_rows = _matrix_qty_rows(ipd, wo.process_name, row_kind)
		except frappe.ValidationError as e:
			# One stale IPD must not block the other fabrics' calculation.
			warnings.append(str(e))
			continue
		has_colour = _item_has_attribute(fabric.cloth_item, FABRIC_COLOUR_ATTRIBUTE)
		if step:
			_add_planning_data(qty_rows, row_kind, lot, wo, fabric, ipd, step)
		rows.append({
			"fabric_row": fabric.name,
			"yarn_item": ipd.get("yarn_item"),
			"cloth_item": fabric.cloth_item,
			"treated_item": treated_item,
			"production_detail": fabric.production_detail,
			"kind": row_kind,
			"ratio": flt(ipd.get("cloth_per_kg_yarn")) or 1,
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
	from essdee_yrp.fabric_tracking import (
		get_consumed_by_dia_colour,
		get_produced_by_dia,
		get_produced_by_dia_colour,
		get_step_planned,
		get_step_received,
	)

	cloth = fabric.cloth_item

	if kind == "knitting":
		program_rows = {
			r.dia: r for r in lot.get("lot_fabric_programs") or [] if r.cloth_item == cloth
		}
		ordered = get_produced_by_dia(lot.name, wo.process_name, cloth, exclude_wo=wo.name)
		for qr in qty_rows:
			dia = (qr.get("out_attrs") or {}).get(FABRIC_DIA_ATTRIBUTE)
			row = program_rows.get(dia)
			program = flt(row.weight) if row else 0
			already = flt(ordered.get(dia))
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
	prev_step = steps[position - 1] if position > 0 else None
	prev_received = (
		get_step_received(lot.name, cloth, prev_step["process_name"]) if prev_step else None
	)
	planned = get_step_planned(lot.name, cloth, wo.process_name)
	ordered_out = get_produced_by_dia_colour(lot.name, wo.process_name, cloth, exclude_wo=wo.name)
	consumed_in = get_consumed_by_dia_colour(lot.name, wo.process_name, cloth, exclude_wo=wo.name)

	for qr in qty_rows:
		in_attrs = qr.get("in_attrs") or {}
		out_attrs = qr.get("out_attrs") or {}
		in_key = (in_attrs.get(FABRIC_DIA_ATTRIBUTE) or "", in_attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
		out_key = (out_attrs.get(FABRIC_DIA_ATTRIBUTE) or "", out_attrs.get(FABRIC_COLOUR_ATTRIBUTE) or "")
		available = None
		if prev_received is not None:
			produced = _lookup_attr_sum(prev_received, in_key)
			consumed = _lookup_attr_sum(
				{(k[0] or "", k[1] or ""): v for k, v in consumed_in.items()}, in_key)
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
	for dyeing/compacting; knitting rows carry Dia (Colour merged at calc)."""
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
		for group_index, group in sorted(matrix.get_combinations_grouped().items()):
			out = (group.get("output") or [{}])[0]
			inp = (group.get("input") or [{}])[0]
			qty_rows.append({
				"key": f"{name}:{group_index}",
				"label": _group_label(kind, inp.get("attrs") or {}, out.get("attrs") or {}),
				"out_attrs": out.get("attrs") or {},
				# input-side attrs carry (from_dia, colour) for compacting and
				# (dia, from_colour) for dyeing — availability is keyed on them.
				"in_attrs": inp.get("attrs") or {},
			})
	return qty_rows


def _identity_qty_rows(ipd, treated_item):
	"""No-conversion process (e.g. Washing): one qty row per variant combo of
	the treated item, derived from the IPD (dias x colours). Deliverable =
	receivable, so out_attrs is the full variant spec."""
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

	has_dia = FABRIC_DIA_ATTRIBUTE in declared
	has_colour = FABRIC_COLOUR_ATTRIBUTE in declared
	# UNION derivation: an identity process has no fixed position in the
	# knit->dye->compact chain, so offer every dia/colour the IPD knows
	# (extra rows are harmless blanks; missing rows are a hard stop).
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

	return [{
		"key": f"identity:{i}",
		"label": " · ".join(combo.values()) or treated_item,
		"out_attrs": combo,
	} for i, combo in enumerate(combos)]


def _identity_attr_values(ipd, attribute):
	"""Union of every value the IPD's fabric tabs mention for `attribute`,
	falling back to the IPD's attribute-mapping values."""
	if attribute == FABRIC_DIA_ATTRIBUTE:
		values = [r.dia for r in ipd.get("knitting_dia_details") or [] if r.dia]
		values += [r.from_dia for r in ipd.get("compacting_dia_details") or [] if r.from_dia]
		values += [r.to_dia for r in ipd.get("compacting_dia_details") or [] if r.to_dia]
	else:
		values = [r.from_colour for r in ipd.get("dyeing_colour_details") or [] if r.from_colour]
		values += [r.to_colour for r in ipd.get("dyeing_colour_details") or [] if r.to_colour]
	if not values:
		values = get_ipd_attribute_values(ipd, attribute)
	return list(dict.fromkeys(values))


def _group_label(kind, in_attrs, out_attrs):
	if kind == "knitting":
		return out_attrs.get(FABRIC_DIA_ATTRIBUTE) or "?"
	if in_attrs == out_attrs:
		# in-chain identity step: nothing changes — plain variant label
		return " · ".join(v for v in out_attrs.values()) or "?"
	changed = [a for a in out_attrs if in_attrs.get(a) != out_attrs.get(a)]
	if len(changed) > 1:
		# multi_swap (Dye-Compact): show the full combo transition
		return (" · ".join(in_attrs.get(a, "?") for a in sorted(in_attrs))
			+ " → " + " · ".join(out_attrs.get(a, "?") for a in sorted(out_attrs)))
	if kind == "dyeing":
		dia = out_attrs.get(FABRIC_DIA_ATTRIBUTE)
		swap = f"{in_attrs.get(FABRIC_COLOUR_ATTRIBUTE)} → {out_attrs.get(FABRIC_COLOUR_ATTRIBUTE)}"
		return f"{dia}: {swap}" if dia else swap
	colour = out_attrs.get(FABRIC_COLOUR_ATTRIBUTE)
	swap = f"{in_attrs.get(FABRIC_DIA_ATTRIBUTE)} → {out_attrs.get(FABRIC_DIA_ATTRIBUTE)}"
	return f"{colour}: {swap}" if colour else swap


def _knit_colour_options(ipd):
	"""Knitted (greige) colour choices. Prefer the dyeing tab's from-colours —
	greige knitted in any other colour could never be consumed by the dyeing
	matrices. Fall back to the IPD Colour mapping, then all Colour values."""
	from_colours = list(dict.fromkeys(
		r.from_colour for r in ipd.get("dyeing_colour_details") or [] if r.from_colour
	))
	if from_colours:
		return from_colours
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
def calculate_fabric_deliverables(work_order, rows):
	"""rows = [{fabric_row, colour?, yarn_qty?, entries: [{out_attrs, qty}]}].

	knitting:   entries = cloth kgs per dia; yarn deliverable computed by the
	            engine via cloth_per_kg_yarn, overridable with yarn_qty.
	dyeing:     entries = kgs per (dia, from->to colour) group, 1:1.
	compacting: entries = kgs per (colour, from->to dia) group, 1:1.
	Each entry carries the matrix group `key` ("<matrix>:<group_index>") the
	popup row came from — group resolution is BY KEY, never by attrs: two legal
	mappings can share identical output attrs (White→Black and Ecru→Black at
	the same dia), and an attrs-based first-match would misroute the quantity
	through the wrong group."""
	from yrp.yrp.doctype.item.item import get_or_create_variant

	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("write")
	if wo.docstatus != 0:
		frappe.throw(_("Calculate can only update a draft Work Order."))

	lot = _get_lot(wo)
	fabric_rows = {f.name: f for f in lot.get("lot_fabric_details") or []}
	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))

	deliverables, receivables = [], []
	matrix_cache = {}
	for entry in rows:
		fabric = fabric_rows.get(entry.get("fabric_row"))
		if not fabric:
			frappe.throw(_("Unknown Lot fabric row {0}.").format(entry.get("fabric_row")))
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		kind = _step_kind(get_fabric_step(ipd, wo.process_name))
		identity_row = None
		if not kind:
			identity_row = get_identity_process_row(ipd, wo.process_name)
			if identity_row:
				kind = "identity"
		if not kind:
			frappe.throw(_("{0} is not a fabric process on IPD {1}.").format(wo.process_name, ipd.name))

		if kind == "identity":
			# No conversion: deliverable = receivable, same variant, same qty.
			# out_attrs are client-sent: accept only combos this IPD derives.
			treated_item = identity_row.process_item or fabric.cloth_item
			treated_uom = frappe.db.get_value("Item", treated_item, "default_unit_of_measure")
			allowed = {frozenset((r["out_attrs"] or {}).items()) for r in _identity_qty_rows(ipd, treated_item)}
			for line in entry.get("entries") or []:
				qty = flt(line.get("qty"))
				if qty <= 0:
					continue
				out_attrs = dict(line.get("out_attrs") or {})
				if frozenset(out_attrs.items()) not in allowed:
					frappe.throw(
						_("Combination {0} is not derived from IPD {1} — reopen the Calculate popup.").format(
							out_attrs or treated_item, ipd.name))
				variant = get_or_create_variant(treated_item, out_attrs)
				deliverables.append({
					"item_variant": variant,
					"qty": qty,
					"uom": treated_uom,
					"pending_quantity": qty,
					"received_type": default_received_type,
					"is_calculated": 1,
				})
				receivables.append({
					"item_variant": variant,
					"qty": qty,
					"uom": treated_uom,
					"pending_quantity": qty,
				})
			continue

		has_colour = _item_has_attribute(fabric.cloth_item, FABRIC_COLOUR_ATTRIBUTE)
		colour = entry.get("colour")
		valid_colours = None
		if kind == "knitting":
			_require_ipd_yarn(ipd)
			# colours are client-sent (entry-level for old payloads, line-level
			# for multi-colour knitting) — enforce the same restriction the UI
			# shows (greige = dyeing from-colours), else a crafted call could
			# mint variants that poison the (dia, colour) tracking keys
			valid_colours = set(_knit_colour_options(ipd))

		# Aggregate scaled inputs by variant; receivables per entered row.
		aggregated = {}
		fabric_receivables = []
		cloth_uom = frappe.db.get_value("Item", fabric.cloth_item, "default_unit_of_measure")
		for line in entry.get("entries") or []:
			qty = flt(line.get("qty"))
			if qty <= 0:
				continue
			line_colour = line.get("colour") or colour
			if kind == "knitting" and has_colour:
				if not line_colour:
					frappe.throw(_("Select the cloth Colour for {0}.").format(fabric.cloth_item))
				if line_colour not in valid_colours:
					frappe.throw(
						_("{0} is not a valid greige colour for IPD {1}.").format(line_colour, ipd.name)
					)
			matrix, group = _resolve_matrix_group(matrix_cache, line.get("key"), ipd, wo.process_name)
			out_combo = (group.get("output") or [{}])[0]
			out_qty = flt(out_combo.get("qty"))
			if out_qty <= 0:
				frappe.throw(_("Matrix group {0} has no positive output quantity.").format(line.get("key")))
			scale = qty / out_qty

			input_item = matrix.input_item or ipd.item
			for inp in group.get("input") or []:
				inp_qty = flt(inp.get("qty")) * scale * (1 + flt(inp.get("wastage_pct")) / 100.0)
				variant = get_or_create_variant(input_item, inp.get("attrs") or {})
				key = (variant, inp.get("uom"))
				aggregated.setdefault(key, {"item": input_item, "qty": 0.0})
				aggregated[key]["qty"] += inp_qty

			out_attrs = dict(out_combo.get("attrs") or {})
			if kind == "knitting" and line_colour and has_colour:
				out_attrs[FABRIC_COLOUR_ATTRIBUTE] = line_colour
			fabric_receivables.append({
				"item_variant": get_or_create_variant(fabric.cloth_item, out_attrs),
				"qty": qty,
				"uom": cloth_uom,
				"pending_quantity": qty,
			})
		if not fabric_receivables:
			continue

		# Knitting: the popup's editable yarn figure overrides the computed
		# input. Valid while knitting matrices have exactly ONE input (the
		# attr-less yarn); with more inputs the override is ignored.
		yarn_override = flt(entry.get("yarn_qty"))
		if kind == "knitting" and yarn_override > 0 and len(aggregated) == 1:
			next(iter(aggregated.values()))["qty"] = yarn_override

		for (variant, uom), data in aggregated.items():
			qty = flt(data["qty"], 3)
			deliverables.append({
				"item_variant": variant,
				"qty": qty,
				"uom": uom or frappe.db.get_value("Item", data["item"], "default_unit_of_measure"),
				"pending_quantity": qty,
				"received_type": default_received_type,
				"is_calculated": 1,
			})
		receivables.extend(fabric_receivables)

	if not deliverables:
		frappe.throw(_("Enter a quantity greater than zero for at least one row."))

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

	# Idempotent rewrite (MGK pattern): drop prior calculated deliverables,
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


def _item_has_attribute(item, attribute):
	return attribute in _item_attribute_names(item)


def _item_attribute_names(item):
	item_doc = frappe.get_cached_doc("Item", item)
	return [row.attribute for row in item_doc.get("attributes") or []]


def _get_lot(wo):
	if not wo.get("lot"):
		frappe.throw(_("Select a Lot on the Work Order first."))
	lot = frappe.get_doc("Lot", wo.lot)
	lot.check_permission("read")
	return lot


def _require_ipd_yarn(ipd):
	yarn_item = ipd.get("yarn_item")
	if not yarn_item:
		frappe.throw(_("Set the Yarn Item on IPD {0} (Knitting tab) first.").format(ipd.name))
	return yarn_item
