from importlib import import_module
from importlib.util import find_spec
from io import BytesIO
from unittest import TestCase
from unittest.mock import patch

import frappe
import openpyxl

MODULE = "essdee_yrp.finishing.web_reports"

REJECTION = {
	"types": ["Oil Mark", "Stain"],
	"report_detail": {
		"RW-1": {
			"date": "2026-10-02 10:00:00",
			"grn_number": "GRN-1",
			"lot": "LOT-1",
			"item": "TSHIRT",
			"types": {"Oil Mark": 5},
			"total": 5,
			"rejection_detail": {"Oil Mark-Red": {"items": []}},
		},
	},
}
REWORK = {
	"types": ["Oil Mark"],
	"report_detail": {
		"RW-2": {
			"date": "2026-10-03 08:00:00.125",
			"grn_number": "GRN-2",
			"lot": "LOT-2",
			"item": "POLO",
			"types": {"Oil Mark": 7},
			"rejection_detail": {"Oil Mark": 2},
			"rework_detail": {"Oil Mark-Navy-Top": {"items": []}},
		},
	},
}


def workbook_rows():
	content = frappe.local.response.filecontent
	sheet = openpyxl.load_workbook(BytesIO(content)).active
	return [list(row) for row in sheet.iter_rows(values_only=True)]


class TestFinishingWebReports(TestCase):
	def _reports(self):
		self.assertIsNotNone(find_spec(MODULE), "Finishing web report endpoints must exist")
		return import_module(MODULE)

	def test_report_endpoints_are_whitelisted_for_authenticated_users(self):
		reports = self._reports()
		for name in (
			"get_packing_dpr",
			"get_dispatch_report",
			"get_ironing_dpr",
			"get_rejection_details",
			"download_rejection_details",
			"get_rework_completion",
			"get_rework_details",
			"download_rework_details",
			"get_rework_groups",
		):
			with self.subTest(endpoint=name):
				endpoint = getattr(reports, name)
				self.assertIn(endpoint, frappe.whitelisted)
				self.assertNotIn(endpoint, frappe.guest_methods)

	def test_dispatch_report_has_no_unguarded_legacy_whitelisted_alias(self):
		source = import_module("essdee_yrp.finishing.reports")
		legacy = import_module(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan.sd_yrp_finishing_plan"
		)
		self.assertIs(legacy.get_finishing_dispatch_report, source.get_finishing_dispatch_report)
		self.assertNotIn(source.get_finishing_dispatch_report, frappe.whitelisted)

	def test_rejection_export_rebuilds_from_filters_with_frappe_15_columns(self):
		reports = self._reports()
		with patch(
			"essdee_yrp.finishing.report_sources.get_rejection_items", return_value=REJECTION
		) as source:
			reports.download_rejection_details("2026-10-01", "2026-10-31", lot="LOT-1")
		source.assert_called_once_with("2026-10-01", "2026-10-31", "LOT-1", None, None)
		self.assertEqual(frappe.local.response.filename, "rejection_details.xlsx")
		self.assertEqual(
			workbook_rows(),
			[
				["Series No", "Date", "GRN Number", "Lot", "Item", "Colour", "Oil Mark", "Stain", "Total"],
				["RW-1", "02-10-2026", "GRN-1", "LOT-1", "TSHIRT", "Red", 5, 0, 5],
			],
		)

	def test_rework_export_shows_pending_minus_rejection_per_type(self):
		reports = self._reports()
		with patch(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.get_rework_items",
			return_value=REWORK,
		):
			reports.download_rework_details(lot="LOT-2")
		self.assertEqual(frappe.local.response.filename, "rework_details.xlsx")
		self.assertEqual(
			workbook_rows(),
			[
				["Series No", "Date", "GRN Number", "Lot", "Item", "Colour", "Oil Mark"],
				["RW-2", "03-10-2026", "GRN-2", "LOT-2", "POLO", "Navy-Top", 5],
			],
		)

	def test_packing_dpr_passes_the_frappe_15_arguments(self):
		reports = self._reports()
		with patch(
			"essdee_yrp.finishing.reports.get_finishing_packed_details", return_value={"data": []}
		) as source:
			reports.get_packing_dpr(
				from_date="2026-10-01", to_date="2026-10-02", summary=1, lots=["LOT-1"], items=["TSHIRT"]
			)
		source.assert_called_once_with(
			date=None,
			lot_list=["LOT-1"],
			item_list=["TSHIRT"],
			from_date="2026-10-01",
			to_date="2026-10-02",
			summary=1,
		)

	def test_dispatch_report_requires_finishing_plan_and_grn_read_permissions(self):
		reports = self._reports()
		permissions = {
			("SD YRP Finishing Plan", "read"),
			("YRP Goods Received Note", "read"),
		}
		with (
			patch.object(
				frappe,
				"has_permission",
				side_effect=lambda doctype, ptype="read", **_kwargs: (doctype, ptype) in permissions,
			),
			patch(
				"essdee_yrp.finishing.reports.get_finishing_dispatch_report",
				return_value={"data": [{"lot": "LOT-1"}]},
			) as source,
		):
			self.assertEqual(
				reports.get_dispatch_report("2026-10-01", "2026-10-31", ["LOT-1"], ["TSHIRT"]),
				{"data": [{"lot": "LOT-1"}]},
			)
			source.assert_called_once_with("2026-10-01", "2026-10-31", ["LOT-1"], ["TSHIRT"])

		for missing in permissions:
			with self.subTest(missing=missing):
				with (
					patch.object(
						frappe,
						"has_permission",
						side_effect=lambda doctype, ptype="read", **_kwargs: (doctype, ptype)
						in (permissions - {missing}),
					),
					patch("essdee_yrp.finishing.reports.get_finishing_dispatch_report") as source,
					self.assertRaises(frappe.PermissionError),
				):
					reports.get_dispatch_report("2026-10-01", "2026-10-31")
				source.assert_not_called()

	def test_dispatch_report_uses_its_explicit_access_gate_for_stock_rows(self):
		reports = self._reports()
		permissions = {
			("SD YRP Finishing Plan", "read"),
			("YRP Goods Received Note", "read"),
		}

		def permitted_list(doctype, **_kwargs):
			if doctype == "YRP Stock Entry":
				raise frappe.PermissionError("Stock Entry permission must not become an undocumented requirement")
			return []

		with (
			patch.object(
				frappe,
				"has_permission",
				side_effect=lambda doctype, ptype="read", **_kwargs: (doctype, ptype) in permissions,
			),
			patch.object(frappe, "get_list", side_effect=permitted_list) as get_list,
			patch.object(frappe, "get_all", return_value=[]) as get_all,
		):
			self.assertEqual(reports.get_dispatch_report("2026-10-01", "2026-10-31"), {"data": [], "sizes": []})

		self.assertEqual(get_list.call_args_list[0].args[0], "YRP Goods Received Note")
		self.assertTrue(any(call.args[0] == "YRP Stock Entry" for call in get_all.call_args_list))
