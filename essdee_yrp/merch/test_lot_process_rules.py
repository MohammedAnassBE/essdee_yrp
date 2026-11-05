from unittest import TestCase

from essdee_yrp.merch import lot_process_rules as rules


def order(name, process, status="Submitted", docstatus=1, creation="2026-10-01", **values):
	return {
		"name": name,
		"process_name": process,
		"status": status,
		"docstatus": docstatus,
		"creation": creation,
		**values,
	}


IPD = {
	"cutting_process": "Cutting",
	"stiching_process": "Stitching",
	"packing_process": "Packing",
	"stiching_in_stage": "IAV-CUT",
}
IPD_PROCESSES = [
	{"process_name": "Printing", "in_stage": "IAV-CUT"},
	{"process_name": "Ironing", "in_stage": "IAV-PIECE"},
]


def steps():
	return rules.item_steps(IPD, IPD_PROCESSES)


def node_names(nodes):
	return [node["process"] for node in nodes]


class TestStatus(TestCase):
	def test_order_status_maps_every_work_order_status(self):
		expected = {
			"Draft": "idle",
			"Submitted": "idle",
			"Partially Delivered": "partial",
			"Fully Delivered": "partial",
			"Partially Received": "partial",
			"Fully Received": "done",
			"Partially Billed": "done",
			"Fully Billed": "done",
			"Close Request": "done",
			"Closed": "done",
		}
		for status, tone in expected.items():
			self.assertEqual(rules.order_status(order("WO", "Cutting", status)), tone, status)

	def test_step_status_ignores_cancelled_and_drafts(self):
		self.assertIsNone(rules.order_status(order("WO", "Cutting", "Cancelled", docstatus=2)))
		self.assertEqual(rules.order_status(order("WO", "Printing", "Submitted", docstatus=0)), "idle")
		self.assertEqual(
			rules.step_status(
				[order("A", "Cutting", "Fully Received"), order("B", "Cutting", "Cancelled", docstatus=2)]
			),
			"done",
		)

	def test_step_status_aggregates_several_orders(self):
		done, partial, idle = (
			order("A", "S", "Closed"),
			order("B", "S", "Partially Received"),
			order("C", "S", "Submitted"),
		)
		self.assertEqual(rules.step_status([]), "idle")
		self.assertEqual(rules.step_status([done, dict(done, name="D")]), "done")
		self.assertEqual(rules.step_status([idle, idle]), "idle")
		self.assertEqual(rules.step_status([done, idle]), "partial")
		self.assertEqual(rules.step_status([idle, partial]), "partial")
		self.assertEqual(rules.combine_status(["done", "idle"]), "partial")


class TestItemNodes(TestCase):
	def test_item_steps_follow_ipd_order(self):
		self.assertEqual(
			[(step["process"], step["stage"]) for step in steps()],
			[
				("Cutting", "Cutting"),
				("Printing", "Cut stage"),
				("Stitching", "Stitching"),
				("Ironing", "Piece stage"),
				("Packing", "Packing"),
			],
		)

	def test_build_item_nodes_without_orders(self):
		nodes = rules.build_item_nodes(steps(), [], {})
		self.assertEqual(node_names(nodes), ["Cutting", "Printing", "Stitching", "Ironing", "Packing"])
		self.assertTrue(all(node["orders"] == [] for node in nodes))

	def test_group_order_replaces_covered_steps_at_last_slot(self):
		group = order("WO-2627-01617", "Ironing and Packing", includes_packing=1)
		nodes = rules.build_item_nodes(
			steps(), [order("WO-1", "Cutting"), group], {"Ironing and Packing": ["Ironing", "Packing"]}
		)
		self.assertEqual(node_names(nodes), ["Cutting", "Printing", "Stitching", "Ironing and Packing"])
		self.assertEqual(nodes[-1]["stage"], "Group process")
		self.assertEqual(nodes[-1]["covers"], ["Ironing", "Packing"])
		self.assertEqual([row["name"] for row in nodes[-1]["orders"]], ["WO-2627-01617"])

	def test_member_with_own_order_stays(self):
		orders = [order("BF", "Ironing"), order("G", "Ironing and Packing")]
		nodes = rules.build_item_nodes(steps(), orders, {"Ironing and Packing": ["Ironing", "Packing"]})
		self.assertEqual(
			node_names(nodes), ["Cutting", "Printing", "Stitching", "Ironing", "Ironing and Packing"]
		)
		ironing = nodes[3]
		self.assertEqual([row["name"] for row in ironing["orders"]], ["BF"])
		self.assertEqual(ironing["also_covered_by"], ["Ironing and Packing"])

	def test_groups_on_same_slot_follow_creation(self):
		orders = [
			order("B", "Fusing and Stitching", creation="2026-10-05"),
			order("A", "Printing and Stitching", creation="2026-10-02"),
		]
		groups = {
			"Fusing and Stitching": ["Fusing", "Stitching"],
			"Printing and Stitching": ["Printing", "Stitching"],
		}
		nodes = rules.build_item_nodes(steps(), orders, groups)
		self.assertEqual(
			node_names(nodes),
			["Cutting", "Printing and Stitching", "Fusing and Stitching", "Ironing", "Packing"],
		)

	def test_unknown_process_gets_extra_node(self):
		nodes = rules.build_item_nodes(steps(), [order("Y", "Yolk Fusing")], {})
		self.assertEqual(
			node_names(nodes), ["Cutting", "Printing", "Stitching", "Ironing", "Yolk Fusing", "Packing"]
		)
		self.assertEqual(nodes[4]["stage"], "Other process")


