import { copyElementAsImage } from "../../components/reports/copyElementAsImage.js"

const UNCLIPPED_TEXT = { overflow: "visible", textOverflow: "clip", whiteSpace: "normal", overflowWrap: "anywhere" }

/** Live width plus the table's horizontal overflow, so the border and context header grow with the table. */
export function getLotOcrExportWidth(source) {
	const wrap = source.querySelector(".ppo-lot-ocr__table-wrap")
	const overflow = wrap ? wrap.scrollWidth - wrap.clientWidth : 0
	return Math.ceil(Math.max(source.offsetWidth, source.clientWidth) + Math.max(0, overflow))
}

/** Off-screen, unclipped copy of the Lot OCR capture; remove `host` when done. */
export function createLotOcrExport(source, documentRef = document) {
	if (!source) throw new Error("Nothing available to copy.")
	const exportWidth = getLotOcrExportWidth(source)
	const clone = source.cloneNode(true)
	clone.dataset.ocrExport = "true"
	Object.assign(clone.style, { width: `${exportWidth}px`, maxWidth: "none", overflow: "visible" })
	clone.querySelectorAll(".ppo-lot-ocr__table-wrap").forEach((element) => {
		Object.assign(element.style, { width: "100%", maxWidth: "none", maxHeight: "none", overflow: "visible" })
	})
	clone.querySelectorAll(".ppo-lot-ocr__context strong").forEach((element) => Object.assign(element.style, UNCLIPPED_TEXT))

	const host = documentRef.createElement("div")
	host.setAttribute("aria-hidden", "true")
	Object.assign(host.style, { position: "fixed", left: "-100000px", top: "0", width: `${exportWidth}px`, pointerEvents: "none" })
	host.appendChild(clone)
	documentRef.body.appendChild(host)
	return { element: clone, host }
}

/** Copies every process row and size column, independent of the dialog's size or scroll. */
export async function copyLotOcrImage(source, view = window, copy = copyElementAsImage) {
	const exportCapture = createLotOcrExport(source, view.document)
	try {
		await new Promise((resolve) => view.requestAnimationFrame(resolve))
		await copy(exportCapture.element)
	} finally {
		exportCapture.host.remove()
	}
}
