import { autofillSingleOptions } from "../../composables/useSingleOptionAutofill.js"

/** Sets the Purchase Order delivery location and fills `set_warehouse` with the location's only enabled Warehouse. */
export function changePurchaseOrderDeliveryLocation(form, value, { fetchOptions, onChange } = {}) {
	const location = value || ""
	if (location === (form.default_delivery_location || "")) return Promise.resolve({})
	form.default_delivery_location = location
	form.set_warehouse = ""
	return autofillSingleOptions(form, {
		trigger: "default_delivery_location",
		targets: { warehouse: "set_warehouse" },
		...(fetchOptions ? { fetchOptions } : {}),
		onChange,
	})
}
