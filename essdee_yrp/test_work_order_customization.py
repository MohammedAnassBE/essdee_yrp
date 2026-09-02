from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.work_order_hooks import validate_lot_process_selection


class TestWorkOrderCustomization(FrappeTestCase):
	def test_no_receivables_is_an_essdee_custom_field(self):
		field = frappe.get_meta('YRP Work Order', cached=False).get_field("no_receivables")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Check")
		self.assertEqual(field.default, "0")
		self.assertTrue(
			frappe.db.exists(
				"Custom Field",
				{
					"dt": 'YRP Work Order',
					"fieldname": "no_receivables",
					"module": "Essdee YRP",
				},
			)
		)

	def test_item_is_explicit_and_production_detail_is_derived(self):
		context = {
			"is_cloth_process": True,
			"item_options": ["CLOTH-A"],
			"options": [
				{"item": "CLOTH-A", "production_detail": "IPD-A"},
			],
		}

		with patch(
			"essdee_yrp.api.work_order._get_work_order_selection_context",
			return_value=context,
		):
			with self.assertRaisesRegex(frappe.ValidationError, "not available"):
				validate_lot_process_selection(
					frappe._dict(lot="LOT-A", process_name="KNITTING", item=None)
				)

			doc = frappe._dict(lot="LOT-A", process_name="KNITTING", item="CLOTH-A")
			validate_lot_process_selection(doc)
			self.assertEqual(doc.production_detail, "IPD-A")
