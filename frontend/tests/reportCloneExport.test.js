import assert from "node:assert/strict"
import test from "node:test"

import { copyCompletedReportImage, createCompletedReportExport } from "../src/departments/cutting/completedReportExport.js"
import { copyLotOcrImage, createLotOcrExport } from "../src/departments/sales/lotOcrExport.js"

class FakeElement {
	constructor(tag, { classes = [], attributes = {}, size = {}, children = [] } = {}) {
		Object.assign(this, { tag, attributes: { ...attributes }, style: {}, dataset: {}, parent: null, children: [] })
		this.classes = new Set(classes)
		Object.assign(this, { offsetWidth: 0, clientWidth: 0, scrollWidth: 0, ...size })
		this.classList = { add: (name) => this.classes.add(name) }
		children.forEach((child) => this.appendChild(child))
	}
	appendChild(child) { child.parent = this; this.children.push(child); return child }
	remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); this.parent = null }
	setAttribute(name, value) { this.attributes[name] = value }
	removeAttribute(name) { delete this.attributes[name] }
	descendants() { return this.children.flatMap((child) => [child, ...child.descendants()]) }
	matchesSimple(selector) {
		if (selector.startsWith(".")) return this.classes.has(selector.slice(1))
		if (selector.startsWith("[")) return selector.slice(1, -1) in this.attributes
		return this.tag === selector
	}
	matches(selector) {
		const [ancestor, own] = selector.trim().split(/\s+/).length > 1 ? selector.trim().split(/\s+/) : [null, selector.trim()]
		if (!this.matchesSimple(own)) return false
		if (!ancestor) return true
		for (let node = this.parent; node; node = node.parent) if (node.matchesSimple(ancestor)) return true
		return false
	}
	querySelectorAll(selectors) { return this.descendants().filter((node) => selectors.split(",").some((selector) => node.matches(selector))) }
	querySelector(selectors) { return this.querySelectorAll(selectors)[0] || null }
	cloneNode() {
		const copy = new FakeElement(this.tag, { classes: [...this.classes], attributes: this.attributes, size: { offsetWidth: this.offsetWidth, clientWidth: this.clientWidth, scrollWidth: this.scrollWidth } })
		this.children.forEach((child) => copy.appendChild(child.cloneNode()))
		return copy
	}
}

function fakeDocument() {
	const body = new FakeElement("body")
	return { body, createElement: (tag) => new FakeElement(tag), querySelector: () => null }
}

function completedSource() {
	const tableWrap = (scrollWidth) => new FakeElement("div", { classes: ["completed-report__table-wrap"], attributes: { "aria-labelledby": "h" }, size: { clientWidth: 600, scrollWidth } })
	const group = (scrollWidth) => new FakeElement("section", { classes: ["completed-report__group"], children: [
		new FakeElement("h3", { classes: ["completed-report__sr-only"], attributes: { id: "h" } }),
		tableWrap(scrollWidth),
	] })
	const meta = new FakeElement("header", { classes: ["completed-report__meta"], children: [
		new FakeElement("div", { classes: ["completed-report__meta-item"], children: [new FakeElement("strong")] }),
	] })
	return new FakeElement("div", { classes: ["completed-report-capture"], size: { offsetWidth: 606, clientWidth: 606 }, children: [
		new FakeElement("article", { children: [meta, group(900), group(1250)] }),
	] })
}

test("completed cut quantity export widens every box by the widest table overflow", () => {
	const documentRef = fakeDocument()
	const source = completedSource()
	const { element, host } = createCompletedReportExport(source, documentRef)
	assert.equal(element.style.width, "1256px")
	assert.equal(host.style.width, "1256px")
	assert.equal(host.parent, documentRef.body)
	assert.equal(element.querySelectorAll(".completed-report__sr-only").length, 0)
	assert.equal(element.querySelectorAll("[id],[aria-labelledby]").length, 0)
	for (const box of element.querySelectorAll(".completed-report__table-wrap,.completed-report__group")) assert.equal(box.style.overflow, "visible")
	assert.deepEqual(element.querySelector(".completed-report__meta-item strong").style, { overflow: "visible", textOverflow: "clip", whiteSpace: "normal", overflowWrap: "anywhere" })
	assert.equal(source.querySelectorAll(".completed-report__sr-only").length, 2, "live dialog is untouched")
	assert.deepEqual(source.querySelector(".completed-report__table-wrap").style, {})
})

test("completed cut quantity copy captures the clone and always removes it", async () => {
	const documentRef = fakeDocument()
	const view = { document: documentRef, requestAnimationFrame: (callback) => callback() }
	let captured
	await copyCompletedReportImage(completedSource(), view, async (element) => { captured = element; assert.equal(documentRef.body.children.length, 1) })
	assert.ok(captured.classes.has("completed-report-capture--export"))
	assert.equal(documentRef.body.children.length, 0)
	await assert.rejects(copyCompletedReportImage(completedSource(), view, async () => { throw new Error("denied") }), /denied/)
	assert.equal(documentRef.body.children.length, 0)
	await assert.rejects(copyCompletedReportImage(null, view), /Nothing available to copy/)
})

function lotOcrSource(scrollWidth) {
	return new FakeElement("div", { classes: ["ppo-lot-ocr__capture"], size: { offsetWidth: 702, clientWidth: 700 }, children: [
		new FakeElement("header", { classes: ["ppo-lot-ocr__context"], children: [new FakeElement("div", { children: [new FakeElement("strong")] })] }),
		new FakeElement("div", { classes: ["ppo-lot-ocr__table-wrap"], size: { clientWidth: 700, scrollWidth } }),
	] })
}

test("lot OCR export includes the border and every size column, and unclips the context values", () => {
	const { element } = createLotOcrExport(lotOcrSource(1400), fakeDocument())
	assert.equal(element.style.width, "1402px")
	assert.equal(element.style.overflow, "visible")
	assert.equal(element.querySelector(".ppo-lot-ocr__table-wrap").style.overflow, "visible")
	assert.equal(element.querySelector(".ppo-lot-ocr__context strong").style.whiteSpace, "normal")
	assert.equal(createLotOcrExport(lotOcrSource(700), fakeDocument()).element.style.width, "702px")
})

test("lot OCR copy removes the off-screen clone after capture", async () => {
	const documentRef = fakeDocument()
	const view = { document: documentRef, requestAnimationFrame: (callback) => callback() }
	let captured
	await copyLotOcrImage(lotOcrSource(1400), view, async (element) => { captured = element })
	assert.equal(captured.dataset.ocrExport, "true")
	assert.equal(documentRef.body.children.length, 0)
})
