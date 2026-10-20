import copy
import unittest
from unittest.mock import call, patch

import frappe
from frappe.model.meta import get_field_precision
from frappe.utils import flt

from essdee_yrp.purchase_invoice import (
	_build_work_order_context,
	_inactive_zero_receivable,
	_validate_selected_physical_quantities,
	build_legacy_work_order_invoice_payload,
	build_work_order_invoice_payload,
	commercial_group_key,
)
from essdee_yrp.work_order_billing import _get_work_order_process_cost, _process_cost_rate
from essdee_yrp.work_order_piece_tracking import get_selected_grn_piece_quantities


class _Row(frappe._dict):
	def as_dict(self):
		return dict(self)


class WorkOrderBillingTest(unittest.TestCase):
	def _calculated(self, item_variant="GARMENT-S", quantity=10, colour="Navy"):
		return frappe._dict(
			item_variant=item_variant,
			quantity=quantity,
			delivered_quantity=quantity,
			received_qty=quantity,
			billed_qty=0,
			set_combination={"major_colour": colour},
		)

	def _grn_item(self, item_variant="GARMENT-S", quantity=2, colour="Navy", idx=1):
		return frappe._dict(
			name=f"GRN-ITEM-{idx}",
			idx=idx,
			item_variant=item_variant,
			quantity=quantity,
			stock_qty=quantity,
			rate=3,
			amount=quantity * 3,
			uom="Nos",
			received_type="Accepted",
			set_combination={"major_colour": colour},
		)

	def _fixture(
		self,
		*,
		received_json=False,
		process_cost=True,
		gstin=None,
		grn_items=None,
		calculated=None,
	):
		grn_items = grn_items or [self._grn_item()]
		calculated = calculated or [self._calculated()]
		work_order = frappe._dict(
			name="WO-1",
			process_name="Sewing",
			process_cost="PC-1" if process_cost else None,
			production_detail="IPD-1",
			item="GARMENT",
			lot="LOT-1",
			wo_date="2026-04-01",
			is_rework=0,
			supplier="SUP-1",
			work_order_calculated_items=calculated,
			work_order_track_pieces=[],
			receivables=[
				frappe._dict(
					name=f"RECEIVABLE-{row.idx}",
					item_variant=row.item_variant,
					set_combination=row.set_combination,
					cost=3,
				)
				for row in grn_items
			],
		)
		grn = frappe._dict(
			name="GRN-1",
			against_id=work_order.name,
			posting_date="2026-04-02",
			process_name="Sewing",
			items=grn_items,
		)
		process = frappe._dict(
			name="Sewing",
			item="BILLING",
			is_group=0,
			process_details=[],
		)
		ipd = frappe._dict(
			name="IPD-1",
			is_set_item=0,
			primary_item_attribute="Size",
			cutting_process="Sewing" if received_json else "Cutting",
			stiching_in_stage="Input",
			stiching_attribute="Panel",
			ipd_processes=[],
			stiching_item_details=[],
		)
		cost = frappe._dict(
			name="PC-1",
			tax_slab="GST-5",
			depends_on_attribute=0,
			attribute=None,
			process_cost_values=[frappe._dict(min_order_qty=0, price=5)],
		)
		return work_order, grn, process, ipd, cost, gstin

	def _build(
		self,
		fixture,
		*,
		extra_grns=None,
		final_rates=None,
		piece_quantities=None,
		variant_attributes=None,
	):
		work_order, grn, process, ipd, cost, gstin = fixture
		grns = [grn, *(extra_grns or [])]
		documents = {
			("YRP Work Order", work_order.name): work_order,
			("YRP Process", process.name): process,
			("YRP Process Cost", cost.name): cost,
			**{("YRP Goods Received Note", row.name): row for row in grns},
		}

		def get_doc(doctype, name):
			return documents[(doctype, name)]

		with (
			patch("essdee_yrp.work_order_billing._validate_selected_grn"),
			patch(
				"essdee_yrp.work_order_billing._quantity_precisions",
				return_value={"physical": 3, "commercial": 3, "billed": 3},
			),
			patch("essdee_yrp.work_order_billing.frappe.get_doc", side_effect=get_doc),
			patch("essdee_yrp.work_order_billing.frappe.get_cached_doc", return_value=ipd),
			patch(
				"essdee_yrp.work_order_billing.frappe.db.get_single_value",
				return_value="2026-01-01",
			),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=gstin),
			patch("essdee_yrp.work_order_billing.get_or_create_variant", return_value="BILLING"),
			patch("essdee_yrp.work_order_billing.resolve_item_uom", return_value=frappe._dict(uom="Nos")),
			patch("essdee_yrp.work_order_billing._get_item_group", return_value="Services"),
			patch("essdee_yrp.work_order_billing._get_tax_rate", return_value=5),
			patch(
				"essdee_yrp.work_order_billing.get_variant_attributes",
				side_effect=lambda item: (variant_attributes or {}).get(item, {}),
			),
			patch(
				"essdee_yrp.work_order_billing.get_selected_grn_piece_quantities",
				return_value=piece_quantities or {},
			),
		):
			return build_work_order_invoice_payload(
				[row.name for row in grns],
				supplier="SUP-1",
				final_rates=final_rates,
			)

	def test_rate_tiers_match_production_api_rules(self):
		def cost(rows, *, depends_on_attribute=0, attribute=None):
			return frappe._dict(
				depends_on_attribute=depends_on_attribute,
				attribute=attribute,
				process_cost_values=[frappe._dict(**row) for row in rows],
			)

		single = cost([{"min_order_qty": 100, "price": 7}])
		self.assertEqual(_process_cost_rate(single, 1, "ITEM"), 7)

		multiple = cost([
			{"min_order_qty": 100, "price": 10},
			{"min_order_qty": 50, "price": 3},
			{"min_order_qty": 50, "price": 2},
		])
		self.assertEqual(_process_cost_rate(multiple, 100, "ITEM"), 5)
		self.assertEqual(_process_cost_rate(multiple, 50, "ITEM"), 0)

		attribute_cost = cost(
			[
				{"min_order_qty": 0, "price": 4, "attribute_value": "Red"},
				{"min_order_qty": 0, "price": 9, "attribute_value": "Blue"},
			],
			depends_on_attribute=1,
			attribute="Colour",
		)
		with patch(
			"essdee_yrp.work_order_billing.get_variant_attributes",
			return_value={"Colour": "Red"},
		):
			self.assertEqual(_process_cost_rate(attribute_cost, 10, "ITEM", "Panel"), 4)
			self.assertEqual(_process_cost_rate(attribute_cost, 10, "ITEM", "Colour"), 13)

		blank_attribute_cost = cost(
			[{"min_order_qty": 0, "price": 7, "attribute_value": None}],
			depends_on_attribute=1,
			attribute="Colour",
		)
		with patch(
			"essdee_yrp.work_order_billing.get_variant_attributes",
			return_value={},
		):
			self.assertEqual(_process_cost_rate(blank_attribute_cost, 10, "ITEM", "Panel"), 0)

	def test_historical_process_cost_uses_fallback_filter_order(self):
		work_order = frappe._dict(
			process_name="Sewing",
			item="GARMENT",
			wo_date="2025-01-01",
			lot="LOT-1",
			is_rework=0,
			supplier="SUP-1",
			process_cost="STORED-PC",
		)
		process_cost = frappe._dict(name="PC-FALLBACK")
		with (
			patch(
				"essdee_yrp.work_order_billing.frappe.get_meta",
				return_value=frappe._dict(get_field=lambda fieldname: fieldname == "workflow_state"),
			),
			patch(
				"essdee_yrp.work_order_billing.frappe.get_list",
				side_effect=[[], [], [], [frappe._dict(name=process_cost.name)]],
			) as get_list,
			patch("essdee_yrp.work_order_billing.frappe.get_doc", return_value=process_cost) as get_doc,
		):
			self.assertIs(_get_work_order_process_cost(work_order, True), process_cost)

		base = {
			"process_name": "Sewing",
			"item": "GARMENT",
			"is_expired": 0,
			"from_date": ["<=", "2025-01-01"],
			"docstatus": 1,
			"workflow_state": "Approved",
			"lot": "LOT-1",
			"is_rework": 0,
			"supplier": "SUP-1",
		}
		expected = []
		for filters in (
			base,
			{key: value for key, value in base.items() if key != "supplier"},
			{key: value for key, value in base.items() if key != "lot"},
			{key: value for key, value in base.items() if key not in {"lot", "supplier"}},
		):
			expected.append(
				call(
					"YRP Process Cost",
					filters=filters,
					fields=["name"],
					order_by="modified desc",
					limit_page_length=1,
				)
			)
		self.assertEqual(get_list.call_args_list, expected)
		get_doc.assert_called_once_with("YRP Process Cost", process_cost.name)

	def test_mixed_date_selection_uses_fallback_cost_for_every_work_order(self):
		process = frappe._dict(name="Sewing", item="BILLING", is_group=0, process_details=[])
		ipd = frappe._dict(
			name="IPD-1",
			is_set_item=0,
			primary_item_attribute="Size",
			cutting_process="Cutting",
			stiching_in_stage="Input",
			stiching_attribute="Panel",
			ipd_processes=[],
			stiching_item_details=[],
		)
		documents = {("YRP Process", process.name): process}
		grns = []
		for index, posting_date in enumerate(("2025-12-31", "2026-04-02"), start=1):
			item = self._grn_item(f"GARMENT-{index}", idx=index)
			work_order = frappe._dict(
				name=f"WO-{index}",
				process_name="Sewing",
				process_cost=f"STORED-{index}",
				production_detail="IPD-1",
				item=f"GARMENT-{index}",
				lot="LOT-1",
				wo_date="2025-12-01",
				is_rework=0,
				supplier="SUP-1",
				work_order_calculated_items=[self._calculated(f"GARMENT-{index}")],
				work_order_track_pieces=[],
				receivables=[
					frappe._dict(
						name=f"RECEIVABLE-{index}",
						item_variant=item.item_variant,
						set_combination=item.set_combination,
						cost=3,
					)
				],
			)
			grn = frappe._dict(
				name=f"GRN-{index}",
				against_id=work_order.name,
				posting_date=posting_date,
				items=[item],
			)
			fallback = frappe._dict(
				name=f"FALLBACK-{index}",
				tax_slab=None,
				depends_on_attribute=0,
				process_cost_values=[frappe._dict(min_order_qty=0, price=7)],
			)
			documents[("YRP Work Order", work_order.name)] = work_order
			documents[("YRP Goods Received Note", grn.name)] = grn
			documents[("YRP Process Cost", fallback.name)] = fallback
			grns.append(grn)

		def get_doc(doctype, name):
			return documents[(doctype, name)]

		def get_list(_doctype, *, filters, **_kwargs):
			index = filters["item"].rsplit("-", 1)[1]
			return [frappe._dict(name=f"FALLBACK-{index}")]

		actual_get_meta = frappe.get_meta

		def get_meta(doctype):
			if doctype == "YRP Process Cost":
				return frappe._dict(get_field=lambda _fieldname: None)
			return actual_get_meta(doctype)

		with (
			patch("essdee_yrp.work_order_billing._validate_selected_grn"),
			patch(
				"essdee_yrp.work_order_billing._quantity_precisions",
				return_value={"physical": 3, "commercial": 3, "billed": 3},
			),
			patch("essdee_yrp.work_order_billing.frappe.get_doc", side_effect=get_doc),
			patch("essdee_yrp.work_order_billing.frappe.get_cached_doc", return_value=ipd),
			patch(
				"essdee_yrp.work_order_billing.frappe.db.get_single_value",
				return_value="2026-01-01",
			),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=None),
			patch(
				"essdee_yrp.work_order_billing.frappe.get_meta",
				side_effect=get_meta,
			),
			patch("essdee_yrp.work_order_billing.frappe.get_list", side_effect=get_list) as fallback_lookup,
			patch("essdee_yrp.work_order_billing.get_or_create_variant", return_value="BILLING"),
			patch("essdee_yrp.work_order_billing.resolve_item_uom", return_value=frappe._dict(uom="Nos")),
			patch("essdee_yrp.work_order_billing._get_item_group", return_value="Services"),
			patch("essdee_yrp.work_order_billing._get_tax_rate", return_value=0),
		):
			payload = build_work_order_invoice_payload([row.name for row in grns], supplier="SUP-1")

		self.assertEqual(payload["pre_tax_total"], 28)
		self.assertEqual(payload["commercial_items"][0]["source_rate"], 7)
		self.assertEqual(fallback_lookup.call_count, 2)

	def test_non_received_json_uses_grn_quantity_without_tracking(self):
		payload = self._build(self._fixture())

		self.assertEqual(payload["total_quantity"], 2)
		self.assertEqual(payload["pre_tax_total"], 10)
		self.assertEqual(payload["warnings"], [])
		self.assertEqual(payload["wo_items"][0]["quantity"], 2)

	def test_grn_quantity_that_exceeds_invoice_precision_raises(self):
		fixture = self._fixture(grn_items=[self._grn_item(quantity=1 / 3)])

		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"Goods Received Note GRN-1 row 1.*YRP Purchase Invoice Item.qty.*precision 3",
		):
			self._build(fixture)

	def test_computed_quantity_that_exceeds_invoice_precision_raises(self):
		fixture = self._fixture(
			received_json=True,
			grn_items=[self._grn_item("PANEL-A", 1)],
		)

		with self.assertRaisesRegex(
			frappe.ValidationError,
			r"GRN-1.*calculated row 1.*SD YRP Essdee Purchase Invoice Item.qty.*precision 3",
		):
			self._build(
				fixture,
				piece_quantities={("GARMENT-S", '{"major_colour":"Navy"}'): 1 / 3},
			)

	def test_stored_precision_quantities_reconcile_after_reload_rebuild(self):
		fixture = self._fixture(
			grn_items=[
				self._grn_item(quantity=1, idx=1),
				self._grn_item(quantity=0.333, idx=2),
			]
		)

		def simulate_persist(payload):
			persisted = copy.deepcopy(payload)
			for rows, doctype, fieldname in (
				(persisted["items"], "YRP Purchase Invoice Item", "qty"),
				(persisted["commercial_items"], "SD YRP Essdee Purchase Invoice Item", "qty"),
				(persisted["wo_items"], "YRP PI Work Order Billed Detail", "quantity"),
			):
				precision = get_field_precision(frappe.get_meta(doctype).get_field(fieldname))
				for row in rows:
					row[fieldname] = flt(row[fieldname], precision)
			for row in persisted["items"] + persisted["commercial_items"]:
				row["amount"] = row["qty"] * row["rate"]
			return persisted

		initial = simulate_persist(self._build(fixture))
		reloaded = simulate_persist(
			self._build(
				fixture,
				final_rates={
					row["group_key"]: row["rate"] for row in initial["commercial_items"]
				},
			)
		)

		for payload in (initial, reloaded):
			commercial_value = sum(row["amount"] for row in payload["commercial_items"])
			physical_value = sum(row["amount"] for row in payload["items"])
			self.assertEqual(commercial_value, physical_value)
			self.assertEqual(payload["commercial_items"][0]["qty"], 1.333)
			self.assertEqual(payload["wo_items"][0]["quantity"], 1.333)

	def test_received_json_uses_selected_grns_piece_calculation(self):
		fixture = self._fixture(
			received_json=True,
			grn_items=[self._grn_item("PANEL-A", 4)],
		)
		second_grn = frappe._dict(
			name="GRN-2",
			against_id="WO-1",
			posting_date="2026-04-03",
			process_name="Sewing",
			items=[self._grn_item("PANEL-B", 6)],
		)

		payload = self._build(
			fixture,
			extra_grns=[second_grn],
			piece_quantities={("GARMENT-S", '{"major_colour":"Navy"}'): 5},
		)

		self.assertEqual(payload["total_quantity"], 5)
		self.assertEqual(payload["pre_tax_total"], 25)
		self.assertEqual(sum(row["qty"] * row["rate"] for row in payload["items"]), 25)
		self.assertEqual(payload["warnings"], [])

	def test_selected_grns_complete_panels_that_neither_completes_alone(self):
		work_order = frappe._dict(
			name="WO-1",
			production_detail="IPD-1",
			work_order_calculated_items=[self._calculated()],
			work_order_track_pieces=[],
		)
		ipd = frappe._dict(
			name="IPD-1",
			is_set_item=0,
			primary_item_attribute="Size",
			stiching_attribute="Panel",
			stiching_in_stage="Input",
			cutting_process="Cutting",
			stiching_process="Stitching",
			packing_process="Packing",
			emblishment_details_json={},
			ipd_processes=[frappe._dict(process_name="Sewing", in_stage="Input")],
			stiching_item_details=[
				frappe._dict(stiching_attribute_value="Front", quantity=1),
				frappe._dict(stiching_attribute_value="Back", quantity=1),
			],
		)
		front = frappe._dict(
			name="GRN-FRONT",
			process_name="Sewing",
			items=[self._grn_item("PANEL-FRONT-S", 3)],
		)
		back = frappe._dict(
			name="GRN-BACK",
			process_name="Sewing",
			items=[self._grn_item("PANEL-BACK-S", 3)],
		)
		complete = {
			"items": [
				{
					"name": "GARMENT",
					"attributes": {},
					"item_keys": {"major_colour": "Navy"},
					"primary_attribute": "Size",
					"values": {"S": {}},
				}
			]
		}
		incomplete = {
			"items": [
				{
					"name": "GARMENT",
					"attributes": {},
					"item_keys": {"major_colour": "Navy"},
					"values": {"S": {"Front": {}, "Back": {}}},
				}
			]
		}
		attributes = {
			"GARMENT-S": {"Size": "S"},
			"PANEL-FRONT-S": {"Size": "S", "Panel": "Front"},
			"PANEL-BACK-S": {"Size": "S", "Panel": "Back"},
		}

		def cached_doc(doctype, _name):
			if doctype == "YRP Item Production Detail":
				return ipd
			return frappe._dict(is_group=0)

		with (
			patch(
				"essdee_yrp.work_order_piece_tracking.PieceState._initial_panel_structures",
				side_effect=lambda: (copy.deepcopy(complete), copy.deepcopy(incomplete)),
			),
			patch("essdee_yrp.work_order_piece_tracking.frappe.get_cached_doc", side_effect=cached_doc),
			patch(
				"essdee_yrp.work_order_piece_tracking.get_variant_attr_details",
				side_effect=lambda item: attributes[item],
			),
			patch("essdee_yrp.work_order_piece_tracking.get_parent_item", return_value="GARMENT"),
			patch("essdee_yrp.work_order_piece_tracking.get_or_create_variant", return_value="GARMENT-S"),
		):
			front_only = get_selected_grn_piece_quantities(work_order, [front])
			back_only = get_selected_grn_piece_quantities(work_order, [back])
			combined = get_selected_grn_piece_quantities(work_order, [front, back])

		key = ("GARMENT-S", '{"major_colour":"Navy"}')
		self.assertEqual(front_only[key], 0)
		self.assertEqual(back_only[key], 0)
		self.assertEqual(combined[key], 3)

	def test_unmatched_grn_row_is_warned_and_not_billed(self):
		fixture = self._fixture(
			grn_items=[
				self._grn_item(),
				self._grn_item("UNPLANNED", 4, idx=2),
			]
		)

		payload = self._build(fixture)

		self.assertEqual(payload["total_quantity"], 2)
		self.assertEqual(payload["pre_tax_total"], 10)
		self.assertEqual(len(payload["warnings"]), 1)
		self.assertIn("GRN GRN-1 row 2 item UNPLANNED", payload["warnings"][0]["reason"])
		unmatched = next(row for row in payload["items"] if row["item"] == "UNPLANNED")
		self.assertEqual((unmatched["rate"], unmatched["source_rate"]), (0, 3))

	def test_received_json_incomplete_panel_set_bills_zero_without_warning(self):
		payload = self._build(
			self._fixture(
				received_json=True,
				grn_items=[self._grn_item("PANEL-A", 4)],
			),
			piece_quantities={("GARMENT-S", '{"major_colour":"Navy"}'): 0},
		)

		self.assertEqual(payload["total_quantity"], 0)
		self.assertEqual(payload["pre_tax_total"], 0)
		self.assertEqual(payload["warnings"], [])

	def test_missing_process_cost_bills_quantity_at_zero_without_warning(self):
		payload = self._build(self._fixture(process_cost=False))

		self.assertEqual(payload["total_quantity"], 2)
		self.assertEqual(payload["pre_tax_total"], 0)
		self.assertEqual(payload["warnings"], [])
		self.assertEqual(
			(payload["commercial_items"][0]["rate"], payload["commercial_items"][0]["source_rate"]),
			(0, 0),
		)

	def test_tax_requires_supplier_gstin(self):
		without_gstin = self._build(self._fixture(gstin=None))
		with_gstin = self._build(self._fixture(gstin="29ABCDE1234F1Z5"))

		self.assertIsNone(without_gstin["commercial_items"][0]["tax"])
		self.assertEqual(with_gstin["commercial_items"][0]["tax"], "GST-5")

	def test_edited_final_rate_reconciles_physical_value(self):
		group_key = commercial_group_key("BILLING", "LOT-1", "Nos", 5, None)
		payload = self._build(self._fixture(), final_rates={group_key: 7})

		self.assertEqual(payload["commercial_items"][0]["rate"], 7)
		self.assertEqual(payload["pre_tax_total"], 14)
		self.assertEqual(sum(row["amount"] for row in payload["items"]), 14)

	def test_panel_tiers_keep_group_rates_through_rate_edit_and_rebuild(self):
		calculated = [
			self._calculated("GARMENT-S"),
			self._calculated("GARMENT-L"),
		]
		grn_items = [
			self._grn_item("PANEL-S", 4, idx=1),
			self._grn_item("PANEL-L", 8, idx=2),
		]
		fixture = self._fixture(
			received_json=True,
			grn_items=grn_items,
			calculated=calculated,
		)
		fixture[4].depends_on_attribute = 1
		fixture[4].attribute = "Size"
		fixture[4].process_cost_values = [
			frappe._dict(min_order_qty=0, price=5, attribute_value="S"),
			frappe._dict(min_order_qty=0, price=7, attribute_value="L"),
		]
		piece_quantities = {
			("GARMENT-S", '{"major_colour":"Navy"}'): 2,
			("GARMENT-L", '{"major_colour":"Navy"}'): 4,
		}
		attributes = {
			"GARMENT-S": {"Size": "S"},
			"GARMENT-L": {"Size": "L"},
			"PANEL-S": {"Size": "S", "Panel": "Front"},
			"PANEL-L": {"Size": "L", "Panel": "Front"},
		}
		initial = self._build(
			fixture,
			piece_quantities=piece_quantities,
			variant_attributes=attributes,
		)
		groups = {row["source_rate"]: row["group_key"] for row in initial["commercial_items"]}
		edited_rates = {groups[5]: 6, groups[7]: 10}
		edited = self._build(
			fixture,
			final_rates=edited_rates,
			piece_quantities=piece_quantities,
			variant_attributes=attributes,
		)
		saved = self._build(
			fixture,
			final_rates={row["group_key"]: row["rate"] for row in edited["commercial_items"]},
			piece_quantities=piece_quantities,
			variant_attributes=attributes,
		)

		physical = {row["item"]: row for row in edited["items"]}
		self.assertEqual((physical["PANEL-S"]["essdee_group_key"], physical["PANEL-S"]["rate"]), (groups[5], 3))
		self.assertEqual((physical["PANEL-L"]["essdee_group_key"], physical["PANEL-L"]["rate"]), (groups[7], 5))
		self.assertEqual(edited["pre_tax_total"], 52)
		self.assertEqual(
			[
				(row["item"], row["essdee_group_key"], row["rate"], row["source_rate"])
				for row in saved["items"]
			],
			[
				(row["item"], row["essdee_group_key"], row["rate"], row["source_rate"])
				for row in edited["items"]
			],
		)

	def test_physical_source_rate_runs_real_submit_allocator(self):
		from yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment import (
			create_purchase_invoice_adjustment,
		)

		fixture = self._fixture()
		work_order, grn = fixture[:2]
		work_order.receivables[0].cost = 0
		work_order.doctype = "YRP Work Order"
		grn.doctype = "YRP Goods Received Note"
		grn.against = "YRP Work Order"
		payload = self._build(
			fixture,
			final_rates={commercial_group_key("BILLING", "LOT-1", "Nos", 5, None): 7},
		)
		invoice_item = frappe._dict(payload["items"][0])
		invoice_item.name = "PI-ITEM-1"
		invoice_item.idx = 1
		invoice = frappe._dict(
			doctype="YRP Purchase Invoice",
			name="PI-1",
			posting_date="2026-04-03",
			grn=[frappe._dict(grn=grn.name)],
			items=[invoice_item],
		)

		def get_doc(doctype, name):
			return {
				("YRP Goods Received Note", grn.name): grn,
				("YRP Work Order", work_order.name): work_order,
			}[(doctype, name)]

		module = "yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment"
		with (
			patch(f"{module}.frappe.get_doc", side_effect=get_doc),
			patch(f"{module}.find_receipt_sle", return_value="SLE-1"),
			patch(f"{module}._get_sle", return_value=frappe._dict()),
			patch(f"{module}.get_dimension_fieldnames", return_value=[]),
			patch(f"{module}.create_adjustment", return_value="SVA-1") as create_adjustment,
		):
			self.assertEqual(create_purchase_invoice_adjustment(invoice), "SVA-1")

		allocation = create_adjustment.call_args.kwargs["allocations"][0]
		self.assertEqual((invoice_item.source_rate, allocation["old_rate"]), (0, 0))
		self.assertEqual((allocation["source_grn_item"], allocation["new_rate"]), ("GRN-ITEM-1", 7))

	def test_interleaved_work_orders_allocate_rates_to_their_own_grn_rows(self):
		from essdee_yrp.work_order_billing import create_work_order_purchase_invoice_adjustment

		process = frappe._dict(name="Sewing", item="BILLING", is_group=0, process_details=[])
		ipd = frappe._dict(
			name="IPD-1",
			is_set_item=0,
			primary_item_attribute="Size",
			cutting_process="Cutting",
			stiching_in_stage="Input",
			stiching_attribute="Panel",
			ipd_processes=[],
			stiching_item_details=[],
		)
		documents = {("YRP Process", process.name): process}
		work_orders = {}
		for label, rate in (("A", 5), ("B", 7)):
			work_order = frappe._dict(
				doctype="YRP Work Order",
				name=f"WO-{label}",
				process_name="Sewing",
				process_cost=f"PC-{label}",
				production_detail="IPD-1",
				item="PHYSICAL",
				lot="LOT-1",
				wo_date="2026-04-01",
				is_rework=0,
				supplier="SUP-1",
				work_order_calculated_items=[self._calculated("PHYSICAL")],
				work_order_track_pieces=[],
				receivables=[
					frappe._dict(
						item_variant="PHYSICAL",
						set_combination={"major_colour": "Navy"},
						cost=0,
					)
				],
			)
			process_cost = frappe._dict(
				name=f"PC-{label}",
				tax_slab=None,
				depends_on_attribute=0,
				attribute=None,
				process_cost_values=[frappe._dict(min_order_qty=0, price=rate)],
			)
			work_orders[label] = work_order
			documents[("YRP Work Order", work_order.name)] = work_order
			documents[("YRP Process Cost", process_cost.name)] = process_cost

		grns = []
		for name, label in (("A1", "A"), ("B1", "B"), ("A2", "A")):
			item = self._grn_item("PHYSICAL", 2)
			item.name = f"{name}-ROW"
			item.rate = 0
			item.amount = 0
			grn = frappe._dict(
				doctype="YRP Goods Received Note",
				name=f"GRN-{name}",
				against="YRP Work Order",
				against_id=work_orders[label].name,
				posting_date="2026-04-02",
				items=[item],
			)
			grns.append(grn)
			documents[("YRP Goods Received Note", grn.name)] = grn

		def get_doc(doctype, name):
			return documents[(doctype, name)]

		with (
			patch("essdee_yrp.work_order_billing._validate_selected_grn"),
			patch(
				"essdee_yrp.work_order_billing._quantity_precisions",
				return_value={"physical": 3, "commercial": 3, "billed": 3},
			),
			patch("essdee_yrp.work_order_billing.frappe.get_doc", side_effect=get_doc),
			patch("essdee_yrp.work_order_billing.frappe.get_cached_doc", return_value=ipd),
			patch(
				"essdee_yrp.work_order_billing.frappe.db.get_single_value",
				return_value="2026-01-01",
			),
			patch("essdee_yrp.work_order_billing.frappe.db.get_value", return_value=None),
			patch("essdee_yrp.work_order_billing.get_or_create_variant", return_value="BILLING"),
			patch("essdee_yrp.work_order_billing.resolve_item_uom", return_value=frappe._dict(uom="Nos")),
			patch("essdee_yrp.work_order_billing._get_item_group", return_value="Services"),
			patch("essdee_yrp.work_order_billing._get_tax_rate", return_value=0),
		):
			payload = build_work_order_invoice_payload(
				[row.name for row in grns],
				supplier="SUP-1",
			)
		self.assertEqual(
			[(row["qty"], row["rate"]) for row in payload["items"]],
			[(2, 5), (2, 5), (2, 7)],
		)

		invoice_items = []
		for index, row in enumerate(payload["items"], start=1):
			item = frappe._dict(row)
			item.name = f"PI-ITEM-{index}"
			item.idx = index
			invoice_items.append(item)
		invoice = frappe._dict(
			doctype="YRP Purchase Invoice",
			name="PI-INTERLEAVED",
			posting_date="2026-04-03",
			grn=[frappe._dict(grn=row.name) for row in grns],
			items=invoice_items,
			pi_work_order_billed_details=[frappe._dict(row) for row in payload["wo_items"]],
		)

		module = "yrp.yrp_stock.doctype.yrp_stock_valuation_adjustment.yrp_stock_valuation_adjustment"
		with (
			patch(f"{module}.frappe.get_doc", side_effect=get_doc),
			patch(
				f"{module}.find_receipt_sle",
				side_effect=lambda _doctype, _grn, item: f"SLE-{item}",
			),
			patch(f"{module}._get_sle", return_value=frappe._dict()),
			patch(f"{module}.get_dimension_fieldnames", return_value=[]),
			patch(f"{module}.create_adjustment", return_value="SVA-1") as create_adjustment,
		):
			self.assertEqual(create_work_order_purchase_invoice_adjustment(invoice), "SVA-1")

		allocations = create_adjustment.call_args.kwargs["allocations"]
		self.assertEqual(
			{row["source_grn_item"]: row["new_rate"] for row in allocations},
			{"A1-ROW": 5, "A2-ROW": 5, "B1-ROW": 7},
		)

	def test_zero_quantity_calculated_items_remain_in_billed_rows(self):
		fixture = self._fixture(
			calculated=[
				self._calculated("GARMENT-S", 10),
				self._calculated("GARMENT-L", 0),
			]
		)

		payload = self._build(fixture)

		self.assertEqual(
			[(row["item_variant"], row["quantity"]) for row in payload["wo_items"]],
			[("GARMENT-S", 2), ("GARMENT-L", 0)],
		)

	def test_zero_quantity_tier_group_is_not_a_commercial_line(self):
		fixture = self._fixture(
			calculated=[
				self._calculated("GARMENT-S", 10),
				self._calculated("GARMENT-L", 0),
			]
		)
		fixture[4].process_cost_values = [
			frappe._dict(min_order_qty=0, price=6),
			frappe._dict(min_order_qty=1, price=7.5),
		]

		payload = self._build(fixture)

		self.assertTrue(payload["commercial_items"])
		self.assertTrue(all(flt(row["qty"]) for row in payload["commercial_items"]))
		self.assertEqual(
			[(row["item_variant"], row["quantity"]) for row in payload["wo_items"]],
			[("GARMENT-S", 2), ("GARMENT-L", 0)],
		)


