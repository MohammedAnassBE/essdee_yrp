"""Permissions and action capabilities for one IPD, decided on the server only."""

from frappe import _

from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.web_common import action, permission_flags

PERMISSION_TYPES = ("read", "write", "create", "delete")


def get_permissions(doc) -> dict:
	if doc.is_new():
		flags = permission_flags(DOCTYPE, PERMISSION_TYPES)
		return {**flags, "can_read": flags["can_create"], "can_write": flags["can_create"]}
	return permission_flags(DOCTYPE, PERMISSION_TYPES, doc)


def is_approved(doc) -> bool:
	return not doc.is_new() and doc.get("approval_status") == "Approved"


def edit_reason(approved, can_write):
	if approved:
		return _("Approved IPDs are read only.")
	return "" if can_write else _("Editing needs write permission.")


def get_capabilities(doc, permissions) -> dict:
	from essdee_yrp.merch.ipd.payload import is_approver

	approved = is_approved(doc)
	can_write = permissions["can_write"]
	editable = can_write and not approved
	approver = is_approver() and can_write and not doc.is_new()
	return {
		"edit": action(editable, _("Edit"), edit_reason(approved, can_write)),
		"save": action(
			editable, _("Create IPD") if doc.is_new() else _("Save"), edit_reason(approved, can_write)
		),
		"approved_edits": action(
			can_write and approved and not doc.get("is_cloth_item"),
			_("Add processes / panels"),
			_("Editing needs write permission.") if approved else _("Only Approved IPDs use this."),
		),
		"run_checks": action(
			permissions["can_read"] and not approved,
			_("Run checks"),
			_("Approved IPDs need no checks.") if approved else _("Reading needs read permission."),
		),
		"approve": action(
			approver and not approved, _("Approve"), _("Only senior merchandisers can approve.")
		),
		"revert_approval": action(
			approver and approved, _("Revert Approval"), _("Only senior merchandisers can revert approval.")
		),
		"new_version": action(
			permissions["can_create"] and not doc.is_new(),
			_("New version from this"),
			_("Creating IPDs needs create permission."),
		),
		"regenerate_process_matrix": action(
			can_write and not doc.is_new(), _("Regenerate IPD Process Matrix"), _("Needs write permission.")
		),
	}


def assert_allowed(doc, command):
	from frappe import PermissionError, throw

	capability = get_capabilities(doc, get_permissions(doc)).get(command)
	if not capability:
		throw(_("Unknown IPD command: {0}").format(command))
	if not capability["allowed"]:
		throw(capability["reason"] or _("Not permitted."), PermissionError)
