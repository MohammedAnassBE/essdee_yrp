import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import * as views from "../src/departments/quality/qualityViews.js"
import * as fields from "../src/departments/quality/inspectionFields.js"
import * as overview from "../src/utils/documentOverview.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const selection = { colours: [{ colour: "Blue", selected: 1 }], sizes: [{ size: "M", selected: 1 }] }
const complete = Object.freeze({ result: "Pass", calculated_result: "Pass", order_qty: 1000, offer_qty: 200,
	sample_piece_count: 20, major_aql_level: "2.5", minor_aql_level: "4.0",
	major_defect_maximum_allowed: 2, minor_defect_maximum_allowed: 3, major_defect_found: 2, minor_defect_found: 3 })
const manual = Object.freeze({ ...complete, calculated_result: null, offer_qty: 100, sample_piece_count: 0,
	order_qty: 0, major_defect_maximum_allowed: 0, minor_defect_maximum_allowed: 0, major_defect_found: 5, minor_defect_found: 1 })
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const text = (root) => findNodes(root, (node) => node.type !== "comment").map((node) => node.text).join(" ")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const container = (props, { slots }) => Vue.h("section", props, slots.default?.())

test("result summary distinguishes stored calculations, manual overrides and current limits", () => {
	assert.deepEqual(views.inspectionResultSummary(complete), {
		result: "Pass", calculated: "Pass", isManual: false, limitResult: "Pass", note: "",
	})
	assert.deepEqual(views.inspectionResultSummary({ ...complete, result: "Hold" }), {
		result: "Hold", calculated: "Pass", isManual: true, limitResult: "Pass",
		note: "Manual override. Found defects give Pass against the allowed limits",
	})
	assert.deepEqual(views.inspectionResultSummary(manual), {
		result: "Pass", calculated: "", isManual: true, limitResult: "Fail",
		note: "Entered manually, not calculated. Found defects give Fail against the allowed limits",
	})
	assert.equal(views.inspectionResultSummary({ ...complete, calculated_result: "Fail" }).note, "Manual override")
	assert.deepEqual(views.inspectionResultSummary(), { result: "", calculated: "", isManual: false, limitResult: "", note: "" })
	for (const missing of [null, undefined, "", " "]) {
		assert.equal(views.inspectionResultSummary({ ...complete, minor_defect_maximum_allowed: missing }).limitResult, "")
	}
	assert.equal(views.inspectionResultSummary({ ...manual, major_defect_found: 0, minor_defect_found: 0 }).limitResult, "Pass")
})

test("editor result state follows the stored calculation across edits and new documents", () => {
	const form = Object.freeze({ ...complete, major_defect_found: 3 })
	assert.deepEqual(views.inspectionEditorResultState(form, "Pass", views.inspectionResultPreview(form)), {
		isManual: false, showOverride: false, message: "Result will be recalculated to Fail on save.",
	})
	assert.deepEqual(views.inspectionEditorResultState({ ...complete, result: "Fail" }, "Pass", "Pass"), {
		isManual: true, showOverride: true, message: "Result Fail will be kept instead of the calculated Pass.",
	})
	for (const storedCalculated of [undefined, ""]) {
		assert.deepEqual(views.inspectionEditorResultState(form, storedCalculated, "Fail"), {
			isManual: true, showOverride: true, message: "Result Pass will be kept instead of the calculated Fail.",
		})
		assert.deepEqual(views.inspectionEditorResultState({}, storedCalculated, "Fail"), {
			isManual: false, showOverride: false, message: "",
		})
	}
	assert.deepEqual(views.inspectionEditorResultState({ result: "Fail" }, "Pass", "Fail"), {
		isManual: true, showOverride: false, message: "",
	})
	assert.deepEqual(views.inspectionEditorResultState({ result: "Fail" }, "Pass", ""), {
		isManual: true, showOverride: false, message: "",
	})
})

