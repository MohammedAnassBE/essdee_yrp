import assert from "node:assert/strict"
import { readFileSync, readdirSync } from "node:fs"

import {
	PLANNING_ROUTES, PLANNING_WORKSPACES, activeReportGroup, isCurrentRecordRequest,
	visiblePlanningWorkspaces, visibleReportGroups,
	PLANNING_PRODUCTION_REPORTS, visibleProductionReports,
} from "../frontend/src/departments/planning/planningViews.js"
import { lotTabs } from "../frontend/src/departments/planning/lot/lotViews.js"
import { editTabFor } from "../frontend/src/departments/planning/lot/lotEditor.js"
import { getLockedRedirect } from "../frontend/src/router/departmentLock.js"
import { departments } from "../frontend/src/departments/registry.js"
import { CLOSE_REASONS, bulkCloseFilterHint, closeReasonHint, pendingSummary, sortedWorkOrders } from "../frontend/src/departments/planning/reports/workOrderBulkClose.js"
import {
	workOrderDefaults, workOrderHint, workOrderRequest, percentageHint, pairedDateHint,
	mergePastedValues, populatedFilters,
	addProcess, moveProcess, stockHint, progressTotals, progressCellLink, progressCellValue, sizeMatrixColumns,
	quantityHint, monthWiseHint, quantityDeepLink,
} from "../frontend/src/departments/planning/reports/productionReportFilters.js"

const read = (path) => readFileSync(path, "utf8")
const department = (path) => read(`frontend/src/departments/${path}`)
const keys = ["cutting_plans", "sewing_plans", "finishing_plans", "lots", "production_orders", "work_orders", "reports"]
assert.deepEqual(PLANNING_WORKSPACES.map((item) => item.key), keys)
assert.ok(PLANNING_WORKSPACES.every((item) => item.to.startsWith("/planning/")))
assert.deepEqual(visiblePlanningWorkspaces({ lots: { can_read: true }, reports: { can_read: false } }).map((item) => item.key), ["lots"])
assert.deepEqual(visiblePlanningWorkspaces(), [])
assert.deepEqual(visiblePlanningWorkspaces({ reports: { can_read: true } }).map((item) => item.key), ["reports"])
assert.deepEqual(visibleReportGroups({ cutting: true, finishing: true }).map((group) => group.value), ["cutting", "finishing"])
const groups = visibleReportGroups({ cutting: true, finishing: true })
assert.equal(activeReportGroup(groups, "sewing"), "cutting")
assert.equal(activeReportGroup(groups, "finishing"), "finishing")
assert.equal(activeReportGroup([], "cutting"), "")
assert.equal(isCurrentRecordRequest("A", "A", 2, 2), true)
assert.equal(isCurrentRecordRequest("A", "B", 2, 2), false)
assert.equal(isCurrentRecordRequest("A", "A", 1, 2), false)

const router = read("frontend/src/router/index.js")
assert.equal(new Set(Object.values(PLANNING_ROUTES)).size, Object.keys(PLANNING_ROUTES).length)
for (const key of Object.keys(PLANNING_ROUTES)) assert.ok(router.includes(`PLANNING_ROUTES.${key}`), key)
for (const item of PLANNING_WORKSPACES) assert.ok(router.includes(`"${item.to}"`), item.to)
assert.ok(router.includes('{ path: "/planning/reports", name: PLANNING_ROUTES.reports, component: PlanningReports }'))
assert.ok(router.includes('const PlanningReports = () => import("../departments/planning/PlanningReports.vue")'))
assert.equal(PLANNING_ROUTES.reports, "planning-reports")
for (const file of readdirSync("frontend/src/departments/planning", { recursive: true, withFileTypes: true })) {
	if (!file.isFile()) continue
	const parent = file.parentPath || file.path
	assert.doesNotMatch(read(`${parent}/${file.name}`), /departments\/purchase|purchase\/lot|api\/purchase\.js|PURCHASE_ROUTES/)
}

const list = department("planning/lot/LotsList.vue")
assert.doesNotMatch(list, /New Lot|lotNew/)
assert.ok(list.includes('back-to="/planning"'))
assert.ok(list.includes("getPlanningCapabilities())?.sections?.lots"))
assert.ok(list.includes('initial-status="Open"'))
assert.ok(list.includes('severity="warn"'))
assert.match(list, /\.planning-lots-page__loading\s*\{[^}]*gap: var\(--erp-space-4\);[^}]*padding: var\(--erp-space-3\) 0;/)
const editor = department("planning/lot/useLotEditor.js")
const actionsSource = editor.match(/const editorActions = computed\(\(\) => \[[\s\S]*?\n\t\]\)/)?.[0]
assert.ok(actionsSource, "Planning editor actions must be available for permission regression checks")
const actionsFor = new Function("computed", "record", "loadError", "isNew", "acting", "canSave", "cancel", "save", `${actionsSource}; return editorActions`)
for (const [record, loadError, expected] of [
	[null, "", ["cancel"]],
	[null, "PermissionError", ["cancel"]],
	[{ name: "LOT-1" }, "PermissionError", ["cancel"]],
	[{ name: "LOT-1" }, "", ["cancel", "save"]],
]) {
	const actions = actionsFor((get) => get(), { value: record }, { value: loadError }, false,
		{ value: "" }, { value: false }, () => {}, () => {})
	assert.deepEqual(actions.map((action) => action.key), expected)
}
assert.ok(department("planning/lot/LotPage.vue").includes("permissions?.can_write"))
const fixture = JSON.parse(read("essdee_yrp/fixtures/yrp_ui_layout.json"))
const planningLayout = fixture.find((row) => row.experience_key === "planning")
assert.equal(planningLayout.name, "Production Planner")
assert.deepEqual(JSON.parse(planningLayout.config).experience_props.workspaces, keys)
assert.ok(read("essdee_yrp/hooks.py").includes('"planning": ["workspaces"]'))
const planning = departments.find((item) => item.key === "planning")
assert.deepEqual(getLockedRedirect("/", planning), { path: "/planning", replace: true })
assert.equal(getLockedRedirect("/planning/lots/X", planning), undefined)
assert.equal(typeof lotTabs, "function")
assert.equal(typeof editTabFor, "function")

