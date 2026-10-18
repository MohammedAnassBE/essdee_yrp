from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.cutting import reports
from essdee_yrp.finishing import report_sources
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_bundle_edit import sd_yrp_cut_bundle_edit as bundle


class TestWebHotspotReads(TestCase):
	def test_category_batch_keeps_input_order_duplicates_and_blank_fallback(self):
		rows = [frappe._dict(name=str(i), item=item) for i, item in enumerate(("B", "A", "B", "missing", None))]
		with patch.object(frappe, "get_all", return_value=[frappe._dict(name="A", product_category="other"), frappe._dict(name="B", product_category="target")]) as query, patch.object(frappe.db, "get_value", return_value="target") as fallback:
			self.assertEqual(reports._lots_in_category(rows, "target"), [rows[0], rows[2], rows[4]])
			self.assertEqual(query.call_count, 1)
			fallback.assert_called_once_with("Item", None, "product_category")

	def test_bundle_choices_use_selected_headers_without_reloading_each_ledger(self):
		rows = [frappe._dict(name="CB1", size="M", colour="Blue", panel="Front", set_combination="{}"), frappe._dict(name="CB2", size="S", colour="Red", panel="Back", set_combination="{}")]
		ipd = frappe._dict(stiching_item_details=[frappe._dict(stiching_attribute_value="Front")], is_set_item=0)
		with patch.object(bundle, "_require_manage_access"), patch.object(bundle, "get_combine_datetime", return_value="time"), patch.object(frappe.db, "sql", return_value=rows), patch.object(frappe, "get_value", return_value="IPD"), patch.object(frappe, "get_doc", side_effect=lambda dt, name: ipd if dt == "YRP Item Production Detail" else (_ for _ in ()).throw(AssertionError("redundant ledger load"))), patch.object(bundle, "_attribute_value", side_effect=lambda v: v):
			result = bundle.get_major_colours("2026-10-18", "10:00", "Warehouse", "Lot")
			self.assertEqual(result["sizes"], ["M", "S"])
			self.assertEqual(result["colours"], ["Blue", "Red"])

	def test_empty_ironing_skips_children_but_keeps_configuration_errors(self):
		with patch.object(report_sources, "require_read"), patch.object(report_sources, "ironing_filters", return_value={}), patch.object(frappe, "get_list", return_value=[]), patch.object(frappe, "get_all", side_effect=AssertionError("unused orphan children")), patch.object(frappe, "get_cached_doc", side_effect=ValueError("missing configuration")):
			with self.assertRaisesRegex(ValueError, "missing configuration"):
				report_sources.get_ironing_dpr("2026-10-18")

	def test_multiccr_rpc_keeps_public_permission_guard_and_private_helper(self):
		self.assertIn(reports.get_multiccr, frappe.whitelisted)
		self.assertNotIn(reports._lots_in_category, frappe.whitelisted)
