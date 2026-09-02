import frappe
from frappe.tests.utils import FrappeTestCase


class TestReviewedProductionCustomizations(FrappeTestCase):
	def test_work_station_action_is_essdee_custom_field(self):
		field = frappe.get_meta('YRP Work Station', cached=False).get_field("action")
		self.assertIsNotNone(field)
		self.assertEqual(
			(field.fieldtype, field.options, field.reqd, field.in_list_view),
			("Link", 'SD YRP Action', 1, 1),
		)
		self.assertTrue(
			frappe.db.exists(
				"Custom Field",
				{
					"dt": 'YRP Work Station',
					"fieldname": "action",
					"module": "Essdee YRP",
				},
			)
		)

	def test_lot_has_time_and_action_child_table(self):
		field = frappe.get_meta('SD YRP Lot', cached=False).get_field(
			"lot_time_and_action_details"
		)
		self.assertIsNotNone(field)
		self.assertEqual(
			(field.fieldtype, field.options, field.hidden),
			("Table", 'SD YRP Lot Time and Action Detail', 1),
		)
		self.assertFalse(
			frappe.db.exists(
				"Custom Field",
				{"dt": 'SD YRP Lot', "fieldname": "lot_time_and_action_details"},
			)
		)

	def test_production_ordered_detail_matches_approved_source_fields(self):
		meta = frappe.get_meta('YRP Production Ordered Detail', cached=False)
		reference_doctype = meta.get_field("reference_doctype")
		reference_name = meta.get_field("reference_name")
		lot = meta.get_field("lot")
		quantity = meta.get_field("quantity")

		self.assertEqual(
			(reference_doctype.fieldtype, reference_doctype.options),
			("Link", "DocType"),
		)
		self.assertEqual(
			(reference_name.fieldtype, reference_name.options),
			("Dynamic Link", "reference_doctype"),
		)
		self.assertEqual(
			(lot.fieldtype, lot.options, lot.in_list_view),
			("Link", 'SD YRP Lot', 1),
		)
		self.assertEqual(quantity.fieldtype, "Int")
		self.assertTrue(
			frappe.db.exists(
				"Custom Field",
				{
					"dt": 'YRP Production Ordered Detail',
					"fieldname": "lot",
					"module": "Essdee YRP",
				},
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"Property Setter",
				{
					"doc_type": 'YRP Production Ordered Detail',
					"field_name": "quantity",
					"property": "fieldtype",
					"value": "Int",
				},
			)
		)
