from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing import packing_grn

# FP-2627-00244 / WO-2627-01364, size M: (colour, idx, planned, delivered, real received)
SIZE_M = (
	("Soft Orange", 2, 785, 750, 450),
	("Liver", 7, 1015, 736, 350),
	("Wenge", 12, 605, 604, 450),
	("Dark Grey", 17, 430, 416, 350),
	("Cool Grey", 22, 15, 0, 0),
	("Olive", 27, 920, 904, 465),
	("Black", 32, 1011, 1003, 550),
)
# Migrated F15 history: GRN box count credited to every packing colour.
INFLATED_RECEIVED = {
	"Soft Orange": 608,
	"Liver": 633,
	"Wenge": 588,
	"Dark Grey": 569,
	"Cool Grey": 524,
	"Olive": 623,
	"Black": 639,
}


def variant(colour):
	return f"VEST-{colour}-M"


def work_order(received=None):
	calculated = [
		frappe._dict(
			name=f"CALC-{colour}",
			idx=idx,
			item_variant=variant(colour),
			quantity=planned,
			delivered_quantity=delivered,
			received_qty=(received or {}).get(colour, real),
			set_combination=f'{{"major_colour":"{colour}"}}',
		)
		for colour, idx, planned, delivered, real in SIZE_M
	]
	deliverables = [
		frappe._dict(name=f"DEL-{row.item_variant}", item_variant=row.item_variant, uom="Pieces")
		for row in calculated
	]
	return frappe._dict(
		name="WO-1",
		process_name="Ironing and Packing",
		production_detail="IPD-1",
		work_order_calculated_items=calculated,
		deliverables=deliverables,
	)


def attributes(item_variant):
	if item_variant.startswith("VEST-"):
		_prefix, colour, size = item_variant.split("-")
		return {"Size": size, "Colour": colour}
	return {"Size": item_variant.rsplit("-", 1)[-1]}


IPD = frappe._dict(primary_item_attribute="Size", packing_attribute="Colour", is_set_item=0)


def packing_grn_doc(**values):
	return frappe._dict(
		{
			"against": "YRP Work Order",
			"against_id": "WO-1",
			"includes_packing": 1,
			"from_warehouse": "S-0171",
			"posting_date": "2026-10-23",
			"posting_time": "10:00:00",
			"flags": frappe._dict(),
			**values,
		}
	)


class TestPackingGarmentAllocation(TestCase):
	def _plan(self, grn, wo):
		with (
			patch.object(packing_grn, "get_variant_attr_details", side_effect=attributes),
			patch.object(
				packing_grn,
				"_find_deliverable",
				side_effect=lambda deliverables, row: next(
					item for item in deliverables if item.item_variant == row.item_variant
				),
			),
			patch("yrp.stock.utils.get_conversion_factor", return_value={"conversion_factor": 1}),
			patch(
				"yrp.yrp.doctype.yrp_work_order.yrp_work_order._stock_dimension_values",
				return_value={"lot": "C0426-35/2", "received_type": "Accepted"},
			),
			patch.object(packing_grn, "get_loose_piece_stock_variant", return_value="VEST-Loose Piece-M"),
			patch.object(packing_grn, "get_stock_balance", return_value=(1798, 21.5)),
		):
			if packing_grn.is_dynamic_packing_grn(grn):
				return packing_grn._allocate_dynamic_consumed_garments(grn, wo, IPD)
			return packing_grn._allocate_consumed_garments(grn, wo, IPD)

	@staticmethod
	def _by_colour(plan):
		totals = {colour: 0 for colour, *_rest in SIZE_M}
		for row in plan:
			totals[attributes(row["item_variant"])["Colour"]] += row["stock_qty"]
		return [totals[colour] for colour, *_rest in SIZE_M]

	def test_real_remaining_allocates_1500_pieces_per_colour(self):
		grn = packing_grn_doc(items=[frappe._dict(name="OUT-M", item_variant="BOX-M", stock_qty=1500)])
		plan = self._plan(grn, work_order())

		self.assertEqual(self._by_colour(plan), [300, 386, 154, 66, 0, 439, 155])
		self.assertEqual({row["valuation_rate"] for row in plan}, {21.5})
		self.assertTrue(all(row["work_order_deliverable"] for row in plan))

	def test_colour_split_never_blocks_when_history_is_short(self):
		grn = packing_grn_doc(items=[frappe._dict(name="OUT-M", item_variant="BOX-M", stock_qty=1500)])
		plan = self._plan(grn, work_order(INFLATED_RECEIVED))

		self.assertAlmostEqual(sum(row["stock_qty"] for row in plan), 1500)
		filled = [142, 103, 16, 0, 0, 281, 364]
		self.assertTrue(all(total >= real for total, real in zip(self._by_colour(plan), filled, strict=True)))

	def test_dynamic_batch_spreads_excess_on_its_colour(self):
		grn = packing_grn_doc(
			packing_calculation_version=2,
			items=[frappe._dict(name="OUT-M", item_variant="BOX-M", stock_qty=500)],
			packing_batches=[frappe._dict(colour="Black", box_quantity=100, ratio_json='{"M": 5}')],
		)
		with patch.object(packing_grn, "is_dynamic_packing_grn", return_value=True):
			plan = self._plan(grn, work_order())

		self.assertEqual(self._by_colour(plan), [0, 0, 0, 0, 0, 0, 500])


class TestLoosePieceStockGate(TestCase):
	def _validate(self, garments, balance, flags=None):
		grn = packing_grn_doc(flags=frappe._dict(flags or {}))
		with (
			patch.object(packing_grn, "get_loose_piece_stock_variant", return_value="VEST-Loose Piece-M"),
			patch("yrp.stock.utils.get_stock_balance", return_value=(balance, 21.5)) as stock,
		):
			packing_grn.validate_loose_piece_stock(grn, work_order(), garments)
		return stock

	@staticmethod
	def _garments(quantities):
		return [
			{
				"item_variant": variant(colour),
				"stock_qty": quantity,
				"stock_uom": "Pieces",
				"dimensions": {"lot": "C0426-35/2", "received_type": "Accepted"},
			}
			for (colour, *_rest), quantity in zip(SIZE_M, quantities, strict=True)
		]

	def test_colours_share_one_loose_piece_bucket(self):
		stock = self._validate(self._garments([300, 386, 154, 66, 0, 439, 155]), 1798)

		stock.assert_called_once()
		self.assertEqual(stock.call_args.args[:2], ("VEST-Loose Piece-M", "S-0171"))
		self.assertEqual(stock.call_args.kwargs["lot"], "C0426-35/2")
		self.assertEqual(stock.call_args.kwargs["received_type"], "Accepted")

	def test_short_loose_piece_stock_is_blocked(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			self._validate(self._garments([300, 386, 154, 66, 0, 439, 155]), 906)

		message = str(raised.exception)
		self.assertIn("VEST-Loose Piece-M", message)
		self.assertIn("need 1500", message)
		self.assertIn("short 594", message)

	def test_draft_preview_skips_the_gate(self):
		stock = self._validate(self._garments([1500, 0, 0, 0, 0, 0, 0]), 0, {"skip_input_stock_check": 1})

		stock.assert_not_called()
