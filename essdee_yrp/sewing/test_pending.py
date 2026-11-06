"""Sewing Pending: From type minus To type per work station, lot and item."""

from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.utils import flt

from essdee_yrp.sewing import pending
from essdee_yrp.sewing.pending import (
	GRN_QUANTITY,
	build_pending_groups,
	get_sewing_pending_data,
	validate_pending_types,
)

TYPES = ["Input Qty", "Line Output", "Checking Output", GRN_QUANTITY]


def cell(line, lot, colour, size, part=""):
	return ((line, lot, "Shirt", "", "IPD"), (colour, part, size))


class TestPendingGroups(TestCase):
	sizes = {"IPD": ["S", "M", "L"]}

	def test_only_positive_cells_are_kept_and_lines_sort_naturally(self):
		from_quantities = {
			cell("Line 10", "LOT-1", "Red", "M"): 50,
			cell("Line 2", "LOT-1", "Red", "L"): 30,
			cell("Line 2", "LOT-1", "Red", "S"): 10,
			cell("Line 2", "LOT-1", "Blue", "S"): 5,
			cell("Line 2", "LOT-2", "Red", "M"): 10,
		}
		to_quantities = {
			cell("Line 10", "LOT-1", "Red", "M"): 20,
			cell("Line 2", "LOT-1", "Blue", "S"): 9,
			cell("Line 2", "LOT-2", "Red", "M"): 10,
			cell("Line 4", "LOT-1", "Red", "M"): 4,
		}
		groups, totals = build_pending_groups(from_quantities, to_quantities, self.sizes)
		self.assertEqual([group["work_station"] for group in groups], ["Line 2", "Line 10"])
		row = groups[0]["rows"][0]
		self.assertEqual(len(groups[0]["rows"]), 1)
		self.assertEqual((row["lot"], row["from_qty"], row["to_qty"], row["pending"]), ("LOT-1", 40, 0, 40))
		self.assertEqual(row["sizes"], ["S", "L"])
		self.assertEqual(
			row["colours"],
			[
				{"colour": "Red", "part": "", "values": {"L": 30, "S": 10}, "total": 40},
			],
		)
		self.assertEqual(row["size_totals"], {"S": 10, "L": 30})
		self.assertFalse(row["has_part"])
		self.assertEqual(groups[1]["totals"], {"from_qty": 50, "to_qty": 20, "pending": 30})
		self.assertEqual(totals, {"from_qty": 90, "to_qty": 20, "pending": 70})

	def test_rows_sort_by_lot_and_set_parts_stay_separate(self):
		from_quantities = {
			cell("L1", "B", "Red", "S"): 1,
			cell("L1", "A", "Red", "S", "Top"): 2,
			cell("L1", "A", "Red", "S", "Bottom"): 3,
		}
		groups, _ = build_pending_groups(from_quantities, {}, self.sizes)
		rows = groups[0]["rows"]
		self.assertEqual([row["lot"] for row in rows], ["A", "B"])
		self.assertTrue(rows[0]["has_part"])
		self.assertEqual(
			[(colour["part"], colour["total"]) for colour in rows[0]["colours"]], [("Bottom", 3), ("Top", 2)]
		)


class TestPendingTypes(TestCase):
	def settings(self):
		return frappe._dict(sewing_input_qty_type="Input Qty", sewing_line_output_type="Line Output")

	def test_defaults_come_from_mrp_settings(self):
		with patch.object(pending.frappe, "get_cached_doc", return_value=self.settings()):
			self.assertEqual(validate_pending_types(TYPES, "", None), ("Input Qty", "Line Output"))

	def test_grn_quantity_is_allowed_on_either_side(self):
		self.assertEqual(
			validate_pending_types(TYPES, "Line Output", GRN_QUANTITY), ("Line Output", GRN_QUANTITY)
		)
		self.assertEqual(
			validate_pending_types(TYPES, GRN_QUANTITY, "Input Qty"), (GRN_QUANTITY, "Input Qty")
		)

	def test_unknown_or_equal_types_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			validate_pending_types(TYPES, "Order Qty", "Line Output")
		with self.assertRaises(frappe.ValidationError):
			validate_pending_types(TYPES, "Line Output", "Line Output")


