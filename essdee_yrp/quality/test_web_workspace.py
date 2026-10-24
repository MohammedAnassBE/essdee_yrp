import frappe
from frappe.desk.query_report import run as run_desk_report
from frappe.tests import IntegrationTestCase
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache

from essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection import (
	create_inspection_debit,
	get_debit_details,
)
from essdee_yrp.quality.web_workspace import (
	COMBINED_SECTIONS,
	get_capabilities,
	get_inspection_workspace,
	get_new_inspection_defaults,
	save_inspection,
	update_inspection_result,
)

DOCTYPE = "SD YRP Essdee Quality Inspection"
QA_USER = "quality-web-test@example.com"


class TestQualityWebWorkspace(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.source = frappe.db.get_value(
			DOCTYPE,
			{"docstatus": 1, "name": ["like", "EQI-2627-%"], "major_aql_level": ["is", "set"]},
			["name", "against_id", "major_aql_level", "minor_aql_level"],
			as_dict=True,
			order_by="creation desc",
		)

	def setUp(self):
		frappe.set_user("Administrator")
		if not self.source:
			self.skipTest("Quality workspace tests run after source data migration")

	def tearDown(self):
		frappe.set_user("Administrator")

	def new_draft(self, **values):
		defaults = get_new_inspection_defaults(against_id=self.source.against_id)
		details = defaults["against_details"]
		selection = {
			"colours": [{**details["colours"][0], "selected": 1}],
			"sizes": [{**row, "selected": 1} for row in details["sizes"]],
		}
		payload = {
			"against_id": self.source.against_id,
			"inspection_type": "Final",
			"offer_qty": 300,
			"checking_level": "Level 2",
			"major_aql_level": self.source.major_aql_level,
			"minor_aql_level": self.source.minor_aql_level,
			"colour_and_size_data": selection,
			**values,
		}
		return save_inspection(payload)

	def test_capabilities_list_quality_sections(self):
		capabilities = get_capabilities()
		for section in ("inspections", "work_orders", "reports"):
			self.assertTrue(capabilities["sections"][section]["can_read"], section)
		self.assertIn("quality_inspection_rft", capabilities["reports"])

	def test_brand_qa_user_reads_the_combined_cards_and_lot_cut_quantity(self):
		frappe.set_user(_qa_user().name)
		capabilities = get_capabilities()
		for section in COMBINED_SECTIONS:
			self.assertTrue(capabilities["sections"][section]["can_read"], section)
			self.assertFalse(capabilities["sections"][section]["can_create"], section)
		self.assertTrue(capabilities["reports"]["lot_cut_quantity"]["can_read"])
		for doctype in ("Item", "SD YRP Sewing Plan Entry Detail", "SD YRP Product Release"):
			self.assertTrue(frappe.has_permission(doctype, "read"), f"{doctype} renders the card pages")
		read_only = ("SD YRP Cutting Plan", "SD YRP Finishing Plan", "YRP Process Cost", "SD YRP Product")
		for doctype in (*read_only, "SD YRP Lotwise Item Profit"):
			for ptype in ("write", "create", "submit", "cancel", "delete"):
				self.assertFalse(frappe.has_permission(doctype, ptype), f"{doctype} {ptype}")

	def test_brand_qa_manager_cancels_inspections_and_debits(self):
		frappe.set_user(_qa_user(role="Brand QA Manager").name)
		for doctype in (DOCTYPE, "YRP Debit"):
			self.assertTrue(frappe.has_permission(doctype, "cancel"), doctype)
		self.assertFalse(frappe.has_permission("YRP Debit", "create"))
		self.assertTrue(get_capabilities()["sections"]["lotwise_item_profits"]["can_read"])

	def test_rft_web_report_matches_desk(self):
		clear_web_report_cache()
		lot = frappe.db.get_value(DOCTYPE, self.source.name, "lot")
		filters = {"lot": lot, "result": "Pass"}
		desk = run_desk_report("SD YRP Qualily Inspection RFT", filters=filters, ignore_prepared_report=True)
		web = run_web_report("quality-inspection-rft", filters)
		self.assertTrue(desk["result"])
		self.assertEqual(web["columns"], desk["columns"])
		self.assertEqual(web["result"], desk["result"])

	def test_defaults_from_grn_resolve_its_work_order(self):
		grn = frappe.db.get_value(
			"YRP Goods Received Note",
			{"against": "YRP Work Order", "against_id": self.source.against_id},
			"name",
		)
		if not grn:
			self.skipTest("No GRN against the inspected Work Order")
		defaults = get_new_inspection_defaults(grn=grn)
		self.assertEqual(defaults["against_id"], self.source.against_id)
		self.assertTrue(defaults["against_details"]["colours"])

	def test_save_derives_source_fields_from_work_order(self):
		work_order = frappe.get_doc("YRP Work Order", self.source.against_id)
		workspace = self.new_draft(item="Tampered Item")
		record = workspace["record"]
		self.assertEqual(record["docstatus"], 0)
		self.assertEqual((record["item"], record["lot"], record["supplier"]), (work_order.item, work_order.lot, work_order.supplier))
		self.assertEqual(record["supplier_name"], frappe.db.get_value("Supplier", work_order.supplier, "supplier_name"))
		self.assertGreater(record["sample_piece_count"], 0)
		self.assertTrue(workspace["actions"]["submit"]["allowed"])

	def test_save_rejects_colours_the_work_order_did_not_deliver(self):
		with self.assertRaises(frappe.ValidationError):
			self.new_draft(colour_and_size_data={"colours": [{"colour": "No Such Colour", "selected": 1}], "sizes": []})

	def test_manual_result_override_is_kept_like_production(self):
		record = self.new_draft(major_defect_found=0, minor_defect_found=0)["record"]
		self.assertEqual((record["result"], record["calculated_result"]), ("Pass", "Pass"))
		record = save_inspection({"result": "Fail"}, record["name"], str(record["modified"]))["record"]
		self.assertEqual((record["result"], record["calculated_result"]), ("Fail", "Pass"))
		record = save_inspection({"major_defect_found": 0}, record["name"], str(record["modified"]))["record"]
		self.assertEqual((record["result"], record["calculated_result"]), ("Fail", "Pass"))

	def test_hold_result_can_be_updated_after_submit(self):
		record = self.new_draft(result="Hold")["record"]
		doc = frappe.get_doc(DOCTYPE, record["name"])
		doc.submit()
		workspace = get_inspection_workspace(doc.name)
		self.assertTrue(workspace["actions"]["update_status"]["allowed"])
		record = update_inspection_result(doc.name, "Pass", str(workspace["record"]["modified"]))["record"]
		self.assertEqual((record["docstatus"], record["result"]), (1, "Pass"))
		with self.assertRaises(frappe.ValidationError):
			update_inspection_result(doc.name, "Fail", str(record["modified"]))

	def test_cancelled_inspection_amends_with_its_selection(self):
		record = self.new_draft(description="amend source")["record"]
		doc = frappe.get_doc(DOCTYPE, record["name"])
		doc.submit()
		doc.cancel()
		defaults = get_new_inspection_defaults(amend_from=doc.name)
		self.assertEqual(defaults["amended_from"], doc.name)
		selected = [row["colour"] for row in defaults["against_details"]["colours"] if row["selected"]]
		self.assertEqual(selected, [row.colour for row in doc.essdee_quality_inspection_colours if row.selected])
		selection = {key: defaults["against_details"][key] for key in ("colours", "sizes")}
		values = {key: defaults[key] for key in ("against_id", "inspection_type", "offer_qty", "checking_level", "major_aql_level", "minor_aql_level", "result")}
		self.assertEqual(defaults["result"], "Pass")
		amended = save_inspection(
			{**values, "amended_from": doc.name, "colour_and_size_data": selection, "major_defect_found": 99}
		)["record"]
		self.assertEqual((amended["amended_from"], amended["description"]), (doc.name, None))
		self.assertEqual((amended["result"], amended["calculated_result"]), ("Fail", "Fail"))
		self.assertTrue(amended["name"].startswith(doc.name))

	def test_duplicate_defaults_copy_a_submitted_inspection_without_saving(self):
		record = self.new_draft(description="duplicate source")["record"]
		doc = frappe.get_doc(DOCTYPE, record["name"])
		doc.submit()
		count = frappe.db.count(DOCTYPE)
		defaults = get_new_inspection_defaults(duplicate_from=doc.name)
		self.assertEqual(frappe.db.count(DOCTYPE), count)
		self.assertNotIn("amended_from", defaults)
		self.assertNotIn("name", defaults)
		self.assertEqual((defaults["description"], defaults["offer_qty"]), ("duplicate source", doc.offer_qty))
		selected = [row["colour"] for row in defaults["against_details"]["colours"] if row["selected"]]
		self.assertEqual(selected, [row.colour for row in doc.essdee_quality_inspection_colours if row.selected])
		values = {key: defaults[key] for key in ("against_id", "inspection_type", "offer_qty", "checking_level", "major_aql_level", "minor_aql_level")}
		selection = {key: defaults["against_details"][key] for key in ("colours", "sizes")}
		copy = save_inspection({**values, "colour_and_size_data": selection})["record"]
		self.assertNotEqual(copy["name"], doc.name)
		self.assertEqual((copy["docstatus"], copy["amended_from"]), (0, None))
		self.assertEqual(frappe.db.get_value(DOCTYPE, doc.name, "docstatus"), 1)

	def test_amended_manual_override_keeps_both_result_fields(self):
		record = self.new_draft(result="Hold")["record"]
		doc = frappe.get_doc(DOCTYPE, record["name"])
		doc.submit()
		doc.cancel()
		defaults = get_new_inspection_defaults(amend_from=doc.name)
		selection = {key: defaults["against_details"][key] for key in ("colours", "sizes")}
		values = {key: defaults[key] for key in ("against_id", "inspection_type", "offer_qty", "checking_level", "major_aql_level", "minor_aql_level", "result")}
		amended = save_inspection({**values, "amended_from": doc.name, "colour_and_size_data": selection})["record"]
		self.assertEqual((amended["result"], amended["calculated_result"]), ("Hold", doc.calculated_result))

	def test_uploaded_file_is_attached_to_the_saved_inspection(self):
		file = frappe.get_doc({"doctype": "File", "file_name": "qa-web-test.txt", "content": b"qa", "is_private": 0}).insert()
		record = self.new_draft(upload_quality_approval_sheet=file.file_url)["record"]
		attached = frappe.db.get_value("File", file.name, ["attached_to_doctype", "attached_to_name", "attached_to_field"])
		self.assertEqual(attached, (DOCTYPE, record["name"], "upload_quality_approval_sheet"))

	def test_brand_qa_user_creates_and_sees_inspection_debit(self):
		user = _qa_user()
		frappe.set_user(user.name)
		self.assertTrue(get_inspection_workspace(self.source.name)["actions"]["create_debit"]["allowed"])
		result = create_inspection_debit(
			quality_inspection=self.source.name,
			debit_value=75,
			reason="Quality web test",
			debit_document="/files/quality-web-test.jpg",
		)
		debits = get_debit_details(self.source.name)
		self.assertIn(result["name"], [row.name for row in debits])
		frappe.set_user("Administrator")
		debit = frappe.get_doc("YRP Debit", result["name"])
		self.assertEqual((debit.docstatus, debit.work_order, debit.inspection), (1, self.source.against_id, 1))
		self.assertEqual(debit.quality_inspection, self.source.name)

	def test_only_production_debit_roles_can_create_inspection_debit(self):
		for role in ("Brand QA Manager", "Stock User"):
			frappe.set_user("Administrator")
			user = _qa_user(role=role)
			frappe.set_user(user.name)
			with self.assertRaises(frappe.PermissionError, msg=role):
				create_inspection_debit(self.source.name, 75, "Quality web test", "/files/quality-web-test.jpg")

def _qa_user(role="Brand QA User"):
	if frappe.db.exists("User", QA_USER):
		user = frappe.get_doc("User", QA_USER)
		user.set("roles", [])
	else:
		user = frappe.get_doc({"doctype": "User", "email": QA_USER, "first_name": "Quality Web", "send_welcome_email": 0})
	user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return user
