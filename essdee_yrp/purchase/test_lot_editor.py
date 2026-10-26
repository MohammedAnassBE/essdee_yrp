import json
from contextlib import ExitStack, contextmanager
from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot as controller
from essdee_yrp.purchase import lot_editor as editor
from essdee_yrp.purchase import lot_workspace as workspace


def order_details_fixture():
	item = {
		"name": "Shirt", "attributes": {"Colour": "Blue", "Part": "Top"},
		"item_keys": {"major_colour": "Blue", "major_part": "Top"},
		"is_set_item": 1, "set_attr": "Part", "pack_attr": "Packing", "major_attr_value": "Top",
		"primary_attribute": "Size", "dependent_attribute": None, "dependent_attribute_details": [],
		"values": {"S": {"qty": 160.0}, "L": {"qty": 399.0}}, "total_qty": 559.0,
	}
	group = {
		"attributes": ["Colour", "Part"], "primary_attribute": "Size", "primary_attribute_values": ["S", "L"],
		"dependent_attribute": None, "dependent_attribute_details": [], "additional_parameters": [],
		"stiching_attribute": "Part", "items": [item, deepcopy(item)],
		"size_wise_total": {"S": 320.0, "L": 798.0}, "total_sum": 1118.0,
	}
	group["items"][1]["attributes"]["Colour"] = "Red"
	group["items"][1]["item_keys"]["major_colour"] = "Red"
	other = deepcopy(group)
	other["attributes"] = ["Colour"]
	for row in other["items"]:
		row["attributes"].pop("Part")
	return [group, other]


def browser_order_details(stored):
	return json.loads(json.dumps(stored), parse_float=lambda value: int(float(value)))


