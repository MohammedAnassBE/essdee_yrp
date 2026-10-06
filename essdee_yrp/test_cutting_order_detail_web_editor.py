from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting.order_detail_editor import (
	_merge_authoritative_combination,
	_merge_named_rows,
	_normalize_values,
	_serialize_detail,
	get_detail_editor,
	save_detail,
)


class TestCuttingOrderDetailWebEditor(TestCase):
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
				"set_item_combination": {"values": [{"major_attribute": "Navy", "val": {"Top": "Navy"}}]},
				"stiching_combination": {"values": [{"major_attribute": "Navy", "val": {"Front": "Navy"}}]},
			})

		doc.insert.assert_called_once_with()
		generate.assert_called_once_with(doc, generate.call_args.args[1])
		self.assertEqual(payload["record"]["name"], "COD-NEW")
