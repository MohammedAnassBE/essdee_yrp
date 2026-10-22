from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe
from frappe.model.base_document import BaseDocument
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.fabric_store.documents.goods_received_note import (
	_editable_headers,
	_is_additional_grn_source,
	_merge_authoritative_rows,
	_merge_inspection_sources,
	_source_defaults,
	_special_source_context,
	calculate_goods_received_note,
	execute_goods_received_note_command,
	get_delivery_address,
	get_goods_received_note_calculation,
	get_goods_received_note_workspace,
	get_supplier_address,
	preview_goods_received_note_source,
	save_goods_received_note,
	save_goods_received_note_inspection,
)
from essdee_yrp.garment_grn import _allocate_calculated_receivables


class TestFabricStoreGoodsReceivedNote(TestCase):
	def setUp(self):
		self.actual_dia_context = self.enterContext(patch(
			"essdee_yrp.fabric_store.documents.goods_received_note._actual_dia_context",
			return_value={"enabled": False, "dia_options": []},
		))

	def test_web_delivery_address_search_and_default_contract(self):
		source = (Path(__file__).parent.parent / "frontend/src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue").read_text()
		# Like production_api, the Delivery Address picker lists only the Delivery Location's addresses.
		self.assertIn('searchLinkedDocument("Address", "Supplier", form.delivery_location, text)', source)
		self.assertNotIn('searchLink("Address", text, { disabled: 0 })', source)
		self.assertIn('searchLinkedDocument("Address", "Supplier", form.supplier, text)', source)
		self.assertIn('searchLinkedDocument("Contact", "Supplier", form.supplier, text)', source)
		self.assertIn('if (fieldname === "delivery_location") await defaultAddress("delivery_address", value)', source)
		self.assertIn('if (fieldname === "supplier") await defaultAddress("supplier_address", value)', source)
		self.assertIn('if (fieldname in addressDefaults) invalidateAddress(fieldname)', source)
		self.assertIn("isCurrent() && !form[fieldname]", source)
		self.assertIn("function applyWorkspace(nextWorkspace) {\n\tinvalidateAddresses()", source)

	def test_po_delivery_address_uses_shipping_party_then_po_delivery_location(self):
		po = MagicMock()
		po.get.side_effect = {"default_delivery_location": "S-0071", "shipping_address": "COMPANY-ADDRESS"}.get
		for party_address, expected in (("PARTY-SHIPPING", "PARTY-SHIPPING"), (None, "S-0071-Primary")):
			with (
				self.subTest(party_address=party_address),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults", return_value={"to_warehouse": "WH"}),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.db.get_value", return_value="S-0070"),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=party_address) as party,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc", return_value=po),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_primary_address", side_effect=lambda supplier: f"{supplier}-Primary"),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_supplier_address", return_value="BILLING"),
			):
				defaults = _source_defaults("Purchase Order", "PO-1")
				self.assertEqual(defaults["delivery_location"], "S-0070")
				self.assertEqual(defaults["delivery_address"], expected)
				party.assert_called_once_with("S-0070", preferred_type="Shipping")
		po.check_permission.assert_called_once_with("read")

	def test_delivery_location_change_has_no_po_fallback(self):
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=None),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc") as get_doc,
		):
			self.assertEqual(get_delivery_address("NO-ADDRESS"), "")
		get_doc.assert_not_called()

	def test_work_order_delivery_address_uses_shipping_party_without_po_fallback(self):
		for empty in (None, ""):
			for party_address in ("Essdee Knitting Mills Private Limited-Billing-4", None):
				defaults = {"delivery_location": "S-0171", "delivery_address": empty, "supplier_address": "WO-BILLING"}
				with (
					self.subTest(empty=empty, party_address=party_address),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", return_value=dict(defaults)),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=party_address) as party,
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc") as get_doc,
				):
					self.assertEqual(_source_defaults("YRP Work Order", "WO-2627-01298"), {**defaults, "delivery_address": party_address or ""})
					party.assert_called_once_with("S-0171", preferred_type="Shipping")
					get_doc.assert_not_called()

	def test_source_address_defaults_preserve_work_order_and_existing_po_values(self):
		defaults = {"delivery_address": "PICKED", "delivery_location": "UNIT", "supplier_address": "PICKED-BILLING"}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults", return_value=dict(defaults)),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", return_value=dict(defaults)),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_delivery_address") as address,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_supplier_address") as supplier_address,
		):
			self.assertEqual(_source_defaults("YRP Work Order", "WO-1"), defaults)
			self.assertEqual(_source_defaults("Purchase Order", "PO-1"), defaults)
		address.assert_not_called()
		supplier_address.assert_not_called()

	def test_new_po_grn_previews_and_saves_with_default_or_operator_picked_addresses(self):
		for picked in (None, "PICKED"):
			with self.subTest(picked=picked):
				doc = self.make_document()
				doc.meta.istable = False
				doc.meta.get.return_value = [
					frappe._dict(fieldname=fieldname, fieldtype="Link", reqd=1)
					for fieldname in ("supplier_address", "delivery_address")
				]
				values = {"against": "Purchase Order", "against_id": "PO-1"}
				if picked:
					values["delivery_address"] = picked
					values["supplier_address"] = picked
				po = frappe._dict(shipping_address="COMPANY-ADDRESS", default_delivery_location="S-0070", supplier_address="Usha Quality Stickerz-Billing")
				po.check_permission = MagicMock()
				# Exercise the actual source default path through both preview and save.
				# Insert must see both mandatory address fields already populated.
				doc.insert.side_effect = lambda: (
					self.assertEqual(BaseDocument._get_missing_mandatory_fields(doc), []),
					self.assertEqual(doc.delivery_address, picked or "S-0070-Shipping"),
					self.assertEqual(doc.supplier_address, picked or "Usha Quality Stickerz-Billing"),
				)
				with (
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
					patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["supplier_address", "delivery_address"]),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults", side_effect=lambda name: {"supplier": "Usha Quality Stickerz", "delivery_location": "S-0070", "items": []}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", side_effect=lambda party, preferred_type: "Usha Quality Stickerz-Billing" if preferred_type == "Billing" else None),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc", return_value=po),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_primary_address", side_effect=lambda supplier: f"{supplier}-Shipping"),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[]),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
				):
					preview = preview_goods_received_note_source(values)
					self.assertEqual(preview["values"]["supplier_address"], picked or "Usha Quality Stickerz-Billing")
					self.assertEqual(preview["values"]["delivery_address"], picked or "S-0070-Shipping")
					save_goods_received_note(values)
				doc.insert.assert_called_once()

	def test_new_work_order_grn_previews_and_saves_with_delivery_address(self):
		address = "Essdee Knitting Mills Private Limited-Billing-4"
		for picked in (None, "PICKED"):
			with self.subTest(picked=picked):
				doc = self.make_document()
				doc.meta.istable = False
				doc.meta.get.return_value = [
					frappe._dict(fieldname=fieldname, fieldtype="Link", reqd=1)
					for fieldname in ("supplier_address", "delivery_address")
				]
				values = {"against": "YRP Work Order", "against_id": "WO-2627-01298"}
				if picked:
					values["delivery_address"] = picked
				doc.insert.side_effect = lambda: (
					self.assertEqual(BaseDocument._get_missing_mandatory_fields(doc), []),
					self.assertEqual(doc.delivery_address, picked or address),
				)
				with (
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
					patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["supplier_address", "delivery_address"]),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", side_effect=lambda *args: {"delivery_location": "S-0171", "delivery_address": None, "supplier_address": address, "items": []}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=address),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[]),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
				):
					preview = preview_goods_received_note_source(values)
					self.assertEqual(preview["values"]["delivery_address"], picked or address)
					self.assertEqual(preview["values"]["supplier_address"], address)
					save_goods_received_note(values)
				doc.insert.assert_called_once()

	def test_saved_grn_workspace_keeps_stored_addresses(self):
		for docstatus in (0, 1):
			with self.subTest(docstatus=docstatus):
				doc = self.make_document(docstatus=docstatus)
				doc.delivery_address = "STORED"
				doc.supplier_address = "STORED-BILLING"
				with (
					patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value={}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note._inspection_context", return_value={}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_supplier_notification_capabilities", return_value={"sms": False, "whatsapp": False}),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[]),
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_delivery_address") as address,
					patch("essdee_yrp.fabric_store.documents.goods_received_note.get_supplier_address") as supplier_address,
				):
					values = get_goods_received_note_workspace(doc.name)["values"]
					self.assertEqual(values["delivery_address"], "STORED")
					self.assertEqual(values["supplier_address"], "STORED-BILLING")
				address.assert_not_called()
				supplier_address.assert_not_called()

	def test_po_supplier_address_uses_billing_party_then_po_fallback(self):
		po = frappe._dict(supplier_address="PO-BILLING")
		po.check_permission = MagicMock()
		for party_address, expected in (("PARTY-BILLING", "PARTY-BILLING"), (None, "PO-BILLING")):
			with (
				self.subTest(party_address=party_address),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults", return_value={"supplier": "SUPPLIER", "delivery_address": "SHIPPING"}),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=party_address) as party,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc", return_value=po) as get_doc,
			):
				self.assertEqual(_source_defaults("Purchase Order", "PO-1")["supplier_address"], expected)
				party.assert_called_once_with("SUPPLIER", preferred_type="Billing")
				if party_address:
					get_doc.assert_not_called()
				else:
					get_doc.assert_called_once_with("Purchase Order", "PO-1")
		po.check_permission.assert_called_once_with("read")

	def test_supplier_change_has_no_po_fallback(self):
		for supplier, party_address in (("SUPPLIER", "BILLING"), ("NO-ADDRESS", None), (None, None)):
			with (
				self.subTest(supplier=supplier),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=party_address) as party,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc") as get_doc,
			):
				self.assertEqual(get_supplier_address(supplier), party_address or "")
				party.assert_called_once_with(supplier, preferred_type="Billing")
				get_doc.assert_not_called()

	def test_work_order_only_adds_empty_supplier_address_default(self):
		for party_address in ("BILLING", None):
			defaults = {"supplier": "WO-SUPPLIER", "delivery_address": "WO-SHIPPING", "items": [{"quantity": 5}], "item_details": [{"kind": "wo"}]}
			with (
				self.subTest(party_address=party_address),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", return_value=dict(defaults)) as loader,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value=party_address) as party,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_delivery_address") as delivery,
				patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.get_doc") as get_doc,
			):
				self.assertEqual(_source_defaults("YRP Work Order", "WO-1", "DC-1"), {**defaults, "supplier_address": party_address or ""})
				loader.assert_called_once_with("WO-1", "DC-1")
				party.assert_called_once_with("WO-SUPPLIER", preferred_type="Billing")
				delivery.assert_not_called()
				get_doc.assert_not_called()

	def test_padded_zero_quantity_cell_does_not_create_a_forged_row(self):
		with patch(
			"essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames",
			return_value=(),
		):
			merged = _merge_authoritative_rows(
				[],
				[{"item_variant": "ITEM-S", "quantity": 0, "secondary_qty": 0}],
			)

		self.assertEqual(merged, [])

	def test_duplicate_workspace_is_unsaved_and_keeps_entered_groups(self):
		source = self.make_document(docstatus=1)
		duplicate = self.make_document()
		duplicate.name = None
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=source),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=duplicate),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._onload_matrices", return_value=([{"copy": "items"}], [{"copy": "corrections"}])),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[]),
		):
			workspace = get_goods_received_note_workspace(source={"duplicate_from": source.name})

		self.assertIsNone(workspace["record"]["name"])
		self.assertEqual(workspace["values"]["comments"], source.comments)
		self.assertEqual(workspace["matrices"]["items"], [{"copy": "items"}])

	def test_allow_non_bundle_is_an_editable_draft_header_like_desk(self):
		# production_api's GRN form lets the user tick Allow Non Bundle; the received rows stay editable.
		self.assertFalse(_special_source_context({"allow_non_bundle": 1})["active"])
		doc = frappe._dict(is_return=0)
		self.assertEqual(_editable_headers(doc, {"allow_non_bundle": 1, "is_rework": 1}), {"allow_non_bundle": 1})
		# A Cut Panel Movement GRN keeps the bundle mode its movement set.
		cpm_grn = frappe._dict(is_return=0, cut_panel_movement="CPM-1")
		self.assertEqual(_editable_headers(cpm_grn, {"allow_non_bundle": 0, "comments": "x"}), {"comments": "x"})

	def test_special_source_grn_cannot_be_duplicated_as_an_ordinary_receipt(self):
		source = self.make_document(docstatus=1)
		source.additional_grn = 1
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=source),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "source-managed"):
				get_goods_received_note_workspace(source={"duplicate_from": source.name})

	def test_calculated_output_is_allocated_across_duplicate_receivable_rows(self):
		work_order = frappe._dict(
			receivables=[
				frappe._dict(name="WOR-1", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=1),
				frappe._dict(name="WOR-2", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=2),
				frappe._dict(name="WOR-3", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=33.6, idx=3),
			]
		)

		allocations = _allocate_calculated_receivables(
			work_order,
			{"item_variant": "FABRIC-GREY", "set_combination": "{}", "qty": 50.4},
		)

		self.assertEqual(
			[(row.name, quantity) for row, quantity in allocations],
			[("WOR-1", 33.6), ("WOR-2", 16.8)],
		)

	def test_calculated_output_above_combined_pending_quantity_is_rejected_clearly(self):
		work_order = frappe._dict(
			name="WO-1",
			receivables=[
				frappe._dict(name="WOR-1", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=10, idx=1),
				frappe._dict(name="WOR-2", item_variant="FABRIC-GREY", set_combination="{}", pending_quantity=5, idx=2),
			],
		)

		with self.assertRaisesRegex(frappe.ValidationError, "Only 15.*pending"):
			_allocate_calculated_receivables(
				work_order,
				{"item_variant": "FABRIC-GREY", "set_combination": "{}", "qty": 16},
			)

	def test_additional_grn_calculation_is_not_capped_by_pending_quantity(self):
		work_order = frappe._dict(
			name="WO-1",
			receivables=[
				frappe._dict(name="WOR-1", item_variant="STYLE-S", set_combination="{}", pending_quantity=0, idx=1),
				frappe._dict(name="WOR-2", item_variant="STYLE-S", set_combination="{}", pending_quantity=3, idx=2),
			],
		)

		allocations = _allocate_calculated_receivables(
			work_order,
			{"item_variant": "STYLE-S", "set_combination": "{}", "qty": 16},
			capped=False,
		)

		self.assertEqual([(row.name, quantity) for row, quantity in allocations], [("WOR-1", 16)])

	def test_additional_grn_calculation_starts_from_every_receivable_row(self):
		from essdee_yrp.garment_grn import _validate_grn_calculation, get_calculation_base_rows

		grn = frappe._dict(additional_grn=1, items=["SAVED"], delivery_challan=None)
		with (
			patch("essdee_yrp.additional_grn.get_receivable_rows", return_value=["ALL"]) as receivable_rows,
			patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note._pending_receivable_rows") as pending,
		):
			self.assertEqual(get_calculation_base_rows(grn, "WO", {}, "Accepted"), ["ALL"])
		receivable_rows.assert_called_once_with("WO", ["SAVED"])
		pending.assert_not_called()

		draft = frappe._dict(docstatus=0, against="YRP Work Order", against_id="WO-1", additional_grn=1)
		with patch("essdee_yrp.garment_grn.frappe.get_doc", side_effect=LookupError("reached Work Order")):
			with self.assertRaisesRegex(LookupError, "reached Work Order"):
				_validate_grn_calculation(draft)

	def make_document(
		self,
		*,
		docstatus=0,
		is_internal_unit=0,
		transfer_complete=0,
		is_return=0,
		is_rework=0,
		additional_grn=0,
	):
		doc = frappe._dict(
			doctype="YRP Goods Received Note",
			name="GRN-1",
			docstatus=docstatus,
			modified="2026-10-06 10:00:00",
			naming_series="YRP-GRN-.YYYY.-",
			against="YRP Work Order",
			against_id="WO-1",
			delivery_challan="DC-1",
			is_return=is_return,
			is_rework=is_rework,
			additional_grn=additional_grn,
			includes_packing=0,
			cutting_laysheet=None,
			cut_panel_movement=None,
			from_closed_wo_sewing_details=0,
			allow_non_bundle=0,
			posting_date="2026-10-06",
			posting_time="10:00:00",
			edit_posting_date_and_time=0,
			process_name="Stitching",
			item="STYLE-1",
			production_detail="IPD-1",
			supplier="SUPPLIER-1",
			delivery_location="UNIT-1",
			from_warehouse="Supplier - E",
			to_warehouse="Stores - E",
			freight_charges=25,
			comments="Receipt",
			is_internal_unit=is_internal_unit,
			transfer_complete=transfer_complete,
			ste_transferred=0,
			ste_transferred_percent=0,
			total_received_quantity=8,
			total=400,
			grand_total=425,
			items=[
				frappe._dict(
					name="GRNI-1",
					item_variant="STYLE-S",
					quantity=5,
					secondary_qty=2,
					uom="Nos",
					rate=50,
					ref_doctype="YRP Work Order Receivables",
					ref_docname="WOR-1",
					row_index="0::Accepted",
					received_type="Accepted",
					lot="LOT-1",
					set_combination='{"colour":"Red"}',
				),
				frappe._dict(
					name="GRNI-2",
					item_variant="STYLE-S",
					quantity=3,
					uom="Nos",
					rate=50,
					ref_doctype="YRP Work Order Receivables",
					ref_docname="WOR-1",
					row_index="0::Rejected",
					received_type="Rejected",
					lot="LOT-1",
					set_combination='{"colour":"Red"}',
				),
			],
			correction_items=[
				frappe._dict(
					name="GRNC-1",
					item_variant="STYLE-M",
					quantity=1,
					uom="Nos",
					rate=60,
					ref_docname="WOR-C1",
					work_order_correction="WOC-1",
					row_index="1",
					received_type="Accepted",
					lot="LOT-1",
				),
			],
		)
		doc.check_permission = MagicMock()
		doc.has_permission = MagicMock(return_value=True)
		doc.update = MagicMock(side_effect=lambda values: dict.update(doc, values))
		doc.set = MagicMock(
			side_effect=lambda fieldname, value: dict.__setitem__(
				doc,
				fieldname,
				[
					frappe._dict(row) if isinstance(row, dict) else row
					for row in value
				]
				if isinstance(value, list)
				else value,
			)
		)
		doc.insert = MagicMock()
		doc.save = MagicMock()
		doc.submit = MagicMock()
		doc.cancel = MagicMock()
		doc.run_method = MagicMock()
		doc.get_onload = MagicMock(
			return_value={
				"item_details": [{"kind": "normal"}],
				"correction_item_details": [{"kind": "correction"}],
			}
		)
		doc.meta = MagicMock()
		doc.meta.get_field.side_effect = lambda fieldname: frappe._dict(
			fieldname=fieldname,
			label=fieldname.replace("_", " ").title(),
			fieldtype="Currency" if fieldname in {"total", "grand_total", "freight_charges"} else "Data",
			hidden=0,
			read_only=0,
			reqd=0,
			options="",
		)
		return doc

	def workspace_base(self, doc, **kwargs):
		permissions = {
			"can_read": True,
			"can_create": True,
			"can_write": doc.docstatus == 0,
			"can_submit": doc.docstatus == 0,
			"can_cancel": doc.docstatus == 1,
			"can_amend": doc.docstatus == 2,
			"can_print": True,
		}
		capabilities = {
			name: {key: value for key, value in spec.items() if key not in {"eligible", "permission"}}
			for name, spec in kwargs["capabilities"].items()
			if spec.get("eligible", True)
			and (not spec.get("permission") or permissions.get(f"can_{spec['permission']}", False))
		}
		return {
			"record": {
				"doctype": doc.doctype,
				"name": doc.name,
				"docstatus": doc.docstatus,
				"modified": doc.modified,
			},
			"fields": [{"fieldname": fieldname, "value": doc.get(fieldname)} for fieldname in kwargs["fieldnames"]],
			"totals": [{"fieldname": fieldname, "value": doc.get(fieldname)} for fieldname in kwargs["totals"]],
			"permissions": permissions,
			"capabilities": capabilities,
			"print_formats": [],
		}

	def test_workspace_exposes_calculate_matrices_dimensions_and_special_context(self):
		self.actual_dia_context.return_value = {"enabled": True, "attribute": "Dia", "dia_options": ["14", "14.5"]}
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value={"inspection_entries": [], "completion_entries": []}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_stock_dimensions_for_ui", return_value=[{"fieldname": "received_type", "label": "Received Type", "options": "YRP Received Type", "mandatory": 1}]),
		):
			workspace = get_goods_received_note_workspace(doc.name)

		self.assertEqual(workspace["matrices"]["items"], [{"kind": "normal"}])
		self.assertEqual(workspace["matrices"]["correction_items"], [{"kind": "correction"}])
		self.assertIn("calculate", workspace["capabilities"])
		self.assertFalse(workspace["special_source"]["active"])
		self.assertEqual(workspace["dimensions"][0]["fieldtype"], "Link")
		self.assertTrue(workspace["dimensions"][0]["locked"])

		self.assertEqual(workspace["actual_dia"], self.actual_dia_context.return_value)

	def test_workspace_hides_calculate_for_rework_but_offers_it_for_additional_grn(self):
		for flags, has_calculate in (({"is_rework": 1}, False), ({"additional_grn": 1}, True)):
			doc = self.make_document(**flags)
			with (
				patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
				patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
				patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value={}),
			):
				workspace = get_goods_received_note_workspace(doc.name)
			# Like production_api, Calculate stays available on an Additional GRN.
			self.assertEqual("calculate" in workspace["capabilities"], has_calculate, flags)
		self.assertTrue(workspace["special_source"]["active"])
		# Like production_api, an Additional GRN keeps its received quantities editable.
		self.assertFalse(workspace["special_source"]["read_only"])
		self.assertTrue(_special_source_context({"is_rework": 1})["read_only"])

	def test_additional_grn_preview_lists_every_work_order_receivable(self):
		defaults = {
			"supplier": "SUPPLIER-1",
			"items": [{"item_variant": "STYLE-S", "quantity": 0, "max_receivable_quantity": -1}],
			"item_details": [{"kind": "additional"}],
			"correction_items": [],
			"correction_item_details": [],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_additional_grn_defaults", return_value=defaults) as additional,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults") as ordinary,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value="ADDRESS"),
		):
			workspace = preview_goods_received_note_source(
				{"against": "YRP Work Order", "against_id": "WO-1", "delivery_challan": "DC-1", "additional_grn": 1}
			)
		additional.assert_called_once_with("WO-1")
		ordinary.assert_not_called()
		self.assertEqual(workspace["values"]["additional_grn"], 1)
		self.assertEqual(workspace["matrices"]["items"], [{"kind": "additional"}])
		self.assertTrue(workspace["special_source"]["active"])
		self.assertFalse(workspace["special_source"]["read_only"])

	def test_additional_grn_flag_is_ignored_for_purchase_orders_and_returns(self):
		for source in (
			{"purchase_order": "PO-1", "additional_grn": 1},
			{"against": "YRP Work Order", "against_id": "WO-1", "is_return": 1, "additional_grn": 1},
		):
			with self.subTest(source=source):
				self.assertFalse(_is_additional_grn_source(source))
		self.assertTrue(_is_additional_grn_source({"work_order": "WO-1", "additional_grn": "1"}))

	def test_new_additional_grn_save_takes_operator_quantities(self):
		doc = self.make_document()
		doc.name = "GRN-NEW"
		doc.items = []
		doc.correction_items = []
		source_row = dict(self.make_document()["items"][0], quantity=0, max_receivable_quantity=-1)
		defaults = {
			"supplier": "SUPPLIER-1",
			"from_warehouse": "Supplier - E",
			"to_warehouse": "Stores - E",
			"items": [source_row],
			"correction_items": [],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_additional_grn_defaults", return_value=defaults),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=[dict(source_row, quantity=7)]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_party_address", return_value="ADDRESS"),
			patch("essdee_yrp.fabric_grn.validate_actual_dia_rows"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			save_goods_received_note(
				{"against": "YRP Work Order", "against_id": "WO-1", "additional_grn": 1, "item_details": [{}]}
			)
		self.assertEqual(doc.additional_grn, 1)
		self.assertEqual([row.quantity for row in doc["items"]], [7])
		doc.insert.assert_called_once()

	def test_work_order_preview_uses_essdee_defaults(self):
		defaults = {
			"supplier": "SUPPLIER-1",
			"supplier_address": "WO-BILLING",
			"items": [{"item_variant": "STYLE-S", "quantity": 5}],
			"item_details": [{"kind": "wo"}],
			"correction_items": [],
			"correction_item_details": [],
		}
		with patch(
			"essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults",
			return_value=defaults,
		) as loader:
			workspace = preview_goods_received_note_source(
				{"against": "YRP Work Order", "against_id": "WO-1", "delivery_challan": "DC-1"}
			)
		self.assertEqual(workspace["values"]["supplier"], "SUPPLIER-1")
		self.assertEqual(workspace["matrices"]["items"], [{"kind": "wo"}])
		loader.assert_called_once_with("WO-1", "DC-1")

	def test_purchase_order_preview_uses_base_defaults(self):
		defaults = {
			"supplier": "SUPPLIER-PO",
			"supplier_address": "PO-BILLING",
			"items": [{"item_variant": "FABRIC-1", "quantity": 2}],
			"item_details": [{"kind": "po"}],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_purchase_order_defaults", return_value=defaults) as loader,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_delivery_address", return_value="PO-SHIPPING"),
		):
			workspace = preview_goods_received_note_source(
				{"purchase_order": "PO-1", "comments": "Kept"}
			)
		self.assertEqual(workspace["record"]["against"], "Purchase Order")
		self.assertEqual(workspace["values"]["comments"], "Kept")
		self.assertEqual(workspace["values"]["delivery_address"], "PO-SHIPPING")
		loader.assert_called_once_with("PO-1")

	def test_existing_save_uses_saved_rows_and_preserves_other_types_corrections_and_special_rows(self):
		doc = self.make_document(is_rework=1)
		browser_rows = [
			{
				"item_variant": "STYLE-S",
				"quantity": 4,
				"rate": 999,
				"ref_docname": "WOR-1",
				"row_index": "0::Accepted",
				"received_type": "Accepted",
				"lot": "FORGED",
				"set_combination": '{"colour":"Red"}',
			},
			{
				"item_variant": "STYLE-S",
				"quantity": 3,
				"ref_docname": "WOR-1",
				"row_index": "0::Rejected",
				"received_type": "Rejected",
				"lot": "LOT-1",
				"set_combination": '{"colour":"Red"}',
			},
		]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_rows),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={"record": {"name": doc.name}}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults") as defaults,
		):
			result = save_goods_received_note(
				{
					"comments": "Updated",
					"supplier": "FORGED",
					"item_details": [{"browser": True}],
				},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result["record"]["name"], doc.name)
		self.assertEqual(doc.supplier, "SUPPLIER-1")
		self.assertEqual(doc["items"][0].quantity, 5, "special prepared rows stay untouched")
		self.assertEqual(doc["items"][1].received_type, "Rejected")
		self.assertEqual(doc.correction_items[0].name, "GRNC-1")
		defaults.assert_not_called()

	def test_existing_save_rejects_delivery_challan_relink_without_rebuilding_rows(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaisesRegex(frappe.ValidationError, "Delivery Challan cannot be changed"),
		):
			save_goods_received_note(
				{"delivery_challan": "DC-FORGED"},
				name=doc.name,
				expected_modified=doc.modified,
			)
		doc.save.assert_not_called()

	def test_ordinary_existing_save_merges_quantity_but_rejects_forged_lineage(self):
		doc = self.make_document()
		browser_rows = [
			# The common matrix ungrouping helper renumbers logical rows. Saved
			# Received-Type suffixes therefore cannot be trusted as browser identity.
			dict(doc["items"][0], quantity=4, rate=999, row_index=0),
			dict(doc["items"][1], quantity=2, row_index=1),
		]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_rows),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
			):
				save_goods_received_note({"item_details": [{}]}, name=doc.name)
		self.assertEqual(doc["items"][0].quantity, 4)
		self.assertEqual(doc["items"][0].rate, 50)
		self.assertEqual(doc["items"][0].lot, "LOT-1")

		forged = [dict(doc["items"][0], ref_docname="WOR-FORGED", quantity=4)]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=forged),
			self.assertRaises(frappe.ValidationError),
		):
			save_goods_received_note({"item_details": [{}]}, name=doc.name)

	def test_saved_draft_accepts_added_dia_and_preserves_source_fields(self):
		doc = self.make_document()
		self.actual_dia_context.return_value = {"enabled": True, "attribute": "Dia", "dia_options": ["14", "14.5"]}
		source = dict(doc["items"][0], item_variant="Greige-14")
		doc["items"] = [frappe._dict(source)]
		added_row = dict(source, item_variant="Greige-14.5", quantity=20, rate=999)
		added_row.pop("name", None)
		browser_rows = [dict(source, quantity=10), added_row]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_rows),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
			patch("essdee_yrp.fabric_grn.get_parent_item", return_value="Greige"),
			patch("essdee_yrp.fabric_grn.get_dia_attribute", return_value="Dia"),
			patch("essdee_yrp.fabric_grn._configured_dia_values", return_value=["14", "14.5"]),
			patch("essdee_yrp.fabric_grn._variant_attrs", side_effect=[{"Colour": "Greige", "Dia": "14"}, {"Colour": "Greige", "Dia": "14.5"}]),
		):
			save_goods_received_note({"item_details": [{}]}, name=doc.name)
		self.assertEqual([(row.item_variant, row.quantity) for row in doc["items"]], [("Greige-14", 10), ("Greige-14.5", 20)])
		added = doc["items"][1]
		self.assertEqual(added.ref_docname, source["ref_docname"])
		self.assertEqual(added.ref_doctype, source["ref_doctype"])
		self.assertEqual(added.rate, source["rate"])
		self.assertNotIn("name", added)
		self.assertNotEqual(added.row_index, source["row_index"])
		doc.save.assert_called_once()

	def test_submitted_save_updates_allow_on_submit_item_tables_only(self):
		doc = self.make_document(docstatus=1)
		doc.meta.fields = [
			frappe._dict(fieldname="items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="correction_items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="comments", fieldtype="Small Text", allow_on_submit=0, hidden=0, read_only=0),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		browser_items = [dict(doc["items"][0], quantity=4), dict(doc["items"][1], quantity=2)]
		browser_corrections = [dict(doc.correction_items[0], quantity=1)]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["items", "correction_items", "comments"]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=browser_items),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_correction_items_from_ui", return_value=browser_corrections),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={"record": {"name": doc.name}}),
		):
			result = save_goods_received_note(
				{"item_details": [{"browser": True}], "correction_item_details": [{"browser": True}]},
				name=doc.name,
				expected_modified=doc.modified,
			)

		self.assertEqual(result["record"]["name"], doc.name)
		self.assertEqual(doc["items"][0].quantity, 4)
		self.assertEqual(doc["items"][1].quantity, 2)
		self.assertEqual(doc.correction_items[0].quantity, 1)
		doc.save.assert_called_once_with()

	def test_submitted_po_save_rejects_lot_change_without_replacing_row(self):
		doc = self.make_document(docstatus=1)
		doc.against = "Purchase Order"
		doc.against_id = "PO-1"
		for row in doc["items"]:
			row.ref_doctype = "Purchase Order Item"
			row.ref_docname = "PO-ROW"
		original = [dict(row) for row in doc["items"]]
		browser = [dict(original[0], lot="Open Lot", quantity=99)]
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note.get_allow_on_submit_fields",
				return_value=["items"],
			),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note._purchase_order_lot_context",
				return_value={
					"lot_options": {"PO-ROW": ["LOT-1", "Open Lot"]},
					"lot_fieldname": "lot",
					"purchase_order": "PO-1",
				},
			),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames",
				return_value=("lot", "received_type"),
			),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui",
				return_value=browser,
			),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace",
				return_value={},
			),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "available item rows changed"):
				save_goods_received_note(
					{"item_details": [{"browser": True}]}, name=doc.name, expected_modified=doc.modified
				)
		self.assertEqual([dict(row) for row in doc["items"]], original)
		doc.save.assert_not_called()

	def test_submitted_save_rejects_non_allow_on_submit_header(self):
		doc = self.make_document(docstatus=1)
		doc.meta.fields = [
			frappe._dict(fieldname="items", fieldtype="Table", allow_on_submit=1, hidden=0, read_only=0),
			frappe._dict(fieldname="comments", fieldtype="Small Text", allow_on_submit=0, hidden=0, read_only=0),
		]
		doc.meta.get_field.side_effect = lambda fieldname: next(
			(field for field in doc.meta.fields if field.fieldname == fieldname),
			None,
		)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.common.get_permitted_fields", return_value=["items", "comments"]),
			self.assertRaisesRegex(frappe.ValidationError, "Allow on Submit"),
		):
			save_goods_received_note({"comments": "FORGED"}, name=doc.name, expected_modified=doc.modified)
		doc.save.assert_not_called()

	def test_new_save_keeps_authoritative_source_and_delegates_freight_and_submit_to_controller(self):
		doc = self.make_document()
		doc.name = "GRN-NEW"
		doc.items = []
		doc.correction_items = []
		defaults = {
			"supplier": "SUPPLIER-1",
			"from_warehouse": "Supplier - E",
			"supplier_address": "WO-BILLING",
			"to_warehouse": "Stores - E",
			"items": [dict(self.make_document()["items"][0])],
			"correction_items": [],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_work_order_defaults", return_value=defaults),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.ungroup_items_from_ui", return_value=[dict(defaults["items"][0], quantity=4)]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			save_goods_received_note(
				{
					"against": "YRP Work Order",
					"against_id": "WO-1",
					"supplier": "FORGED",
					"freight_charges": 100,
					"item_details": [{}],
				},
				submit=True,
			)
		self.assertEqual(doc.supplier, "SUPPLIER-1")
		self.assertEqual(doc.freight_charges, 100)
		doc.insert.assert_called_once()
		doc.submit.assert_called_once()

	def test_calculate_delegates_selected_type_and_returns_refreshed_workspace(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified") as stale,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables", return_value={"received_type": "Rejected"}) as calculate,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={"record": {"name": doc.name}}),
		):
			result = calculate_goods_received_note(
				doc.name,
				[{"source_row": "WOCI-1", "qty": 3}],
				"Rejected",
				doc.modified,
			)
		stale.assert_called_once_with(doc, doc.modified)
		calculate.assert_called_once_with(doc.name, [{"source_row": "WOCI-1", "qty": 3}], "Rejected", doc.modified)
		self.assertEqual(result["calculation"]["received_type"], "Rejected")

	def test_stale_calculate_is_rejected_before_controller_delegation(self):
		doc = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified", side_effect=frappe.TimestampMismatchError),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables") as calculate,
			self.assertRaises(frappe.TimestampMismatchError),
		):
			calculate_goods_received_note(doc.name, [], "Accepted", "stale")
		calculate.assert_not_called()

	def test_direct_calculation_endpoints_reject_ineligible_special_mode(self):
		doc = self.make_document()
		doc.from_finishing = 1
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_grn_calculation_context") as context,
			self.assertRaisesRegex(frappe.ValidationError, "Calculate is not available"),
		):
			get_goods_received_note_calculation(doc.name)
		context.assert_not_called()

		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.calculate_grn_receivables") as calculate,
			self.assertRaisesRegex(frappe.ValidationError, "Calculate is not available"),
		):
			calculate_goods_received_note(doc.name, [], "Accepted", doc.modified)
		calculate.assert_not_called()

	def test_submitted_grn_exposes_inspection_initial_payload_and_existing_entries(self):
		doc = self.make_document(docstatus=1)
		related = {"inspection_entries": [{"name": "INS-1"}], "completion_entries": []}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=doc),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_workspace_base", side_effect=self.workspace_base),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._related_documents", return_value=related),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._target_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_inspection_initial_payload", return_value=[{"ref_docname": "GRNI-1"}]),
		):
			workspace = get_goods_received_note_workspace(doc.name)
		self.assertIn("create_inspection", workspace["capabilities"])
		self.assertIn("view_inspections", workspace["capabilities"])
		self.assertTrue(workspace["inspection"]["can_submit"])
		self.assertEqual(workspace["inspection"]["initial_payload"][0]["ref_docname"], "GRNI-1")

	def test_inspection_save_uses_authoritative_sources_and_submits_controller(self):
		grn = self.make_document(docstatus=1)
		inspection = frappe._dict(
			doctype="YRP Inspection Entry",
			name="INS-NEW",
			docstatus=0,
			modified="2026-10-06 11:00:00",
			items=[],
		)
		inspection.update = MagicMock(side_effect=lambda values: dict.update(inspection, values))
		inspection.set = MagicMock(side_effect=lambda key, value: dict.__setitem__(inspection, key, value))
		inspection.insert = MagicMock()
		inspection.submit = MagicMock()
		source = {
			"item_variant": "STYLE-S",
			"warehouse": "Transit - E",
			"grn_qty": 5,
			"ref_doctype": "YRP Goods Received Note Item",
			"ref_docname": "GRNI-1",
			"source_received_type": "Accepted",
			"received_type": "Accepted",
			"lot": "LOT-1",
			"splits": [{"target_received_type": "Accepted", "qty": 5, "received_date": "2026-10-06"}],
		}
		browser = dict(source, warehouse="FORGED", lot="FORGED", splits=[{"target_received_type": "Rejected", "qty": 5, "received_date": "2026-10-06"}])
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.has_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.new_doc", return_value=inspection),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_inspection_initial_payload", return_value=[source]),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.db.exists", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._inspection_projection", return_value={"record": {"name": inspection.name}}),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			result = save_goods_received_note_inspection(
				grn.name,
				{"remarks": "Checked", "item_details": [browser]},
				submit=True,
			)
		self.assertEqual(inspection.against_id, grn.name)
		self.assertIn('"warehouse": "Transit - E"', inspection.item_details)
		self.assertNotIn("FORGED", inspection.item_details)
		inspection.insert.assert_called_once()
		inspection.submit.assert_called_once()
		self.assertEqual(result["inspection"]["record"]["name"], inspection.name)

	def test_inspection_splits_cannot_exceed_authoritative_source_quantity(self):
		source = {
			"item_variant": "STYLE-S",
			"grn_qty": 5,
			"ref_doctype": "YRP Goods Received Note Item",
			"ref_docname": "GRNI-1",
		}
		browser = {
			**source,
			"splits": [
				{"target_received_type": "Accepted", "qty": 4},
				{"target_received_type": "Rejected", "qty": 2},
			],
		}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note.frappe.db.exists", return_value=True),
			self.assertRaisesRegex(frappe.ValidationError, "exceed.*available quantity"),
		):
			_merge_inspection_sources([source], [browser])

	def test_complete_transfer_and_lifecycle_commands_use_native_controllers(self):
		grn = self.make_document(docstatus=1, is_internal_unit=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._target_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.make_grn_completion", return_value="STE-1") as complete,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			result = execute_goods_received_note_command(grn.name, "complete_transfer")
		complete.assert_called_once_with(grn.name)
		self.assertEqual(result["created"]["name"], "STE-1")

		draft = self.make_document()
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=draft),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			execute_goods_received_note_command(draft.name, "submit")
		draft.submit.assert_called_once()

	def test_complete_transfer_reopens_existing_draft_completion(self):
		grn = self.make_document(docstatus=1, is_internal_unit=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note._target_permission", return_value=True),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_draft_completion_stock_entry", return_value="STE-DRAFT") as find_draft,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.make_grn_completion") as complete,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.get_goods_received_note_workspace", return_value={}),
		):
			result = execute_goods_received_note_command(grn.name, "complete_transfer")

		find_draft.assert_called_once_with("YRP Goods Received Note", grn.name)
		complete.assert_not_called()
		self.assertEqual(result["created"], {"doctype": "YRP Stock Entry", "name": "STE-DRAFT"})

	def test_forged_or_wrong_state_command_is_rejected(self):
		grn = self.make_document(docstatus=1)
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaises(frappe.ValidationError),
		):
			execute_goods_received_note_command(grn.name, "delete_everything")

		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			self.assertRaises(frappe.ValidationError),
		):
			execute_goods_received_note_command(grn.name, "submit")

	def test_notification_commands_delegate_to_existing_supplier_services(self):
		grn = self.make_document(docstatus=1)
		prepared = {"channel": "sms", "context": {"templates": [{"name": "GRN"}]}}
		sent = {"channel": "sms", "result": {"ok": True}}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._get_grn", return_value=grn),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.assert_expected_modified"),
			patch("essdee_yrp.fabric_store.documents.goods_received_note.prepare_supplier_notification", return_value=prepared) as prepare,
			patch("essdee_yrp.fabric_store.documents.goods_received_note.send_supplier_notification", return_value=sent) as send,
		):
			self.assertEqual(
				execute_goods_received_note_command(grn.name, "prepare_sms", expected_modified=grn.modified),
				prepared,
			)
			payload = {"template_name": "Receipt", "mobile_no": "9944405056", "params": {"name": grn.name}}
			self.assertEqual(
				execute_goods_received_note_command(grn.name, "send_sms", payload, grn.modified),
				sent,
			)

		prepare.assert_called_once_with(grn, "YRP Goods Received Note", "sms")
		send.assert_called_once_with(grn, "YRP Goods Received Note", "sms", payload)


