import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt
from yrp.stock.save_stock_items import group_items_for_ui

from essdee_yrp.fabric_store.documents.common import get_effective_fields
from essdee_yrp.fabric_store.documents.purchase_order import get_purchase_order_workspace
from essdee_yrp.fabric_store.web_workspace import _document_status, get_document

DOCUMENT_SECTIONS = {
	"work_orders": {
		"doctype": "YRP Work Order",
		"fields": (
			"status",
			"process_name",
			"supplier",
			"supplier_name",
			"wo_date",
			"planned_quantity",
			"total_quantity",
			"total_no_of_pieces_delivered",
			"total_no_of_pieces_received",
		),
		"order_by": "wo_date desc, modified desc",
	},
	"purchase_orders": {
		"doctype": "Purchase Order",
		"fields": (
			"status",
			"supplier",
			"supplier_name",
			"transaction_date",
			"schedule_date",
			"total_qty",
			"grand_total",
			"currency",
		),
		"order_by": "transaction_date desc, modified desc",
	},
	"goods_received_notes": {
		"doctype": "YRP Goods Received Note",
		"fields": (
			"posting_date",
			"posting_time",
			"process_name",
			"supplier",
			"against",
			"against_id",
			"is_return",
			"total_received_quantity",
		),
		"order_by": "posting_date desc, posting_time desc, modified desc",
	},
	"delivery_challans": {
		"doctype": "YRP Delivery Challan",
		"fields": (
			"posting_date",
			"posting_time",
			"process_name",
			"supplier",
			"work_order",
			"purchase_order",
			"total_delivered_qty",
		),
		"order_by": "posting_date desc, posting_time desc, modified desc",
	},
}
DETAIL_FIELDS = {
	"YRP Work Order": (
		"process_name",
		"supplier",
		"wo_date",
		"expected_delivery_date",
		"open_status",
		"item",
		"comments",
	),
	"Purchase Order": (
		"supplier",
		"transaction_date",
		"schedule_date",
		"status",
		"currency",
		"set_warehouse",
		"comments",
	),
	"YRP Goods Received Note": (
		"against",
		"against_id",
		"delivery_challan",
		"process_name",
		"supplier",
		"posting_date",
		"posting_time",
		"supplier_document_no",
		"vehicle_no",
		"is_return",
		"comments",
	),
	"YRP Delivery Challan": (
		"work_order",
		"purchase_order",
		"process_name",
		"supplier",
		"from_warehouse",
		"to_warehouse",
		"posting_date",
		"posting_time",
		"vehicle_no",
		"comments",
	),
}
SUMMARY_FIELDS = {
	"YRP Work Order": (
		("planned_quantity", "Planned qty"),
		("total_quantity", "Total qty"),
		("total_no_of_pieces_delivered", "Pieces delivered"),
		("total_no_of_pieces_received", "Pieces received"),
	),
	"Purchase Order": (("lot_qty", "Lot qty"), ("total_qty", "Total qty"), ("grand_total", "Grand total")),
	"YRP Goods Received Note": (("total_received_quantity", "Received qty"), ("total", "Total value")),
	"YRP Delivery Challan": (("total_delivered_qty", "Delivered qty"), ("stock_value", "Total value")),
}
CHILD_LINKS = {
	"Purchase Order": (("SD YRP Lot MultiSelect", "sd_lot"), ("Purchase Order Item", "items")),
	"YRP Goods Received Note": (("YRP Goods Received Note Item", "items"),),
	"YRP Delivery Challan": (("YRP Delivery Challan Item", "items"),),
	"YRP Work Order": (),
}


def _check_lot_permission(lot):
	frappe.get_doc("SD YRP Lot", lot).check_permission("read")


def _require_lot_field(doctype, fieldname="lot"):
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field or field.fieldtype != "Link" or field.options != "SD YRP Lot":
		frappe.throw(f"{doctype}.{fieldname} must link to SD YRP Lot.")


def _linked_names(lot, doctype):
	fields = ["lot", "default_lot"] if doctype == "Purchase Order" else ["lot"]
	for fieldname in fields:
		_require_lot_field(doctype, fieldname)
	names = set(
		frappe.get_all(
			doctype, or_filters={field: lot for field in fields}, pluck="name", limit_page_length=0
		)
	)
	for child_doctype, parentfield in CHILD_LINKS[doctype]:
		_require_lot_field(child_doctype)
		names.update(
			frappe.get_all(
				child_doctype,
				filters={"lot": lot, "parenttype": doctype, "parentfield": parentfield},
				pluck="parent",
				limit_page_length=0,
			)
		)
	return sorted(names)


def _visible_section(lot, section):
	doctype = section["doctype"]
	if not frappe.has_permission(doctype, "read"):
		return {"permitted": False, "count": 0, "rows": []}
	names = _linked_names(lot, doctype)
	if not names:
		return {"permitted": True, "count": 0, "rows": []}
	filters = {"name": ["in", names], "docstatus": ["!=", 2]}
	rows = frappe.get_list(
		doctype,
		filters=filters,
		fields=["name", "docstatus", "modified", *section["fields"]],
		order_by=section["order_by"],
		limit_page_length=500,
	)
	count = frappe.get_list(
		doctype, filters=filters, fields=[{"COUNT": "name", "as": "count"}], order_by="", limit_page_length=1
	)
	return {"permitted": True, "count": cint(count[0].count), "rows": [dict(row) for row in rows]}


def _purchase_order_quantities(lot, names):
	if not names:
		return {}
	_require_lot_field("Purchase Order Item")
	items = frappe.qb.DocType("Purchase Order Item")
	rows = (
		frappe.qb.from_(items)
		.select(items.parent, Sum(items.qty).as_("lot_qty"))
		.where((items.lot == lot) & items.parent.isin(names) & (items.parenttype == "Purchase Order"))
		.groupby(items.parent)
		.run(as_dict=True)
	)
	return {row.parent: flt(row.lot_qty) for row in rows}


