import math
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions, get_workflow, has_approval_access
from frappe.utils import add_days, cint, getdate, nowdate
from yrp import attribute_links
from yrp.stock.dimensions import append_production_group_filters

from essdee_yrp import process_cost
from essdee_yrp.api.work_order import get_work_order_selection_context
from essdee_yrp.purchase.lot_documents import DOCUMENT_SECTIONS
from essdee_yrp.web_common import action, assert_expected_modified, parse_mapping, permission_flags

DOCTYPE = "YRP Process Cost"
EDITOR_FIELDS = (
	"lot", "process_name", "item", "uom", "supplier", "supplier_name",
	"from_date", "to_date", "is_rework", "tax_slab", "attribute",
)
VIEW_FIELDS = (*EDITOR_FIELDS, "is_expired", "depends_on_attribute", "approved_by")
REQUIRED_FIELDS = ("lot", "process_name", "item", "uom", "supplier", "from_date", "tax_slab")
WRITE_FIELDS = tuple(field for field in EDITOR_FIELDS if field not in ("uom", "supplier_name"))
TIER_FIELDS = ("min_order_qty", "price", "attribute_value")
PERMISSIONS = ("read", "create", "write", "delete")
STATES = ("Draft", "Approval Pending", "Approved", "Rejected", "Expired")


def _schema(fieldname, doctype=DOCTYPE):
	field = frappe.get_meta(doctype).get_field(fieldname)
	if not field:
		frappe.throw(_("Missing field {0}.{1}").format(doctype, fieldname))
	schema = {key: field.get(key) for key in ("fieldname", "fieldtype", "label", "options", "reqd", "read_only")}
	if field.fieldtype in ("Float", "Currency", "Int"):
		schema["precision"] = frappe.get_precision(doctype, fieldname)
	return schema


def _state(doc):
	return doc.get(get_workflow(DOCTYPE).workflow_state_field) or "Draft"


def is_editable_by_user(doc):
	if cint(doc.docstatus) != 0:
		return False
	state = next((row for row in get_workflow(DOCTYPE).states if row.state == _state(doc)), None)
	return bool(state and state.allow_edit in frappe.get_roles()
		and frappe.has_permission(DOCTYPE, ptype="write", doc=doc))


def is_deletable_by_user(doc):
	return cint(doc.docstatus) == 0 and bool(frappe.has_permission(DOCTYPE, ptype="delete", doc=doc))


def _assert_editable(doc):
	if not is_editable_by_user(doc):
		frappe.throw(_("This Process Cost is not editable in state {0}.").format(_state(doc)), frappe.PermissionError)


def _approval_matches(doc):
	filters = [
		["item", "=", doc.item], ["process_name", "=", doc.process_name],
		["supplier", "=", doc.supplier], ["is_rework", "=", cint(doc.is_rework)],
		["docstatus", "=", 1], ["is_expired", "=", 0],
		["workflow_state", "=", "Approved"], ["name", "!=", doc.name],
	]
	append_production_group_filters(filters, doc, DOCTYPE)
	return frappe.get_list(DOCTYPE, filters=filters, fields=["name", "from_date"], order_by="from_date asc")


def _approve_preview(doc):
	lines = []
	for row in _approval_matches(doc):
		if getdate(row.from_date) == getdate(doc.from_date):
			return action(False, "Approve", _("A Process Cost was found with the same From Date. Please expire it before submitting this one."))
		if getdate(row.from_date) < getdate(doc.from_date):
			date = getdate(add_days(doc.from_date, -1)).strftime("%d-%m-%Y")
			lines.append(_("Approving will end {0} on {1}").format(row.name, date))
	return {**action(True, "Approve"), "preview": "\n".join(lines)}


def _actions(doc):
	result = []
	for transition in get_transitions(doc):
		if not has_approval_access(frappe.session.user, doc, transition):
			continue
		payload = _approve_preview(doc) if transition.action == "Approve" else action(True, _(transition.action))
		result.append({**payload, "action": transition.action, "next_state": transition.next_state})
	return result


