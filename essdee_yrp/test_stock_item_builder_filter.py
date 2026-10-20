import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.link_search import link_search
from essdee_yrp.cutting.web_workspace import STOCK_ITEM_BUILDER_FILTERS


class TestStockItemBuilderFilter(IntegrationTestCase):
	def test_builder_search_includes_templates_and_plain_items_only(self):
		prefix = f"_Test Builder {frappe.generate_hash(length=8)}"
		attribute = frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": f"{prefix} Size",
				"item_attribute_values": [{"attribute_value": "Small", "abbr": "S"}],
			}
		).insert(ignore_permissions=True)
		template = self.make_item(
			f"{prefix} Template", has_variants=1, attributes=[{"attribute": attribute.name}]
		)
		variant = create_variant(template.name, {attribute.name: "Small"}).insert(ignore_permissions=True)
		plain = self.make_item(f"{prefix} Plain")
		disabled = self.make_item(
			f"{prefix} Disabled", has_variants=1, disabled=1, attributes=[{"attribute": attribute.name}]
		)

		rows = link_search("Item", prefix, filters=dict(STOCK_ITEM_BUILDER_FILTERS))
		names = {row["name"] for row in rows}
		self.assertIn(template.name, names)
		self.assertIn(plain.name, names)
		self.assertNotIn(variant.name, names)
		self.assertNotIn(disabled.name, names)

	def make_item(self, item_code, **values):
		return frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"name1": item_code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
				**values,
			}
		).insert(ignore_permissions=True)
