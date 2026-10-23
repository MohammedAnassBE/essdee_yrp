import importlib
import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.cutting.reports import get_item_data, get_multiccr

REPORT_CASES = {
	"sd_yrp_cut_bundle_balance": {"lot": "__missing__"},
	"sd_yrp_dc_report": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"sd_yrp_dispatch_percentage_report": {"percentage": 75, "lot": ["__missing__"]},
	"sd_yrp_finishing_plan_report": {"lot": "__missing__"},
	"sd_yrp_grn_report": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"sd_yrp_grn_summary": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"sd_yrp_jobwork_issued_items": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"sd_yrp_lot_purchase_summary": {"lot": "__missing__"},
	"sd_yrp_non_grn_received_items": {
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
	},
	"sd_yrp_non_jobwork_issued_items": {
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
	},
	"sd_yrp_purchase_order_itemwise": {"purchase_order": "__missing__"},
	"sd_yrp_purchase_order_log": {"purchase_order": "__missing__"},
	"sd_yrp_qualily_inspection_rft": {"lot": "__missing__"},
	"sd_yrp_recently_modified_docs": {"doctype": "SD YRP Lot", "days": 0},
	"sd_yrp_vendor_bill_pending_report": {"department": "__missing__"},
	"sd_yrp_work_order_pending_report": {"lot": ["__missing__"]},
	"sd_yrp_work_order_report": {
		"based_on": "Date",
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
		"lot": "__missing__",
	},
}


class TestOperationalReports(IntegrationTestCase):
	def test_multiccr_accepts_historical_cutting_plan_payload(self):
		if not frappe.db.exists("SD YRP Cutting Plan", "CP-2608-00006"):
			self.skipTest("Historical cutting-plan parity runs after data migration")
		result = get_multiccr(lot_list=json.dumps(["F1024-54"]))
		self.assertIn("F1024-54", result["output_lots"])

	def test_multiccr_loads_laysheets_without_full_documents(self):
		lot = frappe.db.get_value(
			"SD YRP Cutting Plan",
			{"docstatus": 1, "lot": ["in", frappe.get_all("SD YRP Lot", {"production_detail": ["is", "set"]}, pluck="name")]},
			"lot",
		)
		if not lot:
			self.skipTest("No submitted cutting plan with a production lot")
		original_get_doc = frappe.get_doc
		with patch.object(frappe, "get_doc", wraps=original_get_doc) as get_doc:
			result = get_multiccr(lot_list=json.dumps([lot]))
		self.assertIn(lot, result["output_lots"])
		loaded = {call.args[0] for call in get_doc.call_args_list if call.args and isinstance(call.args[0], str)}
		self.assertNotIn("SD YRP Cutting LaySheet", loaded)
		self.assertNotIn("SD YRP Recut and Print Panel", loaded)

	def test_ccr_laysheet_rows_match_documents(self):
		from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
			CCR_LAYSHEET_CHILDREN,
			get_ccr_laysheets,
		)

		laysheet = frappe.db.get_value(
			"SD YRP Cutting LaySheet", {"status": "Label Printed", "cutting_plan": ["is", "set"]}, "name"
		)
		if not laysheet:
			self.skipTest("No label-printed lay sheet")
		document = frappe.get_doc("SD YRP Cutting LaySheet", laysheet)
		rows = {row.name: row for row in get_ccr_laysheets(document.cutting_plan, include_bundles=True)}
		self.assertEqual(rows[laysheet].calculated_parts, document.calculated_parts)
		for parentfield, (_doctype, fields) in CCR_LAYSHEET_CHILDREN.items():
			expected = [[child.get(field) for field in fields] for child in document.get(parentfield)]
			actual = [[child.get(field) for field in fields] for child in rows[laysheet][parentfield]]
			self.assertEqual(actual, expected, parentfield)

	def test_multiccr_item_merge_accepts_different_size_ranges(self):
		def lot_payload(size, quantity):
			return {
				"item": "Runtime Item",
				"completed_json": [
					{
						"items": [
							{
								"attributes": {"Colour": "Blue"},
								"values": {size: quantity},
								"total_qty": quantity,
							}
						],
						"total_qty": {size: quantity},
					}
				],
				"total_qty": quantity,
				"cloth_details": [],
				"cloth_total": {
					"required": 0,
					"used": 0,
					"balance": 0,
					"received": 0,
				},
			}

		result = get_item_data(
			{
				"LOT-1": lot_payload("70 cm", 2),
				"LOT-2": lot_payload("75 cm", 3),
			}
		)
		payload = result["Runtime Item"]["completed_json"][0]
		self.assertEqual(payload["total_qty"], {"70 cm": 2, "75 cm": 3})
		self.assertEqual(
			payload["items"][0]["values"],
			{"70 cm": 2, "75 cm": 3},
		)

	def test_migrated_reports_execute_against_f16_schema(self):
		for report, filters in REPORT_CASES.items():
			with self.subTest(report=report):
				module = importlib.import_module(f"essdee_yrp.essdee_yrp.report.{report}.{report}")
				result = module.execute(frappe._dict(filters))
				columns, data = result[:2]
				self.assertIsInstance(columns, list)
				self.assertIsInstance(data, list)

	def test_report_metadata_is_essdee_owned_and_has_no_legacy_doctype(self):
		root = Path(frappe.get_app_path("essdee_yrp")) / "essdee_yrp" / "report"
		for report in REPORT_CASES:
			with self.subTest(report=report):
				metadata = json.loads((root / report / f"{report}.json").read_text())
				self.assertEqual(metadata["module"], "Essdee YRP")
				self.assertNotEqual(metadata.get("ref_doctype"), "Vendor Bill Tracking")
