from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.work_order_close import close_work_order


class TestWorkOrderClose(UnitTestCase):
	def test_selected_reason_is_stored_only_in_essdee_fields(self):
		with (
			patch.object(frappe.db, "get_value", return_value="Open"),
			patch.object(frappe.db, "set_value") as set_value,
			patch(
				"yrp.yrp.doctype.work_order.work_order.update_stock",
				return_value="Close Request",
			) as update_stock,
		):
			result = close_work_order(
				"WO-1",
				sd_close_reason="Others",
				close_other_reason="Production stopped",
				close_remarks="Reviewed",
			)

		update_stock.assert_called_once_with(
			"WO-1",
			close_reason=None,
			close_other_reason=None,
			close_remarks="Reviewed",
		)
		set_value.assert_called_once_with(
			"Work Order",
			"WO-1",
			{
				"sd_close_reason": "Others",
				"close_other_reason": "Production stopped",
			},
			update_modified=False,
		)
		self.assertEqual(result, {"status": "Close Request", "deducted_qty": 0.0})

	def test_base_desk_close_reason_argument_is_an_input_alias(self):
		with (
			patch.object(frappe.db, "get_value", return_value="Open"),
			patch.object(frappe.db, "set_value") as set_value,
			patch(
				"yrp.yrp.doctype.work_order.work_order.update_stock",
				return_value="Close Request",
			),
		):
			close_work_order("WO-1", close_reason="Sewing Shortage")

		self.assertEqual(
			set_value.call_args.args[2],
			{"sd_close_reason": "Sewing Shortage", "close_other_reason": ""},
		)

	def test_invalid_fixed_reason_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			close_work_order("WO-1", sd_close_reason="Arbitrary free text")
