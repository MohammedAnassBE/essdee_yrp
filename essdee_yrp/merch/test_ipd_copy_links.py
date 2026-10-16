import frappe
from frappe.tests import UnitTestCase
from yrp.attribute_links import attribute_for

from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import SAMPLES


class TestIpdCopyLinks(UnitTestCase):
	"""Stitching combination rows share the set combination DocType but store stitching values."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("ipd_copy_links")
		self.addCleanup(lambda: frappe.db.rollback(save_point="ipd_copy_links"))
		self.source = frappe.get_doc(DOCTYPE, SAMPLES["set_item"])
		if not (self.source.is_set_item and self.source.stiching_item_combination_details):
			self.skipTest("A set item IPD with a stitching combination is required")

	def test_rows_resolve_their_own_table_attribute(self):
		stitched = self.source.stiching_item_combination_details[0]
		set_row = self.source.set_item_combination_details[0]
		field = "set_item_attribute_value"
		self.assertEqual(attribute_for(stitched, field, (self.source,)), self.source.stiching_attribute)
		self.assertEqual(attribute_for(set_row, field, (self.source,)), self.source.set_item_attribute)

	def test_plain_copy_keeps_stitching_values_valid(self):
		copy = frappe.copy_doc(self.source)
		copy.approval_status = "Not Approved"
		copy.approved_by = None
		copy.set("item_bom", [])
		copy.insert()
		self.assertEqual(
			[row.set_item_attribute_value for row in copy.stiching_item_combination_details],
			[row.set_item_attribute_value for row in self.source.stiching_item_combination_details],
		)
