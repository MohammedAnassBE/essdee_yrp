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
export const COPY_BLOCKED_MESSAGE = "The browser blocked the clipboard. Try Copy again or use Export."
export const COPY_AGAIN_MESSAGE = "The report image is ready. Click Copy again to put it on the clipboard."
// Browsers allow execCommand("copy") only for about 5 s after a click; a slower capture waits for the next click.
const PENDING_COPY_MS = 30_000
let pendingCopy = null

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
	if (document.activeElement instanceof HTMLElement) document.activeElement.blur()

	const restore = expandForCapture(element, window, { hide })
	let blob, text
	try {
		const width = Math.max(element.scrollWidth, element.clientWidth)
		const height = Math.max(element.scrollHeight, element.clientHeight)
		assertCanvasFits(width, height)
		// html-to-image otherwise shrinks anything past 16384px until it is unreadable.
		blob = await toBlob(element, { backgroundColor: "#ffffff", pixelRatio: 1, width, height, skipAutoScale: true })
		text = element.innerText || ""
	} finally {
		restore()
	}
	if (!blob) throw new Error(TOO_LARGE_MESSAGE)

	await writeImageToClipboard(blob, text, { key: element })
}

/** Finishes a capture that outlived the click; call synchronously from the next click. */
export function copyPendingImage(key, doc = globalThis.document, now = Date.now()) {
	const ready = pendingCopy?.key === key && now - pendingCopy.at < PENDING_COPY_MS ? pendingCopy : null
	pendingCopy = null
	return Boolean(ready) && copyWithCommand(doc, ready.data)
}

/** The async image clipboard needs HTTPS; on plain http copy the PNG as an HTML image through execCommand. */
export async function writeImageToClipboard(blob, text = "", { key = null, clipboard = globalThis.navigator?.clipboard, doc = globalThis.document } = {}) {
	if (clipboard?.write && typeof ClipboardItem !== "undefined") {
		await clipboard.write([new ClipboardItem({ "image/png": blob })])
		return
	}
	const data = { "text/html": `<img src="${await blobToDataUrl(blob)}" alt="Report">`, "text/plain": text }
	if (copyWithCommand(doc, data)) return
	if (key && globalThis.navigator?.userActivation?.isActive === false) {
		pendingCopy = { key, data, at: Date.now() }
		throw Object.assign(new Error(COPY_AGAIN_MESSAGE), { retryable: true })
	}
	throw new Error(COPY_BLOCKED_MESSAGE)
}

/** Writes `data` (mime type to string) to the clipboard from a synthetic copy event. */
export function copyWithCommand(doc, data) {
	let written = false
	const onCopy = event => {
		event.preventDefault()
		for (const [type, value] of Object.entries(data)) event.clipboardData.setData(type, value)
		written = true
	}
	doc.addEventListener("copy", onCopy, true)
	try {
		return Boolean(doc.execCommand("copy")) && written
	} catch {
		return false
	} finally {
		doc.removeEventListener("copy", onCopy, true)
	}
}

function blobToDataUrl(blob) {
	return new Promise((resolve, reject) => {
		const reader = new FileReader()
		reader.onload = () => resolve(reader.result)
		reader.onerror = () => reject(reader.error)
		reader.readAsDataURL(blob)
	})
}
