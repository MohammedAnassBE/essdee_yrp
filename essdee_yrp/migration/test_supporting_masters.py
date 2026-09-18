import json
import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import (
	APPROVED_FRAPPE_DATA_ORDER,
	F15SourceBridge,
	_assert_supporting_child_ownership,
	_load_supporting_external_masters,
	_transform_supporting_document,
	_validate_external_references,
	_verify_supporting_business_master_identities,
)


class SupportingMasterTest(unittest.TestCase):
	def test_approved_frappe_scope_is_explicit_and_never_includes_removed_f16_doctypes(self):
		bridge = runpy.run_path(
			str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py")
		)
		approved = set(bridge["APPROVED_FRAPPE_DATA_ORDER"])
		self.assertEqual(
			tuple(bridge["APPROVED_FRAPPE_DATA_ORDER"]), APPROVED_FRAPPE_DATA_ORDER
		)
		self.assertIn("User", approved)
		self.assertIn("Module Profile", approved)
		self.assertIn("Custom DocPerm", approved)
		self.assertNotIn("Energy Point Settings", approved)
		self.assertNotIn("S3 Backup Settings", approved)
		self.assertEqual(
			bridge["APPROVED_FRAPPE_ARCHIVE_ONLY_DOCTYPES"],
			("Energy Point Settings", "S3 Backup Settings"),
		)
		self.assertNotIn("Message Log", approved)

	def test_approved_user_drops_only_spine_role_and_keeps_supported_preferences(self):
		bridge = runpy.run_path(
			str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py")
		)
		user = {
			"name": "user@example.com",
			"roles": [
				{"role": "System Manager"},
				{"role": "Spine User"},
			],
			"block_modules": [{"module": "Core"}],
			"social_logins": [{"provider": "frappe"}],
			"module_profile": "Default",
		}
		frappe = SimpleNamespace(
			get_meta=lambda _doctype: SimpleNamespace(issingle=False),
			get_doc=lambda _doctype, _name: SimpleNamespace(
				as_dict=lambda **_kwargs: dict(user)
			),
		)
		actual = bridge["_approved_frappe_document"](
			frappe, "User", user["name"], set(), passwords=False
		)
		self.assertEqual(actual["roles"], [{"role": "System Manager"}])
		self.assertEqual(actual["block_modules"], [{"module": "Core"}])
		self.assertEqual(actual["social_logins"], [{"provider": "frappe"}])
		self.assertEqual(actual["module_profile"], "Default")

	def test_exact_archive_keeps_live_incompatible_and_auth_rows(self):
		bridge = runpy.run_path(
			str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py")
		)
		iterator = bridge["iter_approved_frappe_exact_archive_records"]
		globals_ = iterator.__globals__
		def sql(statement, params=(), **_kwargs):
			if "FROM __Auth" in statement and params[0] == "S3 Backup Settings":
				return [{"doctype": "S3 Backup Settings", "name": "S3 Backup Settings",
					"fieldname": "aws_secret", "password": "ciphertext", "encrypted": 1}]
			return []

		frappe = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda *_args: True,
				sql=sql,
			)
		)
		with patch.dict(
			globals_,
			{
				"APPROVED_FRAPPE_DATA_ORDER": ("DefaultValue",),
				"APPROVED_FRAPPE_ARCHIVE_ONLY_DOCTYPES": ("S3 Backup Settings",),
				"_spine_doctypes": lambda _frappe: set(),
				"_approved_frappe_names": lambda *_args: ["UNSAFE-DEFAULT"],
				"_approved_frappe_exact_document": lambda _frappe, doctype, name: {
					"doctype": doctype,
					"name": name,
					"defkey": "setup_complete" if doctype == "DefaultValue" else None,
				},
			},
		):
			records = list(iterator(frappe))
		self.assertEqual(
			[row["source_doctype"] for row in records],
			[
				"Approved Frappe Exact::DefaultValue",
				"Approved Frappe Exact::S3 Backup Settings",
				"Approved Frappe Exact::__Auth",
			],
		)
		self.assertEqual(records[-1]["row"]["password"], "ciphertext")

	def test_target_only_children_are_not_deleted_by_supporting_reload(self):
		field = SimpleNamespace(fieldname='links', options='Dynamic Link')
		with patch('essdee_yrp.migration.live.frappe.get_meta', return_value=SimpleNamespace(get_table_fields=lambda: [field])), \
			patch('essdee_yrp.migration.live.frappe.get_all', return_value=['TARGET-ONLY']):
			with self.assertRaisesRegex(MigrationError, 'Target-only children'):
				_assert_supporting_child_ownership({'name': 'A-1', 'links': [{'name': 'SOURCE'}]}, 'Address')

	def test_source_child_identity_cannot_take_over_an_unrelated_parent(self):
		field = SimpleNamespace(fieldname='links', options='Dynamic Link')
		with patch('essdee_yrp.migration.live.frappe.get_meta', return_value=SimpleNamespace(get_table_fields=lambda: [field])), \
			patch('essdee_yrp.migration.live.frappe.get_all', side_effect=[[], [SimpleNamespace(name='SOURCE', parent='OTHER', parenttype='Address', parentfield='links')]]):
			with self.assertRaisesRegex(MigrationError, 'identity collision'):
				_assert_supporting_child_ownership({'name': 'A-1', 'links': [{'name': 'SOURCE'}]}, 'Address')

	def meta(self, doctype):
		fields = {
			"Address": [("address_title", "Data", None), ("links", "Table", "Dynamic Link")],
			"Dynamic Link": [("link_doctype", "Link", "DocType"), ("link_name", "Dynamic Link", "link_doctype")],
		}
		return SimpleNamespace(issingle=False, fields=[SimpleNamespace(fieldname=name, fieldtype=kind, options=options)
			for name, kind, options in fields[doctype]])

	def columns(self, doctype):
		return ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "_user_tags"] + (
			["address_title"] if doctype == "Address" else ["parent", "parenttype", "parentfield", "link_doctype", "link_name"])

	def transform(self, document):
		with (
			patch("essdee_yrp.migration.live.frappe.get_meta", side_effect=self.meta),
			patch("essdee_yrp.migration.live.frappe.db.get_table_columns", side_effect=self.columns),
		):
			return _transform_supporting_document(document, "Address", {"Supplier": "YRP Supplier", "Location": "YRP Warehouse"})

	def test_address_reverse_links_map_doctype_without_renaming_fields_or_records(self):
		source = {"doctype": "Address", "name": "A-1", "address_title": "Billing",
			"_user_tags": "source-tag", "links": [{"doctype": "Dynamic Link", "name": "L-1",
				"link_doctype": "Supplier", "link_name": "S-1", "parenttype": "Address", "idx": 0}]}
		actual = self.transform(source)
		self.assertEqual(actual["name"], "A-1")
		self.assertEqual(actual["_user_tags"], "source-tag")
		self.assertEqual(actual["links"][0]["link_doctype"], "YRP Supplier")
		self.assertEqual(actual["links"][0]["link_name"], "S-1")
		self.assertEqual(actual["links"][0]["parenttype"], "Address")
		self.assertEqual(actual["links"][0]["idx"], 0)
		self.assertEqual(source["links"][0]["link_doctype"], "Supplier")

	def test_populated_unsupported_field_fails_without_printing_its_value(self):
		with self.assertRaises(MigrationError) as error:
			self.transform({"name": "A-1", "retired_field": "private source value"})
		self.assertIn("retired_field", str(error.exception))
		self.assertNotIn("private source value", str(error.exception))
		self.transform({"name": "A-1", "retired_field": None})

	def test_existing_erp_business_master_is_preserved_without_replacement(self):
		target = Mock()
		source = SimpleNamespace(
			iter_supporting_documents=lambda doctype, names: iter(
				[
					{"doctype": doctype, "name": "A-1", "address_title": "MRP value"}
				]
				if names
				else []
			)
		)
		plan = SimpleNamespace(specs={})
		reconciliation = {}
		with (
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value="a-1"),
			patch("essdee_yrp.migration.live._assert_supporting_child_ownership") as ownership,
		):
			counts = _load_supporting_external_masters(
				target,
				source,
				{"Address": {"A-1"}},
				plan=plan,
				dry_run=False,
				reconciliation=reconciliation,
			)
		self.assertEqual(counts["Address"], 1)
		self.assertNotIn(
			"Address", [invocation.args[0] for invocation in target.upsert_batch.call_args_list]
		)
		ownership.assert_not_called()
		self.assertEqual(
			reconciliation["preserved_target_identities"]["Address"],
			{"A-1": "a-1"},
		)
		self.assertEqual(
			reconciliation["inserted_source_identities"]["Address"], []
		)

	def test_missing_business_master_is_transformed_and_inserted(self):
		target = Mock()
		document = {"doctype": "Address", "name": "A-1"}
		source = SimpleNamespace(
			iter_supporting_documents=lambda _doctype, names: iter(
				[document] if names else []
			)
		)
		plan = SimpleNamespace(specs={})
		transformed = {"doctype": "Address", "name": "A-1", "address_title": "MRP"}
		reconciliation = {}
		with (
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=False),
			patch("essdee_yrp.migration.live._assert_supporting_child_ownership") as ownership,
			patch(
				"essdee_yrp.migration.live._transform_supporting_document",
				return_value=transformed,
			) as transform,
		):
			counts = _load_supporting_external_masters(
				target,
				source,
				{"Address": {"A-1"}},
				plan=plan,
				dry_run=False,
				reconciliation=reconciliation,
			)
		self.assertEqual(counts["Address"], 1)
		ownership.assert_called_once_with(document, "Address")
		transform.assert_called_once()
		self.assertIn(
			("Address", [transformed]),
			[invocation.args for invocation in target.upsert_batch.call_args_list],
		)
		self.assertEqual(
			reconciliation["inserted_source_identities"]["Address"], ["A-1"]
		)

	def test_supporting_business_identity_verification_matches_database_case(self):
		source = SimpleNamespace(
			iter_related_business_masters=lambda: iter(
				[
					{"doctype": "Address", "name": "ACME-Billing"},
					{"doctype": "Contact", "name": "Manoj Kumar S"},
				]
			)
		)
		with patch(
			"essdee_yrp.migration.live.frappe.get_all",
			side_effect=[["Acme-Billing"], ["Manoj kumar S"]],
		):
			result = _verify_supporting_business_master_identities(source)

		self.assertEqual(result["status"], "Pass")
		self.assertEqual(result["failures"], [])

	def test_supporting_business_master_verifier_requires_every_source_identity(self):
		source = SimpleNamespace(
			iter_related_business_masters=lambda: iter(
				[
					{"doctype": "Address", "name": "A-1"},
					{"doctype": "Address", "name": "A-2"},
					{"doctype": "Contact", "name": "C-1"},
				]
			)
		)
		with patch(
			"essdee_yrp.migration.live.frappe.get_all",
			side_effect=[["A-1"], ["C-1"]],
		):
			result = _verify_supporting_business_master_identities(source)
		self.assertEqual(result["status"], "Failed")
		self.assertEqual(len(result["failures"]), 1)
		self.assertIn("Address: 1 source identities", result["failures"][0])

	def test_supporting_argument_batches_are_bounded(self):
		bridge = object.__new__(F15SourceBridge)
		bridge._run = Mock(return_value=[])
		list(bridge.iter_supporting_documents("Address", [f"A-{n}" for n in range(501)]))
		self.assertEqual([len(json.loads(call.args[0][-1])) for call in bridge._run.call_args_list], [250, 250, 1])

	def test_source_packing_process_defaults_historical_lot_bom_process(self):
		bridge = object.__new__(F15SourceBridge)
		bridge.settings = SimpleNamespace(required_defaults={})
		bridge._run = Mock(
			return_value=[
				{
					"kind": "migration_defaults",
					"default_received_type": "Accepted",
					"default_packing_process": "Packing",
					"root_item_groups": ["All Item Groups"],
					"bill_received_via": [],
				}
			]
		)
		self.assertEqual(
			bridge.reference_data()["migration_defaults"]["Lot BOM.process_name"],
			"Packing",
		)

	def test_existing_direct_address_references_are_still_in_reload_scope(self):
		spec = SimpleNamespace(target="YRP Supplier", ignored_fields={}, field_map={},
			target_schema={"fields": [{"fieldname": "billing_address", "fieldtype": "Link", "options": "Address"}]})
		plan = SimpleNamespace(specs={"Supplier": spec})
		source = SimpleNamespace(iter_external_references=lambda: iter([{
			"source_doctype": "Supplier", "source_name": "S-1", "fieldname": "billing_address", "value": "A-1"}]))
		with patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True):
			checked, scope = _validate_external_references(plan, source)
		self.assertEqual(checked, 1)
		self.assertEqual(scope, {"Address": {"A-1"}})

	def test_missing_workflow_state_is_loaded_as_a_supporting_master(self):
		spec = SimpleNamespace(
			target="YRP Item Price",
			ignored_fields={},
			field_map={},
			target_schema={
				"fields": [
					{
						"fieldname": "workflow_state",
						"fieldtype": "Link",
						"options": "Workflow State",
					}
				]
			},
		)
		plan = SimpleNamespace(specs={"Item Price": spec})
		source = SimpleNamespace(
			iter_external_references=lambda: iter(
				[
					{
						"source_doctype": "Item Price",
						"source_name": "ITP-00034",
						"fieldname": "workflow_state",
						"value": "Approval Pending",
					}
				]
			)
		)

		def exists(doctype, name):
			return doctype == "DocType" and name == "Workflow State"

		with patch("essdee_yrp.migration.live.frappe.db.exists", side_effect=exists):
			checked, scope = _validate_external_references(plan, source)
		self.assertEqual(checked, 1)
		self.assertEqual(scope, {"Workflow State": {"Approval Pending"}})

	def test_source_bridge_allows_workflow_state_supporting_documents(self):
		bridge = runpy.run_path(
			str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py")
		)
		self.assertIn("Workflow State", bridge["SUPPORTING_EXTERNAL_DOCTYPES"])

	def test_supporting_scope_includes_every_address_and_contact(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		db = Mock()
		db.sql.side_effect = [
			[SimpleNamespace(name="A-1"), SimpleNamespace(name="A-2")],
			[SimpleNamespace(name="C-1"), SimpleNamespace(name="C-UNLINKED")],
			[
				SimpleNamespace(parenttype="Address", parent="A-1"),
				SimpleNamespace(parenttype="Contact", parent="C-1"),
			],
			[("A-2",)],
		]
		self.assertEqual(bridge["related_business_master_names"](SimpleNamespace(db=db), {"Supplier": {}}),
			{"Address": ["A-1", "A-2"], "Contact": ["C-1", "C-UNLINKED"]})

	def test_missing_reverse_link_parent_cannot_be_silently_discarded(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		db = Mock()
		db.sql.side_effect = [
			[SimpleNamespace(name="A-1")],
			[],
			[SimpleNamespace(parenttype="Address", parent="MISSING")],
		]
		with self.assertRaisesRegex(RuntimeError, "preserve this orphan explicitly"):
			bridge["related_business_master_names"](SimpleNamespace(db=db), {"Supplier": {}})

	def test_missing_contact_address_cannot_be_silently_discarded(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		db = Mock()
		db.sql.side_effect = [
			[SimpleNamespace(name="A-1")],
			[SimpleNamespace(name="C-1")],
			[],
			[("MISSING",)],
		]
		with self.assertRaisesRegex(RuntimeError, "selects a missing source Address"):
			bridge["related_business_master_names"](SimpleNamespace(db=db), {})
