import { toBlob } from "html-to-image"

const SCROLLING = /auto|scroll|hidden/
const EXPANDED_STYLE = { overflow: "visible", "max-height": "none", "max-width": "none", height: "auto", "scrollbar-gutter": "auto" }
const UNCLIPPED_TEXT_STYLE = { "white-space": "normal", "overflow-wrap": "anywhere", "text-overflow": "clip" }
const PLAIN_INPUT_STYLE = { border: "0", background: "transparent", "box-shadow": "none", padding: "0" }
const PLAIN_INPUT_SELECTOR = "td input, td textarea, th input, th textarea"
// Chromium and Firefox refuse canvases past these sizes.
const MAX_CANVAS_SIDE = 32_767
const MAX_CANVAS_AREA = 268_000_000
export const TOO_LARGE_MESSAGE = "Report is too large to copy as one image. Narrow the filters or use Export."

function isVisuallyHidden(style) {
	return (style.clip && style.clip !== "auto") || (style.clipPath && style.clipPath !== "none")
}

function isClipping(element, style) {
	return SCROLLING.test(`${style.overflowX} ${style.overflowY}`) && !isVisuallyHidden(style)
		&& (element.scrollHeight > element.clientHeight || element.scrollWidth > element.clientWidth)
}

function applyStyle(element, style, saved) {
	const previous = element.style.cssText
	saved.push(() => { element.style.cssText = previous })
	for (const [property, value] of Object.entries(style)) element.style.setProperty(property, value, "important")
}

function flattenInputs(element, restore) {
	for (const input of element.querySelectorAll(PLAIN_INPUT_SELECTOR)) {
		const width = Math.max(input.clientWidth, input.scrollWidth)
		applyStyle(input, { ...PLAIN_INPUT_STYLE, ...(width ? { width: `${width}px` } : {}) }, restore)
		const placeholder = input.getAttribute("placeholder")
		if (placeholder === null) continue
		input.removeAttribute("placeholder")
		restore.push(() => input.setAttribute("placeholder", placeholder))
	}
}

/**
 * Lays `element` out at full size for an image capture: `hide` selectors and [data-capture-hide] drop out,
 * clipping boxes grow to their content, ellipsis text wraps, cell inputs render as plain text and the root
 * widens to its widest table. Returns a function that restores the page.
 */
export function expandForCapture(element, view = window, { hide = [] } = {}) {
	const restore = []
	for (const node of element.querySelectorAll(["[data-capture-hide]", ...hide].join(", "))) {
		applyStyle(node, { display: "none" }, restore)
	}
	// Innermost first, so an outer box clipped by an expanded child is caught too.
	for (const node of [element, ...element.querySelectorAll("*")].reverse()) {
		const style = view.getComputedStyle(node)
		if (!isClipping(node, style)) continue
		applyStyle(node, style.textOverflow === "ellipsis" ? { ...EXPANDED_STYLE, ...UNCLIPPED_TEXT_STYLE } : EXPANDED_STYLE, restore)
	}
	flattenInputs(element, restore)
	if (element.scrollWidth > element.clientWidth) {
		applyStyle(element, { width: "max-content", "min-width": `${element.offsetWidth}px`, "max-width": "none" }, restore)
	}
	return () => { for (const undo of restore.reverse()) undo() }
}

export function assertCanvasFits(width, height) {
	if (width > MAX_CANVAS_SIDE || height > MAX_CANVAS_SIDE || width * height > MAX_CANVAS_AREA) {
		throw new Error(TOO_LARGE_MESSAGE)
	}
}

export async function copyElementAsImage(element, { hide = [] } = {}) {
	if (!element) throw new Error("Nothing available to copy.")
	if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
		throw new Error("Image clipboard is not supported by this browser.")
	}

	if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

	const restore = expandForCapture(element, window, { hide })
	let blob
	try {
		const width = Math.max(element.scrollWidth, element.clientWidth)
		const height = Math.max(element.scrollHeight, element.clientHeight)
		assertCanvasFits(width, height)
		// html-to-image otherwise shrinks anything past 16384px until it is unreadable.
		blob = await toBlob(element, { backgroundColor: "#ffffff", pixelRatio: 1, width, height, skipAutoScale: true })
	} finally {
		restore()
	}
	if (!blob) throw new Error(TOO_LARGE_MESSAGE)

	await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })])
}
