from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.finishing import loose_piece, transactions

PIECE = "EC-TEST-Liver-S"


def packing_doc(**values):
	return frappe._dict(
		{"doctype": "YRP Delivery Challan", "includes_packing": 1, "production_detail": "IPD-1", **values}
	)


def plan_or_db(real):
	return lambda doctype, *args, **kwargs: (
		"FP-1" if doctype == "SD YRP Finishing Plan" else real(doctype, *args, **kwargs)
	)


def accepted_or_db(real):
	return lambda doctype, fieldname, *args, **kwargs: (
		"Accepted" if fieldname == "default_received_type" else real(doctype, fieldname, *args, **kwargs)
	)


class TestLoosePieceStockVariant(TestCase):
	def _resolve(self, doc, *, is_stitched=True, loose_piece_stage="Loose Piece"):
		with (
			patch.object(loose_piece.attribute_db, "get_value", return_value=("Stage", "Piece")),
			patch.object(loose_piece, "check_dependent_stage_variant", return_value=is_stitched) as check,
			patch.object(frappe.db, "get_single_value", return_value=loose_piece_stage),
			patch.object(
				loose_piece,
				"get_variant_attr_details",
				return_value={"Colour": "Liver", "Size": "S", "Stage": "Piece"},
			),
			patch.object(loose_piece, "get_parent_item", return_value="EC-TEST"),
			patch.object(
				loose_piece, "build_variant_attributes", return_value={"Stage": "Loose Piece", "Size": "S"}
			) as build,
			patch.object(
				loose_piece, "get_or_create_variant", return_value="EC-TEST-Loose Piece-S"
			) as create,
		):
			result = loose_piece.get_loose_piece_stock_variant(doc, PIECE)
		return result, check, build, create

	def test_non_packing_voucher_keeps_the_variant(self):
		result, check, _build, create = self._resolve(packing_doc(includes_packing=0))
		self.assertEqual(result, PIECE)
		check.assert_not_called()
		create.assert_not_called()

	def test_stitched_piece_is_held_as_loose_piece_stage(self):
		result, check, build, create = self._resolve(packing_doc())
		self.assertEqual(result, "EC-TEST-Loose Piece-S")
		check.assert_called_once_with(PIECE, "Stage", "Piece")
		build.assert_called_once_with(
			{"Colour": "Liver", "Size": "S", "Stage": "Piece"}, "Loose Piece", "IPD-1"
		)
		create.assert_called_once_with("EC-TEST", {"Stage": "Loose Piece", "Size": "S"})

	def test_other_stage_keeps_the_variant(self):
		result, _check, _build, create = self._resolve(packing_doc(), is_stitched=False)
		self.assertEqual(result, PIECE)
		create.assert_not_called()

	def test_cancel_reverses_a_voucher_posted_before_loose_piece_holding(self):
		doc = packing_doc(docstatus=2, name="DC-OLD")
		with patch.object(frappe.db, "exists", return_value=None) as exists:
			result, *_mocks = self._resolve(doc)
		self.assertEqual(result, PIECE)
		exists.assert_called_once_with(
			"YRP Stock Ledger Entry",
			{"voucher_type": "YRP Delivery Challan", "voucher_no": "DC-OLD", "item": "EC-TEST-Loose Piece-S"},
		)

	def test_cancel_reverses_a_loose_piece_voucher_as_posted(self):
		with patch.object(frappe.db, "exists", return_value="SLE-1"):
			result, *_mocks = self._resolve(packing_doc(docstatus=2, name="DC-NEW"))
		self.assertEqual(result, "EC-TEST-Loose Piece-S")

	def test_missing_loose_piece_stage_fails_loudly(self):
		with self.assertRaises(frappe.ValidationError):
			self._resolve(packing_doc(), loose_piece_stage=None)

	def test_dc_completion_reads_the_delivery_challan_ipd(self):
		entry = frappe._dict(doctype="YRP Stock Entry", against="YRP Delivery Challan", against_id="DC-1")
		with patch.object(frappe.db, "get_value", return_value="IPD-DC") as get_value:
			self.assertEqual(loose_piece.get_production_detail(entry), "IPD-DC")
		get_value.assert_called_once_with("YRP Delivery Challan", "DC-1", "production_detail")


class TestFinishingDeliveryChallanQuantity(TestCase):
	def _item_list(self, quantity_field):
		data = {
			"data": {
				"data": {
					"Liver": {
						"colour": "Liver",
						"check_value": True,
						"set_combination": {"major_colour": "Liver"},
						"values": {"S": {"balance_dc": 3, "return_qty": 9}},
					}
				}
			}
		}
		ipd = frappe._dict(
			primary_item_attribute="Size",
			packing_attribute="Colour",
			is_set_item=0,
			stiching_out_stage="Piece",
		)
		with (
			patch.object(transactions.attribute_db, "get_value", return_value="IPD-1"),
			patch.object(frappe, "get_cached_doc", return_value=ipd),
			patch.object(transactions, "build_variant_attributes", return_value={}),
			patch.object(transactions, "get_or_create_variant", return_value=PIECE),
		):
			return transactions.get_delivery_challan_item_list("LOT-1", "EC-TEST", data, quantity_field)

	def test_loose_piece_dc_posts_the_typed_quantity(self):
		items = self._item_list("balance_dc")
		self.assertEqual(next(iter(items.values()))["qty"], 3)

	def test_conversion_reads_the_loose_piece_entry(self):
		items = self._item_list("return_qty")
		self.assertEqual(next(iter(items.values()))["qty"], 9)

	def test_unknown_quantity_field_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._item_list("balance")

	def test_conversion_creates_an_unflagged_dc_for_the_entered_quantity(self):
		work_order = MagicMock(supplier="S-1")
		real_get_doc = frappe.get_doc
		with (
			patch.object(
				frappe,
				"get_doc",
				side_effect=lambda *args, **kwargs: (
					work_order if args[:1] == ("YRP Work Order",) else real_get_doc(*args, **kwargs)
				),
			),
			patch.object(transactions, "_validate_work_order_context"),
			patch.object(transactions.frappe.db, "get_value", side_effect=plan_or_db(frappe.db.get_value)),
			patch.object(
				transactions.frappe.db,
				"get_single_value",
				side_effect=accepted_or_db(frappe.db.get_single_value),
			),
			patch.object(transactions, "create_delivery_challan", return_value="DC-1") as create_dc,
			patch.object(transactions, "return_items", return_value="GRN-1") as return_items,
		):
			created = transactions.convert_to_loose_piece_items(
				{"data": {}}, "WO-1", "LOT-1", "EC-TEST", "S-1"
			)
		self.assertEqual(created, {"delivery_challan": "DC-1", "goods_received_note": "GRN-1"})
		self.assertEqual(create_dc.call_args.args[0]["selected_type"], "balance")
		self.assertEqual(create_dc.call_args.kwargs["quantity_field"], "return_qty")
		self.assertEqual(return_items.call_args.args[4]["received_type"], "Accepted")

	def test_conversion_from_another_location_names_the_packing_unit(self):
		work_order = MagicMock(supplier="S-0171")
		with (
			patch.object(frappe, "get_doc", return_value=work_order),
			patch.object(transactions, "_validate_work_order_context"),
			patch.object(transactions, "create_delivery_challan") as create_dc,
			self.assertRaisesRegex(frappe.ValidationError, "already at S-0171"),
		):
			transactions.convert_to_loose_piece_items({"data": {}}, "WO-1", "LOT-1", "EC-TEST", "S-0172")
		create_dc.assert_not_called()
