from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sd_yrp_sync import (
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
	PRODUCTION_ORDER_GRID_ATTRIBUTE,
)
from essdee_yrp.setup import ensure_yrp_production_order_settings


class TestSDYRPSyncSetup(IntegrationTestCase):
	def test_essdee_production_order_settings_are_self_healing_and_idempotent(self):
		settings = frappe.get_doc({
			"doctype": "YRP Settings",
			"production_order_attributes": [
				{"attribute": "Colour", "is_grid_attribute": 0},
			],
			"po_dependent_attribute": None,
			"po_dependent_attribute_value": None,
		})

		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc", return_value=settings),
			patch.object(settings, "save") as save,
		):
			self.assertTrue(ensure_yrp_production_order_settings())
			grid_rows = [
				row
				for row in settings.production_order_attributes
				if row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE
			]
			self.assertEqual(len(grid_rows), 1)
			self.assertEqual(grid_rows[0].is_grid_attribute, 1)
			self.assertEqual(
				[row.attribute for row in settings.production_order_attributes],
				["Colour", PRODUCTION_ORDER_GRID_ATTRIBUTE],
			)
			self.assertEqual(
				settings.po_dependent_attribute,
				PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
			)
			self.assertEqual(
				settings.po_dependent_attribute_value,
				PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
			)

			self.assertFalse(ensure_yrp_production_order_settings())
			save.assert_called_once_with(ignore_permissions=True)
