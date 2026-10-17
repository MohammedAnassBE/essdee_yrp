import frappe
from frappe.tests import UnitTestCase
from yrp.attribute_values import get_mapping_document

from essdee_yrp.ipd_validations import ensure_ipd_owned_mappings, is_mapping_shared
from essdee_yrp.merch.ipd.fields import DOCTYPE

MAPPING = "YRP Item Item Attribute Mapping"


class TestIpdOwnedMappings(UnitTestCase):
	"""Use existing records and savepoints, avoiding IntegrationTestCase's setup commit."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("ipd_owned_mappings")
		self.addCleanup(lambda: frappe.db.rollback(save_point="ipd_owned_mappings"))
		for name in frappe.get_all(DOCTYPE, filters={"is_cloth_item": 0}, pluck="name"):
			doc = frappe.get_doc(DOCTYPE, name)
			item = frappe.get_doc("Item", doc.item)
			item_mappings = {row.attribute: row.mapping for row in item.attributes if row.mapping}
			row = next((row for row in doc.item_attributes if row.attribute in item_mappings), None)
			if row:
				self.doc = doc
				self.row = row
				self.item_mapping = item_mappings[row.attribute]
				break
		else:
			self.skipTest("An existing garment IPD with an Item attribute mapping is required")

	def test_item_variant_mapping_gets_an_owned_copy(self):
		self.row.mapping = self.item_mapping
		original_values = mapping_values(self.item_mapping)
		self.assertTrue(
			frappe.db.exists("Item Variant Attribute", {"mapping": self.item_mapping, "parenttype": "Item"})
		)
		self.assertTrue(is_mapping_shared(MAPPING, self.row.mapping, self.doc.name))
		ensure_ipd_owned_mappings(self.doc)
		self.assertNotEqual(self.row.mapping, self.item_mapping)
		self.assertTrue(frappe.db.exists(MAPPING, self.row.mapping))
		self.assertEqual(mapping_values(self.row.mapping), original_values)
		self.assertFalse(is_mapping_shared(MAPPING, self.row.mapping, self.doc.name))
		self.assertEqual(mapping_values(self.item_mapping), original_values)

	def test_on_trash_guard_skips_item_mapping(self):
		self.row.mapping = self.item_mapping
		# Match on_trash's guard without deleting any real document.
		deletable = [
			row.mapping
			for row in self.doc.item_attributes
			if row.mapping and not is_mapping_shared(MAPPING, row.mapping, self.doc.name)
		]
		self.assertNotIn(self.item_mapping, deletable)
		self.assertTrue(frappe.db.exists(MAPPING, self.item_mapping))


def mapping_values(name):
	return [row.attribute_value for row in get_mapping_document(name).get("values")]
