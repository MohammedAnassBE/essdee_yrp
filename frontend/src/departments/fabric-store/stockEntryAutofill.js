import { autofillSingleOptions, forgetAutofill } from "../../composables/useSingleOptionAutofill.js"

export const STOCK_ENTRY_WAREHOUSE_BY_LOCATION = { from_supplier: "from_warehouse", to_supplier: "to_warehouse" }

/** Fills the Stock Entry Warehouse paired with `locationField` when its location has one enabled Warehouse and the Warehouse field is shown and editable. */
export function autofillStockEntryWarehouse(form, locationField, headerFields, options = {}) {
	const warehouseField = STOCK_ENTRY_WAREHOUSE_BY_LOCATION[locationField]
	const field = warehouseField && headerFields.find((candidate) => candidate.fieldname === warehouseField)
	if (!field || field.read_only) return Promise.resolve({})
	return autofillSingleOptions(form, { ...options, trigger: locationField, targets: { warehouse: warehouseField } })
}

/** Queues Stock Entry location autofills after the Warehouse mismatch check so Save can await the latest. */
export function createStockEntryAutofill(form, warehouseCheck, getHeaderFields, { fetchOptions, onChange, onError }) {
	let pending = Promise.resolve()
	return {
		locationChanged(operation, locationField) {
			if (operation !== "stock_entry" || !STOCK_ENTRY_WAREHOUSE_BY_LOCATION[locationField]) return
			pending = pending
				.then(() => warehouseCheck.settled())
				.then(() => autofillStockEntryWarehouse(form, locationField, getHeaderFields(), { fetchOptions, onChange }))
				.catch(onError)
		},
		settled: () => pending,
		forget: () => forgetAutofill(form, Object.values(STOCK_ENTRY_WAREHOUSE_BY_LOCATION)),
	}
}
