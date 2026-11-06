const sum = (rows, key) => rows.reduce((total, row) => total + (Number(row?.[key]) || 0), 0)
const weighted = (amountKey, qtyKey) => (rows) => {
	const qty = sum(rows, qtyKey)
	return qty ? sum(rows, amountKey) / qty : null
}
const COSTING_TOTALS = { label: "costing_name", columns: { cost: { type: "currency", total: (rows) => sum(rows, "cost") } } }
const ADDITIONAL_COST_TOTALS = { label: "costing_name", columns: { total: { type: "currency", total: (rows) => sum(rows, "total") } } }

/** Footer config per Lotwise table; columns left out (per-piece values, per-kg rates, percentages) stay blank. */
export const LOTWISE_TABLE_TOTALS = {
	qty_rate_chart: {
		label: "size",
		columns: {
			qty: { type: "number", total: (rows) => sum(rows, "qty") },
			rate: { type: "currency", total: weighted("net_rate", "qty") },
			net_rate: { type: "currency", total: (rows) => sum(rows, "net_rate") },
		},
	},
	cloth_value: {
		label: "yarn",
		columns: {
			qty: { type: "number", total: (rows) => sum(rows, "qty") },
			total_cost: { type: "currency", total: weighted("net_rate", "qty") },
			net_rate: { type: "currency", total: (rows) => sum(rows, "net_rate") },
		},
	},
	piece_cloth_weight: { label: "size", columns: {} },
	cmt: COSTING_TOTALS,
	packing_materials: COSTING_TOTALS,
	trims: COSTING_TOTALS,
	trade_discounts: ADDITIONAL_COST_TOTALS,
	other_costs: ADDITIONAL_COST_TOTALS,
}

export function formatLotwiseValue(value, type) {
	const number = Number(value)
	const formatted = (Number.isFinite(number) ? number : 0).toLocaleString("en-IN", {
		maximumFractionDigits: 2,
	})
	if (type === "currency") return `₹${formatted}`
	if (type === "percent") return `${formatted}%`
	return formatted
}

/** Formatted footer cells for one Lotwise table, keyed by column fieldname. */
export function lotwiseTableTotals(table, rows) {
	const config = LOTWISE_TABLE_TOTALS[table]
	if (!config) throw new Error(`Totals for ${table} are not configured.`)
	const values = Array.isArray(rows) ? rows : []
	const footer = { [config.label]: "Total" }
	for (const [column, { type, total }] of Object.entries(config.columns)) {
		const value = total(values)
		footer[column] = value === null ? "" : formatLotwiseValue(value, type)
	}
	return footer
}
