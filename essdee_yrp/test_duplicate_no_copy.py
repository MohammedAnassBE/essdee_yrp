from unittest import TestCase

import frappe

NO_COPY_FIELDS = {
	"YRP Work Order": (
		"status",
		"start_date",
		"end_date",
		"deliverables",
		"receivables",
		"work_order_calculated_items",
		"is_delivered",
		"open_status",
		"close_reason",
		"close_remarks",
		"closed_by",
		"approved_by",
		"rejection_reason",
		"first_dc_date",
		"first_grn_date",
		"last_dc_date",
		"last_grn_date",
		"total_no_of_pieces_delivered",
		"total_no_of_pieces_received",
		"received_types_json",
		"completed_items_json",
		"incompleted_items_json",
		"wo_delivered_completed_json",
		"wo_delivered_incompleted_json",
		"work_order_tracking_logs",
		"work_order_excess_usage_items",
		"work_order_track_pieces",
		"reduce_stock_entry",
		"update_stock_entry",
	),
	"YRP Delivery Challan": (
		"total_delivered_qty",
		"transfer_complete",
		"ste_transferred",
		"ste_transferred_percent",
	),
	"YRP Goods Received Note": (
		"total_received_quantity",
		"purchase_invoice_name",
		"transfer_complete",
		"ste_transferred",
		"ste_transferred_percent",
	),
	"SD YRP Lot": ("status", "last_calculated_time", "is_transferred", "transferred_lot", "has_transferred"),
	"SD YRP Cutting Plan": (
		"cp_status",
		"open_status",
		"no_of_colours_completed",
		"completed_items_json",
		"incomplete_items_json",
		"cutting_start_date",
		"cutting_end_date",
	),
	"SD YRP Cutting Order": (
		"co_status",
		"completed_items_json",
		"incomplete_items_json",
		"cutting_start_date",
		"cutting_end_date",
	),
	"SD YRP Finishing Plan": (
		"fp_status",
		"fp_status_since",
		"finishing_start_date",
		"finishing_end_date",
		"audit_requested_date",
		"audit_completed_date",
		"return_grn_list",
		"pack_return_list",
		"incomplete_transfer_dc_list",
		"incomplete_transfer_grn_list",
	),
	"SD YRP Finishing Plan Dispatch": ("fp_total_dispatched",),
	"YRP Item Production Detail": ("approval_status", "approved_by"),
	"YRP Process Cost": ("is_expired", "approved_by"),
	"YRP Item Price": ("approved_by",),
	"YRP Debit": ("status", "approved_by"),
	"YRP Purchase Invoice": (
		"status",
		"approved_by",
		"senior_merch_approved_by",
		"purchase_invoice_wo_approval_details",
	),
	"YRP Production Order": ("submitted_by", "price_approval_status"),
	"YRP Bill Tracking": ("form_status", "received_date"),
	"SD YRP Essdee Quality Inspection": ("calculated_result",),
	"YRP Inspection Entry": ("status",),
	"Purchase Order": ("open_status", "yrp_fulfillment_status", "approved_by"),
}

COPIED_INPUT_FIELDS = {
	"YRP Goods Received Note": ("against", "against_id", "is_return"),
	"YRP Bill Tracking": ("received_via",),
}


class TestDuplicateNoCopy(TestCase):
	def test_state_fields_are_no_copy(self):
		for doctype, fieldnames in NO_COPY_FIELDS.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, fieldname=fieldname):
					field = meta.get_field(fieldname)
					self.assertIsNotNone(field)
					self.assertTrue(field.no_copy)

	def test_user_inputs_are_still_copied(self):
		for doctype, fieldnames in COPIED_INPUT_FIELDS.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, fieldname=fieldname):
					self.assertFalse(meta.get_field(fieldname).no_copy)

	def test_copy_doc_blanks_work_order_state(self):
		source = frappe.get_doc(
			{
				"doctype": "YRP Work Order",
				"supplier": "Copied Supplier",
				"status": "Closed",
				"open_status": "Close",
				"closed_by": "Administrator",
				"is_delivered": 1,
				"deliverables": [{"item_variant": "Stale Variant", "qty": 5}],
			}
		)
		copy = frappe.copy_doc(source, ignore_no_copy=False)
		self.assertEqual(copy.supplier, "Copied Supplier")
		self.assertIsNone(copy.status)
		self.assertIsNone(copy.open_status)
		self.assertIsNone(copy.closed_by)
		self.assertFalse(copy.is_delivered)
		self.assertEqual(copy.get("deliverables"), [])
