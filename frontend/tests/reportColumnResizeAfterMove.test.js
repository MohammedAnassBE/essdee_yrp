import assert from "node:assert/strict"
import test from "node:test"

const { attachColumnLayout, LIVE_RESIZE_CELL_LIMIT } = await import("../src/components/reports/columnLayoutController.js")
const { orderColumns } = await import("../src/components/reports/columnLayout.js")

const camel = name => name.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())

class Style {
	setProperty(name, value) { this[camel(name)] = value }
	removeProperty(name) { delete this[camel(name)] }
}

/** Just enough DOM for the controller: elements, selectors it uses, listeners and layout from the colgroup. */
class Element {
	constructor(doc, tag) {
		Object.assign(this, { ownerDocument: doc, tagName: tag.toUpperCase(), children: [], parentElement: null, dataset: {}, style: new Style(), attributes: {}, listeners: {}, text: "", natural: 0 })
		const classes = new Set()
		this.classList = { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name), toggle: (name, on) => on ? classes.add(name) : classes.delete(name) }
	}
	set className(value) { this.classList.add(value) }
	get firstChild() { return this.children[0] || null }
	get textContent() { return this.text + this.children.map(child => child.textContent).join("") }
	get colSpan() { return 1 }
	get rowSpan() { return 1 }
	append(child) { child.parentElement = this; this.children.push(child) }
	insertBefore(child, before) { child.parentElement = this; const index = this.children.indexOf(before); this.children.splice(index < 0 ? this.children.length : index, 0, child) }
	remove() { this.parentElement?.children.splice(this.parentElement.children.indexOf(this), 1); this.parentElement = null }
	setAttribute(name, value) { this.attributes[name] = String(value) }
	getAttribute(name) { return this.attributes[name] ?? null }
	hasAttribute(name) { return name in this.attributes }
	addEventListener(type, listener) { (this.listeners[type] ||= []).push(listener) }
	removeEventListener(type, listener) { this.listeners[type] = (this.listeners[type] || []).filter(entry => entry !== listener) }
	fire(type, event) { for (const listener of [...(this.listeners[type] || [])]) listener(event) }
	setPointerCapture() {}
	descendants() { return this.children.flatMap(child => [child, ...child.descendants()]) }
	matches(selector) {
		if (selector === "table") return this.tagName === "TABLE"
		if (selector === "[aria-label]") return this.hasAttribute("aria-label")
		if (selector.startsWith("th.")) return this.tagName === "TH" && this.classList.contains(selector.slice(3))
		if (selector.startsWith(".")) return this.classList.contains(selector.slice(1))
		return false
	}
	closest(selector) { for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node; return null }
	contains(node) { for (let current = node; current; current = current.parentElement) if (current === this) return true; return false }
	querySelectorAll(selector) {
		if (selector.startsWith(":scope > ")) { const inner = selector.slice(9); return this.children.filter(child => inner === "colgroup" ? child.tagName === "COLGROUP" : child.matches(inner)) }
		return this.descendants().filter(node => node.matches(selector))
	}
	querySelector(selector) { return this.querySelectorAll(selector)[0] || null }
	/** A header cell is as wide as its <col> once the table is sized, else its content width. */
	getBoundingClientRect() {
		const table = this.closest("table")
		const colgroup = table?.children.find(child => child.dataset.columnLayout === "widths")
		const index = this.parentElement?.children.indexOf(this)
		const width = this.tagName === "TH" && colgroup ? parseFloat(colgroup.children[index].style.width) : this.natural
		return { left: 0, right: width, top: 0, bottom: 20, width, height: 20 }
	}
}

function createPage(labels, { rowCount = 1 } = {}) {
	const frames = new Map()
	let nextFrame = 0
	const view = {
		getComputedStyle: node => ({ position: node.style.position || "static", left: "auto", overflowX: "visible" }),
		requestAnimationFrame: callback => { frames.set(++nextFrame, callback); return nextFrame },
		cancelAnimationFrame: id => frames.delete(id),
		MutationObserver: class { observe() {} disconnect() {} },
		innerHeight: 900,
	}
	/** Runs the callbacks queued for the next animation frame. */
	function paint() { const queued = [...frames.values()]; frames.clear(); for (const callback of queued) callback(performance.now()); return queued.length }
	const doc = { defaultView: view, createElement: tag => new Element(doc, tag) }
	doc.body = new Element(doc, "body")
	const root = new Element(doc, "div")
	const table = new Element(doc, "table")
	table.dataset.columnLayout = "results"
	table.setAttribute("data-column-order", "")
	const row = new Element(doc, "tr")
	const cells = new Map(labels.map(label => { const th = new Element(doc, "th"); th.text = label; th.natural = 100; return [label, th] }))
	for (const th of cells.values()) row.append(th)
	Object.defineProperty(row, "cells", { get: () => row.children })
	row.parentElement = table
	table.tHead = { rows: [row] }
	Object.defineProperty(table, "rows", { get: () => ({ length: rowCount + 1 }) })
	root.append(table)
	const layout = { widths: {}, order: {} }
	const controller = attachColumnLayout(root, layout)
	/** Re-renders the header in the saved order, moving the same cells as Vue's keyed patch does. */
	function render() {
		const ordered = orderColumns(labels.map(label => ({ label })), layout.order.results)
		row.children = ordered.map(column => cells.get(column.label))
		controller.sync()
	}
	function press(label) {
		const handle = cells.get(label).querySelector(":scope > .report-col-resize")
		root.fire("pointerdown", { button: 0, clientX: 500, pointerId: 1, target: handle, preventDefault() {}, stopPropagation() {} })
		return { move: delta => handle.fire("pointermove", { clientX: 500 + delta }), release: () => { handle.fire("pointerup", {}); controller.sync() } }
	}
	function resize(label, delta) {
		const drag = press(label)
		drag.move(delta)
		drag.release()
	}
	const widths = () => Object.fromEntries([...cells].map(([label, th]) => [label, th.getBoundingClientRect().width]))
	const order = () => row.children.map(th => th.text)
	return { layout, render, resize, press, paint, widths, order, doc }
}

