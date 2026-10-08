export const LIST_NAVIGATION_VERSION = 1

function normalizedDirection(sortOrder) {
	return String(sortOrder || "desc").toLowerCase() === "asc" ? "asc" : "desc"
}

export function deterministicOrder(sortField = "modified", sortOrder = "desc") {
	const field = String(sortField || "modified").trim() || "modified"
	const direction = normalizedDirection(sortOrder)
	return field === "name" ? `name ${direction}` : `${field} ${direction}, name ${direction}`
}

export function navigationStorageKey(sourceRouteName, doctype) {
	return ["essdee-yrp", "list-navigation", LIST_NAVIGATION_VERSION, sourceRouteName, doctype]
		.map((part) => encodeURIComponent(String(part || "")))
		.join(":")
}

export function createListNavigationState(input = {}) {
	return {
		version: LIST_NAVIGATION_VERSION,
		sourceRouteName: String(input.sourceRouteName || ""),
		sourceFullPath: String(input.sourceFullPath || ""),
		doctype: String(input.doctype || ""),
		filters: Array.isArray(input.filters) ? structuredClone(input.filters) : [],
		orderBy: String(input.orderBy || deterministicOrder()),
		pageStart: Math.max(0, Number(input.pageStart) || 0),
		pageSize: Math.max(1, Number(input.pageSize) || 20),
		globalIndex: Math.max(0, Number(input.globalIndex) || 0),
		total: Math.max(0, Number(input.total) || 0),
		targetRouteName: String(input.targetRouteName || ""),
		targetParamName: String(input.targetParamName || ""),
	}
}

function isValidState(state) {
	return Boolean(
		state &&
			state.version === LIST_NAVIGATION_VERSION &&
			state.sourceRouteName &&
			state.doctype &&
			Array.isArray(state.filters) &&
			Number.isInteger(state.globalIndex) &&
			state.globalIndex >= 0,
	)
}

export function writeNavigationState(storage, state) {
	const normalized = createListNavigationState(state)
	const key = navigationStorageKey(normalized.sourceRouteName, normalized.doctype)
	try {
		storage?.setItem(key, JSON.stringify(normalized))
		return key
	} catch {
		return ""
	}
}

export function readNavigationState(storage, key) {
	if (!storage || !key) return null
	try {
		const state = JSON.parse(storage.getItem(key))
		return isValidState(state) ? createListNavigationState(state) : null
	} catch {
		return null
	}
}

export function createNavigationReference(state, index, currentName) {
	return {
		version: LIST_NAVIGATION_VERSION,
		stateKey: navigationStorageKey(state?.sourceRouteName, state?.doctype),
		index: Math.max(0, Number(index) || 0),
		currentName: String(currentName || ""),
		targetRouteName: String(state?.targetRouteName || ""),
		doctype: String(state?.doctype || ""),
	}
}

export function adjacentWindowStart(index) {
	return Math.max(0, (Number(index) || 0) - 1)
}

export function resolveAdjacentNames({ reference, rows = [] } = {}) {
	const index = Math.max(0, Number(reference?.index) || 0)
	const expectedOffset = index - adjacentWindowStart(index)
	const current = rows[expectedOffset]
	if (!current || current.name !== reference?.currentName) {
		return {
			previousName: null,
			nextName: null,
			changed: true,
			reason: "List changed — return to list",
		}
	}

	return {
		previousName: rows[expectedOffset - 1]?.name || null,
		nextName: rows[expectedOffset + 1]?.name || null,
		changed: false,
		reason: "",
	}
}
