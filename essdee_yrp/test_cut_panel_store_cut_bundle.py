import re
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cut_panel_store.cut_bundle_workspace import (
	_authoritative_bundle_values,
	confirm_cut_bundle_print,
	execute_cut_bundle_command,
	get_cut_bundle_editor,
	get_cut_bundle_print_data,
	preview_cut_bundle_source,
	save_cut_bundle,
)


class TestCutBundleDialogContract(TestCase):
	def test_template_does_not_pass_events_to_defaulted_handler_arguments(self):
		source = (Path(__file__).parent.parent / "frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue").read_text()
		template = source.split("<script setup>")[0]
		self.assertIn('@click="preview()"', template)
		for event, handler in re.findall(r'@([\w:.-]+)="(\w+)"', template):
			signature = re.search(rf"function {handler}\(([^)]*)\)", source)
			self.assertIsNotNone(signature, f"Audit {event}: {handler}")
			self.assertNotIn("=", signature[1], f"{event} passes a payload to {handler}")
		self.assertIn("await preview(sequence, requestedDocumentName)", source)

	def test_preview_cleanup_is_owned_by_latest_request_and_source_changes_invalidate_it(self):
		source = (Path(__file__).parent.parent / "frontend/src/departments/cut-panel-store/CutBundleEditDialog.vue").read_text()
		self.assertIn('if (sequence === previewSequence && acting.value === "preview") acting.value = ""', source)
		self.assertIn("function sourceChanged() { invalidatePreview();", source)
		self.assertIn("function colourChanged() { invalidatePreview();", source)


