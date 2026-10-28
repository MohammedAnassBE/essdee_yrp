import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const { assertCanvasFits, CAPTURE_PRINT_CLASS, captureElementImage, expandForCapture, getCapturePixelRatio, getCaptureSize, getInputText, TOO_LARGE_MESSAGE } = await import("../src/components/reports/copyElementAsImage.js")

const ownerDocument = { createElement: tag => node({ tag }) }

function node({ overflow = "visible", size = [100, 100], content = size, placeholder = null, tag = "div", textOverflow = "clip", clip = "auto", hidden = false, rect = [0, 0, ...size], value = "" } = {}) {
	const attributes = placeholder === null ? {} : { placeholder }
	const style = {
		cssText: "height: 40px;",
		setProperty(property, value, priority) { this.cssText += ` ${property}: ${value} !${priority};` },
	}
	const classes = new Set()
	const element = {
		classList: { add: name => classes.add(name), remove: name => classes.delete(name), contains: name => classes.has(name) },
		innerText: "Report",
		ownerDocument, parentNode: null, value, textContent: "",
		tagName: tag.toUpperCase(), tag, overflow, textOverflow, clip, hidden, style, children: [],
		clientWidth: size[0], clientHeight: size[1], scrollWidth: content[0], scrollHeight: content[1], offsetWidth: size[0],
		getBoundingClientRect: () => ({ left: rect[0], top: rect[1], width: rect[2], height: rect[3], right: rect[0] + rect[2], bottom: rect[1] + rect[3] }),
		getAttribute: name => attributes[name] ?? null,
		setAttribute: (name, value) => { attributes[name] = value },
		removeAttribute: name => { delete attributes[name] },
		insertBefore(child, before) { child.parentNode = this; this.children.splice(this.children.indexOf(before), 0, child) },
		remove() { this.parentNode?.children.splice(this.parentNode.children.indexOf(this), 1); this.parentNode = null },
		querySelectorAll(selector) {
			const all = this.children.flatMap(child => [child, ...child.querySelectorAll("*")])
			if (selector === "*") return all
			if (selector === "table" || selector === "caption") return all.filter(child => child.tag === selector)
			if (selector.includes("input")) return all.filter(child => child.tag === "input")
			return all.filter(child => child.hidden)
		},
	}
	return element
}
const view = { getComputedStyle: element => ({ overflowX: element.overflow, overflowY: element.overflow, textOverflow: element.textOverflow, clip: element.clip, clipPath: "none", position: element.position ?? "static", display: "block", marginTop: "4px" }) }

test("copy expands clipping scroll containers, swaps cell inputs for their text and restores the page", () => {
	const root = node({ overflow: "hidden" })
	const frame = node({ overflow: "auto", size: [800, 110], content: [1200, 420] })
	const quiet = node({ overflow: "auto", size: [200, 50], content: [200, 50] })
	const remarks = node({ tag: "input", placeholder: "Remarks", value: "Short 2 pcs" })
	frame.children.push(remarks)
	remarks.parentNode = frame
	root.children.push(frame, quiet)
	// The frame grows the shell once expanded, so the outer box clips only after the inner pass.
	frame.style.setProperty = function (property, value, priority) {
		this.cssText += ` ${property}: ${value} !${priority};`
		root.scrollHeight = 520
	}
	frame.style.setProperty = frame.style.setProperty.bind(frame.style)

	const restore = expandForCapture(root, view)
	assert.match(frame.style.cssText, /overflow: visible !important; max-height: none !important; max-width: none !important; height: auto !important; scrollbar-gutter: auto !important;/)
	assert.match(root.style.cssText, /overflow: visible !important/)
	assert.equal(quiet.style.cssText, "height: 40px;")
	// A cloned input renders taller than on screen and overflows its pinned row height, so it becomes plain text.
	assert.match(remarks.style.cssText, /display: none !important/)
	const [text] = frame.children
	assert.equal(text.tag, "span")
	assert.equal(text.textContent, "Short 2 pcs")
	assert.equal(text.style.cssText, "display: inline-block; width: 100px;")

	restore()
	for (const element of [root, frame, quiet, remarks]) assert.equal(element.style.cssText, "height: 40px;")
	assert.deepEqual(frame.children, [remarks], "the text stand-in is removed")
})

