from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.test_cloth_program import _ensure_item
from essdee_yrp.api.work_order import _merge_source_context, _resolve_variant
from essdee_yrp.fabric_source import (
	_knitting_factor_targets,
	_project_receipt_buckets,
	_source_breakdown,
	consume_source_bucket,
	fill_from_source_grns,
	get_source_availability,
	get_source_process_options,
	project_output_attributes,
	validate_source_demands,
)


def _row(colour, target):
	return {
		"key": target,
		"input_specs": [{
			"item": "Test Cloth",
			"attrs": {"Dia": "32 Dia", "Colour": colour},
			"qty": 1,
		}],
		"output_qty": 1,
		"out_attrs": {"Dia": "32 Dia", "Colour": target},
	}


class TestFabricSourceProcesses(TestCase):
	@patch("essdee_yrp.fabric_source.get_fabric_steps")
	def test_earlier_steps_are_offered_immediate_first(self, get_steps):
		get_steps.return_value = [
			{"position": 0, "process_name": "Knitting"},
			{"position": 1, "process_name": "White Wash"},
			{"position": 2, "process_name": "Dyeing"},
			{"position": 3, "process_name": "Washing"},
		]
		options = get_source_process_options(
			frappe._dict(name="Test IPD"), "Washing"
		)
		self.assertEqual(
			[option["process_name"] for option in options],
			["Dyeing", "White Wash", "Knitting"],
		)


