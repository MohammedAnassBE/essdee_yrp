import random
import time
from collections.abc import Mapping

import frappe
from frappe import _
from frappe.model.workflow import (
	apply_workflow,
	get_transitions,
	get_workflow,
	has_approval_access,
	is_transition_condition_satisfied,
)
from frappe.utils import add_days, cint, flt, format_date, nowdate
from yrp.attribute_links import value as actual_attribute_value
from yrp.attribute_value_identity import attribute_value_name
from yrp.attribute_values import get_mapping_values
from yrp.yrp.doctype.yrp_item.yrp_item import get_global_attribute_values

from essdee_yrp.fabric_store.documents.common import get_effective_fields
from essdee_yrp.web_common import assert_expected_modified, parse_mapping, permission_flags

DOCTYPE = "YRP Item Price"
EDITOR_FIELDS = (
	"item_name",
	"supplier",
	"from_date",
	"to_date",
	"depends_on_attribute",
	"attribute",
	"tax",
)
TIER_FIELDS = ("moq", "price", "lead_time", "attribute_value")
VIEW_FIELDS = (
	"item_name",
	"supplier",
	"supplier_name",
	"uom",
	"from_date",
	"to_date",
	"depends_on_attribute",
	"attribute",
	"tax",
	"approved_by",
)
READ_ONLY_EDITOR_FIELDS = ("uom", "supplier_name", "approved_by")
PERMISSION_TYPES = ("read", "create", "write", "submit", "delete")
MAX_ACTION_ATTEMPTS = 2


def _parse_list(value, label: str) -> list:
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} is not valid JSON.").format(label))
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(label))
	return value


def _workflow_state(doc) -> str:
	workflow = get_workflow(DOCTYPE)
	return doc.get(workflow.workflow_state_field) or ""


def is_editable_by_user(doc) -> bool:
	"""Desk parity: draft docstatus, the state's allow_edit role and write permission."""
	if cint(doc.docstatus) != 0:
		return False
	workflow = get_workflow(DOCTYPE)
	state = next((row for row in workflow.states if row.state == _workflow_state(doc)), None)
	return bool(
		state
		and state.allow_edit in frappe.get_roles()
		and frappe.has_permission(DOCTYPE, ptype="write", doc=doc)
	)


def is_deletable_by_user(doc) -> bool:
	return bool(
		is_editable_by_user(doc) and frappe.has_permission(DOCTYPE, ptype="delete", doc=doc)
	)


def _not_editable_message(doc) -> str:
	return _("This Item Price cannot be edited in state {0}.").format(_workflow_state(doc))


def _record(doc) -> dict:
	return {
		"doctype": DOCTYPE,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"item_name": doc.item_name,
		"supplier": doc.supplier,
		"supplier_name": doc.supplier_name,
		"uom": doc.uom,
		"from_date": doc.from_date,
		"to_date": doc.to_date,
		"depends_on_attribute": cint(doc.depends_on_attribute),
		"attribute": doc.attribute,
		"tax": doc.tax,
		"workflow_state": _workflow_state(doc),
		"approved_by": doc.approved_by,
		"modified": doc.modified,
		"owner": doc.owner,
	}


def _tiers(doc) -> list[dict]:
	return [
		{
			"name": row.name,
			"moq": row.moq,
			"price": row.price,
			"lead_time": row.lead_time,
			"attribute_value": row.attribute_value,
			"attribute_value_label": actual_attribute_value(row.attribute_value),
		}
		for row in doc.get("item_price_values") or []
	]


def get_price_tiers(names) -> dict[str, list[dict]]:
	"""Price Values rows per YRP Item Price, in row order; callers check read access."""
	tiers = {name: [] for name in names}
	if not tiers:
		return tiers
	for row in frappe.get_all(
		"YRP Item Price Value",
		filters={"parent": ["in", list(tiers)], "parenttype": DOCTYPE},
		fields=["parent", *TIER_FIELDS],
		order_by="parent asc, idx asc",
	):
		tiers[row.parent].append(
			{
				"moq": row.moq,
				"price": row.price,
				"lead_time": row.lead_time,
				"attribute_value": row.attribute_value,
				"attribute_value_label": actual_attribute_value(row.attribute_value),
			}
		)
	return tiers


@frappe.whitelist()
def get_item_price_summaries(names) -> dict[str, dict]:
	requested = list(dict.fromkeys(str(name or "").strip() for name in _parse_list(names, _("Item Prices"))))
	requested = [name for name in requested if name]
	if len(requested) > 100:
		frappe.throw(_("Prices can be loaded for at most 100 Item Prices at a time."))
	if not requested:
		return {}
	frappe.has_permission(DOCTYPE, ptype="read", throw=True)
	visible = frappe.get_list(DOCTYPE, filters={"name": ["in", requested]}, pluck="name", limit=0)
	return {name: price_summary(tiers) for name, tiers in get_price_tiers(visible).items()}


