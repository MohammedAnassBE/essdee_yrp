import json
from copy import deepcopy
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting.order_detail_editor import (
	_merge_authoritative_combination,
	_merge_named_rows,
	_normalize_values,
	_save_authoritative_combinations,
	_serialize_detail,
	get_detail_editor,
	save_detail,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order_detail.sd_yrp_cutting_order_detail import (
	SDYRPCuttingOrderDetail,
)
from essdee_yrp.ipd_ui import fetch_combination_items


def combination_fixture(attributes):
	return {
		"attributes": attributes,
		"values": [
			{"major_attribute": colour, "val": dict.fromkeys(attributes, colour)}
			for colour in ("Navy", "White")
		],
	}


class TestCuttingOrderDetailWebEditor(TestCase):
	def test_empty_ui_combinations_use_server_generated_values(self):
		for attributes in (["Front", "Back"], ["Top", "Bottom"]):
			expected = combination_fixture(attributes)
			for incoming in (None, {}, {"attributes": []}, {"attributes": [], "values": []}, {"values": None}):
				with self.subTest(attributes=attributes, incoming=incoming):
					self.assertEqual(_merge_authoritative_combination(expected, incoming, "Combination"), expected)

	def test_reordered_attributes_accept_cell_edits_and_keep_server_order(self):
		for attributes, label in ((["Front", "Back"], "Panel Combination"), (["Top", "Bottom"], "Set Item Combination")):
			with self.subTest(label=label):
				expected = combination_fixture(attributes)
				incoming = deepcopy(expected)
				incoming["attributes"].reverse()
				incoming["values"].reverse()
				incoming["values"][1]["val"][attributes[0]] = "Blue"
				merged = _merge_authoritative_combination(expected, incoming, label)
				self.assertEqual(merged["attributes"], attributes)
				self.assertEqual(list(merged["values"][0]["val"]), attributes)
				self.assertEqual(merged["values"][0]["val"][attributes[0]], "Blue")
				self.assertEqual(expected["values"][0]["val"][attributes[0]], "Navy")

	def test_real_combination_coordinate_changes_still_require_regeneration(self):
		for attributes in (["Front", "Back"], ["Top", "Bottom"]):
			expected = combination_fixture(attributes)
			invalid_attributes = [[], attributes[:1], [*attributes, "Sleeve"], [attributes[0], "Renamed"], [attributes[0], attributes[0]], [*attributes, attributes[0]]]
			for changed in invalid_attributes:
				with self.subTest(attributes=changed), self.assertRaises(frappe.ValidationError):
					_merge_authoritative_combination(expected, {**deepcopy(expected), "attributes": changed}, "Combination")
			for rows in (expected["values"][:1], [*expected["values"], expected["values"][0]], [{"major_attribute": "Unknown", "val": dict.fromkeys(attributes, "Blue")} ]):
				with self.subTest(rows=rows), self.assertRaises(frappe.ValidationError):
					_merge_authoritative_combination(expected, {**deepcopy(expected), "values": rows}, "Combination")
			for columns in ({attributes[0]: "Blue"}, {**dict.fromkeys(attributes, "Blue"), "Injected": "Blue"}):
				incoming = deepcopy(expected)
				incoming["values"][0]["val"] = columns
				with self.subTest(columns=columns), self.assertRaises(frappe.ValidationError):
					_merge_authoritative_combination(expected, incoming, "Combination")

	def test_existing_combinations_resave_and_roundtrip_native_child_rows(self):
		for is_set_item in (0, 1):
			with self.subTest(is_set_item=is_set_item):
				self._assert_existing_combination_roundtrip(is_set_item)

	def _assert_existing_combination_roundtrip(self, is_set_item):
		panels = combination_fixture(["Front", "Back"])
		parts = combination_fixture(["Top", "Bottom"])
		doc = self._combination_doc(is_set_item)
		with (
			patch("essdee_yrp.cutting.order_detail_editor.get_co_new_combination", return_value=panels),
			patch("essdee_yrp.cutting.order_detail_editor.get_new_combination", return_value=parts),
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order_detail.sd_yrp_cutting_order_detail.get_mapping_document", return_value=SimpleNamespace(values=[frappe._dict(attribute_value=part) for part in ("Top", "Bottom")])),
		):
			_save_authoritative_combinations(doc, {
				"set_item_combination": {"attributes": [], "values": []},
				"stiching_combination": {"attributes": [], "values": []},
			})
			incoming = self._stored_combinations(doc, is_set_item)
			self.assertEqual(incoming["stiching_combination"]["attributes"], ["Back", "Front"])
			_save_authoritative_combinations(doc, incoming)
			self.assertEqual(self._stored_combinations(doc, is_set_item), incoming)
			incoming["stiching_combination"]["values"][0]["val"]["Front"] = "Blue"
			_save_authoritative_combinations(doc, {**incoming, "regenerate_combinations": "0"})
			self.assertEqual(json.loads(doc.stiching_item_detail)["values"][0]["val"]["Front"], "Blue")
			self.assertEqual(fetch_combination_items([dict(row) for row in doc.stiching_item_combination_details])["values"], incoming["stiching_combination"]["values"])
			self.assertEqual(len(doc.stiching_item_combination_details), 4)
			# Explicit regeneration replaces stale cells in both matrices with server defaults.
			if is_set_item:
				incoming["set_item_combination"]["attributes"] = ["Stale Part"]
			_save_authoritative_combinations(doc, {**incoming, "regenerate_combinations": True})
			self.assertEqual(json.loads(doc.stiching_item_detail), panels)
			if is_set_item:
				self.assertEqual(json.loads(doc.set_item_detail), parts)

	def _combination_doc(self, is_set_item=0):
		doc = frappe._dict(
			name="COD-001", is_set_item=is_set_item, stiching_attribute="Panel", set_item_attribute="Part",
			major_panel_value="Front", major_attribute_value="Top", is_same_colour=0,
			attribute_values=[frappe._dict(attribute_value=colour) for colour in ("Navy", "White")],
			item_attributes=[frappe._dict(attribute="Panel", mapping="PANELS"), frappe._dict(attribute="Part", mapping="PARTS")],
			stiching_item_details=[
				frappe._dict(stiching_attribute_value="Front", set_item_attribute_value="Top", is_default=1),
				frappe._dict(stiching_attribute_value="Back", set_item_attribute_value="Bottom", is_default=1),
			],
		)
		doc.is_new = lambda: False
		doc.set = lambda field, value: doc.__setitem__(field, [frappe._dict(row) for row in value] if isinstance(value, list) else value)
		doc.save = MagicMock(side_effect=lambda: SDYRPCuttingOrderDetail.before_validate(doc))
		doc.reload = MagicMock()
		return doc

	def test_generate_after_adding_colour_and_removing_panel_but_save_rejects_stale_coordinates(self):
		doc = self._combination_doc()
		doc.check_permission = MagicMock()
		mapping = SimpleNamespace(
			values=[frappe._dict(attribute_value=panel) for panel in ("Front", "Back")],
			check_permission=MagicMock(),
		)
		with (
			patch("essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order_detail.sd_yrp_cutting_order_detail.get_mapping_document", return_value=mapping),
			patch.object(frappe, "get_doc", return_value=doc),
		):
			_save_authoritative_combinations(doc, {"stiching_combination": {"attributes": [], "values": []}})
			incoming = self._stored_combinations(doc, 0)
			doc.attribute_values.append(frappe._dict(attribute_value="Red"))
			with self.assertRaisesRegex(frappe.ValidationError, "rows changed.*Regenerate"):
				_save_authoritative_combinations(doc, {**incoming, "regenerate_combinations": False})
			_save_authoritative_combinations(doc, {**incoming, "regenerate_combinations": True})
			incoming = self._stored_combinations(doc, 0)
			self.assertEqual({row["major_attribute"] for row in incoming["stiching_combination"]["values"]}, {"Navy", "White", "Red"})
			self.assertEqual(len(doc.stiching_item_combination_details), 6)
			mapping.values.pop()
			doc.stiching_item_details.pop()
			with self.assertRaisesRegex(frappe.ValidationError, "attributes changed.*Regenerate"):
				_save_authoritative_combinations(doc, incoming)
			_save_authoritative_combinations(doc, {**incoming, "regenerate_combinations": "1"})
			stored = self._stored_combinations(doc, 0)["stiching_combination"]
			self.assertEqual(stored["attributes"], ["Front"])
			self.assertTrue(all(set(row["val"]) == {"Front"} for row in stored["values"]))
			self.assertEqual(len(doc.stiching_item_combination_details), 3)

	def test_regeneration_is_an_accepted_editor_option(self):
		self.assertTrue(_normalize_values({"item": "STYLE-001", "regenerate_combinations": True})["regenerate_combinations"])

	def _stored_combinations(self, doc, is_set_item):
		values = {"stiching_combination": fetch_combination_items([dict(row) for row in doc.stiching_item_combination_details])}
		if is_set_item:
			values["set_item_combination"] = fetch_combination_items([dict(row) for row in doc.set_item_combination_details])
			self.assertEqual(json.loads(doc.set_item_detail)["values"], values["set_item_combination"]["values"])
			self.assertEqual(len(doc.set_item_combination_details), 4)
		return values

	def test_existing_attribute_mapping_identity_cannot_be_retargeted(self):
		existing = [frappe._dict(name="ATTR-1", attribute="Size", mapping="MAP-SIZE")]
		with self.assertRaises(frappe.ValidationError):
			_merge_named_rows(
				existing,
				[{"_row_key": "ATTR-1", "attribute": "Colour", "mapping": "MAP-COLOUR"}],
				("attribute", "mapping"),
				("attribute", "mapping"),
			)

		rows = _merge_named_rows(
			existing,
			[{"_row_key": "ATTR-1"}],
			("attribute", "mapping"),
			("attribute", "mapping"),
			("mapping",),
		)
		self.assertEqual(rows, [{"name": "ATTR-1", "attribute": "Size", "mapping": "MAP-SIZE"}])

		with self.assertRaises(frappe.ValidationError):
			_merge_named_rows(
				[],
				[{"attribute": "Size", "mapping": "MAP-FOREIGN"}],
				("attribute", "mapping"),
				("attribute", "mapping"),
				("mapping",),
			)

	def test_new_editor_requires_create_and_applies_settings_defaults(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Order Detail",
			name=None,
			docstatus=0,
			modified=None,
			item="STYLE-001",
			version=0,
			primary_attribute="Size",
			packing_attribute="Colour",
			stiching_attribute="Panel",
			set_item_attribute="Part",
			attribute_no=0,
			is_set_item=0,
			major_attribute_value=None,
			major_panel_value=None,
			is_same_colour=0,
			cloth_detail_json="[]",
			item_attributes=[],
			attribute_values=[],
			stiching_item_details=[],
			set_item_combination_details=[],
			stiching_item_combination_details=[],
		)
		settings = frappe._dict(
			default_primary_attribute="Size",
			default_packing_attribute="Colour",
			default_stitching_attribute="Panel",
			default_set_item_attribute="Part",
		)
		with (
			patch("essdee_yrp.cutting.order_detail_editor.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.cutting.order_detail_editor.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_detail_editor.frappe.get_cached_doc", return_value=settings),
		):
			payload = get_detail_editor(item="STYLE-001")

		permission.assert_any_call("SD YRP Cutting Order Detail", ptype="create", throw=True)
		self.assertEqual(payload["record"]["item"], "STYLE-001")
		self.assertEqual(payload["record"]["primary_attribute"], "Size")
		self.assertEqual(payload["record"]["packing_attribute"], "Colour")
		self.assertTrue(payload["permissions"]["can_create"])

	def test_projection_includes_colours_sizes_panels_and_derived_combinations(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Order Detail",
			name="COD-001",
			docstatus=0,
			modified="same",
			item="STYLE-001",
			version=1,
			primary_attribute="Size",
			packing_attribute="Colour",
			stiching_attribute="Panel",
			set_item_attribute="Part",
			attribute_no=1,
			is_set_item=1,
			major_attribute_value="TOP",
			major_panel_value="Front",
			is_same_colour=0,
			cloth_detail_json='[{"name1":"Main"}]',
			item_attributes=[
				frappe._dict(name="ATTR-1", attribute="Size", mapping="MAP-SIZE"),
				frappe._dict(name="ATTR-2", attribute="Colour", mapping="MAP-COLOUR"),
			],
			attribute_values=[frappe._dict(name="COLOUR-1", attribute_value="Navy")],
			stiching_item_details=[frappe._dict(name="PANEL-1", stiching_attribute_value="Front", set_item_attribute_value="Top", quantity=1, is_default=1)],
			set_item_combination_details=[frappe._dict(name="SET-1")],
			stiching_item_combination_details=[frappe._dict(name="STITCH-1")],
		)
		mapping_values = {
			"MAP-SIZE": [frappe._dict(attribute_value="S"), frappe._dict(attribute_value="M")],
			"MAP-COLOUR": [frappe._dict(attribute_value="Navy")],
		}

		def mapping(name, cached=True):
			return frappe._dict(values=mapping_values[name])

		with (
			patch("essdee_yrp.cutting.order_detail_editor.get_mapping_document", side_effect=mapping),
			patch("essdee_yrp.cutting.order_detail_editor.fetch_combination_items", side_effect=[{"attributes": ["Part"], "values": [{"major_attribute": "Navy"}]}, {"attributes": ["Panel"], "values": [{"major_attribute": "Navy"}]}]),
			patch("essdee_yrp.cutting.order_detail_editor._permission_flags", return_value={"can_write": True}),
		):
			payload = _serialize_detail(doc)

		self.assertEqual(payload["attributes"][0]["values"], ["S", "M"])
		self.assertEqual(payload["colours"][0]["attribute_value"], "Navy")
		self.assertEqual(payload["panels"][0]["stiching_attribute_value"], "Front")
		self.assertEqual(payload["set_item_combination"]["values"][0]["major_attribute"], "Navy")
		self.assertEqual(payload["stiching_combination"]["values"][0]["major_attribute"], "Navy")
		self.assertEqual(payload["cloth_details"], [{"name1": "Main"}])

	def test_named_child_rows_keep_identity_and_reject_unknown_or_duplicate_keys(self):
		existing = [frappe._dict(name="ROW-1", attribute_value="Navy")]
		merged = _merge_named_rows(
			existing,
			[{"_row_key": "ROW-1", "attribute_value": "Black"}, {"attribute_value": "White"}],
			("attribute_value",),
		)
		self.assertEqual(merged, [{"name": "ROW-1", "attribute_value": "Black"}, {"attribute_value": "White"}])

		with self.assertRaises(frappe.ValidationError):
			_merge_named_rows(existing, [{"_row_key": "ROW-X", "attribute_value": "Black"}], ("attribute_value",))
		with self.assertRaises(frappe.ValidationError):
			_merge_named_rows(existing, [{"_row_key": "ROW-1"}, {"_row_key": "ROW-1"}], ("attribute_value",))

	def test_detail_values_reject_controller_owned_fields_and_raw_combinations(self):
		for fieldname in ("version", "primary_attribute", "packing_attribute", "stiching_attribute", "set_item_combination_details"):
			with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
				_normalize_values({"item": "STYLE-001", fieldname: "tampered"})

	def test_existing_detail_checks_write_permission_and_stale_timestamp(self):
		doc = MagicMock()
		doc.name = "COD-001"
		doc.modified = "newer"
		with (
			patch("essdee_yrp.cutting.order_detail_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_detail_editor.frappe.has_permission", return_value=True) as permission,
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				save_detail({"item": "STYLE-001"}, name="COD-001", expected_modified="older")

		permission.assert_any_call("SD YRP Cutting Order Detail", ptype="write", doc=doc, throw=True)
		doc.save.assert_not_called()

	def test_combination_merge_rejects_browser_invented_rows_and_columns(self):
		expected = {"attributes": ["Top", "Bottom"], "values": [{"major_attribute": "Navy", "val": {"Top": "Navy", "Bottom": None}}]}
		incoming = {"attributes": ["Top", "Bottom"], "values": [{"major_attribute": "Navy", "val": {"Top": "Navy", "Bottom": "Blue"}}]}
		self.assertEqual(_merge_authoritative_combination(expected, incoming, "Set")["values"][0]["val"]["Bottom"], "Blue")
		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_combination(expected, {"attributes": ["Top"], "values": incoming["values"]}, "Set")
		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_combination(expected, {"attributes": ["Top", "Bottom"], "values": [{"major_attribute": "Injected", "val": {"Top": "X", "Bottom": "Y"}}]}, "Set")

	def test_new_detail_generates_combinations_on_server_after_insert(self):
		doc = MagicMock()
		doc.name = "COD-NEW"
		doc.modified = "same"
		with (
			patch("essdee_yrp.cutting.order_detail_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.order_detail_editor.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_detail_editor._save_authoritative_combinations") as generate,
			patch("essdee_yrp.cutting.order_detail_editor.get_detail_editor", return_value={"record": {"name": "COD-NEW"}}),
		):
			payload = save_detail({
				"item": "STYLE-001",
				"attribute_no": 1,
				"is_set_item": 1,
				"attributes": [],
				"colours": [{"attribute_value": "Navy"}],
				"panels": [{"stiching_attribute_value": "Front", "set_item_attribute_value": "Top", "quantity": 1, "is_default": 1}],
				"cloth_details": [],
				"set_item_combination": {"attributes": [], "values": []},
				"stiching_combination": {"attributes": [], "values": []},
			})

		doc.insert.assert_called_once_with()
		generate.assert_called_once_with(doc, generate.call_args.args[1])
		self.assertEqual(payload["record"]["name"], "COD-NEW")
