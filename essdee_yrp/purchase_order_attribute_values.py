"""Change variant attribute values on submitted YRP Purchase Order rows."""

import frappe
from frappe import _
from frappe.utils import cint, cstr, escape_html, flt, now_datetime
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item.yrp_item import (
	get_global_attribute_values,
	get_or_create_variant,
	validate_attribute_value,
)

SYSTEM_MANAGER_ROLE = "System Manager"
ROW_PAYLOAD_KEYS = {"name", "item_code", "qty", "attributes"}


def has_goods_receipt(purchase_order: str) -> bool:
	"""True when a non-cancelled YRP GRN or Purchase Receipt exists against the order."""
	return bool(
		frappe.db.exists(
			"YRP Goods Received Note",
			{"against": "Purchase Order", "against_id": purchase_order, "docstatus": ["<", 2]},
		)
		or frappe.db.exists(
			"Purchase Receipt Item",
			{"purchase_order": purchase_order, "docstatus": ["<", 2]},
		)
	)


def get_attribute_update_block_reason(doc) -> str:
	if SYSTEM_MANAGER_ROLE not in frappe.get_roles():
		return _("Only a System Manager can update attribute values.")
	if not doc.get("is_yrp_managed"):
		return _("Only YRP managed Purchase Orders support attribute updates.")
	if cint(doc.docstatus) != 1:
		return _("Only submitted Purchase Orders support attribute updates.")
	if has_goods_receipt(doc.name):
		return _("A Goods Received Note exists against this Purchase Order.")
	return ""


def can_update_attribute_values(doc) -> bool:
	return not get_attribute_update_block_reason(doc)


def _get_updatable_purchase_order(name: str):
	if SYSTEM_MANAGER_ROLE not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can update attribute values."), frappe.PermissionError)
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("read")
	reason = get_attribute_update_block_reason(doc)
	if reason:
		frappe.throw(reason)
	return doc


@frappe.whitelist()
def can_update_purchase_order_attribute_values(name: str) -> bool:
	doc = frappe.get_doc("Purchase Order", name)
	doc.check_permission("read")
	return can_update_attribute_values(doc)


def get_variant_attributes(item_code: str) -> dict:
	rows = frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": item_code, "parenttype": "Item", "parentfield": "attributes"},
		fields=["attribute", "attribute_value"],
		order_by="idx asc",
	)
	return {row.attribute: attribute_value(row.attribute_value) for row in rows}


def get_allowed_attribute_values(template) -> dict:
	"""Same value source as the PO editor search: the template mapping, else global values."""
	from yrp.yrp.doctype.yrp_item.yrp_item import _mapping_values

	allowed = {}
	for row in template.get("attributes") or []:
		numeric = cint(frappe.get_cached_value("Item Attribute", row.attribute, "numeric_values"))
		allowed[row.attribute] = (
			[] if numeric else (_mapping_values(row) or get_global_attribute_values(row.attribute))
		)
	return allowed


def get_row_attributes(row) -> dict:
	"""Return the editable attribute contract for one Purchase Order Item row."""
	template_name = frappe.db.get_value("Item", row.item_code, "variant_of")
	if not template_name:
		return {"template": "", "attributes": []}
	template = frappe.get_cached_doc("Item", template_name)
	allowed = get_allowed_attribute_values(template)
	current = get_variant_attributes(row.item_code)
	attributes = [
		{
			"attribute": attribute,
			"value": value,
			"options": allowed.get(attribute, []),
			"editable": attribute != template.dependent_attribute,
		}
		for attribute, value in current.items()
	]
	return {"template": template_name, "attributes": attributes}


@frappe.whitelist()
def get_purchase_order_attribute_rows(name: str) -> dict:
	doc = _get_updatable_purchase_order(name)
	rows = []
	for row in doc.get("items") or []:
		rows.append(
			{
				"name": row.name,
				"idx": row.idx,
				"item_code": row.item_code,
				"item_name": row.item_name,
				"qty": flt(row.qty),
				"uom": row.uom,
				"rate": flt(row.rate),
				"amount": flt(row.amount),
				**get_row_attributes(row),
			}
		)
	return {"name": doc.name, "modified": str(doc.modified), "rows": rows}


def _parse_rows(rows) -> list[dict]:
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Send at least one row to update."))
	for row in rows:
		if not isinstance(row, dict) or not row.get("name"):
			frappe.throw(_("Each row must name its Purchase Order Item."))
		unknown = set(row) - ROW_PAYLOAD_KEYS
		if unknown:
			frappe.throw(
				_("Only attribute values can change. Remove: {0}").format(", ".join(sorted(unknown)))
			)
	return rows