class LegacyInvoiceZeroRowsTest(unittest.TestCase):
	def test_zero_row_with_any_nonzero_receipt_is_not_ignored(self):
		receivable = frappe._dict(name="R0", item_variant="SIZE-S", qty=0)
		self.assertTrue(_inactive_zero_receivable(receivable, []))
		for quantity in (1, -1):
			for item in (
				dict(ref_docname="R0", item_variant="OTHER"),
				dict(item_variant="SIZE-S"),
			):
				grn = frappe._dict(items=[frappe._dict(quantity=quantity, **item)])
				self.assertFalse(_inactive_zero_receivable(receivable, [grn]))
		receivable.qty = 1
		self.assertFalse(_inactive_zero_receivable(receivable, []))

	def test_legacy_context_omits_only_inactive_allocation_rows(self):
		zero = frappe._dict(name="R0", item_variant="SIZE-S", qty=0, cost=5)
		active = frappe._dict(name="R1", item_variant="SIZE-L", qty=10, cost=5)
		work_order = frappe._dict(
			name="WO-1",
			process_name="Sewing",
			production_detail=None,
			process_cost=None,
			lot="LOT-1",
			receivables=[zero, active],
			work_order_calculated_items=[
				frappe._dict(item_variant="SIZE-S", quantity=0),
				frappe._dict(item_variant="SIZE-L", quantity=10),
			],
			work_order_track_pieces=[
				frappe._dict(
					against="Goods Received Note",
					against_id="G1",
					item_variant="SIZE-S",
					received_qty=0,
				),
				frappe._dict(
					against="Goods Received Note",
					against_id="G1",
					item_variant="SIZE-L",
					received_qty=1,
				),
			],
		)
		grn = frappe._dict(
			name="G1",
			lot="LOT-1",
			items=[
				frappe._dict(item_variant="SIZE-S", quantity=0),
				frappe._dict(
					item_variant="SIZE-L",
					quantity=1,
					ref_docname="R1",
					ref_doctype="YRP Work Order Receivables",
				),
			],
		)
		with (
			patch("essdee_yrp.purchase_invoice.frappe.db.get_value", return_value="Billing"),
			patch("essdee_yrp.purchase_invoice.get_or_create_variant", return_value="Billing"),
			patch("essdee_yrp.purchase_invoice.resolve_item_uom", return_value=frappe._dict(uom="Nos")),
			patch("essdee_yrp.purchase_invoice.get_variant_attributes", return_value={}),
		):
			context = _build_work_order_context(
				work_order,
				[grn],
				allow_missing_process_cost=True,
				allow_legacy_references=True,
			)
		self.assertEqual(set(context["receivables_by_name"]), {"R1"})
		self.assertEqual(context["demands"][0]["selected_qty"], 1)
		_validate_selected_physical_quantities(context, [grn])
		self.assertEqual(len(work_order.receivables), 2)

	def test_legacy_payload_rate_edit_reconciles_physical_value(self):
		commercial = _Row(
			idx=1,
			item="BILLING",
			lot="LOT-1",
			item_group="Services",
			qty=2,
			uom="Nos",
			source_rate=5,
			rate=7,
			tax=None,
			group_key="GROUP-1",
		)
		detail = _Row(
			work_order="WO-1",
			item_variant="GARMENT-S",
			quantity=2,
			set_combination={"major_colour": "Navy"},
		)
		invoice = frappe._dict(
			name="PI-LEGACY",
			supplier="SUP-1",
			grand_total=14,
			total=14,
			total_tax=0,
			grn=[frappe._dict(grn="GRN-1")],
			essdee_items=[commercial],
			pi_work_order_billed_details=[detail],
		)
		work_order = frappe._dict(
			name="WO-1",
			process_name="Sewing",
			lot="LOT-1",
			receivables=[
				frappe._dict(
					name="RECEIVABLE-1",
					item_variant="GARMENT-S",
					set_combination={"major_colour": "Navy"},
					cost=5,
				)
			],
		)
		grn = frappe._dict(
			name="GRN-1",
			against_id="WO-1",
			lot="LOT-1",
			items=[
				frappe._dict(
					idx=1,
					item_variant="GARMENT-S",
					quantity=2,
					stock_qty=2,
					uom="Nos",
					rate=3,
					ref_doctype="YRP Work Order Receivables",
					ref_docname="RECEIVABLE-1",
					set_combination={"major_colour": "Navy"},
				)
			],
		)
		with (
			patch("essdee_yrp.purchase_invoice._load_historical_work_order_grn", return_value=grn),
			patch("essdee_yrp.purchase_invoice.frappe.get_doc", return_value=work_order),
			patch("essdee_yrp.purchase_invoice.frappe.db.get_value", return_value="BILLING"),
			patch("essdee_yrp.purchase_invoice.frappe.db.exists", return_value=True),
			patch("essdee_yrp.purchase_invoice.resolve_item_uom", return_value=frappe._dict(uom="Nos")),
			patch("essdee_yrp.purchase_invoice._get_item_group", return_value="Services"),
			patch("essdee_yrp.purchase_invoice._get_tax_rate", return_value=0),
		):
			initial = build_legacy_work_order_invoice_payload(invoice)
			commercial.rate = 9
			edited = build_legacy_work_order_invoice_payload(invoice)

		self.assertEqual((initial["items"][0]["source_rate"], initial["items"][0]["rate"]), (5, 7))
		self.assertEqual((edited["items"][0]["source_rate"], edited["items"][0]["rate"]), (5, 9))
		self.assertEqual(edited["pre_tax_total"], 18)
		self.assertEqual(
			edited["pre_tax_total"],
			sum(row["qty"] * row["rate"] for row in edited["commercial_items"]),
		)
