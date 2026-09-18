import unittest
import runpy
import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, mock_open, patch

from essdee_yrp.migration.engine import MigrationError, transform_document
from essdee_yrp.migration.live import FrappeBulkTarget, _relocate_migrated_file_urls, _update_direct_attachment_field
from essdee_yrp.migration.planner import build_schema_analysis
from essdee_yrp.migration.preservation import auth_identity, run_auth, run_retired_archive, transform_orphan


class PreservationTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.plan, _ = build_schema_analysis()

	def credential(self, **changes):
		row = dict(doctype="Stock Settings", name="Stock Settings",
			fieldname="sms_old_database_password", password="test-ciphertext",
			encrypted=1, decryptable=False)
		return {**row, **changes}

	def test_password_single_identity_is_mapped(self):
		self.assertEqual(auth_identity(self.credential(), self.plan),
			("YRP YRP Stock Settings", "YRP YRP Stock Settings", "sms_old_database_password"))

	def test_unknown_password_field_fails_without_exposing_secret(self):
		row = self.credential(fieldname="not_declared")
		with self.assertRaises(MigrationError) as error:
			auth_identity(row, self.plan)
		self.assertNotIn(row["password"], str(error.exception))

	def test_ciphertext_is_preserved_and_report_is_redacted(self):
		row = self.credential()
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with (
			patch("essdee_yrp.migration.preservation.frappe.get_meta", return_value=SimpleNamespace(issingle=True)),
			patch("essdee_yrp.migration.preservation.frappe.db.sql") as sql,
		):
			result = run_auth(self.plan, source)
		self.assertEqual(sql.call_args.args[1][-2:], ("test-ciphertext", 1))
		self.assertEqual(result["raw_preserved"], 1)
		self.assertEqual(len(result["source_key_unavailable"]), 1)
		self.assertNotIn(row["password"], repr(result))

	def test_decryptable_password_is_reencrypted(self):
		row = self.credential(plaintext="test-plaintext", decryptable=True)
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with (
			patch("essdee_yrp.migration.preservation.frappe.get_meta", return_value=SimpleNamespace(issingle=True)),
			patch("essdee_yrp.migration.preservation.set_encrypted_password") as encrypt,
		):
			result = run_auth(self.plan, source)
		encrypt.assert_called_once_with("YRP YRP Stock Settings", "YRP YRP Stock Settings",
			"test-plaintext", fieldname="sms_old_database_password")
		self.assertEqual(result["reencrypted"], 1)
		self.assertNotIn("test-plaintext", repr(result))

	def test_verify_detects_changed_ciphertext_without_rewriting(self):
		source = SimpleNamespace(iter_auth_rows=lambda: iter([self.credential()]))
		with (
			patch("essdee_yrp.migration.preservation.frappe.get_meta", return_value=SimpleNamespace(issingle=True)),
			patch("essdee_yrp.migration.preservation.frappe.db.sql", return_value=[("changed", 1)]) as sql,
		):
			result = run_auth(self.plan, source, verify=True)
		self.assertEqual(result["status"], "Failed")
		self.assertTrue(sql.call_args.args[0].startswith("SELECT"))
		self.assertNotIn("test-ciphertext", repr(result))

	def test_orphan_preserves_original_identity_and_zero_position(self):
		row = {"doctype": "Item BOM Attribute Mapping Value", "name": "ORPHAN",
			"parenttype": "Item BOM Attribute Mapping", "parentfield": "values",
			"parent": "DELETED-PARENT", "idx": 0}
		result = transform_orphan(row, self.plan)
		self.assertEqual(result["parenttype"], "YRP Item BOM Attribute Mapping")
		self.assertEqual(result["parent"], "DELETED-PARENT")
		self.assertEqual(result["name"], "ORPHAN")
		self.assertEqual(result["idx"], 0)

	def test_orphan_credential_is_preserved_without_creating_a_record(self):
		row = self.credential(doctype="FG Item OMS Settings", name="DELETED-CHILD",
			fieldname="api_secret", source_record_exists=False)
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with (
			patch("essdee_yrp.migration.preservation.frappe.db.exists", return_value=False),
			patch("essdee_yrp.migration.preservation.frappe.db.sql") as sql,
		):
			result = run_auth(self.plan, source)
		self.assertEqual(result["source_orphan_count"], 1)
		self.assertEqual(sql.call_args.args[1][:3],
			("SD YRP FG Item OMS Settings", "DELETED-CHILD", "api_secret"))
		self.assertNotIn(row["password"], repr(result))

	def test_missing_target_credential_parent_still_fails_for_existing_source(self):
		row = self.credential(doctype="FG Item OMS Settings", name="CHILD",
			fieldname="api_secret", source_record_exists=True)
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with patch("essdee_yrp.migration.preservation.frappe.db.exists", return_value=False):
			with self.assertRaisesRegex(MigrationError, "Credential target record missing"):
				run_auth(self.plan, source)

	def test_orphan_credential_cannot_attach_to_an_existing_target_record(self):
		row = self.credential(doctype="FG Item OMS Settings", name="CHILD",
			fieldname="api_secret", source_record_exists=False)
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with patch("essdee_yrp.migration.preservation.frappe.db.exists", return_value=True):
			with self.assertRaisesRegex(MigrationError, "Orphan source credential collides"):
				run_auth(self.plan, source)

	def test_non_single_credentials_require_source_existence_evidence_in_dry_run(self):
		row = self.credential(doctype="FG Item OMS Settings", name="CHILD", fieldname="api_secret")
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with self.assertRaisesRegex(MigrationError, "Credential source-record evidence missing"):
			run_auth(self.plan, source, dry_run=True)

	def test_orphan_credential_dry_run_reports_without_writing(self):
		row = self.credential(doctype="FG Item OMS Settings", name="CHILD",
			fieldname="api_secret", source_record_exists=False)
		source = SimpleNamespace(iter_auth_rows=lambda: iter([row]))
		with patch("essdee_yrp.migration.preservation.frappe.db.sql") as sql:
			result = run_auth(self.plan, source, dry_run=True)
		self.assertEqual(result["source_orphan_count"], 1)
		sql.assert_not_called()

	def test_restored_item_description_is_preserved(self):
		result = transform_document(
			{"doctype": "Item", "name": "I-1", "description": "preserve me"},
			self.plan,
		)
		self.assertEqual(result["description"], "preserve me")

	def test_bulk_writer_refuses_missing_populated_column(self):
		with patch("essdee_yrp.migration.live.frappe.db.get_table_columns", return_value=["name"]):
			with self.assertRaisesRegex(MigrationError, "Refusing to drop populated fields"):
				FrappeBulkTarget()._bulk_upsert("Example", [{"name": "E-1", "missing": 4}])

	def test_bulk_writer_does_not_null_fields_omitted_by_sparse_rows(self):
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_table_columns",
				return_value=["name", "docstatus", "description"],
			),
			patch(
				"essdee_yrp.migration.live.frappe.db.sql",
				side_effect=[[], None, None],
			) as sql,
		):
			FrappeBulkTarget()._bulk_upsert(
				"Example",
				[
					{"name": "E-1", "docstatus": 0, "description": "new"},
					{"name": "E-2", "description": "structure only"},
				],
			)

		self.assertEqual(sql.call_count, 3)
		first_insert, second_insert = sql.call_args_list[1:]
		self.assertIn("`docstatus`", first_insert.args[0])
		self.assertNotIn("`docstatus`", second_insert.args[0])
		self.assertEqual(first_insert.args[1], ["E-1", "new", 0])
		self.assertEqual(second_insert.args[1], ["E-2", "structure only"])

	def test_purchase_invoice_uses_only_direct_and_grouped_item_tables(self):
		row = {"doctype": "Purchase Invoice Item", "name": "PII-1", "item": "I-1",
			"qty": 2, "rate": 10, "amount": 19.95, "idx": 8}
		doc = {"doctype": "Purchase Invoice", "name": "PI-1", "items": [row]}
		result = transform_document(doc, self.plan)
		self.assertEqual(result["items"][0]["amount"], 19.95)
		self.assertEqual(result["essdee_items"][0]["amount"], 20)
		self.assertNotIn("original_item_rows", result)

	def test_populated_physical_column_absent_from_metadata_blocks_export(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		database = Mock()
		database.sql.side_effect = [[("name", "varchar"), ("old_quantity", "decimal")], [(3,)]]
		with self.assertRaisesRegex(RuntimeError, r"Example.old_quantity \(3 values\)"):
			bridge["audit_physical_field_coverage"](SimpleNamespace(db=database), {"Example": {"fields": []}})

	def test_empty_legacy_column_is_explicitly_inventoried(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		database = Mock()
		database.sql.side_effect = [[("old_quantity", "decimal")], [(0,)]]
		result = bridge["audit_physical_field_coverage"](SimpleNamespace(db=database), {"Example": {"fields": []}})
		self.assertEqual(result["undefined_empty_fields"], [{"doctype": "Example", "field": "old_quantity", "material_values": 0}])

	def test_undeclared_single_value_blocks_without_revealing_value(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		database = Mock()
		database.sql.return_value = [("retired_secret", "not-for-the-report")]
		with self.assertRaises(RuntimeError) as error:
			bridge["audit_physical_field_coverage"](SimpleNamespace(db=database), {"Settings": {"issingle": 1, "fields": []}})
		self.assertIn("Settings.retired_secret", str(error.exception))
		self.assertNotIn("not-for-the-report", str(error.exception))

	def test_attachment_relocation_never_replaces_a_different_source_selection(self):
		meta = SimpleNamespace(get_field=lambda name: SimpleNamespace(fieldtype="Attach Image"))
		for selected, expected_writes in (("/files/selected.jpg", 0), ("/files/original.jpg", 1), (None, 0)):
			with (
				self.subTest(selected=selected),
				patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
				patch("essdee_yrp.migration.live.frappe.get_meta", return_value=meta),
				patch("essdee_yrp.migration.live.frappe.db.get_value", return_value=selected),
				patch("essdee_yrp.migration.live.frappe.db.set_value") as write,
			):
				_update_direct_attachment_field("Example", "E-1", "image", "/files/relocated.jpg",
					source_url="/files/original.jpg")
				self.assertEqual(write.call_count, expected_writes)

	def test_unchanged_file_url_does_not_touch_parent(self):
		with patch("essdee_yrp.migration.live.frappe.db.set_value") as write:
			_update_direct_attachment_field("Example", "E-1", "image", "/files/original.jpg",
				source_url="/files/original.jpg")
		write.assert_not_called()

	def test_child_file_relocation_is_scoped_to_exact_file_and_original_url(self):
		with (
			patch("essdee_yrp.migration.live._update_direct_attachment_field"),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
			patch("essdee_yrp.migration.live.frappe.db.sql") as sql,
		):
			_relocate_migrated_file_urls("Example", "E-1", "images", "/files/new.jpg",
				source_url="/files/old.jpg", source_file_name="FILE-1")
		self.assertEqual(sql.call_count, 2)
		for args in sql.call_args_list:
			self.assertIn("WHERE child.`file`=%s", args.args[0])
			self.assertIn("AND child.", args.args[0])
			self.assertEqual(args.args[1], ("/files/new.jpg", "FILE-1", "/files/old.jpg"))

	def test_retired_rows_are_archived_without_touching_live_successor(self):
		record = {"source_doctype": "Employee Department", "row": {"name": "Old", "idx": 19}}
		source = SimpleNamespace(iter_retired_rows=lambda: iter([record]))
		with patch("essdee_yrp.migration.preservation.frappe.db.set_value") as write:
			result = run_retired_archive("MIG-1", source)
		self.assertEqual(result["rows"], 1)
		self.assertEqual(write.call_args.args[:3],
			("SD YRP MRP Data Migration", "MIG-1", "retired_source_rows_json"))

	def test_retired_archive_verifier_rejects_missing_rows(self):
		record = {"source_doctype": "Employee Department", "row": {"name": "Old", "idx": 19}}
		source = SimpleNamespace(iter_retired_rows=lambda: iter([record]))
		with patch("essdee_yrp.migration.preservation.frappe.db.get_value", return_value="[]"):
			result = run_retired_archive("MIG-1", source, verify=True)
		self.assertEqual(result["status"], "Failed")

	def test_retired_missing_blob_requires_explicit_source_gap_allowance(self):
		record = {"source_doctype": "File", "row": {"name": "F-1"},
			"blob_issue": "Source blob unavailable"}
		source = SimpleNamespace(iter_retired_rows=lambda: iter([record]))
		with patch("essdee_yrp.migration.preservation.frappe.db.set_value") as write:
			with self.assertRaisesRegex(MigrationError, "retired attachment blobs"):
				run_retired_archive("MIG-1", source)
			write.assert_not_called()
			result = run_retired_archive("MIG-1", source, dry_run=True, allow_missing_files=True)
			self.assertEqual(result["missing_blob_count"], 1)
			write.assert_not_called()

	def test_retired_file_bytes_are_checked_and_archived(self):
		import frappe
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		export = bridge["retired_source_rows"]
		content = b"historical attachment test"
		row = frappe._dict(name="F-1", file_size=len(content),
			content_hash=hashlib.md5(content).hexdigest())
		database = Mock()
		database.table_exists.return_value = False
		database.sql.return_value = [row]
		with (
			patch.dict(export.__globals__, {"_resolve_physical_file": lambda *_: (None, "/test/attachment")}),
			patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=len(content))),
			patch("builtins.open", mock_open(read_data=content)),
		):
			records = list(export(SimpleNamespace(db=database)))
		self.assertEqual(base64.b64decode(records[0]["blob_base64"]), content)
		self.assertNotIn("blob_issue", records[0])

	def test_plain_file_mapping_prefers_valid_duplicate_over_corrupt_original(self):
		from io import BytesIO

		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts' / 'f15_source_bridge.py'))
		row = {'name': 'ORIGINAL', 'content_hash': hashlib.md5(b'good').hexdigest(), 'file_size': 4, 'is_private': 1}
		api = SimpleNamespace(get_all=lambda *args, **kwargs: ['ORIGINAL', 'DUPLICATE'],
			get_doc=lambda doctype, name: SimpleNamespace(get_full_path=lambda: '/test/' + name))
		with patch('os.path.isfile', return_value=True), patch('os.path.getsize', return_value=4), \
			patch('builtins.open', side_effect=lambda path, mode: BytesIO(b'good' if path.endswith('DUPLICATE') else b'bad!')):
			_doc, path = bridge['_resolve_physical_file'](api, row)
		self.assertEqual(path, '/test/DUPLICATE')

	def test_retired_file_corruption_is_reported_not_archived_as_valid(self):
		import frappe
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		export = bridge["retired_source_rows"]
		database = Mock()
		database.table_exists.return_value = False
		database.sql.return_value = [frappe._dict(name="F-1", file_size=6, content_hash="wrong-hash")]
		with (
			patch.dict(export.__globals__, {"_resolve_physical_file": lambda *_: (None, "/test/attachment")}),
			patch("pathlib.Path.stat", return_value=SimpleNamespace(st_size=6)),
			patch("builtins.open", mock_open(read_data=b"broken")),
		):
			records = list(export(SimpleNamespace(db=database)))
		self.assertIn("blob_issue", records[0])
		self.assertNotIn("blob_base64", records[0])

	def test_source_decimal_must_fit_target_storage_without_rounding(self):
		with (
			patch("essdee_yrp.migration.live.frappe.db.get_table_columns", return_value=["name", "qty"]),
			patch("essdee_yrp.migration.live.frappe.db.sql", return_value=[("qty", 3)]) as sql,
		):
			with self.assertRaisesRegex(MigrationError, "Refusing numeric rounding"):
				FrappeBulkTarget()._bulk_upsert("Example", [{"name": "E-1", "qty": "1.234567891"}])
		self.assertEqual(sql.call_count, 1)  # only the storage-definition read