def _supplier_names(rows):
	names = sorted({row["supplier"] for row in rows if row.get("supplier")})
	if not names:
		return {}
	return {
		row.name: row.supplier_name
		for row in frappe.get_all(
			"Supplier", filters={"name": ["in", names]}, fields=["name", "supplier_name"], limit_page_length=0
		)
	}


@frappe.whitelist()
def get_lot_documents(lot: str) -> dict:
	"""List readable Purchase documents linked to a Lot."""
	_check_lot_permission(lot)
	sections = {key: _visible_section(lot, section) for key, section in DOCUMENT_SECTIONS.items()}
	purchase_orders = sections["purchase_orders"]["rows"]
	quantities = _purchase_order_quantities(lot, [row["name"] for row in purchase_orders])
	for row in purchase_orders:
		row["lot_qty"] = quantities.get(row["name"], 0)
	transactions = sections["goods_received_notes"]["rows"] + sections["delivery_challans"]["rows"]
	suppliers = _supplier_names(transactions)
	for row in transactions:
		row.update(
			status=_document_status(frappe._dict(row)), supplier_name=suppliers.get(row.get("supplier"), "")
		)
	return sections


def _is_linked(doc, lot):
	_require_lot_field(doc.doctype)
	if doc.get("lot") == lot:
		return True
	if doc.doctype == "Purchase Order":
		_require_lot_field(doc.doctype, "default_lot")
		if doc.get("default_lot") == lot:
			return True
	for child_doctype, parentfield in CHILD_LINKS[doc.doctype]:
		_require_lot_field(child_doctype)
		if any(row.get("lot") == lot for row in doc.get(parentfield) or []):
			return True
	return False


def _document_payload(doc):
	if doc.doctype == "Purchase Order":
		return get_purchase_order_workspace(doc.name)
	if doc.doctype != "YRP Work Order":
		return get_document(doc.doctype, doc.name)
	rows = doc.get("deliverables") or []
	return {
		"record": {
			"doctype": doc.doctype,
			"name": doc.name,
			"docstatus": doc.docstatus,
			"status": doc.status,
			"modified": doc.modified,
		},
		"details": get_effective_fields(doc, DETAIL_FIELDS[doc.doctype]),
		"deliverables": group_items_for_ui(rows, "YRP Work Order Deliverables"),
		"item_row_count": len(rows),
	}


def _summary(doc, lot):
	quantities = _purchase_order_quantities(lot, [doc.name]) if doc.doctype == "Purchase Order" else {}
	return [
		{
			"fieldname": field,
			"label": label,
			"value": quantities.get(doc.name, 0) if field == "lot_qty" else doc.get(field),
			"fieldtype": "Currency" if field in {"grand_total", "total", "stock_value"} else "Float",
		}
		for field, label in SUMMARY_FIELDS[doc.doctype]
	]


def _detail_link_names(details, doctype):
	return {
		field["value"]
		for field in details
		if field["fieldtype"] == "Link" and field.get("options") == doctype and field.get("value")
	}


def _detail_link_titles(details, supplier):
	titles = {}
	for doctype, title_field in (("Supplier", "supplier_name"), ("Warehouse", "warehouse_name")):
		names = _detail_link_names(details, doctype)
		if doctype == "Supplier" and supplier:
			names.add(supplier)
		titles[doctype] = (
			{
				row.name: row[title_field]
				for row in frappe.get_all(
					doctype,
					filters={"name": ["in", sorted(names)]},
					fields=["name", title_field],
					limit_page_length=0,
				)
			}
			if names
			else {}
		)
	return titles


def _document_currency(doc):
	if doc.doctype == "Purchase Order":
		return doc.currency
	if not doc.meta.get_field("company"):
		return frappe.db.get_default("currency")
	return frappe.get_cached_value("Company", doc.get("company"), "default_currency")


def _dialog_payload(doc, lot):
	payload = _document_payload(doc)
	fields = {field["fieldname"]: field for field in payload["details"]}
	if doc.doctype == "Purchase Order":
		fields.update({field["fieldname"]: field for field in get_effective_fields(doc, ("status",))})
	details = [fields[field] for field in DETAIL_FIELDS[doc.doctype] if field in fields]
	supplier = doc.get("supplier")
	titles = _detail_link_titles(details, supplier)
	for field in details:
		if field["fieldtype"] == "Link" and field.get("options") in titles:
			field["display_value"] = titles[field["options"]].get(field["value"], "")
	supplier_name = doc.get("supplier_name") if doc.doctype in {"YRP Work Order", "Purchase Order"} else None
	payload["record"].update(
		supplier=supplier,
		supplier_name=supplier_name or titles["Supplier"].get(supplier, ""),
	)
	if doc.doctype != "YRP Work Order":
		payload["record"]["currency"] = _document_currency(doc)
	matrix_key = "deliverables" if doc.doctype == "YRP Work Order" else "item_groups"
	return {
		"record": payload["record"],
		"details": details,
		"summary": _summary(doc, lot),
		"item_row_count": payload["item_row_count"],
		matrix_key: payload[matrix_key],
	}


@frappe.whitelist()
def get_lot_document(lot: str, doctype: str, name: str) -> dict:
	"""Load one readable linked document for a read-only dialog."""
	_check_lot_permission(lot)
	if doctype not in DETAIL_FIELDS:
		frappe.throw("Unsupported Lot document type.", frappe.PermissionError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	if not _is_linked(doc, lot):
		frappe.throw("This document is not linked to the Lot.", frappe.PermissionError)
	return _dialog_payload(doc, lot)
