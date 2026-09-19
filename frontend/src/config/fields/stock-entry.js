/**
 * Stock Entry — keep each location/warehouse pair aligned with Desk.
 *
 * YRP stores the selected location in from_supplier / to_supplier and the
 * physical warehouse separately. Once a location is selected, the Warehouse
 * autocomplete must only show enabled warehouses belonging to that Supplier.
 */
import { searchLink } from "@/api/client"

const linkSearchHandlers = {
	from_warehouse: (form) =>
		form.from_supplier
			? (q) => searchLink("Warehouse", q, { supplier: form.from_supplier, disabled: 0 })
			: null,
	to_warehouse: (form) =>
		form.to_supplier
			? (q) => searchLink("Warehouse", q, { supplier: form.to_supplier, disabled: 0 })
			: null,
}

const labels = {
	from_supplier: "From Location",
	to_supplier: "To Location",
}

export default {
	linkSearchHandlers,
	labels,
}
