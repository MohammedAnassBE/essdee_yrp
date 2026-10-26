import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.purchase_audit_report.purchase_audit_report import execute

DATE = "2099-03-10"
NEXT_DATE = "2099-03-20"


class TestPurchaseAuditReport(IntegrationTestCase):
	def setUp(self):
		self.key = frappe.generate_hash(length=8)
		self.supplier = self.make_supplier("Audit Maker")
		self.warehouse = self.make_warehouse("Audit Store", self.supplier)
		self.template = self.make_item("T", template=True)
		self.variant = self.make_item("V", parent=self.template)

	def make_supplier(self, name):
		return frappe.get_doc({"doctype": "Supplier", "supplier_name": f"{name} {self.key}"}).insert().name

	def make_warehouse(self, name, supplier=None):
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		doc = {"doctype": "Warehouse", "warehouse_name": f"{name} {self.key}", "company": company}
		return frappe.get_doc({**doc, "supplier": supplier}).insert(ignore_permissions=True).name

	def make_item(self, code, parent=None, template=False):
		name = f"AUD-{self.key}-{code}"
		frappe.get_doc(
			{
				"doctype": "Item",
				"name": name,
				"item_code": name,
				"item_name": name,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}, "name"),
				"stock_uom": "Nos",
				"has_variants": int(template),
				"variant_of": parent,
			}
		).db_insert()
		return name

	def make_voucher(self, doctype, **fields):
		doc = frappe.get_doc({"doctype": doctype, "name": f"AUD-{frappe.generate_hash(length=10)}"})
		doc.update({"docstatus": 1, "posting_date": DATE, **fields})
		doc.db_insert()
		return doc

	def add_entry(self, voucher, qty, date=DATE, warehouse=None, item=None, time="10:00:00"):
		frappe.get_doc(
			{
				"doctype": "YRP Stock Ledger Entry",
				"item": item or self.variant,
				"warehouse": warehouse or self.warehouse,
				"posting_date": date,
				"posting_time": time,
				"posting_datetime": f"{date} 10:00:00",
				"qty": qty,
				"voucher_type": voucher.doctype,
				"voucher_no": voucher.name,
				"lot": None,
				"received_type": None,
				"is_cancelled": 0,
				"docstatus": 1,
			}
		).db_insert()

	def run_report(self, **filters):
		base = {"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse}
		return execute({**base, **filters})[1]

	def make_all_movements(self):
		grn = self.make_voucher(
			"YRP Goods Received Note", against="Purchase Order", supplier=self.supplier, is_return=0
		)
		wo_grn = self.make_voucher(
			"YRP Goods Received Note", against="YRP Work Order", supplier=self.supplier
		)
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		send = self.make_voucher("YRP Stock Entry", purpose="Send to Warehouse")
		receive = self.make_voucher("YRP Stock Entry", purpose="Receive at Warehouse")
		add = self.make_voucher("YRP Stock Update", update_type="Add")
		reduce = self.make_voucher("YRP Stock Update", update_type="Reduce")
		dc = self.make_voucher("YRP Delivery Challan", supplier=self.supplier)
		conversion = self.make_voucher("SD YRP Item Conversion")
		movements = [
			(grn, 100),
			(wo_grn, 7),
			(receipt, 20),
			(issue, -5),
			(send, -8),
			(receive, 9),
			(add, 3),
			(reduce, -2),
			(dc, -30),
			(conversion, 4),
			(conversion, -6),
		]
		for voucher, qty in movements:
			self.add_entry(voucher, qty)
		return {voucher.name: voucher for voucher, _qty in movements}

	def test_each_voucher_lands_in_its_column(self):
		vouchers = self.make_all_movements()
		rows = [row for row in self.run_report() if row.get("against_id")]
		by_voucher = {row["against_id"]: row for row in rows}
		expected = {
			"YRP Goods Received Note:Purchase Order": ("po_grn", 100),
			"YRP Goods Received Note:YRP Work Order": ("other_inward", 7),
			"YRP Stock Entry:Material Receipt": ("se_material_receipt", 20),
			"YRP Stock Entry:Material Issue": ("se_material_issue", -5),
			"YRP Stock Entry:Send to Warehouse": ("sent_warehouse", -8),
			"YRP Stock Entry:Receive at Warehouse": ("received_warehouse", 9),
			"YRP Stock Update:Add": ("added_stock", 3),
			"YRP Stock Update:Reduce": ("reduced_stock", -2),
			"YRP Delivery Challan:": ("dc_qty", -30),
		}
		for name, voucher in vouchers.items():
			if voucher.doctype == "SD YRP Item Conversion":
				continue
			kind = voucher.get("against") or voucher.get("purpose") or voucher.get("update_type") or ""
			column, qty = expected[f"{voucher.doctype}:{kind}"]
			with self.subTest(voucher=voucher.doctype, kind=kind):
				self.assertEqual(by_voucher[name][column], abs(qty))
		conversion = next(row for row in rows if row["against"] == "SD YRP Item Conversion")
		self.assertEqual((conversion["conversion_inward"], conversion["conversion_outward"]), (4, 6))

	def test_totals_and_difference_match_ledger_net(self):
		self.make_all_movements()
		rows = self.run_report(summarized_view=1)
		self.assertEqual({row["supplier"] for row in rows}, {self.supplier, None})
		total = {
			field: sum(row[field] for row in rows)
			for field in ("total_inward", "total_outward", "difference")
		}
		self.assertEqual(total["total_inward"], 100 + 7 + 20 + 9 + 3 + 4)
		self.assertEqual(total["total_outward"], 5 + 8 + 2 + 30 + 6)
		ledger_net = frappe.db.sql(
			"SELECT SUM(qty) FROM `tabYRP Stock Ledger Entry` WHERE warehouse = %s", self.warehouse
		)[0][0]
		self.assertEqual(total["difference"], ledger_net)
		for row in rows:
			self.assertEqual(row["difference"], row["total_inward"] - row["total_outward"])
			self.assertEqual((row["item"], row["item_variant"]), (self.template, self.variant))

	def test_document_rows_keep_earliest_known_posting_time(self):
		transfer = self.make_voucher("YRP Stock Entry", purpose="Send to Warehouse")
		mixed = self.make_voucher("YRP Stock Entry", purpose="Send to Warehouse")
		untimed = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(transfer, 2, time="11:00:00")
		self.add_entry(transfer, -3, time="09:30:00")
		self.add_entry(mixed, 2, time=None)
		self.add_entry(mixed, -3, time="08:00:00")
		self.add_entry(untimed, 4, time=None)
		times = {row["against_id"]: row["posting_time"] for row in self.run_report()}
		self.assertEqual(str(times[transfer.name]), "9:30:00")
		self.assertEqual(str(times[mixed.name]), "8:00:00")
		self.assertIsNone(times[untimed.name])

	def test_rejects_missing_or_reversed_dates(self):
		for filters in ({"from_date": DATE}, {"from_date": NEXT_DATE, "to_date": DATE}):
			with self.subTest(filters=filters), self.assertRaises(frappe.ValidationError):
				execute(filters)

	def test_summarized_view_drops_document_and_bucket_columns(self):
		self.make_all_movements()
		columns, _rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "summarized_view": 1})
		fields = [column["fieldname"] for column in columns]
		self.assertEqual(fields[-3:], ["total_inward", "total_outward", "difference"])
		self.assertNotIn("against_id", fields)
		self.assertNotIn("po_grn", fields)

	def test_month_wise_report_splits_totals_per_month(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		self.add_entry(receipt, 10)
		self.add_entry(issue, -4, date="2099-04-02")
		self.add_entry(receipt, 6, date="2099-05-31")
		filters = {"to_date": "2099-05-31", "summarized_view": 1, "month_wise_report": 1}
		columns, rows = execute({"from_date": DATE, "warehouse": self.warehouse, **filters})
		labels = [column["label"] for column in columns if column["fieldtype"] == "Float"]
		self.assertEqual(
			labels,
			[
				"Mar 2099 Inward",
				"Mar 2099 Outward",
				"Apr 2099 Inward",
				"Apr 2099 Outward",
				"May 2099 Inward",
				"May 2099 Outward",
				"Total Inward",
				"Total Outward",
				"Difference",
			],
		)
		(row,) = rows
		months = [row[column["fieldname"]] for column in columns if column["fieldtype"] == "Float"][:6]
		self.assertEqual(months, [10, 0, 0, 4, 6, 0])
		self.assertEqual(sum(months[0::2]), row["total_inward"])
		self.assertEqual(sum(months[1::2]), row["total_outward"])
		self.assertEqual(row["difference"], 12)

	def test_month_wise_report_needs_summarized_view(self):
		self.make_all_movements()
		columns, _rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "month_wise_report": 1})
		self.assertIn("against_id", [column["fieldname"] for column in columns])

	def test_supplier_filter_excludes_documents_without_supplier(self):
		self.make_all_movements()
		rows = self.run_report(supplier=self.supplier, summarized_view=1)
		self.assertEqual(
			[(row["po_grn"], row["other_inward"], row["dc_qty"]) for row in rows], [(100, 7, 30)]
		)
		self.assertEqual(rows[0]["supplier"], self.supplier)

	def test_item_filters_match_template_and_variant(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		standalone = self.make_item("S")
		self.add_entry(receipt, 2)
		self.add_entry(receipt, 5, item=standalone)
		cases = [
			({"item": self.template}, {self.variant}),
			({"item": standalone}, {standalone}),
			({"item_variant": self.variant}, {self.variant}),
			({"item": standalone, "item_variant": self.variant}, set()),
		]
		for filters, expected in cases:
			with self.subTest(filters=filters):
				self.assertEqual({row["item_variant"] for row in self.run_report(**filters)}, expected)

	def test_item_group_filter_includes_child_groups(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 2)
		group = frappe.db.get_value("Item", self.variant, "item_group")
		root = frappe.db.get_value("Item Group", group, "parent_item_group")
		other = frappe.db.get_value("Item Group", {"name": ["!=", group], "is_group": 0}, "name")
		self.assertEqual(len(self.run_report(item_group=root)), 1)
		self.assertEqual(len(self.run_report(item_group=group)), 1)
		self.assertEqual(self.run_report(item_group=other), [])
