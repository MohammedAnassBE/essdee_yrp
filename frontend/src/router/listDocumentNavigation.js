import {
	createListNavigationState,
	createNavigationReference,
	writeNavigationState,
} from "../utils/listNavigation.js"

export function openListDocument(router, row, snapshot, { routeName, paramName }) {
	if (!row?.name) return Promise.resolve()
	if (!snapshot || typeof window === "undefined") {
		return router.push({ name: routeName, params: { [paramName]: row.name } })
	}

	const state = createListNavigationState({
		...snapshot,
		targetRouteName: routeName,
		targetParamName: paramName,
	})
	const stateKey = writeNavigationState(window.sessionStorage, state)
	const reference = {
		...createNavigationReference(state, state.globalIndex, row.name, row.modified),
		stateKey,
	}

	return router.push({
		name: routeName,
		params: { [paramName]: row.name },
		state: { essdeeListNavigation: reference },
	})
}

export function preserveListNavigationState(currentName = "", currentModified = "") {
	if (typeof window === "undefined") return undefined
	const reference = window.history.state?.essdeeListNavigation
	if (!reference || typeof reference !== "object") return undefined
	return {
		essdeeListNavigation: {
			...reference,
			currentName: String(currentName || reference.currentName || ""),
			currentModified: String(currentModified || reference.currentModified || ""),
		},
	}
}
