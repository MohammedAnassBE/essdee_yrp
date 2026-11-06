import frappe
from frappe import _
from frappe.utils import cint

from essdee_yrp.purchase_order_approval import get_live_request

PRODUCTION_ORDER_DOCTYPE = "YRP Production Order"
PRODUCTION_ORDERS_FIELD = "production_orders"
PRODUCTION_ORDER_ROW_DOCTYPE = "SD YRP Purchase Order Production Order"
YRP_PURCHASE_ORDER_SERIES = "YRP-PO-.YYYY.-"


def is_open_production_order(production_order) -> bool:
	"""A submitted Production Order that Finishing has not closed."""
	return cint(production_order.docstatus) == 1 and production_order.get("status") != "Closed"


def can_create_purchase_order_against(production_order) -> bool:
	return is_open_production_order(production_order) and bool(
		frappe.has_permission("Purchase Order", ptype="create")
	)


def get_production_order_names(rows) -> list:
	"""Production Order names from table rows or plain names, in order."""
	return [row.get("production_order") if hasattr(row, "get") else row for row in rows or []]


def get_production_order_row(name) -> dict:
	"""Validate one source Production Order and return its table row."""
	if not name:
		frappe.throw(_("Select a Production Order for every Purchase Order source row."))
	if not frappe.db.exists(PRODUCTION_ORDER_DOCTYPE, name):
		frappe.throw(_("{0} {1} does not exist.").format(_(PRODUCTION_ORDER_DOCTYPE), name), frappe.DoesNotExistError)
	production_order = frappe.get_doc(PRODUCTION_ORDER_DOCTYPE, name)
	production_order.check_permission("read")
	if not is_open_production_order(production_order):
		frappe.throw(
			_("Production Order {0} is {1}. Purchase Orders can only be created against an open, submitted Production Order.").format(
				name,
				_("Cancelled") if cint(production_order.docstatus) == 2 else production_order.get("status") or _("Draft"),
			)
		)
	return {"production_order": name, "item_name": production_order.get("item")}


def get_production_order_rows(production_orders) -> list[dict]:
	"""Validate the Production Orders a Purchase Order is raised against and return its table rows."""
	names = get_production_order_names(production_orders)
	duplicates = sorted({name for name in names if name and names.count(name) > 1})
	if duplicates:
		frappe.throw(_("Production Order {0} is selected more than once.").format(", ".join(duplicates)))
	return [get_production_order_row(name) for name in names]


def get_production_order_table(doc) -> list[dict]:
	return [
		{"production_order": row.get("production_order"), "item_name": row.get("item_name")}
		for row in doc.get(PRODUCTION_ORDERS_FIELD) or []
	]


def get_stored_production_orders(purchase_order) -> list:
	return frappe.get_all(
		PRODUCTION_ORDER_ROW_DOCTYPE,
		filters={"parenttype": "Purchase Order", "parentfield": PRODUCTION_ORDERS_FIELD, "parent": purchase_order},
		pluck="production_order",
		order_by="idx asc",
	)


@frappe.whitelist()
def make_purchase_order(production_orders) -> dict:
	"""Unsaved Purchase Order raised against one or more open Production Orders."""
	frappe.has_permission("Purchase Order", ptype="create", throw=True)
	rows = get_production_order_rows(frappe.parse_json(production_orders))
	if not rows:
		frappe.throw(_("Select at least one Production Order."))
	doc = frappe.new_doc("Purchase Order")
	doc.is_yrp_managed = 1
	doc.naming_series = YRP_PURCHASE_ORDER_SERIES
	doc.set(PRODUCTION_ORDERS_FIELD, rows)
	return doc.as_dict()


