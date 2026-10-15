from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports import inhouse_quantity as report
from essdee_yrp.planning.reports.test_b2_support import LiveReportChecks


class TestInhouseQuantity(TestCase):
	def test_parts_suppliers_dates_difference_and_latest_tone(self):
		detail = {"is_set_item": 1, "set_item_attribute": "Part", "primary_item_attribute": "Size", "packing_attribute": "Colour", "major_attribute_value": "Top"}
		attributes = {part: {"Part": part, "Size": "M", "Colour": "Red"} for part in ("Top", "Bottom")}
		orders = [{"name": name, "supplier": "Unit", "first_dc_date": first, "last_dc_date": "2026-01-10", "last_grn_date": last} for name, first, last in (("A", "2026-01-02", "2026-01-12"), ("B", "2026-01-01", "2026-01-15"))]
		items = [{"parent": name, "item_variant": part, "set_combination": '{"major_colour":"Red"}', "delivered_quantity": 10, "received_qty": 8} for name in ("A", "B") for part in attributes]
		statuses = {(name, colour, "M"): {"tone": tone, "rank": rank} for name, tone, rank in (("A", "fail", 1), ("B", "pass", 0)) for colour in ("Red", "Red(Red)")}
		rows = report.aggregate(items, attributes, detail, ["M"], orders, statuses)
		self.assertEqual(len(rows), 12)
		self.assertEqual([row["type"] for row in rows[:3]], ["Delivered", "Received", "Difference"])
		self.assertEqual([row["total"] for row in rows[:3]], [20, 16, 4])
		self.assertEqual({row["part"] for row in rows}, {"Top", "Bottom"})
		self.assertEqual(rows[0]["first_date"], "2026-01-01")
		self.assertEqual(rows[0]["last_date"], "2026-01-15")
		self.assertEqual(rows[0]["diff"], 5)
		self.assertEqual(rows[1]["tones"], {"size_0": "pass"})
		self.assertEqual(report.aggregate(items, attributes, detail, ["M"], orders)[1]["tones"], {"size_0": ""})
		secondary = next(row for row in rows if row.get("part") == "Bottom" and row["type"] == "Received" and not row.get("is_total_row"))
		self.assertEqual(secondary["colour"], "Red(Red)")
		self.assertEqual(secondary["tones"], {"size_0": "pass"})

	def test_part_footers_sum_sizes_across_colours_and_suppliers(self):
		detail = {"is_set_item": 1, "set_item_attribute": "Part", "primary_item_attribute": "Size", "packing_attribute": "Colour", "major_attribute_value": "Top"}
		attributes = {f"{part}-{size}-{colour}": {"Part": part, "Size": size, "Colour": colour} for part in ("Top", "Bottom") for size in ("S", "M") for colour in ("Red", "Blue")}
		orders = [{"name": name, "supplier": name} for name in ("A", "B")]
		items = [{"parent": order["name"], "item_variant": variant, "set_combination": '{"major_colour":"Red"}', "delivered_quantity": 5, "received_qty": 3} for order in orders for variant in attributes]
		rows = report.aggregate(items, attributes, detail, ["S", "M"], orders)
		footers = [row for row in rows if row.get("is_total_row")]
		self.assertEqual(rows[-6:], footers)
		self.assertEqual(len(footers), 6)
		for part in ("Top", "Bottom"):
			self.assertEqual([(row["type"], row["size_0"], row["size_1"], row["total"]) for row in footers if row["part"] == part], [("Delivered", 20, 20, 40), ("Received", 12, 12, 24), ("Difference", 8, 8, 16)])
		self.assertTrue(all(row["colour"] == "Total" and not row.get("tones") and not row.get("supplier") for row in footers))

	def test_non_set_overall_totals_and_supplier_names(self):
		orders = [{"name": name, "supplier": name} for name in ("S-1", "S-2")]
		items = [{"parent": order["name"], "item_variant": "V", "set_combination": '{"major_colour":"Red"}', "delivered_quantity": 5, "received_qty": 3} for order in orders]
		with patch.object(frappe, "get_all", return_value=[{"name": "S-1", "supplier_name": "Sewing Unit"}, {"name": "S-2", "supplier_name": ""}]) as read:
			labels = report.quantities.supplier_names(orders + orders)
			read.assert_called_once_with("Supplier", filters={"name": ["in", ["S-1", "S-2"]]}, fields=["name", "supplier_name"], limit_page_length=0)
		rows = report.aggregate(items, {"V": {"Size": "M"}}, {"primary_item_attribute": "Size"}, ["M"], orders, supplier_labels=labels)
		self.assertEqual([row["supplier"] for row in rows[:6:3]], ["Sewing Unit", "S-2"])
		self.assertEqual([(row["size_0"], row["total"]) for row in rows[-3:]], [(10, 10), (6, 6), (4, 4)])
		self.assertTrue(all(row["is_total_row"] for row in rows[-3:]))
		with patch.object(frappe, "get_all") as read:
			self.assertEqual(report.quantities.supplier_names([]), {})
			read.assert_not_called()

	def test_inspections_are_not_read_without_permission(self):
		with patch.object(report.quantities, "can_read", return_value=False), patch.object(frappe, "get_list") as read:
			self.assertEqual(report.inspection_status([{"name": "A"}]), {})
			read.assert_not_called()

	def test_inspection_queries_are_batched_latest_first(self):
		inspections = [{"name": name, "against_id": "A", "result": result} for name, result in (("New", "Hold"), ("Old", "Fail"))]
		def children(doctype, parents, fields, parenttype):
			field = "colour" if "Colour" in doctype else "size"
			return [{"parent": name, field: "Red" if field == "colour" else "M", "selected": 1} for name in parents]
		with patch.object(report.quantities, "can_read", return_value=True), patch.object(frappe, "get_list", return_value=inspections) as read, patch.object(report.quantities, "child_rows", side_effect=children) as child:
			self.assertEqual(report.inspection_status([{"name": "A"}])[("A", "Red", "M")]["tone"], "hold")
			self.assertEqual(child.call_count, 2)
			self.assertIn("posting_date desc", read.call_args.kwargs["order_by"])


class TestInhouseQuantityLive(LiveReportChecks, IntegrationTestCase):
	report = report