def price_summary(tiers: list[dict]) -> dict:
	prices = [flt(tier["price"]) for tier in tiers]
	return {
		"min_price": min(prices) if prices else None,
		"max_price": max(prices) if prices else None,
		"slab_count": len(prices),
	}


def _history(doc) -> list[dict]:
	supplier_filter = doc.supplier if doc.supplier else ["is", "not set"]
	return frappe.get_list(
		DOCTYPE,
		filters={
			"item_name": doc.item_name,
			"supplier": supplier_filter,
			"name": ["!=", doc.name],
		},
		fields=[
			"name",
			"workflow_state",
			"docstatus",
			"from_date",
			"to_date",
			"uom",
			"approved_by",
			"modified",
		],
		order_by="from_date desc, creation desc",
		limit=0,
	)


def _timeline(doc) -> list[dict]:
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": DOCTYPE,
			"reference_name": doc.name,
			"comment_type": ["in", ["Comment", "Info", "Workflow"]],
		},
		fields=["name", "comment_type", "content", "comment_by", "owner", "creation"],
		order_by="creation desc",
		limit=50,
	)
	entries = [
		{
			"name": row.name,
			"kind": row.comment_type.lower(),
			"label": row.comment_type,
			"content": frappe.utils.strip_html_tags(row.content or ""),
			"by": row.comment_by or row.owner,
			"creation": row.creation,
		}
		for row in comments
	]
	entries.extend(_document_events(doc))
	if doc.approved_by and cint(doc.docstatus) in (1, 2):
		approved_comment = next(
			(
				entry
				for entry in entries
				if entry["kind"] == "workflow" and entry["content"] == _("Approved")
			),
			None,
		)
		entries.append(
			{
				"name": f"{doc.name}-approved-by",
				"kind": "approval",
				"label": _("Approval"),
				"content": _("Approved by {0}").format(doc.approved_by),
				"by": doc.approved_by,
				"creation": approved_comment["creation"] if approved_comment else doc.modified,
			}
		)
	entries.sort(key=lambda entry: str(entry["creation"] or ""), reverse=True)
	return entries


def _document_events(doc) -> list[dict]:
	"""Desk Activity parity: who created the price and each saved edit."""
	events = [
		{
			"name": f"{doc.name}-created",
			"kind": "created",
			"label": _("Created"),
			"content": _("{0} created this").format(doc.owner),
			"by": doc.owner,
			"creation": doc.creation,
		}
	]
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": DOCTYPE, "docname": doc.name},
		fields=["name", "owner", "creation"],
		order_by="creation asc",
	)
	events.extend(
		{
			"name": version.name,
			"kind": "edited",
			"label": _("Edited"),
			"content": _("{0} edited this").format(version.owner),
			"by": version.owner,
			"creation": version.creation,
		}
		for version in versions
	)
	return events


def _approval_predecessor(doc):
	if not doc.item_name or not doc.supplier or not doc.from_date:
		return None
	rows = frappe.get_list(
		DOCTYPE,
		filters=[
			["name", "!=", doc.name],
			["item_name", "=", doc.item_name],
			["supplier", "=", doc.supplier],
			["docstatus", "=", 1],
			["workflow_state", "=", "Approved"],
			["from_date", "<", doc.from_date],
		],
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", doc.from_date]],
		fields=["name", "from_date", "to_date"],
		order_by="from_date desc, creation desc",
		limit=2,
	)
	return rows[0] if len(rows) == 1 else None


def _action_preview(doc, action: str) -> str:
	if action != "Approve":
		return ""
	predecessor = _approval_predecessor(doc)
	if not predecessor:
		return ""
	return _("Approving will end {0} on {1}.").format(
		predecessor.name,
		format_date(add_days(doc.from_date, -1)),
	)


def _state_doc_status(workflow, state: str) -> int:
	return next((cint(row.doc_status) for row in workflow.states if row.state == state), 0)


def _action_payload(doc, workflow, transition) -> dict:
	return {
		"action": transition.action,
		"state": transition.state,
		"next_state": transition.next_state,
		"next_state_doc_status": _state_doc_status(workflow, transition.next_state),
		"label": _(transition.action),
		"preview": _action_preview(doc, transition.action),
	}


def _actions(doc) -> list[dict]:
	user = frappe.session.user
	workflow = get_workflow(DOCTYPE)
	return [
		_action_payload(doc, workflow, transition)
		for transition in get_transitions(doc, workflow)
		if has_approval_access(user, doc, transition)
	]