test("copy lifts table captions out of the table height so cloned rows keep their on-screen height", () => {
	const root = node()
	const table = node({ tag: "table" })
	const caption = node({ tag: "caption", size: [800, 36] })
	const srCaption = node({ tag: "caption", size: [1, 1], clip: "rect(0px, 0px, 0px, 0px)" })
	table.children.push(caption)
	caption.parentNode = table
	root.children.push(table, srCaption)
	const restore = expandForCapture(root, view)
	assert.match(table.style.cssText, /position: relative !important; margin-top: 40px !important;/)
	assert.match(caption.style.cssText, /position: absolute !important; top: -36px !important; left: 0 !important; width: 100% !important;/)
	assert.equal(srCaption.style.cssText, "height: 40px;", "a screen-reader caption is left alone")
	restore()
	for (const element of [table, caption]) assert.equal(element.style.cssText, "height: 40px;")
})

test("copy widens an overflowing root to its widest table and restores it", () => {
	const root = node({ overflow: "visible", size: [600, 100], content: [940, 100] })
	const restore = expandForCapture(root, view)
	assert.match(root.style.cssText, /width: max-content !important; min-width: 600px !important; max-width: none !important;/)
	restore()
	assert.equal(root.style.cssText, "height: 40px;")

	const narrow = node()
	expandForCapture(narrow, view)
	assert.equal(narrow.style.cssText, "height: 40px;", "a root that fits keeps its width")
})

test("copy wraps clipped ellipsis text instead of letting it run over the next cell", () => {
	const root = node()
	const cell = node({ overflow: "hidden", size: [120, 30], content: [300, 30], textOverflow: "ellipsis" })
	root.children.push(cell)
	const restore = expandForCapture(root, view)
	assert.match(cell.style.cssText, /max-width: none !important;.*white-space: normal !important; overflow-wrap: anywhere !important; text-overflow: clip !important;/)
	restore()
	assert.equal(cell.style.cssText, "height: 40px;")
})

test("copy skips visually hidden screen-reader text", () => {
	const root = node()
	const srOnly = node({ overflow: "hidden", size: [1, 1], content: [60, 20], clip: "rect(0px, 0px, 0px, 0px)" })
	root.children.push(srOnly)
	expandForCapture(root, view)
	assert.equal(srOnly.style.cssText, "height: 40px;")
})

test("copy hides [data-capture-hide] and caller selectors, then restores them", () => {
	const root = node()
	const filters = node({ hidden: true })
	const filterInput = node({ tag: "input", placeholder: "Filter Lot" })
	root.children.push(filters, filterInput)
	filterInput.parentNode = root
	const restore = expandForCapture(root, view, { hide: [".report-shell__filters"] })
	assert.match(filters.style.cssText, /display: none !important/)
	assert.match(filterInput.style.cssText, /display: none !important/, "header filter inputs render as plain text")
	restore()
	assert.equal(filters.style.cssText, "height: 40px;")
	assert.deepEqual(root.children, [filters, filterInput])
})

test("copy refuses an image the browser cannot draw instead of shrinking it", () => {
	assert.doesNotThrow(() => assertCanvasFits(1600, 30_000))
	assert.throws(() => assertCanvasFits(1600, 40_000), { message: TOO_LARGE_MESSAGE })
	assert.throws(() => assertCanvasFits(12_000, 30_000), { message: TOO_LARGE_MESSAGE })
})

test("copy captures at 2x and steps down to 1.5x or 1x for large reports", () => {
	assert.equal(getCapturePixelRatio(1400, 2_000), 2)
	assert.equal(getCapturePixelRatio(1400, 5_000), 1.5)
	assert.equal(getCapturePixelRatio(1400, 11_500), 1, "a 16 MP report keeps today's 1x speed")
	assert.equal(getCapturePixelRatio(1600, 30_000), 1)
	assert.throws(() => getCapturePixelRatio(1600, 40_000), { message: TOO_LARGE_MESSAGE })
})

