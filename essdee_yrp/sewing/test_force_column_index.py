import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sewing.entry import _force_column_index


class TestForceColumnIndex(IntegrationTestCase):
	def test_hint_uses_the_site_index_name(self):
		table = "tabSD YRP Sewing Plan"
		name = frappe.db.get_column_index(table, "supplier").Key_name
		hint = _force_column_index(table, "supplier")
		self.assertEqual(hint, f"force index (`{name}`)")
		frappe.db.sql(f"select name from `{table}` {hint} where supplier = %s", "x")

	def test_no_hint_without_an_index(self):
		self.assertEqual(_force_column_index("tabSD YRP Sewing Plan", "supplier_address"), "")
