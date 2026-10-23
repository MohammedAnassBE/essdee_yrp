import threading
import traceback
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, has_approval_access
from frappe.utils import add_days, formatdate, nowdate
from yrp.concurrency_test_support import commit_connection


def _workspace_fixture_names(doctype, fieldname, token):
	return frappe.get_all(
		doctype,
		filters={fieldname: ["like", f"%{token}%"]},
		pluck="name",
		limit=0,
	)


def _cleanup_workspace_fixture_records(token):
	suppliers = _workspace_fixture_names("Supplier", "name", token)
	prices = set(_workspace_fixture_names("YRP Item Price", "item_name", token))
	if suppliers:
		prices.update(
			frappe.get_all(
				"YRP Item Price",
				filters={"supplier": ["in", suppliers]},
				pluck="name",
				limit=0,
			)
		)
	for name in prices:
		if not frappe.db.exists("YRP Item Price", name):
			continue
		frappe.db.set_value(
			"YRP Item Price",
			name,
			{"docstatus": 0, "workflow_state": "Draft"},
			update_modified=False,
		)
		frappe.delete_doc(
			"YRP Item Price", name, force=True, ignore_permissions=True, delete_permanently=True
		)
	for doctype in ("Item", "Supplier", "UOM", "User"):
		for name in _workspace_fixture_names(doctype, "name", token):
			if frappe.db.exists(doctype, name):
				frappe.delete_doc(
					doctype, name, force=True, ignore_permissions=True, delete_permanently=True
				)
	commit_connection()
	leftovers = {
		doctype: _workspace_fixture_names(doctype, "name", token)
		for doctype in ("Item", "Supplier", "UOM", "User")
	}
	leftovers["YRP Item Price"] = _workspace_fixture_names(
		"YRP Item Price", "item_name", token
	)
	return {doctype: names for doctype, names in leftovers.items() if names}


def _cleanup_workspace_fixture_run(site, sites_path, token):
	result = {}

	def cleanup():
		frappe.init(site, sites_path=sites_path)
		frappe.connect()
		frappe.flags.in_test = True
		frappe.set_user("Administrator")
		try:
			result["leftovers"] = _cleanup_workspace_fixture_records(token)
		except Exception as error:
			frappe.db.rollback()
			result["error"] = f"{error}\n{traceback.format_exc()}"
		finally:
			frappe.destroy()

	thread = threading.Thread(target=cleanup, daemon=True)
	thread.start()
	thread.join(timeout=30)
	if thread.is_alive():
		raise AssertionError(f"Fixture cleanup timed out for run token {token}")
	if result.get("error"):
		raise AssertionError(result["error"])
	if result.get("leftovers"):
		raise AssertionError(f"Committed fixture leftovers for run token {token}: {result['leftovers']}")


