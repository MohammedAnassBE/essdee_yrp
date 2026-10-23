import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.document_activity import (
	VersionParser,
	display_value,
	get_document_activity,
	get_full_names,
)

PARENT = "Test YRP Activity Source"
CHILD = "Test YRP Activity Row"
READER_ROLE = "Test YRP Activity Reader"
READER = "activity-reader@test.local"
STRANGER = "activity-stranger@test.local"


def ensure_doctypes():
	if not frappe.db.exists("DocType", CHILD):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": CHILD,
				"module": "Core",
				"custom": 1,
				"istable": 1,
				"fields": [
					{"fieldname": "item", "label": "Item Name", "fieldtype": "Data"},
					{"fieldname": "qty", "label": "Quantity", "fieldtype": "Float"},
					{"fieldname": "row_secret", "label": "Row Secret", "fieldtype": "Data", "hidden": 1},
				],
			}
		).insert()
	if not frappe.db.exists("DocType", PARENT):
		frappe.get_doc(
			{
				"doctype": "DocType",
				"name": PARENT,
				"module": "Core",
				"custom": 1,
				"is_submittable": 1,
				"track_changes": 1,
				"fields": [
					{"fieldname": "title", "label": "Title", "fieldtype": "Data", "allow_on_submit": 1},
					{"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date"},
					{"fieldname": "is_urgent", "label": "Is Urgent", "fieldtype": "Check"},
					{"fieldname": "secret", "label": "Secret", "fieldtype": "Data", "hidden": 1},
					{"fieldname": "rate", "label": "Rate", "fieldtype": "Data", "permlevel": 1},
					{"fieldname": "rows", "label": "Lines", "fieldtype": "Table", "options": CHILD},
				],
				"permissions": [
					{
						"role": "System Manager",
						"read": 1,
						"write": 1,
						"create": 1,
						"submit": 1,
						"cancel": 1,
						"amend": 1,
					},
					{"role": "System Manager", "permlevel": 1, "read": 1, "write": 1},
					{"role": READER_ROLE, "read": 1},
				],
			}
		).insert()


def ensure_users():
	if not frappe.db.exists("Role", READER_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": READER_ROLE, "desk_access": 1}).insert()
	for email, first_name, roles in ((READER, "Activity", [READER_ROLE]), (STRANGER, "Stranger", [])):
		if not frappe.db.exists("User", email):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first_name,
					"last_name": "Tester",
					"send_welcome_email": 0,
				}
			)
			for role in roles:
				user.append("roles", {"role": role})
			user.insert(ignore_permissions=True)


def set_docstatus(doc, docstatus):
	"""Submit or cancel with a Version row; tests skip versions by default."""
	doc.docstatus = docstatus
	doc.save(ignore_version=False)


def version(data, owner="Administrator", name="v-1"):
	return frappe._dict(name=name, owner=owner, creation="2026-10-23 10:15:00", data=json.dumps(data))


