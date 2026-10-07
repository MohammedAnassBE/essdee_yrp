import json
from io import BytesIO
from unittest.mock import MagicMock, call, patch
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import frappe
from frappe import _dict
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils.xlsxutils import make_xlsx
from lxml.etree import XMLSyntaxError

from essdee_yrp.cut_panel_store import excel_sticker_workspace as workspace
from essdee_yrp.cut_panel_store.excel_sticker_workspace import (
	EXCEL_STICKER_DOCTYPE,
	execute_excel_sticker_command,
	get_excel_sticker_editor,
	get_excel_sticker_preview,
	get_excel_sticker_print_data,
	save_excel_sticker,
)


MODULE = "essdee_yrp.cut_panel_store.excel_sticker_workspace"


def excel_doc(*, name="ESP-1", docstatus=0, modified="M1", serialized_data=""):
	doc = MagicMock()
	doc.doctype = EXCEL_STICKER_DOCTYPE
	doc.name = name
	doc.docstatus = docstatus
	doc.modified = modified
	doc.excel_file = "/private/files/stickers.xlsx"
	doc.print_format = "EXCEL-FORMAT"
	doc.serialized_data = serialized_data
	doc.has_permission.side_effect = lambda permission: permission in {
		"read",
		"write",
		"submit",
		"cancel",
		"print",
	}
	return doc


def file_doc(*, parent="ESP-1", owner=None, filename="stickers.xlsx", is_private=1):
	file = MagicMock()
	file.name = "FILE-1"
	file.file_name = filename
	file.file_url = f"/{'private/' if is_private else ''}files/{filename}"
	file.is_private = is_private
	file.attached_to_doctype = EXCEL_STICKER_DOCTYPE
	file.attached_to_name = parent
	file.attached_to_field = "excel_file"
	file.owner = owner or frappe.session.user
	return file


def print_format(*, labels_per_row=2):
	doc = MagicMock()
	doc.name = "EXCEL-FORMAT"
	doc.width = 4
	doc.height = 6
	doc.labels_per_row = labels_per_row
	doc.zpl_raw_print_format_details = [
		_dict(printer_type="200dpi", raw_code="RAW-200"),
		_dict(printer_type="300dpi", raw_code="RAW-300"),
	]
	return doc


