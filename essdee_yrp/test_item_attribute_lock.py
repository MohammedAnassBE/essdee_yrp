"""Template attribute set locking regressions."""

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.item_validations import validate


class TestItemAttributeLock(IntegrationTestCase):
	def tearDown(self):
		try:
			super().tearDown()
		finally:
			frappe.db.rollback()

	def setUp(self):
		super().setUp()
		self.attribute_names = [f"_Test Attr Lock {frappe.generate_hash(length=10)}" for _ in range(3)]
		for name in self.attribute_names:
			frappe.get_doc(
				{
					"doctype": "Item Attribute",
					"name": name,
					"attribute_name": name,
				}
			).db_insert()
		self.template = self.make_item("Template", has_variants=1)
		self.template.append("attributes", {"attribute": self.attribute_names[0]})
		self.template.append("attributes", {"attribute": self.attribute_names[1]})
		for row in self.template.attributes:
			row.db_insert()
		self.variant = self.make_item("Variant", variant_of=self.template.name)
		for name in self.attribute_names[:2]:
			self.variant.append("attributes", {"attribute": name, "attribute_value": "One"}).db_insert()
		self.template._doc_before_save = frappe.get_doc("Item", self.template.name)

	def make_item(self, suffix, **values):
		name = f"_Test Attr Lock {suffix} {frappe.generate_hash(length=10)}"
		document = frappe.get_doc(
			{
				"doctype": "Item",
				"name": name,
				"item_code": name,
				"item_name": name,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				**values,
			}
		)
		document.db_insert()
		document.set("__islocal", 0)
		return document

	def assert_locked(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			validate(self.template)
		self.assertIn(
			f"Cannot add or remove attributes on Item <strong>{self.template.name}</strong>",
			str(raised.exception),
		)
		self.assertIn("it has 1 variant(s). Delete or migrate the variants first.", str(raised.exception))

	def test_adding_attribute_with_variant_is_blocked(self):
		self.template.flags.skip_cloth_yarn_ratio_validation = True
		self.template.flags.skip_variant_attribute_lock = True
		self.template.append("attributes", {"attribute": self.attribute_names[2]})
		self.assert_locked()

	def test_removing_attribute_with_variant_is_blocked(self):
		self.template.set("attributes", self.template.attributes[:1])
		self.assert_locked()

	def test_attribute_changes_without_variants_are_allowed(self):
		frappe.db.delete("Item Variant Attribute", {"parent": self.variant.name, "parenttype": "Item"})
		frappe.db.delete("Item", {"name": self.variant.name})
		self.template.set("attributes", [])
		validate(self.template)

	def test_reordering_attributes_with_variants_is_allowed(self):
		self.template.set("attributes", list(reversed(self.template.attributes)))
		validate(self.template)
