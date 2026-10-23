import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as productionOrderDisplay from "../src/departments/sales/productionOrderDisplay.js"
import * as pendingRequest from "../src/departments/sales/productionOrderPendingRequest.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const salesSource = (name) => source(`../src/departments/sales/${name}`)

test("F-A01 save blockers name every missing field and explain an empty matrix", async () => {
	const { productionOrderSaveBlockers } = await import("../src/departments/sales/productionOrderSaveBlockers.js")
	assert.deepEqual(productionOrderSaveBlockers({}, []), ["Item", "Production Term", "Delivery Date", "Don't Deliver After", "Select an Item to load its size matrix"])
	const complete = { item: "POLO", production_term: "TERM", delivery_date: "2026-10-20", dont_deliver_after: "2026-10-21" }
	assert.deepEqual(productionOrderSaveBlockers(complete, [{ quantity: 0 }, { quantity: -1 }]), ["at least one size quantity above 0"])
	assert.deepEqual(productionOrderSaveBlockers(complete, [{ quantity: "2" }]), [])
	assert.deepEqual(productionOrderSaveBlockers(complete, [{ quantity: "invalid" }]), ["at least one size quantity above 0"])
	const editor = salesSource("ProductionOrderEditor.vue")
	assert.match(editor, /const canSave = computed\(\(\) => saveBlockers\.value\.length === 0\)/)
	assert.match(editor, /v-if="[^"\n]*saveBlockers\.length[^"\n]*"[^>]*[\s\S]*?saveBlockers\.join/)
})

test("F-A02 editor and view expose fabric details, submitted terms and multiline comment log", () => {
	const editor = salesSource("ProductionOrderEditor.vue")
	for (const field of ["gsm", "fabric", "dia"]) assert.match(editor, new RegExp(`v-model="form\\.${field}"`))
	assert.match(editor, /doctype="YRP Item Attribute Value"/)
	assert.match(editor, /doctype="YRP Production Term" :filters="\{ docstatus: 1 \}"/)
	const workspace = source("../../essdee_yrp/sales/web_workspace.py")
	for (const field of ["gsm", "fabric", "dia"]) {
		assert.match(workspace.match(/RECORD_FIELDS = \(([\s\S]*?)\)/)[1], new RegExp(`"${field}"`))
		assert.match(workspace.match(/EDITOR_FIELDS = \(([\s\S]*?)\)/)[1], new RegExp(`"${field}"`))
	}
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /v-if="workspace\.histories\?\.comments"/)
	assert.match(view, /Comment Log/)
	assert.match(view, /white-space: pre-wrap/)
})

test("F-A03 past delivery warning compares local calendar dates and does not block saving", async () => {
	const { productionOrderDeliveryWarning, productionOrderSaveBlockers } = await import("../src/departments/sales/productionOrderSaveBlockers.js")
	assert.equal(productionOrderDeliveryWarning("2026-10-19", new Date(2026, 9, 20)), "Delivery Date is in the past. Request Approval will be blocked until it is changed.")
	for (const date of ["", "2026-10-20", "2026-10-21"]) assert.equal(productionOrderDeliveryWarning(date, new Date(2026, 9, 20)), "")
	assert.deepEqual(productionOrderSaveBlockers({ item: "I", production_term: "T", delivery_date: "2026-10-19", dont_deliver_after: "2026-10-21" }, [{ quantity: 1 }]), [])
	assert.match(salesSource("ProductionOrderEditor.vue"), /v-if="deliveryWarning"/)
})

test("F-A04 commands have explicit confirmation and success messages, with delete toast before navigation", async () => {
	const { productionOrderConfirmation, productionOrderSuccess } = await import("../src/departments/sales/productionOrderMessages.js")
	const messages = {
		delete: "Delete PPO-1? This cannot be undone.", cancel: "Cancel PPO-1? Linked documents are checked before it is cancelled.",
		amend: "Create an amended copy of PPO-1?", reopen: "Reopen PPO-1?", approve_ppo: "Approve and submit PPO-1?",
		request_ppo_approval: "Send PPO-1 for PPO approval?", approve_status: "Approve the requested status change for PPO-1?",
		approve_quantity_ratio: "Approve the requested quantity and ratio changes for PPO-1?", approve_transfer: "Approve the incoming quantity transfer to PPO-1?",
	}
	for (const [command, message] of Object.entries(messages)) assert.equal(productionOrderConfirmation(command, "PPO-1"), message)
	assert.equal(productionOrderSuccess("delete", "Delete"), "Production Order deleted")
	assert.equal(productionOrderSuccess("change_status", "Change Status", { record: { status: "Pending Request" } }), "Status change sent for approval")
	assert.equal(productionOrderSuccess("change_status", "Change Status", { record: { status: "Not Processed" } }), "Status updated")
	assert.equal(productionOrderSuccess("change_dates", "Change Dates"), "Date change tracked")
	assert.equal(productionOrderSuccess("approve_ppo", "Approve & Submit PPO"), "PPO approved and submitted")
	assert.equal(productionOrderSuccess("unknown_command", "Custom"), "Custom done")
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /useToast/)
	assert.ok(view.indexOf("toast.add(") < view.indexOf("if (result.deleted)"))
})

