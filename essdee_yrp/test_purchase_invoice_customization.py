import frappe
from frappe.tests.utils import FrappeTestCase


class TestPurchaseInvoiceCustomization(FrappeTestCase):
	def test_parent_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Purchase Invoice", cached=False)
		expected = {
			"gstin": ("Data", None),
			"pan_no": ("Data", None),
			"gst_state": ("Select", "\nIn-State\nOut-State"),
			"do_not_submit_invoice": ("Check", None),
			"erp_inv_name": ("Data", None),
			"erp_inv_docstatus": ("Int", None),
			"final_amount": ("Currency", None),
			"eligibility_for_itc": (
				"Select",
				"Input Service Distributor\nImport Of Service\nImport Of Capital Goods\n"
				"ITC on Reverse Charge\nIneligible As Per Section 17(5)\n"
				"Ineligible Others\nAll Other ITC",
			),
			"cancel_without_cancelling_erp_inv": ("Check", None),
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
							"dt": "Purchase Invoice",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

		self.assertIsNone(meta.get_field("vendor_bill_tracking"))
		bill_tracking = meta.get_field("bill_tracking")
		self.assertEqual((bill_tracking.fieldtype, bill_tracking.options), ("Link", "Bill Tracking"))
		self.assertFalse(
			frappe.db.exists(
				"Custom Field",
				{"dt": "Purchase Invoice", "fieldname": "bill_tracking"},
			)
		)

	def test_child_fields_and_mandatory_item_group(self):
		meta = frappe.get_meta("Purchase Invoice Item", cached=False)
		lot = meta.get_field("lot")
		expense_head = meta.get_field("expense_head")
		item_group = meta.get_field("item_group")

		self.assertEqual((lot.fieldtype, lot.options, lot.in_list_view), ("Link", "Lot", 1))
		self.assertEqual(
			(expense_head.fieldtype, expense_head.read_only, expense_head.in_list_view),
			("Data", 1, 1),
		)
		self.assertEqual(item_group.reqd, 1)
		self.assertIsNotNone(meta.get_field("set_combination"))

		for fieldname in ("lot", "expense_head"):
			field = frappe.db.get_value(
				"Custom Field",
				{
					"dt": "Purchase Invoice Item",
					"fieldname": fieldname,
					"module": "Essdee YRP",
				},
				["description", "is_system_generated"],
				as_dict=True,
			)
			self.assertIsNotNone(field)
			self.assertNotEqual(field.description, "Managed by YRP Stock Dimension")
			self.assertEqual(field.is_system_generated, 1)

		self.assertTrue(
			frappe.db.exists(
				"Property Setter",
				{
					"doc_type": "Purchase Invoice Item",
					"field_name": "item_group",
					"property": "reqd",
					"value": "1",
				},
			)
		)
