import assert from "node:assert/strict"
import test from "node:test"
import { canReadDoctype, deskDocumentPath, documentLinkTarget, linkFieldTarget } from "../src/utils/linkTarget.js"
import { hasWebDocumentPage, webDocumentPath, webDocumentRoute } from "../src/router/webDocumentRoutes.js"

test("read permission uses boot can_read and both Administrator identities", () => {
	const previous = globalThis.window
	try {
		globalThis.window = undefined
		assert.equal(canReadDoctype("Item"), false)
		assert.equal(canReadDoctype("Item", {}), false)
		assert.equal(canReadDoctype("Item", { user: { can_read: ["Item"] } }), true)
		assert.equal(canReadDoctype("User", { user: { can_read: ["Item"] } }), false)
		assert.equal(canReadDoctype("Item", { user: { can_read: "Item" } }), false)
		assert.equal(canReadDoctype("Item", { user: { name: "Administrator" } }), true)
		globalThis.window = { frappe: { session: { user: "Administrator" } } }
		assert.equal(canReadDoctype("User"), true)
		globalThis.window.frappe = { boot: { user: { name: "reader", can_read: ["Item"] } } }
		assert.equal(canReadDoctype("Item"), true)
	} finally { globalThis.window = previous }
})

test("document targets encode names and choose web pages or the explicit Desk fallback", () => {
	const name = "A/B #1?x&y%", encoded = encodeURIComponent(name)
	assert.deepEqual(documentLinkTarget("Item", name), { href: `/web/purchase/items/${encoded}`, route: `/purchase/items/${encoded}` })
	assert.deepEqual(documentLinkTarget("User", name), { href: `/desk/user/${encoded}`, route: null })
	assert.equal(deskDocumentPath("Item Attribute", name), `/desk/item-attribute/${encoded}`)
	assert.equal(documentLinkTarget("", name), null)
	assert.equal(documentLinkTarget("Item", ""), null)
	assert.equal(documentLinkTarget("Item", "   "), null)
	assert.equal(hasWebDocumentPage("User"), false)
	assert.equal(webDocumentRoute("User", "U"), "/document-unavailable?doctype=User&name=U")
})

test("route extensions preserve default, Merch and Planning document pages", () => {
	const mappings = {
		Item: "/purchase/items",
		"YRP Production Order": "/sales/production-orders",
		"SD YRP Cutting Order": "/cutting/orders",
		"SD YRP Cutting Bulk Lay Sheets": "/cutting/bulk-lay-sheets",
		"SD YRP Cutting Laysheet Planner": "/cutting/lay-sheet-planner",
	}
	for (const [doctype, path] of Object.entries(mappings)) {
		assert.equal(hasWebDocumentPage(doctype), true)
		assert.equal(webDocumentPath(doctype, "A/B"), `/web${path}/A%2FB`)
	}
	for (const [doctype, path] of Object.entries({ "SD YRP Lot": "lots", "YRP Work Order": "work-orders", "YRP Production Order": "production-orders", "SD YRP Cutting Plan": "cutting-plans", "SD YRP Finishing Plan": "finishing-plans" })) {
		assert.equal(documentLinkTarget(doctype, "A/B", "/web/planning/lots/L").route, `/planning/${path}/A%2FB`)
	}
	assert.equal(documentLinkTarget("SD YRP Lot", "X", "/web/merch/lots/L").route, "/merch/lots/X")
	assert.equal(documentLinkTarget("YRP Production Order", "X", "/web/merch/lots/L").route, "/merch/production-orders/X")
	assert.equal(documentLinkTarget("SD YRP Lot", "X", "/web/merchandise").route, "/purchase/lots/X")
})

test("field targets resolve Link, Dynamic Link and explicit backend targets with raw names", () => {
	assert.deepEqual(linkFieldTarget({ fieldtype: "Link", options: "User", value: " Person ", link_name: " user@example.test " }), { doctype: "User", name: "user@example.test" })
	assert.deepEqual(linkFieldTarget({ fieldtype: "Dynamic Link", options: "against", value: "DOC" }, { against: "Item" }), { doctype: "Item", name: "DOC" })
	assert.deepEqual(linkFieldTarget({ fieldtype: "Dynamic Link", options: "against", link_doctype: "User", value: "U" }, { against: "Item" }), { doctype: "User", name: "U" })
	assert.deepEqual(linkFieldTarget({ fieldtype: "Data", link_doctype: "Item", value: 123 }), { doctype: "Item", name: "123" })
	for (const field of [{ fieldtype: "Data", value: "X" }, { fieldtype: "Link", options: "Item", value: " " }, { fieldtype: "Link", options: "Item", value: "X", link_name: "" }, { fieldtype: "Dynamic Link", options: "against", value: "X" }]) assert.equal(linkFieldTarget(field), null)
})

test("F-A18 Sales PPO linked lots open the Merch Lot page while other departments keep their routes", () => {
	for (const path of ["/web/sales", "/web/sales/production-orders/PPO-1"]) {
		assert.equal(webDocumentPath("SD YRP Lot", "LOT/1", path), "/web/merch/lots/LOT%2F1")
	}
	assert.equal(webDocumentPath("SD YRP Lot", "LOT/1", "/web/planning/production-orders/PPO-1"), "/web/planning/lots/LOT%2F1")
	assert.equal(webDocumentPath("SD YRP Lot", "LOT/1", "/web/merch/production-orders/PPO-1"), "/web/merch/lots/LOT%2F1")
	assert.equal(webDocumentPath("SD YRP Lot", "LOT/1", "/web/purchase"), "/web/purchase/lots/LOT%2F1")
	assert.equal(webDocumentPath("SD YRP Lot", "LOT/1", "/web/sales-other"), "/web/purchase/lots/LOT%2F1")
})
