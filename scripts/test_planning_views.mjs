import assert from "node:assert/strict"
import { readFileSync, readdirSync } from "node:fs"

import {
	PLANNING_ROUTES, PLANNING_WORKSPACES, activeReportGroup, isCurrentRecordRequest,
	visiblePlanningWorkspaces, visibleReportGroups,
} from "../frontend/src/departments/planning/planningViews.js"
import { lotTabs } from "../frontend/src/departments/planning/lot/lotViews.js"
import { editTabFor } from "../frontend/src/departments/planning/lot/lotEditor.js"
import { getLockedRedirect } from "../frontend/src/router/departmentLock.js"
import { departments } from "../frontend/src/departments/registry.js"

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
assert.equal(planningLayout.name, "Planning")
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
assert.ok(planningReports.includes("visibleReportGroups((await getPlanningCapabilities())?.sections?.reports?.groups)"))
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
const loadReports = new Function("loading", "loadError", "groups", "visibleReportGroups", "getPlanningCapabilities", `${loadSource}; return load`)(
	loadingState, errorState, groupState, visibleReportGroups,
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
assert.doesNotMatch(planningReports, /production|padding-inline|max-width: none|margin-inline/)
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
console.log("Planning views assertions passed")
