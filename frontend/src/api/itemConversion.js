import { callMethod, callRead } from "./frappe.js"

const METHOD = "essdee_yrp.fabric_store.documents.item_conversion"
const VALUATION_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_item_conversion.sd_yrp_item_conversion.get_item_conversion_valuation_rate"

export function getItemConversion(name = "") {
	return callMethod(`${METHOD}.get_item_conversion`, { name: name || undefined })
}

export function getItemConversionItemSchema(item) {
	return callRead(`${METHOD}.get_item_conversion_item_schema`, { item })
}

export function saveItemConversion(values, options = {}) {
	return callMethod(`${METHOD}.save_item_conversion`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function changeItemConversionStatus(name, action, expectedModified = "") {
	return callMethod(`${METHOD}.change_item_conversion_status`, { name, action, expected_modified: expectedModified || undefined })
}

export function getItemConversionValuationRate(args) {
	return callMethod(VALUATION_METHOD, args)
}
