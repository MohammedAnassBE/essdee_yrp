from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.api.test_cloth_program import _ensure_item
from essdee_yrp.api.work_order import _resolve_variant
from essdee_yrp.fabric_source import (
	fill_from_source_grns,
	get_source_availability,
	get_source_process_options,
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
	def test_only_earlier_steps_are_offered_immediate_first(self, get_steps):
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

	@patch("essdee_yrp.fabric_source._rows_in_stock_uom")
	@patch("essdee_yrp.fabric_source.get_source_availability")
	@patch("essdee_yrp.fabric_source.resolve_source_process")
	def test_calculate_rechecks_stale_or_overallocated_quantity(
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

		with self.assertRaisesRegex(
			frappe.ValidationError, "only 80.0 Kg remains available"
		):
			validate_source_demands(
				[{"item_variant": "Greige-32", "qty": 90, "uom": "Kg"}],
				lot="LOT-1",
				ipd=frappe._dict(name="IPD-1"),
				cloth_item="Test Cloth",
				current_process="Dyeing",
				current_work_order="WO-2",
				source_process="0::Knitting",
			)


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
		self.suffix = suffix

	def test_submitted_grns_minus_same_source_work_order_reservations(self):
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
		reserved.uom = "Kg"
		reserved.is_calculated = 1
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
		other_reserved.uom = "Kg"
		other_reserved.is_calculated = 1
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
		)
		self.assertEqual(available["received"], {self.variant: 120})
		self.assertEqual(available["reserved"], {self.variant: 60})
		self.assertEqual(available["net"], {self.variant: 60})

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
		)
		self.assertEqual(available["reserved"], {self.variant: 25})
		self.assertEqual(available["net"], {self.variant: 95})

		frappe.db.set_value("Work Order", other_target.name, "docstatus", 2)
		available = get_source_availability(
			lot=self.lot,
			ipd=self.ipd,
			cloth_item=self.item,
			source_process="Knitting",
			source_step="0::Knitting",
			current_process="Dyeing",
			current_work_order=self.current,
		)
		self.assertEqual(available["net"], {self.variant: 120})
