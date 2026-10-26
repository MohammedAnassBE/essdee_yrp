from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.merch import lot_workspace as workspace

MODULE = "essdee_yrp.merch.lot_workspace"


class Row(frappe._dict):
	def set(self, field, value):
		self[field] = value


def get_lot(**values):
	data = {
		"name": "ZZ TEST LOT",
		"modified": "2026-10-15 10:00:00",
		"docstatus": 0,
		"production_detail": "IPD-1",
		"production_order": None,
		"item": "Item-1",
		"lot_time_and_action_details": [],
		"is_transferred": 0,
		"items": [],
		"lot_order_details": [Row(quantity=10)],
		"lot_fabric_details": [Row(cloth_item="Cloth-1")],
		"bom_additional_items": [],
		**values,
	}
	doc = Mock()
	doc.meta.get_field.side_effect = lambda field: Row(label=field, fieldtype="Data")
	for key, value in data.items():
		setattr(doc, key, value)
	doc.get.side_effect = lambda key, default=None: data.get(key, default)

	def set_value(key, value):
		data[key] = value
		setattr(doc, key, value)

	def append(key, value):
		row = Row(value)
		data[key].append(row)
		return row

	doc.set.side_effect = set_value
	doc.append.side_effect = append
	return doc


def throw(message, exc=frappe.ValidationError, **kwargs):
	raise exc(message)