def validate_new_purchase_order_against(doc, method=None) -> None:
	"""before_insert: a fresh Purchase Order may only reference open Production Orders.

	An amendment may keep the Production Orders of its cancelled original unchanged.
	"""
	names = get_production_order_names(doc.get(PRODUCTION_ORDERS_FIELD))
	if doc.get("amended_from") and names == get_stored_production_orders(doc.amended_from):
		return
	doc.set(PRODUCTION_ORDERS_FIELD, get_production_order_rows(names))


def validate_purchase_order_against_unchanged(doc, method=None) -> None:
	"""validate / before_update_after_submit: Production Orders are fixed once inserted."""
	if doc.flags.in_insert or doc.is_new():
		return
	names = get_production_order_names(doc.get(PRODUCTION_ORDERS_FIELD))
	if names != get_stored_production_orders(doc.name):
		frappe.throw(_("Production Orders cannot be changed after the Purchase Order is created. Use the PPO button."))


def get_purchase_orders_against(production_order: str) -> list[dict]:
	"""Purchase Orders raised against a Production Order that the current user can read."""
	if not (
		frappe.has_permission("Purchase Order", ptype="read")
		and frappe.has_permission("Purchase Order", ptype="select")
	):
		return []
	names = frappe.get_all(
		PRODUCTION_ORDER_ROW_DOCTYPE,
		filters={"parenttype": "Purchase Order", "parentfield": PRODUCTION_ORDERS_FIELD, "production_order": production_order},
		pluck="parent",
	)
	if not names:
		return []
	rows = frappe.get_list(
		"Purchase Order",
		filters={"name": ["in", names]},
		fields=["name", "docstatus", "status", "supplier_name", "modified"],
		order_by="creation desc",
		limit_page_length=50,
	)
	return [row for row in rows if frappe.has_permission("Purchase Order", ptype="read", doc=row.name)]


def is_production_order_table_open(doc) -> bool:
	"""A Draft, or a submitted Development Purchase Order that has no Production Order linked yet."""
	if cint(doc.docstatus) == 0:
		return True
	return cint(doc.docstatus) == 1 and bool(doc.get("is_development")) and not doc.get(PRODUCTION_ORDERS_FIELD)


def can_manage_production_orders(doc) -> bool:
	"""Whether the PPO button applies: submit permission on an open Production Order table."""
	return bool(
		doc.get("is_yrp_managed")
		and is_production_order_table_open(doc)
		and frappe.has_permission("Purchase Order", ptype="submit", doc=doc)
	)


def can_remove_production_orders(doc) -> bool:
	"""Linked Production Orders are fixed once submitted or sent for Telegram approval."""
	return bool(cint(doc.docstatus) == 0 and can_manage_production_orders(doc) and not get_live_request(doc.name))


def set_production_order_onload(doc, method=None) -> None:
	"""onload: tell the Desk form whether the PPO button applies."""
	doc.set_onload("can_manage_production_orders", can_manage_production_orders(doc))
	doc.set_onload("can_remove_production_orders", can_remove_production_orders(doc))


