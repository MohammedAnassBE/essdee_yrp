import { callMethod } from "./frappe.js"

const CAPABILITIES_METHOD = "essdee_yrp.accounts.web_capabilities"
const WORKSPACE_METHOD = "essdee_yrp.accounts.purchase_invoice_workspace"
const EDITOR_METHOD = "essdee_yrp.accounts.purchase_invoice_editor"
const PURCHASE_INVOICE_METHOD = "yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice"
const ERP_INVOICE_METHOD = "essdee_yrp.erp_purchase_invoice"
const AUDIT_PENDING_METHOD = "essdee_yrp.accounts.audit_pending"

export function getAuditPendingDashboard(showPartiallyDispatched = false) {
	return callMethod(`${AUDIT_PENDING_METHOD}.get_dashboard_data`, {
		show_partially_dispatched: showPartiallyDispatched ? 1 : 0,
	})
}

export function getAuditPendingBreakdown(finishingPlan) {
	return callMethod(`${AUDIT_PENDING_METHOD}.get_pending_breakdown`, { finishing_plan: finishingPlan })
}

export function getAuditPendingDispatchDetail(finishingPlan, history) {
	return callMethod(`${AUDIT_PENDING_METHOD}.get_dispatch_detail`, {
		finishing_plan: finishingPlan,
		source_doctype: history.source_doctype,
		source_name: history.source_name,
		stock_entry: history.stock_entry,
	})
}

export function getAccountsCapabilities() {
	return callMethod(`${CAPABILITIES_METHOD}.get_capabilities`)
}

export function getPurchaseInvoiceWorkspace(name) {
	return callMethod(`${WORKSPACE_METHOD}.get_purchase_invoice_workspace`, { name })
}

export function getPurchaseInvoiceEditor(name = null, billTracking = null) {
	return callMethod(`${EDITOR_METHOD}.get_purchase_invoice_editor`, { name, bill_tracking: billTracking })
}

export function savePurchaseInvoice({ values, grns, items }, options = {}) {
	return callMethod(`${EDITOR_METHOD}.save_purchase_invoice`, {
		values,
		grns,
		items,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified ?? null,
	})
}

export function executePurchaseInvoiceCommand(name, command, payload = {}, expectedModified = null) {
	return callMethod(`${EDITOR_METHOD}.execute_purchase_invoice_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified ?? null,
	})
}

export function getEligibleGrns({ supplier, against, searchText, purchaseInvoice, billTracking, limit }) {
	return callMethod(`${PURCHASE_INVOICE_METHOD}.get_eligible_grns`, {
		supplier,
		against,
		search_text: searchText || undefined,
		purchase_invoice: purchaseInvoice || undefined,
		bill_tracking: billTracking || undefined,
		limit: limit || undefined,
	})
}

export function fetchGrnDetails({ grns, against, supplier, purchaseInvoice, billTracking }) {
	return callMethod(`${PURCHASE_INVOICE_METHOD}.fetch_grn_details`, {
		grns,
		against,
		supplier,
		purchase_invoice: purchaseInvoice || undefined,
		bill_tracking: billTracking || undefined,
	})
}

export function approveInvoice(name, comments) {
	return callMethod(`${PURCHASE_INVOICE_METHOD}.approve_invoice`, { name, comments })
}

export function checkAllWorkOrdersClosed(purchaseInvoice) {
	return callMethod(`${PURCHASE_INVOICE_METHOD}.check_all_wo_closed`, { purchase_invoice: purchaseInvoice })
}

export function fetchExpenseHeads(items) {
	return callMethod(`${ERP_INVOICE_METHOD}.fetch_items_expense_head`, { items })
}

export function submitErpBill(name) {
	return callMethod(`${ERP_INVOICE_METHOD}.submit_erp_invoice`, { name })
}

export function getErpBillLink(name) {
	return callMethod(`${ERP_INVOICE_METHOD}.get_erp_inv_link`, { name })
}
