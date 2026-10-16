from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import inward_quantity as report
from essdee_yrp.planning.reports import production_quantities as quantities
from essdee_yrp.planning.reports.test_b2_support import LiveReportChecks


class TestInwardQuantity(TestCase):
	def test_colour_part_type_size_totals_and_order(self):
		detail = {"is_set_item": 1, "set_item_attribute": "Part", "primary_item_attribute": "Size", "packing_attribute": "Colour", "major_attribute_value": "Bottom"}
		attributes = {"A": {"Size": "M", "Colour": "Red", "Part": "Top"}, "B": {"Size": "S", "Colour": "Red", "Part": "Bottom"}}
		items = [{"item_variant": variant, "set_combination": '{"major_colour":"Red"}', "received_type_json": '{"Accepted":3,"Rejected":1}'} for variant in attributes]
		rows = report.aggregate(items, attributes, detail, ["M", "S"])
		self.assertEqual(len(rows), 12)
		self.assertEqual(rows[0]["part"], "Bottom")
		self.assertEqual(rows[0]["size_1"], 3)
		self.assertEqual(rows[2]["total"], 4)
		self.assertEqual(sum(row["total"] for row in rows if row["colour"] == "Total" and row["type"] == "Total"), 8)
		self.assertNotIn("part", [row["fieldname"] for row in quantities.matrix_columns(["M"], False)])
		self.assertEqual([row["label"] for row in quantities.matrix_columns(["M", "S"], True)][4:6], ["M", "S"])

	def test_composite_processes_and_submitted_non_rework_query(self):
		details = [{"parent": "Group", "process_name": "Cut"}, {"parent": "Cut", "process_name": "Child"}]
		self.assertEqual(quantities.expand_processes("Cut", details), ["Child", "Cut", "Group"])
		with patch.object(frappe, "get_list", return_value=[]) as read:
			quantities.work_orders({"lot": "L", "process_name": ["in", ["Cut"]]})
			self.assertEqual(read.call_args.kwargs["filters"], {"docstatus": 1, "is_rework": 0, "lot": "L", "process_name": ["in", ["Cut"]]})

	def test_required_filters_and_lot_permission(self):
		with patch.object(report, "require_access"):
			for filters in ({}, {"lot": "L"}, {"process": "P"}):
				with self.assertRaises(frappe.ValidationError):
					report.run(filters)
		lot = frappe._dict(production_detail="D")
		lot.check_permission = lambda permission: frappe.throw("Denied", frappe.PermissionError)
		with patch.object(frappe, "get_doc", return_value=lot):
			with self.assertRaises(frappe.PermissionError):
				quantities.quantity_context({"lot": "L", "process": "P"})


class TestInwardQuantityLive(LiveReportChecks, IntegrationTestCase):
	report = report
