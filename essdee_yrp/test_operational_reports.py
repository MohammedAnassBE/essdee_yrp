import importlib
import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.cutting.reports import get_item_data, get_multiccr


REPORT_CASES = {
	"cut_bundle_balance": {"lot": "__missing__"},
	"dc_report": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"dispatch_percentage_report": {"percentage": 75, "lot": ["__missing__"]},
	"finishing_plan_report": {"lot": "__missing__"},
	"grn_report": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"grn_summary": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"jobwork_issued_items": {"from_date": "2099-01-01", "to_date": "2099-01-02"},
	"lot_purchase_summary": {"lot": "__missing__"},
	"non_grn_received_items": {
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
	},
	"non_jobwork_issued_items": {
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
	},
	"purchase_order_itemwise": {"purchase_order": "__missing__"},
	"purchase_order_log": {"purchase_order": "__missing__"},
	"qualily_inspection_rft": {"lot": "__missing__"},
	"recently_modified_docs": {"doctype": "Lot", "days": 0},
	"vendor_bill_pending_report": {"department": "__missing__"},
	"work_order_pending_report": {"lot": ["__missing__"]},
	"work_order_report": {
		"based_on": "Date",
		"from_date": "2099-01-01",
		"to_date": "2099-01-02",
		"lot": "__missing__",
	},
}


class TestOperationalReports(IntegrationTestCase):
	def test_multiccr_accepts_historical_cutting_plan_payload(self):
		result = get_multiccr(lot_list=json.dumps(["F1024-54"]))
		self.assertIn("F1024-54", result["output_lots"])

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
				module = importlib.import_module(
					f"essdee_yrp.essdee_yrp.report.{report}.{report}"
				)
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