const landing = department("Planning.vue")
assert.ok(landing.includes('title="Planning" :show-title="false" flat inline-navigation'))
assert.ok(landing.includes('empty-text="No permitted Planning workspaces"'))
assert.ok(landing.includes(':skeleton-count="7"'))
assert.ok(landing.includes('@retry="load"'))
assert.ok(landing.includes(':loading="loading"'))
assert.doesNotMatch(landing, /WorkspacePlaceholder|full-width/)
const defaults = {
	"CuttingPlans.vue": ["/cutting", "Cutting", "cutting-plan", "cutting-plan-new"],
	"CuttingPlanEditorPage.vue": ["/cutting/plans", "Cutting Plans", "cutting-plan"],
	"CuttingPlan.vue": ["/cutting/plans", "Cutting Plans"],
	"finishing/FinishingPlans.vue": ["/finishing", "Finishing", "finishing-plan"],
	"finishing/FinishingPlan.vue": ["/finishing/plans", "Finishing Plans"],
	"sales/SalesSection.vue": ["/sales", "Sales", "sales-production-order", "sales-production-order-new"],
	"sales/ProductionOrders.vue": ["sales-production-order", "sales-production-order-new"],
	"sales/ProductionOrder.vue": ["/sales/production-orders", "Production Orders", "sales-production-order", "sales-production-order-edit", "sales-production-orders"],
	"sales/ProductionOrderEditorPage.vue": ["/sales/production-orders", "Production Orders", "sales-production-order"],
}
for (const [file, values] of Object.entries(defaults)) {
	for (const value of values) assert.ok(department(file).includes(`default: "${value}"`), `${file}: ${value}`)
}
const sewing = department("sewing/SewingWorkspaceShell.vue")
assert.ok(sewing.includes('props.backTo || (props.section'))
assert.ok(sewing.includes('path: "/sewing", query: supplier.value'))
assert.ok(sewing.includes('props.backLabel || (props.section ? "Sewing" : "Workspaces")'))
assert.ok(sewing.includes('v-if="!embedded" class="sewing-workspace-shell__title"'))
assert.ok(sewing.includes("'sewing-workspace-shell__header--embedded': embedded"))
assert.match(sewing, /\.sewing-workspace-shell__header--embedded \{ justify-content: flex-end; \}/)
assert.ok(sewing.includes('<SewingUnitPicker v-if="section !== \'attendance\'" />'))
assert.ok(sewing.includes("Select a Sewing Unit to view {{ title }}."))
for (const file of ["CuttingReports.vue", "finishing/FinishingReports.vue", "sewing/SewingReports.vue", "sewing/SewingWorkspaceShell.vue"]) {
	assert.ok(department(file).includes("embedded: { type: Boolean, default: false }"), file)
	assert.ok(department(file).includes(':embedded="embedded"'), file)
}
const departmentPage = read("frontend/src/components/DepartmentPage.vue")
assert.ok(departmentPage.includes("embedded: { type: Boolean, default: false }"))
assert.ok(departmentPage.includes('<div v-if="embedded" class="department-page-embedded"><slot /></div>'))
assert.match(departmentPage, /<main\s+v-else/)
assert.ok(departmentPage.includes("inline: computed(() => props.inlineNavigation && !props.embedded)"))
assert.ok(departmentPage.includes("!isLockedExit(backTo)"))
for (const inlineNavigation of [false, true]) {
	for (const embedded of [false, true]) {
		const expression = departmentPage.match(/inline: computed\(\(\) => (.*?)\),/)[1]
		assert.equal(new Function("props", `return ${expression}`)({ inlineNavigation, embedded }), inlineNavigation && !embedded)
	}
}

