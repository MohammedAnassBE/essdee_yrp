from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.api.item_filter import get_item_filter_values


class TestItemFilterValues(TestCase):
	def test_expands_templates_and_keeps_plain_and_disabled_items(self):
		with (
			patch("essdee_yrp.api.item_filter.frappe.has_permission") as permission,
			patch(
				"essdee_yrp.api.item_filter.frappe.get_list",
				return_value=[
					frappe._dict(name="VARIANT", variant_of="TEMPLATE"),
					frappe._dict(name="DISABLED-VARIANT", variant_of="TEMPLATE"),
				],
			) as get_list,
		):
			result = get_item_filter_values('["TEMPLATE", "PLAIN", "TEMPLATE"]')
		self.assertEqual(
			result, {"TEMPLATE": ["TEMPLATE", "VARIANT", "DISABLED-VARIANT"], "PLAIN": ["PLAIN"]}
		)
		permission.assert_called_once_with("Item", "read", throw=True)
		get_list.assert_called_once_with(
			"Item",
			filters={"variant_of": ["in", ["TEMPLATE", "PLAIN"]]},
			fields=["name", "variant_of"],
			limit_page_length=0,
		)

	def test_requires_item_read_permission_before_query(self):
		with (
			patch("essdee_yrp.api.item_filter.frappe.has_permission", side_effect=frappe.PermissionError),
			patch("essdee_yrp.api.item_filter.frappe.get_list") as get_list,
			self.assertRaises(frappe.PermissionError),
		):
			get_item_filter_values(["TEMPLATE"])
		get_list.assert_not_called()

	def test_empty_items_do_not_query(self):
		with (
			patch("essdee_yrp.api.item_filter.frappe.has_permission"),
			patch("essdee_yrp.api.item_filter.frappe.get_list") as get_list,
		):
			self.assertEqual(get_item_filter_values([]), {})
		get_list.assert_not_called()
