import json
import unittest

import frappe

from essdee_yrp.cut_panel_store.movement_workspace import generate_movement_bundles
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_edit.sd_yrp_cut_bundle_edit import _require_manage_access
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement import (
	get_cut_bundle_unmoved_data,
)
from essdee_yrp.fabric_store.web_workspace import get_collapsed_stock

LEDGER = "SD YRP Cut Bundle Movement Ledger"


class TestCutBundleLedgerPermissions(unittest.TestCase):
	"""Ledger rows are system entries; access is checked on the parent movement only."""

	def setUp(self):
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("cut_bundle_ledger_permissions")
		stock = frappe.db.sql(
			f"""SELECT lot, supplier FROM `tab{LEDGER}`
			WHERE is_cancelled = 0 AND quantity_after_transaction > 0 AND is_collapsed = 0
			ORDER BY posting_datetime DESC LIMIT 1""",
			as_dict=True,
		)
		if not stock:
			self.skipTest("No cut bundle stock on this site.")
		self.lot, self.supplier = stock[0].lot, stock[0].supplier

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="cut_bundle_ledger_permissions")
		frappe.set_user(self.user)

	def make_user(self, role):
		user = f"_test_ledger_perm_{frappe.scrub(role)}@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Ledger Permission",
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
		return user

	def unmoved(self):
		return get_cut_bundle_unmoved_data(self.supplier, self.lot, frappe.utils.nowdate(), "23:59:59", 0)

	def test_movement_user_without_ledger_access_can_load_bundles(self):
		frappe.set_user(self.make_user("Store User"))
		self.assertTrue(frappe.has_permission("SD YRP Cut Panel Movement", "create"))
		self.assertFalse(frappe.has_permission(LEDGER, "read"))

		self.assertTrue(self.unmoved().get("data"))
		generated = generate_movement_bundles(json.dumps({"lot": self.lot, "from_warehouse": self.supplier}))
		self.assertTrue(generated.get("data"))
		self.assertEqual(get_collapsed_stock(self.lot, self.supplier)["lot"], self.lot)
		_require_manage_access(self.lot)

	def test_user_without_movement_access_is_still_blocked(self):
		frappe.set_user(self.make_user("Cutting User"))
		self.assertFalse(frappe.has_permission("SD YRP Cut Panel Movement", "create"))
		with self.assertRaises(frappe.PermissionError):
			self.unmoved()
