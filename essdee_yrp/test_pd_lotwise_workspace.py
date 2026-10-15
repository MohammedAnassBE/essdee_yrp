from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.product_development import lotwise_workspace

TEMPLATE_DOCTYPE = "SD YRP Lotwise Item Profit Additional Cost Template"


class TestPdLotwiseWorkspace(IntegrationTestCase):
	def values(self, **extra):
		lots = frappe.get_all("SD YRP Lot", pluck="name", limit=1)
		return {
			"lot": lots[0] if lots else None,
			"lot_costing_type": "Costing",
			"qty_rate_chart": [{"size": "S", "qty": 2, "rate": 10}],
			**extra,
		}

	def test_command_recalculates_without_saving(self):
		before = frappe.db.count("SD YRP Lotwise Item Profit")
		result = lotwise_workspace.run_lotwise_command(self.values(), "recalculate")
		self.assertEqual(result["record"]["total_selling_value"], 20)
		self.assertEqual(frappe.db.count("SD YRP Lotwise Item Profit"), before)

	def test_command_requires_create_permission_for_new_document(self):
		with (
			patch.object(frappe, "has_permission", side_effect=frappe.PermissionError),
			self.assertRaises(frappe.PermissionError),
		):
			lotwise_workspace.run_lotwise_command(self.values(), "recalculate")

	def test_command_requires_write_permission_for_existing_document(self):
		doc = MagicMock()
		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			lotwise_workspace.run_lotwise_command(
				self.values(), "recalculate", name="LOTWISE-1"
			)
		doc.check_permission.assert_called_once_with("write")

	def test_record_payload_labels_sizes_without_mutating_document(self):
		doc = frappe.get_doc(
			{
				"doctype": lotwise_workspace.LOTWISE,
				"qty_rate_chart": [{"size": "IAV-S", "qty": 1, "rate": 1}],
				"piece_cloth_weight": [
					{"size": "IAV-S", "cloth_group": "Cotton", "weight": 100}
				],
			}
		)
		with patch.object(lotwise_workspace, "size_labels", return_value={"IAV-S": "60 cm"}):
			record, labels = lotwise_workspace.record_payload(doc)
		self.assertEqual(labels, {"IAV-S": "60 cm"})
		self.assertEqual(record["qty_rate_chart"][0]["size"], "60 cm")
		self.assertEqual(record["piece_cloth_weight"][0]["size"], "60 cm")
		self.assertEqual(doc.qty_rate_chart[0].size, "IAV-S")
		self.assertEqual(doc.piece_cloth_weight[0].size, "IAV-S")

	def test_unknown_command_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			lotwise_workspace.run_lotwise_command(self.values(), "drop_tables")

	def test_calculate_rate_requires_numeric_percent(self):
		with self.assertRaises(frappe.ValidationError):
			lotwise_workspace.run_lotwise_command(
				self.values(), "calculate_rate", {"percent": "abc"}
			)

	def test_save_creates_and_recalculates(self):
		values = self.values()
		if not values["lot"]:
			self.skipTest("needs an SD YRP Lot")
		payload = lotwise_workspace.save_lotwise_item_profit(values)
		self.assertTrue(payload["record"]["name"])
		self.assertEqual(payload["record"]["total_qty"], 2)

	def test_save_rejects_mismatched_template_type(self):
		templates = {
			template_type: frappe.db.get_value(TEMPLATE_DOCTYPE, {"type": template_type}, "name")
			for template_type in ("Discounts", "Other")
		}
		if not self.values()["lot"] or not all(templates.values()):
			self.skipTest("needs a Lot and an additional cost template of each type")
		with self.assertRaisesRegex(frappe.ValidationError, "not a Discounts template"):
			lotwise_workspace.save_lotwise_item_profit(
				self.values(trade_discounts_template=templates["Other"])
			)

	def test_save_rejects_stale_modified(self):
		existing = frappe.get_all("SD YRP Lotwise Item Profit", pluck="name", limit=1)
		if not existing:
			self.skipTest("no Lotwise Item Profit on the test site")
		with self.assertRaises(frappe.TimestampMismatchError):
			lotwise_workspace.save_lotwise_item_profit(
				{"gst": 5}, name=existing[0], expected_modified="2000-01-01 00:00:00"
			)

	def test_existing_mutations_require_modified_timestamp(self):
		existing = frappe.get_all("SD YRP Lotwise Item Profit", pluck="name", limit=1)
		if not existing:
			self.skipTest("no Lotwise Item Profit on the test site")
		with self.assertRaisesRegex(frappe.ValidationError, "Reload the record"):
			lotwise_workspace.save_lotwise_item_profit({"gst": 5}, name=existing[0])
		with self.assertRaisesRegex(frappe.ValidationError, "Reload the record"):
			lotwise_workspace.delete_lotwise_item_profit(existing[0], expected_modified="")

	def test_existing_save_locks_before_stale_check(self):
		existing = frappe.get_all("SD YRP Lotwise Item Profit", pluck="name", limit=1)
		if not existing:
			self.skipTest("no Lotwise Item Profit on the test site")
		with (
			patch.object(frappe, "get_doc", wraps=frappe.get_doc) as get_document,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			lotwise_workspace.save_lotwise_item_profit(
				{"gst": 5}, name=existing[0], expected_modified="2000-01-01 00:00:00"
			)
		get_document.assert_called_once_with(
			lotwise_workspace.LOTWISE, existing[0], for_update=True
		)

	def test_delete_locks_before_stale_check(self):
		existing = frappe.get_all("SD YRP Lotwise Item Profit", pluck="name", limit=1)
		if not existing:
			self.skipTest("no Lotwise Item Profit on the test site")
		with (
			patch.object(frappe, "get_doc", wraps=frappe.get_doc) as get_document,
			patch.object(frappe, "delete_doc") as delete_document,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			lotwise_workspace.delete_lotwise_item_profit(
				existing[0], expected_modified="2000-01-01 00:00:00"
			)
		get_document.assert_called_once_with(
			lotwise_workspace.LOTWISE, existing[0], for_update=True
		)
		delete_document.assert_not_called()

	def test_save_rejects_foreign_child_row_name(self):
		rows = frappe.get_all("SD YRP Lotwise Item Profit Qty Rate", pluck="name", limit=1)
		if not rows:
			self.skipTest("no Lotwise Item Profit Qty Rate on the test site")
		with self.assertRaisesRegex(frappe.ValidationError, "qty_rate_chart"):
			lotwise_workspace.save_lotwise_item_profit(
				self.values(qty_rate_chart=[{"name": rows[0], "size": "S", "qty": 2, "rate": 10}])
			)

	def test_new_workspace_prefills_product_sizes(self):
		products = frappe.get_all(
			"SD YRP Product", filters={"size_range": ["is", "set"]}, pluck="name", limit=1
		)
		if not products:
			self.skipTest("needs a product with sizes")
		payload = lotwise_workspace.get_lotwise_workspace(product=products[0])
		self.assertEqual(payload["record"]["product"], products[0])
		self.assertIn("size_labels", payload)
		self.assertTrue(
			all(not row["size"].startswith("IAV-") for row in payload["record"]["qty_rate_chart"])
		)
		self.assertEqual(
			payload["costing_types"],
			["Costing", "Planned Qty", "Cutting Qty", "Final Qty", "Audited Final"],
		)

	def test_new_workspace_reports_missing_product(self):
		missing = f"PD-MISSING-PRODUCT-{frappe.generate_hash(length=10)}"
		with self.assertRaises(frappe.DoesNotExistError):
			lotwise_workspace.get_lotwise_workspace(product=missing)
