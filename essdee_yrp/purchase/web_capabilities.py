import frappe
from frappe import _

from essdee_yrp.web_common import permission_flags

SECTIONS = {
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
			sections[key] = {"label": label, **permissions}
	return {"sections": sections}
