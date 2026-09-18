from pathlib import Path
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.migration.config import TARGET_APPS, MigrationSettings
from essdee_yrp.migration.live import F15SourceBridge
from essdee_yrp.migration.sample import (
	QueryOnlySampleTarget,
	_collect_missing_link_identities,
	_close_percentage_sample_dependencies,
	_dependency_round_order,
	_do_percentage_approved_frappe_data,
	_finalize_percentage_business_configuration,
	_load_percentage_sample_functional_dependencies,
	_load_percentage_sample_configuration_dependencies,
	_percentage_limit,
	_purchase_invoice_grn_dependencies,
	_same_db_value,
	_strip_password_values,
	_transformed_attribute_value_names,
)


class TestQueryOnlySample(UnitTestCase):
	def source_bridge(self):
		return F15SourceBridge(
			MigrationSettings(
				adapter="local_bench",
				source_bench=Path("/test/source-bench"),
				source_site="source.test",
				source_app="production_api",
				target_site="target.test",
				target_apps=TARGET_APPS,
				required_defaults={},
			)
		)

	def test_source_bridge_caps_export_at_the_source(self):
		bridge = self.source_bridge()
		with patch.object(bridge, "_run", return_value=iter(())) as run:
			list(bridge.iter_documents("Lot", batch_size=20, limit=20))
		run.assert_called_once_with(
			["export", "--doctype", "Lot", "--batch-size", "20", "--limit", "20"]
		)

	def test_source_bridge_exports_exact_dependency_names_in_bounded_chunks(self):
		bridge = self.source_bridge()
		with patch.object(bridge, "_run", return_value=iter(())) as run:
			list(bridge.iter_documents("Item", names=["ITEM-2", "ITEM-1", "ITEM-1"]))
		run.assert_called_once_with(
			[
				"export",
				"--doctype",
				"Item",
				"--batch-size",
				"250",
				"--names-json",
				'["ITEM-1","ITEM-2"]',
			]
		)

	def test_source_bridge_resolves_child_dependencies_to_their_parent(self):
		bridge = self.source_bridge()
		rows = iter(
			[
				{
					"source_doctype": "Cutting Plan Detail",
					"name": "ROW-1",
					"parent": "CP-1",
					"parenttype": "Cutting Plan",
				}
			]
		)
		with patch.object(bridge, "_run", return_value=rows) as run:
			self.assertEqual(
				list(bridge.resolve_source_identities("Cutting Plan Detail", ["ROW-1"])),
				[
					{
						"source_doctype": "Cutting Plan Detail",
						"name": "ROW-1",
						"parent": "CP-1",
						"parenttype": "Cutting Plan",
					}
				],
			)
		run.assert_called_once_with(
			[
				"resolve-identities",
				"--doctype",
				"Cutting Plan Detail",
				"--names-json",
				'["ROW-1"]',
			]
		)

	def test_source_bridge_fetches_cut_bundle_edit_ledger_dependencies_in_chunks(self):
		bridge = self.source_bridge()
		with patch.object(bridge, "_run", return_value=iter(())) as run:
			list(bridge.iter_cut_bundle_edit_ledger_dependencies(["EDIT-2", "EDIT-1"]))
		run.assert_called_once_with(
			[
				"cut-bundle-edit-ledgers",
				"--names-json",
				'["EDIT-1","EDIT-2"]',
			]
		)

	def test_source_bridge_returns_effective_live_schemas(self):
		bridge = self.source_bridge()
		rows = iter(
			[
				{
					"kind": "schema",
					"schema": {"name": "Lot", "doctype": "DocType", "fields": []},
				}
			]
		)
		with patch.object(bridge, "_run", return_value=rows) as run:
			self.assertEqual(set(bridge.schemas()), {"Lot"})
		run.assert_called_once_with(["schemas"])

	def test_parent_upsert_never_passes_password_payload_to_sql(self):
		meta = frappe._dict(
			issingle=False,
			get_table_fields=lambda: [],
		)
		target = QueryOnlySampleTarget()
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(target, "_bulk_upsert") as bulk_upsert,
			patch.object(target, "_replace_child_tables_sql"),
		):
			target.upsert_batch(
				'SD YRP MRP Settings',
				[
					{
						"doctype": 'SD YRP MRP Settings',
						"name": 'SD YRP MRP Settings',
						"value": "kept",
						"__migration_passwords": {"api_secret": "must-not-enter-parent-table"},
					}
				],
			)
		self.assertEqual(
			bulk_upsert.call_args.args,
			('SD YRP MRP Settings', [{"name": 'SD YRP MRP Settings', "value": "kept"}]),
		)

	def test_single_upsert_replaces_fresh_site_values_without_duplicates(self):
		meta = frappe._dict(
			name="Settings",
			fields=[frappe._dict(fieldname="value", fieldtype="Data")],
			get_table_fields=lambda: [],
		)
		with (
			patch.object(frappe.db, "sql") as sql,
			patch.object(frappe, "clear_document_cache") as clear_document_cache,
		):
			QueryOnlySampleTarget()._upsert_single_sql(
				meta,
				{"doctype": "Settings", "name": "Settings", "value": "migrated"},
			)

		self.assertEqual(sql.call_count, 2)
		delete_query, delete_values = sql.call_args_list[0].args
		self.assertIn("DELETE FROM `tabSingles`", delete_query)
		self.assertEqual(delete_values, ["Settings", "value"])
		insert_query, insert_values = sql.call_args_list[1].args
		self.assertIn("INSERT INTO `tabSingles`", insert_query)
		self.assertNotIn("ON DUPLICATE KEY", insert_query)
		self.assertEqual(insert_values, ["Settings", "value", "migrated"])
		clear_document_cache.assert_called_once_with("Settings", "Settings")

	def test_single_link_closure_bypasses_stale_value_cache(self):
		plan = frappe._dict(
			specs={
				"Settings": frappe._dict(
					target="Target Settings", table_option_map={}, is_child=False
				)
			},
			target_schemas={
				"Target Settings": {
					"fields": [
						{
							"fieldname": "default_process",
							"fieldtype": "Link",
							"options": "Target Process",
						}
					]
				}
			},
		)
		settings_meta = frappe._dict(issingle=True, istable=False)
		with (
			# A real Single has no dedicated SQL table.  The closure collector must
			# still inspect its Link values in tabSingles.
			patch.object(frappe.db, "table_exists", return_value=False),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_table_columns", return_value=[]),
			patch.object(frappe.db, "get_single_value", return_value="Knitting") as get_single,
			patch.object(frappe, "get_meta", return_value=settings_meta),
			patch(
				"essdee_yrp.migration.sample._existing_names", return_value=set()
			),
		):
			missing = _collect_missing_link_identities(plan)

		self.assertEqual(missing, {"Target Process": {"Knitting"}})
		get_single.assert_called_once_with(
			"Target Settings", "default_process", cache=False
		)

	def test_percentage_sample_finalizes_post_load_production_order_settings(self):
		with (
			patch(
				"essdee_yrp.setup.ensure_yrp_production_order_settings",
				return_value=True,
			) as ensure_settings,
			patch(
				"essdee_yrp.sd_yrp_sync.validate_yrp_settings_for_production_order"
			) as validate_settings,
			patch.object(frappe.db, "commit") as commit,
		):
			result = _finalize_percentage_business_configuration()

		self.assertEqual(
			result,
			{
				"status": "Pass",
				"production_order_settings": "Configured",
				"changed": True,
			},
		)
		ensure_settings.assert_called_once_with()
		validate_settings.assert_called_once_with()
		commit.assert_called_once_with()

	def test_percentage_sample_loads_exact_production_order_configuration_dependencies(self):
		plan = frappe._dict(
			specs={
				"Item Attribute": frappe._dict(target="Item Attribute"),
				"Item Attribute Value": frappe._dict(target="Item Attribute Value"),
			}
		)
		source = MagicMock()
		source.iter_documents.side_effect = lambda doctype, **kwargs: [
			{"doctype": doctype, "name": name} for name in kwargs["names"]
		]
		target = MagicMock()
		target.existing_names.side_effect = [set(), {"Pack"}]
		with (
			patch(
				"essdee_yrp.migration.sample._transformed_attribute_value_names",
				return_value={"Red"},
			),
			patch(
				"essdee_yrp.migration.sample.transform_document",
				side_effect=lambda document, _plan: document,
			),
			patch(
				"essdee_yrp.migration.sample._resolve_and_validate_required_target_values"
			),
			patch("essdee_yrp.migration.sample._strip_password_values"),
			patch(
				"essdee_yrp.migration.sample._verify_documents_sql",
				return_value={"issues": []},
			),
			patch.object(frappe.db, "commit"),
		):
			result = _load_percentage_sample_configuration_dependencies(
				source,
				target,
				plan,
				{},
				batch_size=250,
			)

		self.assertEqual(
			result,
			{"status": "Pass", "required": 4, "already_present": 1, "loaded": 3},
		)
		self.assertEqual(
			target.upsert_batch.call_args_list,
			[
				call(
					"Item Attribute",
					[
						{"doctype": "Item Attribute", "name": "Size"},
						{"doctype": "Item Attribute", "name": "Stage"},
					],
				),
				call(
					"Item Attribute Value",
					[{"doctype": "Item Attribute Value", "name": "Red"}],
				),
			],
		)

	def test_percentage_sample_collects_every_link_to_data_attribute_value(self):
		plan = frappe._dict(
			specs={
				"Child A": frappe._dict(
					target="Target Child",
					field_map={"source_value": "target_value"},
					value_transformers={
						"source_value": "attribute_value_link_to_data"
					},
				),
				"Settings": frappe._dict(
					target="Target Settings",
					field_map={},
					value_transformers={
						"default_stage": "attribute_value_link_to_data"
					},
				),
			}
		)
		child_meta = frappe._dict(issingle=False)
		settings_meta = frappe._dict(issingle=True)
		with (
			patch.object(
				frappe,
				"get_meta",
				side_effect=[child_meta, settings_meta],
			),
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(
				frappe.db, "get_table_columns", return_value=["target_value"]
			),
			patch.object(frappe.db, "sql", return_value=[("Red",), ("Blue",)]),
			patch.object(
				frappe.db, "get_single_value", return_value="Pack"
			),
		):
			values = _transformed_attribute_value_names(plan)

		self.assertEqual(values, {"Red", "Blue", "Pack"})

	def test_percentage_sample_reconciles_fresh_site_default_collisions(self):
		source = MagicMock()
		source.iter_approved_frappe_documents.return_value = [
			{
				"doctype": "DefaultValue",
				"name": "source-default",
				"parent": "__default",
				"parenttype": "__default",
				"defkey": "letter_head",
				"defvalue": "Source Letter Head",
			}
		]
		target = MagicMock()
		report = {"issues": []}
		with (
			patch(
				"essdee_yrp.migration.sample._prepare_approved_frappe_document",
				side_effect=lambda document, _plan: document,
			),
			patch("essdee_yrp.migration.sample._strip_password_values"),
			patch("essdee_yrp.migration.sample._assert_approved_frappe_child_identities"),
			patch(
				"essdee_yrp.migration.sample._verify_documents_sql",
				return_value={"issues": [], "child_rows": 0, "field_values": 5},
			),
			patch(
				"essdee_yrp.migration.sample._reconcile_approved_default_values",
				return_value={"status": "Reconciled", "removed_target_only_collisions": 1},
			) as reconcile,
			patch.object(frappe.db, "savepoint"),
			patch.object(frappe.db, "commit"),
			patch.object(frappe, "clear_cache") as clear_cache,
		):
			_do_percentage_approved_frappe_data(
				source,
				target,
				frappe._dict(),
				{"approved_frappe_data": {"counts": {"DefaultValue": 1}}},
				25,
				250,
				report,
			)

		reconcile.assert_called_once_with(
			[source.iter_approved_frappe_documents.return_value[0]],
			dry_run=False,
		)
		clear_cache.assert_called_once_with()
		self.assertEqual(
			report["approved_frappe_default_value_reconciliation"]["status"],
			"Reconciled",
		)

	def test_sample_removes_both_masked_and_decrypted_password_values(self):
		meta = frappe._dict(
			fields=[
				frappe._dict(fieldname="api_secret", fieldtype="Password"),
				frappe._dict(fieldname="title", fieldtype="Data"),
			]
		)
		document = {
			"doctype": "Settings",
			"name": "Settings",
			"api_secret": "********",
			"title": "kept",
			"__migration_passwords": {"api_secret": "decrypted-secret"},
		}
		with patch.object(frappe, "get_meta", return_value=meta):
			self.assertEqual(_strip_password_values(document), 1)
		self.assertNotIn("api_secret", document)
		self.assertNotIn("__migration_passwords", document)
		self.assertEqual(document["title"], "kept")

	def test_sample_does_not_treat_json_payload_as_a_child_table(self):
		meta = frappe._dict(
			fields=[
				frappe._dict(fieldname="original_rows", fieldtype="JSON"),
			]
		)
		document = {
			"doctype": "Settings",
			"name": "Settings",
			"original_rows": [
				{"doctype": "Retired Source Child", "name": "ROW-1", "value": "kept"}
			],
		}
		with patch.object(frappe, "get_meta", return_value=meta) as get_meta:
			self.assertEqual(_strip_password_values(document), 0)
		get_meta.assert_called_once_with("Settings")
		self.assertEqual(document["original_rows"][0]["value"], "kept")

	def test_numeric_and_json_sql_round_trip_comparison(self):
		self.assertTrue(_same_db_value(1, 1.0, "Float"))
		self.assertTrue(
			_same_db_value(
				55000.00000000001,
				55000.0,
				"Currency",
				numeric_scale=9,
			)
		)
		self.assertTrue(_same_db_value({"b": 2, "a": 1}, '{"a":1,"b":2}', "JSON"))

	def test_percentage_sample_rounds_up_and_keeps_nonempty_doctypes(self):
		self.assertEqual(_percentage_limit(0, 25), 0)
		self.assertEqual(_percentage_limit(1, 25), 1)
		self.assertEqual(_percentage_limit(5, 25), 2)
		self.assertEqual(_percentage_limit(100, 25), 25)

	def test_dependency_closure_defers_purchase_invoice_behind_new_prerequisites(self):
		plan = frappe._dict(
			parent_doctypes=["Item Variant", "Process", "Purchase Invoice"]
		)
		ordered, deferred = _dependency_round_order(
			plan,
			{
				"Process": {"Stitching"},
				"Purchase Invoice": {"MPI-1"},
			},
			{},
		)
		self.assertEqual(ordered, ["Process"])
		self.assertEqual(deferred, 1)

		ordered, deferred = _dependency_round_order(
			plan,
			{"Purchase Invoice": {"MPI-1"}},
			{},
		)
		self.assertEqual(ordered, ["Purchase Invoice"])
		self.assertEqual(deferred, 0)

	def test_dependency_closure_continues_past_twenty_progressing_rounds(self):
		plan = frappe._dict(
			parent_doctypes=["Node"],
			specs={"Node": frappe._dict(target="Target Node")},
		)
		source = MagicMock()
		source.resolve_source_identities.side_effect = (
			lambda _doctype, names: [{"name": next(iter(names))}]
		)
		source.iter_documents.side_effect = (
			lambda _doctype, **kwargs: [
				{"doctype": "Node", "name": name}
				for name in kwargs["names"]
			]
		)
		target = MagicMock()
		missing_rounds = [
			{"Target Node": {f"NODE-{index}"}} for index in range(1, 22)
		] + [{}]
		with (
			patch(
				"essdee_yrp.migration.sample._source_candidates_by_target",
				return_value={"Target Node": {"Node"}},
			),
			patch(
				"essdee_yrp.migration.sample._source_broken_link_manifest",
				return_value=[],
			),
			patch(
				"essdee_yrp.migration.sample._collect_missing_link_identities",
				side_effect=missing_rounds,
			),
			patch(
				"essdee_yrp.migration.sample.transform_document",
				side_effect=lambda document, _plan: {
					"doctype": "Target Node",
					"name": document["name"],
				},
			),
			patch(
				"essdee_yrp.migration.sample._resolve_and_validate_required_target_values"
			),
			patch("essdee_yrp.migration.sample._strip_password_values"),
			patch(
				"essdee_yrp.migration.sample._verify_documents_sql",
				return_value={"issues": []},
			),
			patch.object(frappe.db, "commit"),
		):
			result = _close_percentage_sample_dependencies(
				source,
				target,
				plan,
				{},
				batch_size=250,
			)

		self.assertEqual(result["status"], "Pass")
		self.assertEqual(len(result["rounds"]), 21)
		self.assertEqual(result["loaded_parent_documents"], {"Node": 21})

	def test_functional_dependency_closure_loads_missing_cut_bundle_ledgers(self):
		plan = frappe._dict(
			specs={
				"Cut Bundle Edit": frappe._dict(target="Target Edit"),
				"Cut Bundle Movement Ledger": frappe._dict(target="Target Ledger"),
			}
		)
		source = MagicMock()
		source.iter_cut_bundle_edit_ledger_dependencies.return_value = [
			{"source_doctype": "Cut Bundle Movement Ledger", "name": "LEDGER-1"}
		]
		source.iter_documents.return_value = [
			{"doctype": "Cut Bundle Movement Ledger", "name": "LEDGER-1"}
		]
		target = MagicMock()
		target.existing_names.return_value = set()
		with (
			patch.object(frappe, "get_all", return_value=["EDIT-1"]),
			patch(
				"essdee_yrp.migration.sample.transform_document",
				return_value={"doctype": "Target Ledger", "name": "LEDGER-1"},
			),
			patch(
				"essdee_yrp.migration.sample._resolve_and_validate_required_target_values"
			),
			patch("essdee_yrp.migration.sample._strip_password_values"),
			patch(
				"essdee_yrp.migration.sample._verify_documents_sql",
				return_value={"issues": []},
			),
			patch.object(frappe.db, "commit"),
		):
			result = _load_percentage_sample_functional_dependencies(
				source,
				target,
				plan,
				{},
				batch_size=250,
			)

		self.assertEqual(
			result,
			{"status": "Pass", "required": 1, "already_present": 0, "loaded": 1},
		)
		target.upsert_batch.assert_called_once_with(
			"Target Ledger", [{"doctype": "Target Ledger", "name": "LEDGER-1"}]
		)

	def test_dependency_closure_leaves_exact_source_broken_links_for_final_audit(self):
		plan = frappe._dict(
			parent_doctypes=["Node"],
			specs={"Node": frappe._dict(target="Target Node")},
		)
		source = MagicMock()
		source.resolve_source_identities.return_value = []
		with (
			patch(
				"essdee_yrp.migration.sample._source_candidates_by_target",
				return_value={"Target Node": {"Node"}},
			),
			patch(
				"essdee_yrp.migration.sample._source_broken_link_manifest",
				return_value=[
					{"target_link_doctype": "Target Node", "value": "MISSING"}
				],
			),
			patch(
				"essdee_yrp.migration.sample._collect_missing_link_identities",
				return_value={"Target Node": {"MISSING"}},
			),
		):
			result = _close_percentage_sample_dependencies(
				source,
				MagicMock(),
				plan,
				{},
				batch_size=250,
			)

		self.assertEqual(result["status"], "Pass")
		self.assertEqual(result["rounds"], [])
		self.assertEqual(result["audited_source_invalid_identities"], 1)

	def test_purchase_invoice_dependencies_surface_grns_before_projection(self):
		source = MagicMock()
		source.iter_documents.return_value = [
			{
				"doctype": "Purchase Invoice",
				"name": "MPI-1",
				"grn": [
					{"grn": "GRN-2"},
					{"grn": "GRN-1"},
					{"grn": "GRN-2"},
				],
			}
		]

		self.assertEqual(
			_purchase_invoice_grn_dependencies(
				source, {"MPI-1"}, batch_size=250
			),
			{"GRN-1", "GRN-2"},
		)
		source.iter_documents.assert_called_once_with(
			"Purchase Invoice", batch_size=250, names=["MPI-1"]
		)

	def test_sample_module_has_no_document_mutation_api(self):
		source = (Path(__file__).resolve().parent / "sample.py").read_text()
		# ``get_doc`` is deliberately used by the post-load onload gate. It is
		# read-only; historical writes must remain restricted to the audited SQL
		# bulk target and must never invoke controller insert/save behavior.
		self.assertNotIn(".insert(", source)
		self.assertNotIn(".save(", source)


if __name__ == "__main__":
	import unittest

	unittest.main()
