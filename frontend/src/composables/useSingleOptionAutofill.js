import { watch } from "vue"
import { callMethod } from "../api/frappe.js"

export const SINGLE_LOCATION_OPTIONS_METHOD = "essdee_yrp.api.supplier_warehouse.get_single_location_options"

const autofilledByTarget = new WeakMap()
const sequenceByTarget = new WeakMap()

export function getSingleLocationOptions(args) {
	return callMethod(SINGLE_LOCATION_OPTIONS_METHOD, args)
}

function autofilledValues(target) {
	if (!autofilledByTarget.has(target)) autofilledByTarget.set(target, new Map())
	return autofilledByTarget.get(target)
}

function nextSequence(target, trigger) {
	if (!sequenceByTarget.has(target)) sequenceByTarget.set(target, new Map())
	const sequences = sequenceByTarget.get(target)
	const sequence = (sequences.get(trigger) || 0) + 1
	sequences.set(trigger, sequence)
	return () => sequences.get(trigger) === sequence
}

/** Forget what was filled; forgetting everything also drops responses still in flight. */
export function forgetAutofill(target, fields = null) {
	if (!fields) {
		const sequences = sequenceByTarget.get(target)
		for (const [trigger, sequence] of sequences || []) sequences.set(trigger, sequence + 1)
	}
	const values = autofilledByTarget.get(target)
	if (!values) return
	if (!fields) values.clear()
	else for (const field of fields) values.delete(field)
}

export function isAutofilled(target, field) {
	const values = autofilledByTarget.get(target)
	return Boolean(values?.has(field) && values.get(field) === target[field])
}

function isFillable(target, field) {
	return !target[field] || isAutofilled(target, field)
}

/** Fill empty or stale auto-filled `targets` of `target` from the only warehouse/address of `target[trigger]`. */
export async function autofillSingleOptions(target, {
	trigger,
	triggerType = "supplier",
	targets,
	preferPrimaryAddress = false,
	fetchOptions = getSingleLocationOptions,
	onChange,
}) {
	const value = target[trigger]
	const isCurrent = nextSequence(target, trigger)
	const args = preferPrimaryAddress ? { [triggerType]: value, prefer_primary: 1 } : { [triggerType]: value }
	const options = value ? await fetchOptions(args) || {} : {}
	if (!isCurrent() || target[trigger] !== value) return {}
	const fillable = Object.entries(targets).filter(([key, field]) => field
		&& isFillable(target, key === "address_display" && targets.address ? targets.address : field))
	const values = autofilledValues(target)
	const changes = {}
	for (const [key, field] of fillable) {
		const next = options[key] || ""
		if (next) values.set(field, next)
		else values.delete(field)
		if ((target[field] || "") === next) continue
		target[field] = next
		changes[field] = next
	}
	if (onChange && Object.keys(changes).length) onChange(changes, target)
	return changes
}

/** Watch `form[config.trigger]` and run `autofillSingleOptions` on each change. */
export function useSingleOptionAutofill(form, config) {
	const { isEnabled = () => true, onError = (reason) => console.error(reason), immediate = false } = config
	const refresh = async () => {
		if (!isEnabled()) return {}
		try { return await autofillSingleOptions(form, config) }
		catch (reason) {
			onError(reason)
			return {}
		}
	}
	const stop = watch(() => form[config.trigger], (value, previous) => {
		if (value !== previous) refresh()
	}, { immediate })
	return { refresh, stop, forget: (fields) => forgetAutofill(form, fields) }
}
