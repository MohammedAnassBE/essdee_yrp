#!/usr/bin/env node

import assert from "node:assert/strict"

import { dprFormState } from "../frontend/src/departments/cutting/reports/dailyProductionReportState.js"

assert.deepEqual(dprFormState({
	mode: "summary",
	items: ["ITEM-1"],
	lots: ["LOT-1"],
	location: "Machine Cutting",
	from_date: "2026-10-01",
	to_date: "2026-10-12",
}), {
	summaryMode: true,
	filters: {
		items: ["ITEM-1"],
		lots: ["LOT-1"],
		location: "Machine Cutting",
		fromDate: "2026-10-01",
		toDate: "2026-10-12",
	},
})
assert.deepEqual(dprFormState({ mode: "daily", date: "2026-10-13", location: "" }), {
	summaryMode: false,
	filters: { date: "2026-10-13", location: "" },
})

console.log("daily production report state OK")
