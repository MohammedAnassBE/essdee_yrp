from unittest import TestCase

import frappe


class TestPurchaseWebCapabilities(TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.savepoint = "purchase_capabilities_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(cls.savepoint)
		cls.suffix = frappe.generate_hash(length=8)
		cls.fixture_users = {
			"purchase_manager": cls._make_user(
				"purchase-manager", ["Purchase Manager", "Purchase User"]
			),
			"item_manager": cls._make_user("item-manager", ["Item Manager"]),
			"purchase_user": cls._make_user("purchase-user", ["Purchase User"]),
			"roleless": cls._make_user("roleless", []),
		}
		frappe.clear_cache()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in cls.fixture_users.values():
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		frappe.db.rollback(save_point=cls.savepoint)

	@classmethod
	def _make_user(cls, label, roles):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"round2-cap-{label}-{cls.suffix}@example.test",
				"first_name": f"Round 2 Cap {label}",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_capabilities_match_doctype_permissions_for_each_fixture_role(self):
		from essdee_yrp.purchase.web_capabilities import get_capabilities

		for role_key, user in self.fixture_users.items():
			with self.subTest(role=role_key):
				frappe.set_user(user)
				payload = get_capabilities()
				for key, doctype, permission_types in (
					("lots", "SD YRP Lot", ("read", "create", "write")),
					("items", "Item", ("read", "create", "write")),
					(
						"item_prices",
						"YRP Item Price",
						("read", "create", "write", "submit"),
					),
					(
						"bill_tracking",
						"YRP Bill Tracking",
						("read", "create", "write", "submit"),
					),
				):
					can_read = bool(frappe.has_permission(doctype, "read"))
					self.assertEqual(key in payload["sections"], can_read)
					if can_read:
						self.assertEqual(
							{
								permission_type: payload["sections"][key][f"can_{permission_type}"]
								for permission_type in permission_types
							},
							{
								permission_type: bool(
									frappe.has_permission(doctype, permission_type)
								)
								for permission_type in permission_types
							},
						)

	def test_expected_role_differences_are_visible(self):
		from essdee_yrp.purchase.web_capabilities import get_capabilities

		frappe.set_user(self.fixture_users["purchase_manager"])
		manager = get_capabilities()
		self.assertTrue(manager["sections"]["items"]["can_create"])
		self.assertTrue(manager["sections"]["item_prices"]["can_submit"])

		frappe.set_user(self.fixture_users["purchase_user"])
		purchase_user = get_capabilities()
		self.assertFalse(purchase_user["sections"]["items"]["can_create"])
		self.assertTrue(purchase_user["sections"]["item_prices"]["can_create"])
		self.assertFalse(purchase_user["sections"]["item_prices"]["can_submit"])

		frappe.set_user(self.fixture_users["item_manager"])
		item_manager = get_capabilities()
		self.assertTrue(item_manager["sections"]["items"]["can_create"])

	def test_lot_all_role_can_write_without_create(self):
		from essdee_yrp.purchase.web_capabilities import get_capabilities

		frappe.set_user(self.fixture_users["roleless"])
		lots = get_capabilities()["sections"]["lots"]
		self.assertTrue(lots["can_write"])
		self.assertFalse(lots["can_create"])

	def test_lot_merchandiser_can_create_and_write(self):
		from essdee_yrp.purchase.web_capabilities import get_capabilities

		if not frappe.db.exists("Role", "Merchandiser"):
			self.skipTest("Merchandiser role fixture is missing")
		user = self._make_user("lot-merchandiser", ["Merchandiser"])
		self.fixture_users["lot_merchandiser"] = user
		frappe.set_user(user)
		lots = get_capabilities()["sections"]["lots"]
		self.assertTrue(lots["can_write"])
		self.assertTrue(lots["can_create"])

	def test_item_prices_return_the_ordered_workflow_states(self):
		from frappe.model.workflow import get_workflow

		from essdee_yrp.purchase.web_capabilities import get_capabilities

		frappe.set_user(self.fixture_users["purchase_user"])
		sections = get_capabilities()["sections"]
		self.assertEqual(
			sections["item_prices"]["workflow_states"],
			[row.state for row in get_workflow("YRP Item Price").states],
		)
		self.assertEqual(sections["items"]["workflow_states"], [])
