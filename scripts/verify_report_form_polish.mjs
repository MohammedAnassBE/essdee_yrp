#!/usr/bin/env node

import { readFileSync } from "node:fs"

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const assert = (condition, message) => {
	if (!condition) throw new Error(message)
}

const cuttingReports = read("../frontend/src/departments/CuttingReports.vue")
const stockBalanceReport = read("../frontend/src/components/reports/StockBalanceReport.vue")
const cuttingOrderEditor = read("../frontend/src/departments/cutting/order/CuttingOrderEditor.vue")

assert(
	cuttingReports.includes('class="report-tabs__mobile"')
		&& cuttingReports.includes(':options="visibleTabs"')
		&& cuttingReports.includes("@media (max-width: 700px)"),
	"Cutting Reports has no discoverable compact report selector below 700px",
)
assert(
	stockBalanceReport.includes('class="stock-link-filter"')
		&& stockBalanceReport.includes('class="stock-advanced"')
		&& stockBalanceReport.includes('const advancedOpen = ref(')
		&& stockBalanceReport.includes("@media (max-width: 430px)")
		&& stockBalanceReport.includes("grid-template-columns: minmax(0, 1fr);"),
	"Stock Balance optional filters do not collapse into a readable mobile disclosure below 430px",
)
assert(
	cuttingOrderEditor.includes('placeholder="Item filled from detail"')
		&& cuttingOrderEditor.includes('placeholder="Select Cutting Location"'),
	"New Cutting Orders do not explain their blank dependent fields",
)

console.log("report and form polish contracts: OK")
