import frappe
from frappe.tests.utils import FrappeTestCase

from yrp.stock.dimensions import (
	MANAGED_DIMENSION_FIELD_MARKER,
	STOCK_DOCTYPES,
	get_stock_dimensions,
)


class TestRepostItemValuationCustomization(FrappeTestCase):
	def test_via_landed_cost_voucher_is_essdee_owned(self):
		field = frappe.get_meta("Repost Item Valuation", cached=False).get_field(
			"via_landed_cost_voucher"
		)

		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(field.default, "0")
		self.assertEqual(field.insert_after, "allow_negative_stock")
		self.assertTrue(
			frappe.db.exists(
				"Custom Field",
				{
					"dt": "Repost Item Valuation",
					"fieldname": "via_landed_cost_voucher",
					"module": "Essdee YRP",
				},
			)
		)

	def test_stock_dimensions_remain_base_yrp_managed(self):
		self.assertIn("Repost Item Valuation", STOCK_DOCTYPES)
		meta = frappe.get_meta("Repost Item Valuation", cached=False)

		for dimension in get_stock_dimensions():
			with self.subTest(fieldname=dimension.fieldname):
				field = meta.get_field(dimension.fieldname)
				self.assertIsNotNone(field)
				self.assertEqual(field.fieldtype, "Link")
				self.assertEqual(field.options, dimension.dimension_doctype)
				self.assertIn(MANAGED_DIMENSION_FIELD_MARKER, field.description or "")
				self.assertFalse(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Repost Item Valuation",
							"fieldname": dimension.fieldname,
							"module": "Essdee YRP",
						},
					)
				)
