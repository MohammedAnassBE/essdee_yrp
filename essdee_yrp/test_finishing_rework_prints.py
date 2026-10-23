import json
import os
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.api.print import get_desk_print_formats
from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import sd_yrp_grn_rework_item as rework_items

FORMATS = {
	"essdee_rework_print": "Essdee Rework Print",
	"essdee_reworked_print": "Essdee Reworked Print",
}
FORMAT_DIR = os.path.join(os.path.dirname(__file__), "essdee_yrp", "print_format")


def rework_source():
	return frappe._dict(
		name="RW-1",
		grn_number="GRN-1",
		lot="LOT-1",
		item="TSHIRT",
		warehouse="WH-1",
		creation="2026-10-01 09:00:00",
		grn_rework_item_details=[
			frappe._dict(
				name="d1",
				item_variant="V-S",
				received_type="Oil Mark",
				quantity=5,
				reworked=2,
				rejection=1,
				completed=1,
				uom="Nos",
				set_combination="{}",
			),
			frappe._dict(
				name="d2",
				item_variant="V-M",
				received_type="Oil Mark",
				quantity=4,
				reworked=4,
				rejection=0,
				completed=1,
				uom="Nos",
				set_combination="{}",
			),
		],
		check_permission=lambda _ptype: None,
	)


def rework_row(name, variant):
	return frappe._dict(
		name=name,
		item_variant=variant,
		received_type="Oil Mark",
		quantity=1,
		reworked=0,
		rejection=0,
		completed=0,
		uom="Nos",
		set_combination="{}",
	)


@contextmanager
def patched_rework(source, mapped_sizes=("S", "M", "L", "XL")):
	with (
		patch.object(frappe, "has_permission", return_value=True),
		patch.object(rework_items, "get_rework_sources", return_value=[source]),
		patch.object(
			rework_items.attribute_db,
			"get_cached_value",
			side_effect=lambda doctype, _name, fields: (
				"IPD" if doctype == "SD YRP Lot" else ("Colour", "Size", 0, None)
			),
		),
		patch.object(
			rework_items,
			"get_variant_attr_details",
			side_effect=lambda variant: {"Colour": "Red", "Size": variant.split("-", 1)[1]},
		),
		patch(
			"essdee_yrp.finishing.views.get_attribute_details",
			return_value={"primary_attribute_values": list(mapped_sizes)},
		),
	):
		yield


class TestFinishingReworkPrints(TestCase):
	def test_rework_sizes_follow_item_mapping_order(self):
		source = rework_source()
		source.grn_rework_item_details = [
			rework_row("d1", "V-XL"),
			rework_row("d2", "V-L"),
			rework_row("d3", "V-S"),
			rework_row("d4", "V-M"),
		]
		with patched_rework(source):
			data = rework_items.get_rework_items()
		items = data["report_detail"]["RW-1"]["rework_detail"]["Oil Mark-Red"]["items"]
		self.assertEqual([row["Size"] for row in items], ["S", "M", "L", "XL"])

	def test_formats_are_standard_grn_formats(self):
		for folder, name in FORMATS.items():
			with self.subTest(name=name):
				with open(os.path.join(FORMAT_DIR, folder, f"{folder}.json")) as handle:
					data = json.load(handle)
				self.assertEqual(
					(data["name"], data["doc_type"], data["standard"], data["module"]),
					(name, "YRP Goods Received Note", "Yes", "Essdee YRP"),
				)
				self.assertIn("get_rework_items(None, None, None, doc.name,", data["format_data"])

	def test_formats_are_registered_for_grn_printing(self):
		rows = []
		for folder in FORMATS:
			with open(os.path.join(FORMAT_DIR, folder, f"{folder}.json")) as handle:
				rows.append(json.load(handle))
		with (
			patch.object(frappe, "get_all", return_value=rows),
			patch.object(frappe, "get_meta", return_value=frappe._dict(default_print_format="")),
			patch.object(frappe.db, "get_single_value", return_value=0),
		):
			self.assertEqual(get_desk_print_formats("YRP Goods Received Note"), ["Standard", *sorted(FORMATS.values(), key=str.casefold, reverse=True)])

	def test_rework_items_is_a_jinja_method(self):
		self.assertIn(
			"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item.get_rework_items",
			hooks.jinja["methods"],
		)

	def test_rework_items_report_reworked_totals_like_frappe_15(self):
		with patched_rework(rework_source()):
			data, series = rework_items.get_rework_items(grn_number="GRN-1", show_reworked=1)
		detail = data["report_detail"]["RW-1"]
		self.assertEqual(series, "RW-1")
		self.assertEqual((detail["reworked_detail"], detail["total_reworked"]), ({"Oil Mark": 6}, 6))
		self.assertEqual((data["total_reworked_detail"], data["total_reworked"]), ({"Oil Mark": 6}, 6))

	def test_formats_render_for_a_grn_with_rework(self):
		grn = frappe.db.get_value("SD YRP GRN Rework Item", {"completed": 0}, "grn_number")
		if not grn or not frappe.db.exists("Print Format", "Essdee Rework Print"):
			self.skipTest("No pending rework GRN or format not synced on this site")
		html = frappe.get_print("YRP Goods Received Note", grn, "Essdee Rework Print", no_letterhead=1)
		self.assertIn("GRN Rework Item - RW-", html)
		self.assertIn("DIRECTLY OK PCS", html)
