import frappe


def production_fixture():
	detail = {"name": "D", "primary_item_attribute": "Size", "stiching_in_stage": "Panels", "stiching_process": "Sew", "cutting_process": "Cut", "is_set_item": 0}
	orders = [{"name": name, "lot": "L", "process_name": process, "supplier": "S", "supplier_name": "Unit", "first_dc_date": date, "last_grn_date": date} for name, process, date in (("C", "Cut", "2026-10-01"), ("S1", "Sew", "2026-10-02"), ("S2", "Sew", "2026-10-03"), ("P1", "Print", "2026-10-04"), ("P2", "Wash", "2026-10-05"))]
	items = [{"parent": parent, "item_variant": "V", "set_combination": '{"major_colour":"Red"}', "delivered_quantity": sent, "received_qty": received, "received_type_json": '{"Accepted":20}'} for parent, sent, received in (("C", 100, 90), ("S1", 40, 30), ("S2", 30, 20), ("P1", 70, 60), ("P2", 40, 35))]
	return {"lots": [{"name": "L", "item": "Style", "production_detail": "D"}], "details": {"D": detail}, "orders": orders, "items": items, "attributes": {"V": {"Size": "M"}}, "order_rows": [{"parent": "L", "item_variant": "V", "quantity": 100, "cut_qty": 90, "set_combination": '{"major_colour":"Red"}'}], "expanded": {name: [name] for name in ("Cut", "Sew", "Print", "Wash")}, "stages": [{"parent": "D", "process_name": "Print", "in_stage": "Panels", "out_stage": "Pieces"}, {"parent": "D", "process_name": "Wash", "in_stage": "Pieces", "out_stage": "Panels"}]}


def finishing_fixture():
	return {"plans": {"FP": {"name": "FP", "lot": "L", "pieces_per_box": 5}}, "parts": {"D": 2}, "dispatches": [{"parent": "FP", "item_variant": "V", "dispatched": 3}], "inwards": [{"parent": "FP", "item_variant": "V", "transferred_qty": 7, "dc_qty": 45}]}


class LiveProductionChecks:
	def test_report_registration_and_dependencies(self):
		from yrp.web_reports.registry import clear_web_report_cache, get_web_report

		clear_web_report_cache()
		key = "planning-" + self.report.__name__.rsplit(".", 1)[-1].replace("_", "-")
		entry = get_web_report(key)
		self.assertEqual(entry.kind, "callable")
		self.assertTrue(entry.permission_doctypes)
		if key == "planning-work-in-progress":
			for field, value in {"days": 31, "from_field": "from_date", "to_field": "to_date", "missing_bound": "background"}.items():
				self.assertEqual(entry.background[field], value)
		else:
			self.assertEqual(entry.background, "never")
		for doctype in self.report.dependency_doctypes():
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)

	def test_run_returns_columns(self):
		previous = frappe.session.user
		try:
			frappe.set_user("Administrator")
			lots = frappe.get_all("SD YRP Lot", filters={"production_detail": ["is", "set"]}, fields=["name", "status"], limit_page_length=1)
			if not lots:
				self.skipTest("Requires a Lot with an IPD on the tester site.")
			filters = {"lot": lots[0].name} if self.report.__name__.endswith("colour_wise_diff") else {"lot": [lots[0].name], "lot_status": lots[0].status}
			self.assertTrue(self.report.run(filters)["columns"])
		finally:
			frappe.set_user(previous)

	def test_denied_user(self):
		previous = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				self.report.run({})
		finally:
			frappe.set_user(previous)
