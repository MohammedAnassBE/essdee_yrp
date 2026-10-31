import assert from "node:assert/strict"
import test from "node:test"
import { downloadPrintPdf } from "../src/api/frappe.js"
import { buildPrintPdfArgs } from "../src/utils/printUrl.js"

async function withBrowser(response, run) {
	const old = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch, create: URL.createObjectURL, revoke: URL.revokeObjectURL }
	const requests = [], links = []
	globalThis.window = { csrf_token: "token", setTimeout: () => {} }
	globalThis.document = { cookie: "", createElement: tag => { const link = { tag, click() { link.clicked = true } }; links.push(link); return link } }
	globalThis.fetch = async (url, request) => { requests.push([url, request]); return response }
	URL.createObjectURL = () => "blob:pdf"
	URL.revokeObjectURL = () => {}
	try { await run(requests, links) } finally {
		Object.assign(globalThis, { window: old.window, document: old.document, fetch: old.fetch })
		URL.createObjectURL = old.create; URL.revokeObjectURL = old.revoke
	}
}

test("PDF args mirror the print letter head selection", () => {
	assert.deepEqual(buildPrintPdfArgs({ doctype: "Purchase Order", name: "PO-1", format: "Essdee Purchase Order", letterHead: "" }), { doctype: "Purchase Order", name: "PO-1", format: "Essdee Purchase Order", no_letterhead: 1 })
	assert.deepEqual(buildPrintPdfArgs({ doctype: "Purchase Order", name: "PO-1", format: "F", letterHead: "Essdee" }), { doctype: "Purchase Order", name: "PO-1", format: "F", no_letterhead: 0, letterhead: "Essdee" })
})

test("PDF download posts every print arg to Frappe and saves it as the document name", async () => {
	const response = { ok: true, status: 200, headers: { get: () => "inline; filename=YRP-PO-2026-00057.pdf" }, blob: async () => new Blob(["%PDF"]) }
	await withBrowser(response, async (requests, links) => {
		const args = { doctype: "YRP Production Order", name: "YRP-PO-2026-00057", format: "Essdee Production Order", pieces_per_box: 12 }
		await downloadPrintPdf(args)
		assert.equal(requests[0][0], "/api/method/frappe.utils.print_format.download_pdf")
		assert.equal(requests[0][1].method, "POST")
		assert.deepEqual(JSON.parse(requests[0][1].body), args)
		assert.equal(links[0].download, "YRP-PO-2026-00057.pdf")
		assert.equal(links[0].href, "blob:pdf")
		assert.equal(links[0].clicked, true)
	})
	const bare = { ...response, headers: { get: () => "" } }
	await withBrowser(bare, async (_requests, links) => {
		await downloadPrintPdf({ doctype: "Purchase Order", name: "PO 1/2", format: "Standard" })
		assert.equal(links[0].download, "PO-1-2.pdf")
	})
})

test("PDF generation failures surface the server message", async () => {
	const response = { ok: false, status: 500, json: async () => ({ exc_type: "OSError", _server_messages: JSON.stringify([JSON.stringify({ message: "wkhtmltopdf not found" })]) }) }
	await withBrowser(response, async (_requests, links) => {
		await assert.rejects(downloadPrintPdf({ doctype: "Purchase Order", name: "PO-1", format: "Standard" }), /wkhtmltopdf not found/)
		assert.deepEqual(links, [])
	})
})
