import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { canShowFiUpdates, fiUpdateKey, fiUpdatePayload, groupFiUpdatesByLot } from "../src/departments/sewing/plan/fiUpdates.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const planner = { sections: { plans: { can_read: true, can_update_fi_dates: true } } }
const rows = [
	{ lot: "L1", item: "Tee", colour: "Red", part: "Top", sewing_plan: "SP1", is_set_item: 1, set_attr: "Part" },
	{ lot: "L1", item: "Tee", colour: "Red", part: "Bottom", sewing_plan: "SP1", is_set_item: 1, set_attr: "Part" },
	{ lot: "L2", item: "Polo", colour: "Blue", part: null, sewing_plan: "SP2", is_set_item: 0 },
]

test("FI Updates shows only in Planning's Sewing Plan for a Production Planner", () => {
	assert.equal(canShowFiUpdates("planning-sewing-plans", planner), true)
	assert.equal(canShowFiUpdates("sewing-plans", planner), false)
	assert.equal(canShowFiUpdates("planning-sewing-plans", { sections: { plans: { can_read: true, can_update_fi_dates: false } } }), false)
	assert.equal(canShowFiUpdates("planning-sewing-plans", {}), false)
})

test("FI rows group by Lot and send only dated Lot, Colour and Part rows", () => {
	const groups = groupFiUpdatesByLot(rows)
	assert.deepEqual(groups.map(group => [group.lot, group.item, group.isSetItem, group.rows.length]), [["L1", "Tee", true, 2], ["L2", "Polo", false, 1]])
	const dates = { [fiUpdateKey(rows[1])]: "2026-10-20", [fiUpdateKey(rows[2])]: "" }
	assert.deepEqual(fiUpdatePayload(rows, dates), [{ sewing_plan: "SP1", lot: "L1", colour: "Red", part: "Bottom", date: "2026-10-20" }])
	assert.notEqual(fiUpdateKey(rows[0]), fiUpdateKey(rows[1]))
})

test("Sewing Plan workspace mounts FI Updates through the capability gate", () => {
	const workspace = read("departments/sewing/SewingPlanWorkspace.vue")
	assert.match(workspace, /canShowFiUpdates\(route\.name, props\.capabilities\) \? \[\{ value: "fi-updates", label: "FI Updates" \}\]/)
	assert.match(workspace, /<SewingFiUpdates v-else-if="active === 'fi-updates'" \/>/)
	assert.match(read("api/sewing.js"), /essdee_yrp\.sewing\.fi_dates"/)
})
