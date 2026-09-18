import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe import _dict

from essdee_yrp.essdee_yrp.doctype.sd_yrp_box_sticker_print import (
	sd_yrp_box_sticker_print as box_sticker_print,
)
from essdee_yrp.finishing.box_sticker import (
	build_box_sticker_details,
	get_missing_box_sticker_prices,
)


class TestBoxStickerPrint(unittest.TestCase):
	def test_preview_posts_zpl_in_the_request_body(self):
		client = Path(box_sticker_print.__file__).with_suffix(".js").read_text(
			encoding="utf-8"
		)
		self.assertIn('method: "POST"', client)
		self.assertIn("body: result.code", client)
		self.assertNotIn("encodeURIComponent(result.code)", client)

	def test_save_does_not_refetch_or_overwrite_mrp(self):
		doc = SimpleNamespace(
			box_sticker_print_details=[
				_dict(size="S", quantity=1, allow_excess_quantity=0, mrp=999)
			]
		)
		frappe_mock = MagicMock()
		with patch.object(box_sticker_print, "frappe", frappe_mock):
			box_sticker_print.BoxStickerPrint.before_validate(doc)
		self.assertEqual(doc.box_sticker_print_details[0].mrp, 999)
		frappe_mock.db.get_value.assert_not_called()

	def test_work_order_builds_sticker_rows_from_resolved_price_map(self):
		self.assertEqual(
			build_box_sticker_details(
				["S", "M"], {"S": 100, "M": 0}, {"S": 125, "M": 135}
			),
			[
				{
					"size": "S",
					"quantity": 100.0,
					"mrp": 125.0,
					"allow_excess_quantity": 0,
					"allow_excess_percentage": 5,
				},
				{
					"size": "M",
					"quantity": 0.0,
					"mrp": 135.0,
					"allow_excess_quantity": 1,
					"allow_excess_percentage": 5,
				},
			],
		)

	def test_migrated_packing_work_order_has_complete_price_scope(self):
		work_order = "WO-2627-00839"
		if not frappe.db.exists('YRP Work Order', work_order):
			self.skipTest("Migrated packing Work Order oracle is unavailable")
		self.assertEqual(get_missing_box_sticker_prices(work_order), [])
