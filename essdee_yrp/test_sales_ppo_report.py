from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.sales import ppo_report, web_workspace


class TestSalesPpoReport(TestCase):
	def test_report_requires_report_permission(self):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				ppo_report.get_ppo_report()

	def test_filters_current_orders_by_dates_status_and_product_category(self):
		calls = []

		def fake_get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			if doctype == "Item":
				return ["ITEM-1", "ITEM-2"]
			if doctype == "YRP Production Order":
				return []
			raise AssertionError(f"Unexpected doctype {doctype}")

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_all", side_effect=fake_get_all),
		):
			result = ppo_report.get_ppo_report(
				{
					"from_date": "2026-10-01",
					"to_date": "2026-10-31",
					"status": "Open",
					"product_category": "Mens",
				}
			)

		order_call = next(kwargs for doctype, kwargs in calls if doctype == "YRP Production Order")
		self.assertEqual(
			order_call["filters"],
			{
				"docstatus": ["!=", 2],
				"status": "Open",
				"delivery_date": ["between", ["2026-10-01", "2026-10-31"]],
				"item": ["in", ["ITEM-1", "ITEM-2"]],
			},
		)
		self.assertEqual(result, ppo_report.empty_report())

	def test_empty_category_and_no_records_return_complete_empty_shape(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_all", return_value=[]),
		):
			self.assertEqual(
				ppo_report.get_ppo_report({"product_category": "Missing"}),
				{
					"orders": [],
					"size_groups": [],
					"max_columns": 0,
					"summary": {"total_orders": 0, "total_quantity": 0, "size_groups": 0},
				},
			)

	def test_mixed_size_groups_keep_positional_alignment_and_literal_totals(self):
		orders = [
			{
				"name": "PPO-2",
				"item": "One Size Sock",
				"fabric": "Cotton Rib",
				"dia": "18 Dia",
				"gsm": 180,
				"delivery_date": "2026-10-15",
				"posting_date": "2026-10-02",
				"docstatus": 1,
				"status": "Open",
			},
			{
				"name": "PPO-1",
				"item": "Classic Shirt",
				"delivery_date": "2026-10-12",
				"posting_date": "2026-10-01",
				"docstatus": 1,
				"status": "Open",
			},
		]
		details = [
			{"parent": "PPO-1", "attributes_json": '{"Size":"M"}', "quantity": 20},
			{"parent": "PPO-1", "attributes_json": '{"Size":"S"}', "quantity": 10},
			{"parent": "PPO-2", "attributes_json": '{"Size":"Free"}', "quantity": 5},
		]
		size_types = [
			{"label": "Apparel", "sizes": ["S", "M", "L"]},
			{"label": "Free Size", "sizes": ["Free"]},
		]
		attributes = {
			"Classic Shirt": {"primary_attribute": "Size", "primary_attribute_values": ["S", "M"]},
			"One Size Sock": {"primary_attribute": "Size", "primary_attribute_values": ["Free"]},
		}

		result = ppo_report.build_report(orders, details, size_types, attributes)

		self.assertEqual([row["name"] for row in result["orders"]], ["PPO-1", "PPO-2"])
		self.assertEqual(result["max_columns"], 3)
		self.assertEqual(result["orders"][0]["qty_by_position"], [10, 20, 0])
		self.assertEqual(result["orders"][0]["total"], 30)
		self.assertEqual(result["orders"][1]["qty_by_position"], [5, 0, 0])
		self.assertEqual(result["orders"][1]["total"], 5)
		self.assertEqual(
			{key: result["orders"][1][key] for key in ("fabric", "dia", "gsm")},
			{"fabric": "Cotton Rib", "dia": "18 Dia", "gsm": 180},
		)
		self.assertEqual(result["summary"], {"total_orders": 2, "total_quantity": 35, "size_groups": 2})

	def test_current_rows_without_attribute_json_use_variant_primary_attribute(self):
		details = [
			{"parent": "PPO-1", "item_variant": "SHIRT-M", "attributes_json": None, "quantity": 20},
			{"parent": "PPO-1", "item_variant": "SHIRT-S", "attributes_json": None, "quantity": 10},
		]
		with patch.object(
			ppo_report,
			"get_variant_attr_details",
			side_effect=lambda variant: {"Size": variant.rsplit("-", 1)[-1]},
		):
			result = ppo_report.attach_variant_primary_values(details, {"PPO-1": "Size"})

		self.assertEqual([row["primary_value"] for row in result], ["M", "S"])

	def test_dispatch_rows_are_combined_by_date_lot_and_size(self):
		result = ppo_report.pivot_dispatch_rows(
			[
				{"date": "2026-10-03", "lot": "LOT-2", "size": "M", "quantity": 4},
				{"date": "2026-10-02", "lot": "LOT-1", "size": "S", "quantity": 5},
				{"date": "2026-10-02", "lot": "LOT-1", "size": "S", "quantity": 3},
				{"date": "2026-10-02", "lot": "LOT-1", "size": "M", "quantity": 2},
			]
		)

		self.assertEqual(result["sizes"], ["M", "S"])
		self.assertEqual(
			result["rows"],
			[
				{"date": "2026-10-02", "lot": "LOT-1", "sizes": {"S": 8, "M": 2}, "total": 10},
				{"date": "2026-10-03", "lot": "LOT-2", "sizes": {"M": 4}, "total": 4},
			],
		)

	def test_dispatch_summary_uses_current_lot_and_finishing_plan_doctypes(self):
		calls = []

		def fake_get_all(doctype, **kwargs):
			calls.append((doctype, kwargs))
			if doctype == "SD YRP Lot":
				return ["LOT-1"]
			if doctype == "SD YRP Finishing Plan":
				return ["FP-1"]
			return []

		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_all", side_effect=fake_get_all),
			patch.object(ppo_report, "load_dispatch_rows", return_value=[]),
		):
			result = ppo_report.get_ppo_dispatch_summary("PPO-1")

		self.assertEqual(calls[0][0], "SD YRP Lot")
		self.assertEqual(calls[0][1]["filters"], {"production_order": "PPO-1"})
		self.assertEqual(calls[1][0], "SD YRP Finishing Plan")
		self.assertEqual(calls[1][1]["filters"], {"lot": ["in", ["LOT-1"]]})
		self.assertEqual(result, {"sizes": [], "rows": []})

	def test_excel_download_sets_binary_response_metadata(self):
		fake_xlsx = SimpleNamespace(getvalue=lambda: b"xlsx-bytes")
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(ppo_report, "get_ppo_report", return_value={
				"orders": [{
					"name": "PPO-1", "item": "Shirt", "posting_date": "2026-10-01",
					"delivery_date": "2026-10-10", "dont_deliver_after": "2026-10-12",
					"lead_time": 9, "status": "Open", "group_label": "Apparel",
					"qty_by_position": [10, 20], "total": 30, "comments": "",
				}],
				"size_groups": [{"label": "Apparel", "sizes": ["S", "M"]}],
				"max_columns": 2,
				"summary": {"total_orders": 1, "total_quantity": 30, "size_groups": 1},
			}),
			patch.object(ppo_report, "make_xlsx", return_value=fake_xlsx),
			patch.object(ppo_report, "now_datetime", return_value=SimpleNamespace(strftime=lambda _fmt: "09-10-2026_18-30-00")),
		):
			ppo_report.download_ppo_report()

		self.assertEqual(frappe.response["filename"], "PPO_Report_09-10-2026_18-30-00.xlsx")
		self.assertEqual(frappe.response["filecontent"], b"xlsx-bytes")
		self.assertEqual(frappe.response["type"], "binary")

	def test_report_endpoints_are_authenticated(self):
		for endpoint in (
			web_workspace.get_ppo_report,
			web_workspace.get_ppo_dispatch_summary,
			web_workspace.download_ppo_report,
		):
			self.assertIn(endpoint, frappe.whitelisted)
			self.assertNotIn(endpoint, frappe.guest_methods)
