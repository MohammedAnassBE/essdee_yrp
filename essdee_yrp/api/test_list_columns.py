import frappe
from frappe.client import get_list as client_get_list
from frappe.core.doctype.doctype.test_doctype import new_doctype
from frappe.model import get_permitted_fields
from frappe.permissions import get_role_permissions
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.list_columns import (
	get_allowed_list_fields,
	get_user_listview,
	reset_user_listview,
	save_user_listview,
)


class TestListColumns(IntegrationTestCase):
	DOCTYPE = "Test Essdee List Columns"
	ROLE = "Test Essdee List Columns Role"
	USER = "test_list_columns@example.com"
	SELECT_ROLE = "Test Essdee List Columns Select Role"
	SELECT_USER = "test_list_columns_select@example.com"

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.delete_doc_if_exists("DocType", cls.DOCTYPE, force=True)
		for user in (cls.USER, cls.SELECT_USER):
			frappe.delete_doc_if_exists("User", user, force=True)
		for role in (cls.ROLE, cls.SELECT_ROLE):
			frappe.delete_doc_if_exists("Role", role, force=True)

		for role in (cls.ROLE, cls.SELECT_ROLE):
			frappe.get_doc(
				{
					"doctype": "Role",
					"role_name": role,
					"desk_access": 1,
				}
			).insert(ignore_permissions=True)
		for email, first_name, role in (
			(cls.USER, "List Columns Test", cls.ROLE),
			(cls.SELECT_USER, "List Columns Select Test", cls.SELECT_ROLE),
		):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": first_name,
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
		new_doctype(
			cls.DOCTYPE,
			search_fields="public_field, restricted_field",
			fields=[
				{
					"fieldname": "public_field",
					"fieldtype": "Data",
					"label": "Public Field",
					"in_list_view": 1,
				},
				{
					"fieldname": "restricted_field",
					"fieldtype": "Data",
					"label": "Restricted Field",
					"permlevel": 1,
				},
				{
					"fieldname": "masked_field",
					"fieldtype": "Data",
					"label": "Masked Field",
					"mask": 1,
				},
				{
					"fieldname": "hidden_view_field",
					"fieldtype": "Data",
					"label": "Hidden View Field",
					"hidden": 1,
				},
				{
					"fieldname": "party_account_currency",
					"fieldtype": "Link",
					"label": "Party Account Currency",
					"options": "Currency",
					"hidden": 1,
				},
				{
					"fieldname": "advance_paid",
					"fieldtype": "Currency",
					"label": "Advance Paid",
					"options": "party_account_currency",
					"in_list_view": 1,
				},
				{
					"fieldname": "attach_image",
					"fieldtype": "Attach Image",
					"label": "Attached Image",
				},
				{
					"fieldname": "signature",
					"fieldtype": "Signature",
					"label": "Signature",
				},
				{
					"fieldname": "ignored_section",
					"fieldtype": "Section Break",
					"label": "Ignored Section",
				},
				{
					"fieldname": "ignored_image",
					"fieldtype": "Image",
					"label": "Ignored Image",
					"options": "attach_image",
				},
			],
			permissions=[
				{"role": cls.ROLE, "read": 1},
				{
					"role": cls.SELECT_ROLE,
					"select": 1,
					"read": 0,
					"write": 0,
					"create": 0,
					"delete": 0,
				},
				{
					"role": "System Manager",
					"read": 1,
					"write": 1,
					"create": 1,
					"delete": 1,
					"mask": 1,
				},
			],
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=cls.DOCTYPE)
		cls.record = frappe.get_doc(
			{
				"doctype": cls.DOCTYPE,
				"public_field": "visible value",
				"restricted_field": "restricted value",
				"masked_field": "masked value",
				"hidden_view_field": "view value",
				"party_account_currency": "INR",
				"advance_paid": 100,
				"attach_image": "/files/list-columns-image.png",
				"signature": "/files/list-columns-signature.png",
			}
		).insert(ignore_permissions=True)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		cls._delete_preferences()
		if frappe.db.exists("DocType", cls.DOCTYPE):
			frappe.db.delete(cls.DOCTYPE)
			frappe.delete_doc("DocType", cls.DOCTYPE, force=True, ignore_permissions=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{cls.DOCTYPE}`")
		for user in (cls.USER, cls.SELECT_USER):
			frappe.delete_doc_if_exists("User", user, force=True)
		for role in (cls.ROLE, cls.SELECT_ROLE):
			frappe.delete_doc_if_exists("Role", role, force=True)
		frappe.clear_cache(doctype=cls.DOCTYPE)
		# DocType DDL commits implicitly, so the cleanup must be committed too.
		frappe.db.commit()  # nosemgrep
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self._delete_preferences()
		frappe.set_user(self.USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		self._delete_preferences()
		frappe.set_user(self.previous_user)
		super().tearDown()

	@classmethod
	def _delete_preferences(cls):
		names = frappe.get_all(
			"YRP User Listview",
			filters={
				"user": ("in", (cls.USER, cls.SELECT_USER)),
				"doctype_name": cls.DOCTYPE,
			},
			pluck="name",
		)
		if names:
			frappe.db.delete("YRP User Listview Field", {"parent": ("in", names)})
			frappe.db.delete("YRP User Listview", {"name": ("in", names)})

	def test_meta_visibility_standard_and_image_fields(self):
		fields = get_allowed_list_fields(self.DOCTYPE)
		by_name = {field["fieldname"]: field for field in fields}

		self.assertTrue(
			{"name", "owner", "creation", "modified_by", "modified", "public_field"}.issubset(
				by_name
			)
		)
		self.assertEqual(by_name["owner"]["label"], "Created By")
		self.assertEqual(by_name["creation"]["fieldtype"], "Datetime")
		self.assertEqual(by_name["attach_image"]["fieldtype"], "Attach Image")
		self.assertEqual(by_name["signature"]["fieldtype"], "Signature")
		self.assertNotIn("hidden_view_field", by_name)
		self.assertNotIn("ignored_section", by_name)
		self.assertNotIn("ignored_image", by_name)

		with_view_field = get_allowed_list_fields(self.DOCTYPE, ["hidden_view_field"])
		hidden = next(
			field for field in with_view_field if field["fieldname"] == "hidden_view_field"
		)
		self.assertEqual(hidden["label"], "Hidden View Field")
		self.assertEqual(hidden["hidden"], 1)

	def test_hidden_currency_reference_is_returned_as_fetch_only_dependency(self):
		settings = get_user_listview(self.DOCTYPE)
		fieldnames = {field["fieldname"] for field in settings["fields"]}

		self.assertIn("advance_paid", fieldnames)
		self.assertNotIn("party_account_currency", fieldnames)
		self.assertEqual(
			settings["currency_fields"],
			{"advance_paid": "party_account_currency"},
		)

		rows = client_get_list(
			self.DOCTYPE,
			fields=["name", "advance_paid", "party_account_currency"],
			filters={"name": self.record.name},
			limit_page_length=1,
		)
		self.assertEqual(rows[0].party_account_currency, "INR")
		self.assertEqual(rows[0].advance_paid, 100)

	def test_view_fields_and_save_cannot_expose_restricted_or_masked_fields(self):
		fields = get_allowed_list_fields(
			self.DOCTYPE,
			["hidden_view_field", "restricted_field", "masked_field"],
		)
		fieldnames = {field["fieldname"] for field in fields}

		self.assertIn("public_field", fieldnames)
		self.assertIn("hidden_view_field", fieldnames)
		self.assertNotIn("restricted_field", fieldnames)
		self.assertNotIn("masked_field", fieldnames)

		for fieldname in ("restricted_field", "masked_field"):
			with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
				save_user_listview(
					self.DOCTYPE,
					[{"fieldname": fieldname, "enabled": 1}],
					["hidden_view_field", "restricted_field", "masked_field"],
				)

	def test_select_only_search_field_requires_read_permlevel_access(self):
		frappe.set_user(self.SELECT_USER)
		roles = frappe.get_roles(self.SELECT_USER)
		permissions = get_role_permissions(self.DOCTYPE, user=self.SELECT_USER)
		self.assertTrue(permissions.get("select"), {"roles": roles, "permissions": permissions})
		self.assertFalse(permissions.get("read"), {"roles": roles, "permissions": permissions})
		self.assertTrue(frappe.only_has_select_perm(self.DOCTYPE))
		self.assertIn(
			"restricted_field",
			get_permitted_fields(self.DOCTYPE, permission_type="select"),
		)

		fields = get_allowed_list_fields(self.DOCTYPE, ["restricted_field"])
		fieldnames = {field["fieldname"] for field in fields}
		self.assertIn("public_field", fieldnames)
		self.assertNotIn("restricted_field", fieldnames)

		rows = client_get_list(
			self.DOCTYPE,
			fields=["name", "restricted_field"],
			filters={"name": self.record.name},
			limit_page_length=1,
		)
		self.assertEqual(len(rows), 1)
		self.assertNotIn("restricted_field", rows[0])

		with self.assertRaises(frappe.ValidationError):
			save_user_listview(
				self.DOCTYPE,
				[{"fieldname": "restricted_field", "enabled": 1}],
				["restricted_field"],
			)

	def test_save_rejects_invalid_and_empty_columns_without_overwriting(self):
		for fieldname in ("not_a_real_field", "hidden_view_field"):
			with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
				save_user_listview(
					self.DOCTYPE,
					[{"fieldname": fieldname, "enabled": 1}],
				)

		existing_columns = [{"fieldname": "public_field", "enabled": 1}]
		self.assertEqual(save_user_listview(self.DOCTYPE, existing_columns), "ok")
		with self.assertRaises(frappe.ValidationError):
			save_user_listview(self.DOCTYPE, [])
		self.assertEqual(get_user_listview(self.DOCTYPE)["columns"], existing_columns)

	def test_save_and_get_roundtrip_keeps_order_and_standard_fields(self):
		columns = [
			{"fieldname": "creation", "enabled": 1},
			{"fieldname": "hidden_view_field", "enabled": 1},
			{"fieldname": "owner", "enabled": 0},
		]
		self.assertEqual(
			save_user_listview(self.DOCTYPE, columns, ["hidden_view_field"]),
			"ok",
		)

		settings = get_user_listview(self.DOCTYPE, ["hidden_view_field"])
		self.assertEqual(settings["columns"], columns)
		stored = frappe.get_all(
			"YRP User Listview Field",
			filters={"parent": self._preference_name()},
			fields=["fieldname", "fieldtype", "label"],
			order_by="idx asc",
		)
		self.assertEqual(
			[row.fieldname for row in stored],
			["creation", "hidden_view_field", "owner"],
		)
		self.assertEqual(stored[0].fieldtype, "Datetime")
		self.assertEqual(stored[2].label, "Created By")
		without_hidden_view_field = get_user_listview(self.DOCTYPE)
		self.assertEqual(
			[row["fieldname"] for row in without_hidden_view_field["columns"]],
			["creation", "owner"],
		)

		self.assertEqual(reset_user_listview(self.DOCTYPE), "ok")
		self.assertIsNone(get_user_listview(self.DOCTYPE, ["hidden_view_field"])["columns"])

	def test_empty_and_unavailable_saved_settings_are_returned_as_empty(self):
		preference = frappe.get_doc(
			{
				"doctype": "YRP User Listview",
				"user": self.USER,
				"doctype_name": self.DOCTYPE,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(get_user_listview(self.DOCTYPE)["columns"], [])

		preference.append(
			"fields",
			{
				"fieldname": "restricted_field",
				"fieldtype": "Data",
				"label": "Restricted Field",
				"enabled": 1,
			},
		)
		preference.save(ignore_permissions=True)
		self.assertEqual(
			get_user_listview(self.DOCTYPE, ["restricted_field"])["columns"],
			[],
		)

	def test_list_queries_return_real_values_for_selected_allowed_fields(self):
		fields = [
			"name",
			"public_field",
			"hidden_view_field",
			"attach_image",
			"signature",
		]
		expected = {
			"name": self.record.name,
			"public_field": "visible value",
			"hidden_view_field": "view value",
			"attach_image": "/files/list-columns-image.png",
			"signature": "/files/list-columns-signature.png",
		}
		filters = {"name": self.record.name}

		rows = frappe.get_list(
			self.DOCTYPE,
			fields=fields,
			filters=filters,
			limit=1,
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(dict(rows[0]), expected)

		client_rows = client_get_list(
			self.DOCTYPE,
			fields=fields,
			filters=filters,
			limit_page_length=1,
		)
		self.assertEqual(len(client_rows), 1)
		self.assertEqual(dict(client_rows[0]), expected)

	def _preference_name(self):
		return frappe.db.get_value(
			"YRP User Listview",
			{"user": self.USER, "doctype_name": self.DOCTYPE},
			"name",
		)
