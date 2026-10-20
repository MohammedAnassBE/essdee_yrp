import json
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import inward_quantity, size_wise_stock
from essdee_yrp.sales import ppo_report


def desk_report(name):
	path = Path(__file__).parent / "essdee_yrp" / "report" / name
	assert (path / f"{name}.py").exists(), f"Desk report missing: {name}"
	return import_module(f"essdee_yrp.essdee_yrp.report.{name}.{name}")


class TestPlanningSalesDeskReports(IntegrationTestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.previous_user)

	def lot(self):
		lots = frappe.get_all("SD YRP Lot", filters={"production_detail": ["is", "set"]}, fields=["name", "item", "status"], limit_page_length=1)
		if not lots:
			self.skipTest("Requires a Lot with a production detail.")
		return lots[0]

	def test_inward_matches_web_columns_rows_and_message(self):
		desk = desk_report("sd_yrp_inward_quantity_report")
		lot = self.lot()
		process = frappe.db.get_value("YRP Work Order", {"lot": lot.name}, "process_name") or frappe.db.get_value("YRP Process", {}, "name")
		if not process:
			self.skipTest("Requires a Process.")
		filters = {"lot": lot.name, "process": process}
		web = inward_quantity.run(filters)
		columns, rows, message = desk.execute(filters)
		self.assertEqual(columns, web["columns"])
		self.assertEqual(rows, web["result"])
		self.assertEqual(message, web["message"])

	def test_size_stock_matches_web_for_ordered_processes_and_both_statuses(self):
		desk = desk_report("sd_yrp_size_wise_stock_report")
		lot = self.lot()
		processes = frappe.get_all("YRP Process", pluck="name", order_by="name desc", limit_page_length=2)
		for status in ("Open", "Closed"):
			with self.subTest(status=status):
				filters = {"lot": [lot.name], "item": [lot.item], "lot_status": status, "process_list": frappe.as_json(processes)}
				web = size_wise_stock.run(filters)
				columns, rows = desk.execute(filters)
				self.assertEqual(columns, web["columns"])
				self.assertEqual(rows, web["result"])

	def test_ppo_matches_web_orders_sizes_and_summary(self):
		desk = desk_report("sd_yrp_ppo_report")
		for filters in ({}, {"status": "Draft"}, {"from_date": "1900-01-01", "to_date": "1900-01-02"}):
			with self.subTest(filters=filters):
				web = ppo_report.get_ppo_report(filters)
				columns, rows, _message, _chart, summary = desk.execute(filters)
				self.assertEqual(len(rows), len(web["orders"]))
				for actual, expected in zip(rows, web["orders"], strict=True):
					self.assertEqual({key: actual[key] for key in expected}, expected)
					self.assertEqual([actual[f"size_{index}"] for index in range(web["max_columns"])], expected["qty_by_position"])
				self.assertEqual(len([column for column in columns if column["fieldname"].startswith("size_")]), web["max_columns"])
				self.assertEqual([entry["value"] for entry in summary], [web["summary"][key] for key in ("total_orders", "total_quantity", "size_groups")])

	def test_planning_required_filters_match_web_validation(self):
		for name in ("sd_yrp_inward_quantity_report", "sd_yrp_size_wise_stock_report"):
			with self.subTest(report=name), self.assertRaises(frappe.ValidationError):
				desk_report(name).execute({})

	def test_ppo_mixed_groups_and_summarized_dispatch_use_group_size_order(self):
		desk = desk_report("sd_yrp_ppo_report")
		web = ppo_report.build_report(
			[{"name": "PPO-A", "item": "Shirt"}, {"name": "PPO-B", "item": "Sock"}],
			[{"parent": "PPO-A", "attributes_json": '{"Size":"M"}', "quantity": 7}, {"parent": "PPO-B", "attributes_json": '{"Size":"One"}', "quantity": 4}],
			[{"label": "Apparel", "sizes": ["S", "M"]}, {"label": "One Size", "sizes": ["One"]}],
			{"Shirt": {"primary_attribute_values": ["S", "M"]}, "Sock": {"primary_attribute_values": ["One"]}},
		)
		with (
			patch.object(ppo_report, "get_ppo_report", return_value=web),
			patch.object(ppo_report, "get_ppo_dispatch_summary_bulk", return_value={"PPO-A": {"rows": [{"date": "2026-10-01", "lot": "L", "sizes": {"M": 3, "S": 1}, "total": 4}]}, "PPO-B": {"rows": []}}),
		):
			columns, rows, _message, _chart, summary = desk.execute({"summarized": 1, "show_fabric": 1, "show_dia": 1, "show_gsm": 1})
		self.assertEqual([(row["size_0"], row["size_1"], row["total"]) for row in rows], [(0, 7, 7), (1, 3, 4), (1, 3, 4), (4, 0, 4)])
		self.assertEqual([row["row_type"] for row in rows], ["Order", "Dispatch", "Dispatched Total", "Order"])
		self.assertEqual(summary[1]["value"], 11)
		self.assertEqual([col["label"] for col in columns if col["fieldname"].startswith("size_")], ["Apparel: S / One Size: One", "Apparel: M"])
		self.assertTrue({"fabric", "dia", "gsm"} <= {col["fieldname"] for col in columns})

	def test_standard_report_metadata_and_matching_workspace_links(self):
		root = Path(__file__).parent / "essdee_yrp"
		for slug, name, ref, workspace in (
			("sd_yrp_inward_quantity_report", "SD YRP Inward Quantity Report", "SD YRP Lot", "planning"),
			("sd_yrp_size_wise_stock_report", "SD YRP Size Wise Stock Report", "SD YRP Lot", "planning"),
			("sd_yrp_ppo_report", "SD YRP PPO Report", "YRP Production Order", "sales"),
		):
			with self.subTest(report=name):
				metadata_path = root / "report" / slug / f"{slug}.json"
				self.assertTrue(metadata_path.exists(), f"Missing Report JSON: {name}")
				doc = frappe.get_doc(json.loads(metadata_path.read_text()))
				self.assertEqual((doc.name, doc.ref_doctype, doc.module, doc.report_type, doc.is_standard), (name, ref, "Essdee YRP", "Script Report", "Yes"))
				self.assertIn("All", [role.role for role in doc.roles])
				page = json.loads((root / "workspace" / workspace / f"{workspace}.json").read_text())
				self.assertIn(name, [link.get("link_to") for link in page["links"] if link.get("link_type") == "Report"])
				cards = {block["data"].get("card_name") for block in json.loads(page["content"]) if block["type"] == "card"}
				self.assertTrue(any(link["type"] == "Card Break" and link["label"] in cards for link in page["links"]))

	def test_guest_is_denied_by_every_source_service(self):
		frappe.set_user("Guest")
		for name in ("sd_yrp_inward_quantity_report", "sd_yrp_size_wise_stock_report", "sd_yrp_ppo_report"):
			with self.subTest(report=name), self.assertRaises(frappe.PermissionError):
				desk_report(name).execute({})
