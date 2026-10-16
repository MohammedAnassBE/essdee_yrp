from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import ipd_ui, ipd_validations
from essdee_yrp.api import cloth_program
from essdee_yrp.api import test_cloth_program as fixtures
from essdee_yrp.cloth_program_access import has_cloth_program_role, require_cloth_program_role
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import SDYRPLot
from essdee_yrp.merch import lot_workspace
from essdee_yrp.merch.test_lot_workspace import get_lot

INSERT_MESSAGE = "Cloth IPDs are created by Lot → Build Cloth Program."
MERCH_ROLE = "ZZ TEST Cloth Merch"


def ensure_user(label, roles):
	email = f"zz.test.cloth.{label}@example.com"
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"ZZ TEST Cloth {label}",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)
	return email


class TestLotDeskClothProgram(TestCase):
	def test_print_url_uses_document_doctype(self):
		path = Path(frappe.get_app_path("essdee_yrp", "essdee_yrp", "doctype", "sd_yrp_lot"))
		source = (path / "sd_yrp_lot.js").read_text()
		self.assertIn("/printview?doctype=${encodeURIComponent(frm.doc.doctype)}", source)
		self.assertNotIn("/printview?doctype=Lot&", source)
		self.assertIn('encodeURIComponent("Essdee Lot Cloth Program")', source)


class TestClothProgramGuards(TestCase):
	def setUp(self):
		self.roles = self.enterContext(patch.object(frappe, "get_roles", return_value=["All"]))
		self.setting = self.enterContext(patch.object(frappe.db, "get_single_value", return_value=MERCH_ROLE))
		self.enterContext(patch.object(frappe, "throw", side_effect=self.throw))

	@staticmethod
	def throw(message, exception=frappe.ValidationError):
		raise exception(message)

	def test_role_gate_accepts_configured_role_and_system_manager(self):
		for roles in ([MERCH_ROLE], ["System Manager"]):
			with self.subTest(roles=roles):
				self.roles.return_value = roles
				self.assertTrue(has_cloth_program_role())
				require_cloth_program_role()

	def test_role_gate_rejects_unconfigured_and_unauthorized_users(self):
		self.assertFalse(has_cloth_program_role())
		with self.assertRaises(frappe.PermissionError):
			require_cloth_program_role()
		self.setting.return_value = ""
		with self.assertRaisesRegex(frappe.PermissionError, "Set Merch User Role in SD YRP MRP Settings"):
			require_cloth_program_role()
		self.roles.return_value = ["System Manager"]
		require_cloth_program_role()

	def test_both_commands_reject_before_demand_or_save(self):
		doc = get_lot()
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(cloth_program.attribute_db, "get_value"),
			patch.object(cloth_program, "compute_cloth_demand") as demand,
		):
			for command in (cloth_program.build_cloth_programs, cloth_program.recalculate_cloth_program):
				arguments = {"selections": []} if command == cloth_program.build_cloth_programs else {}
				with self.subTest(command=command.__name__), self.assertRaises(frappe.PermissionError):
					command(doc.name, **arguments)
			demand.assert_not_called()
			doc.save.assert_not_called()
			doc.check_permission.assert_called_with("write")

	def test_capabilities_hide_cloth_commands_without_role(self):
		with (
			patch.object(lot_workspace, "permission_flags", return_value={"can_write": True}),
			patch.object(lot_workspace.production_order_workflow, "user_can_manage_production_order", return_value=True),
			patch.object(lot_workspace, "get_command_blocks", return_value=dict.fromkeys(lot_workspace.COMMAND_LABELS, "")),
		):
			for roles, visible in ((["All"], False), ([MERCH_ROLE], True)):
				self.roles.return_value = roles
				capabilities = lot_workspace.get_lot_capabilities(get_lot())
				for command in ("build_cloth_programs", "recalculate_cloth_program"):
					self.assertEqual(capabilities[command]["visible"], visible)
					self.assertEqual(capabilities[command]["allowed"], visible)

	def test_insert_guard_rejects_client_flags_before_other_validation(self):
		doc = Mock()
		doc.get.side_effect = lambda field: field == "is_cloth_item"
		doc.is_new.return_value = True
		doc.flags.generated_cloth_ipd_insert = True
		with self.assertRaisesRegex(frappe.PermissionError, INSERT_MESSAGE):
			ipd_validations.before_validate(doc)

	def test_insert_guard_accepts_builder_and_restores_context(self):
		doc = Mock()
		doc.get.side_effect = lambda field: field == "is_cloth_item"
		doc.is_new.return_value = True
		with ipd_validations.allow_generated_cloth_ipd_insert():
			ipd_validations.validate_cloth_ipd_insert(doc)
		self.assertFalse(frappe.flags.get("generated_cloth_ipd_insert"))
		with self.assertRaisesRegex(frappe.PermissionError, INSERT_MESSAGE):
			ipd_validations.validate_cloth_ipd_insert(doc)

	def test_insert_guard_leaves_garments_and_existing_cloth_unaffected(self):
		doc = Mock()
		doc.is_new.return_value = False
		ipd_validations.validate_cloth_ipd_insert(doc)
		doc.is_new.return_value = True
		doc.get.return_value = None
		ipd_validations.validate_cloth_ipd_insert(doc)


