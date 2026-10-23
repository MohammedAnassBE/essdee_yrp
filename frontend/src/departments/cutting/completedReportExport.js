import { copyElementAsImage } from "../../components/reports/copyElementAsImage.js"

const UNCLIPPED_TEXT = { overflow: "visible", textOverflow: "clip", whiteSpace: "normal", overflowWrap: "anywhere" }

/** Live width plus the widest table overflow, so every group, border and header grows with its table. */
export function getCompletedReportExportWidth(source) {
	const overflows = Array.from(source.querySelectorAll(".completed-report__table-wrap"), (wrap) => wrap.scrollWidth - wrap.clientWidth)
	return Math.ceil(Math.max(source.offsetWidth, source.clientWidth) + Math.max(0, ...overflows))
}

/** Off-screen, unclipped copy of a Completed Cut Quantity capture; remove `host` when done. */
export function createCompletedReportExport(source, documentRef = document) {
	if (!source) throw new Error("Nothing available to copy.")
	const exportWidth = getCompletedReportExportWidth(source)
	const clone = source.cloneNode(true)
	clone.classList.add("completed-report-capture--export")
	Object.assign(clone.style, { width: `${exportWidth}px`, maxWidth: "none" })
	clone.querySelectorAll(".completed-report__sr-only").forEach((element) => element.remove())
	clone.querySelectorAll("[id]").forEach((element) => element.removeAttribute("id"))
	clone.querySelectorAll("[aria-labelledby]").forEach((element) => element.removeAttribute("aria-labelledby"))
	clone.querySelectorAll(".completed-report__table-wrap, .completed-report__group").forEach((element) => {
		Object.assign(element.style, { overflow: "visible", maxWidth: "none" })
	})
	clone.querySelectorAll(".completed-report__meta-item strong").forEach((element) => Object.assign(element.style, UNCLIPPED_TEXT))

	const host = documentRef.createElement("div")
	host.className = "completed-report-export-host"
	host.setAttribute("aria-hidden", "true")
	Object.assign(host.style, { position: "fixed", left: "-100000px", top: "0", width: `${exportWidth}px`, pointerEvents: "none" })
	host.appendChild(clone)
	;(documentRef.querySelector(".app-shell") || documentRef.body).appendChild(host)
	return { element: clone, host }
}

/** Copies every group, row and column of the report, independent of the dialog's size or scroll. */
export async function copyCompletedReportImage(source, view = window, copy = copyElementAsImage) {
	const exportCapture = createCompletedReportExport(source, view.document)
	try {
		await new Promise((resolve) => view.requestAnimationFrame(resolve))
		await copy(exportCapture.element)
	} finally {
		exportCapture.host.remove()
	}
}
