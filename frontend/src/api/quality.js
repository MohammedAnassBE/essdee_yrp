import { callMethod } from "./frappe.js"

const WORKSPACE = "essdee_yrp.quality.web_workspace"
const INSPECTION = "essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection"

export function getQualityCapabilities() {
	return callMethod(`${WORKSPACE}.get_capabilities`)
}

export function getInspectionWorkspace(name) {
	return callMethod(`${WORKSPACE}.get_inspection_workspace`, { name })
}

export function getNewInspectionDefaults({ against_id, grn, amend_from, duplicate_from } = {}) {
	return callMethod(`${WORKSPACE}.get_new_inspection_defaults`, { against_id, grn, amend_from, duplicate_from })
}

export function saveInspection(values, { name, expectedModified } = {}) {
	return callMethod(`${WORKSPACE}.save_inspection`, {
		values,
		name: name || undefined,
		expected_modified: expectedModified ?? null,
	})
}

export function updateInspectionResult(name, result, expectedModified) {
	return callMethod(`${WORKSPACE}.update_inspection_result`, {
		name,
		result,
		expected_modified: expectedModified ?? null,
	})
}

export function getInspectionAgainstDetails(against_id) {
	return callMethod(`${INSPECTION}.get_against_details`, { against: "YRP Work Order", against_id })
}

export function getInspectionAqlLimits({ checking_level, offer_qty, major_aql_level, minor_aql_level }) {
	return callMethod(`${INSPECTION}.get_max_minor_defect_allowed`, {
		level: checking_level,
		offer_qty,
		major_aql_level,
		minor_aql_level,
	})
}

export function createInspectionDebit(quality_inspection, { debit_value, reason, debit_document }) {
	return callMethod(`${INSPECTION}.create_inspection_debit`, {
		quality_inspection,
		debit_value,
		reason,
		debit_document,
	})
}
