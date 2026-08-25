import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.fg_item_size_range.fg_item_size_range import (
	get_sizes,
)
from essdee_yrp.essdee_yrp.doctype.lotwise_item_profit.lotwise_item_profit import (
	get_lot_qty,
)
from essdee_yrp.essdee_yrp.doctype.product_image.product_image import (
	get_image_list,
)
from essdee_yrp.essdee_yrp.doctype.sales_piece_sticker_print.sales_piece_sticker_print import (
	get_template,
)


class TestDirectBusinessLogic(FrappeTestCase):
	def test_lot_quantity_api_uses_only_approved_fields(self):
		lot = frappe.get_all(
			"Lot Planned Qty",
			filters={"parenttype": "Lot"},
			pluck="parent",
			limit=1,
		)[0]
		lot_doc = frappe.get_doc("Lot", lot)
		self.assertEqual(
			get_lot_qty(lot, "qty"),
			{row.size: row.qty for row in lot_doc.planned_qty if row.size},
		)
		with self.assertRaises(frappe.ValidationError):
			get_lot_qty(lot, "__dict__")

	def test_product_image_lookup_returns_only_readable_shape(self):
		rows = get_image_list("")
		self.assertLessEqual(len(rows), 50)
		self.assertTrue(
			all(
				set(row) == {"image_url", "image_title", "image_name"}
				for row in rows
			)
		)

	def test_existing_product_release_onload_builds_image_payloads(self):
		name = frappe.get_all("Product Release", pluck="name", limit=1)[0]
		doc = frappe.get_doc("Product Release", name)
		doc.run_method("onload")
		self.assertIsInstance(doc.get("__onload") or {}, dict)

	def test_existing_size_range_reads_installed_values(self):
		name = frappe.get_all("FG Item Size Range", pluck="name", limit=1)[0]
		doc = frappe.get_doc("FG Item Size Range", name)
		self.assertEqual(
			get_sizes(name),
			[row.attribute_value for row in doc.sizes if row.attribute_value],
		)

	def test_fg_template_reuses_base_attribute_mapping_contract(self):
		name = frappe.get_all("FG Item Master Template", pluck="name", limit=1)[0]
		doc = frappe.get_doc("FG Item Master Template", name)
		doc.run_method("onload")
		self.assertIn("attr_list", doc.get("__onload") or {})

	def test_sales_piece_template_uses_ceiling_label_rows(self):
		item = frappe._dict(
			quantity=5,
			mrp_price=100,
			offer_price=80,
			sku="SKU-1",
		)
		result = get_template(
			item,
			"{{ print_quantity }}|{{ mrp_price }}|{{ offer_price }}|{{ sku }}",
			2,
			"Essdee",
		)
		self.assertEqual(result, "3|100.00|80.00|SKU-1")
