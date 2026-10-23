import { autofillSingleOptions } from "../../composables/useSingleOptionAutofill.js"

export const WORK_ORDER_PARTY_ADDRESSES = Object.freeze({ supplier: "supplier_address", delivery_location: "delivery_address" })

/** Set a Work Order party, drop the previous party's address and fill the new party's only address. */
export async function changeWorkOrderParty(form, partyField, value, options = {}) {
	const addressField = WORK_ORDER_PARTY_ADDRESSES[partyField]
	if (!addressField) throw new Error(`Unknown Work Order party field ${partyField}.`)
	form[partyField] = value || ""
	form[addressField] = ""
	return autofillSingleOptions(form, { trigger: partyField, targets: { address: addressField }, ...options })
}
