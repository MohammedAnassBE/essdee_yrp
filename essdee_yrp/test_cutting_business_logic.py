import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import flt, nowdate, nowtime

from yrp.stock.save_stock_items import group_items_for_ui
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	create_return_grn,
	get_work_order_defaults as get_dc_work_order_defaults,
)
from yrp.yrp.doctype.goods_received_note.goods_received_note import (
	get_work_order_defaults as get_grn_work_order_defaults,
)

from essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet import (
	_save_cutting_plan_cloth_usage,
	_cutting_grn_consumed_rows,
	_cutting_grn_output_rows,
	cancel_cut_bundle,
	create_cut_bundle_ledger,
	create_grn_entry,
	mark_labels_printed,
	print_labels,
	update_cloth_stock,
)
from essdee_yrp.cutting.reports import (
	get_cut_sheet_report,
	get_cutting_detail_report,
	get_daily_production_report,
	get_daily_production_summary_report,
	get_multiccr,
)
from essdee_yrp.cutting.movement import (
	_overlay_source_rows,
	apply_transaction,
	build_delivery_challan_defaults,
	build_goods_received_note_defaults,
	build_stock_entry_defaults,
	get_grouped_movement_rows,
	set_completion_cut_panel_movement,
	validate_transaction_link,
)
from essdee_yrp.fabric_grn import _resolve_deliverable_source
from essdee_yrp.overrides.delivery_challan import (
	strip_generated_invalid_zero_placeholders,
	strip_unselected_cpm_items,
)
from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import (
	can_change_approval_grammage,
	create_balance_lot_transfer,
	has_cls_grammage_approval_role,
)
from essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement import (
	CutPanelMovement,
	_latest_logical_bundle_rows,
)
from essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger import (
	_collapsed_set_combination_key,
	get_collapsed_previous_cbm_list,
	get_cut_bundle_entry,
	get_latest_cbml_for_variant,
)
from essdee_yrp.setup import ensure_mrp_cancel_permissions


class TestCutBundleMovementTransactionFiltering(UnitTestCase):
	def setUp(self):
		self.ipd = frappe._dict(
			primary_item_attribute="Size",
			packing_attribute="Colour",
			stiching_attribute="Panel",
			stiching_in_stage="Cut",
			dependent_attribute="Stage",
			is_set_item=1,
			stiching_item_details=[
				frappe._dict(stiching_attribute_value="Bottom Front Left", quantity=1),
				frappe._dict(stiching_attribute_value="Bottom Front Right", quantity=1),
				frappe._dict(stiching_attribute_value="Bottom Back", quantity=2),
			],
		)
		self.combination = {"major_colour": "Airforce", "major_part": "Top"}
		self.cpm = frappe._dict(
			lot="LOT-SPLIT-DC",
			cut_panel_movement_json=json.dumps(
				{
					"panels": {
						"Bottom": [
							"Bottom Front Left",
							"Bottom Front Right",
							"Bottom Back",
						]
					},
					"data": {
						"(Airforce)Dark Grey-Bottom": {
							"part": "Bottom",
							"data": [
								{
									"lay_no": "1",
									"bundle_no": "1",
									"shade": "A",
									"size": "45 cm",
									"set_combination": self.combination,
									"Bottom Front Left": 10,
									"Bottom Front Left_moved": 1,
									"Bottom Front Left_colour": "Dark Grey",
									"Bottom Front Right": 10,
									"Bottom Front Right_moved": 1,
									"Bottom Front Right_colour": "Dark Grey",
									"Bottom Back": 10,
									"Bottom Back_moved": 1,
									"Bottom Back_colour": "Dark Grey",
								}
							],
						}
					},
				}
			),
		)
		self.variant_attributes = {
			"VAR-LEFT": {
				"Size": "45 cm",
				"Colour": "Dark Grey",
				"Panel": "Bottom Front Left",
			},
			"VAR-RIGHT": {
				"Size": "45 cm",
				"Colour": "Dark Grey",
				"Panel": "Bottom Front Right",
			},
			"VAR-BACK": {
				"Size": "45 cm",
				"Colour": "Dark Grey",
				"Panel": "Bottom Back",
			},
		}

	def test_completion_inherits_authoritative_collapsed_bundle_context(self):
		stock_entry = frappe._dict(
			doctype="Stock Entry",
			purpose="DC Completion",
			against="Delivery Challan",
			against_id="DC-COLLAPSED",
			cut_panel_movement="CPM-ALREADY-COPIED",
			allow_non_bundle=0,
		)
		stock_entry.meta = frappe._dict(
			get_field=lambda fieldname: fieldname == "allow_non_bundle"
		)
		against_meta = frappe._dict(
			get_field=lambda fieldname: fieldname
			in {"cut_panel_movement", "allow_non_bundle"}
		)

		with (
			patch.object(frappe, "get_meta", return_value=against_meta),
			patch.object(frappe.db, "get_value", return_value=1) as get_value,
		):
			set_completion_cut_panel_movement(stock_entry)

		self.assertEqual(stock_entry.cut_panel_movement, "CPM-ALREADY-COPIED")
		self.assertEqual(stock_entry.allow_non_bundle, 1)
		get_value.assert_called_once_with(
			"Delivery Challan", "DC-COLLAPSED", "allow_non_bundle"
		)

	def test_completion_cannot_spoof_collapsed_bundle_mode(self):
		stock_entry = frappe._dict(
			doctype="Stock Entry",
			purpose="GRN Completion",
			against="Goods Received Note",
			against_id="GRN-EXACT",
			cut_panel_movement="CPM-EXACT",
			allow_non_bundle=1,
		)
		stock_entry.meta = frappe._dict(
			get_field=lambda fieldname: fieldname == "allow_non_bundle"
		)
		against_meta = frappe._dict(
			get_field=lambda fieldname: fieldname
			in {"cut_panel_movement", "allow_non_bundle"}
		)

		with (
			patch.object(frappe, "get_meta", return_value=against_meta),
			patch.object(frappe.db, "get_value", return_value=0),
		):
			set_completion_cut_panel_movement(stock_entry)

		self.assertEqual(stock_entry.allow_non_bundle, 0)

	def test_latest_bundle_rows_normalise_historical_json_text(self):
		rows = [
			frappe._dict(
				name="opening",
				cbm_key="bundle-1",
				set_combination=(
					'{"major_colour":"White","major_part":"Top",'
					'"major_panel":"Top Front","is_set_item":1}'
				),
				posting_datetime="2026-08-26 10:00:00",
				creation="2026-08-26 10:00:01",
				lay_no=1,
				quantity_after_transaction=20,
			),
			frappe._dict(
				name="moved",
				cbm_key="bundle-1",
				set_combination='{"major_part": "Top", "major_colour": "White"}',
				posting_datetime="2026-08-27 10:00:00",
				creation="2026-08-27 10:00:01",
				lay_no=1,
				quantity_after_transaction=0,
			),
			frappe._dict(
				name="other-combination",
				cbm_key="bundle-1",
				set_combination='{"major_colour":"Black","major_part":"Top"}',
				posting_datetime="2026-08-26 10:00:00",
				creation="2026-08-26 10:00:02",
				lay_no=1,
				quantity_after_transaction=10,
			),
		]
		latest = _latest_logical_bundle_rows(rows)
		self.assertEqual([row.name for row in latest], ["other-combination"])

	def _entries(self, doc):
		module = (
			"essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger."
			"cut_bundle_movement_ledger"
		)
		with (
			patch(f"{module}.frappe.get_value", return_value=("IPD-SPLIT", "ITEM-SPLIT")),
			patch(f"{module}.frappe.get_cached_doc", return_value=self.ipd),
			patch(
				f"{module}.get_variant_attr_details",
				side_effect=lambda variant: self.variant_attributes[variant],
			),
		):
			return get_cut_bundle_entry(self.cpm, doc, "SUPPLIER-TARGET", -1)[0]

	def _dc(self, name, items):
		return frappe._dict(
			doctype="Delivery Challan",
			name=name,
			posting_date="2026-08-24",
			posting_time="12:00:00",
			items=[
				frappe._dict(
					item_variant=variant,
					delivered_quantity=quantity,
					set_combination=self.combination,
				)
				for variant, quantity in items
			],
		)

	def test_sequential_split_dcs_move_only_their_transaction_panels(self):
		printing_entries = self._entries(
			self._dc("DC-PRINTING", [("VAR-LEFT", 10), ("VAR-RIGHT", 10)])
		)
		self.assertEqual(
			{entry["panel"] for entry in printing_entries},
			{"Bottom Front Left", "Bottom Front Right"},
		)
		self.assertEqual(sum(abs(entry["quantity"]) for entry in printing_entries), 20)

		later_entries = self._entries(self._dc("DC-LATER", [("VAR-BACK", 20)]))
		self.assertEqual({entry["panel"] for entry in later_entries}, {"Bottom Back"})
		# Bottom Back requires two physical panels per garment bundle. The DC
		# therefore carries 20 pieces while CBML keeps the whole-bundle count 10.
		self.assertEqual(sum(abs(entry["quantity"]) for entry in later_entries), 10)

	def test_split_dc_rejects_a_partial_physical_bundle_quantity(self):
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"transaction quantity 19.0 does not match the selected whole-bundle quantity 20.0",
		):
			self._entries(self._dc("DC-PARTIAL", [("VAR-BACK", 19)]))

	def test_stock_entry_filter_does_not_require_set_combination_child_field(self):
		doc = frappe._dict(
			doctype="Stock Entry",
			name="STE-SPLIT",
			posting_date="2026-08-24",
			posting_time="12:00:00",
			items=[frappe._dict(item="VAR-LEFT", qty=10)],
		)
		entries = self._entries(doc)
		self.assertEqual({entry["panel"] for entry in entries}, {"Bottom Front Left"})
		self.assertEqual(sum(abs(entry["quantity"]) for entry in entries), 10)

	def _grouped_rows(self, movement):
		module = "essdee_yrp.cutting.movement"
		cpm = frappe._dict(
			name="CPM-COLLAPSED",
			lot="LOT-COLLAPSED",
			cut_panel_movement_json=json.dumps(movement),
		)
		variant_by_panel = {
			"Bottom Front Left": "VAR-LEFT",
			"Bottom Front Right": "VAR-RIGHT",
			"Bottom Back": "VAR-BACK",
		}
		with (
			patch(f"{module}._load_movement", return_value=cpm),
			patch(f"{module}.frappe.db.get_value", return_value=("IPD-SPLIT", "ITEM-SPLIT")),
			patch(f"{module}.frappe.db.get_single_value", return_value="Accepted"),
			patch(f"{module}.frappe.get_cached_doc", return_value=self.ipd),
			patch(f"{module}.flt", side_effect=lambda value, *_args: float(value or 0)),
			patch(f"{module}._get_uom", return_value="Pieces"),
			patch(
				f"{module}.get_or_create_variant",
				side_effect=lambda _item, attrs: variant_by_panel[attrs["Panel"]],
			),
			patch(f"{module}.apply_dimension_defaults"),
		):
			return get_grouped_movement_rows("CPM-COLLAPSED", "Delivery Challan")[2]

	def test_collapsed_cpm_quantity_is_already_physical_panel_stock(self):
		rows = self._grouped_rows(
			{
				"data": {},
				"panels": {"Bottom": ["Bottom Back"]},
				"is_set_item": 1,
				"collapsed_details": [
					{
						"moved": 1,
						"move_qty": 3,
						"quantity": 5,
						"panel": "Bottom Back",
						"size": "45 cm",
						"colour": "Dark Grey",
						"set_combination": self.combination,
					}
				],
			}
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["item_variant"], "VAR-BACK")
		# Bottom Back has an IPD multiplier of 2, but a collapsed CBML row is
		# already stored as physical pieces and must not be multiplied again.
		self.assertEqual(rows[0]["qty"], 3)

	def test_collapsed_cpm_rejects_overdraw(self):
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Collapsed move qty 6.0 exceeds available qty 5.0",
		):
			self._grouped_rows(
				{
					"data": {},
					"panels": {"Bottom": ["Bottom Back"]},
					"is_set_item": 1,
					"collapsed_details": [
						{
							"moved": 1,
							"move_qty": 6,
							"quantity": 5,
							"panel": "Bottom Back",
							"size": "45 cm",
							"colour": "Dark Grey",
							"set_combination": self.combination,
						}
					],
				}
			)

	def test_cpm_rejects_mixed_exact_and_collapsed_stock(self):
		movement = json.loads(self.cpm.cut_panel_movement_json)
		movement["is_set_item"] = 1
		movement["collapsed_details"] = [
			{
				"moved": 1,
				"move_qty": 1,
				"quantity": 5,
				"panel": "Bottom Back",
				"size": "45 cm",
				"colour": "Dark Grey",
				"set_combination": self.combination,
			}
		]
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Exact bundles and collapsed quantities cannot be mixed",
		):
			self._grouped_rows(movement)

	def test_collapsed_identity_matches_f15_major_colour_and_part_convention(self):
		work_order_combination = {
			"major_colour": "Red",
			"major_part": "Top",
		}
		exact_bundle_combination = {
			**work_order_combination,
			"major_panel": "Front",
			"is_same_packing_attribute": 1,
			"is_set_item": 1,
		}
		self.assertEqual(
			_collapsed_set_combination_key(work_order_combination),
			_collapsed_set_combination_key(exact_bundle_combination),
		)
		self.assertNotEqual(
			_collapsed_set_combination_key(work_order_combination),
			_collapsed_set_combination_key(
				{"major_colour": "Black", "major_part": "Top"}
			),
		)

	def test_collapsed_only_cpm_selection_survives_submit_filtering(self):
		doc = frappe._dict(
			cut_panel_movement_json=json.dumps(
				{
					"data": {},
					"panels": {},
					"accessory_data": [],
					"collapsed_details": [
						{
							"moved": 1,
							"move_qty": 3,
							"quantity": 5,
							"panel": "Bottom Back",
						},
						{
							"moved": 0,
							"move_qty": 2,
							"quantity": 2,
							"panel": "Front",
						},
					],
				}
			)
		)
		CutPanelMovement.before_submit(doc)
		self.assertEqual(len(doc.cut_panel_movement_json["collapsed_details"]), 1)
		self.assertEqual(
			doc.cut_panel_movement_json["collapsed_details"][0]["move_qty"], 3
		)

	def test_overlay_keeps_only_nonzero_cpm_matches(self):
		source_rows = [
			frappe._dict(item_variant="VAR-LEFT", set_combination=self.combination),
			frappe._dict(item_variant="VAR-RIGHT", set_combination=self.combination),
		]
		movement_rows = [
			frappe._dict(
				item_variant="VAR-LEFT",
				set_combination=self.combination,
				quantity=10,
				table_index=1,
				row_index=2,
			)
		]
		rows = _overlay_source_rows(
			source_rows, movement_rows, target_doctype="Goods Received Note"
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].item_variant, "VAR-LEFT")
		self.assertEqual(rows[0].quantity, 10)

	def test_overlay_rejects_any_unmatched_selected_panel(self):
		source_rows = [
			frappe._dict(item_variant="VAR-LEFT", set_combination=self.combination)
		]
		movement_rows = [
			frappe._dict(
				item_variant="VAR-LEFT",
				set_combination=self.combination,
				quantity=10,
			),
			frappe._dict(
				item_variant="VAR-BACK",
				set_combination=self.combination,
				quantity=5,
			),
		]
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Some selected panels do not match",
		):
			_overlay_source_rows(
				source_rows, movement_rows, target_doctype="Goods Received Note"
			)

	def test_cpm_delivery_challan_drops_generated_zero_size_placeholders(self):
		doc = frappe.get_doc(
			{
				"doctype": "Delivery Challan",
				"cut_panel_movement": "CPM-COLLAPSED",
				"items": [
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "VAR-ZERO",
						"qty": 0,
						"ref_doctype": 0,
					},
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "VAR-MOVED",
						"qty": 10,
						"ref_doctype": "Work Order Deliverables",
					},
				],
			}
		)

		strip_unselected_cpm_items(doc)

		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0].item_variant, "VAR-MOVED")
		self.assertEqual(doc.items[0].ref_doctype, "Work Order Deliverables")

	def test_ordinary_delivery_challan_keeps_base_zero_rows(self):
		doc = frappe.get_doc(
			{
				"doctype": "Delivery Challan",
				"items": [
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "VAR-VALID-ZERO",
						"qty": 0,
						"ref_doctype": "Work Order Deliverables",
						"ref_docname": "VALID-ROW",
					},
					{
						"doctype": "Delivery Challan Item",
						"item_variant": "VAR-GENERATED-ZERO",
						"qty": 0,
						"ref_doctype": 0,
						"ref_docname": 0,
					}
				],
			}
		)

		strip_generated_invalid_zero_placeholders(doc)
		strip_unselected_cpm_items(doc)

		self.assertEqual(len(doc.items), 1)
		self.assertEqual(doc.items[0].item_variant, "VAR-VALID-ZERO")
		self.assertEqual(doc.items[0].ref_doctype, "Work Order Deliverables")


