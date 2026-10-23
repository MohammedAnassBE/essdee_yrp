from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item import get_rework_sources
from essdee_yrp.finishing.web_reports import get_rework_details, get_rework_groups

DETAIL_FIELDS = (
	"name",
	"item_variant",
	"received_type",
	"quantity",
	"reworked",
	"rejection",
	"completed",
	"uom",
	"set_combination",
)


class TestReworkSources(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.names = frappe.get_all("SD YRP GRN Rework Item", pluck="name", order_by="creation desc", limit=20)
		if not self.names:
			self.skipTest("No GRN Rework Items are available")

	def test_batched_sources_match_loaded_documents(self):
		sources = get_rework_sources({"name": ["in", self.names]})

		self.assertEqual([source.name for source in sources], self.names)
		for source in sources:
			doc = frappe.get_doc("SD YRP GRN Rework Item", source.name)
			self.assertEqual(
				(source.grn_number, source.lot, source.item, source.warehouse, source.creation),
				(doc.grn_number, doc.lot, doc.item, doc.warehouse, doc.creation),
			)
			self.assertEqual(
				[[row.get(field) for field in DETAIL_FIELDS] for row in source.grn_rework_item_details],
				[[row.get(field) for field in DETAIL_FIELDS] for row in doc.grn_rework_item_details],
			)

	def test_rework_reports_do_not_load_rework_documents_one_by_one(self):
		lot = frappe.db.get_value("SD YRP GRN Rework Item", self.names[0], "lot")
		loaded = []
		get_doc = frappe.get_doc

		def tracking_get_doc(*args, **kwargs):
			loaded.append(args[0] if args else None)
			return get_doc(*args, **kwargs)

		with patch("frappe.get_doc", side_effect=tracking_get_doc):
			for show_reworked in (0, 1):
				get_rework_details(lot=lot, show_reworked=show_reworked)
				get_rework_groups(lot=lot, show_reworked=show_reworked)

		self.assertNotIn("SD YRP GRN Rework Item", loaded)
