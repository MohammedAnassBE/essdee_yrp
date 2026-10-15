import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.hr.web_workspace"
const BILL_TRACKING_METHOD = "yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking"
const BILL_TRACKING_OVERRIDE_METHOD = "essdee_yrp.overrides.bill_tracking"
const DEPARTMENT_METHOD = "yrp.yrp.doctype.yrp_department.yrp_department"
const DELIVERY_PERSON_METHOD = (
	"yrp.yrp.doctype.yrp_vendor_bill_delivery_person.yrp_vendor_bill_delivery_person"
)

export function getHrCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getBillTrackingWorkspace(name) {
	return callMethod(`${WORKSPACE_METHOD}.get_bill_tracking_workspace`, { name })
}

export function getBillTrackingEditor(name = null) {
	return callMethod(`${WORKSPACE_METHOD}.get_bill_tracking_editor`, { name })
}

export function saveBillTracking(values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_bill_tracking`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified ?? null,
	})
}

export function executeBillTrackingCommand(name, command, expectedModified = null) {
	return callMethod(`${WORKSPACE_METHOD}.execute_bill_tracking_command`, {
		name,
		command,
		expected_modified: expectedModified ?? null,
	})
}

export function assignBill(name, assignedTo, remarks) {
	return callMethod(`${BILL_TRACKING_METHOD}.assign_vendor_bill`, {
		name,
		assigned_to: assignedTo,
		remarks,
	})
}

export function bulkAssignBills(assignTo, names, remarks) {
	return callMethod(`${BILL_TRACKING_METHOD}.bulk_assign_bills`, {
		assign_to: assignTo,
		selected_docs: names.map((name) => ({ name })),
		remarks,
	})
}

export function acknowledgeBillReceived(name) {
	return callMethod(`${BILL_TRACKING_METHOD}.make_bill_received_acknowledgement`, { doc_name: name })
}

export function requestBillCancellation(name) {
	return callMethod(`${BILL_TRACKING_OVERRIDE_METHOD}.request_bill_cancellation`, { name })
}

export function approveBillCancellation(name) {
	return callMethod(`${BILL_TRACKING_OVERRIDE_METHOD}.approve_bill_cancellation`, { name })
}

export function cancelBill(name, cancelReason) {
	return callMethod(`${BILL_TRACKING_METHOD}.cancel_vendor_bill`, { name, cancel_reason: cancelReason })
}

export function getUserDepartments() {
	return callMethod(`${DEPARTMENT_METHOD}.get_user_departments`)
}

export function getDeliveryPersonSuggestions(supplier, search) {
	return callMethod(`${DELIVERY_PERSON_METHOD}.get_last_ten_delivery_persons`, { supplier, search })
}
