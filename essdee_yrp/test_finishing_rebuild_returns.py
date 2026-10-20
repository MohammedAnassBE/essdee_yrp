from unittest import TestCase
from unittest.mock import MagicMock, patch

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


class TestEmptyDispatchSelection(TestCase):
	def test_saving_with_no_quantity_keeps_an_empty_selection(self):
		doc = frappe.new_doc("SD YRP Finishing Plan Dispatch")
		doc.finishing_items = "[]"
		doc.before_validate()
		self.assertEqual(doc.finishing_plan_dispatch_items, [])
		self.assertEqual(doc.finishing_items, "[]")


class TestReturnReworkSource(TestCase):
	def test_finishing_return_with_a_rework_type_opens_rework(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import sd_yrp_grn_rework_item as rework_item

		row = frappe._dict(
			name="row-1", quantity=1, received_type="Misstitch", row_index="0", item_variant="EC-TEST-Liver-S"
		)
		grn = frappe._dict(
			docstatus=1, is_return=1, from_finishing=1, items=[row], name="GRN-1", to_warehouse="S-1"
		)
		rework = MagicMock()
		with (
			patch.object(rework_item, "_received_type_defaults", return_value=("Accepted", "Rejected")),
			patch.object(frappe.db, "exists", return_value=None),
			patch.object(rework_item, "_actual_receipt_warehouse", return_value="S-1"),
			patch.object(frappe, "new_doc", return_value=rework),
		):
			rework_item.sync_grn_rework(grn)
		rework.insert.assert_called_once()
		self.assertEqual(rework.append.call_args.args[1]["received_type"], "Misstitch")


class TestReturnReworkRowFormat(TestCase):
	def test_rework_row_stores_its_set_combination_as_json(self):
		from essdee_yrp.finishing import grn as finishing_grn

		plan = MagicMock()
		detail = frappe._dict(item_variant="EC-TEST-Liver-S", set_combination='{"major_colour": "Liver"}')
		plan.get.side_effect = lambda field, default=None: {"finishing_plan_details": [detail]}.get(field, [])
		row = frappe._dict(
			item_variant="EC-TEST-Liver-S",
			set_combination={"major_colour": "Liver"},
			quantity=1,
			received_type="Misstitch",
		)
		grn = frappe._dict(items=[row], name="GRN-1", is_pack=0, from_finishing=1)
		with (
			patch.object(finishing_grn, "_received_type_defaults", return_value=("Accepted", "Rejected")),
			patch.object(finishing_grn, "_update_finishing_list_field"),
		):
			finishing_grn._update_return_receipt(plan, grn, cancelled=False)
		rework_rows = next(
			call.args[1]
			for call in plan.set.call_args_list
			if call.args[0] == "finishing_plan_reworked_details"
		)
		set_combination = rework_rows[0]["set_combination"]
		self.assertIsInstance(set_combination, str)
		self.assertEqual(frappe.parse_json(set_combination), {"major_colour": "Liver"})
