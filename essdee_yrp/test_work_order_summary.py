import inspect
import unittest
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.api import work_order


class TestWorkOrderSummaryReadModel(unittest.TestCase):
	@patch.object(frappe, "get_all")
	def test_deliverables_keep_exact_sources_and_received_types_separate(self, get_all):
		def metadata(doctype, **_kwargs):
			if doctype == "Item":
				return [
					frappe._dict(
						name="CLOTH-RED-32",
						item_name="Red Cloth 32",
						variant_of="CLOTH",
					)
				]
			if doctype == "Item Variant Attribute":
				return [
					frappe._dict(
						parent="CLOTH-RED-32",
						attribute="Colour",
						attribute_value="Red",
						idx=1,
					),
					frappe._dict(
						parent="CLOTH-RED-32",
						attribute="Dia",
						attribute_value="32 Dia",
						idx=2,
					),
				]
			raise AssertionError(doctype)

		get_all.side_effect = metadata
		rows = [
			frappe._dict(
				item_variant="CLOTH-RED-32",
				qty=100,
				pending_quantity=25,
				uom="Kg",
				source_grn="GRN-1",
				source_grn_item="GRN-ITEM-1",
				received_type="Accepted",
			),
			frappe._dict(
				item_variant="CLOTH-RED-32",
				qty=20,
				pending_quantity=-2,
				uom="Kg",
				source_grn="GRN-1",
				source_grn_item="GRN-ITEM-1",
				received_type="Accepted",
			),
			frappe._dict(
				item_variant="CLOTH-RED-32",
				qty=10,
				pending_quantity=15,
				uom="Kg",
				source_grn="GRN-2",
				source_grn_item="GRN-ITEM-2",
				received_type="Rejected",
			),
		]

		result = work_order._summarise_work_order_movements(
			rows,
			include_source=True,
		)

		self.assertEqual(len(result["rows"]), 2)
		accepted = next(
			row for row in result["rows"] if row["source_grn_item"] == "GRN-ITEM-1"
		)
		self.assertEqual(accepted["item"], "CLOTH")
		self.assertEqual(accepted["item_name"], "Red Cloth 32")
		self.assertEqual(
			accepted["attributes"],
			[
				{"attribute": "Colour", "value": "Red"},
				{"attribute": "Dia", "value": "32 Dia"},
			],
		)
		self.assertEqual(accepted["planned_qty"], 120)
		self.assertEqual(accepted["actual_qty"], 95)
		self.assertEqual(accepted["pending_qty"], 25)
		rejected = next(
			row for row in result["rows"] if row["source_grn_item"] == "GRN-ITEM-2"
		)
		self.assertEqual(rejected["received_type"], "Rejected")
		self.assertEqual(rejected["actual_qty"], 0)
		self.assertEqual(
			result["totals"],
			[
				{
					"uom": "Kg",
					"planned_qty": 130,
					"actual_qty": 95,
					"pending_qty": 40,
				}
			],
		)

	@patch.object(frappe, "get_all")
	def test_receivables_keep_uom_totals_and_planned_process_cost(self, get_all):
		get_all.side_effect = [
			[
				frappe._dict(name="CLOTH-OUT", item_name="Cloth Output", variant_of="CLOTH"),
				frappe._dict(name="PIECE-OUT", item_name="Piece Output", variant_of=None),
			],
			[],
		]
		rows = [
			frappe._dict(
				item_variant="CLOTH-OUT",
				qty=50,
				pending_quantity=20,
				uom="Kg",
				total_cost=125,
			),
			frappe._dict(
				item_variant="PIECE-OUT",
				qty=100,
				pending_quantity=40,
				uom="Nos",
				total_cost=75,
			),
		]

		result = work_order._summarise_work_order_movements(rows)

		self.assertEqual([row["uom"] for row in result["totals"]], ["Kg", "Nos"])
		self.assertEqual(result["planned_process_cost"], 200)
		self.assertEqual(
			{row["item_variant"]: row["planned_process_cost"] for row in result["rows"]},
			{"CLOTH-OUT": 125, "PIECE-OUT": 75},
		)

	@patch.object(work_order, "_get_work_order_valuation_summary")
	@patch.object(work_order, "_get_work_order_debit_summary")
	@patch.object(work_order, "_summarise_work_order_movements")
	@patch.object(frappe, "get_doc")
	def test_endpoint_checks_read_permission_and_combines_sections(
		self, get_doc, summarise, debits, valuation
	):
		wo = MagicMock()
		wo.name = "YRP-WO-1"
		wo.get.side_effect = lambda fieldname: {
			"deliverables": ["deliverable"],
			"receivables": ["receivable"],
		}[fieldname]
		get_doc.return_value = wo
		summarise.side_effect = [
			{"rows": ["issued"], "totals": [], "planned_process_cost": 0},
			{"rows": ["received"], "totals": [], "planned_process_cost": 250},
		]
		debits.return_value = [frappe._dict(name="WOD-1", debit_value=30, docstatus=1)]
		valuation.return_value = {"input_value": 100, "process_value": 40, "output_value": 140}

		result = work_order.get_work_order_summary("YRP-WO-1")

		wo.check_permission.assert_called_once_with("read")
		self.assertEqual(result["work_order"], "YRP-WO-1")
		self.assertEqual(result["deliverables"]["rows"], ["issued"])
		self.assertEqual(result["receivables"]["rows"], ["received"])
		self.assertEqual(result["planned_process_cost"], 250)
		self.assertEqual(result["debit_total"], 30)
		self.assertEqual(result["valuation"]["output_value"], 140)
		self.assertEqual(
			summarise.call_args_list[0].kwargs,
			{"include_source": True},
		)

	@patch.object(frappe, "get_list")
	@patch.object(frappe, "has_permission", return_value=True)
	@patch.object(frappe.db, "exists", return_value=True)
	def test_debit_summary_reports_document_lifecycle(
		self, _exists, _permission, get_list
	):
		get_list.return_value = [
			frappe._dict(name="WOD-1", status="Debit Requested", docstatus=0),
			frappe._dict(name="WOD-2", status="Approved", docstatus=1),
			frappe._dict(name="WOD-3", status="Approved", docstatus=2),
		]

		rows = work_order._get_work_order_debit_summary("YRP-WO-1")

		self.assertEqual([row.status for row in rows], ["Draft", "Approved", "Cancelled"])
		get_list.assert_called_once()

	@patch.object(frappe.db, "sql")
	def test_valuation_uses_only_active_submitted_grn_ledger_rows(self, sql):
		sql.return_value = [
			frappe._dict(input_value=120.5, output_value=175.75)
		]

		result = work_order._get_work_order_valuation_summary("YRP-WO-1")

		self.assertEqual(
			result,
			{
				"input_value": 120.5,
				"process_value": 55.25,
				"output_value": 175.75,
			},
		)
		query = sql.call_args.args[0]
		self.assertIn("tabYRP Stock Ledger Entry", query)
		self.assertIn("tabYRP Goods Received Note", query)
		self.assertIn("grn.docstatus = 1", query)
		self.assertIn("IFNULL(sle.is_cancelled, 0) = 0", query)
		self.assertIn("grn.against = 'YRP Work Order'", query)
		self.assertEqual(sql.call_args.args[1], {"work_order": "YRP-WO-1"})

	def test_legacy_summary_api_signature_remains_compatible(self):
		self.assertEqual(
			list(inspect.signature(work_order.fetch_summary_details).parameters),
			["doc_name", "production_detail"],
		)
