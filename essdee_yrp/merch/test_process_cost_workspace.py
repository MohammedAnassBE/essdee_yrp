import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.model.document import Document
from frappe.model.workflow import get_transitions

from essdee_yrp.merch import process_cost_workspace as workspace

MODULE = "essdee_yrp.merch.process_cost_workspace"


def workflow_fixture():
	import yrp

	path = Path(yrp.__file__).parent / "fixtures" / "workflow.json"
	workflow = next(row for row in json.loads(path.read_text()) if row["document_type"] == workspace.DOCTYPE)
	workflow = frappe._dict(workflow)
	workflow.states = [frappe._dict(row) for row in workflow.states]
	workflow.transitions = [frappe._dict(row) for row in workflow.transitions]
	for row in workflow.transitions:
		row.as_dict = lambda row=row: row
	return workflow


def cost_document(state="Draft", docstatus=0):
	values = frappe._dict(doctype=workspace.DOCTYPE, name="ZZ TEST PC", workflow_state=state,
		docstatus=docstatus, modified="2099-01-01 00:00:00", owner="zz.creator@example.test",
		item="ZZ TEST Item", process_name="ZZ TEST Process", supplier="ZZ TEST Supplier",
		is_rework=0, lot="ZZ TEST Lot", from_date="2099-01-01", attribute=None, process_cost_values=[])
	doc = Mock(spec=Document)
	doc.get.side_effect = values.get
	for key, value in values.items():
		setattr(doc, key, value)
	doc.is_new.return_value = False
	return doc


