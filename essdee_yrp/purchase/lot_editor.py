import frappe
from frappe import _
from frappe.desk.form.load import run_onload
from yrp.attribute_links import value as attribute_value

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import get_colour_attribute
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import (
	check_enabled_po,
	fetch_order_item_details,
	get_isfinal_uom,
	get_item_details,
	get_packing_attributes,
)
from essdee_yrp.purchase.lot_workspace import get_lot_workspace
from essdee_yrp.web_common import assert_expected_modified, parse_mapping, permission_flags

EDITABLE_FIELDS = (
	"lot_name", "production_order", "item", "production_detail", "assigned_person", "season",
	"expected_delivery_date", "status", "size_set_colour", "capacity_planning", "primary_item_attribute",
)
IPD_DERIVED = {
	"uom": "uom", "pack_in_stage": "pack_in_stage", "packing_uom": "packing_uom",
	"pack_out_stage": "pack_out_stage", "dependent_attribute_mapping": "dependent_attr_mapping",
	"tech_pack_version": "tech_pack_version", "pattern_version": "pattern_version", "packing_combo": "packing_combo",
}
DERIVED_FIELDS = (
	"version", "uom", "pack_in_stage", "pack_out_stage", "packing_uom", "cloth_excess_percentage",
	"total_order_quantity", "total_quantity", "assigned_person_name", "is_transferred", "has_transferred", "transferred_lot",
)
FABRIC_FIELDS = ("name", "cloth_item", "production_detail", "plan_status", "plan_built_on", "plan_error")


def load_writable_lot(name=None):
	if name:
		doc = frappe.get_doc("SD YRP Lot", name)
		doc.check_permission("write")
		return doc
	frappe.has_permission("SD YRP Lot", ptype="create", throw=True)
	return frappe.new_doc("SD YRP Lot")


def check_context_permission():
	if not any(frappe.has_permission("SD YRP Lot", ptype=permission) for permission in ("create", "write")):
		frappe.throw(_("Not permitted to edit Lots."), frappe.PermissionError)


def _lot_locks(doc, ppo_mode, is_new):
	return {
		"lot_name": not is_new,
		"item": ppo_mode,
		"production_order": (not ppo_mode) or bool(doc.item and not doc.production_order),
		"order_details": bool(doc.lot_time_and_action_details) or bool(doc.is_transferred),
	}


def editor_field(doc, fieldname, locks, colour_options):
	field = doc.meta.get_field(fieldname)
	return {
		"fieldname": fieldname, "label": field.label, "fieldtype": field.fieldtype,
		"options": "\n".join(colour_options) if fieldname == "size_set_colour" else field.options,
		"reqd": bool(field.reqd), "read_only": bool(locks.get(fieldname)),
	}


def lot_onload(doc):
	run_onload(doc)
	return doc.get("__onload") or frappe._dict()


def form_item_details(doc, onload):
	details = onload.get("item_details")
	if details is None and doc.item and doc.production_detail:
		details = get_item_details(item_name=doc.item, uom=doc.uom,
			production_detail=doc.production_detail, ppo=doc.production_order)
	return details or None


def size_set_colour_options(doc):
	if doc.production_detail and doc.lot_order_details:
		return get_packing_attributes(doc.production_detail)["major_colours"]
	return []


def derived_values(doc):
	values = {field: doc.get(field) for field in DERIVED_FIELDS}
	for field in ("pack_in_stage", "pack_out_stage"):
		values[f"{field}_name"] = values[field]
		values[field] = attribute_value(values[field])
	return values


@frappe.whitelist()
def get_lot_form(name: str | None = None) -> dict:
	doc = load_writable_lot(name)
	message_start = len(frappe.get_message_log())
	ppo_mode = bool(check_enabled_po())
	locks = _lot_locks(doc, ppo_mode, not name)
	onload = lot_onload(doc)
	colours = size_set_colour_options(doc)
	item_details = form_item_details(doc, onload)
	return {
		"record": {"name": doc.name if name else "", "status": doc.status,
			"modified": str(doc.modified) if name else None},
		"values": {**{field: doc.get(field) for field in EDITABLE_FIELDS},
			"lot_fabric_details": [{field: row.get(field) for field in FABRIC_FIELDS}
				for row in doc.lot_fabric_details]},
		"derived": derived_values(doc),
		"fields": [editor_field(doc, field, locks, colours) for field in EDITABLE_FIELDS],
		"ppo_mode": ppo_mode, "locks": locks,
		"item_details": item_details,
		"item_details_generated": bool(name and onload.get("item_details") is None and item_details),
		"order_item_details": onload.get("order_item_details") or [],
		"size_set_colour_options": colours, "colour_attribute": get_colour_attribute(),
		"permissions": permission_flags("SD YRP Lot", ("write", "create"), doc),
		"messages": frappe.get_message_log()[message_start:],
	}


@frappe.whitelist()
def get_lot_production_detail_context(production_detail: str, item: str, production_order: str | None = None) -> dict:
	check_context_permission()
	if production_order:
		get_lot_production_order_item(production_order)
	message_start = len(frappe.get_message_log())
	context = get_isfinal_uom(production_detail, get_pack_stage=True)
	details = get_item_details(item_name=item, uom=context["uom"], production_detail=production_detail,
		dependent_attr_mapping=context.get("dependent_attr_mapping"), ppo=production_order)
	derived = {field: context.get(key) for field, key in IPD_DERIVED.items()}
	stages = frappe.db.get_value("YRP Item Production Detail", production_detail,
		["pack_in_stage", "pack_out_stage"], as_dict=True) or {}
	derived.update({f"{field}_name": stages.get(field) for field in ("pack_in_stage", "pack_out_stage")})
	return {"derived": derived,
		"item_details": details or None, "messages": frappe.get_message_log()[message_start:]}


