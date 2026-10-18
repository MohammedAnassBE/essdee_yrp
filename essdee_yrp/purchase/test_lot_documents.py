from contextlib import ExitStack
from types import SimpleNamespace
from unittest import SkipTest
from unittest.mock import Mock, patch

import frappe
from frappe.model.meta import get_default_df
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, get_datetime, getdate, to_timedelta

from essdee_yrp.purchase import lot_documents as documents


class TestLotDocuments(FrappeTestCase):
	def test_unreadable_lot_blocks_all_queries(self):
		doc = SimpleNamespace(check_permission=Mock(side_effect=frappe.PermissionError))
		with patch.object(frappe, "get_doc", return_value=doc), patch.object(frappe, "get_all") as query:
			with self.assertRaises(frappe.PermissionError):
				documents.get_lot_documents("private-lot")
			query.assert_not_called()

	def test_permission_denied_section_has_no_rows(self):
		with (
			patch.object(frappe, "has_permission", return_value=False),
			patch.object(frappe, "get_all") as query,
		):
			section = documents._visible_section("LOT", documents.DOCUMENT_SECTIONS["work_orders"])
		self.assertEqual(section, {"permitted": False, "count": 0, "rows": []})
		query.assert_not_called()

	def test_purchase_order_link_paths_are_deduplicated(self):
		with patch.object(documents, "_require_lot_field"), patch.object(frappe, "get_all") as query:
			query.side_effect = [["PO-1", "PO-2", "PO-1"], ["PO-2", "PO-3"], ["PO-1", "PO-4"]]
			self.assertEqual(
				documents._linked_names("LOT", "Purchase Order"), ["PO-1", "PO-2", "PO-3", "PO-4"]
			)
		self.assertEqual(query.call_args_list[0].kwargs["or_filters"], {"lot": "LOT", "default_lot": "LOT"})
		self.assertEqual(query.call_args_list[1].args[0], "SD YRP Lot MultiSelect")
		self.assertEqual(query.call_args_list[1].kwargs["filters"]["parentfield"], "sd_lot")
		self.assertEqual(query.call_args_list[2].args[0], "Purchase Order Item")
		self.assertTrue(all(call.kwargs.get("order_by", "modified desc") is None for call in query.call_args_list))

	def test_visible_query_excludes_cancelled_and_keeps_total_count(self):
		with ExitStack() as stack:
			stack.enter_context(patch.object(frappe, "has_permission", return_value=True))
			stack.enter_context(patch.object(documents, "_linked_names", return_value=["PO-1", "PO-2"]))
			query = stack.enter_context(
				patch.object(
					frappe,
					"get_list",
					side_effect=[
						[frappe._dict(name="PO-2", docstatus=1)],
						[frappe._dict(count=501)],
					],
				)
			)
			section = documents._visible_section("LOT", documents.DOCUMENT_SECTIONS["purchase_orders"])
		self.assertEqual(section["count"], 501)
		self.assertEqual(query.call_count, 2)
		self.assertEqual(query.call_args_list[0].kwargs["limit_page_length"], 500)
		self.assertEqual(query.call_args_list[1].kwargs["fields"], [{"COUNT": "name", "as": "count"}])
		self.assertEqual(query.call_args_list[1].kwargs["filters"], query.call_args_list[0].kwargs["filters"])
		for call in query.call_args_list:
			self.assertEqual(call.kwargs["filters"]["docstatus"], ["!=", 2])

	def test_sort_queries_use_document_dates(self):
		orders = [
			"wo_date desc, modified desc",
			"transaction_date desc, modified desc",
			"posting_date desc, posting_time desc, modified desc",
			"posting_date desc, posting_time desc, modified desc",
		]
		with ExitStack() as stack:
			stack.enter_context(patch.object(frappe, "has_permission", return_value=True))
			stack.enter_context(patch.object(documents, "_linked_names", return_value=["document"]))
			query = stack.enter_context(
				patch.object(
					frappe,
					"get_list",
					side_effect=lambda *args, **kwargs: (
						[frappe._dict(count=0)]
						if kwargs["fields"] == [{"COUNT": "name", "as": "count"}]
						else []
					),
				)
			)
			for section, order in zip(documents.DOCUMENT_SECTIONS.values(), orders, strict=True):
				documents._visible_section("LOT", section)
				self.assertEqual(query.call_args_list[-2].kwargs["order_by"], order)

	def test_detail_rejects_unsupported_doctype(self):
		with patch.object(documents, "_check_lot_permission"), patch.object(frappe, "get_doc") as loader:
			with self.assertRaises(frappe.PermissionError):
				documents.get_lot_document("LOT", "Sales Invoice", "INV")
			loader.assert_not_called()

	def test_detail_rejects_unlinked_document(self):
		doc = frappe._dict(doctype="YRP Work Order", lot="OTHER", check_permission=Mock())
		with ExitStack() as stack:
			stack.enter_context(patch.object(documents, "_check_lot_permission"))
			stack.enter_context(patch.object(documents, "_require_lot_field"))
			stack.enter_context(patch.object(frappe, "get_doc", return_value=doc))
			builder = stack.enter_context(patch.object(documents, "_dialog_payload"))
			with self.assertRaises(frappe.PermissionError):
				documents.get_lot_document("LOT", "YRP Work Order", "WO")
			doc.check_permission.assert_called_once_with("read")
			builder.assert_not_called()

	def test_detail_rejects_unreadable_document(self):
		doc = frappe._dict(check_permission=Mock(side_effect=frappe.PermissionError))
		with (
			patch.object(documents, "_check_lot_permission"),
			patch.object(frappe, "get_doc", return_value=doc),
		):
			with self.assertRaises(frappe.PermissionError):
				documents.get_lot_document("LOT", "Purchase Order", "PO")

	def test_each_purchase_order_link_path_authorizes_detail(self):
		for values in (
			{"lot": "LOT"},
			{"default_lot": "LOT"},
			{"sd_lot": [frappe._dict(lot="LOT")]},
			{"items": [frappe._dict(lot="LOT")]},
		):
			with self.subTest(values=values), patch.object(documents, "_require_lot_field"):
				self.assertTrue(documents._is_linked(frappe._dict(doctype="Purchase Order", **values), "LOT"))

	def test_transaction_header_and_child_links_authorize_detail(self):
		for doctype in ("YRP Delivery Challan", "YRP Goods Received Note"):
			for values in ({"lot": "LOT"}, {"items": [frappe._dict(lot="LOT")]}):
				with (
					self.subTest(doctype=doctype, values=values),
					patch.object(documents, "_require_lot_field"),
				):
					self.assertTrue(documents._is_linked(frappe._dict(doctype=doctype, **values), "LOT"))

	def test_missing_or_wrong_lot_dimension_fails_before_query(self):
		for field in (None, SimpleNamespace(fieldtype="Link", options="SD Lot")):
			with self.subTest(field=field), patch.object(frappe, "get_meta") as meta:
				meta.return_value.get_field.return_value = field
				with self.assertRaises(frappe.ValidationError):
					documents._require_lot_field("Purchase Order Item")

	def test_dialog_batches_link_titles_and_keeps_raw_codes(self):
		details = [
			{"fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "value": "S-1"},
			{"fieldname": "from_warehouse", "fieldtype": "Link", "options": "Warehouse", "value": "W-1"},
			{"fieldname": "to_warehouse", "fieldtype": "Link", "options": "Warehouse", "value": "W-2"},
		]
		doc = frappe._dict(
			doctype="YRP Delivery Challan",
			name="DC-1",
			supplier="S-1",
			meta=SimpleNamespace(get_field=lambda field: None),
		)
		base = {"record": {}, "details": details, "item_row_count": 1, "item_groups": [{"items": []}]}
		with (
			patch.object(documents, "_document_payload", return_value=base),
			patch.object(documents, "_summary", return_value=[]),
			patch.object(frappe.db, "get_default", return_value="INR") as default_currency,
			patch.object(
				frappe,
				"get_all",
				side_effect=[
					[frappe._dict(name="S-1", supplier_name="Supplier One")],
					[
						frappe._dict(name="W-1", warehouse_name="Stores"),
						frappe._dict(name="W-2", warehouse_name="Factory"),
					],
				],
			) as query,
		):
			payload = documents._dialog_payload(doc, "LOT")
		self.assertEqual(query.call_count, 2)
		self.assertEqual(query.call_args_list[0].args, ("Supplier",))
		self.assertEqual(query.call_args_list[1].args, ("Warehouse",))
		self.assertEqual(query.call_args_list[1].kwargs["filters"], {"name": ["in", ["W-1", "W-2"]]})
		self.assertEqual([field["value"] for field in payload["details"]], ["S-1", "W-1", "W-2"])
		self.assertEqual(
			[field["display_value"] for field in payload["details"]], ["Supplier One", "Stores", "Factory"]
		)
		self.assertEqual(payload["record"]["supplier_name"], "Supplier One")
		self.assertEqual(payload["record"]["currency"], "INR")
		default_currency.assert_called_once_with("currency")

	def test_transaction_currency_uses_company_when_field_exists(self):
		doc = frappe._dict(
			doctype="YRP Goods Received Note",
			company="Essdee",
			meta=SimpleNamespace(
				get_field=lambda field: SimpleNamespace(fieldtype="Link", options="Company")
			),
		)
		with (
			patch.object(frappe, "get_cached_value", return_value="INR") as company_currency,
			patch.object(frappe.db, "get_default") as default_currency,
		):
			self.assertEqual(documents._document_currency(doc), "INR")
		company_currency.assert_called_once_with("Company", "Essdee", "default_currency")
		default_currency.assert_not_called()


class TestLiveLotDocuments(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user(self.previous_user)
		super().tearDown()

	def _fixture_lot(self):
		if not frappe.db.exists("SD YRP Lot", "C1225-03"):
			self.skipTest("Live fixture C1225-03 is missing")
		for section in documents.DOCUMENT_SECTIONS.values():
			doctype = section["doctype"]
			if not frappe.get_meta(doctype).get_field("lot"):
				self.skipTest(f"No Lot dimension on {doctype}")
		return "C1225-03"

	def test_live_counts(self):
		lot = self._fixture_lot()
		payload = documents.get_lot_documents(lot)
		links = (
			("work_orders", "YRP Work Order", ("lot",), ()),
			(
				"purchase_orders",
				"Purchase Order",
				("lot", "default_lot"),
				(("SD YRP Lot MultiSelect", "sd_lot"), ("Purchase Order Item", "items")),
			),
			(
				"goods_received_notes",
				"YRP Goods Received Note",
				("lot",),
				(("YRP Goods Received Note Item", "items"),),
			),
			(
				"delivery_challans",
				"YRP Delivery Challan",
				("lot",),
				(("YRP Delivery Challan Item", "items"),),
			),
		)
		for key, doctype, header_fields, child_tables in links:
			with self.subTest(key=key):
				names = self._expected_linked_names(lot, doctype, header_fields, child_tables)
				count = (
					frappe.db.count(doctype, {"name": ["in", names], "docstatus": ["!=", 2]}) if names else 0
				)
				self.assertEqual(payload[key]["count"], count)
		self.assertGreater(payload["purchase_orders"]["count"], 0)

	def _expected_linked_names(self, lot, doctype, header_fields, child_tables):
		names = set(
			frappe.get_all(
				doctype, or_filters={field: lot for field in header_fields}, pluck="name", limit_page_length=0
			)
		)
		for child_doctype, parentfield in child_tables:
			names.update(
				frappe.get_all(
					child_doctype,
					filters={"lot": lot, "parenttype": doctype, "parentfield": parentfield},
					pluck="parent",
					limit_page_length=0,
				)
			)
		return sorted(names)

	def test_live_cancelled_documents_are_excluded(self):
		payload = documents.get_lot_documents(self._fixture_lot())
		for section in payload.values():
			self.assertTrue(all(row["docstatus"] != 2 for row in section["rows"]))

	def test_live_purchase_order_quantity_aggregate(self):
		lot = self._fixture_lot()
		names = documents._linked_names(lot, "Purchase Order")
		if not names:
			self.skipTest("No linked Purchase Orders in fixture")
		items = frappe.get_all(
			"Purchase Order Item",
			filters={"lot": lot, "parent": ["in", names]},
			fields=["parent", "qty"],
			limit_page_length=0,
		)
		if not items:
			self.skipTest("No Purchase Order items carrying this Lot")
		expected = {}
		for row in items:
			expected[row.parent] = expected.get(row.parent, 0) + flt(row.qty)
		actual = documents._purchase_order_quantities(lot, names)
		self.assertEqual(set(actual), set(expected))
		for name, quantity in expected.items():
			self.assertAlmostEqual(actual[name], quantity)

	def test_live_sort_is_newest_first(self):
		payload = documents.get_lot_documents(self._fixture_lot())
		for key, section in payload.items():
			fields = [part.split()[0] for part in documents.DOCUMENT_SECTIONS[key]["order_by"].split(",")]
			meta = frappe.get_meta(documents.DOCUMENT_SECTIONS[key]["doctype"])
			fieldtypes = {
				field: (meta.get_field(field) or get_default_df(field)).fieldtype for field in fields
			}
			values = [
				tuple(self._sort_value(row.get(field), fieldtypes[field]) for field in fields)
				for row in section["rows"]
			]
			self.assertEqual(values, sorted(values, reverse=True))

	def _sort_value(self, value, fieldtype):
		if value is None:
			return (False, None)
		converters = {"Date": getdate, "Time": to_timedelta, "Datetime": get_datetime}
		return (True, converters[fieldtype](value))

	def test_live_linked_documents_load_expected_matrices(self):
		lot = self._fixture_lot()
		sections = documents.get_lot_documents(lot)
		for key, section in sections.items():
			with self.subTest(key=key):
				if not section["rows"]:
					raise SkipTest(f"No {key} fixture documents")
				doctype = documents.DOCUMENT_SECTIONS[key]["doctype"]
				name, payload = self._matrix_fixture_payload(lot, doctype, section["rows"])
				self.assertEqual(payload["record"]["doctype"], doctype)
				self.assertEqual(payload["record"]["name"], name)
				self.assertTrue(payload["details"])
				self.assertTrue(payload["deliverables" if key == "work_orders" else "item_groups"])
				self.assertGreater(payload["item_row_count"], 0)
				if key == "purchase_orders":
					self.assertTrue(payload["record"]["supplier"])

	def _matrix_fixture_payload(self, lot, doctype, rows):
		for row in rows:
			payload = documents.get_lot_document(lot, doctype, row["name"])
			if doctype != "YRP Work Order" or payload["deliverables"]:
				return row["name"], payload
		self.fail(f"No deliverables on any linked {doctype}")
