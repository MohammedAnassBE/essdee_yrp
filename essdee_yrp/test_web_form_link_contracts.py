from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.work_order import _get_work_order_selection_context


def _frontend_path(*parts):
	return Path(frappe.get_app_path("essdee_yrp")).parent / "frontend" / "src" / Path(*parts)


class TestWebFormLinkContracts(UnitTestCase):
	def test_work_order_selection_skips_a_stale_ipd_process_link(self):
		lot = frappe._dict({
			"item": "Garment",
			"production_detail": "Garment IPD",
			"lot_fabric_details": [frappe._dict({
				"name": "FABRIC-ROW-1",
				"cloth_item": "Cloth",
				"production_detail": "Stale Cloth IPD",
			})],
		})
		with (
			patch("essdee_yrp.api.work_order.frappe.get_doc", return_value=lot),
			patch("essdee_yrp.api.work_order.frappe.db.get_value", return_value=1),
			patch("essdee_yrp.api.work_order.frappe.get_cached_doc", return_value=frappe._dict()),
			patch(
				"essdee_yrp.api.work_order.get_fabric_step",
				side_effect=frappe.DoesNotExistError,
			),
		):
			context = _get_work_order_selection_context("LOT-1", "Knitting")

		self.assertTrue(context["is_cloth_process"])
		self.assertEqual(context["options"], [])
		self.assertEqual(context["item_options"], [])

	def test_stock_entry_warehouses_are_scoped_to_locations(self):
		config = _frontend_path("config", "fields", "stock-entry.js").read_text(encoding="utf-8")
		index = _frontend_path("config", "fields", "index.js").read_text(encoding="utf-8")

		self.assertIn('{ supplier: form.from_supplier, disabled: 0 }', config)
		self.assertIn('{ supplier: form.to_supplier, disabled: 0 }', config)
		self.assertIn('from_supplier: "From Location"', config)
		self.assertIn('to_supplier: "To Location"', config)
		self.assertIn('"Stock Entry": stockEntry', index)

	def test_work_order_auto_selects_only_one_party_address(self):
		detail = _frontend_path("views", "dynamic", "DocDetail.vue").read_text(encoding="utf-8")
		client = _frontend_path("api", "client.js").read_text(encoding="utf-8")

		self.assertIn("async function autoSelectOnlyWorkOrderAddress", detail)
		self.assertIn('if (addresses.length === 1)', detail)
		self.assertIn('await autoSelectOnlyWorkOrderAddress(fieldname)', detail)
		self.assertIn('get_address_display', detail)
		self.assertIn('function plainAddressDisplay(value)', detail)
		self.assertIn(':modelValue="formTextDisplayValue(f)"', detail)
		self.assertIn('link_name: partyName, disabled: 0', client)

	def test_stock_entry_location_change_clears_stale_warehouse(self):
		detail = _frontend_path("views", "dynamic", "DocDetail.vue").read_text(encoding="utf-8")

		self.assertIn('if (fieldname === "from_supplier") form.from_warehouse = ""', detail)
		self.assertIn('if (fieldname === "to_supplier") form.to_warehouse = ""', detail)
