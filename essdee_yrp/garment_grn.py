"""Garment-process GRN consumption rows.

Production API treated an ordinary, non-group embellishment process (for
example Printing: Cut -> Cut) as a one-to-one conversion: every received panel
also consumes the same panel variant from the supplier warehouse.  Base YRP
owns the stock posting; this Essdee hook supplies that company-specific
``grn_deliverables`` calculation before submission.
"""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_grn import _stock_uom_values


def before_validate(doc, method=None):
	if not _is_identity_garment_grn(doc):
		return

	work_order = frappe.get_cached_doc("Work Order", doc.against_id)
	# ``is_calculated`` describes how a Work Order row was populated; it does
	# not change whether the submitted row is a valid stock source.  Migrated
	# and manually-added deliverables can legitimately have it unset, and an
	# identity garment GRN must still consume the exact matching panel row.
	deliverables = list(work_order.get("deliverables") or [])
	rows = []
	for received in doc.get("items") or []:
		quantity = flt(received.get("quantity"))
		if quantity <= 0:
			continue
		source = _find_deliverable(deliverables, received, work_order.name)
		rows.append(
			{
				"item_variant": received.item_variant,
				"quantity": quantity,
				"uom": received.uom,
				"work_order_deliverable": source.name,
				"lot": received.get("lot") or source.get("lot") or work_order.get("lot"),
				"received_type": received.get("received_type")
				or source.get("received_type")
				or frappe.db.get_single_value(
					"YRP Stock Settings", "default_received_type"
				),
				"valuation_rate": flt(source.get("valuation_rate") or source.get("rate")),
				"set_combination": received.get("set_combination") or {},
				**_stock_uom_values(received.item_variant, received.uom, quantity),
			}
		)
	doc.set("grn_deliverables", rows)


def _is_identity_garment_grn(grn):
	if grn.get("against") != "Work Order" or not grn.get("against_id"):
		return False
	if (
		grn.get("is_return")
		or grn.get("is_rework")
		or grn.get("additional_grn")
		or grn.get("includes_packing")
		or grn.get("cutting_laysheet")
	):
		return False

	work_order = frappe.get_cached_doc("Work Order", grn.against_id)
	if not work_order.get("production_detail") or not work_order.get("process_name"):
		return False
	ipd = frappe.get_cached_doc("Item Production Detail", work_order.production_detail)
	if ipd.get("is_cloth_item"):
		return False
	if work_order.process_name in {
		ipd.get("cutting_process"),
		ipd.get("stiching_process"),
		ipd.get("packing_process"),
	}:
		return False
	if frappe.db.get_value("Process", work_order.process_name, "is_group"):
		return False

	process_row = next(
		(
			row
			for row in (ipd.get("ipd_processes") or [])
			if row.get("process_name") == work_order.process_name
		),
		None,
	)
	return bool(process_row)


def _find_deliverable(deliverables, received, work_order_name):
	from yrp.yrp.doctype.delivery_challan.delivery_challan import _normal_json

	candidates = [
		row
		for row in deliverables
		if row.item_variant == received.item_variant
		and (not received.get("uom") or row.get("uom") == received.get("uom"))
	]
	received_combination = _normal_json(received.get("set_combination"))
	combined = [
		row
		for row in candidates
		if _normal_json(row.get("set_combination")) == received_combination
	]
	if combined:
		candidates = combined

	for fieldname in ("lot", "received_type"):
		value = received.get(fieldname)
		if not value:
			continue
		matched = [row for row in candidates if row.get(fieldname) == value]
		if matched:
			candidates = matched

	if len(candidates) == 1:
		return candidates[0]
	if len(candidates) > 1:
		frappe.throw(
			_(
				"Received panel {0} matches multiple Deliverables in Work Order {1}."
			).format(received.item_variant, work_order_name)
		)
	frappe.throw(
		_("Received panel {0} is not a Deliverable in Work Order {1}.").format(
			received.item_variant, work_order_name
		)
	)
