from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.model.base_document import get_controller
from frappe.tests.utils import FrappeTestCase
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import PurchaseInvoice

from essdee_yrp.erp import get_erp_response_message
from essdee_yrp.erp_purchase_invoice import (
	CANCEL_ENDPOINT,
	CREATE_ENDPOINT,
	EXPENSE_ACCOUNT_ENDPOINT,
	SUBMIT_ENDPOINT,
	_create_local_erp_invoice,
	_run_local_erp_action,
	build_erp_invoice_payload,
	cancel_erp_invoice,
	close_bill_tracking_from_erp,
	create_erp_invoice,
	fetch_expense_accounts,
	fetch_items_expense_head,
	get_bill_tracking_invoice_defaults,
	get_erp_inv_link,
	revert_bill_tracking_from_erp,
	submit_erp_invoice,
)
from essdee_yrp.purchase_invoice import (
	MODERN_RATE_SOURCE,
	_physical_rate_weights,
	_unique_quantity_partition,
	build_legacy_work_order_invoice_payload,
	build_purchase_order_invoice_payload,
	build_verification_details,
	commercial_group_key,
	project_purchase_order_items,
)


class TestPurchaseInvoiceCustomization(FrappeTestCase):
	def test_legacy_direct_item_quantity_partition_must_be_unique(self):
		items = [("S", 264), ("M", 2016), ("L", 2016), ("2XL", 404)]
		self.assertIsNone(_unique_quantity_partition(items, [("RATE-8", 2684), ("RATE-0", 2016)]))
		self.assertEqual(
			_unique_quantity_partition(
				[("S", 264), ("M", 2016), ("2XL", 404), ("REST", 7903)],
				[("RATE-8", 2684), ("RATE-0", 7903)],
			),
			[("RATE-8", ["S", "M", "2XL"]), ("RATE-0", ["REST"])],
		)

	def test_legacy_rate_edit_rebuilds_only_hidden_physical_rows(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "MPI-LEGACY-TEST"
		invoice.against = "YRP Work Order"
		invoice.essdee_rate_table_source = "migrated_v1"
		invoice.append(
			"essdee_items",
			{
				"item": "PROCESS-ITEM",
				"qty": 10,
				"uom": "Nos",
				"rate": 7,
				"group_key": "GROUP-1",
			},
		)
		payload = {
			"items": [
				{
					"item": "PHYSICAL-ITEM",
					"qty": 10,
					"uom": "Nos",
					"rate": 7,
				}
			],
			"total_quantity": 10,
			"unlinked": False,
		}
		with patch(
			"essdee_yrp.overrides.purchase_invoice.build_legacy_work_order_invoice_payload",
			return_value=payload,
		) as rebuild:
			invoice._rebuild_essdee_work_order_items()
		rebuild.assert_called_once_with(invoice)
		self.assertEqual(invoice.essdee_items[0].item, "PROCESS-ITEM")
		self.assertEqual(invoice.items[0].item, "PHYSICAL-ITEM")

	def test_purchase_order_grouped_rate_rebuilds_direct_grn_rows(self):
		group_key = commercial_group_key("INNER-ELASTIC-8MM", "Open Lot", "Meter", 0.7, None)

		def purchase_order_invoice(final_rate):
			invoice = frappe.new_doc("YRP Purchase Invoice")
			invoice.name = "MPI-PO-LEGACY-TEST"
			invoice.against = "Purchase Order"
			invoice.essdee_rate_table_source = "migrated_v1"
			invoice.append(
				"items",
				{
					"item": "INNER-ELASTIC-8MM",
					"lot": "Open Lot",
					"item_group": "Purchase Accessories",
					"qty": 100,
					"uom": "Meter",
					"source_rate": 0.7,
					"rate": 0.7,
					"amount": 70,
					"actual_rate": 0.7,
					"actual_qty": 100,
					"essdee_group_key": group_key,
					"essdee_rate_weight": 1,
				},
			)
			invoice.append(
				"essdee_items",
				{
					"item": "INNER-ELASTIC-8MM",
					"lot": "Open Lot",
					"item_group": "Purchase Accessories",
					"qty": 100,
					"uom": "Meter",
					"source_rate": 0.7,
					"rate": final_rate,
					"amount": 100 * final_rate,
					"group_key": group_key,
				},
			)
			return invoice

		before = purchase_order_invoice(0.7)
		invoice = purchase_order_invoice(0.9)
		# A forged hidden-table rate is ignored; the saved direct GRN structure and
		# the posted grouped final rate are the only inputs to the rebuild.
		invoice.items[0].rate = 500
		with patch.object(invoice, "get_doc_before_save", return_value=before):
			invoice._rebuild_essdee_purchase_order_items()

		self.assertEqual(invoice.items[0].rate, 0.9)
		self.assertEqual(invoice.items[0].amount, 90)
		self.assertEqual(invoice.items[0].source_rate, 0.7)
		self.assertEqual(invoice.items[0].essdee_group_key, group_key)
		self.assertEqual(invoice.essdee_items[0].rate, 0.9)

	def test_purchase_order_projection_groups_direct_grn_variants(self):
		direct, grouped = project_purchase_order_items(
			[
				{
					"item": "INNER-ELASTIC-8MM",
					"lot": "Open Lot",
					"item_group": "Purchase Accessories",
					"qty": 100,
					"uom": "Meter",
					"source_rate": 0.7,
					"rate": 0.7,
				},
				{
					"item": "INNER-ELASTIC-8MM",
					"lot": "Open Lot",
					"item_group": "Purchase Accessories",
					"qty": 50,
					"uom": "Meter",
					"source_rate": 0.7,
					"rate": 0.7,
				},
			]
		)

		self.assertEqual(len(direct), 2)
		self.assertEqual(len(grouped), 1)
		self.assertEqual(grouped[0]["qty"], 150)
		self.assertEqual(grouped[0]["amount"], 105)
		self.assertTrue(all(row["essdee_group_key"] == grouped[0]["group_key"] for row in direct))

	def test_purchase_order_payload_takes_tax_from_po_item_when_grn_row_has_none(self):
		grn_item = frappe._dict(
			item_variant="YARN-1",
			quantity=10,
			rate=100,
			uom="Kg",
			tax=None,
			ref_doctype="Purchase Order Item",
			ref_docname="PO-ITEM-1",
		)
		grn = frappe._dict(name="GRN-1", supplier="SUPPLIER-1", items=[grn_item])
		module = "essdee_yrp.purchase_invoice"
		with (
			patch(f"{module}._validate_selected_grn"),
			patch(f"{module}.frappe.get_doc", return_value=grn),
			patch(f"{module}._get_po_material_rate", return_value=100),
			patch(f"{module}._get_item_group", return_value="Yarn"),
			patch(f"{module}._get_tax_rate", side_effect=lambda tax: float(tax or 0)),
			patch(f"{module}.frappe.db.get_value", return_value="5") as get_value,
		):
			payload = build_purchase_order_invoice_payload(["GRN-1"], supplier="SUPPLIER-1")

		get_value.assert_called_once_with("Purchase Order Item", "PO-ITEM-1", "tax")
		self.assertEqual(payload["items"][0]["tax"], "5")
		self.assertEqual(payload["commercial_items"][0]["tax"], "5")
		self.assertAlmostEqual(payload["tax_total"], 50)
		self.assertAlmostEqual(payload["total"], 1050)

	def test_purchase_order_payload_caps_selected_grns_at_server_boundary(self):
		with self.assertRaises(frappe.ValidationError):
			build_purchase_order_invoice_payload(
				[f"GRN-{index}" for index in range(201)],
			)

	def test_legacy_projection_allows_only_rate_changes_without_refetch(self):
		def legacy_invoice(rate=7, qty=10):
			invoice = frappe.new_doc("YRP Purchase Invoice")
			invoice.name = "MPI-LEGACY-TEST"
			invoice.supplier = "SUPPLIER-1"
			invoice.against = "YRP Work Order"
			invoice.essdee_rate_table_source = "migrated_v1"
			invoice.append(
				"essdee_items",
				{
					"item": "PROCESS-ITEM",
					"qty": qty,
					"uom": "Nos",
					"source_rate": 7,
					"rate": rate,
					"group_key": "GROUP-1",
				},
			)
			return invoice

		before = legacy_invoice()
		invoice = legacy_invoice(rate=8)
		with patch.object(invoice, "get_doc_before_save", return_value=before):
			invoice._validate_legacy_projection_inputs()
			invoice.essdee_items[0].qty = 11
			with self.assertRaises(frappe.ValidationError):
				invoice._validate_legacy_projection_inputs()
			invoice.essdee_rate_table_source = "yrp_grn_v1"
			invoice._validate_legacy_projection_inputs()

	def test_legacy_projection_rejects_negative_rates_and_duplicate_groups(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "MPI-LEGACY-TEST"
		invoice.append(
			"essdee_items",
			{
				"item": "PROCESS-ITEM",
				"qty": 10,
				"uom": "Nos",
				"rate": -1,
				"group_key": "GROUP-1",
			},
		)
		with self.assertRaises(frappe.ValidationError):
			build_legacy_work_order_invoice_payload(invoice)

		invoice.essdee_items[0].rate = 1
		invoice.append(
			"essdee_items",
			{
				"item": "PROCESS-ITEM",
				"qty": 10,
				"uom": "Nos",
				"rate": 1,
				"group_key": "GROUP-1",
			},
		)
		with self.assertRaises(frappe.ValidationError):
			build_legacy_work_order_invoice_payload(invoice)

	def test_remote_erp_exception_details_are_not_rendered_to_users(self):
		response = MagicMock(status_code=500, text="")
		response.json.return_value = {"exception": '<img src=x onerror="alert(1)"> internal traceback'}
		with (
			patch("essdee_yrp.erp.frappe.log_error") as log_error,
			self.assertRaises(frappe.ValidationError) as raised,
		):
			get_erp_response_message(response, title="ERP test")

		self.assertNotIn("onerror", str(raised.exception))
		self.assertIn("Check Error Log", str(raised.exception))
		log_error.assert_called_once()

	def test_essdee_controller_and_fetch_override_are_active(self):
		self.assertEqual(
			get_controller("YRP Purchase Invoice").__name__,
			"EssdeePurchaseInvoice",
		)
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(
			overrides["yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.fetch_grn_details"][-1],
			"essdee_yrp.purchase_invoice.fetch_grn_details",
		)
		self.assertEqual(
			overrides[
				"production_api.production_api.doctype.vendor_bill_tracking."
				"vendor_bill_tracking.close_vendor_bill"
			][-1],
			"essdee_yrp.erp_purchase_invoice.close_bill_tracking_from_erp",
		)
		self.assertEqual(
			overrides[
				"production_api.production_api.doctype.vendor_bill_tracking."
				"vendor_bill_tracking.revert_purchase_invoice_link"
			][-1],
			"essdee_yrp.erp_purchase_invoice.revert_bill_tracking_from_erp",
		)

	def test_rate_projection_markers_cannot_be_used_to_bypass_fetch(self):
		legacy = frappe.new_doc("YRP Purchase Invoice")
		legacy.essdee_rate_table_source = "migrated_v1"
		with self.assertRaises(frappe.ValidationError):
			legacy.before_validate()

		unfetched = frappe.new_doc("YRP Purchase Invoice")
		unfetched.against = "YRP Work Order"
		with self.assertRaises(frappe.ValidationError):
			unfetched.before_submit()

	def test_parent_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("YRP Purchase Invoice", cached=False)
		expected = {
			"gstin": ("Data", None),
			"pan_no": ("Data", None),
			"gst_state": ("Select", "\nIn-State\nOut-State"),
			"do_not_submit_invoice": ("Check", None),
			"erp_inv_name": ("Data", None),
			"erp_inv_docstatus": ("Int", None),
			"final_amount": ("Currency", None),
			"eligibility_for_itc": (
				"Select",
				"Input Service Distributor\nImport Of Service\nImport Of Capital Goods\n"
				"ITC on Reverse Charge\nIneligible As Per Section 17(5)\n"
				"Ineligible Others\nAll Other ITC",
			),
			"cancel_without_cancelling_erp_inv": ("Check", None),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), definition)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "YRP Purchase Invoice",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

		self.assertIsNone(meta.get_field("vendor_bill_tracking"))
		bill_tracking = meta.get_field("bill_tracking")
		self.assertEqual((bill_tracking.fieldtype, bill_tracking.options), ("Link", "YRP Bill Tracking"))
		self.assertFalse(
			frappe.db.exists(
				"Custom Field",
				{"dt": "YRP Purchase Invoice", "fieldname": "bill_tracking"},
			)
		)

	def test_mrp_settings_owns_complete_erp_connection_contract(self):
		meta = frappe.get_meta("SD YRP MRP Settings", cached=False)
		expected = {
			"enable_purchase_invoice_sync": "Check",
			"erp_site_url": "Data",
			"erp_api_key": "Data",
			"erp_api_secret": "Password",
			"purchase_invoice_series_map": "Table",
		}
		for fieldname, fieldtype in expected.items():
			with self.subTest(fieldname=fieldname):
				self.assertEqual(meta.get_field(fieldname).fieldtype, fieldtype)

	def test_erp_payload_uses_process_items_not_hidden_physical_rows(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "YRP-MPI-TEST"
		invoice.naming_series = "YRP-MPI-.YYYY.-"
		invoice.against = "YRP Work Order"
		invoice.bill_tracking = "BT-TEST"
		invoice.append(
			"items",
			{
				"item": "Physical Panel",
				"item_group": "Panels",
				"qty": 200,
				"uom": "Nos",
				"rate": 2.5,
				"tax": "5",
			},
		)
		invoice.append(
			"essdee_items",
			{
				"item": "Stitching Charges",
				"lot": "LOT-TEST",
				"item_group": "Service",
				"expense_head": "Job Work Charges - E",
				"qty": 100,
				"uom": "Nos",
				"source_rate": 5,
				"rate": 7,
				"tax": "5",
				"group_key": "group-1",
			},
		)

		with patch(
			"essdee_yrp.erp_purchase_invoice.get_purchase_invoice_series",
			return_value="ERP-PI-.YYYY.-",
		):
			payload = build_erp_invoice_payload(invoice)

		self.assertEqual(payload["vendor_bill_tracking"], "BT-TEST")
		self.assertNotIn("bill_tracking", payload)
		self.assertNotIn("essdee_items", payload)
		self.assertEqual(payload["mapped_series"], "ERP-PI-.YYYY.-")
		self.assertEqual(len(payload["items"]), 1)
		self.assertEqual(payload["items"][0]["item"], "Stitching Charges")
		self.assertEqual(payload["items"][0]["lot"], "LOT-TEST")
		self.assertEqual(payload["items"][0]["qty"], 100)
		self.assertEqual(payload["items"][0]["rate"], 7)
		self.assertEqual(payload["items"][0]["tax"], 5)

	def test_purchase_order_erp_payload_uses_grouped_items_not_direct_rows(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "YRP-MPI-PO-TEST"
		invoice.naming_series = "YRP-MPI-.YYYY.-"
		invoice.against = "Purchase Order"
		invoice.append(
			"items",
			{"item": "DIRECT-GRN-ITEM", "qty": 10, "uom": "Nos", "rate": 5},
		)
		invoice.append(
			"essdee_items",
			{
				"item": "GROUPED-PO-ITEM",
				"qty": 10,
				"uom": "Nos",
				"source_rate": 5,
				"rate": 7,
				"group_key": "group-1",
			},
		)
		with patch(
			"essdee_yrp.erp_purchase_invoice.get_purchase_invoice_series",
			return_value="ERP-PI-.YYYY.-",
		):
			payload = build_erp_invoice_payload(invoice)

		self.assertEqual(len(payload["items"]), 1)
		self.assertEqual(payload["items"][0]["item"], "GROUPED-PO-ITEM")
		self.assertEqual(payload["items"][0]["rate"], 7)

	def test_expense_account_fetch_is_deduplicated_by_billing_item(self):
		response = object()
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.is_purchase_invoice_sync_active",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.post_erp_request",
				return_value=response,
			) as post,
			patch(
				"essdee_yrp.erp_purchase_invoice.get_erp_response_message",
				return_value="Job Work Charges - E",
			),
		):
			rows = fetch_expense_accounts(
				[
					{"item": "Stitching Charges", "qty": 10},
					{"item": "Stitching Charges", "qty": 20},
				]
			)

		post.assert_called_once_with(
			EXPENSE_ACCOUNT_ENDPOINT,
			{"item": "Stitching Charges"},
		)
		self.assertEqual(
			[row["expense_head"] for row in rows],
			["Job Work Charges - E", "Job Work Charges - E"],
		)

	def test_same_site_expense_account_fetch_uses_local_erpnext_data(self):
		api = MagicMock()
		api.get_erp_item_expense_account.return_value = "Job Work Charges - E"
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice._local_erp_purchase_invoice_api",
				return_value=api,
			),
			patch("essdee_yrp.erp_purchase_invoice.post_erp_request") as post,
		):
			rows = fetch_expense_accounts(
				[
					{"item": "Stitching Charges", "qty": 10},
					{"item": "Stitching Charges", "qty": 20},
				]
			)

		api.get_erp_item_expense_account.assert_called_once_with("Stitching Charges")
		post.assert_not_called()
		self.assertEqual(
			[row["expense_head"] for row in rows],
			["Job Work Charges - E", "Job Work Charges - E"],
		)

	def test_public_expense_account_fetch_is_bounded(self):
		with (
			patch("essdee_yrp.erp_purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.erp_purchase_invoice.post_erp_request") as post,
			self.assertRaisesRegex(frappe.ValidationError, "maximum of 200"),
		):
			fetch_items_expense_head([{"item": f"ITEM-{index}"} for index in range(201)])
		post.assert_not_called()

	def test_controller_runs_local_validation_before_erp_lifecycle(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.against = "Purchase Order"
		invoice.essdee_rate_table_source = MODERN_RATE_SOURCE
		with (
			patch.object(PurchaseInvoice, "before_submit") as local_submit,
			patch("essdee_yrp.overrides.purchase_invoice.create_erp_invoice") as erp_create,
		):
			invoice.before_submit()
			local_submit.assert_called_once_with()
			erp_create.assert_called_once_with(invoice)

		lifecycle = MagicMock()
		with (
			patch.object(PurchaseInvoice, "before_cancel") as local_cancel,
			patch("essdee_yrp.overrides.purchase_invoice.cancel_erp_invoice") as erp_cancel,
			patch(
				"essdee_yrp.overrides.purchase_invoice.unlink_erp_invoice_from_bill_tracking"
			) as unlink_erp,
		):
			lifecycle.attach_mock(unlink_erp, "unlink")
			lifecycle.attach_mock(erp_cancel, "cancel")
			invoice.before_cancel()
			local_cancel.assert_called_once_with()
			self.assertEqual(
				lifecycle.mock_calls,
				[call.unlink(invoice), call.cancel(invoice)],
			)

		with (
			patch.object(PurchaseInvoice, "on_submit") as local_on_submit,
			patch("essdee_yrp.overrides.purchase_invoice.link_erp_invoice_to_bill_tracking") as link_erp,
		):
			invoice.on_submit()
			local_on_submit.assert_called_once_with()
			link_erp.assert_called_once_with(invoice)

	def test_modern_work_order_submit_does_not_refetch_or_block_on_warnings(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "PI-WARNING-TEST"
		invoice.against = "YRP Work Order"
		invoice.supplier = "SUP-1"
		invoice.essdee_rate_table_source = MODERN_RATE_SOURCE
		invoice.append("grn", {"grn": "GRN-BAD"})
		invoice.append("essdee_items", {"group_key": "GROUP-1", "rate": 0})
		with (
			patch("essdee_yrp.overrides.purchase_invoice.build_work_order_invoice_payload") as build_payload,
			patch.object(PurchaseInvoice, "before_submit") as local_submit,
			patch("essdee_yrp.overrides.purchase_invoice.create_erp_invoice") as erp_create,
		):
			invoice.before_submit()

		build_payload.assert_not_called()
		local_submit.assert_called_once_with()
		erp_create.assert_called_once_with(invoice)

	def test_validate_locks_selected_grns_and_rechecks_active_owner_before_base(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "PI-NEW"
		invoice.append("grn", {"grn": "GRN-B"})
		invoice.append("grn", {"grn": "GRN-A"})
		locked = [
			frappe._dict(name="GRN-A", purchase_invoice_name="PI-OTHER"),
			frappe._dict(name="GRN-B", purchase_invoice_name=None),
		]

		def locking_read(query, _params, **_kwargs):
			if "tabYRP Goods Received Note" in query:
				return locked
			if "tabYRP Purchase Invoice GRN" in query:
				return []
			if "tabYRP Purchase Invoice`" in query:
				return [frappe._dict(name="PI-OTHER", docstatus=0)]
			raise AssertionError(query)

		with (
			patch.object(invoice, "_reset_changed_commercial_approval"),
			patch(
				"essdee_yrp.overrides.purchase_invoice.frappe.db.sql",
				side_effect=locking_read,
			) as sql,
			patch("essdee_yrp.overrides.purchase_invoice.frappe.get_all", return_value=[]) as get_all,
			patch.object(PurchaseInvoice, "validate") as base_validate,
			self.assertRaisesRegex(frappe.ValidationError, "GRN-A.*PI-OTHER"),
		):
			invoice.validate()

		self.assertEqual(len(sql.call_args_list), 3)
		self.assertTrue(all("FOR UPDATE" in call.args[0] for call in sql.call_args_list))
		self.assertEqual(sql.call_args_list[0].args[1], ("GRN-A", "GRN-B"))
		self.assertEqual(
			sql.call_args_list[1].args[1],
			("YRP Purchase Invoice", "GRN-A", "GRN-B"),
		)
		self.assertEqual(sql.call_args_list[2].args[1], ("PI-OTHER",))
		get_all.assert_not_called()
		base_validate.assert_not_called()

	def test_modern_work_order_submit_uses_identity_preserving_allocator(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.against = "YRP Work Order"
		invoice.essdee_rate_table_source = MODERN_RATE_SOURCE
		with (
			patch.object(PurchaseInvoice, "on_submit") as base_submit,
			patch.object(invoice, "close_bill_tracking") as close_bill,
			patch(
				"essdee_yrp.overrides.purchase_invoice.create_work_order_purchase_invoice_adjustment"
			) as create_adjustment,
			patch("essdee_yrp.overrides.purchase_invoice.link_erp_invoice_to_bill_tracking") as link_erp,
		):
			invoice.on_submit()

		base_submit.assert_not_called()
		close_bill.assert_called_once_with()
		create_adjustment.assert_called_once_with(invoice)
		link_erp.assert_called_once_with(invoice)

	def test_same_site_create_uses_local_erp_creator(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "YRP-MPI-LOCAL"
		result = {
			"name": "ERP-PI-LOCAL",
			"docstatus": 1,
			"amount": 125,
			"due_date": "2026-09-30",
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.build_erp_invoice_payload",
				return_value={"name": invoice.name},
			),
			patch(
				"essdee_yrp.erp_purchase_invoice._create_local_erp_invoice",
				return_value=result,
			) as local_create,
			patch("essdee_yrp.erp_purchase_invoice.post_erp_request") as post,
		):
			create_erp_invoice(invoice)

		local_create.assert_called_once_with({"name": invoice.name})
		post.assert_not_called()
		self.assertEqual(invoice.erp_inv_name, "ERP-PI-LOCAL")
		self.assertEqual(invoice.erp_inv_docstatus, 1)
		self.assertEqual(invoice.final_amount, 125)

	def test_local_erp_creator_compares_already_prefixed_item_groups_directly(self):
		api = MagicMock()
		api.get_erp_item_expense_account.return_value = "Purchase Expenses - E"
		api._create.return_value = {
			"name": "ERP-PI-LOCAL",
			"docstatus": 1,
			"amount": 125,
			"due_date": "2026-09-30",
		}
		payload = {
			"vendor_bill_tracking": "BT-TEST",
			"items": [
				{
					"item": "POLYTHENE",
					"item_group": "M_Purchase Accessories",
				}
			],
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._local_erp_purchase_invoice_api",
				return_value=api,
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.exists", return_value=True),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.db.get_value",
				return_value="M_Purchase Accessories",
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.set_value"),
		):
			result = _create_local_erp_invoice(payload)

		api.create.assert_not_called()
		api._create.assert_called_once()
		created_payload = api._create.call_args.args[0]
		self.assertEqual(
			created_payload["items"][0]["item_group"],
			"M_Purchase Accessories",
		)
		self.assertIsNone(created_payload["vendor_bill_tracking"])
		self.assertEqual(result["name"], "ERP-PI-LOCAL")

	def test_local_erp_creator_uses_item_master_group_over_stale_row_group(self):
		api = MagicMock()
		api.get_erp_item_expense_account.return_value = "Service Expenses - E"
		api._create.return_value = {"name": "ERP-PI-LOCAL", "docstatus": 0}
		payload = {
			"items": [
				{"item": "STITCHING TO CHECKING EXPENSES", "item_group": "Products"},
				{"item": "POLYTHENE", "item_group": "Purchase Accessories"},
			],
		}
		master_groups = {
			"STITCHING TO CHECKING EXPENSES": "M_Service",
			"POLYTHENE": "M_Purchase Accessories",
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._local_erp_purchase_invoice_api",
				return_value=api,
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.exists", return_value=True),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.db.get_value",
				side_effect=lambda doctype, name, field: master_groups[name],
			),
		):
			_create_local_erp_invoice(payload)

		created_items = api._create.call_args.args[0]["items"]
		self.assertEqual(
			[row["item_group"] for row in created_items],
			["M_Service", "M_Purchase Accessories"],
		)
		self.assertEqual(payload["items"][0]["item_group"], "Products")

	def test_same_site_submit_temporarily_suppresses_legacy_remote_callback(self):
		api = MagicMock()
		api.submit.return_value = {
			"name": "ERP-PI-DRAFT",
			"docstatus": 1,
			"amount": 500,
			"due_date": "2026-09-30",
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.db.get_value",
				return_value="BT-TEST",
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.set_value") as db_set,
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.exists", return_value=True),
			patch(
				"essdee_yrp.erp_purchase_invoice._local_erp_purchase_invoice_api",
				return_value=api,
			),
		):
			result = _run_local_erp_action("submit", "ERP-PI-DRAFT")

		api.submit.assert_called_once_with("ERP-PI-DRAFT")
		self.assertEqual(result["docstatus"], 1)
		self.assertEqual(db_set.call_args_list[0].args[2:4], ("vendor_bill_tracking", None))
		self.assertEqual(db_set.call_args_list[1].args[2:4], ("vendor_bill_tracking", "BT-TEST"))

	def test_same_site_show_bill_routes_to_local_purchase_invoice(self):
		invoice = frappe._dict(
			name="YRP-MPI-LOCAL",
			docstatus=1,
			erp_inv_name="PI/LOCAL 001",
		)
		with (
			patch("essdee_yrp.erp_purchase_invoice.frappe.get_doc", return_value=invoice),
			patch("essdee_yrp.erp_purchase_invoice.frappe.has_permission"),
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=True,
			),
		):
			link = get_erp_inv_link(invoice.name)

		self.assertEqual(link, "/app/purchase-invoice/PI%2FLOCAL%20001")

	def test_create_and_cancel_use_existing_erp_endpoints(self):
		invoice = frappe.new_doc("YRP Purchase Invoice")
		invoice.name = "YRP-MPI-TEST"
		invoice.against = "Purchase Order"
		invoice.erp_inv_name = "ERP-PI-TEST"
		response = object()
		result = {
			"name": "ERP-PI-TEST",
			"docstatus": 1,
			"amount": 123.45,
			"due_date": "2026-09-30",
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.is_purchase_invoice_sync_active",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.build_erp_invoice_payload",
				return_value={"name": invoice.name},
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.post_erp_request",
				return_value=response,
			) as post,
			patch(
				"essdee_yrp.erp_purchase_invoice.get_erp_response_message",
				return_value=result,
			),
		):
			create_erp_invoice(invoice)
			post.assert_called_once_with(CREATE_ENDPOINT, {"data": {"name": invoice.name}})

		self.assertEqual(invoice.erp_inv_docstatus, 1)
		self.assertEqual(invoice.final_amount, 123.45)
		self.assertEqual(str(invoice.due_date), "2026-09-30")

		invoice.erp_inv_docstatus = 1
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.is_purchase_invoice_sync_active",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.post_erp_request",
				return_value=response,
			) as post,
			patch(
				"essdee_yrp.erp_purchase_invoice.get_erp_response_message",
			),
		):
			cancel_erp_invoice(invoice)
			post.assert_called_once_with(CANCEL_ENDPOINT, {"name": "ERP-PI-TEST"})
		self.assertEqual(invoice.erp_inv_docstatus, 2)

	def test_submit_uses_existing_erp_endpoint_and_updates_remote_fields(self):
		invoice = frappe._dict(
			name="YRP-MPI-TEST",
			docstatus=1,
			erp_inv_name="ERP-PI-DRAFT",
			erp_inv_docstatus=0,
		)
		response = object()
		result = {
			"name": "ERP-PI-DRAFT",
			"docstatus": 1,
			"amount": 500,
			"due_date": "2026-09-30",
		}
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.is_same_site_erp_available",
				return_value=False,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.is_purchase_invoice_sync_active",
				return_value=True,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=invoice,
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.has_permission"),
			patch(
				"essdee_yrp.erp_purchase_invoice.post_erp_request",
				return_value=response,
			) as post,
			patch(
				"essdee_yrp.erp_purchase_invoice.get_erp_response_message",
				return_value=result,
			),
			patch("essdee_yrp.erp_purchase_invoice.frappe.db.set_value") as db_set,
		):
			submit_erp_invoice(invoice.name)

		post.assert_called_once_with(SUBMIT_ENDPOINT, {"name": "ERP-PI-DRAFT"})
		db_set.assert_called_once()
		self.assertEqual(invoice.erp_inv_docstatus, 1)
		self.assertEqual(invoice.final_amount, 500)

	def test_legacy_erp_bill_tracking_callbacks_use_the_local_invoice(self):
		bill = MagicMock()
		bill.form_status = "Open"
		bill.purchase_invoice = None
		bill.erp_purchase_invoice = None
		bill.get.side_effect = lambda fieldname: getattr(bill, fieldname, None)
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._same_site_erp_invoice_context",
				return_value=(False, None),
			),
			patch(
				"essdee_yrp.erp_purchase_invoice._local_invoice_for_erp_callback",
				return_value="YRP-MPI-TEST",
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
		):
			close_bill_tracking_from_erp("BT-TEST", "ERP-PI-TEST", "ERP submit")
		bill.close_vendor_bill.assert_called_once_with("YRP-MPI-TEST", "ERP submit")
		bill.save.assert_called_once_with(ignore_permissions=True)
		bill.check_permission.assert_called_once_with("write")

		bill.purchase_invoice = "YRP-MPI-TEST"
		bill.form_status = "Closed"
		bill.erp_purchase_invoice = "ERP-PI-TEST"
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._same_site_erp_invoice_context",
				return_value=(False, None),
			),
			patch(
				"essdee_yrp.erp_purchase_invoice._local_invoice_for_erp_callback",
				return_value="YRP-MPI-TEST",
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
			patch(
				"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.revert_purchase_invoice_link"
			) as revert,
		):
			revert_bill_tracking_from_erp(
				"BT-TEST",
				"purchase_invoice",
				"ERP-PI-TEST",
				origin="ERP-cancel",
			)
		revert.assert_called_once_with(
			"BT-TEST",
			"YRP-MPI-TEST",
			origin="ERP-cancel",
		)
		self.assertEqual(bill.check_permission.call_args_list[-1].args, ("write",))

	def test_same_site_erp_invoice_closes_and_reopens_without_a_yrp_invoice(self):
		bill = MagicMock()
		bill.docstatus = 1
		bill.form_status = "Open"
		bill.purchase_invoice = None
		bill.erp_purchase_invoice = None
		bill.assigned_to = "Accounts"
		bill.get.side_effect = lambda fieldname: getattr(bill, fieldname, None)

		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._same_site_erp_invoice_context",
				return_value=(True, None),
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
		):
			close_bill_tracking_from_erp("BT-TEST", "ERP-PI-TEST", "ERP submit")

		self.assertEqual(bill.form_status, "Closed")
		self.assertEqual(bill.erp_purchase_invoice, "ERP-PI-TEST")
		self.assertEqual(bill.append.call_args.args[0], "bill_tracking_history")
		self.assertEqual(bill.append.call_args.args[1]["action"], "Close")
		bill.save.assert_called_once_with(ignore_permissions=True)

		bill.reset_mock()
		bill.form_status = "Closed"
		bill.erp_purchase_invoice = "ERP-PI-TEST"
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice._same_site_erp_invoice_context",
				return_value=(True, None),
			),
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
		):
			revert_bill_tracking_from_erp(
				"BT-TEST",
				"purchase_invoice",
				"ERP-PI-TEST",
				origin="ERP-cancel",
			)

		self.assertEqual(bill.form_status, "Reopen")
		self.assertIsNone(bill.erp_purchase_invoice)
		self.assertEqual(bill.append.call_args.args[0], "bill_tracking_history")
		self.assertEqual(bill.append.call_args.args[1]["action"], "Reopen")
		bill.save.assert_called_once_with(ignore_permissions=True)

	def test_erp_bill_tracking_callbacks_check_permission_before_lookup(self):
		bill = MagicMock()
		bill.check_permission.side_effect = frappe.PermissionError
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
			patch("essdee_yrp.erp_purchase_invoice._same_site_erp_invoice_context") as same_site_lookup,
			patch("essdee_yrp.erp_purchase_invoice._local_invoice_for_erp_callback") as lookup,
			self.assertRaises(frappe.PermissionError),
		):
			close_bill_tracking_from_erp("BT-TEST", "ERP-PI-TEST")
		same_site_lookup.assert_not_called()
		lookup.assert_not_called()

	def test_child_fields_and_mandatory_item_group(self):
		meta = frappe.get_meta("YRP Purchase Invoice Item", cached=False)
		lot = meta.get_field("lot")
		expense_head = meta.get_field("expense_head")
		item_group = meta.get_field("item_group")

		self.assertEqual((lot.fieldtype, lot.options, lot.in_list_view), ("Link", "SD YRP Lot", 1))
		self.assertEqual(
			(expense_head.fieldtype, expense_head.read_only, expense_head.in_list_view),
			("Data", 1, 1),
		)
		self.assertEqual(item_group.reqd, 1)
		self.assertIsNotNone(meta.get_field("set_combination"))

		for fieldname in ("lot", "expense_head"):
			field = frappe.db.get_value(
				"Custom Field",
				{
					"dt": "YRP Purchase Invoice Item",
					"fieldname": fieldname,
					"module": "Essdee YRP",
				},
				["description", "is_system_generated"],
				as_dict=True,
			)
			self.assertIsNotNone(field)
			self.assertNotEqual(field.description, "Managed by YRP Stock Dimension")
			self.assertEqual(field.is_system_generated, 1)

		self.assertTrue(
			frappe.db.exists(
				"Property Setter",
				{
					"doc_type": "YRP Purchase Invoice Item",
					"field_name": "item_group",
					"property": "reqd",
					"value": "1",
				},
			)
		)

	def test_commercial_table_and_physical_allocation_fields_are_installed(self):
		parent = frappe.get_meta("YRP Purchase Invoice", cached=False)
		commercial = parent.get_field("essdee_items")
		self.assertEqual(
			(commercial.fieldtype, commercial.options),
			("Table", "SD YRP Essdee Purchase Invoice Item"),
		)
		self.assertIsNotNone(parent.get_field("essdee_rate_table_source"))

		physical = frappe.get_meta("YRP Purchase Invoice Item", cached=False)
		self.assertIsNotNone(physical.get_field("essdee_group_key"))
		self.assertIsNotNone(physical.get_field("essdee_rate_weight"))

		visible = frappe.get_meta("SD YRP Essdee Purchase Invoice Item", cached=False)
		self.assertTrue(visible.istable)
		self.assertEqual(visible.get_field("rate").read_only, 0)
		self.assertEqual(visible.get_field("source_rate").read_only, 1)

	def test_group_identity_uses_source_rate_not_editable_final_rate(self):
		key = commercial_group_key("STITCH", "LOT-1", "Nos", 5, "GST 5")
		self.assertEqual(
			key,
			commercial_group_key("STITCH", "LOT-1", "Nos", 5.0, "GST 5"),
		)
		self.assertNotEqual(
			key,
			commercial_group_key("STITCH", "LOT-1", "Nos", 4, "GST 5"),
		)

	def test_verification_details_keep_production_api_colour_size_matrix(self):
		rows = [
			frappe._dict(
				work_order="WO-1",
				item_variant="GARMENT-BLACK-S",
				set_combination='{"major_colour":"Black"}',
				total_delivered=10,
				total_received=9,
				billed=2,
				quantity=3,
			),
			frappe._dict(
				work_order="WO-1",
				item_variant="GARMENT-BLACK-M",
				set_combination={"major_colour": "Black"},
				total_delivered=20,
				total_received=18,
				billed=4,
				quantity=5,
			),
			frappe._dict(
				work_order="WO-1",
				item_variant="GARMENT-NAVY-S",
				set_combination='{"major_colour":"Navy"}',
				total_delivered=7,
				total_received=7,
				billed=1,
				quantity=7,
			),
		]
		attributes = {
			"GARMENT-BLACK-S": {"Size": "S", "Colour": "Black"},
			"GARMENT-BLACK-M": {"Size": "M", "Colour": "Black"},
			"GARMENT-NAVY-S": {"Size": "S", "Colour": "Navy"},
		}
		context = frappe._dict(
			lot="LOT-1",
			item_name="Garment",
			is_set_item=0,
			primary_attribute="Size",
			packing_attr="Colour",
			set_attr=None,
		)
		with (
			patch(
				"essdee_yrp.purchase_invoice._get_variant_attribute_map",
				return_value=attributes,
			),
			patch(
				"essdee_yrp.purchase_invoice._get_verification_work_order_context",
				return_value=context,
			),
			patch(
				"essdee_yrp.purchase_invoice._get_existing_verification_bills",
				return_value=[{"pi_name": "MPI-OLD"}],
			),
		):
			details = build_verification_details(rows)

		self.assertEqual(len(details), 1)
		matrix = details[0]
		self.assertEqual(matrix["sizes"], ["S", "M"])
		self.assertEqual(list(matrix["colours"]), ["Black", "Navy"])
		self.assertEqual(matrix["bills"], [{"pi_name": "MPI-OLD"}])
		self.assertEqual(matrix["colours"]["Black"]["data"]["M"]["quantity"], 5)
		self.assertEqual(matrix["total_qty"]["Black"]["total_received"], 27)
		self.assertEqual(matrix["grand_total"]["sizes"]["S"]["total_delivered"], 17)
		self.assertEqual(matrix["grand_total"]["total"]["pending_for_bill"], 27)

	def test_verification_details_preserve_set_item_colour_and_part(self):
		row = frappe._dict(
			work_order="WO-SET",
			item_variant="SET-TOP-NAVY-60",
			set_combination={"major_colour": "Dark Navy", "major_part": "Top"},
			total_delivered=10,
			total_received=10,
			billed=0,
			quantity=10,
		)
		with (
			patch(
				"essdee_yrp.purchase_invoice._get_variant_attribute_map",
				return_value={
					"SET-TOP-NAVY-60": {
						"Size": "60 cm",
						"Colour": "Dark Navy",
						"Part": "Top",
					}
				},
			),
			patch(
				"essdee_yrp.purchase_invoice._get_verification_work_order_context",
				return_value=frappe._dict(
					lot="LOT-SET",
					item_name="Capri Set",
					is_set_item=1,
					primary_attribute="Size",
					packing_attr="Colour",
					set_attr="Part",
				),
			),
			patch(
				"essdee_yrp.purchase_invoice._get_existing_verification_bills",
				return_value=[],
			),
		):
			matrix = build_verification_details([row])[0]

		key = "Dark Navy(Dark Navy) @Top"
		self.assertEqual(matrix["colours"][key]["part"], "Top")
		self.assertEqual(matrix["colours"][key]["data"]["60 cm"]["quantity"], 10)

	def test_finished_rate_splits_across_panel_multiplicity(self):
		front = frappe._dict(name="front", qty=100, cost=1)
		back = frappe._dict(name="back", qty=100, cost=1)
		sleeve = frappe._dict(name="sleeve", qty=200, cost=0.5)
		demand = {
			"planned_qty": 100,
			"source_rate": 3,
			"receivables": [front, back, sleeve],
		}
		weights = _physical_rate_weights(demand, None)
		self.assertEqual(weights, {"front": 1 / 3, "back": 1 / 3, "sleeve": 1 / 6})
		final_rate = 5
		physical_value = sum(row.qty * final_rate * weights[row.name] for row in (front, back, sleeve))
		self.assertAlmostEqual(physical_value, demand["planned_qty"] * final_rate)

	def test_zero_source_rate_uses_value_preserving_quantity_fallback(self):
		front = frappe._dict(name="front", qty=100, cost=0)
		sleeve = frappe._dict(name="sleeve", qty=200, cost=0)
		demand = {
			"planned_qty": 100,
			"source_rate": 0,
			"receivables": [front, sleeve],
		}
		weights = _physical_rate_weights(demand, None)
		self.assertEqual(weights, {"front": 1 / 3, "sleeve": 1 / 3})
		self.assertAlmostEqual(
			front.qty * weights["front"] + sleeve.qty * weights["sleeve"],
			100,
		)


