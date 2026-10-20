"""MRP readiness guards, independent of stock lifecycle and persisted fixtures."""

from unittest import TestCase

import frappe

from essdee_yrp.sewing.reporting import READINESS_FIELDS, _assemble_status


class TestStatusSummaryReadiness(TestCase):
	def row(self, *, line=0, checking=0, aql=0, pre_final=0, final=0, reject=0):
		settings = frappe._dict(
			sewing_input_qty_type="Input", sewing_line_output_type="Line",
			type_wise_diff_summary="Checking", sewing_plan_inspection_type="AQL",
		)
		plan = frappe._dict(name="SP", item="Shirt", lot="Lot", work_order="WO")
		stages = [("Line", line, "Accepted"), ("Checking", checking, "Accepted"),
			("AQL", aql, "Accepted"), ("Checking", reject, "Reject")]
		snapshot = frappe._dict(
			plans={"SP": plan},
			orders=[frappe._dict(parent="SP", item_variant="Blue-M", set_combination={"major_colour": "Blue"}, quantity=100, pre_final=pre_final, final_inspection=final, fi_date=None)],
			entries=[frappe._dict(name=str(i), sewing_plan="SP", input_type=stage, received_type=receipt, entry_date=None)
				for i, (stage, _, receipt) in enumerate(stages)],
			details=[frappe._dict(parent=str(i), item_variant="Blue-M", set_combination={"major_colour": "Blue"}, quantity=quantity) for i, (_, quantity, _) in enumerate(stages)],
			lots={"Lot": frappe._dict(production_detail="IPD")},
			ipds={"IPD": frappe._dict(is_set_item=0, packing_attribute="Colour", primary_item_attribute="Size", set_item_attribute="Part")},
		)
		rows, _ = _assemble_status(snapshot, [], {"Blue-M": {"Colour": "Blue", "Size": "M"}}, settings, "Accepted", ["Line", "Checking", "AQL"])
		return rows[0]

	def test_zero_entries_do_not_create_readiness(self):
		row = self.row()
		for label, alias in READINESS_FIELDS.items():
			self.assertEqual(row[label], "")
			self.assertEqual(row[alias], "")

	def test_upstream_quantity_alone_leaves_downstream_readiness_blank(self):
		row = self.row(line=100, checking=80, aql=60, pre_final=0, final=0)
		self.assertEqual(row["Ready for Checking"], "Under Checking")
		self.assertEqual(row["Ready for AQL"], "Under AQL")
		self.assertEqual(row["Ready for Pre final"], "")
		self.assertEqual(row["Ready for Final Inspection"], "")

	def test_completed_quantity_without_source_leaves_checking_and_aql_blank(self):
		self.assertEqual(self.row(checking=10)["Ready for Checking"], "")
		self.assertEqual(self.row(aql=10)["Ready for AQL"], "")
		self.assertEqual(self.row(pre_final=10)["Ready for Pre final"], "")

	def test_final_inspection_only_needs_a_positive_final_quantity(self):
		self.assertEqual(self.row(final=10)["Ready for Final Inspection"], "Completed")
		self.assertEqual(self.row(pre_final=20, final=10)["Ready for Final Inspection"], "Under Final Inspection")
		self.assertEqual(self.row(aql=20, pre_final=-1, final=-1)["Ready for Pre final"], "")
		self.assertEqual(self.row(final=-1)["Ready for Final Inspection"], "")

	def test_checking_counts_rejects_but_aql_uses_accepted_output(self):
		row = self.row(line=10, reject=10, aql=5)
		self.assertEqual(row["Ready for Checking"], "Completed")
		self.assertEqual(row["Ready for AQL"], "")
		self.assertEqual(row["Checking Stock"], 0)
		self.assertEqual(row["Checking"], 0)
		self.assertEqual(row["Reject"], 10)


