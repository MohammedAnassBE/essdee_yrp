import frappe
from frappe.tests.utils import FrappeTestCase

STANDARD_FILTERS = {
	"YRP Delivery Challan": ("transfer_complete",),
	"YRP Goods Received Note": ("transfer_complete", "lot"),
}


class TestDcGrnListFilters(FrappeTestCase):
	def test_transfer_complete_and_grn_lot_are_standard_filters(self):
		for doctype, fieldnames in STANDARD_FILTERS.items():
			meta = frappe.get_meta(doctype, cached=False)
			for fieldname in fieldnames:
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field, f"{doctype}.{fieldname}")
				self.assertEqual(field.in_standard_filter, 1, f"{doctype}.{fieldname}")
