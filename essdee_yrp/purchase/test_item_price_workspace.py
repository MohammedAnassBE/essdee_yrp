import threading
import traceback
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow, get_transitions, has_approval_access
from frappe.utils import add_days, format_date, nowdate
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
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			save_item_price(self._values(price=20), approved, doc.modified)

		rejected = self._save(supplier=self.suppliers[1])["record"]["name"]
		self._transition(rejected, "Submit", "purchase_user")
		self._transition(rejected, "Reject", "purchase_manager")
		doc = frappe.get_doc("YRP Item Price", rejected)
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			save_item_price(self._values(supplier=self.suppliers[1]), rejected, doc.modified)

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
		self.assertIn(format_date(add_days(doc.from_date, -1)), approve["preview"])
		self.assertFalse(payload["can_edit"])
		self.assertFalse(payload["can_delete"])
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
		self.assertFalse(rejected_payload["can_edit"])
		self.assertFalse(rejected_payload["can_delete"])
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			get_item_price_editor(rejected)
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			delete_item_price(rejected, rejected_payload["record"]["modified"])

		frappe.set_user(self.fixture_users["purchase_manager"])
		expired_payload = get_item_price_workspace(approved)
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			get_item_price_editor(approved)
		with self.assertRaisesRegex(frappe.ValidationError, "Draft"):
			delete_item_price(approved, expired_payload["record"]["modified"])

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
