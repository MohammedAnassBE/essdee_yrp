from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowtime, today

from essdee_yrp.finishing import views, web_entries


def _ironing_target():
	for name in frappe.get_all(
		"SD YRP Finishing Plan",
		filters={"docstatus": ["<", 2], "fp_status": ["not in", ["Auto Closed", "OCR Completed"]]},
		pluck="name",
		order_by="name asc",
		limit=20,
	):
		doc = frappe.get_doc("SD YRP Finishing Plan", name)
		rows = views.build_plan_views(doc)["finishing_ironing"]["data"]
		for colour, row in rows.items():
			for size in row.get("values") or {}:
				return doc, colour, size
	return None


def _test_warehouse():
	return (
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"_Test Zero Valuation {frappe.generate_hash(length=8)}",
				"company": frappe.db.get_value("Company", {}, "name"),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _ironing_excess_total(doc):
	doc.reload()
	return sum(flt(row.ironing_excess) for row in doc.finishing_plan_details)


class TestFinishingZeroValuation(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		target = _ironing_target()
		if not target:
			self.skipTest("No Finishing Plan with ironing rows is available")
		self.doc, self.colour, self.size = target
		self.received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")

	def add_ironing_excess(self, quantity, last_rate):
		with patch("yrp.stock.utils.get_last_sle_rate", return_value=(last_rate, None)):
			result = web_entries.add_ironing_excess(
				self.doc, {"quantities": {self.colour: {"sizes": {self.size: quantity}}}}
			)
		stock_entry = frappe.get_doc("YRP Stock Entry", result["name"])
		ledger = frappe.get_all(
			"YRP Stock Ledger Entry",
			filters={"voucher_no": stock_entry.name, "is_cancelled": 0},
			fields=["qty", "rate", "warehouse", "lot"],
		)
		return stock_entry, ledger

	def test_ironing_excess_posts_stock_without_valuation(self):
		before = _ironing_excess_total(self.doc)
		stock_entry, ledger = self.add_ironing_excess(3, 0)

		self.assertEqual(stock_entry.docstatus, 1)
		self.assertEqual([(row.qty, row.rate) for row in stock_entry.items], [(3, 0)])
		self.assertTrue(stock_entry.items[0].allow_zero_valuation_rate)
		self.assertEqual(
			[(row.qty, row.rate, row.warehouse, row.lot) for row in ledger],
			[(3, 0, self.doc.delivery_location, self.doc.lot)],
		)
		self.assertEqual(_ironing_excess_total(self.doc), before + 3)
		self.assertIn(stock_entry.name, self.doc.ironing_excess_list)

	def test_ironing_excess_keeps_known_valuation(self):
		stock_entry, ledger = self.add_ironing_excess(2, 12.5)

		self.assertEqual(stock_entry.items[0].rate, 12.5)
		self.assertEqual([(row.qty, row.rate) for row in ledger], [(2, 12.5)])

	def test_plain_material_receipt_still_rejects_zero_rate(self):
		variant = self.doc.finishing_plan_details[0].item_variant
		stock_entry = frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": "Material Receipt",
				"to_warehouse": self.doc.delivery_location,
				"items": [
					{
						"item": variant,
						"qty": 1,
						"rate": 0,
						"lot": self.doc.lot,
						"received_type": self.received_type,
					}
				],
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Rate must be greater than zero"):
			stock_entry.insert(ignore_permissions=True)

	def test_old_lot_transfer_moves_zero_valued_stock(self):
		variant = self.doc.finishing_plan_details[0].item_variant
		source_lot = self.doc.lot
		target_lot = frappe.db.get_value("SD YRP Lot", {"name": ["!=", source_lot]}, "name")
		warehouse = _test_warehouse()
		receipt = frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": "Material Receipt",
				"to_warehouse": warehouse,
				"posting_date": today(),
				"posting_time": nowtime(),
				"items": [
					{
						"item": variant,
						"qty": 5,
						"rate": 0,
						"allow_zero_valuation_rate": 1,
						"lot": source_lot,
						"received_type": self.received_type,
					}
				],
			}
		).insert(ignore_permissions=True)
		receipt.submit()

		transfer = frappe.new_doc("SD YRP Lot Transfer")
		transfer.append(
			"items",
			{
				"item": variant,
				"from_lot": source_lot,
				"to_lot": target_lot,
				"warehouse": warehouse,
				"qty": 4,
				"received_type": self.received_type,
			},
		)
		transfer.insert(ignore_permissions=True)
		transfer.submit()

		ledger = frappe.get_all(
			"YRP Stock Ledger Entry",
			filters={"voucher_no": transfer.name, "is_cancelled": 0},
			fields=["lot", "qty", "rate", "qty_after_transaction"],
			order_by="qty asc",
		)
		self.assertEqual(transfer.docstatus, 1)
		self.assertEqual(
			[(row.lot, row.qty, row.rate) for row in ledger],
			[(source_lot, -4, 0), (target_lot, 4, 0)],
		)
		self.assertEqual([row.qty_after_transaction for row in ledger], [1, 4])
