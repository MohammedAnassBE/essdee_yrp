from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.overrides import inspection_entry as inspection_override


class TestInspectionEntryCustomization(FrappeTestCase):
	def test_uncompleted_internal_grn_uses_transit_warehouse(self):
		sources = [{"item_variant": "TEST-VARIANT", "warehouse": "FINAL"}]
		grn = frappe._dict(
			name="TEST-GRN",
			is_internal_unit=1,
			transfer_complete=0,
			items=[frappe._dict(ste_received_quantity=0)],
		)
		with (
			patch(
				"essdee_yrp.overrides.inspection_entry.get_base_initial_payload",
				return_value=sources,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.get_doc",
				return_value=grn,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.db.get_single_value",
				return_value="TRANSIT",
			),
			patch("essdee_yrp.overrides.inspection_entry._attach_display_meta") as attach,
		):
			result = inspection_override.get_initial_payload("YRP Goods Received Note", grn.name)

		self.assertEqual(result[0]["warehouse"], "TRANSIT")
		attach.assert_called_once_with(result)

	def test_completed_internal_grn_keeps_final_warehouse(self):
		sources = [{"item_variant": "TEST-VARIANT", "warehouse": "FINAL"}]
		grn = frappe._dict(
			name="TEST-GRN",
			is_internal_unit=1,
			transfer_complete=1,
			items=[frappe._dict(ste_received_quantity=10)],
		)
		with (
			patch(
				"essdee_yrp.overrides.inspection_entry.get_base_initial_payload",
				return_value=sources,
			),
			patch(
				"essdee_yrp.overrides.inspection_entry.frappe.get_doc",
				return_value=grn,
			),
		):
			result = inspection_override.get_initial_payload("YRP Goods Received Note", grn.name)

		self.assertEqual(result[0]["warehouse"], "FINAL")

	@patch.object(frappe, "get_all")
	def test_source_grns_resolve_only_exact_grn_child_references(self, get_all):
		get_all.return_value = [
			frappe._dict(
				name="GRN-ITEM-2",
				parent="GRN-1",
				parenttype="YRP Goods Received Note",
			),
			frappe._dict(
				name="GRN-ITEM-1",
				parent="GRN-1",
				parenttype="YRP Goods Received Note",
			),
		]
		doc = frappe._dict(
			against_id="GRN-1",
			items=[
				frappe._dict(
					ref_doctype="YRP Goods Received Note Item",
					ref_docname="GRN-ITEM-2",
				),
				frappe._dict(
					ref_doctype="YRP Goods Received Note Item",
					ref_docname="GRN-ITEM-1",
				),
				frappe._dict(ref_doctype="YRP Stock Entry Item", ref_docname="STE-ITEM-1"),
			],
		)

		source_items = inspection_override._source_grn_item_names(doc)
		result = inspection_override._source_grn_names(doc, source_items)

		self.assertEqual(source_items, ["GRN-ITEM-1", "GRN-ITEM-2"])
		self.assertEqual(result, ["GRN-1"])
		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			{"name": ["in", ["GRN-ITEM-1", "GRN-ITEM-2"]]},
		)

	@patch.object(frappe, "get_all")
	def test_source_grn_child_must_belong_to_inspection_against_grn(self, get_all):
		get_all.return_value = [
			frappe._dict(
				name="GRN-ITEM-OTHER",
				parent="GRN-OTHER",
				parenttype="YRP Goods Received Note",
			)
		]
		doc = frappe._dict(against_id="GRN-1", items=[])

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"does not belong to Goods Received Note GRN-1",
		):
			inspection_override._source_grn_names(doc, ["GRN-ITEM-OTHER"])

	@patch.object(frappe.db, "sql")
	def test_source_grn_children_are_locked_in_stable_order(self, sql):
		sql.return_value = [
			frappe._dict(
				name="GRN-ITEM-1",
				parent="GRN-1",
				parenttype="YRP Goods Received Note",
			)
		]

		rows = inspection_override._lock_source_grn_items(
			["GRN-ITEM-2", "GRN-ITEM-1", "GRN-ITEM-1"]
		)

		self.assertIn("ORDER BY name FOR UPDATE", sql.call_args.args[0])
		self.assertTrue(sql.call_args.kwargs["as_dict"])
		self.assertEqual(
			sql.call_args.args[1],
			{"names": ("GRN-ITEM-1", "GRN-ITEM-2")},
		)
		self.assertEqual(rows, sql.return_value)

	@patch("yrp.stock.stock_ledger.enqueue_voucher_repost")
	@patch("yrp.stock.stock_ledger.make_sl_entries")
	@patch("essdee_yrp.fabric_substitution._rebuild_lot_fabric_conversions")
	@patch("essdee_yrp.fabric_substitution.get_default_knitting_lots_for_grn_items")
	@patch("essdee_yrp.fabric_substitution.lock_lots_for_default_knitting_grn_items")
	@patch.object(inspection_override, "_lock_source_grn_items")
	@patch.object(inspection_override, "_lock_source_grns")
	@patch.object(inspection_override, "_source_grn_names", return_value=["GRN-1"])
	@patch.object(
		inspection_override,
		"_source_grn_item_names",
		return_value=["GRN-ITEM-1"],
	)
	@patch.object(inspection_override, "_approver_role", return_value="Stock Manager")
	@patch.object(frappe, "get_roles", return_value=["Stock Manager"])
	@patch.object(frappe, "get_doc")
	def test_convert_stock_locks_lot_grn_and_current_inspection_before_rebuild(
		self,
		get_doc,
		_get_roles,
		_role,
		source_items,
		source_names,
		lock_grns,
		lock_items,
		lock_lots,
		current_lots,
		rebuild,
		make_entries,
		enqueue,
	):
		events = []
		discovery = frappe._dict(
			docstatus=1,
			against="YRP Goods Received Note",
			against_id="GRN-1",
			items=[],
		)
		locked = MagicMock()
		locked.name = "INSPECTION-1"
		locked.docstatus = 1
		locked.status = "Submitted"
		locked.get.side_effect = lambda field: {
			"is_converted": 0,
			"items": [],
			"against": "YRP Goods Received Note",
			"against_id": "GRN-1",
		}.get(field)
		locked._build_sl_entries.return_value = ["SLE"]
		locked.db_set.side_effect = lambda field, value: events.append(f"set:{field}:{value}")

		def load_doc(_doctype, _name, **kwargs):
			if kwargs.get("for_update"):
				events.append("inspection")
				return locked
			events.append("discover")
			return discovery

		get_doc.side_effect = load_doc
		lock_lots.side_effect = lambda names: events.append("lots") or ["LOT-1"]
		lock_grns.side_effect = lambda names: events.append("grns")
		locked_source_rows = [
			frappe._dict(
				name="GRN-ITEM-1",
				parent="GRN-1",
				parenttype="YRP Goods Received Note",
			)
		]
		lock_items.side_effect = lambda names: events.append("items") or locked_source_rows
		current_lots.side_effect = (
			lambda names, **kwargs: events.append("revalidate") or ["LOT-1"]
		)
		make_entries.side_effect = lambda entries: events.append("ledger")
		enqueue.side_effect = lambda doc: events.append("repost")
		rebuild.side_effect = lambda lot, **kwargs: events.append("rebuild")

		result = inspection_override.convert_stock("INSPECTION-1")

		self.assertEqual(result, {"status": "Converted", "is_converted": 1})
		self.assertEqual(
			events,
			[
				"discover",
				"lots",
				"grns",
				"items",
				"revalidate",
				"inspection",
				"ledger",
				"repost",
				"set:status:Converted",
				"set:is_converted:1",
				"rebuild",
			],
		)
		self.assertEqual(source_items.call_count, 2)
		self.assertIs(source_items.call_args_list[0].args[0], discovery)
		self.assertIs(source_items.call_args_list[1].args[0], locked)
		self.assertEqual(source_names.call_count, 2)
		self.assertEqual(source_names.call_args_list[0].args, (discovery, ["GRN-ITEM-1"]))
		self.assertEqual(source_names.call_args_list[1].args, (discovery, ["GRN-ITEM-1"]))
		self.assertEqual(
			source_names.call_args_list[1].kwargs,
			{"source_rows": locked_source_rows},
		)
		lock_lots.assert_called_once_with(["GRN-ITEM-1"])
		lock_grns.assert_called_once_with(["GRN-1"])
		lock_items.assert_called_once_with(["GRN-ITEM-1"])
		current_lots.assert_called_once_with(["GRN-ITEM-1"], for_update=True)
		rebuild.assert_called_once_with("LOT-1", already_locked=True)

	def test_convert_stock_rejects_changed_post_lock_lot_qualification_before_ledger(self):
		discovery = frappe._dict(
			docstatus=1,
			against="YRP Goods Received Note",
			against_id="GRN-1",
			items=[],
		)
		locked_rows = [
			frappe._dict(
				name="GRN-ITEM-1",
				parent="GRN-1",
				parenttype="YRP Goods Received Note",
			)
		]
		with (
			patch.object(inspection_override, "_approver_role", return_value="Stock Manager"),
			patch.object(frappe, "get_roles", return_value=["Stock Manager"]),
			patch.object(frappe, "get_doc", return_value=discovery) as get_doc,
			patch.object(
				inspection_override,
				"_source_grn_item_names",
				return_value=["GRN-ITEM-1"],
			),
			patch.object(inspection_override, "_source_grn_names", return_value=["GRN-1"]),
			patch.object(inspection_override, "_lock_source_grns"),
			patch.object(
				inspection_override,
				"_lock_source_grn_items",
				return_value=locked_rows,
			),
			patch(
				"essdee_yrp.fabric_substitution.lock_lots_for_default_knitting_grn_items",
				return_value=["LOT-1"],
			),
			patch(
				"essdee_yrp.fabric_substitution.get_default_knitting_lots_for_grn_items",
				return_value=[],
			) as current_lots,
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
		):
			with self.assertRaisesRegex(frappe.ValidationError, "source lineage changed"):
				inspection_override.convert_stock("INSPECTION-1")

		current_lots.assert_called_once_with(["GRN-ITEM-1"], for_update=True)
		self.assertEqual(get_doc.call_count, 1)
		make_entries.assert_not_called()

	@patch("yrp.stock.stock_ledger.enqueue_voucher_repost")
	@patch("yrp.stock.stock_ledger.make_sl_entries")
	@patch("essdee_yrp.fabric_substitution.lock_lots_for_default_knitting_grn_items")
	@patch.object(inspection_override, "_approver_role", return_value="Stock Manager")
	@patch.object(frappe, "get_roles", return_value=["Stock Manager"])
	@patch.object(frappe, "get_doc")
	def test_stock_entry_inspection_converts_without_lot_rebuild(
		self, get_doc, _get_roles, _role, lock_lots, make_entries, enqueue
	):
		discovery = frappe._dict(docstatus=1, against="YRP Stock Entry", items=[])
		locked = MagicMock(docstatus=1, status="Submitted")
		locked.get.return_value = 0
		locked._build_sl_entries.return_value = []
		get_doc.side_effect = [discovery, locked]

		result = inspection_override.convert_stock("INSPECTION-STOCK")

		self.assertEqual(result["status"], "Converted")
		lock_lots.assert_not_called()
		make_entries.assert_not_called()
		enqueue.assert_called_once_with(locked)

	@patch.object(inspection_override, "_approver_role", return_value="Stock Manager")
	@patch.object(frappe, "get_roles", return_value=["Stock Manager"])
	@patch.object(frappe, "get_doc")
	def test_convert_stock_rechecks_current_state_after_locks(self, get_doc, _roles, _role):
		discovery = frappe._dict(docstatus=1, against="YRP Stock Entry", items=[])
		locked = MagicMock(docstatus=1, status="Converted")
		locked.get.return_value = 1
		get_doc.side_effect = [discovery, locked]

		with self.assertRaisesRegex(frappe.ValidationError, "already converted"):
			inspection_override.convert_stock("INSPECTION-1")

		locked._build_sl_entries.assert_not_called()

	def test_convert_stock_hook_routes_to_essdee_override(self):
		hooks = Path(frappe.get_app_path("essdee_yrp", "hooks.py")).read_text(encoding="utf-8")

		self.assertIn(
			'"yrp.yrp.doctype.yrp_inspection_entry.yrp_inspection_entry.convert_stock": '
			'"essdee_yrp.overrides.inspection_entry.convert_stock"',
			hooks,
		)