def _assert_row_unchanged(row, payload) -> None:
	if payload.get("item_code") and payload["item_code"] != row.item_code:
		frappe.throw(
			_("Row #{0} changed since it was opened. Reload the Purchase Order and try again.").format(
				row.idx
			)
		)
	if "qty" in payload and flt(payload["qty"]) != flt(row.qty):
		frappe.throw(_("Row #{0}: quantity cannot change while updating attribute values.").format(row.idx))


def _validate_attribute_value(row, attribute, value, allowed) -> None:
	if not value:
		frappe.throw(_("Row #{0}: {1} is required.").format(row.idx, attribute))
	options = allowed.get(attribute) or []
	if options and value not in options:
		frappe.throw(_("Row #{0}: {1} is not an allowed value for {2}.").format(row.idx, value, attribute))
	validate_attribute_value(attribute, value)


def get_target_attributes(row, payload) -> tuple[str, dict, dict]:
	"""Return (template, current, target) attributes after validating the requested changes."""
	contract = get_row_attributes(row)
	if not contract["template"]:
		frappe.throw(_("Row #{0}: {1} is not an Item variant.").format(row.idx, row.item_code))
	current = {entry["attribute"]: entry["value"] for entry in contract["attributes"]}
	editable = {entry["attribute"]: entry["options"] for entry in contract["attributes"] if entry["editable"]}
	requested = payload.get("attributes") or {}
	if not isinstance(requested, dict):
		frappe.throw(_("Row #{0}: attributes must be an object.").format(row.idx))
	target = dict(current)
	for attribute, value in requested.items():
		value = attribute_value(value)
		if attribute not in editable:
			if current.get(attribute) == value:
				continue
			frappe.throw(_("Row #{0}: {1} cannot be changed here.").format(row.idx, attribute))
		_validate_attribute_value(row, attribute, value, editable)
		target[attribute] = value
	return contract["template"], current, target


def get_new_item_code(row, template: str, target: dict) -> str:
	item_code = get_or_create_variant(template, target)
	saved = {key: cstr(value) for key, value in get_variant_attributes(item_code or "").items()}
	if not item_code or saved != {key: cstr(value) for key, value in target.items()}:
		frappe.throw(
			_("Row #{0}: no variant of {1} matches {2}.").format(row.idx, template, format_attributes(target))
		)
	if cint(frappe.db.get_value("Item", item_code, "disabled")):
		frappe.throw(_("Row #{0}: Item {1} is disabled.").format(row.idx, item_code))
	return item_code


def set_row_item(row, item_code: str) -> None:
	item = frappe.db.get_value("Item", item_code, ["item_name", "description"], as_dict=True)
	frappe.db.set_value(
		"Purchase Order Item",
		row.name,
		{"item_code": item_code, "item_name": item.item_name, "description": item.description},
		update_modified=False,
	)


def format_attributes(attributes: dict) -> str:
	return ", ".join(f"{key}: {value}" for key, value in attributes.items())


def add_change_comment(doc, changes: list[dict]) -> None:
	lines = [_("Attribute values updated:")]
	for change in changes:
		lines.append(
			_("Row #{0}: {1} ({2}) → {3} ({4})").format(
				change["idx"],
				change["old_item_code"],
				format_attributes(change["old_attributes"]),
				change["new_item_code"],
				format_attributes(change["new_attributes"]),
			)
		)
	doc.add_comment("Comment", text="<br>".join(escape_html(line) for line in lines))


@frappe.whitelist(methods=["POST"])
def update_purchase_order_attribute_values(name: str, rows) -> dict:
	"""Swap row variants for the chosen attribute values; quantity, rate and amount stay as saved."""
	frappe.db.get_value("Purchase Order", name, "name", for_update=True)
	doc = _get_updatable_purchase_order(name)
	doc_rows = {row.name: row for row in doc.get("items") or []}
	changes = []
	for payload in _parse_rows(rows):
		row = doc_rows.get(payload["name"])
		if not row:
			frappe.throw(_("Row {0} does not belong to Purchase Order {1}.").format(payload["name"], name))
		_assert_row_unchanged(row, payload)
		template, current, target = get_target_attributes(row, payload)
		if target == current:
			continue
		new_item_code = get_new_item_code(row, template, target)
		set_row_item(row, new_item_code)
		changes.append(
			{
				"idx": row.idx,
				"old_item_code": row.item_code,
				"new_item_code": new_item_code,
				"old_attributes": current,
				"new_attributes": target,
			}
		)
	if changes:
		doc.db_set({"modified": now_datetime(), "modified_by": frappe.session.user}, update_modified=False)
		add_change_comment(doc, changes)
		doc.notify_update()
	return {"name": doc.name, "changes": changes}
