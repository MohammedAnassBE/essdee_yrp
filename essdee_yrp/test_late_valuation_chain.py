from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment import (
	create_adjustment,
	create_reversal,
	process_adjustment,
	register_production_links,
)
from yrp.yrp_stock.doctype.stock_valuation_adjustment.test_stock_valuation_adjustment import (
	_stock_context,
	_stock_entry,
	_warehouse,
)


def cleanup_u40_probe_artifacts():
	"""Reverse/cancel only isolated U40 test entries left by an interrupted run."""
	names = frappe.db.sql(
		"""
		SELECT name
		FROM `tabStock Entry`
		WHERE docstatus = 1
		  AND (
			LEFT(COALESCE(from_warehouse, ''), 20) = '_Test Valuation U40 '
			OR LEFT(COALESCE(to_warehouse, ''), 20) = '_Test Valuation U40 '
		  )
		ORDER BY creation DESC, name DESC
		""",
		pluck=True,
	)
	with patch(
		"yrp.yrp_stock.doctype.stock_valuation_adjustment."
		"stock_valuation_adjustment.enqueue_adjustment"
	):
		for name in names:
			for reversal in create_reversal("Stock Entry", name):
				reversal_state = frappe.db.get_value(
					"Stock Valuation Adjustment",
					reversal,
					["status", "reversal_of"],
					as_dict=True,
				)
				if (
					reversal_state.status not in {"Completed", "Reversed"}
					and reversal_state.reversal_of
					and frappe.db.get_value(
						"Stock Valuation Adjustment", reversal_state.reversal_of, "status"
					)
					== "Reversed"
				):
					# Repair only an interrupted test race where the reversal's
					# final parent lock deadlocked after marking its original.
					frappe.db.set_value(
						"Stock Valuation Adjustment",
						reversal_state.reversal_of,
						"status",
						"Reversal Queued",
					)
				process_adjustment(reversal)
	for name in names:
		doc = frappe.get_doc("Stock Entry", name)
		if doc.docstatus == 1:
			doc.cancel()
	return names


def cleanup_exact_valuation_test_artifacts(stock_entries):
	"""Reverse/cancel an explicit list of base valuation-suite test vouchers.

	The strict warehouse-prefix guard prevents this administrative test helper
	from ever accepting a retained business voucher.
	"""
	if isinstance(stock_entries, str):
		stock_entries = frappe.parse_json(stock_entries)
	names = sorted(set(stock_entries or []))
	if not names:
		return []

	docs = []
	for name in names:
		doc = frappe.get_doc("Stock Entry", name)
		warehouses = [doc.from_warehouse, doc.to_warehouse]
		warehouses = [warehouse for warehouse in warehouses if warehouse]
		if not warehouses or any(
			not warehouse.startswith("_Test Valuation ") for warehouse in warehouses
		):
			frappe.throw(f"Refusing cleanup for non-test Stock Entry {name}")
		docs.append(doc)

	with patch(
		"yrp.yrp_stock.doctype.stock_valuation_adjustment."
		"stock_valuation_adjustment.enqueue_adjustment"
	):
		for name in names:
			for original in frappe.get_all(
				"Stock Valuation Adjustment",
				filters={
					"source_doctype": "Stock Entry",
					"source_name": name,
					"adjustment_type": ["!=", "Reversal"],
					"docstatus": 1,
				},
				fields=["name", "status"],
				order_by="creation asc",
			):
				if original.status not in {"Completed", "Reversal Queued", "Reversed"}:
					process_adjustment(original.name)
			for reversal in create_reversal("Stock Entry", name):
				if frappe.db.get_value(
					"Stock Valuation Adjustment", reversal, "status"
				) not in {"Completed", "Reversed"}:
					process_adjustment(reversal)

	for doc in sorted(docs, key=lambda row: (row.creation, row.name), reverse=True):
		doc.reload()
		if doc.docstatus == 1:
			doc.cancel()
	return names


