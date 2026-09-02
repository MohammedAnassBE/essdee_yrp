from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


class TestProductionOrderCustomization(FrappeTestCase):
	def test_ppo_request_form_stays_editable_for_authorized_manager(self):
		form_source = Path(
			frappe.get_app_path(
				"essdee_yrp", "public", "js", "production_order_workflow.js"
			)
		).read_text()
		self.assertNotIn('frm.doc.status !== "PPO Request"', form_source)
		self.assertNotIn("frm.disable_save()", form_source)

	def test_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta('YRP Production Order', cached=False)
		expected = {
			"comment_log": {"fieldtype": "Long Text", "read_only": 1},
			"date_change_history": {
				"fieldtype": "Table",
				"options": 'SD YRP Production Order Date Change',
				"read_only": 1,
				"allow_on_submit": 1,
			},
			"incoming_quantity_transfer_request": {
				"fieldtype": "Long Text",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
			"item": {
				"fieldtype": "Link",
				"options": 'YRP Item',
				"reqd": 1,
				"in_list_view": 1,
			},
			"lot_price_overrides": {
				"fieldtype": "Table",
				"options": 'SD YRP PPO Lot Price Detail',
				"hidden": 1,
				"allow_on_submit": 1,
			},
			"ppo_requested_by": {
				"fieldtype": "Link",
				"options": "User",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
			},
			"ppo_requested_on": {
				"fieldtype": "Datetime",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
			},
			"quantity_ratio_request": {
				"fieldtype": "Long Text",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
			"quantity_transfer_history": {
				"fieldtype": "Table",
				"options": 'SD YRP PPO Quantity Transfer History',
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
			"status": {
				"fieldtype": "Select",
				"default": "Draft",
				"options": (
					"\nDraft\nPPO Request\nOpen\nPending Request\nItem Changed\n"
					"Not Processed\nClosed"
				),
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
				"in_list_view": 1,
				"in_standard_filter": 1,
			},
			"status_change_request": {
				"fieldtype": "Long Text",
				"hidden": 1,
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
			"transferred_on": {
				"fieldtype": "Datetime",
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
			"transferred_to_ppo": {
				"fieldtype": "Link",
				"options": 'YRP Production Order',
				"read_only": 1,
				"no_copy": 1,
				"allow_on_submit": 1,
			},
		}

		for fieldname, properties in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				for property_name, value in properties.items():
					self.assertEqual(field.get(property_name), value)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": 'YRP Production Order',
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_naming_series_matches_production_api(self):
		field = frappe.get_meta('YRP Production Order', cached=False).get_field(
			"naming_series"
		)
		self.assertEqual(field.fieldtype, "Select")
		self.assertEqual(field.options, "\nPPO-")
		self.assertEqual(field.reqd, 1)
		self.assertEqual(field.hidden, 0)
		self.assertFalse(field.default)