class TestCuttingBusinessLogic(IntegrationTestCase):
	@staticmethod
	def _allow_test_negative_stock(item_variant):
		parent_item = frappe.db.get_value("Item Variant", item_variant, "item")
		frappe.db.set_value(
			"Item", parent_item, "allow_negative_stock", 1, update_modified=False
		)
		frappe.clear_document_cache("Item", parent_item)
		return parent_item

	@classmethod
	def _seed_bundle_balance(
		cls,
		*,
		work_order,
		lot,
		location,
		item_variant,
		panel,
		colour,
		size,
		set_combination,
		quantity,
		collapsed=False,
	):
		"""Create rollback-safe CBML stock independent of live UAT balances."""

		item = cls._allow_test_negative_stock(item_variant)
		current_stock = get_stock_balance(
			item_variant,
			location,
			lot=lot,
			received_type="Accepted",
		)
		reconciliation = frappe.get_doc(
			{
				"doctype": "Stock Reconciliation",
				"purpose": "Stock Reconciliation",
				"posting_date": nowdate(),
				"posting_time": nowtime(),
				"default_warehouse": location,
				"items": [
					{
						"item": item_variant,
						"warehouse": location,
						"qty": current_stock + quantity,
						"rate": 1,
						"lot": lot,
						"received_type": "Accepted",
					}
				],
			}
		)
		reconciliation.insert(ignore_permissions=True)
		reconciliation.submit()
		opening = 0
		if collapsed:
			rows = get_collapsed_previous_cbm_list(
				"9999-12-31",
				"23:59:59",
				location,
				item_variant,
				lot=lot,
				set_combination=set_combination,
			)
			opening = flt(rows[0].quantity_after_transaction) if rows else 0
		sequence = frappe.db.count("Cut Bundle Movement Ledger") + 900000
		row = frappe.get_doc(
			{
				"doctype": "Cut Bundle Movement Ledger",
				"lot": lot,
				"supplier": location,
				"lay_no": 0 if collapsed else sequence,
				"bundle_no": 0 if collapsed else sequence,
				"panel": panel,
				"shade": "TEST",
				"collapsed_bundle": int(collapsed),
				"item_variant": item_variant,
				"item": item,
				"voucher_type": "Work Order",
				"voucher_no": work_order,
				"size": size,
				"colour": colour,
				"quantity": quantity,
				"quantity_after_transaction": opening + quantity,
				"set_combination": json.dumps(set_combination),
				"posting_date": nowdate(),
				"posting_time": nowtime(),
			}
		)
		row.flags.ignore_permissions = 1
		row.set_posting_datetime()
		row.set_key()
		row.insert(ignore_permissions=True)
		row.submit()
		return row

	@staticmethod
	def _insert_submitted_work_order_row(doctype, parentfield, work_order, values):
		frappe.get_doc(
			{
				"doctype": doctype,
				"parent": work_order,
				"parenttype": "Work Order",
				"parentfield": parentfield,
				"docstatus": 1,
				**values,
			}
		).insert(ignore_permissions=True)

	@staticmethod
	def _transaction_from_defaults(doctype, defaults):
		doc = frappe.new_doc(doctype)
		for fieldname, value in defaults.items():
			if fieldname in {
				"items",
				"item_details",
				"correction_items",
				"correction_item_details",
			}:
				continue
			if doc.meta.get_field(fieldname):
				doc.set(fieldname, value)
		doc.item_details = json.dumps(defaults["item_details"])
		doc.insert()
		return doc

	def test_f15_cutting_cancel_permissions_are_restored(self):
		ensure_mrp_cancel_permissions()
		for doctype, expected_submit in (
			("Cut Panel Movement", 0),
			("Cutting Marker", 1),
		):
			permission = frappe.db.get_value(
				"Custom DocPerm",
				{
					"parent": doctype,
					"role": "System Manager",
					"permlevel": 0,
					"if_owner": 0,
				},
				["cancel", "submit"],
				as_dict=True,
			)
			self.assertEqual(permission.cancel, 1)
			self.assertEqual(permission.submit, expected_submit)
			standard_rows = frappe.get_all(
				"DocPerm",
				filters={"parent": doctype},
				fields=["role", "permlevel", "if_owner", "read", "write", "create", "submit"],
			)
			for standard in standard_rows:
				custom = frappe.db.get_value(
					"Custom DocPerm",
					{
						"parent": doctype,
						"role": standard.role,
						"permlevel": standard.permlevel,
						"if_owner": standard.if_owner,
					},
					["read", "write", "create", "submit"],
					as_dict=True,
				)
				self.assertIsNotNone(custom)
				self.assertEqual(custom.read, standard.read)
				self.assertEqual(custom.write, standard.write)
				self.assertEqual(custom.create, standard.create)
				if standard.role != "System Manager":
					self.assertEqual(custom.submit, standard.submit)

	def _assert_bundle_generation_persists_precise_cutting_plan_cloth_usage(self):
		laysheet = SimpleNamespace(
			name="CLS-TEST",
			cutting_laysheet_details=[
				SimpleNamespace(
					colour="Red",
					cloth_type="Rib Fabric",
					actual_dia="26 Dia",
					used_weight=0.082,
				),
				SimpleNamespace(
					colour="Red",
					cloth_type="Rib Fabric",
					actual_dia="26 Dia",
					used_weight=1.118,
				),
			],
			cutting_laysheet_accessory_details=[
				SimpleNamespace(
					colour="Red",
					cloth_type="Main Fabric",
					actual_dia="26 Dia",
					weight=1.5,
				)
			],
		)
		rib = SimpleNamespace(
			colour="Red",
			cloth_type="Rib Fabric",
			dia="26 Dia",
			weight=1.2,
			used_weight=0,
			balance_weight=1.2,
		)
		accessory = SimpleNamespace(
			colour="Red",
			cloth_type="Main Fabric",
			dia="26 Dia",
			weight=1.5,
			used_weight=0,
			balance_weight=1.5,
		)
		cutting_plan = SimpleNamespace(
			cutting_plan_cloth_details=[rib, accessory],
			save=MagicMock(),
		)
		original_get_doc = frappe.get_doc
		original_get_all = frappe.get_all

		def get_doc(doctype, name):
			if (doctype, name) == ("Cutting Plan", "CP-TEST"):
				return cutting_plan
			return original_get_doc(doctype, name)

		def get_all(doctype, *args, **kwargs):
			if doctype == "Cutting LaySheet":
				return [laysheet.name]
			return original_get_all(doctype, *args, **kwargs)

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(frappe, "get_doc", side_effect=get_doc),
		):
			_save_cutting_plan_cloth_usage(laysheet, "CP-TEST")
			self.assertAlmostEqual(rib.used_weight, 1.2, places=3)
			_save_cutting_plan_cloth_usage(laysheet, "CP-TEST")
			self.assertAlmostEqual(rib.used_weight, 1.2, places=3)

		self.assertAlmostEqual(rib.used_weight, 1.2, places=3)
		self.assertEqual(rib.balance_weight, 0)
		self.assertEqual(accessory.used_weight, 1.5)
		self.assertEqual(accessory.balance_weight, 0)
		self.assertEqual(cutting_plan.save.call_count, 2)
		cutting_plan.save.assert_called_with(ignore_permissions=True)

	def test_cutting_plan_creates_balance_lot_transfer_draft(self):
		cutting_plan = "CP-2603-00030"
		if not frappe.db.exists("Cutting Plan", cutting_plan):
			self.skipTest(f"Migrated Cutting Plan oracle {cutting_plan} is unavailable")
		target_lot = frappe.db.get_value(
			"Lot", {"name": ["!=", "C0326-28"]}, "name", order_by="modified desc"
		)
		if not target_lot:
			self.skipTest("A target Lot is unavailable")

		name = create_balance_lot_transfer(cutting_plan, target_lot)
		transfer = frappe.get_doc("Lot Transfer", name)
		self.assertEqual(transfer.docstatus, 0)
		self.assertEqual(transfer.comments, f"Balance cloth from Cutting Plan {cutting_plan}")
		self.assertTrue(transfer.items)
		self.assertTrue(all(row.from_lot == "C0326-28" for row in transfer.items))
		self.assertTrue(all(row.to_lot == target_lot for row in transfer.items))
		self.assertTrue(all(row.warehouse == "S-0164" for row in transfer.items))
		self.assertTrue(all(row.received_type == "Accepted" for row in transfer.items))
		self.assertAlmostEqual(sum(flt(row.qty) for row in transfer.items), 0.2, places=3)

	def test_grammage_approval_roles_are_installed_and_runtime_safe(self):
		field = frappe.get_meta("MRP Settings").get_field(
			"cls_grammage_approval_roles"
		)
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Table")
		self.assertEqual(field.options, "CLS Grammage Approval Role")
		self.assertEqual(
			[row.role for row in frappe.get_single("MRP Settings").get(field.fieldname)],
			["Merch Manager", "Factory Manager", "Senior Merch"],
		)
		self.assertEqual(
			can_change_approval_grammage(),
			has_cls_grammage_approval_role(),
		)

	@patch(
		"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.make_sl_entries"
	)
	@patch(
		"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_table_entries",
		return_value=[],
	)
	@patch(
		"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet._get_warehouse_for_supplier",
		return_value="Mapped Supplier Warehouse",
	)
	def test_dia_change_stock_uses_mapped_warehouse(
		self, resolve_warehouse, get_table_entries, make_sl_entries
	):
		laysheet = frappe._dict(
			{
				"name": "CLS-TEST",
				"cutting_plan": "CP-TEST",
				"lot": "LOT-TEST",
				"cutting_laysheet_details": [],
				"cutting_laysheet_accessory_details": [],
			}
		)
		with (
			patch.object(
				frappe,
				"get_value",
				side_effect=["WO-TEST", ("IPD-TEST", "Supplier Name")],
			),
			patch.object(frappe, "get_doc", return_value=frappe._dict()),
			patch.object(
				frappe.db,
				"get_single_value",
				return_value="Accepted",
			),
		):
			update_cloth_stock(laysheet, 1, -1)

		resolve_warehouse.assert_called_once_with("Supplier Name")
		self.assertEqual(get_table_entries.call_count, 2)
		for call in get_table_entries.call_args_list:
			self.assertEqual(call.args[2], "Mapped Supplier Warehouse")
		make_sl_entries.assert_called_once_with([], force_inline=True)

	def test_cutting_desk_endpoints_resolve_and_require_login(self):
		methods = (
			"essdee_yrp.api.work_order.fetch_summary_details",
			"essdee_yrp.cutting.reports.get_cut_sheet_report",
			"essdee_yrp.cutting.reports.get_cutting_detail_report",
			"essdee_yrp.cutting.reports.get_daily_production_report",
			"essdee_yrp.cutting.reports.get_daily_production_summary_report",
			"essdee_yrp.cutting.reports.get_multiccr",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.calculate_laysheets",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.can_change_approval_grammage",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.change_approval_grammage",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.create_balance_lot_transfer",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.create_recut_print_panel",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.fetch_received_cloth",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.get_cloth1",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.get_cutting_plan_laysheets_report",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.get_items",
			"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.get_recut_print_panel_details",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.approve_grammage",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.can_approve_grammage",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.cancel_laysheet",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_cloth_accessories",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_cut_sheet_data",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_input_fields",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_parts",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_piece_weight_tolerance",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_primary_values",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_select_attributes",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.mark_labels_printed",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.print_labels",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.request_grammage_approval",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.revert_labels",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.update_cutting_plan",
			"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.update_label_print_status",
			"essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement.get_cut_bundle_unmoved_data",
			"essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement.create_stock_entry",
			"essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement.create_delivery_challan",
			"essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement.create_goods_received_note",
			"essdee_yrp.essdee_yrp.doctype.cut_bundle_edit.cut_bundle_edit.get_major_colours",
			"essdee_yrp.essdee_yrp.doctype.cut_bundle_edit.cut_bundle_edit.get_major_set_colours",
			"essdee_yrp.essdee_yrp.doctype.cut_bundle_edit.cut_bundle_edit.print_labels",
		)
		for method in methods:
			function = frappe.get_attr(method)
			self.assertIn(function, frappe.whitelisted, method)
			self.assertNotIn(function, frappe.guest_methods, method)

		summary = frappe.get_attr("essdee_yrp.api.work_order.fetch_summary_details")(
			"WO-2627-00714", "Flame Thermal Kids Set-7"
		)
		self.assertEqual(summary["work_order_docstatus"], 1)
		self.assertTrue(summary["item_detail"])
		self.assertTrue(summary["deliverables"])

	def test_recut_uses_f16_dimension_aware_stock_contract(self):
		recut_name = "8dvt4000gs"
		if not frappe.db.exists("Recut and Print Panel", recut_name):
			self.skipTest(f"Migrated Recut oracle {recut_name} is unavailable")

		doc = frappe.get_doc("Recut and Print Panel", recut_name)
		doc._set_cloth_variants_and_rates()
		entries = doc._get_stock_ledger_entries()
		self.assertEqual(len(entries), len(doc.recut_and_print_panel_details))
		self.assertTrue(all(row["warehouse"] == "S-0163" for row in entries))
		self.assertTrue(all(row["lot"] == doc.lot for row in entries))
		self.assertTrue(all(row["received_type"] for row in entries))
		self.assertTrue(all(flt(row["qty"]) < 0 for row in entries))
		self.assertTrue(all(flt(row["outgoing_rate"]) > 0 for row in entries))

		cancel_entries = doc._get_stock_ledger_entries(cancel=True)
		self.assertTrue(all(flt(row["qty"]) > 0 for row in cancel_entries))
		self.assertTrue(all(flt(row["rate"]) > 0 for row in cancel_entries))

	def test_cut_panel_movement_stock_entry_lifecycle(self):
		movement_name = "CPM-2608-00220"
		if not frappe.db.exists(
			"Cut Panel Movement",
			{"name": movement_name, "docstatus": 1, "against_id": ["is", "not set"]},
		):
			self.skipTest(f"Unlinked Cut Panel Movement oracle {movement_name} is unavailable")

		build_defaults = frappe.get_attr(
			"essdee_yrp.cutting.movement.build_stock_entry_defaults"
		)
		defaults = build_defaults(movement_name)
		for row in defaults["items"]:
			parent_item = frappe.db.get_value("Item Variant", row["item"], "item")
			frappe.db.set_value(
				"Item", parent_item, "allow_negative_stock", 1, update_modified=False
			)
			frappe.clear_document_cache("Item", parent_item)

		entry = frappe.new_doc("Stock Entry")
		entry.purpose = defaults["purpose"]
		entry.from_warehouse = defaults["from_warehouse"]
		entry.from_supplier = defaults["from_supplier"]
		entry.to_warehouse = "S-0163"
		entry.cut_panel_movement = movement_name
		entry.item_details = json.dumps(defaults["item_details"])
		entry.insert()
		entry.submit()

		self.assertEqual(entry.docstatus, 1)
		self.assertEqual(
			frappe.db.get_value("Cut Panel Movement", movement_name, "against_id"),
			entry.name,
		)
		self.assertTrue(
			frappe.db.exists(
				"Stock Ledger Entry",
				{
					"voucher_type": "Stock Entry",
					"voucher_no": entry.name,
					"is_cancelled": 0,
				},
			)
		)
		bundle_count = frappe.db.count(
			"Cut Bundle Movement Ledger",
			filters={
				"voucher_type": "Stock Entry",
				"voucher_no": entry.name,
				"is_cancelled": 0,
			},
		)
		self.assertGreater(bundle_count, 0)

		entry.cancel()
		self.assertEqual(entry.docstatus, 2)
		self.assertFalse(
			frappe.db.get_value("Cut Panel Movement", movement_name, "against_id")
		)
		self.assertFalse(
			frappe.db.exists(
				"Stock Ledger Entry",
				{
					"voucher_type": "Stock Entry",
					"voucher_no": entry.name,
					"is_cancelled": 0,
				},
			)
		)
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"voucher_type": "Stock Entry",
					"voucher_no": entry.name,
					"is_cancelled": 0,
				},
			)
		)

	def test_printing_split_dc_bundle_filter_matches_stock_ledger(self):
		cpm_name = "CPM-2608-00224"
		dc_name = "DC-2026-00008"
		if not (
			frappe.db.exists("Cut Panel Movement", cpm_name)
			and frappe.db.exists("Delivery Challan", {"name": dc_name, "docstatus": 1})
		):
			self.skipTest("Printing split-DC oracle is unavailable")

		cpm = frappe.get_doc("Cut Panel Movement", cpm_name)
		dc = frappe.get_doc("Delivery Challan", dc_name)
		entries, _collapsed = get_cut_bundle_entry(cpm, dc, dc.from_location, -1)
		self.assertEqual(
			{entry["panel"] for entry in entries},
			{"Bottom Front Left", "Bottom Front Right"},
		)

		ipd = frappe.get_cached_doc(
			"Item Production Detail",
			frappe.db.get_value("Lot", cpm.lot, "production_detail"),
		)
		panel_quantities = {
			row.stiching_attribute_value: flt(row.quantity)
			for row in ipd.get("stiching_item_details") or []
		}
		bundle_physical_qty = sum(
			abs(flt(entry["quantity"])) * panel_quantities[entry["panel"]]
			for entry in entries
		)
		stock_physical_qty = abs(
			sum(
				flt(quantity)
				for quantity in frappe.get_all(
					"Stock Ledger Entry",
					filters={
						"voucher_type": "Delivery Challan",
						"voucher_no": dc_name,
						"warehouse": dc.from_warehouse,
						"is_cancelled": 0,
					},
					pluck="qty",
				)
			)
		)
		self.assertEqual(bundle_physical_qty, 350)
		self.assertEqual(bundle_physical_qty, stock_physical_qty)

	def test_printing_collapsed_redelivery_grn_return_and_cancel_matrix(self):
		work_order_name = "YRP-WO-2026-00040"
		variant = "Maze Capri Set R.N.S-Bottom Front Left-Dark Grey-45 cm"
		lot = "C0826-57"
		from_location = "S-0170"
		printing_supplier = "Sri Krishna Printing"
		if not frappe.db.exists(
			"Work Order",
			{
				"name": work_order_name,
				"docstatus": 1,
				"open_status": ["!=", "Close"],
			},
		):
			self.skipTest("Printing Work Order oracle is unavailable")
		if not frappe.get_meta("Stock Entry").get_field("allow_non_bundle"):
			self.fail("Stock Entry allow_non_bundle fixture is not installed")

		combination = {
			"major_colour": "Airforce",
			"major_part": "Top",
		}

		def balance(location):
			rows = get_collapsed_previous_cbm_list(
				nowdate(),
				nowtime(),
				location,
				variant,
				lot=lot,
				set_combination=combination,
			)
			return flt(rows[0].quantity_after_transaction) if rows else 0

		def voucher_qty(doctype, name, location):
			return sum(
				flt(row.quantity)
				for row in frappe.get_all(
					"Cut Bundle Movement Ledger",
					filters={
						"voucher_type": doctype,
						"voucher_no": name,
						"supplier": location,
						"collapsed_bundle": 1,
						"is_cancelled": 0,
					},
					fields=["quantity"],
				)
			)

		def stock_qty(doctype, name, warehouse):
			return sum(
				flt(quantity)
				for quantity in frappe.get_all(
					"Stock Ledger Entry",
					filters={
						"voucher_type": doctype,
						"voucher_no": name,
						"warehouse": warehouse,
						"is_cancelled": 0,
					},
					pluck="qty",
				)
			)

		for location in (from_location, printing_supplier):
			self._seed_bundle_balance(
				work_order=work_order_name,
				lot=lot,
				location=location,
				item_variant=variant,
				panel="Bottom Front Left",
				colour="Dark Grey",
				size="45 cm",
				set_combination=combination,
				quantity=2,
				collapsed=True,
			)
		deliverable_name = frappe.db.get_value(
			"Work Order Deliverables",
			{"parent": work_order_name, "item_variant": variant},
			"name",
		)
		frappe.db.set_value(
			"Work Order Deliverables",
			deliverable_name,
			{"pending_quantity": 2, "stock_update": 9},
			update_modified=False,
		)
		start_from = balance(from_location)
		start_supplier = balance(printing_supplier)
		self.assertGreaterEqual(start_from, 1)
		self.assertGreaterEqual(start_supplier, 1)

		dc_defaults = get_dc_work_order_defaults(work_order_name)
		dc_row = next(
			frappe._dict(row)
			for row in dc_defaults["items"]
			if row.get("item_variant") == variant
			and json.loads(row.get("set_combination") or "{}") == combination
		)
		dc_row.qty = 1
		dc_row.delivered_quantity = 1
		dc_row.stock_qty = flt(dc_row.conversion_factor or 1)
		dc_defaults["items"] = [dc_row]
		dc_defaults["item_details"] = group_items_for_ui(
			dc_defaults["items"], "Delivery Challan"
		)
		dc_defaults["allow_non_bundle"] = 1
		dc_defaults["work_order"] = work_order_name
		work_order = frappe.get_doc("Work Order", work_order_name)
		dc_defaults["supplier_address"] = work_order.supplier_address
		dc_defaults["supplier_address_details"] = work_order.supplier_address_details
		dc_defaults["from_address"] = work_order.delivery_address
		dc_defaults["from_address_details"] = work_order.delivery_address_details
		dc = self._transaction_from_defaults("Delivery Challan", dc_defaults)
		dc.submit()
		self.assertEqual(balance(from_location), start_from - 1)
		self.assertEqual(balance(printing_supplier), start_supplier + 1)
		self.assertEqual(voucher_qty("Delivery Challan", dc.name, from_location), -1)
		self.assertEqual(voucher_qty("Delivery Challan", dc.name, printing_supplier), 1)
		self.assertEqual(stock_qty("Delivery Challan", dc.name, dc.from_warehouse), -1)
		self.assertEqual(stock_qty("Delivery Challan", dc.name, dc.to_warehouse), 1)

		frappe.db.set_value(
			"Work Order Receivables",
			{"parent": work_order_name, "item_variant": variant},
			"pending_quantity",
			3,
			update_modified=False,
		)
		grn_defaults = get_grn_work_order_defaults(work_order_name)
		grn_row = next(
			frappe._dict(row)
			for row in grn_defaults["items"]
			if row.get("item_variant") == variant
			and json.loads(row.get("set_combination") or "{}") == combination
		)
		grn_row.quantity = 1
		grn_row.stock_qty = flt(grn_row.conversion_factor or 1)
		grn_defaults["items"] = [grn_row]
		grn_defaults["item_details"] = group_items_for_ui(
			grn_defaults["items"], "Goods Received Note"
		)
		grn_defaults["delivery_challan"] = dc.name
		grn_defaults["allow_non_bundle"] = 1
		grn_defaults["against"] = "Work Order"
		grn_defaults["against_id"] = work_order_name
		grn_defaults["supplier_address"] = work_order.supplier_address
		grn_defaults["supplier_address_display"] = work_order.supplier_address_details
		grn_defaults["delivery_address"] = work_order.delivery_address
		grn_defaults["delivery_address_display"] = work_order.delivery_address_details
		grn = self._transaction_from_defaults("Goods Received Note", grn_defaults)
		grn.submit()
		self.assertEqual(balance(from_location), start_from)
		self.assertEqual(balance(printing_supplier), start_supplier)
		self.assertEqual(voucher_qty("Goods Received Note", grn.name, printing_supplier), -1)
		self.assertEqual(voucher_qty("Goods Received Note", grn.name, from_location), 1)
		self.assertEqual(stock_qty("Goods Received Note", grn.name, grn.from_warehouse), -1)
		self.assertEqual(stock_qty("Goods Received Note", grn.name, grn.to_warehouse), 1)

		grn.cancel()
		self.assertEqual(balance(from_location), start_from - 1)
		self.assertEqual(balance(printing_supplier), start_supplier + 1)

		return_name = create_return_grn(
			dc.name,
			[
				{
					"delivery_challan_item": dc.items[0].name,
					"return_quantity": 1,
				}
			],
		)
		return_grn = frappe.get_doc("Goods Received Note", return_name)
		self.assertEqual(return_grn.allow_non_bundle, 0)
		return_grn.submit()
		self.assertEqual(balance(from_location), start_from)
		self.assertEqual(balance(printing_supplier), start_supplier)
		self.assertEqual(
			voucher_qty("Goods Received Note", return_grn.name, printing_supplier), -1
		)
		self.assertEqual(voucher_qty("Goods Received Note", return_grn.name, from_location), 1)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Work Order Deliverables", dc.items[0].ref_docname, "pending_quantity"
				)
			),
			2,
		)

		redelivery_defaults = get_dc_work_order_defaults(work_order_name)
		redelivery_row = next(
			frappe._dict(row)
			for row in redelivery_defaults["items"]
			if row.get("item_variant") == variant
			and json.loads(row.get("set_combination") or "{}") == combination
		)
		redelivery_row.qty = 1
		redelivery_row.delivered_quantity = 1
		redelivery_row.stock_qty = flt(redelivery_row.conversion_factor or 1)
		redelivery_defaults["items"] = [redelivery_row]
		redelivery_defaults["item_details"] = group_items_for_ui(
			redelivery_defaults["items"], "Delivery Challan"
		)
		redelivery_defaults["allow_non_bundle"] = 1
		redelivery_defaults["work_order"] = work_order_name
		redelivery_defaults["supplier_address"] = work_order.supplier_address
		redelivery_defaults["supplier_address_details"] = work_order.supplier_address_details
		redelivery_defaults["from_address"] = work_order.delivery_address
		redelivery_defaults["from_address_details"] = work_order.delivery_address_details
		redelivery = self._transaction_from_defaults(
			"Delivery Challan", redelivery_defaults
		)
		redelivery.submit()
		self.assertEqual(balance(from_location), start_from - 1)
		self.assertEqual(balance(printing_supplier), start_supplier + 1)

		frappe.db.savepoint("before_return_cancel_with_redelivery")
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"has already been re-delivered",
		):
			return_grn.cancel()
		frappe.db.rollback(save_point="before_return_cancel_with_redelivery")
		return_grn.reload()
		self.assertEqual(return_grn.docstatus, 1)
		self.assertEqual(balance(from_location), start_from - 1)
		self.assertEqual(balance(printing_supplier), start_supplier + 1)

		redelivery.cancel()
		self.assertEqual(balance(from_location), start_from)
		self.assertEqual(balance(printing_supplier), start_supplier)
		return_grn.cancel()
		self.assertEqual(balance(from_location), start_from - 1)
		self.assertEqual(balance(printing_supplier), start_supplier + 1)
		dc.cancel()
		self.assertEqual(balance(from_location), start_from)
		self.assertEqual(balance(printing_supplier), start_supplier)
		for doctype, name in (
			("Delivery Challan", dc.name),
			("Delivery Challan", redelivery.name),
			("Goods Received Note", grn.name),
			("Goods Received Note", return_grn.name),
		):
			self.assertFalse(
				frappe.db.exists(
					"Cut Bundle Movement Ledger",
					{
						"voucher_type": doctype,
						"voucher_no": name,
						"is_cancelled": 0,
					},
				)
			)

	def test_piece_tracking_rebuild_preserves_work_order_pending_quantity(self):
		from essdee_yrp.work_order_piece_tracking import rebuild_work_order_piece_tracking

		work_order_name = "YRP-WO-2026-00040"
		if not frappe.db.exists("Work Order", work_order_name):
			self.skipTest(f"Printing Work Order oracle {work_order_name} is unavailable")
		row_name = frappe.db.get_value(
			"Work Order Deliverables",
			{"parent": work_order_name, "pending_quantity": 0},
			"name",
		)
		if not row_name:
			self.skipTest("Printing Work Order has no fully delivered row")

		frappe.db.set_value(
			"Work Order Deliverables",
			row_name,
			"pending_quantity",
			1,
			update_modified=False,
		)
		rebuild_work_order_piece_tracking(work_order_name, check_permission=False)
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Work Order Deliverables", row_name, "pending_quantity"
				)
			),
			1,
		)

	def test_collapsed_cbml_query_isolates_set_combinations(self):
		seed_name = frappe.db.get_value(
			"Cut Bundle Movement Ledger",
			{
				"lot": "C0826-57",
				"supplier": "S-0170",
				"collapsed_bundle": 1,
				"is_cancelled": 0,
			},
			"name",
		)
		if not seed_name:
			self.skipTest("Collapsed CBML oracle is unavailable")
		seed = frappe.get_doc("Cut Bundle Movement Ledger", seed_name)
		other_combination = {
			"major_colour": "CBML Isolation Test",
			"major_part": "Top",
		}
		row = frappe.get_doc(
			{
				"doctype": "Cut Bundle Movement Ledger",
				"lot": seed.lot,
				"supplier": seed.supplier,
				"lay_no": 0,
				"bundle_no": 0,
				"panel": seed.panel,
				"shade": "NA",
				"collapsed_bundle": 1,
				"item_variant": seed.item_variant,
				"item": seed.item,
				"voucher_type": seed.voucher_type,
				"voucher_no": seed.voucher_no,
				"size": seed.size,
				"colour": seed.colour,
				"quantity": 99,
				"quantity_after_transaction": 99,
				"set_combination": json.dumps(other_combination),
				"posting_date": nowdate(),
				"posting_time": nowtime(),
			}
		)
		row.flags.ignore_permissions = 1
		row.set_posting_datetime()
		row.set_key()
		row.insert(ignore_permissions=True)
		row.submit()

		other_rows = get_collapsed_previous_cbm_list(
			"9999-12-31",
			"23:59:59",
			seed.supplier,
			seed.item_variant,
			lot=seed.lot,
			set_combination=other_combination,
		)
		seed_rows = get_collapsed_previous_cbm_list(
			"9999-12-31",
			"23:59:59",
			seed.supplier,
			seed.item_variant,
			lot=seed.lot,
			set_combination=seed.set_combination,
		)
		self.assertEqual(other_rows[0].name, row.name)
		self.assertNotEqual(seed_rows[0].name, row.name)

	def test_printing_first_collapse_redelivery_and_lifo_cancel(self):
		work_order_name = "YRP-WO-2026-00040"
		lot = "C0826-57"
		variant = "Maze Capri Set R.N.S-Front-Red-45 cm"
		combination = {"major_colour": "Red", "major_part": "Top"}
		source = "S-0164"
		target = "Sri Krishna Printing"
		if not all(
			frappe.db.exists(doctype, name)
			for doctype, name in (
				("Work Order", work_order_name),
				("Item Variant", variant),
				("Supplier", source),
				("Supplier", target),
			)
		):
			self.skipTest("Printing first-collapse oracle data is unavailable")
		self._seed_bundle_balance(
			work_order=work_order_name,
			lot=lot,
			location=source,
			item_variant=variant,
			panel="Front",
			colour="Red",
			size="45 cm",
			set_combination=combination,
			quantity=2,
		)

		latest_exact = []
		for row in get_latest_cbml_for_variant(
			source, lot, "45 cm", "Red", "Front", "Maze Capri Set R.N.S"
		):
			doc = frappe.get_doc("Cut Bundle Movement Ledger", row.name)
			if (
				doc.panel == "Front"
				and _collapsed_set_combination_key(doc.set_combination)
				== _collapsed_set_combination_key(combination)
			):
				latest_exact.append(doc)
		if not latest_exact:
			self.skipTest("No exact Front/Red bundles are available at S-0164")
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"lot": lot,
					"supplier": source,
					"item_variant": variant,
					"collapsed_bundle": 1,
					"is_cancelled": 0,
				},
			)
		)
		exact_opening = sum(flt(row.quantity_after_transaction) for row in latest_exact)
		self.assertGreaterEqual(exact_opening, 2)

		def collapsed_balance(location):
			rows = get_collapsed_previous_cbm_list(
				"9999-12-31",
				"23:59:59",
				location,
				variant,
				lot=lot,
				set_combination=combination,
			)
			return flt(rows[0].quantity_after_transaction) if rows else 0

		def make_dc():
			defaults = get_dc_work_order_defaults(work_order_name)
			row = next(
				frappe._dict(value)
				for value in defaults["items"]
				if value.get("item_variant") == variant
				and _collapsed_set_combination_key(value.get("set_combination"))
				== _collapsed_set_combination_key(combination)
			)
			row.qty = 1
			row.delivered_quantity = 1
			row.stock_qty = flt(row.conversion_factor or 1)
			defaults["items"] = [row]
			defaults["item_details"] = group_items_for_ui(
				defaults["items"], "Delivery Challan"
			)
			defaults["work_order"] = work_order_name
			defaults["from_location"] = source
			defaults["from_warehouse"] = source
			defaults["allow_non_bundle"] = 1
			work_order = frappe.get_doc("Work Order", work_order_name)
			defaults["supplier_address"] = work_order.supplier_address
			defaults["supplier_address_details"] = work_order.supplier_address_details
			defaults["from_address"] = work_order.delivery_address
			defaults["from_address_details"] = work_order.delivery_address_details
			return self._transaction_from_defaults("Delivery Challan", defaults)

		first = make_dc()
		first.submit()
		self.assertEqual(collapsed_balance(source), exact_opening - 1)
		self.assertEqual(collapsed_balance(target), 1)
		self.assertTrue(all(row.reload().is_collapsed for row in latest_exact))

		second = make_dc()
		second.submit()
		self.assertEqual(collapsed_balance(source), exact_opening - 2)
		self.assertEqual(collapsed_balance(target), 2)
		frappe.db.savepoint("before_out_of_order_collapsed_cancel")
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Cancel the later collapsed-bundle movement Delivery Challan",
		):
			first.cancel()
		frappe.db.rollback(save_point="before_out_of_order_collapsed_cancel")
		first.reload()
		self.assertEqual(first.docstatus, 1)
		self.assertEqual(collapsed_balance(source), exact_opening - 2)
		self.assertEqual(collapsed_balance(target), 2)

		second.cancel()
		first.cancel()
		self.assertEqual(collapsed_balance(source), 0)
		self.assertEqual(collapsed_balance(target), 0)
		self.assertTrue(all(not row.reload().is_collapsed for row in latest_exact))
		for name in (first.name, second.name):
			self.assertFalse(
				frappe.db.exists(
					"Cut Bundle Movement Ledger",
					{
						"voucher_type": "Delivery Challan",
						"voucher_no": name,
						"is_cancelled": 0,
					},
				)
			)

	def test_printing_exact_bundle_dc_return_and_cancel(self):
		work_order_name = "YRP-WO-2026-00040"
		lot = "C0826-57"
		variant = "Maze Capri Set R.N.S-Front-Red-45 cm"
		combination = {"major_colour": "Red", "major_part": "Top"}
		source = "S-0164"
		target = "Sri Krishna Printing"
		if not all(
			frappe.db.exists(doctype, name)
			for doctype, name in (
				("Work Order", work_order_name),
				("Item Variant", variant),
				("Supplier", source),
				("Supplier", target),
			)
		):
			self.skipTest("Printing exact-return oracle data is unavailable")
		self._seed_bundle_balance(
			work_order=work_order_name,
			lot=lot,
			location=source,
			item_variant=variant,
			panel="Front",
			colour="Red",
			size="45 cm",
			set_combination=combination,
			quantity=2,
		)

		exact = None
		for row in get_latest_cbml_for_variant(
			source, lot, "45 cm", "Red", "Front", "Maze Capri Set R.N.S"
		):
			candidate = frappe.get_doc("Cut Bundle Movement Ledger", row.name)
			if (
				candidate.panel == "Front"
				and flt(candidate.quantity_after_transaction) > 0
				and _collapsed_set_combination_key(candidate.set_combination)
				== _collapsed_set_combination_key(combination)
			):
				exact = candidate
				break
		if not exact:
			self.skipTest("No exact Front/Red bundle is available at S-0164")
		quantity = flt(exact.quantity_after_transaction)
		deliverable_name, ordered_quantity = frappe.db.get_value(
			"Work Order Deliverables",
			{"parent": work_order_name, "item_variant": variant},
			["name", "qty"],
		)
		frappe.db.set_value(
			"Work Order Deliverables",
			deliverable_name,
			{
				"pending_quantity": quantity,
				"stock_update": flt(ordered_quantity) - quantity,
			},
			update_modified=False,
		)

		def make_cpm(location):
			movement = {
				"accessory_data": [],
				"collapsed_details": [],
				"is_set_item": 1,
				"panels": {"Top": ["Front"]},
				"data": {
					"Red-Top": {
						"part": "Top",
						"data": [
							{
								"lay_no": exact.lay_no,
								"bundle_no": exact.bundle_no,
								"shade": exact.shade,
								"size": exact.size,
								"set_combination": combination,
								"Front": quantity,
								"Front_colour": exact.colour,
								"Front_moved": 1,
								"bundle_moved": 1,
							}
						],
					}
				},
			}
			cpm = frappe.new_doc("Cut Panel Movement")
			cpm.lot = lot
			cpm.item = "Maze Capri Set R.N.S"
			cpm.from_warehouse = location
			cpm.posting_date = nowdate()
			cpm.posting_time = nowtime()
			cpm.cut_panel_movement_json = json.dumps(movement)
			cpm.insert()
			cpm.submit()
			return cpm

		outward_cpm = make_cpm(source)
		dc_defaults = build_delivery_challan_defaults(
			outward_cpm.name, work_order_name
		)
		dc_defaults["from_location"] = source
		dc_defaults["from_warehouse"] = source
		dc = self._transaction_from_defaults("Delivery Challan", dc_defaults)
		dc.submit()
		self.assertEqual(sum(flt(row.delivered_quantity) for row in dc.items), quantity)

		return_cpm = make_cpm(target)
		return_name = create_return_grn(
			dc.name,
			[
				{
					"delivery_challan_item": dc.items[0].name,
					"return_quantity": quantity,
				}
			],
		)
		return_grn = frappe.get_doc("Goods Received Note", return_name)
		return_grn.cut_panel_movement = return_cpm.name
		return_grn.save()
		return_grn.submit()
		self.assertEqual(return_grn.allow_non_bundle, 0)
		self.assertEqual(
			sum(
				flt(row.quantity)
				for row in frappe.get_all(
					"Cut Bundle Movement Ledger",
					filters={
						"voucher_type": "Goods Received Note",
						"voucher_no": return_grn.name,
						"supplier": source,
						"is_cancelled": 0,
					},
					fields=["quantity"],
				)
			),
			quantity,
		)
		self.assertEqual(
			sum(
				flt(row.quantity)
				for row in frappe.get_all(
					"Cut Bundle Movement Ledger",
					filters={
						"voucher_type": "Goods Received Note",
						"voucher_no": return_grn.name,
						"supplier": target,
						"is_cancelled": 0,
					},
					fields=["quantity"],
				)
			),
			-quantity,
		)

		return_grn.cancel()
		return_cpm.cancel()
		dc.cancel()
		outward_cpm.cancel()
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"voucher_type": ["in", ["Delivery Challan", "Goods Received Note"]],
					"voucher_no": ["in", [dc.name, return_grn.name]],
					"is_cancelled": 0,
				},
			)
		)
		exact.reload()
		self.assertEqual(exact.quantity_after_transaction, quantity)
		self.assertEqual(exact.is_collapsed, 0)

	def test_cut_panel_movement_allows_only_one_active_root_transaction(self):
		movement_name = "CPM-2608-00220"
		if not frappe.db.exists(
			"Cut Panel Movement",
			{"name": movement_name, "docstatus": 1, "against_id": ["is", "not set"]},
		):
			self.skipTest(f"Unlinked Cut Panel Movement oracle {movement_name} is unavailable")

		defaults = build_stock_entry_defaults(movement_name)
		entry = frappe.new_doc("Stock Entry")
		entry.purpose = defaults["purpose"]
		entry.from_warehouse = defaults["from_warehouse"]
		entry.from_supplier = defaults["from_supplier"]
		entry.to_warehouse = "S-0163"
		entry.cut_panel_movement = movement_name
		entry.item_details = json.dumps(defaults["item_details"])
		entry.insert()

		with self.assertRaisesRegex(
			frappe.ValidationError,
			f"already used by active Stock Entry {entry.name}",
		):
			build_delivery_challan_defaults(movement_name, "WO-NOT-REACHED")

		companion = frappe._dict(
			doctype="Stock Entry",
			name="STE-COMPLETION-TEST",
			purpose="DC Completion",
			cut_panel_movement=movement_name,
		)
		validate_transaction_link(companion)
		entry.delete()

	def test_cut_panel_movement_dc_and_grn_round_trip_lifecycle(self):
		movement_name = "CPM-2608-00220"
		work_order_name = "WO-2627-00857"
		if not frappe.db.exists(
			"Cut Panel Movement",
			{"name": movement_name, "docstatus": 1, "against_id": ["is", "not set"]},
		):
			self.skipTest(f"Unlinked Cut Panel Movement oracle {movement_name} is unavailable")
		if not frappe.db.exists(
			"Work Order",
			{
				"name": work_order_name,
				"docstatus": 1,
				"open_status": ["!=", "Close"],
			},
		):
			self.skipTest(f"Open Work Order oracle {work_order_name} is unavailable")

		movement, _ipd, rows = get_grouped_movement_rows(
			movement_name, "Delivery Challan"
		)
		for index, row in enumerate(rows):
			qty = flt(row["qty"])
			common = {
				"item_variant": row["item_variant"],
				"qty": qty,
				"uom": row["uom"],
				"lot": movement.lot,
				"received_type": row["received_type"],
				"pending_quantity": qty,
				"table_index": index,
				"row_index": index,
				"set_combination": row["set_combination"],
			}
			self._insert_submitted_work_order_row(
				"Work Order Deliverables", "deliverables", work_order_name, common
			)
			self._insert_submitted_work_order_row(
				"Work Order Receivables", "receivables", work_order_name, common
			)
			parent_item = frappe.db.get_value(
				"Item Variant", row["item_variant"], "item"
			)
			frappe.db.set_value(
				"Item", parent_item, "allow_negative_stock", 1, update_modified=False
			)
			frappe.clear_document_cache("Item", parent_item)
		frappe.clear_document_cache("Work Order", work_order_name)

		dc_defaults = build_delivery_challan_defaults(movement_name, work_order_name)
		dc = self._transaction_from_defaults("Delivery Challan", dc_defaults)
		dc.submit()
		self.assertEqual(dc.docstatus, 1)
		self.assertEqual(
			frappe.db.get_value("Cut Panel Movement", movement_name, "against_id"),
			dc.name,
		)
		self.assertGreater(
			frappe.db.count(
				"Cut Bundle Movement Ledger",
				filters={
					"voucher_type": "Delivery Challan",
					"voucher_no": dc.name,
					"is_cancelled": 0,
				},
			),
			0,
		)

		incoming = frappe.new_doc("Cut Panel Movement")
		incoming.lot = movement.lot
		incoming.item = movement.item
		incoming.from_warehouse = frappe.db.get_value(
			"Work Order", work_order_name, "supplier"
		)
		incoming.movement_from_cutting = 0
		incoming.posting_date = nowdate()
		incoming.posting_time = nowtime()
		incoming.cut_panel_movement_json = movement.cut_panel_movement_json
		incoming.insert()
		incoming.submit()

		grn_defaults = build_goods_received_note_defaults(incoming.name, work_order_name)
		grn = self._transaction_from_defaults("Goods Received Note", grn_defaults)
		grn.submit()
		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(
			frappe.db.get_value("Cut Panel Movement", incoming.name, "against_id"),
			grn.name,
		)
		self.assertGreater(
			frappe.db.count(
				"Cut Bundle Movement Ledger",
				filters={
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			),
			0,
		)

		grn.cancel()
		self.assertFalse(
			frappe.db.get_value("Cut Panel Movement", incoming.name, "against_id")
		)
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			)
		)
		incoming.cancel()
		dc.cancel()
		self.assertFalse(
			frappe.db.get_value("Cut Panel Movement", movement_name, "against_id")
		)
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"voucher_type": "Delivery Challan",
					"voucher_no": dc.name,
					"is_cancelled": 0,
				},
			)
		)

	def test_cut_panel_movement_rejects_closed_work_order_server_side(self):
		movement_name = "CPM-2608-00220"
		closed_work_order = "WO-2627-00778"
		if not frappe.db.exists(
			"Cut Panel Movement",
			{"name": movement_name, "docstatus": 1, "against_id": ["is", "not set"]},
		):
			self.skipTest(f"Unlinked Cut Panel Movement oracle {movement_name} is unavailable")
		if not frappe.db.exists(
			"Work Order",
			{
				"name": closed_work_order,
				"lot": "C0426-34/1",
				"docstatus": 1,
				"open_status": "Close",
			},
		):
			self.skipTest(f"Closed Work Order oracle {closed_work_order} is unavailable")

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Select an open, submitted Work Order",
		):
			build_delivery_challan_defaults(movement_name, closed_work_order)
		with self.assertRaisesRegex(
			frappe.ValidationError,
			"Select an open, submitted Work Order",
		):
			build_goods_received_note_defaults(movement_name, closed_work_order)

	@patch(
		"essdee_yrp.essdee_yrp.doctype.cut_bundle_movement_ledger.cut_bundle_movement_ledger.update_collapsed_bundle"
	)
	def test_allow_non_bundle_routes_collapsed_bundle_submit_and_cancel(self, update):
		doc = frappe._dict(
			{
				"doctype": "Delivery Challan",
				"name": "DC-COLLAPSED-TEST",
				"lot": "LOT-COLLAPSED-TEST",
				"allow_non_bundle": 1,
				"cut_panel_movement": None,
			}
		)
		with patch("essdee_yrp.cutting.movement._bundle_tracking_disabled", return_value=False):
			apply_transaction(doc)
			apply_transaction(doc, cancelled=True)
		self.assertEqual(
			[(entry.args, entry.kwargs) for entry in update.call_args_list],
			[
				(
					("Delivery Challan", "DC-COLLAPSED-TEST", "on_submit"),
					{"non_stich_process": False},
				),
				(
					("Delivery Challan", "DC-COLLAPSED-TEST", "on_cancel"),
					{"non_stich_process": False},
				),
			],
		)

		update.reset_mock()
		grn = frappe._dict(
			{
				"doctype": "Goods Received Note",
				"name": "GRN-COLLAPSED-TEST",
				"lot": "LOT-COLLAPSED-TEST",
				"allow_non_bundle": 1,
				"cut_panel_movement": None,
			}
		)
		with patch("essdee_yrp.cutting.movement._bundle_tracking_disabled", return_value=False):
			apply_transaction(grn)
		self.assertEqual(
			(update.call_args.args, update.call_args.kwargs),
			(
				("Goods Received Note", "GRN-COLLAPSED-TEST", "on_submit"),
				{"non_stich_process": True},
			),
		)

	def test_cut_bundle_edit_transform_and_cancel_lifecycle(self):
		rows = frappe.db.sql(
			"""
			SELECT current.lot, current.supplier, current.item, current.lay_no,
				current.bundle_no, current.size, current.colour, current.panel,
				current.shade, current.set_combination,
				current.quantity_after_transaction
			FROM `tabCut Bundle Movement Ledger` current
			WHERE current.is_cancelled = 0 AND current.is_collapsed = 0
				AND current.collapsed_bundle = 0 AND current.transformed = 0
				AND current.quantity_after_transaction > 0
			ORDER BY current.creation DESC
			LIMIT 1
			""",
			as_dict=True,
		)
		if not rows:
			self.skipTest("No current untransformed bundle is available for the CBE oracle")
		row = rows[0]
		lot = row.lot
		warehouse = row.supplier
		selection = {
			"lay_no": row.lay_no,
			"bundle_no": row.bundle_no,
			"qty": row.quantity_after_transaction,
			"panel": row.panel,
			"set_combination": frappe.parse_json(row.set_combination) or {},
			"shade": row.shade,
			"size": row.size,
			"colour": row.colour,
			"is_collapsed": False,
		}
		movement = {"panels": [], "data": {}, "accessory_data": [], "is_set_item": 0}

		doc = frappe.new_doc("Cut Bundle Edit")
		doc.lot = lot
		doc.item = row.item
		doc.warehouse = warehouse
		doc.colour = row.colour
		doc.posting_date = nowdate()
		doc.posting_time = nowtime()
		doc.cut_panel_movement_json = json.dumps(movement)
		doc.input_json = json.dumps([selection])
		doc.output_json = json.dumps([selection])
		doc.insert()
		doc.submit()

		created = frappe.get_all(
			"Cut Bundle Movement Ledger",
			filters={"transformed_from": doc.name, "is_cancelled": 0},
			pluck="name",
		)
		self.assertTrue(created)
		self.assertTrue(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"lot": lot,
					"supplier": warehouse,
					"lay_no": selection["lay_no"],
					"bundle_no": selection["bundle_no"],
					"size": selection["size"],
					"colour": selection["colour"],
					"panel": selection["panel"],
					"transformed": 1,
					"is_cancelled": 0,
				},
			)
		)

		doc.cancel()
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{"transformed_from": doc.name, "is_cancelled": 0},
			)
		)
		self.assertTrue(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"lot": lot,
					"supplier": warehouse,
					"lay_no": selection["lay_no"],
					"bundle_no": selection["bundle_no"],
					"size": selection["size"],
					"colour": selection["colour"],
					"panel": selection["panel"],
					"transformed": 0,
					"is_cancelled": 0,
				},
			)
		)

	def test_cutting_reports_match_migrated_oracles(self):
		if not frappe.db.exists(
			"Cutting LaySheet", {"bundle_generated_date": "2026-08-01"}
		):
			self.skipTest("Migrated Cutting report oracle is unavailable")

		daily = get_daily_production_report("2026-08-01", "")
		self.assertEqual(
			(
				len(daily["report_data"]),
				daily["bundle_generated"],
				daily["label_printed"],
				daily["created"],
			),
			(6, 13, 13, 11),
		)
		self.assertEqual(
			sum(row["total_sum"] for row in daily["report_data"]),
			13046,
		)

		summary = get_daily_production_summary_report(
			from_date="2026-08-01",
			to_date="2026-08-01",
			location="",
		)
		self.assertEqual(len(summary), 1)
		self.assertEqual(summary[0]["report_data"], daily["report_data"])

		detail = get_cutting_detail_report("2026-08-01", "2026-08-01", "")
		self.assertEqual(
			(
				len(detail["report_data"]),
				detail["bundle_generated"],
				detail["label_printed"],
				detail["created"],
			),
			(6, 13, 13, 13),
		)

		cut_sheet = get_cut_sheet_report("2026-08-01", "")
		self.assertEqual(len(cut_sheet), 7)
		self.assertIn(
			("EC-11401 Tank Top (MMA Collection)", "C0426-35"),
			{(row["style_no"], row["lot_no"]) for row in cut_sheet},
		)

		multi_ccr = get_multiccr(
			open_status="",
			lot_list='["C0426-35"]',
			item_list="[]",
			category="",
		)
		self.assertEqual(multi_ccr["output_lots"], ["C0426-35"])
		self.assertEqual(
			multi_ccr["output_items"],
			["EC-11401 Tank Top (MMA Collection)"],
		)

	def test_migrated_cutting_laysheet_creates_f16_grn(self):
		laysheet_name = "CLS-2608-00049"
		if not frappe.db.exists("Cutting LaySheet", laysheet_name):
			self.skipTest(f"Migrated oracle {laysheet_name} is unavailable")

		# This is a historical, unprinted draft from the migrated production
		# snapshot. Later receipts have already reduced its Work Order pending and
		# cloth balance. Restore only those prerequisites inside this test's
		# rollback transaction; production validations remain fully active.
		laysheet = frappe.get_doc("Cutting LaySheet", laysheet_name)
		work_order_name, production_detail = frappe.db.get_value(
			"Cutting Plan",
			laysheet.cutting_plan,
			["work_order", "production_detail"],
		)
		work_order = frappe.get_doc("Work Order", work_order_name)
		item = frappe.db.get_value("Lot", laysheet.lot, "item")
		_unused_defaults, receipt_rows = _cutting_grn_output_rows(
			laysheet,
			work_order,
			item,
			production_detail,
		)
		for row in receipt_rows:
			frappe.db.set_value(
				"Work Order Receivables",
				row.ref_docname,
				"pending_quantity",
				max(float(row.pending_quantity or 0), float(row.quantity or 0)),
				update_modified=False,
			)
		for row in _cutting_grn_consumed_rows(laysheet):
			parent_item = frappe.db.get_value("Item Variant", row["item_variant"], "item")
			frappe.db.set_value(
				"Item",
				parent_item,
				"allow_negative_stock",
				1,
				update_modified=False,
			)
			frappe.clear_document_cache("Item", parent_item)
		pending_before = {
			row.ref_docname: flt(
				frappe.db.get_value(
					"Work Order Receivables", row.ref_docname, "pending_quantity"
				)
			)
			for row in receipt_rows
		}

		before = frappe.get_all(
			"Goods Received Note",
			filters={"cutting_laysheet": laysheet_name},
			pluck="name",
		)
		grn_name = create_grn_entry(laysheet_name)
		grn = frappe.get_doc("Goods Received Note", grn_name)

		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(grn.cutting_laysheet, laysheet_name)
		self.assertEqual(grn.delivery_location, grn.supplier)
		self.assertEqual(grn.to_warehouse, grn.from_warehouse)
		self.assertFalse(grn.is_internal_unit)
		self.assertTrue(grn.items)
		self.assertTrue(grn.grn_deliverables)
		self.assertTrue(all(row.received_type for row in grn.items))
		self.assertTrue(all(row.lot for row in grn.items))
		self.assertNotIn(grn.name, before)
		for row in grn.items:
			self.assertAlmostEqual(
				flt(
					frappe.db.get_value(
						"Work Order Receivables", row.ref_docname, "pending_quantity"
					)
				),
				pending_before[row.ref_docname] - flt(row.quantity),
				places=3,
			)

		active_sles = frappe.get_all(
			"Stock Ledger Entry",
			filters={
				"voucher_type": "Goods Received Note",
				"voucher_no": grn.name,
				"is_cancelled": 0,
			},
			fields=["qty", "lot", "received_type"],
		)
		self.assertTrue(any(flt(row.qty) > 0 for row in active_sles))
		self.assertTrue(any(flt(row.qty) < 0 for row in active_sles))
		self.assertTrue(all(row.lot and row.received_type for row in active_sles))
		self.assertEqual(create_grn_entry(laysheet_name), grn.name)
		self.assertEqual(
			frappe.db.count(
				"Stock Ledger Entry",
				filters={
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			),
			len(active_sles),
		)

		parent_state_before_retry = frappe.db.get_value(
			"Cutting Plan",
			laysheet.cutting_plan,
			["completed_items_json", "incomplete_items_json"],
		)
		retry = print_labels(
			[laysheet.cutting_laysheet_bundles[0].as_dict()],
			laysheet.lay_no,
			laysheet.name,
			"Panel",
			cutting_plan=laysheet.cutting_plan,
		)
		self.assertEqual(retry["grn"], grn.name)
		self.assertIn("^XA", retry["zpl"])
		self.assertEqual(
			mark_labels_printed(laysheet.name, grn.name),
			{"status": "Label Printed", "goods_received_note": grn.name},
		)
		self.assertEqual(
			frappe.db.get_value(
				"Cutting Plan",
				laysheet.cutting_plan,
				["completed_items_json", "incomplete_items_json"],
			),
			parent_state_before_retry,
		)

		ledger_source = frappe._dict(
			{
				"doctype": laysheet.doctype,
				"name": laysheet.name,
				"lot": laysheet.lot,
				"item": laysheet.item,
				"lay_no": laysheet.lay_no,
				"cutting_plan": laysheet.cutting_plan,
				"cutting_order": laysheet.cutting_order,
				"posting_date": nowdate(),
				"posting_time": nowtime(),
				"cutting_laysheet_bundles": [laysheet.cutting_laysheet_bundles[0]],
			}
		)
		create_cut_bundle_ledger(ledger_source)
		bundle_count = frappe.db.count(
			"Cut Bundle Movement Ledger",
			filters={
				"voucher_type": "Cutting LaySheet",
				"voucher_no": laysheet.name,
				"is_cancelled": 0,
			},
		)
		self.assertGreater(bundle_count, 0)
		create_cut_bundle_ledger(ledger_source)
		self.assertEqual(
			frappe.db.count(
				"Cut Bundle Movement Ledger",
				filters={
					"voucher_type": "Cutting LaySheet",
					"voucher_no": laysheet.name,
					"is_cancelled": 0,
				},
			),
			bundle_count,
		)
		cancel_cut_bundle(ledger_source)
		self.assertFalse(
			frappe.db.exists(
				"Cut Bundle Movement Ledger",
				{
					"voucher_type": "Cutting LaySheet",
					"voucher_no": laysheet.name,
					"is_cancelled": 0,
				},
			)
		)

		grn.cancel()
		self.assertEqual(grn.docstatus, 2)
		self.assertFalse(
			frappe.db.exists(
				"Stock Ledger Entry",
				{
					"voucher_type": "Goods Received Note",
					"voucher_no": grn.name,
					"is_cancelled": 0,
				},
			)
		)
		for ref_docname, pending in pending_before.items():
			self.assertAlmostEqual(
				flt(
					frappe.db.get_value(
						"Work Order Receivables", ref_docname, "pending_quantity"
					)
				),
				pending,
				places=3,
			)

	def test_migrated_grn_consumption_resolves_legacy_deliverable(self):
		grn_name = "GRN-2627-05036"
		if not frappe.db.exists("Goods Received Note", grn_name):
			self.skipTest(f"Migrated oracle {grn_name} is unavailable")
		grn = frappe.get_doc("Goods Received Note", grn_name)
		work_order = frappe.get_doc("Work Order", grn.against_id)
		deliverables = {row.name: row for row in work_order.deliverables}
		legacy_row = grn.grn_deliverables[0]
		self.assertFalse(legacy_row.work_order_deliverable)
		resolved = _resolve_deliverable_source(legacy_row, deliverables, work_order)
		self.assertEqual(resolved.name, "64o9unhedh")

	def test_migrated_packing_grn_allows_stock_only_consumption_rows(self):
		grn_name = "GRN-2627-05053"
		if not frappe.db.exists("Goods Received Note", grn_name):
			self.skipTest(f"Migrated oracle {grn_name} is unavailable")
		grn = frappe.get_doc("Goods Received Note", grn_name)
		self.assertTrue(grn.includes_packing)
		self.assertTrue(grn.grn_deliverables)
		self.assertFalse(
			any(row.work_order_deliverable for row in grn.grn_deliverables)
		)

		from essdee_yrp.fabric_grn import on_cancel, on_submit

		with patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries:
			on_submit(grn)
			issued = make_entries.call_args.args[0]
			self.assertEqual(len(issued), len(grn.grn_deliverables))
			self.assertTrue(all(row["qty"] < 0 for row in issued))

		with patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries:
			on_cancel(grn)
			restored = make_entries.call_args.args[0]
			self.assertEqual(len(restored), len(grn.grn_deliverables))
			self.assertTrue(all(row["qty"] < 0 for row in restored))
			self.assertTrue(all(row["is_cancelled"] == 1 for row in restored))
			self.assertTrue(make_entries.call_args.kwargs["cancel"])


class TestCuttingPlanClothUsage(UnitTestCase):
	def test_bundle_generation_persists_precise_cutting_plan_cloth_usage(self):
		TestCuttingBusinessLogic._assert_bundle_generation_persists_precise_cutting_plan_cloth_usage(
			self
		)
