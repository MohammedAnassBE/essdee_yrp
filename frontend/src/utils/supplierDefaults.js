import { callMethod, searchLink, searchLinkedDocument } from "../api/frappe.js"

export function defaultOption(current, options, preferred = "") {
	if (current) return current
	if (preferred) return preferred
	return options?.length === 1 ? (options[0].name ?? options[0]) : ""
}

export async function fillSupplierDefaults(form, { partyField, addressField, warehouseField, preferPrimary = false }) {
	const party = form[partyField]
	if (!party) return
	const fill = async (field, readOptions, readPreferred = async () => "") => {
		if (!field || form[field]) return
		const [options, preferred] = await Promise.all([readOptions(), readPreferred()])
		if (form[partyField] !== party) return
		form[field] = defaultOption(form[field], options, preferred)
	}
	await Promise.all([
		fill(addressField, () => searchLinkedDocument("Address", "Supplier", party, "", 2),
			() => preferPrimary ? callMethod("yrp.yrp.doctype.yrp_supplier.yrp_supplier.get_primary_address", { supplier: party }) : ""),
		fill(warehouseField, () => searchLink("Warehouse", "", { disabled: 0, supplier: party }, 2)),
	])
}