const planningReports = department("planning/PlanningReports.vue")
assert.equal((planningReports.match(/<InlinePageNavigation\b/g) || []).length, 1)
assert.ok(planningReports.includes('back-to="/planning" back-label="Planning"'))
assert.ok(planningReports.includes(':show-title="false" flat full-width inline-navigation'))
assert.ok(planningReports.includes('<h1 id="planning-reports-title">Reports</h1>'))
assert.ok(planningReports.includes('<SelectButton v-if="groups.length > 1"'))
assert.ok(planningReports.includes(':options="groups"'))
assert.ok(planningReports.includes(':allow-empty="false"'))
assert.ok(planningReports.includes("groups.value = visibleReportGroups(reports?.groups)"))
assert.ok(planningReports.includes("production.value = reports?.production || {}"))
const groupSource = planningReports.match(/const group = computed\(\{[\s\S]*?\n\}\)/)[0]
const reportRoute = { query: { group: "finishing", report: "packing-dpr", tab: "dpr", supplier: "UNIT-1" } }
let replacement
const groupModel = new Function("computed", "activeReportGroup", "groups", "route", "router", `${groupSource}; return group`)(
	(value) => value, activeReportGroup, { value: groups }, reportRoute, { replace: (value) => { replacement = value } },
)
assert.equal(groupModel.get(), "finishing")
for (const requested of [undefined, "invalid", ["cutting", "finishing"]]) {
	reportRoute.query.group = requested
	assert.equal(groupModel.get(), "cutting")
}
groupModel.set("cutting")
assert.deepEqual(replacement, { query: { group: "cutting" } })
assert.ok(planningReports.includes('<Skeleton height="76px" /><Skeleton height="420px" />'))
assert.ok(planningReports.includes('<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />'))
assert.ok(planningReports.includes('<Message v-else-if="!groups.length" severity="warn" :closable="false">You do not have permission to view Planning reports.</Message>'))
const loadSource = planningReports.match(/async function load\(\) \{[\s\S]*?\n\}/)[0]
const loadingState = { value: false }
const errorState = { value: "" }
const groupState = { value: [] }
let resolveCapabilities
let rejectCapabilities
const productionState = { value: {} }
const loadReports = new Function("loading", "loadError", "groups", "production", "visibleReportGroups", "getPlanningCapabilities", `${loadSource}; return load`)(
	loadingState, errorState, groupState, productionState, visibleReportGroups,
	() => new Promise((resolve, reject) => { resolveCapabilities = resolve; rejectCapabilities = reject }),
)
let pendingLoad = loadReports()
assert.equal(loadingState.value, true)
resolveCapabilities({ sections: { reports: { groups: { sewing: true, cutting: false } } } })
await pendingLoad
assert.deepEqual(groupState.value, [{ value: "sewing", label: "Sewing" }])
assert.equal(loadingState.value, false)
pendingLoad = loadReports()
rejectCapabilities(new Error("Permission service unavailable"))
await pendingLoad
assert.equal(errorState.value, "Permission service unavailable")
assert.deepEqual(groupState.value, [])
assert.equal(loadingState.value, false)
pendingLoad = loadReports()
assert.equal(errorState.value, "")
resolveCapabilities({ sections: {} })
await pendingLoad
assert.deepEqual(groupState.value, [])
assert.equal(loadingState.value, false)
for (const [component, value, path] of [
	["CuttingReports", "cutting", "../CuttingReports.vue"],
	["SewingReports", "sewing", "../sewing/SewingReports.vue"],
	["FinishingReports", "finishing", "../finishing/FinishingReports.vue"],
]) {
	assert.ok(planningReports.includes(`<${component} v-else-if="group === '${value}'" embedded :key="group" />`))
	assert.ok(planningReports.includes(`const ${component} = defineAsyncComponent(() => import("${path}"))`))
}
assert.doesNotMatch(planningReports, /padding-inline|max-width: none|margin-inline/)
assert.match(planningReports, /position: sticky; top: var\(--erp-shell-header-height\); z-index: var\(--erp-layer-sticky\); background: var\(--erp-bg\)/)
assert.ok(planningReports.includes("padding: 0 0 var(--erp-space-5)"))
assert.ok(planningReports.includes(":style=\"{ '--planning-reports-sticky-offset': `${headerHeight}px` }\""))
assert.ok(planningReports.includes('ref="header" class="planning-reports__header"'))
assert.ok(planningReports.includes("headerHeight.value = header.value.getBoundingClientRect().height"))
assert.ok(planningReports.includes("new ResizeObserver(updateHeaderHeight)"))
assert.ok(planningReports.includes("headerObserver.observe(header.value)"))
assert.ok(planningReports.includes("onBeforeUnmount(() => headerObserver?.disconnect())"))
const cuttingReports = department("CuttingReports.vue")
assert.ok(cuttingReports.includes(":class=\"{ 'cutting-reports--embedded': embedded }\""))
assert.match(cuttingReports, /\.cutting-reports--embedded \.report-tabs__list,\s*\.cutting-reports--embedded \.report-tabs__mobile\s*\{\s*top: calc\(var\(--erp-shell-header-height\) \+ var\(--planning-reports-sticky-offset, 0px\)\);\s*\}/)
assert.match(cuttingReports, /\.report-tabs__list\s*\{[^}]*top: var\(--erp-shell-header-height\);/)
assert.match(cuttingReports, /@media \(max-width: 700px\)\s*\{\s*\.report-tabs__mobile\s*\{[^}]*top: var\(--erp-shell-header-height\);/)
for (const file of ["sewing/SewingReportsWorkspace.vue", "finishing/FinishingReports.vue"]) {
	assert.doesNotMatch(department(file), /position:\s*sticky/, file)
}
for (const file of ["CuttingReports.vue", "sewing/SewingReportsWorkspace.vue", "finishing/FinishingReports.vue"]) {
	assert.ok(department(file).includes("max-width: 700px"), file)
}
assert.ok(department("sales/ProductionOrder.vue").includes("if (!capability?.allowed) return []"))
assert.deepEqual(PLANNING_PRODUCTION_REPORTS.map((report) => report.key), ["work_order", "dispatch_percentage", "work_order_pending", "finishing_plan", "inward_quantity", "inhouse_quantity", "month_wise_detail", "process_pending", "size_wise_stock", "colour_wise_diff", "work_in_progress", "work_order_bulk_close"])
assert.deepEqual(visibleProductionReports(), [])
assert.deepEqual(visibleProductionReports({ work_order: { can_read: false }, finishing_plan: { can_read: true } }).map((report) => report.key), ["finishing_plan"])
assert.deepEqual(visibleReportGroups({ production: true }), [{ value: "production", label: "Production / WIP" }])
assert.ok(planningReports.includes('<PlanningProductionReports v-else-if="group === \'production\'" :reports="production" />'))
const productionPage = department("planning/reports/PlanningProductionReports.vue")
assert.ok(productionPage.includes("visibleProductionReports(props.reports)"))
assert.doesNotMatch(productionPage, /getPlanningCapabilities|DepartmentPage/)
assert.ok(productionPage.includes('import("../../finishing/reports/FinishingPlanReport.vue")'))
assert.ok(productionPage.includes('provide(pageNavigationKey, { ...navigation, inline: computed(() => false) })'))
assert.ok(productionPage.includes("top: calc(var(--erp-shell-header-height) + var(--planning-reports-sticky-offset, 0px))"))
assert.ok(productionPage.includes("max-width: 700px"))
const activeSource = productionPage.match(/const active = computed\(\{[\s\S]*?\n\}\)/)[0]
const productionTabs = { value: visibleProductionReports({ dispatch_percentage: { can_read: true }, finishing_plan: { can_read: true } }) }
const productionRoute = { query: { group: "production", report: "finishing-plan" } }
const activeProduction = new Function("computed", "tabs", "route", "router", activeSource + "; return active")(
	(value) => value, productionTabs, productionRoute, { replace: (value) => { replacement = value } },
)
assert.equal(activeProduction.get(), "finishing-plan")
for (const request of ["work-order", "invalid", undefined, ["finishing-plan"]]) {
	productionRoute.query.report = request
	assert.equal(activeProduction.get(), "dispatch-percentage")
}
activeProduction.set("finishing-plan")
assert.equal(replacement.query.group, "production")
assert.equal(replacement.query.report, "finishing-plan")
productionTabs.value = []
assert.equal(activeProduction.get(), undefined)
const reportProvider = read("essdee_yrp/web_reports.py")
for (const [file, key] of [
	["WorkOrderReport", "planning-work-order"],
	["DispatchPercentageReport", "planning-dispatch-percentage"],
	["WorkOrderPendingReport", "planning-work-order-pending"],
]) {
	const source = department("planning/reports/" + file + ".vue")
	assert.ok(source.includes("ReportShell"))
	assert.ok(source.includes('useWebReport({ reportKey: "' + key + '" })'))
	assert.ok(reportProvider.includes('key="' + key + '"'))
	for (const contract of [':loading="loading"', ':generated="generated"', ':error="layoutError || reportError"', 'empty-title="No rows for these filters."', 'copyable', 'ReportColumnPicker', '@click="downloadCsv"', 'Boolean(hint)']) assert.ok(source.includes(contract), file + ": " + contract)
}
const workDefaults = workOrderDefaults("2026-03-31")
assert.equal(workDefaults.from_date, "2026-02-28")
assert.equal(workOrderDefaults("2024-03-31").from_date, "2024-02-29")
assert.equal(workOrderDefaults("2026-01-15").from_date, "2025-12-15")
assert.equal(workDefaults.to_date, "2026-03-31")
assert.equal(workDefaults.based_on, "Date")
assert.equal(workOrderHint(workDefaults), "")
assert.ok(workOrderHint({ ...workDefaults, from_date: "" }))
assert.ok(workOrderHint({ ...workDefaults, to_date: "" }))
assert.equal(workOrderHint({ ...workDefaults, based_on: "WO Status", from_date: "", to_date: "" }), "")
const workOrderFilters = { ...workDefaults, supplier: "SUP-1", process_name: "PROC-1", item: "ITEM-1", lot: "LOT-1", status: "Close" }
assert.deepEqual(workOrderRequest(workOrderFilters), {
	based_on: "Date", from_date: "2026-02-28", to_date: "2026-03-31", supplier: "SUP-1", process_name: "PROC-1", item: "ITEM-1", lot: "LOT-1",
})
assert.deepEqual(workOrderRequest({ ...workOrderFilters, based_on: "WO Status" }), {
	based_on: "WO Status", supplier: "SUP-1", process_name: "PROC-1", item: "ITEM-1", lot: "LOT-1", status: "Close",
})
for (const value of [null, undefined, 0, -1, 0.5, 101, NaN, "75"]) assert.ok(percentageHint(value))
for (const value of [1, 75, 99.5, 100]) assert.equal(percentageHint(value), "")
assert.deepEqual(mergePastedValues(["LOT-1"], " LOT-2,LOT-1\nLOT-3\r\n, LOT-2 "), ["LOT-1", "LOT-2", "LOT-3"])
assert.deepEqual(mergePastedValues(["ITEM-1"], "ITEM-2, ITEM-1"), ["ITEM-1", "ITEM-2"])
const dispatch = department("planning/reports/DispatchPercentageReport.vue")
assert.ok(dispatch.includes("percentage: 75"))
assert.ok(dispatch.includes('pasteTarget.value = "Lot"'))
assert.ok(dispatch.includes('pasteTarget.value === "Item" ? "item" : "lot"'))
assert.equal(pairedDateHint({ from_date: "", to_date: "" }), "")
assert.ok(pairedDateHint({ from_date: "2026-10-01", to_date: "" }))
assert.ok(pairedDateHint({ from_date: "", to_date: "2026-10-15" }))
assert.equal(pairedDateHint({ from_date: "2026-10-01", to_date: "2026-10-15" }), "")
assert.ok(pairedDateHint({ from_date: "2026-10-15", to_date: "2026-10-01" }))
const pending = department("planning/reports/WorkOrderPendingReport.vue")
assert.equal((pending.match(/<AsyncLinkMultiSelect\b/g) || []).length, 6)
assert.ok(pending.includes("['', 'Open', 'Close Request', 'Close']"))
assert.ok(pending.includes('variant_of: [\'is\', \'set\']'))
assert.ok(pending.includes("reportSummary || []"))
assert.ok(pending.includes("#metrics"))
assert.deepEqual(populatedFilters({ lot: [], item: ["ITEM-1"], from_date: "", percentage: 75 }), { item: ["ITEM-1"], percentage: 75 })
assert.deepEqual(visibleProductionReports({ inward_quantity: { can_read: true }, inhouse_quantity: { can_read: false }, month_wise_detail: { can_read: true }, process_pending: { can_read: true } }).map((report) => report.key), ["inward_quantity", "month_wise_detail", "process_pending"])
for (const filters of [{ lot: "", process: "" }, { lot: "L", process: "" }, { lot: "", process: "P" }]) assert.ok(quantityHint(filters))
assert.equal(quantityHint({ lot: "L", process: "P" }), "")
assert.ok(monthWiseHint({ lot: [], item: [], from_date: "", to_date: "" }))
assert.ok(monthWiseHint({ lot: ["L"], item: [], from_date: "2026-01-01", to_date: "" }))
assert.equal(monthWiseHint({ lot: [], item: ["A"], from_date: "2025-01-01", to_date: "2026-01-01" }), "")
assert.deepEqual(quantityDeepLink({ group: "production", report: "inhouse-quantity", lot: "L", process: "P" }), { lot: "L", process: "P" })
assert.deepEqual(quantityDeepLink({ lot: ["L"], process: undefined }), { lot: "", process: "" })
const inhouse = department("planning/reports/InhouseQuantityReport.vue")
for (const [file, key] of [["InwardQuantityReport", "inward-quantity"], ["InhouseQuantityReport", "inhouse-quantity"], ["MonthWiseDetailReport", "month-wise-detail"], ["ProcessPendingReport", "process-pending"]]) {
	const source = department(`planning/reports/${file}.vue`)
	assert.ok(source.includes(`useWebReport({ reportKey: "planning-${key}" })`))
	assert.ok(reportProvider.includes(`key="planning-${key}"`))
	for (const contract of ["ReportShell", ':loading="loading"', ':generated="generated"', ':error="reportError"', 'empty-title="No rows for these filters."', 'Boolean(hint)', '@click="downloadCsv"']) assert.ok(source.includes(contract), `${file}: ${contract}`)
}
assert.ok(inhouse.includes("quantityDeepLink(route.query)"))
assert.ok(inhouse.includes("if (!quantityHint(values)) generate()"))
assert.ok(inhouse.includes("{ immediate: true }"))
assert.ok(inhouse.includes(':cell-tone="(column, row) => row.tones?.[column.fieldname]'))
const processPending = department("planning/reports/ProcessPendingReport.vue")
assert.ok(processPending.includes('lot_status: "Open"'))
assert.ok(processPending.includes('mergePastedValues(filters[key], pastedText.value)'))
assert.ok(processPending.includes(':placeholder="defaultProcess'))
assert.ok(processPending.includes('process_pending.get_defaults'))
assert.ok(processPending.includes("'/planning/lots/' + encodeURIComponent(row.lot)"))
assert.ok(processPending.includes("#metrics"))
assert.ok(processPending.includes('<WorkspaceLoadError v-if="defaultsError" class="process-defaults-error" title="Default process unavailable" :message="defaultsError" @retry="loadDefaults" />'))
assert.ok(processPending.includes('import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"'))
assert.doesNotMatch(processPending, /<small v-if="defaultsError"/)
const defaultsLoader = processPending.match(/async function loadDefaults\(\) \{[\s\S]*?\n\}/)[0]
const defaultProcessState = { value: "" }
const defaultsErrorState = { value: "" }
let defaultsAttempt = 0
const retryDefaults = new Function("defaultProcess", "defaultsError", "callMethod", `${defaultsLoader}; return loadDefaults`)(defaultProcessState, defaultsErrorState, async () => {
	if (!defaultsAttempt++) throw new Error("Defaults unavailable")
	return { process: "Stitching" }
})
await retryDefaults()
assert.equal(defaultsErrorState.value, "Defaults unavailable")
await retryDefaults()
assert.equal(defaultsErrorState.value, "")
assert.equal(defaultProcessState.value, "Stitching")
assert.ok(department("planning/reports/MonthWiseDetailReport.vue").includes('v-for="group in itemGroups"'))
for (const tone of ["success-soft", "danger-soft", "warning-soft"]) assert.ok(department("planning/reports/PlanningReportTable.vue").includes(`var(--erp-${tone})`))
pendingLoad = loadReports()
resolveCapabilities({ sections: { reports: { groups: { production: true }, production: { work_order: { can_read: true } } } } })
await pendingLoad
assert.deepEqual(productionState.value, { work_order: { can_read: true } })
assert.deepEqual(groupState.value, [{ value: "production", label: "Production / WIP" }])
pendingLoad = loadReports()
rejectCapabilities(new Error("Unavailable"))
await pendingLoad
assert.deepEqual(productionState.value, {})
assert.deepEqual(groupState.value, [])
assert.deepEqual(visibleProductionReports({ work_order_bulk_close: { can_read: true, can_write: false } }).map((report) => report.key), ["work_order_bulk_close"])
assert.deepEqual(visibleProductionReports({ work_order_bulk_close: { can_write: true } }), [])
assert.ok(productionPage.includes('work_order_bulk_close: defineAsyncComponent(() => import("./WorkOrderBulkClose.vue"))'))
assert.ok(productionPage.includes("currentTab.key === 'work_order_bulk_close' ? { permissions: reports[currentTab.key] } : {}"))
const bulkClose = department("planning/reports/WorkOrderBulkClose.vue")
assert.match(bulkClose, /import \{ getOpenWorkOrders, getWorkOrderCloseDetails, closeWorkOrders \} from "\.\.\/\.\.\/\.\.\/api\/planning.js"/)
assert.doesNotMatch(bulkClose, /callMethod|fetch\(|useWebReport|work_order_close\.|essdee_yrp\./)
assert.ok(bulkClose.includes('generate-label="Load Work Orders"'))
assert.ok(bulkClose.includes(':generate-disabled="Boolean(filterHint) || busy"'))
assert.ok(bulkClose.includes('v-if="permissions.can_write" :label="`Close Selected (${selectedNames.length})`"'))
assert.ok(bulkClose.includes(':disabled="!selectedNames.length || loading || busy"'))
for (const column of ["Work Order", "WO Date", "Item", "Lot", "Process", "Delivered", "Received", "Difference"]) assert.ok(bulkClose.includes(column))
assert.ok(bulkClose.includes("'/planning/work-orders/' + encodeURIComponent(row.name)"))
assert.ok(bulkClose.includes(':aria-sort="dateSort'))
assert.ok(bulkClose.includes('empty-title="No open Work Orders for this supplier and filters."'))
assert.ok(bulkClose.includes(':groups="pendingGroups" mode="summary"'))
assert.ok(bulkClose.includes(':groups="recut.items"'))
assert.ok(bulkClose.includes('v-if="details.debits?.length"'))
assert.ok(bulkClose.includes('v-if="closeValues.close_reason === \'Others\'"'))
assert.ok(bulkClose.includes('aria-label="Other Reason" required'))
assert.ok(bulkClose.includes('aria-label="Remarks"'))
assert.ok(bulkClose.includes('<DocumentConfirmationDialog'))
assert.ok(bulkClose.includes('<DocumentErrorDialog :message="actionError"'))
assert.ok(read("frontend/src/components/reports/ReportShell.vue").includes('generateLabel: { type: String, default: "Generate" }'))
assert.ok(read("frontend/src/departments/cutting/reports/AsyncLinkMultiSelect.vue").includes('disabled: { type: Boolean, default: false }'))
const deskBulkClose = read("essdee_yrp/essdee_yrp/page/work_order_bulk_close/work_order_bulk_close.js")
const deskReasons = JSON.parse(deskBulkClose.match(/fieldname: "close_reason",[\s\S]*?options:\s*("[^"\n]*")/)[1]).split("\n")
assert.deepEqual(CLOSE_REASONS, deskReasons)
assert.ok(bulkCloseFilterHint({ supplier: "" }))
assert.ok(bulkCloseFilterHint({ supplier: "S", wo_from_date: "2026-10-15", wo_to_date: "2026-10-01" }))
for (const dates of [{}, { wo_from_date: "2026-10-15" }, { wo_to_date: "2026-10-15" }, { wo_from_date: "2026-10-15", wo_to_date: "2026-10-15" }]) assert.equal(bulkCloseFilterHint({ supplier: "S", ...dates }), "")
assert.ok(closeReasonHint({ close_reason: "" }))
assert.ok(closeReasonHint({ close_reason: "Others", close_other_reason: "  " }))
assert.equal(closeReasonHint({ close_reason: "Others", close_other_reason: "Factory stopped" }), "")
assert.equal(closeReasonHint({ close_reason: "NA" }), "")
const unsortedOrders = [{ name: "WO-2", wo_date: "2026-10-15" }, { name: "WO-1", wo_date: "2026-10-01" }, { name: "WO-3", wo_date: "2026-10-15" }]
assert.deepEqual(sortedWorkOrders(unsortedOrders, "asc").map((row) => row.name), ["WO-1", "WO-2", "WO-3"])
assert.deepEqual(sortedWorkOrders(unsortedOrders, "desc").map((row) => row.name), ["WO-3", "WO-2", "WO-1"])
assert.equal(unsortedOrders[0].name, "WO-2")
const summaryFixture = [{ primary_attribute_values: ["S", "M"], items: [
	{ name: "Pending", values: { S: { qty: 10, delivered: 8, received: 3 }, M: { qty: 20, delivered: 12, received: 5 } } },
	{ name: "Received", values: { S: { qty: 10, delivered: 10, received: 10 } } },
] }, { items: [{ values: { default: { delivered: 1, received: 2 } } }] }]
const pendingGroups = pendingSummary(summaryFixture)
assert.equal(pendingGroups.length, 1)
assert.deepEqual(pendingGroups[0].items.map((item) => [item.name, item.total_qty, item.total_delivered, item.total_received]), [["Pending", 30, 20, 8]])
assert.equal(summaryFixture[0].items.length, 2)
assert.equal(summaryFixture[0].items[0].total_qty, undefined)

const planningApi = read("frontend/src/api/planning.js")
const apiRequests = []
const api = new Function("callMethod", planningApi.replace(/^import .*$/gm, "").replaceAll("export function", "function") + "; return { getOpenWorkOrders, getWorkOrderCloseDetails, closeWorkOrders }")((...args) => { apiRequests.push(args); return Promise.resolve({}) })
await api.getOpenWorkOrders({ supplier: "S", lot: ["L"], item: ["I"] })
await api.getWorkOrderCloseDetails("WO-1")
await api.closeWorkOrders(["WO-1"], { close_reason: "NA", close_remarks: "Checked" })
assert.deepEqual(apiRequests, [
	["essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close.get_open_work_orders", { supplier: "S", lot: ["L"], item: ["I"] }],
	["essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close.get_work_order_close_details", { work_order: "WO-1" }],
	["essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close.close_work_orders", { work_orders: ["WO-1"], close_reason: "NA", close_remarks: "Checked" }],
])

const setupSource = bulkClose.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, "")
const mockedComputed = (getter) => ({ get value() { return getter() } })
let closeCalls = 0
let listCalls = 0
let failClose = true
const notifications = []
const closePermissions = { can_write: true }
const createBulkTool = new Function("computed", "onBeforeUnmount", "reactive", "ref", "watch", "defineProps", "useToast", "getOpenWorkOrders", "getWorkOrderCloseDetails", "closeWorkOrders", "CLOSE_REASONS", "bulkCloseFilterHint", "closeReasonHint", "pendingSummary", "sortedWorkOrders", setupSource + "; return { filters, rows, selection, selectedNames, selectAll, loadWorkOrders, openCloseDialog, requestConfirmation, confirmClose, closeValues, closeNames, closeVisible, confirmVisible, actionError, busy }")
const bulkTool = createBulkTool(mockedComputed, () => {}, (value) => value, (value) => ({ value }), () => {}, () => ({ permissions: closePermissions }), () => ({ add: (value) => notifications.push(value) }), async () => { listCalls++; return unsortedOrders }, async () => ({}), async (names, values) => {
	closeCalls++
	assert.deepEqual(names, ["WO-3", "WO-2", "WO-1"])
	assert.equal(values.close_reason, "NA")
	if (failClose) throw new Error("Stock dimensions do not match")
	return { results: [{ work_order: "WO-1", open_status: "Close" }, { work_order: "WO-2", open_status: "Close Request" }] }
}, CLOSE_REASONS, bulkCloseFilterHint, closeReasonHint, pendingSummary, sortedWorkOrders)
await bulkTool.loadWorkOrders()
assert.equal(listCalls, 0)
bulkTool.filters.supplier = "S"
await bulkTool.loadWorkOrders()
assert.equal(listCalls, 1)
bulkTool.selection.value = ["UNLISTED"]
bulkTool.selectAll(true)
assert.deepEqual(bulkTool.selection.value, ["WO-3", "WO-2", "WO-1"])
bulkTool.selectAll(false)
bulkTool.openCloseDialog()
assert.equal(bulkTool.closeVisible.value, false)
bulkTool.selectAll(true)
closePermissions.can_write = false
bulkTool.openCloseDialog()
assert.equal(bulkTool.closeVisible.value, false)
closePermissions.can_write = true
bulkTool.openCloseDialog()
bulkTool.requestConfirmation()
assert.equal(bulkTool.confirmVisible.value, false)
bulkTool.closeValues.close_reason = "NA"
await bulkTool.confirmClose()
assert.equal(closeCalls, 0, "Closing requires the explicit confirmation dialog")
bulkTool.requestConfirmation()
await bulkTool.confirmClose()
assert.equal(closeCalls, 1)
assert.equal(bulkTool.actionError.value, "Stock dimensions do not match")
assert.deepEqual(bulkTool.selection.value, ["WO-3", "WO-2", "WO-1"])
assert.equal(bulkTool.rows.value.length, 3)
assert.equal(listCalls, 1)
assert.deepEqual(notifications, [])
failClose = false
bulkTool.requestConfirmation()
await bulkTool.confirmClose()
assert.equal(closeCalls, 2)
assert.equal(listCalls, 2)
assert.deepEqual(bulkTool.selection.value, [])
assert.deepEqual(notifications.map(({ summary, detail }) => [summary, detail]), [["WO-1", "Close"], ["WO-2", "Close Request"]])
assert.equal(bulkTool.closeVisible.value, false)
assert.equal(bulkTool.busy.value, false)
console.log("Planning bulk close assertions passed (C1–C9)")
console.log("Planning views assertions passed")

assert.deepEqual(addProcess(["Print"], "Wash"), ["Print", "Wash"])
assert.deepEqual(addProcess(["Print"], "Print"), ["Print"])
assert.deepEqual(moveProcess(["Print", "Wash", "Pack"], 1, -1), ["Wash", "Print", "Pack"])
assert.deepEqual(moveProcess(["Print", "Wash", "Pack"], 1, 1), ["Print", "Pack", "Wash"])
assert.deepEqual(moveProcess(["Print"], 0, -1), ["Print"])
const orderedSelector = department("planning/reports/OrderedProcessSelect.vue")
for (const contract of ['label="Add process"', 'doctype="YRP Process"', 'modelValue.filter', 'move(index, -1)', 'move(index, 1)', 'emit("update:modelValue", values)']) assert.ok(orderedSelector.includes(contract), contract)
for (const filters of [{ lot: [], item: [] }, { lot: ["L"], item: [], from_date: "2026-10-01", to_date: "" }]) assert.ok(stockHint(filters))
for (const filters of [{ lot: ["L"], item: [] }, { lot: [], item: ["I"] }, { lot: [], item: [], category: "C" }, { lot: [], item: [], product_category: "C" }]) assert.equal(stockHint(filters), "")
const numericColumns = [{ fieldname: "cut", fieldtype: "Float" }, { fieldname: "dispatch", fieldtype: "Float" }]
const totalFixture = [{ item: "A", cut: 12, dispatch: 5 }, { item: "B", cut: 8, dispatch: 3 }, { item: "Total", is_total_row: true, cut: 999, dispatch: 999 }]
assert.deepEqual(progressTotals(totalFixture, numericColumns).at(-1), { item: "Total", is_total_row: true, cut: 20, dispatch: 8 })
assert.deepEqual(progressTotals(totalFixture, numericColumns.slice(0, 1)).at(-1), { item: "Total", is_total_row: true, cut: 20 })
assert.deepEqual(progressTotals([], numericColumns), [])
assert.equal(totalFixture.at(-1).cut, 999)
assert.deepEqual(progressCellLink({ fieldname: "received" }, { lot: "L / 1", process_links: { received: "Print & Wash" } }), { path: "/planning/reports", query: { group: "production", report: "inhouse-quantity", lot: "L / 1", process: "Print & Wash" } })
assert.equal(progressCellLink({ fieldname: "received" }, { is_total_row: true, lot: "L", process_links: { received: "Print" } }), "")
assert.deepEqual(visibleProductionReports({ size_wise_stock: { can_read: true }, colour_wise_diff: { can_read: false }, work_in_progress: { can_read: true } }).map((report) => report.key), ["size_wise_stock", "work_in_progress"])
for (const [file, key] of [["ColourWiseDiffReport", "colour-wise-diff"], ["SizeWiseStockReport", "size-wise-stock"], ["WorkInProgressReport", "work-in-progress"]]) {
	const source = department(`planning/reports/${file}.vue`)
	for (const contract of ["ReportShell", "OrderedProcessSelect", ':loading="loading"', ':generated="generated"', "reportError", 'empty-title="No rows for these filters."', "Boolean(hint)", "JSON.stringify(filters.process_list)", `useWebReport({ reportKey: "planning-${key}" })`]) assert.ok(source.includes(contract), `${file}: ${contract}`)
	assert.ok(reportProvider.includes(`key="planning-${key}"`))
	assert.ok(productionPage.includes(`import("./${file}.vue")`))
}
const workInProgress = department("planning/reports/WorkInProgressReport.vue")
for (const contract of ["ReportColumnPicker", "progressTotals(layoutRows.value, columns.value, cellValue)", ':cell-link="progressCellLink"', 'v-if="isBackgroundResult" label="Download"', '@click="download"', 'ReportRunStatus :state="state"', 'determinate @rebuild', 'Lot creation']) assert.ok(workInProgress.includes(contract), contract)
assert.ok(reportProvider.includes('background={"days": 31, "from_field": "from_date", "to_field": "to_date", "missing_bound": "background"}'))
console.log("Planning B3 assertions passed (C1–C9 frontend contracts)")

// Run the actual Planning column adapter with an isolated layout and download sink.
const { reportCellValue } = await import("../frontend/src/composables/reportColumns.js")
const { formatReportCell } = await import("../frontend/src/departments/finishing/reports/finishingReports.js")
const linkedColumns = [
	{ fieldname: "item", label: "Style", kind: "base" },
	{ key: "linked:item:weight", fieldname: "weight", label: "Item weight", kind: "linked", source_column: "item", target_field: "weight", fieldtype: "Float" },
	{ key: "linked:lot:weight", fieldname: "weight", label: "Lot weight", kind: "linked", source_column: "lot", target_field: "weight", fieldtype: "Float" },
]
const linkedRows = [{ item: "A", lot: "L1", __linked: { item: { weight: 5 }, lot: { weight: 2 } } }, { item: "B", lot: "L2", __linked: { item: { weight: 7 }, lot: { weight: 3 } } }, { is_total_row: true, item: "Total", weight: 999 }]
const recalculated = progressTotals(linkedRows, linkedColumns, reportCellValue)
assert.equal(recalculated.at(-1)["linked:item:weight"], 12)
assert.equal(recalculated.at(-1)["linked:lot:weight"], 5)
assert.equal(reportCellValue(recalculated.at(-1), linkedColumns[1]), "") // Shared default remains unchanged.
const adapterSource = department("planning/reports/usePlanningReportColumns.js").replace(/^import .*\n/gm, "").replace("export function", "function")
const createAdapter = new Function("onMounted", "ref", "useReportColumns", "formatReportCell", adapterSource + "\nreturn usePlanningReportColumns")
const layoutStub = { displayColumns: { value: linkedColumns }, rows: { value: linkedRows }, cellValue: reportCellValue, loadLayout() {} }
const adapter = createAdapter(() => {}, (value) => ({ value }), () => layoutStub, formatReportCell)("planning-work-in-progress", {}, {}, { cellValue: progressCellValue, exportRows: () => recalculated })
assert.equal(adapter.formattedCell(linkedColumns[1], recalculated.at(-1)), "12")
assert.equal(adapter.formattedCell(linkedColumns[2], recalculated.at(-1)), "5")
assert.equal(adapter.formattedCell(linkedColumns[1], recalculated[0]), "5")
let csvBlob
const originalCreateObjectURL = URL.createObjectURL
const originalDocument = globalThis.document
const originalWindow = globalThis.window
try {
	URL.createObjectURL = (blob) => { csvBlob = blob; return "blob:planning-test" }
	globalThis.document = { createElement: () => ({ click() {} }) }
	globalThis.window = { setTimeout() {} }
	adapter.downloadCsv()
	assert.equal((await csvBlob.text()).split("\r\n").at(-1), '"Total","12","5"')
} finally {
	URL.createObjectURL = originalCreateObjectURL
	globalThis.document = originalDocument
	globalThis.window = originalWindow
}
const sizeColumns = [{ fieldname: "type", label: "Type" }, { fieldname: "size_0", label: "M" }, { fieldname: "size_1", label: "S" }, { fieldname: "total", label: "Total" }]
assert.deepEqual(sizeMatrixColumns(sizeColumns, { matrix_sizes: ["M", "S"] }).map((column) => column.fieldname), ["type", "size_0", "size_1", "total"])
assert.deepEqual(sizeMatrixColumns(sizeColumns, { matrix_sizes: ["S", "M"] }).map((column) => column.fieldname), ["type", "size_1", "size_0", "total"])
assert.ok(department("planning/reports/SizeWiseStockReport.vue").includes(':columns="matrix.columns"'))
assert.ok(workInProgress.includes("{ cellValue: progressCellValue, exportRows: () => rows.value }"))
console.log("Planning B3 fix assertions passed (linked totals render/export; per-matrix size order)")
