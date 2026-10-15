import frappe
from frappe import _
from frappe.model.workflow import get_workflow, get_workflow_name

from essdee_yrp.web_common import permission_flags

SECTIONS = {
	"lots": ("SD YRP Lot", _("Lots"), ("read", "create", "write")),
	"items": ("Item", _("Items"), ("read", "create", "write")),
	"item_prices": (
		"YRP Item Price",
		_("Item Prices"),
		("read", "create", "write", "submit"),
	),
}


@frappe.whitelist()
def get_capabilities() -> dict:
	sections = {}
	for key, (doctype, label, permission_types) in SECTIONS.items():
		permissions = permission_flags(doctype, permission_types)
		if permissions["can_read"]:
			sections[key] = {"label": label, **permissions, "workflow_states": _workflow_states(doctype)}
	return {"sections": sections}


def _workflow_states(doctype: str) -> list[str]:
	if not get_workflow_name(doctype):
		return []
	return [row.state for row in get_workflow(doctype).states]
