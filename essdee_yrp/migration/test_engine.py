from __future__ import annotations

import unittest

from essdee_yrp.migration.engine import (
	Checkpoint,
	DocTypeRule,
	MemorySource,
	MemoryTarget,
	MigrationError,
	build_plan,
	document_digest,
	run_migration,
	transform_document,
)


def schema(name, fields, *, istable=False):
	return {"name": name, "fields": fields, "istable": int(istable)}


def field(fieldname, fieldtype="Data", options=None):
	value = {"fieldname": fieldname, "fieldtype": fieldtype}
	if options is not None:
		value["options"] = options
	return value


class MigrationEngineTest(unittest.TestCase):
	def test_identity_documents_use_the_generic_engine(self):
		schemas = {"Action": schema("Action", [field("title"), field("enabled", "Check")])}
		plan = build_plan(schemas, schemas)
		self.assertTrue(plan.ready)
		self.assertEqual(plan.specs["Action"].kind, "identity")
		document = {
			"doctype": "Action",
			"name": "Cut",
			"owner": "Administrator",
			"title": "Cut",
			"enabled": 1,
		}
		self.assertEqual(transform_document(document, plan), document)

	def test_received_type_rename_preserves_name_and_maps_field(self):
		source = {
			"GRN Item Type": schema(
				"GRN Item Type",
				[field("grn_type"), field("type", "Select"), field("show_in_sewing_plan", "Check")],
			)
		}
		target = {'YRP Received Type': schema('YRP Received Type', [field("received_type_name")])}
		rules = {
			"GRN Item Type": DocTypeRule(
				target='YRP Received Type',
				field_map={"grn_type": "received_type_name"},
				ignored_fields={
					"type": "Test-only reviewed exclusion",
					"show_in_sewing_plan": "Test-only reviewed exclusion",
				},
			)
		}
		plan = build_plan(
			source,
			target,
			rules=rules,
			doctype_map={"GRN Item Type": 'YRP Received Type'},
		)
		document = {
			"doctype": "GRN Item Type",
			"name": "Accepted",
			"grn_type": "Accepted",
			"type": "Accepted",
			"show_in_sewing_plan": 1,
		}
		self.assertEqual(
			transform_document(document, plan),
			{
				"doctype": 'YRP Received Type',
				"name": "Accepted",
				"received_type_name": "Accepted",
			},
		)

	def test_received_type_link_and_child_parent_metadata_are_remapped(self):
		source = {
			"GRN Item Type": schema("GRN Item Type", [field("grn_type")]),
			"Work Order": schema(
				"Work Order", [field("deliverables", "Table", "Work Order Deliverables")]
			),
			"Work Order Deliverables": schema(
				"Work Order Deliverables",
				[field("item_type", "Link", "GRN Item Type"), field("qty", "Float")],
				istable=True,
			),
		}
		target = {
			'YRP Received Type': schema('YRP Received Type', [field("received_type_name")]),
			'YRP Work Order': schema(
				'YRP Work Order', [field("deliverables", "Table", 'YRP Work Order Deliverables')]
			),
			'YRP Work Order Deliverables': schema(
				'YRP Work Order Deliverables',
				[field("received_type", "Link", 'YRP Received Type'), field("qty", "Float")],
				istable=True,
			),
		}
		rules = {
			"GRN Item Type": DocTypeRule(
				target='YRP Received Type', field_map={"grn_type": "received_type_name"}
			),
			"Work Order Deliverables": DocTypeRule(field_map={"item_type": "received_type"}),
		}
		plan = build_plan(
			source,
			target,
			rules=rules,
			doctype_map={
				"GRN Item Type": "YRP Received Type",
				"Work Order": "YRP Work Order",
				"Work Order Deliverables": "YRP Work Order Deliverables",
			},
		)
		self.assertTrue(plan.ready, plan.issues)
		document = {
			"doctype": "Work Order",
			"name": "WO-1",
			"deliverables": [
				{
					"doctype": "Work Order Deliverables",
					"name": "ROW-1",
					"parent": "WO-1",
					"parenttype": "Work Order",
					"parentfield": "deliverables",
					"item_type": "Accepted",
					"qty": 12.5,
				}
			],
		}
		row = transform_document(document, plan)["deliverables"][0]
		self.assertEqual(row["received_type"], "Accepted")
		self.assertEqual(row["parenttype"], 'YRP Work Order')
		self.assertEqual(row["parentfield"], "deliverables")

	def test_table_and_child_doctype_renames_are_recursive(self):
		source = {
			"Essdee Raw Print Format": schema(
				"Essdee Raw Print Format",
				[field("raw_print_format_details", "Table", "Essdee Raw Print Format Detail")],
			),
			"Essdee Raw Print Format Detail": schema(
				"Essdee Raw Print Format Detail", [field("raw_code", "Code")], istable=True
			),
		}
		target = {
			'YRP ZPL Raw Print Format': schema(
				'YRP ZPL Raw Print Format',
				[field("zpl_raw_print_format_details", "Table", 'YRP ZPL Raw Print Format Detail')],
			),
			'YRP ZPL Raw Print Format Detail': schema(
				'YRP ZPL Raw Print Format Detail', [field("raw_code", "Code")], istable=True
			),
		}
		doctype_map = {
			"Essdee Raw Print Format": 'YRP ZPL Raw Print Format',
			"Essdee Raw Print Format Detail": 'YRP ZPL Raw Print Format Detail',
		}
		rules = {
			"Essdee Raw Print Format": DocTypeRule(
				target='YRP ZPL Raw Print Format',
				field_map={"raw_print_format_details": "zpl_raw_print_format_details"},
			),
			"Essdee Raw Print Format Detail": DocTypeRule(target='YRP ZPL Raw Print Format Detail'),
		}
		plan = build_plan(source, target, rules=rules, doctype_map=doctype_map)
		output = transform_document(
			{
				"doctype": "Essdee Raw Print Format",
				"name": "Box",
				"raw_print_format_details": [
					{
						"doctype": "Essdee Raw Print Format Detail",
						"name": "ROW",
						"parent": "Box",
						"parenttype": "Essdee Raw Print Format",
						"parentfield": "raw_print_format_details",
						"raw_code": "^XA^XZ",
					}
				],
			},
			plan,
		)
		row = output["zpl_raw_print_format_details"][0]
		self.assertEqual(output["doctype"], 'YRP ZPL Raw Print Format')
		self.assertEqual(row["doctype"], 'YRP ZPL Raw Print Format Detail')
		self.assertEqual(row["parenttype"], 'YRP ZPL Raw Print Format')
		self.assertEqual(row["parentfield"], "zpl_raw_print_format_details")

	def test_dynamic_link_controller_value_follows_doctype_mapping(self):
		source = {
			"Ledger": schema(
				"Ledger",
				[
					field("voucher_type", "Link", "DocType"),
					field("voucher_no", "Dynamic Link", "voucher_type"),
				],
			),
			"Delivery Challan": schema("Delivery Challan", [field("title")]),
		}
		target = {
			"SD YRP Ledger": schema(
				"SD YRP Ledger",
				[
					field("voucher_type", "Link", "DocType"),
					field("voucher_no", "Dynamic Link", "voucher_type"),
				],
			),
			"YRP Delivery Challan": schema("YRP Delivery Challan", [field("title")]),
		}
		plan = build_plan(
			source,
			target,
			doctype_map={
				"Ledger": "SD YRP Ledger",
				"Delivery Challan": "YRP Delivery Challan",
			},
		)
		self.assertTrue(plan.ready, plan.issues)
		output = transform_document(
			{
				"doctype": "Ledger",
				"name": "LEDGER-1",
				"voucher_type": "Delivery Challan",
				"voucher_no": "DC-1",
			},
			plan,
		)
		self.assertEqual(output["doctype"], "SD YRP Ledger")
		self.assertEqual(output["voucher_type"], "YRP Delivery Challan")
		self.assertEqual(output["voucher_no"], "DC-1")

	def test_direct_doctype_link_value_follows_doctype_mapping(self):
		source = {
			"Route": schema("Route", [field("reference_doctype", "Link", "DocType")]),
			"Process Cost": schema("Process Cost", [field("title")]),
		}
		target = {
			"SD YRP Route": schema(
				"SD YRP Route", [field("reference_doctype", "Link", "DocType")]
			),
			"YRP Process Cost": schema("YRP Process Cost", [field("title")]),
		}
		plan = build_plan(
			source,
			target,
			doctype_map={
				"Route": "SD YRP Route",
				"Process Cost": "YRP Process Cost",
			},
		)
		output = transform_document(
			{
				"doctype": "Route",
				"name": "ROW-1",
				"reference_doctype": "Process Cost",
			},
			plan,
		)
		self.assertEqual(output["reference_doctype"], "YRP Process Cost")

	def test_renamed_single_uses_target_doctype_as_its_identity(self):
		source_schema = schema("Settings", [field("enabled", "Check")])
		source_schema["issingle"] = 1
		target_schema = schema("SD YRP Settings", [field("enabled", "Check")])
		target_schema["issingle"] = 1
		plan = build_plan(
			{"Settings": source_schema},
			{"SD YRP Settings": target_schema},
			doctype_map={"Settings": "SD YRP Settings"},
		)
		output = transform_document(
			{"doctype": "Settings", "name": "Settings", "enabled": 1},
			plan,
		)
		self.assertEqual(output["name"], "SD YRP Settings")

	def test_unmapped_source_field_blocks_plan_and_writes(self):
		source = {"Source": schema("Source", [field("known"), field("unknown")])}
		target = {"Source": schema("Source", [field("known")])}
		plan = build_plan(source, target)
		self.assertFalse(plan.ready)
		self.assertIn("Source: unknown: target field 'unknown' does not exist", plan.issues)
		with self.assertRaises(MigrationError):
			run_migration(
				plan,
				MemorySource({"Source": [{"doctype": "Source", "name": "A", "known": "1"}]}),
				MemoryTarget(),
				dry_run=False,
			)

	def test_dependency_order_and_cycles_are_deterministic(self):
		schemas = {
			"A": schema("A", [field("b", "Link", "B")]),
			"B": schema("B", [field("a", "Link", "A")]),
			"C": schema("C", [field("a", "Link", "A")]),
		}
		plan = build_plan(schemas, schemas)
		self.assertEqual(plan.dependency_groups, (("A", "B"), ("C",)))

	def test_rule_can_require_a_write_time_dependency(self):
		schemas = {"A": schema("A", []), "B": schema("B", [])}
		plan = build_plan(
			schemas,
			schemas,
			rules={"A": DocTypeRule(extra_dependencies=frozenset({"B"}))},
		)
		self.assertEqual(plan.dependency_groups, (("B",), ("A",)))

	def test_custom_transformer_must_be_registered_and_preserve_identity(self):
		source = {"Old": schema("Old", [field("value")])}
		target = {"New": schema("New", [field("converted")])}
		rules = {"Old": DocTypeRule(target="New", custom_transformer="convert_old")}
		blocked = build_plan(source, target, rules=rules)
		self.assertFalse(blocked.ready)

		def convert(document, spec, plan):
			return {
				"doctype": spec.target,
				"name": document["name"],
				"converted": document["value"].upper(),
			}

		plan = build_plan(source, target, rules=rules, transformers={"convert_old": convert})
		self.assertTrue(plan.ready)
		self.assertEqual(
			transform_document({"doctype": "Old", "name": "A", "value": "yes"}, plan),
			{"doctype": "New", "name": "A", "converted": "YES"},
		)

	def test_link_option_change_requires_and_uses_value_transformer(self):
		source = {"Stock": schema("Stock", [field("warehouse", "Link", "Supplier")])}
		target = {"Stock": schema("Stock", [field("warehouse", "Link", "Warehouse")])}
		rules = {
			"Stock": DocTypeRule(value_transformers={"warehouse": "supplier_to_warehouse"})
		}
		blocked = build_plan(source, target, rules=rules)
		self.assertIn("value transformer 'supplier_to_warehouse' is required", blocked.issues[0])

		def map_warehouse(value, document, spec, fieldname):
			return {"Supplier A": "Warehouse A"}[value]

		plan = build_plan(
			source,
			target,
			rules=rules,
			value_transformers={"supplier_to_warehouse": map_warehouse},
		)
		self.assertTrue(plan.ready, plan.issues)
		self.assertEqual(
			transform_document(
				{"doctype": "Stock", "name": "ROW", "warehouse": "Supplier A"}, plan
			)["warehouse"],
			"Warehouse A",
		)

	def test_contextual_child_table_maps_to_a_different_target_child(self):
		source = {
			"Parent": schema("Parent", [field("rows", "Table", "Shared Child")]),
			"Shared Child": schema("Shared Child", [field("value")], istable=True),
		}
		target = {
			"Parent": schema("Parent", [field("rows", "Table", "Special Child")]),
			"Shared Child": schema("Shared Child", [field("value")], istable=True),
			"Special Child": schema("Special Child", [field("value")], istable=True),
		}
		plan = build_plan(
			source,
			target,
			rules={"Parent": DocTypeRule(table_option_map={"rows": "Special Child"})},
		)
		self.assertTrue(plan.ready, plan.issues)
		output = transform_document(
			{
				"doctype": "Parent",
				"name": "P-1",
				"rows": [
					{
						"doctype": "Shared Child",
						"name": "ROW-1",
						"parent": "P-1",
						"parenttype": "Parent",
						"parentfield": "rows",
						"value": "kept",
					}
				],
			},
			plan,
		)
		self.assertEqual(output["rows"][0]["doctype"], "Special Child")
		self.assertEqual(output["rows"][0]["value"], "kept")

	def test_post_transformer_receives_parent_source_document(self):
		source = {
			"Parent": schema("Parent", [field("header"), field("rows", "Table", "Row")]),
			"Row": schema("Row", [field("value")], istable=True),
		}
		target = source
		rules = {"Row": DocTypeRule(post_transformer="copy_header")}
		blocked = build_plan(source, target, rules=rules)
		self.assertFalse(blocked.ready)

		def copy_header(output, source, spec, plan, parent):
			return {**output, "value": parent["header"]}

		plan = build_plan(
			source,
			target,
			rules=rules,
			post_transformers={"copy_header": copy_header},
		)
		output = transform_document(
			{
				"doctype": "Parent",
				"name": "P-1",
				"header": "derived",
				"rows": [{"doctype": "Row", "name": "R-1", "value": "old"}],
			},
			plan,
		)
		self.assertEqual(output["rows"][0]["value"], "derived")

	def test_dry_run_never_stores_and_resume_uses_content_hash(self):
		schemas = {"Action": schema("Action", [field("title")])}
		plan = build_plan(schemas, schemas)
		document = {"doctype": "Action", "name": "Cut", "title": "Cut"}
		source = MemorySource({"Action": [document]})
		target = MemoryTarget()
		checkpoint = Checkpoint()

		dry_result = run_migration(plan, source, target, checkpoint=checkpoint, dry_run=True)
		self.assertEqual((dry_result.transformed, dry_result.stored), (1, 0))
		self.assertEqual(target.store_calls, 0)
		self.assertEqual(checkpoint.completed, {})

		write_result = run_migration(plan, source, target, checkpoint=checkpoint, dry_run=False)
		self.assertEqual((write_result.stored, target.store_calls), (1, 1))
		self.assertTrue(checkpoint.is_current("Action", "Cut", document_digest(document)))

		resume_result = run_migration(plan, source, target, checkpoint=checkpoint, dry_run=False)
		self.assertEqual((resume_result.skipped, target.store_calls), (1, 1))

		changed = {**document, "title": "Cutting"}
		changed_result = run_migration(
			plan,
			MemorySource({"Action": [changed]}),
			target,
			checkpoint=checkpoint,
			dry_run=False,
		)
		self.assertEqual((changed_result.stored, target.store_calls), (1, 2))

	def test_checkpoint_round_trip(self):
		checkpoint = Checkpoint(completed={"A:1": "hash"}, failures={"B:2": "bad"})
		self.assertEqual(Checkpoint.from_dict(checkpoint.as_dict()), checkpoint)

	def test_password_payload_survives_generic_and_custom_transforms(self):
		schemas = {"Settings": schema("Settings", [field("api_secret", "Password")])}
		generic_plan = build_plan(schemas, schemas)
		secret = {"api_secret": "plain-only-in-memory"}
		generic = transform_document(
			{
				"doctype": "Settings",
				"name": "Settings",
				"api_secret": "********",
				"__migration_passwords": secret,
			},
			generic_plan,
		)
		self.assertEqual(generic["__migration_passwords"], secret)

		def custom(document, spec, plan):
			return {"doctype": "Settings", "name": document["name"]}

		custom_plan = build_plan(
			schemas,
			schemas,
			rules={"Settings": DocTypeRule(custom_transformer="custom")},
			transformers={"custom": custom},
		)
		custom_output = transform_document(
			{
				"doctype": "Settings",
				"name": "Settings",
				"__migration_passwords": secret,
			},
			custom_plan,
		)
		self.assertEqual(custom_output["__migration_passwords"], secret)


if __name__ == "__main__":
	unittest.main()
