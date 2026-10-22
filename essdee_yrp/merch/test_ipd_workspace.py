import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.attribute_values import get_mapping_document

from essdee_yrp import ipd_ui
from essdee_yrp.merch import ipd_workspace as workspace
from essdee_yrp.merch.ipd import attribute_values, copy_version, draft, fields
from essdee_yrp.merch.ipd.bom_mapping import required_columns
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd_test_support import SAMPLES, make_user, rolled_back, unapprove

FLOOR = "_test_ipd_floor@example.com"
WRITER = "_test_ipd_merch@example.com"
SENIOR_NOWRITE = "_test_ipd_senior_nowrite@example.com"
SENIOR = "_test_ipd_senior@example.com"
ITEM_MANAGER = "_test_ipd_item_manager@example.com"
EDITABLE = SAMPLES["set_item"]
APPROVED = SAMPLES["panel_wise"]


def wire(value):
	return json.loads(json.dumps(value, default=str))


def modified(name):
	return str(frappe.db.get_value(DOCTYPE, name, "modified"))


class TestIpdWorkspace(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(FLOOR, ["YRP Floor Verify"])
		make_user(WRITER, ["Merchandiser"])
		make_user(SENIOR_NOWRITE, ["Senior Merch"])
		make_user(SENIOR, ["Senior Merch", "Merchandiser"])
		make_user(ITEM_MANAGER, ["Merchandiser", "Item Manager"])
		frappe.db.set_single_value("SD YRP MRP Settings", "senior_merch_role", "Senior Merch")
		unapprove(EDITABLE)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_user(self, user):
		frappe.set_user(user)

	def test_list_capabilities_follow_doctype_permissions(self):
		self.as_user(FLOOR)
		self.assertEqual(workspace.get_ipd_list_capabilities(), {"can_read": True, "can_create": False})
		self.as_user(WRITER)
		self.assertEqual(workspace.get_ipd_list_capabilities(), {"can_read": True, "can_create": True})

	def test_role_matrix(self):
		self.as_user(FLOOR)
		payload = workspace.get_ipd_workspace(EDITABLE)
		self.assertFalse(payload["capabilities"]["edit"]["allowed"])
		self.assertNotIn("grids", payload)
		for call in (
			lambda: workspace.get_ipd_editor(EDITABLE),
			lambda: workspace.save_ipd({}, EDITABLE, modified(EDITABLE)),
			lambda: workspace.get_ipd_grids(EDITABLE, {}, ["set_combination"]),
			lambda: workspace.copy_ipd(EDITABLE, "QA-TP", "QA-P"),
			lambda: ipd_ui.duplicate_ipd(EDITABLE),
		):
			self.assertRaises(frappe.PermissionError, call)

		self.as_user(SENIOR_NOWRITE)
		self.assertRaises(frappe.PermissionError, workspace.get_ipd_workspace, EDITABLE)
		self.assertRaises(frappe.PermissionError, ipd_ui.approve_ipd, EDITABLE)

		self.as_user(WRITER)
		capabilities = workspace.get_ipd_editor(EDITABLE)["capabilities"]
		self.assertTrue(capabilities["save"]["allowed"])
		self.assertFalse(capabilities["approve"]["allowed"])
		self.assertRaises(
			frappe.PermissionError,
			workspace.execute_ipd_command,
			EDITABLE,
			"approve",
			expected_modified=modified(EDITABLE),
		)

		self.as_user(SENIOR)
		capabilities = workspace.get_ipd_workspace(EDITABLE)["capabilities"]
		self.assertTrue(capabilities["approve"]["allowed"])
		self.assertFalse(capabilities["revert_approval"]["allowed"])

	def test_approved_ipd_is_read_only_but_can_regenerate(self):
		self.as_user(SENIOR)
		capabilities = workspace.get_ipd_workspace(APPROVED)["capabilities"]
		self.assertFalse(capabilities["edit"]["allowed"])
		self.assertEqual(capabilities["edit"]["reason"], "Approved IPDs are read only.")
		self.assertTrue(capabilities["revert_approval"]["allowed"])
		self.assertTrue(capabilities["regenerate_process_matrix"]["allowed"])
		self.assertFalse(capabilities["approve"]["allowed"])
		with self.assertRaisesRegex(frappe.ValidationError, "Approved IPDs are read only"):
			workspace.save_ipd({"description": "x"}, APPROVED, modified(APPROVED))

	def test_approve_then_revert(self):
		self.as_user(SENIOR)
		with rolled_back("approve_revert"):
			payload = workspace.execute_ipd_command(EDITABLE, "approve", expected_modified=modified(EDITABLE))
			self.assertEqual(payload["record"]["approval_status"], "Approved")
			self.assertEqual(payload["record"]["approved_by"], SENIOR)
			self.assertTrue(payload["capabilities"]["revert_approval"]["allowed"])
			payload = workspace.execute_ipd_command(
				EDITABLE, "revert_approval", expected_modified=payload["record"]["modified"]
			)
			self.assertEqual(payload["record"]["approval_status"], "Not Approved")

	def test_approve_refused_when_a_server_rule_fails(self):
		self.as_user(SENIOR)
		with rolled_back("approve_server_rule"):
			row = frappe.get_doc(DOCTYPE, EDITABLE).stiching_item_details[0]
			frappe.db.set_value(row.doctype, row.name, "quantity", 0, update_modified=False)
			with self.assertRaisesRegex(frappe.ValidationError, "Zero is not considered"):
				workspace.execute_ipd_command(EDITABLE, "approve", expected_modified=modified(EDITABLE))
			self.assertEqual(frappe.db.get_value(DOCTYPE, EDITABLE, "approval_status"), "Not Approved")

	def test_client_only_rule_blocks_approve_and_save(self):
		self.as_user(SENIOR)
		with rolled_back("approve_client_rule"):
			row = frappe.get_doc(DOCTYPE, EDITABLE).stiching_item_combination_details[0]
			frappe.db.set_value(row.doctype, row.name, "attribute_value", None, update_modified=False)
			with self.assertRaisesRegex(frappe.ValidationError, "Fill all the combinations"):
				workspace.execute_ipd_command(EDITABLE, "approve", expected_modified=modified(EDITABLE))
			values = wire(workspace.get_ipd_editor(EDITABLE)["values"])
			with self.assertRaisesRegex(frappe.ValidationError, "Fill all the combinations"):
				workspace.save_ipd(
					{"stiching_item_detail": values["stiching_item_detail"]}, EDITABLE, modified(EDITABLE)
				)

	def test_cloth_processes_are_readable_writable_and_checked(self):
		self.as_user(SENIOR)
		name = SAMPLES["cloth"]
		with rolled_back("cloth_processes"):
			unapprove(name)
			doc = frappe.get_doc(DOCTYPE, name)
			self.assertIn("processes", fields.sections_for(doc))
			self.assertIn("ipd_processes", fields.writable_keys(doc))
			self.assertNotIn("emblishment_details_json", fields.writable_keys(doc))
			payload = workspace.get_ipd_editor(name)
			self.assertIn("ipd_processes", payload["values"])
			self.assertNotIn("emblishment_details_json", payload["values"])
			rows = wire(payload["values"]["ipd_processes"])
			if not rows:
				process = frappe.get_doc(DOCTYPE, EDITABLE).ipd_processes[0].process_name
				rows = [{"process_name": process, "in_stage": None, "out_stage": None}]
			# A cloth process can consume the cloth item itself.
			rows[0]["process_item"] = doc.item
			patch_values = {"ipd_processes": rows}
			built = draft.build_draft(name, patch_values)
			self.assertEqual(built.ipd_processes[0].process_item, doc.item)
			checks = workspace.check_ipd(name, patch_values)
			self.assertFalse(any(entry["rule"] == "patch" for entry in checks["problems"]))
			invalid_rows = [dict(row) for row in rows]
			invalid_rows[0]["process_item"] = frappe.db.get_value(DOCTYPE, EDITABLE, "item")
			invalid_checks = workspace.check_ipd(name, {"ipd_processes": invalid_rows})
			self.assertTrue(
				any(entry["field"] == "ipd_processes" for entry in invalid_checks["problems"])
			)
			saved = workspace.save_ipd(patch_values, name, modified(name))
			self.assertEqual(saved["values"]["ipd_processes"][0]["process_item"], doc.item)
			self.assertEqual(frappe.get_doc(DOCTYPE, name).ipd_processes[0].process_item, doc.item)

	def test_cloth_embellishment_is_rejected_by_draft_checks_and_save(self):
		self.as_user(SENIOR)
		name = SAMPLES["cloth"]
		with rolled_back("cloth_no_embellishment"):
			unapprove(name)
			patch_values = {"emblishment_details_json": {"Printing": []}}
			with self.assertRaisesRegex(frappe.ValidationError, "not part of this kind"):
				draft.build_draft(name, patch_values)
			checks = workspace.check_ipd(name, patch_values)
			self.assertTrue(any(entry["rule"] == "patch" for entry in checks["problems"]))
			with self.assertRaisesRegex(frappe.ValidationError, "not part of this kind"):
				workspace.save_ipd(patch_values, name, modified(name))

	def test_stale_writes_are_refused(self):
		self.as_user(SENIOR)
		stale = "2000-01-01 00:00:00.000000"
		with self.assertRaises(frappe.TimestampMismatchError):
			workspace.save_ipd({"description": "x"}, EDITABLE, stale)
		with self.assertRaises(frappe.TimestampMismatchError):
			workspace.execute_ipd_command(EDITABLE, "approve", expected_modified=stale)
		with self.assertRaises(frappe.TimestampMismatchError):
			workspace.execute_ipd_command(APPROVED, "revert_approval", expected_modified=stale)
		with self.assertRaisesRegex(frappe.ValidationError, "Reload the record"):
			workspace.save_ipd({"description": "x"}, EDITABLE)

	def test_patch_guards(self):
		values = wire(workspace.get_ipd_editor(EDITABLE)["values"])
		guards = {
			"Item is fixed": {"item": "Some Other Item"},
			"read only": {"approval_status": "Approved"},
			"cannot be changed here": {"amended_from": EDITABLE},
			"not part of this kind": {"fabric_routes": []},
			"Unknown .* row: missing-row": {
				"stiching_item_details": [{"name": "missing-row", "quantity": 1}]
			},
			"is not a valid": {"packing_mode": "Bogus Packing"},
			"must be an object": {"cutting_items_json": []},
		}
		for message, patch_values in guards.items():
			with self.subTest(message=message), self.assertRaisesRegex(frappe.ValidationError, message):
				workspace.save_ipd(patch_values, EDITABLE, modified(EDITABLE))
		with self.assertRaisesRegex(frappe.ValidationError, "derived from the panel-wise matrix"):
			name = SAMPLES["panel_grouped"]
			workspace.save_ipd({"cutting_items_json": {"items": []}}, name, modified(name))
		self.assertIn("stiching_item_details", values)

	def test_new_draft_gets_item_defaults_and_owned_mappings(self):
		self.as_user(WRITER)
		item = frappe.db.get_value(DOCTYPE, EDITABLE, "item")
		new = workspace.get_ipd_editor()
		self.assertIsNone(new["record"]["name"])
		self.assertEqual(new["capabilities"]["save"]["label"], "Create IPD")
		with rolled_back("new_draft"):
			payload = workspace.save_ipd({"item": item, "tech_pack_version": "QA-TP"})
			doc = frappe.get_doc(DOCTYPE, payload["record"]["name"])
			item_mappings = set(frappe.get_all("Item Variant Attribute", {"parent": item}, pluck="mapping"))
			self.assertTrue(doc.item_attributes)
			self.assertFalse({row.mapping for row in doc.item_attributes} & item_mappings)
			item_doc = frappe.get_doc("Item", item)
			if item_doc.dependent_attribute_mapping:
				self.assertTrue(doc.dependent_attribute_mapping)
				self.assertNotEqual(doc.dependent_attribute_mapping, item_doc.dependent_attribute_mapping)
			mappings_by_attribute = {row.attribute: row.mapping for row in item_doc.attributes}
			for row in doc.item_attributes:
				with self.subTest(attribute=row.attribute):
					self.assertEqual(
						[value.attribute_value for value in get_mapping_document(row.mapping).get("values")],
						[
							value.attribute_value
							for value in get_mapping_document(mappings_by_attribute[row.attribute]).get("values")
						],
					)
			self.assertEqual(doc.owner, WRITER)
			with self.assertRaisesRegex(frappe.ValidationError, "Item is fixed"):
				workspace.save_ipd({"item": item}, doc.name, str(doc.modified))

	def test_duplicate_opens_unsaved_copy_and_saves_owned_mappings(self):
		self.as_user(WRITER)
		source = frappe.get_doc(DOCTYPE, EDITABLE)
		count = frappe.db.count(DOCTYPE)
		draft_payload = workspace.get_ipd_editor(duplicate_from=EDITABLE)
		self.assertIsNone(draft_payload["record"]["name"])
		self.assertEqual(draft_payload["values"]["item"], source.item)
		self.assertEqual(draft_payload["values"]["approval_status"], "Not Approved")
		self.assertEqual(frappe.db.count(DOCTYPE), count)
		with rolled_back("duplicate_draft"):
			payload = workspace.save_ipd({"tech_pack_version": "QA-DUP"}, duplicate_from=EDITABLE)
			doc = frappe.get_doc(DOCTYPE, payload["record"]["name"])
			self.assertNotEqual(doc.name, EDITABLE)
			self.assertEqual(doc.tech_pack_version, "QA-DUP")
			self.assertEqual(doc.item, source.item)
			for table in ("item_attributes", "packing_attribute_details", "stiching_item_details", "item_bom"):
				with self.subTest(table=table):
					self.assertEqual(len(doc.get(table)), len(source.get(table)))
			self.assertFalse(
				{row.mapping for row in doc.item_attributes if row.mapping}
				& {row.mapping for row in source.item_attributes if row.mapping}
			)
			source_bom = {row.attribute_mapping for row in source.item_bom if row.attribute_mapping}
			copied_bom = {row.attribute_mapping for row in doc.item_bom if row.attribute_mapping}
			self.assertEqual(len(copied_bom), len(source_bom))
			self.assertFalse(copied_bom & source_bom)
			self.assertEqual(frappe.db.get_value(DOCTYPE, EDITABLE, "modified"), source.modified)

	def test_save_attribute_values(self):
		self.as_user(WRITER)
		entry = colour_context(EDITABLE)
		with rolled_back("chip_remove"):
			result = workspace.save_ipd_attribute_values(
				EDITABLE, "Colour", entry["values"][:-1], entry["mapping_modified"]
			)
			self.assertEqual(result["values"], entry["values"][:-1])
			self.assertIn("set_combination", result["grids_stale"])
		catalogue = frappe.get_all(
			"Item Attribute Value",
			{"parent": "Colour", "parenttype": "Item Attribute"},
			pluck="attribute_value",
		)
		extra = next(value for value in catalogue if value not in entry["values"])
		with rolled_back("chip_add_existing"):
			result = workspace.save_ipd_attribute_values(
				EDITABLE, "Colour", [*entry["values"], extra.lower(), extra], entry["mapping_modified"]
			)
			self.assertEqual(result["values"], [*entry["values"], extra])
		unknown = ["QA Unknown Colour", "QA Other Unknown Colour"]
		self.assertTrue(set(unknown).isdisjoint(catalogue))
		for user in (WRITER, ITEM_MANAGER):
			self.as_user(user)
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"QA Unknown Colour, QA Other Unknown Colour is not a Colour value. Pick values from the Colour list.",
			):
				workspace.save_ipd_attribute_values(
					EDITABLE, "Colour", [extra, *unknown], entry["mapping_modified"]
				)
			self.assertEqual(colour_context(EDITABLE), entry)
			self.assertCountEqual(attribute_values.get_global_attribute_values("Colour"), catalogue)

	def test_attribute_values_stale_after_lock(self):
		entry = colour_context(EDITABLE)
		calls = []
		real = attribute_values.get_mapping_document

		def tracked(name, **kwargs):
			calls.append(kwargs)
			return real(name, **kwargs)

		with (
			patch.object(attribute_values, "get_mapping_document", side_effect=tracked),
			self.assertRaises(frappe.TimestampMismatchError),
		):
			workspace.save_ipd_attribute_values(EDITABLE, "Colour", entry["values"], "2000-01-01 00:00:00")
		self.assertEqual(calls, [{"for_update": True}])

	def test_attribute_values_refused(self):
		entry = colour_context(EDITABLE)
		with self.assertRaisesRegex(frappe.ValidationError, "is not an attribute"):
			workspace.save_ipd_attribute_values(EDITABLE, "Width", [], entry["mapping_modified"])
		with rolled_back("chip_shared"):
			other = frappe.get_doc(DOCTYPE, SAMPLES["standard"]).item_attributes[0]
			frappe.db.set_value(other.doctype, other.name, "mapping", entry["mapping"], update_modified=False)
			with self.assertRaisesRegex(frappe.ValidationError, "shared"):
				workspace.save_ipd_attribute_values(
					EDITABLE, "Colour", entry["values"], entry["mapping_modified"]
				)
		approved = colour_context(APPROVED)
		with self.assertRaisesRegex(frappe.ValidationError, "Approved IPDs are read only"):
			workspace.save_ipd_attribute_values(
				APPROVED, "Colour", approved["values"], approved["mapping_modified"]
			)

	def test_bom_mapping_wrapper(self):
		payload = workspace.get_ipd_editor(EDITABLE)
		row_name, detail = next(iter(payload["context"]["bom_mappings"].items()))
		with rolled_back("bom_save"):
			result = workspace.save_ipd_bom_mapping(
				EDITABLE, row_name, detail["rows"], detail["mapping_modified"]
			)
			self.assertEqual(result["bom_mappings"][row_name]["rows"], detail["rows"])
		with self.assertRaises(frappe.TimestampMismatchError):
			workspace.save_ipd_bom_mapping(EDITABLE, row_name, detail["rows"], "2000-01-01 00:00:00")
		with rolled_back("bom_shared"):
			other = frappe.get_doc(DOCTYPE, SAMPLES["standard"]).item_bom[0]
			frappe.db.set_value(
				other.doctype, other.name, "attribute_mapping", detail["mapping"], update_modified=False
			)
			with self.assertRaisesRegex(frappe.ValidationError, "shared"):
				workspace.save_ipd_bom_mapping(EDITABLE, row_name, detail["rows"], detail["mapping_modified"])
		with rolled_back("bom_shared_same_ipd"):
			sibling = next(row for row in frappe.get_doc(DOCTYPE, EDITABLE).item_bom if row.name != row_name)
			frappe.db.set_value(
				sibling.doctype, sibling.name, "attribute_mapping", detail["mapping"], update_modified=False
			)
			shared = workspace.get_ipd_editor(EDITABLE)["context"]["bom_mappings"]
			self.assertTrue(shared[row_name]["is_shared"])
			self.assertTrue(shared[sibling.name]["is_shared"])
			with self.assertRaisesRegex(frappe.ValidationError, "shared"):
				workspace.save_ipd_bom_mapping(EDITABLE, row_name, detail["rows"], detail["mapping_modified"])
		with self.assertRaisesRegex(frappe.ValidationError, "not part of this IPD"):
			workspace.save_ipd_bom_mapping(
				EDITABLE, "missing-row", detail["rows"], detail["mapping_modified"]
			)

	def test_bom_mapping_excludes_same_attribute_columns(self):
		mapping = frappe.get_doc("YRP Item BOM Attribute Mapping", first_bom_mapping(EDITABLE))
		attribute = mapping.item_attributes[0].attribute
		mapping.item_attributes[0].same_attribute = 1
		mapping.append("bom_item_attributes", {"attribute": attribute, "same_attribute": 1})
		self.assertNotIn(attribute, required_columns(mapping)["item"])
		self.assertNotIn(attribute, required_columns(mapping)["bom"])

	def test_used_by_and_source_respect_user_permissions(self):
		older = f"{frappe.db.get_value(DOCTYPE, EDITABLE, 'item')}-1"
		with rolled_back("user_permissions"):
			frappe.db.set_value(DOCTYPE, EDITABLE, "copied_from", older, update_modified=False)
			frappe.get_doc(
				{"doctype": "User Permission", "user": WRITER, "allow": DOCTYPE, "for_value": EDITABLE}
			).insert(ignore_permissions=True)
			self.as_user(WRITER)
			payload = workspace.get_ipd_workspace(EDITABLE)
			self.assertEqual([row["ipd"] for row in payload["used_by"]], [EDITABLE])
			self.assertEqual(payload["source"], {"name": None, "hidden": True})
			self.assertEqual(workspace.get_ipd_changes(EDITABLE), {"source": None, "changes": []})

	def test_lot_counts_follow_lot_permissions(self):
		source = "437807-Ladies Bow Frill-2"
		lots = frappe.get_all("SD YRP Lot", filters={"production_detail": source}, pluck="name")
		if not lots:
			self.skipTest(f"{source} has no lots")
		with rolled_back("lot_permissions"):
			frappe.get_doc(
				{"doctype": "User Permission", "user": WRITER, "allow": "SD YRP Lot", "for_value": lots[0]}
			).insert(ignore_permissions=True)
			self.as_user(WRITER)
			self.assertEqual(workspace.get_ipd_copy_options(source)["source"]["lot_count"], 1)
			doc = frappe.get_doc(DOCTYPE, source)
			value = attribute_values.attribute_value(doc.packing_attribute_details[0].attribute_value)
			usage = workspace.get_attribute_value_usage(source, doc.packing_attribute, [value])["usage"]
			lot_entries = [entry for entry in usage[value] if entry["section"] == "lots"]
			self.assertEqual([entry["count"] for entry in lot_entries], [1])

	def test_mapping_writes_lock_the_ipd_first(self):
		entry = colour_context(EDITABLE)
		calls = []
		real = frappe.get_doc

		def tracked(*args, **kwargs):
			if args[:1] == (DOCTYPE,):
				calls.append(kwargs.get("for_update"))
			return real(*args, **kwargs)

		with rolled_back("chip_lock"), patch.object(attribute_values.frappe, "get_doc", side_effect=tracked):
			workspace.save_ipd_attribute_values(
				EDITABLE, "Colour", entry["values"], entry["mapping_modified"]
			)
		self.assertEqual(calls[0], True)

	def test_usage_reports_draft_only_values(self):
		values = wire(workspace.get_ipd_editor(EDITABLE)["values"])
		rows = [*values["stiching_item_details"], {"stiching_attribute_value": "QA Hood", "quantity": 1}]
		usage = workspace.get_attribute_value_usage(
			EDITABLE,
			"Panel",
			["QA Hood", rows[0]["stiching_attribute_value"]],
			{"stiching_item_details": rows},
		)["usage"]
		self.assertEqual(usage["QA Hood"][0]["section"], "stitching")
		sections = {entry["section"] for entry in usage[rows[0]["stiching_attribute_value"]]}
		self.assertTrue({"stitching", "lots"} <= sections)
		self.assertEqual(
			workspace.get_attribute_value_usage(EDITABLE, "Panel", ["Nowhere"])["usage"], {"Nowhere": []}
		)

	def test_copy_sections(self):
		self.as_user(WRITER)
		options = workspace.get_ipd_copy_options(EDITABLE)
		item = frappe.db.get_value(DOCTYPE, EDITABLE, "item")
		versions = frappe.get_all(DOCTYPE, {"item": item}, pluck="version")
		self.assertEqual(options["next_version"], max(versions) + 1)
		locked = {row["key"] for row in options["sections"] if row["locked"]}
		self.assertEqual(locked, {"attributes", "packing", "set_item", "stitching"})
		with self.assertRaisesRegex(frappe.ValidationError, "Tech Pack Version"):
			workspace.copy_ipd(EDITABLE, "", "QA-P")
		for sections in (
			[],
			["cutting"],
			["accessories"],
			["processes"],
			["cutting", "accessories"],
			["cutting", "processes"],
			["accessories", "processes"],
			["cutting", "accessories", "processes"],
		):
			with self.subTest(sections=sections), rolled_back("copy_sections"):
				name = workspace.copy_ipd(EDITABLE, "QA-TP", "QA-P", sections)["name"]
				doc = frappe.get_doc(DOCTYPE, name)
				kept = copy_version.close_sections(sections)
				self.assertEqual(doc.copied_from, EDITABLE)
				self.assertEqual((doc.tech_pack_version, doc.pattern_version), ("QA-TP", "QA-P"))
				self.assertEqual(bool(doc.cloth_detail), "cutting" in kept)
				self.assertEqual(bool(doc.item_bom), "accessories" in kept)
				self.assertEqual(bool(doc.ipd_processes), "processes" in kept)
				owned = frappe.get_all(
					"YRP Item BOM Attribute Mapping", {"item_production_detail": name}, pluck="name"
				)
				self.assertEqual(
					sorted(owned),
					sorted(row.attribute_mapping for row in doc.item_bom if row.attribute_mapping),
				)
				changes = {change["field"] for change in workspace.get_ipd_changes(name)["changes"]}
				self.assertTrue({"tech_pack_version", "pattern_version"} <= changes)

	def test_copy_failure_leaves_nothing(self):
		before = frappe.db.count(DOCTYPE)
		mappings = frappe.db.count("YRP Item Item Attribute Mapping")
		with (
			patch.object(copy_version, "drop_section", side_effect=frappe.ValidationError("boom")),
			self.assertRaisesRegex(frappe.ValidationError, "boom"),
		):
			workspace.copy_ipd(EDITABLE, "QA-TP", "QA-P", [])
		self.assertEqual(frappe.db.count(DOCTYPE), before)
		self.assertEqual(frappe.db.count("YRP Item Item Attribute Mapping"), mappings)


def colour_context(name):
	payload = workspace.get_ipd_editor(name)
	return wire(next(entry for entry in payload["context"]["attributes"] if entry["attribute"] == "Colour"))


def first_bom_mapping(name):
	return next(
		row.attribute_mapping for row in frappe.get_doc(DOCTYPE, name).item_bom if row.attribute_mapping
	)
