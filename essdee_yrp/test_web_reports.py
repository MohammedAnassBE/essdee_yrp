import unittest

import frappe
from frappe.desk.query_report import run as run_query_report
from frappe.tests import IntegrationTestCase
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache

from essdee_yrp.cut_panel_store.report_workspace import get_cut_bundle_balance


class TestEssdeeWebReportParity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.fixture_key = frappe.generate_hash(length=10).lower()
		cls.item = _physical_item()
		if not cls.item:
			raise unittest.SkipTest("needs one physical stock Item")
		company = frappe.db.get_value("Company", {}, "name")
		cls.warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"Web Report Parity {frappe.generate_hash(length=8)}",
				"company": company,
			}
		).insert(ignore_permissions=True).name
		cls.stock_ledger = _insert_stock_ledger(cls.item, cls.warehouse)
		cls.purchase_order = _insert_purchase_order(cls.fixture_key, cls.item, company)
		cls.finishing_plan, cls.fixture_lot = _insert_finishing_plan(cls.fixture_key, cls.item)
		cls.cut_bundle_ledger = _insert_cut_bundle_ledger(cls.fixture_key, cls.item, cls.fixture_lot)

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		_delete_fixture("SD YRP Cut Bundle Movement Ledger", getattr(cls, "cut_bundle_ledger", None))
		_delete_fixture("SD YRP Finishing Plan Detail", f"WEB-FPD-{getattr(cls, 'fixture_key', '')}")
		_delete_fixture("SD YRP Finishing Plan", getattr(cls, "finishing_plan", None))
		_delete_fixture("Purchase Order Item", f"WEB-POI-{getattr(cls, 'fixture_key', '')}")
		_delete_fixture("Purchase Order", getattr(cls, "purchase_order", None))
		_delete_fixture("YRP Stock Ledger Entry", getattr(cls, "stock_ledger", None))
		if frappe.db.exists("Warehouse", cls.warehouse):
			frappe.delete_doc("Warehouse", cls.warehouse, ignore_permissions=True, force=True)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()

	def test_stock_balance_matches_query_report(self):
		filters = {
			"from_date": frappe.utils.today(),
			"to_date": frappe.utils.today(),
			"item": self.item,
			"parent_item": "",
			"warehouse": self.warehouse,
			"lot": "",
			"received_type": "",
			"remove_zero_balance_item": 1,
			"show_variant_attributes": 0,
			"show_stock_ageing_data": 0,
			"show_inward_date_split": 0,
		}
		expected = self._assert_query_report_parity("stock-balance", "YRP Stock Balance", filters)
		self.assertIn(self.item, {row["item"] for row in expected["result"]})

	def test_purchase_order_itemwise_matches_query_report(self):
		filters = {
			"item": "",
			"supplier": "",
			"purchase_order": self.purchase_order,
			"delivery_location": "",
			"lot": "",
			"status": "",
			"open_status": "Open",
			"docstatus": "",
			"date_based_on": "",
			"from_date": "",
			"to_date": "",
		}
		expected = self._assert_query_report_parity(
			"purchase-order-itemwise",
			"SD YRP Purchase Order Itemwise",
			filters,
		)
		self.assertEqual([row["name"] for row in expected["result"]], [self.purchase_order])

	def test_finishing_plan_matches_query_report(self):
		filters = {"lot": self.fixture_lot, "item": self.item, "season": "", "product_category": ""}
		expected = self._assert_query_report_parity(
			"finishing-plan",
			"SD YRP Finishing Plan Report",
			filters,
		)
		self.assertEqual([(row["item"], row["lot"]) for row in expected["result"]], [(self.item, self.fixture_lot)])

	def test_cut_bundle_balance_matches_existing_endpoint(self):
		filters = {"lot": self.fixture_lot, "supplier": ""}
		expected = get_cut_bundle_balance(filters)
		actual = run_web_report("cut-bundle-balance", filters)
		self.assertEqual([row["name"] for row in expected["result"]], [self.cut_bundle_ledger])
		self.assertEqual(actual["columns"], expected["columns"])
		self.assertEqual(actual["result"], expected["result"])
		self.assertEqual(actual["summary"], expected["summary"])

	def _assert_query_report_parity(self, key, report_name, filters):
		expected = run_query_report(
			report_name,
			filters=dict(filters),
			ignore_prepared_report=True,
			are_default_filters=True,
		)
		actual = run_web_report(key, dict(filters))
		self.assertTrue(expected["result"], f"Controlled {key} fixture produced no rows")
		self.assertEqual(actual["columns"], expected["columns"])
		self.assertEqual(actual["result"], expected["result"])
		self.assertEqual(actual["report_summary"], expected["report_summary"])
		self.assertEqual(actual["message"], expected["message"])
		return expected


