from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning import lot_workspace, web_workspace


class TestPlanningWebCapabilities(TestCase):
	def setUp(self):
		self.sources = {}
		for alias in (
			"cutting_capabilities", "sewing_workspace", "finishing_workspace",
			"sales_workspace", "fabric_store_workspace",
		):
			patcher = patch.object(getattr(web_workspace, alias), "get_capabilities")
			self.sources[alias] = patcher.start()
			self.addCleanup(patcher.stop)
			self.sources[alias].return_value = {"sections": {}}
		patcher = patch.object(web_workspace.cutting_reports, "get_report_permissions", return_value={})
		self.report_permissions = patcher.start()
		self.addCleanup(patcher.stop)
		patcher = patch.object(
			web_workspace, "permission_flags", return_value={"can_read": False, "can_write": False},
		)
		self.lot_permissions = patcher.start()
		self.addCleanup(patcher.stop)

	def test_all_sources_readable(self):
		self.sources["cutting_capabilities"].return_value = {
			"cutting-plans": {"can_read": True, "can_create": True},
		}
		for alias in ("sewing_workspace", "finishing_workspace"):
			self.sources[alias].return_value = {
				"sections": {"plans": {"can_read": True}, "reports": {"can_read": True}},
			}
		self.sources["sales_workspace"].return_value = {
			"sections": {"production_orders": {"label": "Production Orders", "can_read": True}},
		}
		self.sources["fabric_store_workspace"].return_value = {
			"sections": {"work_orders": {"label": "Work Orders", "can_read": True}},
		}
		self.report_permissions.return_value = {
			"cutting-plans": True, "daily-production": False, "stock-balance": True,
		}
		self.lot_permissions.return_value = {"can_read": True, "can_write": False}
		sections = web_workspace.get_capabilities()["sections"]
		self.assertEqual(set(sections), {
			"cutting_plans", "sewing_plans", "finishing_plans", "lots",
			"production_orders", "work_orders", "reports",
		})
		self.assertEqual(sections["reports"]["groups"], {
			"cutting": True, "sewing": True, "finishing": True,
		})
		self.assertEqual(sections["lots"], {"label": "Lot", "can_read": True, "can_write": False})
		for source in self.sources.values():
			source.assert_called_once_with()
		self.report_permissions.assert_called_once_with()
		self.lot_permissions.assert_called_once_with("SD YRP Lot", ("read", "write"))

	def test_nothing_readable(self):
		self.sources["cutting_capabilities"].return_value = {"cutting-plans": {"can_read": False}}
		self.sources["sales_workspace"].return_value = {
			"sections": {"production_orders": {"can_read": False, "can_create": True}},
		}
		self.assertEqual(web_workspace.get_capabilities(), {"sections": {}})

	def test_cutting_plans_alone_does_not_grant_reports(self):
		self.report_permissions.return_value = {"cutting-plans": True, "daily-production": False}
		self.assertNotIn("reports", web_workspace.get_capabilities()["sections"])


class TestPlanningLotWrappers(TestCase):
	def test_empty_names_cannot_create_lots(self):
		with patch.object(lot_workspace.lot_editor, "get_lot_form") as get_form, patch.object(
			lot_workspace.lot_editor, "save_lot",
		) as save:
			for name in ("", "  ", None):
				with self.subTest(name=name):
					with self.assertRaises(frappe.PermissionError):
						lot_workspace.get_lot_form(name)
					with self.assertRaises(frappe.PermissionError):
						lot_workspace.save_lot({}, name)
			get_form.assert_not_called()
			save.assert_not_called()

	def test_omitted_names_cannot_create_lots(self):
		with patch.object(lot_workspace.lot_editor, "get_lot_form") as get_form, patch.object(
			lot_workspace.lot_editor, "save_lot",
		) as save:
			with self.assertRaises(frappe.PermissionError):
				lot_workspace.get_lot_form()
			with self.assertRaises(frappe.PermissionError):
				lot_workspace.save_lot({})
			get_form.assert_not_called()
			save.assert_not_called()

	def test_workspace_delegates(self):
		with patch.object(lot_workspace.purchase_lot_workspace, "get_lot_workspace", return_value={"name": "LOT-1"}) as source:
			self.assertEqual(lot_workspace.get_lot_workspace("LOT-1"), {"name": "LOT-1"})
			source.assert_called_once_with("LOT-1")

	def test_save_delegates_with_modified_timestamp(self):
		values = {"status": "Open"}
		with patch.object(lot_workspace.lot_editor, "save_lot", return_value={"name": "LOT-1"}) as source:
			self.assertEqual(lot_workspace.save_lot(values, "LOT-1", "ts"), {"name": "LOT-1"})
			source.assert_called_once_with(values, "LOT-1", "ts")

	def test_other_wrappers_delegate(self):
		cases = (
			(lot_workspace.lot_documents, "get_lot_documents", ("LOT-1",)),
			(lot_workspace.lot_documents, "get_lot_document", ("LOT-1", "YRP Work Order", "WO-1")),
			(lot_workspace.lot_editor, "get_lot_form", ("LOT-1",)),
			(lot_workspace.lot_editor, "get_lot_production_detail_context", ("IPD-1", "ITEM-1", "PPO-1")),
			(lot_workspace.lot_editor, "get_lot_production_order_item", ("PPO-1",)),
		)
		for module, method, arguments in cases:
			with self.subTest(method=method), patch.object(module, method, return_value={"ok": True}) as source:
				self.assertEqual(getattr(lot_workspace, method)(*arguments), {"ok": True})
				source.assert_called_once_with(*arguments)
