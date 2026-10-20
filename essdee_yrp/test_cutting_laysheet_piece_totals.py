from types import SimpleNamespace
from unittest import TestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	SDYRPCuttingLaySheet,
)


def laysheet(total_pieces, is_manual_entry=0, bundles=()):
	return SimpleNamespace(
		is_manual_entry=is_manual_entry,
		total_no_of_pieces=total_pieces,
		total_used_weight=0,
		piece_weight=0,
		cutting_laysheet_bundles=[SimpleNamespace(quantity=qty) for qty in bundles],
	)


class TestCuttingLaySheetPieceTotals(TestCase):
	def test_marker_lay_recomputes_pieces_after_ply_edit(self):
		doc = laysheet(total_pieces=125)
		SDYRPCuttingLaySheet.set_piece_totals(doc, total_bits=10, ratio_sum=25, used_weight=29.325)
		self.assertEqual(doc.total_no_of_pieces, 250)
		self.assertEqual(doc.total_used_weight, 29.325)
		self.assertAlmostEqual(doc.piece_weight, 29.325 / 250)

	def test_manual_lay_counts_bundle_pieces(self):
		doc = laysheet(total_pieces=0, is_manual_entry=1, bundles=(30, 20))
		SDYRPCuttingLaySheet.set_piece_totals(doc, total_bits=0, ratio_sum=0, used_weight=10)
		self.assertEqual(doc.total_no_of_pieces, 50)
		self.assertAlmostEqual(doc.piece_weight, 0.2)

	def test_lay_without_pieces_clears_old_piece_weight(self):
		doc = laysheet(total_pieces=250)
		doc.piece_weight = 0.1173
		SDYRPCuttingLaySheet.set_piece_totals(doc, total_bits=0, ratio_sum=25, used_weight=29.325)
		self.assertEqual((doc.total_no_of_pieces, doc.piece_weight), (0, 0))


class TestLaySheetRevertGuard(TestCase):
	def test_bundles_moved_by_any_later_voucher_block_revert(self):
		from unittest.mock import patch

		import frappe

		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
			has_moved_bundles,
		)

		with patch.object(frappe.db, "sql", return_value=[("CBML-LATER",)]) as sql:
			self.assertTrue(has_moved_bundles("CLS-1"))
		query, values = sql.call_args.args
		self.assertIn("transformed = 1", query)
		self.assertIn("own.is_collapsed = 1", query)
		self.assertEqual(values, {"laysheet": "CLS-1"})
		with patch.object(frappe.db, "sql", return_value=[]):
			self.assertFalse(has_moved_bundles("CLS-1"))

	def test_cancel_is_blocked_after_bundles_moved(self):
		from unittest.mock import MagicMock, patch

		import frappe

		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as module

		doc = MagicMock(status="Label Printed", goods_received_note="GRN-1")
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_roles", return_value=["System Manager"]),
			patch.object(module, "_lock_cutting_laysheet"),
			patch.object(module, "has_moved_bundles", return_value=True),
			patch.object(module, "update_cloth_stock") as update_cloth_stock,
			self.assertRaisesRegex(frappe.ValidationError, "moved"),
		):
			module.cancel_laysheet("CLS-1")
		update_cloth_stock.assert_not_called()


class TestLaySheetCancelRecalculation(TestCase):
	def test_cancelled_status_is_saved_before_the_plan_recalculates(self):
		from unittest.mock import MagicMock, patch

		import frappe

		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as module
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as plan_module

		doc = MagicMock(status="Label Printed", goods_received_note=None, cutting_plan="CP-1")
		calls = []
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(frappe, "get_roles", return_value=["System Manager"]),
			patch.object(module, "_lock_cutting_laysheet"),
			patch.object(module, "has_moved_bundles", return_value=False),
			patch.object(
				module,
				"_save_laysheet_terminal_transition",
				side_effect=lambda d: calls.append(("save", d.status)),
			),
			patch.object(
				plan_module, "calculate_laysheets", side_effect=lambda cp: calls.append(("calc", cp))
			),
			patch.object(module, "update_cutting_plan_dates"),
		):
			module.cancel_laysheet("CLS-1")
		self.assertEqual(calls, [("save", "Cancelled"), ("calc", "CP-1")])

	def test_plan_recalculation_is_enqueued_after_commit(self):
		from unittest.mock import patch

		import frappe

		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan import sd_yrp_cutting_plan as plan_module

		with (
			patch.object(plan_module, "_get_submitted_cutting_plan"),
			patch.object(plan_module, "get_phantom_panels", return_value=[]),
			patch.object(frappe, "enqueue") as enqueue,
		):
			plan_module.calculate_laysheets("CP-1")
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