test("calculation notes explain AQL range, missing inspection rows and manual mismatch without mutation", () => {
	const empty = Object.freeze({ colours: [], sizes: [] })
	assert.deepEqual(views.inspectionCalculationNotes(manual, empty), [
		{ key: "aql_range", severity: "warn", text: "Offer Qty 100 is outside the 2.5 AQL table range, so the sample size is 0." },
		{ key: "no_delivery", severity: "warn", text: "No colours or sizes are recorded on this inspection, so Order Qty is 0." },
		{ key: "manual_mismatch", severity: "warn", text: "Result Pass was entered manually; the found defects give Fail." },
	])
	assert.deepEqual(views.inspectionCalculationNotes(complete, selection), [])
	assert.deepEqual(views.inspectionCalculationNotes(), [])
	for (const sample_piece_count of [undefined, 20]) {
		assert.ok(!views.inspectionCalculationNotes({ ...manual, sample_piece_count }).some(({ key }) => key === "aql_range"))
	}
	for (const missing of [null, undefined, ""]) {
		for (const key of ["major_aql_level", "minor_aql_level"]) {
			assert.ok(!views.inspectionCalculationNotes({ ...manual, [key]: missing }, selection).some(({ key }) => key === "aql_range"))
		}
	}
	assert.ok(!views.inspectionCalculationNotes({ ...manual, offer_qty: 0 }).some(({ key }) => key === "aql_range"))
	assert.ok(views.inspectionCalculationNotes({ ...manual, major_defect_maximum_allowed: null }).some(({ key }) => key === "aql_range"))
})

test("AQL range note describes only the major table sample when minor allowance is nonzero", () => {
	const asymmetric = { ...complete, sample_piece_count: 0, minor_defect_maximum_allowed: 5 }
	assert.deepEqual(views.inspectionCalculationNotes(asymmetric, selection), [
		{ key: "aql_range", severity: "warn", text: "Offer Qty 200 is outside the 2.5 AQL table range, so the sample size is 0." },
	])
	assert.equal(views.inspectionStatTiles(asymmetric)[4].hint, "of 5 allowed")
})

test("selection notes cover either missing selection and distinguish missing inspection rows", () => {
	for (const partial of [
		{ ...selection, colours: [] }, { ...selection, sizes: [] },
		{ ...selection, colours: [{ colour: "Blue", selected: 0 }] },
		{ ...selection, sizes: [{ size: "M", selected: 0 }] },
	]) {
		assert.deepEqual(views.inspectionCalculationNotes(complete, partial), [
			{ key: "no_selection", severity: "warn", text: "Select colours and sizes to calculate Order Qty." },
		])
	}
})

test("tiles explain zero quantities while keeping production comparisons and the optional selection argument", () => {
	const tiles = views.inspectionStatTiles(manual, {})
	assert.deepEqual(tiles.slice(0, 3).map(({ value, hint }) => [value, hint]), [
		["—", "Select colours and sizes"], ["100", ""], ["—", "Outside AQL range"],
	])
	assert.ok(tiles.slice(3).every(({ tone, hint }) => tone === "danger" && hint === "of 0 allowed"))
	assert.equal(views.inspectionStatTiles(manual)[0].value, "0")
	assert.equal(views.inspectionStatTiles(manual, selection)[0].value, "0")
	assert.equal(views.inspectionStatTiles({ ...manual, order_qty: 10 }, {})[0].value, "10")
	assert.equal(views.inspectionStatTiles({ offer_qty: 100, sample_piece_count: null })[2].hint, "")
	assert.equal(views.inspectionStatTiles({ offer_qty: 0, sample_piece_count: 0 })[2].value, "0")
	assert.equal(views.inspectionStatTiles({ ...manual, minor_defect_found: 0 })[4].tone, "success")
})

