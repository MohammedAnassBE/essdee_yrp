import json

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_audit_report.sd_yrp_purchase_audit_report import (
	execute,
	item_query,
)

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

	def add_entry(self, voucher, qty, date=DATE, warehouse=None, item=None, lot=None, **fields):
		frappe.get_doc(
			{
				"doctype": "YRP Stock Ledger Entry",
				"item": item or self.variant,
				"warehouse": warehouse or self.warehouse,
				"posting_date": date,
				"posting_time": "10:00:00",
				"posting_datetime": f"{date} 10:00:00",
				"qty": qty,
				"voucher_type": voucher.doctype,
				"voucher_no": voucher.name,
				"lot": lot,
				"received_type": None,
				"is_cancelled": 0,
				"docstatus": 1,
				**fields,
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
		self.make_all_movements()
		rows = {row["supplier"]: row for row in self.run_report()}
		expected = {
			self.supplier: {"po_grn": 100, "other_inward": 7, "dc_qty": 30},
			None: {
				"se_material_receipt": 20,
				"se_material_issue": 5,
				"sent_warehouse": 8,
				"received_warehouse": 9,
				"added_stock": 3,
				"reduced_stock": 2,
				"conversion_inward": 4,
				"conversion_outward": 6,
			},
		}
		self.assertEqual(set(rows), set(expected))
		for supplier, columns in expected.items():
			with self.subTest(supplier=supplier):
				quantities = {field: rows[supplier][field] for field in columns}
				self.assertEqual(quantities, columns)

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

	def test_detailed_view_collapses_vouchers_per_variant_lot_and_received_type(self):
		first = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		second = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		self.add_entry(first, 10, lot=f"LOT-{self.key}")
		self.add_entry(second, 6, date=NEXT_DATE, lot=f"LOT-{self.key}")
		self.add_entry(issue, -4, lot=f"LOT-{self.key}")
		self.add_entry(first, 3, lot=f"OTHER-{self.key}")
		columns, rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse})
		fields = [column["fieldname"] for column in columns]
		for field in ("against", "against_id", "posting_date", "posting_time"):
			self.assertNotIn(field, fields)
		by_lot = {row["lot"]: row for row in rows}
		self.assertEqual(len(rows), 2)
		row = by_lot[f"LOT-{self.key}"]
		self.assertEqual((row["se_material_receipt"], row["se_material_issue"]), (16, 4))
		self.assertEqual((row["total_inward"], row["total_outward"], row["difference"]), (16, 4, 12))
		self.assertEqual(by_lot[f"OTHER-{self.key}"]["total_inward"], 3)

	def test_rejects_missing_or_reversed_dates(self):
		for filters in ({"from_date": DATE}, {"from_date": NEXT_DATE, "to_date": DATE}):
			with self.subTest(filters=filters), self.assertRaises(frappe.ValidationError):
				execute(filters)

	def test_summarized_view_drops_bucket_columns(self):
		self.make_all_movements()
		columns, _rows = execute({"from_date": DATE, "to_date": NEXT_DATE, "summarized_view": 1})
		fields = [column["fieldname"] for column in columns]
		self.assertEqual(fields[-4:], ["total_inward", "total_outward", "difference", "stock_balance"])
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
				"Stock Balance",
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
		self.assertIn("po_grn", [column["fieldname"] for column in columns])

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
			({"item": [self.template, standalone]}, {self.variant, standalone}),
			({"item": json.dumps([standalone])}, {standalone}),
			({"item": []}, {self.variant, standalone}),
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
		self.assertEqual(len(self.run_report(item_group=[other, group])), 1)

	def test_item_query_limits_options_to_item_group_tree(self):
		standalone = self.make_item("S")
		parent = self.make_item_group("Parent", is_group=1)
		child = self.make_item_group("Child", parent=parent)
		frappe.db.set_value("Item", self.variant, "item_group", child)
		cases = [
			({}, {self.template, standalone}),
			({"variant": 1}, {self.variant, standalone}),
			({"item_group": [parent]}, {self.template}),
			({"item_group": json.dumps([child]), "variant": 1}, {self.variant}),
			({"item_group": [parent, child], "variant": 1}, {self.variant}),
		]
		for filters, expected in cases:
			with self.subTest(filters=filters):
				rows = item_query("Item", f"AUD-{self.key}", "name", 0, 20, filters)
				self.assertEqual({row[0] for row in rows}, expected)

	def make_item_group(self, name, parent="All Item Groups", is_group=0):
		doc = {"doctype": "Item Group", "item_group_name": f"AUD {name} {self.key}"}
		doc.update(parent_item_group=parent, is_group=is_group)
		return frappe.get_doc(doc).insert(ignore_permissions=True).name

	def test_stock_balance_is_closing_qty_at_to_date(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		moved, reconciled = f"LOT-{self.key}", f"RECON-{self.key}"
		self.add_entry(receipt, 50, date="2099-03-01", lot=moved)
		self.add_entry(receipt, 10, lot=moved)
		self.add_entry(issue, -4, lot=moved)
		self.add_entry(receipt, 100, date="2099-04-01", lot=moved)
		self.add_entry(receipt, 7, date="2099-03-01", lot=reconciled)
		self.add_entry(reconciliation, 0, date="2099-03-05", lot=reconciled, qty_after_transaction=20)
		self.add_entry(receipt, 5, lot=reconciled)
		views = ({}, {"summarized_view": 1}, {"summarized_view": 1, "month_wise_report": 1})
		for view in views:
			with self.subTest(view=view):
				columns, rows = execute(
					{"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse, **view}
				)
				self.assertEqual(columns[-1]["fieldname"], "stock_balance")
				self.assertEqual(
					{row["lot"]: row["stock_balance"] for row in rows}, {moved: 56, reconciled: 25}
				)
