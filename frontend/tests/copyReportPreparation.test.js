import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
const { useIncrementalRows } = incrementalRows
import { useCopyFeedback } from "../src/composables/useCopyFeedback.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const nodes = (root, predicate) => findNodes(root, predicate)
const tick = async () => { await new Promise(done => setImmediate(done)); await Vue.nextTick() }
const Button = props => Vue.h("button", props, props.label)

function mountShell(beforeCopy, copyElementAsImage) {
	globalThis.window ??= { setTimeout, clearTimeout }
	const shell = loadComponent(resolve("frontend/src/components/reports/ReportShell.vue"), {
		"primevue/button": Button, "primevue/message": () => null, "primevue/skeleton": () => null,
		"./copyElementAsImage.js": { copyElementAsImage, copyPendingImage: () => false },
		"../../composables/useCopyFeedback.js": { useCopyFeedback: options => useCopyFeedback({ ...options, toast: { add() {} } }) },
		"./ReportActions.vue": () => null, "./ReportExportButton.vue": () => null,
		"./reportExport.js": { renderedReportRows: () => [] },
		"../../composables/useIncrementalRows.js": incrementalRows,
		"../navigation/InlinePageNavigation.vue": () => null,
		"../navigation/pageNavigationContext.js": { usePageNavigation: () => null },
	})
	return mountComponent(shell, { title: "Rework Details", generated: true, hasResults: true, copyable: true, beforeCopy })
}
const copyButton = root => nodes(root, node => node.type === "button" && node.props.label === "Copy Report")[0]

test("Copy Report runs beforeCopy first and undoes it after the capture, even when the copy fails", async () => {
	for (const failure of [null, new Error("Report is too large")]) {
		const calls = []
		const root = mountShell(async () => { calls.push("prepare"); return () => calls.push("restore") }, async (element, options) => {
			calls.push("copy")
			assert.deepEqual(options.hide, [".report-shell__filters", ".report-shell__refreshing"])
			if (failure) throw failure
		})
		copyButton(root).props.onClick()
		await tick()
		assert.deepEqual(calls, ["prepare", "copy", "restore"])
	}
})

test("FinishingSeriesTable expandAll opens every detail row and drops the toggle columns", () => {
	const table = loadComponent(resolve("frontend/src/departments/finishing/components/FinishingSeriesTable.vue"), {
		"../../../components/reports/reportUtils.js": { formatDate: value => value },
		"../finishingViews.js": { formatQuantity: value => String(value) },
	})
	const rows = ["S-1", "S-2"].map(series => ({ series, colour: "Red", total: 1, values: {}, detail: { grn_number: "GRN", lot: "L", item: "I", date: "2026-10-23" } }))
	const detailRows = root => nodes(root, node => node.type === "tr" && node.props.class === "series-table__detail")
	const toggles = root => nodes(root, node => node.props.class === "series-table__toggle")

	const collapsed = mountComponent(table, { rows, types: ["Stain"], expanded: "S-1", printable: true })
	assert.equal(detailRows(collapsed).length, 1)
	assert.equal(nodes(detailRows(collapsed)[0], node => node.type === "td")[0].props.colspan, 10)

	const copying = mountComponent(table, { rows, types: ["Stain"], expanded: "", printable: true, expandAll: true })
	assert.equal(detailRows(copying).length, 2)
	assert.equal(toggles(copying).length, 0)
	assert.equal(nodes(detailRows(copying)[0], node => node.type === "td")[0].props.colspan, 8)
})

test("renderAllRows mounts every lazily rendered row until the result changes", async () => {
	const rows = Vue.ref(Array.from({ length: 450 }, (_, index) => index))
	let incremental
	mountComponent({ setup() { incremental = useIncrementalRows(rows); return () => null } })
	const { renderedRows, unrenderedCount, renderAllRows } = incremental
	assert.equal(renderedRows.value.length, 200)
	renderAllRows()
	assert.equal(renderedRows.value.length, 450)
	assert.equal(unrenderedCount.value, 0)
	rows.value = Array.from({ length: 300 }, (_, index) => index)
	await Vue.nextTick()
	assert.equal(renderedRows.value.length, 200)
})

test("a full-render restore steps back only when no new result arrived meanwhile", async () => {
	const rows = Vue.ref(Array.from({ length: 900 }, (_, index) => index))
	let incremental
	mountComponent({ setup() { incremental = useIncrementalRows(rows); return () => null } })
	const { renderedRows, renderMoreRows, renderAllRows } = incremental
	renderMoreRows()
	renderMoreRows()
	const restore = renderAllRows()
	assert.equal(renderedRows.value.length, 900)
	restore()
	assert.equal(renderedRows.value.length, 600)
	const stale = renderAllRows()
	rows.value = Array.from({ length: 800 }, (_, index) => index)
	await Vue.nextTick()
	renderAllRows()
	stale()
	assert.equal(renderedRows.value.length, 800, "a restore from before the reset leaves the newer state alone")
})
