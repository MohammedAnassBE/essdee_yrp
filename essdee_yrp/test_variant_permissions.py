from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_template.sd_yrp_lot_template import get_calculated_bom
from essdee_yrp.setup import ensure_production_planner_read_permissions

PLANNER_USER = "_test_variant_production_planner@example.com"
ROLELESS_USER = "_test_variant_roleless@example.com"
LOT_TEMPLATE_MODULE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_lot_template.sd_yrp_lot_template"


def _user(email, roles=()):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "Variant", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.add_roles(*roles)
	return email


def _item_permissions(role):
	return frappe.get_all(
		"Custom DocPerm",
		filters={"parent": "Item", "role": role, "permlevel": 0, "if_owner": 0},
		fields=["read", "write", "create"],
	)


class TestProductionPlannerItemRead(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_planner_gets_item_read_without_create_or_write(self):
		frappe.db.delete("Custom DocPerm", {"parent": "Item", "role": "Production Planner"})
		frappe.clear_cache(doctype="Item")

		ensure_production_planner_read_permissions()
		ensure_production_planner_read_permissions()

		self.assertEqual(_item_permissions("Production Planner"), [{"read": 1, "write": 0, "create": 0}])
		self.assertEqual(_item_permissions("Item Manager"), [{"read": 1, "write": 1, "create": 1}])
		frappe.set_user(_user(PLANNER_USER, ["Production Planner"]))
		self.assertTrue(frappe.has_permission("Item", "read"))
		self.assertFalse(frappe.has_permission("Item", "create"))
		self.assertFalse(frappe.has_permission("Item", "write"))

	def test_calculated_bom_requires_lot_template_read_before_creating_variants(self):
		lot_template = frappe.get_doc(
			{
				"doctype": "SD YRP Lot Template",
				"name": f"_Test Lot Template {frappe.generate_hash(length=8)}",
				"item": frappe.db.get_value("Item", {"has_variants": 1}),
			}
		).insert(ignore_permissions=True)
		frappe.set_user(_user(ROLELESS_USER))

		with (
			patch(f"{LOT_TEMPLATE_MODULE}.get_or_create_variant") as create_variant,
			self.assertRaises(frappe.PermissionError),
		):
			get_calculated_bom(lot_template.name, [])
		create_variant.assert_not_called()
