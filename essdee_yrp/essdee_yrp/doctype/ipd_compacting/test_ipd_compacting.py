from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.ipd_compacting.ipd_compacting import (
	compacting_key,
	merge_compacting_details,
	validate_submitted_details,
)


class TestIPDCompacting(IntegrationTestCase):
	def setUp(self):
		self.expected = [
			{
				"cloth_item": "CLOTH-1",
				"packing_attribute_value": "Red",
				"input_dia": "60",
			},
			{
				"cloth_item": "CLOTH-1",
				"packing_attribute_value": "Blue",
				"input_dia": "62",
			},
		]

	def test_merge_preserves_saved_dia_by_business_key(self):
		rows = merge_compacting_details(
			self.expected,
			[{**self.expected[1], "compacting_dia": "64"}],
		)
		self.assertIsNone(rows[0]["compacting_dia"])
		self.assertEqual(rows[1]["compacting_dia"], "64")

	def test_submission_is_normalized_to_complete_expected_routes(self):
		with patch(
			"essdee_yrp.essdee_yrp.doctype.ipd_compacting.ipd_compacting.frappe.get_all",
			return_value=["60", "62", "64"],
		):
			rows = validate_submitted_details(
				self.expected,
				[{**self.expected[0], "compacting_dia": "64"}],
			)
		self.assertEqual({compacting_key(row) for row in rows}, {compacting_key(row) for row in self.expected})
		by_key = {compacting_key(row): row for row in rows}
		self.assertEqual(by_key[compacting_key(self.expected[0])]["compacting_dia"], "64")
		self.assertIsNone(by_key[compacting_key(self.expected[1])]["compacting_dia"])

	def test_submission_rejects_a_route_outside_the_ipd(self):
		with self.assertRaises(frappe.ValidationError):
			validate_submitted_details(
				self.expected,
				[{
					"cloth_item": "OTHER",
					"packing_attribute_value": "Red",
					"input_dia": "60",
				}],
			)
