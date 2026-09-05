import { ref } from "vue"

export const MAX_COLOUR_COLUMNS = 6

export function isMultiColour(row) {
	return row.kind === "knitting" && !row.reference_routed && row.has_colour
		&& (row.colour_options || []).length > 0
		&& row.colour_options.length <= MAX_COLOUR_COLUMNS
}

export function createFabricEntries(context) {
	return (context.rows || []).map((row) => {
		const multiColour = isMultiColour(row)
		const entry = {
			colour: multiColour ? null : row.greige_colour || null,
			yarnQty: null,
			qtys: (row.qty_rows || []).map((qr) => qr.prefill ?? null),
			colourQtys: {},
		}
		if (multiColour) {
			entry.qtys = (row.qty_rows || []).map(() => null)
			for (const colour of row.colour_options) {
				entry.colourQtys[colour] = (row.qty_rows || []).map((qr) =>
					colour === row.greige_colour ? qr.prefill ?? null : null,
				)
			}
		}
		if (row.kind === "knitting") {
			const quantities = multiColour ? Object.values(entry.colourQtys).flat() : entry.qtys
			const total = quantities.reduce((sum, qty) => sum + (Number(qty) || 0), 0)
			entry.yarnQty = Math.round(total / (Number(row.ratio) || 1) * 1000) / 1000
		}
		return entry
	})
}

// Commit a context and its editable quantities together, only after a successful
// request. A failed Fill must not erase the operator's existing data entry.
export function useFabricDeliverableContext(fetchContext) {
	const ctx = ref(null)
	const entries = ref([])
	const loading = ref(false)
	let generation = 0

	function invalidate() {
		generation++
		loading.value = false
	}

	async function load(workOrder, sourceProcess = null, { reset = false } = {}) {
		const request = ++generation
		loading.value = true
		if (reset) {
			ctx.value = null
			entries.value = []
		}
		try {
			const result = await fetchContext({ work_order: workOrder, source_process: sourceProcess })
			if (request !== generation) return false
			const next = result || { is_fabric_process: false, rows: [] }
			const nextEntries = createFabricEntries(next)
			ctx.value = next
			entries.value = nextEntries
			return true
		} catch (error) {
			if (request === generation) throw error
			return false
		} finally {
			if (request === generation) loading.value = false
		}
	}

	return { ctx, entries, loading, load, invalidate }
}
