import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.utils import get_variant_attr_details

from essdee_yrp.finishing import web_entries

FINISHING_PLAN = "FP-2627-00197"
ALTERNATIVE_ITEM = "AISHWARYA PLAIN (S/Box)"
PRODUCTION_DETAIL = "AISHWARYA PLAIN (S/Box)-4"
COLOURS = ["Navy", "Coffee Brown", "Maroon", "Airforce Navy", "Military Green"]
SIZES = ["75 cm", "80 cm", "85 cm", "90 cm", "95 cm", "100 cm", "105 cm", "110 cm"]
ENTERED = {("Navy", "75 cm"): 34, ("Navy", "80 cm"): 192, ("Maroon", "85 cm"): 452}


def quantity_matrix(entries):
	matrix = {colour: {"checked": False, "sizes": dict.fromkeys(SIZES, 0)} for colour in COLOURS}
	for (colour, size), qty in entries.items():
		matrix[colour]["checked"] = True
		matrix[colour]["sizes"][size] = qty
	return json.dumps(matrix)


def colour_size(variant):
	attributes = get_variant_attr_details(variant)
	return attributes.get("Colour"), attributes.get("Size")


class TestAlternativeLotQuantities(FrappeTestCase):
	def test_calculate_order_keeps_each_rows_cut_qty(self):
		lot = frappe.new_doc("SD YRP Lot")
		for variant, cut_qty in (("V-1", 10), ("V-2", 20)):
			lot.append("lot_order_details", {"item_variant": variant, "set_combination": '{"major_colour": "A"}', "cut_qty": cut_qty})
		rebuilt = [
			{"item_variant": variant, "quantity": 5, "set_combination": {"major_colour": "A"}} for variant in ("V-1", "V-2")
		]
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.calculate_order_details", return_value=(rebuilt, 10)
		):
			lot.calculate_order()
		self.assertEqual([row.cut_qty for row in lot.lot_order_details], [10, 20])

	def test_new_lot_keeps_entered_colour_size_quantities(self):
		if not frappe.db.exists("SD YRP Finishing Plan", FINISHING_PLAN) or not frappe.db.exists(
			"YRP Item Production Detail", PRODUCTION_DETAIL
		):
			self.skipTest("Finishing Plan or alternative Item Production Detail is unavailable")
		values = {
			"alternative_item": ALTERNATIVE_ITEM,
			"production_detail": PRODUCTION_DETAIL,
			"quantities": quantity_matrix(ENTERED),
			"lot_source": "New Lot",
			"lot_name": "TEST-ALT-QTY",
		}
		with patch.object(frappe, "enqueue"), patch.object(frappe.db, "commit"):
			result = web_entries.create_alternative_plan(frappe.get_doc("SD YRP Finishing Plan", FINISHING_PLAN), values)
		work_order = frappe.get_doc("YRP Work Order", result["name"])
		lot = frappe.get_doc("SD YRP Lot", work_order.lot)
		expected = {key: (qty, qty) for key, qty in ENTERED.items()}
		self.assertEqual(
			{colour_size(row.item_variant): (row.quantity, row.cut_qty) for row in lot.lot_order_details}, expected
		)
		deliverables = {
			colour_size(row.item_variant): row.qty for row in work_order.deliverables if row.uom == "Pieces"
		}
		self.assertEqual(deliverables, ENTERED)
