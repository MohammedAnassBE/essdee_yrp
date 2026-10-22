import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.finishing.alternative import create_alternative_fp
from essdee_yrp.finishing.alternative_checks import throw_alternative_plan_issues

FINISHING_PLAN = "FP-2526-00237"
ALTERNATIVE_ITEM = "Casual Designer Vest - 4"
PRODUCTION_DETAIL = "Casual Designer Vest - 4-18"
LOT_NAME = "E2E-ALT-CHECKS"


class TestAlternativePlanChecks(FrappeTestCase):
	def test_issues_are_raised_as_one_bulleted_message(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			throw_alternative_plan_issues(["First problem", "Second problem"])
		self.assertEqual(
			str(raised.exception),
			"The Alternative Plan cannot be created yet. Fix the following:"
			"<br>• First problem<br>• Second problem",
		)
		throw_alternative_plan_issues([])

	def test_every_missing_prerequisite_is_listed_in_one_error(self):
		"""An E2E plan whose alternative lacks several prerequisites reports all of them at once."""
		if not frappe.db.exists("SD YRP Finishing Plan", FINISHING_PLAN) or not frappe.db.exists(
			"YRP Item Production Detail", PRODUCTION_DETAIL
		):
			self.skipTest("E2E Finishing Plan or alternative Item Production Detail is unavailable")
		source_item = frappe.db.get_value("SD YRP Finishing Plan", FINISHING_PLAN, "item")
		balance = frappe.get_doc("SD YRP Finishing Plan", FINISHING_PLAN).get_finishing_plans()
		available = balance["finishing_qty"]["data"]["Liver"]["values"]["S"]["balance"]
		quantities = {
			"Liver": {"check_value": 1, "values": {"S": {"conversion_qty": available + 5}}},
			"Cool Grey": {"check_value": 1, "values": {"S": {"conversion_qty": 1}}},
		}
		frappe.clear_messages()

		with self.assertRaises(frappe.ValidationError) as raised:
			create_alternative_fp(
				doc_name=FINISHING_PLAN,
				alternative_item=ALTERNATIVE_ITEM,
				production_detail=PRODUCTION_DETAIL,
				lot_name=LOT_NAME,
				qty_details={"data": {"data": quantities}},
			)

		message = str(raised.exception)
		for expected in (
			f"• Liver / S: converting {available + 5:g}, but only {available:g} is available",
			f"• Colour Cool Grey is not in Item Production Detail {PRODUCTION_DETAIL}",
			f"• Colour Liver is not in Item Production Detail {PRODUCTION_DETAIL}",
			f"• Item {ALTERNATIVE_ITEM} is not configured as an alternative of {source_item}",
		):
			self.assertIn(expected, message)
		self.assertEqual(len([row for row in frappe.message_log if row]), 1)
		self.assertFalse(frappe.db.exists("SD YRP Lot", {"lot_name": LOT_NAME}))