def get_save_actions(doc) -> list[dict]:
	"""Transitions available right after saving: the doc's own, or the initial state's for a new doc."""
	if not doc.is_new():
		return _actions(doc)
	user = frappe.session.user
	roles = set(frappe.get_roles())
	workflow = get_workflow(DOCTYPE)
	initial_state = workflow.states[0].state
	doc.set(workflow.workflow_state_field, initial_state)
	new_doc_owner = frappe._dict(owner=user)
	return [
		_action_payload(doc, workflow, transition)
		for transition in workflow.transitions
		if transition.state == initial_state
		and transition.allowed in roles
		and has_approval_access(user, new_doc_owner, transition)
		and is_transition_condition_satisfied(transition, doc)
	]


def _overview_fields(doc) -> list[dict]:
	fields = get_effective_fields(doc, VIEW_FIELDS)
	for field in fields:
		if field["fieldname"] == "approved_by":
			field["link_name"] = doc.get("approved_by")
	return fields


@frappe.whitelist()
def get_item_price_workspace(name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
	return {
		"record": _record(doc),
		"fields": _overview_fields(doc),
		"tier_fields": _tier_fields(),
		"tiers": _tiers(doc),
		"actions": _actions(doc),
		"can_edit": is_editable_by_user(doc),
		"can_delete": is_deletable_by_user(doc),
		"permissions": permission_flags(DOCTYPE, PERMISSION_TYPES, doc),
		"history": _history(doc),
		"timeline": _timeline(doc),
	}


def _item_for_editor(item_name: str | None):
	if not item_name:
		return None
	item = frappe.get_doc("Item", item_name)
	frappe.has_permission("Item", ptype="read", doc=item, throw=True)
	if item.variant_of:
		frappe.throw(_("Item Prices are not created for variant items."))
	return item


def _attribute_options(item) -> list[dict]:
	if not item:
		return []
	result = []
	for row in item.get("attributes") or []:
		labels = get_mapping_values(row.mapping) if row.get("mapping") else []
		if not labels:
			labels = get_global_attribute_values(row.attribute)
		result.append(
			{
				"attribute": row.attribute,
				"values": [
					{"name": attribute_value_name(row.attribute, label), "label": label}
					for label in labels
				],
			}
		)
	return result


def _editor_values(doc, item, *, existing: bool) -> dict:
	values = {fieldname: doc.get(fieldname) for fieldname in EDITOR_FIELDS}
	values["uom"] = doc.uom if existing else (item.stock_uom if item else None)
	values["from_date"] = values["from_date"] or nowdate()
	values["item_price_values"] = _tiers(doc)
	values["supplier_name"] = doc.supplier_name
	values["approved_by"] = doc.approved_by if cint(doc.docstatus) in (1, 2) else None
	return values


def _field_schema(fieldname: str) -> dict:
	field = frappe.get_meta(DOCTYPE).get_field(fieldname)
	return {
		"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
		"required": fieldname in {"item_name", "supplier", "uom", "from_date", "tax"},
		"read_only": fieldname in READ_ONLY_EDITOR_FIELDS,
	}


def _tier_field_schema(fieldname: str) -> dict:
	field = frappe.get_meta("YRP Item Price Value").get_field(fieldname)
	return {
		"fieldname": fieldname,
		"fieldtype": field.fieldtype,
		"label": field.label,
		"precision": 0 if field.fieldtype == "Int" else frappe.get_precision(field.parent, fieldname),
	}


def _tier_fields() -> dict:
	return {fieldname: _tier_field_schema(fieldname) for fieldname in TIER_FIELDS}


def _editor_payload(doc, *, existing: bool, item=None) -> dict:
	unit_mismatch = bool(existing and item and doc.uom != item.stock_uom)
	return {
		"values": _editor_values(doc, item, existing=existing),
		"fields": {
			fieldname: _field_schema(fieldname)
			for fieldname in (*EDITOR_FIELDS, *READ_ONLY_EDITOR_FIELDS)
		},
		"tier_fields": _tier_fields(),
		"attributes": _attribute_options(item),
		"options": {
			"tax_slabs": frappe.get_all(
				"YRP Tax Slab",
				filters={"enabled": 1},
				fields=["name as value", "percentage as label"],
				order_by="percentage asc",
				limit=0,
			),
		},
		"modified": doc.modified if existing else None,
		"permissions": permission_flags(DOCTYPE, PERMISSION_TYPES, doc if existing else None),
		"workflow": {
			"state": _workflow_state(doc) if existing else get_workflow(DOCTYPE).states[0].state,
			"save_actions": get_save_actions(doc),
		},
		"item_uom": item.stock_uom if item else None,
		"unit_mismatch": unit_mismatch,
		"unit_mismatch_message": (
			_(
				"This Item Price uses {0}, but the Item now uses {1}. Re-enter the prices in a new Item Price."
			).format(doc.uom, item.stock_uom)
			if unit_mismatch
			else ""
		),
	}


@frappe.whitelist()
def get_item_price_editor(name: str | None = None, item: str | None = None) -> dict:
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
		if not is_editable_by_user(doc):
			frappe.throw(_not_editable_message(doc))
		item_doc = _item_for_editor(doc.item_name)
		return _editor_payload(doc, existing=True, item=item_doc)
	frappe.has_permission(DOCTYPE, ptype="create", throw=True)
	doc = frappe.new_doc(DOCTYPE)
	doc.item_name = item
	item_doc = _item_for_editor(item)
	if item_doc:
		doc.uom = item_doc.stock_uom
	return _editor_payload(doc, existing=False, item=item_doc)


def _parse_tiers(rows) -> list[dict]:
	parsed = []
	for row in _parse_list(rows or [], _("Price tiers")):
		if not isinstance(row, Mapping):
			frappe.throw(_("Price tier rows must be objects."))
		attribute_value = row.get("attribute_value")
		if isinstance(attribute_value, Mapping):
			attribute_value = attribute_value.get("name")
		parsed.append(
			{
				fieldname: attribute_value if fieldname == "attribute_value" else row.get(fieldname)
				for fieldname in TIER_FIELDS
			}
		)
	return parsed


def _load_price_for_save(name: str | None, expected_modified=None):
	if not name:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		return frappe.new_doc(DOCTYPE)
	preflight = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype="write", doc=preflight, throw=True)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
	assert_expected_modified(doc, expected_modified)
	if not is_editable_by_user(doc):
		frappe.throw(_not_editable_message(doc))
	return doc


