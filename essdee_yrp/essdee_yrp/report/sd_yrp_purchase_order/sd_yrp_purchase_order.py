"""The MRP saved PURCHASE ORDER view over migrated Purchase Order fields.

ERPNext's status describes billing/receipt workflow. MRP's saved status column
instead describes fulfillment; keep its original labels and date field alias.
"""

import frappe
from frappe import _
from frappe.query_builder import Case
from frappe.query_builder.functions import Coalesce, NullIf

LEGACY_STATUS = {"Received": "Delivered", "Partially Received": "Partially Delivered"}
STATUS_OPTIONS = (
	"Draft\nPending Approval\nOrdered\nPartially Delivered\nDelivered\nCancelled\n"
	"Partially Cancelled\nOverdue\nClosed"
)


def legacy_rows(rows):
	result = []
	for row in rows:
		status = row.yrp_fulfillment_status or row.status
		# Migration stores Pending Approval as Draft fulfillment, retaining the
		# approval state in ERPNext's status. Don't turn an approval request into Draft.
		if row.status == "Pending Approval":
			status = row.status
		result.append(
			dict(
				name=row.name,
				docstatus=row.docstatus,
				supplier=row.supplier,
				po_date=row.transaction_date,
				open_status="Closed" if row.open_status == "Close" else row.open_status,
				status=LEGACY_STATUS.get(status, status),
			)
		)
	return result


def execute(filters=None):
	filters = frappe._dict(filters or {})
	frappe.has_permission("Purchase Order", "report", throw=True)
	query_filters = {}
	open_status = filters.get("open_status", "Open")
	if open_status:
		query_filters["open_status"] = "Close" if open_status == "Closed" else open_status
	for source, target in (
		("name", "name"),
		("supplier", "supplier"),
		("po_date", "transaction_date"),
		("docstatus", "docstatus"),
	):
		if filters.get(source) is not None and filters.get(source) != "":
			query_filters[target] = filters[source]
	query = frappe.qb.get_query(
		"Purchase Order",
		filters=query_filters,
		fields=[
			"name",
			"docstatus",
			"supplier",
			"transaction_date",
			"open_status",
			"status",
			"yrp_fulfillment_status",
		],
		order_by="modified asc",
		limit=500,
		ignore_permissions=False,
	)
	if status := filters.get("status"):
		po = frappe.qb.DocType("Purchase Order")
		# Apply the same fallback, approval override and labels as legacy_rows,
		# before the saved view's 500-row limit and with user permissions intact.
		effective = (
			Case()
			.when(po.status == "Pending Approval", po.status)
			.else_(Coalesce(NullIf(po.yrp_fulfillment_status, ""), po.status))
		)
		legacy_status = Case()
		for stored, displayed in LEGACY_STATUS.items():
			legacy_status = legacy_status.when(effective == stored, displayed)
		query = query.where(legacy_status.else_(effective) == status)
	rows = query.run(as_dict=True)
	columns = [
		dict(fieldname="name", label=_("ID"), fieldtype="Link", options="Purchase Order", width=191),
		dict(fieldname="supplier", label=_("Supplier"), fieldtype="Link", options="Supplier", width=208),
		dict(fieldname="po_date", label=_("PO Date"), fieldtype="Date", width=120),
		dict(
			fieldname="open_status",
			label=_("Open Status"),
			fieldtype="Select",
			options="Open\nClosed",
			width=97,
		),
		dict(fieldname="status", label=_("Status"), fieldtype="Select", options=STATUS_OPTIONS, width=302),
	]
	return columns, legacy_rows(rows)
