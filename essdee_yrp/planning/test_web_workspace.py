from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.planning import web_workspace


class TestPlanningReportsSection(TestCase):
	def production(self, multi_ccr, ppo):
		with (
			patch.object(web_workspace, "can_run_desk_report", return_value=False),
			patch.object(web_workspace.cutting_reports, "get_report_permissions", return_value={"multi-ccr": multi_ccr}),
			patch("essdee_yrp.planning.reports.production_quantities.can_read", return_value=False),
			patch.object(web_workspace.frappe, "has_permission", side_effect=lambda doctype, ptype: doctype == "YRP Production Order" and ppo),
		):
			return web_workspace._reports_section({}, {})["production"]

	def test_multi_ccr_and_ppo_follow_source_access(self):
		self.assertEqual(self.production(True, True), {
			"multi_ccr": {"label": "Multi CCR", "can_read": True},
			"ppo_report": {"label": "PPO Report", "can_read": True, "can_export": True},
		})
		self.assertEqual(self.production(False, False), {})


class TestPlanningBoxStickerSection(TestCase):
	def sections(self, granted):
		empty = {"sections": {}}
		with (
			patch.object(web_workspace.sewing_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.finishing_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.sales_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.fabric_store_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.cutting_capabilities, "get_capabilities", return_value={}),
			patch.object(web_workspace, "_reports_section", return_value={"can_read": False}),
			patch.object(
				web_workspace.frappe, "has_permission",
				side_effect=lambda doctype, ptype, doc=None: doctype == "SD YRP Box Sticker Print" and ptype in granted,
			),
		):
			return web_workspace.get_capabilities()["sections"]

	def test_box_sticker_card_follows_box_sticker_print_read(self):
		self.assertEqual(self.sections({"read", "create"}), {"box_stickers": {
			"label": "Box Sticker Print", "can_read": True, "can_create": True, "can_write": False, "can_submit": False,
		}})
		self.assertEqual(self.sections({"create"}), {})


class TestPlanningStockTransfersSection(TestCase):
	def sections(self, store_sections):
		empty = {"sections": {}}
		with (
			patch.object(web_workspace.sewing_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.finishing_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.sales_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.fabric_store_workspace, "get_capabilities", return_value={"sections": store_sections}),
			patch.object(web_workspace.cutting_capabilities, "get_capabilities", return_value={}),
			patch.object(web_workspace, "_reports_section", return_value={"can_read": False}),
			patch.object(web_workspace.frappe, "has_permission", return_value=False),
		):
			return web_workspace.get_capabilities()["sections"]

	def test_stock_transfers_card_follows_fabric_store_operations(self):
		operations = {"stock_update": {"doctype": "YRP Stock Update", "can_read": True}}
		self.assertEqual(self.sections({"stock_transfers": {"label": "Stock Transfers", "operations": operations}}), {
			"stock_transfers": {"can_read": True, "label": "Stock Transfers", "operations": operations},
		})
		self.assertEqual(self.sections({}), {})


class TestPlanningReworkAndPurchaseOrderSections(TestCase):
	def sections(self, finishing_sections, store_sections):
		empty = {"sections": {}}
		with (
			patch.object(web_workspace.sewing_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.finishing_workspace, "get_capabilities", return_value={"sections": finishing_sections}),
			patch.object(web_workspace.sales_workspace, "get_capabilities", return_value=empty),
			patch.object(web_workspace.fabric_store_workspace, "get_capabilities", return_value={"sections": store_sections}),
			patch.object(web_workspace.cutting_capabilities, "get_capabilities", return_value={}),
			patch.object(web_workspace, "_reports_section", return_value={"can_read": False}),
			patch.object(web_workspace.frappe, "has_permission", return_value=False),
		):
			return web_workspace.get_capabilities()["sections"]

	def test_cards_follow_finishing_rework_and_store_purchase_order_read(self):
		rework = {"label": "Rework Details", "can_read": True, "can_write": False}
		purchase_orders = {"label": "Purchase Orders", "can_read": True, "can_create": False}
		self.assertEqual(
			self.sections({"rework_details": rework}, {"purchase_orders": purchase_orders}),
			{"rework_details": rework, "purchase_orders": purchase_orders},
		)
		self.assertEqual(self.sections({}, {}), {})