class TestCutPanelStoreCutBundleWorkspace(UnitTestCase):
	def setUp(self):
		super().setUp()
		self.available = {
			"panels": ["Front", "Back"],
			"is_set_item": 0,
			"data": {
				"Navy": {
					"part": None,
					"data": [{
						"lay_no": 1,
						"bundle_no": 7,
						"size": "M",
						"shade": "A",
						"set_combination": {},
						"Front": 10,
						"Front_colour": "Navy",
						"Front_moved": False,
						"Back": 10,
						"Back_colour": "Navy",
						"Back_moved": False,
						"bundle_moved": False,
					}],
				},
			},
			"collapsed_details": [],
			"accessory_data": [],
		}
		self.input_rows = [
			{
				"lay_no": 1, "bundle_no": 7, "qty": 10, "panel": "Front",
				"set_combination": {}, "shade": "A", "size": "M", "colour": "Navy", "is_collapsed": False,
			},
			{
				"lay_no": 1, "bundle_no": 7, "qty": 10, "panel": "Back",
				"set_combination": {}, "shade": "A", "size": "M", "colour": "Navy", "is_collapsed": False,
			},
		]
		self.output_rows = [
			{"lay_no": 1, "bundle_no": 8, "qty": 10, "panel": "Front", "set_combination": {}, "shade": "A", "size": "M", "colour": "Navy"},
			{"lay_no": 1, "bundle_no": 9, "qty": 10, "panel": "Back", "set_combination": {}, "shade": "A", "size": "M", "colour": "Navy"},
		]

	def test_new_editor_derives_context_without_requiring_a_cutting_plan(self):
		lot = MagicMock(item="ITEM-1", production_detail="IPD-1")
		lot.check_permission = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=lot),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.db.exists", return_value=True),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.nowdate", return_value="2026-10-07"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.nowtime", return_value="12:00:00"),
		):
			payload = get_cut_bundle_editor(source={"lot": "LOT-1", "warehouse": "CUT-STORE"})

		self.assertIsNone(payload["record"])
		self.assertEqual(payload["context"]["item"], "ITEM-1")
		self.assertNotIn("cutting_plan", payload["defaults"])
		self.assertEqual(payload["defaults"]["warehouse"], "CUT-STORE")
		self.assertTrue(payload["permissions"]["can_create"])

	def test_preview_is_permission_checked_and_returns_authoritative_choices(self):
		lot = MagicMock(item="ITEM-1", production_detail="IPD-1")
		lot.check_permission = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=lot),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.db.exists", return_value=True),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.get_major_colours", return_value={"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]}),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.get_cut_bundle_unmoved_data", return_value=self.available) as generator,
		):
			payload = preview_cut_bundle_source("LOT-1", "CUT-STORE", {"selected_colour": "Navy", "posting_date": "2026-10-07", "posting_time": "12:00:00"})

		self.assertEqual(payload["choices"]["colours"], ["Navy"])
		self.assertEqual(payload["available"], self.available)
		generator.assert_called_once_with("CUT-STORE", "LOT-1", "2026-10-07", "12:00:00", 0, get_collapsed=True, bundle_colour="Navy")

	def test_authoritative_values_reject_forged_input_and_use_server_identity(self):
		forged = deepcopy(self.input_rows)
		forged[0]["qty"] = 999
		with self.assertRaises(frappe.ValidationError):
			_authoritative_bundle_values(self.available, forged, self.output_rows, {"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]}, "LOT-1")

		client_rows = deepcopy(self.input_rows)
		client_rows[0]["set_combination"] = {"forged": True}
		with self.assertRaises(frappe.ValidationError):
			_authoritative_bundle_values(self.available, client_rows, self.output_rows, {"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]}, "LOT-1")

		with patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.get_major_set_colours", return_value={"major_colour": "Navy"}):
			result = _authoritative_bundle_values(self.available, self.input_rows, self.output_rows, {"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]}, "LOT-1")

		self.assertEqual(result["inputs"][0]["set_combination"], {})
		self.assertEqual(result["outputs"][0]["set_combination"], {"major_colour": "Navy"})

	def test_output_identity_is_normalised_and_fractional_quantity_is_rejected(self):
		duplicate = [
			{**self.output_rows[0], "panel": "Front, Back", "qty": 10},
			{**self.output_rows[0], "panel": "Front,Back", "qty": 10, "is_collapsed": True},
		]
		with self.assertRaises(frappe.ValidationError):
			_authoritative_bundle_values(
				self.available,
				self.input_rows,
				duplicate,
				{"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]},
				"LOT-1",
			)

		fractional = deepcopy(self.output_rows)
		fractional[0]["qty"] = 9.5
		with self.assertRaises(frappe.ValidationError):
			_authoritative_bundle_values(
				self.available,
				self.input_rows,
				fractional,
				{"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]},
				"LOT-1",
			)

	def test_save_uses_lot_identity_and_rejects_stale_updates(self):
		doc = MagicMock(name="CBE-1", doctype="SD YRP Cut Bundle Edit", docstatus=0, modified="NEW", lot="LOT-1", warehouse="CUT-STORE", item="ITEM-1")
		doc.save = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			save_cut_bundle({"inputs": self.input_rows, "outputs": self.output_rows}, name="CBE-1", expected_modified="OLD")

	def test_save_and_submit_apply_authoritative_payload(self):
		doc = MagicMock(name="CBE-NEW", doctype="SD YRP Cut Bundle Edit", docstatus=0, modified="2026-10-07 12:00:00")
		doc.save = MagicMock()
		doc.submit = MagicMock()
		doc.check_permission = MagicMock()
		lot = MagicMock(item="ITEM-1", production_detail="IPD-1")
		lot.check_permission = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=lot),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._source_snapshot", return_value={"available": self.available, "choices": {"colours": ["Navy"], "sizes": ["M"], "panels": ["Front", "Back"]}}),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._lock_source_rows") as lock_rows,
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.nowdate", return_value="2026-10-07"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.nowtime", return_value="12:00:00"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.get_major_set_colours", return_value={}),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._record_payload", return_value={"name": "CBE-NEW"}),
		):
			result = save_cut_bundle({"lot": "LOT-1", "warehouse": "CUT-STORE", "selected_colour": "Navy", "inputs": self.input_rows, "outputs": self.output_rows}, submit=True)

		self.assertEqual(result["name"], "CBE-NEW")
		self.assertEqual(doc.lot, "LOT-1")
		self.assertEqual(doc.item, "ITEM-1")
		self.assertEqual(doc.warehouse, "CUT-STORE")
		doc.save.assert_called_once()
		doc.submit.assert_called_once()
		lock_rows.assert_called_once()

	def test_lifecycle_commands_enforce_docstatus_and_permissions(self):
		draft = MagicMock(name="CBE-1", doctype="SD YRP Cut Bundle Edit", docstatus=0, modified="M1")
		draft.check_permission = MagicMock()
		draft.submit = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=draft),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._revalidate_saved_draft"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._record_payload", return_value={"docstatus": 1}),
		):
			self.assertEqual(execute_cut_bundle_command("CBE-1", "submit")["docstatus"], 1)
		draft.check_permission.assert_called_with("submit")
		draft.submit.assert_called_once()

		submitted = MagicMock(name="CBE-1", doctype="SD YRP Cut Bundle Edit", docstatus=1, modified="M2")
		submitted.check_permission = MagicMock()
		submitted.cancel = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=submitted),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._record_payload", return_value={"docstatus": 2}),
		):
			execute_cut_bundle_command("CBE-1", "cancel")
		submitted.check_permission.assert_called_with("cancel")
		submitted.cancel.assert_called_once()

	def test_print_data_does_not_mark_printed_until_qz_confirms(self):
		doc = MagicMock(name="CBE-1", doctype="SD YRP Cut Bundle Edit", docstatus=1, modified="M1", printed_time=None)
		doc.check_permission = MagicMock()
		cache = MagicMock()
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.print_labels", return_value="^XA^XZ"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.generate_hash", return_value="TOKEN"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.cache", cache),
		):
			payload = get_cut_bundle_print_data("CBE-1", "Zebra")

		self.assertEqual(payload["zpl"], "^XA^XZ")
		self.assertEqual(payload["printer"], "Zebra")
		self.assertEqual(payload["confirmation_token"], "TOKEN")
		cache.set_value.assert_called_once()
		doc.db_set.assert_not_called()

	def test_confirm_print_marks_once_and_returns_refreshed_record(self):
		doc = MagicMock(name="CBE-1", doctype="SD YRP Cut Bundle Edit", docstatus=1, modified="M1", printed_time=None)
		doc.name = "CBE-1"
		doc.check_permission = MagicMock()
		cache = MagicMock()
		cache.get_value.return_value = {"name": "CBE-1", "user": "Administrator", "modified": "M1"}
		with (
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace._record_payload", return_value={"name": "CBE-1", "printed_time": "2026-10-07 12:30:00"}),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.now_datetime", return_value="2026-10-07 12:30:00"),
			patch("essdee_yrp.cut_panel_store.cut_bundle_workspace.frappe.cache", cache),
		):
			result = confirm_cut_bundle_print("CBE-1", expected_modified="M1", confirmation_token="TOKEN")

		self.assertEqual(result["printed_time"], "2026-10-07 12:30:00")
		doc.check_permission.assert_any_call("print")
		doc.check_permission.assert_any_call("write")
		cache.delete_value.assert_called_once_with("cut-bundle-print:TOKEN")
		doc.db_set.assert_called_once()
