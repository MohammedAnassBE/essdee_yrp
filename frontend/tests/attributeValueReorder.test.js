import assert from "node:assert/strict"
import test from "node:test"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as ipdEditor from "../src/departments/merch/ipd/ipdEditor.js"
import * as purchaseViews from "../src/departments/purchase/purchaseViews.js"

const reorderModule = () => import("../src/components/common/useChipReorder.js")
const values = ["40", "45", "75"]
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const chips = root => findNodes(root, node => node.props.role === "listitem")
const text = node => [node.text, ...node.children.map(text)].join(" ")
const Button = props => Vue.h("button", props, props.label)
const key = (name, target = {}) => ({ key: name, altKey: true, target, preventDefault() {}, stopPropagation() {} })
const rect = (left, top, width = 40) => ({ left, top, right: left + width, bottom: top + 20, width, height: 20 })

async function harness() {
	const { useChipReorder } = await reorderModule()
	const items = Vue.ref([...values]), enabled = Vue.ref(true), calls = [], messages = [], focused = []
	const elements = values.map((value, index) => ({
		dataset: { chipValue: value }, getBoundingClientRect: () => rect(index * 50, 0),
		focus: () => focused.push(value), closest: () => null,
		setPointerCapture(id) { this.captured = id },
		hasPointerCapture(id) { return this.captured === id },
		releasePointerCapture() { this.captured = null },
	}))
	const container = Vue.ref({ querySelectorAll: () => elements, getBoundingClientRect: () => rect(0, 0, 150) })
	let reorder
	mountComponent({ setup() {
		reorder = useChipReorder({ items: () => items.value, enabled: () => enabled.value, container,
			onReorder: ordered => { calls.push(ordered); items.value = ordered }, announce: message => messages.push(message) })
		return () => Vue.h("div")
	} })
	const pointer = (index, x, y = 10, extra = {}) => ({ pointerId: 1, button: 0, isPrimary: true, clientX: x, clientY: y,
		currentTarget: elements[index], target: elements[index], preventDefault() {}, ...extra })
	const props = index => reorder.chipProps(items.value[index], index)
	return { items, enabled, calls, messages, focused, elements, container, pointer, props, reorder }
}

async function ipd(editable = true, save = async () => {}) {
	const calls = [], props = Vue.reactive({ attribute: "Size", values: [...values], editable })
	const key = Symbol("editor")
	const component = loadComponent(resolve("frontend/src/departments/merch/ipd/sections/IpdAttributeChips.vue"), {
		"primevue/button": Button,
		"../../../../api/purchase.js": { searchItemAttributeValues: async () => [] },
		"../../../../components/common/LinkField.vue": () => Vue.h("input"),
		"../../../../components/documents/DocumentConfirmationDialog.vue": () => null,
		"../../../../components/common/useChipReorder.js": await reorderModule(),
		"../ipdEditor.js": ipdEditor, "../useIpdEditor.js": { IPD_EDITOR_KEY: key },
	})
	const root = mountComponent({ setup() {
		Vue.provide(key, { saveAttributeValues: async (...args) => { calls.push(args); await save(); props.values = args[1] }, valueUsage: async () => ({}) })
		return () => Vue.h(component, props)
	} })
	return { root, props, calls }
}

async function dialog() {
	const applied = [], props = Vue.reactive({ visible: false, attribute: "Size", values: [...values], onApply: (...args) => applied.push(args) })
	const component = loadComponent(resolve("frontend/src/departments/purchase/item/ItemAttributeValuesDialog.vue"), {
		"primevue/button": Button, "primevue/inputtext": () => Vue.h("input"), "primevue/message": () => null,
		"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, [slots.default?.(), slots.footer?.()]) : null,
		"../../../api/purchase.js": { searchItemAttributeValues: async () => [] },
		"../../../components/common/LinkField.vue": () => Vue.h("input"),
		"../../../components/common/useChipReorder.js": await reorderModule(), "../purchaseViews.js": purchaseViews,
	})
	const root = mountComponent(component, props)
	props.visible = true
	await tick()
	return { root, props, applied }
}

