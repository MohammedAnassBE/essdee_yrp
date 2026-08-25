import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.dynamic_packing import (
	DYNAMIC_PACKING_VERSION,
	aggregate_batch_pieces,
	is_batch_tracked_packing_grn,
	is_dynamic_packing_grn,
	normalize_packing_batches,
	packing_batch_label,
)


class TestDynamicPacking(FrappeTestCase):
	def test_normalize_packing_batches_preserves_physical_boxes(self):
		rows = normalize_packing_batches(
			[
				{
					"colour": "Navy",
					"box_quantity": 3,
					"ratio": {"S": 2, "M": 3},
				}
			],
			valid_sizes=["S", "M"],
			valid_colours=["Navy"],
			expected_pieces_per_box=5,
		)

		self.assertEqual(rows[0]["box_quantity"], 3)
		self.assertEqual(rows[0]["pieces_per_box"], 5)
		self.assertEqual(rows[0]["size_pieces"], {"S": 6, "M": 9})
		self.assertEqual(rows[0]["total_pieces"], 15)

	def test_aggregate_uses_selected_box_field(self):
		rows = [
			frappe._dict(
				ratio_json=frappe.as_json({"S": 2, "M": 3}),
				box_quantity=4,
				dispatched_boxes=2,
			)
		]
		sizes, boxes, pieces = aggregate_batch_pieces(rows, "dispatched_boxes")
		self.assertEqual(sizes, {"S": 4, "M": 6})
		self.assertEqual(boxes, 2)
		self.assertEqual(pieces, 10)

	def test_invalid_ratio_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			normalize_packing_batches(
				[{"colour": "Navy", "box_quantity": 1, "ratio": {"XL": 5}}],
				valid_sizes=["S", "M"],
				valid_colours=["Navy"],
			)

	def test_batch_helpers_cover_legacy_and_dynamic_versions(self):
		legacy = frappe._dict(packing_calculation_version=1)
		dynamic = frappe._dict(packing_calculation_version=DYNAMIC_PACKING_VERSION)
		self.assertTrue(is_batch_tracked_packing_grn(legacy))
		self.assertFalse(is_dynamic_packing_grn(legacy))
		self.assertTrue(is_dynamic_packing_grn(dynamic))
		self.assertEqual(
			packing_batch_label({"colour": "Navy", "ratio": {"S": 2, "M": 3}}),
			"Navy [S:2, M:3]",
		)
