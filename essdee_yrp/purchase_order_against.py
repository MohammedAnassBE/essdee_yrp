import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.purchase_order_approval import MRP_SETTINGS_DOCTYPE, get_approval_item_codes

PRODUCTION_ORDER_DOCTYPE = "YRP Production Order"
PRODUCTION_ORDERS_FIELD = "production_orders"
PRODUCTION_ORDER_ROW_DOCTYPE = "SD YRP Purchase Order Production Order"
YRP_PURCHASE_ORDER_SERIES = "YRP-PO-.YYYY.-"
DEFAULT_APPROVAL_ITEM_LIMIT_KG = 500
KG_UOM = "Kg"


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
		frappe.throw(_("Production Orders cannot be changed after the Purchase Order is created."))


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


def get_approval_item_limit_kg() -> float:
	"""The settings limit; an unset single Float reads as 0, so 0 means the default."""
	value = flt(frappe.db.get_single_value(MRP_SETTINGS_DOCTYPE, "max_approval_item_kg_without_production_order"))
	return value if value > 0 else DEFAULT_APPROVAL_ITEM_LIMIT_KG


def get_row_quantity_in_kg(row) -> float:
	"""Row quantity in Kg from its stock UOM; a UOM with no Kg conversion fails loudly."""
	stock_qty = flt(row.get("stock_qty")) or flt(row.get("qty")) * (flt(row.get("conversion_factor")) or 1)
	stock_uom = row.get("stock_uom") or row.get("uom")
	if stock_uom == KG_UOM:
		return stock_qty
	to_kg = frappe.db.get_value("UOM Conversion Factor", {"from_uom": stock_uom, "to_uom": KG_UOM}, "value")
	if to_kg:
		return stock_qty * flt(to_kg)
	from_kg = frappe.db.get_value("UOM Conversion Factor", {"from_uom": KG_UOM, "to_uom": stock_uom}, "value")
	if from_kg:
		return stock_qty / flt(from_kg)
	frappe.throw(
		_("Row #{0}: approval Item {1} is in UOM {2}, which cannot be converted to Kg.").format(
			row.get("idx"), frappe.bold(row.get("item_code")), frappe.bold(stock_uom)
		)
	)


def get_approval_item_quantity_in_kg(doc) -> float:
	rows = doc.get("items") or []
	approval_items = get_approval_item_codes(row.get("item_code") for row in rows)
	return sum(get_row_quantity_in_kg(row) for row in rows if row.get("item_code") in approval_items)


def validate_approval_item_limit_without_production_order(doc, method=None) -> None:
	"""validate: a draft not raised against a Production Order may order at most the approval item limit."""
	if cint(doc.docstatus) != 0 or doc.get(PRODUCTION_ORDERS_FIELD):
		return
	limit = get_approval_item_limit_kg()
	quantity = round(get_approval_item_quantity_in_kg(doc), 3)
	if quantity > limit:
		frappe.throw(
			_("{0} kg of approval items exceeds the {1} kg limit for a Purchase Order not raised against a Production Order.").format(
				f"{quantity:g}", f"{limit:g}"
			)
		)
