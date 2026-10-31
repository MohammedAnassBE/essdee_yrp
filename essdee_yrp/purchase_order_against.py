import frappe
from frappe import _
from frappe.utils import cint, flt

from essdee_yrp.purchase_order_approval import MRP_SETTINGS_DOCTYPE, get_approval_item_codes

PRODUCTION_ORDER_DOCTYPE = "YRP Production Order"
AGAINST_FIELDS = ("against", "against_id")
SUPPORTED_AGAINST_DOCTYPES = {PRODUCTION_ORDER_DOCTYPE}
DEFAULT_APPROVAL_ITEM_LIMIT_KG = 500
KG_UOM = "Kg"


def is_open_production_order(production_order) -> bool:
	"""A submitted Production Order that Finishing has not closed."""
	return cint(production_order.docstatus) == 1 and production_order.get("status") != "Closed"


def can_create_purchase_order_against(production_order) -> bool:
	return is_open_production_order(production_order) and bool(
		frappe.has_permission("Purchase Order", ptype="create")
	)


def get_purchase_order_against(against, against_id) -> dict:
	"""Validate a Purchase Order source reference and return its field values."""
	if not against and not against_id:
		return {}
	if against not in SUPPORTED_AGAINST_DOCTYPES or not against_id:
		frappe.throw(_("A Purchase Order can only be created against a Production Order."))
	if not frappe.db.exists(against, against_id):
		frappe.throw(_("{0} {1} does not exist.").format(_(against), against_id), frappe.DoesNotExistError)
	production_order = frappe.get_doc(against, against_id)
	production_order.check_permission("read")
	if not is_open_production_order(production_order):
		frappe.throw(
			_("Production Order {0} is {1}. Purchase Orders can only be created against an open, submitted Production Order.").format(
				against_id,
				_("Cancelled") if cint(production_order.docstatus) == 2 else production_order.get("status") or _("Draft"),
			)
		)
	return {"against": against, "against_id": against_id}


def get_against_reference(values) -> tuple:
	return tuple(values.get(fieldname) or None for fieldname in AGAINST_FIELDS) if values else (None, None)


def validate_new_purchase_order_against(doc, method=None) -> None:
	"""before_insert: a fresh Purchase Order may only reference an open Production Order.

	An amendment may keep the reference of its cancelled original unchanged.
	"""
	reference = get_against_reference(doc)
	if doc.get("amended_from"):
		original = frappe.db.get_value("Purchase Order", doc.amended_from, AGAINST_FIELDS, as_dict=True)
		if get_against_reference(original) == reference:
			return
	get_purchase_order_against(*reference)


def validate_purchase_order_against_unchanged(doc, method=None) -> None:
	"""validate / before_update_after_submit: Against and Against ID are fixed once inserted."""
	if doc.flags.in_insert or doc.is_new():
		return
	stored = frappe.db.get_value("Purchase Order", doc.name, AGAINST_FIELDS, as_dict=True)
	if stored is not None and get_against_reference(stored) != get_against_reference(doc):
		frappe.throw(_("Against and Against ID cannot be changed after the Purchase Order is created."))


def get_purchase_orders_against(against: str, against_id: str) -> list[dict]:
	"""Linked Purchase Orders the current user can read."""
	if not (
		frappe.has_permission("Purchase Order", ptype="read")
		and frappe.has_permission("Purchase Order", ptype="select")
	):
		return []
	rows = frappe.get_list(
		"Purchase Order",
		filters={"against": against, "against_id": against_id},
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
	if cint(doc.docstatus) != 0 or doc.get("against_id"):
		return
	limit = get_approval_item_limit_kg()
	quantity = round(get_approval_item_quantity_in_kg(doc), 3)
	if quantity > limit:
		frappe.throw(
			_("{0} kg of approval items exceeds the {1} kg limit for a Purchase Order not raised against a Production Order.").format(
				f"{quantity:g}", f"{limit:g}"
			)
		)
