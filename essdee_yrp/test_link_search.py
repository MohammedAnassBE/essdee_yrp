from unittest.mock import Mock, patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.api.link_search import link_search, linked_document_search


class TestLinkSearch(UnitTestCase):
	def test_attribute_values_prioritize_exact_visible_value_with_parent_permission(self):
		document = Mock()
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc", return_value=document),
			patch.object(frappe, "get_all", return_value=[frappe._dict(attribute_value=value) for value in ("Small Loose", "Small Box", "Small")]),
		):
			self.assertEqual(link_search("Item Attribute Value", "small", {"attribute_name": "Size"}, page_length=2), [{"name": "Small", "label": "Small"}, {"name": "Small Loose", "label": "Small Loose"}])
		document.check_permission.assert_called_once_with("read")

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
			{"name": ["in", ["SUPPLIER-1-Billing", "SUPPLIER-1-Shipping"]], "disabled": 0},
		)

	def test_visible_only_search_matches_search_fields_shown_as_description(self):
		meta = frappe._dict(name="SD YRP Lot", title_field=None, search_fields="item")
		meta.has_field = lambda fieldname: fieldname in {"lot_name", "item"}
		lot = {"name": "C1225-03", "item": "Hamic - Tiger Bermuda"}

		with patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta), patch(
			"essdee_yrp.api.link_search.frappe.get_list", side_effect=[[lot], []]
		) as get_list:
			rows = link_search("SD YRP Lot", "tiger", match_visible_only=True)

		self.assertEqual(rows, [{"name": "C1225-03", "label": "C1225-03", "description": "Hamic - Tiger Bermuda"}])
		self.assertEqual(
			get_list.call_args_list[0].kwargs["or_filters"],
			[["name", "like", "%tiger%"], ["item", "like", "%tiger%"]],
		)
		self.assertEqual(get_list.call_args_list[0].kwargs["fields"], ["name", "item"])
		self.assertEqual(get_list.call_args_list[1].kwargs["fields"], ["name", "item"])

	def test_normal_link_search_keeps_configured_search_fields(self):
		meta = frappe._dict(name="SD YRP Lot", title_field=None, search_fields="item")
		meta.has_field = lambda fieldname: fieldname in {"lot_name", "item"}

		with patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta), patch(
			"essdee_yrp.api.link_search.frappe.get_list", return_value=[]
		) as get_list:
			link_search("SD YRP Lot", "Vest")

		self.assertEqual(
			get_list.call_args_list[0].kwargs["or_filters"],
			[["name", "like", "%Vest%"], ["item", "like", "%Vest%"]],
		)

	def test_exact_name_or_label_precedes_newer_prefixes_without_duplicates(self):
		meta = frappe._dict(name="Item", title_field="item_name", search_fields="item_group")
		meta.has_field = lambda fieldname: fieldname in {"item_name", "item_group"}
		filters = {"has_variants": 1, "variant_of": ["is", "not set"], "disabled": 0}
		newer = [{"name": f"ZZ TEST-{number}", "item_name": f"Polo {number}"} for number in range(20)]
		exact = {"name": "ZZ TEST-Polo", "item_name": "Polo"}
		for normal_rows in (newer, [*newer[:19], exact]):
			with (
				self.subTest(already_in_page=exact in normal_rows),
				patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta),
				patch("essdee_yrp.api.link_search.frappe.get_list", side_effect=[normal_rows, [exact]]) as get_list,
			):
				rows = link_search("Item", "polo", filters)
			self.assertEqual(rows[0], {"name": "ZZ TEST-Polo", "label": "Polo"})
			self.assertEqual(len(rows), 20)
			self.assertEqual(len({row["name"] for row in rows}), 20)
			self.assertEqual([row["name"] for row in rows[1:]], [row["name"] for row in newer[:19]])
			for call in get_list.call_args_list:
				self.assertEqual(call.args, ("Item",))
				self.assertEqual(call.kwargs["filters"], filters)
				self.assertEqual(call.kwargs["order_by"], "modified desc")
			self.assertEqual(get_list.call_args.kwargs["or_filters"], [["name", "=", "polo"], ["item_name", "=", "polo"]])

	def test_no_exact_match_preserves_rows_order_filters_and_limit(self):
		meta = frappe._dict(name="YRP Production Term", title_field=None, search_fields=None)
		meta.has_field = lambda _fieldname: False
		expected = [{"name": "ZZ TEST-Term 2"}, {"name": "ZZ TEST-Term 1"}]
		with (
			patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta),
			patch("essdee_yrp.api.link_search.frappe.get_list", side_effect=[expected, []]) as get_list,
		):
			rows = link_search("YRP Production Term", "Term", [["docstatus", "=", 1]], page_length=2)
		self.assertEqual(rows, [{**row, "label": row["name"]} for row in expected])
		for call in get_list.call_args_list:
			self.assertEqual(call.kwargs["filters"], [["docstatus", "=", 1]])
			self.assertEqual(call.kwargs["limit_page_length"], 2)

	def test_empty_search_keeps_single_modified_order_query(self):
		meta = frappe._dict(name="Item", title_field=None, search_fields=None)
		meta.has_field = lambda _fieldname: False
		with (
			patch("essdee_yrp.api.link_search.frappe.get_meta", return_value=meta),
			patch("essdee_yrp.api.link_search.frappe.get_list", return_value=[]) as get_list,
		):
			self.assertEqual(link_search("Item"), [])
		get_list.assert_called_once()
		self.assertIsNone(get_list.call_args.kwargs["or_filters"])
