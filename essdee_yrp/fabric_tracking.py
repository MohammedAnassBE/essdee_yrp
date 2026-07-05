# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

"""GRN-driven received tracking for the Lot fabric chain + the balance queries
the fabric WO popup uses.

Every chain step's receipts land on `Lot Fabric Step Ledger` Output rows keyed
(process, dia, colour) — plan (planned_weight, solver-owned) and actuals
(received_weight, owned here) live side by side. The knitting/conversion step
ADDITIONALLY updates `Lot Fabric Program.received_weight` per dia: the program
stays the WO driver and the knitting popup's balance source.
(`Lot Fabric Colour Program` is legacy — frozen, no longer written.)

Rework GRNs are skipped — a rework re-receives kgs that were already counted.

Balance semantics:
  - production against the program/plan -> WO RECEIVABLES (outputs)
  - consumption of available cloth      -> WO DELIVERABLES (inputs, is_calculated=1)
"""

import frappe
from frappe.utils import flt

from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
)


def on_grn_submit(doc, method=None):
	_apply_grn(doc, 1)


def on_grn_cancel(doc, method=None):
	_apply_grn(doc, -1)


def _apply_grn(grn, sign):
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return
	if grn.get("is_rework"):
		return
	wo = frappe.get_cached_doc("Work Order", grn.against_id)
	if not wo.get("lot"):
		return
	# Serialize per lot: two GRNs of the same lot submitting concurrently would
	# otherwise race the read-modify-write below (lost kgs / duplicate key rows).
	frappe.db.get_value("Lot", wo.lot, "name", for_update=True)
	lot = frappe.get_doc("Lot", wo.lot)
	from essdee_yrp.fabric_chain import get_fabric_step

	for fabric in lot.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		step = get_fabric_step(ipd, wo.process_name)
		if not step:
			continue
		# every chain step's receipts land on the step ledger (dia + colour)
		deltas = _grn_deltas_for_cloth(grn, fabric.cloth_item, with_colour=True)
		if not deltas:
			continue
		_bump_ledger_rows(lot, fabric.cloth_item, step["process_name"], deltas, sign)
		if step["shape"] == "conversion":
			# the knitting program keeps its own dia-level received figure —
			# it is the WO driver and the knitting popup's balance source
			per_dia = {}
			for key, kg in deltas.items():
				per_dia[(key[0],)] = per_dia.get((key[0],), 0) + kg
			_bump_program_rows(lot, "lot_fabric_programs", "Lot Fabric Program",
				fabric.cloth_item, per_dia, sign, "received_weight")


def _bump_ledger_rows(lot, cloth_item, process_name, deltas, sign):
	"""Add sign×kg to the step ledger's Output received_weight per (dia, colour);
	missing rows are created at planned 0 so no receipt is silently dropped."""
	rows = {}
	for r in lot.get("lot_fabric_step_ledger") or []:
		if r.cloth_item != cloth_item or r.process_name != process_name:
			continue
		if (r.side or "Output") != "Output":
			continue
		rows[(r.dia or "", r.colour or "")] = r

	inserted = 0
	for key, kg in deltas.items():
		dia = key[0] or ""
		colour = (key[1] if len(key) > 1 else "") or ""
		row = rows.get((dia, colour))
		if row:
			frappe.db.sql(
				"UPDATE `tabLot Fabric Step Ledger` "
				"SET received_weight = ROUND(IFNULL(received_weight, 0) + %s, 3) WHERE name = %s",
				(sign * kg, row.name),
			)
		else:
			new_row = frappe.new_doc("Lot Fabric Step Ledger")
			new_row.parenttype = "Lot"
			new_row.parent = lot.name
			new_row.parentfield = "lot_fabric_step_ledger"
			new_row.idx = len(lot.get("lot_fabric_step_ledger") or []) + 1 + inserted
			new_row.cloth_item = cloth_item
			new_row.process_name = process_name
			new_row.side = "Output"
			new_row.dia = dia or None
			new_row.colour = colour or None
			new_row.planned_weight = 0
			new_row.received_weight = flt(sign * kg, 3)
			new_row.save(ignore_permissions=True)
			inserted += 1


def get_step_received(lot, cloth_item, process_name):
	"""{(dia, colour): kg} received on a step's ledger Output rows — the popup's
	'previous stage produced' figure."""
	result = {}
	for r in frappe.get_all(
		"Lot Fabric Step Ledger",
		filters={
			"parent": lot, "parenttype": "Lot", "cloth_item": cloth_item,
			"process_name": process_name, "side": "Output",
		},
		fields=["dia", "colour", "received_weight"],
	):
		key = (r.dia or "", r.colour or "")
		result[key] = result.get(key, 0) + flt(r.received_weight)
	return result


