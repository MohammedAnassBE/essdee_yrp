import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"

import { DEPARTMENT_RECORD_ROUTES, webDocumentPath } from "../frontend/src/router/webDocumentRoutes.js"

const previousPrefixes = {
	"YRP Debit": "/web/accounts/debits/",
	"SD YRP Lot": "/web/purchase/lots/",
	"YRP Work Order": "/web/fabric-store/work-orders/",
	"Purchase Order": "/web/fabric-store/purchase-orders/",
	"YRP Delivery Challan": "/web/fabric-store/delivery-challans/",
	"YRP Goods Received Note": "/web/fabric-store/goods-received-notes/",
	"SD YRP Cutting Plan": "/web/cutting/plans/",
	"SD YRP Finishing Plan": "/web/finishing/plans/",
	"SD YRP Finishing Plan Dispatch": "/web/finishing/dispatches/",
	"SD YRP Product": "/web/pd/products/",
	"SD YRP Product Release": "/web/pd/product-releases/",
	"SD YRP Lotwise Item Profit": "/web/pd/lotwise-item-profits/",
	"YRP Purchase Invoice": "/web/accounts/purchase-invoices/",
	"YRP Bill Tracking": "/web/hr/bill-tracking/",
	"YRP Item Price": "/web/purchase/item-prices/",
	"YRP Item Production Detail": "/web/merch/item-production-details/",
}
const source = readFileSync(new URL("../frontend/src/router/webDocumentRoutes.js", import.meta.url), "utf8")
const globalRoutes = vm.runInNewContext(`${source.split("export const DEPARTMENT_RECORD_ROUTES")[0]}; recordRoutes`)
const fallback = (doctype, name) => `/web/document-unavailable?${new URLSearchParams({ doctype, name })}`
for (const name of ["Record 1", "A/B?#&%", "தமிழ்", 123]) {
	for (const [doctype, resolve] of Object.entries(globalRoutes)) {
		const prefix = previousPrefixes[doctype] || (doctype === "YRP Process Cost" ? "/web/merch/process-costs/" : null)
		assert.ok(prefix, `new global route needs an explicit regression expectation: ${doctype}`)
		const expected = prefix + encodeURIComponent(String(name))
		assert.equal(resolve(String(name)), expected)
		for (const path of ["/web/sales/production-orders", "/web/hr/bill-tracking", "/web/accounts/purchase-invoices", "/web/merchandise", "/merch", ""]) {
			assert.equal(webDocumentPath(doctype, name, path), expected)
		}
	}
	for (const path of ["/web/merch", "/web/merch/", "/web/merch/work-orders/WO-1"]) {
		for (const [doctype, resolve] of Object.entries(DEPARTMENT_RECORD_ROUTES["/merch"])) {
			assert.equal(webDocumentPath(doctype, name, path), resolve(String(name)))
		}
		assert.equal(webDocumentPath("Purchase Order", name, path), previousPrefixes["Purchase Order"] + encodeURIComponent(String(name)))
	}
	for (const path of ["/web/sales/", "/web/merch/"]) {
		assert.equal(webDocumentPath("Unknown DocType", name, path), fallback("Unknown DocType", String(name)))
	}
}
for (const [doctype, section] of Object.entries({
	"SD YRP Lot": "lots", "YRP Work Order": "work-orders", "YRP Production Order": "production-orders",
	"YRP Process Cost": "process-costs", "YRP Bill Tracking": "bill-tracking",
	"YRP Purchase Invoice": "purchase-invoices", "YRP Item Production Detail": "item-production-details",
})) {
	assert.equal(webDocumentPath(doctype, "A/B", "/web/merch/"), `/web/merch/${section}/A%2FB`)
}
const originalLocation = globalThis.location
try {
	globalThis.location = { pathname: "/web/merch/purchase-invoices/PI-1" }
	assert.equal(webDocumentPath("YRP Bill Tracking", "BT-1"), "/web/merch/bill-tracking/BT-1")
	assert.equal(webDocumentPath("YRP Work Order", "WO-1").replace(/^\/web(?=\/)/, ""), "/merch/work-orders/WO-1")
	globalThis.location.pathname = "/web/accounts/purchase-invoices/PI-1"
	assert.equal(webDocumentPath("YRP Bill Tracking", "BT-1"), "/web/hr/bill-tracking/BT-1")
} finally {
	if (originalLocation === undefined) delete globalThis.location
	else globalThis.location = originalLocation
}
for (const path of ["/web/merch", "/web/sales"]) {
	assert.equal(webDocumentPath("", "A", path), "/web/document-unavailable")
	assert.equal(webDocumentPath("YRP Work Order", "", path), "/web/document-unavailable")
}
console.log("web document routes tests passed")
