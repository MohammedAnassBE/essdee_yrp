from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	get_bundle_items,
)


class BundleRow(dict):
	def __getattr__(self, key):
		return self.get(key)

	def as_dict(self):
		return dict(self)


class TestCuttingLaySheetPrint(TestCase):
	def test_movement_chart_bundle_items_resolve_size_title(self):
		doc = frappe._dict(
			cutting_laysheet_bundles=[
				BundleRow(bundle_no=1, size="IAV-S", colour="IAV-NAVY", part="Back"),
				BundleRow(bundle_no=1, size="IAV-S", colour="IAV-NAVY", part="Front"),
				BundleRow(bundle_no=2, size="IAV-M", colour="IAV-NAVY", part="Back"),
			]
		)
		doc.check_permission = MagicMock()
		labels = {"IAV-S": "S", "IAV-M": "M"}
		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet._attribute_value",
				side_effect=lambda value: labels.get(value, value),
			),
		):
			items = get_bundle_items("CLS-TEST")

		self.assertEqual([item["size"] for item in items], ["S", "M"])
