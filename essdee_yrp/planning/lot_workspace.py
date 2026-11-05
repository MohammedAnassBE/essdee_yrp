import frappe
from frappe import _

from essdee_yrp.merch import lot_process_flow
from essdee_yrp.merch import lot_workspace as merch_lot_workspace
from essdee_yrp.merch.lot_process_data import LotFlowData
from essdee_yrp.purchase import lot_documents, lot_editor
from essdee_yrp.purchase import lot_workspace as purchase_lot_workspace


def _require_existing(name):
	if not (name or "").strip():
		frappe.throw(_("Planning edits existing Lots only."), frappe.PermissionError)


@frappe.whitelist()
def get_lot_workspace(name: str):
	flow = LotFlowData(name)
	return {
		**purchase_lot_workspace.get_lot_workspace(name),
		"header": merch_lot_workspace.get_record_facts(flow.doc, purchase_lot_workspace.HEADER_FIELDS),
		"order_pieces": flow.order_pieces(),
	}


@frappe.whitelist()
def get_lot_process_flow(lot: str):
	return lot_process_flow.get_process_flow(lot)


@frappe.whitelist()
def get_lot_step_detail(lot: str, key: str):
	return lot_process_flow.get_step_detail(lot, key)


@frappe.whitelist()
def get_lot_work_order_detail(work_order: str):
	return lot_process_flow.get_work_order_detail(work_order)


@frappe.whitelist()
def get_lot_documents(lot: str):
	return lot_documents.get_lot_documents(lot)


@frappe.whitelist()
def get_lot_document(lot: str, doctype: str, name: str):
	return lot_documents.get_lot_document(lot, doctype, name)


@frappe.whitelist()
def get_lot_form(name: str | None = None):
	_require_existing(name)
	return lot_editor.get_lot_form(name)


@frappe.whitelist()
def get_lot_production_detail_context(
	production_detail: str, item: str, production_order: str | None = None,
):
	return lot_editor.get_lot_production_detail_context(production_detail, item, production_order)


@frappe.whitelist()
def get_lot_production_order_item(production_order: str):
	return lot_editor.get_lot_production_order_item(production_order)


@frappe.whitelist(methods=["POST"])
def save_lot(values, name: str | None = None, expected_modified: str | None = None):
	_require_existing(name)
	return lot_editor.save_lot(values, name, expected_modified)
