import { packingDerived, stableStringify } from "../ipdEditor.js"

export const PACKING_MODES = [
	{ value: "colour", label: "Colour mix" },
	{ value: "ratio", label: "Size ratio" },
	{ value: "wise", label: "Size wise" },
	{ value: "assortment", label: "Assortment" },
]

export function packingModeOf(draft = {}) {
	if (!Number(draft.based_on_other_attribute_mapping)) return "colour"
	if (draft.packing_mode === "Size Ratio Packing") return "ratio"
	if (draft.packing_mode === "Size Wise Packing") return "wise"
	return "assortment"
}

export function packingModePatch(mode) {
	if (mode === "colour") return { based_on_other_attribute_mapping: 0 }
	if (mode === "ratio") return { based_on_other_attribute_mapping: 1, packing_mode: "Size Ratio Packing" }
	if (mode === "wise") return { based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing", packing_size_details: [] }
	return { based_on_other_attribute_mapping: 1, packing_mode: "" }
}

export function packingChanges(draft, patch) {
	const next = { ...draft, ...patch }
	const combined = { ...patch, ...packingDerived(next) }
	return Object.fromEntries(Object.entries(combined).filter(([key, value]) => stableStringify(value ?? null) !== stableStringify(draft[key] ?? null)))
}

export function isComboDerived(draft = {}) {
	return packingModeOf(draft) === "colour" ? !Number(draft.auto_calculate) : ["ratio", "wise"].includes(packingModeOf(draft))
}
