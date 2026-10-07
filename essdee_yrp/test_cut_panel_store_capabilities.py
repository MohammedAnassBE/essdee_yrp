from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.cut_panel_store.web_workspace import get_capabilities


class TestCutPanelStoreCapabilities(TestCase):
	def test_capabilities_expose_exact_six_sections_when_permitted(self):
		with patch(
			"essdee_yrp.cut_panel_store.web_workspace.frappe.has_permission",
			return_value=True,
		):
			payload = get_capabilities()

		self.assertEqual(
			set(payload["sections"]),
			{
				"movements",
				"work_orders",
				"cut_bundle_edits",
				"box_stickers",
				"excel_stickers",
				"reports",
			},
		)
		self.assertNotIn("raw_stickers", payload["sections"])
		self.assertNotIn("SD YRP Raw Sticker Print", str(payload))

	def test_capabilities_omit_unreadable_sections(self):
		readable = {
			"SD YRP Cut Panel Movement",
			"SD YRP Cut Bundle Edit",
			"YRP Stock Ledger Entry",
		}

		def has_permission(doctype, ptype="read", **_kwargs):
			return doctype in readable and ptype in {"read", "report"}

		with patch(
			"essdee_yrp.cut_panel_store.web_workspace.frappe.has_permission",
			side_effect=has_permission,
		):
			payload = get_capabilities()

		self.assertEqual(
			set(payload["sections"]),
			{"movements", "cut_bundle_edits", "reports"},
		)
		self.assertTrue(payload["sections"]["movements"]["can_read"])
		self.assertFalse(payload["sections"]["movements"]["can_create"])

	def test_report_capability_requires_report_permission(self):
		def has_permission(doctype, ptype="read", **_kwargs):
			return ptype == "read" and doctype in {
				"YRP Stock Ledger Entry",
				"SD YRP Cut Bundle Movement Ledger",
			}

		with patch(
			"essdee_yrp.cut_panel_store.web_workspace.frappe.has_permission",
			side_effect=has_permission,
		):
			payload = get_capabilities()

		self.assertNotIn("reports", payload["sections"])
