from unittest import TestCase
from unittest.mock import patch

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
		frappe.set_user("Administrator")
		cls.savepoint = "purchase_item_editor_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(cls.savepoint)
		cls.suffix = frappe.generate_hash(length=8)
		cls.item_group = cls._make_item_group(False)
		cls.group_node = cls._make_item_group(True)
		cls.uom = cls._make_uom(f"Web Item Unit {cls.suffix}")
		cls.secondary_uom = cls._make_uom(f"Web Secondary Unit {cls.suffix}", secondary_only=True)
		cls.colour = cls._make_attribute("Colour", ["Red", "Blue", "Green"])
		cls.size = cls._make_attribute("Size", ["Small", "Medium"])
		cls.accent = cls._make_attribute("Accent", ["Red"])
		cls.length = cls._make_numeric_attribute("Length")
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
				"percentage": f"0.{cls.suffix[:6]}",
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
				self._values(attributes=[{"attribute": self.colour, "values": []}]),
				"at least one value",
			),
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
			self.assertEqual(
				unrestricted_values["values"],
				[{"name": attribute_value_name(self.length, "1"), "label": "1"}],
			)
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

	def test_update_appends_values_before_variants_then_locks_all_attribute_changes(self):
		from essdee_yrp.purchase.item_editor import (
			add_attribute_values,
			get_item_editor,
			update_item,
		)

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
		values["attributes"][0]["values"].append(
			{"name": attribute_value_name(self.colour, "Green"), "label": "Green"}
		)
		values["attributes"][0]["mapping_modified"] = frappe.db.get_value(
			"YRP Item Item Attribute Mapping", mapping.name, "modified"
		)
		doc.reload()
		with self.assertRaisesRegex(frappe.ValidationError, "Locked: variants exist"):
			update_item(doc.name, values, doc.modified)
		with self.assertRaisesRegex(frappe.ValidationError, "Locked: variants exist"):
			add_attribute_values(
				doc.name,
				self.colour,
				["Green"],
				values["attributes"][0]["mapping_modified"],
			)

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

	def test_removing_last_or_price_referenced_value_is_rejected(self):
		from essdee_yrp.purchase.item_editor import update_item

		created = self._create_as(
			"item_manager",
			self._values(attributes=[self._attribute_row(self.colour, "Red", "Blue")]),
		)
		doc = frappe.get_doc("Item", created["name"])
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", doc.attributes[0].mapping)
		base = self._values(
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
		base["attributes"][0]["values"] = []
		with self.assertRaisesRegex(frappe.ValidationError, "last value"):
			update_item(doc.name, base, doc.modified)

		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "YRP Item Price",
				"item_name": doc.name,
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
						"attribute_value": attribute_value_name(self.colour, "Blue"),
					}
				],
			}
		).insert(ignore_permissions=True)
		doc.reload()
		mapping.reload()
		base["attributes"][0] = {
			**self._attribute_row(self.colour, "Red"),
			"mapping_modified": mapping.modified,
		}
		frappe.set_user(self.fixture_users["item_manager"])
		with self.assertRaisesRegex(frappe.ValidationError, "price tier"):
			update_item(doc.name, base, doc.modified)

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

	def test_active_prices_include_only_effective_approved_records_and_resolved_tiers(self):
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
		prices = get_item_editor(item)["active_prices"]

		self.assertEqual([price["name"] for price in prices], [active])
		self.assertNotIn(future, [price["name"] for price in prices])
		self.assertNotIn(expired, [price["name"] for price in prices])
		self.assertNotIn(draft, [price["name"] for price in prices])
		self.assertNotIn(rejected, [price["name"] for price in prices])
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

	def test_empty_mapping_adds_only_new_global_values_and_stays_empty(self):
		from essdee_yrp.purchase.item_editor import add_attribute_values, update_item

		frappe.set_user("Administrator")
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"_Test All Values {frappe.generate_hash(length=8)}",
				"item_name": f"_Test All Values {frappe.generate_hash(length=8)}",
				"item_group": self.item_group,
				"stock_uom": self.uom,
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"is_sales_item": 0,
				"has_variants": 1,
				"variant_based_on": "Item Attribute",
				"attributes": [{"attribute": self.colour}],
			}
		).insert(ignore_permissions=True)
		mapping = frappe.get_doc("YRP Item Item Attribute Mapping", item.attributes[0].mapping)
		self.assertEqual(get_mapping_values(mapping.name), [])

		new_value = f"Purple {frappe.generate_hash(length=6)}"
		frappe.set_user(self.fixture_users["item_manager"])
		result = add_attribute_values(item.name, self.colour, [new_value], mapping.modified)
		self.assertTrue(result["all_values_allowed"])
		self.assertEqual(get_mapping_values(mapping.name), [])
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": self.colour, "attribute_value": new_value},
			)
		)
		mapping.reload()
		second_value = f"Orange {frappe.generate_hash(length=6)}"
		item.reload()
		update_item(
			item.name,
			self._values(
				item.item_name,
				item_group=item.item_group,
				stock_uom=item.stock_uom,
				attributes=[
					{
						"attribute": self.colour,
						"mapping_modified": mapping.modified,
						"values": ["Red", "Blue", "Green", new_value, second_value],
					}
				],
			),
			item.modified,
		)
		self.assertEqual(get_mapping_values(mapping.name), [])
		self.assertTrue(
			frappe.db.exists(
				"Item Attribute Value",
				{"parent": self.colour, "attribute_value": second_value},
			)
		)
		mapping.reload()
		with self.assertRaisesRegex(frappe.ValidationError, "All values are already allowed"):
			add_attribute_values(item.name, self.colour, ["Red"], mapping.modified)

	def test_mutations_are_post_only(self):
		from essdee_yrp.purchase.item_editor import (
			add_attribute_values,
			create_item,
			update_item,
		)

		for method in (create_item, update_item, add_attribute_values):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[method], ["POST"])
