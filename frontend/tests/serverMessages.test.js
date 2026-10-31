import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { callMethod, getDoc } from "../src/api/frappe.js"
import { parseServerMessages, setServerMessageHandler } from "../src/api/serverMessages.js"

const frappeMessages = (...entries) => JSON.stringify(entries.map((entry) => JSON.stringify(entry)))

async function withFetch(response, run) {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { csrf_token: "token", location: { host: "x", pathname: "/", search: "", hash: "" } }
	globalThis.fetch = async () => response
	try { return await run() } finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch; setServerMessageHandler(null) }
}

test("parseServerMessages reads msgprint entries as plain text and skips caught throws", () => {
	const raw = frappeMessages(
		{ message: "No Sewing Plan was created: <b>S-0155</b> does not apply sewing plans.", title: "Sewing Plan", indicator: "orange" },
		{ message: "Saved", alert: 1, indicator: "green" },
		{ message: ["Row 1", "Row 2"], as_list: 1 },
		{ message: "" },
		{ message: "Please set a default contact for supplier S-1", raise_exception: 1, indicator: "red" },
	)
	assert.deepEqual(parseServerMessages(raw), [
		{ title: "Sewing Plan", message: "No Sewing Plan was created: S-0155 does not apply sewing plans.", indicator: "orange", alert: false },
		{ title: "Message", message: "Saved", indicator: "green", alert: true },
		{ title: "Message", message: "Row 1\nRow 2", indicator: "", alert: false },
	])
	assert.deepEqual(parseServerMessages("not json"), [])
})

test("a successful call announces its server messages once and still returns the message", async () => {
	const seen = []
	const payload = { message: "WO-1", _server_messages: frappeMessages({ message: "No Finishing Plan was created." }) }
	const result = await withFetch({ ok: true, status: 200, json: async () => payload }, async () => {
		setServerMessageHandler((messages) => seen.push(messages))
		return callMethod("essdee_yrp.example", {})
	})
	assert.equal(result, "WO-1")
	assert.equal(seen.length, 1)
	assert.equal(seen[0][0].message, "No Finishing Plan was created.")
})

test("resource reads announce messages too, and a response without messages stays silent", async () => {
	const seen = []
	await withFetch({ ok: true, status: 200, json: async () => ({ data: { name: "A" } }) }, async () => {
		setServerMessageHandler((messages) => seen.push(messages))
		assert.deepEqual(await getDoc("YRP Work Order", "A"), { name: "A" })
	})
	assert.equal(seen.length, 0)
})

test("a silent call keeps its own confirmation and announces nothing", async () => {
	const seen = []
	const payload = { message: "ok", _server_messages: frappeMessages({ message: "Grammage approved successfully", alert: 1 }) }
	await withFetch({ ok: true, status: 200, json: async () => payload }, async () => {
		setServerMessageHandler((messages) => seen.push(messages))
		assert.equal(await callMethod("essdee_yrp.example", {}, { silent: true }), "ok")
	})
	assert.equal(seen.length, 0)
	const bulk = fs.readFileSync(new URL("../src/api/cuttingBulkLaySheets.js", import.meta.url), "utf8")
	assert.match(bulk, /call\("approve_grammage", \{ doc_name: name, detail_name: detailName \}, \{ silent: true \}\)/)
})

test("errors keep throwing with the server message and are not announced", async () => {
	const seen = []
	const payload = { exc_type: "ValidationError", exc: "[]", _server_messages: frappeMessages({ message: "Insufficient stock", raise_exception: 1, indicator: "red" }) }
	await withFetch({ ok: false, status: 417, json: async () => payload }, async () => {
		setServerMessageHandler((messages) => seen.push(messages))
		await assert.rejects(callMethod("essdee_yrp.example", {}), (error) => error.message === "Insufficient stock" && error.status === 417)
	})
	assert.equal(seen.length, 0)
})

test("the app shell mounts one server message dialog", () => {
	const app = fs.readFileSync(new URL("../src/App.vue", import.meta.url), "utf8")
	assert.equal(app.match(/<ServerMessageDialog \/>/g)?.length, 1)
	const dialog = fs.readFileSync(new URL("../src/components/common/ServerMessageDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /setServerMessageHandler\(show\)/)
	assert.match(dialog, /toast\.add/)
})

test("a stock shortage list keeps one line per short item", async () => {
	const message = "Insufficient stock for 2 items:<ul><li>40&apos;s GL Dyed Fabric New-Navy-19 Dia (Lot F0426-86) at S-0163: balance 16.9, requested 16.95, short 0.05</li><li>Rib &lt;Navy&gt; at S-0163: balance 1.0, requested 3.0, short 2.0</li></ul>"
	const payload = { exc_type: "NegativeStockError", exc: "[]", _server_messages: frappeMessages({ message, title: "Insufficient Stock", raise_exception: 1, indicator: "red" }) }
	await withFetch({ ok: false, status: 417, json: async () => payload }, async () => {
		await assert.rejects(callMethod("essdee_yrp.example", {}), (error) => {
			assert.equal(error.message, "Insufficient stock for 2 items:\n• 40's GL Dyed Fabric New-Navy-19 Dia (Lot F0426-86) at S-0163: balance 16.9, requested 16.95, short 0.05\n• Rib <Navy> at S-0163: balance 1.0, requested 3.0, short 2.0")
			return true
		})
	})
})

test("the document error dialog scrolls a long message", () => {
	const dialog = fs.readFileSync(new URL("../src/components/documents/DocumentErrorDialog.vue", import.meta.url), "utf8")
	assert.match(dialog, /\.document-error-dialog__body p \{[^}]*max-height: [^;]+;[^}]*overflow-y: auto;/)
})
