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
		(row,) = self.run_report()
		expected = {
			"po_grn": 100,
			"other_inward": 7,
			"dc_qty": 30,
			"se_material_receipt": 20,
			"se_material_issue": 5,
			"sent_warehouse": 8,
			"received_warehouse": 9,
			"added_stock": 3,
			"reduced_stock": 2,
			"conversion_inward": 4,
			"conversion_outward": 6,
			"lot_transfer_in": 0,
			"lot_transfer_out": 0,
		}
		self.assertEqual({field: row[field] for field in expected}, expected)
		self.assertEqual(row["suppliers"], self.supplier)
		self.assertNotIn("supplier", row)

	def test_lot_transfer_has_its_own_columns(self):
		transfer = self.make_voucher("SD YRP Lot Transfer")
		self.add_entry(transfer, 12, lot=f"TO-{self.key}")
		self.add_entry(transfer, -12, lot=f"FROM-{self.key}")
		rows = {row["lot"]: row for row in self.run_report()}
		self.assertEqual(rows[f"TO-{self.key}"]["lot_transfer_in"], 12)
		self.assertEqual(rows[f"FROM-{self.key}"]["lot_transfer_out"], 12)
		for row in rows.values():
			self.assertEqual((row["other_inward"], row["other_outward"]), (0, 0))

	def test_totals_and_difference_match_ledger_net(self):
		self.make_all_movements()
		(row,) = self.run_report(summarized_view=1)
		self.assertEqual(row["total_inward"], 100 + 7 + 20 + 9 + 3 + 4)
		self.assertEqual(row["total_outward"], 5 + 8 + 2 + 30 + 6)
		ledger_net = frappe.db.sql(
			"SELECT SUM(qty) FROM `tabYRP Stock Ledger Entry` WHERE warehouse = %s", self.warehouse
		)[0][0]
		self.assertEqual(row["difference"], ledger_net)
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
		self.assertEqual(
			fields[-6:],
			[
				"total_inward",
				"total_outward",
				"difference",
				"reconciliation_adjustment",
				"opening_stock",
				"stock_balance",
			],
		)
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
				"Reconciliation Adjustment",
				"Opening Stock",
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

	def test_supplier_filter_keeps_every_movement_of_matching_keys(self):
		self.make_all_movements()
		other = self.make_supplier("Other Maker")
		other_dc = self.make_voucher("YRP Delivery Challan", supplier=other)
		self.add_entry(other_dc, -11)
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		self.add_entry(receipt, 5, lot=f"UNRELATED-{self.key}")
		(row,) = self.run_report(supplier=self.supplier)
		self.assertEqual(row["lot"], None)
		self.assertEqual((row["dc_qty"], row["se_material_receipt"], row["po_grn"]), (41, 20, 100))
		self.assertEqual(self.run_report(supplier=other), [])

	def test_supplier_filter_matches_dc_sent_from_supplier_location(self):
		receiver = self.make_supplier("Receiver")
		dc = self.make_voucher("YRP Delivery Challan", supplier=receiver, from_location=self.supplier)
		self.add_entry(dc, -9)
		(row,) = self.run_report(supplier=self.supplier)
		self.assertEqual(row["dc_qty"], 9)
		self.assertEqual(self.run_report(supplier=receiver), [])

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

	def test_opening_stock_is_balance_before_from_date(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		issue = self.make_voucher("YRP Stock Entry", purpose="Material Issue")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		moved, reconciled = f"LOT-{self.key}", f"RECON-{self.key}"
		self.add_entry(receipt, 50, date="2099-03-01", lot=moved)
		self.add_entry(receipt, 10, lot=moved)
		self.add_entry(issue, -4, lot=moved)
		self.add_entry(receipt, 7, date="2099-03-01", lot=reconciled)
		self.add_entry(reconciliation, 0, date="2099-03-05", lot=reconciled, qty_after_transaction=20)
		self.add_entry(receipt, 3, date="2099-03-09", lot=reconciled)
		self.add_entry(receipt, 5, lot=reconciled)
		for view in ({}, {"summarized_view": 1}):
			with self.subTest(view=view):
				columns, rows = execute(
					{"from_date": DATE, "to_date": NEXT_DATE, "warehouse": self.warehouse, **view}
				)
				fields = [column["fieldname"] for column in columns]
				self.assertEqual(fields[-2:], ["opening_stock", "stock_balance"])
				self.assertEqual(
					{row["lot"]: row["opening_stock"] for row in rows}, {moved: 50, reconciled: 23}
				)
				for row in rows:
					self.assertEqual(row["reconciliation_adjustment"], 0)
					self.assertEqual(row["opening_stock"] + row["difference"], row["stock_balance"])

	def test_reconciliation_inside_range_shows_as_adjustment(self):
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		lot = f"RECON-{self.key}"
		self.add_entry(receipt, 7, date="2099-03-01", lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-05", lot=lot, qty_after_transaction=30)
		self.add_entry(receipt, 5, lot=lot)
		self.add_entry(reconciliation, -15, date="2099-03-15", lot=lot, qty_after_transaction=20)
		self.add_entry(receipt, 3, date="2099-03-18", lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-19", lot=lot, qty_after_transaction=10)
		(row,) = self.run_report()
		fields = (
			"opening_stock",
			"total_inward",
			"total_outward",
			"reconciliation_adjustment",
			"stock_balance",
		)
		self.assertEqual(tuple(row[field] for field in fields), (30, 8, 0, -28, 10))

	def test_rows_reconcile_to_stock_balance_in_detailed_and_summarized_views(self):
		self.make_all_movements()
		receipt = self.make_voucher("YRP Stock Entry", purpose="Material Receipt")
		transfer = self.make_voucher("SD YRP Lot Transfer")
		reconciliation = self.make_voucher("YRP Stock Reconciliation")
		lot = f"LOT-{self.key}"
		self.add_entry(receipt, 40, date="2099-03-01", lot=lot)
		self.add_entry(transfer, -15, lot=lot)
		self.add_entry(reconciliation, 0, date="2099-03-12", lot=lot, qty_after_transaction=18)
		self.add_entry(transfer, 15, date="2099-03-15")
		for view in ({}, {"summarized_view": 1}, {"supplier": self.supplier}):
			with self.subTest(view=view):
				rows = self.run_report(**view)
				self.assertTrue(rows)
				for row in rows:
					net = row["total_inward"] - row["total_outward"] + row["reconciliation_adjustment"]
					self.assertEqual(row["opening_stock"] + net, row["stock_balance"])