test("after a column moves, each resize handle still resizes its own column", () => {
	const page = createPage(["Item", "Item Variant", "Item Group", "Warehouse", "Lot"])
	page.resize("Item Variant", 60)
	assert.deepEqual(page.widths(), { Item: 100, "Item Variant": 160, "Item Group": 100, Warehouse: 100, Lot: 100 })

	page.layout.order = { results: ["Item", "Item Group", "Item Variant", "Warehouse", "Lot"] }
	page.render()
	assert.deepEqual(page.order(), ["Item", "Item Group", "Item Variant", "Warehouse", "Lot"])
	assert.deepEqual(page.widths(), { Item: 100, "Item Variant": 160, "Item Group": 100, Warehouse: 100, Lot: 100 })

	page.resize("Item Group", 30)
	assert.deepEqual(page.widths(), { Item: 100, "Item Variant": 160, "Item Group": 130, Warehouse: 100, Lot: 100 })
	page.resize("Item Variant", -40)
	assert.deepEqual(page.widths(), { Item: 100, "Item Variant": 120, "Item Group": 130, Warehouse: 100, Lot: 100 })
	assert.deepEqual(page.layout.widths, { results: { "Item Variant": 120, "Item Group": 130 } })
})

test("widths follow their columns through a move to first and to last", () => {
	const page = createPage(["Lot", "Colour", "Total"])
	page.resize("Colour", -50)
	page.resize("Total", 20)
	page.layout.order = { results: ["Total", "Lot", "Colour"] }
	page.render()
	assert.deepEqual(page.widths(), { Lot: 100, Colour: 50, Total: 120 })
	page.layout.order = { results: ["Lot", "Total", "Colour"] }
	page.render()
	page.resize("Colour", 10)
	page.resize("Lot", 5)
	assert.deepEqual(page.widths(), { Lot: 105, Colour: 60, Total: 120 })
	assert.deepEqual(page.layout.widths, { results: { Colour: 60, Total: 120, Lot: 105 } })
})

test("a drag applies the latest width once per frame and saves it only on release", () => {
	const page = createPage(["Item", "Colour", "Total"])
	page.paint()
	const drag = page.press("Item")
	for (const delta of [5, 10, 15, 20]) drag.move(delta)
	assert.equal(page.widths().Item, 100, "nothing moves between frames")
	assert.equal(page.paint(), 1, "four pointer moves queue one frame")
	assert.equal(page.widths().Item, 120)
	drag.move(-200)
	page.paint()
	assert.equal(page.widths().Item, 30, "the minimum width holds")
	assert.deepEqual(page.layout.widths, {}, "nothing is saved mid-drag")
	drag.move(35)
	drag.release()
	assert.deepEqual(page.layout.widths, { results: { Item: 135 } })
	assert.deepEqual(page.widths(), { Item: 135, Colour: 100, Total: 100 })
})

test("a large table previews the drag with a guide line and resizes once on release", () => {
	const page = createPage(["Item", "Colour", "Total"], { rowCount: LIVE_RESIZE_CELL_LIMIT })
	const drag = page.press("Colour")
	drag.move(40)
	page.paint()
	const guide = page.doc.body.children.find(node => node.classList.contains("report-col-resize-guide"))
	assert.equal(guide?.dataset.width, "140px")
	assert.deepEqual(page.widths(), { Item: 100, Colour: 100, Total: 100 }, "the table is not relaid out mid-drag")
	drag.release()
	assert.equal(page.doc.body.children.includes(guide), false)
	assert.deepEqual(page.widths(), { Item: 100, Colour: 140, Total: 100 })
	assert.deepEqual(page.layout.widths, { results: { Colour: 140 } })
})
