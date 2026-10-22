from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import print_helpers


class TestDeliveryChallanPrint(IntegrationTestCase):
	"""The Essdee Delivery Challan print reads like F15's Delivery Challan print."""

	def make_doc(self, **values):
		doc = frappe.new_doc("YRP Delivery Challan")
		doc.update(values)
		return doc

	def test_stored_party_names_and_address_snapshots_are_printed(self):
		doc = self.make_doc(
			from_location="FROM",
			from_location_name="Stored From",
			from_address_details="Stored from address",
			supplier="TO",
			supplier_name="Stored To",
			supplier_address_details="Stored to address",
			letter_head="Doc Head",
		)
		with patch.object(print_helpers, "get_supplier_address_display", return_value="Primary"):
			print_helpers.prepare_delivery_challan_print(doc)
		self.assertEqual(doc.from_location_name, "Stored From")
		self.assertEqual(doc.from_address_details, "Stored from address")
		self.assertEqual(doc.supplier_name, "Stored To")
		self.assertEqual(doc.supplier_address_details, "Stored to address")
		self.assertEqual(doc.letter_head, "Doc Head")

	def test_missing_snapshots_fall_back_to_address_link_then_party_address(self):
		doc = self.make_doc(from_location="FROM", from_address="FROM-Billing", supplier="TO")
		with (
			patch.object(print_helpers, "_supplier_name", side_effect=lambda party: f"{party} name"),
			patch.object(
				print_helpers,
				"_address_display",
				side_effect=lambda address: f"{address} display" if address else "",
			),
			patch.object(
				print_helpers, "get_supplier_address_display", side_effect=lambda party: f"{party} primary"
			),
		):
			print_helpers.prepare_delivery_challan_print(doc)
		self.assertEqual(doc.from_location_name, "FROM name")
		self.assertEqual(doc.from_address_details, "FROM-Billing display")
		self.assertEqual(doc.supplier_name, "TO name")
		self.assertEqual(doc.supplier_address_details, "TO primary")

	def test_letter_head_falls_back_to_dc_grn_setting(self):
		doc = self.make_doc(letter_head=None)
		with patch.object(frappe.db, "get_single_value", return_value="MRP Head") as get_single_value:
			self.assertEqual(print_helpers.get_dc_grn_letter_head(doc), "MRP Head")
		get_single_value.assert_called_once_with("SD YRP MRP Settings", "dc_grn_letter_head")
		doc.letter_head = "Doc Head"
		self.assertEqual(print_helpers.get_dc_grn_letter_head(doc), "Doc Head")

	def get_structure(self, groups):
		doc = self.make_doc(items=[])
		with (
			patch.object(frappe, "get_doc", return_value=doc),
			patch.object(print_helpers, "_group_items", return_value=groups),
		):
			return print_helpers.get_dc_structure("DC-TEST")[0]

	def test_attributes_sort_once_a_second_row_is_grouped(self):
		groups = self.get_structure([{"attributes": ["Panel", "Colour", "Stage"], "items": [{}, {}]}])
		self.assertEqual(groups[0]["attributes"], ["Colour", "Panel", "Stage"])

	def test_single_row_keeps_item_attribute_order(self):
		groups = self.get_structure([{"attributes": ["Panel", "Colour"], "items": [{}]}])
		self.assertEqual(groups[0]["attributes"], ["Panel", "Colour"])