def get_step_planned(lot, cloth_item, process_name):
	"""{(dia, colour): kg} planned on a step's ledger Output rows."""
	result = {}
	for r in frappe.get_all(
		"Lot Fabric Step Ledger",
		filters={
			"parent": lot, "parenttype": "Lot", "cloth_item": cloth_item,
			"process_name": process_name, "side": "Output",
		},
		fields=["dia", "colour", "planned_weight"],
	):
		key = (r.dia or "", r.colour or "")
		result[key] = result.get(key, 0) + flt(r.planned_weight)
	return result


def _grn_deltas_for_cloth(grn, cloth_item, with_colour):
	"""{(dia,) | (dia, colour): kg} summed over the GRN's rows of this cloth's variants."""
	variant_names = list({r.item_variant for r in grn.get("items") or [] if r.item_variant})
	if not variant_names:
		return {}
	attrs = _variant_attribute_map(variant_names, cloth_item)
	deltas = {}
	for row in grn.get("items") or []:
		info = attrs.get(row.item_variant)
		if not info or not info.get(FABRIC_DIA_ATTRIBUTE):
			continue
		if with_colour:
			# Colour is OPTIONAL — a dia-only cloth (no Colour attribute) must
			# still track; its ledger rows just carry a blank colour
			key = (info[FABRIC_DIA_ATTRIBUTE], info.get(FABRIC_COLOUR_ATTRIBUTE) or "")
		else:
			key = (info[FABRIC_DIA_ATTRIBUTE],)
		# stock_qty = quantity × conversion_factor in the stock UOM (kg for cloth).
		deltas[key] = deltas.get(key, 0) + (flt(row.stock_qty) or flt(row.quantity))
	return deltas


def _variant_attribute_map(variant_names, cloth_item):
	"""{variant: {attribute: value}} restricted to the cloth's variants, Dia/Colour only."""
	rows = frappe.db.sql(
		"""
		SELECT iv.name AS variant, iva.attribute, iva.attribute_value
		FROM `tabItem Variant` iv
		JOIN `tabItem Variant Attribute` iva ON iva.parent = iv.name
		WHERE iv.name IN %(variants)s AND iv.item = %(item)s
			AND iva.attribute IN (%(dia)s, %(colour)s)
		""",
		{
			"variants": variant_names, "item": cloth_item,
			"dia": FABRIC_DIA_ATTRIBUTE, "colour": FABRIC_COLOUR_ATTRIBUTE,
		},
		as_dict=True,
	)
	result = {}
	for r in rows:
		result.setdefault(r.variant, {})[r.attribute] = r.attribute_value
	return result


def _bump_program_rows(lot, parentfield, child_doctype, cloth_item, deltas, sign, value_field):
	"""Add sign×kg to `value_field` per key; missing rows are created at weight 0
	so no receipt is silently dropped. Direct row-level writes — a full lot.save()
	from inside GRN submit would re-run Lot's order/PPO machinery."""
	rows = {}
	for r in lot.get(parentfield) or []:
		if r.cloth_item != cloth_item:
			continue
		key = (r.dia,) if child_doctype == "Lot Fabric Program" else (r.dia, r.colour)
		rows[key] = r

	# table + column come from the hardcoded call sites, never from user input
	table = "tabLot Fabric Program" if child_doctype == "Lot Fabric Program" \
		else "tabLot Fabric Colour Program"
	column = "received_weight" if value_field == "received_weight" else "compacted_weight"
	inserted = 0
	for key, kg in deltas.items():
		row = rows.get(key)
		if row:
			# atomic increment — safe even without the per-lot lock
			frappe.db.sql(
				f"UPDATE `{table}` SET {column} = ROUND(IFNULL({column}, 0) + %s, 3) WHERE name = %s",
				(sign * kg, row.name),
			)
		else:
			new_row = frappe.new_doc(child_doctype)
			new_row.parenttype = "Lot"
			new_row.parent = lot.name
			new_row.parentfield = parentfield
			new_row.idx = len(lot.get(parentfield) or []) + 1 + inserted
			new_row.cloth_item = cloth_item
			new_row.dia = key[0]
			if child_doctype == "Lot Fabric Colour Program":
				new_row.colour = key[1]
			new_row.weight = 0
			new_row.set(column, flt(sign * kg, 3))
			new_row.save(ignore_permissions=True)
			inserted += 1


@frappe.whitelist()
def rebuild_fabric_tracking(lot):
	"""Zero both received columns and replay every submitted fabric GRN of this lot.
	Recovery path for any drift — same idea as production_api's Calculate Pieces."""
	from frappe import _
	if not frappe.db.has_column("Work Order", "lot"):
		frappe.throw(_("Configure the 'lot' stock dimension (YRP Stock Settings) first."))
	lot_doc = frappe.get_doc("Lot", lot)
	lot_doc.check_permission("write")
	frappe.db.get_value("Lot", lot, "name", for_update=True)

	for row in lot_doc.get("lot_fabric_programs") or []:
		frappe.db.set_value("Lot Fabric Program", row.name, "received_weight", 0, update_modified=False)
	for row in lot_doc.get("lot_fabric_step_ledger") or []:
		frappe.db.set_value("Lot Fabric Step Ledger", row.name, "received_weight", 0,
			update_modified=False)

	grn_names = frappe.db.sql(
		"""
		SELECT grn.name
		FROM `tabGoods Received Note` grn
		JOIN `tabWork Order` wo ON wo.name = grn.against_id
		WHERE grn.against = 'Work Order' AND grn.docstatus = 1
			AND IFNULL(grn.is_rework, 0) = 0 AND wo.lot = %(lot)s
		ORDER BY grn.posting_date, grn.posting_time
		""",
		{"lot": lot},
		pluck="name",
	)
	for name in grn_names:
		_apply_grn(frappe.get_doc("Goods Received Note", name), 1)

	from essdee_yrp.fabric_program import fetch_fabric_program_details
	return fetch_fabric_program_details(frappe.get_doc("Lot", lot))


