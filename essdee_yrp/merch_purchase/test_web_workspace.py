from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.merch_purchase import web_workspace

MERCH = {
	"sections": {
		"lots": {"label": "Lot", "can_read": True, "can_create": True},
		"production_orders": {"label": "Production Order", "can_read": True, "can_create": False},
		"work_orders": {"label": "Work Order", "can_read": False, "can_create": False},
		"reports": {"label": "Reports", "can_read": True, "can_create": False},
	},
	"reports": {"work_in_progress": {"label": "Work In Progress", "can_read": True}, "grn_report": {"label": "GRN Report", "can_read": True}},
}
PURCHASE = {
	"sections": {
		"lots": {"label": "Lots", "can_read": True, "can_create": True, "can_write": True, "workflow_states": []},
		"items": {"label": "Items", "can_read": True, "can_create": False, "can_write": False, "workflow_states": []},
	},
}
STORE = {
	"sections": {
		"work_orders": {"label": "Work Orders", "can_read": True},
		"purchase_orders": {"label": "Purchase Orders", "can_read": True, "can_create": True},
		"stock_transfers": {"label": "Stock Transfers", "operations": {"stock_entry": {"can_read": True}}},
		"reports": {"label": "Reports", "reports": {"stock_balance": {"label": "Stock Balance", "can_read": True}, "grn_report": {"label": "GRN Report", "can_read": True}}},
	},
}
CUT_PANEL = {
	"sections": {
		"box_stickers": {"label": "Box Sticker Print", "can_read": True},
		"excel_stickers": {"label": "Excel Sticker Print", "can_read": True, "can_create": True},
		"movements": {"can_read": True},
	}
}


def _patched(merch=MERCH, purchase=PURCHASE, store=STORE, cut_panel=CUT_PANEL):
	return (
		patch.object(web_workspace.merch, "get_capabilities", return_value=merch),
		patch.object(web_workspace.purchase, "get_capabilities", return_value=purchase),
		patch.object(web_workspace.fabric_store, "get_capabilities", return_value=store),
		patch.object(web_workspace.cut_panel_store, "get_capabilities", return_value=cut_panel),
	)


class TestMerchPurchaseWebWorkspace(TestCase):
	def get_capabilities(self, **sources):
		merch, purchase, store, cut_panel = _patched(**sources)
		with merch, purchase, store, cut_panel:
			return web_workspace.get_capabilities()

	def test_sections_are_the_union_of_merch_and_purchase_once_each(self):
		sections = self.get_capabilities()["sections"]
		self.assertEqual(
			list(sections),
			["lots", "production_orders", "work_orders", "items", "purchase_orders", "stock_transfers", "box_stickers", "excel_stickers", "reports"],
		)
		self.assertEqual(sections["excel_stickers"], CUT_PANEL["sections"]["excel_stickers"])
		self.assertEqual(sections["lots"], {
			"label": "Lot", "can_read": True, "can_create": True, "can_write": True, "workflow_states": [],
		})
		self.assertEqual(sections["work_orders"], MERCH["sections"]["work_orders"], "Merch owns Work Orders; the store copy is not used")
		self.assertTrue(sections["stock_transfers"]["can_read"])
		self.assertNotIn("movements", sections)

	def test_reports_combine_both_departments_without_duplicates(self):
		capabilities = self.get_capabilities()
		self.assertEqual(sorted(capabilities["reports"]), ["grn_report", "stock_balance", "work_in_progress"])
		self.assertEqual(capabilities["sections"]["reports"], {"label": "Reports", "can_read": True, "can_create": False})

	def test_reports_card_closes_when_no_report_is_readable(self):
		merch = {**MERCH, "reports": {"work_in_progress": {"label": "Work In Progress", "can_read": False}}}
		store = {"sections": {"purchase_orders": STORE["sections"]["purchase_orders"]}}
		capabilities = self.get_capabilities(merch=merch, store=store, cut_panel={"sections": {}})
		self.assertFalse(capabilities["sections"]["reports"]["can_read"])
		self.assertNotIn("stock_transfers", capabilities["sections"])
		self.assertNotIn("box_stickers", capabilities["sections"])
		self.assertNotIn("excel_stickers", capabilities["sections"])

	def test_each_section_follows_its_doctype_permission(self):
		denied = {"Purchase Order", "SD YRP Lot", "YRP Excel Sticker Print"}

		def has_permission(doctype, ptype="read", doc=None, *args, **kwargs):
			return doctype not in denied

		frappe.set_user("Administrator")
		with patch("frappe.has_permission", side_effect=has_permission):
			sections = web_workspace.get_capabilities()["sections"]
		self.assertNotIn("purchase_orders", sections)
		self.assertNotIn("excel_stickers", sections)
		self.assertTrue(sections["box_stickers"]["can_read"])
		self.assertFalse(sections["lots"]["can_read"])
		self.assertNotIn("can_write", sections["lots"], "Purchase hides an unreadable Lot section")
		self.assertTrue(sections["items"]["can_read"])
		self.assertTrue(sections["production_orders"]["can_read"])