class TestCutPanelStoreExcelStickerWorkspace(UnitTestCase):
	def test_editor_returns_only_a_bounded_safe_sample(self):
		rows = []
		for index in range(workspace.SAMPLE_ROW_LIMIT + 3):
			rows.append(
				{
					f"column_{column}": "x" * (workspace.SAMPLE_CELL_LIMIT + 20)
					for column in range(workspace.SAMPLE_COLUMN_LIMIT + 3)
				}
			)
		doc = excel_doc(docstatus=1, serialized_data=json.dumps(rows))
		attachment = file_doc()
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment]),
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
		):
			payload = get_excel_sticker_editor("ESP-1")

		record = payload["record"]
		self.assertEqual(record["row_count"], workspace.SAMPLE_ROW_LIMIT + 3)
		self.assertEqual(len(record["sample"]["rows"]), workspace.SAMPLE_ROW_LIMIT)
		self.assertEqual(len(record["sample"]["columns"]), workspace.SAMPLE_COLUMN_LIMIT)
		self.assertLessEqual(
			len(record["sample"]["rows"][0]["column_0"]),
			workspace.SAMPLE_CELL_LIMIT,
		)
		self.assertNotIn("serialized_data", record)
		doc.check_permission.assert_called_once_with("read")
		attachment.check_permission.assert_called_once_with("read")

	def test_sample_uses_unique_aliases_and_reports_clipped_content(self):
		prefix = "h" * (workspace.SAMPLE_HEADER_LIMIT + 10)
		doc = excel_doc(
			docstatus=1,
			serialized_data=json.dumps(
				[
					{
						f"{prefix}-one": "x" * (workspace.SAMPLE_CELL_LIMIT + 10),
						f"{prefix}-two": "short",
					}
				]
			),
		)
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, file_doc()]),
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
		):
			payload = get_excel_sticker_editor("ESP-1")

		sample = payload["record"]["sample"]
		self.assertEqual(len(set(sample["columns"])), 2)
		self.assertEqual(len(sample["rows"][0]), 2)
		self.assertTrue(sample["truncated"])

	def test_editor_rejects_an_attachment_owned_by_another_document(self):
		doc = excel_doc()
		attachment = file_doc(parent="ESP-OTHER")
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment]),
			self.assertRaises(frappe.ValidationError),
		):
			get_excel_sticker_editor("ESP-1")

	def test_editor_checks_file_read_permission(self):
		doc = excel_doc()
		attachment = file_doc()
		attachment.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment]),
			self.assertRaises(frappe.PermissionError),
		):
			get_excel_sticker_editor("ESP-1")

	def test_new_editor_returns_a_private_upload_target(self):
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True) as permission,
			patch(f"{MODULE}.frappe.generate_hash", return_value="TOKEN"),
		):
			payload = get_excel_sticker_editor()

		self.assertEqual(
			payload["upload"],
			{
				"doctype": EXCEL_STICKER_DOCTYPE,
				"docname": "new-yrp-excel-sticker-print-TOKEN",
				"fieldname": "excel_file",
				"is_private": 1,
			},
		)
		self.assertIn(
			call(EXCEL_STICKER_DOCTYPE, ptype="create", throw=True),
			permission.call_args_list,
		)

	def test_new_save_accepts_only_the_users_same_temporary_draft_xlsx(self):
		doc = excel_doc(name="ESP-NEW")
		attachment = file_doc(parent="new-yrp-excel-sticker-print-TOKEN")
		format_doc = print_format()
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[attachment, format_doc]),
			patch(f"{MODULE}._record_payload", return_value={"name": "ESP-NEW"}),
		):
			payload = save_excel_sticker(
				{
					"excel_file": attachment.file_url,
					"print_format": "EXCEL-FORMAT",
					"temporary_name": "new-yrp-excel-sticker-print-TOKEN",
					"serialized_data": '[{"forged": true}]',
				}
			)

		self.assertEqual(payload, {"name": "ESP-NEW"})
		self.assertEqual(doc.excel_file, attachment.file_url)
		self.assertEqual(doc.print_format, "EXCEL-FORMAT")
		self.assertNotEqual(doc.serialized_data, '[{"forged": true}]')
		self.assertEqual(getattr(doc, "__temporary_name"), "new-yrp-excel-sticker-print-TOKEN")
		doc.save.assert_called_once_with()

	def test_save_rejects_non_xlsx_and_forged_temporary_attachments(self):
		for attachment, temporary_name in (
			(file_doc(filename="stickers.xls"), "ESP-1"),
			(file_doc(parent="new-yrp-excel-sticker-print-OTHER"), "new-yrp-excel-sticker-print-TOKEN"),
		):
			with self.subTest(attachment=attachment.file_name):
				doc = excel_doc(name="ESP-NEW")
				with (
					patch(f"{MODULE}.frappe.has_permission", return_value=True),
					patch(f"{MODULE}.frappe.new_doc", return_value=doc),
					patch(f"{MODULE}.frappe.get_doc", return_value=attachment),
					self.assertRaises(frappe.ValidationError),
				):
					save_excel_sticker(
						{
							"excel_file": attachment.file_url,
							"print_format": "EXCEL-FORMAT",
							"temporary_name": temporary_name,
						}
					)
				doc.save.assert_not_called()

	def test_save_rejects_public_and_wrong_owner_temporary_attachments(self):
		for attachment in (
			file_doc(parent="new-yrp-excel-sticker-print-TOKEN", is_private=0),
			file_doc(parent="new-yrp-excel-sticker-print-TOKEN", owner="other@example.com"),
		):
			with self.subTest(file_url=attachment.file_url, owner=attachment.owner):
				doc = excel_doc(name="ESP-NEW")
				with (
					patch(f"{MODULE}.frappe.has_permission", return_value=True),
					patch(f"{MODULE}.frappe.new_doc", return_value=doc),
					patch(f"{MODULE}.frappe.get_doc", return_value=attachment),
					self.assertRaises(frappe.ValidationError),
				):
					save_excel_sticker(
						{
							"excel_file": attachment.file_url,
							"print_format": "EXCEL-FORMAT",
							"temporary_name": "new-yrp-excel-sticker-print-TOKEN",
						}
					)
				doc.save.assert_not_called()

	def test_existing_save_requires_write_permission_and_fresh_timestamp(self):
		doc = excel_doc(modified="NEW")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			save_excel_sticker({}, name="ESP-1", expected_modified="OLD")
		doc.check_permission.assert_called_once_with("write")

		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			save_excel_sticker({}, name="ESP-1", expected_modified="OLD")

	def test_existing_save_rejects_a_missing_expected_timestamp(self):
		doc = excel_doc(modified="M1")
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			save_excel_sticker({}, name="ESP-1")
		doc.save.assert_not_called()

	def test_save_does_not_combine_submission_with_draft_persistence(self):
		doc = excel_doc(name="ESP-NEW")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.new_doc", return_value=doc),
			self.assertRaises(frappe.ValidationError),
		):
			save_excel_sticker({}, submit=True)
		doc.save.assert_not_called()
		doc.submit.assert_not_called()

	def test_malformed_submit_reports_a_safe_error_without_resaving_the_draft(self):
		doc = excel_doc()
		attachment = file_doc()
		doc.submit.side_effect = BadZipFile("raw zip internals")
		format_doc = print_format()
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			self.assertRaisesRegex(frappe.ValidationError, "valid .xlsx"),
		):
			execute_excel_sticker_command("ESP-1", "submit", expected_modified="M1")

		doc.check_permission.assert_called_with("submit")
		doc.submit.assert_called_once_with()
		doc.save.assert_not_called()

	def test_unreadable_submit_reports_a_safe_error(self):
		doc = excel_doc()
		attachment = file_doc()
		format_doc = print_format()
		doc.submit.side_effect = OSError("/private/secret/server/path")
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			self.assertRaisesRegex(frappe.ValidationError, "valid .xlsx"),
		):
				execute_excel_sticker_command("ESP-1", "submit", expected_modified="M1")

	def test_malformed_xml_submit_reports_a_safe_error(self):
		doc = excel_doc()
		attachment = file_doc()
		format_doc = print_format()
		doc.submit.side_effect = XMLSyntaxError("malformed workbook XML", 1, 1, 1)
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			self.assertRaisesRegex(frappe.ValidationError, "valid .xlsx"),
		):
			execute_excel_sticker_command("ESP-1", "submit", expected_modified="M1")

	def test_empty_workbook_message_remains_clear(self):
		doc = excel_doc()
		attachment = file_doc()
		doc.submit.side_effect = frappe.ValidationError("Excel file is empty")
		format_doc = print_format()
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			self.assertRaisesRegex(frappe.ValidationError, "Excel file is empty"),
		):
			execute_excel_sticker_command("ESP-1", "submit", expected_modified="M1")

	def test_lifecycle_rejects_unknown_commands_before_loading_a_record(self):
		with (
			patch(f"{MODULE}.frappe.get_doc") as get_doc,
			self.assertRaises(frappe.ValidationError),
		):
			execute_excel_sticker_command("ESP-SECRET", "delete", expected_modified="M1")
		get_doc.assert_not_called()

	def test_lifecycle_rejects_unsupported_cancel_before_loading_a_record(self):
		with (
			patch(f"{MODULE}.frappe.get_doc") as get_doc,
			self.assertRaisesRegex(frappe.ValidationError, "Unsupported Excel Sticker Print command"),
		):
			execute_excel_sticker_command("ESP-SECRET", "cancel", expected_modified="M1")
		get_doc.assert_not_called()

	def test_lifecycle_checks_permission_before_disclosing_staleness(self):
		doc = excel_doc(modified="NEW")
		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.has_permission", return_value=True),
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			execute_excel_sticker_command("ESP-1", "submit", expected_modified="OLD")

	def test_lifecycle_global_permission_denial_does_not_load_the_record(self):
		with (
			patch(f"{MODULE}.frappe.has_permission", side_effect=frappe.PermissionError),
			patch(f"{MODULE}.frappe.get_doc") as get_doc,
			self.assertRaises(frappe.PermissionError),
		):
			execute_excel_sticker_command("ESP-SECRET", "submit", expected_modified="M1")
		get_doc.assert_not_called()

	def test_preview_is_read_checked_and_forces_one_300dpi_label(self):
		doc = excel_doc(
			docstatus=1,
			serialized_data=json.dumps([{"sku": "SKU-1", "print_quantity": 999, "dpi": 1}]),
		)
		attachment = file_doc()
		format_doc = print_format()
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			patch(f"{MODULE}.frappe.render_template", return_value="^XA^XZ") as render,
		):
			payload = get_excel_sticker_preview("ESP-1")

		render.assert_called_once_with(
			"RAW-300",
			{"sku": "SKU-1", "print_quantity": 1, "dpi": 300},
		)
		self.assertEqual(
			payload,
			{"code": "^XA^XZ", "zpl": "^XA^XZ", "raw": "^XA^XZ", "height": 6, "width": 4},
		)
		doc.check_permission.assert_called_once_with("read")

	def test_print_uses_exact_resolution_and_server_owned_context(self):
		doc = excel_doc(
			docstatus=1,
			serialized_data=json.dumps(
				[
					{"sku": "SKU-1", "print_quantity": 3, "dpi": 1},
					{"sku": "SKU-2", "print_quantity": 0},
				]
			),
		)
		attachment = file_doc()
		format_doc = print_format(labels_per_row=2)
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			patch(f"{MODULE}.frappe.render_template", return_value="LABEL") as render,
		):
			result = get_excel_sticker_print_data("ESP-1", "200dpi")

		self.assertEqual(result, "LABEL")
		render.assert_called_once_with(
			"RAW-200",
			{"sku": "SKU-1", "print_quantity": 2, "dpi": 203},
		)
		doc.check_permission.assert_called_once_with("print")

	def test_print_selects_the_exact_300dpi_template(self):
		doc = excel_doc(
			docstatus=1,
			serialized_data=json.dumps([{"sku": "SKU-1", "print_quantity": 1, "dpi": 203}]),
		)
		attachment = file_doc()
		format_doc = print_format(labels_per_row=1)
		with (
			patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
			patch(f"{MODULE}.frappe.render_template", return_value="LABEL") as render,
		):
			result = get_excel_sticker_print_data("ESP-1", "300dpi")

		self.assertEqual(result, "LABEL")
		render.assert_called_once_with(
			"RAW-300",
			{"sku": "SKU-1", "print_quantity": 1, "dpi": 300},
		)

	def test_print_rejects_unsupported_resolution_and_bad_quantities(self):
		for printer_type, rows in (
			("600dpi", [{"print_quantity": 1}]),
			("300dpi", [{"print_quantity": "many"}]),
			("300dpi", [{"print_quantity": -1}]),
			("300dpi", [{"print_quantity": 0}]),
		):
			with self.subTest(printer_type=printer_type, rows=rows):
				doc = excel_doc(docstatus=1, serialized_data=json.dumps(rows))
				attachment = file_doc()
				format_doc = print_format()
				with (
					patch(f"{MODULE}.frappe.get_doc", side_effect=[doc, attachment, format_doc]),
					patch(f"{MODULE}.frappe.render_template") as render,
					self.assertRaises(frappe.ValidationError),
				):
					get_excel_sticker_print_data("ESP-1", printer_type)
				render.assert_not_called()

	def test_print_permission_is_checked_before_serialized_rows(self):
		doc = excel_doc(docstatus=1, serialized_data="not-json")
		doc.check_permission.side_effect = frappe.PermissionError
		with (
			patch(f"{MODULE}.frappe.get_doc", return_value=doc),
			self.assertRaises(frappe.PermissionError),
		):
			get_excel_sticker_print_data("ESP-1", "300dpi")