function modules(record, api = {}) {
	const payload = { record: { name: "EQI-1", docstatus: 0, against_id: "WO-1", checking_level: "Level 2", ...record },
		colour_size_data: { colours: [], sizes: [] }, actions: { edit: { allowed: true } } }
	const result = {
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"vue-router": { useRoute: () => ({ params: {}, query: {} }), useRouter: () => ({ replace() {}, push() {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} },
		"../../api/frappe.js": { cancelDoc() {}, submitDoc() {} },
		"../../api/quality.js": { getInspectionWorkspace: async () => payload, getNewInspectionDefaults: async () => payload,
			getInspectionAgainstDetails() {}, getInspectionAqlLimits: async () => ({ sample: 0, major_allowed: 0, minor_allowed: 0 }),
			saveInspection() {}, createInspectionDebit() {}, updateInspectionResult() {}, ...api },
		"../../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"../../utils/documentOverview.js": overview, "../../../utils/documentOverview.js": overview,
		"./qualityViews.js": views, "../qualityViews.js": views,
		"./inspectionFields.js": fields, "../inspectionFields.js": fields,
		"../../components/DepartmentPage.vue": container,
		"../../components/common/FormField.vue": (props) => Vue.h("field", props),
		"../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
		"../../../components/common/DocumentLink.vue": (props) => Vue.h("document-link", props),
		"./components/InspectionColourSizePicker.vue": () => null, "./components/InspectionImageUpload.vue": () => null,
		"./components/InspectionDebitDialog.vue": () => null, "./components/InspectionDebitDetails.vue": () => null,
		"./components/InspectionResultDialog.vue": () => null, "./components/InspectionApprovalSheet.vue": () => null,
		"../fabric-store/FabricDocumentWorkspace.vue": (props, { slots }) => Vue.h("workspace", props, props.loading ? [] : [
			Vue.h("header", {}, slots.header?.({ record: props.workspace.record, headingId: "heading" })),
			slots.matrix?.(), Vue.h("aside", {}, slots.rail?.()),
		]),
	}
	for (const name of ["button", "message", "tab", "tablist", "tabpanel", "tabpanels", "tabs"]) result[`primevue/${name}`] = container
	for (const name of ["DocumentActionStrip", "DocumentConfirmationDialog", "DocumentDeleteButton", "DocumentErrorDialog", "DocumentSaveButton", "DocumentStatusBadge", "DocumentOverview"]) {
		result[`../../components/documents/${name}.vue`] = () => null
	}
	for (const name of ["ListPageSkeleton", "WorkspaceLoadError"]) result[`../../components/common/${name}.vue`] = () => null
	return result
}

const mount = (name, record, api) => mountComponent(loadComponent(resolve(`frontend/src/departments/quality/${name}.vue`), modules(record, api)), { inspectionId: "EQI-1" })

test("view header and rail render the stored calculation and manual override, including null calculations", async () => {
	for (const calculated_result of [null, "Fail", "Pass"]) {
		const root = mount("QualityInspection", { ...manual, calculated_result })
		await tick()
		for (const region of [nodes(root, "header")[0], nodes(root, "aside")[0]]) {
			assert.match(text(region), /Pass/)
			if (calculated_result !== "Pass") {
				assert.match(text(region), /Manual override/)
				assert.match(text(region), new RegExp(`Calculated: ${calculated_result || "—"}`))
			} else assert.doesNotMatch(text(region), /Manual override/)
		}
		assert.match(text(nodes(root, "aside")[0]), new RegExp(`Calculated: ${calculated_result || "—"}`))
		const messages = findNodes(root, (node) => node.props.severity === "warn")
		assert.ok(messages.length >= 2)
		assert.ok(messages.every(({ props }) => props.closable === false && props.size === "small"))
		assert.match(text(root), /Outside AQL range/)
		assert.match(text(root), /Select colours and sizes/)
	}
})

test("editor waits for AQL limits before showing range notes and explains the preserved manual result", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		let finish
		const limits = new Promise((done) => { finish = done })
		const root = mount("QualityInspectionEditorPage", manual, { getInspectionAqlLimits: () => limits })
		await tick()
		assert.doesNotMatch(text(root), /outside the .* AQL table range|Calculated result preview|Manual override/)
		finish({ sample: 0, major_allowed: 0, minor_allowed: 0 }); await tick()
		assert.match(text(root), /Calculated result preview.*Fail/)
		assert.match(text(root), /Manual override/)
		assert.match(text(root), /Result Pass will be kept instead of the calculated Fail\./)
		assert.match(text(root), /Offer Qty 100 is outside the 2\.5 AQL table range, so the sample size is 0\./)
		assert.match(text(root), /No colours or sizes are recorded on this inspection, so Order Qty is 0\./)
		const field = nodes(root, "field").find(({ props }) => props.field.fieldname === "result")
		field.props["onUpdate:modelValue"]("Fail"); await tick()
		assert.doesNotMatch(text(root), /Manual override|will be kept instead|was entered manually/)
	} finally { globalThis.window = previous }
})

test("editor recalculates an automatic result after defect changes and preserves an explicit override", async () => {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		const root = mount("QualityInspectionEditorPage", complete, {
			getInspectionAqlLimits: async () => ({ sample: 20, major_allowed: 2, minor_allowed: 3 }),
		})
		await tick()
		const update = async (name, value) => {
			nodes(root, "field").find(({ props }) => props.field.fieldname === name).props["onUpdate:modelValue"](value)
			await tick()
		}
		await update("major_defect_found", 3)
		assert.match(text(root), /Result will be recalculated to Fail on save\./)
		assert.doesNotMatch(text(root), /Manual override|will be kept instead/)
		assert.equal(findNodes(root, (node) => node.props.class === "quality-page__recalculation").length, 1)
		await update("major_defect_found", 2)
		assert.doesNotMatch(text(root), /will be recalculated/)
		await update("result", "Fail")
		assert.match(text(root), /Manual override/)
		assert.match(text(root), /Result Fail will be kept instead of the calculated Pass\./)
		assert.doesNotMatch(text(root), /will be recalculated/)
	} finally { globalThis.window = previous }
})
