"""Desk projections must preserve the Finishing /web report values."""

import json
from importlib import import_module
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing import web_reports

ROOT = Path(__file__).parent / "essdee_yrp"
REPORTS = {
	"dispatch": "SD YRP Finishing Plan Dispatch Details",
	"packing": "SD YRP Finishing Plan DPR",
	"ironing": "SD YRP Finishing Plan Ironing Report",
	"rejection": "SD YRP Rejection Details",
	"completion": "SD YRP Rework Completion Report",
	"groups": "SD YRP Rework Group Details",
}


def desk_report(key):
	name = frappe.scrub(REPORTS[key])
	return import_module(f"essdee_yrp.essdee_yrp.report.{name}.{name}")


class TestFinishingDeskReports(TestCase):
	def setUp(self):
		self.permission = patch.object(frappe, "has_permission", return_value=True)
		self.permission.start()
		self.addCleanup(self.permission.stop)

	def test_packing_rows_equal_api_rows_in_daily_and_summary_modes(self):
		# Removing a size, changing a total, or dropping summary filters must fail.
		sample = {
			"data": [
				{
					"date": "2026-10-01",
					"lot": "LOT-1",
					"item": "TEE",
					"sizes": ["S", "M"],
					"size_qty": {"S": 12, "M": 6},
					"pieces_per_box": "Mixed",
					"dynamic_ratio_packing": 1,
					"total_boxes": 3,
					"total_pieces": 18,
				}
			],
			"sizes": ["S", "M"],
		}
		for filters in (
			{"date": "2026-10-01"},
			{
				"summary": 1,
				"from_date": "2026-10-01",
				"to_date": "2026-10-02",
				"lots": ["LOT-1"],
				"items": ["TEE"],
			},
		):
			with (
				self.subTest(filters=filters),
				patch(
					"essdee_yrp.finishing.reports.get_finishing_packed_details", return_value=sample
				) as source,
			):
				api = web_reports.get_packing_dpr(**filters)
				columns, rows = desk_report("packing").execute(filters)
				self.assertEqual(source.call_args_list[0], source.call_args_list[1])
				self.assertEqual([{k: row[k] for k in api["data"][0]} for row in rows], api["data"])
				self.assertEqual(
					[rows[0][c["fieldname"]] for c in columns if c["label"] in ("S", "M")], [12, 6]
				)

	def test_dispatch_preserves_packed_dispatched_and_negative_differences(self):
		sample = {
			"data": [
				{
					"lot": "LOT-1",
					"item": "TEE",
					"sizes": ["S", "M"],
					"packed_qty": {"S": 2, "M": 1},
					"dispatched_qty": {"S": 3},
					"pieces_per_box": 6,
					"packed_total_boxes": 3,
					"packed_total_pieces": 18,
					"dispatched_total_boxes": 3,
					"dispatched_total_pieces": 18,
				}
			],
			"sizes": ["S", "M"],
		}
		filters = {"from_date": "2026-10-01", "to_date": "2026-10-31", "lots": ["LOT-1"], "items": ["TEE"]}
		with patch(
			"essdee_yrp.finishing.reports.get_finishing_dispatch_report", return_value=sample
		) as source:
			api = web_reports.get_dispatch_report(**filters)
			columns, rows = desk_report("dispatch").execute(filters)
			self.assertEqual(source.call_args_list[0], source.call_args_list[1])
		self.assertEqual(
			[rows[0][key] for key in ("lot", "item", "pieces_per_box")],
			[api["data"][0][key] for key in ("lot", "item", "pieces_per_box")],
		)
		self.assertEqual([row["type"] for row in rows], ["Packed", "Dispatched", "Diff"])
		self.assertEqual(
			[[row[c["fieldname"]] for c in columns if c["label"] in ("S", "M")] for row in rows],
			[[2, 1], [3, 0], [-1, 1]],
		)
		self.assertEqual([row["total_pieces"] for row in rows], [18, 18, 0])

	def test_ironing_rows_equal_api_rows_with_date_lot_and_part_context(self):
		sample = [
			{
				"date": "2026-10-02",
				"lot": "LOT-1",
				"item": "SET",
				"attributes": ["Part", "Colour"],
				"primary_attributes": ["S", "M"],
				"rows": [{"s_no": 1, "part": "Top", "colour": "Red", "S": 4, "M": 0, "total_qty": 4}],
			}
		]
		for filters in (
			{"date": "2026-10-02"},
			{
				"summary": 1,
				"from_date": "2026-10-01",
				"to_date": "2026-10-03",
				"lots": ["LOT-1"],
				"items": ["SET"],
			},
		):
			with (
				self.subTest(filters=filters),
				patch("essdee_yrp.finishing.report_sources.get_ironing_dpr", return_value=sample) as source,
			):
				api = web_reports.get_ironing_dpr(**filters)
				columns, rows = desk_report("ironing").execute(filters)
				self.assertEqual(source.call_args_list[0], source.call_args_list[1])
			self.assertEqual([{key: row[key] for key in api[0]["rows"][0]} for row in rows], api[0]["rows"])
			self.assertEqual(
				[rows[0][key] for key in ("date", "lot", "item")], ["2026-10-02", "LOT-1", "SET"]
			)
			self.assertEqual([rows[0][c["fieldname"]] for c in columns if c["label"] in ("S", "M")], [4, 0])

	def test_rejection_summary_rows_equal_api_series_and_type_totals(self):
		from essdee_yrp.test_finishing_web_reports import REJECTION

		filters = {
			"start_date": "2026-10-01",
			"end_date": "2026-10-31",
			"lot": "LOT-1",
			"item": "TSHIRT",
			"colour": "Red",
		}
		with patch(
			"essdee_yrp.finishing.report_sources.get_rejection_items", return_value=REJECTION
		) as source:
			api = web_reports.get_rejection_details(**filters)
			columns, rows = desk_report("rejection").execute(filters)
			self.assertEqual(source.call_args_list[0], source.call_args_list[1])
		self.assertEqual(
			[{key: row[key] for key in api["report_detail"]["RW-1"]} for row in rows],
			list(api["report_detail"].values()),
		)
		self.assertEqual((rows[0]["series"], rows[0]["colour"]), ("RW-1", "Red"))
		self.assertEqual([rows[0][c["fieldname"]] for c in columns if c["label"] in api["types"]], [5, 0])

	def test_rejection_displays_each_group_size_and_quantity_without_repeating_totals(self):
		sample = {
			"types": ["Oil Mark", "Stain"],
			"report_detail": {
				"RW-1": {
					"date": "2026-10-02", "grn_number": "GRN-1", "lot": "LOT-1", "item": "TEE",
					"size": "Garment Size", "types": {"Oil Mark": 5, "Stain": 4}, "total": 9,
					"rejection_detail": {
						"Oil Mark-Red": {"items": [
							{"Garment Size": "S", "rejected_qty": 2, "received_type": "Oil Mark"},
							{"Garment Size": "M", "rejected_qty": 3, "received_type": "Oil Mark"},
						]},
						"Stain-Blue": {"items": [
							{"Garment Size": "L", "rejected_qty": 4, "received_type": "Stain"},
						]},
					},
				},
			},
		}
		with patch("essdee_yrp.finishing.report_sources.get_rejection_items", return_value=sample):
			columns, rows = desk_report("rejection").execute({
				"start_date": "2026-10-01", "end_date": "2026-10-31",
			})
		visible = {column["label"]: column["fieldname"] for column in columns}
		self.assertTrue({"Rejection Group", "Size", "Rejected Qty"}.issubset(visible))
		self.assertEqual([
			[row.get(visible[label]) for label in ("Rejection Group", "Size", "Rejected Qty")]
			for row in rows[1:]
		], [["Oil Mark-Red", "S", 2], ["Oil Mark-Red", "M", 3], ["Stain-Blue", "L", 4]])
		self.assertEqual([row["colour"] for row in rows[1:]], ["Red", "Red", "Blue"])
		self.assertTrue(all(row["series"] == "RW-1" and row["lot"] == "LOT-1" for row in rows))
		for label, expected in (("Oil Mark", 5), ("Stain", 4), ("Total", 9)):
			self.assertEqual(sum(row.get(visible[label], 0) for row in rows), expected)

	def test_completion_rows_equal_api_colour_type_and_size_values(self):
		sample = {
			"primary_values": ["S", "M"],
			"types": ["Accepted"],
			"is_set_item": 1,
			"set_attr": "Part",
			"data": {
				"Red(Navy)": {
					"part": "Top",
					"values": {"S": {"Accepted": 4}},
					"type_wise_total": {"Accepted": 4},
					"size_wise_total": {"S": 4},
					"colour_total": {"total": 4},
				}
			},
		}
		with patch(
			"essdee_yrp.finishing.report_sources.get_rework_completion", return_value=sample
		) as source:
			api = web_reports.get_rework_completion("LOT-1", "Ironing")
			columns, rows, *unused = desk_report("completion").execute({"lot": "LOT-1", "process": "Ironing"})
			self.assertEqual(source.call_args_list[0], source.call_args_list[1])
		self.assertEqual(
			[(row["colour"], row["part"], row["type"], row["total"]) for row in rows if row["type"] != "Total"],
			[("Red(Navy)", "Top", "Accepted", api["data"]["Red(Navy)"]["type_wise_total"]["Accepted"])],
		)
		self.assertEqual([rows[0][c["fieldname"]] for c in columns if c["label"] in ("S", "M")], [4, 0])

	def test_completion_displays_colour_subtotals_and_overall_reworked_pieces(self):
		sample = {
			"primary_values": ["S", "M"], "types": ["Accepted", "Repaired"],
			"is_set_item": 1, "set_attr": "Part",
			"data": {
				"Red(Navy)": {
					"part": "Top", "values": {"S": {"Accepted": 4, "Repaired": 2}, "M": {"Repaired": 3}},
					"type_wise_total": {"Accepted": 4, "Repaired": 5},
					"size_wise_total": {"S": 6, "M": 3}, "colour_total": {"total": 9},
				},
				"Blue(Navy)": {
					"part": "Bottom", "values": {"M": {"Accepted": 7}},
					"type_wise_total": {"Accepted": 7},
					"size_wise_total": {"M": 7}, "colour_total": {"total": 7},
				},
			},
		}
		with patch("essdee_yrp.finishing.report_sources.get_rework_completion", return_value=sample):
			result = desk_report("completion").execute({"lot": "LOT-1", "process": "Ironing"})
		columns, rows = result[:2]
		self.assertEqual([row["type"] for row in rows], ["Accepted", "Repaired", "Total"] * 2)
		sizes = [column["fieldname"] for column in columns if column["label"] in ("S", "M")]
		self.assertEqual([
			[row["colour"], row["part"], *[row[size] for size in sizes], row["total"]]
			for row in rows if row["type"] == "Total"
		], [["Red(Navy)", "Top", 6, 3, 9], ["Blue(Navy)", "Bottom", 0, 7, 7]])
		self.assertEqual(result[4], [{
			"label": "Reworked Pieces", "value": 16, "datatype": "Float", "indicator": "Green",
		}])

	def test_empty_completion_has_zero_reworked_pieces_and_no_subtotal_rows(self):
		with patch("essdee_yrp.finishing.report_sources.get_rework_completion", return_value={}):
			result = desk_report("completion").execute({"lot": "LOT-1", "process": "Ironing"})
		self.assertEqual(result[1], [])
		self.assertEqual(result[4][0]["value"], 0)

	def test_group_rows_equal_api_for_pending_and_completed_rework(self):
		for show_reworked in (0, 1):
			with self.subTest(show_reworked=show_reworked):
				sample = {
					"groups": {
						"TEE/LOT-1": {
							"item": "TEE",
							"lot": "LOT-1",
							"sizes": ["S", "M"],
							"is_set_item": 0,
							"rows": [
								{
									"lot": "LOT-1",
									"colour": "Red",
									"part": None,
									"grn_number": "GRN-1",
									"received_type": "Stain",
									"received": {"S": 7 if show_reworked else 5},
									"rejection": {"S": 1},
									"reworked": {"S": 2},
									"items": [],
								}
							],
						}
					},
					"permissions": {"can_write": True},
				}
				filters = {"lot": "LOT-1", "item": "TEE", "colour": "Red", "show_reworked": show_reworked}
				with patch(
					"essdee_yrp.finishing.report_sources.get_rework_group_items", return_value=sample
				) as source:
					api = web_reports.get_rework_groups(**filters)
					columns, rows = desk_report("groups").execute(filters)
					self.assertEqual(source.call_args_list[0], source.call_args_list[1])
				self.assertEqual(
					[{key: row[key] for key in api["groups"]["TEE/LOT-1"]["rows"][0]} for row in rows],
					api["groups"]["TEE/LOT-1"]["rows"],
				)
				self.assertEqual(rows[0]["total"], 7 if show_reworked else 5)
				self.assertEqual(
					[rows[0][c["fieldname"]] for c in columns if c["label"] in ("S", "M")],
					[7 if show_reworked else 5, 0],
				)

	def test_each_report_rejects_missing_web_page_read_permissions(self):
		checks = {
			"dispatch": ["SD YRP Finishing Plan", "YRP Goods Received Note"],
			"packing": ["SD YRP Finishing Plan", "YRP Goods Received Note"],
			"ironing": ["SD YRP Finishing Plan", "YRP Delivery Challan"],
			"rejection": ["SD YRP GRN Rework Item"],
			"completion": ["SD YRP GRN Rework Item"],
			"groups": ["SD YRP GRN Rework Item"],
		}
		for key, doctypes in checks.items():
			for denied in doctypes:
				with (
					self.subTest(report=key, denied=denied),
					patch.object(frappe, "has_permission", side_effect=lambda dt, *a, **kw: dt != denied),
					self.assertRaises(frappe.PermissionError),
				):
					desk_report(key).execute({})

	def test_reference_doctype_does_not_block_existing_web_reader_roles(self):
		from frappe.permissions import get_role_permissions

		from essdee_yrp.finishing.web_workspace import REPORTS as web_pages

		keys = {
			"dispatch": "dispatch_report",
			"packing": "packing_dpr",
			"ironing": "ironing_dpr",
			"rejection": "rejection_details",
			"completion": "rework_completion",
		}
		for key, name in REPORTS.items():
			slug = frappe.scrub(name)
			meta = json.loads((ROOT / "report" / slug / f"{slug}.json").read_text())
			checks = web_pages[keys[key]][1] if key in keys else (("SD YRP GRN Rework Item", "read"),)
			for role in (
				"System Manager",
				"Stock User",
				"Store User",
				"Production Planner",
				"Merch User",
				"Accounts User",
				"AI Bot",
			):
				with (
					self.subTest(report=name, role=role),
					patch.object(frappe, "get_roles", return_value=[role, "All", "Desk User"]),
				):

					def permissions(doctype):
						return get_role_permissions(
							frappe.get_meta(doctype), user="finishing-desk-role-test", debug=True
						)

					if not all(permissions(doctype).get(ptype) for doctype, ptype in checks):
						continue
					self.assertIn(role, [row["role"] for row in meta["roles"]])
					self.assertTrue(permissions(meta["ref_doctype"]).get("report"))

	def test_report_metadata_and_finishing_workspace_resolve_all_six_reports(self):
		workspace = json.loads((ROOT / "workspace/finishing/finishing.json").read_text())
		links = {link.get("link_to") for link in workspace["links"] if link.get("link_type") == "Report"}
		self.assertTrue(set(REPORTS.values()).issubset(links))
		for key, name in REPORTS.items():
			with self.subTest(report=name):
				folder = ROOT / "report" / frappe.scrub(name)
				meta = json.loads((folder / f"{frappe.scrub(name)}.json").read_text())
				self.assertEqual(
					(meta["name"], meta["report_type"], meta["module"]), (name, "Script Report", "Essdee YRP")
				)
				self.assertEqual(
					meta["ref_doctype"],
					"SD YRP GRN Rework Item"
					if key in ("rejection", "completion", "groups")
					else "YRP Delivery Challan"
					if key == "ironing"
					else "YRP Goods Received Note",
				)
				self.assertTrue((folder / f"{frappe.scrub(name)}.js").exists())
