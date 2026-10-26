"""Whitelisted /web endpoints for the Merch Item Production Detail workspace and editor."""

import frappe
from frappe import _

from essdee_yrp import ipd_ui
from essdee_yrp.merch.ipd import client_rules
from essdee_yrp.merch.ipd.attribute_values import get_usage, save_values
from essdee_yrp.merch.ipd.bom_mapping import get_bom_mapping, save_bom_mapping
from essdee_yrp.merch.ipd.capabilities import assert_allowed
from essdee_yrp.merch.ipd.checks import run_checks
from essdee_yrp.merch.ipd.copy_version import (
	attach_bom_mapping_copies,
	copy_options,
	detach_bom_mappings,
	ipd_changes,
)
from essdee_yrp.merch.ipd.copy_version import copy_ipd as copy_into_version
from essdee_yrp.merch.ipd.draft import apply_patch, load_editor_ipd, load_ipd
from essdee_yrp.merch.ipd.fields import DOCTYPE, section_of
from essdee_yrp.merch.ipd.grids import build_grids, stored_panel_flag
from essdee_yrp.merch.ipd.payload import build_payload, mapping_memo
from essdee_yrp.web_common import assert_expected_modified, parse_mapping


def parse_list(value, label):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(label))
	return value


def optional_mapping(value, label):
	return parse_mapping(value, label) if value not in (None, "") else {}


@frappe.whitelist()
def get_ipd_list_capabilities() -> dict:
	return {
		"can_read": bool(frappe.has_permission(DOCTYPE, "read")),
		"can_create": bool(frappe.has_permission(DOCTYPE, "create")),
	}


@frappe.whitelist()
def get_ipd_workspace(name: str) -> dict:
	return build_payload(load_ipd(name, "read"))


@frappe.whitelist()
def get_ipd_editor(name: str | None = None, duplicate_from: str | None = None) -> dict:
	return build_payload(load_editor_ipd(name, duplicate_from), editor=True)


@frappe.whitelist(methods=["POST"])
def get_ipd_grids(name: str, values=None, grids=None) -> dict:
	values = optional_mapping(values, _("IPD values"))
	doc = load_ipd(name, "write")
	include_saved = stored_panel_flag(doc) or "panel_wise_consumption_matrix_json" in values
	apply_patch(doc, values)
	with mapping_memo(doc):
		built, errors = build_grids(doc, parse_list(grids or [], _("Grids")), include_saved)
	return {"grids": built, "grid_errors": errors}


@frappe.whitelist(methods=["POST"])
def check_ipd(name: str | None = None, values=None) -> dict:
	return run_checks(name, optional_mapping(values, _("IPD values")))


@frappe.whitelist(methods=["POST"])
def save_ipd(
	values, name: str | None = None, expected_modified: str | None = None, duplicate_from: str | None = None
) -> dict:
	values = parse_mapping(values, _("IPD values"))
	doc = load_editor_ipd(name, duplicate_from)
	if name:
		assert_expected_modified(doc, expected_modified)
		if doc.approval_status == "Approved":
			frappe.throw(_("Approved IPDs are read only. Revert approval to edit."))
	apply_patch(doc, values)
	detached = [] if name else detach_bom_mappings(doc)
	if name:
		problems = [
			entry
			for entry in client_rules.problems(doc, {section_of(key) for key in values})
			if entry["rule"] not in client_rules.WARNING_RULES
		]
		if problems:
			frappe.throw(problems[0]["message"])
	message_start = len(frappe.get_message_log())
	if name:
		doc.save()
	else:
		doc.insert()
		attach_bom_mapping_copies(doc, detached)
	payload = build_payload(frappe.get_doc(DOCTYPE, doc.name), editor=True)
	payload["messages"] = frappe.get_message_log()[message_start:]
	return payload


def approve(doc, _payload):
	problems = run_checks(doc.name)["problems"]
	if problems:
		frappe.throw(_("Fix the IPD before approving: {0}").format(problems[0]["message"]))
	ipd_ui.approve_ipd(doc.name, "Approved")


def revert_approval(doc, payload):
	ipd_ui.revert_ipd_approval(doc.name, payload.get("reason"))


def regenerate_process_matrix(doc, _payload):
	from essdee_yrp.garment_work_order import regenerate_ipd_process_matrices

	return regenerate_ipd_process_matrices(doc.name)


COMMANDS = {
	"approve": approve,
	"revert_approval": revert_approval,
	"regenerate_process_matrix": regenerate_process_matrix,
}


@frappe.whitelist(methods=["POST"])
def execute_ipd_command(name: str, command: str, payload=None, expected_modified: str | None = None) -> dict:
	if command not in COMMANDS:
		frappe.throw(_("Unknown IPD command: {0}").format(command))
	doc = load_ipd(name, "read")
	assert_allowed(doc, command)
	doc.check_permission("write")
	assert_expected_modified(doc, expected_modified)
	message_start = len(frappe.get_message_log())
	result = COMMANDS[command](doc, optional_mapping(payload, _("Command payload")))
	response = build_payload(frappe.get_doc(DOCTYPE, name))
	response["messages"] = frappe.get_message_log()[message_start:]
	if result is not None:
		response["result"] = result
	return response


@frappe.whitelist()
def get_ipd_copy_options(source: str) -> dict:
	return copy_options(source)


@frappe.whitelist(methods=["POST"])
def copy_ipd(
	source: str, tech_pack_version: str, pattern_version: str, sections=None, item: str | None = None
) -> dict:
	return copy_into_version(
		source, tech_pack_version, pattern_version, parse_list(sections or [], _("Sections")), item or None
	)


@frappe.whitelist()
def get_ipd_changes(name: str) -> dict:
	return ipd_changes(name)


@frappe.whitelist(methods=["POST"])
def get_attribute_value_usage(name: str, attribute: str, values, draft=None) -> dict:
	return get_usage(name, attribute, parse_list(values, _("Values")), optional_mapping(draft, _("Draft")))


@frappe.whitelist(methods=["POST"])
def save_ipd_attribute_values(name: str, attribute: str, values, mapping_modified: str) -> dict:
	return save_values(name, attribute, parse_list(values, _("Values")), mapping_modified)


def bom_mapping_tables(item_attributes, bom_item_attributes):
	return {
		field: parse_list(rows, _(label)) if rows is not None else None
		for field, rows, label in (
			("item_attributes", item_attributes, "Item Attributes"),
			("bom_item_attributes", bom_item_attributes, "BOM Item Attributes"),
		)
	}


@frappe.whitelist()
def get_ipd_bom_mapping(name: str, bom_row: str, item_attributes=None, bom_item_attributes=None) -> dict:
	return get_bom_mapping(name, bom_row, **bom_mapping_tables(item_attributes, bom_item_attributes))


@frappe.whitelist(methods=["POST"])
def save_ipd_bom_mapping(
	name: str, bom_row: str, rows, mapping_modified: str, item_attributes=None, bom_item_attributes=None
) -> dict:
	return save_bom_mapping(
		name,
		bom_row,
		parse_list(rows, _("Mapping rows")),
		mapping_modified,
		**bom_mapping_tables(item_attributes, bom_item_attributes),
	)
