from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt
from yrp.attribute_links import value as attribute_value

from essdee_yrp.essdee_yrp.doctype.sd_yrp_item_conversion.test_sd_yrp_item_conversion import (
	find_stocked_variant,
)
from essdee_yrp.fabric_store.documents import item_conversion

SIZED = {
	"attributes": ["Colour"],
	"primary_attribute": "Size",
	"primary_attribute_values": ["S", "M"],
	"default_uom": "Nos",
	"secondary_uom": None,
}


class TestItemConversionWebEditor(IntegrationTestCase):
	def side_details(self, side):
		with patch.object(item_conversion, "get_attribute_details", return_value=SIZED):
			return item_conversion.get_side_item_details("from", side)

	def test_side_builds_the_desk_grouped_item_json(self):
		groups = self.side_details(
			{
				"item": "Tee",
				"attributes": {"Colour": "Red", "Extra": "x"},
				"primary_value": "M",
				"qty": 3,
				"lot": "L1",
				"received_type": "Accepted",
			}
		)
		self.assertEqual(len(groups), 1)
		self.assertEqual(len(groups[0]["items"]), 1)
		item = groups[0]["items"][0]
		self.assertEqual(item["attributes"], {"Colour": "Red"})
		self.assertEqual(item["values"], {"M": {"qty": 3, "rate": 0, "secondary_qty": 0}})
		self.assertEqual((item["name"], item["lot"], item["default_uom"]), ("Tee", "L1", "Nos"))

	def test_side_requires_item_quantity_and_size(self):
		for side, message in (
			({"qty": 1}, "Select the From Item"),
			({"item": "Tee", "qty": 0, "primary_value": "M"}, "Enter the From Quantity"),
			({"item": "Tee", "qty": 1}, "Select the From Size"),
		):
			with self.subTest(message=message), self.assertRaisesRegex(frappe.ValidationError, message):
				self.side_details(side)

	def test_create_edit_submit_cancel_and_amend_round_trip(self):
		source = find_stocked_variant()
		if not source:
			self.skipTest("Item Conversion web test needs a valued stock Bin")
		variant = frappe.get_doc("Item", source.item_code)
		details = item_conversion.get_attribute_details(source.variant_of)
		values = {entry.attribute: attribute_value(entry.attribute_value) for entry in variant.attributes}
		primary = details.get("primary_attribute")
		side = {
			"item": source.variant_of,
			"attributes": {attribute: values.get(attribute) for attribute in details["attributes"]},
			"primary_value": values.get(primary) if primary else None,
			"lot": source.lot,
			"received_type": source.received_type,
			"qty": 1,
		}
		header = {
			"warehouse": source.warehouse,
			"posting_date": frappe.utils.nowdate(),
			"posting_time": "10:00:00",
		}

		draft = item_conversion.save_item_conversion({**header, "from": side, "to": {**side, "qty": 2}})
		name = draft["record"]["name"]
		self.assertEqual(draft["sides"]["from"]["variant"], source.item_code)
		self.assertEqual(flt(draft["sides"]["to"]["qty"]), 2)
		self.assertEqual(draft["totals"]["difference_amount"], 0)

		edited = item_conversion.save_item_conversion(
			{**header, "from": side, "to": {**side, "qty": 4}},
			name=name,
			expected_modified=draft["record"]["modified"],
		)
		doc = frappe.get_doc(item_conversion.DOCTYPE, name)
		self.assertEqual((len(doc.from_items), len(doc.to_items)), (1, 1))
		self.assertEqual(flt(doc.to_items[0].qty), 4)
		self.assertEqual(doc.from_item, source.variant_of)

		submitted = item_conversion.change_item_conversion_status(
			name, "submit", edited["record"]["modified"]
		)
		self.assertEqual(submitted["record"]["docstatus"], 1)
		cancelled = item_conversion.change_item_conversion_status(
			name, "cancel", submitted["record"]["modified"]
		)
		self.assertEqual(cancelled["record"]["docstatus"], 2)
		amended = item_conversion.change_item_conversion_status(
			name, "amend", cancelled["record"]["modified"]
		)
		self.assertEqual(amended["record"]["amended_from"], name)
		self.assertEqual(amended["sides"]["to"]["variant"], source.item_code)
