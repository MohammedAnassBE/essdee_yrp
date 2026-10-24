"""/web editor for SD YRP Item Conversion: one From item consumed, one To item produced."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, nowtime
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item.yrp_item import get_attribute_details

from essdee_yrp.fabric_store.documents.common import assert_expected_modified, get_document_permissions
from essdee_yrp.print_registry import get_document_print_formats

DOCTYPE = "SD YRP Item Conversion"
HEADER_FIELDS = ("warehouse", "posting_date", "posting_time", "comments")
SIDES = {
	"from": {
		"item_field": "from_item",
		"table": "from_items",
		"details": "from_item_details",
		"label": _("From"),
	},
	"to": {"item_field": "to_item", "table": "to_items", "details": "to_item_details", "label": _("To")},
}
SIDE_ROW_FIELDS = (
	"lot",
	"received_type",
	"uom",
	"qty",
	"secondary_qty",
	"secondary_uom",
	"stock_qty",
	"stock_uom",
	"rate",
	"amount",
	"remarks",
)
TOTAL_FIELDS = ("from_total_amount", "to_total_amount", "difference_amount")
LIFECYCLE_DOCSTATUS = {"submit": 0, "cancel": 1, "amend": 2}


@frappe.whitelist()
def get_item_conversion(name: str | None = None) -> dict:
	"""Return a new or existing Item Conversion as two plain sides plus header values."""
	if not name:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		return {
			"doctype": DOCTYPE,
			"record": {"name": "", "docstatus": 0, "status": _("Draft"), "modified": None},
			"values": {"posting_date": nowdate(), "posting_time": nowtime(), "warehouse": "", "comments": ""},
			"sides": {"from": {}, "to": {}},
			"totals": dict.fromkeys(TOTAL_FIELDS, 0),
			"permissions": {
				"can_create": True,
				"can_write": False,
				"can_submit": bool(frappe.has_permission(DOCTYPE, ptype="submit")),
			},
			"print_formats": [],
		}
	doc = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
	return {
		"doctype": DOCTYPE,
		"record": {
			"name": doc.name,
			"docstatus": cint(doc.docstatus),
			"status": {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}[cint(doc.docstatus)],
			"modified": str(doc.modified),
			"amended_from": doc.amended_from,
		},
		"values": {fieldname: doc.get(fieldname) for fieldname in HEADER_FIELDS},
		"sides": {key: get_side(doc, side) for key, side in SIDES.items()},
		"totals": {fieldname: flt(doc.get(fieldname)) for fieldname in TOTAL_FIELDS},
		"permissions": {
			**get_document_permissions(DOCTYPE, doc),
			"can_delete": bool(
				cint(doc.docstatus) != 1 and frappe.has_permission(DOCTYPE, ptype="delete", doc=doc)
			),
		},
		"print_formats": get_document_print_formats(doc),
	}


def get_side(doc, side: dict) -> dict:
	"""Project the single row of one side into template, attributes and size."""
	rows = doc.get(side["table"]) or []
	if not rows:
		return {"item": doc.get(side["item_field"]) or ""}
	row = rows[0]
	variant = frappe.get_cached_doc("Item", row.item)
	template = variant.variant_of or variant.name
	details = get_attribute_details(template)
	values = {entry.attribute: attribute_value(entry.attribute_value) for entry in variant.attributes}
	primary_attribute = details.get("primary_attribute")
	return {
		"item": template,
		"variant": row.item,
		"attributes": {
			attribute: values[attribute]
			for attribute in details.get("attributes") or []
			if values.get(attribute)
		},
		"primary_value": values.get(primary_attribute) if primary_attribute else None,
		**{fieldname: row.get(fieldname) for fieldname in SIDE_ROW_FIELDS},
	}


@frappe.whitelist()
def get_item_conversion_item_schema(item: str) -> dict:
	"""Return the template's attributes, sizes and UOMs for a side card."""
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	if not item:
		frappe.throw(_("Item is required."))
	from essdee_yrp.cutting.web_workspace import _get_stock_item_schema_data

	return _get_stock_item_schema_data(item)


def get_side_item_details(side_key: str, side: dict) -> list[dict]:
	"""Build the grouped item JSON the Desk component sends for one side."""
	label = SIDES[side_key]["label"]
	template = side.get("item")
	if not template:
		frappe.throw(_("Select the {0} Item.").format(label))
	if flt(side.get("qty")) <= 0:
		frappe.throw(_("Enter the {0} Quantity.").format(label))
	details = get_attribute_details(template)
	primary_attribute = details.get("primary_attribute")
	if primary_attribute and not side.get("primary_value"):
		frappe.throw(_("Select the {0} {1}.").format(label, primary_attribute))
	attributes = side.get("attributes") or {}
	item = {
		"name": template,
		"lot": side.get("lot"),
		"attributes": {
			attribute: attributes[attribute]
			for attribute in details.get("attributes") or []
			if attributes.get(attribute)
		},
		"primary_attribute": primary_attribute,
		"values": {
			(side["primary_value"] if primary_attribute else "default"): {
				"qty": flt(side.get("qty")),
				"rate": 0,
				"secondary_qty": flt(side.get("secondary_qty")),
			}
		},
		"default_uom": details.get("default_uom"),
		"secondary_uom": details.get("secondary_uom"),
		"received_type": side.get("received_type"),
		"remarks": side.get("remarks"),
	}
	return [
		{
			"attributes": details.get("attributes") or [],
			"primary_attribute": primary_attribute,
			"primary_attribute_values": details.get("primary_attribute_values") or [],
			"items": [item],
		}
	]


@frappe.whitelist()
def save_item_conversion(
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	"""Save, and optionally submit, an Item Conversion through its Desk controller."""
	values = values if isinstance(values, dict) else frappe.parse_json(values or "{}")
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
		assert_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft documents can be edited."))
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
	doc.update({fieldname: values.get(fieldname) for fieldname in HEADER_FIELDS if fieldname in values})
	for key, side in SIDES.items():
		side_values = values.get(key) or {}
		doc.set(side["item_field"], side_values.get("item"))
		doc.set(side["details"], frappe.as_json(get_side_item_details(key, side_values)))
	if name:
		doc.save()
	else:
		doc.insert()
	if cint(submit):
		frappe.has_permission(DOCTYPE, ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_item_conversion(doc.name)


@frappe.whitelist()
def change_item_conversion_status(name: str, action: str, expected_modified: str | None = None) -> dict:
	"""Submit, cancel or amend an Item Conversion like the Desk buttons."""
	if action not in LIFECYCLE_DOCSTATUS:
		frappe.throw(_("Unsupported document action: {0}").format(action))
	doc = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype=action, doc=doc, throw=True)
	assert_expected_modified(doc, expected_modified)
	if cint(doc.docstatus) != LIFECYCLE_DOCSTATUS[action]:
		frappe.throw(_("{0} cannot be {1} from its current state.").format(doc.name, action))
	if action == "submit":
		doc.submit()
	elif action == "cancel":
		doc.cancel()
	else:
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.insert()
		name = amended.name
	return get_item_conversion(name)