class TestPurchaseOrderLotMerge(TestCase):
	def merge(self, browser_rows, *, extra_sources=(), source_values=None, **options):
		source = {
			"item_variant": "FABRIC",
			"ref_doctype": "Purchase Order Item",
			"ref_docname": "PO-ROW",
			"row_index": 0,
			"lot": "LOT-1",
			"received_type": "Accepted",
			"quantity": 10,
			"rate": 25,
			"uom": "Kg",
			**(source_values or {}),
		}
		with (
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames",
				return_value=("lot", "received_type"),
			),
			patch.object(frappe.db, "exists", return_value=True),
		):
			return _merge_authoritative_rows(
				[source, *({**source, **row} for row in extra_sources)],
				[{**source, **row} for row in browser_rows],
				**options,
			)

	def test_po_existing_split_keeps_trusted_name_and_row_index(self):
		for row_index in ("0", "0::Accepted", 0):
			with self.subTest(row_index=row_index):
				rows = self.merge(
					[{"name": "FORGED", "row_index": 7, "quantity": 6}],
					source_values={"name": "GRNI-1", "row_index": row_index},
					lot_options={"PO-ROW": ["LOT-1"]},
					lot_fieldname="lot",
					purchase_order="PO-1",
				)
				self.assertEqual((rows[0]["name"], rows[0]["row_index"]), ("GRNI-1", row_index))

	def test_po_new_lot_split_reuses_source_index_and_drops_name(self):
		for row_index in ("0", "0::Accepted", 0):
			with self.subTest(row_index=row_index):
				rows = self.merge(
					[{"quantity": 4}, {"lot": "Open Lot", "row_index": 7, "quantity": 6}],
					source_values={"name": "GRNI-1", "row_index": row_index},
					lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
					lot_fieldname="lot",
					purchase_order="PO-1",
				)
				self.assertEqual([row["row_index"] for row in rows], [row_index, row_index])
				self.assertEqual(rows[0]["name"], "GRNI-1")
				self.assertNotIn("name", rows[1])

	def test_po_new_received_type_split_generates_index(self):
		rows = self.merge(
			[{"lot": "Open Lot", "received_type": "Rejected", "quantity": 6}],
			source_values={"name": "GRNI-1", "row_index": "0::Accepted"},
			lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
			lot_fieldname="lot",
			purchase_order="PO-1",
		)
		self.assertEqual(rows[0]["row_index"], "0::Rejected")
		self.assertNotIn("name", rows[0])

	def test_po_lot_splits_survive_group_ungroup_and_merge(self):
		from yrp.stock.save_stock_items import group_items_for_ui, ungroup_items_from_ui

		options = {
			"lot_options": {"PO-ROW": ["LOT-1", "Open Lot"]},
			"lot_fieldname": "lot",
			"purchase_order": "PO-1",
		}
		rows = self.merge(
			[{"quantity": 4}, {"lot": "Open Lot", "quantity": 6}],
			source_values={"name": "GRNI-1", "row_index": "0"},
			**options,
		)
		rows[1]["name"] = "GRNI-2"
		config = {
			"item_field": "item_variant",
			"qty_field": "quantity",
			"value_fields": ["ref_doctype", "ref_docname", "rate"],
		}
		with (
			patch("yrp.stock.save_stock_items._get_entry_fields", return_value=[]),
			patch("yrp.stock.save_stock_items._child_has_field", return_value=True),
			patch(
				"yrp.stock.save_stock_items.get_dimension_fieldnames", return_value=["lot", "received_type"]
			),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_parent_item", return_value="Fabric"),
			patch("yrp.yrp.doctype.yrp_item.yrp_item.get_attribute_details", return_value={"attributes": []}),
			patch.object(frappe, "get_doc", return_value=frappe._dict(attributes=[])),
			patch("yrp.stock.save_stock_items._resolve_or_create_variant", return_value="FABRIC"),
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames",
				return_value=("lot", "received_type"),
			),
		):
			for _ in range(2):
				grouped = group_items_for_ui(rows, "YRP Goods Received Note", config=config)
				self.assertEqual(len(grouped[0]["items"]), 2)
				browser = ungroup_items_from_ui(grouped, "YRP Goods Received Note", config=config)
				self.assertEqual([row["row_index"] for row in browser], [0, 1])
				rows = _merge_authoritative_rows(rows, browser, **options)
				self.assertEqual(
					[(row["name"], row["lot"], row["quantity"], row["row_index"]) for row in rows],
					[("GRNI-1", "LOT-1", 4, "0"), ("GRNI-2", "Open Lot", 6, "0")],
				)

	def test_po_no_linked_lots_allows_only_own_lot(self):
		options = {"lot_options": {"PO-ROW": ["LOT-1"]}, "lot_fieldname": "lot", "purchase_order": "PO-1"}
		rows = self.merge([{"quantity": 6}], **options)
		self.assertEqual([(row["lot"], row["quantity"]) for row in rows], [("LOT-1", 6)])
		with self.assertRaisesRegex(frappe.ValidationError, "ANY-LOT"):
			self.merge([{"lot": "ANY-LOT", "quantity": 6}], **options)

	def test_po_empty_lot_map_still_validates(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Row 1.*LOT-1.*PO-1"):
			self.merge([{"quantity": 6}], lot_options={}, lot_fieldname="lot", purchase_order="PO-1")

	def test_po_omitted_lineage_is_kept_while_present_lineage_changes_lot(self):
		rows = self.merge(
			[{"lot": "Open Lot", "received_type": "Rejected", "quantity": 6}],
			extra_sources=[{"ref_docname": "PO-ROW-2", "quantity": 7, "rate": 30}],
			lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
			lot_fieldname="lot",
			purchase_order="PO-1",
		)
		self.assertCountEqual(
			[
				(row["ref_docname"], row["lot"], row["received_type"], row["quantity"], row["rate"])
				for row in rows
			],
			[("PO-ROW", "Open Lot", "Rejected", 6, 25), ("PO-ROW-2", "LOT-1", "Accepted", 7, 30)],
		)

	def test_po_present_zero_quantity_lineage_removes_old_splits(self):
		rows = self.merge(
			[{"quantity": 0}],
			extra_sources=[{"lot": "Open Lot", "quantity": 3}],
			lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
			lot_fieldname="lot",
			purchase_order="PO-1",
		)
		self.assertEqual(rows, [])

	def test_po_lot_change_keeps_trusted_fields(self):
		rows = self.merge(
			[{"lot": "Open Lot", "quantity": 6, "rate": 1, "uom": "Forged"}],
			lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
			lot_fieldname="lot",
			purchase_order="PO-1",
		)
		self.assertEqual(
			[(row["lot"], row["quantity"], row["ref_docname"]) for row in rows], [("Open Lot", 6, "PO-ROW")]
		)
		self.assertEqual((rows[0]["rate"], rows[0]["uom"]), (25, "Kg"))

	def test_po_lot_and_received_type_splits(self):
		rows = self.merge(
			[
				{"quantity": 4},
				{"lot": "Open Lot", "quantity": 3},
				{"lot": "Open Lot", "received_type": "Rejected", "quantity": 3},
			],
			lot_options={"PO-ROW": ["LOT-1", "Open Lot"]},
			lot_fieldname="lot",
			purchase_order="PO-1",
		)
		self.assertEqual(
			[(row["lot"], row["received_type"], row["quantity"]) for row in rows],
			[("LOT-1", "Accepted", 4), ("Open Lot", "Accepted", 3), ("Open Lot", "Rejected", 3)],
		)

	def test_po_invalid_lot_names_row_lot_and_order(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Row 1.*BAD.*PO-1"):
			self.merge(
				[{"lot": "BAD"}],
				lot_options={"PO-ROW": ["LOT-1"]},
				lot_fieldname="lot",
				purchase_order="PO-1",
			)

	def test_po_split_cannot_smuggle_lot_with_another_source_reference(self):
		with self.assertRaisesRegex(frappe.ValidationError, "available item rows changed"):
			self.merge(
				[{"ref_docname": "FORGED", "lot": "Open Lot"}],
				lot_options={"PO-ROW": ["LOT-1"], "FORGED": ["Open Lot"]},
				lot_fieldname="lot",
				purchase_order="PO-1",
			)

	def test_po_lot_validation_uses_trusted_clone(self):
		from essdee_yrp.fabric_store.documents.goods_received_note import _clone_purchase_order_split

		def clone_with_trusted_reference(siblings, browser, fieldname):
			clone = _clone_purchase_order_split(siblings, browser, fieldname)
			clone["ref_docname"] = "TRUSTED-ROW"
			return clone

		with (
			patch(
				"essdee_yrp.fabric_store.documents.goods_received_note._clone_purchase_order_split",
				side_effect=clone_with_trusted_reference,
			),
			self.assertRaisesRegex(frappe.ValidationError, "Row 1.*Open Lot.*PO-1"),
		):
			self.merge(
				[{"lot": "Open Lot"}],
				lot_options={"PO-ROW": ["Open Lot"], "TRUSTED-ROW": ["LOT-1"]},
				lot_fieldname="lot",
				purchase_order="PO-1",
			)

	def test_po_duplicate_lot_and_received_type_is_rejected(self):
		with self.assertRaisesRegex(frappe.ValidationError, "duplicate lot"):
			self.merge(
				[{"quantity": 4}, {"quantity": 6}],
				lot_options={"PO-ROW": ["LOT-1"]},
				lot_fieldname="lot",
				purchase_order="PO-1",
			)

	def test_work_order_still_rejects_lot_changes(self):
		with self.assertRaisesRegex(frappe.ValidationError, "available item rows changed"):
			self.merge([{"lot": "Open Lot"}])


class TestPurchaseOrderLotWorkspace(FrappeTestCase):
	def receipt_values(self, quantities):
		from yrp.stock.save_stock_items import group_items_for_ui
		from yrp.yrp.doctype.yrp_goods_received_note.test_purchase_order_grn import (
			TestPurchaseOrderLotSplits,
			_address,
		)
		from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
			get_purchase_order_defaults,
		)

		po, fieldname, first_lot, other_lot = TestPurchaseOrderLotSplits.order_with_two_lots(self)
		source = get_purchase_order_defaults(po.name)["items"][0]
		lots = [first_lot, other_lot]
		rows = [
			{**source, fieldname: lots[index], "quantity": quantity}
			for index, quantity in enumerate(quantities)
		]
		values = {
			"purchase_order": po.name,
			"supplier_address": _address(f"_Test Web GRN Supplier {frappe.generate_hash(length=6)}"),
			"delivery_address": _address(f"_Test Web GRN Delivery {frappe.generate_hash(length=6)}"),
			"item_details": group_items_for_ui(rows, "YRP Goods Received Note"),
		}
		return po, fieldname, first_lot, other_lot, values

	def test_web_receives_whole_row_into_another_lot(self):
		po, fieldname, _first_lot, other_lot, values = self.receipt_values([0, 6])
		workspace = save_goods_received_note(values, submit=True)
		grn = frappe.get_doc("YRP Goods Received Note", workspace["record"]["name"])
		self.assertEqual(grn.docstatus, 1)
		self.assertEqual(
			[(row.get(fieldname), row.quantity, row.ref_docname) for row in grn.items],
			[(other_lot, 6, po.items[0].name)],
		)

	def test_web_split_reload_and_resave_keep_lots_and_quantities(self):
		from yrp.stock.save_stock_items import ungroup_items_from_ui

		po, fieldname, first_lot, other_lot, values = self.receipt_values([4, 6])
		created = save_goods_received_note(values)
		workspace = get_goods_received_note_workspace(created["record"]["name"])
		rows = ungroup_items_from_ui(workspace["matrices"]["items"], "YRP Goods Received Note")
		self.assertEqual({row[fieldname]: row["quantity"] for row in rows}, {first_lot: 4, other_lot: 6})
		self.assertIn(other_lot, workspace["lot_options"][po.items[0].name])
		result = save_goods_received_note(
			{"item_details": workspace["matrices"]["items"]},
			name=workspace["record"]["name"],
			expected_modified=workspace["record"]["modified"],
			submit=True,
		)
		grn = frappe.get_doc("YRP Goods Received Note", result["record"]["name"])
		self.assertEqual(
			{row.get(fieldname): row.quantity for row in grn.items}, {first_lot: 4, other_lot: 6}
		)
		self.assertTrue(all(row.ref_docname == po.items[0].name for row in grn.items))

	def test_web_save_rejects_unlinked_lot(self):
		po, fieldname, _first_lot, _other_lot, values = self.receipt_values([6])
		for group in values["item_details"]:
			for entry in group["items"]:
				entry["dimensions"][fieldname] = "NOT-LINKED"
		for submit in (False, True):
			with (
				self.subTest(submit=submit),
				self.assertRaisesRegex(frappe.ValidationError, f"Row 1.*NOT-LINKED.*{po.name}"),
			):
				save_goods_received_note(values, submit=submit)

	def test_web_submit_revalidates_existing_draft_after_lot_is_unlinked(self):
		po, _fieldname, _first_lot, other_lot, values = self.receipt_values([0, 6])
		created = save_goods_received_note(values)
		frappe.db.delete(
			po.meta.get_field("sd_lot").options, {"parent": po.name, "parenttype": "Purchase Order"}
		)
		with self.assertRaisesRegex(frappe.ValidationError, f"Row 1.*{other_lot}.*{po.name}"):
			save_goods_received_note(
				{},
				name=created["record"]["name"],
				expected_modified=created["record"]["modified"],
				submit=True,
			)


class TestActualDiaWorkspaceMerge(TestCase):
	def test_context_is_only_exposed_on_standard_work_order_drafts(self):
		from essdee_yrp.fabric_store.documents.goods_received_note import _actual_dia_context

		context = {"enabled": True, "attribute": "Dia", "dia_options": ["14"]}
		document = frappe._dict(docstatus=0, against="YRP Work Order", against_id="WO-1")
		with patch("essdee_yrp.fabric_grn.get_actual_dia_context", return_value=context) as get_context:
			self.assertEqual(_actual_dia_context(document), context)
			get_context.assert_called_once_with("WO-1")
			for field in ("is_return", "is_rework", "additional_grn", "includes_packing", "docstatus"):
				self.assertFalse(_actual_dia_context(frappe._dict(document, **{field: 1}))["enabled"])
			self.assertFalse(_actual_dia_context(frappe._dict(document, against="Purchase Order"))["enabled"])

	def test_added_variant_with_colour_change_is_rejected(self):
		from essdee_yrp.fabric_store.documents.goods_received_note import _merge_actual_dia_rows

		source = {"item_variant": "Greige-14", "ref_doctype": "YRP Work Order Receivables", "ref_docname": "REC-1", "quantity": 10}
		browser = {**source, "item_variant": "Blue-14.5", "quantity": 20}
		with (
			patch("essdee_yrp.fabric_store.documents.goods_received_note._dimension_fieldnames", return_value=()),
			patch("essdee_yrp.fabric_grn.get_parent_item", return_value="Fabric"),
			patch("essdee_yrp.fabric_grn.get_dia_attribute", return_value="Dia"),
			patch("essdee_yrp.fabric_grn._variant_attrs", side_effect=[{"Colour": "Greige", "Dia": "14"}, {"Colour": "Blue", "Dia": "14.5"}]),
			self.assertRaisesRegex(frappe.ValidationError, "only Dia may differ"),
		):
			_merge_actual_dia_rows([source], [browser])
