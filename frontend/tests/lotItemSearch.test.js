import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("link suggestions show the search-field description, such as a Lot's Item", () => {
	assert.match(source("../src/components/common/LinkField.vue"), /<small v-if="option\.description">\{\{ formatDatesInText\(option\.description\) \}\}<\/small>/)
	assert.match(source("../src/departments/cutting/reports/AsyncLinkMultiSelect.vue"), /<small v-if="option\.description">\{\{ formatDatesInText\(option\.description\) \}\}<\/small>/)
})

test("sewing supplier Lot suggestions describe each Lot by its Item", async () => {
	const oldWindow = globalThis.window, oldFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" } }
	globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ message: [["C1225-03", "Hamic - Tiger Bermuda"]] }) })
	try {
		const { getSewingSupplierLots } = await import("../src/api/sewing.js")
		assert.deepEqual(await getSewingSupplierLots("Unit 1", "tiger"), [
			{ name: "C1225-03", label: "C1225-03", item: "Hamic - Tiger Bermuda", description: "Hamic - Tiger Bermuda" },
		])
	} finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})
