export const LIST_NAVIGATION_VERSION = 2

function normalizedDirection(sortOrder) {
	return String(sortOrder || "desc").toLowerCase() === "asc" ? "asc" : "desc"
}

export function deterministicOrder(sortField = "modified", sortOrder = "desc") {
	const field = String(sortField || "modified").trim() || "modified"
	const direction = normalizedDirection(sortOrder)
	return field === "name" ? `name ${direction}` : `${field} ${direction}, name ${direction}`
}

export function navigationStorageKey(sourceRouteName, doctype, snapshotId = "") {
	return ["essdee-yrp", "list-navigation", LIST_NAVIGATION_VERSION, sourceRouteName, doctype, snapshotId]
		.map((part) => encodeURIComponent(String(part || "")))
		.join(":")
}

function newSnapshotId() {
	if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
	return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function cloneJson(value, fallback) {
	try {
		return JSON.parse(JSON.stringify(value))
	} catch {
		return fallback
	}
}

export function createListNavigationState(input = {}) {
	return {
		version: LIST_NAVIGATION_VERSION,
		snapshotId: String(input.snapshotId || newSnapshotId()),
		sourceRouteName: String(input.sourceRouteName || ""),
		sourceFullPath: String(input.sourceFullPath || ""),
		doctype: String(input.doctype || ""),
		filters: Array.isArray(input.filters) ? cloneJson(input.filters, []) : [],
		baseFilters: Array.isArray(input.baseFilters) ? cloneJson(input.baseFilters, []) : [],
		advancedFilters: Array.isArray(input.advancedFilters) ? cloneJson(input.advancedFilters, []) : [],
		quickFilters: input.quickFilters && typeof input.quickFilters === "object"
			? cloneJson(input.quickFilters, {})
			: {},
		status: input.status ?? "",
		search: String(input.search || ""),
		sortField: String(input.sortField || "modified"),
		sortOrder: normalizedDirection(input.sortOrder),
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
			state.snapshotId &&
			state.sourceRouteName &&
			state.doctype &&
			Array.isArray(state.filters) &&
			Number.isInteger(state.globalIndex) &&
			state.globalIndex >= 0,
	)
}

export function writeNavigationState(storage, state) {
	const normalized = createListNavigationState(state)
	const key = navigationStorageKey(normalized.sourceRouteName, normalized.doctype, normalized.snapshotId)
	const latestKey = navigationStorageKey(normalized.sourceRouteName, normalized.doctype)
	try {
		const serialized = JSON.stringify(normalized)
		storage?.setItem(key, serialized)
		storage?.setItem(latestKey, serialized)
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

export function createNavigationReference(state, index, currentName, currentModified = "") {
	return {
		version: LIST_NAVIGATION_VERSION,
		snapshotId: String(state?.snapshotId || ""),
		stateKey: navigationStorageKey(state?.sourceRouteName, state?.doctype, state?.snapshotId),
		index: Math.max(0, Number(index) || 0),
		currentName: String(currentName || ""),
		currentModified: String(currentModified || ""),
		targetRouteName: String(state?.targetRouteName || ""),
		doctype: String(state?.doctype || ""),
	}
}

export function navigationContextMatches(reference, state, routeName, currentName) {
	return Boolean(
		reference?.stateKey
			&& reference.version === LIST_NAVIGATION_VERSION
			&& reference.snapshotId
			&& reference.snapshotId === state?.snapshotId
			&& reference.currentName === currentName
			&& reference.currentModified
			&& reference.doctype
			&& reference.doctype === state?.doctype
			&& reference.targetRouteName
			&& reference.targetRouteName === state?.targetRouteName
			&& String(routeName || "") === reference.targetRouteName
			&& state?.targetParamName
			&& state.globalIndex === reference.index,
	)
}

export function adjacentWindowStart(index) {
	return Math.max(0, (Number(index) || 0) - 1)
}

export function resolveAdjacentNames({ reference, rows = [] } = {}) {
	const index = Math.max(0, Number(reference?.index) || 0)
	const expectedOffset = index - adjacentWindowStart(index)
	const current = rows[expectedOffset]
	if (!current || current.name !== reference?.currentName || String(current.modified || "") !== String(reference?.currentModified || "")) {
		return {
			previousName: null,
			previousModified: "",
			nextName: null,
			nextModified: "",
			changed: true,
			reason: "List changed — return to list",
		}
	}

	return {
		previousName: rows[expectedOffset - 1]?.name || null,
		previousModified: String(rows[expectedOffset - 1]?.modified || ""),
		nextName: rows[expectedOffset + 1]?.name || null,
		nextModified: String(rows[expectedOffset + 1]?.modified || ""),
		changed: false,
		reason: "",
	}
}
