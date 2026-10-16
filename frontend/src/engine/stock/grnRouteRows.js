import { groupItemsForDisplay } from "./groupItemsForDisplay.js"

function canonical(value) {
	if (Array.isArray(value)) return value.map(canonical)
	if (value && typeof value === "object") {
		return Object.fromEntries(
			Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
		)
	}
	return value
}

function stableKey(value) {
	return JSON.stringify(canonical(value))
}

function stripReceivedType(dimensions) {
	return Object.fromEntries(
		Object.entries(dimensions || {}).filter(([fieldname]) => fieldname !== "received_type"),
	)
}

function receivedType(entry) {
	return entry?.dimensions?.received_type || ""
}

function normalizedSetCombination(value) {
	if (!value) return {}
	if (typeof value === "string") {
		try {
			return JSON.parse(value)
		} catch (_) {
			return { value }
		}
	}
	return value
}

function columnsFor(group, entry) {
	const values = entry?.values || {}
	const primaryValues = group?.primary_attribute_values || []
	if (primaryValues.length && !Object.prototype.hasOwnProperty.call(values, "default")) {
		return primaryValues.map((value) => ({ key: value, label: value }))
	}
	return [{ key: "default", label: "Qty" }]
}

/** Build one visible row per physical Item/Dia/Received-Type combination.
 *
 * Historical documents can still contain several colour-route entries for the
 * same physical receipt. They are summed for display, but new edits are written
 * into one source entry and compacted to one physical entry before save.
 */
export function buildGrnLogicalRows(groups) {
	const rows = []
	const byKey = new Map()

	for (const group of groups || []) {
		for (const entry of group.items || []) {
			const dimensions = stripReceivedType(entry.dimensions || {})
			const attributes = entry.attributes || {}
			const columns = columnsFor(group, entry)
			const setCombination = normalizedSetCombination(entry.set_combination)
			const key = stableKey({
				name: entry.name,
				dimensions,
				attributes,
				setCombination,
				columns: columns.map((column) => column.key),
			})
			if (!byKey.has(key)) {
				const row = {
					key,
					name: entry.name,
					dimensions,
					dimensionFields: Object.keys(dimensions).filter((fieldname) => dimensions[fieldname]),
					attributes,
					setCombination,
					attributeFields: Object.keys(attributes).filter((fieldname) => attributes[fieldname]),
					columns,
					defaultUom: entry.default_uom || "",
					splits: [],
					_splitBuckets: new Map(),
				}
				byKey.set(key, row)
				rows.push(row)
			}

			const row = byKey.get(key)
			const type = receivedType(entry)
			if (!row._splitBuckets.has(type)) row._splitBuckets.set(type, [])
			row._splitBuckets.get(type).push(entry)
		}
	}

	for (const row of rows) {
		for (const [type, sourceEntries] of row._splitBuckets) {
			const aggregate = groupItemsForDisplay([{
				attributes: [],
				primary_attribute: "",
				primary_attribute_values: [],
				items: sourceEntries,
			}])[0]?.items?.[0]
			if (!aggregate) continue
			row.splits.push({
				key: `${row.key}::${type}`,
				receivedType: type,
				entry: aggregate,
				sourceEntries,
			})
		}
		delete row._splitBuckets
		row.splits.sort((left, right) =>
			(left.receivedType || "").localeCompare(right.receivedType || ""),
		)
	}

	return rows
}

function roundQty(value) {
	return Math.round((Number(value) || 0) * 1000) / 1000
}

export function normalizeGrnReceiptQuantity(value, allowed, otherReceived, allowExcess) {
	const quantity = Math.max(Number(value) || 0, 0)
	if (allowExcess) return quantity
	return Math.min(
		quantity,
		Math.max((Number(allowed) || 0) - (Number(otherReceived) || 0), 0),
	)
}

function enabledCheckValue(value) {
	if (value === true || value === 1 || value === "1") return true
	if (typeof value !== "string") return false
	return ["true", "yes", "on"].includes(value.trim().toLowerCase())
}

export function allowsWorkOrderGrnExcess(doc) {
	if (doc?.against !== "Work Order") return false
	return ![
		"is_return",
		"is_rework",
		"additional_grn",
		"includes_packing",
	].some((fieldname) => enabledCheckValue(doc?.[fieldname]))
}

export function setGrnSplitQuantity(split, primaryValue, value) {
	const cells = (split?.sourceEntries || [])
		.map((entry) => ({ entry, detail: entry?.values?.[primaryValue] }))
		.filter((row) => row.detail)
	if (!cells.length) return

	// A draft owns one physical row. If old route-expanded entries are loaded,
	// move the edited total into the first entry and clear the legacy shadows.
	cells[0].detail.qty = Math.max(roundQty(value), 0)
	for (const { detail } of cells.slice(1)) detail.qty = 0
}

