from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import (
	sd_yrp_grn_rework_item as grn_rework_item,
)
from essdee_yrp.finishing import rebuild


class TestGRNReworkItem(IntegrationTestCase):
	def sync_rework_warehouse(self, **grn_values):
		row = frappe._dict(
			name="ROW-1", quantity=2, received_type="Oil Mark", row_index="0", item_variant="Variant-1"
		)
		grn = frappe._dict(docstatus=1, items=[row], name="GRN-1", to_warehouse="Final", **grn_values)
		rework = MagicMock()
		with (
			patch.object(grn_rework_item, "_received_type_defaults", return_value=("Accepted", "Rejected")),
			patch.object(grn_rework_item.frappe.db, "exists", return_value=None),
			patch.object(grn_rework_item.frappe.db, "get_value", return_value="Transit"),
			patch.object(grn_rework_item.frappe, "new_doc", return_value=rework),
		):
			grn_rework_item.sync_grn_rework(grn)
		return rework.update.call_args.args[0]["warehouse"]

	def test_rework_item_uses_delivery_location_warehouse(self):
		cases = {
			"company to company": {"is_internal_unit": 1},
			"supplier to company": {"is_internal_unit": 0},
			"return": {"is_internal_unit": 0, "is_return": 1},
		}
		for label, values in cases.items():
			with self.subTest(label):
				self.assertEqual(self.sync_rework_warehouse(**values), "Final")

	def test_clearing_requires_stock_in_the_rework_item_warehouse(self):
		parent = frappe._dict(warehouse="Final", grn_number="GRN-1")
		row = frappe._dict(item_variant="Variant-1")
		balances = {"Transit": 2, "Final": 0}

		def clear():
			return grn_rework_item._source_warehouse(
				parent,
				row,
				{"lot": "LOT-1", "received_type": "Oil Mark"},
				1,
				lambda _item, warehouse, **_dims: balances[warehouse],
			)

		with self.assertRaisesRegex(frappe.ValidationError, "Complete Transfer"):
			clear()
		balances["Final"] = 2
		self.assertEqual(clear(), "Final")

	def test_revert_requires_write_permission(self):
		parent = MagicMock()
		parent.check_permission.side_effect = frappe.PermissionError("Not permitted")
		with (
			patch.object(grn_rework_item.frappe, "get_doc", return_value=parent),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
		):
			with self.assertRaises(frappe.PermissionError):
				grn_rework_item.revert_reworked_item("RW-1")
		parent.check_permission.assert_called_once_with("write")
		make_entries.assert_not_called()

	def test_conversion_posts_equal_value_received_type_transfer(self):
		parent = frappe._dict(
			name="RW-TEST",
			lot="LOT-1",
			warehouse="Transit",
			grn_number=None,
		)
		row = frappe._dict(
			name="ROW-1",
			item_variant="Variant-1",
			received_type="Adas",
			uom="Pieces",
			source_grn_item=None,
		)

		def cached_value(doctype, _name, fieldname):
			if doctype == "Item":
				return "Item-1"
			if doctype == "Item" and fieldname == "stock_uom":
				return "Pieces"
			return None

		with (
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=["lot", "received_type"]),
			patch("yrp.stock.utils.get_last_sle_rate", return_value=(13.5, True)),
			patch("yrp.stock.utils.get_stock_balance", return_value=4),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
			patch.object(grn_rework_item.frappe, "get_cached_value", side_effect=cached_value),
		):
			grn_rework_item._post_conversions(parent, [(row, "Accepted", 1)])

		entries = make_entries.call_args.args[0]
		self.assertEqual(len(entries), 2)
		self.assertEqual(entries[0]["qty"], -1)
		self.assertEqual(entries[0]["received_type"], "Adas")
		self.assertEqual(entries[0]["outgoing_rate"], 13.5)
		self.assertEqual(entries[1]["qty"], 1)
		self.assertEqual(entries[1]["received_type"], "Accepted")
		self.assertEqual(entries[1]["rate"], 0)
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		make_entries.assert_called_once_with(entries, force_inline=True)

	def test_finishing_ignores_provisional_rejection(self):
		row = frappe._dict(
			item_variant="Variant-1",
			set_combination="{}",
			quantity=3,
			rejection=2,
			completed=0,
		)
		doc = frappe._dict(
			grn_number="GRN-1",
			grn_rework_item_details=[row],
			grn_reworked_item_details=[],
		)
		with (
			patch.object(rebuild.frappe, "get_all", side_effect=[["RW-1"], []]),
			patch.object(rebuild.frappe, "get_doc", return_value=doc),
			patch.object(rebuild.frappe.db, "get_value", return_value=0),
		):
			values = rebuild._collect_rework("LOT-1", {}, "Accepted", "Rejected")
		self.assertEqual(next(iter(values.values()))["rejected_qty"], 0)