test("copy renders in print mode at the chosen pixel ratio, then removes print mode", async () => {
	const root = node({ size: [800, 600] })
	let options = null
	const render = (element, renderOptions) => {
		assert.ok(element.classList.contains(CAPTURE_PRINT_CLASS), "print mode is on while rendering")
		options = renderOptions
		return "png"
	}
	const result = await captureElementImage(root, { view, render })
	assert.deepEqual(result, { blob: "png", text: "Report" })
	assert.equal(options.pixelRatio, 2)
	assert.equal(options.backgroundColor, "#ffffff")
	assert.equal(root.classList.contains(CAPTURE_PRINT_CLASS), false)
})

test("copy removes print mode and restores the page when the render fails", async () => {
	const root = node({ overflow: "auto", size: [800, 110], content: [800, 420] })
	const render = () => { throw new Error("render failed") }
	await assert.rejects(captureElementImage(root, { view, render }), { message: "render failed" })
	assert.equal(root.classList.contains(CAPTURE_PRINT_CLASS), false)
	assert.equal(root.style.cssText, "height: 40px;")

	const huge = node({ size: [1600, 40_000] })
	await assert.rejects(captureElementImage(huge, { view, render }), { message: TOO_LARGE_MESSAGE })
	assert.equal(huge.classList.contains(CAPTURE_PRINT_CLASS), false)
})

test("copy hides the inline filter row and its empty state; restore brings them back", () => {
	const source = readFileSync(new URL("../src/components/reports/ReportFilterRow.vue", import.meta.url), "utf8")
	assert.match(source, /class="report-filter-row" data-export-ignore data-capture-hide/)
	assert.match(source, /class="report-filter-row__empty" data-export-ignore data-capture-hide/)
	assert.match(source, /<td class="report-cell--last-column" :colspan/, "the empty-state cell has no extra right border")

	const root = node()
	const filterRow = node({ hidden: true, tag: "tr" })
	root.children.push(filterRow)
	const restore = expandForCapture(root, view)
	assert.match(filterRow.style.cssText, /visibility: collapse !important/, "a collapsed row keeps the on-screen column widths")
	restore()
	assert.equal(filterRow.style.cssText, "height: 40px;")
})

test("copy bounds cover the root border and every table, even one spilling past the root", () => {
	const root = node({ size: [1000, 600], content: [998, 598], rect: [10, 20, 1000, 600] })
	const narrow = node({ tag: "table", rect: [26, 40, 900, 200] })
	const wide = node({ tag: "table", rect: [26, 260, 1600.4, 500] })
	const hidden = node({ tag: "table", rect: [0, 0, 0, 0] })
	root.children.push(narrow, wide, hidden)
	assert.deepEqual(getCaptureSize(root), { width: 1617, height: 740 })
	assert.deepEqual(getCaptureSize(node({ size: [800, 400], content: [800, 900] })), { width: 800, height: 900 })
})

test("copy renders the full multi-table bounds and restores the filter row on error", async () => {
	const root = node({ size: [800, 600] })
	const filterRow = node({ hidden: true, tag: "tr" })
	root.children.push(filterRow, node({ tag: "table", rect: [0, 0, 1200, 900] }))
	let options = null
	await captureElementImage(root, { view, render: (_, renderOptions) => { options = renderOptions; assert.match(filterRow.style.cssText, /visibility: collapse/); return "png" } })
	assert.deepEqual([options.width, options.height], [1200, 900])
	await assert.rejects(captureElementImage(root, { view, render: () => { throw new Error("render failed") } }), { message: "render failed" })
	assert.equal(filterRow.style.cssText, "height: 40px;")
})

test("copy prints a checkbox cell as Yes or No, never its constant \"on\" value", () => {
	assert.equal(getInputText({ type: "checkbox", value: "on", checked: true }), "Yes")
	assert.equal(getInputText({ type: "checkbox", value: "on", checked: false }), "No")
	assert.equal(getInputText({ type: "text", value: "Short 2 pcs" }), "Short 2 pcs")
})
