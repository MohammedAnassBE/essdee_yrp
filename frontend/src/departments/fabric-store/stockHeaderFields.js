import { autofillSingleOptions, forgetAutofill } from "../../composables/useSingleOptionAutofill.js"

const warehouseBySupplier = { from_supplier: "from_warehouse", to_supplier: "to_warehouse", default_supplier: "default_warehouse", supplier: "warehouse" }
const supplierByWarehouse = Object.fromEntries(Object.entries(warehouseBySupplier).map(([supplier, warehouse]) => [warehouse, supplier]))
const autofillTargetsByOperation = {
	stock_reconciliation: { default_supplier: { warehouse: "default_warehouse" } },
	stock_update: { supplier: { warehouse: "warehouse" } },
}

/** Header fields for a Fabric Store stock operation; each Supplier precedes the Warehouse it filters, as in Desk set_query. */
export function buildStockHeaderFields(operation, form, editor) {
	const fields = []
	const protectedFields = Boolean(editor.protected_completion)
	const receipt = form.purpose === "Receive at Warehouse"
	const link = (fieldname, label, options, required = false, readOnly = false) => fields.push({ fieldname, label, options, fieldtype: "Link", reqd: required, read_only: readOnly })
	if (["stock_entry", "stock_reconciliation"].includes(operation)) fields.push({ fieldname: "purpose", label: "Purpose", fieldtype: "Select", options: (editor.purpose_options || []).join("\n"), reqd: true, read_only: editor.purpose_locked })
	if (operation === "stock_entry") {
		link("from_supplier", "From Location", "Supplier", false, protectedFields || receipt)
		link("to_supplier", "To Location", "Supplier", false, protectedFields || receipt)
		if (receipt) link("outgoing_stock_entry", "Outgoing Stock Entry", "YRP Stock Entry", true, true)
		link("from_warehouse", "From Warehouse", "Warehouse", form.purpose !== "Material Receipt", protectedFields || receipt || form.purpose === "Material Receipt")
		if (["Send to Warehouse", "Material Receipt", "Receive at Warehouse"].includes(form.purpose) || protectedFields) link("to_warehouse", "To Warehouse", "Warehouse", true, protectedFields || receipt)
		if (form.purpose === "Send to Warehouse") fields.push({ fieldname: "skip_transit", label: "Skip Transit", fieldtype: "Check" })
	}
	if (operation === "stock_reconciliation") {
		link("default_supplier", "Supplier", "Supplier")
		link("default_warehouse", "Warehouse", "Warehouse", true)
	}
	if (operation === "stock_update") {
		fields.push({ fieldname: "update_type", label: "Update Type", fieldtype: "Select", options: (editor.update_type_options || []).join("\n"), reqd: true })
		link("supplier", "Supplier", "Supplier")
		link("warehouse", "Warehouse", "Warehouse", true)
	}
	if (editor.posting_fields?.length) fields.push({ fieldname: "edit_posting_date_and_time", label: "Edit Posting Date and Time", fieldtype: "Check", read_only: protectedFields })
	for (const field of editor.posting_fields || []) fields.push({ ...field, fieldtype: field.fieldname === "posting_date" ? "Date" : "Time", reqd: field.reqd || Boolean(form.edit_posting_date_and_time), read_only: protectedFields || !form.edit_posting_date_and_time })
	for (const field of fields) {
		if (field.options === "Supplier") field.link_filters = { disabled: 0 }
		if (field.options === "Warehouse") {
			const supplier = form[supplierByWarehouse[field.fieldname]]
			field.link_filters = { disabled: 0, ...(supplier ? { supplier } : {}) }
		}
	}
	return fields
}

/** Clears the paired Warehouse when it does not belong to the newly selected Supplier. */
export async function clearMismatchedWarehouse(form, supplierField, warehouseBelongsTo) {
	const warehouseField = warehouseBySupplier[supplierField]
	const supplier = form[supplierField]
	const warehouse = form[warehouseField]
	if (!warehouseField || !supplier || !warehouse) return
	const belongs = await warehouseBelongsTo(warehouse, supplier)
	if (!belongs && form[supplierField] === supplier && form[warehouseField] === warehouse) form[warehouseField] = ""
}

/** Runs supplier checks in order so Save can await the latest; a failed check clears the warehouse. */
export function createWarehouseCheck(form, warehouseBelongsTo, onError) {
	let pending = Promise.resolve()
	return {
		supplierChanged(supplierField) {
			if (!warehouseBySupplier[supplierField]) return
			pending = pending
				.then(() => clearMismatchedWarehouse(form, supplierField, warehouseBelongsTo))
				.catch((reason) => {
					form[warehouseBySupplier[supplierField]] = ""
					onError(reason)
				})
		},
		settled: () => pending,
	}
}

/** Fills the paired Warehouse when the Supplier has exactly one, after the mismatch check has settled. */
export function createSupplierAutofill(form, warehouseCheck, { fetchOptions, onChange, onError }) {
	let pending = Promise.resolve()
	return {
		supplierChanged(operation, supplierField) {
			const targets = autofillTargetsByOperation[operation]?.[supplierField]
			if (!targets) return
			pending = pending
				.then(() => warehouseCheck.settled())
				.then(() => autofillSingleOptions(form, { trigger: supplierField, targets, fetchOptions, onChange }))
				.catch(onError)
		},
		settled: () => pending,
		forget: () => forgetAutofill(form),
	}
}