def _apply_values(doc, values: Mapping) -> None:
	previous_item = doc.item_name if not doc.is_new() else None
	for fieldname in EDITOR_FIELDS:
		if fieldname in values:
			doc.set(fieldname, values[fieldname])
	item = _item_for_editor(doc.item_name)
	if not item:
		frappe.throw(_("Item is required."))
	if doc.is_new() or doc.item_name != previous_item:
		doc.uom = item.stock_uom
	doc.depends_on_attribute = cint(doc.depends_on_attribute)
	if not doc.depends_on_attribute:
		doc.attribute = None
	doc.set("item_price_values", _parse_tiers(values.get("item_price_values") or []))


@frappe.whitelist(methods=["POST"])
def save_item_price(values, name: str | None = None, expected_modified=None) -> dict:
	values = parse_mapping(values, _("Item Price values"))
	doc = _load_price_for_save(name, expected_modified)
	_apply_values(doc, values)
	if name:
		doc.save()
	else:
		doc.insert()
	return get_item_price_workspace(doc.name)


def _execute_item_price_action_once(name: str, action: str, expected_modified):
	preflight = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype="read", doc=preflight, throw=True)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
	assert_expected_modified(doc, expected_modified)
	transition = next(
		(
			row
			for row in get_transitions(doc)
			if row.action == action and has_approval_access(frappe.session.user, doc, row)
		),
		None,
	)
	if not transition:
		frappe.throw(_("This Item Price action is not allowed."), frappe.PermissionError)
	apply_workflow(doc, action)
	return get_item_price_workspace(name)


@frappe.whitelist(methods=["POST"])
def execute_item_price_action(name: str, action: str, expected_modified) -> dict:
	for attempt in range(MAX_ACTION_ATTEMPTS):
		try:
			return _execute_item_price_action_once(name, action, expected_modified)
		except frappe.QueryDeadlockError:
			frappe.db.rollback()
			if attempt + 1 >= MAX_ACTION_ATTEMPTS:
				raise
			time.sleep(random.uniform(0.01, 0.05))
	return {}


@frappe.whitelist(methods=["POST"])
def delete_item_price(name: str, expected_modified) -> dict:
	preflight = frappe.get_doc(DOCTYPE, name)
	frappe.has_permission(DOCTYPE, ptype="delete", doc=preflight, throw=True)
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	frappe.has_permission(DOCTYPE, ptype="delete", doc=doc, throw=True)
	assert_expected_modified(doc, expected_modified)
	if not is_deletable_by_user(doc):
		frappe.throw(_("This Item Price cannot be deleted in state {0}.").format(_workflow_state(doc)))
	frappe.delete_doc(DOCTYPE, name)
	return {"deleted": True, "name": name}
