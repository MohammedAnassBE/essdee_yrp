import test from "node:test"
import assert from "node:assert/strict"

import { drillQuery, readTrackingQuery, trackingQuery } from "../src/departments/planning/dashboard/routeFilters.js"

test("route query round-trips the PPO Tracking selection", () => {
	const query = trackingQuery({ filters: { ppo: ["PPO-1"], lot: [], process: ["Cutting", "Packing"] }, showDispatched: true })
	assert.deepEqual(query, { view: "tracking", ppo: ["PPO-1"], process: ["Cutting", "Packing"], dispatched: "1" })
	assert.deepEqual(readTrackingQuery({ ...query, ppo: "PPO-1" }), { view: "tracking", filters: { ppo: ["PPO-1"], lot: [], process: ["Cutting", "Packing"] }, showDispatched: true })
	assert.equal(readTrackingQuery({}).view, "dashboard")
})

test("a drill-down opens PPO Tracking with only its selection", () => {
	assert.deepEqual(drillQuery({ ppo: [], lot: ["L-1", "L-2"], dispatched: false }), { view: "tracking", lot: ["L-1", "L-2"] })
})

test("readTrackingQuery splits comma-separated values from a typed link", () => {
	assert.deepEqual(readTrackingQuery({ view: "tracking", ppo: "PPO-1, PPO-2,", lot: ["L-1,L-2"] }).filters, { ppo: ["PPO-1", "PPO-2"], lot: ["L-1", "L-2"], process: [] })
})
