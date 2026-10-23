import { autofillSingleOptions } from "../../composables/useSingleOptionAutofill.js"

/** GRN party field → the fields filled from that party's only warehouse/address. */
export const GRN_LOCATION_AUTOFILL = {
	supplier: { trigger: "supplier", targets: { warehouse: "from_warehouse", address: "billing_address" } },
	delivery_location: { trigger: "delivery_location", targets: { warehouse: "to_warehouse" } },
}

/** Fill the only warehouse/address of the GRN party in `fieldname`; no-op for other fields. */
export async function autofillGoodsReceivedNoteLocation(form, fieldname, options = {}) {
	const config = GRN_LOCATION_AUTOFILL[fieldname]
	if (!config) return {}
	return autofillSingleOptions(form, { ...config, ...options })
}
