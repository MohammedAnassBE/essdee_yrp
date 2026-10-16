from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.utils import flt, nowdate, nowtime
from yrp.stock.dimensions import get_dimension_fieldnames, get_stock_dimensions
from yrp.yrp.doctype.yrp_item.yrp_item import get_parent_item
from yrp.yrp_stock.doctype.yrp_stock_entry.yrp_stock_entry import make_stock_in_entry

from essdee_yrp import stock_entry_hooks
from essdee_yrp.fabric_store import web_workspace as workspace
from essdee_yrp.fabric_store.documents import delivery_challan


def document(**values):
	result = SimpleNamespace(**values)
	result.get = lambda key, default=None: getattr(result, key, default)
	result.set = lambda key, value: setattr(result, key, value)
	result.update = lambda data: result.__dict__.update(data)
	result.append = lambda key, value: getattr(result, key).append(frappe._dict(value))
	return result


class TestFabricStoreWebFixes(TestCase):
	def setUp(self):
		self.enterContext(patch.object(workspace, "_", side_effect=lambda text: text))
		self.enterContext(patch.object(delivery_challan, "_", side_effect=lambda text: text))
		self.enterContext(patch.object(stock_entry_hooks, "_", side_effect=lambda text: text))
		self.enterContext(patch.object(frappe, "throw", side_effect=lambda message, *args, **kwargs: self.fail_validation(message)))

	@staticmethod
	def fail_validation(message):
		raise frappe.ValidationError(message)

	def test_missing_address_message_for_both_parties_and_desk_hook(self):
		from essdee_yrp import hooks

		self.assertIn(
			"essdee_yrp.fabric_store.documents.delivery_challan.validate_location_addresses",
			hooks.doc_events["YRP Delivery Challan"]["before_validate"],
		)
		for party_field, address_field in (("from_location", "from_address"), ("supplier", "supplier_address")):
			with (
				self.subTest(party_field=party_field),
				patch.object(frappe.db, "exists", return_value=False),
				patch.object(frappe.db, "get_value", return_value="Essdee Fabric Store - Tiruppur"),
			):
				draft = document(**{party_field: "S-0005", address_field: ""})
				with self.assertRaisesRegex(frappe.ValidationError, r"No address is linked to Essdee Fabric Store - Tiruppur \(S-0005\). Create an address for this location first\."):
					delivery_challan.validate_location_addresses(draft)
				with self.assertRaisesRegex(frappe.ValidationError, "No address is linked"):
					delivery_challan._validate_and_sync_party_dependencies(draft)

	def test_location_address_status_checks_supplier_permission(self):
		supplier = document(supplier_name="Essdee Fabric Store - Tiruppur")
		supplier.check_permission = MagicMock()
		with (
			patch.object(frappe, "get_doc", return_value=supplier),
			patch.object(delivery_challan, "location_has_address", return_value=False),
			patch.object(frappe.db, "get_value", return_value=supplier.supplier_name),
		):
			status = workspace.get_location_address_status("S-0005")
		self.assertEqual(status["party"], "S-0005")
		self.assertIn("Essdee Fabric Store - Tiruppur (S-0005)", status["message"])
		supplier.check_permission.assert_called_once_with("read")

	def test_existing_linked_address_is_allowed_and_wrong_address_is_rejected(self):
		with patch.object(frappe.db, "exists", return_value=True):
			delivery_challan.validate_location_addresses(document(from_location="UNIT", from_address="ADDRESS"))
		with patch.object(frappe.db, "exists", return_value=False):
			with self.assertRaisesRegex(frappe.ValidationError, "is not linked to UNIT"):
				delivery_challan._address_display_for_party("WRONG", "UNIT", "From Address")

	def test_new_operation_defaults_and_posting_metadata(self):
		metadata = MagicMock()
		metadata.get_field.side_effect = lambda fieldname: frappe._dict(label=fieldname.replace("_", " ").title(), reqd=1)
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_meta", return_value=metadata),
			patch.object(workspace, "_fabric_stock_dimensions", return_value=[]),
			patch.object(workspace, "nowdate", return_value="2026-10-15"),
			patch.object(workspace, "nowtime", return_value="12:34:56"),
		):
			for operation in workspace.STOCK_OPERATION_DOCTYPES:
				editor = workspace.get_stock_operation_editor(operation)
				self.assertEqual(editor["defaults"]["posting_date"], "2026-10-15")
				self.assertEqual(editor["defaults"]["posting_time"], "12:34:56")
				self.assertEqual(editor["defaults"]["edit_posting_date_and_time"], 0)
				self.assertEqual(len(editor["posting_fields"]), 2)
				self.assertTrue(all(field["reqd"] for field in editor["posting_fields"]))

	def test_transit_actions_status_and_received_entries(self):
		source = document(doctype="YRP Stock Entry", name="SEND-1", docstatus=1, purpose="Send to Warehouse", skip_transit=0, per_transferred=0)
		with patch.object(frappe, "has_permission", return_value=True), patch.object(frappe, "get_list", return_value=[{"name": "RECEIVE-1", "docstatus": 1}]) as get_list:
			for percentage, skipped, status, allowed in (
				(0, 0, "In transit · 0% received", True),
				(40, 0, "Partly received · 40%", True),
				(100, 0, "Received", False),
				(0, 1, "Transit skipped", False),
			):
				source.per_transferred = percentage
				source.skip_transit = skipped
				self.assertEqual(workspace._document_actions(source)["can_end_transit"], allowed)
				self.assertEqual(workspace._stock_transit_details(source)["status"], status)
				self.assertEqual(get_list.call_args.kwargs["filters"], {"outgoing_stock_entry": source.name, "docstatus": ["!=", 2]})
			source.skip_transit = 0
			with patch.object(frappe, "has_permission", return_value=False):
				self.assertFalse(workspace._document_actions(source)["can_end_transit"])
			source.docstatus = 0
			self.assertEqual(workspace._document_actions(source), {})

	def test_receiving_purpose_requires_valid_source_and_is_locked(self):
		source = document(doctype="YRP Stock Entry", name="SEND", docstatus=1, purpose="Send to Warehouse", skip_transit=0, per_transferred=0)
		with patch.object(workspace, "_get_supported_document", return_value=source):
			with self.assertRaisesRegex(frappe.ValidationError, "through End Transit"):
				workspace._validate_stock_operation_options("stock_entry", {"purpose": "Receive at Warehouse"})
			for fieldname, value in (("docstatus", 0), ("skip_transit", 1), ("per_transferred", 100), ("purpose", "Material Issue")):
				original = getattr(source, fieldname)
				setattr(source, fieldname, value)
				with self.assertRaisesRegex(frappe.ValidationError, "no pending stock"):
					workspace._validate_stock_operation_options("stock_entry", {"purpose": "Receive at Warehouse", "outgoing_stock_entry": "SEND"})
				setattr(source, fieldname, original)
			workspace._validate_stock_operation_options("stock_entry", {"purpose": "Receive at Warehouse", "outgoing_stock_entry": "SEND"})
			workspace._validate_stock_operation_options("stock_entry", {"purpose": "Material Receipt"})
			for purpose in ("DC Completion", "GRN Completion", "Stock Dispatch"):
				with self.assertRaisesRegex(frappe.ValidationError, "supported Stock Entry purpose"):
					workspace._validate_stock_operation_options("stock_entry", {"purpose": purpose})
			with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
				workspace._validate_stock_operation_options("stock_entry", {"purpose": "Material Issue"}, existing_doc=document(purpose="Receive at Warehouse", outgoing_stock_entry="SEND"))

	def test_end_transit_delegates_to_native_mapper_without_saving(self):
		mapped = document(purpose="Receive at Warehouse", outgoing_stock_entry="SEND", from_warehouse="FROM", to_warehouse="TO", posting_date="2026-10-15", posting_time="12:00:00")
		groups = [{"items": [{"name": "Yarn"}]}]
		mapped.get_onload = lambda fieldname: groups
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(workspace, "_transit_source", return_value=document(name="SEND")),
			patch.object(workspace, "get_stock_operation_editor", return_value={"permissions": {"can_create": True}}),
			patch("yrp.yrp_stock.doctype.yrp_stock_entry.yrp_stock_entry.make_stock_in_entry", return_value=mapped) as mapper,
		):
			editor = workspace.end_stock_entry_transit("SEND")
		mapper.assert_called_once_with("SEND")
		self.assertEqual(editor["item_groups"], groups)
		self.assertTrue(editor["purpose_locked"])
		self.assertEqual(editor["defaults"]["outgoing_stock_entry"], "SEND")

	def test_receipt_preserves_mapped_links_rates_and_dimensions(self):
		row = frappe._dict(item="YARN", qty=10, rate=45, lot="LOT", ste_detail="DETAIL", against_stock_entry="SEND")
		row.as_dict = lambda: dict(row)
		mapped = document(items=[row], outgoing_stock_entry="SEND", from_warehouse="FROM", to_warehouse="TO", skip_transit=0)
		draft = document(items=[])
		with (
			patch("yrp.yrp_stock.doctype.yrp_stock_entry.yrp_stock_entry.make_stock_in_entry", return_value=mapped),
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=["lot"]),
			patch.object(workspace, "ungroup_items_from_ui", return_value=[{"item": "YARN", "qty": 4, "rate": 999, "lot": "LOT"}]),
		):
			workspace._set_transit_receipt_items(draft, [{"items": []}], "SEND")
		self.assertEqual(draft.items[0].qty, 4)
		self.assertEqual(draft.items[0].rate, 45)
		self.assertEqual(draft.items[0].ste_detail, "DETAIL")
		self.assertEqual(draft.items[0].against_stock_entry, "SEND")
		self.assertEqual(draft.items[0].lot, "LOT")
		self.assertEqual(frappe.parse_json(draft.item_details), [{"items": []}])
		self.assertEqual(draft.from_warehouse, "FROM")

	def test_web_receipt_inserts_the_native_mapped_document_and_preserves_its_headers(self):
		row = frappe._dict(item="YARN", qty=10, rate=45, ste_detail="DETAIL", against_stock_entry="SEND")
		row.as_dict = lambda: dict(row)
		mapped = document(name="RECEIPT", purpose="Receive at Warehouse", items=[row], outgoing_stock_entry="SEND", from_warehouse="FROM", to_warehouse="TO", skip_transit=0, additional_amount=17, terms_and_condition="TERMS")
		mapped.insert = MagicMock()
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(workspace, "_transit_source"),
			patch.object(workspace, "get_document", return_value={"record": {"name": "RECEIPT"}}),
			patch("yrp.yrp_stock.doctype.yrp_stock_entry.yrp_stock_entry.make_stock_in_entry", return_value=mapped) as mapper,
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=[]),
			patch.object(workspace, "ungroup_items_from_ui", return_value=[{"item": "YARN", "qty": 10}]),
		):
			workspace.save_stock_operation("stock_entry", {"purpose": "Receive at Warehouse", "outgoing_stock_entry": "SEND", "from_warehouse": "FORGED", "to_warehouse": "FORGED", "skip_transit": 1, "item_details": [{"items": []}]})
		mapper.assert_called_once_with("SEND")
		mapped.insert.assert_called_once_with()
		self.assertEqual(mapped.from_warehouse, "FROM")
		self.assertEqual(mapped.to_warehouse, "TO")
		self.assertEqual(mapped.skip_transit, 0)
		self.assertEqual(mapped.additional_amount, 17)
		self.assertEqual(mapped.terms_and_condition, "TERMS")
		self.assertEqual(frappe.parse_json(mapped.item_details), [{"items": []}])

	def test_receipt_rejects_forged_items_dimensions_and_excess_quantity(self):
		for requested in ({"item": "OTHER", "qty": 1, "lot": "LOT"}, {"item": "YARN", "qty": 1, "lot": "OTHER"}, {"item": "YARN", "qty": 11, "lot": "LOT"}, {"item": "YARN", "qty": -1, "lot": "LOT"}):
			row = frappe._dict(item="YARN", qty=10, lot="LOT")
			with (
				patch("yrp.yrp_stock.doctype.yrp_stock_entry.yrp_stock_entry.make_stock_in_entry", return_value=document(items=[row])),
				patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=["lot"]),
				patch.object(workspace, "ungroup_items_from_ui", return_value=[requested]),
				self.assertRaises(frappe.ValidationError),
			):
				workspace._set_transit_receipt_items(document(items=[]), [{}], "SEND")

	def test_transit_submit_guard_locks_and_requires_submitted_transit_source(self):
		from essdee_yrp import hooks

		self.assertEqual(hooks.doc_events["YRP Stock Entry"]["before_submit"], "essdee_yrp.stock_entry_hooks.before_submit")
		source = document(name="SEND", docstatus=1, purpose="Send to Warehouse", skip_transit=0, items=[])
		receipt = document(name="RECEIVE", purpose="Receive at Warehouse", outgoing_stock_entry="SEND", items=[], against=None)
		with patch.object(frappe, "get_doc", return_value=source) as get_doc:
			for fieldname, value in (("docstatus", 0), ("docstatus", 2), ("purpose", "Material Receipt"), ("skip_transit", 1)):
				original = source.get(fieldname)
				setattr(source, fieldname, value)
				with self.subTest(fieldname=fieldname, value=value), self.assertRaisesRegex(frappe.ValidationError, "must be a submitted Send to Warehouse with transit enabled"):
					stock_entry_hooks.before_submit(receipt)
				setattr(source, fieldname, original)
			stock_entry_hooks.before_submit(receipt)
			get_doc.assert_called_with("YRP Stock Entry", "SEND", for_update=True)

	def test_transit_submit_guard_rejects_unlinked_rows_and_sums_own_rows(self):
		source = document(name="SEND", docstatus=1, purpose="Send to Warehouse", skip_transit=0, items=[frappe._dict(name="DETAIL", item="YARN", qty=10)])
		row = frappe._dict(idx=1, item="YARN", qty=6, against_stock_entry="SEND", ste_detail="DETAIL")
		receipt = document(name="RECEIVE", purpose="Receive at Warehouse", outgoing_stock_entry="SEND", items=[row], against=None)
		with (
			patch.object(frappe, "get_doc", return_value=source),
			patch.object(frappe.db, "sql", return_value=[[4]]) as query,
		):
			for fieldname, value in (("ste_detail", None), ("ste_detail", "FOREIGN"), ("against_stock_entry", "OTHER"), ("item", "OTHER")):
				original = row[fieldname]
				row[fieldname] = value
				with self.subTest(fieldname=fieldname, value=value), self.assertRaisesRegex(frappe.ValidationError, "must come from the outgoing Stock Entry"):
					stock_entry_hooks.before_submit(receipt)
				row[fieldname] = original
			query.assert_not_called()
			stock_entry_hooks.before_submit(receipt)
			statement, parameters = query.call_args.args
			self.assertEqual(parameters, ("SEND", "DETAIL", "RECEIVE"))
			for clause in ("SUM(qty)", "against_stock_entry = %s", "ste_detail = %s", "docstatus = 1", "parent != %s"):
				self.assertIn(clause, statement)
			row.qty = 6.0000005
			stock_entry_hooks.before_submit(receipt)
			row.qty = 4
			receipt.items.append(frappe._dict({**row, "idx": 2, "qty": 3}))
			with self.assertRaisesRegex(frappe.ValidationError, r"Row #1: Item YARN: receiving quantity 7\.0 exceeds the quantity still in transit 6\.0\."):
				stock_entry_hooks.before_submit(receipt)
			receipt.items[1].qty = 2
			stock_entry_hooks.before_submit(receipt)


