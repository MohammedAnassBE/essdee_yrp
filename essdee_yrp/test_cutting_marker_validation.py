from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker import (
	SDYRPCuttingMarker,
)

MARKER_MODULE = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker"


class TestCuttingMarkerRatioValidation(TestCase):
	def validate_ratio(self, selected_type, ratio):
		doc = frappe._dict(
			cutting_plan="CP-1",
			selected_type=selected_type,
			calculated_parts="Front",
			marker_details={"ratio_items": [{"size": "M", "panel": "Front", "ratio": ratio}], "group_items": []},
		)
		doc.set = lambda field, value: doc.update({field: value})
		with (
			patch(f"{MARKER_MODULE}.get_parent_ref", return_value=("SD YRP Cutting Plan", "CP-1")),
			patch(f"{MARKER_MODULE}.validate_parent_status"),
			patch(f"{MARKER_MODULE}.get_parent_context", return_value={"item": "SHIRT"}),
			patch(f"{MARKER_MODULE}._attribute_value", side_effect=lambda value: value),
		):
			SDYRPCuttingMarker.before_validate(doc)
		return doc

	def test_invalid_manual_and_machine_ratios_name_the_size(self):
		for selected_type in ("Manual", "Machine"):
			with self.subTest(selected_type=selected_type):
				with self.assertRaisesRegex(frappe.ValidationError, r"Size M: only 0\.5 increments are allowed\."):
					self.validate_ratio(selected_type, 0.7)

	def test_whole_and_half_ratios_remain_valid(self):
		for selected_type in ("Manual", "Machine"):
			for ratio in (0, 0.5, 1, 1.5):
				with self.subTest(selected_type=selected_type, ratio=ratio):
					doc = self.validate_ratio(selected_type, ratio)
					self.assertEqual(doc.cutting_marker_ratios, [{"size": "M", "panel": "Front", "ratio": ratio}])