class TestPendingData(TestCase):
	"""Read-only checks against the site's own Sewing Plans."""

	@classmethod
	def setUpClass(cls):
		cls.supplier = frappe.db.sql(
			"""select sp.supplier from `tabSD YRP Sewing Plan` sp
			join `tabYRP Work Order` wo on wo.name = sp.work_order and wo.open_status = 'Open'
			join `tabSD YRP Sewing Plan Entry Detail` entry on entry.sewing_plan = sp.name
			group by sp.supplier order by count(*) desc limit 1"""
		)
		cls.supplier = cls.supplier[0][0] if cls.supplier else None

	def setUp(self):
		if not self.supplier:
			self.skipTest("No open Sewing Plan with entries on this site.")

	def assert_consistent(self, data):
		self.assertEqual(data["types"], pending.get_pending_types())
		total = 0
		for group in data["groups"]:
			for row in group["rows"]:
				self.assertGreater(row["pending"], 0)
				self.assertEqual(flt(row["from_qty"] - row["to_qty"]), flt(row["pending"]))
				self.assertEqual(row["work_station"], group["work_station"])
				cells = [value for colour in row["colours"] for value in colour["values"].values()]
				self.assertTrue(all(value > 0 for value in cells))
				self.assertEqual(flt(sum(cells)), flt(row["pending"]))
				self.assertEqual(flt(sum(row["size_totals"].values())), flt(row["pending"]))
				total += row["pending"]
		self.assertEqual(flt(total), flt(data["totals"]["pending"]))

	def test_default_pair_is_line_wise_and_consistent(self):
		data = get_sewing_pending_data(self.supplier)
		self.assertTrue(data["is_line_wise"])
		self.assert_consistent(data)

	def test_filters_narrow_the_rows(self):
		data = get_sewing_pending_data(self.supplier, "Line Output", "Checking Output")
		self.assert_consistent(data)
		rows = [row for group in data["groups"] for row in group["rows"]]
		if not rows:
			self.skipTest("No Line Output pending against Checking Output.")
		sample = rows[0]
		for field, value in (
			("work_station", sample["work_station"]),
			("lots", [sample["lot"]]),
			("items", [sample["item"]]),
		):
			filtered = get_sewing_pending_data(
				self.supplier, "Line Output", "Checking Output", **{field: value}
			)
			self.assert_consistent(filtered)
			filtered_rows = [row for group in filtered["groups"] for row in group["rows"]]
			self.assertIn(sample, filtered_rows)
			key = field.rstrip("s") if field != "work_station" else field
			self.assertTrue(all(row[key] == sample[key] for row in filtered_rows))

	def test_multiple_lots_combine_their_rows(self):
		rows = [row for group in get_sewing_pending_data(self.supplier)["groups"] for row in group["rows"]]
		lots = sorted({row["lot"] for row in rows})[:2]
		if len(lots) < 2:
			self.skipTest("Fewer than two Lots with pending input.")
		data = get_sewing_pending_data(self.supplier, lots=frappe.as_json(lots))
		self.assert_consistent(data)
		filtered = [row for group in data["groups"] for row in group["rows"]]
		self.assertEqual(filtered, [row for row in filtered if row["lot"] in lots])
		self.assertEqual(sorted({row["lot"] for row in filtered}), lots)

	def test_grn_quantity_is_work_order_wise_and_rejects_a_work_station_filter(self):
		data = get_sewing_pending_data(self.supplier, "Line Output", GRN_QUANTITY)
		self.assertFalse(data["is_line_wise"])
		self.assertTrue(all(group["work_station"] == "" for group in data["groups"]))
		self.assertTrue(all(row["work_order"] for group in data["groups"] for row in group["rows"]))
		self.assert_consistent(data)
		closed = set(frappe.get_all("YRP Work Order", filters={"open_status": ["!=", "Open"]}, pluck="name"))
		self.assertFalse(
			[row for group in data["groups"] for row in group["rows"] if row["work_order"] in closed]
		)
		with self.assertRaises(frappe.ValidationError):
			get_sewing_pending_data(self.supplier, "Line Output", GRN_QUANTITY, work_station="Any Line")

	def test_closed_work_orders_are_excluded(self):
		plans = pending.get_open_plans(self.supplier)
		statuses = set(
			frappe.get_all(
				"YRP Work Order",
				filters={"name": ["in", [row.work_order for row in plans]]},
				pluck="open_status",
			)
		)
		self.assertEqual(statuses, {"Open"})
		closed_lots = frappe.db.sql_list(
			"""select distinct sp.lot from `tabSD YRP Sewing Plan` sp join `tabYRP Work Order` wo on wo.name = sp.work_order
			where sp.supplier = %s and wo.open_status != 'Open' and sp.lot not in (
				select sp2.lot from `tabSD YRP Sewing Plan` sp2 join `tabYRP Work Order` wo2 on wo2.name = sp2.work_order
				where sp2.supplier = %s and wo2.open_status = 'Open') limit 3""",
			(self.supplier, self.supplier),
		)
		if closed_lots:
			data = get_sewing_pending_data(self.supplier, lots=closed_lots)
			self.assertEqual(data["groups"], [])
