import json
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item import yrp_item

from essdee_yrp.item_bom_attribute_mapping import get_item_bom_mapping_combinations
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd import bom_mapping
from essdee_yrp.merch.ipd.payload import BOM_MAPPING
from essdee_yrp.merch.ipd_test_support import SAMPLES, make_user, rolled_back, unapprove

IPD = SAMPLES["standard"]
READER = "_test_ipd_bom_reader@example.com"
BOM_WITH_COLUMNS = "Inner Card Big"
BOM_WITH_SAME = "Fusing Sticker-MoveWarm (XS-2XL)"
BOM_WITHOUT_COLUMNS = "Compo Label 53% Cot,47% Poly(Taffeta)-Premium Thermal"
FIXTURE_COLUMNS = {
	BOM_WITH_COLUMNS: {"item": ["Colour"], "bom": ["Size"], "same": [], "all_same": False},
	BOM_WITH_SAME: {"item": ["Colour"], "bom": ["Colour"], "same": ["Size"], "all_same": False},
	BOM_WITHOUT_COLUMNS: {"item": ["Colour"], "bom": [], "same": [], "all_same": False},
}


class TestBomMappingRules(TestCase):
	def setUp(self):
		def throw_validation(message, *args):
			raise frappe.ValidationError(message)

		self.enterContext(patch.object(bom_mapping, "_", side_effect=lambda message: message))
		self.enterContext(patch.object(frappe, "throw", side_effect=throw_validation))

	def test_same_columns_and_empty_values(self):
		mapping = frappe._dict(
			{
				field: [frappe._dict(attribute="Size", same_attribute=1)]
				for field in ("item_attributes", "bom_item_attributes")
			}
		)
		self.assertEqual(
			bom_mapping.mapping_columns(mapping), {"item": [], "bom": [], "same": ["Size"], "all_same": True}
		)
		self.assertEqual(bom_mapping.clean_rows([], bom_mapping.required_columns(mapping), True), [])
		with self.assertRaisesRegex(frappe.ValidationError, "Add at least one"):
			bom_mapping.clean_rows([], {"item": ["Colour"], "bom": []})

	def test_attributes_and_each_quantity_are_checked(self):
		self.assertEqual(
			bom_mapping.clean_attributes([{"attribute": "Size", "same_attribute": "1"}], ["Size"], "BOM"),
			[{"attribute": "Size", "same_attribute": 1}],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "duplicate"):
			bom_mapping.clean_attributes([{"attribute": "Size"}] * 2, ["Size"], "BOM")
		with self.assertRaisesRegex(frappe.ValidationError, "choose an attribute"):
			bom_mapping.clean_attributes([{"attribute": "Colour"}], ["Size"], "BOM")
		for kind in ("item", "bom"):
			with self.assertRaisesRegex(
				frappe.ValidationError, "quantity cannot be zero|Quantity cannot be zero"
			):
				bom_mapping.clean_rows(
					[{"type": kind, "attribute": "Size", "attribute_value": "XS", "quantity": 0}],
					{"item": ["Size"], "bom": ["Size"]},
				)

	def test_loader_reads_ipd_and_resolves_combinations_and_values(self):
		row = frappe._dict(name="row1", based_on_attribute_mapping=1, attribute_mapping="map1")
		doc = frappe._dict(name="ipd1", item="Garment", item_bom=[row], check_permission=Mock())
		mapping = frappe._dict(
			name="map1",
			modified="now",
			bom_item="Elastic",
			bom_uom="Meter",
			item_attributes=[frappe._dict(attribute="Colour", same_attribute=0)],
			bom_item_attributes=[frappe._dict(attribute="Size", same_attribute=0)],
			values=[
				frappe._dict(index=0, type="item", attribute="Colour", attribute_value="Black", quantity=1)
			],
		)
		with (
			patch.object(frappe, "get_doc", side_effect=[doc, mapping]),
			patch.object(bom_mapping, "shared_bom_mappings", return_value=set()),
			patch.object(yrp_item, "get_parent_item", side_effect=lambda item: item),
			patch.object(
				frappe,
				"get_cached_doc",
				side_effect=lambda doctype, item: frappe._dict(
					attributes=[frappe._dict(attribute="Colour" if item == "Garment" else "Size")]
				),
			),
			patch.object(yrp_item, "_mapping_values", return_value=[]),
			patch.object(yrp_item, "get_global_attribute_values", return_value=["30 mm"]),
			patch.object(
				bom_mapping, "get_item_bom_mapping_combinations", return_value=[{"item_Colour": "Black"}]
			) as combinations,
		):
			detail = bom_mapping.get_bom_mapping("ipd1", "row1")
		doc.check_permission.assert_called_once_with("read")
		combinations.assert_called_once_with("ipd1", "Garment", ["Colour"], ["Size"])
		self.assertEqual(detail["combinations"], [{"Colour": "Black"}])
		self.assertEqual(detail["bom_values"], {"Size": ["30 mm"]})
		self.assertEqual(detail["values"][0]["attribute_value"], "Black")
		self.assertEqual(detail["item_attribute_options"], ["Colour"])
		self.assertEqual(detail["bom_attribute_options"], ["Size"])

	def test_every_line_sets_each_item_and_bom_column_once(self):
		columns = {"item": ["Colour", "Size"], "bom": ["Size", "Colour"]}
		values = [
			{"index": index, "type": kind, "attribute": attribute, "attribute_value": "value", "quantity": 1}
			for index in (0, 3)
			for kind, attributes in columns.items()
			for attribute in attributes
		]
		self.assertEqual(bom_mapping.clean_rows(values, columns), values)
		for position, row in enumerate(values):
			for duplicate in (False, True):
				with self.subTest(index=row["index"], kind=row["type"], duplicate=duplicate):
					invalid = [*values, row] if duplicate else values[:position] + values[position + 1 :]
					with self.assertRaisesRegex(
						frappe.ValidationError, f"every {row['type']} attribute once"
					):
						bom_mapping.clean_rows(invalid, columns)