export function setGrnSplitComment(split, value) {
	for (const entry of split?.sourceEntries || []) entry.comments = value
}

export function setGrnRowDia(row, dia) {
	for (const split of row?.splits || []) {
		for (const entry of split.sourceEntries || []) {
			entry.attributes = { ...(entry.attributes || {}), Dia: dia }
		}
	}
}

function groupContaining(groups, source) {
	return (groups || []).find((group) => (group.items || []).includes(source))
}

function cloneEntry(source, mutate) {
	const cloned = JSON.parse(JSON.stringify(source))
	delete cloned.row_index
	delete cloned.table_index
	cloned.comments = ""
	for (const detail of Object.values(cloned.values || {})) detail.qty = 0
	mutate(cloned)
	return cloned
}

export function addGrnActualDia(groups, row, dia) {
	const source = row?.splits?.[0]?.sourceEntries?.[0]
	const group = groupContaining(groups, source)
	if (!group || !source) return
	group.items.push(cloneEntry(source, (entry) => {
		entry.attributes = { ...(entry.attributes || {}), Dia: dia }
	}))
}

export function removeGrnRow(groups, row) {
	const entries = new Set(
		(row?.splits || []).flatMap((split) => split.sourceEntries || []),
	)
	for (const group of groups || []) {
		group.items = (group.items || []).filter((entry) => !entries.has(entry))
	}
}

export function addGrnReceivedType(groups, row, type) {
	const source = row?.splits?.[0]?.sourceEntries?.[0]
	const group = groupContaining(groups, source)
	if (!group || !source) return
	group.items.push(cloneEntry(source, (entry) => {
		entry.dimensions = { ...stripReceivedType(entry.dimensions || {}), received_type: type }
	}))
}

export function removeGrnSplit(groups, split) {
	const entries = new Set(split?.sourceEntries || [])
	for (const group of groups || []) {
		group.items = (group.items || []).filter((entry) => !entries.has(entry))
	}
}

export function grnSplitReferenceKey(split, primaryValue = "default") {
	return [...new Set(
		(split?.sourceEntries || [])
			.map((entry) => entry?.values?.[primaryValue]?.ref_docname || entry?.ref_docname || "")
			.filter(Boolean),
	)].sort().join("|")
}

export function compactGrnRouteSplits(data, defaultType) {
	const compacted = JSON.parse(JSON.stringify(data || []))
	for (const group of compacted) {
		const buckets = new Map()
		for (const entry of group.items || []) {
			const identity = stableKey({
				name: entry.name,
				dimensions: stripReceivedType(entry.dimensions || {}),
				attributes: entry.attributes || {},
				setCombination: normalizedSetCombination(entry.set_combination),
				columns: columnsFor(group, entry).map((column) => column.key),
			})
			const key = stableKey({ identity, receivedType: receivedType(entry) })
			if (!buckets.has(key)) buckets.set(key, { identity, entries: [] })
			buckets.get(key).entries.push(entry)
		}

		const physical = []
		for (const { identity, entries } of buckets.values()) {
			const entry = JSON.parse(JSON.stringify(entries[0]))
			for (const key of Object.keys(entry.values || {})) {
				const details = entries.map((candidate) => candidate.values?.[key]).filter(Boolean)
				if (!details.length) continue
				entry.values[key] = { ...details[0] }
				entry.values[key].qty = roundQty(
					details.reduce((sum, detail) => sum + (Number(detail.qty) || 0), 0),
				)
				for (const fieldname of ["pending_quantity", "max_receivable_quantity"]) {
					const values = details.map((detail) => detail[fieldname])
					if (!values.some((value) => value !== undefined && value !== null && value !== "")) continue
					entry.values[key][fieldname] = roundQty(
						values.reduce((sum, value) => sum + (Number(value) || 0), 0),
					)
				}
			}
			entry.comments = entries.find((candidate) => candidate.comments)?.comments || ""
			physical.push({ identity, entry })
		}

		const keep = []
		const identities = new Map()
		for (const row of physical) {
			if (!identities.has(row.identity)) identities.set(row.identity, [])
			identities.get(row.identity).push(row.entry)
		}
		for (const entries of identities.values()) {
			const positive = entries.filter((entry) => Object.values(entry.values || {}).some(
				(detail) => Number(detail?.qty) > 0,
			))
			if (positive.length) {
				keep.push(...positive)
				continue
			}
			const preferred = entries.find((entry) => receivedType(entry) === defaultType) || entries[0]
			if (preferred) keep.push(preferred)
		}
		group.items = keep
	}
	return compacted
}
