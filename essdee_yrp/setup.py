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


def after_install():
	ensure_default_address_template()


def after_migrate():
	ensure_default_address_template()
	ensure_sd_yrp_consumer_config()


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
