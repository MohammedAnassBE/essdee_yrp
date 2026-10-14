/** Supplier and Warehouse pairs shared by the finishing dispatch dialogs. */

import { getSupplierWarehouses } from "../../api/finishing.js"

const supplierRequestSequences = new WeakMap()

export function warehouseFilters(supplier) {
	return { disabled: 0, supplier: supplier || "__unselected__" }
}

/** Set a side's Supplier, clear its Warehouse and prefill the only linked one; returns an error when none exist. */
export async function setDispatchSupplier(form, side, supplier) {
	let sequences = supplierRequestSequences.get(form)
	if (!sequences) {
		sequences = {}
		supplierRequestSequences.set(form, sequences)
	}
	const sequence = (sequences[side] || 0) + 1
	sequences[side] = sequence
	form[`${side}_supplier`] = supplier || ""
	form[`${side}_warehouse`] = ""
	if (!supplier) return ""
	let warehouses
	try {
		warehouses = await getSupplierWarehouses(supplier)
	} catch (reason) {
		if (sequences[side] !== sequence) return ""
		return reason?.message || `Unable to load the Warehouses of Supplier ${supplier}.`
	}
	if (sequences[side] !== sequence || form[`${side}_supplier`] !== supplier) return ""
	if (warehouses.length === 1) form[`${side}_warehouse`] = warehouses[0]
	return warehouses.length ? "" : `Supplier ${supplier} has no Warehouse. Create one from the Supplier.`
}
