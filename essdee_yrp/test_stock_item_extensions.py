from unittest.mock import patch

from frappe.tests import UnitTestCase
from yrp.stock.save_stock_items import (
	PARENT_CHILD_MAP,
	_get_entry_fields,
	ungroup_items_from_ui,
)

from essdee_yrp.stock_item_extensions import get_entry_fields


class TestStockItemExtensions(UnitTestCase):
	def test_fabric_fields_are_contributed_only_to_work_order_rows(self):
		expected = (
			"fabric_reference_variant",
			"fabric_reference_allocations",
		)
		self.assertEqual(get_entry_fields("Work Order Deliverables"), expected)
		self.assertEqual(get_entry_fields("Work Order Receivables"), expected)
		self.assertEqual(get_entry_fields("Stock Entry"), ("set_combination",))
		self.assertNotIn("fabric_reference_variant", get_entry_fields("Stock Entry"))
		self.assertNotIn("fabric_reference_allocations", get_entry_fields("Stock Entry"))

	def test_yrp_loads_essdee_fields_through_the_hook(self):
		fields = _get_entry_fields(
			"Work Order Deliverables",
			PARENT_CHILD_MAP["Work Order Deliverables"],
		)
		self.assertIn("fabric_reference_variant", fields)
		self.assertIn("fabric_reference_allocations", fields)

	def test_fabric_fields_survive_ungrouping(self):
		item_details = [
			{
				"items": [
					{
						"name": "Test Cloth",
						"attributes": {},
						"dimensions": {},
						"default_uom": "Nos",
						"fabric_reference_variant": "Test Cloth-Grey",
						"fabric_reference_allocations": '[{"qty": 1}]',
						"values": {"default": {"qty": 1}},
					}
				]
			}
		]
		with patch(
			"yrp.stock.save_stock_items._resolve_or_create_variant",
			return_value="Test Cloth-Grey",
		):
			rows = ungroup_items_from_ui(item_details, "Work Order Deliverables")

		self.assertEqual(rows[0]["fabric_reference_variant"], "Test Cloth-Grey")
		self.assertEqual(rows[0]["fabric_reference_allocations"], '[{"qty": 1}]')
