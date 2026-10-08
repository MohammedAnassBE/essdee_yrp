#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	createListNavigationState,
	createNavigationReference,
	deterministicOrder,
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

assert.equal(state.version, 1)
assert.equal(state.globalIndex, 22)
assert.deepEqual(state.filters, [["status", "=", "Open"]])

const storage = new MemoryStorage()
const expectedKey = navigationStorageKey("cutting-plans", "Cutting Plan")
assert.equal(writeNavigationState(storage, state), expectedKey)
assert.deepEqual(readNavigationState(storage, expectedKey), state)

storage.setItem(expectedKey, "{not-json")
assert.equal(readNavigationState(storage, expectedKey), null)
storage.setItem(expectedKey, JSON.stringify({ ...state, version: 99 }))
assert.equal(readNavigationState(storage, expectedKey), null)

const startState = createListNavigationState({ ...state, globalIndex: 0, pageStart: 0 })
const startReference = createNavigationReference(startState, 0, "CP-001")
assert.deepEqual(
	resolveAdjacentNames({
		state: startState,
		reference: startReference,
		rows: [{ name: "CP-001" }, { name: "CP-002" }, { name: "CP-003" }],
	}),
	{ previousName: null, nextName: "CP-002", changed: false, reason: "" },
)

const middleReference = createNavigationReference(state, 22, "CP-023")
assert.deepEqual(
	resolveAdjacentNames({
		state,
		reference: middleReference,
		rows: [{ name: "CP-022" }, { name: "CP-023" }, { name: "CP-024" }],
	}),
	{ previousName: "CP-022", nextName: "CP-024", changed: false, reason: "" },
)

const endState = createListNavigationState({ ...state, globalIndex: 62, total: 63, pageStart: 60 })
const endReference = createNavigationReference(endState, 62, "CP-063")
assert.deepEqual(
	resolveAdjacentNames({
		state: endState,
		reference: endReference,
		rows: [{ name: "CP-062" }, { name: "CP-063" }],
	}),
	{ previousName: "CP-062", nextName: null, changed: false, reason: "" },
)

assert.deepEqual(
	resolveAdjacentNames({
		state,
		reference: middleReference,
		rows: [{ name: "CP-021" }, { name: "CP-022" }, { name: "CP-023" }],
	}),
	{
		previousName: null,
		nextName: null,
		changed: true,
		reason: "List changed — return to list",
	},
)

global.window = { history: { state: { essdeeListNavigation: middleReference, unrelated: "kept" } } }
assert.deepEqual(
	preserveListNavigationState("CP-023-RENAMED"),
	{ essdeeListNavigation: { ...middleReference, currentName: "CP-023-RENAMED" } },
)
global.window.history.state = { unrelated: "kept" }
assert.equal(preserveListNavigationState("CP-023"), undefined)
delete global.window

console.log("List navigation state verified.")
