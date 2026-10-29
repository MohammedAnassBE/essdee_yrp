import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.attribute_links import link
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import _get_warehouse_for_supplier

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	cancel_laysheet,
	mark_labels_printed,
	print_labels,
)

LAYSHEET = "CLS-2610-00017"
INPUT_VARIANT = "Sareena Fabric With Wicking-Liver-60 Dia"
ACTUAL_VARIANT = "Sareena Fabric With Wicking-Liver-61 Dia"


class TestCuttingLaySheetDiaConversion(IntegrationTestCase):
	"""Label print converts the Actual Dia cloth into the input dia and consumes it, like production_api."""

	def setUp(self):
		if frappe.db.get_value("SD YRP Cutting LaySheet", LAYSHEET, "status") != "Bundles Generated":
			self.skipTest(f"Bundles Generated oracle {LAYSHEET} is unavailable")
		frappe.set_user("Administrator")
		frappe.db.savepoint("dia_conversion")
		self.addCleanup(frappe.db.rollback, save_point="dia_conversion")
		self.laysheet = frappe.get_doc("SD YRP Cutting LaySheet", LAYSHEET)
		self.work_order = frappe.get_doc(
			"YRP Work Order",
			frappe.db.get_value("SD YRP Cutting Plan", self.laysheet.cutting_plan, "work_order"),
		)
		self.warehouse = _get_warehouse_for_supplier(self.work_order.supplier)
		self.detail = self.laysheet.cutting_laysheet_details[0]
		self.assertEqual(self.detail.cloth_item_variant, INPUT_VARIANT)
		self.converted = flt(self.detail.weight) - flt(self.detail.balance_weight)
		self.deliver_actual_dia_instead_of_input_dia()
		frappe.db.set_value(
			self.detail.doctype,
			self.detail.name,
			"actual_dia",
			link("61 Dia", "Dia"),
			update_modified=False,
		)

	def deliver_actual_dia_instead_of_input_dia(self):
		"""The cutter holds only 61 Dia; none of the IPD input dia 60 was delivered."""
		source = next(row for row in self.work_order.deliverables if row.item_variant == INPUT_VARIANT)
		self.input_deliverable = source.name
		self.dimensions = {"lot": source.lot, "received_type": source.received_type}
		frappe.db.set_value(
			source.doctype, source.name, "pending_quantity", source.qty, update_modified=False
		)
		row = frappe.copy_doc(source)
		row.update(
			{
				"item_variant": ACTUAL_VARIANT,
				"qty": 1.2,
				"pending_quantity": 0,
				"stock_update": 0,
				"idx": source.idx + 100,
				"docstatus": source.docstatus,
				"parent": source.parent,
				"parenttype": source.parenttype,
				"parentfield": source.parentfield,
			}
		)
		row.db_insert()
		input_stock = self.get_balance(INPUT_VARIANT)
		if input_stock:
			self.make_stock_entry("Material Issue", INPUT_VARIANT, input_stock, source.uom)
		self.make_stock_entry("Material Receipt", ACTUAL_VARIANT, 1.2, source.uom)

	def make_stock_entry(self, purpose, item_variant, qty, uom):
		warehouse_field = "to_warehouse" if purpose == "Material Receipt" else "from_warehouse"
		entry = frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": purpose,
				warehouse_field: self.warehouse,
				"items": [
					{
						"item": item_variant,
						"qty": qty,
						"uom": uom,
						"conversion_factor": 1,
						"rate": 10,
						**self.dimensions,
					}
				],
			}
		)
		entry.insert(ignore_permissions=True)
		entry.submit()

	def get_balance(self, item_variant):
		return flt(get_stock_balance(item_variant, self.warehouse, **self.dimensions), 6)

	def get_voucher_qty(self, voucher_no):
		rows = {}
		for row in frappe.get_all(
			"YRP Stock Ledger Entry",
			filters={"voucher_no": voucher_no, "is_cancelled": 0},
			fields=["item", "warehouse", "lot", "received_type", "qty"],
		):
			self.assertEqual(
				(row.warehouse, row.lot, row.received_type),
				(self.warehouse, self.dimensions["lot"], self.dimensions["received_type"]),
			)
			rows[row.item] = rows.get(row.item, 0) + flt(row.qty)
		return rows

	def get_receivable_pending(self):
		return {
			row.item_variant: flt(row.pending_quantity)
			for row in frappe.get_all(
				"YRP Work Order Receivables",
				filters={"parent": self.work_order.name},
				fields=["item_variant", "pending_quantity"],
			)
		}

	def get_input_stock_update(self):
		return flt(frappe.db.get_value("YRP Work Order Deliverables", self.input_deliverable, "stock_update"))

	def print_labels(self):
		grn = print_labels(None, None, LAYSHEET, "Panel")["grn"]
		mark_labels_printed(LAYSHEET, grn)
		return frappe.get_doc("YRP Goods Received Note", grn)

	def test_label_print_moves_actual_dia_into_input_dia_and_consumes_it(self):
		pending_before = self.get_receivable_pending()

		grn = self.print_labels()

		conversion = self.get_voucher_qty(LAYSHEET)
		self.assertAlmostEqual(conversion[ACTUAL_VARIANT], -self.converted, places=6)
		self.assertAlmostEqual(conversion[INPUT_VARIANT], self.converted, places=6)
		self.assertEqual(grn.from_warehouse, self.warehouse)
		consumed = self.get_voucher_qty(grn.name)
		self.assertAlmostEqual(consumed[INPUT_VARIANT], -flt(self.detail.used_weight), places=5)
		self.assertAlmostEqual(self.get_balance(ACTUAL_VARIANT), 1.2 - self.converted, places=6)
		self.assertAlmostEqual(
			self.get_balance(INPUT_VARIANT), self.converted - flt(self.detail.used_weight), places=5
		)
		pending_after = self.get_receivable_pending()
		for row in grn.items:
			self.assertAlmostEqual(
				pending_after[row.item_variant],
				pending_before[row.item_variant] - flt(row.quantity),
				places=6,
			)
		self.assertAlmostEqual(self.get_input_stock_update(), flt(self.detail.used_weight), places=5)

	def test_cancel_laysheet_restores_both_dias_and_receivables(self):
		pending_before = self.get_receivable_pending()
		self.print_labels()

		cancel_laysheet(LAYSHEET)

		self.assertAlmostEqual(self.get_balance(ACTUAL_VARIANT), 1.2, places=6)
		self.assertAlmostEqual(self.get_balance(INPUT_VARIANT), 0, places=6)
		self.assertEqual(self.get_receivable_pending(), pending_before)
		self.assertAlmostEqual(self.get_input_stock_update(), 0, places=5)