def _tiers(doc):
	rows = doc.get("process_cost_values") or []
	labels = {row.attribute_value: row.attribute_value or "" for row in rows}
	names = [value for value in labels if value and value.startswith("IAV-")]
	if names:
		labels.update(dict.fromkeys(names, ""))
		labels.update({value.name: value.attribute_value for value in frappe.get_all(
			attribute_links.MASTER, filters={"name": ["in", names]}, fields=["name", "attribute_value"])})
	return [{**{key: row.get(key) for key in TIER_FIELDS},
		"attribute_value_label": labels[row.attribute_value]} for row in rows]


def _attribute_options(rows, attribute):
	values = [row["attribute_value"] for row in rows]
	if not values:
		return []
	masters = frappe.get_all(attribute_links.MASTER, filters={"attribute_name": attribute},
		or_filters={"name": ["in", values], "attribute_value": ["in", values]},
		fields=["name", "attribute_value"])
	names = {row.attribute_value: row.name for row in masters}
	names.update({row.name: row.name for row in masters})
	return [{"name": names.get(row["attribute_value"], ""), "label": row["attribute_value"] or ""}
		for row in rows]


def _waiting_note(doc, actions, can_edit):
	if _state(doc) == "Approval Pending" and not actions:
		return _("Waiting for Purchase Manager approval")
	if _state(doc) == "Draft" and not can_edit and not actions:
		return _("Waiting for a Purchase User to submit")
	return ""


@frappe.whitelist()
def get_process_cost_list_capabilities():
	return {**permission_flags(DOCTYPE, ("read", "create")), "workflow_states": list(STATES)}


def _work_orders(name):
	section = DOCUMENT_SECTIONS["work_orders"]
	doctype = section["doctype"]
	if not frappe.has_permission(doctype, "read"):
		return {"permitted": False, "count": 0, "rows": []}
	filters = {"process_cost": name, "docstatus": ["!=", 2]}
	rows = frappe.get_list(
		doctype, filters=filters, fields=["name", "docstatus", "modified", *section["fields"]],
		order_by=section["order_by"], limit_page_length=500,
	)
	count = frappe.get_list(
		doctype, filters=filters, fields=[{"COUNT": "name", "as": "count"}], order_by="", limit_page_length=1,
	)
	return {"permitted": True, "count": cint(count[0].count), "rows": [dict(row) for row in rows]}