test("A: drop indexes use horizontal midpoints and wrapped rows", async () => {
	const { chipDropIndex } = await reorderModule()
	const rects = [rect(0, 0), rect(50, 0), rect(0, 30), rect(50, 30)]
	for (const [x, y, expected] of [[-5, 10, 0], [25, 10, 1], [95, 10, 2], [95, 25, 2], [5, 40, 2], [25, 40, 3], [95, 40, 4], [95, -1, 0], [0, 60, 4]]) {
		assert.equal(chipDropIndex(rects, x, y), expected, `${x},${y}`)
	}
})

test("A: pointer drag moves 75 before 40, captures pointer, announces and focuses", async () => {
	const h = await harness()
	h.props(2).onPointerdown(h.pointer(2, 110))
	assert.equal(h.elements[2].captured, 1)
	h.props(2).onPointermove(h.pointer(2, 5))
	assert.equal(h.props(2).class["is-dragging"], true)
	assert.equal(h.props(0).class["is-drop-before"], true)
	await h.props(2).onPointerup(h.pointer(2, 5))
	assert.deepEqual(h.calls, [["75", "40", "45"]])
	assert.deepEqual(h.focused, ["75"])
	assert.deepEqual(h.messages, ["Moved 75 to position 1 of 3."])
	assert.equal(h.elements[2].captured, null)
})

test("A: same-place drop and sub-threshold click do not reorder or save", async () => {
	const h = await harness()
	for (const x of [12, 25]) {
		h.props(0).onPointerdown(h.pointer(0, 10))
		h.props(0).onPointermove(h.pointer(0, x))
		await h.props(0).onPointerup(h.pointer(0, x))
	}
	assert.deepEqual(h.calls, [])
})

test("A: add input and pending chips are excluded from drop targets", async () => {
	const h = await harness()
	h.container.value.children = [...h.elements, { dataset: {}, getBoundingClientRect: () => rect(140, 0, 10) }]
	h.props(0).onPointerdown(h.pointer(0, 10))
	h.props(0).onPointermove(h.pointer(0, 145))
	assert.equal(h.props(2).class["is-drop-after"], false)
	await h.props(0).onPointerup(h.pointer(0, 145))
	assert.deepEqual(h.calls, [])
})

test("B: Alt+Right/Left and Up/Down move one step; edges and plain arrows do nothing", async () => {
	const h = await harness()
	await h.props(0).onKeydown(key("ArrowLeft"))
	await h.props(2).onKeydown(key("ArrowRight"))
	await h.props(0).onKeydown({ ...key("ArrowRight"), altKey: false })
	assert.equal(h.calls.length, 0)
	for (const name of ["ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"]) await h.props(h.items.value.indexOf("40")).onKeydown(key(name))
	assert.deepEqual(h.calls, [["45", "40", "75"], values, ["45", "40", "75"], values])
	assert.deepEqual(h.focused, ["40", "40", "40", "40"])
})

test("C: editable IPD keyboard move saves exactly once with reordered attribute values", async () => {
	const { root, calls } = await ipd()
	assert.equal(chips(root)[0].props.tabindex, 0)
	assert.match(chips(root)[0].props["aria-label"], /40, position 1 of 3.*Alt\+Left/)
	assert.match(text(root), /Drag to reorder, or Alt \+ ← \/ →\./)
	await chips(root)[0].props.onKeydown(key("ArrowRight"))
	await tick()
	assert.deepEqual(calls, [["Size", ["45", "40", "75"]]])
	assert.match(text(findNodes(root, node => node.props.role === "status")[0]), /Moved 40 to position 2 of 3/)
})

test("D: readonly IPD has no focusable/reorderable chips or hint and cannot save", async () => {
	const { root, calls } = await ipd(false)
	for (const chip of nodes(root, "li")) {
		assert.ok(chip.props.tabindex == null)
		assert.ok(!chip.props.draggable)
		assert.ok(!chip.props["data-chip-value"])
		await chip.props.onKeydown?.(key("ArrowRight"))
		chip.props.onPointerdown?.({ target: chip, currentTarget: chip, button: 0 })
	}
	assert.deepEqual(calls, [])
	assert.doesNotMatch(text(root), /Drag to reorder/)
})

test("E: dialog keyboard reorders draft only and Apply emits the reordered list", async () => {
	const { root, props, applied } = await dialog()
	assert.match(text(root), /Drag to reorder, or Alt \+ ← \/ →\./)
	await chips(root)[2].props.onKeydown(key("ArrowLeft"))
	await tick()
	assert.deepEqual(props.values, values)
	assert.deepEqual(applied, [])
	assert.deepEqual(chips(root).map(node => node.props["data-chip-value"]), ["40", "75", "45"])
	const apply = nodes(root, "button").find(node => node.props.label === "Apply")
	assert.equal(apply.props.disabled, false)
	apply.props.onClick()
	assert.deepEqual(applied, [[["40", "75", "45"], []]])
})

