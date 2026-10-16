import json
from pathlib import Path

import frappe
from frappe.tests import UnitTestCase


class TestWorkOrderCloseDialog(UnitTestCase):
	def test_essdee_bundle_owns_garment_close_reasons(self):
		public_js = Path(frappe.get_app_path("essdee_yrp", "public", "js"))
		bundle_source = (public_js / "essdee_yrp.bundle.js").read_text(encoding="utf-8")
		dialog_source = (public_js / "work_order_close_dialog.js").read_text(encoding="utf-8")

		self.assertIn('import "./work_order_close_dialog";', bundle_source)
		for reason in (
			"Cutting Shortage",
			"Printing Shortage",
			"Sewing Shortage",
			"Sewing Missing",
			"Others",
		):
			self.assertIn(reason, dialog_source)

		fixture_path = frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json")
		with open(fixture_path, encoding="utf-8") as fixture_file:
			custom_fields = {row["name"]: row for row in json.load(fixture_file)}
		other_reason = custom_fields["Work Order-close_other_reason"]
		self.assertEqual(other_reason["module"], "Essdee YRP")
		self.assertEqual(other_reason["insert_after"], "close_reason")

		self.assertTrue(custom_fields)
		self.assertTrue(all(row["module"] == "Essdee YRP" for row in custom_fields.values()))
		for base_owned_field in (
			"Bin-lot",
			"Delivery Challan Item-received_type",
			"Goods Received Note Item-lot",
			"Stock Entry Detail-received_type",
			"Work Order-lot",
		):
			self.assertNotIn(base_owned_field, custom_fields)

		for essdee_owned_field in (
			"Item Production Detail-packing_tab",
			"Process-includes_packing",
			"Production Order-lot_ordered_html",
		):
			self.assertIn(essdee_owned_field, custom_fields)
