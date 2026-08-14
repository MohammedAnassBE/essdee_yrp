import frappe
from frappe.tests.utils import FrappeTestCase


class TestGoodsReceivedNoteCustomization(FrappeTestCase):
	EXPECTED_FIELDS = {
		"additional_grn": ("Check", None),
		"allow_non_bundle": ("Check", None),
		"delivery_location_name": ("Data", None),
		"dc_no": ("Data", None),
		"cutting_laysheet": ("Link", "Cutting LaySheet"),
		"mrp_material_issue_ref": ("Link", "Stock Entry"),
		"is_return": ("Check", None),
		"is_pack": ("Check", None),
		"from_finishing": ("Check", None),
		"avoid_sewing_plan_qty": ("Check", None),
		"rework_created": ("Check", None),
		"grn_date": ("Date", None),
		"actual_date": ("Date", None),
		"is_manual_entry": ("Check", None),
		"letter_head": ("Link", "Letter Head"),
		"cut_panel_movement": ("Link", "Cut Panel Movement"),
		"includes_packing": ("Check", None),
		"supplier_document_date": ("Date", None),
		"freight_charge_per_product": ("Currency", None),
		"supplier_name": ("Data", None),
		"delivery_date": ("Date", None),
		"supplier_address": ("Link", "Address"),
		"supplier_address_display": ("Small Text", None),
		"contact_person": ("Link", "Contact"),
		"contact_display": ("Small Text", None),
		"contact_mobile": ("Small Text", None),
		"delivery_address": ("Link", "Address"),
		"delivery_address_display": ("Small Text", None),
		"total_receivable_cost": ("Currency", None),
		"packing_calculation_version": ("Int", None),
		"total_packing_boxes": ("Float", None),
		"total_packing_pieces": ("Float", None),
		"packing_batches": ("Table", "GRN Packing Batch"),
		"items_json": ("JSON", None),
		"grn_excess_usage_items": ("Table", "GRN Excess Usage Item"),
		"total_delivered_qty": ("Float", None),
		"total_tax": ("Currency", None),
		"grand_total": ("Currency", None),
		"in_words": ("Data", None),
		"approved_by": ("Link", "User"),
	}

	def test_approved_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

		for fieldname, expected in self.EXPECTED_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), expected)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Goods Received Note",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_source_field_attributes_are_preserved(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

		self.assertEqual(meta.get_field("delivery_date").default, "Today")
		self.assertEqual(meta.get_field("delivery_date").reqd, 1)
		self.assertEqual(meta.get_field("supplier_address").reqd, 1)
		self.assertEqual(meta.get_field("delivery_address").reqd, 1)
		self.assertEqual(
			meta.get_field("delivery_location_name").fetch_from,
			"delivery_location.supplier_name",
		)
		self.assertEqual(
			meta.get_field("supplier_name").fetch_from,
			"supplier.supplier_name",
		)
		self.assertEqual(
			meta.get_field("is_manual_entry").fetch_from,
			"process_name.is_manual_entry_in_grn",
		)
		self.assertEqual(
			meta.get_field("includes_packing").fetch_from,
			"process_name.includes_packing",
		)
		self.assertEqual(meta.get_field("from_finishing").allow_on_submit, 1)
		self.assertEqual(meta.get_field("mrp_material_issue_ref").allow_on_submit, 1)
		self.assertEqual(meta.get_field("packing_batches").allow_on_submit, 1)
		self.assertEqual(meta.get_field("total_delivered_qty").allow_on_submit, 1)
		self.assertEqual(meta.get_field("avoid_sewing_plan_qty").permlevel, 1)
		self.assertEqual(meta.get_field("approved_by").no_copy, 1)

	def test_obsolete_essdee_stock_entry_fields_are_excluded(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)
		self.assertIsNone(meta.get_field("essdee_yrp_stock_entry"))
		self.assertIsNone(meta.get_field("essdee_yrp_stock_entry_created"))

	def test_approved_base_yrp_fields_are_unchanged(self):
		meta = frappe.get_meta("Goods Received Note", cached=False)

		delivery_location = meta.get_field("delivery_location")
		self.assertEqual(
			(
				delivery_location.options,
				delivery_location.reqd,
				delivery_location.fetch_from,
			),
			("Supplier", 0, "to_warehouse.supplier"),
		)

		freight_charges = meta.get_field("freight_charges")
		self.assertEqual(freight_charges.default, "0")
		self.assertFalse(freight_charges.depends_on)

		lot = meta.get_field("lot")
		self.assertEqual(
			(lot.fieldtype, lot.options, lot.reqd, lot.read_only),
			("Link", "Lot", 1, 0),
		)
