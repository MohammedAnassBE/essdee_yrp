import frappe
from frappe.tests.utils import FrappeTestCase


class TestStockEntryCustomization(FrappeTestCase):
	EXPECTED_PURPOSES = (
		"Material Issue\n"
		"Material Receipt\n"
		"Send to Warehouse\n"
		"Receive at Warehouse\n"
		"Material Consumed\n"
		"Stock Dispatch\n"
		"DC Completion\n"
		"GRN Completion"
	)

	def test_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Stock Entry", cached=False)
		expected = {
			"cut_panel_movement": ("Link", "Cut Panel Movement"),
			"dispatch_colour_details": ("Long Text", None),
			"includes_packing": ("Check", None),
			"packing_batch_dispatch_json": ("JSON", None),
			"packing_slip": ("Data", None),
			"transfer_supplier": ("Link", "Supplier"),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), definition)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Stock Entry",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta("Stock Entry", cached=False)

		packing_slip = meta.get_field("packing_slip")
		self.assertEqual(packing_slip.depends_on, "eval:doc.purpose == 'Stock Dispatch'")
		self.assertEqual(
			packing_slip.mandatory_depends_on,
			"eval:doc.purpose == 'Stock Dispatch'",
		)
		self.assertEqual(meta.get_field("cut_panel_movement").allow_on_submit, 1)
		self.assertEqual(meta.get_field("includes_packing").default, "0")
		self.assertEqual(meta.get_field("dispatch_colour_details").no_copy, 1)
		self.assertEqual(meta.get_field("dispatch_colour_details").read_only, 1)
		self.assertEqual(meta.get_field("packing_batch_dispatch_json").read_only, 1)

	def test_approved_property_customizations(self):
		meta = frappe.get_meta("Stock Entry", cached=False)

		self.assertEqual(meta.get_field("purpose").options, self.EXPECTED_PURPOSES)
		self.assertEqual(
			meta.get_field("additional_amount").read_only_depends_on,
			"eval: doc.purpose != 'Send to Warehouse'",
		)
		for name in (
			"Stock Entry-additional_amount-read_only_depends_on",
			"Stock Entry-purpose-options",
		):
			self.assertTrue(frappe.db.exists("Property Setter", name))

	def test_base_terms_and_condition_behavior_is_unchanged(self):
		field = frappe.get_meta("Stock Entry", cached=False).get_field(
			"terms_and_condition"
		)
		self.assertEqual(field.fetch_from, "to_supplier.po_terms_and_condition")
		self.assertEqual(field.fetch_if_empty, 1)
		self.assertEqual(field.allow_on_submit, 0)