class TestMerchLotWorkspace(TestCase):
	def setUp(self):
		self.stack = ExitStack()
		self.addCleanup(self.stack.close)
		self.doc = get_lot()
		self.get_doc = self.mock("frappe.get_doc", return_value=self.doc)
		self.mock("frappe.throw", side_effect=throw)
		self.permissions = self.mock("frappe.has_permission", return_value=True)
		self.original_action_role = workspace.production_order_workflow.user_can_manage_production_order
		self.action_role = self.mock(
			"production_order_workflow.user_can_manage_production_order", return_value=True
		)
		self.demand = self.mock("cloth_program.compute_cloth_demand", return_value={"cloth": 1})
		self.original_matrices = workspace.ipd_engine._get_process_matrices
		self.matrices = self.mock("ipd_engine._get_process_matrices", return_value={"Cutting": [Row()]})
		self.on_demand = self.mock("is_on_demand_garment_ipd", return_value=False)
		self.response = {"name": self.doc.name, "modified": "new-modified"}
		self.original_workspace = workspace.get_merch_lot_workspace
		self.get_workspace = self.mock("get_merch_lot_workspace", return_value=self.response)

	def mock(self, path, **options):
		return self.stack.enter_context(patch(f"{MODULE}.{path}", **options))

	def command(self, command, payload=None, modified=None):
		return workspace.execute_merch_lot_command(
			self.doc.name,
			command,
			payload=payload,
			expected_modified=self.doc.modified if modified is None else modified,
		)

	def test_read_only_actions_are_hidden_and_not_allowed(self):
		self.permissions.return_value = False
		capabilities = workspace.get_lot_capabilities(self.doc)
		self.assertTrue(all(not value["visible"] and not value["allowed"] for value in capabilities.values()))
		self.demand.assert_not_called()

	def test_workspace_retains_purchase_permissions_and_extra_facts(self):
		with (
			patch(
				f"{MODULE}.lot_workspace.get_lot_workspace",
				return_value={"permissions": {"can_write": False}, "has_cloth_program": True},
			),
			patch(
				f"{MODULE}.lot_workspace.get_facts",
				side_effect=lambda doc, fields: [{"fieldname": field, "value": 10} for field in fields],
			),
		):
			self.permissions.return_value = False
			payload = self.original_workspace(self.doc.name)
			self.assertFalse(payload["permissions"]["can_write"])
			self.assertTrue(payload["has_cloth_program"])
			self.assertFalse(payload["capabilities"]["edit"]["allowed"])
			self.assertEqual(
				payload["ipd_facts"], [{"fieldname": field, "value": 10} for field in workspace.IPD_FACTS]
			)

	def test_save_rejects_no_write_before_delegating(self):
		load = self.mock("lot_editor.load_writable_lot", side_effect=frappe.PermissionError)
		save = self.mock("lot_editor.save_lot")
		with self.assertRaises(frappe.PermissionError):
			workspace.save_merch_lot({}, name=self.doc.name, expected_modified=self.doc.modified)
		load.assert_called_once_with(self.doc.name)
		save.assert_not_called()

	def test_save_rejects_stale_and_missing_modified(self):
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot")
		for modified, exception in (("old", frappe.TimestampMismatchError), (None, frappe.ValidationError)):
			with self.subTest(modified=modified), self.assertRaises(exception):
				workspace.save_merch_lot({}, name=self.doc.name, expected_modified=modified)
		save.assert_not_called()

	def test_locked_box_quantity_ratio_and_mrp_changes_are_rejected(self):
		stored = {
			"items": [
				{"attributes": {"Colour": "Assorted"}, "values": {"M": {"qty": 2, "ratio": 1, "mrp": 10}}}
			]
		}
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		self.mock("sd_yrp_lot.fetch_item_details", return_value=stored)
		save = self.mock("lot_editor.save_lot")
		for lock in ({"lot_time_and_action_details": [Row()]}, {"is_transferred": 1}):
			self.doc = get_lot(items=[Row()], **lock)
			workspace.lot_editor.load_writable_lot.return_value = self.doc
			for field in ("qty", "ratio", "mrp"):
				incoming = frappe.parse_json(frappe.as_json(stored))
				incoming["items"][0]["values"]["M"][field] += 1
				with (
					self.subTest(lock=lock, field=field),
					self.assertRaisesRegex(frappe.ValidationError, "Locked"),
				):
					workspace.save_merch_lot(
						{"item_details": [incoming]}, name=self.doc.name, expected_modified=self.doc.modified
					)
		save.assert_not_called()

	def test_save_delegates_and_returns_merch_workspace(self):
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot", return_value={"name": self.doc.name})
		values = {"item_details": [], "order_item_details": [{"items": [{"quantity": 10}]}], "lot_fabric_details": []}
		self.assertEqual(workspace.save_merch_lot(values, self.doc.name, self.doc.modified), self.response)
		save.assert_called_once_with(values, name=self.doc.name, expected_modified=self.doc.modified)

	def test_save_rejects_empty_or_missing_order_items_without_changing_rows(self):
		load = self.mock("lot_editor.load_writable_lot")
		save = self.mock("lot_editor.save_lot")
		for locked in (False, True):
			self.doc = get_lot(
				lot_order_details=[Row(quantity=10, cut_qty=4, stich_qty=3, pack_qty=2)],
				lot_time_and_action_details=[Row()] if locked else [],
			)
			load.return_value = self.doc
			stored = [dict(row) for row in self.doc.lot_order_details]
			for values in ({"order_item_details": []}, {}, {"order_item_details": None}):
				with self.subTest(locked=locked, values=values):
					with self.assertRaisesRegex(frappe.ValidationError, "Order Items cannot be removed here"):
						workspace.save_merch_lot(values, self.doc.name, self.doc.modified)
					self.assertEqual(self.doc.lot_order_details, stored)
		save.assert_not_called()

	def test_save_allows_empty_order_items_before_order_rows_exist(self):
		self.doc = get_lot(lot_order_details=[])
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot", return_value={"name": self.doc.name})
		values = {"item_details": [], "order_item_details": [], "lot_fabric_details": []}
		for name in (None, self.doc.name):
			with self.subTest(name=name):
				self.assertEqual(workspace.save_merch_lot(values, name, self.doc.modified), self.response)
		self.assertEqual(save.call_count, 2)

	def test_every_command_needs_write_and_a_current_version(self):
		run = self.mock("run_lot_command")
		for command in workspace.COMMAND_LABELS:
			with self.subTest(command=command):
				self.doc.check_permission.side_effect = frappe.PermissionError
				with self.assertRaises(frappe.PermissionError):
					self.command(command)
				self.doc.check_permission.side_effect = None
				with self.assertRaises(frappe.TimestampMismatchError):
					self.command(command, modified="old")
				with self.assertRaises(frappe.ValidationError):
					self.command(command, modified="")
		run.assert_not_called()

	def test_every_command_rebuilds_and_requires_capability(self):
		run = self.mock("run_lot_command")
		self.mock("get_lot_capabilities", return_value={})
		for command in (*workspace.COMMAND_LABELS, "unknown"):
			with self.subTest(command=command), self.assertRaises(frappe.PermissionError):
				self.command(command)
		run.assert_not_called()

	def test_build_passes_selections_routes_excess_and_modified(self):
		build = self.mock("cloth_program.build_cloth_programs")
		selections = [
			{"cloth_item": "Cloth", "fabric_routes": [{"knitting_output_dia": "36", "finished_dia": "30"}]}
		]
		self.assertEqual(
			self.command("build_cloth_programs", {"selections": selections, "excess_percentage": 3}),
			self.response,
		)
		build.assert_called_once_with(
			self.doc.name, selections, modified=self.doc.modified, excess_percentage=3
		)

	def test_recalculate_bom_and_order_commands_delegate(self):
		for command, target, arguments in (
			(
				"recalculate_cloth_program",
				"cloth_program.recalculate_cloth_program",
				{"modified": self.doc.modified},
			),
			("calculate_bom", "sd_yrp_lot.calculate_bom", {}),
			("calculate_order_items", "sd_yrp_lot.update_order_details", {}),
		):
			with self.subTest(command=command):
				delegate = self.mock(target)
				self.command(command)
				delegate.assert_called_once_with(self.doc.name, **arguments)

	def test_change_ppo_role_is_required_including_empty_settings(self):
		link = self.mock("production_order_workflow.link_lot")
		self.action_role.return_value = False
		capability = workspace.get_lot_capabilities(self.doc)["change_ppo"]
		self.assertFalse(capability["allowed"])
		self.assertFalse(capability["visible"])
		with self.assertRaises(frappe.PermissionError):
			self.command("change_ppo", {"production_order": "ZZ PPO"})
		link.assert_not_called()

	def test_change_ppo_delegates_and_checks_submitted_matching_item(self):
		order = get_lot(name="ZZ PPO", docstatus=1)
		self.get_doc.side_effect = lambda doctype, name: (
			order if doctype == "YRP Production Order" else self.doc
		)
		link = self.mock("production_order_workflow.link_lot")
		self.command("change_ppo", {"production_order": order.name})
		link.assert_called_once_with(order.name, self.doc.name)
		order.docstatus = 0
		with self.assertRaises(frappe.ValidationError):
			self.command("change_ppo", {"production_order": order.name})

	def test_document_state_disables_actions_with_reasons(self):
		cases = [
			({"production_order": "PPO-1"}, "change_ppo", "Already linked to PPO-1"),
			({"lot_time_and_action_details": [Row()]}, "calculate_order_items", "Time & Action"),
			({"is_transferred": 1}, "build_cloth_programs", "transferred"),
			({"lot_fabric_details": []}, "recalculate_cloth_program", "No Fabric Details"),
			({"production_detail": None}, "calculate_bom", "Item Production Detail"),
			({"lot_order_details": []}, "calculate_bom", "Calculate Order Items"),
			({"docstatus": 1}, "update_bom_additional_items", "Draft"),
		]
		for values, command, reason in cases:
			with self.subTest(command=command):
				capability = workspace.get_lot_capabilities(get_lot(**values))[command]
				self.assertTrue(capability["visible"])
				self.assertFalse(capability["allowed"])
				self.assertIn(reason, capability["reason"])

	def test_bom_requires_the_domain_process_matrix_lookup(self):
		self.matrices.side_effect = self.original_matrices
		query = self.mock("frappe.get_all", return_value=[])
		capability = workspace.get_lot_capabilities(self.doc)["calculate_bom"]
		self.assertTrue(capability["visible"])
		self.assertFalse(capability["allowed"])
		self.assertEqual(capability["reason"], "No IPD Process Matrix found for IPD IPD-1.")
		query.assert_called_once_with(
			"YRP IPD Process Matrix",
			filters={"ipd": "IPD-1", "docstatus": ["<", 2]},
			pluck="name",
			order_by="process_name asc, idx asc, name asc",
		)
		calculate = self.mock("sd_yrp_lot.calculate_bom")
		with self.assertRaises(frappe.PermissionError):
			self.command("calculate_bom")
		calculate.assert_not_called()

	def test_bom_allows_existing_domain_matrices(self):
		self.assertEqual(workspace.get_bom_block(self.doc), "")
		self.matrices.assert_called_once_with("IPD-1")

	def test_bom_allows_garment_ipd_that_builds_matrices_on_demand(self):
		self.on_demand.return_value = True
		self.matrices.return_value = {}
		self.assertEqual(workspace.get_bom_block(self.doc), "")
		self.on_demand.assert_called_once_with("IPD-1")
		self.matrices.assert_not_called()

	def test_additional_items_round_trip_and_remove(self):
		row = {"item_name": "Label", "process_name": "Packing", "uom": "Nos", "required_qty": 20}
		self.command("update_bom_additional_items", {"rows": [row]})
		self.assertEqual(self.doc.get("bom_additional_items"), [row])
		self.command("update_bom_additional_items", {"rows": []})
		self.assertEqual(self.doc.get("bom_additional_items"), [])
		self.assertEqual(self.doc.save.call_count, 2)

	def test_additional_items_validate_required_fields_and_identity(self):
		self.mock("frappe.get_meta", return_value=Mock(get_label=lambda field: field))
		valid = {"item_name": "Label", "process_name": "Packing", "uom": "Nos", "required_qty": 20}
		for field in workspace.BOM_FIELDS[1:]:
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				self.command("update_bom_additional_items", {"rows": [{**valid, field: None}]})
		with self.assertRaisesRegex(frappe.ValidationError, "Unknown"):
			self.command("update_bom_additional_items", {"rows": [{**valid, "name": "other-lot-row"}]})
		self.doc.save.assert_not_called()

	def test_empty_settings_hide_change_ppo_except_existing_system_manager_exception(self):
		self.action_role.side_effect = self.original_action_role
		self.mock("production_order_workflow.get_ppo_action_roles", return_value=set())
		roles = self.mock("frappe.get_roles", return_value=["Merchandiser"])
		self.assertFalse(workspace.get_lot_capabilities(self.doc)["change_ppo"]["visible"])
		with self.assertRaises(frappe.PermissionError):
			self.command("change_ppo")
		roles.return_value = ["System Manager"]
		self.assertTrue(workspace.get_lot_capabilities(self.doc)["change_ppo"]["allowed"])

	def test_ppo_totals_use_only_lot_ordered_rows(self):
		self.doc = get_lot(production_order="PPO-1")
		order = get_lot(
			name="PPO-1",
			production_order_details=[Row(quantity=100), Row(quantity=20)],
			status="Open",
			delivery_date="2026-12-01",
			production_ordered_details=[
				Row(reference_doctype="SD YRP Lot", reference_name=self.doc.name, quantity=10),
				Row(reference_doctype="SD YRP Lot", reference_name=self.doc.name, quantity=5),
				Row(reference_doctype="SD YRP Lot", reference_name="Lot-2", quantity=20),
				Row(reference_doctype="Other", reference_name="Other-1", quantity=50),
			],
		)
		self.get_doc.return_value = order
		payload = workspace.get_ppo_block(self.doc)
		self.assertEqual(payload["quantity"], 120)
		self.assertEqual(payload["lot_quantity"], 15)
		self.assertEqual(payload["other_lots"], [{"name": "Lot-2", "quantity": 20}])
		self.permissions.return_value = False
		self.assertEqual(workspace.get_ppo_block(self.doc), {"name": "PPO-1"})

	def test_ppo_totals_include_legacy_lot_rows(self):
		self.doc = get_lot(production_order="PPO-1")
		self.get_doc.return_value = get_lot(
			name="PPO-1",
			status="Open",
			delivery_date=None,
			production_order_details=[],
			production_ordered_details=[
				Row(reference_doctype=None, reference_name=None, lot=self.doc.name, quantity=10),
				Row(lot=self.doc.name, quantity=5),
				Row(lot="Lot-2", quantity=20),
				Row(reference_doctype="Other", reference_name="Other-1", quantity=50),
			],
		)
		payload = workspace.get_ppo_block(self.doc)
		self.assertEqual(payload["lot_quantity"], 15)
		self.assertEqual(payload["other_lots"], [{"name": "Lot-2", "quantity": 20}])

	def test_ppo_reference_rows_replace_legacy_rows_per_lot_regardless_of_order(self):
		rows = [
			Row(lot="Lot-1", quantity=100),
			Row(reference_doctype="SD YRP Lot", reference_name="Lot-1", lot="Wrong-lot", quantity=10),
			Row(reference_doctype="SD YRP Lot", reference_name="Lot-1", quantity=5),
			Row(lot="Lot-2", quantity=20),
			Row(lot="Lot-3", quantity=90),
			Row(reference_doctype="SD YRP Lot", reference_name="Lot-3", quantity=0),
		]
		for ordered_rows in (rows, list(reversed(rows))):
			with self.subTest(rows=ordered_rows):
				self.assertEqual(
					workspace.get_ppo_lot_quantities(ordered_rows),
					{
						"Lot-1": 15,
						"Lot-2": 20,
						"Lot-3": 0,
					},
				)

	def test_save_rejects_negative_box_cells_for_new_and_existing_lots(self):
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot")
		for name in (None, self.doc.name):
			for field, label in workspace.BOX_LABELS.items():
				for has_sizes in (False, True):
					with self.subTest(name=name, field=field, has_sizes=has_sizes):
						cell = {"qty": 1, "ratio": 1, "mrp": 10, field: "-10"}
						values = {"M": cell} if has_sizes else cell
						with self.assertRaisesRegex(frappe.ValidationError, f"{label} cannot be negative"):
							workspace.save_merch_lot(
								{"item_details": [{"items": [{"values": values}]}]},
								name,
								self.doc.modified,
							)
		save.assert_not_called()

	def test_save_keeps_zero_and_positive_box_cells(self):
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot", return_value={"name": self.doc.name})
		values = {"item_details": [{"items": [{"values": {"M": {"qty": 2, "ratio": 0, "mrp": 0}}}]}],
			"order_item_details": [{"items": [{"quantity": 10}]}]}
		workspace.save_merch_lot(values, self.doc.name, self.doc.modified)
		save.assert_called_once_with(values, name=self.doc.name, expected_modified=self.doc.modified)

	def test_locked_unchanged_boxes_can_save_but_cannot_rekey_variants(self):
		stored = {
			"item": "Item",
			"items": [{"attributes": {}, "values": {"M": {"qty": 2, "ratio": 1, "mrp": 10}}}],
		}
		self.doc = get_lot(items=[Row()], is_transferred=1)
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		self.mock("sd_yrp_lot.fetch_item_details", return_value=stored)
		save = self.mock("lot_editor.save_lot", return_value={"name": self.doc.name})
		workspace.save_merch_lot(
			{"item_details": [stored], "order_item_details": [stored]}, self.doc.name, self.doc.modified
		)
		save.assert_called_once()
		with self.assertRaisesRegex(frappe.ValidationError, "Locked"):
			workspace.save_merch_lot(
				{"item_details": [{**stored, "item": "Different Item"}]}, self.doc.name, self.doc.modified
			)

	def test_additional_edit_preserves_names_and_server_owned_values(self):
		self.doc = get_lot(bom_additional_items=[Row(name="row-1", available_stock=9)])
		self.get_doc.return_value = self.doc
		row = {
			"name": "row-1",
			"item_name": "Label",
			"process_name": "Packing",
			"uom": "Nos",
			"required_qty": 3,
		}
		self.command("update_bom_additional_items", {"rows": [row]})
		self.assertEqual(self.doc.get("bom_additional_items"), [{**row, "available_stock": 9}])

	def test_order_detail_rekey_is_rejected_by_existing_guard(self):
		group = {"items": [{"attributes": {"Colour": "Navy"}, "values": {"M": {"qty": 10}}}]}
		self.mock("lot_editor.fetch_order_item_details", return_value=[group])
		changed = {"items": [{"attributes": {"Colour": "Black"}, "values": {"M": {"qty": 10}}}]}
		with self.assertRaisesRegex(frappe.ValidationError, "rows cannot be added, removed or re-keyed"):
			workspace.lot_editor.reject_order_details_changes(
				self.doc, {"order_item_details": [changed]}, False
			)

	def test_editor_uses_purchase_form_and_adds_derived_facts_and_locks(self):
		self.mock(
			"lot_editor.get_lot_form",
			return_value={"derived": {}, "locks": {}, "fields": [{"fieldname": "production_order"}]},
		)
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		self.mock("lot_workspace.get_order_details", return_value={})
		self.mock("lot_workspace.get_fabrics", return_value=[])
		self.mock("lot_workspace.get_other_conversions", return_value=[])
		self.assertFalse(workspace.get_merch_lot_editor()["box_locked"])
		self.doc = get_lot(production_order="PPO-1", packing_combo=10)
		workspace.lot_editor.load_writable_lot.return_value = self.doc
		payload = workspace.get_merch_lot_editor(self.doc.name)
		self.assertTrue(payload["box_locked"])
		self.assertEqual(payload["derived"]["packing_combo"], 10)
		self.assertNotIn("read_only", payload["fields"][0])

	def test_existing_ppo_change_saves_through_lot_editor(self):
		self.doc = get_lot(lot_order_details=[])
		self.mock("lot_editor.load_writable_lot", return_value=self.doc)
		save = self.mock("lot_editor.save_lot", return_value={"name": self.doc.name})
		self.mock("get_merch_lot_workspace", return_value={})
		workspace.save_merch_lot({"production_order": "PPO-2"}, self.doc.name, self.doc.modified)
		save.assert_called_once()

	def test_record_facts_keep_false_and_zero_values(self):
		self.doc.meta.get_field.return_value = Row(label="Capacity Planning", fieldtype="Check")
		self.doc.meta.get_field.side_effect = None
		self.mock("lot_workspace.get_facts", return_value=[])
		self.assertEqual(
			workspace.get_record_facts(self.doc, ["capacity_planning"]),
			[
				{
					"fieldname": "capacity_planning",
					"label": "Capacity Planning",
					"fieldtype": "Check",
					"value": 0,
				},
			],
		)

	def test_record_facts_include_metadata_for_empty_link_and_dynamic_link(self):
		self.doc = get_lot(reference_type="Item")
		fields = {
			"season": Row(label="Season", fieldtype="Link", options="YRP Season"),
			"reference": Row(label="Reference", fieldtype="Dynamic Link", options="reference_type"),
		}
		self.doc.meta.get_field.side_effect = fields.get
		facts = {row["fieldname"]: row for row in workspace.get_record_facts(self.doc, fields)}
		self.assertEqual(facts["season"]["options"], "YRP Season")
		self.assertIsNone(facts["season"]["value"])
		self.assertEqual(facts["reference"]["options"], "reference_type")
		self.assertEqual(facts["reference"]["link_doctype"], "Item")

	def test_record_facts_retain_link_targets_and_substituted_labels(self):
		self.doc = get_lot(assigned_person="person@example.test", assigned_person_name="Person")
		self.doc.meta.get_field.side_effect = lambda field: Row(label=field, fieldtype="Link", options="User")
		fact = workspace.get_record_facts(self.doc, ["assigned_person"])[0]
		self.assertEqual(fact["value"], "Person")
		self.assertEqual(fact["link_name"], "person@example.test")
		self.assertEqual(fact["options"], "User")
