from importlib import import_module
from importlib.util import find_spec
from unittest import TestCase
from unittest.mock import patch

import frappe

MODULE = "essdee_yrp.finishing.report_sources"
REPORTS = "essdee_yrp.finishing.reports"

VARIANTS = {
	"TS-S-Red": {"Size": "S", "Colour": "Red"},
	"TS-M-Red": {"Size": "M", "Colour": "Red"},
	"TS-S-Blue": {"Size": "S", "Colour": "Blue"},
	"SET-S-Red-Top": {"Size": "S", "Colour": "Red", "Part": "Top"},
	"SET-S-Navy-Bottom": {"Size": "S", "Colour": "Navy", "Part": "Bottom"},
}
PLAIN_IPD = {
	"packing_attribute": "Colour",
	"primary_item_attribute": "Size",
	"is_set_item": 0,
	"set_item_attribute": None,
}
SET_IPD = {
	"packing_attribute": "Colour",
	"primary_item_attribute": "Size",
	"is_set_item": 1,
	"set_item_attribute": "Part",
}


def row(**values):
	return frappe._dict(values)


def rework_doc(name, details, lot="LOT-1", **extra):
	return frappe._dict(
		name=name,
		grn_number=f"GRN-{name}",
		lot=lot,
		item="TSHIRT",
		creation="2026-10-01 09:00:00",
		grn_rework_item_details=[row(**detail) for detail in details],
		grn_rejected_item_details=[row(**detail) for detail in extra.get("rejected", [])],
		grn_reworked_item_details=[row(**detail) for detail in extra.get("reworked", [])],
	)


