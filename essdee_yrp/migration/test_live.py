from __future__ import annotations

import base64
import hashlib
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.config import MigrationSettings
from essdee_yrp.migration.live import (
	F15SourceBridge,
	FrappeBulkTarget,
	_apply_contextual_defaults,
	_broken_static_link_count,
	_decode_and_validate_file_payload,
	_collect_document_identities,
	_collect_expected_value_rows,
	_is_verified_attachment_url,
	_migration_contract_fingerprint,
	_require_previous_snapshot,
	_run_files,
	_same_migrated_value,
	_validate_configured_default_contract,
	_validate_required_target_values,
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
					"Product Image", "IMG-1", "image", "/files/renamed.png", "Attach Image"
				)
			)
		exists.assert_called_once_with(
			"File",
			{
				"is_folder": 0,
				"attached_to_doctype": "Product Image",
				"attached_to_name": "IMG-1",
				"attached_to_field": "image",
				"file_url": "/files/renamed.png",
			},
		)
		self.assertFalse(
			_is_verified_attachment_url(
				"Product Image", "IMG-1", "title", "/files/renamed.png", "Data"
			)
		)

	def test_single_identity_is_counted_without_querying_a_physical_table(self):
		plan = SimpleNamespace(
			target_schemas={"Company Settings": {"issingle": 1, "fields": []}}
		)
		pending = {}
		expected = {}
		_collect_document_identities(
			{"doctype": "Company Settings", "name": "Company Settings"},
			plan,
			pending,
			expected,
		)
		self.assertEqual(pending, {})
		self.assertEqual(expected, {"Company Settings": 1})

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
					target="Product Sub brand", field_map={}
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
				"Lot BOM": {
					"fields": [
						{
							"fieldname": "process_name",
							"fieldtype": "Link",
							"options": "Process",
						}
					]
				}
			},
			specs={
				"Process": SimpleNamespace(target="Process", is_child=False)
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
		plan = SimpleNamespace(target_schemas={"Lot BOM": {"fields": []}}, specs={})
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
			name="MRP Settings",
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
						"doctype": "MRP Settings",
						"name": "MRP Settings",
						"routes": [
							{
								"doctype": "MRP Settings Route",
								"name": "ROW-1",
								"route": "Goods Received Note",
							}
						],
					}
				],
			)

		delete.assert_called_once_with(
			"MRP Settings Route",
			{
				"parenttype": "MRP Settings",
				"parentfield": "routes",
				"parent": ["in", ["MRP Settings"]],
			},
		)
		self.assertEqual(bulk_rows[0]["parenttype"], "MRP Settings")
		self.assertEqual(bulk_rows[0]["parentfield"], "routes")
		self.assertEqual(bulk_rows[0]["parent"], "MRP Settings")

	def test_single_required_value_can_be_preserved_from_target(self):
		schema = {
			"name": "IPD Settings",
			"issingle": 1,
			"fields": [
				{"fieldname": "required_existing_value", "fieldtype": "Data", "reqd": 1}
			],
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_single_value",
			return_value="Knitting",
		):
			document = {"doctype": "IPD Settings", "name": "IPD Settings"}
			preserved = _validate_required_target_values(document, schema)
			self.assertEqual(preserved, 1)
			self.assertEqual(document["required_existing_value"], "Knitting")

	def test_f16_ipd_settings_required_processes_use_exact_source_masters(self):
		schema = {
			"name": "IPD Settings",
			"issingle": 1,
			"fields": [
				{"fieldname": "default_knitting_process", "fieldtype": "Link", "reqd": 1},
				{"fieldname": "default_dyeing_process", "fieldtype": "Link", "reqd": 1},
			],
		}
		document = {"doctype": "IPD Settings", "name": "IPD Settings"}
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
			"name": "Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {"doctype": "Item", "name": "Legacy Item", "item_group": None}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value="All Item Groups",
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "All Item Groups")

	def test_legacy_item_without_group_uses_root_group(self):
		schema = {
			"name": "Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {"doctype": "Item", "name": "Legacy Item", "item_group": None}
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
			"name": "Purchase Invoice Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Data", "reqd": 1}
			],
		}
		document = {
			"doctype": "Purchase Invoice Item",
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
			"name": "Purchase Invoice Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Data", "reqd": 1}
			],
		}
		document = {
			"doctype": "Purchase Invoice Item",
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
			"name": "Lot BOM",
			"fields": [
				{"fieldname": "process_name", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Lot BOM",
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
			"name": "Lot BOM",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Lot BOM",
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
			"name": "Purchase Order Item",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order Item",
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
			"name": "Purchase Order Item",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order Item",
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
			"name": "Process Cost",
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1},
				{"fieldname": "lot", "fieldtype": "Link", "reqd": 1},
			],
		}
		document = {
			"doctype": "Process Cost",
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
			"name": "Process Cost",
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Process Cost",
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
			"name": "Purchase Order",
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order",
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
			"name": "Goods Received Note",
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Goods Received Note",
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

	def test_cut_panel_warehouse_is_recovered_from_source_references(self):
		schema = {
			"name": "Cut Panel Movement",
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Cut Panel Movement",
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
			"name": "Work Order Deliverables",
			"fields": [
				{"fieldname": "received_type", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Work Order Deliverables",
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
			"name": "Cut Panel Movement",
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Cut Panel Movement",
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
			"name": "IPD Settings",
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
					{"doctype": "IPD Settings", "name": "IPD Settings"}, schema
				)


if __name__ == "__main__":
	unittest.main()
