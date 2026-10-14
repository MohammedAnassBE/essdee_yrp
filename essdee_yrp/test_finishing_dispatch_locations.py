from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch import (
	sd_yrp_finishing_plan_dispatch as finishing_plan_dispatch,
)
from essdee_yrp.finishing import transactions


class TestFinishingDispatchLocations(IntegrationTestCase):
	def setUp(self):
		self.from_supplier = _supplier()
		self.from_warehouse = _warehouse(self.from_supplier)
		self.to_supplier = _supplier()
		self.to_warehouse = _warehouse(self.to_supplier)

	def locations(self, **overrides):
		return {
			"from_supplier": self.from_supplier,
			"from_warehouse": self.from_warehouse,
			"to_supplier": self.to_supplier,
			"to_warehouse": self.to_warehouse,
			**overrides,
		}

	def expected_header(self):
		return {**self.locations(), "transfer_supplier": self.to_supplier}

	def test_box_dispatch_sets_both_supplier_warehouse_pairs(self):
		header, populate_rates, stock_entry = _box_dispatch(self.locations())

		self.assertLessEqual(self.expected_header().items(), header.items())
		self.assertEqual(populate_rates.call_args.args[1], self.from_warehouse)
		stock_entry.submit.assert_called_once_with()

	def test_plan_dispatch_sets_both_supplier_warehouse_pairs(self):
		header, populate_rates, stock_entry = _plan_dispatch(self.locations())

		self.assertLessEqual(self.expected_header().items(), header.items())
		self.assertEqual(populate_rates.call_args.args[1], self.from_warehouse)
		stock_entry.submit.assert_called_once_with()

	def test_rejects_warehouse_not_linked_to_its_supplier(self):
		for dispatch in (_box_dispatch, _plan_dispatch):
			with self.subTest(dispatch=dispatch.__name__):
				with self.assertRaisesRegex(
					frappe.ValidationError,
					f"Warehouse {self.from_warehouse} is not linked to Supplier {self.to_supplier}",
				):
					dispatch(self.locations(to_warehouse=self.from_warehouse))

	def test_rejects_supplier_without_warehouse(self):
		supplier = _supplier()
		for dispatch in (_box_dispatch, _plan_dispatch):
			with self.subTest(dispatch=dispatch.__name__):
				with self.assertRaisesRegex(
					frappe.ValidationError,
					f"Supplier {supplier} has no Warehouse. Create one from the Supplier.",
				):
					dispatch(self.locations(to_supplier=supplier, to_warehouse=self.to_warehouse))

	def test_rejects_disabled_warehouse(self):
		frappe.db.set_value("Warehouse", self.from_warehouse, "disabled", 1)
		_warehouse(self.from_supplier)

		with self.assertRaisesRegex(frappe.ValidationError, f"Warehouse {self.from_warehouse} is disabled"):
			_box_dispatch(self.locations())

	def test_supplier_warehouses_lists_only_enabled_linked_warehouses(self):
		second = _warehouse(self.from_supplier)
		frappe.db.set_value("Warehouse", second, "disabled", 1)
		from essdee_yrp.finishing.dispatch_locations import get_supplier_warehouses

		self.assertEqual(get_supplier_warehouses(self.from_supplier), [self.from_warehouse])


def _supplier():
	group = frappe.get_all("Supplier Group", filters={"is_group": 0}, pluck="name", limit=1)[0]
	supplier = frappe.get_doc(
		{
			"doctype": "Supplier",
			"supplier_name": f"FP Dispatch {frappe.generate_hash(length=8)}",
			"supplier_group": group,
		}
	)
	return supplier.insert(ignore_permissions=True).name


def _warehouse(supplier):
	warehouse = frappe.get_doc(
		{
			"doctype": "Warehouse",
			"warehouse_name": f"FP Dispatch Store {frappe.generate_hash(length=8)}",
			"company": frappe.db.get_value("Company", {}, "name"),
			"supplier": supplier,
		}
	)
	return warehouse.insert(ignore_permissions=True).name


def _box_dispatch(locations):
	finishing_doc = MagicMock(lot="LOT-TEST", item="ITEM-TEST", production_detail="IPD-TEST")
	stock_entry = MagicMock()
	with (
		patch.object(transactions.frappe, "get_doc", return_value=finishing_doc),
		patch.object(transactions.frappe, "get_cached_doc", return_value=frappe._dict(name="IPD-TEST")),
		patch.object(transactions.frappe, "new_doc", return_value=stock_entry),
		patch(
			"essdee_yrp.finishing.packing.get_finishing_packing_summary",
			return_value=frappe._dict(dynamic_ratio_packing=False),
		),
		patch.object(transactions, "_validate_legacy_dispatch_balance"),
		patch.object(transactions, "build_variant_attributes"),
		patch.object(transactions, "get_or_create_variant", return_value="ITEM-TEST-S"),
		patch.object(transactions.attribute_db, "get_value", return_value="Box"),
		patch.object(transactions, "populate_stock_rates") as populate_rates,
	):
		transactions.create_stock_entry(
			data={"S": {"cur_dispatch": 1}},
			item_name="ITEM-TEST",
			doc_name="FP-TEST",
			lot="LOT-TEST",
			goods_value=100,
			vehicle_no="TN-TEST",
			**locations,
		)
	return stock_entry.update.call_args.args[0], populate_rates, stock_entry


def _plan_dispatch(locations):
	dispatch = SimpleNamespace(
		docstatus=1,
		stock_entry=None,
		packing_batch_dispatch_json=None,
		dispatch_colour_details=None,
		finishing_plan_dispatch_items=[
			SimpleNamespace(
				item_variant="ITEM-S",
				quantity=4,
				lot="LOT-1",
				uom="Nos",
				against_id="FP-TEST",
				packing_source="",
			)
		],
		check_permission=MagicMock(),
	)
	stock_entry = MagicMock()
	with (
		patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch),
		patch.object(finishing_plan_dispatch.frappe, "new_doc", return_value=stock_entry),
		patch.object(finishing_plan_dispatch, "populate_stock_rates") as populate_rates,
	):
		finishing_plan_dispatch.create_stock_dispatch(
			doc_name="FPD-TEST", goods_value=100, vehicle_no="TN-TEST", **locations
		)
	return stock_entry.update.call_args.args[0], populate_rates, stock_entry
