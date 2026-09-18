import frappe
from frappe.model.naming import set_new_name
from frappe.tests import IntegrationTestCase

ESSDEE_NAMING_SERIES = {
	'YRP Work Order': "YRP-WO-.YYYY.-",
	'YRP Goods Received Note': "YRP-GRN-.YYYY.-",
	'YRP Stock Entry': "YRP-STE-.YYYY.-",
	'YRP Process Cost': "YRP-PC-",
	'YRP Purchase Invoice': "YRP-MPI-.YYYY.-",
	'YRP Stock Reconciliation': "YRP-ST-RECO-.YYYY.-",
	'YRP Stock Update': "YRP-SUE-.YYYY.-",
}
BASE_NAMING_SERIES = {
	'YRP Delivery Challan': "DC-.YYYY.-",
}
ESSDEE_AUTONAME_SERIES = {
	'YRP Item Price': "YRP-ITP-.#####",
	'YRP Stock Ledger Entry': "YRP-SLE-.YYYY.-.#####",
	'YRP Stock Reservation Entry': "YRP-SRE-.YYYY.-.#####",
}


class TestEssdeeNamingSeries(IntegrationTestCase):
	def test_standard_purchase_order_keeps_native_default_and_offers_yrp_series(self):
		field = frappe.get_meta('Purchase Order', cached=False).get_field("naming_series")
		self.assertEqual(field.default, "PUR-ORD-.YYYY.-")
		self.assertEqual(
			field.options.splitlines(),
			["PUR-ORD-.YYYY.-", "YRP-PO-.YYYY.-"],
		)

		native = frappe.new_doc('Purchase Order')
		set_new_name(native)
		self.assertTrue(native.name.startswith("PUR-ORD-"))

		yrp_managed = frappe.new_doc('Purchase Order')
		yrp_managed.is_yrp_managed = 1
		yrp_managed.run_method("before_naming")
		set_new_name(yrp_managed)
		self.assertTrue(yrp_managed.name.startswith("YRP-PO-"))

	def test_new_database_rows_receive_yrp_names(self):
		frappe.db.savepoint("test_essdee_naming_insert")
		try:
			for doctype in (*ESSDEE_NAMING_SERIES, *ESSDEE_AUTONAME_SERIES):
				doc = frappe.new_doc(doctype)
				doc.db_insert()
				self.assertTrue(doc.name.startswith("YRP-"), f"{doctype}: {doc.name}")
				self.assertTrue(frappe.db.exists(doctype, doc.name))
		finally:
			frappe.db.rollback(save_point="test_essdee_naming_insert")

	def test_property_setters_are_applied_to_live_meta(self):
		for doctype, series in ESSDEE_NAMING_SERIES.items():
			field = frappe.get_meta(doctype, cached=False).get_field("naming_series")
			self.assertEqual(field.options, series)
			self.assertEqual(field.default, series)

		for doctype, series in ESSDEE_AUTONAME_SERIES.items():
			self.assertEqual(frappe.get_meta(doctype, cached=False).autoname, series)

		for doctype, series in BASE_NAMING_SERIES.items():
			field = frappe.get_meta(doctype, cached=False).get_field("naming_series")
			self.assertEqual(field.options, series)
			self.assertEqual(field.default, series)
			self.assertFalse(
				frappe.db.exists(
					"Property Setter",
					{"doc_type": doctype, "field_name": "naming_series"},
				)
			)

	def test_generated_names_use_yrp_prefix(self):
		for doctype in (*ESSDEE_NAMING_SERIES, *ESSDEE_AUTONAME_SERIES):
			doc = frappe.new_doc(doctype)
			set_new_name(doc)
			self.assertTrue(doc.name.startswith("YRP-"), f"{doctype}: {doc.name}")