class TestLotEditor(TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.savepoint = "lot_editor_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(self.savepoint)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point=self.savepoint)
		frappe.set_user(self.previous_user)

	def live_lot(self):
		if not frappe.db.exists("SD YRP Lot", "C1225-03"):
			self.skipTest("Live Lot fixture C1225-03 is missing")
		return frappe.get_doc("SD YRP Lot", "C1225-03")

	@contextmanager
	def light_builders(self):
		with ExitStack() as stack:
			stack.enter_context(patch.object(controller, "fetch_fabric_program_details", return_value=[]))
			stack.enter_context(patch.object(controller, "rebuild_plans_after_save"))
			for method in ("get_order_items", "get_order_details", "get_bom", "get_ocr", "get_fabrics"):
				stack.enter_context(patch.object(workspace, method, return_value=None))
			yield

	def form_payload(self, doc):
		with self.light_builders():
			form = editor.get_lot_form(doc.name)
		values = deepcopy(form["values"])
		values["item_details"] = [form["item_details"]] if form["item_details"] else []
		values["order_item_details"] = form["order_item_details"]
		return values

	def save_values(self, doc, values):
		with self.light_builders():
			return editor.save_lot(values, name=doc.name, expected_modified=str(doc.modified))

	def quantities(self, doc):
		return {
			"boxes": sorted((row.item_variant, row.qty, row.ratio, row.mrp) for row in doc.items),
			"pieces": sorted((row.item_variant, row.quantity, row.cut_qty, row.stich_qty, row.pack_qty)
				for row in doc.lot_order_details),
			"totals": (doc.total_quantity, doc.total_order_quantity),
		}

	@contextmanager
	def stored_order_details(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.production_detail = "IPD"
		doc.append("lot_order_details", {"item_variant": "Stored variant", "quantity": 160.0})
		stored = order_details_fixture()
		with patch.object(editor, "fetch_order_item_details", return_value=stored) as fetch:
			yield doc, stored
			fetch.assert_called_with(doc.lot_order_details, "IPD")

	def test_permissions_require_create_for_new_and_write_for_existing(self):
		with patch.object(frappe, "has_permission", side_effect=frappe.PermissionError), self.assertRaises(frappe.PermissionError):
			editor.get_lot_form()
		doc = self.live_lot()
		with patch.object(type(doc), "check_permission", side_effect=frappe.PermissionError), self.assertRaises(frappe.PermissionError):
			editor.get_lot_form(doc.name)

	def test_all_role_can_edit_but_cannot_create(self):
		doc = self.live_lot()
		user = frappe.get_doc({"doctype": "User", "email": f"lot-editor-{frappe.generate_hash(length=8)}@example.test",
			"first_name": "Lot editor", "enabled": 1, "user_type": "System User", "send_welcome_email": 0,
			"roles": []}).insert(ignore_permissions=True)
		frappe.set_user(user.name)
		try:
			with self.assertRaises(frappe.PermissionError):
				editor.get_lot_form()
			# Isolate Lot permissions from Desk onload's Item read requirement.
			with self.light_builders(), patch.object(editor, "lot_onload",
				return_value={"item_details": [], "order_item_details": []}):
				form = editor.get_lot_form(doc.name)
			self.assertTrue(form["permissions"]["can_write"])
			self.assertFalse(form["permissions"]["can_create"])
		finally:
			frappe.set_user("Administrator")

	def test_context_helpers_require_lot_permission(self):
		with patch.object(frappe, "has_permission", return_value=False):
			with self.assertRaises(frappe.PermissionError):
				editor.get_lot_production_detail_context("IPD", "Item")
			with self.assertRaises(frappe.PermissionError):
				editor.get_lot_production_order_item("PPO")

	def test_locks_follow_stored_document(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.item = "Item"
		doc.production_order = ""
		locks = editor._lot_locks(doc, True, False)
		self.assertFalse(locks["production_order"])
		self.assertTrue(locks["item"])
		self.assertTrue(locks["lot_name"])
		locks = editor._lot_locks(doc, False, True)
		self.assertFalse(locks["production_order"])
		self.assertFalse(locks["item"])
		self.assertFalse(locks["lot_name"])
		doc.production_detail = "IPD"
		self.assertTrue(editor._lot_locks(doc, False, False)["production_order"])
		self.assertFalse(editor._lot_locks(doc, True, True)["production_order"])
		doc.is_transferred = 1
		self.assertTrue(editor._lot_locks(doc, True, False)["order_details"])

	def test_missing_and_stale_modified_are_rejected(self):
		doc = self.live_lot()
		for value, error in ((None, frappe.ValidationError), ("2000-01-01 00:00:00", frappe.TimestampMismatchError)):
			with self.subTest(value=value), self.assertRaises(error):
				editor.save_lot({}, name=doc.name, expected_modified=value)

	def test_locked_lot_name_is_rejected(self):
		doc = self.live_lot()
		values = self.form_payload(doc)
		values["lot_name"] = "Changed"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed here"):
			self.save_values(doc, values)

	def test_locked_item_is_rejected(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.item = "Stored"
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed here"):
			editor._reject_locked_changes(doc, {"item": "Changed"}, editor._lot_locks(doc, True, True))

	def test_production_order_is_editable_until_ipd_is_linked(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.item = "Item"
		values = {"production_order": "PPO-2"}
		editor._reject_locked_changes(doc, values, editor._lot_locks(doc, True, False))
		doc.production_detail = "IPD"
		with self.assertRaisesRegex(frappe.ValidationError, "after an IPD is linked"):
			editor._reject_locked_changes(doc, values, editor._lot_locks(doc, True, False))

	def test_ppo_item_is_verified_and_server_owned(self):
		doc = frappe.new_doc("SD YRP Lot")
		with patch.object(editor, "get_lot_production_order_item", return_value={"item": "PPO Item", "docstatus": 1}):
			values = {"production_order": "PPO", "item": "PPO Item"}
			editor._reject_locked_changes(doc, values, editor._lot_locks(doc, True, True))
			editor._apply_production_order(doc, values, True)
			self.assertEqual(doc.item, "PPO Item")
			with self.assertRaisesRegex(frappe.ValidationError, "must match"):
				editor._apply_production_order(doc, {"production_order": "PPO", "item": "Forged"}, True)

	def test_new_ppo_link_requires_submitted_production_order(self):
		doc = frappe.new_doc("SD YRP Lot")
		for docstatus in (0, 2):
			with patch.object(editor, "get_lot_production_order_item", return_value={"item": "PPO Item", "docstatus": docstatus}):
				with self.assertRaisesRegex(frappe.ValidationError, "submitted Production Order"):
					editor._apply_production_order(doc, {"production_order": "PPO", "item": "PPO Item"}, True)

	def test_existing_ppo_link_survives_later_cancellation(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.production_order = "PPO"
		with patch.object(editor, "get_lot_production_order_item", return_value={"item": "PPO Item", "docstatus": 2}):
			editor._apply_production_order(doc, {"production_order": "PPO", "item": "PPO Item"}, True)
		self.assertEqual(doc.item, "PPO Item")

	def test_unchanged_desk_payload_round_trip(self):
		doc = self.live_lot()
		before = self.quantities(doc)
		self.save_values(doc, self.form_payload(doc))
		doc.reload()
		self.assertEqual(self.quantities(doc), before)

	def test_piece_edit_keeps_other_stages(self):
		doc = self.live_lot()
		if editor._lot_locks(doc, bool(editor.check_enabled_po()), False)["order_details"]:
			self.skipTest("Piece fixture is locked by Time & Action or transfer")
		values = self.form_payload(doc)
		if not values["order_item_details"]:
			self.skipTest("No piece quantities in fixture")
		item = values["order_item_details"][0]["items"][0]
		size = next(iter(item["values"]))
		item["values"][size]["qty"] += 1
		before = self.quantities(doc)
		self.save_values(doc, values)
		doc.reload()
		after = self.quantities(doc)
		self.assertEqual(after["totals"][1], before["totals"][1] + 1)
		self.assertEqual([row[2:] for row in after["pieces"]], [row[2:] for row in before["pieces"]])
		self.assertEqual(sum(row[1] for row in after["pieces"]), sum(row[1] for row in before["pieces"]) + 1)

	def test_production_detail_changed_cleared_and_unchanged(self):
		doc = frappe.new_doc("SD YRP Lot")
		context = {key: f"Value {key}" for key in editor.IPD_DERIVED.values()}
		with patch.object(editor, "get_isfinal_uom", return_value=context) as get_context:
			doc.production_detail = "IPD"
			editor._apply_production_detail_defaults(doc, "Before")
			self.assertEqual({field: doc.get(field) for field in editor.IPD_DERIVED},
				{field: context[key] for field, key in editor.IPD_DERIVED.items()})
			get_context.reset_mock()
			editor._apply_production_detail_defaults(doc, "IPD")
			get_context.assert_not_called()
			doc.production_detail = ""
			editor._apply_production_detail_defaults(doc, "IPD")
			self.assertEqual({doc.get(field) for field in editor.IPD_DERIVED}, {""})

	def test_program_and_requirement_rows_are_unchanged(self):
		doc = self.live_lot()
		fields = ("lot_fabric_programs", "lot_fabric_requirements")
		before = {field: [row.as_dict() for row in doc.get(field)] for field in fields}
		self.save_values(doc, self.form_payload(doc))
		doc.reload()
		self.assertEqual({field: [row.as_dict() for row in doc.get(field)] for field in fields}, before)

	def test_fabric_rows_keep_stored_name_and_plan_status(self):
		doc = frappe.new_doc("SD YRP Lot")
		row = doc.append("lot_fabric_details", {"name": "stored-row", "cloth_item": "Cloth", "plan_status": "Built"})
		editor._apply_fabric_rows(doc, [{"name": row.name, "cloth_item": "Updated", "production_detail": "IPD", "plan_status": "Forged"}])
		self.assertEqual(doc.lot_fabric_details[0].name, "stored-row")
		self.assertEqual(doc.lot_fabric_details[0].plan_status, "Built")
		self.assertEqual(doc.lot_fabric_details[0].cloth_item, "Updated")

	def test_duplicate_cloth_uses_controller_validation(self):
		doc = frappe.new_doc("SD YRP Lot")
		editor._apply_fabric_rows(doc, [{"cloth_item": "Duplicate"}, {"cloth_item": "Duplicate"}])
		with self.assertRaisesRegex(frappe.ValidationError, "appears twice"), self.light_builders():
			doc.before_validate()

	def test_transient_keys_are_required(self):
		for field in ("item_details", "order_item_details", "lot_fabric_details"):
			values = {"item_details": [], "order_item_details": [], "lot_fabric_details": []}
			del values[field]
			with self.subTest(field=field), self.assertRaisesRegex(frappe.ValidationError, f"{field} is required"):
				editor.save_lot(values)

	def test_transient_tables_must_be_lists(self):
		for field in ("item_details", "order_item_details", "lot_fabric_details"):
			for invalid in (None, {}, "[]"):
				values = {"item_details": [], "order_item_details": [], "lot_fabric_details": []}
				values[field] = invalid
				with self.subTest(field=field, value=invalid), self.assertRaisesRegex(frappe.ValidationError, f"{field} must be a list"):
					editor.save_lot(values)

	def test_create_uses_controller_calculate_order(self):
		fixture = self.live_lot()
		values = self.form_payload(fixture)
		if not fixture.item or not fixture.production_detail or not values["item_details"]:
			self.skipTest("No Item/IPD/box fixture available")
		values.update(lot_name="WEB-LOT-" + frappe.generate_hash(length=8), production_order="", lot_fabric_details=[])
		values["item_details"][0]["items"] = values["item_details"][0]["items"][:1]
		values["order_item_details"] = []
		with patch.object(editor, "check_enabled_po", return_value=False), self.light_builders():
			result = editor.save_lot(values)
		doc = frappe.get_doc("SD YRP Lot", result["name"])
		self.assertTrue(doc.items)
		self.assertTrue(doc.lot_order_details)
		self.assertEqual(doc.total_order_quantity, sum(row.quantity for row in doc.lot_order_details))

	def test_duplicate_form_is_unsaved_copy_without_lot_name(self):
		source = self.live_lot()
		count = frappe.db.count("SD YRP Lot")
		with self.light_builders():
			form = editor.get_lot_form(duplicate_from=source.name)
			original = editor.get_lot_form(source.name)
		self.assertEqual(form["record"], {"name": "", "status": form["record"]["status"], "modified": None})
		self.assertFalse(form["values"]["lot_name"])
		for field in ("item", "production_detail", "production_order", "season"):
			self.assertEqual(form["values"][field], source.get(field))
		self.assertEqual(form["item_details"], original["item_details"])
		self.assertEqual(form["order_item_details"], original["order_item_details"])
		self.assertEqual(
			[row["cloth_item"] for row in form["values"]["lot_fabric_details"]],
			[row.cloth_item for row in source.lot_fabric_details],
		)
		self.assertTrue(all(not row["name"] for row in form["values"]["lot_fabric_details"]))
		self.assertFalse(form["locks"]["order_details"])
		self.assertEqual(frappe.db.count("SD YRP Lot"), count)

	def test_workspace_exposes_permissions(self):
		doc = self.live_lot()
		with self.light_builders():
			payload = workspace.get_lot_workspace(doc.name)
		self.assertEqual(payload["permissions"], {"can_write": True, "can_create": True})

	def test_locked_order_details_accept_browser_numbers_and_reject_qty_changes(self):
		with self.stored_order_details() as (doc, stored):
			incoming = browser_order_details(stored)
			self.assertIs(type(stored[0]["items"][0]["values"]["S"]["qty"]), float)
			self.assertIs(type(incoming[0]["items"][0]["values"]["S"]["qty"]), int)
			editor.reject_order_details_changes(doc, {"order_item_details": incoming}, True)
			incoming[0]["items"][0]["values"]["S"]["qty"] += 1
			with self.assertRaisesRegex(frappe.ValidationError, "Lot Order Details cannot be changed"):
				editor.reject_order_details_changes(doc, {"order_item_details": incoming}, True)

	def test_unlocked_order_details_allow_qty_and_derived_total_changes(self):
		with self.stored_order_details() as (doc, stored):
			incoming = browser_order_details(stored)
			incoming[0]["items"][0]["values"]["S"]["qty"] += 1
			incoming[0]["items"][0]["total_qty"] += 1
			incoming[0]["total_sum"] += 1
			incoming[0]["size_wise_total"]["S"] += 1
			editor.reject_order_details_changes(doc, {"order_item_details": incoming}, False)
			self.assertEqual(stored, order_details_fixture())

	def test_unlocked_order_details_allow_cleared_qty(self):
		with self.stored_order_details() as (doc, stored):
			incoming = browser_order_details(stored)
			incoming[0]["items"][0]["values"]["S"]["qty"] = None
			editor.reject_order_details_changes(doc, {"order_item_details": incoming}, False)
			self.assertEqual(stored, order_details_fixture())

	def test_locked_order_details_reject_cleared_qty(self):
		with self.stored_order_details() as (doc, stored):
			incoming = browser_order_details(stored)
			incoming[0]["items"][0]["values"]["S"]["qty"] = None
			with self.assertRaisesRegex(frappe.ValidationError, "Lot Order Details cannot be changed"):
				editor.reject_order_details_changes(doc, {"order_item_details": incoming}, True)

	def test_unlocked_order_details_reject_structure_changes(self):
		mutations = {
			"omit size": lambda groups: groups[0]["items"][0]["values"].pop("S"),
			"omit item": lambda groups: groups[0]["items"].pop(),
			"omit group": lambda groups: groups.pop(),
			"duplicate item": lambda groups: groups[0]["items"].append(deepcopy(groups[0]["items"][0])),
			"change item key": lambda groups: groups[0]["items"][0]["item_keys"].update(major_colour="Green"),
			"reorder groups": lambda groups: groups.reverse(),
			"reorder items": lambda groups: groups[0]["items"].reverse(),
			"change item": lambda groups: groups[0]["items"][0].update(name="Other item"),
			"change attribute": lambda groups: groups[0]["items"][0]["attributes"].update(Colour="Green"),
			"change primary attribute": lambda groups: groups[0]["items"][0].update(primary_attribute="Other size"),
		}
		with self.stored_order_details() as (doc, stored):
			for label, mutate in mutations.items():
				incoming = browser_order_details(stored)
				mutate(incoming)
				with self.subTest(change=label), self.assertRaisesRegex(frappe.ValidationError, "rows cannot be added, removed or re-keyed"):
					editor.reject_order_details_changes(doc, {"order_item_details": incoming}, False)

	def test_save_checks_order_details_before_applying_fields(self):
		with self.stored_order_details() as (doc, stored), ExitStack() as stack:
			stack.enter_context(patch.object(editor, "load_writable_lot", return_value=doc))
			stack.enter_context(patch.object(editor, "assert_expected_modified"))
			stack.enter_context(patch.object(editor, "check_enabled_po", return_value=False))
			stack.enter_context(patch.object(editor, "get_isfinal_uom", return_value={}))
			stack.enter_context(patch.object(editor, "get_lot_workspace", return_value={}))
			save = stack.enter_context(patch.object(doc, "save"))
			values = {"production_detail": "Changed IPD", "lot_fabric_details": [],
				"item_details": [], "order_item_details": browser_order_details(stored)}
			editor.save_lot(values, name="Existing", expected_modified="timestamp")
			save.assert_called_once()
			self.assertEqual(doc.production_detail, "Changed IPD")

	def test_empty_order_details_are_safe_even_when_locked(self):
		doc = frappe.new_doc("SD YRP Lot")
		with patch.object(editor, "fetch_order_item_details") as fetch:
			for locked in (True, False):
				editor.reject_order_details_changes(doc, {"order_item_details": []}, locked)
		fetch.assert_not_called()

	def test_nonempty_order_details_without_stored_rows_or_ipd_are_rejected(self):
		doc = frappe.new_doc("SD YRP Lot")
		with patch.object(editor, "fetch_order_item_details") as fetch:
			for ipd, rows in (("IPD", []), ("", [{"quantity": 1}])):
				doc.production_detail = ipd
				doc.set("lot_order_details", rows)
				with self.subTest(ipd=ipd), self.assertRaises(frappe.ValidationError):
					editor.reject_order_details_changes(doc, {"order_item_details": order_details_fixture()}, False)
		fetch.assert_not_called()

	def test_generated_item_details_flag(self):
		doc = frappe.new_doc("SD YRP Lot")
		doc.item, doc.production_detail = "Item", "IPD"
		details = {"item": "Item", "items": [{"values": {"S": {"qty": 1.0}}}]}
		with ExitStack() as stack:
			stack.enter_context(patch.object(editor, "load_writable_lot", return_value=doc))
			stack.enter_context(patch.object(editor, "check_enabled_po", return_value=True))
			stack.enter_context(patch.object(editor, "get_colour_attribute", return_value="Colour"))
			stack.enter_context(patch.object(editor, "permission_flags", return_value={}))
			onload = stack.enter_context(patch.object(editor, "lot_onload", return_value={}))
			fallback = stack.enter_context(patch.object(editor, "get_item_details", return_value=details))
			self.assertTrue(editor.get_lot_form("Existing")["item_details_generated"])
			self.assertFalse(editor.get_lot_form()["item_details_generated"])
			onload.return_value = {"item_details": details}
			fallback.reset_mock()
			self.assertFalse(editor.get_lot_form("Existing")["item_details_generated"])
			fallback.assert_not_called()
			onload.return_value = {}
			fallback.return_value = []
			self.assertFalse(editor.get_lot_form("Existing")["item_details_generated"])

	def test_production_detail_context_checks_ppo_read_permission(self):
		ppo = Mock()
		ppo.check_permission.side_effect = frappe.PermissionError
		with patch.object(frappe, "get_doc", return_value=ppo) as get_doc:
			with patch.object(editor, "get_isfinal_uom") as get_uom, self.assertRaises(frappe.PermissionError):
				editor.get_lot_production_detail_context("IPD", "Item", "PPO")
		get_doc.assert_called_once_with("YRP Production Order", "PPO")
		ppo.check_permission.assert_called_once_with("read")
		get_uom.assert_not_called()

	def test_context_reuses_desk_methods_and_passes_messages(self):
		ppo = Mock(item="Item")
		with patch.object(frappe, "get_doc", return_value=ppo), patch.object(editor, "get_isfinal_uom", return_value={"uom": "Box"}) as get_uom:
			with patch.object(editor, "get_item_details", return_value=[]) as get_items:
				payload = editor.get_lot_production_detail_context("IPD", "Item", "PPO")
		get_uom.assert_called_once_with("IPD", get_pack_stage=True)
		ppo.check_permission.assert_called_once_with("read")
		get_items.assert_called_once_with(item_name="Item", uom="Box", production_detail="IPD", dependent_attr_mapping=None, ppo="PPO")
		self.assertIsNone(payload["item_details"])
		self.assertEqual(payload["derived"]["uom"], "Box")
