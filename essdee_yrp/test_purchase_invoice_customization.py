from unittest.mock import MagicMock, patch

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
	build_erp_invoice_payload,
	cancel_erp_invoice,
	close_bill_tracking_from_erp,
	create_erp_invoice,
	fetch_expense_accounts,
	fetch_items_expense_head,
	revert_bill_tracking_from_erp,
	submit_erp_invoice,
)
from essdee_yrp.purchase_invoice import (
	_physical_rate_weights,
	_unique_quantity_partition,
	build_legacy_work_order_invoice_payload,
	build_purchase_order_invoice_payload,
	build_verification_details,
	build_work_order_invoice_payload,
	commercial_group_key,
	project_purchase_order_items,
)


class TestPurchaseInvoiceCustomization(FrappeTestCase):
	def test_legacy_direct_item_quantity_partition_must_be_unique(self):
		items = [("S", 264), ("M", 2016), ("L", 2016), ("2XL", 404)]
		self.assertIsNone(
			_unique_quantity_partition(items, [("RATE-8", 2684), ("RATE-0", 2016)])
		)
		self.assertEqual(
			_unique_quantity_partition(
				[("S", 264), ("M", 2016), ("2XL", 404), ("REST", 7903)],
				[("RATE-8", 2684), ("RATE-0", 7903)],
			),
			[("RATE-8", ["S", "M", "2XL"]), ("RATE-0", ["REST"])],
		)

	def test_legacy_rate_edit_rebuilds_only_hidden_physical_rows(self):
		invoice = frappe.new_doc('YRP Purchase Invoice')
		invoice.name = "MPI-LEGACY-TEST"
		invoice.against = 'YRP Work Order'
		invoice.essdee_rate_table_source = "production_api"
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
		group_key = commercial_group_key(
			"INNER-ELASTIC-8MM", "Open Lot", "Meter", 0.7, None
		)

		def purchase_order_invoice(final_rate):
			invoice = frappe.new_doc('YRP Purchase Invoice')
			invoice.name = "MPI-PO-LEGACY-TEST"
			invoice.against = 'YRP Purchase Order'
			invoice.essdee_rate_table_source = "production_api"
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
		self.assertTrue(
			all(row["essdee_group_key"] == grouped[0]["group_key"] for row in direct)
		)

	def test_purchase_order_payload_caps_selected_grns_at_server_boundary(self):
		with self.assertRaises(frappe.ValidationError):
			build_purchase_order_invoice_payload(
				[f"GRN-{index}" for index in range(201)],
			)

	def test_legacy_projection_allows_only_rate_changes_without_refetch(self):
		def legacy_invoice(rate=7, qty=10):
			invoice = frappe.new_doc('YRP Purchase Invoice')
			invoice.name = "MPI-LEGACY-TEST"
			invoice.supplier = "SUPPLIER-1"
			invoice.against = 'YRP Work Order'
			invoice.essdee_rate_table_source = "production_api"
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
		invoice = frappe.new_doc('YRP Purchase Invoice')
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
		response.json.return_value = {
			"exception": '<img src=x onerror="alert(1)"> internal traceback'
		}
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
			get_controller('YRP Purchase Invoice').__name__,
			"EssdeePurchaseInvoice",
		)
		overrides = frappe.get_hooks("override_whitelisted_methods")
		self.assertEqual(
			overrides[
				"yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice.fetch_grn_details"
			][-1],
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
		legacy = frappe.new_doc('YRP Purchase Invoice')
		legacy.essdee_rate_table_source = "production_api"
		with self.assertRaises(frappe.ValidationError):
			legacy.before_validate()

		unfetched = frappe.new_doc('YRP Purchase Invoice')
		unfetched.against = 'YRP Work Order'
		with self.assertRaises(frappe.ValidationError):
			unfetched.before_submit()

	def test_parent_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta('YRP Purchase Invoice', cached=False)
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
							"dt": 'YRP Purchase Invoice',
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

		self.assertIsNone(meta.get_field("vendor_bill_tracking"))
		bill_tracking = meta.get_field("bill_tracking")
		self.assertEqual((bill_tracking.fieldtype, bill_tracking.options), ("Link", 'YRP Bill Tracking'))
		self.assertFalse(
			frappe.db.exists(
				"Custom Field",
				{"dt": 'YRP Purchase Invoice', "fieldname": "bill_tracking"},
			)
		)

	def test_mrp_settings_owns_complete_erp_connection_contract(self):
		meta = frappe.get_meta('SD YRP MRP Settings', cached=False)
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
		invoice = frappe.new_doc('YRP Purchase Invoice')
		invoice.name = "YRP-MPI-TEST"
		invoice.naming_series = "YRP-MPI-.YYYY.-"
		invoice.against = 'YRP Work Order'
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
		invoice = frappe.new_doc('YRP Purchase Invoice')
		invoice.name = "YRP-MPI-PO-TEST"
		invoice.naming_series = "YRP-MPI-.YYYY.-"
		invoice.against = 'YRP Purchase Order'
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

	def test_public_expense_account_fetch_is_bounded(self):
		with (
			patch("essdee_yrp.erp_purchase_invoice.frappe.has_permission"),
			patch("essdee_yrp.erp_purchase_invoice.post_erp_request") as post,
			self.assertRaisesRegex(frappe.ValidationError, "maximum of 200"),
		):
			fetch_items_expense_head(
				[{"item": f"ITEM-{index}"} for index in range(201)]
			)
		post.assert_not_called()

	def test_controller_runs_local_validation_before_erp_lifecycle(self):
		invoice = frappe.new_doc('YRP Purchase Invoice')
		invoice.against = 'YRP Purchase Order'
		with (
			patch.object(PurchaseInvoice, "before_submit") as local_submit,
			patch(
				"essdee_yrp.overrides.purchase_invoice.create_erp_invoice"
			) as erp_create,
		):
			invoice.before_submit()
			local_submit.assert_called_once_with()
			erp_create.assert_called_once_with(invoice)

		with (
			patch.object(PurchaseInvoice, "before_cancel") as local_cancel,
			patch(
				"essdee_yrp.overrides.purchase_invoice.cancel_erp_invoice"
			) as erp_cancel,
		):
			invoice.before_cancel()
			local_cancel.assert_called_once_with()
			erp_cancel.assert_called_once_with(invoice)

	def test_create_and_cancel_use_existing_erp_endpoints(self):
		invoice = frappe.new_doc('YRP Purchase Invoice')
		invoice.name = "YRP-MPI-TEST"
		invoice.against = 'YRP Purchase Order'
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
		with (
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
		with (
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

	def test_erp_bill_tracking_callbacks_check_permission_before_lookup(self):
		bill = MagicMock()
		bill.check_permission.side_effect = frappe.PermissionError
		with (
			patch(
				"essdee_yrp.erp_purchase_invoice.frappe.get_doc",
				return_value=bill,
			),
			patch(
				"essdee_yrp.erp_purchase_invoice._local_invoice_for_erp_callback"
			) as lookup,
			self.assertRaises(frappe.PermissionError),
		):
			close_bill_tracking_from_erp("BT-TEST", "ERP-PI-TEST")
		lookup.assert_not_called()

	def test_child_fields_and_mandatory_item_group(self):
		meta = frappe.get_meta('YRP Purchase Invoice Item', cached=False)
		lot = meta.get_field("lot")
		expense_head = meta.get_field("expense_head")
		item_group = meta.get_field("item_group")

		self.assertEqual((lot.fieldtype, lot.options, lot.in_list_view), ("Link", 'SD YRP Lot', 1))
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
					"dt": 'YRP Purchase Invoice Item',
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
					"doc_type": 'YRP Purchase Invoice Item',
					"field_name": "item_group",
					"property": "reqd",
					"value": "1",
				},
			)
		)

	def test_commercial_table_and_physical_allocation_fields_are_installed(self):
		parent = frappe.get_meta('YRP Purchase Invoice', cached=False)
		commercial = parent.get_field("essdee_items")
		self.assertEqual(
			(commercial.fieldtype, commercial.options),
			("Table", 'SD YRP Essdee Purchase Invoice Item'),
		)
		self.assertIsNotNone(parent.get_field("essdee_rate_table_source"))

		physical = frappe.get_meta('YRP Purchase Invoice Item', cached=False)
		self.assertIsNotNone(physical.get_field("essdee_group_key"))
		self.assertIsNotNone(physical.get_field("essdee_rate_weight"))

		visible = frappe.get_meta('SD YRP Essdee Purchase Invoice Item', cached=False)
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

	def test_hidden_physical_rows_keep_the_work_order_lot(self):
		grn_item = frappe._dict(
			item_variant="PANEL-BLACK-S",
			uom="Pieces",
			quantity=2,
			stock_qty=2,
			rate=5,
			set_combination=None,
		)
		grn = frappe._dict(
			name="GRN-1",
			against_id="WO-1",
			items=[grn_item],
		)
		calculated = frappe._dict(
			item_variant="GARMENT-BLACK-S",
			delivered_quantity=1,
			received_qty=1,
			billed_qty=0,
			set_combination=None,
		)
		receivable = frappe._dict(
			name="REC-1",
			item_variant="PANEL-BLACK-S",
			qty=2,
			cost=5,
		)
		demand = {
			"row": calculated,
			"selected_qty": 1,
			"planned_qty": 1,
			"source_rate": 10,
			"group_key": "GROUP-1",
			"weights": {"REC-1": 0.5},
			"receivables": [receivable],
		}
		context = {
			"demands": [demand],
			"billing_variant": "CUTTING-CHARGES",
			"billing_uom": "Nos",
			"item_group": "Others",
			"tax": None,
			"lot": "LOT-1",
			"demand_by_receivable": {"REC-1": demand},
			"receivables_by_name": {"REC-1": receivable},
		}
		with (
			patch("essdee_yrp.purchase_invoice._validate_selected_grn"),
			patch(
				"essdee_yrp.purchase_invoice.frappe.get_doc",
				side_effect=lambda doctype, name: grn
				if doctype == 'YRP Goods Received Note'
				else frappe._dict(name=name),
			),
			patch(
				"essdee_yrp.purchase_invoice._build_work_order_context",
				return_value=context,
			),
			patch("essdee_yrp.purchase_invoice._validate_selected_physical_quantities"),
			patch(
				"essdee_yrp.purchase_invoice._receivable_for_grn_item",
				return_value=receivable,
			),
			patch("essdee_yrp.purchase_invoice._get_item_group", return_value="Products"),
		):
			payload = build_work_order_invoice_payload(["GRN-1"], supplier="SUP-1")

		self.assertEqual(payload["commercial_items"][0]["lot"], "LOT-1")
		self.assertEqual(payload["items"][0]["lot"], "LOT-1")
		self.assertEqual(payload["items"][0]["amount"], 10)

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
		physical_value = sum(
			row.qty * final_rate * weights[row.name]
			for row in (front, back, sleeve)
		)
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
