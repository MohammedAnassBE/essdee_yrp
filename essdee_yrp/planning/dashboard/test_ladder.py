from unittest import TestCase

from essdee_yrp.planning.dashboard import ladder


def facts(**values):
	return {
		"planned": 1000,
		"cut": 0,
		"dispatch": 0,
		"pack_delivered": 0,
		"sewing_delivered": 0,
		"sewing_received": 0,
		"cutting_status": "",
		"lay_sheets": 0,
		"cloth_received": 0,
		"purchased_fabric": 0,
		**values,
	}


class TestLotStatusLadder(TestCase):
	def status(self, **values):
		return ladder.get_lot_status(facts(**values))

	def test_dispatched_above_ninety_percent_of_basis(self):
		self.assertEqual(self.status(dispatch=901), "Dispatched")

	def test_exactly_ninety_percent_dispatched_is_not_dispatched(self):
		self.assertEqual(self.status(dispatch=900), "Packing in progress")

	def test_basis_is_cut_when_cut_exists(self):
		self.assertEqual(self.status(cut=2000, dispatch=1000), "Packing in progress")

	def test_packing_in_progress_from_packing_delivered(self):
		self.assertEqual(self.status(pack_delivered=1), "Packing in progress")

	def test_ready_for_packing_at_exactly_ninety_percent_sewn(self):
		self.assertEqual(self.status(sewing_received=900), "Ready for packing")

	def test_in_sewing_when_sewing_issued(self):
		self.assertEqual(self.status(sewing_delivered=10), "In sewing")

	def test_in_sewing_when_sewing_output_below_ninety_percent(self):
		self.assertEqual(self.status(sewing_received=899), "In sewing")

	def test_waiting_for_sewing_after_cutting_plan_completed(self):
		self.assertEqual(self.status(cutting_status="Completed"), "Waiting for sewing")
		self.assertEqual(self.status(cutting_status="Cut Panel Dispatch Pending"), "Waiting for sewing")

	def test_in_cutting_with_lay_sheets(self):
		self.assertEqual(self.status(cutting_status="Cutting In Progress", lay_sheets=2), "In cutting")

	def test_waiting_for_cutting_when_cloth_received(self):
		self.assertEqual(self.status(cloth_received=12.5), "Waiting for cutting")

	def test_purchased_fabric_counts_as_received(self):
		self.assertEqual(self.status(purchased_fabric=40), "Waiting for cutting")

	def test_fabric_not_received_otherwise(self):
		self.assertEqual(self.status(cutting_status="Planned"), "Fabric not received")

	def test_zero_basis_never_dispatched(self):
		self.assertEqual(self.status(planned=0, dispatch=5), "Packing in progress")


class TestCuttingStatus(TestCase):
	def test_highest_ranked_cutting_plan_status_wins(self):
		self.assertEqual(
			ladder.get_best_cutting_status(["Planned", "Completed", "Cutting In Progress"]), "Completed"
		)

	def test_no_cutting_plan_is_empty(self):
		self.assertEqual(ladder.get_best_cutting_status([]), "")


class TestLotQuantities(TestCase):
	sewing = {"Stitching", "Stitching and Packing", "Bottom Fusing and Stitching"}

	def quantities(self, orders, received):
		return ladder.get_lot_quantities(orders, received, self.sewing)

	def test_cut_stitching_and_packed_from_their_work_orders(self):
		orders = [
			{"name": "WO-1", "process_name": "Cutting", "includes_packing": 0},
			{"name": "WO-2", "process_name": "Stitching", "includes_packing": 0},
			{"name": "WO-3", "process_name": "Ironing and Packing", "includes_packing": 1},
			{"name": "WO-4", "process_name": "Printing", "includes_packing": 0},
		]
		result = self.quantities(orders, {"WO-1": 100, "WO-2": 90, "WO-3": 80, "WO-4": 70})
		self.assertEqual(result, {"cut": 100, "stitch": 90, "packed": 80})

	def test_stitching_and_packing_with_packing_counts_in_both(self):
		orders = [{"name": "WO-1", "process_name": "Stitching and Packing", "includes_packing": 1}]
		self.assertEqual(self.quantities(orders, {"WO-1": 1936}), {"cut": 0, "stitch": 1936, "packed": 1936})

	def test_stitching_and_packing_without_packing_counts_only_in_stitching(self):
		orders = [{"name": "WO-1", "process_name": "Stitching and Packing", "includes_packing": 0}]
		self.assertEqual(self.quantities(orders, {"WO-1": 6616}), {"cut": 0, "stitch": 6616, "packed": 0})

	def test_each_work_order_counts_once(self):
		orders = [{"name": "WO-1", "process_name": "Stitching", "includes_packing": 0}] * 2
		self.assertEqual(self.quantities(orders, {"WO-1": 50})["stitch"], 50)

	def test_balance_can_be_negative(self):
		self.assertEqual(ladder.get_balance(planned=100, cut=120, dispatch=150), -30)
		self.assertEqual(ladder.get_balance(planned=100, cut=0, dispatch=40), 60)


