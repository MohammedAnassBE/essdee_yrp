from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import add_days, getdate, nowdate
from yrp.attribute_value_identity import attribute_value_name
from yrp.attribute_values import ensure_value_master, get_mapping_values
from yrp.yrp.doctype.yrp_item.yrp_item import (
	ensure_global_attribute_values,
	get_or_create_variant,
)


class TestPurchaseItemEditor(TestCase):
	@classmethod
	def setUpClass(cls):
		from essdee_yrp.patches.grant_purchase_item_master_permissions import execute

		frappe.set_user("Administrator")
		cls.savepoint = "purchase_item_editor_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(cls.savepoint)
		execute()
		cls.suffix = frappe.generate_hash(length=8)
		cls.item_group = cls._make_item_group(False)
		cls.group_node = cls._make_item_group(True)
		cls.uom = cls._make_uom(f"Web Item Unit {cls.suffix}")
		cls.secondary_uom = cls._make_uom(f"Web Secondary Unit {cls.suffix}", secondary_only=True)
		cls.colour = cls._make_attribute("Colour", ["Red", "Blue", "Green"])
		cls.size = cls._make_attribute("Size", ["Small", "Medium"])
		cls.accent = cls._make_attribute("Accent", ["Red"])
		cls.length = cls._make_numeric_attribute("Length")
		cls.stage = cls._make_attribute("Stage", ["Cut", "Pack", "Loose"])
		cls.box_uom = cls._make_uom(f"Web Box Unit {cls.suffix}")
		cls.brand = cls._make_brand(f"WebBrand{cls.suffix}")
		cls.multi_word_brand = cls._make_brand(f"Web Brand {cls.suffix}")
		cls.supplier = cls._make_supplier()
		cls.tax = cls._tax_slab()
		cls.fixture_users = {
			"purchase_manager": cls._make_user(
				"purchase-manager", ["Purchase Manager", "Purchase User"]
			),
			"item_manager": cls._make_user("item-manager", ["Item Manager"]),
			"purchase_user": cls._make_user("purchase-user", ["Purchase User"]),
		}
		for doctype in (
			"Item",
			"Item Attribute",
			"YRP Item Attribute Value",
			"YRP Item Item Attribute Mapping",
		):
			frappe.clear_cache(doctype=doctype)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		for user in cls.fixture_users.values():
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
		frappe.db.rollback(save_point=cls.savepoint)
		for doctype in ("Item", "UOM", "SD YRP Product Category"):
			frappe.clear_cache(doctype=doctype)

	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.test_savepoint = "purchase_item_case_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(self.test_savepoint)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point=self.test_savepoint)
		frappe.set_user(self.previous_user)

	@classmethod
	def _make_user(cls, label, roles):
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"round2-{label}-{cls.suffix}@example.test",
				"first_name": f"Round 2 {label}",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _make_item_group(cls, is_group):
		return frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": f"_Test Web {'Group' if is_group else 'Leaf'} {cls.suffix}",
				"parent_item_group": "All Item Groups",
				"is_group": int(is_group),
			}
		).insert(ignore_permissions=True).name

	@staticmethod
	def _make_uom(name, secondary_only=False):
		doc = frappe.get_doc({"doctype": "UOM", "uom_name": name, "enabled": 1})
		if doc.meta.has_field("secondary_only"):
			doc.secondary_only = int(secondary_only)
		return doc.insert(ignore_permissions=True).name

	@classmethod
	def _make_attribute(cls, label, values):
		name = f"_Test Web {label} {cls.suffix}"
		frappe.get_doc({"doctype": "Item Attribute", "attribute_name": name}).insert(
			ignore_permissions=True
		)
		ensure_global_attribute_values(name, values, check_permission=False)
		return name

	@classmethod
	def _make_numeric_attribute(cls, label):
		name = f"_Test Web {label} {cls.suffix}"
		frappe.get_doc(
			{
				"doctype": "Item Attribute",
				"attribute_name": name,
				"numeric_values": 1,
				"from_range": 1,
				"to_range": 10,
				"increment": 0.5,
			}
		).insert(ignore_permissions=True)
		ensure_global_attribute_values(name, ["1"], check_permission=False)
		return name

	@staticmethod
	def _make_brand(name):
		return frappe.get_doc({"doctype": "Brand", "brand": name}).insert(
			ignore_permissions=True
		).name

	@classmethod
	def _make_supplier(cls):
		return frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": f"_Test Web Supplier {cls.suffix}",
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True).name

	@classmethod
	def _tax_slab(cls):
		if name := frappe.db.get_value("YRP Tax Slab", {"enabled": 1}, "name"):
			return name
		return frappe.get_doc(
			{
				"doctype": "YRP Tax Slab",
				"percentage": int(cls.suffix[:6], 16) / 10**8,
				"enabled": 1,
			}
		).insert(ignore_permissions=True).name

	def _attribute_row(self, attribute, *values):
		return {
			"attribute": attribute,
			"values": [
				{"name": attribute_value_name(attribute, value), "label": value}
				for value in values
			],
		}

	def _values(self, label=None, **overrides):
		values = {
			"name": label or f"_Test Web Item {frappe.generate_hash(length=8)}",
			"brand": None,
			"item_group": self.item_group,
			"stock_uom": self.uom,
			"gst_hsn_code": None,
			"description": "Created from the purchase web editor",
			"disabled": 0,
			"attributes": [],
			"primary_attribute": None,
		}
		values.update(overrides)
		return values

	def _create_as(self, role_key, values=None):
		from essdee_yrp.purchase.item_editor import create_item

		frappe.set_user(self.fixture_users[role_key])
		return create_item(values or self._values())

	def test_plain_item_create_has_no_variants_or_mappings(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		result = self._create_as("purchase_manager")
		doc = frappe.get_doc("Item", result["name"])

		self.assertEqual((doc.item_code, doc.item_name), (result["name"], result["name"]))
		self.assertEqual((doc.has_variants, doc.is_purchase_item, doc.is_stock_item), (0, 1, 1))
		self.assertEqual(doc.is_sales_item, 0)
		self.assertEqual(doc.country_of_origin, frappe.db.get_default("country"))
		self.assertTrue(doc.item_hash_value)
		self.assertEqual(doc.get("attributes"), [])
		self.assertEqual(get_or_create_variant(doc.name, {}), doc.name)
		payload = get_item_editor(doc.name)
		self.assertFalse(payload["attributes_locked"])
		self.assertEqual(payload["variant_count"], 0)

	def test_item_attribute_counts_return_visible_child_row_counts(self):
		from essdee_yrp.purchase.item_editor import get_item_attribute_counts

		plain = self._create_as("item_manager")["name"]
		template = self._create_as(
			"item_manager",
			self._values(
				attributes=[
					self._attribute_row(self.colour, "Red"),
					self._attribute_row(self.size, "Small"),
				]
			),
		)["name"]
		frappe.set_user(self.fixture_users["purchase_manager"])

		self.assertEqual(
			get_item_attribute_counts([plain, template]),
			{plain: 0, template: 2},
		)

	def test_create_item_takes_pricing_mutex_before_inserting(self):
		from essdee_yrp.purchase import item_editor

		frappe.set_user(self.fixture_users["item_manager"])
		with patch.object(item_editor, "lock_pricing_policy") as lock_policy:
			item_editor.create_item(self._values())
		lock_policy.assert_called_once_with()

	def test_template_create_fills_private_mappings_without_creating_variants(self):
		values = self._values(
			attributes=[
				self._attribute_row(self.colour, "Red", "Blue"),
				self._attribute_row(self.size, "Small", "Medium"),
			],
			primary_attribute=self.colour,
		)
		result = self._create_as("item_manager", values)
		doc = frappe.get_doc("Item", result["name"])

		self.assertEqual(doc.has_variants, 1)
		self.assertEqual(doc.variant_based_on, "Item Attribute")
		self.assertEqual(doc.primary_attribute, self.colour)
		self.assertEqual(frappe.db.count("Item", {"variant_of": doc.name}), 0)
		self.assertEqual(
			[get_mapping_values(row.mapping) for row in doc.attributes],
			[["Red", "Blue"], ["Small", "Medium"]],
		)
		variant = get_or_create_variant(doc.name, {self.colour: "Red", self.size: "Small"})
		self.assertEqual(frappe.db.get_value("Item", variant, "variant_of"), doc.name)

	def test_template_create_accepts_attributes_without_values(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		values = self._values(
			attributes=[
				{"attribute": self.colour, "values": []},
				{"attribute": self.size, "values": []},
			],
			primary_attribute=self.colour,
		)
		result = self._create_as("purchase_manager", values)
		doc = frappe.get_doc("Item", result["name"])

		self.assertEqual(doc.has_variants, 1)
		self.assertEqual([row.attribute for row in doc.attributes], [self.colour, self.size])
		self.assertTrue(all(row.mapping for row in doc.attributes))
		self.assertEqual([get_mapping_values(row.mapping) for row in doc.attributes], [[], []])
		payload = get_item_editor(doc.name)
		rows = payload["values"]["attributes"]
		self.assertEqual([row["all_values_allowed"] for row in rows], [True, True])
		self.assertEqual([row["values"] for row in rows], [[], []])
		self.assertEqual([row["value_count"] for row in rows], [3, 2])
		self.assertNotIn("attributes", payload["options"])

	def test_update_keeps_an_unrestricted_mapping_when_values_stay_empty(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[{"attribute": self.colour, "values": []}]),
		)
		doc = frappe.get_doc("Item", created["name"])
		payload = update_item(
			doc.name,
			self._values(
				doc.item_name,
				item_group=doc.item_group,
				stock_uom=doc.stock_uom,
				description="Renamed description",
				attributes=[{"attribute": self.colour, "values": []}],
			),
			doc.modified,
		)

		self.assertTrue(payload["values"]["attributes"][0]["all_values_allowed"])
		self.assertEqual(get_mapping_values(doc.attributes[0].mapping), [])

	def test_update_adds_an_attribute_without_values(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		mapping_modified = frappe.db.get_value(
			"YRP Item Item Attribute Mapping", doc.attributes[0].mapping, "modified"
		)
		payload = update_item(
			doc.name,
			self._values(
				doc.item_name,
				item_group=doc.item_group,
				stock_uom=doc.stock_uom,
				attributes=[
					{**self._attribute_row(self.colour, "Red"), "mapping_modified": mapping_modified},
					{"attribute": self.size, "values": []},
				],
			),
			doc.modified,
		)

		rows = payload["values"]["attributes"]
		self.assertEqual([row["attribute"] for row in rows], [self.colour, self.size])
		self.assertEqual([row["all_values_allowed"] for row in rows], [False, True])

	def test_mapping_fill_failure_is_atomic_when_the_request_rolls_back(self):
		from essdee_yrp.purchase import item_editor

		item_name = f"_Test Web Atomic Item {frappe.generate_hash(length=8)}"
		values = self._values(
			item_name,
			attributes=[
				self._attribute_row(self.colour, "Red"),
				self._attribute_row(self.size, "Small"),
			],
		)
		mapping_count = frappe.db.count("YRP Item Item Attribute Mapping")
		request_savepoint = "item_create_request_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(request_savepoint)
		original_fill_mapping = item_editor._fill_mapping
		call_count = 0

		def fail_second_mapping(*args, **kwargs):
			nonlocal call_count
			call_count += 1
			if call_count == 2:
				raise RuntimeError("forced mapping fill failure")
			return original_fill_mapping(*args, **kwargs)

		frappe.set_user(self.fixture_users["item_manager"])
		with (
			patch.object(item_editor, "_fill_mapping", side_effect=fail_second_mapping),
			self.assertRaisesRegex(RuntimeError, "forced mapping fill failure"),
		):
			item_editor.create_item(values)
		frappe.db.rollback(save_point=request_savepoint)

		self.assertFalse(frappe.db.exists("Item", item_name))
		self.assertEqual(frappe.db.count("YRP Item Item Attribute Mapping"), mapping_count)

	def test_legacy_brand_naming_uses_only_the_first_word(self):
		cases = (
			("Fabric", self.brand, f"{self.brand} Fabric"),
			(f"{self.brand} Fabric", self.brand, f"{self.brand} Fabric"),
			("Fabric", None, "Fabric"),
			(
				f"{self.multi_word_brand.split()[0]} Fabric",
				self.multi_word_brand,
				f"{self.multi_word_brand} {self.multi_word_brand.split()[0]} Fabric",
			),
		)
		for raw_name, brand, expected_prefix in cases:
			with self.subTest(raw_name=raw_name, brand=brand):
				unique_name = f"{raw_name} {frappe.generate_hash(length=6)}"
				result = self._create_as(
					"purchase_manager", self._values(unique_name, brand=brand)
				)
				self.assertEqual(result["name"], expected_prefix + unique_name[len(raw_name) :])

	def test_create_rejects_invalid_structure_and_duplicate_code(self):
		from essdee_yrp.purchase.item_editor import create_item

		created = self._create_as("purchase_manager")
		invalid_cases = (
			(self._values(created["name"]), "already exists"),
			(self._values(item_group=self.group_node), "leaf Item Group"),
			(self._values(stock_uom=self.secondary_uom), "Secondary UOM"),
			(
				self._values(
					attributes=[self._attribute_row(self.colour, "Red")],
					primary_attribute=self.size,
				),
				"Primary Attribute",
			),
			(
				self._values(
					attributes=[
						{
							"attribute": self.colour,
							"values": [
								{
									"name": attribute_value_name(self.accent, "Red"),
									"label": "Red",
								}
							],
						}
					],
				),
				"belongs to",
			),
		)
		frappe.set_user(self.fixture_users["purchase_manager"])
		for values, message in invalid_cases:
			with self.subTest(message=message), self.assertRaisesRegex(frappe.ValidationError, message):
				create_item(values)

	def test_existing_values_need_no_item_attribute_write_but_new_values_do(self):
		from essdee_yrp.purchase.item_editor import create_item, get_item_editor

		frappe.set_user(self.fixture_users["purchase_manager"])
		self.assertFalse(frappe.has_permission("Item Attribute", "write"))
		self.assertFalse(get_item_editor()["permissions"]["can_write_item_attribute"])
		created = create_item(
			self._values(attributes=[self._attribute_row(self.colour, "Red")])
		)
		self.assertTrue(frappe.db.exists("Item", created["name"]))

		new_label = f"New Colour {frappe.generate_hash(length=6)}"
		with self.assertRaises(frappe.PermissionError):
			create_item(
				self._values(
					attributes=[
						{
							"attribute": self.colour,
							"values": [{"name": None, "label": new_label}],
						}
					]
				)
			)
		frappe.set_user(self.fixture_users["item_manager"])
		self.assertTrue(get_item_editor()["permissions"]["can_write_item_attribute"])

	def test_purchase_manager_can_use_existing_numeric_projection(self):
		from essdee_yrp.purchase import item_editor

		frappe.set_user("Administrator")
		unrestricted = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_Test Numeric All Values {frappe.generate_hash(length=8)}",
				"item_name": f"_Test Numeric All Values {frappe.generate_hash(length=8)}",
				"item_group": self.item_group,
				"stock_uom": self.uom,
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"is_sales_item": 0,
				"has_variants": 1,
				"variant_based_on": "Item Attribute",
				"attributes": [{"attribute": self.length}],
			}
		).insert(ignore_permissions=True)
		unrestricted_mapping = frappe.get_doc(
			"YRP Item Item Attribute Mapping", unrestricted.attributes[0].mapping
		)
		self.assertEqual(get_mapping_values(unrestricted_mapping.name), [])

		frappe.set_user(self.fixture_users["purchase_manager"])
		self.assertFalse(frappe.has_permission("Item Attribute", "write"))
		self.assertIn(
			{"name": attribute_value_name(self.length, "1"), "label": "1"},
			item_editor.search_attribute_values(self.length, "1"),
		)
		with patch.object(
			item_editor,
			"ensure_global_attribute_values",
			side_effect=AssertionError("existing numeric projection was treated as new"),
		):
			created = item_editor.create_item(
				self._values(attributes=[self._attribute_row(self.length, "1")])
			)
			doc = frappe.get_doc("Item", created["name"])
			mapping = frappe.get_doc(
				"YRP Item Item Attribute Mapping", doc.attributes[0].mapping
			)
			payload = item_editor.update_item(
				doc.name,
				self._values(
					doc.item_name,
					item_group=doc.item_group,
					stock_uom=doc.stock_uom,
					description="Numeric projection retained",
					attributes=[
						{
							**self._attribute_row(self.length, "1"),
							"mapping_modified": mapping.modified,
						}
					],
				),
				doc.modified,
			)
			unrestricted_payload = item_editor.get_item_editor(unrestricted.name)
			unrestricted_values = unrestricted_payload["values"]["attributes"][0]
			self.assertTrue(unrestricted_values["all_values_allowed"])
			self.assertEqual(unrestricted_values["values"], [])
			self.assertEqual(unrestricted_values["value_count"], 1)
			item_editor.update_item(
				unrestricted.name,
				self._values(
					unrestricted.item_name,
					item_group=unrestricted.item_group,
					stock_uom=unrestricted.stock_uom,
					description="Unrestricted numeric mapping retained",
					attributes=[unrestricted_values],
				),
				unrestricted.modified,
			)

		self.assertEqual(payload["values"]["description"], "Numeric projection retained")
		self.assertEqual(get_mapping_values(mapping.name), ["1"])
		self.assertEqual(get_mapping_values(unrestricted_mapping.name), [])

	def test_role_permissions_allow_managers_and_reject_purchase_user(self):
		from essdee_yrp.purchase.item_editor import (
			create_item,
			search_attribute_values,
			update_item,
		)

		manager_item = self._create_as(
			"purchase_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		self.assertTrue(manager_item["name"])
		frappe.set_user(self.fixture_users["purchase_manager"])
		self.assertIn(
			{"name": attribute_value_name(self.colour, "Red"), "label": "Red"},
			search_attribute_values(self.colour, "red"),
		)

		item_manager_item = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.size, "Small")]),
		)
		self.assertTrue(item_manager_item["name"])

		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaises(frappe.PermissionError):
			create_item(self._values())
		doc = frappe.get_doc("Item", manager_item["name"])
		with self.assertRaises(frappe.PermissionError):
			update_item(
				doc.name,
				self._values(
					doc.item_name,
					item_group=doc.item_group,
					stock_uom=doc.stock_uom,
					attributes=[self._attribute_row(self.colour, "Red")],
				),
				doc.modified,
			)

	def test_update_requires_fresh_item_and_mapping_tokens(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", doc.attributes[0].mapping)
		values = self._values(
			doc.item_name,
			item_group=doc.item_group,
			stock_uom=doc.stock_uom,
			attributes=[
				{
					**self._attribute_row(self.colour, "Red", "Blue"),
					"mapping_modified": mapping.modified,
				}
			],
		)

		frappe.set_user(self.fixture_users["item_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "Reload"):
			update_item(doc.name, values, None)
		with self.assertRaises(frappe.TimestampMismatchError):
			update_item(doc.name, values, "2000-01-01 00:00:00")
		values["attributes"][0]["mapping_modified"] = "2000-01-01 00:00:00"
		with self.assertRaises(frappe.TimestampMismatchError):
			update_item(doc.name, values, doc.modified)

	def test_update_ignores_fields_outside_the_item_edit_allowlist(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as("purchase_manager")
		doc = frappe.get_doc("Item", created["name"])
		values = self._values(
			doc.item_name,
			item_group=doc.item_group,
			stock_uom=self.secondary_uom,
			item_code="FORGED-ITEM-CODE",
			is_stock_item=0,
			is_purchase_item=0,
			is_sales_item=1,
			has_variants=1,
		)
		frappe.set_user(self.fixture_users["purchase_manager"])
		payload = update_item(doc.name, values, doc.modified)
		doc.reload()

		self.assertTrue(payload["fields"]["stock_uom"]["read_only"])
		self.assertEqual(doc.stock_uom, self.uom)
		self.assertEqual(doc.item_code, created["name"])
		self.assertEqual((doc.is_stock_item, doc.is_purchase_item, doc.is_sales_item), (1, 1, 0))
		self.assertEqual(doc.has_variants, 0)

	def test_update_preserves_metadata_on_retained_attribute_rows(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.length, "1")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		row = doc.attributes[0]
		row.numeric_values = 1
		row.from_range = 1
		row.to_range = 10
		row.increment = 0.5
		doc.save(ignore_permissions=True)
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", row.mapping)

		frappe.set_user(self.fixture_users["item_manager"])
		update_item(
			doc.name,
			self._values(
				doc.item_name,
				item_group=doc.item_group,
				stock_uom=doc.stock_uom,
				description="Metadata-preserving edit",
				attributes=[
					{
						**self._attribute_row(self.length, "1"),
						"mapping_modified": mapping.modified,
					}
				],
			),
			doc.modified,
		)
		doc.reload()
		row = doc.attributes[0]
		self.assertEqual(
			(row.numeric_values, row.from_range, row.to_range, row.increment),
			(1, 1, 10, 0.5),
		)

	def test_update_appends_values_before_and_after_variants_exist(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", doc.attributes[0].mapping)
		values = self._values(
			doc.item_name,
			item_group=doc.item_group,
			stock_uom=doc.stock_uom,
			attributes=[
				{
					**self._attribute_row(self.colour, "Red", "Blue"),
					"mapping_modified": mapping.modified,
				}
			],
		)
		frappe.set_user(self.fixture_users["item_manager"])
		update_item(doc.name, values, doc.modified)
		self.assertEqual(get_mapping_values(mapping.name), ["Red", "Blue"])

		get_or_create_variant(doc.name, {self.colour: "Red"})
		payload = get_item_editor(doc.name)
		self.assertTrue(payload["attributes_locked"])
		self.assertEqual(payload["variant_count"], 1)
		self.assertIn("Values can still", payload["attribute_lock_message"])
		self.assertFalse(payload["primary_attribute_locked"])
		self.assertFalse(payload["dependent_attribute_locked"])
		values["attributes"][0]["values"].append(
			{"name": attribute_value_name(self.colour, "Green"), "label": "Green"}
		)
		values["attributes"][0]["mapping_modified"] = frappe.db.get_value(
			"YRP Item Item Attribute Mapping", mapping.name, "modified"
		)
		doc.reload()
		update_item(doc.name, values, doc.modified)
		self.assertEqual(get_mapping_values(mapping.name), ["Red", "Blue", "Green"])

	def _desk_copy_item(self, item):
		frappe.set_user("Administrator")
		doc = frappe.copy_doc(frappe.get_doc("Item", item))
		doc.item_code = doc.item_name = f"ZZ TEST Desk Edit {frappe.generate_hash(length=8)}"
		doc.item_hash_value = None
		return doc.insert()

	def test_web_mapping_edits_match_desk_with_and_without_variants(self):
		for with_variants in (False, True):
			for labels in (
				["Red", "Blue", "Green"],
				["Blue"],
				["Red"],
				[],
				["Blue", "Red"],
			):
				with self.subTest(with_variants=with_variants, labels=labels):
					item = self._create_as(
						"item_manager",
						self._values(
							attributes=[self._attribute_row(self.colour, "Red", "Blue")],
						),
					)["name"]
					desk = self._desk_copy_item(item)
					variants = []
					if with_variants:
						for name in (item, desk.name):
							variants.append(get_or_create_variant(name, {self.colour: "Red"}))
					before_variants = {
						variant: frappe.get_doc("Item", variant).as_dict() for variant in variants
					}
					before_items = {
						name: frappe.get_doc("Item", name).as_dict() for name in (item, desk.name)
					}
					mapping = frappe.get_doc("YRP Item Item Attribute Mapping", desk.attributes[0].mapping)
					mapping.set(
						"values",
						[{"attribute_value": ensure_value_master(self.colour, label)} for label in labels],
					)
					mapping.save()
					self._update_colour_values(item, labels)
					self.assertEqual(get_mapping_values(mapping.name), labels)
					self.assertEqual(
						get_mapping_values(frappe.get_doc("Item", item).attributes[0].mapping), labels
					)
					self.assertEqual(self._parity_snapshot(item), self._parity_snapshot(desk.name))
					for variant, before in before_variants.items():
						self.assertEqual(frappe.get_doc("Item", variant).as_dict(), before)
					for name, before in before_items.items():
						self.assertEqual(frappe.get_doc("Item", name).as_dict(), before)

	def test_variant_templates_lock_attribute_row_add_remove_reorder_and_swap(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		item = self._create_as(
			"item_manager",
			self._values(
				attributes=[
					self._attribute_row(self.colour, "Red"),
					self._attribute_row(self.size, "Small"),
				]
			),
		)["name"]
		get_or_create_variant(item, {self.colour: "Red", self.size: "Small"})
		payload = get_item_editor(item)
		rows = payload["values"]["attributes"]
		before = self._parity_snapshot(item)
		for attributes in (
			[*rows, self._attribute_row(self.accent, "Red")],
			rows[:1],
			[],
			list(reversed(rows)),
			[rows[0], self._attribute_row(self.accent, "Red")],
		):
			with self.subTest(attributes=[row["attribute"] for row in attributes]):
				with self.assertRaisesRegex(
					frappe.ValidationError, "[Aa]ttribute.*locked|[Ll]ocked.*variant"
				):
					update_item(item, {**payload["values"], "attributes": attributes}, payload["modified"])
				self.assertEqual(self._parity_snapshot(item), before)

	def test_dependent_picklist_only_edits_preserve_stage_configuration_and_variants(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes

		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		for labels, omit_details in (
			(["Pack"], False),
			(["Cut"], False),
			([], False),
			(["Cut", "Pack", "Loose"], False),
			(["Cut", "Pack", "Loose"], True),
		):
			with self.subTest(labels=labels, omit_details=omit_details):
				item = self._create_as("purchase_manager", self._dependent_values())["name"]
				desk = self._desk_copy_item(item)
				variants = {
					name: get_or_create_variant(name, {self.stage: "Cut", self.size: "Small"})
					for name in (item, desk.name)
				}
				before_variants = {
					variant: frappe.get_doc("Item", variant).as_dict() for variant in variants.values()
				}
				before_items = {name: frappe.get_doc("Item", name).as_dict() for name in variants}
				before_config = {
					name: frappe.get_doc(
						"YRP Item Dependent Attribute Mapping",
						before_items[name]["dependent_attribute_mapping"],
					).as_dict()
					for name in variants
				}
				mapping = frappe.get_doc("YRP Item Item Attribute Mapping", desk.attributes[0].mapping)
				mapping.set(
					"values",
					[{"attribute_value": ensure_value_master(self.stage, label)} for label in labels],
				)
				mapping.save()
				frappe.set_user(self.fixture_users["purchase_manager"])
				payload = get_item_editor(item)
				values = {
					**payload["values"],
					"attributes": [
						{**row, "values": labels if row["attribute"] == self.stage else row["values"]}
						for row in payload["values"]["attributes"]
					],
				}
				if omit_details:
					values.pop("dependent_details")
				update_item(item, values, payload["modified"])
				for name, variant in variants.items():
					doc = frappe.get_doc("Item", name)
					self.assertEqual(doc.as_dict(), before_items[name])
					self.assertEqual(get_mapping_values(doc.attributes[0].mapping), labels)
					self.assertEqual(
						frappe.get_doc(
							"YRP Item Dependent Attribute Mapping", doc.dependent_attribute_mapping
						).as_dict(),
						before_config[name],
					)
					for stage in ("Cut", "Pack"):
						self.assertEqual(
							build_variant_attributes({self.size: "Small"}, stage, doc),
							{self.stage: stage, self.size: "Small"},
						)
					self.assertEqual(
						get_or_create_variant(name, {self.stage: "Cut", self.size: "Small"}), variant
					)
					self.assertEqual(frappe.get_doc("Item", variant).as_dict(), before_variants[variant])
				self.assertEqual(self._parity_snapshot(item), self._parity_snapshot(desk.name))

	def test_dependent_picklist_addition_keeps_removed_stage_and_skips_parent_save(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		desk = self._desk_copy_item(item)
		variant = get_or_create_variant(item, {self.stage: "Cut", self.size: "Small"})
		before_item = frappe.get_doc("Item", item).as_dict()
		before_variant = frappe.get_doc("Item", variant).as_dict()
		for labels in (["Pack"], ["Pack", "Loose"]):
			payload = get_item_editor(item)
			details = payload["values"]["dependent_details"]
			if "Loose" in labels:
				details = [
					*details,
					{"value": "Loose", "uom": self.uom, "display_name": "Loose", "attributes": [self.size]},
				]
			self._update_dependent(
				item,
				attributes=[
					{**row, "values": labels if row["attribute"] == self.stage else row["values"]}
					for row in payload["values"]["attributes"]
				],
				dependent_details=details,
			)
			self.assertEqual(frappe.get_doc("Item", item).as_dict(), before_item)
			self.assertEqual(frappe.get_doc("Item", variant).as_dict(), before_variant)
		frappe.set_user("Administrator")
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", desk.attributes[0].mapping)
		mapping.set(
			"values",
			[{"attribute_value": ensure_value_master(self.stage, label)} for label in ("Pack", "Loose")],
		)
		mapping.save()
		update_dependent_attribute_details(
			desk.dependent_attribute_mapping,
			{
				"attr_list": {
					"Cut": {"uom": self.uom, "name": "", "attributes": [self.size]},
					"Pack": {"uom": self.uom, "name": "Packed", "attributes": [self.size]},
					"Loose": {"uom": self.uom, "name": "Loose", "attributes": [self.size]},
				}
			},
		)
		self.assertEqual(self._parity_snapshot(item), self._parity_snapshot(desk.name))
		self.assertEqual(self._dependent_rows(item), self._dependent_rows(desk.name))
		self.assertEqual(set(self._dependent_rows(item)), {"Cut", "Pack", "Loose"})

	def test_new_stage_configuration_is_validated_before_mapping_only_writes(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		payload = get_item_editor(item)
		before = self._parity_snapshot(item)
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Loose must use at least one attribute"):
			self._update_dependent(
				item,
				attributes=[
					{
						**row,
						"values": ["Cut", "Pack", "Loose"]
						if row["attribute"] == self.stage
						else row["values"],
					}
					for row in payload["values"]["attributes"]
				],
				dependent_details=[
					*payload["values"]["dependent_details"],
					{
						"value": "Loose",
						"uom": self.uom,
						"display_name": "Loose",
						"attributes": [],
					},
				],
			)
		self.assertEqual(self._parity_snapshot(item), before)

	def test_variant_items_are_not_exposed_or_updated(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		variant = get_or_create_variant(created["name"], {self.colour: "Red"})
		frappe.set_user(self.fixture_users["item_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "Variant items are not shown here"):
			get_item_editor(variant)
		variant_doc = frappe.get_doc("Item", variant)
		with self.assertRaisesRegex(frappe.ValidationError, "Variant items are not shown here"):
			update_item(variant, self._values(variant_doc.item_name), variant_doc.modified)

	def _make_colour_price(self, item, value):
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "YRP Item Price",
				"item_name": item,
				"supplier": self.supplier,
				"uom": self.uom,
				"from_date": add_days(nowdate(), 10),
				"tax": self.tax,
				"depends_on_attribute": 1,
				"attribute": self.colour,
				"item_price_values": [
					{
						"moq": 0,
						"price": 10,
						"lead_time": 1,
						"attribute_value": attribute_value_name(self.colour, value),
					}
				],
			}
		).insert(ignore_permissions=True)

	def _update_colour_values(self, item, values, mapping_modified=None):
		from essdee_yrp.purchase.item_editor import update_item

		doc = frappe.get_doc("Item", item)
		mapping = doc.attributes[0].mapping
		frappe.set_user(self.fixture_users["item_manager"])
		return update_item(
			doc.name,
			self._values(
				doc.item_name,
				item_group=doc.item_group,
				stock_uom=doc.stock_uom,
				attributes=[
					{
						"attribute": self.colour,
						"values": values,
						"mapping_modified": mapping_modified
						or frappe.db.get_value("YRP Item Item Attribute Mapping", mapping, "modified"),
					}
				],
			),
			doc.modified,
		)

	def test_price_referenced_value_cannot_be_dropped_but_mapping_can_allow_all(self):
		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red", "Blue")]),
		)
		mapping = frappe.db.get_value("Item Variant Attribute", {"parent": created["name"]}, "mapping")
		get_or_create_variant(created["name"], {self.colour: "Red"})
		self._make_colour_price(created["name"], "Blue")

		with self.assertRaisesRegex(frappe.ValidationError, "price tier"):
			self._update_colour_values(created["name"], ["Red"])
		payload = self._update_colour_values(created["name"], [])

		self.assertTrue(payload["values"]["attributes"][0]["all_values_allowed"])
		self.assertEqual(get_mapping_values(mapping), [])
		self.assertEqual(
			frappe.db.count("YRP Item Item Attribute Mapping Value", {"parent": mapping}), 0
		)

	def test_update_narrows_an_empty_mapping_and_changes_a_restricted_one(self):
		created = self._create_as(
			"item_manager",
			self._values(attributes=[{"attribute": self.colour, "values": []}]),
		)
		mapping = frappe.db.get_value("Item Variant Attribute", {"parent": created["name"]}, "mapping")

		payload = self._update_colour_values(created["name"], ["Blue", "Red"])
		self.assertEqual(get_mapping_values(mapping), ["Blue", "Red"])
		row = payload["values"]["attributes"][0]
		self.assertFalse(row["all_values_allowed"])
		self.assertEqual([value["label"] for value in row["values"]], ["Blue", "Red"])

		self._update_colour_values(created["name"], ["Green"])
		self.assertEqual(get_mapping_values(mapping), ["Green"])

	def test_narrowing_an_empty_mapping_checks_prices_and_mapping_token(self):
		created = self._create_as(
			"item_manager",
			self._values(attributes=[{"attribute": self.colour, "values": []}]),
		)
		mapping = frappe.db.get_value("Item Variant Attribute", {"parent": created["name"]}, "mapping")

		with self.assertRaises(frappe.TimestampMismatchError):
			self._update_colour_values(created["name"], ["Red"], "2000-01-01 00:00:00")
		self._make_colour_price(created["name"], "Blue")
		with self.assertRaisesRegex(frappe.ValidationError, "price tier"):
			self._update_colour_values(created["name"], ["Red"])
		self.assertEqual(get_mapping_values(mapping), [])

	def test_unreferenced_attribute_can_be_added_to_an_existing_template_with_a_price(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		colour_mapping = frappe.get_doc(
			"YRP Item Item Attribute Mapping", doc.attributes[0].mapping
		)
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "YRP Item Price",
				"item_name": doc.name,
				"supplier": self.supplier,
				"uom": self.uom,
				"from_date": add_days(nowdate(), 10),
				"tax": self.tax,
				"item_price_values": [{"moq": 0, "price": 10, "lead_time": 1}],
			}
		).insert(ignore_permissions=True)
		doc.reload()
		frappe.set_user(self.fixture_users["item_manager"])
		payload = update_item(
			doc.name,
			self._values(
				doc.item_name,
				item_group=doc.item_group,
				stock_uom=doc.stock_uom,
				attributes=[
					{
						**self._attribute_row(self.colour, "Red"),
						"mapping_modified": colour_mapping.modified,
					},
					self._attribute_row(self.size, "Small"),
				],
			),
			doc.modified,
		)

		self.assertEqual(
			[row["attribute"] for row in payload["values"]["attributes"]],
			[self.colour, self.size],
		)

	def test_item_prices_list_every_state_with_current_approved_first(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		created = self._create_as(
			"item_manager",
			self._values(
				attributes=[self._attribute_row(self.colour, "Red", "Blue")],
				primary_attribute=self.colour,
			),
		)
		item = created["name"]

		def make_price(*, from_date, to_date=None, state="Draft", docstatus=0, rows=None):
			frappe.set_user("Administrator")
			doc = frappe.get_doc(
				{
					"doctype": "YRP Item Price",
					"item_name": item,
					"supplier": self.supplier,
					"uom": self.uom,
					"from_date": from_date,
					"to_date": to_date,
					"tax": self.tax,
					"depends_on_attribute": 1,
					"attribute": self.colour,
					"item_price_values": rows
					or [
						{
							"moq": 0.5,
							"price": 12.345,
							"lead_time": 2,
							"attribute_value": attribute_value_name(self.colour, "Red"),
						}
					],
				}
			).insert(ignore_permissions=True)
			if (state, docstatus) != ("Draft", 0):
				frappe.db.set_value(
					"YRP Item Price",
					doc.name,
					{"workflow_state": state, "docstatus": docstatus},
					update_modified=False,
				)
			return doc.name

		active = make_price(
			from_date=add_days(nowdate(), -2),
			to_date=add_days(nowdate(), 2),
			state="Approved",
			docstatus=1,
			rows=[
				{
					"moq": 0.5,
					"price": 12.345,
					"lead_time": 2,
					"attribute_value": attribute_value_name(self.colour, "Red"),
				},
				{
					"moq": 5,
					"price": 10,
					"lead_time": 4,
					"attribute_value": attribute_value_name(self.colour, "Blue"),
				},
			],
		)
		future = make_price(
			from_date=add_days(nowdate(), 3), state="Approved", docstatus=1
		)
		expired = make_price(
			from_date=add_days(nowdate(), -10),
			to_date=add_days(nowdate(), -1),
			state="Approved",
			docstatus=1,
		)
		draft = make_price(from_date=nowdate())
		rejected = make_price(from_date=nowdate(), state="Rejected")

		frappe.set_user(self.fixture_users["purchase_manager"])
		prices = get_item_editor(item)["item_prices"]

		self.assertEqual(
			[price["name"] for price in prices], [active, future, draft, rejected, expired]
		)
		self.assertEqual(
			[price["is_current"] for price in prices], [True, False, False, False, False]
		)
		self.assertEqual(prices[3]["workflow_state"], "Rejected")
		price = prices[0]
		self.assertEqual(price["supplier"], self.supplier)
		self.assertEqual(
			(price["from_date"], price["to_date"]),
			(getdate(add_days(nowdate(), -2)), getdate(add_days(nowdate(), 2))),
		)
		self.assertEqual(price["attribute"], self.colour)
		self.assertEqual(
			[
				(
					tier["attribute_value_label"],
					tier["moq"],
					tier["price"],
					tier["lead_time"],
				)
				for tier in price["tiers"]
			],
			[("Red", 0.5, 12.345, 2), ("Blue", 5, 10, 4)],
		)

	def _dependent_values(self, **overrides):
		defaults = {
			"uoms": [{"uom": self.box_uom, "conversion_factor": 10}],
			"attributes": [
				self._attribute_row(self.stage, "Cut", "Pack"),
				self._attribute_row(self.size),
				self._attribute_row(self.colour),
			],
			"primary_attribute": self.size,
			"dependent_attribute": self.stage,
			"dependent_details": [
				{"value": "Pack", "uom": self.uom, "display_name": "Packed", "attributes": [self.size]},
			],
		}
		return self._values(**{**defaults, **overrides})

	def test_combined_edit_keeps_stage_removed_from_picklist(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		get_or_create_variant(item, {self.stage: "Cut", self.size: "Small"})
		stored = self._dependent_rows(item)
		payload = get_item_editor(item)
		attributes = [
			{
				**row,
				"values": ["Pack"] if row["attribute"] == self.stage else [v["label"] for v in row["values"]],
			}
			for row in payload["values"]["attributes"]
		]
		self._update_dependent(item, attributes=attributes, description="Combined edit")
		self.assertEqual(frappe.db.get_value("Item", item, "description"), "Combined edit")
		self.assertEqual(self._dependent_rows(item), stored)
		self._update_dependent(item, description="Later edit")
		self.assertEqual(self._dependent_rows(item), stored)

	def test_cleared_dependent_picklist_keeps_item_saveable(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		stored = self._dependent_rows(item)
		payload = get_item_editor(item)
		attributes = [
			{**row, "values": [] if row["attribute"] == self.stage else [v["label"] for v in row["values"]]}
			for row in payload["values"]["attributes"]
		]
		self._update_dependent(item, attributes=attributes)
		self._update_dependent(item, description="After clearing")
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Item", item)
		doc.description = "Desk save after clearing"
		doc.save()
		self.assertEqual(self._dependent_rows(item), stored)

	def _dependent_rows(self, item):
		from essdee_yrp.purchase.item_editor import get_item_editor

		return {
			row["value"]: (row["uom"], row["display_name"], sorted(row["attributes"]))
			for row in get_item_editor(item)["values"]["dependent_details"]
		}

	def _update_dependent(self, item, **overrides):
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		payload = get_item_editor(item)
		values = {**payload["values"], **overrides}
		values["attributes"] = overrides.get("attributes") or [
			{**row, "values": [value["label"] for value in row["values"]]}
			for row in payload["values"]["attributes"]
		]
		return update_item(item, values, payload["modified"])

	def test_create_with_dependent_attribute_builds_the_desk_combination(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		values = self._dependent_values(
			dependent_details=[
				{
					"value": "Pack",
					"uom": self.box_uom,
					"display_name": "Packed",
					"attributes": [self.size, self.colour],
				}
			]
		)
		item = self._create_as("purchase_manager", values)["name"]

		doc = frappe.get_doc("Item", item)
		self.assertEqual((doc.primary_attribute, doc.dependent_attribute), (self.size, self.stage))
		self.assertTrue(doc.dependent_attribute_mapping)
		self.assertEqual(
			self._dependent_rows(item),
			{
				"Cut": (self.uom, "", [self.size]),
				"Pack": (self.box_uom, "Packed", sorted([self.size, self.colour])),
			},
		)
		payload = get_item_editor(item)
		self.assertEqual(payload["fields"]["dependent_attribute"]["label"], "Dependent Attribute")
		self.assertEqual(payload["fields"]["primary_attribute"]["label"], "Primary Attribute")
		self.assertIn(self.length, payload["options"]["numeric_attributes"])

	def test_dependent_attribute_needs_values_on_create_but_existing_picklist_can_clear(self):
		values = self._dependent_values()
		values["attributes"][0] = self._attribute_row(self.stage)
		with self.assertRaisesRegex(frappe.ValidationError, "Please configure values for Dependent"):
			self._create_as("purchase_manager", values)

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		attributes = [
			self._attribute_row(self.stage),
			self._attribute_row(self.size),
			self._attribute_row(self.colour),
		]
		attributes[0]["mapping_modified"] = frappe.db.get_value(
			"YRP Item Item Attribute Mapping",
			frappe.get_doc("Item", item).attributes[0].mapping,
			"modified",
		)
		before = self._dependent_rows(item)
		self._update_dependent(item, attributes=attributes)
		self.assertEqual(get_mapping_values(frappe.get_doc("Item", item).attributes[0].mapping), [])
		self.assertEqual(self._dependent_rows(item), before)

	def test_stage_variant_name_collision_rejects_create_before_writes(self):
		for display_name in (None, "", " ", "Same"):
			with self.subTest(display_name=display_name):
				values = self._dependent_values(
					name=f"ZZ TEST Stage Collision {frappe.generate_hash(length=8)}",
					dependent_details=[
						{
							"value": stage,
							"uom": self.uom,
							"display_name": display_name,
							"attributes": [self.size],
						}
						for stage in ("Cut", "Pack")
					],
				)
				before = {doctype: frappe.db.count(doctype) for doctype in (
					"Item", "YRP Item Item Attribute Mapping", "YRP Item Dependent Attribute Mapping"
				)}
				with self.assertRaisesRegex(frappe.ValidationError, "Stages Cut and Pack would create variants with the same name"):
					self._create_as("purchase_manager", values)
				self.assertFalse(frappe.db.exists("Item", values["name"]))
				for doctype, count in before.items():
					self.assertEqual(frappe.db.count(doctype), count)
		with self.assertRaisesRegex(frappe.ValidationError, "same name"):
			self._create_as("purchase_manager", self._dependent_values(dependent_details=None))

	def test_stage_variant_name_collision_rejects_partial_update_before_writes(self):
		item = self._create_as("purchase_manager", self._dependent_values(
			name=f"ZZ TEST Stage Update {frappe.generate_hash(length=8)}"
		))["name"]
		before = self._parity_snapshot(item)
		with self.assertRaisesRegex(frappe.ValidationError, "Stages Cut and Pack would create variants with the same name"):
			self._update_dependent(
				item, description="ZZ TEST must not be stored",
				dependent_details=[{"value": "Cut", "uom": self.uom, "display_name": "Packed", "attributes": [self.size]}],
			)
		self.assertEqual(self._parity_snapshot(item), before)
		self.assertEqual(self._dependent_rows(item)["Cut"], (self.uom, "", [self.size]))

	def test_existing_stage_name_collision_loads_and_requires_fix_before_save(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values(
			name=f"ZZ TEST Existing Stage Collision {frappe.generate_hash(length=8)}"
		))["name"]
		frappe.set_user("Administrator")
		mapping = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		update_dependent_attribute_details(mapping, {"attr_list": {
			stage: {"uom": self.uom, "name": "", "attributes": [self.size]} for stage in ("Cut", "Pack")
		}})
		frappe.set_user(self.fixture_users["purchase_manager"])
		loaded = get_item_editor(item)
		self.assertEqual([row["display_name"] for row in loaded["values"]["dependent_details"]], ["", ""])
		before = self._parity_snapshot(item)
		with self.assertRaisesRegex(frappe.ValidationError, "same name"):
			self._update_dependent(item, description="ZZ TEST blocked until fixed")
		self.assertEqual(self._parity_snapshot(item), before)
		self._update_dependent(item, dependent_details=[
			{"value": "Cut", "uom": self.uom, "display_name": "Cut Panel", "attributes": [self.size]}
		])
		frappe.set_user("Administrator")
		self.assertEqual(get_or_create_variant(item, {self.stage: "Pack", self.size: "Small"}), f"{item}-Small")
		self.assertEqual(get_or_create_variant(item, {self.stage: "Cut", self.size: "Small"}), f"{item}-Cut Panel-Small")

	def test_dependent_rules_follow_desk_validation(self):
		values = self._dependent_values(primary_attribute=None)
		with self.assertRaisesRegex(frappe.ValidationError, "Please set Primary Attribute"):
			self._create_as("purchase_manager", values)
		values = self._dependent_values(primary_attribute=self.stage)
		with self.assertRaisesRegex(frappe.ValidationError, "same as the Primary Attribute"):
			self._create_as("purchase_manager", values)
		values = self._dependent_values(dependent_attribute=self.accent)
		with self.assertRaisesRegex(frappe.ValidationError, "standard Variant Attributes table"):
			self._create_as("purchase_manager", values)

	def test_update_keeps_stored_stages_and_adds_requested_new_stage(self):
		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		doc = frappe.get_doc("Item", item)
		mapping_name = doc.dependent_attribute_mapping
		stage_mapping = doc.attributes[0].mapping
		attributes = [
			{
				**self._attribute_row(self.stage, "Pack", "Loose"),
				"mapping_modified": frappe.db.get_value(
					"YRP Item Item Attribute Mapping", stage_mapping, "modified"
				),
			},
			self._attribute_row(self.size),
			self._attribute_row(self.colour),
		]
		self._update_dependent(
			item,
			attributes=attributes,
			dependent_details=[
				{"value": "Pack", "uom": self.box_uom, "display_name": "Box", "attributes": [self.colour]},
				{"value": "Loose", "uom": self.uom, "display_name": "Loose", "attributes": [self.size]},
			],
		)

		self.assertEqual(frappe.db.get_value("Item", item, "dependent_attribute_mapping"), mapping_name)
		self.assertEqual(
			self._dependent_rows(item),
			{
				"Cut": (self.uom, "", [self.size]),
				"Pack": (self.box_uom, "Box", [self.colour]),
				"Loose": (self.uom, "Loose", [self.size]),
			},
		)

	def test_unchanged_dependent_details_do_not_rewrite_the_mapping(self):
		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		mapping_name = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		before = frappe.db.get_value("YRP Item Dependent Attribute Mapping", mapping_name, "modified")
		self._update_dependent(item, description="Only the description changes")
		after = frappe.db.get_value("YRP Item Dependent Attribute Mapping", mapping_name, "modified")
		self.assertEqual(before, after)

	def test_changing_or_clearing_the_dependent_attribute_leaves_no_stale_mapping(self):
		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		stage_mapping = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		colour_values = [
			self._attribute_row(self.stage, "Cut", "Pack"),
			self._attribute_row(self.size),
			self._attribute_row(self.colour, "Red"),
		]
		colour_values[2]["mapping_modified"] = frappe.db.get_value(
			"YRP Item Item Attribute Mapping",
			frappe.get_doc("Item", item).attributes[2].mapping,
			"modified",
		)
		self._update_dependent(item, attributes=colour_values, dependent_attribute=self.colour)

		colour_mapping = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		self.assertFalse(frappe.db.exists("YRP Item Dependent Attribute Mapping", stage_mapping))
		self.assertEqual(
			frappe.db.get_value("YRP Item Dependent Attribute Mapping", colour_mapping, "dependent_attribute"),
			self.colour,
		)
		self.assertEqual(self._dependent_rows(item), {"Red": (self.uom, "", [self.size])})

		self._update_dependent(item, dependent_attribute=None)
		self.assertEqual(
			frappe.db.get_value(
				"Item", item, ["dependent_attribute", "dependent_attribute_mapping"]
			),
			(None, None),
		)
		self.assertFalse(frappe.db.exists("YRP Item Dependent Attribute Mapping", colour_mapping))

	def test_removing_every_attribute_deletes_the_dependent_mapping(self):
		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		mapping_name = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		payload = get_item_editor(item)
		values = {**payload["values"], "attributes": [], "primary_attribute": None, "dependent_attribute": None}
		update_item(item, values, payload["modified"])
		self.assertEqual(
			frappe.db.get_value("Item", item, ["has_variants", "dependent_attribute_mapping"]),
			(0, None),
		)
		self.assertFalse(frappe.db.exists("YRP Item Dependent Attribute Mapping", mapping_name))

	def test_desk_combination_edit_after_opening_rejects_the_web_save(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		payload = get_item_editor(item)
		mapping_name = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		frappe.db.set_value(
			"YRP Item Dependent Attribute Mapping", mapping_name, "modified", "2000-01-01 00:00:00"
		)
		update_dependent_attribute_details(
			mapping_name,
			{"attr_list": {value: {"uom": self.box_uom, "name": "Desk", "attributes": [self.size]} for value in ("Cut", "Pack")}},
		)
		values = {
			**payload["values"],
			"description": "Stale web save",
			"attributes": [
				{**row, "values": [value["label"] for value in row["values"]]}
				for row in payload["values"]["attributes"]
			],
		}
		with self.assertRaises(frappe.TimestampMismatchError):
			update_item(item, values, payload["modified"])
		self.assertEqual(self._dependent_rows(item)["Cut"], (self.box_uom, "Desk", [self.size]))

	def test_primary_attribute_set_change_and_clear_with_variants_matches_desk(self):
		item = self._create_as(
			"item_manager",
			self._values(
				attributes=[
					self._attribute_row(self.colour, "Red"),
					self._attribute_row(self.size, "Small"),
				]
			),
		)["name"]
		desk = self._desk_copy_item(item)
		for name in (item, desk.name):
			get_or_create_variant(name, {self.colour: "Red", self.size: "Small"})
		for primary in (self.colour, self.size, None):
			with self.subTest(primary=primary):
				frappe.set_user("Administrator")
				desk.primary_attribute = primary
				desk.save()
				self._update_dependent(item, primary_attribute=primary)
				self.assertEqual(frappe.db.get_value("Item", item, "primary_attribute"), primary)
				self.assertEqual(self._parity_snapshot(item), self._parity_snapshot(desk.name))

	def test_dependent_attribute_clear_set_and_change_with_variants_matches_desk(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		item = self._create_as(
			"purchase_manager",
			self._dependent_values(
				attributes=[
					self._attribute_row(self.stage, "Cut", "Pack"),
					self._attribute_row(self.size),
					self._attribute_row(self.colour, "Red"),
				]
			),
		)["name"]
		desk = self._desk_copy_item(item)
		frappe.set_user("Administrator")
		for name in (item, desk.name):
			get_or_create_variant(name, {self.stage: "Cut", self.size: "Small", self.colour: "Red"})
		self._update_dependent(
			item,
			dependent_details=[
				{"value": "Cut", "uom": self.box_uom, "display_name": "Cut Panel", "attributes": [self.size]},
			],
		)
		self.assertEqual(self._dependent_rows(item)["Cut"], (self.box_uom, "Cut Panel", [self.size]))
		for dependent in (None, self.stage, self.colour, None):
			with self.subTest(dependent=dependent):
				frappe.set_user("Administrator")
				if desk.dependent_attribute and dependent and desk.dependent_attribute != dependent:
					desk.dependent_attribute = None
					desk.save()
				desk.dependent_attribute = dependent
				desk.save()
				if dependent:
					stages = ("Cut", "Pack") if dependent == self.stage else ("Red",)
					update_dependent_attribute_details(
						desk.dependent_attribute_mapping,
						{
							"attr_list": {
								value: {"uom": self.uom, "name": value, "attributes": [self.size]}
								for value in stages
							}
						},
					)
				else:
					stages = ()
				self._update_dependent(
					item,
					dependent_attribute=dependent,
					dependent_details=[
						{"value": value, "uom": self.uom, "display_name": value, "attributes": [self.size]}
						for value in stages
					],
				)
				self.assertEqual(frappe.db.get_value("Item", item, "dependent_attribute"), dependent)
				self.assertEqual(self._parity_snapshot(item), self._parity_snapshot(desk.name))
				self.assertEqual(self._dependent_rows(item), self._dependent_rows(desk.name))

	def test_primary_and_dependent_locks_follow_family_stock_and_preserve_values(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		for doctype, field in (
			("YRP Bin", "item_code"),
			("YRP Stock Ledger Entry", "item"),
			("YRP Stock Reservation Entry", "item_code"),
		):
			for stock_on_variant in (False, True):
				with self.subTest(doctype=doctype, stock_on_variant=stock_on_variant):
					item = self._create_as("purchase_manager", self._dependent_values())["name"]
					frappe.set_user("Administrator")
					variant = get_or_create_variant(item, {self.stage: "Cut", self.size: "Small"})
					frappe.get_doc(
						{
							"doctype": doctype,
							"name": frappe.generate_hash(),
							field: variant if stock_on_variant else item,
						}
					).db_insert()
					payload = get_item_editor(item)
					self.assertTrue(payload["primary_attribute_locked"])
					self.assertTrue(payload["dependent_attribute_locked"])
					self.assertIn("YRP stock", payload["primary_attribute_lock_message"])
					self.assertIn("YRP stock", payload["dependent_attribute_lock_message"])
					before = self._item_configuration(item)
					before_details = self._dependent_rows(item)
					for changes in ({"primary_attribute": self.colour}, {"dependent_attribute": None}):
						desk = frappe.get_doc("Item", item)
						desk.update(changes)
						point = "stock_rule_" + frappe.generate_hash(length=8)
						frappe.db.savepoint(point)
						with self.assertRaisesRegex(frappe.ValidationError, "after YRP stock exists"):
							desk.save()
						frappe.db.rollback(save_point=point)
						with self.assertRaisesRegex(frappe.ValidationError, "after YRP stock exists"):
							self._update_dependent(item, **changes)
						self.assertEqual(self._item_configuration(item), before)
						self.assertEqual(self._dependent_rows(item), before_details)
					self._update_dependent(
						item,
						attributes=[
							payload["values"]["attributes"][0],
							payload["values"]["attributes"][1],
							{**payload["values"]["attributes"][2], "values": ["Red"]},
						],
					)
					self.assertEqual(
						get_mapping_values(frappe.get_doc("Item", item).attributes[2].mapping), ["Red"]
					)

	def test_values_staged_in_the_dialog_are_created_on_save(self):
		created = self._create_as(
			"item_manager",
			self._values(attributes=[{"attribute": self.colour, "values": []}]),
		)
		mapping = frappe.db.get_value("Item Variant Attribute", {"parent": created["name"]}, "mapping")
		new_value = f"Purple {frappe.generate_hash(length=6)}"

		self._update_colour_values(created["name"], ["Red", new_value])

		self.assertEqual(get_mapping_values(mapping), ["Red", new_value])
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": self.colour, "attribute_value": new_value},
			)
		)

	def test_narrowing_a_row_without_a_mapping_record_creates_the_mapping(self):
		created = self._create_as(
			"item_manager",
			self._values(attributes=[{"attribute": self.colour, "values": []}]),
		)
		row = frappe.get_doc("Item", created["name"]).attributes[0]
		frappe.db.set_value("Item Variant Attribute", row.name, "mapping", None)

		self._update_colour_values(created["name"], ["Red"])

		mapping = frappe.db.get_value("Item Variant Attribute", row.name, "mapping")
		self.assertTrue(mapping)
		self.assertEqual(get_mapping_values(mapping), ["Red"])

	def test_values_that_differ_only_by_case_reuse_the_stored_value(self):
		new_value = f"Purple {frappe.generate_hash(length=6)}"
		created = self._create_as(
			"item_manager",
			self._values(
				attributes=[
					{
						"attribute": self.colour,
						"values": ["red", "BLUE", "Red", new_value, new_value.upper()],
					}
				]
			),
		)
		mapping = frappe.db.get_value("Item Variant Attribute", {"parent": created["name"]}, "mapping")

		self.assertEqual(get_mapping_values(mapping), ["Red", "Blue", new_value])
		global_values = frappe.get_all(
			"Item Attribute Value", filters={"parent": self.colour}, pluck="attribute_value"
		)
		self.assertNotIn("red", global_values)
		self.assertEqual([value.casefold() for value in global_values].count(new_value.casefold()), 1)

	def test_value_search_puts_an_exact_match_past_the_page_first(self):
		from essdee_yrp.purchase.item_editor import search_attribute_values

		attribute = self._make_attribute(
			f"Many {frappe.generate_hash(length=6)}",
			[f"Xm {index:03}" for index in range(120)] + ["M"],
		)

		labels = [row["label"] for row in search_attribute_values(attribute, "m")]

		self.assertEqual(labels[0], "M")
		self.assertEqual(len(labels), 99)

	def test_reselected_attribute_saves_with_the_loaded_mapping_token(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red")]),
		)
		for values in ([], ["Blue"]):
			doc = frappe.get_doc("Item", created["name"])
			loaded = get_item_editor(doc.name)["values"]["attributes"][0]
			update_item(
				doc.name,
				self._values(
					doc.item_name,
					item_group=doc.item_group,
					stock_uom=doc.stock_uom,
					attributes=[
						{
							"attribute": self.colour,
							"values": values,
							"mapping_modified": loaded["mapping_modified"],
						}
					],
				),
				doc.modified,
			)
			self.assertEqual(get_mapping_values(loaded["mapping"]), values)

	def _master_values(self, **overrides):
		return self._values(
			label=f"ZZ TEST Item Master {frappe.generate_hash(length=8)}",
			**{"uoms": [{"uom": self.box_uom, "conversion_factor": 10}], **overrides},
		)

	def test_master_new_payload_waits_for_user_stock_uom(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		frappe.set_user(self.fixture_users["purchase_manager"])
		payload = get_item_editor()
		self.assertIsNone(payload["values"]["stock_uom"])
		self.assertEqual(payload["values"]["uoms"], [])

	def _parameter_fixture(self):
		frappe.set_user("Administrator")
		suffix = frappe.generate_hash(length=8)
		keys = [
			frappe.get_doc({"doctype": "YRP Additional Parameter Key", "key": f"ZZ TEST {key} {suffix}"})
			.insert(ignore_permissions=True)
			.name
			for key in ("GSM", "DIA")
		]
		values = [
			frappe.get_doc(
				{
					"doctype": "YRP Additional Parameter Value",
					"key": key,
					"value": f"ZZ TEST {label} {suffix}",
				}
			)
			.insert(ignore_permissions=True)
			.name
			for key, label in ((keys[0], "180"), (keys[0], "200"), (keys[1], "36"))
		]
		return keys, values

	def test_master_uoms_create_edit_remove_and_keep_child_names(self):
		item = self._create_as("purchase_manager", self._master_values())["name"]
		doc = frappe.get_doc("Item", item)
		self.assertEqual(
			[(row.uom, row.conversion_factor) for row in doc.uoms], [(self.uom, 1), (self.box_uom, 10)]
		)
		names = {row.uom: row.name for row in doc.uoms}
		updated = self._update_dependent(
			item,
			uoms=[
				{"uom": self.box_uom, "conversion_factor": 12},
				{"uom": self.secondary_uom, "conversion_factor": 5},
			],
		)
		self.assertEqual(updated["values"]["uoms"][1]["name"], names[self.box_uom])
		self.assertEqual(updated["values"]["uoms"][1]["conversion_factor"], 12)
		self.assertEqual(frappe.get_doc("Item", item).uoms[0].name, names[self.uom])
		self._update_dependent(item, uoms=[])
		doc.reload()
		self.assertEqual([(row.uom, row.conversion_factor) for row in doc.uoms], [(self.uom, 1)])
		self.assertEqual(doc.uoms[0].name, names[self.uom])

	def test_master_uoms_propagate_to_an_existing_variant(self):
		item = self._create_as(
			"purchase_manager",
			self._master_values(
				attributes=[self._attribute_row(self.colour, "Red")], primary_attribute=self.colour
			),
		)["name"]
		frappe.set_user("Administrator")
		variant = get_or_create_variant(item, {self.colour: "Red"})
		original_get = frappe.db.get_single_value

		def single_value(doctype, fieldname, *args, **kwargs):
			if (doctype, fieldname) == ("Item Variant Settings", "do_not_update_variants"):
				return 0
			return original_get(doctype, fieldname, *args, **kwargs)

		with patch.object(frappe.db, "get_single_value", side_effect=single_value):
			self._update_dependent(
				item,
				uoms=[
					{"uom": self.box_uom, "conversion_factor": 12},
					{"uom": self.secondary_uom, "conversion_factor": 5},
				],
			)
		self.assertEqual(
			{row.uom: row.conversion_factor for row in frappe.get_doc("Item", variant).uoms},
			{self.uom: 1, self.box_uom: 12, self.secondary_uom: 5},
		)

	def test_master_parameter_rows_round_trip_and_keep_matching_names(self):
		keys, values = self._parameter_fixture()
		rows = [
			{"additional_parameter_key": keys[0], "additional_parameter_value": values[0]},
			{"additional_parameter_key": keys[1], "additional_parameter_value": None},
		]
		item = self._create_as("purchase_manager", self._master_values(additional_parameters=rows))["name"]
		doc = frappe.get_doc("Item", item)
		first_name = doc.additional_parameters[0].name
		self.assertEqual(
			[
				(row.additional_parameter_key, row.additional_parameter_value or None)
				for row in doc.additional_parameters
			],
			[(keys[0], values[0]), (keys[1], None)],
		)
		self._update_dependent(
			item,
			additional_parameters=[
				{"additional_parameter_key": keys[0], "additional_parameter_value": values[1]}
			],
		)
		doc.reload()
		self.assertEqual(len(doc.additional_parameters), 1)
		self.assertEqual(
			(doc.additional_parameters[0].name, doc.additional_parameters[0].additional_parameter_value),
			(first_name, values[1]),
		)
		self._update_dependent(
			item,
			additional_parameters=[
				{"additional_parameter_key": keys[0], "additional_parameter_value": values[1]},
				rows[1],
			],
		)
		self.assertEqual(len(frappe.get_doc("Item", item).additional_parameters), 2)

	def test_master_scalar_fields_round_trip_with_meta_labels(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		product = frappe.get_doc(
			{
				"doctype": "SD YRP Product Category",
				"category": f"ZZ TEST Product {frappe.generate_hash(length=8)}",
			}
		).insert(ignore_permissions=True)
		category = frappe.get_doc(
			{
				"doctype": "YRP Item Category",
				"category_name": f"ZZ TEST Category {frappe.generate_hash(length=8)}",
				"node_type": "Item Type",
			}
		).insert(ignore_permissions=True)
		hsns = frappe.get_all("GST HSN Code", pluck="name", limit=2)
		fields = dict(
			secondary_unit_of_measure=self.secondary_uom,
			po_excess_allowed_percentage=10,
			product_category=product.name,
			hsn_code="123456",
			categories=[category.name],
			is_ineligible_for_itc=1,
			brand=self.brand,
			description="<p>ZZ TEST &amp; original HTML</p>",
			gst_hsn_code=hsns[0] if hsns else None,
		)
		item = self._create_as("purchase_manager", self._master_values(**fields))["name"]
		payload = get_item_editor(item)
		for field, value in fields.items():
			self.assertEqual(payload["values"][field], value, field)
			self.assertEqual(
				payload["fields"][field]["label"], frappe.get_meta("Item").get_field(field).label
			)
		self.assertEqual(frappe.db.get_value("Item", item, "product_category"), product.name)
		payload = self._update_dependent(item, product_category=None)
		self.assertIsNone(payload["values"]["product_category"])
		payload = self._update_dependent(item, product_category=product.name)
		self.assertEqual(payload["values"]["product_category"], product.name)
		self.assertEqual(frappe.db.get_value("Item", item, "product_category"), product.name)
		changes = {
			**fields,
			"secondary_unit_of_measure": self.box_uom,
			"po_excess_allowed_percentage": 5,
			"brand": self.multi_word_brand,
			"description": "<p>ZZ TEST changed</p>",
			"hsn_code": "654321",
			"categories": [],
			"is_ineligible_for_itc": 0,
			"product_category": None,
			"gst_hsn_code": hsns[-1] if hsns else None,
		}
		payload = self._update_dependent(item, **changes)
		for field, value in changes.items():
			self.assertEqual(payload["values"][field], value, field)
		payload = self._update_dependent(
			item, name="ZZ TEST Changed Name", stock_uom=self.box_uom, disabled=1
		)
		self.assertEqual(
			(payload["values"]["name"], payload["values"]["stock_uom"], payload["values"]["disabled"]),
			("ZZ TEST Changed Name", self.uom, 1),
		)

	def test_master_missing_stage_conversion_rejected_before_item_or_mapping_insert(self):
		values = self._dependent_values(
			name=f"ZZ TEST Missing Conversion {frappe.generate_hash(length=8)}",
			uoms=[],
			dependent_details=[{"value": "Pack", "uom": self.box_uom, "display_name": "Packed", "attributes": [self.size]}],
		)
		before = frappe.db.count("YRP Item Item Attribute Mapping")
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack uses UOM.*no.*conversion"):
			self._create_as("purchase_manager", values)
		self.assertFalse(frappe.db.exists("Item", values["name"]))
		self.assertEqual(frappe.db.count("YRP Item Item Attribute Mapping"), before)
		values["uoms"] = [{"uom": self.box_uom, "conversion_factor": 10}]
		item = self._create_as("purchase_manager", values)["name"]
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack uses UOM"):
			self._update_dependent(item, uoms=[])
		self.assertEqual(frappe.get_doc("Item", item).uoms[1].conversion_factor, 10)

	def test_empty_stage_attributes_rejected_on_create_and_update(self):
		values = self._dependent_values()
		values["dependent_details"][0]["attributes"] = []
		before = frappe.db.count("YRP Item Item Attribute Mapping")
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack must use at least one attribute"):
			self._create_as("purchase_manager", values)
		self.assertFalse(frappe.db.exists("Item", values["name"]))
		self.assertEqual(frappe.db.count("YRP Item Item Attribute Mapping"), before)
		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		stored = self._dependent_rows(item)
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack must use at least one attribute"):
			self._update_dependent(item, dependent_details=values["dependent_details"])
		self.assertEqual(self._dependent_rows(item), stored)

	def test_legacy_empty_stage_loads_but_requires_attributes_to_save(self):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		frappe.set_user("Administrator")
		mapping = frappe.db.get_value("Item", item, "dependent_attribute_mapping")
		update_dependent_attribute_details(mapping, {"attr_list": {
			"Cut": {"uom": self.uom, "name": "", "attributes": [self.size]},
			"Pack": {"uom": self.uom, "name": "Packed", "attributes": []},
		}})
		frappe.set_user(self.fixture_users["purchase_manager"])
		self.assertEqual(get_item_editor(item)["values"]["dependent_details"][1]["attributes"], [])
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack must use at least one attribute"):
			self._update_dependent(item, description="ZZ TEST requires stage repair")
		self._update_dependent(item, dependent_details=[{
			"value": "Pack", "uom": self.uom, "display_name": "Packed", "attributes": [self.size],
		}])

	def test_master_changed_stage_requires_conversion_and_missing_uom_fails_before_insert(self):
		values = self._dependent_values(name=f"ZZ TEST Stage UOM {frappe.generate_hash(length=8)}", uoms=[])
		item = self._create_as("purchase_manager", values)["name"]
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack uses UOM"):
			self._update_dependent(
				item, dependent_details=[{"value": "Pack", "uom": self.box_uom, "attributes": [self.size]}]
			)
		values["name"] += " Missing"
		values["dependent_details"] = [{"value": "Pack", "uom": None}]
		with self.assertRaisesRegex(frappe.ValidationError, "Select a valid UOM"):
			self._create_as("purchase_manager", values)
		self.assertFalse(frappe.db.exists("Item", values["name"]))

	def test_master_invalid_factors_and_duplicate_uoms_rejected_on_create_and_update(self):
		item = self._create_as("purchase_manager", self._master_values())["name"]
		cases = [
			(
				[{"uom": self.uom, "conversion_factor": 2}],
				"Conversion factor for default Unit of Measure must be 1 in row 1",
			),
			([{"uom": self.box_uom, "conversion_factor": 1}] * 2, "entered more than once"),
			*(
				[[{"uom": self.box_uom, "conversion_factor": factor}], "must be greater than 0"]
				for factor in (0, None, "", -1, "NaN", "Infinity")
			),
		]
		for rows, message in cases:
			with self.subTest(rows=rows):
				values = self._master_values(uoms=rows)
				with self.assertRaisesRegex(frappe.ValidationError, message):
					self._create_as("purchase_manager", values)
				self.assertFalse(frappe.db.exists("Item", values["name"]))
				with self.assertRaisesRegex(frappe.ValidationError, message):
					self._update_dependent(item, uoms=rows)

	def test_master_parameter_key_and_value_validation_on_create_and_update(self):
		keys, values = self._parameter_fixture()
		item = self._create_as("purchase_manager", self._master_values())["name"]
		cases = [
			([{"additional_parameter_value": values[0]}], "select an Additional Parameter Key"),
			(
				[{"additional_parameter_key": keys[0], "additional_parameter_value": values[2]}],
				"does not belong to Key",
			),
			([{"additional_parameter_key": keys[0]}] * 2, "is repeated"),
		]
		for rows, message in cases:
			with self.subTest(rows=rows):
				request = self._master_values(additional_parameters=rows)
				with self.assertRaisesRegex(frappe.ValidationError, message):
					self._create_as("purchase_manager", request)
				self.assertFalse(frappe.db.exists("Item", request["name"]))
				with self.assertRaisesRegex(frappe.ValidationError, message):
					self._update_dependent(item, additional_parameters=rows)

	def test_master_parameter_value_key_matches_case_insensitively(self):
		keys, values = self._parameter_fixture()
		frappe.db.set_value("YRP Additional Parameter Value", values[0], "key", keys[0].lower())
		rows = [{"additional_parameter_key": keys[0], "additional_parameter_value": values[0]}]
		item = self._create_as("purchase_manager", self._master_values(additional_parameters=rows))["name"]
		self.assertEqual(
			[(row.additional_parameter_key, row.additional_parameter_value) for row in frappe.get_doc("Item", item).additional_parameters],
			[(keys[0], values[0])],
		)

	def test_parameter_case_duplicates_rejected_and_single_key_canonicalized(self):
		keys, _ = self._parameter_fixture()
		rows = [{"additional_parameter_key": key} for key in (keys[0], keys[0].lower())]
		item = self._create_as("purchase_manager", self._master_values())["name"]
		with self.assertRaisesRegex(frappe.ValidationError, "is repeated"):
			self._create_as("purchase_manager", self._master_values(additional_parameters=rows))
		with self.assertRaisesRegex(frappe.ValidationError, "is repeated"):
			self._update_dependent(item, additional_parameters=rows)
		created = self._create_as(
			"purchase_manager", self._master_values(additional_parameters=rows[1:])
		)["name"]
		self._update_dependent(item, additional_parameters=rows[1:])
		for name in (created, item):
			self.assertEqual(frappe.get_doc("Item", name).additional_parameters[0].additional_parameter_key, keys[0])

	def test_master_legacy_duplicate_parameters_load_but_need_fixing_to_save(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		keys, _ = self._parameter_fixture()
		item = self._create_as(
			"purchase_manager",
			self._master_values(additional_parameters=[{"additional_parameter_key": keys[0]}]),
		)["name"]
		doc = frappe.get_doc("Item", item)
		frappe.set_user("Administrator")
		doc.append("additional_parameters", {"additional_parameter_key": keys[0]})
		doc.save()
		self.assertEqual(len(get_item_editor(item)["values"]["additional_parameters"]), 2)
		with self.assertRaisesRegex(frappe.ValidationError, "is repeated"):
			self._update_dependent(item, description="ZZ TEST requires repair")
		self._update_dependent(item, additional_parameters=[{"additional_parameter_key": keys[0]}])

	def test_master_negative_po_excess_rejected_on_create_and_update(self):
		request = self._master_values(po_excess_allowed_percentage=-1)
		with self.assertRaisesRegex(frappe.ValidationError, "greater than or equal to 0"):
			self._create_as("purchase_manager", request)
		self.assertFalse(frappe.db.exists("Item", request["name"]))
		item = self._create_as("purchase_manager", self._master_values())["name"]
		with self.assertRaisesRegex(frappe.ValidationError, "greater than or equal to 0"):
			self._update_dependent(item, po_excess_allowed_percentage=-1)

	def _yarn_items(self):
		return [self._create_as("purchase_manager", self._master_values())["name"] for _ in range(2)]

	def test_master_yarn_search_excludes_fabric_variants_in_both_search_paths(self):
		from essdee_yrp.api.link_search import link_search

		prefix = f"ZZ TEST Fabric Yarn Search {frappe.generate_hash(length=8)}"
		yarn = self._create_as("purchase_manager", self._master_values(name=f"{prefix} Yarn"))["name"]
		cloth = self._create_as(
			"purchase_manager",
			self._master_values(
				name=f"{prefix} Cloth", is_cloth_item=1,
				yarn_ratio_details=[{"yarn_item": yarn, "ratio": 100}],
				attributes=[self._attribute_row(self.colour, "Red")],
				primary_attribute=self.colour,
			),
		)["name"]
		variant = get_or_create_variant(cloth, {self.colour: "Red"})
		self.assertFalse(frappe.db.get_value("Item", variant, "is_cloth_item"))
		filters = {"disabled": 0, "is_cloth_item": 0, "variant_of": ["is", "not set"], "name": ["!=", cloth]}
		self.assertEqual([row["name"] for row in link_search("Item", prefix, filters)], [yarn])
		self.assertEqual(link_search("Item", variant, filters), [])
		self.assertEqual([row["name"] for row in link_search("Item", yarn, filters)], [yarn])

	def test_cloth_template_variant_rejected_as_yarn_on_create_and_update(self):
		yarn = self._yarn_items()[0]
		cloth = self._create_as("purchase_manager", self._master_values(
			is_cloth_item=1, yarn_ratio_details=[{"yarn_item": yarn, "ratio": 100}],
			attributes=[self._attribute_row(self.colour, "Red")], primary_attribute=self.colour,
		))["name"]
		variant = get_or_create_variant(cloth, {self.colour: "Red"})
		self.assertFalse(frappe.db.get_value("Item", variant, "is_cloth_item"))
		rows = [{"yarn_item": variant, "ratio": 100}]
		with self.assertRaisesRegex(frappe.ValidationError, "Cloth Item.*cannot be selected as yarn"):
			self._create_as("purchase_manager", self._master_values(is_cloth_item=1, yarn_ratio_details=rows))
		with self.assertRaisesRegex(frappe.ValidationError, "Cloth Item.*cannot be selected as yarn"):
			self._update_dependent(cloth, yarn_ratio_details=rows)

	def test_master_cloth_yarn_recipe_round_trip_and_existing_hook_errors(self):
		yarns = self._yarn_items()
		rows = [{"yarn_item": yarns[0], "ratio": 60}, {"yarn_item": yarns[1], "ratio": 40}]
		item = self._create_as(
			"purchase_manager", self._master_values(is_cloth_item=1, yarn_ratio_details=rows)
		)["name"]
		doc = frappe.get_doc("Item", item)
		names = [row.name for row in doc.yarn_ratio_details]
		self.assertEqual(sum(row.ratio for row in doc.yarn_ratio_details), 100)
		self._update_dependent(item, yarn_ratio_details=[{**rows[0], "ratio": 50}, {**rows[1], "ratio": 50}])
		self.assertEqual([row.name for row in frappe.get_doc("Item", item).yarn_ratio_details], names)
		for invalid, message in (
			([], "Add at least one Yarn Ratio"),
			([{"yarn_item": yarns[0], "ratio": 90}], "exactly 100"),
		):
			request = self._master_values(is_cloth_item=1, yarn_ratio_details=invalid)
			with self.assertRaisesRegex(frappe.ValidationError, message):
				self._create_as("purchase_manager", request)
			self.assertFalse(frappe.db.exists("Item", request["name"]))
			with self.assertRaisesRegex(frappe.ValidationError, message):
				self._update_dependent(item, yarn_ratio_details=invalid)

	def test_master_yarn_validation_reuses_cloth_duplicate_self_and_attribute_rules(self):
		yarns = self._yarn_items()
		cloth = self._create_as(
			"purchase_manager",
			self._master_values(is_cloth_item=1, yarn_ratio_details=[{"yarn_item": yarns[0], "ratio": 100}]),
		)["name"]
		unsupported = self._create_as(
			"purchase_manager", self._master_values(attributes=[self._attribute_row(self.size, "Small")])
		)["name"]
		cases = [
			([{"yarn_item": yarns[0], "ratio": 50}] * 2, "duplicated"),
			([{"yarn_item": cloth, "ratio": 100}], "cannot be selected as yarn"),
			([{"yarn_item": unsupported, "ratio": 100}], "may only use"),
		]
		for rows, message in cases:
			with self.assertRaisesRegex(frappe.ValidationError, message):
				self._create_as(
					"purchase_manager", self._master_values(is_cloth_item=1, yarn_ratio_details=rows)
				)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot use itself as yarn"):
			self._update_dependent(cloth, yarn_ratio_details=[{"yarn_item": cloth, "ratio": 100}])

	def test_master_item_link_lookup_filters_values_under_item_permissions(self):
		from essdee_yrp.purchase.item_tables import search_item_editor_links

		keys, values = self._parameter_fixture()
		frappe.set_user(self.fixture_users["purchase_manager"])
		self.assertEqual(
			{
				row["name"]
				for row in search_item_editor_links("YRP Additional Parameter Value", "ZZ TEST", keys[0])
			},
			set(values[:2]),
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Set Additional Parameter Key first"):
			search_item_editor_links("YRP Additional Parameter Value")
		with self.assertRaises(frappe.PermissionError):
			search_item_editor_links("User")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			search_item_editor_links("YRP Additional Parameter Key")

	def test_master_web_and_desk_payloads_have_the_same_stored_configuration(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		keys, parameter_values = self._parameter_fixture()
		values = self._parity_values(keys[0], parameter_values[0])
		web_item = self._create_as("purchase_manager", values)["name"]
		frappe.set_user("Administrator")
		desk = self._desk_parity_item(values)
		self.assertEqual(self._parity_snapshot(web_item), self._parity_snapshot(desk.name))
		self.assertEqual(self._dependent_rows(web_item), self._dependent_rows(desk.name))
		web = frappe.get_doc("Item", web_item)
		web.save()
		self.assertEqual(self._parity_snapshot(web_item), self._parity_snapshot(desk.name))
		self.assertEqual(
			get_item_editor(web_item)["fields"]["uoms"]["columns"]["conversion_factor"]["label"],
			frappe.get_meta("UOM Conversion Detail").get_field("conversion_factor").label,
		)

	def _parity_values(self, key, value):
		return self._dependent_values(
			name=f"ZZ TEST Item Master Web {frappe.generate_hash(length=6)}",
			secondary_unit_of_measure=self.secondary_uom,
			po_excess_allowed_percentage=5,
			additional_parameters=[{"additional_parameter_key": key, "additional_parameter_value": value}],
			dependent_details=[
				{"value": "Pack", "uom": self.box_uom, "display_name": "Packed", "attributes": [self.size, self.colour]},
			],
		)

	def _desk_parity_values(self, values):
		desk_name = f"ZZ TEST Item Master Desk {frappe.generate_hash(length=6)}"
		return {
			"doctype": "Item", "item_code": desk_name, "item_name": desk_name,
			"item_group": values["item_group"], "stock_uom": values["stock_uom"],
			"description": values["description"], "has_variants": 1,
			"variant_based_on": "Item Attribute", "primary_attribute": self.size,
			"attributes": [{"attribute": row["attribute"]} for row in values["attributes"]],
			"uoms": [{"uom": self.uom, "conversion_factor": 1}, *values["uoms"]],
			"secondary_unit_of_measure": self.secondary_uom, "po_excess_allowed_percentage": 5,
			"additional_parameters": values["additional_parameters"],
			"is_stock_item": 1, "is_purchase_item": 1, "is_sales_item": 0,
			"country_of_origin": frappe.db.get_default("country"),
		}

	def _desk_parity_item(self, values):
		from yrp.yrp.doctype.yrp_item.yrp_item import update_dependent_attribute_details

		desk = frappe.get_doc(self._desk_parity_values(values)).insert()
		for request, row in zip(values["attributes"], desk.attributes, strict=True):
			mapping = frappe.get_doc("YRP Item Item Attribute Mapping", row.mapping)
			mapping.set("values", [{"attribute_value": value["name"]} for value in request["values"]])
			mapping.save()
		desk.dependent_attribute = self.stage
		desk.save()
		update_dependent_attribute_details(
			desk.dependent_attribute_mapping,
			{"attr_list": {
				"Cut": {"uom": self.uom, "name": "", "attributes": [self.size]},
				"Pack": {"uom": self.box_uom, "name": "Packed", "attributes": [self.size, self.colour]},
			}},
		)
		return desk

	def _parity_snapshot(self, item):
		doc = frappe.get_doc("Item", item)
		ignored = {
			"name",
			"item_code",
			"item_name",
			"creation",
			"modified",
			"modified_by",
			"owner",
			"item_hash_value",
			"dependent_attribute_mapping",
		}
		result = {field: doc.get(field) for field in doc.meta.get_valid_columns() if field not in ignored}
		for field in doc.meta.get_table_fields():
			result[field.fieldname] = self._parity_children(doc.get(field.fieldname) or [])
		return result

	def _parity_children(self, rows):
		ignored = {"name", "parent", "creation", "modified", "modified_by", "owner", "mapping"}
		values = []
		for row in rows:
			value = {field: row.get(field) for field in row.meta.get_valid_columns() if field not in ignored}
			if row.get("mapping"):
				value["mapping_values"] = get_mapping_values(row.mapping)
			values.append(value)
		return values

	def test_master_payload_reports_stock_and_fg_packing_context(self):
		from essdee_yrp.purchase.item_editor import get_item_editor

		item = self._create_as("purchase_manager", self._master_values())["name"]
		with (
			patch("essdee_yrp.purchase.item_usage._item_family_has_yrp_stock", return_value=True),
			patch("essdee_yrp.purchase.item_editor.finished_goods_packing", return_value=12),
		):
			payload = get_item_editor(item)
		self.assertTrue(payload["has_item_transactions"])
		self.assertEqual(payload["fg_pcs_per_box"], 12)

	def _receipt(self, item, warehouse, dimensions):
		return frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": "Material Receipt",
				"to_warehouse": warehouse,
				"items": [{"item": item, "qty": 3, "rate": 1, "row_index": 0, "table_index": 0, **dimensions}],
			}
		)

	def _receipt_dimensions(self):
		"""Make isolated stock dimensions inside the case's rollback savepoint."""
		lot = frappe.new_doc("SD YRP Lot")
		lot.name = lot.lot_name = f"ZZ TEST Item Master Lot {frappe.generate_hash(length=8)}"
		# Match the minimal lot fixture in test_delivery_challan_customization.
		lot.db_insert()
		received_type = frappe.db.get_value("YRP Received Type", "Accepted", "name")
		if not received_type:
			received_type = frappe.get_doc({
				"doctype": "YRP Received Type",
				"received_type_name": f"ZZ TEST Accepted {frappe.generate_hash(length=8)}",
				"is_default": 0,
			}).insert(ignore_permissions=True).name
		return {"lot": lot.name, "received_type": received_type}

	def test_master_stock_entry_uses_stage_conversion_and_rejects_direct_db_removal(self):
		stock_uom = frappe.db.get_value("UOM", "Pieces", "name") or self._make_uom("Pieces")
		packing_uom = frappe.db.get_value("UOM", "Box", "name") or self._make_uom("Box")
		values = self._dependent_values(
			name=f"ZZ TEST Stock Master {frappe.generate_hash(length=8)}",
			stock_uom=stock_uom,
			uoms=[{"uom": packing_uom, "conversion_factor": 10}],
			attributes=[
				self._attribute_row(self.stage, "Cut", "Pack"),
				self._attribute_row(self.colour, "Red"),
				self._attribute_row(self.size, "Small"),
			],
			dependent_details=[
				{"value": "Pack", "uom": packing_uom, "attributes": [self.size]},
				{"value": "Cut", "uom": stock_uom, "attributes": [self.colour, self.size]},
			],
		)
		item = self._create_as("purchase_manager", values)["name"]
		frappe.set_user("Administrator")
		pack = get_or_create_variant(item, {self.stage: "Pack", self.size: "Small"})
		cut_attributes = {self.stage: "Cut", self.colour: "Red", self.size: "Small"}
		cut = get_or_create_variant(item, cut_attributes)
		self.assertEqual(pack, f"{item}-Small")
		self.assertEqual(cut, f"{item}-Red-Small")
		self.assertEqual(
			frappe.db.get_value("Item", cut, "item_tuple_attribute"),
			str(tuple(sorted(cut_attributes.items()))),
		)
		dimensions = self._receipt_dimensions()
		warehouse = (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": f"ZZ TEST Item Master {frappe.generate_hash(length=8)}",
					"company": frappe.db.get_value("Company", {}, "name"),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		for variant, expected in (
			(pack, (packing_uom, stock_uom, 10, 30)),
			(cut, (stock_uom, stock_uom, 1, 3)),
		):
			entry = self._receipt(variant, warehouse, dimensions).insert()
			row = frappe.get_doc("YRP Stock Entry", entry.name).items[0]
			self.assertEqual((row.lot, row.received_type), (dimensions["lot"], dimensions["received_type"]))
			self.assertEqual(row.qty, 3)
			self.assertEqual((row.uom, row.stock_uom, row.conversion_factor, row.stock_qty), expected)
		frappe.db.delete("UOM Conversion Detail", {"parent": item, "uom": packing_uom})
		frappe.clear_document_cache("Item", item)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"no positive conversion to stock UOM.*Complete UOM Conversion Details first",
		):
			self._receipt(pack, warehouse, dimensions).insert()

	def _classification_fixture(self):
		frappe.set_user("Administrator")
		parent, names = None, []
		for kind in ("Item Type", "Category", "Value"):
			doc = frappe.get_doc(
				{
					"doctype": "YRP Item Category",
					"category_name": f"ZZ TEST {kind} {frappe.generate_hash(length=8)}",
					"node_type": kind,
					"parent_yrp_item_category": parent,
				}
			).insert(ignore_permissions=True)
			parent = doc.name
			names.append(parent)
		return names

	def _item_tax_template(self, company):
		if existing := frappe.db.get_value("Item Tax Template", {"company": company}, "name"):
			return existing
		account = frappe.db.get_value(
			"Account",
			{
				"company": company,
				"is_group": 0,
				"account_type": ["in", ["Tax", "Income Account", "Expense Account"]],
			},
			"name",
		)
		return (
			frappe.get_doc(
				{
					"doctype": "Item Tax Template",
					"title": f"ZZ TEST Item Master {frappe.generate_hash(length=8)}",
					"company": company,
					"taxes": [{"tax_type": account, "tax_rate": 5}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _desk_only_snapshot(self, doc):
		ignored = {"creation", "modified", "modified_by", "owner"}
		result = {
			field: doc.get(field)
			for field in (
				"valuation_method",
				"variant_based_on",
				"weight_per_unit",
				"allow_negative_stock",
				"yrp_item_type",
			)
		}
		for field in ("item_defaults", "taxes", "yrp_categories", "barcodes"):
			result[field] = [
				{key: value for key, value in row.as_dict().items() if key not in ignored}
				for row in doc.get(field) or []
			]
		return result

	def test_master_web_edit_preserves_desk_only_tables_fields_and_child_identity(self):
		root, category, value = self._classification_fixture()
		item = self._create_as("purchase_manager", self._master_values())["name"]
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Item", item)
		company = frappe.db.get_value("Company", {}, "name")
		if not doc.item_defaults:
			doc.append("item_defaults", {"company": company})
		doc.item_defaults[0].default_supplier = self.supplier
		doc.append(
			"taxes",
			{
				"item_tax_template": self._item_tax_template(company),
				"minimum_net_rate": 1,
				"maximum_net_rate": 100,
			},
		)
		doc.yrp_item_type = root
		doc.append("yrp_categories", {"category": category, "value": value})
		doc.append("barcodes", {"barcode": f"ZZ TEST {frappe.generate_hash(length=8)}"})
		doc.valuation_method = "FIFO"
		doc.weight_per_unit = 2
		doc.save()
		doc.reload()
		before = self._desk_only_snapshot(doc)
		self._update_dependent(
			item, description="ZZ TEST web change", uoms=[{"uom": self.box_uom, "conversion_factor": 12}]
		)
		doc.reload()
		self.assertEqual(self._desk_only_snapshot(doc), before)

	def test_master_permission_patch_grants_links_and_level_one_fields(self):
		from essdee_yrp.api.link_search import link_search
		from essdee_yrp.patches.grant_purchase_item_master_permissions import (
			LEVEL_ONE_GRANTS,
			PERMISSION_GRANTS,
			execute,
		)
		from essdee_yrp.purchase.item_tables import search_item_editor_links

		execute()
		execute()
		self._assert_permission_grants(PERMISSION_GRANTS, 0)
		self._assert_permission_grants(LEVEL_ONE_GRANTS, 1)
		product = frappe.get_doc({
			"doctype": "SD YRP Product Category", "category": f"ZZ TEST Permissions {self.suffix}",
		}).insert(ignore_permissions=True)
		for role_key in ("purchase_manager", "item_manager"):
			frappe.set_user(self.fixture_users[role_key])
			self.assertEqual(search_item_editor_links("SD YRP Product Category", product.name), [
				{"name": product.name, "label": product.name},
			])
			item = self._create_as(role_key, self._master_values(product_category=product.name))["name"]
			self.assertEqual(frappe.db.get_value("Item", item, "product_category"), product.name)
			self._update_dependent(item, product_category=None)
			self._update_dependent(item, product_category=product.name)
			self.assertEqual(frappe.db.get_value("Item", item, "product_category"), product.name)
		frappe.set_user("Administrator")
		user = self._make_user("master-links", ["Purchase Manager"])
		frappe.set_user(user)
		self.assertEqual([row["name"] for row in link_search("UOM", self.box_uom)], [self.box_uom])

	def _assert_permission_grants(self, grants, permlevel):
		for doctype, roles in grants.items():
			for role, permissions in roles.items():
				rows = frappe.get_all("Custom DocPerm", filters={
					"parent": doctype, "role": role, "permlevel": permlevel, "if_owner": 0,
				}, fields=["name", *permissions])
				self.assertEqual(len(rows), 1)
				self.assertTrue(all(rows[0][permission] == 1 for permission in permissions))

	def test_item_link_search_uses_permission_aware_list(self):
		from essdee_yrp.purchase.item_tables import search_item_editor_links

		frappe.set_user(self.fixture_users["purchase_manager"])
		with patch.object(frappe, "get_list", return_value=["GSM"]) as get_list:
			self.assertEqual(search_item_editor_links("YRP Additional Parameter Key", "gsm"), [
				{"name": "GSM", "label": "GSM"},
			])
		get_list.assert_called_once_with(
			"YRP Additional Parameter Key", filters={"name": ["like", "%gsm%"]},
			pluck="name", order_by="name", limit=20,
		)

	def test_attribute_search_rejects_an_unreadable_item_before_searching(self):
		from essdee_yrp.purchase.item_editor import search_attribute_values

		item = self._create_as("purchase_manager", self._dependent_values())["name"]
		frappe.set_user("Guest")
		self.assertFalse(frappe.has_permission("Item", "read", doc=item))
		with patch("essdee_yrp.purchase.item_editor.search_item_attribute_values") as search:
			with self.assertRaises(frappe.PermissionError):
				search_attribute_values(self.stage, item=item)
		search.assert_not_called()

	def _insert_transaction_row(self, doctype, child, field, item):
		parent = frappe.get_doc({"doctype": doctype, "name": frappe.generate_hash(), "docstatus": 0})
		parent.db_insert()
		parentfield = next(
			row.fieldname for row in frappe.get_meta(doctype).fields if row.options == child
		)
		frappe.get_doc({
			"doctype": child, "name": frappe.generate_hash(), "parent": parent.name,
			"parenttype": doctype, "parentfield": parentfield, field: item, "docstatus": 0,
		}).db_insert()
		return parent

	def test_submitted_transaction_rows_warn_without_stock_for_template_and_variant(self):
		from essdee_yrp.purchase.item_editor import get_item_editor
		from essdee_yrp.purchase.item_usage import TRANSACTION_ITEM_LINKS, _item_family_has_yrp_stock

		item = self._create_as("purchase_manager", self._master_values(
			attributes=[self._attribute_row(self.colour, "Red")], primary_attribute=self.colour,
		))["name"]
		variant = get_or_create_variant(item, {self.colour: "Red"})
		self.assertFalse(_item_family_has_yrp_stock(item))
		for doctype, links in TRANSACTION_ITEM_LINKS.items():
			for child, field in links:
				with self.subTest(doctype=doctype, child=child, field=field):
					self._assert_submitted_usage(item, variant, doctype, child, field)
		self.assertFalse(_item_family_has_yrp_stock(item))
		self.assertFalse(get_item_editor(item)["has_item_transactions"])

	def _assert_submitted_usage(self, item, variant, doctype, child, field):
		from essdee_yrp.purchase.item_editor import get_item_editor

		for linked_item in (item, variant):
			parent = self._insert_transaction_row(doctype, child, field, linked_item)
			self.assertFalse(get_item_editor(item)["has_item_transactions"])
			frappe.db.set_value(doctype, parent.name, "docstatus", 1)
			self.assertTrue(get_item_editor(item)["has_item_transactions"])
			frappe.db.set_value(doctype, parent.name, "docstatus", 2)
			self.assertFalse(get_item_editor(item)["has_item_transactions"])

	def test_set_item_disabled_changes_only_disabled_on_item_missing_stage_conversion(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, set_item_disabled

		item = self._create_as("purchase_manager", self._dependent_values(dependent_details=[{
			"value": "Pack", "uom": self.box_uom, "display_name": "Packed", "attributes": [self.size],
		}]))["name"]
		frappe.db.delete("UOM Conversion Detail", {"parent": item, "uom": self.box_uom})
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack uses UOM"):
			self._update_dependent(item, disabled=1)
		before = self._item_configuration(item)
		payload = set_item_disabled(item, 1, get_item_editor(item)["modified"])
		after = self._item_configuration(item)
		self.assertEqual(payload["values"]["disabled"], 1)
		self.assertEqual(after, before)
		self.assertEqual(set_item_disabled(item, 0, payload["modified"])["values"]["disabled"], 0)

	def _item_configuration(self, item):
		doc = frappe.get_doc("Item", item)
		for row in [doc, *doc.get_all_children()]:
			row.modified = None
			row.modified_by = None
		values = doc.as_dict()
		values.pop("disabled")
		return values

	def test_set_item_disabled_requires_write_permission_and_fresh_token(self):
		from essdee_yrp.purchase.item_editor import get_item_editor, set_item_disabled

		item = self._create_as("purchase_manager", self._master_values())["name"]
		modified = get_item_editor(item)["modified"]
		with self.assertRaises(frappe.TimestampMismatchError):
			set_item_disabled(item, 1, "2000-01-01 00:00:00")
		self.assertFalse(frappe.db.get_value("Item", item, "disabled"))
		frappe.set_user(self.fixture_users["purchase_user"])
		with self.assertRaises(frappe.PermissionError):
			set_item_disabled(item, 1, modified)
		self.assertFalse(frappe.db.get_value("Item", item, "disabled"))

	def test_mutations_are_post_only(self):
		from essdee_yrp.purchase.item_editor import create_item, set_item_disabled, update_item

		for method in (create_item, set_item_disabled, update_item):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["POST"])


class TestItemTableValidation(TestCase):
	def setUp(self):
		self.context = ExitStack()
		self.addCleanup(self.context.close)
		self.database = MagicMock()
		self.context.enter_context(patch.object(frappe, "db", self.database))
		self.database.exists.return_value = True
		self.context.enter_context(
			patch("essdee_yrp.purchase.item_tables._", side_effect=lambda message: message)
		)
		self.context.enter_context(
			patch("essdee_yrp.purchase.item_dependent_attribute._", side_effect=lambda message: message)
		)
		self.context.enter_context(patch.object(frappe, "throw", side_effect=self._reject))

	@staticmethod
	def _reject(message, *args, **kwargs):
		raise frappe.ValidationError(message)

	def test_stock_row_is_injected_without_hiding_a_crafted_factor(self):
		from essdee_yrp.purchase.item_tables import parse_item_tables

		self.assertEqual(parse_item_tables({}, "Pieces")["uoms"], [{"uom": "Pieces", "conversion_factor": 1}])
		with self.assertRaisesRegex(frappe.ValidationError, "default Unit of Measure must be 1 in row 1"):
			parse_item_tables({"uoms": [{"uom": "Pieces", "conversion_factor": 2}]}, "Pieces")

	def test_item_usage_runs_one_limited_exists_query_per_transaction_doctype(self):
		from essdee_yrp.purchase.item_usage import TRANSACTION_ITEM_LINKS, has_item_transactions

		with (
			patch("essdee_yrp.purchase.item_usage._item_family_has_yrp_stock", return_value=False),
			patch.object(frappe, "get_all", return_value=["Variant"]),
			patch.object(frappe.db, "sql", return_value=[]) as query,
		):
			self.assertFalse(has_item_transactions("Template"))
		self.assertEqual(query.call_count, len(TRANSACTION_ITEM_LINKS))
		for call in query.call_args_list:
			self.assertIn("exists (", call.args[0])
			self.assertIn("limit 1", call.args[0])
			self.assertEqual(call.args[1]["family"], ["Template", "Variant"])

	def test_fg_packing_context_requires_positive_pieces_per_box(self):
		from essdee_yrp.purchase.item_tables import finished_goods_packing

		for pieces in (None, "", 0, "0", -1):
			with self.subTest(pieces=pieces):
				self.database.get_value.return_value = pieces
				self.assertIsNone(finished_goods_packing("ZZ TEST FG Item"))
		self.database.get_value.return_value = 12
		self.assertEqual(finished_goods_packing("ZZ TEST FG Item"), 12)
		self.database.get_value.assert_called_with("SD YRP FG Item Master", {"item": "ZZ TEST FG Item"}, "pcs_per_box")
		self.database.get_value.reset_mock()
		self.assertIsNone(finished_goods_packing(None))
		self.database.get_value.assert_not_called()

	def test_item_tables_do_not_bypass_native_permlevel_access(self):
		from frappe.model.base_document import BaseDocument

		from essdee_yrp.purchase.item_tables import apply_item_tables, parse_item_tables

		doc = frappe._dict(doctype="Item", flags=frappe._dict(), product_category="ZZ TEST Category")
		doc.set = lambda field, value: doc.update({field: value})
		doc.is_new = lambda: True
		fields = [
			frappe._dict(fieldname=field, fieldtype="Link", permlevel=1)
			for field in ("product_category", "valuation_method")
		]
		with patch.object(frappe, "new_doc", return_value=frappe._dict(valuation_method="FIFO")):
			BaseDocument.reset_values_if_no_permlevel_access(doc, [0], fields)
			self.assertIsNone(doc.product_category)
			apply_item_tables(doc, parse_item_tables({"product_category": "ZZ TEST Category"}, "Pieces"))
			doc.valuation_method = "Moving Average"
			self.assertFalse(doc.flags.get("ignore_permlevel_for_fields"))
			BaseDocument.reset_values_if_no_permlevel_access(doc, [0], fields)
		self.assertIsNone(doc.product_category)
		self.assertEqual(doc.valuation_method, "FIFO")
		self.assertFalse(doc.flags.ignore_permissions)

	def test_nonpositive_nonfinite_and_duplicate_conversions_fail(self):
		from essdee_yrp.purchase.item_tables import parse_item_tables

		for factor in (0, None, "", -1, "NaN", "Infinity", "invalid"):
			with (
				self.subTest(factor=factor),
				self.assertRaisesRegex(frappe.ValidationError, "greater than 0"),
			):
				parse_item_tables({"uoms": [{"uom": "Box", "conversion_factor": factor}]}, "Pieces")
		with self.assertRaisesRegex(frappe.ValidationError, "entered more than once"):
			parse_item_tables({"uoms": [{"uom": "Box", "conversion_factor": 10}] * 2}, "Pieces")

	def test_stage_defaults_and_conversion_checks_use_the_final_value_set(self):
		from essdee_yrp.purchase.item_tables import final_dependent_details, validate_stage_conversions

		values = {
			"primary_attribute": "Size",
			"dependent_details": [{"value": "Pack", "uom": "Box", "attributes": ["Size"]}, {"value": "Removed", "uom": ""}],
		}
		attributes = [{"attribute": "Stage", "values": ["Cut", "Pack"]}, {"attribute": "Size", "values": []}]
		details = final_dependent_details(values, attributes, "Stage", "Pieces")
		self.assertEqual(details["Cut"], {"uom": "Pieces", "attributes": ["Size"]})
		self.assertNotIn("Removed", details)
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack uses UOM Box.*Box → Pieces"):
			validate_stage_conversions(details, [{"uom": "Pieces", "conversion_factor": 1}], "Pieces")
		validate_stage_conversions(details, [{"uom": "Box", "conversion_factor": 10}], "Pieces")

	def test_empty_stage_attributes_fail_for_requested_and_stored_rows(self):
		from essdee_yrp.purchase.item_tables import final_dependent_details

		attributes = [{"attribute": "Stage", "values": ["Pack"]}, {"attribute": "Size"}]
		row = {"value": "Pack", "uom": "Pieces", "attributes": []}
		with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack must use at least one attribute"):
			final_dependent_details({"dependent_details": [row]}, attributes, "Stage", "Pieces")
		with patch("essdee_yrp.purchase.item_tables.dependent_details_payload", return_value=[row]):
			with self.assertRaisesRegex(frappe.ValidationError, "Stage Pack must use at least one attribute"):
				final_dependent_details({}, attributes, "Stage", "Pieces", frappe._dict(dependent_attribute="Stage"))

	def test_stage_variant_name_collisions_compare_sets_and_effective_display_names(self):
		from essdee_yrp.purchase.item_dependent_attribute import (
			stage_variant_name_collisions,
			validate_stage_variant_names,
		)

		for first, second in ((None, ""), ("", " "), ("Same", " Same ")):
			with self.subTest(first=first, second=second):
				details = {
					"Cut": {"display_name": first, "attributes": ["Size", "Colour"]},
					"Pack": {"display_name": second, "attributes": ["Colour", "Size", "Size"], "uom": "Box"},
				}
				self.assertEqual(stage_variant_name_collisions(details), [("Cut", "Pack")])
				with self.assertRaisesRegex(frappe.ValidationError, "Stages Cut and Pack would create variants with the same name. Give one of them a Display Name or tick different attributes."):
					validate_stage_variant_names(details)
		for pack in ({"display_name": "Packed", "attributes": ["Size"]}, {"attributes": ["Colour", "Size"]}):
			details = {"Cut": {"attributes": ["Size"]}, "Pack": pack}
			self.assertEqual(stage_variant_name_collisions(details), [])
			validate_stage_variant_names(details)
		self.assertEqual(stage_variant_name_collisions({}), [])

	def test_stage_name_validation_uses_retained_and_default_final_rows(self):
		from essdee_yrp.purchase.item_dependent_attribute import stage_variant_name_collisions
		from essdee_yrp.purchase.item_tables import final_dependent_details

		attributes = [{"attribute": "Stage", "values": ["Cut", "Pack"]}, {"attribute": "Size"}]
		stored = [{"value": "Cut", "uom": "Pieces", "display_name": "Cut Panel", "attributes": ["Size"]}]
		doc = frappe._dict(dependent_attribute="Stage")
		with patch("essdee_yrp.purchase.item_tables.dependent_details_payload", return_value=stored):
			details = final_dependent_details({"primary_attribute": "Size"}, attributes, "Stage", "Pieces", doc)
			self.assertEqual(stage_variant_name_collisions(details), [])
			details = final_dependent_details({"dependent_details": [
				{"value": "Pack", "uom": "Pieces", "display_name": "Cut Panel", "attributes": ["Size"]},
				{"value": "Removed", "uom": "Pieces", "display_name": "Cut Panel", "attributes": ["Size"]},
			]}, attributes, "Stage", "Pieces", doc)
		self.assertEqual(stage_variant_name_collisions(details), [("Cut", "Pack")])
		self.assertNotIn("Removed", details)

	def test_blank_stage_uom_fails_during_preflight(self):
		from essdee_yrp.purchase.item_tables import final_dependent_details

		with self.assertRaisesRegex(frappe.ValidationError, "Select a valid UOM for Stage Pack"):
			final_dependent_details(
				{"dependent_details": [{"value": "Pack", "uom": ""}]},
				[{"attribute": "Stage", "values": ["Pack"]}],
				"Stage",
				"Pieces",
			)

	def test_parameter_validation_checks_ownership_duplicates_and_optional_value(self):
		from essdee_yrp.purchase.item_tables import parse_item_tables

		self.database.get_value.side_effect = lambda doctype, name, field: (
			name["name"].upper() if doctype == "YRP Additional Parameter Key" else "GSM"
		)
		rows = [
			{"additional_parameter_key": "GSM", "additional_parameter_value": "180"},
			{"additional_parameter_key": "DIA"},
		]
		self.assertIsNone(
			parse_item_tables({"additional_parameters": rows}, "Pieces")["additional_parameters"][1][
				"additional_parameter_value"
			]
		)
		for invalid, message in (
			([{}], "select an Additional Parameter Key"),
			(rows * 2, "is repeated"),
			(
				[{"additional_parameter_key": "DIA", "additional_parameter_value": "180"}],
				"does not belong to Key",
			),
		):
			with self.subTest(rows=invalid), self.assertRaisesRegex(frappe.ValidationError, message):
				parse_item_tables({"additional_parameters": invalid}, "Pieces")

	def test_parameter_casefold_duplicates_and_canonical_name(self):
		from essdee_yrp.purchase.item_tables import parse_item_tables

		self.database.get_value.return_value = "GSM"
		rows = [{"additional_parameter_key": key} for key in ("GSM", "gsm")]
		with self.assertRaisesRegex(frappe.ValidationError, "Additional Parameter Key GSM is repeated"):
			parse_item_tables({"additional_parameters": rows}, "Pieces")
		parsed = parse_item_tables({"additional_parameters": rows[1:]}, "Pieces")
		self.assertEqual(parsed["additional_parameters"][0]["additional_parameter_key"], "GSM")
		self.database.get_value.assert_called_with("YRP Additional Parameter Key", {"name": "gsm"}, "name")

	def test_negative_and_nonfinite_po_excess_fail(self):
		from essdee_yrp.purchase.item_tables import parse_item_tables

		for percentage in (-1, "NaN", "Infinity"):
			with self.assertRaisesRegex(frappe.ValidationError, "greater than or equal to 0"):
				parse_item_tables({"po_excess_allowed_percentage": percentage}, "Pieces")

	def test_child_update_keeps_identity_and_unedited_columns(self):
		from essdee_yrp.purchase.item_tables import _replace_rows

		row = frappe._dict(name="existing-box", uom="Box", conversion_factor=10, custom_value="keep")
		doc = frappe._dict(uoms=[row, frappe._dict(name="old-unit", uom="Unit", conversion_factor=5)])
		doc.set = lambda field, rows: doc.update({field: rows})
		_replace_rows(
			doc,
			"uoms",
			"uom",
			[{"uom": "Box", "conversion_factor": 12}, {"uom": "Pieces", "conversion_factor": 1}],
		)
		self.assertIs(doc.uoms[0], row)
		self.assertEqual((row.name, row.custom_value, row.conversion_factor), ("existing-box", "keep", 12))
		self.assertEqual([row["uom"] for row in doc.uoms], ["Box", "Pieces"])
