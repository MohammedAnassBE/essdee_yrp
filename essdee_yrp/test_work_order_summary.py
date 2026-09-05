from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.work_order import (
	_get_work_order_debit_summary,
	_summarise_work_order_movements,
	get_work_order_summary,
)


class TestWorkOrderSummary(IntegrationTestCase):
	@patch("essdee_yrp.api.work_order.frappe.get_all")
	def test_movement_summary_groups_variants_and_uses_pending_balance(self, get_all):
		get_all.side_effect = [
			[("FABRIC-RED-24", "Fabric"), ("YARN-GREIGE", "Yarn")],
			[
				frappe._dict(parent="FABRIC-RED-24", attribute="Colour", attribute_value="Red", idx=1),
				frappe._dict(parent="FABRIC-RED-24", attribute="Dia", attribute_value="24 Dia", idx=2),
				frappe._dict(parent="YARN-GREIGE", attribute="Colour", attribute_value="Greige", idx=1),
			],
		]
		rows = [
			frappe._dict(item_variant="FABRIC-RED-24", qty=100, pending_quantity=25, uom="Kg"),
			frappe._dict(item_variant="FABRIC-RED-24", qty=20, pending_quantity=-2, uom="Kg"),
			frappe._dict(item_variant="YARN-GREIGE", qty=10, pending_quantity=15, uom="Kg"),
		]

		result = _summarise_work_order_movements(rows)

		self.assertEqual(len(result["rows"]), 2)
		fabric = next(row for row in result["rows"] if row["item_variant"] == "FABRIC-RED-24")
		self.assertEqual(fabric["item"], "Fabric")
		self.assertEqual(fabric["attributes"], [
			{"attribute": "Colour", "value": "Red"},
			{"attribute": "Dia", "value": "24 Dia"},
		])
		self.assertEqual(fabric["planned_qty"], 120)
		self.assertEqual(fabric["actual_qty"], 95)
		self.assertEqual(fabric["pending_qty"], 25)
		# Corrupt pending > planned data must never display a negative actual.
		yarn = next(row for row in result["rows"] if row["item_variant"] == "YARN-GREIGE")
		self.assertEqual(yarn["actual_qty"], 0)
		self.assertEqual(result["totals"], [{
			"uom": "Kg",
			"planned_qty": 130,
			"actual_qty": 95,
			"pending_qty": 40,
		}])

	@patch("essdee_yrp.api.work_order._get_work_order_debit_summary")
	@patch("essdee_yrp.api.work_order._summarise_work_order_movements")
	@patch("essdee_yrp.api.work_order.frappe.get_doc")
	def test_whitelisted_summary_checks_work_order_read_permission(self, get_doc, summarise, debits):
		wo = MagicMock()
		wo.name = "WO-TEST"
		wo.get.side_effect = lambda fieldname: {
			"deliverables": ["deliverable"],
			"receivables": ["receivable"],
		}[fieldname]
		get_doc.return_value = wo
		summarise.side_effect = ["deliverable-summary", "receivable-summary"]
		debits.return_value = ["debit-summary"]

		result = get_work_order_summary("WO-TEST")

		wo.check_permission.assert_called_once_with("read")
		self.assertEqual(result, {
			"work_order": "WO-TEST",
			"deliverables": "deliverable-summary",
			"receivables": "receivable-summary",
			"debits": ["debit-summary"],
		})

	@patch("essdee_yrp.api.work_order.frappe.get_list")
	@patch("essdee_yrp.api.work_order.frappe.has_permission", return_value=True)
	@patch("essdee_yrp.api.work_order.frappe.db.exists", return_value=True)
	def test_debit_summary_reports_document_lifecycle(self, _exists, _permission, get_list):
		get_list.return_value = [
			frappe._dict(name="WOD-1", status="Debit Requested", docstatus=0),
			frappe._dict(name="WOD-2", status="Approved", docstatus=1),
			frappe._dict(name="WOD-3", status="Approved", docstatus=2),
		]

		rows = _get_work_order_debit_summary("WO-TEST")

		self.assertEqual([row.status for row in rows], ["Draft", "Approved", "Cancelled"])
		get_list.assert_called_once()
