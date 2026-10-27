import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const { getWorkspacePaths, departments } = await import("../src/departments/registry.js")
const { accountsLauncherItems } = await import("../src/departments/accounts/accountsViews.js")

const layouts = JSON.parse(readFileSync(new URL("../../essdee_yrp/fixtures/yrp_ui_layout.json", import.meta.url), "utf8"))
const layout = layouts.find((row) => row.name === "Accounts")
const workspaces = JSON.parse(layout.config).experience_props.workspaces

test("Accounts shows the Merch Lot and PD Lotwise Item Profit cards before Reports", () => {
	assert.deepEqual(accountsLauncherItems().map((item) => [item.key, item.to]), [
		["debits", "/accounts/debits"],
		["purchase_invoices", "/accounts/purchase-invoices"],
		["bill_tracking", "/accounts/bill-tracking"],
		["lots", "/merch/lots"],
		["lotwise_item_profits", "/pd/lotwise-item-profits"],
		["reports", "/accounts/reports"],
	])
	assert.deepEqual([...workspaces].sort(), accountsLauncherItems().map((item) => item.key).sort(), "the shipped layout lists every card")
})

test("the Accounts layout opens only the combined Lot and Lotwise Item Profit pages", () => {
	const paths = getWorkspacePaths(departments.find((item) => item.key === "accounts"))

	assert.deepEqual(paths.lots, ["/merch/lots"])
	assert.deepEqual(paths.lotwise_item_profits, ["/pd/lotwise-item-profits"])
	assert.equal(paths.item_production_details, undefined)
})