class TestFinishingReportSources(TestCase):
	def _sources(self):
		self.assertIsNotNone(find_spec(MODULE), "Finishing report sources must exist")
		return import_module(MODULE)

	def _attrs(self):
		return patch(
			f"{MODULE}.get_variant_attr_details", side_effect=lambda variant: dict(VARIANTS[variant])
		)

	def test_rejection_report_groups_rows_by_source_with_earliest_time(self):
		sources = self._sources()
		doc = rework_doc(
			"RW-1",
			[],
			rejected=[
				{
					"item_variant": "TS-S-Red",
					"quantity": 2,
					"received_type": "Oil Mark",
					"rejected_time": "2026-10-03 10:00:00",
				},
				{
					"item_variant": "TS-M-Red",
					"quantity": 3,
					"received_type": "Oil Mark",
					"rejected_time": "2026-10-02 10:00:00",
				},
				{
					"item_variant": "TS-S-Red",
					"quantity": 9,
					"received_type": "Stain",
					"rejected_time": "2026-11-01 10:00:00",
				},
			],
		)
		with self._attrs():
			data = sources.build_rejection_report([(doc, PLAIN_IPD)], "2026-10-01", "2026-10-31", None)
		detail = data["report_detail"]["RW-1"]
		self.assertEqual(data["types"], ["Oil Mark"])
		self.assertEqual(data["total_sum"], 5)
		self.assertEqual(detail["date"], "2026-10-02 10:00:00")
		self.assertEqual(detail["types"], {"Oil Mark": 5})
		self.assertEqual(
			detail["rejection_detail"]["Oil Mark-Red"]["items"],
			[
				{"Size": "S", "rejected_qty": 2, "variant": "TS-S-Red", "received_type": "Oil Mark"},
				{"Size": "M", "rejected_qty": 3, "variant": "TS-M-Red", "received_type": "Oil Mark"},
			],
		)

	def test_rejection_report_skips_sources_without_matching_rows(self):
		sources = self._sources()
		doc = rework_doc(
			"RW-2",
			[],
			rejected=[
				{
					"item_variant": "TS-S-Blue",
					"quantity": 1,
					"received_type": "Stain",
					"rejected_time": "2026-10-03",
				}
			],
		)
		with self._attrs():
			data = sources.build_rejection_report([(doc, PLAIN_IPD)], None, None, "Red")
		self.assertEqual(data["report_detail"], {})

	def test_rejection_sources_load_rows_and_ipds_in_batches(self):
		sources = self._sources()
		docs = [
			row(name="RW-1", grn_number="GRN-1", creation="2026-10-01", lot="LOT-1", item="TSHIRT"),
			row(name="RW-2", grn_number="GRN-2", creation="2026-10-01", lot="LOT-NO-IPD", item="TSHIRT"),
		]
		rejected = [
			row(
				parent="RW-1", item_variant="TS-S-Red", received_type="Stain", quantity=2, rejected_time=None
			),
			row(
				parent="RW-2", item_variant="TS-S-Red", received_type="Stain", quantity=1, rejected_time=None
			),
		]
		lot_ipds = {"LOT-1": ("IPD-1", PLAIN_IPD), "LOT-NO-IPD": (None, None)}
		with (
			patch.object(frappe, "get_list", return_value=docs) as get_list,
			patch.object(frappe, "get_all", return_value=rejected) as get_all,
			patch(f"{MODULE}.get_lot_ipds", return_value=lot_ipds),
			patch.object(frappe, "get_doc", side_effect=AssertionError("per-document load")),
		):
			entries = sources.readable_rework_entries(["RW-1", "RW-2"])
		get_list.assert_called_once()
		get_all.assert_called_once()
		self.assertEqual([(doc.name, ipd) for doc, ipd in entries], [("RW-1", PLAIN_IPD)])
		self.assertEqual(entries[0][0].grn_rejected_item_details, [rejected[0]])
		with patch.object(frappe, "get_list") as get_list:
			self.assertEqual(sources.readable_rework_entries([]), [])
		get_list.assert_not_called()

	def test_rework_completion_uses_major_colour_and_default_received_type(self):
		sources = self._sources()
		rows = [
			row(item_variant="SET-S-Red-Top", quantity=4, set_combination='{"major_colour": "Maroon"}'),
			row(item_variant="SET-S-Red-Top", quantity=1, set_combination='{"major_colour": "Maroon"}'),
		]
		with self._attrs():
			data = sources.build_rework_completion(rows, SET_IPD, ["S", "M"], "Accepted")
		self.assertEqual(data["types"], ["Accepted"])
		colour = data["data"]["Red(Maroon)"]
		self.assertEqual(colour["part"], "Top")
		self.assertEqual(colour["values"]["S"], {"Accepted": 5})
		self.assertEqual(colour["size_wise_total"], {"S": 5})
		self.assertEqual(colour["colour_total"]["total"], 5)
		self.assertTrue(data["is_set_item"])

	def test_rework_groups_split_rows_by_colour_grn_and_received_type(self):
		sources = self._sources()
		doc = rework_doc(
			"RW-3",
			[
				{
					"name": "d1",
					"item_variant": "TS-S-Red",
					"received_type": "Oil Mark",
					"quantity": 5,
					"reworked": 2,
					"rejection": 1,
					"completed": 0,
					"uom": "Nos",
					"set_combination": "{}",
				},
				{
					"name": "d2",
					"item_variant": "TS-M-Red",
					"received_type": "Oil Mark",
					"quantity": 4,
					"reworked": 0,
					"rejection": 0,
					"completed": 0,
					"uom": "Nos",
					"set_combination": "{}",
				},
				{
					"name": "d3",
					"item_variant": "TS-S-Blue",
					"received_type": "Stain",
					"quantity": 7,
					"reworked": 0,
					"rejection": 0,
					"completed": 1,
					"uom": "Nos",
					"set_combination": "{}",
				},
			],
		)
		with self._attrs():
			data = sources.build_rework_groups([(doc, PLAIN_IPD, ["S", "M"])], show_reworked=0, colour=None)
		group = data["groups"]["TSHIRT/LOT-1"]
		self.assertEqual(group["sizes"], ["S", "M"])
		self.assertEqual(len(group["rows"]), 1)
		first = group["rows"][0]
		self.assertEqual(
			(first["colour"], first["grn_number"], first["received_type"]), ("Red", "GRN-RW-3", "Oil Mark")
		)
		self.assertEqual(first["received"], {"S": 3, "M": 4})
		self.assertEqual(first["rejection"], {"S": 1, "M": 0})
		self.assertEqual([item["row_name"] for item in first["items"]], ["d1", "d2"])

	def test_ironing_report_sums_delivered_quantity_by_part_and_colour(self):
		sources = self._sources()
		challans = [
			{
				"name": "DC-1",
				"actual_date": "2026-10-05",
				"lot": "LOT-1",
				"item": "SET",
				"ipd": "IPD-SET",
				"items": [
					row(item_variant="SET-S-Red-Top", delivered_quantity=4),
					row(item_variant="SET-S-Navy-Bottom", delivered_quantity=2),
				],
			},
			{
				"name": "DC-2",
				"actual_date": "2026-10-05",
				"lot": "LOT-1",
				"item": "SET",
				"ipd": "IPD-SET",
				"items": [row(item_variant="SET-S-Red-Top", delivered_quantity=1)],
			},
		]
		ipds = {
			"IPD-SET": {
				"is_set_item": 1,
				"set_item_attribute": "Part",
				"primary_item_attribute": "Size",
				"primary_values": ["S", "M"],
			}
		}
		report = sources.build_ironing_report(challans, ipds, "Colour", "Part", VARIANTS)
		self.assertEqual(len(report), 1)
		block = report[0]
		self.assertEqual(
			(block["date"], block["lot"], block["primary_attributes"], block["attributes"]),
			("2026-10-05", "LOT-1", ["S", "M"], ["Colour", "Part"]),
		)
		self.assertEqual(
			block["rows"][0], {"colour": "Red", "part": "Top", "S": 5, "M": 0, "total_qty": 5, "s_no": 1}
		)
		self.assertEqual(block["rows"][1]["s_no"], 2)

	def test_lot_ipds_load_lots_and_ipds_in_two_queries(self):
		sources = self._sources()
		lots = [row(name="LOT-1", production_detail="IPD-1"), row(name="LOT-NO-IPD", production_detail=None)]
		ipds = [row(name="IPD-1", **PLAIN_IPD)]
		with (
			patch(f"{MODULE}.attribute_db.get_all", side_effect=[lots, ipds]) as get_all,
			patch(f"{MODULE}.attribute_db.get_cached_value", side_effect=AssertionError("per-lot load")),
		):
			lot_ipds = sources.get_lot_ipds(["LOT-1", "LOT-NO-IPD", "LOT-1", None])
		self.assertEqual(get_all.call_count, 2)
		self.assertEqual(lot_ipds, {"LOT-1": ("IPD-1", PLAIN_IPD), "LOT-NO-IPD": (None, None)})
		with patch(f"{MODULE}.attribute_db.get_all") as get_all:
			self.assertEqual(sources.get_lot_ipds([None]), {})
		get_all.assert_not_called()

	def test_variant_attributes_load_every_variant_in_one_query(self):
		sources = self._sources()
		rows = [
			row(parent="TS-S-Red", attribute="Size", attribute_value="S"),
			row(parent="TS-S-Red", attribute="Colour", attribute_value="IAV-RED"),
		]
		with (
			patch.object(frappe.db, "sql", return_value=rows) as query,
			patch(f"{MODULE}.attribute_db.value", side_effect=lambda raw: {"IAV-RED": "Red"}.get(raw, raw)),
		):
			attributes = sources.get_variant_attributes({"TS-S-Red", "MISSING"})
		query.assert_called_once()
		self.assertEqual(set(query.call_args.args[1]["variants"]), {"TS-S-Red", "MISSING"})
		self.assertEqual(attributes, {"TS-S-Red": {"Size": "S", "Colour": "Red"}, "MISSING": {}})
		with patch.object(frappe.db, "sql") as query:
			self.assertEqual(sources.get_variant_attributes(set()), {})
		query.assert_not_called()

	def test_packed_details_summary_groups_by_date_then_lot(self):
		self._sources()
		reports = import_module(REPORTS)
		grns = [
			frappe._dict(name="GRN-B", lot="LOT-2", actual_date="2026-10-02"),
			frappe._dict(name="GRN-A", lot="LOT-1", actual_date="2026-10-02"),
			frappe._dict(name="GRN-C", lot="LOT-1", actual_date="2026-10-01"),
		]
		packing = frappe._dict(
			sizes=["S"],
			size_pieces={"S": 5},
			total_boxes=1,
			total_pieces=5,
			dynamic_ratio_packing=False,
			pieces_per_box=5,
		)
		with (
			patch.object(frappe, "get_list", return_value=grns) as get_list,
			patch(
				f"{REPORTS}.attribute_db.get_value",
				return_value=frappe._dict(item="TSHIRT", production_detail="IPD-1"),
			),
			patch.object(frappe, "get_cached_doc", return_value=frappe._dict(name="IPD-1")),
			patch(f"{REPORTS}.load_packing_grns", return_value={}),
			patch(f"{REPORTS}.get_packing_grn_report_values", return_value=packing),
			patch(
				f"{REPORTS}.apply_set_item_multiplier_to_packing_report",
				side_effect=lambda value, _ipd: value,
			),
		):
			result = reports.get_finishing_packed_details(
				from_date="2026-10-01", to_date="2026-10-31", summary=1
			)
		self.assertEqual(
			get_list.call_args.kwargs["filters"]["actual_date"], ["between", ["2026-10-01", "2026-10-31"]]
		)
		self.assertEqual(
			[(row["date"], row["lot"]) for row in result["data"]],
			[("2026-10-01", "LOT-1"), ("2026-10-02", "LOT-1"), ("2026-10-02", "LOT-2")],
		)

	def test_packing_grn_values_use_batched_grn_items(self):
		reports = import_module(REPORTS)
		grns = [row(name="GRN-A", packing_calculation_version=0, total_packing_boxes=0)]
		items = [
			row(parent="GRN-A", item_variant="TS-S-Red", quantity=2),
			row(parent="GRN-A", item_variant="TS-M-Red", quantity=3),
		]
		attributes = [
			row(parent=variant, attribute=attribute, attribute_value=value)
			for variant, values in VARIANTS.items()
			for attribute, value in values.items()
		]
		ipd = frappe._dict(name="IPD-1", packing_combo=4, primary_item_attribute="Size")
		original_get_all = frappe.get_all
		original_sql = frappe.db.sql
		attribute_queries = []
		records = {"YRP Goods Received Note": grns, "YRP Goods Received Note Item": items}

		def get_all(doctype, *args, **kwargs):
			if doctype in records:
				return records[doctype]
			return original_get_all(doctype, *args, **kwargs)

		def sql(query, *args, **kwargs):
			if "Item Variant Attribute" not in query:
				return original_sql(query, *args, **kwargs)
			attribute_queries.append(args[0])
			return attributes

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			patch.object(frappe.db, "sql", side_effect=sql),
			patch(f"{REPORTS}.get_ipd_primary_values", return_value=["S", "M"]),
			patch(f"{REPORTS}._attribute_value", side_effect=lambda value: value),
		):
			packing = reports.get_packing_grn_report_values(["GRN-A"], ipd)
		self.assertEqual(
			[set(values["variants"]) for values in attribute_queries], [{"TS-S-Red", "TS-M-Red"}]
		)
		self.assertEqual(packing.size_pieces, {"S": 8, "M": 12})
		self.assertEqual((packing.total_boxes, packing.total_pieces), (5, 20))

	def test_packed_details_summary_requires_an_ordered_range(self):
		reports = import_module(REPORTS)
		for kwargs in (
			{"summary": 1, "from_date": "2026-10-01"},
			{"summary": 1, "from_date": "2026-10-05", "to_date": "2026-10-01"},
			{},
		):
			with self.subTest(kwargs=kwargs), self.assertRaises(frappe.ValidationError):
				reports.get_finishing_packed_details(**kwargs)

	def test_dispatch_report_loads_every_source_in_batches(self):
		reports = import_module(REPORTS)
		records = {
			"YRP Goods Received Note": [
				row(name="GRN-A", packing_calculation_version=0, total_packing_boxes=0)
			],
			"YRP Goods Received Note Item": [
				row(parent="GRN-A", item_variant="TS-S-Red", quantity=2),
				row(parent="GRN-A", item_variant="TS-M-Red", quantity=3),
			],
			"YRP Stock Entry": [
				row(name="SE-1", packing_batch_dispatch_json=None),
				row(
					name="SE-2",
					packing_batch_dispatch_json='[{"finishing_plan": "FP-2", "box_quantity": 2}]',
				),
			],
			"SD YRP Finishing Plan": [row(name="FP-2", lot="LOT-2")],
			"YRP Stock Entry Detail": [
				row(parent="SE-1", item="TS-S-Red", qty=1, lot="LOT-1"),
				row(parent="SE-2", item="TS-M-Red", qty=6, lot="LOT-2"),
			],
		}
		lots = [
			row(name="LOT-1", item="TSHIRT", production_detail="IPD-1"),
			row(name="LOT-2", item="TSHIRT", production_detail="IPD-1"),
		]
		attributes = [
			row(parent=variant, attribute=attribute, attribute_value=value)
			for variant, values in VARIANTS.items()
			for attribute, value in values.items()
		]
		queried = []
		attribute_queries = []
		original_sql = frappe.db.sql

		original_get_all = frappe.get_all

		def get_all(doctype, *args, **kwargs):
			if doctype not in records:
				return original_get_all(doctype, *args, **kwargs)
			queried.append(doctype)
			return records[doctype]

		def sql(query, *args, **kwargs):
			if "Item Variant Attribute" not in query:
				return original_sql(query, *args, **kwargs)
			attribute_queries.append(query)
			return attributes

		ipd = frappe._dict(name="IPD-1", packing_combo=4, primary_item_attribute="Size")
		with (
			patch.object(frappe, "get_list", return_value=[row(name="GRN-A", lot="LOT-1")]),
			patch.object(frappe, "get_all", side_effect=get_all),
			patch(f"{REPORTS}.attribute_db.get_all", return_value=lots) as lot_query,
			patch.object(frappe.db, "sql", side_effect=sql),
			patch.object(frappe, "get_cached_doc", return_value=ipd),
			patch(f"{REPORTS}.get_ipd_primary_values", side_effect=lambda _name: ["S", "M"]),
			patch(f"{REPORTS}._attribute_value", side_effect=lambda value: value),
		):
			result = reports.get_finishing_dispatch_report("2026-10-01", "2026-10-31")
		self.assertEqual(sorted(queried), sorted(set(queried)))
		lot_query.assert_called_once()
		self.assertEqual(len(attribute_queries), 2)
		by_lot = {entry["lot"]: entry for entry in result["data"]}
		self.assertEqual(by_lot["LOT-1"]["packed_qty"], {"S": 8, "M": 12})
		self.assertEqual(by_lot["LOT-1"]["dispatched_qty"], {"S": 4, "M": 0})
		self.assertEqual(by_lot["LOT-1"]["dispatched_total_boxes"], 1)
		self.assertEqual(by_lot["LOT-2"]["dispatched_qty"], {"S": 0, "M": 6})
		self.assertEqual(by_lot["LOT-2"]["dispatched_total_boxes"], 2)
		self.assertEqual(by_lot["LOT-2"]["pieces_per_box"], "Mixed")
		self.assertEqual(result["sizes"], ["S", "M"])
