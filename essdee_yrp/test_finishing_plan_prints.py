from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.finishing import inward, ocr

IPD = frappe._dict(
	primary_item_attribute="Size",
	packing_attribute="Colour",
	set_item_attribute="Part",
	is_set_item=0,
)
VARIANTS = {"Olive-S": {"Size": "S", "Colour": "Olive"}, "Liver-S": {"Size": "S", "Colour": "Liver"}}


def _calculated_row(variant, received):
	return frappe._dict(
		item_variant=variant,
		set_combination=frappe.as_json({"major_colour": VARIANTS[variant]["Colour"]}),
		received_type_json=frappe.as_json(received),
	)


def _inspection(supplier, supplier_name, result):
	return frappe._dict(
		supplier=supplier,
		supplier_name=supplier_name,
		result=result,
		essdee_quality_inspection_colours=[frappe._dict(selected=1, colour="Rose")],
		essdee_quality_inspection_sizes=[frappe._dict(selected=1, size="S")],
	)


@patch("essdee_yrp.finishing.inward.get_variant_attr_details", side_effect=VARIANTS.get)
class TestFinishingInwardPrintData(IntegrationTestCase):
	def test_received_colour_without_cutting_rows_has_zero_cut_quantity(self, _attributes):
		data = {}
		inward._add_inward_rows(
			data,
			[_calculated_row("Liver-S", {"Accepted": 2})],
			IPD,
			"S",
			"Rejected",
			["Accepted"],
			cutting=False,
		)
		inward._add_inward_rows(
			data, [_calculated_row("Olive-S", {})], IPD, "S", "Rejected", ["Accepted"], cutting=True
		)

		self.assertEqual(data["item"]["cut_detail"], {"Liver": 0, "Olive": 0})
		self.assertEqual(data["item"]["colours"]["Olive"]["sewing_received"], 0)


class TestFinishingInwardEqiCheck(IntegrationTestCase):
	@patch("essdee_yrp.finishing.inward._attribute_value", side_effect=lambda value: value)
	@patch("essdee_yrp.finishing.inward.frappe.get_all", return_value=["EQI-1"])
	@patch("essdee_yrp.finishing.inward.frappe.get_doc", return_value=_inspection("S-0174", None, "Fail"))
	def test_failed_inspection_without_supplier_name_names_the_supplier(self, *_mocks):
		self.assertEqual(inward.get_eqi_status(["WO-1"]), {"S-0174": {"Rose": {"S": "Fail"}}})

		with (
			patch("essdee_yrp.finishing.inward.frappe.db.get_value", return_value="LOT-1"),
			patch("essdee_yrp.finishing.inward.frappe.db.get_single_value", return_value="Stitching"),
			patch("essdee_yrp.finishing.rebuild.get_process_work_orders", return_value=["WO-1"]),
			self.assertRaisesRegex(frappe.ValidationError, "EQI not passed for Size S: S-0174"),
		):
			inward.check_eqi_status("S", "FP-1")


class TestFinishingOcrPrintData(IntegrationTestCase):
	def test_sizes_missing_from_the_plan_render_as_zero(self):
		part = ocr._empty_part()
		part["total"]["S"] = ocr._empty_size()
		part["data"]["Olive"] = {"values": {"S": ocr._empty_cell()}, "colour_total": ocr._empty_cell()}
		doc = frappe._dict(production_detail="IPD-1", check_permission=lambda _ptype: None)
		with (
			patch("essdee_yrp.finishing.ocr.frappe.get_doc", return_value=doc),
			patch("essdee_yrp.finishing.ocr.get_ocr_details", return_value={"Item": part}),
			patch("essdee_yrp.finishing.ocr.get_ipd_primary_values", return_value=["S", "M"]),
		):
			ocr_data, metrics, sizes = ocr.get_fp_ocr_details("FP-1")

		self.assertEqual(sizes, ["S", "M"])
		self.assertEqual(ocr_data["Item"]["total"]["M"], ocr._empty_size())
		self.assertEqual(ocr_data["Item"]["data"]["Olive"]["values"]["M"], ocr._empty_cell())
		self.assertEqual(metrics["get_total_difference"]["Item"]["M"], 0)