def get_production_order_options(txt="", page_length=20) -> list[dict]:
	"""Open Production Orders the user can read, matched on ID or Item."""
	like = f"%{(txt or '').strip()}%"
	return frappe.get_list(
		PRODUCTION_ORDER_DOCTYPE,
		filters={"docstatus": 1, "status": ["!=", "Closed"]},
		or_filters=[["name", "like", like], ["item", "like", like]],
		fields=["name", "item"],
		order_by="modified desc",
		limit_page_length=cint(page_length) or 20,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def production_order_query(doctype, txt, searchfield, start, page_len, filters):
	"""Desk Link query: Production Order ID with its Item."""
	return [(row.name, row.item) for row in get_production_order_options(txt, page_len)]


@frappe.whitelist()
def search_production_orders(txt="", page_length=20) -> list[dict]:
	"""/web Link search: Production Order ID labelled with its Item."""
	return [
		{"name": row.name, "label": row.name, "description": row.item or "", "item": row.item}
		for row in get_production_order_options(txt, page_length)
	]


@frappe.whitelist()
def get_purchase_order_production_order(production_order) -> dict:
	"""One validated table row (Production Order + Item Name) for the PPO dialog."""
	return get_production_order_row(production_order)


def get_managed_purchase_order(name):
	"""Lock and load a Purchase Order whose Production Orders the user may change."""
	frappe.db.get_value("Purchase Order", name, "name", for_update=True)
	doc = frappe.get_doc("Purchase Order", name)
	if cint(doc.docstatus) == 2:
		frappe.throw(_("Production Orders cannot be changed on a cancelled Purchase Order."))
	if not is_production_order_table_open(doc):
		frappe.throw(_("After submit, PPOs can be added only to a Development Purchase Order that has no PPO linked yet."))
	if not doc.get("is_yrp_managed"):
		frappe.throw(_("Production Orders can be linked only to YRP managed Purchase Orders."))
	if not frappe.has_permission("Purchase Order", ptype="submit", doc=doc):
		frappe.throw(_("Submit permission on Purchase Order {0} is required to change its Production Orders.").format(name), frappe.PermissionError)
	return doc


def validate_production_order_removal(doc) -> None:
	if cint(doc.docstatus) != 0:
		frappe.throw(_("PPOs cannot be removed after the Purchase Order is submitted."))
	live_request = get_live_request(doc.name)
	if live_request:
		frappe.throw(_("PPOs cannot be removed while Telegram approval request {0} is {1}.").format(live_request.name, live_request.status))


def get_requested_production_orders(production_orders) -> list[str]:
	requested = frappe.parse_json(production_orders) or []
	if not isinstance(requested, list):
		frappe.throw(_("Production Orders must be a list."))
	return list(dict.fromkeys(name for name in get_production_order_names(requested) if name))


def get_production_order_change_comment(added, removed) -> str:
	actions = []
	if added:
		actions.append(_("Added PPO {0}").format(", ".join(added)))
	if removed:
		actions.append(_("Removed PPO {0}").format(", ".join(removed)))
	return "<br>".join(frappe.utils.escape_html(action) for action in actions)


@frappe.whitelist()
def update_purchase_order_production_orders(name, production_orders) -> list[dict]:
	"""Set a Purchase Order's Production Orders; new ones must be open, duplicates are dropped.

	Draft: add and remove (no removal while a Telegram request is live). Submitted Development PO without
	PPOs: add only. Only the table rows are written, so the document validators and unrelated legacy
	Draft validations (e.g. a missing warehouse) are not re-run; a Version and a timeline comment record it.
	"""
	doc = get_managed_purchase_order(name)
	rows = {row.production_order: row for row in doc.get(PRODUCTION_ORDERS_FIELD) or []}
	names = get_requested_production_orders(production_orders)
	added = [production_order for production_order in names if production_order not in rows]
	removed = [production_order for production_order in rows if production_order not in names]
	if not added and not removed:
		return get_production_order_table(doc)
	if removed:
		validate_production_order_removal(doc)
	new_rows = {row["production_order"]: row for row in get_production_order_rows(added)}
	before = frappe.get_doc(doc.as_dict())
	for production_order in removed:
		frappe.db.delete(PRODUCTION_ORDER_ROW_DOCTYPE, rows[production_order].name)
	doc.set(PRODUCTION_ORDERS_FIELD, [rows.get(production_order) or new_rows[production_order] for production_order in names])
	for idx, row in enumerate(doc.get(PRODUCTION_ORDERS_FIELD), start=1):
		row.idx = idx
		if row.production_order in new_rows:
			row.db_insert()
		else:
			row.db_set("idx", idx, update_modified=False)
	doc.db_set("modified_by", frappe.session.user)
	version = frappe.new_doc("Version")
	if version.update_version_info(before, doc):
		version.insert(ignore_permissions=True)
	doc.add_comment("Comment", get_production_order_change_comment(added, removed))
	doc.notify_update()
	return get_production_order_table(doc)