class TestClothProgramAccess(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", MERCH_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": MERCH_ROLE}).insert(ignore_permissions=True)
		self.users = {
			"other": ensure_user("other", []),
			"merch": ensure_user("merch", [MERCH_ROLE]),
			"manager": ensure_user("manager", ["System Manager"]),
		}
		self.merch_role = MERCH_ROLE
		original = frappe.db.get_single_value
		self.setting = patch.object(
			frappe.db, "get_single_value",
			side_effect=lambda doctype, field, *args, **kwargs: self.merch_role
			if (doctype, field) == ("SD YRP MRP Settings", "merch_user_role")
			else original(doctype, field, *args, **kwargs),
		)
		self.setting.start()
		self.addCleanup(self.setting.stop)
		self.suffix = frappe.generate_hash(length=6)
		self.lot = frappe.get_doc({
			"doctype": "SD YRP Lot", "lot_name": f"ZZ TEST Cloth Access {self.suffix}",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def prepare_program(self):
		dia = fixtures._ensure_iav("Dia", "ZZ TEST Cloth Access Dia")
		colour = fixtures._ensure_iav("Colour", "ZZ TEST Cloth Access Colour")
		self.cloth = fixtures._ensure_attributed_item(f"ZZ TEST Cloth Access {self.suffix}", ["Dia", "Colour"])
		frappe.db.set_value("Item", self.cloth, {"is_cloth_item": 1, "has_variants": 1})
		frappe.clear_document_cache("Item", self.cloth)
		self.selection = {
			"cloth_item": self.cloth,
			"yarn_item": fixtures._ensure_item("ZZ TEST Cloth Access Yarn"),
			"knitting_process": fixtures._ensure_process("ZZ TEST Cloth Access Knit", is_item_conversion=1),
			"dyeing_process": None,
			"compacting_process": None,
			"cloth_per_kg_yarn": 1,
			"greige_colour": colour,
		}
		self.demand = {(self.cloth, dia, colour): 10}
		self.tuples = {(dia, colour): 10}

	def build(self):
		with patch.object(cloth_program, "compute_cloth_demand", return_value=self.demand):
			return cloth_program.build_cloth_programs(self.lot.name, [self.selection])

	def test_build_and_recalculate_reject_non_merch_before_writes(self):
		before = self.lot.as_json()
		count = frappe.db.count("YRP Item Production Detail")
		frappe.set_user(self.users["other"])
		self.lot.check_permission("write")
		for command in (cloth_program.build_cloth_programs, cloth_program.recalculate_cloth_program):
			arguments = {"selections": []} if command == cloth_program.build_cloth_programs else {}
			with self.subTest(command=command.__name__), patch.object(
				cloth_program, "compute_cloth_demand"
			) as demand:
				with self.assertRaises(frappe.PermissionError):
					command(self.lot.name, **arguments)
				demand.assert_not_called()
		self.assertEqual(self.lot.reload().as_json(), before)
		self.assertEqual(frappe.db.count("YRP Item Production Detail"), count)

	def test_merch_and_system_manager_can_build_and_recalculate(self):
		self.prepare_program()
		for user in ("merch", "manager"):
			with self.subTest(user=user):
				frappe.set_user(self.users[user])
				self.assertEqual(self.build()["cloths_built"], 1)
				with patch.object(cloth_program, "compute_cloth_demand", return_value=self.demand):
					cloth_program.recalculate_cloth_program(self.lot.name)
				self.assertEqual(self.lot.reload().lot_fabric_details[0].plan_status, "Built")

	def test_blank_merch_setting_allows_only_system_manager(self):
		self.prepare_program()
		self.merch_role = ""
		for user in ("other", "merch"):
			frappe.set_user(self.users[user])
			self.assertFalse(has_cloth_program_role())
			with self.assertRaisesRegex(frappe.PermissionError, "Set Merch User Role in SD YRP MRP Settings"):
				self.build()
			with self.assertRaisesRegex(frappe.PermissionError, "Set Merch User Role in SD YRP MRP Settings"):
				cloth_program.recalculate_cloth_program(self.lot.name)
		frappe.set_user(self.users["manager"])
		self.assertEqual(self.build()["cloths_built"], 1)
		with patch.object(cloth_program, "compute_cloth_demand", return_value=self.demand):
			cloth_program.recalculate_cloth_program(self.lot.name)

	def test_lot_write_is_required_even_for_merch(self):
		frappe.set_user(self.users["merch"])
		with patch.object(SDYRPLot, "check_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				cloth_program.build_cloth_programs(self.lot.name, [])
			with self.assertRaises(frappe.PermissionError):
				cloth_program.recalculate_cloth_program(self.lot.name)

	def test_capabilities_and_desk_onload_follow_role(self):
		for user, visible in (("other", False), ("merch", True), ("manager", True)):
			with self.subTest(user=user):
				frappe.set_user(self.users[user])
				with patch.object(lot_workspace, "get_command_blocks", return_value=dict.fromkeys(
					lot_workspace.COMMAND_LABELS, ""
				)):
					capabilities = lot_workspace.get_lot_capabilities(self.lot)
				for command in ("build_cloth_programs", "recalculate_cloth_program"):
					self.assertEqual(capabilities[command]["visible"], visible)
					self.assertEqual(capabilities[command]["allowed"], visible)
				self.lot.onload()
				self.assertEqual(self.lot.get_onload("can_manage_cloth_program"), visible)

	def test_manual_cloth_insert_rejects_item_flag_and_client_flags(self):
		self.prepare_program()
		count = frappe.db.count("YRP Item Production Detail")
		for cloth_flag in (0, 1):
			doc = frappe.get_doc({
				"doctype": "YRP Item Production Detail", "item": self.cloth, "is_cloth_item": cloth_flag,
				"generated_cloth_ipd_insert": True,
			})
			doc.flags.generated_cloth_ipd_insert = True
			with self.assertRaisesRegex(frappe.PermissionError, INSERT_MESSAGE):
				doc.insert(ignore_permissions=True)
		self.assertEqual(frappe.db.count("YRP Item Production Detail"), count)

	def test_client_insert_and_duplicate_are_rejected(self):
		from frappe.client import insert

		self.prepare_program()
		name = cloth_program._find_or_create_cpd(self.cloth, self.selection, self.tuples)
		count = frappe.db.count("YRP Item Production Detail")
		with self.assertRaisesRegex(frappe.PermissionError, INSERT_MESSAGE):
			insert({"doctype": "YRP Item Production Detail", "item": self.cloth})
		with self.assertRaisesRegex(frappe.PermissionError, INSERT_MESSAGE):
			ipd_ui.duplicate_ipd(name)
		self.assertEqual(frappe.db.count("YRP Item Production Detail"), count)

	def test_builder_creates_new_versions_and_retains_approved_lock(self):
		self.prepare_program()
		first = cloth_program._find_or_create_cpd(self.cloth, self.selection, self.tuples)
		self.selection["cloth_per_kg_yarn"] = 2
		second = cloth_program._find_or_create_cpd(self.cloth, self.selection, self.tuples)
		self.assertNotEqual(first, second)
		doc = frappe.get_doc("YRP Item Production Detail", second)
		self.assertEqual(doc.approval_status, "Approved")
		self.assertFalse(frappe.flags.get("generated_cloth_ipd_insert"))
		with self.assertRaisesRegex(frappe.ValidationError, "Revert Approval before editing"):
			doc.save(ignore_permissions=True)

	def test_insert_context_restores_flags_after_failure(self):
		previous = frappe.flags.get("generated_cloth_ipd_insert")
		with self.assertRaisesRegex(ValueError, "ZZ TEST"):
			with ipd_validations.allow_generated_cloth_ipd_insert():
				with ipd_validations.allow_generated_cloth_ipd_insert():
					self.assertTrue(frappe.flags.generated_cloth_ipd_insert)
				self.assertTrue(frappe.flags.generated_cloth_ipd_insert)
				raise ValueError("ZZ TEST")
		self.assertEqual(frappe.flags.get("generated_cloth_ipd_insert"), previous)

	def test_migration_flags_allow_cloth_insert_validation(self):
		self.prepare_program()
		doc = frappe.get_doc({"doctype": "YRP Item Production Detail", "item": self.cloth})
		for flag in ("in_patch", "in_migrate", "in_install"):
			with self.subTest(flag=flag), patch.dict(frappe.flags, {flag: True}):
				ipd_validations.validate_cloth_ipd_insert(doc)

	def insert_garment(self):
		item = fixtures._ensure_item("ZZ TEST Cloth Access Garment")
		doc = frappe.get_doc({
			"doctype": "YRP Item Production Detail", "item": item,
			"based_on_other_attribute_mapping": 1, "packing_mode": "Size Wise Packing",
		})
		doc.flags.skip_ipd_settings_defaults = True
		return doc.insert(ignore_permissions=True)

	def test_garment_insert_is_unaffected(self):
		doc = self.insert_garment()
		self.assertTrue(frappe.db.exists(doc.doctype, doc.name))
		self.assertFalse(ipd_validations.is_cloth_ipd(doc))

	def test_approval_and_revert_work_for_existing_garment_and_cloth(self):
		self.prepare_program()
		cloth = cloth_program._find_or_create_cpd(self.cloth, self.selection, self.tuples)
		garment = self.insert_garment().name
		frappe.set_user(self.users["manager"])
		for name in (cloth, garment):
			with self.subTest(name=name):
				self.assertEqual(ipd_ui.revert_ipd_approval(name), {"status": "success"})
				self.assertEqual(ipd_ui.approve_ipd(name), {"status": "success"})
				self.assertEqual(frappe.db.get_value("YRP Item Production Detail", name, "approval_status"), "Approved")
				self.assertEqual(ipd_ui.revert_ipd_approval(name), {"status": "success"})

	def test_merch_build_role_does_not_grant_approval(self):
		frappe.set_user(self.users["merch"])
		for command in (ipd_ui.approve_ipd, ipd_ui.revert_ipd_approval):
			with self.subTest(command=command.__name__), self.assertRaises(frappe.PermissionError):
				command("ZZ TEST Missing IPD")
