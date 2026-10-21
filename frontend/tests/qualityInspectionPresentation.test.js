import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import * as views from "../src/departments/quality/qualityViews.js"
import * as fields from "../src/departments/quality/inspectionFields.js"
import * as overview from "../src/utils/documentOverview.js"
import { linkFieldTarget } from "../src/utils/linkTarget.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const tick = () => Vue.nextTick()
const read = (file) => readFileSync(resolve(`frontend/src/departments/quality/${file}`), "utf8")
const component = (name, modules = {}) => loadComponent(resolve(`frontend/src/departments/quality/components/${name}.vue`), {
	"../qualityViews.js": views,
	"../inspectionFields.js": fields,
	"../../../utils/documentOverview.js": overview,
	"../../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
	...modules,
})

test("inspection tiles compare found with allowed, retain zero limits, and keep missing limits neutral", () => {
	for (const [found, allowed, tone] of [[2, 3, "success"], [3, 3, "success"], [4, 3, "danger"], [0, 0, "success"], [1, 0, "danger"], [4, null, "neutral"], [4, undefined, "neutral"], [4, "", "neutral"]]) {
		const record = { major_defect_found: found, major_defect_maximum_allowed: allowed, minor_defect_found: found, minor_defect_maximum_allowed: allowed }
		const tiles = views.inspectionStatTiles(record).filter(({ key }) => ["major", "minor"].includes(key))
		assert.ok(tiles.every((tile) => tile.tone === tone))
		assert.ok(tiles.every((tile) => tile.value === String(found)))
		assert.ok(tiles.every((tile) => tile.hint === (allowed == null || allowed === "" ? "Limit not set" : `of ${allowed} allowed`)))
	}
	assert.equal(views.inspectionStatTiles({ major_defect_maximum_allowed: "3", major_defect_found: "4" })[3].tone, "danger")
})

test("inspection tiles show the three quantities, hide zero SPI, and do not mutate the record", () => {
	const record = Object.freeze({ order_qty: 1000, offer_qty: 100, sample_piece_count: 20, spi_found: 0 })
	const tiles = views.inspectionStatTiles(record)
	assert.deepEqual(tiles.slice(0, 3).map(({ label, value }) => [label, value]), [["Order Qty", "1,000"], ["Offer Qty", "100"], ["Sample Size", "20"]])
	for (const spi_found of [undefined, null, "", 0, "0"]) assert.ok(!views.inspectionStatTiles({ spi_found }).some(({ key }) => key === "spi_found"))
	assert.equal(views.inspectionStatTiles({ spi_found: 8 }).at(-1).value, "8")
	assert.equal(views.inspectionStatTiles({})[0].value, "—")
})

test("inspection detail fields omit empty values and third party, preserve zero, and resolve real link identities", () => {
	const record = Object.freeze({ against_id: "WO /1", supplier: "SUP-1", supplier_name: "Sewing Unit", inspector: "inspector@example.com", amended_from: "EQI-0", order_qty: 0, description: " ", posting_date: null, is_third_party: 0, third_party_supplier: "THIRD", third_party_supplier_name: "External Inspector" })
	const details = views.inspectionDetailFields(record)
	assert.ok(details.every(({ fieldname, label, fieldtype }) => fieldname && label && fieldtype))
	assert.ok(!details.some(({ fieldname }) => ["description", "posting_date", "is_third_party", "third_party_supplier", "third_party_supplier_name"].includes(fieldname)))
	assert.equal(details.find(({ fieldname }) => fieldname === "order_qty").value, 0)
	assert.deepEqual(linkFieldTarget(details.find(({ fieldname }) => fieldname === "against_id")), { doctype: "YRP Work Order", name: "WO /1" })
	const supplier = details.find(({ fieldname }) => fieldname === "supplier")
	assert.deepEqual(linkFieldTarget(supplier), { doctype: "Supplier", name: "SUP-1" })
	assert.equal(supplier.value, "Sewing Unit")
	assert.deepEqual(linkFieldTarget(details.find(({ fieldname }) => fieldname === "amended_from")), { doctype: views.INSPECTION_DOCTYPE, name: "EQI-0" })
	assert.deepEqual(overview.buildDocumentOverviewGroups([], views.INSPECTION_DETAIL_SECTIONS), [])
	assert.ok(!overview.buildDocumentOverviewGroups(details, views.INSPECTION_DETAIL_SECTIONS).some(({ key }) => key === "third_party"))
	const thirdParty = views.inspectionDetailFields({ ...record, is_third_party: "1" })
	assert.equal(thirdParty.find(({ fieldname }) => fieldname === "third_party_supplier_name").value, "External Inspector")
	assert.deepEqual(linkFieldTarget(thirdParty.find(({ fieldname }) => fieldname === "third_party_supplier")), { doctype: "Supplier", name: "THIRD" })
})