def _physical_item():
	items = frappe.db.sql(
		"""select name from `tabItem`
		where is_stock_item = 1 and (coalesce(variant_of, '') != '' or coalesce(has_variants, 0) = 0)
		order by name limit 1""",
		pluck=True,
	)
	return items[0] if items else None


def _insert_stock_ledger(item, warehouse):
	dimensions = {}
	from yrp.stock.dimensions import get_stock_dimensions

	for dimension in get_stock_dimensions():
		value = frappe.db.get_value(dimension["dimension_doctype"], {}, "name")
		if dimension.get("mandatory") and not value:
			raise RuntimeError(f"needs one {dimension['dimension_doctype']}")
		dimensions[dimension["fieldname"]] = value
	doc = frappe.get_doc(
		{
			"doctype": "YRP Stock Ledger Entry",
			"item": item,
			"warehouse": warehouse,
			"posting_date": frappe.utils.today(),
			"posting_time": frappe.utils.nowtime(),
			"voucher_type": "Item",
			"voucher_no": f"WEB-STOCK-{frappe.generate_hash(length=8)}",
			"qty": 11,
			"qty_after_transaction": 11,
			"rate": 5,
			"valuation_rate": 5,
			"stock_value": 55,
			"stock_value_difference": 55,
			**dimensions,
		}
	).insert(ignore_permissions=True, ignore_links=True)
	return doc.name


def _insert_purchase_order(key, item, company):
	name = f"WEB-PO-{key}"
	parent = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"name": name,
			"company": company,
			"supplier": f"WEB-SUPPLIER-{key}",
			"supplier_name": "Web Report Supplier",
			"transaction_date": frappe.utils.today(),
			"schedule_date": frappe.utils.today(),
			"status": "Draft",
			"open_status": "Open",
		}
	)
	parent.db_insert()
	child = frappe.get_doc(
		{
			"doctype": "Purchase Order Item",
			"name": f"WEB-POI-{key}",
			"parent": name,
			"parenttype": "Purchase Order",
			"parentfield": "items",
			"idx": 1,
			"item_code": item,
			"item_name": item,
			"description": item,
			"schedule_date": frappe.utils.today(),
			"qty": 7,
			"stock_qty": 7,
			"pending_quantity": 7,
			"cancelled_quantity": 0,
			"uom": frappe.db.get_value("Item", item, "stock_uom"),
			"stock_uom": frappe.db.get_value("Item", item, "stock_uom"),
			"conversion_factor": 1,
			"rate": 13,
			"amount": 91,
		}
	)
	child.db_insert()
	return name


def _insert_finishing_plan(key, item):
	name = f"WEB-FP-{key}"
	lot = f"WEB-LOT-{key}"
	parent = frappe.get_doc(
		{
			"doctype": "SD YRP Finishing Plan",
			"name": name,
			"item": item,
			"lot": lot,
			"is_set_item": 0,
			"pieces_per_box": 5,
			"fp_status": "Planned",
		}
	)
	parent.db_insert()
	child = frappe.get_doc(
		{
			"doctype": "SD YRP Finishing Plan Detail",
			"name": f"WEB-FPD-{key}",
			"parent": name,
			"parenttype": "SD YRP Finishing Plan",
			"parentfield": "finishing_plan_details",
			"idx": 1,
			"item_variant": item,
			"cutting_qty": 10,
			"delivered_quantity": 8,
			"dc_qty": 7,
			"lot_transferred": 0,
			"ironing_excess": 0,
			"return_qty": 0,
			"pack_return_qty": 0,
			"transferred_qty": 0,
		}
	)
	child.db_insert()
	return name, lot


def _insert_cut_bundle_ledger(key, item, lot):
	name = f"WEB-CBM-{key}"
	doc = frappe.get_doc(
		{
			"doctype": "SD YRP Cut Bundle Movement Ledger",
			"name": name,
			"lot": lot,
			"item": item,
			"supplier": f"WEB-SUPPLIER-{key}",
			"supplier_name": "Web Report Supplier",
			"lay_no": 1,
			"bundle_no": 1,
			"panel": "Front",
			"shade": "A",
			"size": "M",
			"colour": "Blue",
			"quantity": 9,
			"quantity_after_transaction": 9,
			"posting_date": frappe.utils.today(),
			"posting_time": frappe.utils.nowtime(),
			"posting_datetime": frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=-1),
			"cbm_key": f"WEB-CBM-KEY-{key}",
			"is_cancelled": 0,
			"is_collapsed": 0,
			"collapsed_bundle": 0,
			"transformed": 0,
		}
	)
	doc.db_insert()
	return name


def _delete_fixture(doctype, name):
	if name and frappe.db.exists(doctype, name):
		frappe.db.delete(doctype, {"name": name})
