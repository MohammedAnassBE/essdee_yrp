import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { formatFullDateTime, prettyDate } from "../src/utils/prettyDate.js"

const now = new Date(2026, 9, 22, 14, 30, 0)
const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("short relative time matches Frappe Desk list view", () => {
	assert.equal(prettyDate("2026-10-22 14:29:30.123456", { now }), "now")
	assert.equal(prettyDate("2026-10-22 14:25:00", { now }), "5 m")
	assert.equal(prettyDate("2026-10-22 12:10:00", { now }), "2 h")
	assert.equal(prettyDate("2026-10-21 23:59:00", { now }), "1 d")
	assert.equal(prettyDate("2026-10-16 09:00:00", { now }), "6 d")
	assert.equal(prettyDate("2026-10-01 09:00:00", { now }), "3 w")
	assert.equal(prettyDate("2026-08-01 09:00:00", { now }), "2 M")
	assert.equal(prettyDate("2024-10-01 09:00:00", { now }), "2 y")
})

test("long relative time matches Frappe Desk wording", () => {
	const long = (value) => prettyDate(value, { now, mini: false })
	assert.equal(long("2026-10-22 14:29:30"), "just now")
	assert.equal(long("2026-10-22 14:28:30"), "1 minute ago")
	assert.equal(long("2026-10-22 14:20:00"), "10 minutes ago")
	assert.equal(long("2026-10-22 13:00:00"), "1 hour ago")
	assert.equal(long("2026-10-21 10:00:00"), "yesterday")
	assert.equal(long("2026-10-19 10:00:00"), "3 days ago")
	assert.equal(long("2026-10-12 10:00:00"), "1 week ago")
	assert.equal(long("2026-08-01 10:00:00"), "2 months ago")
	assert.equal(long("2025-08-01 10:00:00"), "1 year ago")
})

test("empty, invalid and future values render nothing", () => {
	assert.equal(prettyDate("", { now }), "")
	assert.equal(prettyDate(null, { now }), "")
	assert.equal(prettyDate("not a date", { now }), "")
	assert.equal(prettyDate("2026-10-23 09:00:00", { now }), "")
})

test("full timestamp uses the /web day-first format", () => {
	assert.equal(formatFullDateTime("2026-10-22 09:05:07.947516"), "22-10-2026 09:05:07")
	assert.equal(formatFullDateTime("2026-10-22"), "22-10-2026")
	assert.equal(formatFullDateTime(""), "")
})

test("every shared list row shows last modified like Desk", () => {
	const listView = source("../src/components/common/ListView.vue")
	assert.match(listView, /import \{ formatFullDateTime, prettyDate \} from "..\/..\/utils\/prettyDate.js"/)
	assert.match(listView, /class="list-modified-column"/)
	assert.match(listView, /class="list-modified-value" :title="modifiedTitle\(data\)">\{\{ modifiedLabel\(data\) \}\}/)
	assert.match(listView, /class="mobile-list-record__modified" :title="modifiedTitle\(row\)">\{\{ modifiedLabel\(row\) \}\}/)
	assert.match(listView, /"modified",\n\t\t\.\.\.\(isSubmittable/)
})

test("a mounted list row renders the short modified time with the full timestamp on hover", async () => {
	const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
	const listColumns = await import("../src/components/common/listColumns.js")
	const listNavigation = await import("../src/utils/listNavigation.js")
	const statusTone = await import("../src/utils/statusTone.js")
	const listStatusFilters = await import("../src/components/common/listStatusFilters.js")
	const listItemFilters = await import("../src/components/common/listItemFilters.js")
	const prettyDateModule = await import("../src/utils/prettyDate.js")
	globalThis.Document ??= class Document {}
	globalThis.ShadowRoot ??= class ShadowRoot {}
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const pad = (value) => String(value).padStart(2, "0")
	const fiveMinutesAgo = new Date(Date.now() - 5 * 60000 - 1000)
	const modified = `${fiveMinutesAgo.getFullYear()}-${pad(fiveMinutesAgo.getMonth() + 1)}-${pad(fiveMinutesAgo.getDate())} ${pad(fiveMinutesAgo.getHours())}:${pad(fiveMinutesAgo.getMinutes())}:${pad(fiveMinutesAgo.getSeconds())}.123456`
	const fetched = []
	const stub = (name) => (props) => Vue.h(name, props)
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/list" }) },
		"../../api/frappe.js": {
			getMeta: async () => [{ name: "Entry", fields: [] }],
			getActiveWorkflow: async () => null,
			getUserListview: async () => ({ fields: [{ fieldname: "name" }, { fieldname: "modified", fieldtype: "Datetime" }], columns: null }),
			getItemFilterValues: async () => ({}),
			getList: async (doctype, args) => { fetched.push(args.fields); return [{ name: "ENTRY-1", modified }] },
			getCount: async () => 1,
			getCounts: async (doctype, filterSets) => filterSets.map(() => 1),
		},
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDateModule,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("./ListviewFilters.vue") }
	const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
	let root
	try {
		root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({ doctype: "Entry", navigationEnabled: false }))
		await tick(); await tick()
		assert.ok(fetched[0].includes("modified"))
		const [label] = findNodes(root, (node) => node.props?.class === "mobile-list-record__modified")
		assert.equal((label.text || label.children.map((child) => child.text).join("")).trim(), "5 m")
		assert.match(label.props.title, /^Last updated 5 minutes ago · \d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2}$/)
	} finally {
		globalThis.window = previousWindow
		root?.unmount?.()
	}
})
