import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import test_fabric_store_goods_received_note as fixtures
from essdee_yrp.fabric_store.documents.goods_received_note import save_goods_received_note


class TestFabricStoreGRNHeaderLot(FrappeTestCase):
	def test_web_single_lot_header_is_derived(self):
		po, fieldname, first_lot, _other_lot, values = fixtures.TestPurchaseOrderLotWorkspace.receipt_values(
			self, [4]
		)
		frappe.db.set_value("Purchase Order", po.name, fieldname, None)
		workspace = save_goods_received_note(values, submit=True)
		grn = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertEqual(grn.get(fieldname), first_lot)
		self.assertEqual(grn.docstatus, 1)

	def test_web_multi_lot_header_is_blank_on_save_and_submit(self):
		po, fieldname, first_lot, other_lot, values = fixtures.TestPurchaseOrderLotWorkspace.receipt_values(
			self, [4, 6]
		)
		frappe.db.set_value("Purchase Order", po.name, fieldname, None)
		workspace = save_goods_received_note(values)
		grn = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertFalse(grn.get(fieldname))
		workspace = save_goods_received_note(
			{},
			name=grn.name,
			expected_modified=workspace["record"]["modified"],
			submit=True,
		)
		grn.reload()
		self.assertEqual(grn.docstatus, 1)
		self.assertFalse(grn.get(fieldname))
		self.assertEqual(
			{row.get(fieldname): row.quantity for row in grn.items}, {first_lot: 4, other_lot: 6}
		)
