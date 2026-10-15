"""Replicated Item role regression tests."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.item_roles import VARIANT_INHERITED_FIELDS
from essdee_yrp.migration.live import _prepare_item_migration_documents
from essdee_yrp.migration.transformers import item_variant_to_standard_item
from essdee_yrp.sd_yrp_sync import map_source_item_variant


class TestSyncItemRoles(IntegrationTestCase):
	def tearDown(self):
		try:
			super().tearDown()
		finally:
			frappe.db.rollback()

	def map_variant(self, name, has_variants, attributes, **values):
		parent = frappe._dict(name="Parent", has_variants=has_variants)
		parent.update({field: f"value-{field}" for field in VARIANT_INHERITED_FIELDS})
		parent.update(stock_uom="Kg", is_stock_item=1, disabled=1, description="Parent description")
		document = SimpleNamespace(name="Parent", get=parent.get, as_dict=lambda: dict(parent))
		with (
			patch(
				"frappe.get_all",
				side_effect=lambda *args, **kwargs: ["Parent"] if kwargs.get("pluck") else [parent],
			),
			patch("frappe.get_cached_doc", return_value=document),
		):
			data = {
				"name": name,
				"item": "PARENT",
				"attributes": attributes,
				"item_tuple_attribute": "tuple",
				**values,
			}
			mapped = map_source_item_variant(data)
			migrated = _prepare_item_migration_documents(
				"Item Variant",
				[{**item_variant_to_standard_item(data, None, None), "_source_item_parent": data["item"]}],
			)[0]
		return mapped, migrated

	def test_empty_self_variant_preserves_template(self):
		mapped, migrated = self.map_variant("PARENT", 1, [])
		self.assertEqual(mapped, {"doctype": "Item", "name": "Parent", "item_tuple_attribute": "tuple"})
		self.assertNotIn("has_variants", migrated)
		self.assertNotIn("attributes", migrated)

	def test_plain_parent_and_empty_variants_are_standalone(self):
		for has_variants, attributes in (
			(0, [{"attribute": "Size", "attribute_value": "7 Inch"}]),
			(0, []),
			(1, []),
		):
			with self.subTest(has_variants=has_variants, attributes=attributes):
				mapped, migrated = self.map_variant("Variant", has_variants, attributes)
				for result in (mapped, migrated):
					self.assertIsNone(result["variant_of"])
					self.assertEqual(result["attributes"], [])
					self.assertEqual(result["has_variants"], 0)
					self.assertEqual(result["item_tuple_attribute"], "tuple")
					self.assertEqual(result["is_stock_item"], 1)
					self.assertEqual(result["disabled"], 1)
					self.assertEqual(result["description"], "Parent description")

	def test_template_variant_inheritance_matches_migration(self):
		mapped, migrated = self.map_variant(
			"Variant", 1, [{"attribute": "Size", "attribute_value": "7 Inch"}]
		)
		self.assertEqual(mapped["variant_of"], "Parent")
		self.assertEqual(migrated["variant_of"], "Parent")
		for field in VARIANT_INHERITED_FIELDS:
			self.assertEqual(mapped[field], migrated[field])

	def test_template_merge_upsert_updates_only_tuple_data(self):
		from essdee_yrp.sd_yrp_sync import upsert_item

		payload = {"doctype": "Item", "name": "Parent", "item_tuple_attribute": "tuple"}
		with (
			patch("essdee_yrp.sd_yrp_sync.map_source_item_variant", return_value=payload),
			patch("frappe.db.exists", return_value=True),
			patch("essdee_yrp.sd_yrp_sync.upsert_filtered_doc") as upsert,
		):
			upsert_item({"name": "PARENT"}, source_doctype="Item Variant")
		upsert.assert_called_once_with(payload)
		self.assertEqual(set(payload), {"doctype", "name", "item_tuple_attribute"})

	def test_null_and_empty_values_inherit_but_explicit_values_survive(self):
		mapped, migrated = self.map_variant(
			"Variant",
			1,
			[{"attribute": "Size", "attribute_value": "One"}],
			item_group=None,
			stock_uom="",
			description="Source description",
			is_stock_item=0,
		)
		for result in (mapped, migrated):
			self.assertEqual(result["item_group"], "value-item_group")
			self.assertEqual(result["stock_uom"], "Kg")
			self.assertEqual(result["description"], "Source description")
			self.assertEqual(result["is_stock_item"], 0)

	def test_variant_parent_uom_overrides_explicit_source_uom(self):
		mapped, migrated = self.map_variant(
			"Variant", 1, [{"attribute": "Size", "attribute_value": "One"}], stock_uom="Nos"
		)
		for result in (mapped, migrated):
			self.assertEqual(result["stock_uom"], "Kg")

	def test_repeated_null_group_sync_preserves_existing_group(self):
		from essdee_yrp.sd_yrp_sync import upsert_item

		name = f"_Test Null Group {frappe.generate_hash(length=10)}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"name": name,
				"item_code": name,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
			}
		).db_insert()
		payload = {"name": name, "item_group": None, "stock_uom": "Nos"}
		for _ in range(2):
			upsert_item(payload)
			self.assertEqual(frappe.db.get_value("Item", name, "item_group"), "All Item Groups")
