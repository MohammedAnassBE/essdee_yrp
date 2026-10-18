from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as cp
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot as lot


class TestWebReadReuse(TestCase):
	def test_cloth_identity_does_not_load_item_children(self):
		row = frappe._dict(accessory=0, cloth_item_variant="Variant", colour="Blue", dia="20", weight=2)
		with patch.object(frappe.db, "get_value", return_value=frappe._dict(name="Variant", variant_of="Parent")), patch.object(frappe, "get_doc", side_effect=AssertionError("unused Item children")), patch.object(cp, "_attribute_value", side_effect=lambda value: value):
			self.assertEqual(cp.fetch_cloth_details([row])[0]["item"], "Parent")

	def test_missing_cloth_keeps_original_document_error(self):
		with patch.object(frappe.db, "get_value", return_value=None), patch.object(frappe, "get_doc", side_effect=frappe.DoesNotExistError("missing")):
			with self.assertRaises(frappe.DoesNotExistError):
				cp.fetch_cloth_details([frappe._dict(cloth_item_variant="missing")])

	def test_recut_builder_reuses_permission_checked_plan(self):
		doc = frappe._dict(name="CP")
		with patch.object(frappe, "has_permission", return_value=True) as permission, patch.object(frappe, "get_all", return_value=[]) as rows, patch.object(frappe, "get_doc", side_effect=AssertionError("duplicate CP read")):
			self.assertEqual(cp._get_recut_print_panel_details(doc, "Recut"), {})
			permission.assert_called_once_with("SD YRP Recut and Print Panel", "read", throw=True)
			self.assertEqual(rows.call_args.kwargs["filters"]["cutting_plan"], "CP")

	def test_ocr_lazy_reads_preserve_values_with_fewer_child_queries(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("SD YRP Lot", "C1225-03"):
			self.skipTest("Live Lot fixture missing")
		def measure():
			queries = []
			original = frappe.db.sql
			def sql(*args, **kwargs):
				queries.append(args[0])
				return original(*args, **kwargs)
			with patch.object(frappe.db, "sql", side_effect=sql):
				result = lot.get_ocr_details("C1225-03")
			return result, len(queries)
		with patch.object(frappe, "get_lazy_doc", side_effect=frappe.get_doc):
			expected, eager_count = measure()
		actual, lazy_count = measure()
		self.assertEqual(actual, expected)
		self.assertLess(lazy_count, eager_count * 0.75)

	def test_four_order_stages_share_one_structural_pass(self):
		frappe.set_user("Administrator")
		doc = frappe.get_doc("SD YRP Lot", "C1225-03")
		ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
		fields = ("quantity", "cut_qty", "stich_qty", "pack_qty")
		expected = {key: lot.build_order_item_details(doc.lot_order_details, ipd, key) for key in fields}
		with patch.object(lot, "get_item_attribute_details", wraps=lot.get_item_attribute_details) as attributes:
			actual = lot.build_order_item_stages(doc.lot_order_details, ipd, fields)
			self.assertEqual(actual, expected)
			self.assertEqual(attributes.call_count, len({r.row_index for r in doc.lot_order_details}))

	def test_dispatch_reads_only_used_finishing_children(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch.sd_yrp_finishing_plan_dispatch import fetch_fp_items

		frappe.set_user("Administrator")
		def measure():
			with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as query:
				result = fetch_fp_items()
				return result, query.call_count
		with patch.object(frappe, "get_lazy_doc", side_effect=frappe.get_doc):
			expected, eager = measure()
		actual, lazy = measure()
		self.assertEqual(actual, expected)
		self.assertLess(lazy, eager * 0.8)