class TestVersionParser(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_users()
		ensure_doctypes()
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.parser = VersionParser(frappe.get_meta(PARENT))

	def test_field_changes_use_labels_and_skip_hidden_fields(self):
		entry = self.parser.parse(
			version({"changed": [["title", "Old", "New"], ["secret", "a", "b"], ["is_urgent", 0, 1]]})
		)
		self.assertEqual(
			entry["changes"],
			[
				{"label": "Title", "fieldtype": "Data", "old": "Old", "new": "New"},
				{"label": "Is Urgent", "fieldtype": "Check", "old": 0, "new": 1},
			],
		)
		self.assertEqual(entry["events"], [])

	def test_docstatus_changes_become_events(self):
		self.assertEqual(
			self.parser.parse(version({"changed": [["docstatus", 0, 1]]}))["events"], ["submitted"]
		)
		self.assertEqual(
			self.parser.parse(version({"changed": [["docstatus", 1, 2]]}))["events"], ["cancelled"]
		)

	def test_child_rows_are_counted_and_row_changes_numbered(self):
		entry = self.parser.parse(
			version(
				{
					"added": [["rows", {"item": "A"}], ["rows", {"item": "B"}]],
					"removed": [["rows", {"item": "C"}]],
					"row_changed": [["rows", 2, "row-3", [["qty", 1, 4], ["row_secret", "x", "y"]]]],
				}
			)
		)
		self.assertEqual(entry["rows_added"], [{"table": "Lines", "count": 2}])
		self.assertEqual(entry["rows_removed"], [{"table": "Lines", "count": 1}])
		self.assertEqual(
			entry["row_changes"],
			[
				{
					"table": "Lines",
					"row": 3,
					"changes": [{"label": "Quantity", "fieldtype": "Float", "old": 1, "new": 4}],
				}
			],
		)

	def test_created_via_updater_reference(self):
		entry = self.parser.parse(
			version(
				{
					"created_by": "Administrator",
					"updater_reference": {"doctype": "Data Import", "docname": "DI-1"},
				}
			)
		)
		self.assertEqual(entry["events"], ["created"])
		self.assertEqual(entry["via"], "Data Import DI-1")

	def test_versions_with_only_invisible_changes_are_skipped(self):
		self.assertIsNone(
			self.parser.parse(version({"changed": [["secret", "a", "b"], ["unknown_field", 1, 2]]}))
		)
		self.assertIsNone(self.parser.parse(version({"comment": "legacy"})))

	def test_permlevel_fields_hidden_from_readers_without_access(self):
		frappe.set_user(READER)
		parser = VersionParser(frappe.get_meta(PARENT))
		self.assertIsNone(parser.parse(version({"changed": [["rate", "10", "12"]]})))
		frappe.set_user("Administrator")
		self.assertEqual(
			self.parser.parse(version({"changed": [["rate", "10", "12"]]}))["changes"][0]["label"], "Rate"
		)

	def test_display_value_strips_html_and_truncates(self):
		self.assertEqual(display_value("<b>Bold</b>"), "Bold")
		self.assertEqual(len(display_value("x" * 200)), 80)
		self.assertIsNone(display_value(None))


class TestDocumentActivity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_users()
		ensure_doctypes()
		frappe.db.commit()

	def setUp(self):
		frappe.set_user("Administrator")
		self.doc = frappe.get_doc(
			{"doctype": PARENT, "title": "First", "rows": [{"item": "Shirt", "qty": 1}]}
		).insert()
		self.doc.title = "Second"
		self.doc.append("rows", {"item": "Collar", "qty": 2})
		self.doc.save(ignore_version=False)
		self.doc.rows[0].qty = 5
		self.doc.save(ignore_version=False)
		set_docstatus(self.doc, 1)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_returns_stamps_and_versions_newest_first(self):
		activity = get_document_activity(PARENT, self.doc.name)
		self.assertEqual(activity["created"]["user"], "Administrator")
		self.assertEqual(activity["created"]["at"], str(self.doc.creation))
		self.assertEqual(
			activity["modified"]["at"], str(frappe.db.get_value(PARENT, self.doc.name, "modified"))
		)
		versions = activity["versions"]
		self.assertEqual(versions[0]["events"], ["submitted"])
		self.assertEqual(versions[1]["row_changes"][0]["row"], 1)
		self.assertEqual(
			versions[2]["changes"][0],
			{"label": "Title", "fieldtype": "Data", "old": "First", "new": "Second"},
		)
		self.assertEqual(versions[2]["rows_added"], [{"table": "Lines", "count": 1}])
		self.assertFalse(activity["has_more"])

	def test_paginates_with_limit_and_offset(self):
		first = get_document_activity(PARENT, self.doc.name, start=0, page_length=2)
		self.assertEqual(len(first["versions"]), 2)
		self.assertTrue(first["has_more"])
		self.assertEqual(first["next_start"], 2)
		rest = get_document_activity(PARENT, self.doc.name, start=first["next_start"], page_length=2)
		self.assertFalse(rest["has_more"])
		self.assertEqual(rest["versions"][0]["changes"][0]["new"], "Second")

	def test_pages_skip_versions_with_nothing_visible(self):
		for value in ("a", "b", "c"):
			frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": PARENT,
					"docname": self.doc.name,
					"data": json.dumps({"changed": [["secret", "", value]]}),
				}
			).insert(ignore_permissions=True)
		first = get_document_activity(PARENT, self.doc.name, start=0, page_length=1)
		self.assertEqual(first["versions"][0]["events"], ["submitted"])
		self.assertEqual(first["next_start"], 4)
		self.assertTrue(first["has_more"])
		rest = get_document_activity(PARENT, self.doc.name, start=first["next_start"], page_length=10)
		self.assertEqual(len(rest["versions"]), 2)
		self.assertFalse(rest["has_more"])

	def test_amended_document_reports_its_source(self):
		set_docstatus(self.doc, 2)
		amended = frappe.copy_doc(self.doc)
		amended.amended_from = self.doc.name
		amended.docstatus = 0
		amended.insert()
		activity = get_document_activity(PARENT, amended.name)
		self.assertEqual(activity["created"]["amended_from"], self.doc.name)
		self.assertEqual(activity["versions"][0]["events"], ["amended"])
		self.assertEqual(activity["versions"][0]["amended_from"], self.doc.name)
		self.assertEqual(get_document_activity(PARENT, self.doc.name)["versions"][0]["events"], ["cancelled"])

	def test_returns_user_full_names(self):
		frappe.set_user(READER)
		activity = get_document_activity(PARENT, self.doc.name)
		self.assertEqual(activity["created"]["user_name"], "Administrator")
		self.assertEqual(activity["versions"][0]["user_name"], "Administrator")
		self.assertEqual(
			get_full_names({READER, "Administrator", None}),
			{READER: "Activity Tester", "Administrator": "Administrator"},
		)

	def test_requires_read_permission(self):
		frappe.set_user(STRANGER)
		with self.assertRaises(frappe.PermissionError):
			get_document_activity(PARENT, self.doc.name)