test("F: pointerdown on remove button or input never captures or starts dragging", async () => {
	const h = await harness()
	for (const tag of ["button", "input"]) {
		h.props(2).onPointerdown(h.pointer(2, 110, 10, { target: { closest: () => ({ tagName: tag }) } }))
		h.props(2).onPointermove(h.pointer(2, 5))
		await h.props(2).onPointerup(h.pointer(2, 5))
	}
	assert.equal(h.elements[2].captured, undefined)
	assert.deepEqual(h.calls, [])
})

test("F: IPD and dialog remove buttons still remove their value", async () => {
	const ipdView = await ipd(), dialogView = await dialog()
	for (const { root } of [ipdView, dialogView]) {
		const chip = chips(root)[0], button = nodes(chip, "button")[0]
		chip.props.onPointerdown({ button: 0, target: { closest: () => button }, currentTarget: chip })
		await button.props.onClick()
		await tick()
	}
	assert.deepEqual(ipdView.calls, [["Size", ["45", "75"]]])
	assert.deepEqual(chips(dialogView.root).map(node => node.props["data-chip-value"]), ["45", "75"])
})

test("pointer cancel, Escape, disabled state and outside drops never save", async () => {
	for (const reason of ["cancel", "escape", "disabled", "outside"]) {
		const h = await harness()
		h.props(2).onPointerdown(h.pointer(2, 110))
		h.props(2).onPointermove(h.pointer(2, 5))
		if (reason === "cancel") h.props(2).onPointercancel(h.pointer(2, 5))
		if (reason === "escape") h.props(2).onKeydown(key("Escape"))
		if (reason === "disabled") { h.enabled.value = false; await tick() }
		await h.props(2).onPointerup(h.pointer(2, reason === "outside" ? 500 : 5))
		assert.deepEqual(h.calls, [], reason)
	}
})

test("IPD busy saving blocks additional keyboard moves and pointer capture", async () => {
	let finish
	const { root, calls } = await ipd(true, () => new Promise(resolve => { finish = resolve }))
	const saving = chips(root)[0].props.onKeydown(key("ArrowRight"))
	await tick()
	assert.ok(chips(root)[0].props.tabindex == null)
	await chips(root)[1].props.onKeydown(key("ArrowLeft"))
	assert.equal(calls.length, 1)
	finish()
	await saving
})

test("A: drop index groups chips of unequal height into one visual row", async () => {
	const { chipDropIndex } = await reorderModule()
	const short = rect(0, 10), tall = { left: 50, top: 0, right: 90, bottom: 40, width: 40, height: 40 }
	const rects = [short, tall, rect(0, 50)]
	for (const [x, y, expected] of [[95, 5, 2], [5, 5, 0], [60, 5, 1], [5, 45, 2], [95, 60, 3]]) {
		assert.equal(chipDropIndex(rects, x, y), expected, `${x},${y}`)
	}
})

test("focus stays where the user moved it while a reorder save is running", async () => {
	const h = await harness()
	const other = { focus() {} }
	const doc = { activeElement: h.elements[0], body: {} }
	h.container.value.ownerDocument = doc
	h.container.value.contains = element => h.elements.includes(element)
	const original = h.calls.push.bind(h.calls)
	h.calls.push = ordered => { doc.activeElement = other; return original(ordered) }
	await h.props(0).onKeydown(key("ArrowRight"))
	assert.deepEqual([...h.calls], [["45", "40", "75"]])
	assert.deepEqual(h.focused, [])
})

test("IPD reorder clears a pending Backspace selection", async () => {
	const { root } = await ipd()
	const add = findNodes(root, node => node.props.class === "ipd-chip-add")[0]
	add.props.onKeydown({ key: "Backspace", target: { tagName: "INPUT", value: "" }, preventDefault() {} })
	await tick()
	const selected = () => chips(root).filter(chip => String(chip.props.class).split(" ").includes("is-selected")).length
	assert.equal(selected(), 1)
	await chips(root)[2].props.onKeydown(key("ArrowLeft"))
	await tick()
	assert.equal(selected(), 0)
})