class TestPurchaseItemPriceWorkspace(TestCase):
	@classmethod
	def setUpClass(cls):
		frappe.set_user("Administrator")
		cls.savepoint = "purchase_price_workspace_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(cls.savepoint)
		cls.savepoint_active = True
		cls.suffix = frappe.generate_hash(length=8)
		cls.cleanup_site = frappe.local.site
		cls.cleanup_sites_path = frappe.local.sites_path
		cls.addClassCleanup(cls._cleanup_class_fixtures)
		cls.uom = cls._make_uom()
		cls.other_uom = cls._make_uom("Other")
		cls.item = cls._make_item()
		cls.other_item = cls._make_item("Other", cls.other_uom)
		cls.suppliers = [cls._make_supplier(label) for label in ("A", "B")]
		cls.tax = cls._tax_slab()
		cls.fixture_users = {
			"purchase_user": cls._make_user("purchase-user", ["Purchase User"]),
			"purchase_manager": cls._make_user(
				"purchase-manager", ["Purchase User", "Purchase Manager"]
			),
			"manager_only": cls._make_user("manager-only", ["Purchase Manager"]),
			"system_manager": cls._make_user("system-manager", ["System Manager"]),
			"roleless": cls._make_user("roleless", []),
		}

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in cls.fixture_users.values():
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		cls._rollback_class_savepoint()

	@classmethod
	def _rollback_class_savepoint(cls):
		if cls.savepoint_active:
			frappe.db.rollback(save_point=cls.savepoint)
			cls.savepoint_active = False

	@classmethod
	def _cleanup_class_fixtures(cls):
		cls._rollback_class_savepoint()
		_cleanup_workspace_fixture_run(cls.cleanup_site, cls.cleanup_sites_path, cls.suffix)

	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.test_savepoint = "purchase_price_case_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(self.test_savepoint)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point=self.test_savepoint)
		frappe.set_user(self.previous_user)

	@classmethod
	def _make_user(cls, label, roles):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"round2-price-{label}-{cls.suffix}@example.test",
				"first_name": f"Round 2 Price {label}",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _make_uom(cls, label=""):
		return frappe.get_doc(
			{
				"doctype": "UOM",
				"uom_name": f"Web Price Unit {label} {cls.suffix}".replace("  ", " "),
				"enabled": 1,
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _make_item(cls, label="", uom=None):
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_Test Web Price Item {label} {cls.suffix}".replace("  ", " "),
				"item_name": f"_Test Web Price Item {label} {cls.suffix}".replace("  ", " "),
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": uom or cls.uom,
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"is_sales_item": 0,
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _make_supplier(cls, label):
		return frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test Web Price Supplier {label} {cls.suffix}",
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _tax_slab(cls):
		if name := frappe.db.get_value("YRP Tax Slab", {"enabled": 1}, "name"):
			return name
		return frappe.get_doc(
			{
				"doctype": "YRP Tax Slab",
				"percentage": f"0.{cls.suffix[:6]}",
				"enabled": 1,
			}
		).insert(ignore_permissions=True).name

	def _values(self, **overrides):
		values = {
			"item_name": self.item,
			"supplier": self.suppliers[0],
			"from_date": nowdate(),
			"to_date": None,
			"depends_on_attribute": 0,
			"attribute": None,
			"tax": self.tax,
			"item_price_values": [{"moq": 0, "price": 10, "lead_time": 2}],
		}
		values.update(overrides)
		return values

	def _save(self, user_key="purchase_user", **overrides):
		from essdee_yrp.purchase.item_price_workspace import save_item_price

		frappe.set_user(self.fixture_users[user_key])
		return save_item_price(self._values(**overrides))

	def _transition(self, name, action, user_key):
		frappe.set_user(self.fixture_users[user_key])
		return apply_workflow(frappe.get_doc("YRP Item Price", name), action)

	def test_save_uses_allowlist_and_item_stock_uom(self):
		payload = self._save(
			workflow_state="Approved",
			docstatus=1,
			approved_by="Administrator",
			uom="Forged UOM",
			amended_from="ITP-00001",
		)
		doc = frappe.get_doc("YRP Item Price", payload["record"]["name"])

		self.assertEqual(doc.workflow_state, "Draft")
		self.assertEqual(doc.docstatus, 0)
		self.assertFalse(doc.approved_by)
		self.assertEqual(doc.uom, self.uom)
		self.assertFalse(doc.amended_from)

	def test_editor_returns_read_only_uom_enabled_taxes_and_defaults(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(item=self.item)

		self.assertEqual(payload["values"]["item_name"], self.item)
		self.assertEqual(payload["values"]["uom"], self.uom)
		self.assertEqual(payload["values"]["from_date"], nowdate())
		self.assertTrue(payload["fields"]["uom"]["read_only"])
		self.assertIn(self.tax, [row["value"] for row in payload["options"]["tax_slabs"]])
		self.assertEqual(payload["tier_fields"]["moq"]["precision"], frappe.get_precision("YRP Item Price Value", "moq"))
		self.assertEqual(payload["tier_fields"]["price"]["precision"], 3)
		self.assertEqual(payload["tier_fields"]["lead_time"]["precision"], 0)

	def test_editor_prefills_unsaved_duplicate_of_approved_price(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		source = self._price_in_state("Approved")
		count = frappe.db.count("YRP Item Price")
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(duplicate_from=source)

		self.assertEqual(payload["values"]["item_name"], self.item)
		self.assertEqual(payload["values"]["supplier"], self.suppliers[0])
		self.assertEqual(payload["values"]["from_date"], nowdate())
		self.assertIsNone(payload["values"]["approved_by"])
		self.assertIsNone(payload["modified"])
		self.assertEqual(payload["workflow"]["state"], "Draft")
		self.assertTrue(payload["values"]["item_price_values"])
		self.assertTrue(all(not row["name"] for row in payload["values"]["item_price_values"]))
		self.assertEqual(frappe.db.count("YRP Item Price"), count)

	def test_editor_offers_item_picklist_first_then_other_global_values(self):
		from yrp.stock.test_uom import _attribute
		from yrp.yrp.doctype.yrp_item.yrp_item import ensure_global_attribute_values

		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		attribute = f"_Test Web Price Colour {self.suffix}"
		mapping = _attribute(attribute, "Red")
		ensure_global_attribute_values(attribute, ["Blue"], check_permission=False)
		item = frappe.get_doc("Item", self._make_item("Picklist"))
		item.has_variants = 1
		item.append("attributes", {"attribute": attribute, "mapping": mapping})
		item.save(ignore_permissions=True)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(item=item.name)

		options = next(row for row in payload["attributes"] if row["attribute"] == attribute)
		self.assertEqual([value["label"] for value in options["values"]], ["Red", "Blue"])

	def test_editor_offers_numeric_values_outside_the_item_picklist(self):
		from yrp.attribute_values import ensure_value_master

		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		attribute = frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": f"_Test Web Price Gauge {self.suffix}",
				"numeric_values": 1,
				"from_range": 0,
				"to_range": 100,
				"increment": 1,
			}
		).insert(ignore_permissions=True)
		mapping = frappe.get_doc(
			{
				"doctype": "YRP Item Item Attribute Mapping",
				"attribute_name": attribute.name,
				"values": [{"attribute_value": ensure_value_master(attribute.name, "10")}],
			}
		).insert(ignore_permissions=True)
		ensure_value_master(attribute.name, "20")
		item = frappe.get_doc("Item", self._make_item("Gauge"))
		item.has_variants = 1
		item.append("attributes", {"attribute": attribute.name, "mapping": mapping.name})
		item.save(ignore_permissions=True)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(item=item.name)

		options = next(row for row in payload["attributes"] if row["attribute"] == attribute.name)
		self.assertEqual([value["label"] for value in options["values"]], ["10", "20"])

	def test_migrated_draft_keeps_stored_uom_and_rejects_relabelled_prices(self):
		from essdee_yrp.purchase.item_price_workspace import (
			get_item_price_editor,
			save_item_price,
		)

		name = self._save()["record"]["name"]
		frappe.db.set_value("YRP Item Price", name, "uom", self.other_uom, update_modified=False)
		doc = frappe.get_doc("YRP Item Price", name)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(name)

		self.assertEqual(payload["values"]["uom"], self.other_uom)
		self.assertEqual(payload["item_uom"], self.uom)
		self.assertTrue(payload["unit_mismatch"])
		self.assertIn("Re-enter the prices", payload["unit_mismatch_message"])
		with self.assertRaisesRegex(frappe.ValidationError, "Re-enter the prices"):
			save_item_price(payload["values"], name, doc.modified)

		stored = frappe.db.get_value("YRP Item Price", name, ["uom", "price"], as_dict=True)
		self.assertEqual(stored.uom, self.other_uom)
		self.assertEqual(frappe.db.get_value("YRP Item Price Value", {"parent": name}, "price"), 10)

	def test_item_unit_change_is_flagged_without_relabelling_existing_tiers(self):
		from essdee_yrp.purchase.item_price_workspace import (
			get_item_price_editor,
			save_item_price,
		)

		name = self._save()["record"]["name"]
		frappe.db.set_value("Item", self.item, "stock_uom", self.other_uom, update_modified=False)
		doc = frappe.get_doc("YRP Item Price", name)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(name)

		self.assertEqual(payload["values"]["uom"], self.uom)
		self.assertEqual(payload["item_uom"], self.other_uom)
		self.assertTrue(payload["unit_mismatch"])
		with self.assertRaisesRegex(frappe.ValidationError, "new Item Price"):
			save_item_price(payload["values"], name, doc.modified)
		self.assertEqual(frappe.db.get_value("YRP Item Price", name, "uom"), self.uom)

	def test_changing_an_existing_drafts_item_uses_the_new_items_unit(self):
		from essdee_yrp.purchase.item_price_workspace import save_item_price

		name = self._save()["record"]["name"]
		doc = frappe.get_doc("YRP Item Price", name)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = save_item_price(
			self._values(item_name=self.other_item),
			name,
			doc.modified,
		)

		self.assertEqual(payload["record"]["item_name"], self.other_item)
		self.assertEqual(payload["record"]["uom"], self.other_uom)

	def test_save_rejects_invalid_tiers_and_non_editable_states(self):
		from essdee_yrp.purchase.item_price_workspace import save_item_price

		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaisesRegex(frappe.ValidationError, "price tier"):
			save_item_price(self._values(item_price_values=[]))

		approved = self._save(from_date=add_days(nowdate(), -10))["record"]["name"]
		self._transition(approved, "Submit", "purchase_user")
		self._transition(approved, "Approve", "purchase_manager")
		doc = frappe.get_doc("YRP Item Price", approved)
		frappe.set_user(self.fixture_users["purchase_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be edited in state Approved"):
			save_item_price(self._values(price=20), approved, doc.modified)

	def test_web_save_requires_supplier_allows_past_dates_and_checks_staleness(self):
		from essdee_yrp.purchase.item_price_workspace import save_item_price

		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaisesRegex(frappe.ValidationError, "Supplier is required"):
			save_item_price(self._values(supplier=""))

		name = save_item_price(
			self._values(supplier=self.suppliers[1], from_date=add_days(nowdate(), -20))
		)["record"]["name"]
		doc = frappe.get_doc("YRP Item Price", name)
		with self.assertRaisesRegex(frappe.ValidationError, "Reload"):
			save_item_price(self._values(supplier=self.suppliers[1]), name, None)
		with self.assertRaises(frappe.TimestampMismatchError):
			save_item_price(
				self._values(supplier=self.suppliers[1]),
				name,
				"2000-01-01 00:00:00",
			)

		self._transition(name, "Submit", "purchase_user")
		self._transition(name, "Approve", "purchase_manager")
		doc.reload()
		self.assertEqual((doc.workflow_state, doc.docstatus), ("Approved", 1))

	def test_workspace_actions_match_workflow_and_show_predecessor_preview(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		predecessor = self._save(from_date=add_days(nowdate(), -30))["record"]["name"]
		self._transition(predecessor, "Submit", "purchase_user")
		self._transition(predecessor, "Approve", "purchase_manager")
		current = self._save(from_date=add_days(nowdate(), -5))["record"]["name"]
		self._transition(current, "Submit", "purchase_user")

		frappe.set_user(self.fixture_users["purchase_manager"])
		doc = frappe.get_doc("YRP Item Price", current)
		expected = [
			transition.action
			for transition in get_transitions(doc)
			if has_approval_access(frappe.session.user, doc, transition)
		]
		payload = get_item_price_workspace(current)

		self.assertEqual([row["action"] for row in payload["actions"]], expected)
		approve = next(row for row in payload["actions"] if row["action"] == "Approve")
		self.assertIn(predecessor, approve["preview"])
		self.assertIn(formatdate(add_days(doc.from_date, -1), "dd-mm-yyyy"), approve["preview"])
		self.assertTrue(payload["can_edit"])
		self.assertTrue(payload["can_delete"])
		self.assertIn(predecessor, [row["name"] for row in payload["history"]])

	def test_workspace_timeline_includes_comments_automatic_expiry_and_approver(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		self._transition(name, "Submit", "purchase_user")
		self._transition(name, "Approve", "purchase_manager")
		frappe.set_user("Administrator")
		doc = frappe.get_doc("YRP Item Price", name)
		doc.add_comment("Comment", "Buyer confirmed the negotiated rate")
		doc.add_comment("Info", "Cancelled automatically due to expiry")

		frappe.set_user(self.fixture_users["purchase_manager"])
		payload = get_item_price_workspace(name)
		contents = [entry["content"] for entry in payload["timeline"]]

		self.assertIn("Buyer confirmed the negotiated rate", contents)
		self.assertIn("Cancelled automatically due to expiry", contents)
		self.assertIn(f"Approved by {self.fixture_users['purchase_manager']}", contents)
		self.assertTrue(all(entry["name"] for entry in payload["timeline"]))

	def test_workspace_sends_desk_field_labels_for_sections_and_price_values(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_workspace(name)
		fields = {field["fieldname"]: field for field in payload["fields"]}

		self.assertEqual(fields["from_date"]["label"], "From Date")
		self.assertEqual(fields["from_date"]["fieldtype"], "Date")
		self.assertEqual(fields["uom"]["label"], "UOM")
		self.assertEqual(fields["uom"]["value"], self.uom)
		self.assertEqual(fields["tax"]["label"], "Tax Slab")
		self.assertEqual(fields["depends_on_attribute"]["label"], "Depends On Attribute")
		self.assertEqual(fields["supplier_name"]["label"], "Supplier Name")
		self.assertIn("approved_by", fields)
		self.assertEqual(payload["tier_fields"]["moq"]["label"], "MOQ")
		self.assertEqual(payload["tier_fields"]["lead_time"]["label"], "Lead Time")
		self.assertEqual(payload["tier_fields"]["attribute_value"]["label"], "Attribute Value")

	def test_workspace_timeline_starts_with_the_creation_entry(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		frappe.set_user(self.fixture_users["purchase_user"])
		timeline = get_item_price_workspace(name)["timeline"]

		created = next(entry for entry in timeline if entry["kind"] == "created")
		self.assertEqual(created["by"], self.fixture_users["purchase_user"])
		self.assertEqual(created["content"], f"{self.fixture_users['purchase_user']} created this")

	def test_workspace_timeline_lists_every_saved_version(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		self._transition(name, "Submit", "purchase_user")
		self._transition(name, "Approve", "purchase_manager")
		versions = frappe.get_all("Version", filters={"ref_doctype": "YRP Item Price", "docname": name}, pluck="name")

		frappe.set_user(self.fixture_users["purchase_user"])
		timeline = get_item_price_workspace(name)["timeline"]

		edited = [entry["name"] for entry in timeline if entry["kind"] == "edited"]
		self.assertGreaterEqual(len(versions), 2)
		self.assertCountEqual(edited, versions)

	def test_editor_sends_read_only_supplier_name_and_hides_unapproved_approver(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		name = self._save()["record"]["name"]
		frappe.db.set_value("YRP Item Price", name, "approved_by", "Administrator", update_modified=False)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_editor(name)

		self.assertEqual(payload["fields"]["supplier_name"]["label"], "Supplier Name")
		self.assertTrue(payload["fields"]["supplier_name"]["read_only"])
		self.assertTrue(payload["fields"]["approved_by"]["read_only"])
		self.assertEqual(payload["fields"]["from_date"]["label"], "From Date")
		self.assertEqual(payload["values"]["supplier_name"], frappe.db.get_value("Supplier", self.suppliers[0], "supplier_name"))
		self.assertIsNone(payload["values"]["approved_by"])

	def test_draft_edit_requires_workflow_allow_edit_role(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		frappe.set_user(self.fixture_users["manager_only"])
		payload = get_item_price_workspace(name)

		self.assertTrue(frappe.has_permission("YRP Item Price", "write", doc=frappe.get_doc("YRP Item Price", name)))
		self.assertFalse(payload["can_edit"])

	def test_action_requires_fresh_token_and_allowed_transition(self):
		from essdee_yrp.purchase.item_price_workspace import execute_item_price_action

		name = self._save()["record"]["name"]
		doc = frappe.get_doc("YRP Item Price", name)
		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaisesRegex(frappe.ValidationError, "Reload"):
			execute_item_price_action(name, "Submit", None)
		with self.assertRaises(frappe.TimestampMismatchError):
			execute_item_price_action(name, "Submit", "2000-01-01 00:00:00")
		with self.assertRaises(frappe.PermissionError):
			execute_item_price_action(name, "Approve", doc.modified)

		result = execute_item_price_action(name, "Submit", doc.modified)
		self.assertEqual(result["record"]["workflow_state"], "Approval Pending")

	def test_web_actions_cover_self_approval_rejection_expiry_and_final_states(self):
		from essdee_yrp.purchase.item_price_workspace import (
			delete_item_price,
			execute_item_price_action,
			get_item_price_editor,
			get_item_price_workspace,
		)

		approved = self._save(user_key="purchase_manager")["record"]["name"]
		frappe.set_user(self.fixture_users["purchase_manager"])
		approved_payload = execute_item_price_action(
			approved,
			"Submit",
			frappe.db.get_value("YRP Item Price", approved, "modified"),
		)
		approved_payload = execute_item_price_action(
			approved,
			"Approve",
			approved_payload["record"]["modified"],
		)
		self.assertEqual(approved_payload["record"]["workflow_state"], "Approved")
		self.assertEqual([row["action"] for row in approved_payload["actions"]], ["Expired"])
		approved_payload = execute_item_price_action(
			approved,
			"Expired",
			approved_payload["record"]["modified"],
		)
		self.assertEqual(
			(
				approved_payload["record"]["workflow_state"],
				approved_payload["record"]["docstatus"],
			),
			("Expired", 2),
		)
		self.assertEqual(approved_payload["actions"], [])
		self.assertFalse(approved_payload["can_edit"])
		self.assertFalse(approved_payload["can_delete"])

		rejected = self._save(supplier=self.suppliers[1])["record"]["name"]
		frappe.set_user(self.fixture_users["purchase_user"])
		rejected_payload = execute_item_price_action(
			rejected,
			"Submit",
			frappe.db.get_value("YRP Item Price", rejected, "modified"),
		)
		frappe.set_user(self.fixture_users["purchase_manager"])
		rejected_payload = execute_item_price_action(
			rejected,
			"Reject",
			rejected_payload["record"]["modified"],
		)
		self.assertEqual(rejected_payload["record"]["workflow_state"], "Rejected")
		self.assertEqual(rejected_payload["actions"], [])
		self.assertTrue(rejected_payload["can_edit"])
		self.assertTrue(rejected_payload["can_delete"])
		self.assertEqual(get_item_price_editor(rejected)["workflow"]["save_actions"], [])

		frappe.set_user(self.fixture_users["purchase_manager"])
		expired_payload = get_item_price_workspace(approved)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be edited in state Expired"):
			get_item_price_editor(approved)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be deleted in state Expired"):
			delete_item_price(approved, expired_payload["record"]["modified"])

	def _price_in_state(self, state, supplier_index=0):
		name = self._save(supplier=self.suppliers[supplier_index])["record"]["name"]
		path = {
			"Draft": [],
			"Approval Pending": ["Submit"],
			"Rejected": ["Submit", "Reject"],
			"Approved": ["Submit", "Approve"],
			"Expired": ["Submit", "Approve", "Expired"],
		}[state]
		for action in path:
			self._transition(name, action, "purchase_manager")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("YRP Item Price", name, "workflow_state"), state)
		return name

	def test_workspace_buttons_per_state_and_role_match_the_workflow(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		expected = {
			"Draft": {
				"purchase_user": (["Submit"], True, False),
				"purchase_manager": (["Submit"], True, True),
				"manager_only": ([], False, False),
				"system_manager": ([], False, False),
			},
			"Approval Pending": {
				"purchase_user": ([], False, False),
				"purchase_manager": (["Approve", "Reject"], True, True),
				"manager_only": (["Approve", "Reject"], True, True),
				"system_manager": ([], False, False),
			},
			"Approved": {
				"purchase_user": ([], False, False),
				"purchase_manager": (["Expired"], False, False),
				"manager_only": (["Expired"], False, False),
				"system_manager": ([], False, False),
			},
			"Rejected": {
				"purchase_user": ([], True, False),
				"purchase_manager": ([], True, True),
				"manager_only": ([], False, False),
				"system_manager": ([], False, False),
			},
			"Expired": {
				"purchase_user": ([], False, False),
				"purchase_manager": ([], False, False),
				"manager_only": ([], False, False),
				"system_manager": ([], False, False),
			},
		}
		approving_suppliers = {"Approved": 0, "Expired": 1}
		for state, roles in expected.items():
			name = self._price_in_state(state, supplier_index=approving_suppliers.get(state, 0))
			for user_key, (actions, can_edit, can_delete) in roles.items():
				with self.subTest(state=state, role=user_key):
					frappe.set_user(self.fixture_users[user_key])
					payload = get_item_price_workspace(name)
					self.assertEqual([row["action"] for row in payload["actions"]], actions)
					self.assertEqual(payload["can_edit"], can_edit)
					self.assertEqual(payload["can_delete"], can_delete)

	def test_action_payload_carries_next_state_and_its_doc_status(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._price_in_state("Approved")
		frappe.set_user(self.fixture_users["purchase_manager"])
		(expired,) = get_item_price_workspace(name)["actions"]
		self.assertEqual(
			(expired["action"], expired["state"], expired["next_state"], expired["next_state_doc_status"]),
			("Expired", "Approved", "Expired", 2),
		)

	def test_each_web_transition_moves_the_state_and_disallowed_ones_are_rejected(self):
		from essdee_yrp.purchase.item_price_workspace import execute_item_price_action

		def run(name, action, user_key):
			frappe.set_user(self.fixture_users[user_key])
			modified = frappe.db.get_value("YRP Item Price", name, "modified")
			return execute_item_price_action(name, action, modified)["record"]

		name = self._save()["record"]["name"]
		with self.assertRaises(frappe.PermissionError):
			run(name, "Approve", "purchase_manager")
		self.assertEqual(run(name, "Submit", "purchase_user")["workflow_state"], "Approval Pending")
		with self.assertRaises(frappe.PermissionError):
			run(name, "Approve", "purchase_user")
		with self.assertRaises(frappe.PermissionError):
			run(name, "Submit", "purchase_manager")
		approved = run(name, "Approve", "purchase_manager")
		self.assertEqual((approved["workflow_state"], approved["docstatus"]), ("Approved", 1))
		with self.assertRaises(frappe.PermissionError):
			run(name, "Expired", "purchase_user")
		expired = run(name, "Expired", "purchase_manager")
		self.assertEqual((expired["workflow_state"], expired["docstatus"]), ("Expired", 2))
		with self.assertRaises(frappe.PermissionError):
			run(name, "Expired", "purchase_manager")
		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "YRP Item Price",
				"reference_name": name,
				"comment_type": "Workflow",
				"creation": [">=", frappe.db.get_value("YRP Item Price", name, "creation")],
			},
			pluck="content",
		)
		self.assertEqual(sorted(comments), sorted(["Approval Pending", "Approved", "Expired"]))

		rejected = self._save(supplier=self.suppliers[1])["record"]["name"]
		run(rejected, "Submit", "purchase_user")
		self.assertEqual(run(rejected, "Reject", "purchase_manager")["workflow_state"], "Rejected")
		for action in ("Submit", "Approve", "Reject"):
			with self.subTest(action=action), self.assertRaises(frappe.PermissionError):
				run(rejected, action, "purchase_manager")

	def test_rejected_price_is_editable_by_a_purchase_user_and_keeps_its_state(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor, save_item_price

		name = self._price_in_state("Rejected")
		frappe.set_user(self.fixture_users["purchase_user"])
		editor = get_item_price_editor(name)
		self.assertEqual(editor["workflow"], {"state": "Rejected", "save_actions": []})
		payload = save_item_price(
			self._values(item_price_values=[{"moq": 0, "price": 12, "lead_time": 2}]),
			name,
			editor["modified"],
		)
		self.assertEqual(payload["record"]["workflow_state"], "Rejected")
		self.assertEqual(payload["actions"], [])
		self.assertEqual(payload["tiers"][0]["price"], 12)

	def test_pending_price_is_editable_by_a_purchase_manager_only(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor, save_item_price

		name = self._price_in_state("Approval Pending")
		modified = frappe.db.get_value("YRP Item Price", name, "modified")
		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be edited in state Approval Pending"):
			get_item_price_editor(name)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be edited in state Approval Pending"):
			save_item_price(self._values(), name, modified)

		frappe.set_user(self.fixture_users["purchase_manager"])
		editor = get_item_price_editor(name)
		self.assertEqual(editor["workflow"]["state"], "Approval Pending")
		self.assertEqual(
			[row["action"] for row in editor["workflow"]["save_actions"]], ["Approve", "Reject"]
		)
		payload = save_item_price(
			self._values(item_price_values=[{"moq": 0, "price": 14, "lead_time": 2}]),
			name,
			editor["modified"],
		)
		self.assertEqual(payload["record"]["workflow_state"], "Approval Pending")
		self.assertEqual(payload["record"]["docstatus"], 0)

	def test_editor_save_actions_follow_the_initial_state_transitions(self):
		from frappe.model.workflow import get_workflow

		from essdee_yrp.purchase.item_price_workspace import get_item_price_editor

		initial_state = get_workflow("YRP Item Price").states[0].state
		frappe.set_user(self.fixture_users["purchase_user"])
		editor = get_item_price_editor(item=self.item)
		self.assertEqual(editor["workflow"]["state"], initial_state)
		self.assertEqual([row["action"] for row in editor["workflow"]["save_actions"]], ["Submit"])
		self.assertEqual(editor["workflow"]["save_actions"][0]["next_state"], "Approval Pending")

		draft = self._save()["record"]["name"]
		self.assertEqual(
			[row["action"] for row in get_item_price_editor(draft)["workflow"]["save_actions"]],
			["Submit"],
		)

		frappe.set_user(self.fixture_users["system_manager"])
		self.assertEqual(get_item_price_editor(item=self.item)["workflow"]["save_actions"], [])

	def test_new_price_save_actions_respect_transition_conditions(self):
		import copy

		from frappe.model.workflow import get_workflow

		from essdee_yrp.purchase import item_price_workspace

		workflow = copy.deepcopy(get_workflow("YRP Item Price"))
		initial_state = workflow.states[0].state
		submit = next(row for row in workflow.transitions if row.action == "Submit")
		frappe.set_user(self.fixture_users["purchase_user"])

		def save_actions(condition):
			submit.condition = condition
			with patch.object(item_price_workspace, "get_workflow", return_value=workflow):
				editor = item_price_workspace.get_item_price_editor(item=self.item)
			return [row["action"] for row in editor["workflow"]["save_actions"]]

		self.assertEqual(
			save_actions(f"doc.workflow_state == {initial_state!r} and doc.item_name == {self.item!r}"),
			["Submit"],
		)
		self.assertEqual(save_actions("doc.item_name == 'not this item'"), [])

	def test_delete_follows_the_state_edit_role_and_delete_permission(self):
		from essdee_yrp.purchase.item_price_workspace import delete_item_price

		for state in ("Approval Pending", "Rejected"):
			with self.subTest(state=state):
				name = self._price_in_state(state)
				modified = frappe.db.get_value("YRP Item Price", name, "modified")
				frappe.set_user(self.fixture_users["purchase_user"])
				with self.assertRaises(frappe.PermissionError):
					delete_item_price(name, modified)
				frappe.set_user(self.fixture_users["purchase_manager"])
				self.assertEqual(delete_item_price(name, modified), {"deleted": True, "name": name})
				self.assertFalse(frappe.db.exists("YRP Item Price", name))

		approved = self._price_in_state("Approved")
		frappe.set_user(self.fixture_users["purchase_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be deleted in state Approved"):
			delete_item_price(approved, frappe.db.get_value("YRP Item Price", approved, "modified"))

	def test_unapproved_price_hides_a_migrated_approver_from_the_timeline(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_workspace

		name = self._save()["record"]["name"]
		frappe.db.set_value("YRP Item Price", name, "approved_by", "Administrator", update_modified=False)
		frappe.set_user(self.fixture_users["purchase_user"])
		payload = get_item_price_workspace(name)
		self.assertNotIn("approval", [entry["kind"] for entry in payload["timeline"]])

	def test_standalone_system_manager_has_no_workflow_action(self):
		from essdee_yrp.purchase.item_price_workspace import (
			execute_item_price_action,
			get_item_price_workspace,
		)

		name = self._save()["record"]["name"]
		modified = frappe.db.get_value("YRP Item Price", name, "modified")
		frappe.set_user(self.fixture_users["system_manager"])
		payload = get_item_price_workspace(name)
		self.assertEqual(payload["actions"], [])
		with self.assertRaises(frappe.PermissionError):
			execute_item_price_action(name, "Submit", modified)

	def test_action_retries_the_whole_request_at_most_twice(self):
		from essdee_yrp.purchase import item_price_workspace

		result = {"record": {"name": "ITP-00001"}}
		with (
			patch.object(
				item_price_workspace,
				"_execute_item_price_action_once",
				side_effect=[frappe.QueryDeadlockError("deadlock"), result],
			) as execute_once,
			patch.object(item_price_workspace.frappe.db, "rollback") as rollback,
			patch.object(item_price_workspace.time, "sleep"),
		):
			self.assertEqual(
				item_price_workspace.execute_item_price_action(
					"ITP-00001", "Approve", "2026-10-13 10:00:00"
				),
				result,
			)
		execute_once.assert_called_with("ITP-00001", "Approve", "2026-10-13 10:00:00")
		self.assertEqual(execute_once.call_count, 2)
		rollback.assert_called_once_with()

		with (
			patch.object(
				item_price_workspace,
				"_execute_item_price_action_once",
				side_effect=frappe.QueryDeadlockError("still deadlocked"),
			) as execute_once,
			patch.object(item_price_workspace.frappe.db, "rollback"),
			patch.object(item_price_workspace.time, "sleep"),
			self.assertRaises(frappe.QueryDeadlockError),
		):
			item_price_workspace.execute_item_price_action(
				"ITP-00001", "Approve", "2026-10-13 10:00:00"
			)
		self.assertEqual(execute_once.call_count, 2)

	def test_delete_is_draft_only_and_requires_fresh_token(self):
		from essdee_yrp.purchase.item_price_workspace import delete_item_price

		name = self._save(user_key="purchase_manager")["record"]["name"]
		doc = frappe.get_doc("YRP Item Price", name)
		frappe.set_user(self.fixture_users["purchase_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "Reload"):
			delete_item_price(name, None)
		with self.assertRaises(frappe.TimestampMismatchError):
			delete_item_price(name, "2000-01-01 00:00:00")
		self.assertEqual(delete_item_price(name, doc.modified), {"deleted": True, "name": name})
		self.assertFalse(frappe.db.exists("YRP Item Price", name))

	def test_price_summaries_report_slab_range_for_readable_prices(self):
		from essdee_yrp.purchase.item_price_workspace import get_item_price_summaries

		single = self._save()["record"]["name"]
		slabs = [{"moq": 0, "price": 12.5, "lead_time": 2}, {"moq": 100, "price": 9, "lead_time": 3}]
		ranged = self._save(supplier=self.suppliers[1], item_price_values=slabs)["record"]["name"]

		summaries = get_item_price_summaries([single, ranged, single, "ITP-MISSING"])

		self.assertEqual(summaries[single], {"min_price": 10, "max_price": 10, "slab_count": 1})
		self.assertEqual(summaries[ranged], {"min_price": 9, "max_price": 12.5, "slab_count": 2})
		self.assertNotIn("ITP-MISSING", summaries)
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_item_price_summaries([single])

	def test_price_endpoints_follow_doctype_permissions(self):
		from essdee_yrp.purchase.item_price_workspace import (
			get_item_price_editor,
			save_item_price,
		)

		frappe.set_user(self.fixture_users["roleless"])
		with self.assertRaises(frappe.PermissionError):
			get_item_price_editor(item=self.item)
		with self.assertRaises(frappe.PermissionError):
			save_item_price(self._values())

	def test_price_lifecycle_paths_never_take_the_pricing_mutex(self):
		from essdee_yrp.purchase.item_price_workspace import (
			delete_item_price,
			execute_item_price_action,
			save_item_price,
		)

		frappe.set_user(self.fixture_users["purchase_user"])
		with patch("yrp.yrp_retail.pricing.lock_pricing_policy") as lock_policy:
			workspace = save_item_price(self._values())
			name = workspace["record"]["name"]
			workspace = save_item_price(
				self._values(item_price_values=[{"moq": 0, "price": 11, "lead_time": 2}]),
				name,
				workspace["record"]["modified"],
			)
			workspace = execute_item_price_action(
				name, "Submit", workspace["record"]["modified"]
			)

			frappe.set_user(self.fixture_users["purchase_manager"])
			execute_item_price_action(name, "Approve", workspace["record"]["modified"])
			delete_workspace = save_item_price(
				self._values(supplier=self.suppliers[1], from_date=add_days(nowdate(), 1))
			)
			delete_item_price(
				delete_workspace["record"]["name"],
				delete_workspace["record"]["modified"],
			)
		lock_policy.assert_not_called()

	def test_mutations_are_post_only_and_no_revision_api_exists(self):
		from essdee_yrp.purchase import item_price_workspace

		for method in (
			item_price_workspace.save_item_price,
			item_price_workspace.execute_item_price_action,
			item_price_workspace.delete_item_price,
		):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["POST"])
		self.assertFalse(hasattr(item_price_workspace, "create_item_price_revision"))


class TestPurchaseItemPriceDeleteConcurrency(TestCase):
	def setUp(self):
		self.run_token = frappe.generate_hash(length=12)
		self.addCleanup(
			_cleanup_workspace_fixture_run,
			frappe.local.site,
			frappe.local.sites_path,
			self.run_token,
		)

	def _run_connection(self, callback):
		site = frappe.local.site
		sites_path = frappe.local.sites_path
		result = {}

		def run():
			frappe.init(site, sites_path=sites_path)
			frappe.connect()
			frappe.flags.in_test = True
			frappe.set_user("Administrator")
			try:
				result["value"] = callback()
			except Exception as error:
				frappe.db.rollback()
				result["error"] = f"{error}\n{traceback.format_exc()}"
			finally:
				frappe.destroy()

		thread = threading.Thread(target=run, daemon=True)
		thread.start()
		thread.join(timeout=20)
		self.assertFalse(thread.is_alive(), "Database helper connection timed out")
		self.assertNotIn("error", result, result.get("error"))
		return result.get("value")

	def _make_fixture(self):
		def create():
			suffix = f"{self.run_token}-{frappe.generate_hash(length=6)}"
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": f"round2-price-race-{suffix}@example.test",
					"first_name": "Round 2 Price Race",
					"enabled": 1,
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Purchase User"}],
				}
			).insert(ignore_permissions=True)
			uom = frappe.get_doc(
				{"doctype": "UOM", "uom_name": f"Web Delete Race Unit {suffix}", "enabled": 1}
			).insert(ignore_permissions=True)
			item = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": f"_Test Web Delete Race Item {suffix}",
					"item_name": f"_Test Web Delete Race Item {suffix}",
					"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
					"stock_uom": uom.name,
					"is_stock_item": 1,
					"is_purchase_item": 1,
					"is_sales_item": 0,
				}
			).insert(ignore_permissions=True)
			supplier = frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": f"_Test Web Delete Race Supplier {suffix}",
					"supplier_group": frappe.db.get_value(
						"Supplier Group", {"is_group": 0}, "name"
					),
				}
			).insert(ignore_permissions=True)
			price = frappe.get_doc(
				{
					"doctype": "YRP Item Price",
					"item_name": item.name,
					"supplier": supplier.name,
					"uom": uom.name,
					"from_date": nowdate(),
					"tax": frappe.db.get_value("YRP Tax Slab", {"enabled": 1}, "name"),
					"item_price_values": [{"moq": 0, "price": 10, "lead_time": 1}],
				}
			).insert(ignore_permissions=True)
			commit_connection()
			return {
				"user": user.name,
				"uom": uom.name,
				"item": item.name,
				"supplier": supplier.name,
				"price": price.name,
				"modified": str(price.modified),
			}

		return self._run_connection(create)

	def _cleanup_fixture(self, fixture):
		def cleanup():
			if frappe.db.exists("YRP Item Price", fixture["price"]):
				frappe.db.set_value(
					"YRP Item Price",
					fixture["price"],
					{"docstatus": 0, "workflow_state": "Draft"},
					update_modified=False,
				)
				frappe.delete_doc(
					"YRP Item Price",
					fixture["price"],
					force=True,
					ignore_permissions=True,
					delete_permanently=True,
				)
			for doctype, name in (
				("Item", fixture["item"]),
				("Supplier", fixture["supplier"]),
				("UOM", fixture["uom"]),
				("User", fixture["user"]),
			):
				frappe.delete_doc(
					doctype,
					name,
					force=True,
					ignore_permissions=True,
					delete_permanently=True,
				)
			commit_connection()

		self._run_connection(cleanup)

	def test_deadlock_retry_rolls_back_partial_writes_and_reloads(self):
		from essdee_yrp.purchase import item_price_workspace

		fixture = self._make_fixture()

		def exercise_retry():
			frappe.set_user(fixture["user"])
			original_apply_workflow = item_price_workspace.apply_workflow
			attempts = 0

			def deadlock_after_partial_write(doc, action):
				nonlocal attempts
				attempts += 1
				if attempts == 1:
					frappe.db.set_value(
						"YRP Item Price",
						doc.name,
						"to_date",
						add_days(nowdate(), 7),
					)
					raise frappe.QueryDeadlockError("forced retry after partial write")
				return original_apply_workflow(doc, action)

			with (
				patch.object(
					item_price_workspace,
					"apply_workflow",
					side_effect=deadlock_after_partial_write,
				),
				patch.object(item_price_workspace.time, "sleep"),
			):
				payload = item_price_workspace.execute_item_price_action(
					fixture["price"], "Submit", fixture["modified"]
				)
			stored = frappe.db.get_value(
				"YRP Item Price",
				fixture["price"],
				["workflow_state", "to_date"],
				as_dict=True,
			)
			commit_connection()
			return payload["record"]["workflow_state"], stored, attempts

		try:
			state, stored, attempts = self._run_connection(exercise_retry)
			self.assertEqual(attempts, 2)
			self.assertEqual(state, "Approval Pending")
			self.assertEqual(stored.workflow_state, "Approval Pending")
			self.assertIsNone(stored.to_date)
		finally:
			self._cleanup_fixture(fixture)

	def test_delete_validates_the_post_lock_price_snapshot(self):
		from essdee_yrp.purchase.item_price_workspace import delete_item_price

		fixture = self._make_fixture()
		site = frappe.local.site
		sites_path = frappe.local.sites_path
		price_locked = threading.Event()
		delete_attempting_lock = threading.Event()
		progress = threading.local()
		results = {}
		database_class = type(frappe.local.db)
		original_sql = database_class.sql

		def observe_sql(database, query, *args, **kwargs):
			if (
				getattr(progress, "operation", None) == "delete"
				and isinstance(query, str)
				and "tabYRP Item Price" in query
				and "for update" in query.lower()
			):
				delete_attempting_lock.set()
			return original_sql(database, query, *args, **kwargs)

		def connection(operation, callback):
			frappe.init(site, sites_path=sites_path)
			frappe.connect()
			frappe.flags.in_test = True
			frappe.set_user("Administrator")
			progress.operation = operation
			try:
				callback()
			finally:
				frappe.destroy()

		def approve_while_locked():
			try:
				doc = frappe.get_doc("YRP Item Price", fixture["price"], for_update=True)
				price_locked.set()
				if not delete_attempting_lock.wait(10):
					raise TimeoutError("Delete request never attempted the price row lock")
				doc.db_set({"workflow_state": "Approved", "docstatus": 1})
				commit_connection()
				results["approval"] = "approved"
			except Exception as error:
				frappe.db.rollback()
				results["approval"] = f"{error}\n{traceback.format_exc()}"

		def delete_after_stale_read():
			if not price_locked.wait(10):
				raise TimeoutError("Approval request never locked the price")
			try:
				delete_item_price(fixture["price"], fixture["modified"])
				commit_connection()
				results["delete"] = "deleted"
			except frappe.TimestampMismatchError as error:
				frappe.db.rollback()
				results["delete"] = type(error).__name__
			except Exception as error:
				frappe.db.rollback()
				results["delete"] = f"unexpected {type(error).__name__}: {error}"

		threads = [
			threading.Thread(
				target=connection, args=("approve", approve_while_locked), daemon=True
			),
			threading.Thread(
				target=connection, args=("delete", delete_after_stale_read), daemon=True
			),
		]
		try:
			with patch.object(database_class, "sql", new=observe_sql):
				for thread in threads:
					thread.start()
				for thread in threads:
					thread.join(timeout=20)
			self.assertTrue(all(not thread.is_alive() for thread in threads), results)
			self.assertEqual(results.get("approval"), "approved", results)
			self.assertEqual(results.get("delete"), "TimestampMismatchError", results)
			stored = self._run_connection(
				lambda: frappe.db.get_value(
					"YRP Item Price",
					fixture["price"],
					["workflow_state", "docstatus"],
					as_dict=True,
				)
			)
			self.assertEqual((stored.workflow_state, stored.docstatus), ("Approved", 1))
		finally:
			self._cleanup_fixture(fixture)
