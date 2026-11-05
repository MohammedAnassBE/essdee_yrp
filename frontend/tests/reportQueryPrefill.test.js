import assert from "node:assert/strict"
import test from "node:test"

import { reportQueryValues } from "../src/composables/useReportQueryPrefill.js"

test("query params fill only the report's own filters, as lists where the filter is a list", () => {
	const filters = { lot: [], item: "", process_list: [], status: "Open" }
	assert.deepEqual(reportQueryValues({ lot: "C0426-35/2", item: "VEST", process_list: "Stitching", process: "ignored", status: "" }, filters, ["lot", "item", "process_list", "status"]), {
		lot: ["C0426-35/2"], item: "VEST", process_list: ["Stitching"],
	})
	assert.deepEqual(reportQueryValues({ lot: ["L1", "L2"] }, { lot: "" }, ["lot"]), { lot: "L1" })
	assert.deepEqual(reportQueryValues({}, filters, ["lot"]), {})
})