class TestQuantities(TestCase):
	def test_size_grid_sums_orders_per_colour_and_size(self):
		items = [
			{"parent": "A", "variant": "Red-S", "quantity": 10, "delivered_quantity": 8, "received_qty": 5},
			{"parent": "B", "variant": "Red-S", "quantity": 4, "delivered_quantity": 4, "received_qty": 4},
			{"parent": "B", "variant": "Blue-M", "quantity": 3, "delivered_quantity": 0, "received_qty": 0},
		]
		identity = {"Red-S": ("Red", "", "S"), "Blue-M": ("Blue", "", "M")}
		grid = rules.size_grid(items, lambda item: identity[item["variant"]])
		self.assertEqual(
			[(row["colour"], row["planned"], row["delivered"], row["received"]) for row in grid],
			[
				("Blue", {"M": 3}, {"M": 0}, {"M": 0}),
				("Red", {"S": 14}, {"S": 12}, {"S": 9}),
			],
		)

	def test_packing_received_multiplier(self):
		rows = [
			{"item_variant": "V-S", "quantity": 10, "packing_calculation_version": 0},
			{"item_variant": "V-S", "quantity": 7, "packing_calculation_version": 2},
		]
		self.assertEqual(rules.packing_pieces(rows, lambda variant: variant[-1], 5), {"S": 57})

	def test_dispatch_pieces_uses_plan_multiplier(self):
		rows = [
			{"parent": "FP-1", "item_variant": "V-M", "dispatched": 120},
			{"parent": "FP-2", "item_variant": "V-M", "dispatched": 3},
		]
		self.assertEqual(rules.dispatch_pieces(rows, lambda variant: "M", {"FP-1": 5, "FP-2": 1}), {"M": 603})

	def test_cloth_rows_keep_yarn_deliverables_separate(self):
		attributes = {"Yarn-Greige": {"Colour": "Greige"}, "Cloth-Red-24": {"Colour": "Red", "Dia": "24 Dia"}}
		deliverables = [{"item_variant": "Yarn-Greige", "qty": 100, "pending_quantity": 0, "uom": "Kg"}]
		receivables = [{"item_variant": "Cloth-Red-24", "qty": 100, "pending_quantity": 10, "uom": "Kg"}]
		result = rules.cloth_rows(deliverables, receivables, attributes, "Colour", "Dia")
		self.assertEqual(
			result["rows"],
			[{"colour": "Red", "dia": "24 Dia", "planned": 100, "delivered": None, "received": 90}],
		)
		self.assertEqual(result["deliverables"][0]["delivered"], 100)

	def test_cloth_rows_merge_delivered_cloth_by_colour_and_dia(self):
		attributes = {
			"Greige-24": {"Colour": "Red", "Dia": "24 Dia"},
			"Dyed-24": {"Colour": "Red", "Dia": "24 Dia"},
		}
		deliverables = [{"item_variant": "Greige-24", "qty": 50, "pending_quantity": 2, "uom": "Kg"}]
		receivables = [{"item_variant": "Dyed-24", "qty": 50, "pending_quantity": 6, "uom": "Kg"}]
		result = rules.cloth_rows(deliverables, receivables, attributes, "Colour", "Dia")
		self.assertEqual(
			result["rows"],
			[{"colour": "Red", "dia": "24 Dia", "planned": 50, "delivered": 48, "received": 44}],
		)
		self.assertEqual(result["deliverables"], [])
