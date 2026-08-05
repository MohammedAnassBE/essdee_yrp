# Copyright (c) 2024, Essdee and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.lot.lot import get_ocr_details


class TestLot(FrappeTestCase):
	def test_ocr_details_does_not_require_f15_plan_doctypes(self):
		def get_all(doctype, *args, **kwargs):
			if doctype == "Work Order":
				return ["_Test OCR Work Order"]
			if doctype == "Goods Received Note":
				return []
			self.fail(f"Unexpected DocType query: {doctype}")

		work_order = frappe._dict(
			includes_packing=0,
			process_name="_Test OCR Process",
			work_order_calculated_items=[],
		)
		grn_meta = frappe._dict(has_field=lambda _fieldname: False)

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(
				frappe,
				"get_value",
				side_effect=[
					("_Test OCR IPD", "_Test OCR Item"),
					("_Test OCR Sewing", "Size", 1),
				],
			),
			patch.object(frappe, "get_doc", return_value=work_order),
			patch.object(frappe, "get_meta", return_value=grn_meta),
		):
			result = get_ocr_details("_Test OCR Lot")

		self.assertEqual(
			result["processes"]["_Test OCR Process"]["cp_list"],
			[],
		)