class TestFabricSourceFill(TestCase):
	def test_factor_targets_prefill_each_colour_and_actual_dia_once(self):
		rows = [
			{
				"key": "BLACK", "output_item": "Test Cloth", "output_qty": 1,
				"reference_item_variant": "FINAL-BLACK",
				"input_specs": [{
					"item": "Test Cloth", "attrs": {"Dia": "18 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
				"out_attrs": {"Dia": "18 Dia", "Colour": "Black"},
			},
			{
				"key": "NAVY", "output_item": "Test Cloth", "output_qty": 1,
				"reference_item_variant": "FINAL-NAVY",
				"input_specs": [{
					"item": "Test Cloth", "attrs": {"Dia": "18 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
				"out_attrs": {"Dia": "18 Dia", "Colour": "Navy"},
			},
		]
		buckets = [
			{
				"key": "GRNI-22::-", "item_variant": "CLOTH-22-GREIGE",
				"available_stock_qty": 60, "received_stock_qty": 60,
				"source_grn": "GRN-1", "source_grn_item": "GRNI-22",
			},
			{
				"key": "GRNI-24::-", "item_variant": "CLOTH-24-GREIGE",
				"available_stock_qty": 30, "received_stock_qty": 30,
				"source_grn": "GRN-1", "source_grn_item": "GRNI-24",
			},
		]
		variant_info = {
			"CLOTH-22-GREIGE": {
				"item": "Test Cloth", "attrs": {"Dia": "22 Dia", "Colour": "Greige"},
			},
			"CLOTH-24-GREIGE": {
				"item": "Test Cloth", "attrs": {"Dia": "24 Dia", "Colour": "Greige"},
			},
		}
		targets = {
			("BLACK", "CLOTH-22-GREIGE"): 24,
			("BLACK", "CLOTH-24-GREIGE"): 12,
			("NAVY", "CLOTH-22-GREIGE"): 36,
			("NAVY", "CLOTH-24-GREIGE"): 18,
		}

		def resolve(_item, attrs):
			return f"{attrs.get('Dia')}-{attrs.get('Colour')}"

		def attrs(variant):
			dia, colour = variant.split("-", 1)
			return {"Dia": dia, "Colour": colour}

		with (
			patch("essdee_yrp.api.work_order._resolve_variant", side_effect=resolve),
			patch("essdee_yrp.api.work_order._variant_attrs", side_effect=attrs),
			patch("essdee_yrp.fabric_source._conversion_factor", return_value=1),
		):
			unmatched = _project_receipt_buckets(
				rows, buckets, variant_info, route_targets=targets
			)

		self.assertEqual(unmatched, [])
		self.assertTrue(all(row["source_stock_available"] > 0 for row in rows))
		self.assertTrue(all(row["source_stock_per_output"] > 0 for row in rows))
		self.assertEqual(
			{
				(row["matrix_key"], row["source_item_variant"]): row["prefill"]
				for row in rows
			},
			{
				("BLACK", "CLOTH-22-GREIGE"): 24,
				("BLACK", "CLOTH-24-GREIGE"): 12,
				("NAVY", "CLOTH-22-GREIGE"): 36,
				("NAVY", "CLOTH-24-GREIGE"): 18,
			},
		)

	def test_factor_targets_do_not_reuse_one_exact_grn_row_across_routes(self):
		rows = [
			{
				"key": "NAVY", "output_item": "Test Cloth", "output_qty": 1,
				"input_specs": [{
					"item": "Test Cloth",
					"attrs": {"Dia": "26 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
				"out_attrs": {"Dia": "26 Dia", "Colour": "Navy"},
			},
			{
				"key": "GREY", "output_item": "Test Cloth", "output_qty": 1,
				"input_specs": [{
					"item": "Test Cloth",
					"attrs": {"Dia": "26 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
				"out_attrs": {"Dia": "26 Dia", "Colour": "Grey"},
			},
		]
		buckets = [
			{
				"key": "GRNI-1::-", "item_variant": "CLOTH-30-GREIGE",
				"available_stock_qty": 10, "received_stock_qty": 10,
				"source_grn": "GRN-1", "source_grn_item": "GRNI-1",
			},
			{
				"key": "GRNI-2::-", "item_variant": "CLOTH-30-GREIGE",
				"available_stock_qty": 20, "received_stock_qty": 20,
				"source_grn": "GRN-2", "source_grn_item": "GRNI-2",
			},
		]
		variant_info = {
			"CLOTH-30-GREIGE": {
				"item": "Test Cloth",
				"attrs": {"Dia": "30 Dia", "Colour": "Greige"},
			},
		}
		targets = {
			("NAVY", "CLOTH-30-GREIGE"): 18,
			("GREY", "CLOTH-30-GREIGE"): 12,
		}

		def resolve(_item, attrs):
			return f"{attrs.get('Dia')}-{attrs.get('Colour')}"

		def attrs(variant):
			dia, colour = variant.split("-", 1)
			return {"Dia": dia, "Colour": colour}

		with (
			patch("essdee_yrp.api.work_order._resolve_variant", side_effect=resolve),
			patch("essdee_yrp.api.work_order._variant_attrs", side_effect=attrs),
			patch("essdee_yrp.fabric_source._conversion_factor", return_value=1),
		):
			unmatched = _project_receipt_buckets(
				rows, buckets, variant_info, route_targets=targets
			)

		self.assertEqual(unmatched, [])
		self.assertEqual(len(rows), 3)
		source_totals = {}
		route_totals = {}
		for row in rows:
			source_totals[row["source_grn_item"]] = (
				source_totals.get(row["source_grn_item"], 0) + row["prefill"]
			)
			route_totals[row["matrix_key"]] = (
				route_totals.get(row["matrix_key"], 0) + row["prefill"]
			)
		self.assertEqual(source_totals, {"GRNI-1": 10, "GRNI-2": 20})
		self.assertEqual(route_totals, {"NAVY": 18, "GREY": 12})

	def test_knitting_factors_apply_to_each_colour_routes_own_weight(self):
		rows = [
			{
				"key": "BLACK-ROUTE",
				"plan": 40,
				"input_specs": [{
					"item": "Test Cloth", "attrs": {"Dia": "18 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
			},
			{
				"key": "NAVY-ROUTE",
				"plan": 60,
				"input_specs": [{
					"item": "Test Cloth", "attrs": {"Dia": "18 Dia", "Colour": "Greige"},
					"qty": 1,
				}],
			},
		]
		with (
			patch(
				"essdee_yrp.api.work_order._resolve_variant",
				return_value="CLOTH-18-GREIGE",
			),
			patch(
				"essdee_yrp.fabric_substitution.get_actual_dia_factors",
				return_value=[
					{"item_variant": "CLOTH-22-GREIGE", "factor": 0.6},
					{"item_variant": "CLOTH-24-GREIGE", "factor": 0.3},
				],
			),
		):
			targets = _knitting_factor_targets(
				rows, "LOT-1", frappe._dict(name="IPD-1", item="Test Cloth")
			)

		self.assertEqual(targets, {
			("BLACK-ROUTE", "CLOTH-22-GREIGE"): 24,
			("BLACK-ROUTE", "CLOTH-24-GREIGE"): 12,
			("NAVY-ROUTE", "CLOTH-22-GREIGE"): 36,
			("NAVY-ROUTE", "CLOTH-24-GREIGE"): 18,
		})

	def test_exact_source_bucket_caps_one_plan_without_reserving_for_other_plans(self):
		def pool():
			return {"buckets": {"GRNI-1::-": {
				"item_variant": "Greige-32",
				"source_grn": "GRN-1",
				"remaining_stock_qty": 0.001,
			}}}

		available = pool()
		consume_source_bucket(available, "GRNI-1::-", 0.001)
		self.assertEqual(
			available["buckets"]["GRNI-1::-"]["remaining_stock_qty"],
			0,
		)

		overplanned = pool()
		with self.assertRaisesRegex(
			frappe.ValidationError, "exact source GRN row.*only 0.001"
		):
			consume_source_bucket(overplanned, "GRNI-1::-", 0.002)

	@patch("essdee_yrp.fabric_source._lock_source_transactions")
	@patch("essdee_yrp.fabric_source._rows_in_stock_uom")
	@patch("essdee_yrp.fabric_source.get_source_availability")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_source_demand_resolves_identity_without_stock_validation(
		self, resolve, availability, stock_rows, _lock,
	):
		resolve.return_value = {
			"value": "0::Knitting",
			"process_name": "Knitting",
		}
		availability.return_value = {
			"received": {"Greige-32": 0.001},
			"reserved": {"Greige-32": 0},
			"net": {"Greige-32": 0.001},
		}
		stock_rows.return_value = {"Greige-32": 0.001}
		kwargs = {
			"lot": "LOT-1",
			"ipd": frappe._dict(name="IPD-1"),
			"cloth_item": "Test Cloth",
			"current_process": "Dyeing",
			"current_work_order": "WO-2",
			"source_process": "0::Knitting",
		}

		selected = validate_source_demands(
			[{"item_variant": "Greige-32", "qty": 0.001, "uom": "Kg"}],
			**kwargs,
		)
		self.assertEqual(selected["process_name"], "Knitting")
		availability.assert_not_called()
		stock_rows.assert_not_called()
		_lock.assert_not_called()

	def test_source_breakdown_hides_fully_exhausted_historical_rows(self):
		buckets = [
			{
				"key": "OLD-GRN-ITEM::-",
				"source_grn": "OLD-GRN",
				"received_stock_qty": 5,
				"reserved_stock_qty": 5,
				"available_stock_qty": 0,
			},
			{
				"key": "MIN-PRECISION-GRN-ITEM::-",
				"source_grn": "MIN-PRECISION-GRN",
				"received_stock_qty": 0.001,
				"reserved_stock_qty": 0,
				"available_stock_qty": 0.001,
			},
			{
				"key": "ACTIVE-GRN-ITEM::-",
				"source_grn": "ACTIVE-GRN",
				"received_stock_qty": 9,
				"reserved_stock_qty": 4,
				"available_stock_qty": 5,
			},
		]

		self.assertEqual(
			[row["key"] for row in _source_breakdown(buckets)],
			["MIN-PRECISION-GRN-ITEM::-", "ACTIVE-GRN-ITEM::-"],
		)

	def test_compatible_multi_fabric_source_summaries_are_combined(self):
		merged = _merge_source_context(
			{
				"value": "0::Knitting",
				"process_name": "Knitting",
				"received": 10,
				"reserved": 2,
				"available": 8,
				"sources": [{"key": "GRNI-1::-"}],
				"unmatched": ["Variant A"],
			},
			{
				"value": "0::Knitting",
				"process_name": "Knitting",
				"received": 20,
				"reserved": 5,
				"available": 15,
				"sources": [{"key": "GRNI-2::-"}],
				"unmatched": ["Variant A", "Variant B"],
			},
		)

		self.assertEqual(merged["received"], 30)
		self.assertEqual(merged["reserved"], 7)
		self.assertEqual(merged["available"], 23)
		self.assertEqual(
			[source["key"] for source in merged["sources"]],
			["GRNI-1::-", "GRNI-2::-"],
		)
		self.assertEqual(merged["unmatched"], ["Variant A", "Variant B"])

	def test_incompatible_multi_fabric_source_steps_are_rejected(self):
		with self.assertRaisesRegex(
			frappe.ValidationError, "different source-process steps"
		):
			_merge_source_context(
				{"value": "0::Knitting"},
				{"value": "1::Knitting"},
			)

	def test_multi_fabric_merge_is_unavailable_when_either_fabric_has_no_stock(self):
		available = {
			"value": "0::Knitting",
			"received": 10,
			"reserved": 2,
			"available": 8,
			"sources": [{"key": "GRNI-1::-"}],
		}
		unavailable = {
			"value": "0::Knitting",
			"received": 0,
			"reserved": 0,
			"available": 0,
			"unavailable": True,
			"sources": [],
		}

		for first, second in (
			(available, unavailable),
			(unavailable, available),
		):
			with self.subTest(first_unavailable=bool(first.get("unavailable"))):
				merged = _merge_source_context(first, second)
				self.assertTrue(merged["unavailable"])
				self.assertEqual(merged["available"], 8)

	def test_actual_dia_is_carried_until_a_matrix_explicitly_changes_it(self):
		self.assertEqual(
			project_output_attributes(
				{"Dia": "22 Dia", "Colour": "Greige"},
				{"Dia": "18 Dia", "Colour": "Greige"},
				{"Dia": "18 Dia", "Colour": "Red"},
			),
			{"Dia": "22 Dia", "Colour": "Red"},
		)
		self.assertEqual(
			project_output_attributes(
				{"Dia": "22 Dia", "Colour": "Red"},
				{"Dia": "18 Dia", "Colour": "Red"},
				{"Dia": "18 Dia", "Colour": "Red"},
			),
			{"Dia": "22 Dia", "Colour": "Red"},
		)
		self.assertEqual(
			project_output_attributes(
				{"Dia": "22 Dia", "Colour": "Red"},
				{"Dia": "18 Dia", "Colour": "Red"},
				{"Dia": "16 Dia", "Colour": "Red"},
			),
			{"Dia": "16 Dia", "Colour": "Red"},
		)

	def _fill(self, rows, availability, variants):
		with (
			patch(
				"essdee_yrp.fabric_source.resolve_source_process",
				return_value={
					"value": "0::Knitting",
					"process_name": "Knitting",
					"label": "Knitting",
				},
			),
			patch(
				"essdee_yrp.fabric_source.get_source_availability",
				return_value=availability,
			),
			patch(
				"essdee_yrp.fabric_source._variant_info",
				return_value=variants,
			),
		):
			return fill_from_source_grns(
				rows,
				lot="LOT-1",
				ipd=frappe._dict(name="IPD-1", item="Test Cloth"),
				current_process="Dyeing",
				current_work_order="WO-2",
				source_process="0::Knitting",
			)

	def test_shared_greige_is_not_split_between_final_colours(self):
		rows = [_row("Greige", "Red"), _row("Greige", "Navy")]
		availability = {
			"received": {"Greige-32": 150},
			"reserved": {},
			"net": {"Greige-32": 150},
		}
		variants = {
			"Greige-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Greige"},
			},
		}

		self._fill(rows, availability, variants)

		self.assertEqual([row["prefill"] for row in rows], [0, 0])
		self.assertTrue(all(row["source_shared"] for row in rows))
		self.assertEqual([row["source_available"] for row in rows], [150, 150])

	def test_dyed_yarn_knitting_outputs_fill_matching_colours(self):
		rows = [_row("Red", "Red"), _row("Navy", "Navy")]
		availability = {
			"received": {"Red-32": 90, "Navy-32": 60},
			"reserved": {},
			"net": {"Red-32": 90, "Navy-32": 60},
		}
		variants = {
			"Red-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Red"},
			},
			"Navy-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Navy"},
			},
		}

		self._fill(rows, availability, variants)

		self.assertEqual([row["prefill"] for row in rows], [90, 60])
		self.assertFalse(any(row["source_shared"] for row in rows))

	def test_no_compatible_popup_input_raises(self):
		rows = [_row("Red", "Red")]
		availability = {
			"received": {"Greige-32": 50},
			"reserved": {},
			"net": {"Greige-32": 50},
		}
		variants = {
			"Greige-32": {
				"item": "Test Cloth",
				"attrs": {"Dia": "32 Dia", "Colour": "Greige"},
			},
		}

		with self.assertRaisesRegex(
			frappe.ValidationError, "no compatible input row"
		):
			self._fill(rows, availability, variants)

	@patch("essdee_yrp.fabric_source.get_source_availability")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_allow_empty_returns_explicit_unavailable_context(
		self, resolve, availability
	):
		resolve.return_value = {
			"value": "0::Knitting",
			"process_name": "Knitting",
			"label": "Knitting",
		}
		availability.return_value = {
			"received": {"Greige-32": 10},
			"reserved": {"Greige-32": 10},
			"net": {"Greige-32": 0},
		}
		rows = [_row("Greige", "Red")]

		context = fill_from_source_grns(
			rows,
			lot="LOT-1",
			ipd=frappe._dict(name="IPD-1", item="Test Cloth"),
			current_process="Dyeing",
			current_work_order="WO-2",
			source_process="0::Knitting",
			allow_empty=True,
		)

		self.assertTrue(context["unavailable"])
		self.assertEqual(context["received"], 10)
		self.assertEqual(context["reserved"], 10)
		self.assertEqual(context["available"], 0)
		self.assertEqual(rows[0]["prefill"], 0)
		self.assertEqual(rows[0]["source_available"], 0)

	@patch("essdee_yrp.fabric_source._rows_in_stock_uom")
	@patch("essdee_yrp.fabric_source.get_source_availability")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_calculate_does_not_add_a_custom_stock_cap(
		self, resolve, availability, stock_rows
	):
		resolve.return_value = {
			"value": "0::Knitting",
			"process_name": "Knitting",
		}
		availability.return_value = {
			"received": {"Greige-32": 100},
			"reserved": {"Greige-32": 20},
			"net": {"Greige-32": 80},
		}
		stock_rows.return_value = {"Greige-32": 90}

		selected = validate_source_demands(
			[{"item_variant": "Greige-32", "qty": 90, "uom": "Kg"}],
			lot="LOT-1",
			ipd=frappe._dict(name="IPD-1"),
			cloth_item="Test Cloth",
			current_process="Dyeing",
			current_work_order="WO-2",
			source_process="0::Knitting",
		)
		self.assertEqual(selected["process_name"], "Knitting")
		availability.assert_not_called()
		stock_rows.assert_not_called()


class TestFabricSourceTransactions(IntegrationTestCase):
	"""Real parent/child transaction rows exercise the production SQL contract."""

	def _work_order(self, name, process, item, docstatus, source=None):
		doc = frappe.new_doc("Work Order")
		doc.name = name
		doc.docstatus = docstatus
		doc.process_name = process
		doc.item = item
		doc.lot = self.lot
		doc.production_detail = self.ipd
		if source:
			doc.fabric_source_process = source
			doc.fabric_source_process_step = f"0::{source}"
		doc.db_insert()
		return doc

	def _source_receipt(self, suffix, qty, *, is_rework=0, is_return=0):
		wo = self._work_order(
			f"_Test Source WO {suffix}", "Knitting", self.item, 1
		)
		receivable = frappe.new_doc("Work Order Receivables")
		receivable.name = f"_Test Source WOR {suffix}"
		receivable.parent = wo.name
		receivable.parenttype = "Work Order"
		receivable.parentfield = "receivables"
		receivable.item_variant = self.variant
		receivable.qty = qty
		receivable.uom = "Kg"
		receivable.db_insert()

		grn = frappe.new_doc("Goods Received Note")
		grn.name = f"_Test Source GRN {suffix}"
		grn.docstatus = 1
		grn.against = "Work Order"
		grn.against_id = wo.name
		grn.is_rework = is_rework
		grn.is_return = is_return
		grn.to_warehouse = self.warehouse
		grn.db_insert()

		item = frappe.new_doc("Goods Received Note Item")
		item.name = f"_Test Source GRNI {suffix}"
		item.parent = grn.name
		item.parenttype = "Goods Received Note"
		item.parentfield = "items"
		item.item_variant = self.variant
		item.quantity = qty
		item.stock_qty = qty
		item.uom = "Kg"
		item.received_type = "Accepted"
		item.ref_doctype = "Work Order Receivables"
		item.ref_docname = receivable.name
		item.db_insert()
		return grn

	def setUp(self):
		suffix = frappe.generate_hash(length=8)
		self.item = _ensure_item(f"_Test Source Cloth {suffix}")
		self.variant = _resolve_variant(self.item, {})
		self.lot = f"_Test Source Lot {suffix}"
		self.ipd = f"_Test Source IPD {suffix}"
		self.current = f"_Test Current WO {suffix}"
		self.location = f"_Test Source Location {suffix}"
		self.warehouse = f"_Test Source Warehouse {suffix}"
		self.suffix = suffix
		self.enterContext(patch(
			"yrp.yrp.doctype.delivery_challan.delivery_challan._get_warehouse_for_supplier",
			return_value=self.warehouse,
		))

	def test_draft_plans_do_not_reserve_source_grns_but_actual_use_is_deducted(self):
		self._source_receipt(self.suffix, 100)
		# Rework output is still physical input for a later process and therefore
		# remains selectable; only Lot-level cumulative counting was removed.
		self._source_receipt(f"{self.suffix}-RW", 20, is_rework=1)
		# Return GRNs are not positive source availability.
		self._source_receipt(f"{self.suffix}-RET", 10, is_return=1)

		target = self._work_order(
			f"_Test Reserved WO {self.suffix}",
			"Dyeing",
			self.item,
			0,
			source="Knitting",
		)
		reserved = frappe.new_doc("Work Order Deliverables")
		reserved.name = f"_Test Reserved WOD {self.suffix}"
		reserved.parent = target.name
		reserved.parenttype = "Work Order"
		reserved.parentfield = "deliverables"
		reserved.item_variant = self.variant
		reserved.qty = 35
		reserved.pending_quantity = 35
		reserved.uom = "Kg"
		reserved.is_calculated = 1
		reserved.source_grn = f"_Test Source GRN {self.suffix}"
		reserved.source_grn_item = f"_Test Source GRNI {self.suffix}"
		reserved.db_insert()

		# A different downstream process selecting the same Knitting pool must
		# reserve it too; otherwise Dyeing could reuse cloth already allocated to
		# White Wash.
		other_target = self._work_order(
			f"_Test Other Reserved WO {self.suffix}",
			"White Wash",
			self.item,
			0,
			source="Knitting",
		)
		other_reserved = frappe.new_doc("Work Order Deliverables")
		other_reserved.name = f"_Test Other Reserved WOD {self.suffix}"
		other_reserved.parent = other_target.name
		other_reserved.parenttype = "Work Order"
		other_reserved.parentfield = "deliverables"
		other_reserved.item_variant = self.variant
		other_reserved.qty = 25
		other_reserved.pending_quantity = 15
		other_reserved.uom = "Kg"
		other_reserved.is_calculated = 1
		other_reserved.source_grn = f"_Test Source GRN {self.suffix}"
		other_reserved.source_grn_item = f"_Test Source GRNI {self.suffix}"
		other_reserved.db_insert()

		# A Work Order consuming the same physical variant from another source
		# process belongs to a different pool and must not reduce Knitting.
		unrelated_target = self._work_order(
			f"_Test Unrelated Reserved WO {self.suffix}",
			"Washing",
			self.item,
			0,
			source="Dyeing",
		)
		unrelated_reserved = frappe.new_doc("Work Order Deliverables")
		unrelated_reserved.name = f"_Test Unrelated Reserved WOD {self.suffix}"
		unrelated_reserved.parent = unrelated_target.name
		unrelated_reserved.parenttype = "Work Order"
		unrelated_reserved.parentfield = "deliverables"
		unrelated_reserved.item_variant = self.variant
		unrelated_reserved.qty = 40
		unrelated_reserved.uom = "Kg"
		unrelated_reserved.is_calculated = 1
		unrelated_reserved.db_insert()

		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
			target_location=self.location,
		)
		self.assertEqual(available["received"], {self.variant: 120})
		self.assertEqual(available["reserved"], {self.variant: 10})
		self.assertEqual(available["net"], {self.variant: 110})

		# Closing a downstream WO releases only unused plan; the quantity already
		# delivered/consumed remains tied to its exact upstream receipt.
		frappe.db.set_value("Work Order", other_target.name, "open_status", "Close")
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
			target_location=self.location,
		)
		self.assertEqual(available["reserved"], {self.variant: 10})
		self.assertEqual(available["net"], {self.variant: 110})

		# Cancelling the reserving WO releases the quantity without touching Lot.
		frappe.db.set_value("Work Order", target.name, "docstatus", 2)
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
			target_location=self.location,
		)
		self.assertEqual(available["reserved"], {self.variant: 10})
		self.assertEqual(available["net"], {self.variant: 110})

		frappe.db.set_value("Work Order", other_target.name, "docstatus", 2)
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
			target_location=self.location,
		)
		self.assertEqual(available["net"], {self.variant: 120})

	def test_minimum_stock_precision_receipt_remains_available(self):
		self._source_receipt(self.suffix, 0.001)

		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
			target_location=self.location,
		)

		self.assertEqual(available["received"], {self.variant: 0.001})
		self.assertEqual(available["net"], {self.variant: 0.001})
		self.assertEqual(len(available["buckets"]), 1)
		self.assertEqual(
			_source_breakdown(available["buckets"])[0]["available"],
			0.001,
		)
