"""Retire every Essdee UI layout except Premium White.

Fixture sync updates and inserts documents but does not remove fixture records
that disappeared from a later release.  This patch therefore performs the
explicit database cleanup required when Premium White becomes Essdee's sole
layout.  Direct database deletes are intentional for the base-protected
``Default`` layout; all linked preferences are repointed first.
"""

import json

import frappe

from essdee_yrp.ui_config import PREMIUM_LAYOUT_NAME
from yrp.yrp.api.ui_config import validate_config


def execute():
	if not frappe.db.table_exists("UI Layout"):
		return
	if not frappe.db.exists("UI Layout", PREMIUM_LAYOUT_NAME):
		# Fresh installs receive Premium White from fixtures after schema sync.
		return

	_improve_premium_white()
	_repoint_preferences()
	_remove_other_layouts()
	frappe.clear_cache()


def _improve_premium_white():
	doc = frappe.get_doc("UI Layout", PREMIUM_LAYOUT_NAME)
	config = json.loads(doc.config)

	config["nav"] = {
		"position": "sidebar",
		"sidebar": "pinned",
		"groups": [
			{
				"id": "Production",
				"label": "Production",
				"items": [
					{"doctype": "Lot", "icon": "pi pi-inbox"},
					{"doctype": "Work Order", "icon": "pi pi-bars"},
					{
						"doctype": "Work Order Correction",
						"icon": "pi pi-pencil",
					},
					{"doctype": "Debit", "icon": "pi pi-wallet"},
					{"doctype": "Process Cost", "icon": "pi pi-indian-rupee"},
				],
			},
			{
				"id": "Movement",
				"label": "Movement",
				"items": [
					{"doctype": "Delivery Challan", "icon": "pi pi-send"},
					{
						"doctype": "Goods Received Note",
						"icon": "pi pi-plus-circle",
					},
					{"doctype": "Stock Entry", "icon": "pi pi-sync"},
					{
						"doctype": "Lot Transfer",
						"icon": "pi pi-arrow-right-arrow-left",
					},
				],
			},
			{
				"id": "Masters",
				"label": "Masters",
				"items": [
					{"doctype": "Item", "icon": "pi pi-box"},
					{
						"doctype": "Item Production Detail",
						"icon": "pi pi-table",
					},
					{"doctype": "Terms and Condition", "icon": "pi pi-book"},
				],
			},
		],
		"hidden": {},
	}
	config["chrome"] = {"search": True, "themeToggle": True}
	config["quickCreate"] = ["Lot", "Work Order", "Delivery Challan"]

	blocks = config.setdefault("screens", {}).setdefault("home", {}).setdefault(
		"blocks", []
	)
	for block in blocks:
		if block.get("id") == "greet":
			block["props"] = {
				"sub": "Production, movement and stock at a glance.",
				"newCta": {
					"primary": "Lot",
					"menu": ["Work Order", "Delivery Challan"],
				},
			}
			break

	theme = config.setdefault("theme", {})
	theme.update(
		{
			"focus": "#C15F3F",
			"density": "comfortable",
			"fontScale": 1,
			"font": '"Inter Variable", Inter, sans-serif',
		}
	)

	serialized = json.dumps(config, indent=1)
	# Hard validation errors must stop the migration rather than ship a broken
	# sole layout. Soft warnings remain visible when an administrator edits it.
	validate_config(serialized, layer="layout")
	doc.config = serialized
	doc.description = (
		"Essdee's sole and default /web layout: premium warm-white surfaces, "
		"pinned navigation, complete production and movement access, clear "
		"home actions, and a matching dark palette."
	)
	doc.save(ignore_permissions=True)


def _repoint_preferences():
	if not frappe.db.table_exists("YRP UI Preference"):
		return
	for name in frappe.get_all("YRP UI Preference", pluck="name"):
		frappe.db.set_value(
			"YRP UI Preference",
			name,
			"layout",
			PREMIUM_LAYOUT_NAME,
			update_modified=False,
		)


def _remove_other_layouts():
	other_layouts = frappe.get_all(
		"UI Layout",
		filters={"name": ["!=", PREMIUM_LAYOUT_NAME]},
		pluck="name",
	)
	if not other_layouts:
		return

	if frappe.db.table_exists("YRP UI Terminology"):
		terminology = frappe.get_all(
			"YRP UI Terminology",
			filters={"ui_layout": ["in", other_layouts]},
			pluck="name",
		)
		if terminology and frappe.db.table_exists("YRP UI Term"):
			frappe.db.delete("YRP UI Term", {"parent": ["in", terminology]})
		if terminology:
			frappe.db.delete("YRP UI Terminology", {"name": ["in", terminology]})

	# UI Layout's controller protects the base record named Default. The owner
	# explicitly retired it for this app, and references were removed above.
	frappe.db.delete("UI Layout", {"name": ["in", other_layouts]})
