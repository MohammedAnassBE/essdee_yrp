#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	createListNavigationState,
	createNavigationReference,
	deterministicOrder,
	navigationContextMatches,
	navigationStorageKey,
	readNavigationState,
	resolveAdjacentNames,
	writeNavigationState,
} from "../frontend/src/utils/listNavigation.js"
import { preserveListNavigationState } from "../frontend/src/router/listDocumentNavigation.js"

class MemoryStorage {
	#values = new Map()

	getItem(key) {
		return this.#values.has(key) ? this.#values.get(key) : null
	}

	setItem(key, value) {
		this.#values.set(key, String(value))
	}
}

assert.equal(deterministicOrder("modified", "desc"), "modified desc, name desc")
assert.equal(deterministicOrder("supplier", "ASC"), "supplier asc, name asc")
assert.equal(deterministicOrder("name", "desc"), "name desc")

const state = createListNavigationState({
	sourceRouteName: "cutting-plans",
	sourceFullPath: "/web/cutting/cutting-plans?status=Open",
	doctype: "Cutting Plan",
	filters: [["status", "=", "Open"]],
	orderBy: "modified desc, name desc",
	pageStart: 20,
	pageSize: 20,
	globalIndex: 22,
	total: 63,
	targetRouteName: "cutting-plan",
	targetParamName: "cuttingPlanId",
})

assert.equal(state.version, 2)
assert.ok(state.snapshotId)
assert.equal(state.globalIndex, 22)
assert.deepEqual(state.filters, [["status", "=", "Open"]])

const storage = new MemoryStorage()
const expectedKey = navigationStorageKey("cutting-plans", "Cutting Plan", state.snapshotId)
assert.equal(writeNavigationState(storage, state), expectedKey)
assert.deepEqual(readNavigationState(storage, expectedKey), state)
assert.deepEqual(readNavigationState(storage, navigationStorageKey("cutting-plans", "Cutting Plan")), state)

storage.setItem(expectedKey, "{not-json")
assert.equal(readNavigationState(storage, expectedKey), null)
storage.setItem(expectedKey, JSON.stringify({ ...state, version: 99 }))
assert.equal(readNavigationState(storage, expectedKey), null)
writeNavigationState(storage, state)

const startState = createListNavigationState({ ...state, globalIndex: 0, pageStart: 0 })
const startReference = createNavigationReference(startState, 0, "CP-001", "2026-10-08 09:00:01")
assert.deepEqual(
	resolveAdjacentNames({
		state: startState,
		reference: startReference,
		rows: [
			{ name: "CP-001", modified: "2026-10-08 09:00:01" },
			{ name: "CP-002", modified: "2026-10-08 09:00:02" },
			{ name: "CP-003", modified: "2026-10-08 09:00:03" },
		],
	}),
	{ previousName: null, previousModified: "", nextName: "CP-002", nextModified: "2026-10-08 09:00:02", changed: false, reason: "" },
)

const middleReference = createNavigationReference(state, 22, "CP-023", "2026-10-08 09:00:23")
assert.deepEqual(
	resolveAdjacentNames({
		state,
		reference: middleReference,
		rows: [
			{ name: "CP-022", modified: "2026-10-08 09:00:22" },
			{ name: "CP-023", modified: "2026-10-08 09:00:23" },
			{ name: "CP-024", modified: "2026-10-08 09:00:24" },
		],
	}),
	{ previousName: "CP-022", previousModified: "2026-10-08 09:00:22", nextName: "CP-024", nextModified: "2026-10-08 09:00:24", changed: false, reason: "" },
)

const endState = createListNavigationState({ ...state, globalIndex: 62, total: 63, pageStart: 60 })
const endReference = createNavigationReference(endState, 62, "CP-063", "2026-10-08 09:01:03")
assert.deepEqual(
	resolveAdjacentNames({
		state: endState,
		reference: endReference,
		rows: [
			{ name: "CP-062", modified: "2026-10-08 09:01:02" },
			{ name: "CP-063", modified: "2026-10-08 09:01:03" },
		],
	}),
	{ previousName: "CP-062", previousModified: "2026-10-08 09:01:02", nextName: null, nextModified: "", changed: false, reason: "" },
)

assert.deepEqual(
	resolveAdjacentNames({
		state,
		reference: middleReference,
		rows: [
			{ name: "CP-021", modified: "2026-10-08 09:00:21" },
			{ name: "CP-022", modified: "2026-10-08 09:00:22" },
			{ name: "CP-023", modified: "2026-10-08 09:00:23" },
		],
	}),
	{
		previousName: null,
		previousModified: "",
		nextName: null,
		nextModified: "",
		changed: true,
		reason: "List changed — return to list",
	},
)

assert.deepEqual(
	resolveAdjacentNames({
		reference: middleReference,
		rows: [
			{ name: "CP-022", modified: "2026-10-08 09:00:22" },
			{ name: "CP-023", modified: "2026-10-08 10:30:00" },
			{ name: "CP-024", modified: "2026-10-08 09:00:24" },
		],
	}),
	{
		previousName: null,
		previousModified: "",
		nextName: null,
		nextModified: "",
		changed: true,
		reason: "List changed — return to list",
	},
)

const { snapshotId: _previousSnapshotId, ...stateWithoutSnapshot } = state
const newerFilterState = createListNavigationState({ ...stateWithoutSnapshot, filters: [["status", "=", "Closed"]] })
assert.notEqual(newerFilterState.snapshotId, state.snapshotId)
assert.notEqual(writeNavigationState(storage, newerFilterState), expectedKey)
assert.deepEqual(readNavigationState(storage, expectedKey), state)
assert.equal(navigationContextMatches(middleReference, state, "cutting-plan", "CP-023"), true)
assert.equal(navigationContextMatches(middleReference, newerFilterState, "cutting-plan", "CP-023"), false)
assert.equal(navigationContextMatches({ ...middleReference, index: 21 }, state, "cutting-plan", "CP-023"), false)

global.window = { history: { state: { essdeeListNavigation: middleReference, unrelated: "kept" } } }
assert.deepEqual(
	preserveListNavigationState("CP-023-RENAMED", "2026-10-08 11:00:00"),
	{ essdeeListNavigation: { ...middleReference, currentName: "CP-023-RENAMED", currentModified: "2026-10-08 11:00:00" } },
)
global.window.history.state = { unrelated: "kept" }
assert.equal(preserveListNavigationState("CP-023"), undefined)
delete global.window

console.log("List navigation state verified.")
