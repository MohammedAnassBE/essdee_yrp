/** Ironing Excess / Old Lot entries and the Create DC prefill made from each. */

import { initialEntry } from "../finishingEntries.js"

export const EXISTING_DC = "existing"

export function canCreateDc(entry, canCreate) {
	return Boolean(canCreate) && !entry?.dc
}

export function isExistingDc(entry) {
	return entry?.dc === EXISTING_DC
}

/** Create DC entry state with only the source entry's colours checked and filled. */
export function prefilledEntry(payload, quantities) {
	const entry = initialEntry(payload)
	for (const [colour, row] of Object.entries(entry)) {
		const sizes = quantities?.[colour]
		row.checked = Boolean(sizes)
		if (!sizes) continue
		for (const size of Object.keys(row.sizes)) row.sizes[size] = Number(sizes[size]) || 0
	}
	return entry
}
