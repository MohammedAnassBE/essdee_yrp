import frappe
from frappe import _

from essdee_yrp.purchase import lot_documents, lot_editor
from essdee_yrp.purchase import lot_workspace as purchase_lot_workspace


def _require_existing(name):
	if not (name or "").strip():
		frappe.throw(_("Planning edits existing Lots only."), frappe.PermissionError)


@frappe.whitelist()
def get_lot_workspace(name: str):
	return purchase_lot_workspace.get_lot_workspace(name)


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
