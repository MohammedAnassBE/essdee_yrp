from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.link_search import link_search, linked_document_search


class TestLinkSearch(UnitTestCase):
	def test_linked_document_search_returns_only_addresses_for_selected_supplier(self):
		meta = frappe._dict(name="Address", title_field="address_title", search_fields="address_line1")
		meta.has_field = lambda fieldname: fieldname in {"address_title", "address_line1"}

		with (
			patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta),
			patch("essdee_yrp.api.link_search.frappe.has_permission", return_value=True),
			patch(
				"essdee_yrp.api.link_search.frappe.get_all",
				return_value=["SUPPLIER-1-Billing", "SUPPLIER-1-Shipping"],
			) as get_all,
			patch(
				"essdee_yrp.api.link_search.frappe.get_list",
				return_value=[
					frappe._dict(name="SUPPLIER-1-Billing", address_title="Supplier Billing")
				],
			) as get_list,
		):
			rows = linked_document_search("Address", "Supplier", "SUPPLIER-1", "Billing")

		self.assertEqual(rows, [{"name": "SUPPLIER-1-Billing", "label": "Supplier Billing"}])
		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			{
				"parenttype": "Address",
				"link_doctype": "Supplier",
				"link_name": "SUPPLIER-1",
			},
		)
		self.assertEqual(
			get_list.call_args.kwargs["filters"],
			{"name": ["in", ["SUPPLIER-1-Billing", "SUPPLIER-1-Shipping"]]},
		)

	def test_visible_only_search_does_not_match_hidden_search_fields(self):
		meta = frappe._dict(name="SD YRP Lot", title_field=None, search_fields="item")
		meta.has_field = lambda fieldname: fieldname in {"lot_name", "item"}

		with patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta), patch(
			"essdee_yrp.api.link_search.frappe.get_list", return_value=[]
		) as get_list:
			link_search("SD YRP Lot", "TE", match_visible_only=True)

		self.assertEqual(get_list.call_args.kwargs["or_filters"], [["name", "like", "%TE%"]])

	def test_normal_link_search_keeps_configured_search_fields(self):
		meta = frappe._dict(name="SD YRP Lot", title_field=None, search_fields="item")
		meta.has_field = lambda fieldname: fieldname in {"lot_name", "item"}

		with patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta), patch(
			"essdee_yrp.api.link_search.frappe.get_list", return_value=[]
		) as get_list:
			link_search("SD YRP Lot", "Vest")

		self.assertEqual(
			get_list.call_args.kwargs["or_filters"],
			[["name", "like", "%Vest%"], ["item", "like", "%Vest%"]],
		)