class TestIpdBomMapping(TestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.enterContext(rolled_back("ipd_bom_dialog"))
		make_user(READER, ["YRP Floor Verify"])
		unapprove(IPD)
		self.ipd = frappe.get_doc("YRP Item Production Detail", IPD)

	def mapped_row(self, bom_item):
		rows = [
			row
			for row in self.ipd.item_bom
			if row.item == bom_item and row.based_on_attribute_mapping and row.attribute_mapping
		]
		self.assertEqual(len(rows), 1, f"Expected one mapped BOM row for {bom_item!r} in {IPD!r}")
		return rows[0]

	def use_mapping(self, bom_item):
		"""Clone the named fixture only after checking the shape this test needs."""
		self.row = self.mapped_row(bom_item)
		mapping = frappe.copy_doc(frappe.get_doc(BOM_MAPPING, self.row.attribute_mapping))
		self.assertEqual(mapping.bom_item, bom_item)
		self.assertEqual(bom_mapping.mapping_columns(mapping), FIXTURE_COLUMNS[bom_item])
		mapping.item_production_detail = IPD
		mapping.insert(ignore_permissions=True)
		frappe.db.set_value(
			self.row.doctype, self.row.name, "attribute_mapping", mapping.name, update_modified=False
		)
		self.mapping = mapping.name
		self.row.attribute_mapping = mapping.name

	def tearDown(self):
		frappe.set_user("Administrator")

	def detail(self, **tables):
		return workspace.get_ipd_bom_mapping(IPD, self.row.name, **tables)

	def save(self, detail, values=None, **tables):
		return workspace.save_ipd_bom_mapping(
			IPD,
			self.row.name,
			detail["values"] if values is None else values,
			detail["mapping_modified"],
			**tables,
		)

	def test_load_matches_desk_combinations_and_display_values(self):
		for bom_item in (BOM_WITH_COLUMNS, BOM_WITH_SAME, BOM_WITHOUT_COLUMNS):
			with self.subTest(bom_item=bom_item):
				self.use_mapping(bom_item)
				self.assert_loaded_mapping(bom_item)

	def assert_loaded_mapping(self, bom_item):
		detail = self.detail()
		mapping = frappe.get_doc(BOM_MAPPING, self.mapping)
		self.assertEqual(detail["item"], self.ipd.item)
		self.assertEqual(detail["bom_item"], mapping.bom_item)
		self.assertEqual(
			detail["bom_uom"],
			mapping.bom_uom or frappe.get_cached_value("Item", mapping.bom_item, "stock_uom"),
		)
		self.assertEqual(detail["item_attribute_options"], yrp_item.get_attributes(self.ipd.item))
		self.assertEqual(detail["bom_attribute_options"], yrp_item.get_attributes(mapping.bom_item))
		for field in ("item_attributes", "bom_item_attributes"):
			self.assertEqual(
				detail[field],
				[
					{"attribute": row.attribute, "same_attribute": row.same_attribute}
					for row in mapping.get(field)
				],
			)
		columns = detail["columns"]
		self.assertEqual(columns, FIXTURE_COLUMNS[bom_item])
		combinations = get_item_bom_mapping_combinations(IPD, self.ipd.item, columns["item"], columns["bom"])
		self.assertTrue(combinations)
		self.assertEqual(
			detail["combinations"],
			[{attr: row[f"item_{attr}"] for attr in columns["item"]} for row in combinations],
		)
		self.assertEqual(
			[row["attribute_value"] for row in detail["values"]],
			[attribute_value(row.attribute_value) for row in mapping.get("values")],
		)
		self.assertTrue(detail["values"])
		self.assertEqual(set(detail["bom_values"]), set(columns["bom"]))
		for attr in columns["bom"]:
			values = yrp_item.get_attribute_values(mapping.bom_item, [attr]).get(attr)
			self.assertEqual(detail["bom_values"][attr], values or yrp_item.get_global_attribute_values(attr))
			self.assertTrue(detail["bom_values"][attr])
		self.assertFalse(detail["is_shared"])

	def test_load_falls_back_to_global_bom_values(self):
		self.use_mapping(BOM_WITH_COLUMNS)
		before = self.detail()
		tables = {
			"item_attributes": [{"attribute": "Colour"}],
			"bom_item_attributes": [{"attribute": "Size"}],
		}
		global_values = yrp_item.get_global_attribute_values("Size")
		self.assertTrue(global_values)
		with (
			patch.object(yrp_item, "_mapping_values", return_value=[]) as item_values,
			patch.object(
				yrp_item, "get_global_attribute_values", wraps=yrp_item.get_global_attribute_values
			) as fallback,
		):
			detail = self.detail(**tables)
			fallback.assert_any_call("Size")
		self.assertTrue(any(call.args[0].attribute == "Size" for call in item_values.call_args_list))
		self.assertEqual(detail["columns"]["bom"], ["Size"])
		self.assertEqual(detail["bom_values"], {"Size": global_values})
		self.assertEqual(self.detail(), before)

	def test_unsaved_tables_generate_without_persisting(self):
		self.use_mapping(BOM_WITHOUT_COLUMNS)
		before = self.detail()
		tables = {
			"item_attributes": [{"attribute": "Colour"}, {"attribute": "Size"}],
			"bom_item_attributes": [],
		}
		detail = self.detail(**{key: json.dumps(value) for key, value in tables.items()})
		self.assertEqual(detail["columns"]["item"], ["Colour", "Size"])
		self.assertEqual(detail["columns"]["bom"], [])
		combinations = get_item_bom_mapping_combinations(IPD, self.ipd.item, ["Colour", "Size"], [])
		self.assertTrue(combinations)
		self.assertEqual(
			detail["combinations"],
			[{attr: row[f"item_{attr}"] for attr in ("Colour", "Size")} for row in combinations],
		)
		for field, rows in tables.items():
			self.assertEqual(detail[field], [{**row, "same_attribute": 0} for row in rows])
		self.assertEqual(self.detail(), before)

	def test_read_permission_and_invalid_rows(self):
		self.use_mapping(BOM_WITH_COLUMNS)
		frappe.set_user(READER)
		self.assertFalse(frappe.has_permission("Item", "read", doc=self.ipd.item))
		self.assertEqual(self.detail()["mapping"], self.mapping)
		tables = {
			"item_attributes": [{"attribute": "Colour"}],
			"bom_item_attributes": [{"attribute": "Size"}],
		}
		self.assertTrue(self.detail(**tables)["bom_values"]["Size"])
		with self.assertRaises(frappe.PermissionError):
			self.save(self.detail())
		frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "not part of this IPD"):
			workspace.get_ipd_bom_mapping(IPD, "missing")
		frappe.db.set_value(self.row.doctype, self.row.name, "attribute_mapping", None, update_modified=False)
		with self.assertRaisesRegex(frappe.ValidationError, "save the IPD"):
			self.detail()

	def test_save_tables_and_values_runs_controller_and_reloads(self):
		self.use_mapping(BOM_WITHOUT_COLUMNS)
		tables = {
			"item_attributes": [{"attribute": "Colour"}, {"attribute": "Size"}],
			"bom_item_attributes": [],
		}
		detail = self.detail(**tables)
		values = [
			{
				"index": index,
				"type": "item",
				"attribute": attr,
				"attribute_value": combo[attr],
				"quantity": 0.7,
			}
			for index, combo in enumerate(detail["combinations"])
			for attr in detail["columns"]["item"]
		]
		self.assertTrue(values)
		controller = type(frappe.get_doc(BOM_MAPPING, self.mapping))
		with patch.object(controller, "validate", autospec=True, side_effect=controller.validate) as validate:
			result = self.save(detail, values, **tables)
			validate.assert_called_once()
		saved = self.detail()
		self.assertEqual(saved["values"], values)
		self.assertEqual(saved["columns"]["item"], ["Colour", "Size"])
		for field, rows in tables.items():
			self.assertEqual(saved[field], [{**row, "same_attribute": 0} for row in rows])
		self.assertEqual(result["bom_mappings"][self.row.name]["rows"], values)
		self.assertNotEqual(saved["mapping_modified"], detail["mapping_modified"])
		with self.assertRaises(frappe.TimestampMismatchError):
			self.save(detail, values, **tables)

	def test_reject_invalid_tables_on_load_and_save(self):
		self.use_mapping(BOM_WITH_COLUMNS)
		detail = self.detail()
		for field, option in (("item_attributes", "Colour"), ("bom_item_attributes", "Size")):
			for rows, message in (
				([{"attribute": "_invalid"}], "choose an attribute"),
				([{"attribute": option}] * 2, "duplicate attribute"),
			):
				tables = {
					"item_attributes": detail["item_attributes"],
					"bom_item_attributes": detail["bom_item_attributes"],
					field: rows,
				}
				with self.subTest(field=field, rows=rows):
					with self.assertRaisesRegex(frappe.ValidationError, message):
						self.detail(**tables)
					with self.assertRaisesRegex(frappe.ValidationError, message):
						self.save(detail, **tables)
		self.assertEqual(self.detail(), detail)

	def test_every_value_row_needs_quantity_and_complete_columns(self):
		self.use_mapping(BOM_WITH_COLUMNS)
		before = self.detail()
		tables = {
			"item_attributes": [{"attribute": "Colour"}, {"attribute": "Size"}],
			"bom_item_attributes": [{"attribute": "Size"}],
		}
		detail = self.detail(**tables)
		self.assertEqual(detail["columns"]["item"], ["Colour", "Size"])
		self.assertEqual(detail["columns"]["bom"], ["Size"])
		self.assertGreater(len(detail["combinations"]), 1)
		self.assertTrue(detail["bom_values"]["Size"])
		# Reuse the named fixture's saved BOM choice, independent of option ordering.
		saved_bom_sizes = {
			row["attribute_value"]
			for row in before["values"]
			if row["type"] == "bom" and row["attribute"] == "Size"
		}
		self.assertTrue(saved_bom_sizes)
		bom_size = min(saved_bom_sizes)
		self.assertIn(bom_size, detail["bom_values"]["Size"])
		valid_values = [
			{
				"index": index,
				"type": kind,
				"attribute": attribute,
				"attribute_value": combo[attribute] if kind == "item" else bom_size,
				"quantity": 1,
			}
			for index, combo in enumerate(detail["combinations"])
			for kind in ("item", "bom")
			for attribute in detail["columns"][kind]
		]
		for position, row in enumerate(valid_values):
			with self.subTest(index=row["index"], kind=row["type"], attribute=row["attribute"]):
				for field, value, message in (
					("quantity", 0, "quantity cannot be zero|Quantity cannot be zero"),
					("attribute_value", "", "choose a value"),
				):
					with self.subTest(field=field):
						values = [dict(value_row) for value_row in valid_values]
						values[position][field] = value
						with self.assertRaisesRegex(frappe.ValidationError, message):
							self.save(detail, values, **tables)
				for duplicate in (False, True):
					with self.subTest(duplicate=duplicate):
						values = (
							[*valid_values, row]
							if duplicate
							else valid_values[:position] + valid_values[position + 1 :]
						)
						with self.assertRaisesRegex(
							frappe.ValidationError, f"every {row['type']} attribute once"
						):
							self.save(detail, values, **tables)
		with self.assertRaisesRegex(frappe.ValidationError, "Add at least one mapping row"):
			self.save(detail, [], **tables)
		self.assertEqual(self.detail(), before)
		self.save(detail, valid_values, **tables)
		saved = self.detail()
		self.assertEqual(saved["values"], valid_values)
		for field, rows in tables.items():
			self.assertEqual(saved[field], [{**row, "same_attribute": 0} for row in rows])

	def test_all_same_accepts_empty_values_and_legacy_save_still_works(self):
		self.use_mapping(BOM_WITH_SAME)
		detail = self.detail()
		self.assertTrue(detail["values"])
		legacy = self.save(detail)
		saved = self.detail()
		self.assertEqual(saved["values"], detail["values"])
		self.assertEqual(legacy["bom_mappings"][self.row.name]["rows"], detail["values"])
		for field in ("item_attributes", "bom_item_attributes"):
			self.assertEqual(saved[field], detail[field])
		tables = {
			field: [{"attribute": "Size", "same_attribute": 1}]
			for field in ("item_attributes", "bom_item_attributes")
		}
		detail = self.detail(**tables)
		all_same_columns = {"item": [], "bom": [], "same": ["Size"], "all_same": True}
		self.assertEqual(detail["columns"], all_same_columns)
		self.assertEqual(detail["combinations"], [])
		self.assertEqual(detail["bom_values"], {})
		result = self.save(detail, [], **tables)
		saved = self.detail()
		self.assertEqual(saved["values"], [])
		self.assertEqual(saved["columns"], all_same_columns)
		self.assertEqual(saved["combinations"], [])
		for field, rows in tables.items():
			self.assertEqual(saved[field], rows)
		self.assertEqual(result["bom_mappings"][self.row.name]["rows"], [])
		self.assertEqual(result["bom_mappings"][self.row.name]["same_attributes"], ["Size"])

	def test_approved_and_shared_mappings_are_rejected(self):
		self.use_mapping(BOM_WITH_COLUMNS)
		detail = self.detail()
		frappe.db.set_value(self.ipd.doctype, IPD, "approval_status", "Approved", update_modified=False)
		with self.assertRaisesRegex(frappe.ValidationError, "Approved IPDs are read only"):
			self.save(detail)
		unapprove(IPD)
		sibling = self.mapped_row(BOM_WITHOUT_COLUMNS)
		frappe.db.set_value(
			sibling.doctype, sibling.name, "attribute_mapping", self.mapping, update_modified=False
		)
		self.assertTrue(self.detail()["is_shared"])
		with self.assertRaisesRegex(frappe.ValidationError, "shared"):
			self.save(detail)