class TestStatusSummaryGrouping(TestCase):
	def setUp(self):
		self.settings = frappe._dict(
			sewing_input_qty_type="Input", sewing_line_output_type="Line",
			type_wise_diff_summary="Checking", sewing_plan_inspection_type="AQL",
		)
		self.ipd = frappe._dict(is_set_item=0, packing_attribute="Colour",
			primary_item_attribute="Size", set_item_attribute="Part")
		self.attributes = {
			"blue-m": {"Colour": "Blue", "Size": "M", "Finish": "Plain"},
			"blue-l": {"Colour": "Blue", "Size": "L", "Finish": "Plain"},
			"blue-rib": {"Colour": "Blue", "Size": "M", "Finish": "Rib"},
			"red-m": {"Colour": "Red", "Size": "M", "Finish": "Plain"},
		}
		self.snapshot = frappe._dict(
			plans={name: frappe._dict(name=name, item="Shirt", lot="Lot", work_order="WO-" + name)
				for name in ("SP1", "SP2")},
			orders=[], entries=[], details=[],
			lots={"Lot": frappe._dict(production_detail="IPD")}, ipds={"IPD": self.ipd},
		)

	def quantity(self, variant, qty, **fields):
		return frappe._dict(item_variant=variant, set_combination={"major_colour": self.attributes[variant]["Colour"]},
			quantity=qty, pre_final=0, final_inspection=0, fi_date=None,
			delivered_quantity=qty, received_qty=0, **fields)

	def assemble(self, calculated):
		return _assemble_status(self.snapshot, calculated, self.attributes, self.settings,
			"Accepted", ["Input", "Line", "Checking", "Reject", "AQL"])

	def test_same_non_size_attributes_merge_across_plans_before_readiness(self):
		self.snapshot.orders = [self.quantity("blue-m", 10, parent="SP1"),
			self.quantity("blue-l", 20, parent="SP2")]
		self.snapshot.entries = [frappe._dict(name="E1", sewing_plan="SP1", input_type="Line", received_type="Accepted", entry_date=None),
			frappe._dict(name="E2", sewing_plan="SP2", input_type="Checking", received_type="Accepted", entry_date=None)]
		self.snapshot.details = [self.quantity("blue-m", 10, parent="E1"), self.quantity("blue-l", 10, parent="E2")]
		rows, _ = self.assemble([self.quantity("blue-m", 10, parent="WO-SP1"), self.quantity("blue-l", 20, parent="WO-SP2")])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["Order Qty"], 30)
		self.assertEqual(rows[0]["Delivered Qty"], 30)
		self.assertEqual(rows[0]["Ready for Checking"], "Completed")

	def test_non_size_attributes_and_set_combinations_are_part_of_identity(self):
		rows = [self.quantity("blue-m", 10, parent="WO-SP1"),
			self.quantity("blue-rib", 20, parent="WO-SP1"),
			self.quantity("blue-m", 30, parent="WO-SP1")]
		rows[2].set_combination["major_part"] = "Top"
		result, _ = self.assemble(rows)
		self.assertEqual([row["Delivered Qty"] for row in result], [10, 20, 30])

	def test_plan_then_calculated_item_order_is_preserved_across_phases(self):
		# Order rows arrive Blue first; calculated rows across plans arrive SP2 first.
		# MRP loops plans, then their calculated rows, before order/entry facts.
		self.snapshot.orders = [self.quantity("blue-m", 5, parent="SP1"),
			self.quantity("red-m", 7, parent="SP1")]
		rows, _ = self.assemble([self.quantity("blue-m", 3, parent="WO-SP2"),
			self.quantity("red-m", 7, parent="WO-SP1"), self.quantity("blue-m", 5, parent="WO-SP1")])
		self.assertEqual([row["colour"] for row in rows], ["Red", "Blue"])

	def test_observed_unconfigured_receipt_does_not_add_visible_column(self):
		self.snapshot.entries = [frappe._dict(name="E", sewing_plan="SP1", input_type="Input", received_type="Oil Mark", entry_date="2026-01-01")]
		self.snapshot.details = [self.quantity("blue-m", 5, parent="E")]
		rows, columns = self.assemble([self.quantity("blue-m", 10, parent="WO-SP1")])
		self.assertNotIn("Input Oil Mark", columns)
		self.assertEqual(rows[0]["Input Oil Mark"], 5)

	def test_zero_quantity_entries_still_contribute_dates(self):
		self.snapshot.entries = [frappe._dict(name="E", sewing_plan="SP1", input_type="Input", received_type="Accepted", entry_date="2026-01-01")]
		self.snapshot.details = [self.quantity("blue-m", 0, parent="E")]
		rows, _ = self.assemble([self.quantity("blue-m", 10, parent="WO-SP1")])
		self.assertEqual(str(rows[0]["Input Date"]), "2026-01-01")