class TestBillTrackingInvoiceDefaults(TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.previous_user)
		self.addCleanup(frappe.db.rollback)
		self.bill = frappe.get_doc(
			{
				"doctype": "YRP Bill Tracking",
				"supplier": frappe.db.get_value("Supplier", {"disabled": 0}, "name"),
				"bill_no": f"LOCAL-VBT-{frappe.generate_hash(length=10)}",
				"bill_date": "2026-10-20",
				"invoice_value": 1250.75,
				"received_via": frappe.db.get_value("YRP Bill Tracking Received Via", {}, "name"),
				"receive_comment": "Local-only invoice prefill regression test",
			}
		).insert()
		self.bill.submit()

	def test_prefills_saved_bill_without_creating_an_invoice(self):
		before = frappe.db.count("Purchase Invoice")
		defaults = get_bill_tracking_invoice_defaults(self.bill.name)
		self.assertEqual(defaults["supplier"], self.bill.supplier)
		self.assertEqual(defaults["bill_no"], self.bill.bill_no)
		self.assertEqual(str(defaults["bill_date"]), "2026-10-20")
		self.assertEqual(defaults["vendor_bill_tracking"], self.bill.name)
		self.assertEqual(defaults["remarks"], "Bill Tracking Invoice Value: 1250.75")
		self.assertEqual(frappe.db.count("Purchase Invoice"), before)
		self.assertFalse(frappe.db.get_value("YRP Bill Tracking", self.bill.name, "erp_purchase_invoice"))
		meta = frappe.get_meta("Purchase Invoice")
		self.assertTrue(all(meta.has_field(fieldname) for fieldname in defaults))

	def test_rejects_ineligible_bills(self):
		for values in (
			{"docstatus": 0},
			{"docstatus": 2},
			{"form_status": "Pending Approval"},
			{"form_status": "Cancel Request Approved"},
			{"form_status": "Closed"},
			{"form_status": "Cancelled"},
			{"purchase_invoice": "LOCAL-VBT-YRP-PI"},
			{"erp_purchase_invoice": "LOCAL-VBT-ERP-PI"},
		):
			with self.subTest(values=values):
				frappe.db.savepoint("bill_state")
				frappe.db.set_value("YRP Bill Tracking", self.bill.name, values)
				with self.assertRaises(frappe.ValidationError):
					get_bill_tracking_invoice_defaults(self.bill.name)
				frappe.db.rollback(save_point="bill_state")

	def test_requires_purchase_invoice_create_permission(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_bill_tracking_invoice_defaults(self.bill.name)

	def test_requires_configured_invoice_role(self):
		with (
			patch(
				"yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking.get_role_permissions",
				return_value={"can_create_invoice": False},
			),
			self.assertRaises(frappe.PermissionError),
		):
			get_bill_tracking_invoice_defaults(self.bill.name)

	def test_requires_bill_read_permission(self):
		with (
			patch.object(
				type(self.bill), "check_permission", side_effect=frappe.PermissionError
			) as check_permission,
			self.assertRaises(frappe.PermissionError),
		):
			get_bill_tracking_invoice_defaults(self.bill.name)
		check_permission.assert_called_once_with("read")

	def test_does_not_copy_masked_or_unreadable_source_values(self):
		for value in ("XXXXXXXXXX", "XXXXXXXX", None):
			with self.subTest(value=value):

				def restrict_supplier(doc):
					doc.supplier = value

				with (
					patch.object(type(self.bill), "apply_fieldlevel_read_permissions", restrict_supplier),
					self.assertRaises(frappe.PermissionError),
				):
					get_bill_tracking_invoice_defaults(self.bill.name)
