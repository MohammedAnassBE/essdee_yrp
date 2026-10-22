import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.duplicate import build_duplicate_values, get_duplicate_values

PARENT = "Test YRP Duplicate Source"
CHILD = "Test YRP Duplicate Row"
READER_ROLE = "Test YRP Duplicate Reader"
READER = "duplicate-reader@test.local"


def ensure_doctypes():
	if not frappe.db.exists("DocType", CHILD):
		frappe.get_doc({
			"doctype": "DocType", "name": CHILD, "module": "Core", "custom": 1, "istable": 1,
			"fields": [{"fieldname": "item", "label": "Item", "fieldtype": "Data"}],
		}).insert()
	if not frappe.db.exists("DocType", PARENT):
		frappe.get_doc({
			"doctype": "DocType", "name": PARENT, "module": "Core", "custom": 1, "is_submittable": 1,
			"fields": [
				{"fieldname": "title", "label": "Title", "fieldtype": "Data"},
				{"fieldname": "reference", "label": "Reference", "fieldtype": "Data", "no_copy": 1},
				{"fieldname": "rows", "label": "Rows", "fieldtype": "Table", "options": CHILD},
			],
			"permissions": [
				{"role": "System Manager", "read": 1, "write": 1, "create": 1, "submit": 1},
				{"role": READER_ROLE, "read": 1, "write": 0, "create": 0, "delete": 0},
			],
		}).insert()


def ensure_reader():
	if not frappe.db.exists("Role", READER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": READER_ROLE, "desk_access": 1}).insert()
	if not frappe.db.exists("User", READER):
		user = frappe.get_doc({"doctype": "User", "email": READER, "first_name": "Duplicate", "send_welcome_email": 0})
		user.append("roles", {"role": READER_ROLE})
		user.insert(ignore_permissions=True)


class TestDuplicateValues(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_reader()
		ensure_doctypes()
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.source = frappe.get_doc({
			"doctype": PARENT, "title": "Blue shirts", "reference": "REF-1",
			"rows": [{"item": "Shirt"}, {"item": "Collar"}],
		}).insert()
		self.source.submit()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_resets_identity_and_skips_no_copy_fields(self):
		values = build_duplicate_values(PARENT, self.source.name)
		self.assertEqual(values["doctype"], PARENT)
		self.assertEqual(values["title"], "Blue shirts")
		self.assertEqual(values["docstatus"], 0)
		self.assertFalse(values.get("reference"))
		for key in ("name", "owner", "creation", "modified", "modified_by", "amended_from", "__islocal"):
			self.assertNotIn(key, values)

	def test_does_not_insert_or_name_a_document(self):
		count = frappe.db.count(PARENT)
		values = get_duplicate_values(PARENT, self.source.name)
		self.assertEqual(frappe.db.count(PARENT), count)
		self.assertNotIn("name", values)

	def test_copies_child_rows_without_names(self):
		rows = get_duplicate_values(PARENT, self.source.name)["rows"]
		self.assertEqual([row["item"] for row in rows], ["Shirt", "Collar"])
		for row in rows:
			self.assertEqual(row["doctype"], CHILD)
			for key in ("name", "parent", "parentfield", "parenttype", "docstatus"):
				self.assertNotIn(key, row)

	def test_requires_create_permission(self):
		frappe.set_user(READER)
		with self.assertRaises(frappe.PermissionError):
			get_duplicate_values(PARENT, self.source.name)

	def test_refuses_hide_copy_doctype(self):
		self.assertTrue(frappe.get_meta("SD YRP Cut Bundle Movement Ledger").allow_copy)
		with self.assertRaises(frappe.ValidationError):
			get_duplicate_values("SD YRP Cut Bundle Movement Ledger", "missing")

	def test_refuses_child_table_doctype(self):
		with self.assertRaises(frappe.ValidationError):
			get_duplicate_values(CHILD, "missing")
