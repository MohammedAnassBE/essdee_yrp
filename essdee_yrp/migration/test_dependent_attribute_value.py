import unittest

from essdee_yrp.migration.live import _apply_contextual_defaults


class DependentAttributeMigrationTest(unittest.TestCase):
	def test_import_derives_value_from_source_template(self):
		doc = {"doctype": "Item", "name": "Vest-6", "variant_of": "Vest", "attributes": [{"attribute": "Stage", "attribute_value": "Pack", "display_name": ""}]}
		schema = {"fields": [{"fieldname": "dependent_attribute_value", "fieldtype": "Data"}]}
		refs = {"item_dependent_attributes": {"Vest": "Stage"}}
		_apply_contextual_defaults(doc, schema, refs)
		self.assertEqual(doc["dependent_attribute_value"], "Pack")
		# Shared by dry-run, bulk write and verification; deterministic on repeats.
		_apply_contextual_defaults(doc, schema, refs)
		self.assertEqual(doc["dependent_attribute_value"], "Pack")
		doc["attributes"] = []
		_apply_contextual_defaults(doc, schema, refs)
		self.assertIsNone(doc["dependent_attribute_value"])

	def test_mapping_link_conversion_is_scoped_and_repeatable(self):
		from yrp.attribute_value_identity import attribute_value_name
		doc={'doctype':'YRP Item Item Attribute Mapping','attribute_name':'Size','values':[{'attribute_value':'XL'}]}
		refs={'attribute_value_pairs':{'XL':['Size','Label']},'source_attribute_value_attributes':{'XL':'Size'}}
		schema={'fields':[]}
		_apply_contextual_defaults(doc,schema,refs)
		self.assertEqual(doc['values'][0]['attribute_value'],attribute_value_name('Size','XL'))
		_apply_contextual_defaults(doc,schema,refs)
		self.assertEqual(doc['values'][0]['attribute_value'],attribute_value_name('Size','XL'))

	def test_orphan_mapping_uses_source_identity_not_ambiguous_label(self):
		from yrp.attribute_value_identity import attribute_value_name
		doc={'doctype':'YRP Item Item Attribute Mapping Value','attribute_value':'Front'}
		refs={'attribute_value_pairs':{'Front':['Panel','Type']},'source_attribute_value_attributes':{'Front':'Panel'}}
		_apply_contextual_defaults(doc,{'fields':[]},refs)
		self.assertEqual(doc['attribute_value'],attribute_value_name('Panel','Front'))
