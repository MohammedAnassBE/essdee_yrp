import { copyText } from "../../departments/quality/qualityViews.js"

export function documentNameText(name) {
	return name == null ? "" : String(name)
}

/** Unsaved Frappe docs carry a local `new-<doctype>-…` name. */
export function isCopyableDocumentName(name) {
	const text = documentNameText(name)
	return Boolean(text) && !text.startsWith("new-")
}

export async function copyDocumentName(name, copy = copyText) {
	const text = documentNameText(name)
	if (!(await copy(text))) throw new Error(`Could not copy ${text}.`)
}
