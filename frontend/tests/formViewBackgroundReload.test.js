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
	const load = new Function("loading", "loadFailed", "error", "success", "documentName", "clearObject", "fieldErrors", "childErrors", "getMeta", "getDoc", "props", "metas", "replaceForm", "buildInitialValues", "clone", "form", "mode", "resolveInitialMode", "emit", "meta", "cleanDocument", "loadSequence", `${body}\nreturn load`)(
		loading, state, { value: "" }, { value: "" }, { value: documentName }, () => {}, {}, {}, async () => [], async () => ({ name: "CP-1" }),
		{ doctype: "SD YRP Cutting Plan", name: "CP-1" }, { value: [] }, () => {}, () => ({}), (value) => value, {}, { value: "view" }, () => "view", () => {}, { value: {} }, {}, 0,
	)
	return { load, seen }
}

test("background reload keeps the loaded document on screen", async () => {
	const { load, seen } = formViewLoad("CP-1")
	await load({ background: true })
	assert.deepEqual(seen, [false, false])
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
