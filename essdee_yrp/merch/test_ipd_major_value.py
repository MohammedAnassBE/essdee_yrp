import frappe
from frappe.tests import UnitTestCase
from yrp.attribute_links import value as attribute_value

from essdee_yrp.merch.ipd.draft import build_draft
from essdee_yrp.merch.ipd.fields import DOCTYPE


class TestIpdStitchingMajorValue(UnitTestCase):
	"""A plain panel label from /web must resolve to its scoped value before Link validation."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("ipd_major_value")
		self.addCleanup(lambda: frappe.db.rollback(save_point="ipd_major_value"))
		rows = frappe.get_all(
			DOCTYPE,
			filters={
				"is_cloth_item": 0,
				"stiching_attribute": ["is", "set"],
				"stiching_major_attribute_value": ["is", "set"],
			},
			fields=["name", "stiching_attribute", "stiching_major_attribute_value"],
			limit=1,
		)
		if not rows:
			self.skipTest("A garment IPD with a stitching major value is required")
		self.row = rows[0]
		self.label = attribute_value(self.row.stiching_major_attribute_value)

	def validated(self, values):
		doc = build_draft(self.row.name, values)
		doc._action = "save"
		doc._validate_links()
		return doc

	def test_label_resolves_after_value_was_cleared(self):
		frappe.db.set_value(
			DOCTYPE, self.row.name, "stiching_major_attribute_value", None, update_modified=False
		)
		doc = self.validated({"stiching_major_attribute_value": self.label})
		self.assertEqual(doc.stiching_major_attribute_value, self.row.stiching_major_attribute_value)

	def test_label_outside_the_stitching_attribute_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.validated({"stiching_major_attribute_value": "ZZ Not A Panel Value"})
