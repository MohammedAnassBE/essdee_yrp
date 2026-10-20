<template>
	<section class="ppo-transfer-history erp-card" aria-labelledby="ppo-transfer-history-title">
		<header class="ppo-transfer-history__header">
			<div><span>QUANTITY TRANSFERS</span><h2 id="ppo-transfer-history-title">Transfer history</h2></div>
			<small>{{ rows.length }} {{ rows.length === 1 ? "movement" : "movements" }}</small>
		</header>
		<div v-if="rows.length" class="ppo-transfer-history__table-wrap">
			<table>
				<thead><tr><th>Movement</th><th>Production Order</th><th>Size</th><th class="is-number">Quantity</th><th>Requested</th><th>Approved</th><th>Reason</th></tr></thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row.transfer_reference || `${row.counterpart_production_order}-${index}`">
						<td data-label="Movement"><span class="ppo-transfer-history__movement" :class="movementClass(row.movement)">{{ row.movement || "—" }}</span></td>
						<td data-label="Production Order">
							<RouterLink v-if="row.counterpart_production_order" :to="{ name: viewRouteName, params: { productionOrderId: row.counterpart_production_order } }">{{ row.counterpart_production_order }}</RouterLink>
							<strong v-else>—</strong>
							<small v-if="row.transfer_reference">{{ row.transfer_reference }}</small>
						</td>
						<td data-label="Size"><strong>{{ row.size || "—" }}</strong></td>
						<td data-label="Quantity" class="is-number"><strong>{{ formatNumber(row.quantity) }}</strong><small>{{ formatNumber(row.quantity_before) }} → {{ formatNumber(row.quantity_after) }}</small></td>
						<td data-label="Requested"><strong><DocumentLink doctype="User" :name="row.requested_by" :label="row.requested_by || '—'" /></strong><small>{{ formatDateTime(row.requested_on) }}</small></td>
						<td data-label="Approved"><strong><DocumentLink doctype="User" :name="row.approved_by" :label="row.approved_by || '—'" /></strong><small>{{ formatDateTime(row.approved_on) }}</small></td>
						<td data-label="Reason"><span>{{ row.reason || "—" }}</span></td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="ppo-transfer-history__empty"><i class="pi pi-arrow-right-arrow-left" aria-hidden="true" /><div><strong>No quantity transfers</strong><span>This Production Order has no transfer history.</span></div></div>
	</section>
</template>

<script setup>
import DocumentLink from "../../components/common/DocumentLink.vue"
defineProps({
	rows: { type: Array, default: () => [] },
	viewRouteName: { type: String, default: "sales-production-order" },
})

function movementClass(movement) {
	return String(movement || "").toLowerCase() === "reduced" ? "is-reduced" : "is-added"
}
function formatNumber(value) {
	if (value === null || value === undefined || value === "") return "—"
	return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 })
}
function formatDateTime(value) {
	if (!value) return "—"
	const [date, time = ""] = String(value).split(" ")
	const [year, month, day] = date.split("-")
	if (!day) return String(value)
	return `${day}-${month}-${year}${time ? ` ${time.slice(0, 5)}` : ""}`
}
</script>

<style scoped>
.ppo-transfer-history { min-width: 0; overflow: hidden; border-color: var(--erp-border); box-shadow: var(--erp-shadow-xs); }
.ppo-transfer-history__header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 9px 13px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.ppo-transfer-history__header > div { display: grid; gap: 2px; }
.ppo-transfer-history__header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 760; letter-spacing: .05em; }
.ppo-transfer-history__header h2 { margin: 0; color: var(--erp-text); font-size: 15px; }
.ppo-transfer-history__header small { padding: 4px 8px; color: var(--erp-accent-dark); background: var(--erp-accent-soft); border: 1px solid var(--erp-accent-border); border-radius: 999px; font-size: var(--erp-font-size-min); font-weight: 740; white-space: nowrap; }
.ppo-transfer-history__table-wrap { min-width: 0; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; }
th { padding: 8px 10px; color: var(--erp-text-muted); background: var(--erp-surface-muted); border-bottom: 1px solid var(--erp-border-strong); font-size: var(--erp-font-size-min); font-weight: 760; letter-spacing: .035em; text-align: left; text-transform: uppercase; }
td { padding: 10px; color: var(--erp-text-secondary); border-bottom: 1px solid var(--erp-border-subtle); font-size: var(--erp-font-size-caption); vertical-align: top; overflow-wrap: anywhere; }
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover { background: var(--erp-surface-hover); }
th:nth-child(1) { width: 9%; } th:nth-child(2) { width: 17%; } th:nth-child(3) { width: 6%; } th:nth-child(4) { width: 12%; } th:nth-child(5), th:nth-child(6) { width: 18%; } th:nth-child(7) { width: 20%; }
td strong, td a { display: block; color: var(--erp-text); font-weight: 700; }
td a { color: var(--erp-accent-hover); text-decoration: none; }
td a:hover { text-decoration: underline; }
td small { display: block; margin-top: 3px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-variant-numeric: tabular-nums; }
.is-number { text-align: right; font-variant-numeric: tabular-nums; }
.ppo-transfer-history__movement { display: inline-flex; padding: 4px 7px; border-radius: 999px; font-weight: 760; letter-spacing: 0; }
.ppo-transfer-history__movement.is-added { color: var(--erp-success); background: var(--erp-success-soft); }
.ppo-transfer-history__movement.is-reduced { color: var(--erp-danger); background: var(--erp-danger-soft); }
.ppo-transfer-history__empty { display: flex; min-height: 150px; align-items: center; justify-content: center; gap: 10px; padding: 24px; color: var(--erp-text-muted); text-align: left; }
.ppo-transfer-history__empty i { color: var(--erp-accent); font-size: 20px; }
.ppo-transfer-history__empty div { display: grid; gap: 3px; }
.ppo-transfer-history__empty strong { color: var(--erp-text); font-size: var(--erp-font-size-body); }
.ppo-transfer-history__empty span { font-size: var(--erp-font-size-caption); }
@media (max-width: 820px) {
	.ppo-transfer-history__table-wrap { padding: 8px; }
	table, tbody, tr, td { display: block; }
	thead { display: none; }
	tbody { display: grid; gap: 8px; }
	tr { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-radius-md); background: var(--erp-surface-raised); }
	td { display: grid; min-width: 0; gap: 3px; padding: 9px 10px; border-right: 1px solid var(--erp-border-subtle); }
	td:nth-child(2n) { border-right: 0; }
	td::before { content: attr(data-label); color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .03em; text-transform: uppercase; }
	td.is-number { text-align: left; }
	td:last-child { grid-column: 1 / -1; border-right: 0; }
}
@media (max-width: 480px) {
	.ppo-transfer-history__header { align-items: flex-start; }
	tr { grid-template-columns: 1fr; }
	td, td:nth-child(2n) { border-right: 0; }
	td:last-child { grid-column: auto; }
}
</style>