@frappe.whitelist()
def get_process_cost_workspace(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	actions = _actions(doc)
	can_edit = is_editable_by_user(doc)
	return {
		"record": {**{key: doc.get(key) for key in (*VIEW_FIELDS, "name", "modified", "docstatus")},
			"doctype": DOCTYPE, "workflow_state": _state(doc)},
		"fields": [{**_schema(key), "value": doc.get(key)} for key in VIEW_FIELDS],
		"tiers": _tiers(doc), "tier_fields": [_schema(key, "YRP Process Cost Value") for key in TIER_FIELDS],
		"actions": actions, "can_edit": can_edit, "can_delete": is_deletable_by_user(doc),
		"permissions": permission_flags(DOCTYPE, PERMISSIONS, doc),
		"waiting_note": _waiting_note(doc, actions, can_edit),
		"work_orders": _work_orders(doc.name),
	}


def _selection(lot, process_name=None, item=None):
	if not lot:
		return {"item": None, "uom": None, "item_options": [], "is_cloth_process": False}
	lot_doc = frappe.get_doc("SD YRP Lot", lot)
	lot_doc.check_permission("read")
	options = []
	is_cloth = bool(process_name and frappe.db.get_value("YRP Process", process_name, "is_cloth_process"))
	if process_name:
		frappe.has_permission("YRP Process", ptype="read", doc=process_name, throw=True)
	if is_cloth:
		return _cloth_selection(lot_doc, process_name, item)
	item = lot_doc.item
	return {"item": item, "uom": _item_uom(item), "item_options": options, "is_cloth_process": False}


def _lookup_permission_error(fieldname, sources):
	purpose = _("price by Attribute") if fieldname == "attribute" else _("select a cloth Item")
	for doctype, name in sources:
		if name and not frappe.has_permission(doctype, ptype="read", doc=name):
			message = _("You cannot read {0} {1} needed to {2}.").format(doctype, name, purpose)
			return {"field_errors": {fieldname: message}}
	message = _("You cannot read Item or YRP Item Production Detail needed to {0}.").format(purpose)
	return {"field_errors": {fieldname: message}}


def _cloth_selection(lot_doc, process_name, item):
	try:
		options = get_work_order_selection_context(lot_doc.name, process_name)["options"]
		item = item if item in {row["item"] for row in options} else None
		if len(options) == 1:
			item = options[0]["item"]
		if item:
			frappe.has_permission("Item", ptype="read", doc=item, throw=True)
	except frappe.PermissionError:
		fabrics = lot_doc.get("lot_fabric_details") or []
		sources = [("YRP Item Production Detail", row.production_detail) for row in fabrics]
		sources.extend(("Item", row.cloth_item) for row in fabrics)
		return {"item": None, "uom": None, "item_options": [], "is_cloth_process": True,
			**_lookup_permission_error("item", sources)}
	return {"item": item, "uom": _item_uom(item), "item_options": options, "is_cloth_process": True}


def _item_uom(item):
	if not item:
		return None
	return frappe.db.get_value("Item", item, "stock_uom")


def _attribute_permission_error(lot, process_name, item):
	production_detail = process_cost._resolve_ipd_name(item, lot, process_name)
	return _lookup_permission_error("attribute", [
		("Item", item), ("YRP Item Production Detail", production_detail),
	])


@frappe.whitelist()
def get_process_cost_grid(lot, process_name, item=None, attribute=None):
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	selection = _selection(lot, process_name, item)
	values = []
	if attribute and selection["item"] and process_name:
		try:
			rows = process_cost.get_pc_attribute_values(selection["item"], attribute, lot, process_name, for_link=0)
		except frappe.PermissionError:
			return {**selection, "attribute_values": [],
				**_attribute_permission_error(lot, process_name, selection["item"])}
		values = _attribute_options(rows, attribute)
	return {**selection, "attribute_values": values}


@frappe.whitelist()
def search_process_cost_attributes(lot, process_name, item=None, text=""):
	selection = get_process_cost_grid(lot, process_name, item)
	if selection.get("field_errors") or not selection["item"] or not process_name:
		return {"options": [], "field_errors": selection.get("field_errors", {})}
	try:
		rows = process_cost.get_item_attributes("Item Attribute", text, "name", 0, 20,
			{"item": selection["item"], "lot": lot, "process": process_name})
	except frappe.PermissionError:
		return {"options": [], **_attribute_permission_error(lot, process_name, selection["item"])}
	return {"options": [{"name": row[0], "label": row[0]} for row in rows]}


@frappe.whitelist()
def get_process_cost_editor(name=None, lot=None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("read")
		doc.check_permission("write")
		_assert_editable(doc)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		doc.lot = lot
	context = get_process_cost_grid(doc.lot, doc.process_name, doc.item, doc.attribute)
	values = {key: doc.get(key) for key in VIEW_FIELDS}
	values.update(item=context["item"], uom=context["uom"], from_date=doc.from_date or nowdate())
	values["process_cost_values"] = _tiers(doc)
	return {"values": values, "fields": [_schema(key) for key in VIEW_FIELDS],
		"tier_fields": [_schema(key, "YRP Process Cost Value") for key in TIER_FIELDS],
		"modified": doc.modified if name else None, "context": context}


def _field_error(fieldname, message, row=None, column=None):
	payload = frappe.as_json({"field_errors": {fieldname: message}, "row": row, "column": column})
	frappe.throw(_("Process Cost validation failed.") + "\n" + payload, frappe.ValidationError)


def _require_fields(doc):
	for fieldname in REQUIRED_FIELDS:
		if not doc.get(fieldname):
			_field_error(fieldname, _("{0} is required.").format(_schema(fieldname)["label"]))


def _numeric_value(value, row, fieldname):
	try:
		number = float(value)
	except (TypeError, ValueError):
		number = math.nan
	if not math.isfinite(number) or number < 0:
		_field_error("process_cost_values", _("{0} must be a non-negative number.").format(
			_schema(fieldname, "YRP Process Cost Value")["label"]), row, fieldname)
	return number


def _validate_tier(row, index, allowed_values, attribute, seen):
	if not isinstance(row, Mapping):
		_field_error("process_cost_values", _("Process Cost Values rows must be objects."))
	value = row.get("attribute_value") or None
	if attribute and value not in allowed_values:
		_field_error("process_cost_values", _("Select an Attribute Value configured for this Lot and Process."), index, "price")
	if not attribute and value:
		_field_error("process_cost_values", _("Clear Attribute Value when Attribute is empty."), index, "price")
	quantity = _numeric_value(row.get("min_order_qty", 0), index, "min_order_qty")
	price = _numeric_value(row.get("price", 0), index, "price")
	pair = (value, quantity)
	if pair in seen:
		_field_error("process_cost_values", _("Duplicate Attribute Value and Min Order Qty."), index, "min_order_qty")
	seen.add(pair)
	return {"attribute_value": value, "min_order_qty": quantity, "price": price}


def _apply_tiers(doc, values, context):
	rows = values.get("process_cost_values") or []
	if not isinstance(rows, list):
		_field_error("process_cost_values", _("Process Cost Values must be a list."))
	allowed = {row["name"] for row in context["attribute_values"]}
	seen = set()
	tiers = [_validate_tier(row, index, allowed, doc.attribute, seen) for index, row in enumerate(rows)]
	if not any(row["price"] > 0 for row in tiers):
		_field_error("process_cost_values", _("At least one Process Cost Value must have a price greater than 0."))
	doc.set("process_cost_values", tiers)


def _apply_values(doc, values):
	for key in WRITE_FIELDS:
		if key in values:
			doc.set(key, values[key])
	if not doc.lot or not doc.process_name:
		_require_fields(doc)
	context = get_process_cost_grid(doc.lot, doc.process_name, doc.item, doc.attribute)
	for fieldname, message in context.get("field_errors", {}).items():
		_field_error(fieldname, message)
	if context["is_cloth_process"] and doc.item not in {row["item"] for row in context["item_options"]}:
		_field_error("item", _("Select a cloth Item configured for this Lot and Process."))
	doc.item, doc.uom = context["item"], context["uom"]
	_require_fields(doc)
	doc.supplier_name = frappe.db.get_value("Supplier", doc.supplier, "supplier_name")
	if not frappe.db.get_value("YRP Tax Slab", doc.tax_slab, "enabled"):
		_field_error("tax_slab", _("Select an enabled Tax Slab."))
	doc.is_rework = cint(doc.is_rework)
	_apply_tiers(doc, values, context)


def _load_locked(name, permission, expected_modified):
	preflight = frappe.get_doc(DOCTYPE, name)
	preflight.check_permission("read")
	preflight.check_permission(permission)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	doc.check_permission("read")
	doc.check_permission(permission)
	assert_expected_modified(doc, expected_modified)
	return doc


@frappe.whitelist(methods=["POST"])
def save_process_cost(values, name=None, expected_modified=None):
	values = parse_mapping(values, _("Process Cost values"))
	if name:
		doc = _load_locked(name, "write", expected_modified)
		_assert_editable(doc)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
	_apply_values(doc, values)
	doc.save() if name else doc.insert()
	return get_process_cost_workspace(doc.name)


def _execute_once(name, action, expected_modified):
	doc = _load_locked(name, "read", expected_modified)
	transitions = [row for row in get_transitions(doc)
		if row.action == action and has_approval_access(frappe.session.user, doc, row)]
	if not transitions:
		frappe.throw(_("This Process Cost action is not allowed."), frappe.PermissionError)
	apply_workflow(doc, action)
	return get_process_cost_workspace(name)


@frappe.whitelist(methods=["POST"])
def execute_process_cost_command(name, action, expected_modified):
	for attempt in range(2):
		try:
			return _execute_once(name, action, expected_modified)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt:
				raise


@frappe.whitelist(methods=["POST"])
def delete_process_cost(name, expected_modified):
	doc = _load_locked(name, "delete", expected_modified)
	if not is_deletable_by_user(doc):
		frappe.throw(_("Only a draft Process Cost can be deleted."), frappe.PermissionError)
	frappe.delete_doc(DOCTYPE, name)
	return {"deleted": True, "name": name}