test("selected chip groups contain selected nonempty values only and omit empty groups", () => {
	const selection = { colours: [{ colour: "Blue", selected: "1" }, { colour: "Red", selected: 0 }, { colour: "", selected: 1 }], sizes: [{ size: "M", selected: true }, { size: "L", selected: false }] }
	const before = structuredClone(selection)
	assert.deepEqual(views.inspectionSelectedChips(selection), [{ key: "colours", label: "Colours", values: ["Blue"] }, { key: "sizes", label: "Sizes", values: ["M"] }])
	assert.deepEqual(selection, before)
	assert.deepEqual(views.inspectionSelectedChips(), [])
	assert.deepEqual(views.inspectionSelectedChips({ colours: [{ colour: "Blue", selected: 0 }] }), [])
})

test("header facts format dates, show supplier names, and omit empty values", () => {
	const facts = views.inspectionHeaderFacts({ against_id: "WO", supplier: "SUP", supplier_name: "Supplier Name", posting_date: "2026-10-21", lot: "", item: null })
	assert.deepEqual(facts.map(({ fieldname }) => fieldname), ["against_id", "supplier", "posting_date"])
	assert.equal(facts[0].doctype, "YRP Work Order")
	assert.equal(facts[1].display, "Supplier Name")
	assert.equal(facts[2].display, "21-10-2026")
	assert.deepEqual(views.inspectionHeaderFacts(), [])
})

test("summary facts show set inspection fields with link identities and conditional third party names", () => {
	const record = Object.freeze({ checking_level: "Level 2", major_aql_level: "2.5", minor_aql_level: "4.0", unit_name: "UNIT-1", description: "Final check", is_third_party: 1, third_party_supplier: "SUP-3", third_party_supplier_name: "External Inspector", supplier: "HEADER-ONLY" })
	const facts = views.inspectionSummaryFacts(record)
	assert.deepEqual(facts.map(({ fieldname, label, value, display, doctype }) => [fieldname, label, value, display, doctype]), [
		["checking_level", "Checking Level", "Level 2", "Level 2", ""],
		["major_aql_level", "Major AQL Level", "2.5", "2.5", "SD YRP AQL Level"],
		["minor_aql_level", "Minor AQL Level", "4.0", "4.0", "SD YRP AQL Level"],
		["unit_name", "Unit Name", "UNIT-1", "UNIT-1", "Supplier"],
		["description", "Description", "Final check", "Final check", ""],
		["third_party_supplier", "Third party supplier", "SUP-3", "External Inspector", "Supplier"],
	])
	for (const is_third_party of [undefined, 0, "0", 2]) {
		assert.ok(!views.inspectionSummaryFacts({ ...record, is_third_party }).some(({ fieldname }) => fieldname === "third_party_supplier"))
	}
	assert.equal(views.inspectionSummaryFacts({ ...record, is_third_party: "1", third_party_supplier_name: "" }).at(-1).display, "SUP-3")
	assert.deepEqual(views.inspectionSummaryFacts({ checking_level: " ", major_aql_level: "", minor_aql_level: null, unit_name: undefined, is_third_party: 1, third_party_supplier_name: "No link identity" }), [])
	assert.deepEqual(views.inspectionSummaryFacts(), [])
})

test("summary renders compact selected chips, set notes, and linked header facts", () => {
	const summary = component("InspectionSummary")
	const record = { supplier: "SUP", supplier_name: "Unit A", major_aql_level: "2.5", minor_aql_level: "4.0", unit_name: "UNIT-1", is_third_party: 1, third_party_supplier: "SUP-3", third_party_supplier_name: "External Inspector", measurement_deviation: "Sleeve +1cm" }
	const root = mountComponent(summary, { record, selection: { colours: [{ colour: "Blue", selected: 1 }, { colour: "Red", selected: 0 }] } })
	assert.deepEqual(nodes(root, "document-link").map(({ props }) => [props.doctype, props.name, props.label]), [
		["SD YRP AQL Level", "2.5", "2.5"], ["SD YRP AQL Level", "4.0", "4.0"],
		["Supplier", "UNIT-1", "UNIT-1"], ["Supplier", "SUP-3", "External Inspector"],
	])
	assert.equal(nodes(root, "dl")[1].props.class, "quality-header-facts quality-inspection-facts")
	assert.equal(nodes(root, "button").length, 0)
	assert.deepEqual(nodes(root, "span").filter(({ props }) => props.class === "quality-chip").map(({ text }) => text), ["Blue"])
	assert.equal(nodes(root, "h2").length, 1)
	assert.ok(nodes(root, "dd").some(({ text }) => text === "Sleeve +1cm"))
	const header = mountComponent(summary, { record, header: true })
	assert.equal(nodes(header, "document-link")[0].props.label, "Unit A")
	assert.equal(nodes(header, "document-link")[0].props.name, "SUP")
})

