import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.yrp_goods_received_note.test_internal_unit_transfer import (
	_company_supplier,
	_make_grn,
	_make_wo,
	_non_company_supplier,
)
from yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn import (
	_default_received_type,
	_warehouse,
)
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import make_grn_completion

from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import sd_yrp_grn_rework_item as rework_item


class TestReworkInternalTransfer(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.original_transit = frappe.db.get_single_value("YRP Stock Settings", "transit_warehouse")
		cls.transit = _warehouse(f"_T_Rework_Transit_{frappe.generate_hash(length=6)}")
		frappe.db.set_single_value("YRP Stock Settings", "transit_warehouse", cls.transit)
		_default_received_type()
		cls.accepted, cls.rejected = rework_item._received_type_defaults()
		cls.rework_type = frappe.get_all(
			"YRP Received Type",
			filters={"name": ["not in", [cls.accepted, cls.rejected]]},
			pluck="name",
			limit=1,
		)[0]

	@classmethod
	def tearDownClass(cls):
		frappe.db.set_single_value("YRP Stock Settings", "transit_warehouse", cls.original_transit)
		super().tearDownClass()

	def submit_rework_grn(self, sender):
		receiver = _company_supplier("_T_Rework_Receiver")
		wo, from_warehouse, to_warehouse, variant, uom = _make_wo(sender, receiver, qty=10)
		grn = _make_grn(wo, from_warehouse, to_warehouse, variant, uom, qty=5)
		grn.items[0].received_type = self.rework_type
		grn.save()
		self.baseline = self.balances(grn)
		grn.submit()
		rework = frappe.get_doc("SD YRP GRN Rework Item", {"grn_number": grn.name})
		return grn, rework

	def balances(self, grn):
		row = grn.items[0]
		baseline = getattr(self, "baseline", {})
		return {
			received_type: flt(
				get_stock_balance(
					row.item_variant, grn.to_warehouse, lot=row.lot, received_type=received_type
				)
			)
			- baseline.get(received_type, 0)
			for received_type in (self.rework_type, self.accepted)
		}

	def shifted(self, before, qty):
		return {self.rework_type: before[self.rework_type] - qty, self.accepted: before[self.accepted] + qty}

	def clear(self, rework, qty):
		row_name = rework.grn_rework_item_details[0].name
		return rework_item.update_partial_quantity(frappe.as_json([{"row_name": row_name, "rework": qty}]))

	def test_company_to_company_rework_waits_for_complete_transfer(self):
		grn, rework = self.submit_rework_grn(_company_supplier("_T_Rework_Sender"))
		self.assertEqual(grn.is_internal_unit, 1)
		self.assertEqual(rework.warehouse, grn.to_warehouse)
		with self.assertRaisesRegex(frappe.ValidationError, "Complete Transfer"):
			self.clear(rework, 3)

		frappe.get_doc("YRP Stock Entry", make_grn_completion(grn.name)).submit()
		before = self.balances(grn)
		self.assertGreater(before[self.rework_type], 0)
		self.clear(rework, 1)
		self.assertEqual(self.balances(grn), self.shifted(before, 1))

		rework_item.revert_reworked_item(rework.name)
		self.assertEqual(self.balances(grn), before)
		rework.reload()
		self.assertEqual(rework.grn_rework_item_details[0].reworked, 0)

	def test_supplier_to_company_rework_clears_at_delivery_warehouse(self):
		grn, rework = self.submit_rework_grn(_non_company_supplier("_T_Rework_Supplier"))
		self.assertEqual(grn.is_internal_unit, 0)
		self.assertEqual(rework.warehouse, grn.to_warehouse)
		before = self.balances(grn)
		self.clear(rework, 1)
		self.assertEqual(self.balances(grn), self.shifted(before, 1))
