import frappe
from erpnext.controllers.item_variant import create_variant
from frappe.tests import IntegrationTestCase

from essdee_yrp.patches.copy_template_flags_to_variants import add_variant_fields, sync_variant_flags

ATTRIBUTE = "_Test Variant Flag Size"
VALUES = ("S", "M")
FLAGS = ("disabled", "custom_deprecated")


def make_attribute():
	if not frappe.db.exists("Item Attribute", ATTRIBUTE):
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": ATTRIBUTE,
				"item_attribute_values": [{"attribute_value": value, "abbr": value} for value in VALUES],
			}
		).insert(ignore_permissions=True)


def make_item(**values):
	return frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": f"_Test Variant Flag {frappe.generate_hash(length=8)}",
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"gst_hsn_code": frappe.db.get_value("GST HSN Code", {}, "name"),
			**values,
		}
	).insert(ignore_permissions=True)


def get_flags(item_code):
	return frappe.db.get_value("Item", item_code, FLAGS, as_dict=True)


class TestVariantFlags(IntegrationTestCase):
	def setUp(self):
		make_attribute()
		add_variant_fields()
		self.template = make_item(has_variants=1, attributes=[{"attribute": ATTRIBUTE}])
		self.variants = [
			create_variant(self.template.name, {ATTRIBUTE: value}).insert(ignore_permissions=True).name
			for value in VALUES
		]

	def set_template_flags(self, value):
		self.template.reload()
		for flag in FLAGS:
			self.template.set(flag, value)
		self.template.save(ignore_permissions=True)

	def assert_variant_flags(self, value):
		for variant in self.variants:
			self.assertEqual(get_flags(variant), {flag: value for flag in FLAGS})

	def test_template_save_copies_flags_to_variants_and_back(self):
		self.set_template_flags(1)
		self.assert_variant_flags(1)

		self.set_template_flags(0)
		self.assert_variant_flags(0)

	def test_patch_syncs_mismatched_variants_only(self):
		other = make_item()
		frappe.db.set_value("Item", self.template.name, dict.fromkeys(FLAGS, 1))
		frappe.db.set_value("Item", other.name, dict.fromkeys(FLAGS, 0))

		sync_variant_flags()

		self.assert_variant_flags(1)
		self.assertEqual(get_flags(other.name), dict.fromkeys(FLAGS, 0))

	def test_add_variant_fields_is_idempotent(self):
		add_variant_fields()

		rows = frappe.get_all(
			"Variant Field",
			filters={"parent": "Item Variant Settings", "field_name": ["in", FLAGS]},
			pluck="field_name",
		)
		self.assertCountEqual(rows, FLAGS)
