from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.merch_pd import web_workspace

MERCH_PURCHASE = {
	"sections": {
		"lots": {"label": "Lot", "can_read": True},
		"item_production_details": {"label": "Item Production Detail", "can_read": True},
		"purchase_orders": {"label": "Purchase Orders", "can_read": True},
		"work_orders": {"label": "Work Order", "can_read": True},
		"reports": {"label": "Reports", "can_read": True},
	},
	"reports": {},
}
PD = {
	"sections": {
		"products": {"label": "Products", "can_read": True},
		"lotwise_item_profits": {"label": "Lotwise Item Profit", "can_read": False},
	},
}


class TestMerchPdWebWorkspace(TestCase):
	def get_capabilities(self, merch_purchase=MERCH_PURCHASE, pd=PD):
		with (
			patch.object(web_workspace.merch_purchase, "get_capabilities", return_value=merch_purchase),
			patch.object(web_workspace.product_development, "get_capabilities", return_value=pd),
		):
			return web_workspace.get_capabilities()

	def test_sections_are_the_four_merch_pd_cards(self):
		sections = self.get_capabilities()["sections"]
		self.assertEqual(list(sections), ["lots", "item_production_details", "purchase_orders", "lotwise_item_profits"])
		self.assertEqual(sections["lotwise_item_profits"], PD["sections"]["lotwise_item_profits"])

	def test_a_section_its_source_hides_stays_hidden(self):
		sections = {key: value for key, value in MERCH_PURCHASE["sections"].items() if key != "purchase_orders"}
		capabilities = self.get_capabilities(merch_purchase={"sections": sections})
		self.assertNotIn("purchase_orders", capabilities["sections"])

	def test_each_section_follows_its_doctype_permission(self):
		denied = {"Purchase Order", "SD YRP Lotwise Item Profit"}

		def has_permission(doctype, ptype="read", doc=None, *args, **kwargs):
			return doctype not in denied

		frappe.set_user("Administrator")
		with patch("frappe.has_permission", side_effect=has_permission):
			sections = web_workspace.get_capabilities()["sections"]
		self.assertNotIn("purchase_orders", sections)
		self.assertFalse(sections["lotwise_item_profits"]["can_read"])
		self.assertTrue(sections["lots"]["can_read"])
		self.assertTrue(sections["item_production_details"]["can_read"])
