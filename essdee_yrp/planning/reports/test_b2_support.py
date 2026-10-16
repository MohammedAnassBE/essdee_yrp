import frappe


class LiveReportChecks:
	def test_administrator_returns_columns(self):
		previous = frappe.session.user
		try:
			frappe.set_user("Administrator")
			filters = {}
			if self.report.__name__.endswith(("inward_quantity", "inhouse_quantity")):
				lots = frappe.get_all("SD YRP Lot", filters={"production_detail": ["is", "set"]}, fields=["name"], limit_page_length=1)
				process = frappe.db.get_value("YRP Process", {}, "name")
				if not lots or not process:
					self.skipTest("Requires a Lot with an IPD and a Process on the tester site.")
				filters = {"lot": lots[0].name, "process": process}
			elif self.report.__name__.endswith("month_wise_detail"):
				item = frappe.db.get_value("Item", {}, "name")
				if not item:
					self.skipTest("Requires an Item on the tester site.")
				filters = {"item": [item]}
			self.assertTrue(self.report.run(filters)["columns"])
		finally:
			frappe.set_user(previous)


	def test_user_without_access_is_denied(self):
		previous = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				self.report.run({})
		finally:
			frappe.set_user(previous)
