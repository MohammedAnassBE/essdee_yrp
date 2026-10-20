from copy import deepcopy
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe

from essdee_yrp.api.print import get_desk_print_formats
from essdee_yrp.cutting.order_workspace import (
	_build_detail_matrix,
	_merge_order_matrix,
	_normalize_order_values,
	change_order_status,
	get_order_editor,
	get_order_workspace,
	save_order,
	update_completed_items,
)


def detail_data():
	return {
		"item": "STYLE-001",
		"is_set_item": 1,
		"colours": ["Navy"],
		"sizes": ["S", "M"],
		"parts": ["Top", "Bottom"],
		"items": [
			{"colour": "Navy", "part": "Top", "major_colour": "Navy"},
			{"colour": "Black", "part": "Bottom", "major_colour": "Navy"},
		],
	}


class TestCuttingOrderWebWorkspace(TestCase):
	def test_editor_honours_explicit_detail_instead_of_saved_detail(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Order",
			name="CO-001",
			cutting_order_detail="COD-SAVED",
			items_json='{"items":[]}',
		)
		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.cutting.order_workspace.get_cutting_order_detail_data",
				return_value=detail_data(),
			) as get_detail,
			patch(
				"essdee_yrp.cutting.order_workspace._overlay_native_quantities"
			) as overlay,
		):
			payload = get_order_editor("CO-001", "COD-SELECTED")

		get_detail.assert_called_once_with("COD-SELECTED")
		overlay.assert_not_called()
		self.assertEqual(payload["detail"]["item"], "STYLE-001")

	def test_detail_projection_builds_shared_quantity_matrix(self):
		matrix = _build_detail_matrix(detail_data())
		self.assertEqual(matrix[0]["primary_attribute_values"], ["S", "M"])
		self.assertEqual(matrix[0]["items"][0]["_row_key"], "g0:r0")
		self.assertEqual(matrix[0]["items"][1]["attributes"], {"Colour": "Black", "Part": "Bottom"})
		self.assertEqual(matrix[0]["items"][0]["values"], {"S": {"qty": 0}, "M": {"qty": 0}})

	def test_order_matrix_rejects_unknown_duplicate_and_tampered_rows(self):
		authoritative = _build_detail_matrix(detail_data())
		incoming = deepcopy(authoritative)
		incoming[0]["items"][0]["values"]["S"]["qty"] = 25
		merged = _merge_order_matrix(authoritative, incoming)
		self.assertEqual(merged[0]["items"][0]["values"]["S"]["qty"], 25.0)

		unknown = deepcopy(incoming)
		unknown[0]["items"][0]["_row_key"] = "g9:r9"
		with self.assertRaises(frappe.ValidationError):
			_merge_order_matrix(authoritative, unknown)
		duplicate = deepcopy(incoming)
		duplicate[0]["items"].append(deepcopy(duplicate[0]["items"][0]))
		with self.assertRaises(frappe.ValidationError):
			_merge_order_matrix(authoritative, duplicate)
		tampered = deepcopy(incoming)
		tampered[0]["items"][0]["attributes"]["Part"] = "Injected"
		with self.assertRaises(frappe.ValidationError):
			_merge_order_matrix(authoritative, tampered)

	def test_order_values_reject_calculated_fields(self):
		for fieldname in ("item", "is_set_item", "co_status", "lay_no", "completed_items_json"):
			with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
				_normalize_order_values({"cutting_order_detail": "COD-001", fieldname: "tampered"})

	def test_save_maps_detail_owned_identity_and_native_items_json(self):
		doc = MagicMock()
		doc.name = "CO-NEW"
		doc.docstatus = 0
		doc.modified = "same"
		matrix = _build_detail_matrix(detail_data())
		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.order_workspace.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.get_cutting_order_detail_data", return_value=detail_data()),
			patch("essdee_yrp.cutting.order_workspace.get_order_editor", return_value={"record": {"name": "CO-NEW"}}),
		):
			payload = save_order({
				"cutting_order_detail": "COD-001",
				"cutting_location": "Machine Cutting",
				"maximum_no_of_plys": 100,
				"maximum_allow_percent": 10,
				"item_details": matrix,
			}, submit=True)

		updated = doc.update.call_args.args[0]
		self.assertEqual(updated["item"], "STYLE-001")
		self.assertEqual(updated["is_set_item"], 1)
		self.assertIn('"quantities"', updated["items_json"])
		doc.insert.assert_called_once_with()
		doc.submit.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], "CO-NEW")

	def test_workspace_uses_planned_service_related_ordering_and_independent_child_permissions(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Order",
			name="CO-001",
			docstatus=1,
			modified="same",
			cutting_order_detail="COD-001",
			co_status="Submitted",
			cutting_location="Machine Cutting",
			item="STYLE-001",
			lay_no=2,
			maximum_no_of_plys=100,
			maximum_allow_percent=10,
			items_json='{"items":[]}',
			completed_items_json='{"items":[{"completed":true}]}',
			incomplete_items_json='{"items":[]}',
		)
		doc.has_permission = MagicMock(side_effect=lambda ptype: ptype in {"read", "write", "print"})
		planned = [{"items": [{"attributes": {"Colour": "Navy"}}]}]

		def has_permission(doctype, ptype="read", **kwargs):
			if doctype == "SD YRP Cutting Marker":
				return ptype in {"read", "create"}
			if doctype == "SD YRP Cutting LaySheet":
				return ptype == "read"
			return True

		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", side_effect=has_permission),
			patch("essdee_yrp.cutting.order_workspace.frappe.get_list", side_effect=[[{"name": "CM-2"}], [{"name": "CLS-2"}]]) as get_list,
			patch("essdee_yrp.cutting.order_workspace.get_order_editor", return_value={"matrix": {"groups": []}}),
			patch("essdee_yrp.cutting.order_workspace.get_cutting_order_planned_vs_actual", return_value=planned) as get_planned,
			patch("essdee_yrp.cutting.order_workspace.get_document_print_formats", return_value=[{"label": "Cutting Order", "format": "Essdee Cutting Order"}]),
		):
			payload = get_order_workspace("CO-001")

		get_planned.assert_called_once_with("CO-001")
		self.assertEqual(payload["completed_items"]["items"][0]["completed"], True)
		self.assertEqual(payload["planned_detail"], planned)
		self.assertTrue(payload["permissions"]["can_create_marker"])
		self.assertFalse(payload["permissions"]["can_create_laysheet"])
		self.assertTrue(payload["actions"]["can_calculate_laysheets"])
		self.assertEqual(get_list.call_args_list[0].kwargs["order_by"], "modified desc")
		self.assertEqual(get_list.call_args_list[1].kwargs["order_by"], "modified desc")

	def test_status_actions_enforce_state_permission_and_staleness(self):
		doc = MagicMock()
		doc.name = "CO-001"
		doc.modified = "same"
		doc.docstatus = 0
		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", return_value=True) as permission,
			patch("essdee_yrp.cutting.order_workspace.get_order_editor", return_value={"record": {"name": "CO-001"}}),
		):
			change_order_status("CO-001", "submit", "same")
		permission.assert_any_call("SD YRP Cutting Order", ptype="submit", doc=doc, throw=True)
		doc.submit.assert_called_once_with()

		doc.modified = "newer"
		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", return_value=True),
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				change_order_status("CO-001", "submit", "older")

	def test_cutting_order_print_formats_are_registered(self):
		names = ["Essdee Cutting Order", "Essdee Cutting Order CCR", "Essdee Cutting Order Summary"]
		with (
			patch.object(frappe, "get_all", return_value=[{"name": name} for name in reversed(names)]),
			patch.object(frappe, "get_meta", return_value=frappe._dict(default_print_format="")),
			patch.object(frappe.db, "get_single_value", return_value=0),
		):
			self.assertEqual(get_desk_print_formats("SD YRP Cutting Order"), ["Standard", *reversed(names)])

	def test_completed_update_accepts_only_flags_from_the_browser(self):
		doc = frappe._dict(
			doctype="SD YRP Cutting Order",
			name="CO-001",
			docstatus=1,
			modified="same",
			completed_items_json='{"items":[{"attributes":{"Colour":"Navy"},"values":{"S":12},"completed":false}]}',
		)
		doc.save = MagicMock()
		incoming = {
			"items": [{
				"attributes": {"Colour": "Injected"},
				"values": {"S": 999},
				"completed": True,
			}],
		}
		with (
			patch("essdee_yrp.cutting.order_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.order_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.order_workspace.get_order_workspace", return_value={"record": {"name": "CO-001"}}),
		):
			update_completed_items("CO-001", incoming, "same")

		saved = frappe.parse_json(doc.completed_items_json)
		self.assertEqual(saved["items"][0]["attributes"], {"Colour": "Navy"})
		self.assertEqual(saved["items"][0]["values"], {"S": 12})
		self.assertTrue(saved["items"][0]["completed"])
		doc.save.assert_called_once_with()
