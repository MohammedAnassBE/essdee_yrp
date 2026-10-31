import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0]

function formViewLoad(documentName) {
	const source = read("../src/components/common/FormView.vue")
	const body = source.slice(source.indexOf("async function load("), source.indexOf("function buildInitialValues("))
	const seen = []
	const loading = { set value(next) { seen.push(next) }, get value() { return seen.at(-1) } }
	const state = { value: false }
	const live = { refreshes: 0, refresh: async () => { live.refreshes += 1 } }
	const load = new Function("live", "savedAt", "loading", "loadFailed", "error", "success", "documentName", "clearObject", "fieldErrors", "childErrors", "getMeta", "getDoc", "props", "metas", "replaceForm", "buildInitialValues", "clone", "form", "mode", "resolveInitialMode", "emit", "meta", "cleanDocument", "loadSequence", `${body}\nreturn load`)(
		live, { value: null }, loading, state, { value: "" }, { value: "" }, { value: documentName }, () => {}, {}, {}, async () => [], async () => ({ name: "CP-1" }),
		{ doctype: "SD YRP Cutting Plan", name: "CP-1" }, { value: [] }, () => {}, () => ({}), (value) => value, {}, { value: "view" }, () => "view", () => {}, { value: {} }, {}, 0,
	)
	return { load, seen, live }
}

test("background reload keeps the loaded document on screen", async () => {
	const { load, seen, live } = formViewLoad("CP-1")
	await load({ background: true })
	assert.deepEqual(seen, [], "the loading skeleton is never shown")
	assert.equal(live.refreshes, 1, "the live document path reloads in place")
})

test("plain reload and first load still show the loading state", async () => {
	const first = formViewLoad("")
	await first.load({ background: true })
	assert.equal(first.seen[0], true)
	const plain = formViewLoad("CP-1")
	await plain.load()
	assert.equal(plain.seen[0], true)
})

test("Cutting Plan tab refresh reloads in the background so open dialogs stay mounted", () => {
	const source = read("../src/departments/CuttingPlan.vue")
	const refresh = source.slice(source.indexOf("function refreshPage()"), source.indexOf("async function probeEditor"))
	assert.match(refresh, /reload\(\{ background: true \}\)/)
})

test("a CPM or Stock Transfers change reloads both plan tabs", () => {
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingPlanTabs.vue", import.meta.url), "utf8")
	assert.match(source, /<CuttingPlanCpm ref="cpmTab"[^>]*@changed="tabChanged"/)
	assert.match(source, /<CuttingPlanStockTransfers ref="transfersTab"[^>]*@changed="tabChanged"/)
	const body = source.slice(source.indexOf("function tabChanged()"), source.indexOf("function activate(tab)"))
	assert.match(body, /emit\("refresh"\)/)
	assert.match(body, /cpmTab\.value\?\.activate\(\)/)
	assert.match(body, /transfersTab\.value\?\.activate\(\)/)
})