test("F-A05 overview preserves value case and formats datetimes without seconds or timezone conversion", async () => {
	const { productionOrderFieldDisplay } = await import("../src/departments/sales/productionOrderDisplay.js")
	assert.equal(productionOrderFieldDisplay({ fieldname: "submitted_time", fieldtype: "Datetime", value: "2026-10-20 19:29:17.278784" }), "20-10-2026 19:29")
	assert.equal(productionOrderFieldDisplay({ fieldtype: "Datetime", value: "2026-10-20T00:01:00" }), "20-10-2026 00:01")
	assert.equal(productionOrderFieldDisplay({ fieldtype: "Date", value: "2026-10-20" }), "20-10-2026")
	assert.equal(productionOrderFieldDisplay({ fieldname: "comments", value: "Keep Mixed CASE" }), "Keep Mixed CASE")
	assert.equal(productionOrderFieldDisplay({ value: null }), "—")
	assert.equal(productionOrderFieldDisplay({ fieldname: "skip_box_sticker_print", value: 0 }), "No")
	assert.equal(productionOrderFieldDisplay({ fieldname: "dia", fieldtype: "Link", value: "IAV-88ce", display_value: "30" }), "30")
	const overview = salesSource("ProductionOrderOverview.vue")
	assert.match(overview, /\.ppo-overview__facts > div > span\s*\{/)
	assert.doesNotMatch(overview, /\.ppo-overview span\s*\{/)
})

test("F-A06 matrix uses theme surfaces and readable text; PPO header actions wrap on mobile", () => {
	const matrix = salesSource("ProductionOrderMatrix.vue")
	for (const selector of ["thead th", "tbody th"]) {
		const rule = matrix.match(new RegExp(`\\.ppo-matrix ${selector} \\{([^}]+)\\}`))[1]
		assert.match(rule, /background: var\(--erp-surface-soft\)/)
		assert.match(rule, /color: var\(--erp-text\)/)
	}
	assert.doesNotMatch(matrix, /color-mix\([^;]*white/)
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /\.ppo-page-frame :deep\(\.fabric-document-workspace__commandbar\)[\s\S]*?flex-wrap: wrap/)
	assert.match(view, /\.ppo-page-frame :deep\(\.fabric-document-workspace__domain-actions\)[\s\S]*?flex-wrap: wrap/)
	assert.match(view, /\.ppo-page-frame :deep\(\.fabric-document-workspace__domain-actions \.p-button\)[\s\S]*?flex-shrink: 0/)
	assert.match(view, /\.ppo-page-frame :deep\(\.fabric-document-workspace__domain-actions\) \{[^}]*min-width: 0/)
	assert.match(view, /\.ppo-page-frame :deep\(\.document-print-button \.p-button-label\) \{ display: inline/)
})

test("F-A08 pending preview shows only changed sizes, status changes, transfer quantities and PPO requester", async () => {
	const { productionOrderRequestRows } = await import("../src/departments/sales/productionOrderPendingRequest.js")
	assert.deepEqual(productionOrderRequestRows(null), [])
	assert.deepEqual(productionOrderRequestRows({ request_type: "quantity_ratio", changes: [
		{ size: "S", current_quantity: 10, requested_quantity: 12, current_ratio: 1, requested_ratio: 1 },
		{ size: "M", current_quantity: 20, requested_quantity: 20, current_ratio: 2, requested_ratio: 3 },
		{ size: "L", current_quantity: 5, requested_quantity: 5, current_ratio: 1, requested_ratio: 1 },
	] }), [
		{ size: "S", quantity: "10 → 12", ratio: "1 → 1" }, { size: "M", quantity: "20 → 20", ratio: "2 → 3" },
	])
	assert.deepEqual(productionOrderRequestRows({ request_type: "transfer", transfers: { S: 12 }, target_original_quantities: { S: 10 } }), [{ size: "S", quantity: "10 → 22", ratio: "—", transferred: 12 }])
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /<ProductionOrderPendingRequest :request="workspace\.pending_request"/)
	assert.match(view, /<ProductionOrderPendingRequest v-if="approvalRequest" :request="approvalRequest"/)
	const preview = salesSource("ProductionOrderPendingRequest.vue")
	for (const field of ["requested_status", "previous_status", "source_production_order", "source_status", "requested_by", "requested_user", "requested_on", "reason"]) assert.ok(preview.includes(`request.${field}`), field)
	assert.match(source("../src/components/documents/DocumentConfirmationDialog.vue"), /<slot\s*\/>/)
})

test("F-A08 approval dialogs select the matching request and rendered preview preserves reason and time", () => {
	const { productionOrderApprovalRequest } = pendingRequest
	for (const [command, request_type] of Object.entries({ approve_ppo: "ppo_approval", approve_status: "status", approve_quantity_ratio: "quantity_ratio", approve_transfer: "transfer" })) {
		const request = { request_type }
		assert.equal(productionOrderApprovalRequest(command, request), request)
		assert.equal(productionOrderApprovalRequest("delete", request), null)
		assert.equal(productionOrderApprovalRequest(command, null), null)
	}
	assert.equal(productionOrderApprovalRequest("approve_status", { request_type: "quantity_ratio" }), null)
	const preview = loadComponent(resolve("frontend/src/departments/sales/ProductionOrderPendingRequest.vue"), {
		"./productionOrderDisplay.js": productionOrderDisplay,
		"./productionOrderPendingRequest.js": pendingRequest,
		"../../components/common/DocumentLink.vue": (props) => Vue.h("a", {}, props.name),
	})
	const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
	const root = mountComponent(preview, { request: {
		request_type: "transfer", source_production_order: "PPO-SOURCE", source_status: "Item Changed", target_previous_status: "Open",
		transfers: { S: 12 }, target_original_quantities: { S: 10 }, requested_user: "sales@example.com", requested_on: "2026-10-20 19:29:17.278784", reason: "Line One\nLine Two",
	} })
	const content = text(root)
	for (const value of ["PPO-SOURCE", "Item Changed", "sales@example.com", "20-10-2026 19:29", "Line One\nLine Two", "10 → 22"]) assert.ok(content.includes(value), value)
	assert.equal(findNodes(root, (node) => node.type === "tr").length, 2)
	const empty = mountComponent(preview)
	assert.equal(findNodes(empty, (node) => node.type === "section").length, 0)
})

test("F-A09 change status excludes current status", async () => {
	const { productionOrderChangeableStatuses } = await import("../src/departments/sales/productionOrderOptions.js")
	assert.deepEqual(productionOrderChangeableStatuses("Open"), ["Item Changed", "Not Processed"])
	assert.deepEqual(productionOrderChangeableStatuses("Pending Request"), ["Open", "Item Changed", "Not Processed"])
	const dialog = salesSource("ProductionOrderActionDialog.vue")
	assert.match(dialog, /productionOrderChangeableStatuses\(props\.currentStatus\)/)
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /:current-status="workspace\.record\?\.status/)
})

test("F-A19 Lot picker requires same item and no linked PPO", async () => {
	const { productionOrderLotFilters } = await import("../src/departments/sales/productionOrderOptions.js")
	assert.deepEqual(productionOrderLotFilters("ITEM-1"), { item: "ITEM-1", production_order: ["is", "not set"] })
	const dialog = salesSource("ProductionOrderActionDialog.vue")
	assert.match(dialog, /doctype="SD YRP Lot" :filters="lotFilters"/)
	const view = salesSource("ProductionOrder.vue")
	assert.match(view, /:item="workspace\.record\?\.item/)
})

test("sales date displays use the shared DD-MM-YYYY helper", async () => {
	assert.equal(productionOrderDisplay.productionOrderFieldDisplay({ fieldname: "delivery_date", value: "2026-10-23" }), "23-10-2026")
	const history = loadComponent(resolve("frontend/src/departments/sales/ProductionOrderTransferHistory.vue"), {
		"../../components/common/DocumentLink.vue": (props) => Vue.h("a", {}, props.label),
	})
	const text = (node) => node.type === "comment" ? "" : node.text + node.children.map(text).join("")
	const content = text(mountComponent(history, { rows: [{ movement: "Added", requested_by: "a@x", requested_on: "2026-10-23 14:05:09.123", approved_on: "" }] }))
	assert.ok(content.includes("23-10-2026 14:05"), content)
	assert.ok(!content.includes("2026-10-23"))
	for (const name of ["ProductionOrder.vue", "ProductionOrderTransferHistory.vue", "PpoReport.vue", "productionOrderDisplay.js"]) {
		const code = salesSource(name)
		assert.match(code, /utils\/dateFormat\.js|reportUtils\.js/, name)
		assert.doesNotMatch(code, /function formatDate(Time)?\(/, name)
	}
	assert.match(salesSource("ProductionOrder.vue"), /formatDatesInText\(workspace\.histories\.comments\)/)
	assert.match(salesSource("PpoReport.vue"), /formatDatesInText\(order\.comments\)/)
})