class TestProcessCostWorkspace(TestCase):
	def setUp(self):
		self.workflow = workflow_fixture()
		self.roles = []
		self.addCleanup(patch.stopall)
		patch(f"{MODULE}.get_workflow", return_value=self.workflow).start()
		patch("frappe.model.workflow.get_workflow", return_value=self.workflow).start()
		patch(f"{MODULE}.get_transitions", side_effect=get_transitions).start()
		patch("frappe.get_roles", side_effect=lambda: self.roles).start()
		patch("frappe.has_permission", return_value=True).start()
		patch("frappe.session", frappe._dict(user="zz.creator@example.test")).start()
		self.approval_matches = workspace._approval_matches
		patch(f"{MODULE}._approval_matches", return_value=[]).start()

	def assert_actions(self, state, status, role, actions, can_edit):
		self.roles = [role]
		doc = cost_document(state, status)
		self.assertEqual([row["action"] for row in workspace._actions(doc)], actions)
		self.assertEqual(workspace.is_editable_by_user(doc), can_edit)

	def test_state_and_role_matrix(self):
		cases = [
			("Draft", 0, "Purchase User", ["Submit"], True),
			("Draft", 0, "Purchase Manager", [], False),
			("Approval Pending", 0, "Purchase User", [], False),
			("Approval Pending", 0, "Purchase Manager", ["Approve", "Reject"], True),
			("Approved", 1, "Purchase Manager", ["Expired"], False),
			("Rejected", 0, "Purchase User", ["Revise"], True),
			("Rejected", 0, "Purchase Manager", ["Revise"], False),
			("Expired", 2, "Purchase Manager", [], False),
			("Draft", 0, "Merch User", [], False),
			("Draft", 0, "Merch Manager", [], False),
			("Draft", 0, "Production Planner", [], False),
			("Approval Pending", 0, "Brand QA Manager", [], False),
		]
		for case in cases:
			with self.subTest(case=case):
				self.assert_actions(*case)
		for role in ("Merch User", "Merch Manager", "Production Planner", "Brand QA Manager"):
			for state, status in (("Draft", 0), ("Approval Pending", 0), ("Approved", 1), ("Rejected", 0), ("Expired", 2)):
				with self.subTest(role=role, state=state):
					self.assert_actions(state, status, role, [], False)

	def test_self_approval_uses_existing_transition(self):
		self.roles = ["Purchase User", "Purchase Manager"]
		self.assertEqual([row["action"] for row in workspace._actions(cost_document())], ["Submit"])
		self.assertEqual([row["action"] for row in workspace._actions(cost_document("Approval Pending"))], ["Approve", "Reject"])

	def test_read_and_write_permission_are_checked_after_lock(self):
		doc = cost_document()
		with patch(f"{MODULE}.frappe.get_doc", return_value=doc) as get_doc:
			self.assertIs(workspace._load_locked(doc.name, "write", doc.modified), doc)
		get_doc.assert_any_call(workspace.DOCTYPE, doc.name, for_update=True)
		self.assertEqual(doc.check_permission.call_args_list, [(("read",),), (("write",),)] * 2)

	def test_save_refuses_merch_user_after_creation(self):
		self.roles = ["Merch User"]
		with patch(f"{MODULE}._load_locked", return_value=cost_document()), patch(f"{MODULE}._apply_values") as apply_values:
			with self.assertRaisesRegex(frappe.PermissionError, "not editable"):
				workspace.save_process_cost({}, "ZZ TEST PC", "old")
		apply_values.assert_not_called()

	def test_stale_save_action_and_delete(self):
		for callback in (
			lambda: workspace.save_process_cost({}, "ZZ TEST PC", "old"),
			lambda: workspace.execute_process_cost_command("ZZ TEST PC", "Submit", "old"),
			lambda: workspace.delete_process_cost("ZZ TEST PC", "old"),
		):
			with patch(f"{MODULE}.frappe.get_doc", return_value=cost_document()):
				with self.assertRaisesRegex(frappe.TimestampMismatchError, "changed after you opened"):
					callback()

	def test_delete_permission_does_not_require_edit_role(self):
		self.roles = ["Purchase Manager"]
		doc = cost_document()
		self.assertFalse(workspace.is_editable_by_user(doc))
		self.assertTrue(workspace.is_deletable_by_user(doc))
		with patch(f"{MODULE}._load_locked", return_value=doc), patch(f"{MODULE}.frappe.delete_doc") as delete:
			self.assertTrue(workspace.delete_process_cost(doc.name, doc.modified)["deleted"])
		delete.assert_called_once_with(workspace.DOCTYPE, doc.name)
		self.assertFalse(workspace.is_deletable_by_user(cost_document("Expired", 2)))

	def test_waiting_notes(self):
		self.assertEqual(workspace._waiting_note(cost_document(), [], False), "Waiting for a Purchase User to submit")
		self.assertEqual(workspace._waiting_note(cost_document("Approval Pending"), [], False), "Waiting for Purchase Manager approval")

	def test_workspace_includes_readable_work_orders_with_permission_filtered_count(self):
		doc = cost_document()
		section = workspace.DOCUMENT_SECTIONS["work_orders"]
		rows = [frappe._dict(name="ZZ TEST WO", docstatus=1, modified=doc.modified, status="Open")]
		with patch("frappe.get_doc", return_value=doc), patch(f"{MODULE}._schema", return_value={}), \
			patch("frappe.get_list", side_effect=[rows, [frappe._dict(count=501)]]) as get_list:
			payload = workspace.get_process_cost_workspace(doc.name)
		self.assertEqual(payload["work_orders"], {"permitted": True, "count": 501, "rows": [dict(rows[0])]})
		doc.check_permission.assert_any_call("read")
		filters = {"process_cost": doc.name, "docstatus": ["!=", 2]}
		self.assertEqual(get_list.call_count, 2)
		get_list.assert_any_call(section["doctype"], filters=filters,
			fields=["name", "docstatus", "modified", *section["fields"]],
			order_by=section["order_by"], limit_page_length=500)
		get_list.assert_any_call(section["doctype"], filters=filters,
			fields=[{"COUNT": "name", "as": "count"}], order_by="", limit_page_length=1)

	def test_work_orders_without_read_permission_do_not_query(self):
		with patch("frappe.has_permission", return_value=False) as has_permission, patch("frappe.get_list") as get_list:
			self.assertEqual(workspace._work_orders("ZZ TEST PC"), {"permitted": False, "count": 0, "rows": []})
		has_permission.assert_called_once_with("YRP Work Order", "read")
		get_list.assert_not_called()

	def test_work_orders_with_no_visible_rows(self):
		with patch("frappe.get_list", side_effect=[[], [frappe._dict(count=0)]]):
			self.assertEqual(workspace._work_orders("ZZ TEST PC"), {"permitted": True, "count": 0, "rows": []})

	def test_approval_preview_and_clash(self):
		with patch(f"{MODULE}._approval_matches", return_value=[frappe._dict(name="ZZ TEST Older", from_date="2098-01-01")]):
			preview = workspace._approve_preview(cost_document())
		self.assertEqual(preview["preview"], "Approving will end ZZ TEST Older on 31-12-2098")
		with patch(f"{MODULE}._approval_matches", return_value=[frappe._dict(name="ZZ TEST Clash", from_date="2099-01-01")]):
			preview = workspace._approve_preview(cost_document())
		self.assertFalse(preview["allowed"])
		self.assertIn("same From Date", preview["reason"])

	def test_missing_and_zero_price_rows(self):
		for rows in ([], [{"price": 0, "min_order_qty": 0}]):
			with self.subTest(rows=rows), self.assertRaisesRegex(frappe.ValidationError, "At least one Process Cost Value"):
				workspace._apply_tiers(frappe._dict(attribute=None), {"process_cost_values": rows}, {"attribute_values": []})

	def test_attribute_value_required_and_scoped(self):
		for value in (None, "unrelated"):
			with self.subTest(value=value), self.assertRaisesRegex(frappe.ValidationError, "Attribute Value"):
				workspace._validate_tier({"attribute_value": value, "price": 12, "min_order_qty": 0}, 2, {"allowed"}, "Size", set())

	def test_tiers_allow_distinct_quantities_and_reject_duplicates(self):
		seen = set()
		for quantity in (0, 10):
			workspace._validate_tier({"attribute_value": "size-1", "price": 12.5, "min_order_qty": quantity}, 0, {"size-1"}, "Size", seen)
		with self.assertRaisesRegex(frappe.ValidationError, "Duplicate Attribute Value and Min Order Qty"):
			workspace._validate_tier({"attribute_value": "size-1", "price": 13, "min_order_qty": 10}, 2, {"size-1"}, "Size", seen)

	def test_numeric_errors_have_cell_coordinates(self):
		with patch(f"{MODULE}._schema", return_value={"label": "Price"}):
			with self.assertRaises(frappe.ValidationError) as error:
				workspace._numeric_value("NaN", 3, "price")
		payload = json.loads(str(error.exception).split("\n", 1)[1])
		self.assertEqual((payload["row"], payload["column"]), (3, "price"))

	def test_action_rechecks_workflow_role(self):
		self.roles = ["Merch Manager"]
		with patch(f"{MODULE}._load_locked", return_value=cost_document()), patch(f"{MODULE}.apply_workflow") as apply:
			with self.assertRaises(frappe.PermissionError):
				workspace.execute_process_cost_command("ZZ TEST PC", "Submit", "old")
		apply.assert_not_called()

	def test_action_executes_through_workflow(self):
		self.roles = ["Purchase User"]
		doc = cost_document()
		with patch(f"{MODULE}._load_locked", return_value=doc), patch(f"{MODULE}.apply_workflow") as apply, patch(f"{MODULE}.get_process_cost_workspace", return_value={"saved": True}):
			self.assertEqual(workspace.execute_process_cost_command(doc.name, "Submit", doc.modified), {"saved": True})
		apply.assert_called_once_with(doc, "Submit")

	def test_deadlock_retries_once_only(self):
		with patch(f"{MODULE}._execute_once", side_effect=[frappe.QueryDeadlockError, {"ok": True}]) as execute, patch("frappe.db", Mock()) as database:
			self.assertEqual(workspace.execute_process_cost_command("ZZ TEST PC", "Submit", "old"), {"ok": True})
		self.assertEqual(execute.call_count, 2)
		database.rollback.assert_called_once()
		with patch(f"{MODULE}._execute_once", side_effect=frappe.QueryDeadlockError) as execute, patch("frappe.db", Mock()):
			with self.assertRaises(frappe.QueryDeadlockError):
				workspace.execute_process_cost_command("ZZ TEST PC", "Submit", "old")
		self.assertEqual(execute.call_count, 2)

	def test_other_failures_are_not_retried(self):
		with patch(f"{MODULE}._execute_once", side_effect=frappe.PermissionError) as execute:
			with self.assertRaises(frappe.PermissionError):
				workspace.execute_process_cost_command("ZZ TEST PC", "Submit", "old")
		execute.assert_called_once()

	def test_no_create_permission_refuses_insert(self):
		with patch("frappe.has_permission", side_effect=frappe.PermissionError), patch(f"{MODULE}.frappe.new_doc") as new:
			with self.assertRaises(frappe.PermissionError):
				workspace.save_process_cost({})
		new.assert_not_called()

	def test_editor_refuses_read_only_workflow_state(self):
		self.roles = ["Merch User"]
		with patch(f"{MODULE}.frappe.get_doc", return_value=cost_document()):
			with self.assertRaisesRegex(frappe.PermissionError, "not editable"):
				workspace.get_process_cost_editor("ZZ TEST PC")

	def test_required_fields_use_desk_labels(self):
		for fieldname, label in (("lot", "Lot"), ("process_name", "Process"), ("supplier", "Supplier"), ("tax_slab", "Tax Slab"), ("from_date", "From Date")):
			values = frappe._dict(dict.fromkeys(workspace.REQUIRED_FIELDS, "present"))
			values[fieldname] = None
			with patch(f"{MODULE}._schema", return_value={"label": label}):
				with self.assertRaisesRegex(frappe.ValidationError, f"{label} is required"):
					workspace._require_fields(values)

	def test_lot_derives_item_before_process_is_selected(self):
		lot = cost_document()
		with patch(f"{MODULE}.frappe.get_doc", return_value=lot), patch(f"{MODULE}._item_uom", return_value="Nos"):
			context = workspace._selection("ZZ TEST Lot")
		self.assertEqual((context["item"], context["uom"]), ("ZZ TEST Item", "Nos"))
		self.assertFalse(context["is_cloth_process"])

	def restrict_link_reads(self, blocked=("Item", "YRP Item Production Detail")):
		def has_permission(doctype, *args, throw=False, **kwargs):
			if doctype in blocked and throw:
				raise frappe.PermissionError
			return doctype not in blocked

		return patch("frappe.has_permission", side_effect=has_permission)

	def selection_database(self):
		database = Mock()
		values = {("YRP Process", "is_cloth_process"): 0, ("Item", "stock_uom"): "Nos",
			("Supplier", "supplier_name"): "ZZ TEST Supplier Name", ("YRP Tax Slab", "enabled"): 1}
		database.get_value.side_effect = lambda doctype, name, fieldname: values[(doctype, fieldname)]
		return database

	def test_merch_user_grid_derives_item_and_uom_without_item_or_ipd_read(self):
		self.roles = ["Merch User"]
		lot = cost_document()
		with self.restrict_link_reads(), patch("frappe.db", self.selection_database()), patch("frappe.get_doc", return_value=lot):
			for process_name in (None, "ZZ TEST Process"):
				grid = workspace.get_process_cost_grid("ZZ TEST Lot", process_name)
				self.assertEqual((grid["item"], grid["uom"]), (lot.item, "Nos"))
				self.assertNotIn("field_errors", grid)
		lot.check_permission.assert_called_with("read")

	def test_merch_user_can_insert_without_attribute_or_item_or_ipd_read(self):
		self.roles = ["Merch User"]
		doc = frappe._dict(attribute=None, workflow_state="Draft")
		doc.set = lambda key, value: doc.update({key: value})
		doc.insert = Mock(side_effect=lambda: doc.update(name="ZZ TEST PC"))
		values = {"lot": "ZZ TEST Lot", "process_name": "ZZ TEST Process", "item": "untrusted",
			"supplier": "ZZ TEST Supplier", "from_date": "2099-01-01", "tax_slab": "ZZ TEST Tax",
			"process_cost_values": [{"price": 12.5, "min_order_qty": 0}]}
		with self.restrict_link_reads(), patch("frappe.db", self.selection_database()), patch("frappe.new_doc", return_value=doc), patch("frappe.get_doc", return_value=cost_document()), patch(f"{MODULE}.get_process_cost_workspace", return_value={"saved": True}):
			self.assertEqual(workspace.save_process_cost(values), {"saved": True})
		doc.insert.assert_called_once()
		self.assertEqual((doc.item, doc.uom, doc.attribute), ("ZZ TEST Item", "Nos", None))
		self.assertEqual(doc.process_cost_values, [{"attribute_value": None, "min_order_qty": 0, "price": 12.5}])

	def test_attribute_permission_failures_return_field_error_payload(self):
		for blocked in (("Item", "YRP Item Production Detail"), ("YRP Item Production Detail",)):
			with self.subTest(blocked=blocked), self.restrict_link_reads(blocked), patch("frappe.db", self.selection_database()), patch("frappe.get_doc", return_value=cost_document()), patch(f"{MODULE}.process_cost._resolve_ipd_name", return_value="ZZ TEST IPD"):
				grid = workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Process", attribute="Panel")
				self.assertEqual(grid["attribute_values"], [])
				self.assertIn(f"You cannot read {blocked[0]}", grid["field_errors"]["attribute"])
				self.assertIn("needed to price by Attribute", grid["field_errors"]["attribute"])
				if blocked == ("YRP Item Production Detail",):
					self.assertIn("ZZ TEST IPD", grid["field_errors"]["attribute"])

	def test_attribute_search_permission_failure_returns_field_error_payload(self):
		with self.restrict_link_reads(("YRP Item Production Detail",)), patch("frappe.db", self.selection_database()), patch("frappe.get_doc", return_value=cost_document()), patch(f"{MODULE}.process_cost._resolve_ipd_name", return_value="ZZ TEST IPD"):
			result = workspace.search_process_cost_attributes("ZZ TEST Lot", "ZZ TEST Process")
		self.assertEqual(result["options"], [])
		self.assertEqual(result["field_errors"], {"attribute": "You cannot read YRP Item Production Detail ZZ TEST IPD needed to price by Attribute."})

	def test_save_refuses_unresolvable_attribute_before_insert(self):
		doc = cost_document()
		with self.restrict_link_reads(("YRP Item Production Detail",)), patch("frappe.db", self.selection_database()), patch("frappe.new_doc", return_value=doc), patch("frappe.get_doc", return_value=cost_document()), patch(f"{MODULE}.process_cost._resolve_ipd_name", return_value="ZZ TEST IPD"):
			doc.attribute = "Panel"
			with self.assertRaises(frappe.ValidationError) as error:
				workspace.save_process_cost({})
		payload = json.loads(str(error.exception).split("\n", 1)[1])
		self.assertIn("ZZ TEST IPD", payload["field_errors"]["attribute"])
		doc.insert.assert_not_called()

	def test_cloth_permission_failure_returns_item_field_error(self):
		lot = frappe._dict(name="ZZ TEST Lot", item="ZZ TEST Item", lot_fabric_details=[
			frappe._dict(cloth_item="ZZ TEST Cloth", production_detail="ZZ TEST Cloth IPD")])
		lot.check_permission = Mock()
		database = Mock()
		database.get_value.return_value = 1
		with self.restrict_link_reads(), patch("frappe.db", database), patch("frappe.get_doc", return_value=lot), patch(f"{MODULE}.get_work_order_selection_context", side_effect=frappe.PermissionError):
			grid = workspace.get_process_cost_grid(lot.name, "ZZ TEST Dyeing")
		self.assertTrue(grid["is_cloth_process"])
		self.assertEqual(grid["item_options"], [])
		self.assertEqual(grid["field_errors"], {"item": "You cannot read YRP Item Production Detail ZZ TEST Cloth IPD needed to select a cloth Item."})

	def test_grid_keeps_lot_and_process_read_checks(self):
		with patch("frappe.get_doc", return_value=cost_document()), patch("frappe.db", self.selection_database()), self.restrict_link_reads(("YRP Process",)):
			with self.assertRaises(frappe.PermissionError):
				workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Process")
		lot = cost_document()
		lot.check_permission.side_effect = frappe.PermissionError
		with patch("frappe.get_doc", return_value=lot):
			with self.assertRaises(frappe.PermissionError):
				workspace.get_process_cost_grid("ZZ TEST Lot", None)

	def test_cloth_selection_uses_work_order_options(self):
		options = [{"item": "ZZ TEST Cloth A"}, {"item": "ZZ TEST Cloth B"}]
		with patch(f"{MODULE}.frappe.get_doc", return_value=cost_document()), patch("frappe.db", Mock()) as database, patch(f"{MODULE}.get_work_order_selection_context", return_value={"options": options}), patch(f"{MODULE}._item_uom", return_value="Kg"):
			database.get_value.return_value = 1
			context = workspace._selection("ZZ TEST Lot", "ZZ TEST Dyeing", "ZZ TEST Cloth B")
		self.assertEqual(context["item_options"], options)
		self.assertEqual((context["item"], context["uom"]), ("ZZ TEST Cloth B", "Kg"))

	def test_save_refuses_a_non_listed_cloth_item(self):
		doc = cost_document()
		context = {"is_cloth_process": True, "item_options": [{"item": "ZZ TEST Cloth"}]}
		with patch(f"{MODULE}.get_process_cost_grid", return_value=context):
			with self.assertRaisesRegex(frappe.ValidationError, "Select a cloth Item configured for this Lot and Process"):
				workspace._apply_values(doc, {})

	def test_grid_resolves_value_labels_to_ids(self):
		master = frappe._dict(name="size-60", attribute_value="60 cm")
		with patch(f"{MODULE}._selection", return_value={"item": "ZZ TEST Item"}), patch(f"{MODULE}.process_cost.get_pc_attribute_values", return_value=[{"attribute_value": "60 cm"}]) as get_values, patch(f"{MODULE}.frappe.get_all", return_value=[master]) as get_all:
			grid = workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Stitching", attribute="Size")
		self.assertEqual(grid["attribute_values"], [{"name": "size-60", "label": "60 cm"}])
		get_values.assert_called_once_with("ZZ TEST Item", "Size", "ZZ TEST Lot", "ZZ TEST Stitching", for_link=0)
		get_all.assert_called_once_with(workspace.attribute_links.MASTER, filters={"attribute_name": "Size"},
			or_filters={"name": ["in", ["60 cm"]], "attribute_value": ["in", ["60 cm"]]},
			fields=["name", "attribute_value"])

	def test_tier_labels_preserve_values_and_handle_missing_links(self):
		rows = [frappe._dict(attribute_value=value, min_order_qty=index, price=12.5)
			for index, value in enumerate(("IAV-size-60", "60 cm", None, "IAV-missing", "IAV-size-60"))]
		with patch(f"{MODULE}.frappe.get_all", return_value=[frappe._dict(name="IAV-size-60", attribute_value="60 cm")]) as get_all:
			tiers = workspace._tiers(frappe._dict(process_cost_values=rows))
		self.assertEqual(tiers, [{**row, "attribute_value_label": label}
			for row, label in zip(rows, ("60 cm", "60 cm", "", "", "60 cm"), strict=True)])
		get_all.assert_called_once_with(workspace.attribute_links.MASTER,
			filters={"name": ["in", ["IAV-size-60", "IAV-missing"]]}, fields=["name", "attribute_value"])

	def test_grid_preserves_order_duplicates_and_missing_links(self):
		rows = [{"attribute_value": value} for value in ("Missing", "60 cm", "size-60", "60 cm", None)]
		with patch(f"{MODULE}._selection", return_value={"item": "ZZ TEST Item"}), \
			patch(f"{MODULE}.process_cost.get_pc_attribute_values", return_value=rows), \
			patch(f"{MODULE}.frappe.get_all", return_value=[frappe._dict(name="size-60", attribute_value="60 cm")]):
			grid = workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Stitching", attribute="Size")
		self.assertEqual(grid["attribute_values"], [
			{"name": "", "label": "Missing"}, {"name": "size-60", "label": "60 cm"},
			{"name": "size-60", "label": "size-60"}, {"name": "size-60", "label": "60 cm"},
			{"name": "", "label": ""}])

	def test_attribute_queries_do_not_grow_with_tier_count(self):
		workspace._tiers(frappe._dict(process_cost_values=[frappe._dict(attribute_value="IAV-ZZ TEST Tier-0")]))
		for count in (1, 7):
			rows = [frappe._dict(attribute_value=f"IAV-ZZ TEST Tier-{index}", min_order_qty=index, price=12.5)
				for index in range(count)]
			with self.subTest(count=count, source="tiers"), patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
				tiers = workspace._tiers(frappe._dict(process_cost_values=rows))
				self.assertEqual(len(tiers), count)
				self.assertEqual(sql.call_count, 1)
			with self.subTest(count=count, source="grid"), \
				patch(f"{MODULE}._selection", return_value={"item": "ZZ TEST Item"}), \
				patch(f"{MODULE}.process_cost.get_pc_attribute_values", return_value=rows), \
				patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
				grid = workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Stitching", attribute="ZZ TEST Size")
				self.assertEqual(len(grid["attribute_values"]), count)
				self.assertEqual(sql.call_count, 1)

	def test_empty_tiers_and_grid_do_not_query_attribute_values(self):
		with patch(f"{MODULE}.frappe.get_all") as get_all, \
			patch(f"{MODULE}._selection", return_value={"item": "ZZ TEST Item"}), \
			patch(f"{MODULE}.process_cost.get_pc_attribute_values", return_value=[]):
			self.assertEqual(workspace._tiers(frappe._dict(process_cost_values=[])), [])
			self.assertEqual(workspace.get_process_cost_grid("ZZ TEST Lot", "ZZ TEST Stitching", attribute="Size")["attribute_values"], [])
		get_all.assert_not_called()

	def test_approval_preview_matches_controller_production_group(self):
		doc = cost_document()
		with patch(f"{MODULE}.frappe.get_list", return_value=[]) as get_list, patch(f"{MODULE}.append_production_group_filters") as append:
			self.approval_matches(doc)
		get_list.assert_called_once_with(workspace.DOCTYPE, filters=get_list.call_args.kwargs["filters"],
			fields=["name", "from_date"], order_by="from_date asc")
		append.assert_called_once_with(get_list.call_args.kwargs["filters"], doc, workspace.DOCTYPE)
		for criterion in (["is_expired", "=", 0], ["supplier", "=", doc.supplier], ["workflow_state", "=", "Approved"]):
			self.assertIn(criterion, get_list.call_args.kwargs["filters"])

	def test_expired_documents_cannot_be_deleted(self):
		doc = cost_document("Expired", 2)
		with patch(f"{MODULE}._load_locked", return_value=doc), patch(f"{MODULE}.frappe.delete_doc") as delete:
			with self.assertRaises(frappe.PermissionError):
				workspace.delete_process_cost(doc.name, doc.modified)
		delete.assert_not_called()

	def test_saved_values_derive_item_and_preserve_workflow_owned_fields(self):
		doc = frappe._dict(attribute=None, is_expired=0, depends_on_attribute=1,
			workflow_state="Draft", approved_by=None)
		doc.set = lambda key, value: doc.update({key: value})
		values = {"lot": "ZZ TEST Lot", "process_name": "ZZ TEST Stitching", "item": "wrong",
			"supplier": "ZZ TEST Supplier", "from_date": "2099-01-01", "to_date": "2099-12-31",
			"tax_slab": "ZZ TEST Tax", "is_rework": 1, "uom": "wrong", "approved_by": "wrong",
			"is_expired": 1, "workflow_state": "Approved", "depends_on_attribute": 0,
			"process_cost_values": [{"min_order_qty": 0, "price": 12.5}]}
		context = {"item": "ZZ TEST Item", "uom": "Nos", "is_cloth_process": False, "attribute_values": []}
		with patch(f"{MODULE}.get_process_cost_grid", return_value=context), patch("frappe.db", Mock()) as database:
			database.get_value.side_effect = ["ZZ TEST Supplier Name", 1]
			workspace._apply_values(doc, values)
		self.assertEqual((doc.item, doc.uom, doc.supplier_name), ("ZZ TEST Item", "Nos", "ZZ TEST Supplier Name"))
		self.assertEqual(doc.process_cost_values, [{"attribute_value": None, "min_order_qty": 0.0, "price": 12.5}])
		self.assertEqual((doc.is_expired, doc.workflow_state, doc.approved_by, doc.depends_on_attribute), (0, "Draft", None, 1))
		self.assertEqual((doc.to_date, doc.is_rework, doc.supplier), ("2099-12-31", 1, "ZZ TEST Supplier"))