class TestCutPanelStoreExcelStickerIntegration(IntegrationTestCase):
	def _make_format(self, suffix):
		return frappe.get_doc(
			{
				"doctype": "YRP ZPL Raw Print Format",
				"name": f"TEST-EXCEL-STICKER-{suffix}",
				"labels_per_row": 2,
				"width": 4,
				"height": 6,
				"zpl_raw_print_format_details": [
					{
						"printer_type": "200dpi",
						"raw_code": "^XA^FD{{ sku }}-{{ dpi }}-{{ print_quantity }}^FS^XZ",
					},
					{
						"printer_type": "300dpi",
						"raw_code": "^XA^FD{{ sku }}-{{ dpi }}-{{ print_quantity }}^FS^XZ",
					},
				],
			}
		).insert()

	def _attach(self, temporary_name, content, suffix, *, is_private=1):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"stickers-{suffix}.xlsx",
				"content": content,
				"is_private": is_private,
				"attached_to_doctype": EXCEL_STICKER_DOCTYPE,
				"attached_to_name": temporary_name,
				"attached_to_field": "excel_file",
			}
		).insert()

	def test_real_upload_draft_submit_preview_and_print_flow(self):
		suffix = frappe.generate_hash(length=8)
		format_doc = self._make_format(suffix)
		new_editor = get_excel_sticker_editor()
		temporary_name = new_editor["defaults"]["temporary_name"]
		content = make_xlsx(
			[["sku", "print_quantity", "dpi"], ["SKU-1", 3, 1], ["SKU-2", 0, 1]],
			"Stickers",
		).getvalue()
		attachment = self._attach(temporary_name, content, suffix)

		draft = save_excel_sticker(
			{
				"excel_file": attachment.file_url,
				"print_format": format_doc.name,
				"temporary_name": temporary_name,
			}
		)
		self.assertEqual(draft["docstatus"], 0)
		self.assertEqual(draft["row_count"], 0)
		self.assertEqual(
			frappe.db.get_value("File", attachment.name, "attached_to_name"),
			draft["name"],
		)

		submitted = execute_excel_sticker_command(
			draft["name"],
			"submit",
			expected_modified=draft["modified"],
		)
		self.assertEqual(submitted["docstatus"], 1)
		self.assertEqual(submitted["row_count"], 2)
		self.assertEqual(submitted["sample_rows"][0]["sku"], "SKU-1")
		self.assertNotIn("serialized_data", submitted)

		preview = get_excel_sticker_preview(draft["name"])
		self.assertEqual(preview["code"], "^XA^FDSKU-1-300-1^FS^XZ")
		self.assertEqual(
			get_excel_sticker_print_data(draft["name"], "200dpi"),
			"^XA^FDSKU-1-203-2^FS^XZ",
		)
		self.assertFalse(submitted["permissions"].get("can_cancel", False))

	def test_real_save_rejects_public_and_wrong_owner_files(self):
		content = make_xlsx([["sku", "print_quantity"], ["SKU-1", 1]], "Stickers").getvalue()
		for suffix, is_private, owner in (
			(frappe.generate_hash(length=8), 0, frappe.session.user),
			(frappe.generate_hash(length=8), 1, "Guest"),
		):
			with self.subTest(is_private=is_private, owner=owner):
				format_doc = self._make_format(suffix)
				temporary_name = get_excel_sticker_editor()["defaults"]["temporary_name"]
				attachment = self._attach(
					temporary_name,
					content,
					suffix,
					is_private=is_private,
				)
				if owner != frappe.session.user:
					frappe.db.set_value("File", attachment.name, "owner", owner, update_modified=False)
				with self.assertRaises(frappe.ValidationError):
					save_excel_sticker(
						{
							"excel_file": attachment.file_url,
							"print_format": format_doc.name,
							"temporary_name": temporary_name,
						}
					)
				self.assertFalse(
					frappe.db.exists(EXCEL_STICKER_DOCTYPE, {"excel_file": attachment.file_url})
				)

	def test_real_malformed_workbook_error_rolls_back_to_the_saved_draft(self):
		suffix = frappe.generate_hash(length=8)
		format_doc = self._make_format(suffix)
		temporary_name = get_excel_sticker_editor()["defaults"]["temporary_name"]
		valid = make_xlsx([["sku", "print_quantity"], ["SKU-1", 1]], "Stickers").getvalue()
		malformed = BytesIO()
		with ZipFile(BytesIO(valid)) as source, ZipFile(malformed, "w", ZIP_DEFLATED) as target:
			for member in source.namelist():
				content = source.read(member)
				if member == "xl/worksheets/sheet1.xml":
					content = b"<worksheet><sheetData><row>"
				target.writestr(member, content)
		attachment = self._attach(temporary_name, malformed.getvalue(), suffix)
		draft = save_excel_sticker(
			{
				"excel_file": attachment.file_url,
				"print_format": format_doc.name,
				"temporary_name": temporary_name,
			}
		)

		frappe.db.savepoint("before_malformed_excel_submit")
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "valid .xlsx"):
				execute_excel_sticker_command(
					draft["name"],
					"submit",
					expected_modified=draft["modified"],
				)
		finally:
			frappe.db.rollback(save_point="before_malformed_excel_submit")

		preserved = frappe.get_doc(EXCEL_STICKER_DOCTYPE, draft["name"])
		self.assertEqual(preserved.docstatus, 0)
		self.assertFalse(preserved.serialized_data)
		self.assertEqual(preserved.excel_file, attachment.file_url)

	def test_real_missing_worksheet_uses_the_safe_workbook_error(self):
		suffix = frappe.generate_hash(length=8)
		format_doc = self._make_format(suffix)
		temporary_name = get_excel_sticker_editor()["defaults"]["temporary_name"]
		valid = make_xlsx([["sku", "print_quantity"], ["SKU-1", 1]], "Stickers").getvalue()
		missing_sheet = BytesIO()
		with ZipFile(BytesIO(valid)) as source, ZipFile(missing_sheet, "w", ZIP_DEFLATED) as target:
			for member in source.namelist():
				if member != "xl/worksheets/sheet1.xml":
					target.writestr(member, source.read(member))
		attachment = self._attach(temporary_name, missing_sheet.getvalue(), suffix)
		draft = save_excel_sticker(
			{
				"excel_file": attachment.file_url,
				"print_format": format_doc.name,
				"temporary_name": temporary_name,
			}
		)

		frappe.db.savepoint("before_missing_excel_sheet_submit")
		try:
			with self.assertRaisesRegex(frappe.ValidationError, "valid .xlsx"):
				execute_excel_sticker_command(
					draft["name"],
					"submit",
					expected_modified=draft["modified"],
				)
		finally:
			frappe.db.rollback(save_point="before_missing_excel_sheet_submit")

		preserved = frappe.get_doc(EXCEL_STICKER_DOCTYPE, draft["name"])
		self.assertEqual(preserved.docstatus, 0)
		self.assertFalse(preserved.serialized_data)
