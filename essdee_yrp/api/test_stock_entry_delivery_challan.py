from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api import stock_entry as stock_entry_api
from essdee_yrp.api.stock_entry import build_delivery_rows


class _FakeDocument(frappe._dict):
	def check_permission(self, *_args, **_kwargs):
		return None


class _FakeDeliveryChallan(frappe._dict):
	def __init__(self):
		super().__init__(doctype="Delivery Challan", items=[])
		self.was_inserted = False

	def append(self, fieldname, value):
		self.setdefault(fieldname, []).append(frappe._dict(value))

	def insert(self):
		self.name = "DC-TEST-1"
		self.was_inserted = True
		return self


class TestStockEntryDeliveryChallanMapping(UnitTestCase):
	def test_maps_stock_quantity_and_dimensions_to_work_order_deliverable(self):
		work_order = frappe._dict(
			name="WO-1",
			lot="LOT-1",
			deliverables=[
				frappe._dict(
					name="WOD-1",
					item_variant="ITEM-RED-M",
					uom="Nos",
					pending_quantity=8,
					table_index=1,
					row_index="2",
					set_combination='{"Panel":"Front"}',
					lot="LOT-1",
				)
			],
		)
		stock_rows = [
			frappe._dict(
				item="ITEM-RED-M",
				qty=5,
				uom="Nos",
				secondary_qty=2.5,
				secondary_uom="Kg",
				lot="LOT-1",
				received_type="Accepted",
				remarks="Ready to dispatch",
			)
		]

		rows = build_delivery_rows(
			stock_rows,
			work_order,
			["lot", "received_type"],
			["lot"],
		)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_variant"], "ITEM-RED-M")
		self.assertEqual(rows[0]["qty"], 5)
		self.assertEqual(rows[0]["delivered_quantity"], 5)
		self.assertEqual(rows[0]["secondary_qty"], 2.5)
		self.assertEqual(rows[0]["ref_docname"], "WOD-1")
		self.assertEqual(rows[0]["set_combination"], '{"Panel":"Front"}')
		self.assertEqual(rows[0]["lot"], "LOT-1")
		self.assertEqual(rows[0]["received_type"], "Accepted")

	def test_splits_across_duplicate_deliverables_then_keeps_excess(self):
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(name="WOD-1", item_variant="ITEM-1", uom="Kg", pending_quantity=2),
				frappe._dict(name="WOD-2", item_variant="ITEM-1", uom="Kg", pending_quantity=3),
			],
		)
		stock_rows = [frappe._dict(item="ITEM-1", qty=7, uom="Kg")]

		rows = build_delivery_rows(stock_rows, work_order, [], [])

		self.assertEqual([row["ref_docname"] for row in rows], ["WOD-1", "WOD-2"])
		self.assertEqual([row["qty"] for row in rows], [4, 3])

	def test_stock_entry_display_indexes_do_not_override_work_order_allocation(self):
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(
					name="WOD-1",
					item_variant="ITEM-1",
					uom="Kg",
					pending_quantity=2,
					table_index=0,
					row_index="0",
				),
				frappe._dict(
					name="WOD-2",
					item_variant="ITEM-1",
					uom="Kg",
					pending_quantity=4,
					table_index=9,
					row_index="9",
				),
			],
		)

		rows = build_delivery_rows(
			[frappe._dict(item="ITEM-1", qty=3, uom="Kg", table_index=9, row_index=9)],
			work_order,
			[],
			[],
		)

		self.assertEqual([row["ref_docname"] for row in rows], ["WOD-1", "WOD-2"])
		self.assertEqual([row["qty"] for row in rows], [2, 1])

	def test_duplicate_stock_rows_share_remaining_work_order_quantity(self):
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(name="WOD-1", item_variant="ITEM-1", uom="Kg", pending_quantity=3),
				frappe._dict(name="WOD-2", item_variant="ITEM-1", uom="Kg", pending_quantity=2),
			],
		)

		rows = build_delivery_rows(
			[
				frappe._dict(item="ITEM-1", qty=2, uom="Kg"),
				frappe._dict(item="ITEM-1", qty=3, uom="Kg"),
			],
			work_order,
			[],
			[],
		)

		self.assertEqual(
			[(row["ref_docname"], row["qty"]) for row in rows],
			[("WOD-1", 2), ("WOD-1", 1), ("WOD-2", 2)],
		)

	def test_rejects_stock_item_outside_selected_work_order(self):
		work_order = frappe._dict(
			name="WO-1",
			deliverables=[
				frappe._dict(name="WOD-1", item_variant="ITEM-1", uom="Kg", pending_quantity=2),
			],
		)

		with self.assertRaises(frappe.ValidationError):
			build_delivery_rows(
				[frappe._dict(item="OTHER-ITEM", qty=1, uom="Kg")],
				work_order,
				[],
				[],
			)

	def test_rejects_a_different_production_group(self):
		work_order = frappe._dict(
			name="WO-1",
			lot="LOT-1",
			deliverables=[
				frappe._dict(
					name="WOD-1",
					item_variant="ITEM-1",
					uom="Kg",
					pending_quantity=2,
					lot="LOT-1",
				)
			],
		)

		with self.assertRaises(frappe.ValidationError):
			build_delivery_rows(
				[frappe._dict(item="ITEM-1", qty=1, uom="Kg", lot="LOT-2")],
				work_order,
				["lot"],
				["lot"],
			)

	def test_endpoint_allows_same_location_and_warehouse(self):
		entry = _FakeDocument(
			name="STE-1",
			docstatus=1,
			from_supplier="DYEING",
			from_warehouse="DYEING-WH",
			to_supplier="DYEING",
			to_warehouse="DYEING-WH",
			items=[frappe._dict(item="ITEM-1", qty=3, uom="Kg", lot="LOT-1")],
		)
		order = _FakeDocument(
			name="WO-1",
			docstatus=1,
			open_status="Open",
			is_delivered=0,
			lot="LOT-1",
			deliverables=[
				frappe._dict(
					name="WOD-1",
					item_variant="ITEM-1",
					uom="Kg",
					pending_quantity=5,
					lot="LOT-1",
				)
			],
		)
		delivery_challan = _FakeDeliveryChallan()

		def get_doc(doctype, name):
			return {("Stock Entry", "STE-1"): entry, ("Work Order", "WO-1"): order}[
				(doctype, name)
			]

		def exists(doctype, filters):
			if doctype == "Supplier":
				return filters["name"] == "DYEING"
			if doctype == "Warehouse":
				return filters["name"] == "DYEING-WH"
			return False

		with (
			patch.object(stock_entry_api.frappe, "has_permission", return_value=True),
			patch.object(stock_entry_api.frappe, "get_doc", side_effect=get_doc),
			patch.object(stock_entry_api.frappe.db, "exists", side_effect=exists),
			patch.object(stock_entry_api.frappe, "new_doc", return_value=delivery_challan),
			patch.object(stock_entry_api, "nowdate", return_value="2026-09-19"),
			patch.object(stock_entry_api, "nowtime", return_value="12:00:00"),
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=["lot"]),
			patch(
				"yrp.stock.dimensions.get_stock_dimensions",
				return_value=[{"fieldname": "lot", "is_production_group": 1}],
			),
		):
			result = stock_entry_api.make_delivery_challan(
				"STE-1", "WO-1", "DYEING", "DYEING"
			)

		self.assertEqual(result, {"name": "DC-TEST-1"})
		self.assertTrue(delivery_challan.was_inserted)
		self.assertEqual(delivery_challan.work_order, "WO-1")
		self.assertEqual(delivery_challan.from_location, "DYEING")
		self.assertEqual(delivery_challan.supplier, "DYEING")
		self.assertEqual(delivery_challan.from_warehouse, "DYEING-WH")
		self.assertEqual(delivery_challan.to_warehouse, "DYEING-WH")
		self.assertEqual(delivery_challan.get("items")[0].qty, 3)
		self.assertEqual(delivery_challan.get("items")[0].ref_docname, "WOD-1")