class TestLateValuationChain(FrappeTestCase):
	"""Qualify the finalized base propagation engine through Essdee's stage topology."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.item, cls.uom, cls.dimensions = _stock_context()

	def setUp(self):
		super().setUp()
		setting = patch(
			"yrp.yrp_stock.doctype.stock_valuation_adjustment.stock_valuation_adjustment.is_stock_adjustment_enabled",
			return_value=True,
		)
		setting.start()
		self.addCleanup(setting.stop)

	def _sle(self, voucher, positive):
		return frappe.db.get_value(
			"Stock Ledger Entry",
			{
				"voucher_type": voucher.doctype,
				"voucher_no": voucher.name,
				"qty": [">", 0] if positive else ["<", 0],
				"is_cancelled": 0,
			},
			["name", "item", "qty", "rate"],
			as_dict=True,
		)

	def _build_chain(self, label):
		warehouses = [
			_warehouse(f"{label} {stage}")
			for stage in ("Input", "Cutting", "Printing", "Stitching", "Packing")
		]
		source = _stock_entry(
			self.item,
			self.uom,
			self.dimensions,
			"Material Receipt",
			10,
			10,
			to_warehouse=warehouses[0],
			posting_time="08:00:00",
		)
		targets = [self._sle(source, True)]
		stages = []
		for index, (stage, rate) in enumerate(
			(("Cutting", 11), ("Printing", 13), ("Stitching", 16), ("Packing", 20))
		):
			issue = _stock_entry(
				self.item,
				self.uom,
				self.dimensions,
				"Material Issue",
				10,
				0,
				from_warehouse=warehouses[index],
				posting_time=f"08:{index * 2 + 1:02d}:00",
			)
			receipt = _stock_entry(
				self.item,
				self.uom,
				self.dimensions,
				"Material Receipt",
				10,
				rate,
				to_warehouse=warehouses[index + 1],
				posting_time=f"08:{index * 2 + 2:02d}:00",
			)
			consumption = self._sle(issue, False)
			output = self._sle(receipt, True)
			register_production_links(
				issue.doctype,
				issue.name,
				[
					{
						"consumption_sle": consumption.name,
						"output_receipt_sle": output.name,
						"source_row": issue.items[0].name,
						"input_quantity": 10,
						"allocation_weight": 10,
						"stock_dimensions": frappe.as_json(self.dimensions),
					}
				],
			)
			targets.append(output)
			stages.append({"stage": stage, "issue": issue, "receipt": receipt})
		return {
			"source": source,
			"targets": targets,
			"stages": stages,
			"final_warehouse": warehouses[-1],
		}

	def _apply_difference(self, scenario, target_index, difference):
		target = scenario["targets"][target_index]
		source = (
			scenario["source"]
			if target_index == 0
			else scenario["stages"][target_index - 1]["receipt"]
		)
		adjustment_kwargs = dict(
			adjustment_type=(
				"Purchase Invoice Rate Difference"
				if target_index == 0
				else "Work Order Excess Usage"
			),
			source_doctype=source.doctype,
			source_name=source.name,
			effective_date=source.posting_date,
			allocations=[
				{
					"target_sle": target.name,
					"item": target.item,
					"quantity": target.qty,
					"old_rate": target.rate,
					"new_rate": flt(target.rate) + difference / flt(target.qty),
					"difference": difference,
					"allocation_weight": target.qty,
					"stock_dimensions": frappe.as_json(self.dimensions),
				}
			],
			idempotency_key=f"essdee-u40:{source.name}:{difference}",
			enqueue=False,
		)
		adjustment = create_adjustment(**adjustment_kwargs)
		# A retried source hook must return the durable winner rather than create a
		# second valuation adjustment or enqueue a second propagation chain.
		self.assertEqual(create_adjustment(**adjustment_kwargs), adjustment)
		process_adjustment(adjustment)
		result = frappe.db.get_value(
			"Stock Valuation Adjustment",
			adjustment,
			[
				"status",
				"total_source_difference",
				"propagated_stock_difference",
				"terminal_difference",
			],
			as_dict=True,
		)
		self.assertEqual(result.status, "Completed")
		self.assertAlmostEqual(flt(result.total_source_difference), difference)
		self.assertAlmostEqual(flt(result.propagated_stock_difference), difference)
		self.assertAlmostEqual(flt(result.terminal_difference), 0)
		return adjustment

	def _run_order(self, label, order):
		scenario = self._build_chain(label)
		self.addCleanup(self._cleanup_scenario, scenario)
		differences = (10, 1, 2, 3, 4)
		adjustments = []
		for target_index in order:
			adjustments.append(
				self._apply_difference(
					scenario, target_index, differences[target_index]
				)
			)

		expected_overlays = (10, 11, 13, 16, 20)
		actual_overlays = []
		for target, expected in zip(scenario["targets"], expected_overlays, strict=True):
			values = frappe.db.get_value(
				"Stock Ledger Entry",
				target.name,
				["valuation_adjustment_value", "valuation_is_stale"],
				as_dict=True,
			)
			actual_overlays.append(flt(values.valuation_adjustment_value))
			self.assertAlmostEqual(flt(values.valuation_adjustment_value), expected)
			self.assertEqual(flt(values.valuation_is_stale), 0)

		final_target = scenario["targets"][-1]
		final_sle = frappe.db.get_value(
			"Stock Ledger Entry",
			final_target.name,
			["qty", "rate", "valuation_adjustment_value", "stock_value"],
			as_dict=True,
		)
		final_bin = frappe.db.get_value(
			"Bin",
			{
				"item_code": self.item,
				"warehouse": scenario["final_warehouse"],
				**self.dimensions,
			},
			["actual_qty", "stock_value", "valuation_rate"],
			as_dict=True,
		)
		self.assertAlmostEqual(flt(final_sle.qty), 10)
		self.assertAlmostEqual(flt(final_sle.rate), 20)
		self.assertAlmostEqual(flt(final_sle.valuation_adjustment_value), 20)
		self.assertAlmostEqual(flt(final_sle.stock_value), 220)
		self.assertAlmostEqual(flt(final_bin.actual_qty), 10)
		self.assertAlmostEqual(flt(final_bin.stock_value), 220)
		self.assertAlmostEqual(flt(final_bin.valuation_rate), 22)

		for adjustment in adjustments:
			entries = frappe.get_all(
				"Stock Valuation Propagation Entry",
				filters={"adjustment": adjustment},
				fields=["status", "entry_type", "difference", "remaining_difference"],
			)
			self.assertTrue(entries)
			self.assertFalse(
				[row for row in entries if row.status not in {"Applied", "Terminal"}]
			)

		result = {
			"overlays": actual_overlays,
			"final_stock_value": flt(final_sle.stock_value),
			"final_valuation_rate": flt(final_bin.valuation_rate),
		}
		self._cleanup_scenario(scenario)
		return result

	def _cleanup_scenario(self, scenario):
		# Leave no active test stock or adjustment overlays behind. The immutable
		# audit rows remain available to diagnose a failure in the test database.
		scenario["source"].reload()
		if scenario["source"].docstatus != 1:
			return
		with patch(
			"yrp.yrp_stock.doctype.stock_valuation_adjustment."
			"stock_valuation_adjustment.enqueue_adjustment"
		):
			for source in [
				scenario["source"],
				*[stage["receipt"] for stage in scenario["stages"]],
			]:
				for reversal in create_reversal(source.doctype, source.name):
					process_adjustment(reversal)
		for target in scenario["targets"]:
			self.assertAlmostEqual(
				flt(
					frappe.db.get_value(
						"Stock Ledger Entry", target.name, "valuation_adjustment_value"
					)
				),
				0,
			)
		for stage in reversed(scenario["stages"]):
			stage["receipt"].reload()
			if stage["receipt"].docstatus == 1:
				stage["receipt"].cancel()
			stage["issue"].reload()
			if stage["issue"].docstatus == 1:
				stage["issue"].cancel()
		if scenario["source"].docstatus == 1:
			scenario["source"].cancel()

	def test_late_material_and_process_costs_are_order_independent(self):
		# The production worker commits between lock phases by design.  Keep those
		# boundaries inside this test's outer rollback transaction so repeated
		# focused/full-suite runs cannot persist test SLEs or immutable adjustment
		# audit rows on the shared acceptance site.
		with patch.object(frappe.db, "commit") as worker_commit:
			forward = self._run_order("U40 Forward", (0, 1, 2, 3, 4))
			reverse = self._run_order("U40 Reverse", (4, 3, 2, 1, 0))

		self.assertGreater(worker_commit.call_count, 0)

		self.assertEqual(forward["overlays"], [10, 11, 13, 16, 20])
		self.assertEqual(reverse["overlays"], [10, 11, 13, 16, 20])
		self.assertEqual(forward, reverse)
