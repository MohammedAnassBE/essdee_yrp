import { plural } from "./dashboardFormat.js"

/** Copies CSV text to the clipboard (textarea fallback) and confirms with a toast. */
export async function copyCsv(toast, text, count, unit) {
	try {
		await navigator.clipboard.writeText(text)
	} catch {
		const area = Object.assign(document.createElement("textarea"), { value: text })
		document.body.appendChild(area)
		area.select()
		document.execCommand("copy")
		area.remove()
	}
	toast.add({ severity: "success", summary: `Copied ${plural(count, unit)} as CSV`, life: 2200 })
}
