import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import * as views from "../src/departments/quality/qualityViews.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const component = (name, modules) => loadComponent(resolve(`frontend/src/departments/quality/${name}.vue`), modules)
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const container = (props, { slots }) => Vue.h("section", props, [slots.default?.(), slots.footer?.()])
const deferred = () => {
	let resolve
	const promise = new Promise((done) => { resolve = done })
	return { promise, resolve }
}

const selection = {
	colours: [{ colour: "Blue", selected: 1 }, { colour: "Red", selected: 0 }],
	sizes: [{ size: "M", selected: true }, { size: "L", selected: 0 }],
}

function uploadComponent(uploadFile) {
	return component("components/InspectionImageUpload", {
		"primevue/button": Button, "../../../api/frappe.js": { uploadFile },
		"../../../components/documents/DocumentErrorDialog.vue": (props) => Vue.h("error-dialog", props),
		"../qualityViews.js": views,
	})
}

test("real image component renders distinct environment camera and gallery inputs", () => {
	const root = mountComponent(uploadComponent(), {})
	const [camera, gallery] = nodes(root, "input")
	assert.equal(camera.props.type, "file")
	assert.equal(camera.props.accept, "image/*")
	assert.equal(camera.props.capture, "environment")
	assert.equal(gallery.props.accept, "image/*")
	assert.equal(gallery.props.capture, undefined)
	assert.deepEqual(nodes(root, "button").map(({ props }) => props.label), ["Take photo", "Choose from gallery"])
	const any = mountComponent(uploadComponent(), { acceptAny: true })
	assert.equal(nodes(any, "input")[1].props.accept, undefined)
	assert.equal(nodes(any, "input")[0].props.capture, "environment")
})

test("image upload is immediate, public, attached to the saved field, and reports busy/progress", async () => {
	const task = deferred(), requests = [], changes = [], busy = []
	const root = mountComponent(uploadComponent((file, options) => { requests.push({ file, options }); return task.promise }), {
		docname: "EQI-1", "onUpdate:modelValue": (value) => changes.push(value), "onUploading-change": (value) => busy.push(value),
	})
	const file = new File(["image"], "photo.jpg", { type: "image/jpeg" })
	nodes(root, "input")[0].props.onChange({ target: { files: [file], value: "photo.jpg" } })
	await tick()
	assert.equal(requests[0].file, file)
	assert.equal(requests[0].options.doctype, views.INSPECTION_DOCTYPE)
	assert.equal(requests[0].options.docname, "EQI-1")
	assert.equal(requests[0].options.isPrivate, 0)
	assert.equal(requests[0].options.fieldname, "upload_quality_approval_sheet")
	assert.ok(nodes(root, "button").every(({ props }) => props.disabled))
	requests[0].options.onProgress(48); await tick()
	assert.equal(nodes(root, "progress")[0].props.value, 48)
	task.resolve({ file_url: "/files/photo.jpg" }); await tick()
	assert.deepEqual(changes, ["/files/photo.jpg"])
	assert.deepEqual(busy, [true, false])
})

test("failed image upload keeps the value and surfaces its server error", async () => {
	const changes = []
	const root = mountComponent(uploadComponent(async () => { throw new Error("Upload denied") }), {
		modelValue: "/files/previous.jpg", "onUpdate:modelValue": (value) => changes.push(value),
	})
	nodes(root, "input")[1].props.onChange({ target: { files: [new File(["x"], "x.jpg", { type: "image/jpeg" })], value: "" } })
	await tick()
	assert.deepEqual(changes, [])
	assert.equal(nodes(root, "error-dialog")[0].props.message, "Upload denied")
	assert.equal(nodes(root, "img")[0].props.src, "/files/previous.jpg")
})

test("picker renders only selected options when readonly and emits immutable selections when editable", async () => {
	const changes = []
	const props = Vue.reactive({ modelValue: selection, readonly: false, "onUpdate:modelValue": (value) => changes.push(value) })
	const root = mountComponent(component("components/InspectionColourSizePicker", { "primevue/button": Button, "../qualityViews.js": views }), props)
	const all = nodes(root, "button").find(({ props }) => props.label === "Select all")
	all.props.onClick()
	assert.deepEqual(changes[0].colours.map(({ selected }) => selected), [1, 1])
	props.readonly = true; await tick()
	assert.equal(nodes(root, "button").length, 2)
	assert.ok(nodes(root, "button").every(({ props }) => props.disabled))
})

test("Debit dialog requires a positive value, nonblank reason and completed document upload", async () => {
	const changes = []
	const root = mountComponent(component("components/InspectionDebitDialog", {
		"primevue/button": Button, "primevue/dialog": container,
		"../../../components/common/FormField.vue": (props) => Vue.h("field", props),
		"./InspectionImageUpload.vue": (props) => Vue.h("upload", props),
	}), { visible: true, onConfirm: (value) => changes.push(value) })
	const confirm = () => nodes(root, "button").find(({ props }) => props.label === "Create Debit")
	const change = async (name, value) => { nodes(root, "field").find(({ props }) => props.field.fieldname === name).props["onUpdate:modelValue"](value); await tick() }
	assert.ok(confirm().props.disabled)
	await change("debit_value", -10)
	await change("reason", "Rejected stitching")
	nodes(root, "upload")[0].props["onUpdate:modelValue"]("/files/debit.pdf"); await tick()
	assert.ok(confirm().props.disabled)
	await change("debit_value", 100)
	assert.equal(confirm().props.disabled, false)
	nodes(root, "upload")[0].props.onUploadingChange(true); await tick()
	assert.ok(confirm().props.disabled)
	nodes(root, "upload")[0].props.onUploadingChange(false); await tick()
	confirm().props.onClick()
	assert.deepEqual(changes, [{ debit_value: 100, reason: "Rejected stitching", debit_document: "/files/debit.pdf" }])
})

test("action strip keeps its default primary and accepts the confirming Submit control", async () => {
	const strip = loadComponent(resolve("frontend/src/components/documents/DocumentActionStrip.vue"), {
		"primevue/button": Button, "primevue/menu": (props) => Vue.h("menu", props),
	})
	const actions = [{ key: "submit", label: "Submit", primary: true }, { key: "cancel", label: "Cancel", menuOnly: true }]
	const original = mountComponent(strip, { actions })
	assert.equal(nodes(original, "button")[0].props.label, "Submit")
	const confirmations = [], submitted = []
	const saveButton = loadComponent(resolve("frontend/src/components/documents/DocumentSaveButton.vue"), {
		"primevue/button": Button,
		"./documentPrimaryAction.js": await import("../src/components/documents/documentPrimaryAction.js"),
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => (value) => confirmations.push(value) },
	})
	const root = mountComponent(() => Vue.h(strip, { actions }, { primary: () => Vue.h(saveButton, {
		saved: true, dirty: false, showSubmit: true, documentLabel: "Quality Inspection EQI-1", onSubmit: () => submitted.push(true),
	}) }))
	nodes(root, "button")[0].props.onClick()
	assert.equal(confirmations[0].message, "Permanently Submit Quality Inspection EQI-1?")
	assert.deepEqual(submitted, [])
	confirmations[0].accept()
	assert.deepEqual(submitted, [true])
})
