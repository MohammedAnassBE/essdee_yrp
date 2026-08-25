from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.overrides.inspection_entry import get_initial_payload


class TestInspectionEntryCustomization(FrappeTestCase):
	def test_uncompleted_internal_grn_uses_transit_warehouse(self):
		sources = [{"item_variant": "TEST-VARIANT", "warehouse": "FINAL"}]
		grn = frappe._dict(
			name="TEST-GRN",
			is_internal_unit=1,
			transfer_complete=0,
			items=[frappe._dict(ste_received_quantity=0)],
		)
		with (
			patch(
				"essdee_yrp.overrides.inspection_entry.get_base_initial_payload",
				return_value=sources,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.get_doc",
				return_value=grn,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.db.get_single_value",
				return_value="TRANSIT",
			),
			patch("essdee_yrp.overrides.inspection_entry._attach_display_meta") as attach,
		):
			result = get_initial_payload("Goods Received Note", grn.name)

		self.assertEqual(result[0]["warehouse"], "TRANSIT")
		attach.assert_called_once_with(result)

	def test_completed_internal_grn_keeps_final_warehouse(self):
		sources = [{"item_variant": "TEST-VARIANT", "warehouse": "FINAL"}]
		grn = frappe._dict(
			name="TEST-GRN",
			is_internal_unit=1,
			transfer_complete=1,
			items=[frappe._dict(ste_received_quantity=10)],
		)
		with (
			patch(
				"essdee_yrp.overrides.inspection_entry.get_base_initial_payload",
				return_value=sources,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.get_doc",
				return_value=grn,
			),
		):
			result = get_initial_payload("Goods Received Note", grn.name)

		self.assertEqual(result[0]["warehouse"], "FINAL")
