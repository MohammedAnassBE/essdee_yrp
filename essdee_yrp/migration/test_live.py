from __future__ import annotations

import base64
import hashlib
import json
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration import (
	MRPDataMigration,
	_migration_action_reservation,
)
from essdee_yrp.migration.config import MigrationSettings, is_target_reset_enabled
from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import (
	F15SourceBridge,
	FrappeBulkTarget,
	_apply_contextual_defaults,
	_assert_no_other_active_migration,
	_bind_checkpoint_to_source_snapshot,
	_bind_reset_series_checkpoint,
	_broken_static_link_count,
	_build_target_reset_manifest,
	_collect_document_identities,
	_collect_expected_value_rows,
	_decode_and_validate_file_payload,
	_delete_reset_file,
	_delete_target_reset_manifest,
	_flush_batch,
	_generated_supplier_warehouse_names,
	_include_reset_generated_audit_scope,
	_is_verified_attachment_url,
	_mark_reset_started,
	_migration_contract_fingerprint,
	_migration_generated_identity_allowances,
	_nonzero_reset_counts,
	_prepare_purchase_invoice_migration_documents,
	_require_previous_snapshot,
	_run_files,
	_same_migrated_value,
	_source_snapshot,
	_target_reset_counts,
	_target_reset_file_names,
	_validate_configured_default_contract,
	_validate_external_references,
	_validate_required_target_values,
	_validate_target_migration_prerequisites,
	_verify_transformed_value_batch,
	enqueue_job,
	enqueue_reset_job,
	run_job_guarded,
	run_reset_job,
	run_reset_job_guarded,
)


def configured_settings():
	return MigrationSettings(
		adapter="local_bench",
		source_bench=Path("/configured/source-bench"),
		source_site="source.test",
		source_app="production_api",
		target_site="target.test",
		target_apps=("yrp", "essdee_yrp"),
		required_defaults={},
	)


