from unittest.mock import Mock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.product_development import lotwise_costing

DOCTYPE = "SD YRP Lotwise Item Profit"
TEMPLATE_DOCTYPE = "SD YRP Lotwise Item Profit Additional Cost Template"


def make_doc(**values):
	return frappe.get_doc({"doctype": DOCTYPE, "lot_costing_type": "Costing", **values})


class TestLotwiseCosting(IntegrationTestCase):
	def test_calculate_all_matches_legacy_formula(self):
		doc = make_doc(
			gst=5,
			qty_rate_chart=[
				{"size": "S", "qty": 10, "rate": 200, "weight": 0.2},
				{"size": "M", "qty": 10, "rate": 220},
			],
			cloth_value=[
				{
					"yarn": "Cotton",
					"qty": 4,
					"rate": 300,
					"knitting_cost": 20,
					"dyeing_cost": 50,
					"compacting_cost": 10,
					"wastage_allowance": 10,
				}
			],
			cmt=[{"costing_name": "Stitch", "cost": 15}],
			packing_materials=[{"costing_name": "Box", "cost": 3}],
			trims=[{"costing_name": "Label", "cost": 2}],
			trade_discounts=[{"costing_name": "Trade", "based_on": "Total Value", "rate": 10}],
			other_costs=[{"costing_name": "Freight", "based_on": "Total Qty", "rate": 1}],
		)
		lotwise_costing.calculate_all(doc)
		self.assertEqual(doc.total_qty, 20)
		self.assertAlmostEqual(doc.total_selling_value, 4200)
		self.assertAlmostEqual(doc.total_weight, 2.0)
		self.assertAlmostEqual(doc.cloth_value[0].total_cost, 418)
		self.assertAlmostEqual(doc.total_cloth_value, 1672)
		self.assertAlmostEqual(doc.cloth_value_per_piece, 83.6)
		self.assertAlmostEqual(doc.production_cost_per_piece, 20)
		self.assertAlmostEqual(doc.production_cost, 2072)
		self.assertAlmostEqual(doc.total_trade_discount, 420)
		self.assertAlmostEqual(doc.total_other_cost, 20)
		self.assertAlmostEqual(doc.gst_value, 189)
		self.assertAlmostEqual(doc.cost_price, 2701)
		self.assertAlmostEqual(doc.profit, 1499)
		self.assertAlmostEqual(doc.avg_rate_per_piece, 210)
		self.assertAlmostEqual(doc.avg_cost_per_piece, 135.05)
		self.assertAlmostEqual(doc.profit_percent, 1499 / 2701 * 100)
		self.assertAlmostEqual(doc.profit_percent_markdown, 1499 / 4200 * 100)

	def test_zero_totals_do_not_divide_by_zero(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S", "qty": 0, "rate": 0}],
			trade_discounts=[{"based_on": "Total Value", "rate": 5, "total": 99}],
		)
		lotwise_costing.calculate_all(doc)
		for field in (
			"avg_cost_per_piece",
			"avg_rate_per_piece",
			"profit_percent",
			"profit_percent_markdown",
			"cloth_value_per_piece",
		):
			self.assertEqual(doc.get(field), 0, field)
		self.assertEqual(doc.trade_discounts[0].total, 0)

	def test_blank_based_on_totals_zero(self):
		doc = make_doc(other_costs=[{"rate": 5, "total": 7}])
		lotwise_costing.calculate_all(doc)
		self.assertEqual(doc.other_costs[0].total, 0)

	def test_additional_cost_bases_match_legacy_formulas(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S", "qty": 10, "rate": 100}],
			cmt=[{"costing_name": "Stitch", "cost": 40}],
			trade_discounts=[
				{"costing_name": "Per piece", "based_on": "Total Qty", "rate": 2},
				{"costing_name": "Sales", "based_on": "Total Value", "rate": 10},
				{"costing_name": "Production", "based_on": "Production Cost", "rate": 5},
			],
		)
		lotwise_costing.calculate_all(doc)
		self.assertEqual([row.total for row in doc.trade_discounts], [20, 100, 20])
		self.assertEqual(doc.total_trade_discount, 140)
		self.assertEqual(doc.production_cost, 400)

	def test_add_rate_adds_to_every_row_and_resets(self):
		doc = make_doc(
			additional_rate=5,
			qty_rate_chart=[
				{"size": "S", "qty": 1, "rate": 10},
				{"size": "M", "qty": 1, "rate": 20},
			],
		)
		lotwise_costing.add_rate(doc)
		self.assertEqual([row.rate for row in doc.qty_rate_chart], [15, 25])
		self.assertEqual(doc.additional_rate, 0)
		self.assertEqual(doc.total_selling_value, 40)

	def test_load_product_sizes_requires_product_read_permission(self):
		doc = make_doc(product="PRODUCT-001")
		product = Mock()
		product.check_permission.side_effect = frappe.PermissionError
		with (
			patch.object(lotwise_costing.frappe, "get_doc", return_value=product),
			patch.object(lotwise_costing.frappe, "get_all") as get_sizes,
			self.assertRaises(frappe.PermissionError),
		):
			lotwise_costing.load_product_sizes(doc)
		product.check_permission.assert_called_once_with("read")
		get_sizes.assert_not_called()

	def test_piece_cloth_weight_is_every_group_by_size(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S"}, {"size": "M"}, {"size": "S"}],
			cloth_value=[{"yarn": "A"}, {"yarn": "B"}],
		)
		lotwise_costing.build_piece_cloth_weight(doc)
		self.assertEqual(
			[(row.cloth_group, row.size) for row in doc.piece_cloth_weight],
			[("A", "S"), ("A", "M"), ("B", "S"), ("B", "M")],
		)

	def test_piece_cloth_weight_untouched_when_no_cloth(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S"}],
			piece_cloth_weight=[{"size": "X", "cloth_group": "Old"}],
		)
		lotwise_costing.build_piece_cloth_weight(doc)
		self.assertEqual(doc.piece_cloth_weight[0].cloth_group, "Old")

	def test_cloth_qty_sums_weight_times_size_qty(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S", "qty": 100}, {"size": "M", "qty": 50}],
			cloth_value=[{"yarn": "A", "rate": 1}],
			piece_cloth_weight=[
				{"size": "S", "cloth_group": "A", "weight": 200},
				{"size": "M", "cloth_group": "A", "weight": 300},
			],
		)
		lotwise_costing.calculate_cloth_qty(doc)
		self.assertAlmostEqual(doc.cloth_value[0].qty, 35)

	def test_backwards_rate_hits_requested_markdown(self):
		doc = make_doc(
			qty_rate_chart=[{"size": "S", "qty": 10, "group_index": 1}],
			cloth_value=[{"yarn": "A", "rate": 100}],
			piece_cloth_weight=[{"size": "S", "cloth_group": "A", "weight": 500}],
			cmt=[{"costing_name": "Stitch", "cost": 50}],
		)
		lotwise_costing.calculate_all(doc)
		lotwise_costing.calculate_backwards_rate(doc, 20)
		self.assertAlmostEqual(doc.qty_rate_chart[0].rate, 100 / 0.8)

	def test_markdown_of_100_percent_is_rejected(self):
		doc = make_doc(qty_rate_chart=[{"size": "S", "qty": 1, "group_index": 1}])
		with self.assertRaises(frappe.ValidationError):
			lotwise_costing.calculate_backwards_rate(doc, 100)

	def test_fetch_lot_qty_requires_lot_and_type(self):
		doc = make_doc(lot=None)
		with self.assertRaises(frappe.ValidationError):
			lotwise_costing.fetch_lot_qty(doc)

	def test_fetch_lot_qty_uses_legacy_quantity_fields(self):
		for costing_type, quantity_field in lotwise_costing.LOT_QTY_FIELDS.items():
			with self.subTest(costing_type=costing_type):
				doc = make_doc(
					lot="LOT-1",
					lot_costing_type=costing_type,
					qty_rate_chart=[{"size": "S", "qty": 0, "rate": 1}],
				)
				with patch.object(
					lotwise_costing, "get_lot_qty", return_value={"S": 7}
				) as get_quantity:
					lotwise_costing.fetch_lot_qty(doc)
				get_quantity.assert_called_once_with("LOT-1", quantity_field)
				self.assertEqual(doc.qty_rate_chart[0].qty, 7)

	def test_fetch_lot_qty_reports_missing_lot(self):
		doc = make_doc(
			lot=f"PD-MISSING-LOT-{frappe.generate_hash(length=10)}",
			lot_costing_type="Planned Qty",
		)
		with self.assertRaises(frappe.DoesNotExistError):
			lotwise_costing.fetch_lot_qty(doc)

	def test_validate_recalculates(self):
		doc = make_doc(qty_rate_chart=[{"size": "S", "qty": 2, "rate": 5}])
		doc.run_method("validate")
		self.assertEqual(doc.total_selling_value, 10)

	def test_validate_rejects_mismatched_template_types(self):
		templates = {
			template_type: frappe.db.get_value(TEMPLATE_DOCTYPE, {"type": template_type}, "name")
			for template_type in ("Discounts", "Other")
		}
		if not all(templates.values()):
			self.skipTest("needs an additional cost template of each type")
		for fieldname, template_type, expected_type in (
			("trade_discounts_template", "Other", "Discounts"),
			("other_costs_template", "Discounts", "Other"),
		):
			with self.subTest(fieldname=fieldname):
				doc = make_doc(
					**{
						fieldname: templates[template_type],
						"other_costs": [{"costing_name": "Edited", "rate": 7}],
					}
				)
				with self.assertRaisesRegex(frappe.ValidationError, f"not a {expected_type} template"):
					doc.run_method("validate")
				self.assertEqual(doc.other_costs[0].costing_name, "Edited")
