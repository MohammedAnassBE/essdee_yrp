from unittest import TestCase
from unittest.mock import patch

from frappe import _dict

from essdee_yrp.cutting.reports import (
	_accessible_laysheets,
	_readable_plan_work_order,
	get_bundles_by_cutter,
	get_item_data,
	get_report_permissions,
	group_laysheet_stats_by_parent,
	merge_multiccr_recut_rows,
	serialize_multiccr_panel_groups,
	serialize_multiccr_recut_summary,
)


class TestCuttingReportsWorkspace(TestCase):
	def test_work_order_report_data_requires_field_and_record_read_permission(self):
		plan = _dict(work_order="WO-SECRET")
		with patch(
			"essdee_yrp.cutting.reports.get_permitted_fields",
			return_value=["name", "item"],
		):
			self.assertIsNone(_readable_plan_work_order(plan))

		work_order = _dict(doctype="YRP Work Order", name="WO-SECRET")
		with (
			patch(
				"essdee_yrp.cutting.reports.get_permitted_fields",
				return_value=["name", "work_order"],
			),
			patch("essdee_yrp.cutting.reports.frappe.get_doc", return_value=work_order),
			patch("essdee_yrp.cutting.reports.frappe.has_permission", return_value=False),
		):
			self.assertIsNone(_readable_plan_work_order(plan))

	def test_accessible_laysheets_uses_permission_aware_get_list(self):
		rows = [_dict(name="CLS-ALLOWED")]
		with patch("essdee_yrp.cutting.reports.frappe.get_list", return_value=rows) as get_list:
			result = _accessible_laysheets(
				{"bundle_generated_date": "2026-10-03"},
				["name", "cutting_plan"],
			)

		self.assertEqual(result, rows)
		get_list.assert_called_once_with(
			"SD YRP Cutting LaySheet",
			filters={"bundle_generated_date": "2026-10-03"},
			fields=["name", "cutting_plan"],
			limit_page_length=0,
		)

	def test_report_tabs_follow_effective_doctype_permissions(self):
		def has_permission(doctype, ptype):
			return (doctype, ptype) == ("YRP Stock Ledger Entry", "read")

		with patch("essdee_yrp.cutting.reports.frappe.has_permission", side_effect=has_permission):
			permissions = get_report_permissions()

		self.assertFalse(permissions["daily-production"])
		self.assertFalse(permissions["cutting-plans"])
		self.assertFalse(permissions["daily-cut-sheet"])
		self.assertFalse(permissions["multi-ccr"])
		self.assertFalse(permissions["cutting-detail"])
		self.assertFalse(permissions["stock-balance"])

	def test_laysheets_with_null_and_blank_secondary_parent_stay_together(self):
		rows = [
			_dict(
				name="CLS-1",
				cutting_plan="CP-1",
				cutting_order=None,
				status="Label Printed",
				posting_date="2026-09-30",
			),
			_dict(
				name="CLS-2",
				cutting_plan="CP-1",
				cutting_order="",
				status="Bundles Generated",
				posting_date="2026-09-30",
			),
		]

		stats = group_laysheet_stats_by_parent(rows, "2026-09-30")

		self.assertEqual(list(stats), [("SD YRP Cutting Plan", "CP-1")])
		self.assertEqual(stats[("SD YRP Cutting Plan", "CP-1")]["names"], ["CLS-1", "CLS-2"])
		self.assertEqual(stats[("SD YRP Cutting Plan", "CP-1")]["bundle_count"], 2)
		self.assertEqual(stats[("SD YRP Cutting Plan", "CP-1")]["label_count"], 1)

	def test_bundle_grouping_preserves_cutter_and_laysheet(self):
		grouped = get_bundles_by_cutter(
			[{"name": "CLS-1"}, {"name": "CLS-2"}],
			{
				"CLS-1": [_dict(cutter="A", quantity=2)],
				"CLS-2": [_dict(cutter="B", quantity=3), _dict(cutter="A", quantity=1)],
			},
		)

		self.assertEqual(set(grouped), {"A", "B"})
		self.assertEqual(list(grouped["A"]), ["CLS-1", "CLS-2"])
		self.assertEqual(list(grouped["B"]), ["CLS-2"])

	def test_multiccr_panel_groups_and_recut_rows_are_json_ready(self):
		ccr = {
			"sizes": ["S", "M"],
			"marker_data": {
				"Front, Back": {
					("Navy", "Main"): {
						"received_weight": 12,
						"used_weight": 10,
						"balance_weight": 2,
						"total_pieces": 100,
						"reqd_weight": 0.12,
						"S": {"bits": 40},
						"M": {"bits": 60},
					}
				}
			},
		}
		groups = serialize_multiccr_panel_groups("CP-1", ccr)
		self.assertEqual(groups[0]["rows"][0]["piece_weight"], 0.1)
		self.assertEqual(groups[0]["totals"]["sizes"], {"S": 40, "M": 60})

		recut = {}
		merge_multiccr_recut_rows(
			recut,
			{
				"one": {"cloth_type": "Main", "colour": "Navy", "dia": "72", "shade": "A", "weight": 1.25, "no_of_rolls": 1},
				"two": {"cloth_type": "Main", "colour": "Navy", "dia": "72", "shade": "A", "weight": 0.75, "no_of_rolls": 2},
			},
		)
		summary = serialize_multiccr_recut_summary(recut)
		self.assertEqual(summary["totals"], {"weight": 2.0, "no_of_rolls": 3.0})

	def test_style_summary_uses_weighted_colour_averages(self):
		def lot_payload(size, used_weight, pieces, required_weight):
			return {
				"item": "ITEM-1",
				"completed_json": [
					{
						"items": [
							{
								"attributes": {"Colour": "Navy"},
								"item_keys": {"major_colour": "Navy"},
								"values": {size: pieces},
								"total_qty": pieces,
							}
						],
						"total_qty": {size: pieces},
					}
				],
				"total_qty": pieces,
				"cloth_details": [],
				"cloth_total": {"required": 0, "used": 0, "balance": 0, "received": 0},
				"panel_groups": [
					{
						"rows": [
							{
								"colour": "Navy",
								"used_weight": used_weight,
								"total_pieces": pieces,
								"required_weight": required_weight,
							}
						]
					}
				],
			}

		data = get_item_data(
			{
				"LOT-1": lot_payload("S", 10, 100, 0.12),
				"LOT-2": lot_payload("M", 5, 50, 0.18),
			}
		)["ITEM-1"]

		self.assertAlmostEqual(data["average_piece_weight_by_colour"]["Navy"], 0.1)
		self.assertAlmostEqual(data["average_required_weight_by_colour"]["Navy"], 0.14)
		self.assertEqual(data["completed_json"][0]["items"][0]["values"], {"S": 100, "M": 50})
