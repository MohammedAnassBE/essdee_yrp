import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { canOpenList, getListDoctype, getPermissionRedirect, NO_PERMISSION_PATH } from "../src/router/listPermission.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const boot = (canRead) => ({ user: { name: "worker@example.com", can_read: canRead } })
const route = (path) => ({ path, fullPath: path, params: {} })
const withoutChallan = boot(["YRP Work Order", "YRP Goods Received Note"])

test("list pages map to the DocType they list; documents and reports do not", () => {
	assert.equal(getListDoctype("/cut-panel-store/delivery-challans"), "YRP Delivery Challan")
	assert.equal(getListDoctype({ path: "/sewing/work-orders", query: { supplier: "S" } }), "YRP Work Order")
	assert.equal(getListDoctype("/cutting/plans"), "SD YRP Cutting Plan")
	assert.equal(getListDoctype("/finishing/plans"), "SD YRP Finishing Plan")
	assert.equal(getListDoctype("/cut-panel-store/delivery-challans/DC-1"), null)
	assert.equal(getListDoctype("/cut-panel-store/reports"), null)
	assert.equal(getListDoctype("/cut-panel-store"), null)
})

test("cards for unreadable DocTypes are hidden and readable ones stay", () => {
	assert.equal(canOpenList("/cut-panel-store/delivery-challans", withoutChallan), false)
	assert.equal(canOpenList("/cut-panel-store/work-orders", withoutChallan), true)
	assert.equal(canOpenList("/cut-panel-store/reports", withoutChallan), true)
	assert.equal(canOpenList("/cut-panel-store/delivery-challans", { user: { name: "Administrator" } }), true)
})

test("a direct list URL for an unreadable DocType goes to the permission page", () => {
	assert.deepEqual(getPermissionRedirect(route("/cut-panel-store/delivery-challans"), withoutChallan), {
		path: NO_PERMISSION_PATH,
		query: { doctype: "YRP Delivery Challan", from: "/cut-panel-store/delivery-challans" },
		replace: true,
	})
	assert.equal(getPermissionRedirect(route("/cut-panel-store/work-orders"), withoutChallan), undefined)
	assert.equal(getPermissionRedirect(route("/fabric-store/delivery-challans/DC-1"), withoutChallan), undefined)
})

test("router, launcher and permission page are wired to the list guard", () => {
	const router = source("../src/router/index.js")
	assert.match(router, /getLockedRedirect\(to\) \|\| getPermissionRedirect\(to\)/)
	assert.match(router, /path: NO_PERMISSION_PATH,[\s\S]*?meta: \{ permissionDenied: true \}/)
	assert.match(source("../src/components/common/WorkspaceLauncher.vue"), /isWorkspaceInLayout\(item\) && canOpenList\(item\.to\)/)
	assert.match(source("../src/components/documents/DocumentUnavailable.vue"), /You don't have permission to view \{\{ doctype \}\}/)
})

test("logOut posts to the standard Frappe logout and then redirects to /login", async () => {
	const calls = []
	const assigned = []
	globalThis.window = { location: { assign: (url) => assigned.push(url) }, csrf_token: "token" }
	globalThis.fetch = async (url, options) => {
		calls.push({ url, method: options.method })
		return { ok: true, status: 200, json: async () => ({}) }
	}
	const { logOut } = await import("../src/api/frappe.js")
	await logOut()
	assert.deepEqual(calls, [{ url: "/api/method/logout", method: "POST" }])
	assert.deepEqual(assigned, ["/login"])
})
