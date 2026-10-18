import assert from "node:assert/strict"
import test from "node:test"
import { webDocumentRoute, webDocumentPath } from "../src/router/webDocumentRoutes.js"

test("OCR routes use history base once and preserve deep-link encoding", () => {
	for (const doctype of ["YRP Work Order", "SD YRP Cutting Plan", "SD YRP Finishing Plan"]) {
		const route = webDocumentRoute(doctype, "name /?#", "/web/purchase/lots/Lot")
		assert.equal(`/web${route}`, webDocumentPath(doctype, "name /?#", "/web/purchase/lots/Lot"))
		assert.ok(!route.startsWith("/web"))
	}
	assert.equal(webDocumentRoute("YRP Work Order", "WO", "/web/merch/lots/Lot"), "/merch/work-orders/WO")
})