class TestFabricStoreTransitIntegration(TestCase):
	def setUp(self):
		self.savepoint = f"fabric_transit_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(self.savepoint)
		self.addCleanup(lambda: frappe.db.rollback(save_point=self.savepoint))
		self.warehouses = [self.make_warehouse(label) for label in ("From", "To", "Transit")]
		original_get_single_value = frappe.db.get_single_value
		self.enterContext(patch.object(frappe.db, "get_single_value", side_effect=lambda doctype, fieldname, *args, **kwargs: self.warehouses[2] if (doctype, fieldname) == ("YRP Stock Settings", "transit_warehouse") else original_get_single_value(doctype, fieldname, *args, **kwargs)))
		self.item = frappe.db.sql("SELECT name FROM tabItem WHERE is_stock_item = 1 AND (COALESCE(variant_of, '') != '' OR COALESCE(has_variants, 0) = 0) ORDER BY creation LIMIT 1")[0][0]
		self.dimensions = {}
		for dimension in get_stock_dimensions():
			value = frappe.db.get_value(dimension["dimension_doctype"], {}, "name")
			if value:
				self.dimensions[dimension["fieldname"]] = value
		self.uom = frappe.db.get_value("Item", get_parent_item(self.item), "stock_uom")
		self.make_entry("Material Receipt", qty=100).submit()

	def make_warehouse(self, label):
		return frappe.get_doc({"doctype": "Warehouse", "warehouse_name": f"Web Transit {label} {frappe.generate_hash(length=8)}", "company": frappe.db.get_value("Company", {}, "name")}).insert().name

	def make_entry(self, purpose, qty=10, skip_transit=0):
		return frappe.get_doc({
			"doctype": "YRP Stock Entry", "purpose": purpose,
			"from_warehouse": self.warehouses[0] if purpose == "Send to Warehouse" else None,
			"to_warehouse": self.warehouses[1] if purpose == "Send to Warehouse" else self.warehouses[0],
			"skip_transit": skip_transit,
			"items": [{"item": self.item, "qty": qty, "rate": 45, "uom": self.uom, "row_index": 0, "table_index": 0, **self.dimensions}],
		}).insert()

	def make_receiving_draft(self, source, fraction=1):
		editor = workspace.end_stock_entry_transit(source.name)
		for group in editor["item_groups"]:
			for item in group["items"]:
				for value in item["values"].values():
					value["qty"] = flt(value["qty"]) * fraction
		payload = workspace.save_stock_operation("stock_entry", {**editor["defaults"], "item_details": editor["item_groups"]})
		return frappe.get_doc("YRP Stock Entry", payload["record"]["name"])

	def test_saved_full_receipts_cannot_over_receive_on_desk_or_web_submit(self):
		for submit_from_web in (False, True):
			with self.subTest(submit_from_web=submit_from_web):
				source = self.make_entry("Send to Warehouse")
				source.submit()
				self.make_entry("Send to Warehouse").submit()
				first = self.make_receiving_draft(source)
				second = self.make_receiving_draft(source)
				self.assertEqual([first.docstatus, second.docstatus], [0, 0])
				workspace.change_document_status(first.doctype, first.name, "submit", expected_modified=str(first.modified))
				first.reload()
				self.assertEqual(first.docstatus, 1)
				with self.assertRaisesRegex(frappe.ValidationError, r"Row #1: Item .*: receiving quantity 10\.0 exceeds the quantity still in transit 0\.0\."):
					if submit_from_web:
						workspace.change_document_status(second.doctype, second.name, "submit", expected_modified=str(second.modified))
					else:
						second.submit()
				second.reload()
				source.reload()
				self.assertEqual(second.docstatus, 0)
				self.assertEqual(flt(source.per_transferred), 100)

	def test_saved_partial_receipts_that_fit_both_submit(self):
		source = self.make_entry("Send to Warehouse")
		source.submit()
		first = self.make_receiving_draft(source, 0.4)
		second = self.make_receiving_draft(source, 0.6)
		self.assertEqual([first.docstatus, second.docstatus], [0, 0])
		first.submit()
		workspace.change_document_status(second.doctype, second.name, "submit", expected_modified=str(second.modified))
		second.reload()
		source.reload()
		self.assertEqual([first.docstatus, second.docstatus], [1, 1])
		self.assertEqual(flt(source.per_transferred), 100)
		self.assertEqual(flt(source.items[0].transferred_qty), 10)

	def test_web_receipt_matches_desk_then_submit_partial_full_and_cancel(self):
		source = self.make_entry("Send to Warehouse")
		source.submit()
		editor = workspace.end_stock_entry_transit(source.name)
		desk = make_stock_in_entry(source.name)
		posting = {"posting_date": nowdate(), "posting_time": nowtime(), "edit_posting_date_and_time": 1}
		desk.update(posting)
		desk.item_details = frappe.as_json(desk.get_onload("item_details"))
		desk.insert()
		desk.reload()
		payload = workspace.save_stock_operation("stock_entry", {**editor["defaults"], **posting, "item_details": editor["item_groups"]})
		receipt = frappe.get_doc("YRP Stock Entry", payload["record"]["name"])
		for fieldname in ("purpose", "outgoing_stock_entry", "from_warehouse", "to_warehouse", "skip_transit", *posting):
			self.assertEqual(receipt.get(fieldname), desk.get(fieldname), fieldname)
		self.assertEqual(frappe.parse_json(receipt.item_details), frappe.parse_json(desk.item_details))
		self.assertEqual(frappe.parse_json(receipt.item_details), editor["item_groups"])
		row_fields = ("item", "against_stock_entry", "ste_detail", "qty", "rate", "uom", "conversion_factor", "stock_qty", "row_index", "table_index", *get_dimension_fieldnames())
		self.assertEqual([{key: row.get(key) for key in row_fields} for row in receipt.items], [{key: row.get(key) for key in row_fields} for row in desk.items])
		partial = workspace.get_stock_operation_editor("stock_entry", receipt.name)
		for group in partial["item_groups"]:
			for item in group["items"]:
				for value in item["values"].values():
					value["qty"] = flt(value["qty"]) * 0.4
		workspace.save_stock_operation("stock_entry", {**partial["defaults"], "item_details": partial["item_groups"]}, name=receipt.name, submit=True, expected_modified=str(receipt.modified))
		receipt.reload()
		self.assertEqual(frappe.parse_json(receipt.item_details), partial["item_groups"])
		source.reload()
		self.assertEqual(flt(source.per_transferred), 40)
		self.assertTrue(workspace._document_actions(source)["can_end_transit"])
		self.assertEqual(workspace._stock_transit_details(source)["status"], "Partly received · 40%")
		ledger = frappe.get_all("YRP Stock Ledger Entry", filters={"voucher_no": receipt.name, "is_cancelled": 0}, fields=["warehouse", "qty"])
		self.assertEqual({row.warehouse: flt(row.qty) for row in ledger}, {self.warehouses[2]: -4, self.warehouses[1]: 4})
		receipt.cancel()
		source.reload()
		self.assertEqual(flt(source.per_transferred), 0)
		self.assertEqual(workspace._stock_transit_details(source)["status"], "In transit · 0% received")
		editor = workspace.end_stock_entry_transit(source.name)
		payload = workspace.save_stock_operation("stock_entry", {**editor["defaults"], "item_details": editor["item_groups"]}, submit=True)
		source.reload()
		self.assertEqual(flt(source.per_transferred), 100)
		self.assertFalse(workspace._document_actions(source)["can_end_transit"])
		self.assertEqual(workspace._stock_transit_details(source)["status"], "Received")
		self.assertIn(payload["record"]["name"], [row.name for row in workspace._stock_transit_details(source)["received_entries"]])

	def test_new_reconciliation_saves_with_server_posting_defaults(self):
		seed = self.make_entry("Material Receipt", qty=10)
		groups = workspace.get_document("YRP Stock Entry", seed.name)["item_groups"]
		editor = workspace.get_stock_operation_editor("stock_reconciliation")
		payload = workspace.save_stock_operation("stock_reconciliation", {**editor["defaults"], "default_warehouse": self.warehouses[0], "item_details": groups})
		draft = frappe.get_doc("YRP Stock Reconciliation", payload["record"]["name"])
		self.assertEqual(str(draft.posting_date), nowdate())
		self.assertTrue(draft.posting_time)
		self.assertEqual(draft.docstatus, 0)

	def test_skip_transit_and_material_receipt_web_create(self):
		source = self.make_entry("Send to Warehouse", skip_transit=1)
		source.submit()
		self.assertEqual(workspace._stock_transit_details(source)["status"], "Transit skipped")
		self.assertFalse(workspace._document_actions(source)["can_end_transit"])
		with self.assertRaises(frappe.ValidationError):
			workspace.end_stock_entry_transit(source.name)
		groups = workspace.get_document("YRP Stock Entry", source.name)["item_groups"]
		payload = workspace.save_stock_operation("stock_entry", {"purpose": "Material Receipt", "to_warehouse": self.warehouses[1], "item_details": groups}, submit=True)
		self.assertEqual(payload["record"]["docstatus"], 1)
