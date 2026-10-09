from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting.plan_editor import (
	_assert_field_permissions,
	_merge_authoritative_matrix,
	_normalize_values,
	_serialize_editor,
	change_status,
	get_editor,
	load_lot_items,
	save,
)


def matrix_fixture(quantity=12):
	return [
		{
			"attributes": ["Colour"],
			"primary_attribute": "Size",
			"primary_attribute_values": ["S", "M"],
			"items": [
				{
					"name": "STYLE-001",
					"attributes": {"Colour": "Navy", "Stage": "Piece"},
					"item_keys": {"major_colour": "Navy"},
					"primary_attribute": "Size",
					"values": {"S": {"qty": quantity}, "M": {"qty": quantity + 1}},
					"total_qty": quantity * 2 + 1,
				}
			],
			"size_wise_total": {"S": quantity, "M": quantity + 1},
			"total_sum": quantity * 2 + 1,
		}
	]


class TestCuttingPlanWebEditor(TestCase):
	def test_editor_hides_protected_work_order_without_field_read_permission(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Plan",
			name="CP-001",
			docstatus=0,
			work_order="WO-SECRET",
			cp_status="Draft",
		)

		def permitted(_doctype, permission_type=None):
			return ["lot", "maximum_no_of_plys"] if permission_type in {"read", "write"} else []

		with (
			patch("essdee_yrp.cutting.plan_editor.get_permitted_fields", side_effect=permitted),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
		):
			payload = _serialize_editor(doc, [])

		self.assertNotIn("work_order", payload["record"])
		self.assertFalse(payload["fields"]["show_work_order"])
		self.assertFalse(payload["fields"]["can_edit_work_order"])

	def test_direct_rpc_respects_field_permlevels(self):
		with patch(
			"essdee_yrp.cutting.plan_editor.get_permitted_fields",
			return_value=["lot", "maximum_no_of_plys", "maximum_allow_percent", "cutting_location"],
		):
			with self.assertRaises(frappe.PermissionError):
				_assert_field_permissions({"work_order": "WO-001", "item_details": []})

		with patch(
			"essdee_yrp.cutting.plan_editor.get_permitted_fields",
			return_value=["lot", "maximum_no_of_plys"],
		):
			_assert_field_permissions({"lot": "LOT-001", "item_details": []})

	def test_lot_loader_reuses_authoritative_service_and_assigns_row_identity(self):
		lot_doc = frappe._dict(name="LOT-001", item="STYLE-001", production_detail="IPD-001")
		lot_doc.check_permission = MagicMock()
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=lot_doc),
			patch("essdee_yrp.cutting.plan_editor.get_items", return_value=matrix_fixture()) as get_items,
		):
			payload = load_lot_items("LOT-001")

		lot_doc.check_permission.assert_called_once_with("read")
		get_items.assert_called_once_with("LOT-001")
		self.assertEqual(payload["item"], "STYLE-001")
		self.assertEqual(payload["production_detail"], "IPD-001")
		self.assertEqual(payload["groups"][0]["items"][0]["_row_key"], "g0:r0")

	def test_matrix_merge_accepts_only_authoritative_rows_and_quantity_cells(self):
		authoritative = matrix_fixture()
		incoming = deepcopy(authoritative)
		incoming[0]["items"][0]["_row_key"] = "g0:r0"
		incoming[0]["items"][0]["values"]["S"]["qty"] = 25
		incoming[0]["items"][0]["values"]["M"]["qty"] = 30

		merged = _merge_authoritative_matrix(authoritative, incoming)

		row = merged[0]["items"][0]
		self.assertEqual(row["name"], "STYLE-001")
		self.assertEqual(row["attributes"], {"Colour": "Navy", "Stage": "Piece"})
		self.assertEqual(row["values"], {"S": {"qty": 25.0}, "M": {"qty": 30.0}})
		self.assertEqual(merged[0]["size_wise_total"], {"S": 25.0, "M": 30.0})
		self.assertEqual(merged[0]["total_sum"], 55.0)

	def test_matrix_merge_rejects_unknown_duplicate_missing_or_tampered_rows(self):
		authoritative = matrix_fixture()
		valid = deepcopy(authoritative)
		valid[0]["items"][0]["_row_key"] = "g0:r0"

		unknown = deepcopy(valid)
		unknown[0]["items"][0]["_row_key"] = "g9:r9"
		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_matrix(authoritative, unknown)

		duplicate = deepcopy(valid)
		duplicate[0]["items"].append(deepcopy(duplicate[0]["items"][0]))
		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_matrix(authoritative, duplicate)

		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_matrix(authoritative, [{"items": []}])

		tampered = deepcopy(valid)
		tampered[0]["items"][0]["name"] = "INJECTED-ITEM"
		with self.assertRaises(frappe.ValidationError):
			_merge_authoritative_matrix(authoritative, tampered)

	def test_values_allowlist_rejects_derived_fields(self):
		with self.assertRaises(frappe.ValidationError):
			_normalize_values({"lot": "LOT-001", "cp_status": "Completed", "item_details": []})
		with self.assertRaises(frappe.ValidationError):
			_normalize_values({"lot": "LOT-001", "item": "INJECTED", "item_details": []})

		values = _normalize_values(
			{
				"lot": "LOT-001",
				"is_manual_entry": 1,
				"maximum_no_of_plys": 120,
				"maximum_allow_percent": 5,
				"cutting_location": "Machine Cutting",
				"work_order": "WO-001",
				"item_details": matrix_fixture(),
			}
		)
		self.assertEqual(values["lot"], "LOT-001")
		self.assertEqual(values["maximum_no_of_plys"], 120)

	def test_new_editor_requires_create_permission_and_uses_defaults(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Plan",
			name=None,
			docstatus=0,
			modified=None,
			is_manual_entry=0,
			lot=None,
			item=None,
			maximum_no_of_plys=100,
			maximum_allow_percent=10,
			cutting_location="Manual Cutting",
			work_order=None,
			cp_status="Draft",
			items=[],
			production_detail=None,
		)
		doc.get = lambda key, default=None: dict.get(doc, key, default)

		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.cutting.plan_editor.frappe.new_doc", return_value=doc),
		):
			payload = get_editor()

		permission.assert_any_call("SD YRP Cutting Plan", ptype="create", throw=True)
		self.assertEqual(payload["record"]["maximum_no_of_plys"], 100)
		self.assertEqual(payload["record"]["maximum_allow_percent"], 10)
		self.assertTrue(payload["permissions"]["can_create"])

	def test_save_new_plan_maps_authoritative_lot_and_submits_when_requested(self):
		doc = MagicMock()
		doc.doctype = "SD YRP Cutting Plan"
		doc.name = "CP-NEW-001"
		doc.docstatus = 0
		doc.modified = "2026-10-03 12:00:00"
		lot_doc = frappe._dict(item="STYLE-001", production_detail="IPD-001")
		incoming = matrix_fixture(20)
		incoming[0]["items"][0]["_row_key"] = "g0:r0"

		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.plan_editor.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=lot_doc),
			patch("essdee_yrp.cutting.plan_editor.get_items", return_value=matrix_fixture()),
			patch("essdee_yrp.cutting.plan_editor.get_editor", return_value={"record": {"name": "CP-NEW-001"}}),
		):
			payload = save(
				{
					"lot": "LOT-001",
					"maximum_no_of_plys": 100,
					"maximum_allow_percent": 10,
					"cutting_location": "Manual Cutting",
					"item_details": incoming,
				},
				submit=True,
			)

		doc.update.assert_called_once()
		updated = doc.update.call_args.args[0]
		self.assertEqual(updated["item"], "STYLE-001")
		self.assertEqual(updated["production_detail"], "IPD-001")
		self.assertIn("item_details", updated)
		doc.insert.assert_called_once_with()
		doc.submit.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], "CP-NEW-001")

	def test_existing_draft_save_checks_record_permission_and_staleness(self):
		doc = MagicMock()
		doc.name = "CP-001"
		doc.docstatus = 0
		doc.modified = "newer"
		incoming = matrix_fixture()
		incoming[0]["items"][0]["_row_key"] = "g0:r0"
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True) as permission,
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				save({"lot": "LOT-001", "item_details": incoming}, name="CP-001", expected_modified="older")

		permission.assert_any_call("SD YRP Cutting Plan", ptype="write", doc=doc, throw=True)
		doc.save.assert_not_called()

	def test_submitted_editor_exposes_and_saves_only_permitted_allow_on_submit_field(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Plan",
			name="CP-001",
			docstatus=1,
			modified="same",
			work_order="WO-OLD",
			cp_status="Planned",
		)
		doc.meta = frappe._dict(fields=[
			frappe._dict(fieldname="work_order", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="maximum_no_of_plys", allow_on_submit=0, hidden=0, read_only=0),
		])
		doc.meta.get_field = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		doc.update = MagicMock(side_effect=lambda values: dict.update(doc, values))
		doc.save = MagicMock()

		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.cutting.plan_editor.get_permitted_fields",
				side_effect=lambda _doctype, permission_type=None: ["work_order", "maximum_no_of_plys"],
			),
			patch(
				"essdee_yrp.cutting.plan_editor.get_editor",
				return_value={"record": {"name": doc.name, "docstatus": 1, "work_order": "WO-NEW"}},
			),
		):
			editor = _serialize_editor(doc, [])
			result = save({"work_order": "WO-NEW"}, name=doc.name, expected_modified="same")

		self.assertTrue(editor["permissions"]["can_update_after_submit"])
		self.assertEqual(editor["fields"]["allow_on_submit_fields"], ["work_order"])
		self.assertEqual(doc.work_order, "WO-NEW")
		doc.save.assert_called_once_with()
		self.assertEqual(result["record"]["work_order"], "WO-NEW")

	def test_submitted_editor_rejects_non_allow_on_submit_field(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Plan",
			name="CP-001",
			docstatus=1,
			modified="same",
			work_order="WO-OLD",
		)
		doc.meta = frappe._dict(fields=[
			frappe._dict(fieldname="work_order", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="maximum_no_of_plys", allow_on_submit=0, hidden=0, read_only=0),
		])
		doc.meta.get_field = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		doc.save = MagicMock()
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.plan_editor.get_permitted_fields", return_value=["work_order", "maximum_no_of_plys"]),
			self.assertRaisesRegex(frappe.ValidationError, "Allow on Submit"),
		):
			save({"maximum_no_of_plys": 120}, name=doc.name, expected_modified="same")
		doc.save.assert_not_called()

	def test_direct_permission_denial_is_not_bypassed(self):
		with patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				get_editor()

	def test_status_actions_call_native_lifecycle_and_amend(self):
		doc = MagicMock(name="plan")
		doc.name = "CP-001"
		doc.modified = "same"
		doc.docstatus = 0
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.plan_editor.get_editor", return_value={"record": {"name": "CP-001"}}),
		):
			change_status("CP-001", "submit", "same")
		doc.submit.assert_called_once_with()

		doc.docstatus = 1
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.plan_editor.get_editor", return_value={"record": {"name": "CP-001"}}),
		):
			change_status("CP-001", "cancel", "same")
		doc.cancel.assert_called_once_with()

		doc.docstatus = 2
		amended = MagicMock()
		amended.name = "CP-002"
		with (
			patch("essdee_yrp.cutting.plan_editor.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.plan_editor.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.plan_editor.frappe.copy_doc", return_value=amended),
			patch("essdee_yrp.cutting.plan_editor.get_editor", return_value={"record": {"name": "CP-002"}}),
		):
			payload = change_status("CP-001", "amend", "same")
		self.assertEqual(amended.amended_from, "CP-001")
		self.assertEqual(amended.docstatus, 0)
		amended.insert.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], "CP-002")
