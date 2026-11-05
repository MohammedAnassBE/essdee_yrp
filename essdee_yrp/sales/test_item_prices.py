from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.sales import item_prices

DOCTYPE = "SD YRP Sales Item Price"


def unpriced_variant():
	"""An eligible variant of a sales template that has no Sales Item Price yet."""
	for row in item_prices.get_variant_rows(item=None, priced_only=False, limit=500):
		if not frappe.db.exists(DOCTYPE, {"item_variant": row.variant}):
			return row
	return None


class TestSalesItemPriceGrid(TestCase):
	def test_price_types_map_to_doctype_fields_with_mrp_first(self):
		self.assertEqual(
			[(row["value"], row["label"]) for row in item_prices.PRICE_TYPES],
			[("mrp_rate", "MRP Rate"), ("rate", "Distributor Rate"), ("retail_rate", "Retail Rate")],
		)

	def test_build_items_groups_variants_by_template_in_size_range_order(self):
		rows = [
			frappe._dict(item="T", item_name="Tee", variant="T-L", size="L", size_range="R"),
			frappe._dict(item="T", item_name="Tee", variant="T-S", size="S", size_range="R"),
		]
		prices = {"T-S": frappe._dict(rate=10, retail_rate=12, mrp_rate=20)}
		items = item_prices.build_items(rows, prices, {"R": {"S": 1, "L": 2}})
		self.assertEqual(len(items), 1)
		self.assertEqual(items[0]["sizes"], ["S", "L"])
		self.assertEqual(items[0]["variants"], {"S": "T-S", "L": "T-L"})
		self.assertEqual(items[0]["prices"]["mrp_rate"], {"S": 20, "L": 0})
		self.assertEqual(items[0]["prices"]["rate"], {"S": 10, "L": 0})
		self.assertEqual(items[0]["missing"], ["L"])


class TestSalesItemPriceSave(TestCase):
	def tearDown(self):
		frappe.db.rollback()

	def setUp(self):
		self.row = unpriced_variant()
		if not self.row:
			self.skipTest("No unpriced sales variant on this site")

	def test_save_creates_a_piece_price_then_updates_only_the_chosen_rate(self):
		result = item_prices.save_item_prices("mrp_rate", {self.row.variant: "199"})
		self.assertEqual(result, {"created": 1, "updated": 0})
		doc = frappe.get_doc(DOCTYPE, {"item_variant": self.row.variant})
		self.assertEqual((doc.mrp_rate, doc.rate, doc.uom), (199, 0, "Piece"))

		result = item_prices.save_item_prices("rate", {self.row.variant: 120})
		self.assertEqual(result, {"created": 0, "updated": 1})
		doc.reload()
		self.assertEqual((doc.mrp_rate, doc.rate), (199, 120))

	def test_update_records_old_and_new_rate_in_a_version(self):
		item_prices.save_item_prices("rate", {self.row.variant: 100})
		with patch.object(frappe, "in_test", False):  # Frappe skips Version rows under tests
			item_prices.save_item_prices("rate", {self.row.variant: 125})
		data = frappe.get_all(
			"Version", filters={"ref_doctype": DOCTYPE, "docname": self.row.variant}, pluck="data"
		)
		changes = [change for row in data for change in frappe.parse_json(row)["changed"]]
		self.assertTrue(
			any(f == "rate" and "100" in old and "125" in new for f, old, new in changes), changes
		)

	def test_grid_for_the_item_lists_the_new_price(self):
		item_prices.save_item_prices("retail_rate", {self.row.variant: 150})
		payload = item_prices.get_item_price_grid(self.row.item)
		self.assertEqual(payload["uom"], "Piece")
		item = next(entry for entry in payload["items"] if entry["item"] == self.row.item)
		self.assertEqual(item["prices"]["retail_rate"][self.row.size], 150)

	def test_save_rejects_an_unknown_price_type(self):
		with self.assertRaises(frappe.ValidationError):
			item_prices.save_item_prices("purchase_rate", {self.row.variant: 1})

	def test_save_rejects_a_non_sales_variant(self):
		with self.assertRaises(frappe.ValidationError):
			item_prices.save_item_prices("rate", {self.row.item: 1})
		self.assertFalse(frappe.db.exists(DOCTYPE, {"item_variant": self.row.item}))

	def test_save_rejects_negative_rates(self):
		with self.assertRaises(frappe.ValidationError):
			item_prices.save_item_prices("rate", {self.row.variant: -5})


class TestSalesItemPricePermissions(TestCase):
	def test_sales_roles_can_create_and_update_without_delete(self):
		perms = {row.role: row for row in frappe.get_meta(DOCTYPE).permissions}
		for role in ("Sales User", "Sales Manager"):
			with self.subTest(role=role):
				row = perms[role]
				self.assertEqual((row.read, row.write, row.create, row.delete), (1, 1, 1, 0))
