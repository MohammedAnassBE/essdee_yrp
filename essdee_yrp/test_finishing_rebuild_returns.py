from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing import rebuild

KEY = ("EC-TEST-Liver-S", (("major_colour", "Liver"),))


def return_grn(received_type, quantity=1, is_pack=0):
	row = frappe._dict(
		item_variant="EC-TEST-Liver-S",
		set_combination={"major_colour": "Liver"},
		quantity=quantity,
		received_type=received_type,
	)
	return frappe._dict(items=[row], is_pack=is_pack)


class TestRebuildReturnGrns(TestCase):
	def _apply(self, grn):
		plan = frappe._dict(return_grn_list='{"GRN-1": "21-10-2026"}', pack_return_list="{}")
		items = {KEY: rebuild._empty_finishing_row("EC-TEST-Liver-S", {"major_colour": "Liver"})}
		items[KEY]["accepted_qty"] = 20
		items[KEY]["dc_qty"] = 5
		rework = {}
		with (
			patch.object(frappe.db, "get_value", return_value=1),
			patch.object(frappe, "get_doc", return_value=grn),
		):
			rebuild._apply_return_grns(plan, items, rework, "Accepted", "Rejected")
		return items[KEY], rework.get(KEY)

	def test_rejected_return_keeps_its_rework_row(self):
		values, rework = self._apply(return_grn("Rejected"))
		self.assertEqual(values["rework_qty"], 1)
		self.assertEqual(values["accepted_qty"], 19)
		self.assertEqual(values["dc_qty"], 4)
		self.assertEqual(rework, {"quantity": 1, "reworked_quantity": 0, "rejected_qty": 1})

	def test_accepted_return_moves_to_loose_piece(self):
		values, rework = self._apply(return_grn("Accepted", quantity=2))
		self.assertEqual(values["return_qty"], 2)
		self.assertEqual(values["rework_qty"], 0)
		self.assertIsNone(rework)
