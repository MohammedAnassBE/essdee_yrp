from unittest.mock import Mock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_size_range.sd_yrp_fg_item_size_range import (
	get_sizes,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lotwise_item_profit.sd_yrp_lotwise_item_profit import (
	get_lot_qty,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image import (
	get_image_list,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_sales_piece_sticker_print.sd_yrp_sales_piece_sticker_print import (
	get_template,
)


class TestDirectBusinessLogic(FrappeTestCase):
	def test_lot_quantity_api_uses_only_approved_fields(self):
		lot_doc = Mock(
			planned_qty=[
				frappe._dict(size="S", qty=10),
				frappe._dict(size="M", qty=20),
			]
		)
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_lotwise_item_profit.sd_yrp_lotwise_item_profit.frappe.get_doc",
			return_value=lot_doc,
		):
			self.assertEqual(get_lot_qty("LOT-TEST", "qty"), {"S": 10, "M": 20})
			with self.assertRaises(frappe.ValidationError):
				get_lot_qty("LOT-TEST", "__dict__")
		lot_doc.check_permission.assert_called_once_with("read")

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
		doc = frappe.get_doc(
			{
				"doctype": 'SD YRP Product Release',
				"product_placement": [
					{
						"doctype": 'SD YRP Product Placement',
						"title_header": "Front",
					}
				],
			}
		)
		doc.run_method("onload")
		self.assertEqual(
			doc.get("__onload")["placement_images"],
			[
				{
					"image_url": "",
					"image_title": "Front",
					"image_name": None,
				}
			],
		)

	def test_existing_size_range_reads_installed_values(self):
		doc = Mock(
			sizes=[
				frappe._dict(attribute_value="S"),
				frappe._dict(attribute_value="M"),
			]
		)
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_fg_item_size_range.sd_yrp_fg_item_size_range.frappe.get_doc",
			return_value=doc,
		):
			self.assertEqual(get_sizes("SIZE-RANGE-TEST"), ["S", "M"])
		doc.check_permission.assert_called_once_with("read")

	def test_fg_template_reuses_base_attribute_mapping_contract(self):
		doc = frappe.get_doc(
			{
				"doctype": 'SD YRP FG Item Master Template',
				"name": "_Test FG Item Master Template",
			}
		)
		doc.run_method("onload")
		self.assertEqual(doc.get("__onload")["attr_list"], [])
		self.assertEqual(doc.get("__onload")["dependent_attribute"], {})

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