@frappe.whitelist()
def get_lot_production_order_item(production_order: str) -> dict:
	check_context_permission()
	doc = frappe.get_doc("YRP Production Order", production_order)
	doc.check_permission("read")
	return {"item": doc.item}


def is_ppo_item_change(doc, values):
	production_order = values.get("production_order", doc.production_order)
	if production_order:
		return values["item"] == get_lot_production_order_item(production_order)["item"]
	return bool(doc.production_order) and not values["item"]


def is_locked_field_changed(doc, values, locks, field):
	return locks[field] and field in values and (values[field] or "") != (doc.get(field) or "")


def reject_locked_field(doc, values, field):
	if field == "item" and is_ppo_item_change(doc, values):
		return
	frappe.throw(_("{0} cannot be changed here.").format(doc.meta.get_label(field)))


def normalise_order_numbers(value):
	if isinstance(value, dict):
		return {key: normalise_order_numbers(child) for key, child in value.items()}
	if isinstance(value, list):
		return [normalise_order_numbers(child) for child in value]
	return float(value) if type(value) in (int, float) else value


def order_quantity_identity(cell):
	if not isinstance(cell, dict):
		return cell
	return {key: () if key == "qty" and (value is None or type(value) in (int, float)) else value
		for key, value in cell.items()}


def order_item_identity(item):
	if not isinstance(item, dict):
		return item
	identity = {key: value for key, value in item.items() if key != "total_qty"}
	if isinstance(identity.get("values"), dict):
		identity["values"] = {size: order_quantity_identity(cell) for size, cell in identity["values"].items()}
	return identity


def order_group_identity(group):
	if not isinstance(group, dict):
		return group
	identity = {key: value for key, value in group.items() if key not in ("total_sum", "size_wise_total")}
	if isinstance(identity.get("items"), list):
		identity["items"] = [order_item_identity(item) for item in identity["items"]]
	return identity


def reject_order_details_changes(doc, values, locked):
	incoming = values["order_item_details"]
	if not incoming:
		return
	stored = fetch_order_item_details(doc.lot_order_details, doc.production_detail) \
		if doc.lot_order_details and doc.production_detail else []
	if not locked:
		incoming = [order_group_identity(group) for group in incoming]
		stored = [order_group_identity(group) for group in stored]
	if normalise_order_numbers(incoming) != normalise_order_numbers(stored):
		message = _("Lot Order Details cannot be changed here.") if locked else \
			_("Lot Order Details rows cannot be added, removed or re-keyed here.")
		frappe.throw(message)


def _reject_locked_changes(doc, values, locks):
	for field in ("lot_name", "item", "production_order"):
		if is_locked_field_changed(doc, values, locks, field):
			reject_locked_field(doc, values, field)


def _apply_production_order(doc, values, ppo_mode):
	production_order = values.get("production_order", doc.production_order)
	if ppo_mode and production_order:
		item = get_lot_production_order_item(production_order)["item"]
		if values.get("item", item) != item:
			frappe.throw(_("Item must match the Production Order."))
		doc.item = item
		values["item"] = item
	elif doc.production_order and not production_order:
		values.update(item="", production_detail="")


def apply_editable_fields(doc, values, is_new):
	for field in EDITABLE_FIELDS:
		if field in values and (field != "lot_name" or is_new):
			doc.set(field, values[field])


def _apply_production_detail_defaults(doc, previous_ipd):
	if doc.production_detail == previous_ipd:
		return
	context = get_isfinal_uom(doc.production_detail, get_pack_stage=True) if doc.production_detail else {}
	for field, key in IPD_DERIVED.items():
		doc.set(field, context.get(key) if doc.production_detail else "")


def _apply_fabric_rows(doc, rows):
	stored = {row.name: row for row in doc.lot_fabric_details}
	doc.set("lot_fabric_details", [])
	for values in rows:
		name = values.get("name")
		if name and name not in stored:
			frappe.throw(_("Unknown Fabric Details row: {0}").format(name))
		row = stored[name] if name else {}
		row = doc.append("lot_fabric_details", row)
		row.cloth_item = values.get("cloth_item")
		row.production_detail = values.get("production_detail")


def require_transient_tables(values):
	for field in ("item_details", "order_item_details", "lot_fabric_details"):
		if field not in values:
			frappe.throw(_("{0} is required.").format(field))
		if not isinstance(values[field], list):
			frappe.throw(_("{0} must be a list.").format(field))


@frappe.whitelist(methods=["POST"])
def save_lot(values, name: str | None = None, expected_modified: str | None = None) -> dict:
	values = parse_mapping(values, _("Lot values"))
	doc = load_writable_lot(name)
	if name:
		assert_expected_modified(doc, expected_modified)
	require_transient_tables(values)
	ppo_mode = bool(check_enabled_po())
	locks = _lot_locks(doc, ppo_mode, not name)
	_reject_locked_changes(doc, values, locks)
	if name:
		reject_order_details_changes(doc, values, locks["order_details"])
	previous_ipd = doc.production_detail
	_apply_production_order(doc, values, ppo_mode)
	apply_editable_fields(doc, values, not name)
	_apply_production_detail_defaults(doc, previous_ipd)
	_apply_fabric_rows(doc, values["lot_fabric_details"])
	doc.item_details = frappe.as_json(values["item_details"])
	doc.order_item_details = frappe.as_json(values["order_item_details"])
	if name:
		doc.save()
	else:
		doc.insert()
	return get_lot_workspace(doc.name)
