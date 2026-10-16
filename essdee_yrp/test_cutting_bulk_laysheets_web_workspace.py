from copy import deepcopy
from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.base_document import BaseDocument

from essdee_yrp.cutting.bulk_laysheets_workspace import (
	_assert_source_permissions,
	_normalise_values,
	approve_grammage,
	complete_label_print,
	create_bulk_delivery_challans,
	create_bulk_lot_transfer,
	create_delivery_challan,
	create_laysheets,
	create_lot_transfer,
	generate_bundles,
	get_editor,
	get_print_context,
	get_workspace,
	save,
	save_active_editor,
	set_active_laysheet,
	submit_bulk_lot_transfer,
	submit_delivery_challan,
	submit_lot_transfer,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets import (
	sd_yrp_cutting_bulk_lay_sheets as native_bulk,
)

DOCTYPE = "SD YRP Cutting Bulk Lay Sheets"


class SetupChildRow(BaseDocument):
	def __init__(self, values):
		super().__init__({**dict.fromkeys(("name", "cutting_laysheet", "lot_transfer", "delivery_challan", "status")), **values})


def bulk_row(name="ROW-1", status="Create Lay Sheet", **values):
	return frappe._dict(
		{
			"name": name,
			"idx": 1,
			"lot": "LOT-SPLIT-1",
			"cutting_plan": "CP-001",
			"cutting_marker": "CM-001",
			"work_order": "WO-001",
			"cutting_laysheet": None,
			"lot_transfer": None,
			"delivery_challan": None,
			"status": status,
			**values,
		}
	)


def bulk_doc(rows=None, **values):
	doc = frappe._dict(
		{
			"doctype": DOCTYPE,
			"name": "CBLS-001",
			"modified": "2026-10-03 10:00:00",
			"docstatus": 0,
			"main_lot": "LOT-MAIN",
			"from_location": "CUTTING",
			"posting_date": "2026-10-03",
			"cutting_spreader": "SPREADER-1",
			"cutter": "CUTTER-1",
			"status": "Setup",
			"active_cutting_laysheet": None,
			"lot_details": rows if rows is not None else [bulk_row()],
			**values,
		}
	)
	doc.get = lambda key, default=None: dict.get(doc, key, default)
	return doc


class TestCuttingBulkLaySheetsWebWorkspace(TestCase):
	def _save_setup(self, previous, values, name="CBLS-001"):
		doc = object.__new__(native_bulk.SDYRPCuttingBulkLaySheets)
		doc.__dict__.update(previous)
		doc.__dict__.pop("get", None)
		doc.flags = frappe._dict()
		doc._table_fieldnames = {"lot_details": "SD YRP Cutting Bulk Lay Sheet Detail"}
		doc.save = MagicMock(side_effect=doc._validate_lot_rows)
		doc.insert = MagicMock(side_effect=doc._validate_lot_rows)
		plans = {row["cutting_plan"]: row["lot"] for row in values["lot_details"]}
		markers = {row["cutting_marker"]: row["cutting_plan"] for row in values["lot_details"]}

		def get_value(doctype, document_name, fields, **kwargs):
			if doctype == DOCTYPE:
				return previous
			if doctype == "SD YRP Cutting Plan":
				return frappe._dict(lot=plans[document_name], work_order=document_name.replace("CP-", "WO-"), docstatus=1, cp_status="Ready to Cut")
			return frappe._dict(cutting_plan=markers[document_name], docstatus=1)

		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "new_doc", return_value=doc),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_all", return_value=previous.lot_details),
			patch("frappe.model.base_document.get_controller", return_value=SetupChildRow),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_source_permissions"),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value=doc),
		):
			return save(values, name=name, expected_modified=previous.modified)

	def _setup_values(self, doc):
		fields = ("main_lot", "from_location", "posting_date", "cutting_spreader", "cutter")
		values = {field: doc[field] for field in fields}
		values["lot_details"] = [{field: row[field] for field in ("name", "lot", "cutting_plan", "cutting_marker")} for row in doc.lot_details]
		return values

	def test_edit_setup_saves_headers_without_dropping_persisted_child_fields(self):
		for field, value in (("cutter", "CUTTER-2"), ("cutting_spreader", "SPREADER-2"), ("posting_date", "2026-10-04")):
			with self.subTest(field=field):
				previous = bulk_doc([bulk_row(lot_transfer="LT-1", delivery_challan="DC-1")])
				values = self._setup_values(previous)
				values[field] = value
				doc = self._save_setup(previous, values)
				self.assertEqual(doc.get(field), value)
				self.assertEqual({key: doc.lot_details[0].get(key) for key in previous.lot_details[0]}, dict(previous.lot_details[0]))
				doc.save.assert_called_once_with()

	def test_existing_laysheet_row_retains_all_workflow_links_and_status(self):
		previous = bulk_doc([bulk_row(cutting_laysheet="CLS-1", lot_transfer="LT-1", delivery_challan="DC-1", status="Ready to Print")])
		doc = self._save_setup(previous, self._setup_values(previous))
		for field in ("work_order", "cutting_laysheet", "lot_transfer", "delivery_challan", "status"):
			self.assertEqual(doc.lot_details[0].get(field), previous.lot_details[0][field])
		with (
			patch.object(frappe, "get_doc", return_value=previous),
			patch.object(frappe, "has_permission", return_value=True),
		):
			self.assertTrue(get_editor(previous.name)["setup_locked"])

	def test_unlocked_rows_can_be_added_removed_and_change_plan_and_marker(self):
		previous = bulk_doc([bulk_row(), bulk_row(name="ROW-2", lot="LOT-SPLIT-2", cutting_plan="CP-002", cutting_marker="CM-002")])
		values = self._setup_values(previous)
		values["lot_details"] = [
			{"name": "ROW-1", "lot": "LOT-SPLIT-1", "cutting_plan": "CP-003", "cutting_marker": "CM-003"},
			{"lot": "LOT-SPLIT-3", "cutting_plan": "CP-004", "cutting_marker": "CM-004"},
		]
		doc = self._save_setup(previous, values)
		self.assertEqual([(row.lot, row.cutting_plan, row.cutting_marker, row.work_order) for row in doc.lot_details], [
			("LOT-SPLIT-1", "CP-003", "CM-003", "WO-003"),
			("LOT-SPLIT-3", "CP-004", "CM-004", "WO-004"),
		])
		self.assertEqual(doc.lot_details[0].name, "ROW-1")

	def test_laysheet_rows_and_headers_remain_locked_on_server(self):
		previous = bulk_doc([bulk_row(cutting_laysheet="CLS-1")])
		for field in ("main_lot", "from_location", "posting_date", "cutting_spreader", "cutter"):
			values = self._setup_values(previous)
			values[field] = "CHANGED"
			with self.subTest(header=field), self.assertRaises(frappe.ValidationError):
				self._save_setup(previous, values)
		for field in ("lot", "cutting_plan", "cutting_marker"):
			values = self._setup_values(previous)
			values["lot_details"][0][field] = "CHANGED"
			with self.subTest(row=field), self.assertRaises(frappe.ValidationError):
				self._save_setup(previous, values)
		values = self._setup_values(previous)
		values["lot_details"] = [{"lot": "OTHER", "cutting_plan": "CP-002", "cutting_marker": "CM-002"}]
		with self.assertRaises(frappe.ValidationError):
			self._save_setup(previous, values)

	def test_locked_posting_date_accepts_equivalent_string_and_rejects_changed_date(self):
		previous = bulk_doc([bulk_row(cutting_laysheet="CLS-1")], posting_date=date(2026, 10, 15))
		values = self._setup_values(previous)
		values["posting_date"] = "2026-10-15"
		doc = self._save_setup(previous, values)
		self.assertEqual(doc.posting_date, "2026-10-15")
		values["posting_date"] = "2026-10-16"
		with self.assertRaisesRegex(frappe.ValidationError, "Posting Date cannot change"):
			self._save_setup(previous, values)

	def test_locked_bulk_accepts_new_split_lot_with_equivalent_string_date(self):
		previous = bulk_doc([bulk_row(cutting_laysheet="CLS-1")], posting_date=date(2026, 10, 15))
		values = self._setup_values(previous)
		values["posting_date"] = "2026-10-15"
		values["lot_details"].append({"lot": "LOT-SPLIT-2", "cutting_plan": "CP-002", "cutting_marker": "CM-002"})
		doc = self._save_setup(previous, values)
		self.assertEqual(doc.lot_details[0].cutting_laysheet, "CLS-1")
		self.assertEqual(doc.lot_details[1].lot, "LOT-SPLIT-2")

	def test_desk_setup_validation_normalizes_locked_posting_date(self):
		old_setup = bulk_doc([bulk_row(cutting_laysheet="CLS-1")], posting_date=date(2026, 10, 15))
		doc = object.__new__(native_bulk.SDYRPCuttingBulkLaySheets)
		doc.__dict__.update(old_setup)
		doc.__dict__.pop("get", None)
		with (
			patch.object(frappe.db, "get_value", return_value=old_setup),
			patch.object(frappe, "get_all", return_value=old_setup.lot_details),
			patch.object(doc, "_validated_row_plan", return_value=frappe._dict(work_order="WO-001")),
			patch.object(doc, "_validate_row_marker"),
			patch.object(doc, "_restore_existing_row"),
		):
			doc.posting_date = "2026-10-15"
			doc._validate_lot_rows()
			doc.posting_date = "2026-10-16"
			with self.assertRaisesRegex(frappe.ValidationError, "Posting Date cannot change"):
				doc._validate_lot_rows()

	def test_new_setup_saves_and_rejects_split_lot_equal_to_main_lot(self):
		previous = bulk_doc(name=None, lot_details=[], __islocal=1)
		values = self._setup_values(previous)
		values["lot_details"] = [{"lot": "LOT-SPLIT-1", "cutting_plan": "CP-001", "cutting_marker": "CM-001"}]
		doc = self._save_setup(previous, values, name=None)
		doc.insert.assert_called_once_with()
		self.assertEqual(doc.lot_details[0].work_order, "WO-001")
		values["lot_details"][0]["lot"] = values["main_lot"]
		with self.assertRaisesRegex(frappe.ValidationError, "Split Lot must be different"):
			self._save_setup(previous, values, name=None)

	def test_setup_rejects_crafted_read_only_child_fields(self):
		previous = bulk_doc()
		for field in ("work_order", "cutting_laysheet", "lot_transfer", "delivery_challan", "status", "idx", "unknown"):
			values = self._setup_values(previous)
			values["lot_details"][0][field] = "INJECTED"
			with self.subTest(field=field), self.assertRaisesRegex(frappe.ValidationError, "cannot be changed here"):
				_normalise_values(values, previous)

	def test_setup_requires_read_permission_for_every_source_record(self):
		values = {
			"main_lot": "LOT-MAIN",
			"lot_details": [{
				"lot": "LOT-SPLIT",
				"cutting_plan": "CP-SECRET",
				"cutting_marker": "CM-SECRET",
			}],
		}
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", side_effect=lambda dt, name: frappe._dict(doctype=dt, name=name)),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._require_permission") as require,
		):
			_assert_source_permissions(values)

		checked = {(args.args[0], args.args[2].name) for args in require.call_args_list}
		self.assertEqual(
			checked,
			{
				("SD YRP Lot", "LOT-MAIN"),
				("SD YRP Lot", "LOT-SPLIT"),
				("SD YRP Cutting Plan", "CP-SECRET"),
				("SD YRP Cutting Marker", "CM-SECRET"),
			},
		)

	def test_direct_native_print_context_requires_laysheet_print_permission(self):
		bulk = frappe._dict(name="CBLS-001")
		row = frappe._dict(cutting_laysheet="CLS-001")
		laysheet = MagicMock()
		laysheet.name = "CLS-001"

		def deny_print(ptype):
			if ptype == "print":
				raise frappe.PermissionError

		laysheet.check_permission.side_effect = deny_print
		with (
			patch.object(native_bulk, "get_bulk_doc", return_value=bulk),
			patch.object(native_bulk, "get_entry", return_value=row),
			patch.object(native_bulk.frappe, "get_doc", return_value=laysheet),
			patch.object(native_bulk, "validate_bulk_print_prerequisites") as validate,
		):
			with self.assertRaises(frappe.PermissionError):
				native_bulk.get_label_print_context("CBLS-001", "ROW-1")

		validate.assert_not_called()
		laysheet.db_set.assert_not_called()

	def test_values_accept_only_setup_and_authoritative_row_identity(self):
		doc = bulk_doc()
		values = {
			"main_lot": "LOT-MAIN",
			"from_location": "CUTTING",
			"posting_date": "2026-10-03",
			"cutting_spreader": "SPREADER-1",
			"cutter": "CUTTER-1",
			"lot_details": [{
				"_row_key": "ROW-1",
				"name": "ROW-1",
				"lot": "LOT-SPLIT-1",
				"cutting_plan": "CP-001",
				"cutting_marker": "CM-001",
			}],
		}
		normalised = _normalise_values(values, doc)
		self.assertEqual(normalised["lot_details"][0]["name"], "ROW-1")
		self.assertNotIn("_row_key", normalised["lot_details"][0])

		for fieldname in ("status", "active_cutting_laysheet", "work_order", "lot_transfer"):
			with self.subTest(fieldname=fieldname), self.assertRaises(frappe.ValidationError):
				_normalise_values({**values, fieldname: "injected"}, doc)

		unknown = deepcopy(values)
		unknown["lot_details"][0]["name"] = "ROW-OTHER"
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(unknown, doc)

		duplicate = deepcopy(values)
		duplicate["lot_details"].append(deepcopy(duplicate["lot_details"][0]))
		with self.assertRaises(frappe.ValidationError):
			_normalise_values(duplicate, doc)

	def test_new_editor_uses_today_and_create_permission(self):
		doc = bulk_doc(name=None, lot_details=[], posting_date=None)
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.nowdate", return_value="2026-10-03"),
		):
			payload = get_editor()

		self.assertEqual(payload["record"]["posting_date"], "2026-10-03")
		self.assertEqual(payload["record"]["lot_details"], [])
		self.assertTrue(payload["permissions"]["can_create"])

	def test_workspace_projects_active_editor_and_permission_aware_actions(self):
		rows = [
			bulk_row(cutting_laysheet="CLS-001", status="Create Lot Transfer"),
			bulk_row(
				name="ROW-2",
				lot="LOT-SPLIT-2",
				cutting_plan="CP-002",
				cutting_marker="CM-002",
				cutting_laysheet="CLS-002",
				status="Create Lot Transfer",
			),
		]
		doc = bulk_doc(rows, active_cutting_laysheet="CLS-001", status="In Progress")

		def permission(doctype, ptype="read", **kwargs):
			if doctype == "SD YRP Cutting LaySheet":
				return ptype in {"read", "create", "write", "print"}
			if doctype == "SD YRP Lot Transfer":
				return ptype in {"read", "create", "submit"}
			if doctype == "YRP Delivery Challan":
				return ptype == "read"
			return True

		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.has_permission", side_effect=permission),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_entry_status", side_effect=lambda row: row.status),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_laysheet_editor_data", return_value={"context": {"name": "CLS-001"}, "bundles": []}),
		):
			payload = get_workspace("CBLS-001")

		self.assertEqual(payload["active_laysheet"]["context"]["name"], "CLS-001")
		self.assertTrue(payload["rows"][0]["actions"]["can_generate_bundles"])
		self.assertTrue(payload["rows"][0]["actions"]["can_create_lot_transfer"])
		self.assertFalse(payload["rows"][0]["actions"]["can_create_delivery_challan"])
		self.assertTrue(payload["bulk_actions"]["can_create_bulk_lot_transfer"])
		self.assertFalse(payload["permissions"]["delivery_challan"]["can_create"])

	def test_save_new_and_stale_existing_use_native_document_validation(self):
		new_doc = MagicMock()
		new_doc.name = "CBLS-NEW"
		new_doc.modified = "same"
		new_doc.docstatus = 0
		new_doc.lot_details = []
		values = {
			"main_lot": "LOT-MAIN",
			"from_location": "CUTTING",
			"posting_date": "2026-10-03",
			"cutting_spreader": "SPREADER-1",
			"cutter": "CUTTER-1",
			"lot_details": [{"lot": "LOT-SPLIT-1", "cutting_plan": "CP-001", "cutting_marker": "CM-001"}],
		}
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.has_permission", return_value=True),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.new_doc", return_value=new_doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_source_permissions"),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value={"record": {"name": "CBLS-NEW"}}),
		):
			payload = save(values)
		new_doc.update.assert_called_once()
		new_doc.insert.assert_called_once_with()
		self.assertEqual(payload["record"]["name"], "CBLS-NEW")

		existing = bulk_doc(modified="newer")
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=existing),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.has_permission", return_value=True),
		):
			with self.assertRaises(frappe.TimestampMismatchError):
				save(values, name="CBLS-001", expected_modified="older")

	def test_workflow_wrappers_delegate_to_native_methods_and_refresh(self):
		workspace = {"record": {"name": "CBLS-001"}}
		wrappers = [
			(create_laysheets, ("CBLS-001",), "create_laysheets", ("CBLS-001",)),
			(create_lot_transfer, ("CBLS-001", "ROW-1"), "create_lot_transfer", ("CBLS-001", "ROW-1")),
			(create_bulk_lot_transfer, ("CBLS-001",), "create_bulk_lot_transfer", ("CBLS-001",)),
			(create_delivery_challan, ("CBLS-001", "ROW-1", "DC-.#####", "TN01"), "create_delivery_challan", ("CBLS-001", "ROW-1", "DC-.#####", "TN01")),
			(create_bulk_delivery_challans, ("CBLS-001", "DC-.#####", "TN01"), "create_bulk_delivery_challans", ("CBLS-001", "DC-.#####", "TN01")),
		]
		for wrapper, args, native_name, native_args in wrappers:
			with self.subTest(wrapper=wrapper.__name__):
				with (
					patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission"),
					patch(f"essdee_yrp.cutting.bulk_laysheets_workspace.native.{native_name}", return_value="RESULT") as native_call,
					patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value=workspace),
				):
					payload = wrapper(*args)
				native_call.assert_called_once_with(*native_args)
				self.assertEqual(payload["workspace"], workspace)
				self.assertEqual(payload["result"], "RESULT")

	def test_bulk_transfer_submit_checks_the_linked_transfer_record(self):
		doc = bulk_doc([bulk_row(lot_transfer="LT-001", status="Submit Lot Transfer")])
		transfer = frappe._dict(
			doctype="SD YRP Lot Transfer",
			name="LT-001",
			cutting_bulk_lay_sheet="CBLS-001",
		)
		with (
			patch(
				"essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission",
				return_value=doc,
			),
			patch(
				"essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc",
				return_value=transfer,
			),
			patch(
				"essdee_yrp.cutting.bulk_laysheets_workspace._require_permission"
			) as require_permission,
			patch(
				"essdee_yrp.cutting.bulk_laysheets_workspace.native.submit_bulk_lot_transfer",
				return_value="LT-001",
			) as native_call,
			patch(
				"essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace",
				return_value={"record": {"name": "CBLS-001"}},
			),
		):
			payload = submit_bulk_lot_transfer("CBLS-001")

		require_permission.assert_called_once_with("SD YRP Lot Transfer", "submit", transfer)
		native_call.assert_called_once_with("CBLS-001")
		self.assertEqual(payload["result"], "LT-001")

	def test_generate_bundles_uses_saved_laysheet_rows_and_validates_parts(self):
		row = bulk_row(cutting_laysheet="CLS-001", status="Ready to Generate")
		doc = bulk_doc([row])
		laysheet = frappe._dict(
			name="CLS-001",
			cutting_marker="CM-001",
			maximum_no_of_plys=100,
			maximum_allow_percentage=10,
			cutting_laysheet_details=[frappe._dict(name="CLOTH-1")],
			cutting_laysheet_manual_items=[frappe._dict(name="MANUAL-1")],
		)
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=laysheet),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_entry", return_value=row),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._require_permission"),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_parts", return_value=[{"part": "Front", "value": 1}, {"part": "Back", "value": 2}]),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_cut_sheet_data", return_value=[{"bundle_no": 1}]) as generate,
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value={"record": {"name": "CBLS-001"}}),
		):
			payload = generate_bundles(
				"CBLS-001",
				"ROW-1",
				[{"part": "Front", "value": 1}, {"part": "Back", "value": 1}],
				"2026-10-03",
			)

		args = generate.call_args.kwargs
		self.assertEqual(args["doc_name"], "CLS-001")
		self.assertEqual(args["cutting_marker"], "CM-001")
		self.assertEqual(args["laysheet_details"], [{"name": "CLOTH-1"}])
		self.assertEqual(args["manual_item_details"], [{"name": "MANUAL-1"}])
		self.assertEqual(payload["result"], [{"bundle_no": 1}])

	def test_print_context_keeps_native_prerequisite_result(self):
		row = bulk_row(cutting_laysheet="CLS-001")
		doc = bulk_doc([row])
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_entry", return_value=row),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._related_doc", return_value=frappe._dict(name="CLS-001")),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._require_permission") as permission,
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_label_print_context", return_value={"approval_required": True}) as native_call,
		):
			payload = get_print_context("CBLS-001", "ROW-1")
		native_call.assert_called_once_with("CBLS-001", "ROW-1")
		self.assertEqual([call.args[1] for call in permission.call_args_list], ["write", "print"])
		self.assertEqual(payload, {"approval_required": True})

	def test_active_editor_saves_validated_child_payload_with_child_timestamp(self):
		row = bulk_row(cutting_laysheet="CLS-001")
		doc = bulk_doc([row], active_cutting_laysheet="CLS-001")
		laysheet = frappe._dict(name="CLS-001", modified="child-token", cutting_plan="CP-001", cutting_order=None)
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_entry", return_value=row),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=laysheet),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._require_permission"),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.save_web_laysheet_details") as save_details,
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value={"record": {"name": "CBLS-001"}}),
		):
			payload = save_active_editor(
				"CBLS-001",
				"ROW-1",
				{"cloth_items": [{"fabric_type": "Open Width", "items_json": {}, "set_combination": {}}]},
				[],
				"child-token",
			)
		save_details.assert_called_once()
		self.assertEqual(save_details.call_args.kwargs["modified"], "child-token")
		self.assertEqual(save_details.call_args.kwargs["cloth_details"][0]["fabric_type"], "Open Width")
		self.assertEqual(payload["record"]["name"], "CBLS-001")

	def test_per_row_lot_transfer_submit_validates_link_and_uses_native_lifecycle(self):
		row = bulk_row(lot_transfer="LT-001", status="Submit Lot Transfer")
		doc = bulk_doc([row])
		transfer = frappe._dict(name="LT-001", cutting_bulk_lay_sheet="CBLS-001", docstatus=0)
		transfer.submit = MagicMock()
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._assert_action_permission", return_value=doc),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.get_entry", return_value=row),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=transfer),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace._require_permission"),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.refresh_bulk_status") as refresh,
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.get_workspace", return_value={"record": {"name": "CBLS-001"}}),
		):
			payload = submit_lot_transfer("CBLS-001", "ROW-1")
		transfer.submit.assert_called_once_with()
		refresh.assert_called_once_with("CBLS-001")
		self.assertEqual(payload["result"], "LT-001")

	def test_direct_mutation_denial_stops_native_action(self):
		with (
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.get_doc", return_value=bulk_doc()),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.frappe.has_permission", return_value=False),
			patch("essdee_yrp.cutting.bulk_laysheets_workspace.native.create_laysheets") as native_call,
		):
			with self.assertRaises(frappe.PermissionError):
				create_laysheets("CBLS-001")
		native_call.assert_not_called()