class MigrationLiveAdapterTest(unittest.TestCase):
	def test_purchase_invoice_flush_projects_rows_before_upsert(self):
		target = Mock()
		target_document = {"doctype": 'YRP Purchase Invoice', "name": "MPI-1"}
		prepared_document = {
			**target_document,
			"items": [{"doctype": 'YRP Purchase Invoice Item', "item": "ITEM-1"}],
		}
		checkpoint = {"doctypes": {}}
		with (
			patch(
				"essdee_yrp.migration.live._prepare_purchase_invoice_migration_documents",
				return_value=[prepared_document],
			) as prepare,
			patch("essdee_yrp.migration.live.frappe.db.set_value"),
			patch("essdee_yrp.migration.live.frappe.db.commit"),
		):
			processed = _flush_batch(
				"MIG-1",
				"Purchase Invoice",
				'YRP Purchase Invoice',
				[({"name": "MPI-1"}, target_document)],
				target,
				checkpoint,
				False,
			)

		self.assertEqual(processed, 1)
		prepare.assert_called_once_with([target_document])
		target.upsert_batch.assert_called_once_with(
			'YRP Purchase Invoice', [prepared_document]
		)
		self.assertEqual(checkpoint["doctypes"]["Purchase Invoice"]["processed"], 1)

	def test_purchase_invoice_projection_is_built_before_the_migration_write(self):
		document = {
			"doctype": 'YRP Purchase Invoice',
			"name": "MPI-1",
			"docstatus": 1,
			"against": 'YRP Work Order',
			"essdee_rate_table_source": "production_api",
			"items": [],
		}
		invoice = SimpleNamespace(name="MPI-1", docstatus=1)
		with (
			patch("essdee_yrp.migration.live.frappe.get_doc", return_value=invoice),
			patch(
				"essdee_yrp.purchase_invoice.build_legacy_work_order_invoice_payload",
				return_value={
					"items": [{"item": "PHYSICAL-ITEM", "qty": 10}],
					"unlinked": False,
				},
			),
		):
			prepared = _prepare_purchase_invoice_migration_documents([document])

		self.assertEqual(document["items"], [])
		self.assertEqual(
			prepared[0]["items"],
			[
				{
					"doctype": 'YRP Purchase Invoice Item',
					"item": "PHYSICAL-ITEM",
					"docstatus": 1,
					"qty": 10,
					"rate": 0,
					"source_rate": 0,
					"amount": 0,
					"actual_rate": 0,
					"actual_qty": 0,
					"essdee_rate_weight": 0,
				}
			],
		)

	def test_purchase_order_item_numeric_defaults_survive_mixed_child_batches(self):
		document = {
			"doctype": 'YRP Purchase Invoice',
			"name": "MPI-PO-1",
			"against": 'YRP Purchase Order',
			"items": [
				{
					"doctype": 'YRP Purchase Invoice Item',
					"item": "MATERIAL-ITEM",
					"qty": 20,
					"rate": 0.33,
				}
			],
		}

		prepared = _prepare_purchase_invoice_migration_documents([document])

		self.assertNotIn("source_rate", document["items"][0])
		self.assertEqual(
			{
				fieldname: prepared[0]["items"][0][fieldname]
				for fieldname in (
					"docstatus",
					"source_rate",
					"amount",
					"actual_rate",
					"actual_qty",
					"essdee_rate_weight",
				)
			},
			{
				"docstatus": 0,
				"source_rate": 0,
				"amount": 0,
				"actual_rate": 0,
				"actual_qty": 0,
				"essdee_rate_weight": 0,
			},
		)

	def test_submitted_unlinked_invoice_blocks_the_migration_batch(self):
		document = {
			"doctype": 'YRP Purchase Invoice',
			"name": "MPI-1",
			"docstatus": 1,
			"against": 'YRP Work Order',
			"essdee_rate_table_source": "production_api",
		}
		invoice = SimpleNamespace(name="MPI-1", docstatus=1)
		with (
			patch("essdee_yrp.migration.live.frappe.get_doc", return_value=invoice),
			patch(
				"essdee_yrp.purchase_invoice.build_legacy_work_order_invoice_payload",
				return_value={"items": [], "unlinked": True},
			),
			self.assertRaisesRegex(MigrationError, "has no linked GRNs"),
		):
			_prepare_purchase_invoice_migration_documents([document])

	def test_legacy_pi_physical_rows_have_a_separately_verified_identity_allowance(self):
		with (
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
			patch("essdee_yrp.migration.live.frappe.db.sql", return_value=[[8210]]),
		):
			self.assertEqual(
				_migration_generated_identity_allowances(),
				{'YRP Purchase Invoice Item': 8210},
			)

	def test_checkpoint_resumes_only_for_the_exact_reviewed_source_snapshot(self):
		snapshot = {
			"snapshot_fingerprint": "source-a",
			"migration_contract_fingerprint": "code-a",
		}
		bound = _bind_checkpoint_to_source_snapshot(
			{"version": 2, "doctypes": {"Supplier": {"last_name": "SUP-9"}}},
			snapshot,
		)
		bound["doctypes"]["Supplier"] = {"last_name": "SUP-9"}
		resumed = _bind_checkpoint_to_source_snapshot(bound, dict(snapshot))
		self.assertEqual(resumed["doctypes"]["Supplier"]["last_name"], "SUP-9")

		changed = _bind_checkpoint_to_source_snapshot(
			bound,
			{**snapshot, "migration_contract_fingerprint": "code-b"},
		)
		self.assertEqual(changed["doctypes"], {})
		self.assertNotEqual(
			changed["source_snapshot_fingerprint"],
			bound["source_snapshot_fingerprint"],
		)

	def test_external_reference_preflight_maps_link_to_doctype_values(self):
		plan = SimpleNamespace(
			specs={
				"Ledger": SimpleNamespace(
					target="SD YRP Ledger",
					ignored_fields={},
					field_map={},
					target_schema={
						"fields": [
							{
								"fieldname": "voucher_type",
								"fieldtype": "Link",
								"options": "DocType",
							}
						]
					},
				),
				"Delivery Challan": SimpleNamespace(
					target="YRP Delivery Challan"
				),
			}
		)
		source = SimpleNamespace(
			iter_external_references=lambda: iter(
				[
					{
						"source_doctype": "Ledger",
						"source_name": "LEDGER-1",
						"fieldname": "voucher_type",
						"dynamic": False,
						"value": "Delivery Challan",
					}
				]
			)
		)

		def exists(doctype, name=None):
			if doctype == "DocType":
				return name in {"DocType", "YRP Delivery Challan"}
			return False

		with patch("essdee_yrp.migration.live.frappe.db.exists", side_effect=exists):
			checked, supporting = _validate_external_references(plan, source)

		self.assertEqual(checked, 1)
		self.assertEqual(supporting, {})

	def test_action_reservation_uses_one_named_lock_and_always_releases_it(self):
		queries = []

		def sql(query, values=None):
			queries.append((query, values))
			return [[1]]

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration.frappe.local.conf",
				{"db_name": "target_db"},
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration.frappe.db.sql",
				side_effect=sql,
			),
		):
			with _migration_action_reservation():
				pass

		self.assertIn("GET_LOCK", queries[0][0])
		self.assertIn("RELEASE_LOCK", queries[-1][0])
		self.assertEqual(queries[0][1][0], queries[-1][1][0])

	def test_worker_rejects_a_second_active_migration_record(self):
		with patch(
			"essdee_yrp.migration.live.frappe.get_all", return_value=["MIG-OTHER"]
		):
			with self.assertRaisesRegex(MigrationError, "MIG-OTHER"):
				_assert_no_other_active_migration("MIG-CURRENT")

	def test_controller_reloads_its_status_under_row_lock(self):
		doc = SimpleNamespace(name="MIG-1", reload=Mock())
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration.frappe.db.sql",
			return_value=[["MIG-1"]],
		) as sql:
			MRPDataMigration._lock_and_reload(doc)

		self.assertIn("FOR UPDATE", sql.call_args.args[0])
		doc.reload.assert_called_once_with()

	def test_reset_manifest_deletes_non_single_graph_and_preserves_singles(self):
		plan = SimpleNamespace(
			specs={
				"Parent": SimpleNamespace(
					target="Parent", is_child=False, source_schema={"issingle": 0}
				),
				"Supplier": SimpleNamespace(
					target='YRP Supplier', is_child=False, source_schema={"issingle": 0}
				),
				"Settings": SimpleNamespace(
					target="Settings", is_child=False, source_schema={"issingle": 1}
				),
				"Child": SimpleNamespace(
					target="Child", is_child=True, source_schema={"issingle": 0}
				),
			},
			target_schemas={},
		)
		source = SimpleNamespace(
			iter_series=lambda: iter(
				[
					{"name": "PARENT-.#####", "current": 3},
					{"name": "PARENT-.#####", "current": 3},
					{"name": "", "current": 7},
				]
			)
		)
		manifest = _build_target_reset_manifest(plan, source)

		self.assertEqual(manifest["parent_target_doctypes"], ["Parent", 'YRP Supplier'])
		self.assertEqual(manifest["single_target_doctypes"], ["Settings"])
		self.assertEqual(manifest["child_target_doctypes"], ["Child"])
		self.assertEqual(manifest["source_series_names"], ["", "PARENT-.#####"])
		self.assertTrue(manifest["delete_generated_supplier_warehouses"])

	def test_reset_manifest_includes_contextual_target_child_tables(self):
		plan = SimpleNamespace(
			specs={
				"Item Production Detail": SimpleNamespace(
					target='YRP Item Production Detail',
					is_child=False,
					source_schema={"issingle": 0},
				),
				"Item Item Attribute": SimpleNamespace(
					target='YRP Item Item Attribute',
					is_child=True,
					source_schema={"issingle": 0},
				),
			},
			target_schemas={
				'YRP Item Production Detail': {
					"fields": [
						{
							"fieldname": "item_attributes",
							"fieldtype": "Table",
							"options": 'YRP IPD Item Attribute',
						}
					]
				}
			},
		)
		source = SimpleNamespace(iter_series=lambda: iter([]))

		manifest = _build_target_reset_manifest(plan, source)

		self.assertEqual(
			manifest["child_target_doctypes"],
			['YRP IPD Item Attribute', 'YRP Item Item Attribute'],
		)

	def test_guarded_queue_entrypoints_mark_preflight_failures(self):
		for entrypoint, target in (
			(run_job_guarded, "essdee_yrp.migration.live.run_job"),
			(run_reset_job_guarded, "essdee_yrp.migration.live.run_reset_job"),
		):
			with (
				patch(target, side_effect=MigrationError("preflight")),
				patch(
					"essdee_yrp.migration.live.frappe.db.get_value",
					return_value="Queued",
				),
				patch("essdee_yrp.migration.live._mark_failed") as mark_failed,
				self.assertRaisesRegex(MigrationError, "preflight"),
			):
				entrypoint(migration_name="MIG-1")
			mark_failed.assert_called_once_with("MIG-1")

	def test_reset_revalidates_profile_defaults_after_deletion(self):
		settings = SimpleNamespace(
			target_site="target.test",
			source_site="source.test",
			required_defaults={
				"IPD Settings.default_knitting_process": "Knitting",
				"IPD Settings.default_dyeing_process": "Dyeing",
			},
		)
		plan = SimpleNamespace(ready=True)
		source = SimpleNamespace(
			status=Mock(return_value={"site": "source.test", "maintenance_mode": True})
		)
		migration = SimpleNamespace()
		before = {"total": 0}
		after = {"total": 0}

		with ExitStack() as stack:
			for target, kwargs in (
				("essdee_yrp.migration.live.get_migration_settings", {"return_value": settings}),
				("essdee_yrp.migration.live.is_target_reset_enabled", {"return_value": True}),
				("essdee_yrp.migration.live._assert_target_site", {}),
				("essdee_yrp.migration.live._assert_no_other_active_migration", {}),
				("essdee_yrp.migration.live.frappe.get_doc", {"return_value": migration}),
				("essdee_yrp.migration.live.F15SourceBridge", {"return_value": source}),
				(
					"essdee_yrp.migration.live.build_live_schema_analysis",
					{"return_value": (plan, {"target_prerequisites": {}})},
				),
				("essdee_yrp.migration.live._validate_live_target_metadata", {}),
				("essdee_yrp.migration.live._source_broken_link_manifest", {"return_value": []}),
				("essdee_yrp.migration.live._source_snapshot", {"return_value": {}}),
				("essdee_yrp.migration.live._require_previous_snapshot", {}),
				(
					"essdee_yrp.migration.live._build_target_reset_manifest",
					{"return_value": {"single_target_doctypes": []}},
				),
				("essdee_yrp.migration.live._target_reset_counts", {"side_effect": [{}, {}]}),
				(
					"essdee_yrp.migration.live._include_reset_generated_audit_scope",
					{"side_effect": [before, after]},
				),
				(
					"essdee_yrp.migration.live._bind_reset_series_checkpoint",
					{"return_value": before},
				),
				("essdee_yrp.migration.live._mark_reset_started", {}),
				("essdee_yrp.migration.live._delete_target_reset_manifest", {}),
				("essdee_yrp.migration.live._nonzero_reset_counts", {"return_value": {}}),
				(
					"essdee_yrp.migration.live._target_stock_contract",
					{"return_value": ([], [], [])},
				),
				("essdee_yrp.migration.live._mark_reset_complete", {}),
				("essdee_yrp.migration.live.frappe.clear_cache", {}),
			):
				stack.enter_context(patch(target, **kwargs))
			validate_prerequisites = stack.enter_context(
				patch(
					"essdee_yrp.migration.live._validate_target_migration_prerequisites",
					return_value={},
				)
			)
			result = run_reset_job("MIG-1")

		validate_prerequisites.assert_called_once_with(
			[],
			plan=plan,
			source=source,
			required_defaults=settings.required_defaults,
		)
		self.assertEqual(result["preserved_target_prerequisites"], {})

	def test_migration_jobs_enqueue_only_after_the_queued_state_commits(self):
		with patch("essdee_yrp.migration.live.frappe.enqueue") as enqueue:
			enqueue_job("MIG-1", "dry_run", allow_missing_files=True)
			self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
			self.assertEqual(
				enqueue.call_args.args[0],
				"essdee_yrp.migration.live.run_job_guarded",
			)

			enqueue.reset_mock()
			enqueue_reset_job("MIG-1")
			self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
			self.assertEqual(
				enqueue.call_args.args[0],
				"essdee_yrp.migration.live.run_reset_job_guarded",
			)

	def test_reset_delete_never_deletes_a_preserved_single_table(self):
		manifest = {
			"parent_target_doctypes": ["Parent", 'YRP Supplier'],
			"single_target_doctypes": ["Settings"],
			"child_target_doctypes": ["Child"],
			"source_series_names": ["PARENT-.#####"],
			"delete_generated_supplier_warehouses": True,
		}
		before = {
			"file_names": ["FILE-1", "FILE-2"],
			"reset_generated_deleted_document_names": [],
			"generated_supplier_warehouse_names": ["SUP-1"],
			"child_counts": {"Child": 2},
			"parent_counts": {"Parent": 1, 'YRP Supplier': 1},
			"preserved_series_values": {"": 7, "PARENT-.#####": 3},
		}
		with (
			patch("essdee_yrp.migration.live._delete_reset_file") as delete_file,
			patch("essdee_yrp.migration.live.frappe.db.delete") as delete,
			patch("essdee_yrp.migration.live.frappe.db.sql") as sql,
			patch("essdee_yrp.migration.live.frappe.db.commit"),
			patch("essdee_yrp.migration.live.frappe.db.set_value"),
			patch("essdee_yrp.migration.live._update_progress") as update_progress,
		):
			_delete_target_reset_manifest("MIG-1", manifest, before)

		self.assertEqual(delete_file.call_args_list, [call("FILE-1"), call("FILE-2")])
		deleted_doctypes = [call.args[0] for call in delete.call_args_list]
		self.assertEqual(deleted_doctypes, ['YRP Warehouse', "Child", "Parent", 'YRP Supplier'])
		self.assertNotIn("Settings", deleted_doctypes)
		sql.assert_not_called()
		self.assertEqual(
			[call.args[1] for call in update_progress.call_args_list],
			[1, 2, 3, 5, 6, 7],
		)
		self.assertEqual(_nonzero_reset_counts({"parent_total": 0}), {})

	def test_reset_file_uses_physical_lifecycle_without_queueing(self):
		doc = SimpleNamespace(
			validate_protected_file=Mock(),
			_delete_file_on_disk=Mock(),
		)
		with (
			patch("essdee_yrp.migration.live.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.migration.live.frappe.delete_doc") as delete_doc,
			patch("frappe.model.delete_doc.delete_dynamic_links") as delete_links,
		):
			_delete_reset_file("FILE-1")

		doc.validate_protected_file.assert_called_once_with()
		doc._delete_file_on_disk.assert_called_once_with()
		delete_doc.assert_called_once_with(
			"File",
			"FILE-1",
			ignore_permissions=True,
			force=True,
			for_reload=True,
			delete_permanently=True,
		)
		delete_links.assert_called_once_with("File", "FILE-1")

	def test_reset_retry_includes_only_exact_checkpointed_audit_identities(self):
		counts = {"total": 10}
		migration = SimpleNamespace(
			checkpoint_json=json.dumps(
				{
					"mode": "reset",
					"reset_started_on": "2026-08-25 21:29:47.466686",
					"reset_generated_deleted_document_names": [
						"DELETED-1",
						"DELETED-2",
					],
					"reset_generated_comment_names": ["COMMENT-1", "COMMENT-2"],
				}
			)
		)

		def get_all(doctype, **kwargs):
			requested = kwargs["filters"]["name"][1]
			return [name for name in requested if name != "DELETED-2"]

		with patch(
			"essdee_yrp.migration.live.frappe.get_all", side_effect=get_all
		) as get_all_mock:
			result = _include_reset_generated_audit_scope(migration, counts)

		self.assertEqual(result["reset_generated_deleted_document_total"], 1)
		self.assertEqual(result["reset_generated_comment_total"], 2)
		self.assertEqual(result["reset_generated_audit_total"], 3)
		self.assertEqual(result["total"], 13)
		self.assertTrue(
			all(
				call.kwargs["filters"].keys() == {"name"}
				and call.kwargs["limit_page_length"] == 0
				for call in get_all_mock.call_args_list
			)
		)

	def test_failed_reset_analysis_preserves_the_original_reset_start(self):
		doc = SimpleNamespace(
			status="Failed",
			last_action="Reset Target",
			last_started_on="2026-08-25 21:29:47.466686",
			checkpoint_json=json.dumps(
				{"mode": "reset", "preserved_series_values": {"": 5207}}
			),
		)

		MRPDataMigration._preserve_failed_reset_checkpoint(doc)

		checkpoint = json.loads(doc.checkpoint_json)
		self.assertEqual(
			checkpoint["reset_started_on"], "2026-08-25 21:29:47.466686"
		)

	def test_fresh_reset_checkpoint_serializes_its_start_time(self):
		started_on = datetime(2026, 8, 25, 23, 46, 12, 123456)
		with (
			patch("essdee_yrp.migration.live.now_datetime", return_value=started_on),
			patch("essdee_yrp.migration.live.frappe.db.set_value") as set_value,
			patch("essdee_yrp.migration.live.frappe.db.commit"),
		):
			_mark_reset_started(
				"MIG-1",
				{"total": 5, "preserved_series_values": {"": 7}},
			)

		checkpoint = json.loads(set_value.call_args_list[0].args[2]["checkpoint_json"])
		self.assertEqual(checkpoint["reset_started_on"], str(started_on))
		self.assertEqual(checkpoint["preserved_series_values"], {"": 7})
		self.assertEqual(checkpoint["reset_generated_deleted_document_names"], [])
		self.assertEqual(checkpoint["reset_generated_comment_names"], [])

	def test_reset_counts_preserve_every_series_value_exactly(self):
		manifest = {
			"parent_target_doctypes": [],
			"single_target_doctypes": [],
			"child_target_doctypes": [],
			"source_series_names": ["", "SOURCE-.#####"],
			"delete_generated_supplier_warehouses": False,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.sql",
			return_value=[["", 5207], ["TARGET-.#####", 91]],
		):
			before = _target_reset_counts(manifest)

		self.assertEqual(before["total"], 0)
		self.assertEqual(before["series_total"], 0)
		self.assertEqual(before["preserved_series_total"], 2)
		self.assertEqual(
			before["preserved_series_values"], {"": 5207, "TARGET-.#####": 91}
		)

		with patch(
			"essdee_yrp.migration.live.frappe.db.sql",
			return_value=[["", 5207], ["TARGET-.#####", 92]],
		):
			after = _target_reset_counts(manifest, expected_identities=before)

		self.assertEqual(after["preserved_series_mismatch_total"], 1)
		self.assertEqual(
			_nonzero_reset_counts(after), {"preserved_series_mismatch_total": 1}
		)

	def test_reset_retry_keeps_the_first_series_checkpoint(self):
		before = {
			"preserved_series_values": {"": 5207, "TARGET-.#####": 91},
			"preserved_series_total": 2,
			"preserved_series_mismatch_total": 0,
			"preserved_series_mismatches": [],
		}
		migration = SimpleNamespace(
			checkpoint_json=json.dumps(
				{
					"mode": "reset",
					"preserved_series_values": {
						"": 5207,
						"TARGET-.#####": 91,
					},
				}
			)
		)
		bound = _bind_reset_series_checkpoint(migration, before)
		self.assertEqual(
			bound["preserved_series_values"], before["preserved_series_values"]
		)

		before["preserved_series_values"] = {"": 5207, "TARGET-.#####": 92}
		with self.assertRaisesRegex(MigrationError, "after the first reset attempt"):
			_bind_reset_series_checkpoint(migration, before)

	def test_reset_post_counts_reinventory_the_complete_current_scope(self):
		manifest = {
			"parent_target_doctypes": [],
			"single_target_doctypes": [],
			"child_target_doctypes": [],
			"source_series_names": [],
			"delete_generated_supplier_warehouses": True,
		}
		expected = {
			"file_names": ["OLD-FILE"],
			"generated_supplier_warehouse_names": ["OLD-WAREHOUSE"],
			"preserved_series_values": {"WO-": 40},
		}
		with (
			patch(
				"essdee_yrp.migration.live._target_reset_file_names",
				return_value=["NEW-FILE"],
			),
			patch(
				"essdee_yrp.migration.live._generated_supplier_warehouse_names",
				return_value=["NEW-WAREHOUSE"],
			),
			patch(
				"essdee_yrp.migration.live._target_series_values",
				return_value={"WO-": 40},
			),
			patch(
				"essdee_yrp.migration.live._existing_document_names",
				side_effect=lambda doctype, _names: [
					"OLD-FILE" if doctype == "File" else "OLD-WAREHOUSE"
				],
			),
		):
			after = _target_reset_counts(manifest, expected_identities=expected)

		self.assertEqual(after["file_names"], ["NEW-FILE", "OLD-FILE"])
		self.assertEqual(
			after["generated_supplier_warehouse_names"],
			["NEW-WAREHOUSE", "OLD-WAREHOUSE"],
		)
		self.assertEqual(after["total"], 4)

	def test_reset_files_include_only_non_single_parent_graph(self):
		manifest = {
			"parent_target_doctypes": ["Parent"],
			"single_target_doctypes": ["Settings"],
			"child_target_doctypes": ["Child"],
		}
		file_rows = [
			SimpleNamespace(
				name="FILE-PARENT",
				attached_to_doctype="Parent",
				attached_to_name="P-1",
			),
			SimpleNamespace(
				name="FILE-CHILD-DELETE",
				attached_to_doctype="Child",
				attached_to_name="C-1",
			),
			SimpleNamespace(
				name="FILE-CHILD-PRESERVE",
				attached_to_doctype="Child",
				attached_to_name="C-SETTINGS",
			),
		]

		def get_all(doctype, **kwargs):
			return file_rows if doctype == "File" else ["C-1"]

		with patch(
			"essdee_yrp.migration.live.frappe.get_all", side_effect=get_all
		) as get_all_mock:
			names = _target_reset_file_names(manifest)

		self.assertEqual(names, ["FILE-PARENT", "FILE-CHILD-DELETE"])
		self.assertTrue(get_all_mock.call_args_list)
		self.assertTrue(
			all(
				call.kwargs.get("limit_page_length") == 0
				for call in get_all_mock.call_args_list
			)
		)
		child_call = next(
			call for call in get_all_mock.call_args_list if call.args[0] == "Child"
		)
		self.assertEqual(
			child_call.kwargs["filters"]["name"],
			["in", ["C-1", "C-SETTINGS"]],
		)

	def test_generated_supplier_warehouse_scope_survives_a_missing_supplier(self):
		manifest = {"delete_generated_supplier_warehouses": True}
		with patch(
			"essdee_yrp.migration.live.frappe.db.sql",
			return_value=[["SUP-ORPHAN"]],
		) as sql:
			names = _generated_supplier_warehouse_names(manifest)

		self.assertEqual(names, ["SUP-ORPHAN"])
		self.assertNotIn("JOIN", sql.call_args.args[0].upper())

	def test_target_reset_enable_flag_parses_zero_as_disabled(self):
		with patch(
			"essdee_yrp.migration.config.frappe",
			SimpleNamespace(conf={"essdee_yrp_allow_target_reset": "0"}),
		):
			self.assertFalse(is_target_reset_enabled())
		with patch(
			"essdee_yrp.migration.config.frappe",
			SimpleNamespace(conf={"essdee_yrp_allow_target_reset": "1"}),
		):
			self.assertTrue(is_target_reset_enabled())

	def test_target_migration_prerequisites_cover_production_and_stock_settings(self):
		values = {
			('SD YRP IPD Settings', "item_group"): "Products",
			('SD YRP IPD Settings', "default_cutting_process"): "Cutting",
			('SD YRP IPD Settings', "default_knitting_process"): "Knitting",
			('SD YRP IPD Settings', "default_dyeing_process"): "Dyeing",
			('SD YRP IPD Settings', "default_packing_process"): "Packing",
			('SD YRP IPD Settings', "default_pack_in_stage"): "Piece",
			('SD YRP IPD Settings', "default_packing_attribute"): "Colour",
			('SD YRP IPD Settings', "default_pack_out_stage"): "Pack",
			('SD YRP IPD Settings', "default_stitching_process"): "Stitching",
			('SD YRP IPD Settings', "default_stitching_in_stage"): "Cut",
			('SD YRP IPD Settings', "default_stitching_attribute"): "Panel",
			('SD YRP IPD Settings', "default_stitching_out_stage"): "Piece",
			('SD YRP IPD Settings', "default_set_item_attribute"): "Part",
			('YRP YRP Stock Settings', "transit_warehouse"): "S-0165",
			('YRP YRP Stock Settings', "default_received_type"): "Accepted",
			('YRP YRP Stock Settings', "default_rejected_received_type"): "Rejected",
		}
		dimensions = [
			{
				"dimension_doctype": 'SD YRP Lot',
				"fieldname": "lot",
				"label": "Lot",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 1,
			},
			{
				"dimension_doctype": 'YRP Received Type',
				"fieldname": "received_type",
				"label": "Received Type",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 0,
			},
		]
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_single_value",
				side_effect=lambda doctype, fieldname: values[(doctype, fieldname)],
			),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
		):
			result = _validate_target_migration_prerequisites(dimensions)

		self.assertEqual(result["ipd_settings"]["item_group"], "Products")
		self.assertEqual(
			[row["fieldname"] for row in result["stock_dimensions"]],
			["lot", "received_type"],
		)

	def test_target_migration_prerequisites_reject_missing_and_unsafe_dimensions(self):
		def get_value(doctype, fieldname):
			if (doctype, fieldname) == ('SD YRP IPD Settings', "default_cutting_process"):
				return None
			return "Configured Value"

		dimensions = [
			{
				"dimension_doctype": 'SD YRP Lot',
				"fieldname": "lot",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 1,
			},
			{
				"dimension_doctype": 'YRP Received Type',
				"fieldname": "received_type",
				"mandatory": 1,
				"in_valuation": 0,
				"is_production_group": 0,
			},
		]
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_single_value",
				side_effect=get_value,
			),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
			self.assertRaisesRegex(
				MigrationError,
				"default_cutting_process is required[\\s\\S]*received_type[\\s\\S]*in_valuation=1",
			),
		):
			_validate_target_migration_prerequisites(dimensions)

	def test_empty_target_ipd_settings_use_production_api_and_profile_defaults(self):
		stock_values = {
			('YRP YRP Stock Settings', "transit_warehouse"): "S-0165",
			('YRP YRP Stock Settings', "default_received_type"): "Accepted",
			('YRP YRP Stock Settings', "default_rejected_received_type"): "Rejected",
		}
		dimensions = [
			{
				"dimension_doctype": 'SD YRP Lot',
				"fieldname": "lot",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 1,
			},
			{
				"dimension_doctype": 'YRP Received Type',
				"fieldname": "received_type",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 0,
			},
		]
		source_ipd_settings = {
			"doctype": "IPD Settings",
			"name": "IPD Settings",
			"item_group": "Products",
			"default_cutting_process": "Cutting",
			"default_packing_process": "Packing",
			"default_pack_in_stage": "Piece",
			"default_packing_attribute": "Colour",
			"default_pack_out_stage": "Pack",
			"default_stitching_process": "Stitching",
			"default_stitching_in_stage": "Cut",
			"default_stitching_attribute": "Panel",
			"default_stitching_out_stage": "Piece",
			"default_set_item_attribute": "Part",
		}
		plan = SimpleNamespace(
			specs={
				"Item Group": SimpleNamespace(target='YRP Item Group', is_child=False),
				"Item Attribute": SimpleNamespace(target='YRP Item Attribute', is_child=False),
				"Item Attribute Value": SimpleNamespace(
					target='YRP Item Attribute Value', is_child=False
				),
				"Process": SimpleNamespace(target='YRP Process', is_child=False),
				"Supplier": SimpleNamespace(target='YRP Supplier', is_child=False),
				"GRN Item Type": SimpleNamespace(target='YRP Received Type', is_child=False),
			}
		)
		source = SimpleNamespace(
			iter_documents=lambda doctype, **_kwargs: iter(
				[source_ipd_settings] if doctype == "IPD Settings" else []
			),
			document_exists=lambda _doctype, _value: True,
		)
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_single_value",
				side_effect=lambda doctype, fieldname: stock_values.get(
					(doctype, fieldname)
				),
			),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=False),
		):
			result = _validate_target_migration_prerequisites(
				dimensions,
				plan=plan,
				source=source,
				required_defaults={
					"IPD Settings.default_knitting_process": "Knitting",
					"IPD Settings.default_dyeing_process": "Dyeing",
				},
			)

		self.assertEqual(result["ipd_settings"]["default_cutting_process"], "Cutting")
		self.assertEqual(result["ipd_settings"]["default_knitting_process"], "Knitting")
		self.assertEqual(
			result["ipd_settings_sources"],
			{
				"item_group": "production_api",
				"default_cutting_process": "production_api",
				"default_knitting_process": "migration_profile",
				"default_dyeing_process": "migration_profile",
				"default_packing_process": "production_api",
				"default_pack_in_stage": "production_api",
				"default_packing_attribute": "production_api",
				"default_pack_out_stage": "production_api",
				"default_stitching_process": "production_api",
				"default_stitching_in_stage": "production_api",
				"default_stitching_attribute": "production_api",
				"default_stitching_out_stage": "production_api",
				"default_set_item_attribute": "production_api",
			},
		)

	def test_target_migration_prerequisites_parse_string_check_values(self):
		dimensions = [
			{
				"dimension_doctype": 'SD YRP Lot',
				"fieldname": "lot",
				"mandatory": "1",
				"in_valuation": "1",
				"is_production_group": "1",
			},
			{
				"dimension_doctype": 'YRP Received Type',
				"fieldname": "received_type",
				"mandatory": "1",
				"in_valuation": "1",
				"is_production_group": "0",
			},
		]
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_single_value",
				return_value="Configured Value",
			),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
		):
			result = _validate_target_migration_prerequisites(dimensions)

		self.assertEqual(
			result["stock_dimensions"][1]["is_production_group"], "0"
		)

	def test_target_migration_prerequisites_resolve_links_from_frozen_source_after_reset(self):
		values = {
			('SD YRP IPD Settings', fieldname): value
			for fieldname, value in {
				"item_group": "Products",
				"default_primary_attribute": "Size",
				"default_cutting_process": "Cutting",
				"default_knitting_process": "Knitting",
				"default_dyeing_process": "Dyeing",
				"default_packing_process": "Packing",
				"default_pack_in_stage": "Piece",
				"default_packing_attribute": "Colour",
				"default_pack_out_stage": "Pack",
				"default_stitching_process": "Stitching",
				"default_stitching_in_stage": "Cut",
				"default_stitching_attribute": "Panel",
				"default_stitching_out_stage": "Piece",
				"default_set_item_attribute": "Part",
			}.items()
		}
		values.update(
			{
				('YRP YRP Stock Settings', "transit_warehouse"): "S-0165",
				('YRP YRP Stock Settings', "default_received_type"): "Accepted",
				('YRP YRP Stock Settings', "default_rejected_received_type"): "Rejected",
			}
		)
		dimensions = [
			{
				"dimension_doctype": 'SD YRP Lot',
				"fieldname": "lot",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 1,
			},
			{
				"dimension_doctype": 'YRP Received Type',
				"fieldname": "received_type",
				"mandatory": 1,
				"in_valuation": 1,
				"is_production_group": 0,
			},
		]
		plan = SimpleNamespace(
			specs={
				"Item Group": SimpleNamespace(target='YRP Item Group', is_child=False),
				"Item Attribute": SimpleNamespace(target='YRP Item Attribute', is_child=False),
				"Item Attribute Value": SimpleNamespace(
					target='YRP Item Attribute Value', is_child=False
				),
				"Process": SimpleNamespace(target='YRP Process', is_child=False),
				"Supplier": SimpleNamespace(target='YRP Supplier', is_child=False),
				"GRN Item Type": SimpleNamespace(target='YRP Received Type', is_child=False),
			}
		)
		source = SimpleNamespace(document_exists=lambda doctype, value: True)
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_single_value",
				side_effect=lambda doctype, fieldname: values[(doctype, fieldname)],
			),
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=False),
		):
			result = _validate_target_migration_prerequisites(
				dimensions, plan=plan, source=source
			)

		self.assertEqual(result["stock_settings"]["transit_warehouse"], "S-0165")

	def test_missing_link_doctype_uses_structured_failure_result(self):
		with patch("essdee_yrp.migration.live.frappe.db.exists", return_value=False):
			self.assertEqual(
				_broken_static_link_count(
					"Parent", "reference", "Missing Master", is_single=False
				),
				{
					"total": 1,
					"audited": 0,
					"unexpected": 1,
					"samples": ["missing target DocType Missing Master"],
				},
			)

	def test_value_audit_flattens_children_with_written_parent_metadata(self):
		plan = SimpleNamespace(
			target_schemas={
				"Parent": {
					"fields": [
						{
							"fieldname": "items",
							"fieldtype": "Table",
							"options": "Child",
						}
					]
				},
				"Child": {"fields": [{"fieldname": "value", "fieldtype": "Data"}]},
			}
		)
		grouped = {}
		skipped = _collect_expected_value_rows(
			{
				"doctype": "Parent",
				"name": "P-1",
				"title": "One",
				"items": [
					{
						"doctype": "Child",
						"name": "C-1",
						"idx": 99,
						"value": "A",
					}
				],
			},
			plan,
			grouped,
		)
		self.assertEqual(skipped, 0)
		self.assertEqual(grouped["Parent"], [{"name": "P-1", "title": "One"}])
		self.assertEqual(
			grouped["Child"],
			[
				{
					"name": "C-1",
					"idx": 1,
					"value": "A",
					"parent": "P-1",
					"parenttype": "Parent",
					"parentfield": "items",
				}
			],
		)

	def test_value_audit_uses_database_equivalent_numeric_and_json_comparison(self):
		self.assertTrue(_same_migrated_value(1, 1.0, "Float"))
		self.assertTrue(
			_same_migrated_value(
				"1619.333333333", "1619.333", "Float", numeric_scale=3
			)
		)
		self.assertFalse(
			_same_migrated_value("1619.333333333", "1619.333", "Float")
		)
		self.assertTrue(_same_migrated_value({"b": 2, "a": 1}, '{"a":1,"b":2}', "JSON"))
		self.assertFalse(_same_migrated_value(None, "", "Data"))

	def test_value_audit_accepts_only_exact_file_lifecycle_attachment_url(self):
		with patch(
			"essdee_yrp.migration.live.frappe.db.exists", return_value="FILE-1"
		) as exists:
			self.assertTrue(
				_is_verified_attachment_url(
					'SD YRP Product Image', "IMG-1", "image", "/files/renamed.png", "Attach Image"
				)
			)
		exists.assert_called_once_with(
			"File",
			{
				"is_folder": 0,
				"attached_to_doctype": 'SD YRP Product Image',
				"attached_to_name": "IMG-1",
				"attached_to_field": "image",
				"file_url": "/files/renamed.png",
			},
		)
		self.assertFalse(
			_is_verified_attachment_url(
				'SD YRP Product Image', "IMG-1", "title", "/files/renamed.png", "Data"
			)
		)

	def test_single_identity_is_counted_without_querying_a_physical_table(self):
		plan = SimpleNamespace(
			target_schemas={'SD YRP Company Settings': {"issingle": 1, "fields": []}}
		)
		pending = {}
		expected = {}
		_collect_document_identities(
			{"doctype": 'SD YRP Company Settings', "name": 'SD YRP Company Settings'},
			plan,
			pending,
			expected,
		)
		self.assertEqual(pending, {})
		self.assertEqual(expected, {'SD YRP Company Settings': 1})

	def test_generated_child_identity_is_counted_without_a_source_name(self):
		plan = SimpleNamespace(
			target_schemas={
				'SD YRP Essdee Purchase Invoice Item': {"issingle": 0, "fields": []}
			}
		)
		pending = {}
		expected = {}
		_collect_document_identities(
			{
				"doctype": 'SD YRP Essdee Purchase Invoice Item',
				"parent": "PI-1",
				"parenttype": 'YRP Purchase Invoice',
				"parentfield": "essdee_items",
				"idx": 1,
			},
			plan,
			pending,
			expected,
		)
		self.assertEqual(pending, {})
		self.assertEqual(expected, {'SD YRP Essdee Purchase Invoice Item': 1})

	def test_value_audit_uses_child_position_for_generated_rows(self):
		doctype = 'SD YRP Essdee Purchase Invoice Item'
		document = {
			"doctype": doctype,
			"item": "ITEM-1",
			"parent": "PI-1",
			"parenttype": 'YRP Purchase Invoice',
			"parentfield": "essdee_items",
			"idx": 1,
		}
		actual = {"name": "generated-name", **document}
		actual.pop("doctype")
		plan = SimpleNamespace(
			target_schemas={
				doctype: {
					"issingle": 0,
					"fields": [{"fieldname": "item", "fieldtype": "Link"}],
				}
			}
		)

		def sql(query, _values=None, **_kwargs):
			return [] if "information_schema" in query else [actual]

		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_table_columns",
				return_value=[
					"name",
					"item",
					"parent",
					"parenttype",
					"parentfield",
					"idx",
				],
			),
			patch("essdee_yrp.migration.live.frappe.db.sql", side_effect=sql),
		):
			result = _verify_transformed_value_batch([document], plan)

		self.assertEqual(result["documents"], 1)
		self.assertEqual(result["failures"], [])

	def test_orphan_attachment_is_audited_without_creating_target_file(self):
		row = {
			"name": "FILE-ORPHAN",
			"file_name": "orphan.png",
			"file_url": "/private/files/orphan.png",
			"file_size": 10,
			"content_hash": "hash-1",
			"is_private": 1,
			"attached_to_doctype": "Product Sub brand",
			"attached_to_name": "DELETED-PARENT",
			"attached_to_field": "sub_brand_image",
			"missing_blob": 1,
			"orphan_attachment": 1,
		}
		source = SimpleNamespace(
			settings=configured_settings(),
			file_status=lambda: {
				"site": "source.test",
				"file_count": 1,
				"file_bytes": 10,
				"unique_content_count": 1,
				"unique_content_bytes": 10,
				"max_file_size": 10,
			},
			iter_files=lambda **_kwargs: iter([row]),
		)
		plan = SimpleNamespace(
			specs={
				"Product Sub brand": SimpleNamespace(
					target='SD YRP Product Sub brand', field_map={}
				)
			}
		)
		checkpoint = {"version": 2, "doctypes": {}}
		with (
			patch("essdee_yrp.migration.live._load_checkpoint", return_value=checkpoint),
			patch("essdee_yrp.migration.live._prepare_file_settings"),
			patch("essdee_yrp.migration.live._restore_file_settings"),
			patch("essdee_yrp.migration.live._repair_file_links"),
			patch("essdee_yrp.migration.live.frappe.db.set_value"),
			patch("essdee_yrp.migration.live.frappe.db.commit"),
			patch.object(FrappeBulkTarget, "upsert_missing_file_metadata") as upsert,
		):
			result = _run_files(
				"MIG-1", plan, source, dry_run=False, allow_missing_files=True
			)

		upsert.assert_not_called()
		self.assertEqual(result["processed"], 1)
		self.assertEqual(result["orphan_attachment_count"], 1)
		self.assertEqual(checkpoint["files"]["orphan_attachment_names"], ["FILE-ORPHAN"])

	def test_selected_attachment_bridge_arguments_are_explicit(self):
		bridge = F15SourceBridge(configured_settings())
		with patch.object(bridge, "_run", return_value=iter([{"file_count": 2}])) as run:
			self.assertEqual(bridge.file_status(names=["FILE-2", "FILE-1"])["file_count"], 2)
		run.assert_called_once_with(
			["file-status", "--names-json", '["FILE-1", "FILE-2"]']
		)

	def test_series_bridge_is_fixed_to_the_source_series_command(self):
		bridge = F15SourceBridge(configured_settings())
		with patch.object(
			bridge,
			"_run",
			return_value=iter([{"name": "WO-", "current": 42}]),
		) as run:
			self.assertEqual(
				list(bridge.iter_series()),
				[{"name": "WO-", "current": 42}],
			)
		run.assert_called_once_with(["series"])

		with patch.object(bridge, "_run", return_value=iter([])) as run:
			self.assertEqual(
				list(
					bridge.iter_files(
						names=["FILE-2", "FILE-1"], allow_missing=True
					)
				),
				[],
			)
		run.assert_called_once_with(
			[
				"files",
				"--names-json",
				'["FILE-1", "FILE-2"]',
				"--allow-missing",
			]
		)

	def test_configured_default_can_resolve_from_frozen_source_master(self):
		settings = configured_settings()
		settings = MigrationSettings(
			**{
				**settings.__dict__,
				"required_defaults": {"Lot BOM.process_name": "Packing"},
			}
		)
		plan = SimpleNamespace(
			target_schemas={
				'SD YRP Lot BOM': {
					"fields": [
						{
							"fieldname": "process_name",
							"fieldtype": "Link",
							"options": 'YRP Process',
						}
					]
				}
			},
			specs={
				"Lot BOM": SimpleNamespace(target='SD YRP Lot BOM', is_child=True),
				"Process": SimpleNamespace(target='YRP Process', is_child=False)
			},
		)
		source = SimpleNamespace(document_exists=lambda doctype, name: True)
		with patch(
			"essdee_yrp.migration.live.frappe.db.exists", return_value=False
		):
			_validate_configured_default_contract(plan, settings, source)

	def test_unknown_configured_default_fails_schema_analysis(self):
		settings = configured_settings()
		settings = MigrationSettings(
			**{
				**settings.__dict__,
				"required_defaults": {"Lot BOM.misspelled_field": "Packing"},
			}
		)
		plan = SimpleNamespace(
			target_schemas={'SD YRP Lot BOM': {"fields": []}},
			specs={"Lot BOM": SimpleNamespace(target='SD YRP Lot BOM')},
		)
		with self.assertRaisesRegex(MigrationError, "Unknown configured migration default"):
			_validate_configured_default_contract(plan, settings, SimpleNamespace())

	def test_migration_contract_fingerprint_includes_server_defaults(self):
		base = configured_settings()
		changed = MigrationSettings(
			**{
				**base.__dict__,
				"required_defaults": {"Lot BOM.process_name": "Packing"},
			}
		)
		plan = SimpleNamespace(target_schemas={}, specs={})
		self.assertNotEqual(
			_migration_contract_fingerprint(base, plan),
			_migration_contract_fingerprint(changed, plan),
		)

	def test_source_snapshot_fingerprint_includes_target_prerequisites(self):
		settings = configured_settings()
		plan = SimpleNamespace(target_schemas={}, specs={})
		status = {
			"snapshot_fingerprint": "source-1",
			"total_parent_records": 1,
		}
		before = _source_snapshot(
			settings,
			status,
			[],
			plan,
			{"stock_settings": {"default_received_type": "Accepted"}},
		)
		after = _source_snapshot(
			settings,
			status,
			[],
			plan,
			{"stock_settings": {"default_received_type": "Fresh"}},
		)
		self.assertNotEqual(
			before["target_prerequisite_fingerprint"],
			after["target_prerequisite_fingerprint"],
		)

	def test_migrate_requires_the_exact_dry_run_snapshot(self):
		migration = SimpleNamespace(
			report_json=json.dumps(
				{"source_snapshot": {"migration_contract_fingerprint": "before"}}
			)
		)
		_require_previous_snapshot(
			migration,
			"migrate",
			{"migration_contract_fingerprint": "before"},
		)
		with self.assertRaisesRegex(MigrationError, "changed after the previous"):
			_require_previous_snapshot(
				migration,
				"migrate",
				{"migration_contract_fingerprint": "after"},
			)

	def test_attachment_transport_is_byte_and_hash_checked(self):
		content = b"historical attachment bytes\x00\xff"
		row = {
			"name": "FILE-1",
			"file_size": len(content),
			"content_hash": hashlib.md5(content, usedforsecurity=False).hexdigest(),
			"content_base64": base64.b64encode(content).decode("ascii"),
		}
		self.assertEqual(_decode_and_validate_file_payload(row), content)
		row["content_hash"] = "incorrect"
		with self.assertRaisesRegex(MigrationError, "hash mismatch"):
			_decode_and_validate_file_payload(row)

	def test_single_child_tables_are_replaced_with_target_parent_identity(self):
		meta = SimpleNamespace(
			name='SD YRP MRP Settings',
			get_table_fields=lambda: [
				SimpleNamespace(fieldname="routes", options="MRP Settings Route")
			],
		)
		target = FrappeBulkTarget()
		bulk_rows = []
		with (
			patch("essdee_yrp.migration.live.frappe.db.delete") as delete,
			patch.object(target, "_bulk_upsert", side_effect=lambda doctype, rows: bulk_rows.extend(rows)),
		):
			target._replace_child_tables(
				meta,
				[
					{
						"doctype": 'SD YRP MRP Settings',
						"name": 'SD YRP MRP Settings',
						"routes": [
							{
								"doctype": "MRP Settings Route",
								"name": "ROW-1",
								"route": 'YRP Goods Received Note',
							}
						],
					}
				],
			)

		delete.assert_called_once_with(
			"MRP Settings Route",
			{
				"parenttype": 'SD YRP MRP Settings',
				"parentfield": "routes",
				"parent": ["in", ['SD YRP MRP Settings']],
			},
		)
		self.assertEqual(bulk_rows[0]["parenttype"], 'SD YRP MRP Settings')
		self.assertEqual(bulk_rows[0]["parentfield"], "routes")
		self.assertEqual(bulk_rows[0]["parent"], 'SD YRP MRP Settings')

	def test_renamed_single_child_replacement_cleans_source_and_target_parents(self):
		meta = SimpleNamespace(
			name='SD YRP MRP Settings',
			get_table_fields=lambda: [
				SimpleNamespace(fieldname="routes", options="MRP Settings Route")
			],
		)
		target = FrappeBulkTarget()
		with (
			patch("essdee_yrp.migration.live.frappe.db.delete") as delete,
			patch.object(target, "_bulk_upsert"),
		):
			target._replace_child_tables(
				meta,
				[
					{
						"doctype": 'SD YRP MRP Settings',
						"name": 'SD YRP MRP Settings',
						"routes": [
							{
								"doctype": "MRP Settings Route",
								"name": "ROW-1",
								"parent": "MRP Settings",
							}
						],
					}
				],
			)

		delete.assert_called_once_with(
			"MRP Settings Route",
			{
				"parenttype": 'SD YRP MRP Settings',
				"parentfield": "routes",
				"parent": ["in", ['SD YRP MRP Settings', "MRP Settings"]],
			},
		)

	def test_single_required_value_can_be_preserved_from_target(self):
		schema = {
			"name": 'SD YRP IPD Settings',
			"issingle": 1,
			"fields": [
				{"fieldname": "required_existing_value", "fieldtype": "Data", "reqd": 1}
			],
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_single_value",
			return_value="Knitting",
		):
			document = {"doctype": 'SD YRP IPD Settings', "name": 'SD YRP IPD Settings'}
			preserved = _validate_required_target_values(document, schema)
			self.assertEqual(preserved, 1)
			self.assertEqual(document["required_existing_value"], "Knitting")

	def test_f16_ipd_settings_required_processes_use_exact_source_masters(self):
		schema = {
			"name": 'SD YRP IPD Settings',
			"issingle": 1,
			"fields": [
				{"fieldname": "default_knitting_process", "fieldtype": "Link", "reqd": 1},
				{"fieldname": "default_dyeing_process", "fieldtype": "Link", "reqd": 1},
			],
		}
		document = {"doctype": 'SD YRP IPD Settings', "name": 'SD YRP IPD Settings'}
		reference_data = {
			"migration_defaults": {
				"IPD Settings.default_knitting_process": "Knitting",
				"IPD Settings.default_dyeing_process": "Dyeing",
			}
		}
		_apply_contextual_defaults(document, schema, reference_data)
		preserved = _validate_required_target_values(
			document, schema, reference_data=reference_data
		)
		self.assertEqual(preserved, 0)
		self.assertEqual(document["default_knitting_process"], "Knitting")
		self.assertEqual(document["default_dyeing_process"], "Dyeing")

	def test_required_value_can_be_preserved_from_existing_target_document(self):
		schema = {
			"name": 'YRP Item',
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {"doctype": 'YRP Item', "name": "Legacy Item", "item_group": None}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value="All Item Groups",
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "All Item Groups")

	def test_legacy_item_without_group_uses_root_group(self):
		schema = {
			"name": 'YRP Item',
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {"doctype": 'YRP Item', "name": "Legacy Item", "item_group": None}
		preserved = _validate_required_target_values(
			document,
			schema,
			reference_data={
				"migration_defaults": {"root_item_groups": ["All Item Groups"]}
			},
		)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "All Item Groups")

	def test_purchase_invoice_item_group_is_derived_from_item_variant(self):
		schema = {
			"name": 'YRP Purchase Invoice Item',
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Data", "reqd": 1}
			],
		}
		document = {
			"doctype": 'YRP Purchase Invoice Item',
			"name": "ROW-1",
			"item": "VARIANT-1",
			"item_group": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["ITEM-1", "Fabric"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "Fabric")

	def test_legacy_purchase_invoice_item_uses_legacy_item_root_group(self):
		schema = {
			"name": 'YRP Purchase Invoice Item',
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Data", "reqd": 1}
			],
		}
		document = {
			"doctype": 'YRP Purchase Invoice Item',
			"name": "ROW-1",
			"item": "VARIANT-1",
			"item_group": None,
		}
		reference_data = {
			"variant_to_item": {"VARIANT-1": "LEGACY-ITEM"},
			"item_groups": {"LEGACY-ITEM": None},
			"migration_defaults": {"root_item_groups": ["All Item Groups"]},
		}
		preserved = _validate_required_target_values(
			document, schema, reference_data=reference_data
		)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "All Item Groups")

	def test_packaging_lot_bom_process_comes_from_server_profile(self):
		schema = {
			"name": 'SD YRP Lot BOM',
			"fields": [
				{"fieldname": "process_name", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": 'SD YRP Lot BOM',
			"name": "ROW-1",
			"item_name": "TOP-BOX-VARIANT",
			"process_name": None,
		}
		reference_data = {
			"migration_defaults": {"Lot BOM.process_name": "Packing"}
		}
		_apply_contextual_defaults(document, schema, reference_data)
		preserved = _validate_required_target_values(
			document, schema, reference_data=reference_data
		)
		self.assertEqual(preserved, 0)
		self.assertEqual(document["process_name"], "Packing")

	def test_packaging_lot_bom_uom_is_derived_from_item_master(self):
		schema = {
			"name": 'SD YRP Lot BOM',
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": 'SD YRP Lot BOM',
			"name": "ROW-1",
			"item_name": "TOP-BOX-VARIANT",
			"uom": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["TOP-BOX", "Nos"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_purchase_order_item_uom_is_derived_from_item_master(self):
		schema = {
			"name": 'YRP Purchase Order Item',
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": 'YRP Purchase Order Item',
			"name": "ROW-1",
			"item_variant": "LABEL-VARIANT",
			"uom": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["LABEL", "Nos"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_source_item_reference_resolves_uom_before_target_write(self):
		schema = {
			"name": 'YRP Purchase Order Item',
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": 'YRP Purchase Order Item',
			"name": "ROW-NEWER-THAN-TARGET",
			"item_variant": "NEW-VARIANT",
			"uom": None,
		}
		references = {
			"variant_to_item": {"NEW-VARIANT": "NEW-ITEM"},
			"item_defaults": {"NEW-ITEM": "Nos"},
		}
		with patch("essdee_yrp.migration.live.frappe.db.get_value") as get_value:
			preserved = _validate_required_target_values(
				document, schema, reference_data=references
			)
		get_value.assert_not_called()
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_historical_process_cost_blanks_are_preserved_and_audited(self):
		schema = {
			"name": 'YRP Process Cost',
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1},
				{"fieldname": "lot", "fieldtype": "Link", "reqd": 1},
			],
		}
		document = {
			"doctype": 'YRP Process Cost',
			"name": "PC-00001",
			"creation": "2025-01-29 14:14:37",
			"supplier": None,
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(
			audit,
			{"Process Cost.supplier": 1, "Process Cost.lot": 1},
		)

	def test_process_cost_blank_policy_does_not_depend_on_record_date(self):
		schema = {
			"name": 'YRP Process Cost',
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": 'YRP Process Cost',
			"name": "PC-NEW",
			"creation": "2026-01-01 00:00:00",
			"supplier": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Process Cost.supplier": 1})

	def test_historical_multi_lot_purchase_order_blank_is_audited(self):
		schema = {
			"name": 'YRP Purchase Order',
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": 'YRP Purchase Order',
			"name": "PO-2324-0138",
			"creation": "2023-04-22 17:09:45",
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Purchase Order.lot": 1})

	def test_historical_multi_lot_grn_blank_is_audited(self):
		schema = {
			"name": 'YRP Goods Received Note',
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": 'YRP Goods Received Note',
			"name": "GRN-2526-00001",
			"creation": "2025-04-01 10:00:00",
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Goods Received Note.lot": 1})

	def test_pre_field_cutting_planner_description_blank_is_audited(self):
		schema = {
			"name": 'SD YRP Cutting Laysheet Planner',
			"fields": [
				{"fieldname": "description", "fieldtype": "Small Text", "reqd": 1}
			],
		}
		document = {
			"doctype": 'SD YRP Cutting Laysheet Planner',
			"name": "CLP-2026-00001",
			"description": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Cutting Laysheet Planner.description": 1})

	def test_cut_panel_warehouse_is_recovered_from_source_references(self):
		schema = {
			"name": 'SD YRP Cut Panel Movement',
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": 'SD YRP Cut Panel Movement',
			"name": "CPM-2505-00010",
			"creation": "2025-05-27 18:24:23",
			"from_warehouse": None,
		}
		references = {
			"cut_panel_from_warehouse": {"CPM-2505-00010": "S-0164"}
		}
		preserved = _validate_required_target_values(
			document, schema, reference_data=references
		)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["from_warehouse"], "S-0164")

	def test_blank_legacy_stock_received_type_uses_configured_default(self):
		schema = {
			"name": 'YRP Work Order Deliverables',
			"fields": [
				{"fieldname": "received_type", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": 'YRP Work Order Deliverables',
			"name": "ROW-1",
			"received_type": None,
		}
		reference_data = {
			"migration_defaults": {"default_received_type": "Accepted"}
		}
		_apply_contextual_defaults(document, schema, reference_data)
		preserved = _validate_required_target_values(
			document, schema, reference_data=reference_data
		)
		self.assertEqual(preserved, 0)
		self.assertEqual(document["received_type"], "Accepted")

	def test_unrecoverable_pre_field_cut_panel_warehouse_is_audited(self):
		schema = {
			"name": 'SD YRP Cut Panel Movement',
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": 'SD YRP Cut Panel Movement',
			"name": "CPM-2503-00001",
			"creation": "2025-03-25 18:16:12",
			"from_warehouse": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Cut Panel Movement.from_warehouse": 1})

	def test_single_required_value_still_fails_when_both_sites_are_empty(self):
		schema = {
			"name": 'SD YRP IPD Settings',
			"issingle": 1,
			"fields": [
				{"fieldname": "unknown_required_process", "fieldtype": "Link", "reqd": 1}
			],
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_single_value",
			return_value=None,
		):
			with self.assertRaisesRegex(Exception, "unknown_required_process"):
				_validate_required_target_values(
					{"doctype": 'SD YRP IPD Settings', "name": 'SD YRP IPD Settings'}, schema
				)


if __name__ == "__main__":
	unittest.main()
