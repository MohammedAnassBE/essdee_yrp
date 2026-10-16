<template>
	<aside class="lotwise-totals" aria-label="Lotwise totals">
		<header>
			<span>Live summary</span>
			<h2>Costing totals</h2>
		</header>
		<div class="lotwise-totals__items">
			<div v-for="metric in metrics" :key="metric.fieldname" class="lotwise-totals__metric">
				<span>{{ metric.label }}</span>
				<strong>{{ formatValue(values[metric.fieldname], metric.type) }}</strong>
			</div>
		</div>
	</aside>
</template>

<script setup>
const props = defineProps({
	values: { type: Object, default: () => ({}) },
})

const metrics = [
	{ fieldname: "total_qty", label: "Total Qty", type: "number" },
	{ fieldname: "total_selling_value", label: "Total Selling Value", type: "currency" },
	{ fieldname: "total_weight", label: "Total Weight", type: "number" },
	{ fieldname: "total_cloth_value", label: "Total Cloth Value", type: "currency" },
	{ fieldname: "cloth_value_per_piece", label: "Cloth Value / Piece", type: "currency" },
	{ fieldname: "production_cost_per_piece", label: "Production Cost / Piece", type: "currency" },
	{ fieldname: "production_cost", label: "Production Cost", type: "currency" },
	{ fieldname: "total_trade_discount", label: "Trade Discount", type: "currency" },
	{ fieldname: "total_other_cost", label: "Other Cost", type: "currency" },
	{ fieldname: "gst_value", label: "GST Value", type: "currency" },
	{ fieldname: "cost_price", label: "Cost Price", type: "currency" },
	{ fieldname: "avg_cost_per_piece", label: "Avg Cost / Piece", type: "currency" },
	{ fieldname: "avg_rate_per_piece", label: "Avg Rate / Piece", type: "currency" },
	{ fieldname: "profit", label: "Profit", type: "currency" },
	{ fieldname: "profit_percent", label: "Profit % (Markup)", type: "percent" },
	{ fieldname: "profit_percent_markdown", label: "Profit % (Markdown)", type: "percent" },
]

function formatValue(value, type) {
	const number = Number(value)
	const formatted = (Number.isFinite(number) ? number : 0).toLocaleString("en-IN", {
		maximumFractionDigits: 2,
	})
	if (type === "currency") return `₹${formatted}`
	if (type === "percent") return `${formatted}%`
	return formatted
}
</script>

<style scoped>
.lotwise-totals {
	position: sticky;
	top: calc(var(--erp-shell-header-height) + 12px);
	min-width: 0;
	align-self: start;
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-sm);
}

.lotwise-totals header {
	padding: 13px 14px 11px;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.lotwise-totals header span {
	color: var(--erp-accent-hover);
	font-size: var(--erp-font-size-min);
	font-weight: 760;
	letter-spacing: 0.05em;
	text-transform: uppercase;
}

.lotwise-totals h2 {
	margin: 3px 0 0;
	color: var(--erp-text);
	font-size: var(--erp-font-size-section);
}

.lotwise-totals__items {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
}

.lotwise-totals__metric {
	display: grid;
	min-width: 0;
	gap: 3px;
	padding: 10px 12px;
	border-right: 1px solid var(--erp-border-subtle);
	border-bottom: 1px solid var(--erp-border-subtle);
}

.lotwise-totals__metric:nth-child(2n) {
	border-right: 0;
}

.lotwise-totals__metric span {
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 680;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.lotwise-totals__metric strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 0.92rem;
	font-variant-numeric: tabular-nums;
	text-overflow: ellipsis;
	white-space: nowrap;
}

@media (max-width: 1120px) {
	.lotwise-totals {
		position: static;
	}

	.lotwise-totals__items {
		grid-template-columns: repeat(4, minmax(0, 1fr));
	}

	.lotwise-totals__metric:nth-child(2n) {
		border-right: 1px solid var(--erp-border-subtle);
	}

	.lotwise-totals__metric:nth-child(4n) {
		border-right: 0;
	}
}

@media (max-width: 720px) {
	.lotwise-totals__items {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.lotwise-totals__metric:nth-child(4n) {
		border-right: 1px solid var(--erp-border-subtle);
	}

	.lotwise-totals__metric:nth-child(2n) {
		border-right: 0;
	}
}
</style>
