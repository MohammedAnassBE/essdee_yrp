from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.cutting.lot_transfer_quantities import apply_quantities, get_quantity_rows

MODULE = "essdee_yrp.cutting.lot_transfer_quantities"


def make_plan():
	return frappe._dict(
		name="CP-TEST",
		lot="LOT-A",
		cutting_plan_cloth_details=[
			frappe._dict(
				cloth_item_variant="CLOTH-RED",
				cloth_type="Jersey",
				colour="Red",
				dia="30",
				balance_weight=100,
			),
			frappe._dict(
				cloth_item_variant="CLOTH-BLUE",
				cloth_type="Jersey",
				colour="Blue",
				dia="30",
				balance_weight=40,
			),
		],
	)


def make_transfer(docstatus=0, from_lot="LOT-A"):
	doc = MagicMock()
	doc.doctype = "SD YRP Lot Transfer"
	doc.docstatus = docstatus
	doc.items = [
		frappe._dict(
			name="ROW-RED", item="CLOTH-RED", from_lot=from_lot, to_lot="LOT-B", uom="Kg", qty=100, idx=1
		),
		frappe._dict(
			name="ROW-BLUE", item="CLOTH-BLUE", from_lot=from_lot, to_lot="LOT-B", uom="Kg", qty=40, idx=2
		),
	]
	doc.get.side_effect = lambda field: doc.items if field == "items" else None
	doc.set.side_effect = lambda field, value: setattr(doc, field, value)
	return doc


@patch(f"{MODULE}.frappe.has_permission", return_value=True)
class TestLotTransferQuantities(UnitTestCase):
	def test_draft_balance_transfer_exposes_rows_with_plan_balance(self, _has_permission):
		rows = get_quantity_rows(make_plan(), make_transfer())
		self.assertEqual([row["name"] for row in rows], ["ROW-RED", "ROW-BLUE"])
		self.assertEqual(rows[0]["label"], "Jersey · CLOTH-RED")
		self.assertEqual(rows[0]["available"], 100)
		self.assertEqual(rows[1]["available"], 40)

	def test_submitted_or_foreign_lot_transfer_is_not_editable(self, _has_permission):
		self.assertIsNone(get_quantity_rows(make_plan(), make_transfer(docstatus=1)))
		self.assertIsNone(get_quantity_rows(make_plan(), make_transfer(from_lot="LOT-Z")))

	def test_quantity_is_changed_and_saved(self, _has_permission):
		doc = make_transfer()
		apply_quantities(
			make_plan(), doc, '[{"name": "ROW-RED", "qty": 50}, {"name": "ROW-BLUE", "qty": 40}]'
		)
		self.assertEqual([row.qty for row in doc.items], [50, 40])
		doc.save.assert_called_once_with()

	def test_omitted_row_is_deleted_and_rows_are_renumbered(self, _has_permission):
		doc = make_transfer()
		apply_quantities(make_plan(), doc, [{"name": "ROW-BLUE", "qty": 10}])
		self.assertEqual([(row.name, row.qty, row.idx) for row in doc.items], [("ROW-BLUE", 10, 1)])

	def test_invalid_quantities_are_rejected_before_save(self, _has_permission):
		for rows in (
			[{"name": "ROW-RED", "qty": 0}],
			[{"name": "ROW-RED", "qty": 100.001}],
			[{"name": "ROW-OTHER", "qty": 1}],
			[{"name": "ROW-RED", "qty": 1}, {"name": "ROW-RED", "qty": 1}],
			[],
		):
			doc = make_transfer()
			with self.subTest(rows=rows), self.assertRaises(frappe.ValidationError):
				apply_quantities(make_plan(), doc, rows)
			doc.save.assert_not_called()

	def test_only_draft_can_be_changed(self, _has_permission):
		doc = make_transfer(docstatus=1)
		with self.assertRaises(frappe.ValidationError):
			apply_quantities(make_plan(), doc, [{"name": "ROW-RED", "qty": 1}])
		doc.save.assert_not_called()
