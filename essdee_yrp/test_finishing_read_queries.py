from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.report.sd_yrp_finishing_plan_report import sd_yrp_finishing_plan_report as report


def typed(rows):
	return [[(key, type(value), value) for key, value in row.items()] for row in rows]


class TestFinishingReadQueries(TestCase):
	def test_report_reads_only_used_children_with_identical_rows(self):
		if not frappe.db.exists("SD YRP Finishing Plan", {"lot": "C1225-03"}):
			self.skipTest("Live Finishing Plan fixture is missing")
		actual = report.get_data({"lot": "C1225-03"})
		with patch.object(report, "_report_plans", side_effect=lambda names: {name: frappe.get_doc("SD YRP Finishing Plan", name) for name in names}):
			self.assertEqual(report.get_data({"lot": "C1225-03"}), actual)

	def test_batched_plan_rows_match_document_header_and_children(self):
		names = frappe.get_all("SD YRP Finishing Plan", pluck="name", limit_page_length=4)
		expected = {name: frappe.get_doc("SD YRP Finishing Plan", name) for name in names}
		with patch.object(frappe, "get_lazy_doc", side_effect=AssertionError("per-plan header load")):
			actual = report._report_plans(names)
		for name, doc in expected.items():
			for field in ("item", "lot", "pieces_per_box", "production_detail", "is_set_item", "work_order"):
				self.assertEqual(actual[name].get(field), doc.get(field))
			fields = ["finishing_old_lot_given_items"]
			if doc.is_set_item:
				fields += ["finishing_plan_details", "finishing_plan_reworked_details", "finishing_plan_grn_details"]
			for field in fields:
				self.assertEqual([r["name"] for r in actual[name][field]], [r.name for r in doc.get(field)])

	def test_collation_key_covers_only_provable_values(self):
		self.assertEqual(report.collation_key("FP-0001 "), "fp-0001")
		self.assertEqual(report.collation_key("Ab"), report.collation_key("aB  "))
		self.assertNotEqual(report.collation_key(" ab"), report.collation_key("ab"))
		for value in (None, 7, "Café", "a\x01b"):
			self.assertIsNone(report.collation_key(value))

	def test_variant_attribute_rows_match_scalar_reads(self):
		variants = frappe.get_all("Item Variant Attribute", distinct=True, pluck="parent", limit_page_length=40)
		if not variants:
			self.skipTest("No item variants")
		requested = [*variants, variants[0].lower() + " ", "NO-SUCH-VARIANT"]
		rows = report.get_variant_attribute_rows(requested)
		self.assertIn(requested[-2], rows)
		for variant in requested:
			expected = report.get_variant_attr_details(variant)
			if variant in rows:
				self.assertEqual({attribute: report.attribute_value(raw) for attribute, raw in rows[variant]}, expected)

	def test_variant_attribute_rows_leave_unprovable_variants_to_scalar_reads(self):
		rows = [
			frappe._dict(parent="V-1", attribute="Colour", attribute_value="Red"),
			frappe._dict(parent="V-2", attribute="Size", attribute_value="S"),
			frappe._dict(parent="V-2", attribute="Size", attribute_value="M"),
			frappe._dict(parent="V-3", attribute="Colour", attribute_value="IAV-DANGLING"),
		]
		with patch.object(report.frappe.db, "sql", return_value=rows):
			variant_rows = report.get_variant_attribute_rows({"V-1", "v-1", "V-2", "V-3", "Vé"})
		self.assertEqual(
			variant_rows,
			{"V-1": [("Colour", "Red")], "v-1": [("Colour", "Red")], "V-3": [("Colour", "IAV-DANGLING")]},
		)
		with patch.object(report.frappe.db, "sql", return_value=[frappe._dict(parent="Vé", attribute="A", attribute_value="1")]):
			self.assertEqual(report.get_variant_attribute_rows({"V-1"}), {})

	def test_plan_sums_match_per_plan_queries_including_empty_plans(self):
		names = frappe.get_all("SD YRP Finishing Plan", filters={"is_set_item": 0}, pluck="name", limit_page_length=60)
		if not names:
			self.skipTest("No single-item Finishing Plans")
		names.append("NO-SUCH-PLAN")
		for kind, (table, select, columns) in report.PLAN_SUMS.items():
			sums = report.PlanSums(kind, names)
			self.assertFalse(sums.has_foreign_parent)
			for name in names:
				expected = frappe.db.sql(f"SELECT {select} FROM `tab{table}` WHERE parent = %s", name, as_dict=True)[0]
				self.assertEqual(dict(sums.get(name)), dict(expected))
			self.assertEqual(dict(sums.get("NO-SUCH-PLAN")), dict.fromkeys(columns))

	def test_plan_sums_fall_back_to_per_plan_query_for_another_spelling(self):
		with patch.object(report.frappe.db, "sql", return_value=[frappe._dict(plan_name="fp-1", dispatched_box=4.0)]):
			sums = report.PlanSums("dispatch", ["FP-1", "FP-2"])
		self.assertTrue(sums.has_foreign_parent)
		with patch.object(report.frappe.db, "sql", return_value=[frappe._dict(dispatched_box=4.0)]) as sql:
			self.assertEqual(sums.get("FP-1"), {"dispatched_box": 4.0})
		self.assertIn("WHERE parent = %(name)s", sql.call_args.args[0])

	def test_packing_grn_names_match_per_plan_lookup(self):
		names = frappe.get_all("SD YRP Finishing Plan", pluck="name", limit_page_length=0)
		plans = report._report_plans(names)
		batched = report.get_packing_grn_names(list(plans.values()))
		for name, plan in plans.items():
			if name not in batched:
				continue
			expected = []
			if plan.work_order:
				expected = frappe.get_all(
					"YRP Goods Received Note",
					filters={**report.PACKING_GRN_FILTERS, "against_id": plan.work_order, "lot": plan.lot},
					pluck="name",
				)
			self.assertEqual(batched[name], expected)

	def test_packing_grn_names_skip_ties_and_unprovable_rows(self):
		plans = [
			frappe._dict(name="FP-1", work_order="WO-1", lot="L-1"),
			frappe._dict(name="FP-2", work_order="WO-2", lot="L-2"),
			frappe._dict(name="FP-3", work_order=None, lot="L-3"),
			frappe._dict(name="FP-4", work_order="WO-4", lot="Lé"),
		]
		rows = [
			frappe._dict(name="G-1", against_id="wo-1", lot="L-1 ", modified=2),
			frappe._dict(name="G-2", against_id="WO-1", lot="L-1", modified=1),
			frappe._dict(name="G-3", against_id="WO-2", lot="L-2", modified=1),
			frappe._dict(name="G-4", against_id="WO-2", lot="L-2", modified=1),
			frappe._dict(name="G-5", against_id="WO-2", lot=None, modified=3),
		]
		with patch.object(report.frappe, "get_all", return_value=rows):
			self.assertEqual(report.get_packing_grn_names(plans), {"FP-1": ["G-1", "G-2"], "FP-3": []})
		with patch.object(report.frappe, "get_all", return_value=[frappe._dict(name="G", against_id="WO-1", lot="Lé", modified=1)]):
			self.assertEqual(report.get_packing_grn_names(plans), {})

	def test_report_matches_unbatched_reads(self):
		class PerPlanSums(report.PlanSums):
			def __init__(self, kind, names):
				self.table, self.select, self.columns = report.PLAN_SUMS[kind]
				self.rows, self.has_foreign_parent = {}, True

		for filters in ({}, {"product_category": "Vest"}):
			actual = report.get_data(filters)
			with (
				patch.object(report, "get_variant_attribute_rows", return_value={}),
				patch.object(report, "get_packing_grn_names", return_value={}),
				patch.object(report, "PlanSums", PerPlanSums),
			):
				self.assertEqual(typed(report.get_data(filters)), typed(actual))

	def test_unused_prefetched_attribute_values_are_never_resolved(self):
		plan = frappe._dict(
			name="FP-X", item="I", lot="L", pieces_per_box=1, is_set_item=1, production_detail="IPD", work_order=None,
			finishing_plan_details=[frappe._dict(
				item_variant="V-1", cutting_qty=1, delivered_quantity=1, lot_transferred=0, ironing_excess=0,
				return_qty=0, pack_return_qty=0, dc_qty=1, transferred_qty=0,
			)],
			finishing_old_lot_given_items=[frappe._dict(item_variant="V-3", lot_transfer="LT-CANCELLED")],
			finishing_plan_reworked_details=[], finishing_plan_grn_details=[],
		)
		packing = frappe._dict(dynamic_ratio_packing=False, packing_batches=[])
		attribute_rows = [
			frappe._dict(parent="V-1", attribute="Part", attribute_value="Top"),
			frappe._dict(parent="V-3", attribute="Part", attribute_value="IAV-DANGLING"),
		]

		def sql(query, *args, **kwargs):
			return attribute_rows if "Item Variant Attribute" in query else []

		def run(active_rows):
			with (
				patch.object(report.frappe, "get_all", return_value=["FP-X"]),
				patch.object(report, "_report_plans", return_value={"FP-X": plan}),
				patch.object(report, "get_finishing_packing_summary", return_value=packing),
				patch.object(report, "active_old_lot_transfer_rows", side_effect=active_rows),
				patch.object(report.frappe, "get_value", return_value="Part"),
				patch.object(report.frappe.db, "sql", side_effect=sql),
			):
				return report.get_data({})

		self.assertEqual([row["description"] for row in run(lambda rows: [])], ["Top"])
		with self.assertRaises(frappe.ValidationError):
			run(lambda rows: rows)