test("shared stat tiles update their tone as the editor changes defects", async () => {
	const record = Vue.reactive({ major_defect_found: 2, major_defect_maximum_allowed: 3 })
	const root = mountComponent(component("InspectionStatTiles"), { record, only: ["major"] })
	const tile = () => nodes(root, "div")[0]
	assert.match(tile().props.class, /quality-stat-tile--success/)
	record.major_defect_found = 4; await tick()
	assert.match(tile().props.class, /quality-stat-tile--danger/)
	record.major_defect_maximum_allowed = null; await tick()
	assert.match(tile().props.class, /quality-stat-tile--neutral/)
})

test("result badges share result icons and hide missing results", () => {
	const badge = component("InspectionResultBadge")
	for (const [result, icon] of [["Pass", "check"], ["Fail", "times"], ["Hold", "pause"]]) {
		const root = mountComponent(badge, { result })
		assert.match(nodes(root, "strong")[0].props.class, new RegExp(`quality-result-badge--${result.toLowerCase()}`))
		assert.equal(nodes(root, "i")[0].props.class, `pi pi-${icon}-circle`)
	}
	assert.equal(nodes(mountComponent(badge, {}), "strong").length, 0)
})

test("approval sheet opens an accessible zoom dialog and resets when its image changes", async () => {
	const props = Vue.reactive({ src: "/files/approval.jpg" })
	const root = mountComponent(component("InspectionApprovalSheet", {
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
	}), props)
	assert.equal(nodes(root, "dialog").length, 0)
	assert.equal(nodes(root, "button")[0].props["aria-label"], "Zoom approval sheet")
	nodes(root, "button")[0].props.onClick(); await tick()
	assert.notEqual(nodes(root, "dialog")[0].props.modal, undefined)
	assert.equal(nodes(root, "img").length, 2)
	const link = nodes(root, "a")[0]
	assert.equal(link.props.href, props.src)
	assert.equal(link.props.target, "_blank")
	assert.equal(link.props.rel, "noopener")
	props.src = "/files/other.jpg"; await tick()
	assert.equal(nodes(root, "dialog").length, 0)
	props.src = ""; await tick()
	assert.equal(nodes(root, "button").length, 0)
	assert.equal(nodes(root, "img").length, 0)
})

test("quality presentation uses existing tokens, two mobile stat columns and full width rail photos", () => {
	const css = read("quality.css")
	assert.match(read("QualityInspection.vue"), /class="quality-rail-metric quality-result-metric"/)
	assert.doesNotMatch(read("QualityInspection.vue"), /fabric-document-workspace__metric/)
	assert.match(css, /\.quality-rail-metric \{[^}]*display: grid;[^}]*gap: 6px;[^}]*padding: 11px 13px;[^}]*border-bottom: 1px solid var\(--erp-border-subtle\);[^}]*background: var\(--erp-surface\)/)
	assert.match(css, /\.quality-rail-metric \.quality-result-badge \{ justify-self: start/)
	assert.match(css, /\.quality-inspection-facts,\s*\.quality-selections \{ padding: 12px 14px; border: 1px solid var\(--erp-border\); border-radius: var\(--erp-panel-radius\); background: var\(--erp-surface\)/)
	assert.match(css, /repeat\(auto-fit, minmax\(140px, 1fr\)\)/)
	assert.match(css, /@media \(max-width: 620px\)[\s\S]*\.quality-stat-tiles \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/)
	assert.match(css, /\.quality-approval-sheet \{[^}]*grid-column: 1 \/ -1/)
	assert.match(css, /\.quality-approval-sheet__thumbnail \{[^}]*min-height: 44px/)
	assert.match(css, /\.quality-inspection-frame \.p-tab \{ min-height: 44px/)
	assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b|:\s*(white|black)\b|rgba?\(/i)
	for (const token of ["--erp-success-text", "--erp-success-soft", "--erp-danger", "--erp-danger-soft", "--erp-warning", "--erp-warning-soft"]) assert.ok(css.includes(`var(${token})`))
	const picker = read("components/InspectionColourSizePicker.vue")
	assert.match(picker, /repeat\(auto-fill, minmax\(min\(120px, 100%\), 1fr\)\)/)
})
