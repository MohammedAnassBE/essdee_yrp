from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import lot_packing_setup, packing_hooks, purchase_order_lots, work_order_hooks
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot as lot_controller


class FakePurchaseOrder(frappe._dict):
	def __init__(self, **values):
		super().__init__(values)
		self.setdefault("doctype", 'YRP Purchase Order')
		self.setdefault("docstatus", 0)
		self.setdefault("sd_lot", [])
		self.meta = frappe._dict(get_field=lambda fieldname: True)

	def append(self, fieldname, value):
		row = frappe._dict(value)
		self[fieldname].append(row)
		return row

	def set(self, fieldname, value):
		self[fieldname] = value

	def check_permission(self, permission_type):
		return None


class FakeLot(frappe._dict):
	def __init__(self, **values):
		super().__init__(values)
		self.setdefault("docstatus", 0)
		self.setdefault("production_detail", "IPD-1")
		self.setdefault("lot_order_details", [])
		self.setdefault("items", [])
		self.setdefault("lot_time_and_action_details", [])
		self.setdefault("allow_write", True)
		self.saved = False
		self.calculated = False

	def check_permission(self, permission_type):
		if permission_type == "write" and not self.allow_write:
			raise frappe.PermissionError

	def set(self, fieldname, value):
		self[fieldname] = value

	def calculate_order(self):
		self.calculated = True

	def save(self):
		self.saved = True


