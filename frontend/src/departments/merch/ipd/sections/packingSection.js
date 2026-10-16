import { packingDerived, stableStringify } from "../ipdEditor.js"

export function packingChanges(draft, patch) {
	const changes = { ...patch }
	if (Object.hasOwn(changes, "packing_mode")) {
		// FormField's Select clear control emits null for the Desk blank option.
		changes.packing_mode ??= ""
		if (changes.packing_mode === "Size Wise Packing" && draft.packing_mode !== changes.packing_mode) changes.packing_size_details = []
	}
	const next = { ...draft, ...changes }
	const combined = { ...changes, ...packingDerived(next) }
	return Object.fromEntries(Object.entries(combined).filter(([key, value]) => stableStringify(value ?? null) !== stableStringify(draft[key] ?? null)))
}

export function isComboDerived(draft = {}) {
	return !Number(draft.based_on_other_attribute_mapping)
		? !Number(draft.auto_calculate)
		: ["Size Ratio Packing", "Size Wise Packing"].includes(draft.packing_mode)
}