class TestSewingProcesses(TestCase):
	def test_groups_containing_the_setting_count_as_sewing(self):
		details = [
			{"parent": "Stitching and Packing", "process_name": "Stitching"},
			{"parent": "Stitching and Packing", "process_name": "Packing"},
			{"parent": "Bottom Fusing and Stitching", "process_name": "Stitching"},
			{"parent": "Ironing and Packing", "process_name": "Ironing"},
		]
		used = [
			"Stitching",
			"Stitching and Packing",
			"Bottom Fusing and Stitching",
			"Ironing and Packing",
			"Packing",
		]
		self.assertEqual(
			ladder.get_sewing_processes("Stitching", details, used),
			["Bottom Fusing and Stitching", "Stitching", "Stitching and Packing"],
		)

	def test_no_setting_means_no_sewing_process(self):
		self.assertEqual(ladder.get_sewing_processes(None, [], ["Stitching"]), [])


class TestPpoPieces(TestCase):
	def test_pieces_are_boxes_times_the_single_pieces_per_box(self):
		self.assertEqual(ladder.get_ppo_pieces(100.5, [12, 12, None]), 1206)

	def test_boxes_only_when_no_pieces_per_box(self):
		self.assertIsNone(ladder.get_ppo_pieces(554, [None, 0]))

	def test_boxes_only_when_pieces_per_box_differ(self):
		self.assertIsNone(ladder.get_ppo_pieces(554, [6, 12]))


class TestDispatchMultiplier(TestCase):
	def test_batch_tracked_packing_dispatches_pieces(self):
		self.assertEqual(ladder.get_dispatch_multiplier(True, 12), 1)

	def test_box_packing_dispatches_boxes_times_pieces_per_box(self):
		self.assertEqual(ladder.get_dispatch_multiplier(False, 12), 12)


class TestProcessRows(TestCase):
	def test_kind_by_item_cutting_and_packing(self):
		kind = ladder.get_process_kind
		self.assertEqual(kind("Knitting", [{"item": "Fabric", "includes_packing": 0}], "Vest"), "cloth")
		self.assertEqual(kind("Cutting", [{"item": "Vest", "includes_packing": 0}], "Vest"), "cutting")
		self.assertEqual(
			kind("Ironing and Packing", [{"item": "Vest", "includes_packing": 1}], "Vest"),
			"packing",
		)
		self.assertEqual(kind("Printing", [{"item": "Vest", "includes_packing": 0}], "Vest"), "item")

	def test_status_reason_names_one_work_order_or_counts_done(self):
		self.assertEqual(
			ladder.get_status_reason([{"status": "Partially Received", "docstatus": 1}]),
			"WO Partially Received",
		)
		orders = [
			{"status": "Closed", "docstatus": 1},
			{"status": "Fully Received", "docstatus": 1},
			{"status": "Partially Delivered", "docstatus": 1},
		]
		self.assertEqual(ladder.get_status_reason(orders), "2 of 3 WOs done")

	def test_processes_sort_by_first_dc_with_no_dc_last(self):
		rows = [
			{"name": "C", "first_dc": None},
			{"name": "B", "first_dc": "2026-09-01"},
			{"name": "A", "first_dc": "2026-08-01"},
		]
		self.assertEqual([row["name"] for row in ladder.sort_by_first_dc(rows)], ["A", "B", "C"])