class TestLotPackingBoundary(FrappeTestCase):
	def test_boundary_fields_are_essdee_custom_fields(self):
		expected = {
			('YRP Purchase Order', "default_lot"): ("Link", 'SD YRP Lot'),
			('YRP Purchase Order', "sd_lot"): ("Table", 'SD YRP Lot MultiSelect'),
			('YRP Process', "includes_packing"): ("Check", None),
			('YRP Work Order', "includes_packing"): ("Check", None),
		}
		for (doctype, fieldname), (fieldtype, options) in expected.items():
			custom_field = frappe.get_doc("Custom Field", f"{doctype}-{fieldname}")
			self.assertEqual(custom_field.module, "Essdee YRP")
			self.assertEqual(custom_field.fieldtype, fieldtype)
			if options:
				self.assertEqual(custom_field.options, options)

		for fieldname in ("lot_details_section", "default_lot", "sd_lot"):
			self.assertEqual(
				frappe.get_meta('YRP Purchase Order').get_field(fieldname).hidden,
				1,
				fieldname,
			)

		self.assertEqual(frappe.get_meta('SD YRP Lot MultiSelect').module, "Essdee YRP")

	def test_linked_lots_are_deduplicated_and_defaulted(self):
		doc = FakePurchaseOrder(
			sd_lot=[frappe._dict(lot="LOT-A"), frappe._dict(lot="LOT-A")]
		)
		with (
			patch.object(purchase_order_lots, "_lot_dimension_field", return_value=None),
			patch.object(purchase_order_lots, "_check_lot_permission"),
		):
			purchase_order_lots.sync_linked_lots(doc)
		self.assertEqual(doc.default_lot, "LOT-A")
		self.assertEqual([row.lot for row in doc.sd_lot], ["LOT-A"])

	def test_po_item_lots_sync_into_hidden_legacy_links(self):
		doc = FakePurchaseOrder(
			items=[
				frappe._dict(lot="LOT-A"),
				frappe._dict(lot="LOT-B"),
				frappe._dict(lot="LOT-A"),
			]
		)
		with (
			patch.object(purchase_order_lots, "_lot_dimension_field", return_value="lot"),
			patch.object(purchase_order_lots, "_check_lot_permission"),
		):
			purchase_order_lots.sync_linked_lots(doc)
		self.assertEqual([row.lot for row in doc.sd_lot], ["LOT-A", "LOT-B"])
		# Multiple row Lots have no unambiguous legacy header default.
		self.assertIsNone(doc.default_lot)

	def test_grn_rejects_unlinked_configured_lot(self):
		po = frappe._dict(sd_lot=[frappe._dict(lot="LOT-A")])
		grn = frappe._dict(
			against='YRP Purchase Order',
			against_id="PO-TEST",
			items=[frappe._dict(lot="LOT-B")],
		)
		with (
			patch.object(purchase_order_lots, "_lot_dimension_field", return_value="lot"),
			patch.object(frappe, "get_doc", return_value=po),
			self.assertRaisesRegex(frappe.ValidationError, "LOT-B"),
		):
			purchase_order_lots.validate_grn_lots(grn)

	def test_grn_accepts_allowed_or_unrestricted_lot(self):
		grn = frappe._dict(
			against='YRP Purchase Order',
			against_id="PO-TEST",
			items=[frappe._dict(lot="LOT-A")],
		)
		with (
			patch.object(purchase_order_lots, "_lot_dimension_field", return_value="lot"),
			patch.object(
				frappe,
				"get_doc",
				side_effect=[
					frappe._dict(sd_lot=[frappe._dict(lot="LOT-A")]),
					frappe._dict(sd_lot=[]),
				],
			),
		):
			purchase_order_lots.validate_grn_lots(grn)
			purchase_order_lots.validate_grn_lots(grn)

	def test_link_mutation_rejects_cancelled_po_and_missing_reason(self):
		cancelled = FakePurchaseOrder(docstatus=2)
		with (
			patch.object(frappe, "get_doc", return_value=cancelled),
			self.assertRaisesRegex(frappe.ValidationError, "cancelled"),
		):
			purchase_order_lots.update_po_lot_links("PO-1", add_lots=["LOT-A"], comment="x")

		draft = FakePurchaseOrder(sd_lot=[frappe._dict(lot="LOT-A")])
		with (
			patch.object(frappe, "get_doc", return_value=draft),
			self.assertRaisesRegex(frappe.ValidationError, "Reason is required"),
		):
			purchase_order_lots.update_po_lot_links("PO-1", add_lots=["LOT-B"])

	def test_legacy_child_copy_is_idempotent_with_duplicate_source_rows(self):
		legacy = [
			frappe._dict(parent="PO-1", lot="LOT-A", idx=1),
			frappe._dict(parent="PO-1", lot="LOT-A", idx=2),
		]
		with (
			patch.object(frappe.db, "table_exists", return_value=True),
			patch.object(frappe.db, "sql", side_effect=[legacy, [], None]) as sql,
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "log_error"),
		):
			result = lot_packing_setup.migrate_legacy_purchase_order_lot_rows()
		self.assertEqual(result, {"found": 2, "copied": 1, "skipped": 1})
		self.assertEqual(sql.call_count, 3)
		legacy_query = sql.call_args_list[0].args[0]
		self.assertIn("`tabPurchase Order Lot`", legacy_query)
		self.assertNotIn("`tabYRP Purchase Order Lot`", legacy_query)
		self.assertIn("'Purchase Order', 'YRP Purchase Order'", legacy_query)

	def test_work_order_packing_is_copied_by_essdee_hook(self):
		doc = frappe._dict(process_name="PACKING", includes_packing=0)
		doc.meta = frappe._dict(get_field=lambda fieldname: True)
		process_meta = frappe._dict(get_field=lambda fieldname: True)
		with (
			patch.object(frappe, "get_meta", return_value=process_meta),
			patch.object(frappe.db, "get_value", return_value=1),
		):
			work_order_hooks.set_includes_packing(doc)
		self.assertEqual(doc.includes_packing, 1)

	def test_grn_and_stock_entry_copy_packing_from_their_sources(self):
		meta = frappe._dict(get_field=lambda fieldname: True)
		grn = frappe._dict(process_name="PACKING", includes_packing=0, meta=meta)
		stock_entry = frappe._dict(
			against='YRP Goods Received Note',
			against_id="GRN-1",
			includes_packing=0,
			meta=meta,
		)
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(frappe.db, "get_value", return_value=1),
		):
			packing_hooks.set_grn_includes_packing(grn)
			packing_hooks.set_stock_entry_includes_packing(stock_entry)
		self.assertEqual(grn.includes_packing, 1)
		self.assertEqual(stock_entry.includes_packing, 1)

	def test_lot_bom_uses_permission_checked_saved_demands(self):
		lot = FakeLot(
			lot_order_details=[frappe._dict(item_variant="ITEM-SAVED", quantity=4)]
		)
		bom = {
			"major_deliverables": [
				{"item_variant": "CLOTH-1", "required_qty": 2, "uom": "Kg"}
			],
			"accessories": [],
		}
		with (
			patch.object(frappe, "get_doc", return_value=lot),
			patch.object(
				lot_controller,
				"calculate_essdee_accessory_bom",
				return_value=[],
			),
			patch.object(
				lot_controller,
				"calculate_bom_for_variant_demands",
				return_value=bom,
			) as calculate,
			patch.object(
				lot_controller,
				"_build_lot_bom_rows",
				return_value=[{"item": "CLOTH-1"}],
			),
			patch.object(lot_controller, "_build_bom_summary_json", return_value={}),
		):
			result = lot_controller.calculate_bom("LOT-1")

		calculate.assert_called_once_with(
			"IPD-1",
			[{"item_variant": "ITEM-SAVED", "qty": 4.0}],
		)
		self.assertTrue(lot.saved)
		self.assertEqual(result["bom_summary"], [{"item": "CLOTH-1"}])

	def test_lot_bom_requires_write_permission(self):
		lot = FakeLot(
			lot_order_details=[frappe._dict(item_variant="ITEM-1", quantity=1)],
			allow_write=False,
		)
		with (
			patch.object(frappe, "get_doc", return_value=lot),
			patch.object(
				lot_controller,
				"calculate_bom_for_variant_demands",
			) as calculate,
			self.assertRaises(frappe.PermissionError),
		):
			lot_controller.calculate_bom("LOT-1")

		calculate.assert_not_called()

	def test_order_items_cannot_be_recalculated_after_time_and_action(self):
		lot = FakeLot(
			lot_time_and_action_details=[frappe._dict(time_and_action="TNA-1")]
		)
		with (
			patch.object(frappe, "get_doc", return_value=lot),
			self.assertRaisesRegex(frappe.ValidationError, "after Time and Action"),
		):
			lot_controller.update_order_details("LOT-1")

		self.assertFalse(lot.calculated)
		self.assertFalse(lot.saved)

	def test_order_item_recalculation_requires_write_permission(self):
		lot = FakeLot(allow_write=False)
		with (
			patch.object(frappe, "get_doc", return_value=lot),
			self.assertRaises(frappe.PermissionError),
		):
			lot_controller.update_order_details("LOT-1")

		self.assertFalse(lot.calculated)
		self.assertFalse(lot.saved)
