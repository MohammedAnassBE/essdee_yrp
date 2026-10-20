import assert from "node:assert/strict"
import test from "node:test"
import { buildPrintUrl, openPrintUrl } from "../src/utils/printUrl.js"

const args = { doctype: "YRP Goods Received Note", name: "GRN/26 # 1", format: "Essdee A&B / Print" }
const params = (overrides = {}) => new URL(buildPrintUrl({ ...args, ...overrides }), "https://test.local").searchParams

test("print URL encodes the format and document name", () => {
	const url = buildPrintUrl(args)
	assert.ok(url.startsWith("/printview?"))
	assert.ok(url.includes("GRN%2F26+%23+1"))
	assert.equal(params().get("name"), args.name)
	assert.equal(params().get("doctype"), args.doctype)
	assert.equal(params().get("format"), args.format)
})
test("print URL selects a letter head or explicitly disables it", () => {
	assert.equal(params().get("no_letterhead"), "1")
	assert.equal(params().has("letterhead"), false)
	assert.equal(params({ letterHead: "Essdee & Co" }).get("no_letterhead"), "0")
	assert.equal(params({ letterHead: "Essdee & Co" }).get("letterhead"), "Essdee & Co")
})
test("custom buttons can override or omit the letterhead flag", () => {
	assert.equal(params({ noLetterhead: false }).get("no_letterhead"), "0")
	assert.equal(params({ letterHead: "Essdee", noLetterhead: true }).get("no_letterhead"), "1")
	assert.equal(params({ noLetterhead: null }).has("no_letterhead"), false)
})
test("trigger_print defaults to enabled and supports disabling", () => {
	assert.equal(params().get("trigger_print"), "1")
	assert.equal(params({ triggerPrint: false }).get("trigger_print"), "0")
})
test("opening a print URL reports blocked popups", () => {
	const previous = globalThis.window
	try {
		globalThis.window = { open: (...args) => { assert.deepEqual(args, ["/printview?test", "_blank"]); return {} } }
		assert.equal(openPrintUrl("/printview?test"), true)
		globalThis.window.open = () => null
		assert.equal(openPrintUrl("/printview?test"), false)
	} finally { globalThis.window = previous }
})
