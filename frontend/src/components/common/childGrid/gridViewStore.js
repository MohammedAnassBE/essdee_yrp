import { mergeGridView } from "./childGridColumns.js"

const GET_METHOD = "frappe.model.utils.user_settings.get"
const SAVE_METHOD = "frappe.model.utils.user_settings.save"

function parseSettings(raw) {
	const settings = typeof raw === "string" ? JSON.parse(raw || "{}") : raw || {}
	return settings && typeof settings === "object" && !Array.isArray(settings) ? settings : {}
}

/** Per-user child table columns in Frappe's own user settings: `<parent>.GridView[<child doctype>]`, shared with Desk. */
export function createGridViewStore({ read, write }) {
	const settings = new Map()

	async function load(parentDoctype, { fresh = false } = {}) {
		if (fresh || !settings.has(parentDoctype)) {
			settings.set(parentDoctype, read(GET_METHOD, { doctype: parentDoctype }).then(parseSettings))
		}
		try {
			return await settings.get(parentDoctype)
		} catch (error) {
			settings.delete(parentDoctype)
			throw error
		}
	}

	async function get(parentDoctype, childDoctype) {
		const entries = (await load(parentDoctype)).GridView?.[childDoctype]
		return Array.isArray(entries) && entries.length ? entries : null
	}

	async function save(parentDoctype, childDoctype, entries) {
		const current = await load(parentDoctype, { fresh: true })
		const gridView = mergeGridView(current, childDoctype, entries)
		await write(SAVE_METHOD, { doctype: parentDoctype, user_settings: JSON.stringify({ GridView: gridView }) })
		settings.set(parentDoctype, Promise.resolve({ ...current, GridView: gridView }))
	}

	return { get, save }
}