class TestRevertReworkedItem(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		savepoint = f"rework_revert_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		self.addCleanup(lambda: frappe.db.rollback(save_point=savepoint))
		self.enterContext(patch.object(grn_rework_item, "_rebuild_finishing"))
		source = frappe.db.sql(
			"""
			SELECT detail.item_variant, detail.received_type, detail.uom, rework.lot
			FROM `tabSD YRP GRN Rework Item Detail` detail
			JOIN `tabSD YRP GRN Rework Item` rework ON rework.name = detail.parent
			WHERE IFNULL(rework.lot, '') != ''
			LIMIT 1
			""",
			as_dict=True,
		)
		if not source:
			self.skipTest("No Rework Item source row is available")
		self.source = source[0]
		self.accepted, self.rejected = grn_rework_item._received_type_defaults()
		self.warehouse = (
			frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": f"_Test Rework Revert {frappe.generate_hash(length=8)}",
					"company": frappe.db.get_value("Company", {}, "name"),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.receive(10)
		self.rework = self.make_rework_item(quantity=10)

	def receive(self, qty):
		from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item

		frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": "Material Receipt",
				"to_warehouse": self.warehouse,
				"items": [
					{
						"item": self.source.item_variant,
						"qty": qty,
						"rate": 20,
						"uom": frappe.db.get_value(
							"Item", get_parent_item(self.source.item_variant), "stock_uom"
						),
						"row_index": 0,
						"table_index": 0,
						"lot": self.source.lot,
						"received_type": self.source.received_type,
					}
				],
			}
		).insert().submit()

	def make_rework_item(self, quantity):
		rework = frappe.new_doc("SD YRP GRN Rework Item")
		rework.update({"naming_series": "RW-", "lot": self.source.lot, "warehouse": self.warehouse})
		rework.append(
			"grn_rework_item_details",
			{
				"item_variant": self.source.item_variant,
				"received_type": self.source.received_type,
				"quantity": quantity,
				"uom": self.source.uom,
				"set_combination": "{}",
			},
		)
		return rework.insert(ignore_permissions=True)

	def balances(self):
		from yrp.stock.utils import get_stock_balance

		values = {}
		for received_type in (self.source.received_type, self.accepted, self.rejected):
			balance = get_stock_balance(
				self.source.item_variant,
				self.warehouse,
				with_valuation_rate=True,
				lot=self.source.lot,
				received_type=received_type,
			)
			values[received_type] = tuple(flt(value, 4) for value in balance)
		return values

	def active_conversion_entries(self):
		return frappe.db.count(
			"YRP Stock Ledger Entry",
			{"voucher_type": "SD YRP GRN Rework Item", "voucher_no": self.rework.name, "is_cancelled": 0},
		)

	def test_revert_restores_stock_and_reopens_rows(self):
		before = self.balances()
		row_name = self.rework.grn_rework_item_details[0].name
		grn_rework_item.update_partial_quantity(frappe.as_json([{"row_name": row_name, "rework": 4}]))
		grn_rework_item.update_rejected_quantity(
			frappe.as_json([{"row_name": row_name, "rejected": 2}]), completed=1
		)
		self.assertEqual(self.balances()[self.accepted][0], 8)
		self.assertEqual(self.balances()[self.rejected][0], 2)

		grn_rework_item.revert_reworked_item(self.rework.name)

		self.assertEqual(self.balances(), before)
		self.assertEqual(self.active_conversion_entries(), 0)
		self.rework.reload()
		row = self.rework.grn_rework_item_details[0]
		self.assertEqual((row.reworked, row.rejection, row.completed, self.rework.completed), (0, 0, 0, 0))
		self.assertEqual(self.rework.grn_reworked_item_details, [])
		self.assertEqual(self.rework.grn_rejected_item_details, [])

	def test_revert_is_blocked_when_converted_stock_was_used(self):
		row_name = self.rework.grn_rework_item_details[0].name
		grn_rework_item.update_partial_quantity(frappe.as_json([{"row_name": row_name, "rework": 4}]))
		frappe.get_doc(
			{
				"doctype": "YRP Stock Entry",
				"purpose": "Material Issue",
				"from_warehouse": self.warehouse,
				"items": [
					{
						"item": self.source.item_variant,
						"qty": 4,
						"uom": self.source.uom,
						"row_index": 0,
						"table_index": 0,
						"lot": self.source.lot,
						"received_type": self.accepted,
					}
				],
			}
		).insert().submit()

		with self.assertRaisesRegex(frappe.ValidationError, "Insufficient stock"):
			grn_rework_item.revert_reworked_item(self.rework.name)

	def test_revert_without_rework_entries_fails(self):
		with self.assertRaisesRegex(frappe.ValidationError, "no rework entries"):
			grn_rework_item.revert_reworked_item(self.rework.name)
