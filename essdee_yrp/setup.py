"""Consumer-site setup tasks for essdee_yrp.

essdee_yrp.site (and siblings) run frappe + yrp only, without ERPNext's setup
wizard. Records the wizard would normally create are therefore absent. This
module recreates the ones the consumer needs so synced master data (Suppliers,
Addresses, Contacts) opens cleanly.

Wired from hooks.py as `after_install` and `after_migrate` — both idempotent.
"""

import frappe
from frappe.contacts.doctype.address_template.address_template import (
	get_default_address_template,
)

from essdee_yrp.web_build import build_web_spa


# Roles referenced by the migrated MRP DocType permissions but not provided by
# base YRP. Keep these as setup records rather than a Role fixture so migrations
# never delete or recreate an existing role.
MRP_SCHEMA_ROLES = (
	"Brand QA Manager",
	"Brand QA User",
	"CAD User",
	"Cutting User",
	"Merch Manager",
	"Store Manager",
	"T & A Admin",
	"T & A Manager",
	"T & A User",
	"T & A Viewer",
)


def after_install():
	ensure_default_address_template()
	ensure_mrp_schema_roles()
	ensure_yrp_production_order_settings()
	ensure_lot_packing_boundary()


def after_migrate():
	ensure_default_address_template()
	ensure_mrp_schema_roles()
	ensure_sd_yrp_consumer_config()
	ensure_yrp_production_order_settings()
	ensure_lot_packing_boundary()
	build_web_spa()


def ensure_mrp_schema_roles():
	"""Create only the missing application roles referenced by MRP schemas."""
	for role_name in MRP_SCHEMA_ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)


def ensure_lot_packing_boundary():
	"""Keep Essdee-owned fields reliable on fresh installs and upgrades."""
	from essdee_yrp.lot_packing_setup import ensure_boundary

	ensure_boundary()


def ensure_sd_yrp_consumer_config():
	"""Keep the Spine consumer handler mappings in step with SYNC_DOCTYPES.

	Spine treats an unmapped doctype as success — the message is marked
	Processed and silently discarded — so a SYNC_DOCTYPES addition without its
	mapping row drops data with no error. Running the (idempotent)
	ensure_consumer_config on every migrate closes that class permanently.
	"""
	from essdee_yrp.sd_yrp_sync import ensure_consumer_config

	ensure_consumer_config()


def ensure_default_address_template():
	"""Create a default Address Template if none is marked default.

	Without a default, opening any Address (e.g. a synced Supplier's) throws
	"No default Address Template found" from
	frappe.contacts.doctype.address.address.get_address_templates.

	Idempotent: no-op when a default already exists.
	"""
	if frappe.db.get_value("Address Template", {"is_default": 1}, "name"):
		return

	doc = frappe.new_doc("Address Template")
	doc.country = "India"
	doc.is_default = 1
	doc.template = get_default_address_template()
	doc.insert(ignore_permissions=True)


def ensure_yrp_production_order_settings():
	"""Install the Production Order mapping required by the SD YRP consumer.

	The base YRP app intentionally leaves these customer-specific choices blank.
	Essdee's F15 Production Orders are size-grid documents whose generated
	variants use Stage=Pack. A missing mapping prevents the Production Order from
	syncing and every linked Lot then fails with a misleading missing-dependency
	error.

	The function is idempotent and preserves additional configured attributes.
	On a brand-new site it waits until the synced Size/Stage/Pack masters exist;
	the first Production Order message calls it again before validation.
	"""
	from essdee_yrp.sd_yrp_sync import (
		PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
		PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
		PRODUCTION_ORDER_GRID_ATTRIBUTE,
	)

	required_links = (
		("Item Attribute", PRODUCTION_ORDER_GRID_ATTRIBUTE),
		("Item Attribute", PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE),
		("Item Attribute Value", PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE),
	)
	if any(not frappe.db.exists(doctype, name) for doctype, name in required_links):
		return False

	settings = frappe.get_doc("YRP Settings")
	changed = False
	grid_row = None
	for row in settings.production_order_attributes or []:
		if row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE:
			grid_row = row
		should_be_grid = row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE
		if bool(row.is_grid_attribute) != should_be_grid:
			row.is_grid_attribute = should_be_grid
			changed = True

	if grid_row is None:
		settings.append(
			"production_order_attributes",
			{
				"attribute": PRODUCTION_ORDER_GRID_ATTRIBUTE,
				"is_grid_attribute": 1,
			},
		)
		changed = True

	if settings.po_dependent_attribute != PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE:
		settings.po_dependent_attribute = PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE
		changed = True
	if (
		settings.po_dependent_attribute_value
		!= PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE
	):
		settings.po_dependent_attribute_value = PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE
		changed = True

	if changed:
		settings.save(ignore_permissions=True)
	return changed
