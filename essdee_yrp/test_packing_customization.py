import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import delivery_challan_hooks, packing_hooks, work_order_hooks


class FakeDocument(frappe._dict):
	def __init__(self, **values):
		super().__init__(values)
		self.meta = frappe._dict(get_field=lambda fieldname: True)

	def set(self, fieldname, value):
		self[fieldname] = value


class TestPackingCustomization(FrappeTestCase):
	def test_packing_fields_are_packaged_by_essdee(self):
		with open(
			frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json"),
			encoding="utf-8",
		) as fixture_file:
			fields = {row.get("name"): row for row in json.load(fixture_file)}

		for doctype in (
			"Process",
			"Work Order",
			"Delivery Challan",
			"Goods Received Note",
			"Stock Entry",
		):
			field = fields[f"{doctype}-includes_packing"]
			self.assertEqual(field["module"], "Essdee YRP")
			self.assertEqual(field["fieldtype"], "Check")

	def test_work_order_and_grn_copy_process_packing_rule(self):
		process_meta = frappe._dict(get_field=lambda fieldname: True)
		work_order = FakeDocument(process_name="PACKING", includes_packing=0)
		grn = FakeDocument(process_name="PACKING", includes_packing=0)
		with (
			patch.object(frappe, "get_meta", return_value=process_meta),
			patch.object(frappe.db, "get_value", return_value=1),
		):
			work_order_hooks.set_includes_packing(work_order)
			packing_hooks.set_grn_includes_packing(grn)

		self.assertEqual(work_order.includes_packing, 1)
		self.assertEqual(grn.includes_packing, 1)

	def test_dc_and_stock_entry_copy_their_source_packing_rule(self):
		source_meta = frappe._dict(get_field=lambda fieldname: True)
		dc = FakeDocument(work_order="WO-1", includes_packing=0)
		stock_entry = FakeDocument(
			against="Goods Received Note",
			against_id="GRN-1",
			includes_packing=0,
		)
		with (
			patch.object(frappe, "get_meta", return_value=source_meta),
			patch.object(frappe.db, "get_value", return_value=1),
		):
			delivery_challan_hooks.before_validate(dc)
			packing_hooks.set_stock_entry_includes_packing(stock_entry)

		self.assertEqual(dc.includes_packing, 1)
		self.assertEqual(stock_entry.includes_packing, 1)
