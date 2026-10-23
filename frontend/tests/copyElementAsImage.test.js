import assert from "node:assert/strict"
import test from "node:test"

const { assertCanvasFits, expandForCapture, TOO_LARGE_MESSAGE } = await import("../src/components/reports/copyElementAsImage.js")

function node({ overflow = "visible", size = [100, 100], content = size, placeholder = null, tag = "div", textOverflow = "clip", clip = "auto", hidden = false } = {}) {
	const attributes = placeholder === null ? {} : { placeholder }
	const style = {
		cssText: "height: 40px;",
		setProperty(property, value, priority) { this.cssText += ` ${property}: ${value} !${priority};` },
	}
	const element = {
		tag, overflow, textOverflow, clip, hidden, style, children: [],
		clientWidth: size[0], clientHeight: size[1], scrollWidth: content[0], scrollHeight: content[1], offsetWidth: size[0],
		getAttribute: name => attributes[name] ?? null,
		setAttribute: (name, value) => { attributes[name] = value },
		removeAttribute: name => { delete attributes[name] },
		querySelectorAll(selector) {
			const all = this.children.flatMap(child => [child, ...child.querySelectorAll("*")])
			if (selector === "*") return all
			if (selector.includes("input")) return all.filter(child => child.tag === "input")
			return all.filter(child => child.hidden)
		},
	}
	return element
}
const view = { getComputedStyle: element => ({ overflowX: element.overflow, overflowY: element.overflow, textOverflow: element.textOverflow, clip: element.clip, clipPath: "none" }) }

test("copy expands clipping scroll containers, flattens cell inputs and restores the page", () => {
	const root = node({ overflow: "hidden" })
	const frame = node({ overflow: "auto", size: [800, 110], content: [1200, 420] })
	const quiet = node({ overflow: "auto", size: [200, 50], content: [200, 50] })
	const remarks = node({ tag: "input", placeholder: "Remarks" })
	frame.children.push(remarks)
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
	assert.match(remarks.style.cssText, /border: 0 !important; background: transparent !important/)
	assert.match(remarks.style.cssText, /width: 100px !important/)
	assert.equal(remarks.getAttribute("placeholder"), null)

	restore()
	for (const element of [root, frame, quiet, remarks]) assert.equal(element.style.cssText, "height: 40px;")
	assert.equal(remarks.getAttribute("placeholder"), "Remarks")
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
	const restore = expandForCapture(root, view, { hide: [".report-shell__filters"] })
	assert.match(filters.style.cssText, /display: none !important/)
	assert.match(filterInput.style.cssText, /border: 0 !important/, "header filter inputs render as plain text")
	restore()
	assert.equal(filters.style.cssText, "height: 40px;")
	assert.equal(filterInput.getAttribute("placeholder"), "Filter Lot")
})

test("copy refuses an image the browser cannot draw instead of shrinking it", () => {
	assert.doesNotThrow(() => assertCanvasFits(1600, 30_000))
	assert.throws(() => assertCanvasFits(1600, 40_000), { message: TOO_LARGE_MESSAGE })
	assert.throws(() => assertCanvasFits(12_000, 30_000), { message: TOO_LARGE_MESSAGE })
})