# ---------------------------------------------------------------------------
# Balance queries for the WO Calculate popup (consumed by essdee_yrp.api.work_order)
# ---------------------------------------------------------------------------

def get_produced_by_dia(lot, process_name, cloth_item, exclude_wo=None):
	"""{dia: kg} of RECEIVABLES on other non-cancelled WOs of this lot+process —
	how much of the program is already ordered to be produced (knitting)."""
	return _sum_by_attributes(
		"tabWork Order Receivables", lot, process_name, cloth_item, exclude_wo,
		attributes=(FABRIC_DIA_ATTRIBUTE,),
	)


def get_produced_by_dia_colour(lot, process_name, cloth_item, exclude_wo=None):
	"""{(dia, colour): kg} of RECEIVABLES — dyed output already ordered (dyeing)."""
	return _sum_by_attributes(
		"tabWork Order Receivables", lot, process_name, cloth_item, exclude_wo,
		attributes=(FABRIC_DIA_ATTRIBUTE, FABRIC_COLOUR_ATTRIBUTE),
	)


def get_consumed_by_dia(lot, process_name, cloth_item, exclude_wo=None):
	"""{dia: kg} of calculated DELIVERABLES — greige already consumed (dyeing input)."""
	return _sum_by_attributes(
		"tabWork Order Deliverables", lot, process_name, cloth_item, exclude_wo,
		attributes=(FABRIC_DIA_ATTRIBUTE,), calculated_only=True,
	)


def get_consumed_by_dia_colour(lot, process_name, cloth_item, exclude_wo=None):
	"""{(dia, colour): kg} of calculated DELIVERABLES — dyed cloth already consumed
	(compacting input)."""
	return _sum_by_attributes(
		"tabWork Order Deliverables", lot, process_name, cloth_item, exclude_wo,
		attributes=(FABRIC_DIA_ATTRIBUTE, FABRIC_COLOUR_ATTRIBUTE), calculated_only=True,
	)


def _sum_by_attributes(child_table, lot, process_name, cloth_item, exclude_wo,
		attributes, calculated_only=False):
	# WO.lot is the site-configured stock-dimension Custom Field (created by
	# yrp.stock.dimensions, never shipped as a fixture) — degrade gracefully
	# on a site that hasn't configured the lot dimension yet.
	if not frappe.db.has_column("Work Order", "lot"):
		return {}
	attr_joins, attr_selects, group_by = [], [], []
	for i, attribute in enumerate(attributes):
		alias = f"a{i}"
		attr_joins.append(
			f"JOIN `tabItem Variant Attribute` {alias} "
			f"ON {alias}.parent = iv.name AND {alias}.attribute = %(attr{i})s"
		)
		attr_selects.append(f"{alias}.attribute_value AS v{i}")
		group_by.append(f"{alias}.attribute_value")

	# Rework WOs re-handle already-counted kgs — never part of ordered/consumed.
	conditions = " AND IFNULL(wo.is_rework, 0) = 0"
	if exclude_wo:
		conditions += " AND wo.name != %(exclude_wo)s"
	if calculated_only:
		conditions += " AND IFNULL(child.is_calculated, 0) = 1"

	params = {
		"lot": lot, "process_name": process_name, "cloth_item": cloth_item,
		"exclude_wo": exclude_wo,
	}
	for i, attribute in enumerate(attributes):
		params[f"attr{i}"] = attribute

	rows = frappe.db.sql(
		f"""
		SELECT {", ".join(attr_selects)}, SUM(child.qty) AS total
		FROM `{child_table}` child
		JOIN `tabWork Order` wo ON child.parent = wo.name
		JOIN `tabItem Variant` iv ON child.item_variant = iv.name
		{" ".join(attr_joins)}
		WHERE wo.docstatus < 2 AND wo.lot = %(lot)s
			AND wo.process_name = %(process_name)s AND iv.item = %(cloth_item)s
			{conditions}
		GROUP BY {", ".join(group_by)}
		""",
		params,
		as_dict=True,
	)
	if len(attributes) == 1:
		return {r.v0: flt(r.total) for r in rows}
	return {(r.v0, r.v1): flt(r.total) for r in rows}
