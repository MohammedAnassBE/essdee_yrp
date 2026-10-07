<template>
	<div class="essdee-work-order-summary">
		<div class="movement-overview">
			<section class="overview-card">
				<span class="eyebrow">Issued</span>
				<div v-if="data.deliverables.totals.length" class="metric-list">
					<div v-for="row in data.deliverables.totals" :key="`issued-${row.uom}`" class="metric-line">
						<strong>{{ quantity(row.actual_qty) }} {{ row.uom }}</strong>
						<small>{{ quantity(row.pending_qty) }} pending of {{ quantity(row.planned_qty) }}</small>
					</div>
				</div>
				<p v-else class="empty-copy">No issued items.</p>
			</section>

			<section class="overview-card">
				<span class="eyebrow">Received</span>
				<div v-if="data.receivables.totals.length" class="metric-list">
					<div v-for="row in data.receivables.totals" :key="`received-${row.uom}`" class="metric-line">
						<strong>{{ quantity(row.actual_qty) }} {{ row.uom }}</strong>
						<small>{{ quantity(row.pending_qty) }} pending of {{ quantity(row.planned_qty) }}</small>
					</div>
				</div>
				<p v-else class="empty-copy">No receivable items.</p>
			</section>

			<section class="overview-card value-card">
				<span class="eyebrow">Planned process cost</span>
				<strong>{{ money(data.planned_process_cost) }}</strong>
				<small>Saved Work Order estimate</small>
			</section>

			<section class="overview-card value-card">
				<span class="eyebrow">Approved debit</span>
				<strong>{{ money(data.debit_total) }}</strong>
				<small>{{ data.debits.length }} debit record{{ data.debits.length === 1 ? "" : "s" }}</small>
			</section>
		</div>

		<section class="summary-panel valuation-panel">
			<header>
				<div>
					<span class="eyebrow">Posted valuation</span>
					<h5>Input stock + process value = output stock</h5>
				</div>
				<span class="posted-badge">Stock Ledger</span>
			</header>
			<div class="valuation-flow">
				<div>
					<span>Input value</span>
					<strong>{{ money(data.valuation.input_value) }}</strong>
				</div>
				<span class="operator">+</span>
				<div>
					<span>Posted process value</span>
					<strong>{{ money(data.valuation.process_value) }}</strong>
				</div>
				<span class="operator">=</span>
				<div class="output-value">
					<span>Output value</span>
					<strong>{{ money(data.valuation.output_value) }}</strong>
				</div>
			</div>
			<p class="valuation-note">
				Planned process cost is an estimate. Posted values come only from active submitted GRN stock ledger entries.
			</p>
		</section>

		<section class="summary-panel">
			<header>
				<div><span class="eyebrow">Material movement</span><h5>Issued inputs</h5></div>
				<span class="row-count">{{ data.deliverables.rows.length }}</span>
			</header>
			<div v-if="data.deliverables.rows.length" class="table-wrap">
				<table class="table summary-table">
					<thead>
						<tr>
							<th>Item</th>
							<th>Exact source</th>
							<th>Received type</th>
							<th class="number">Planned</th>
							<th class="number">Issued</th>
							<th class="number">Pending</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in data.deliverables.rows" :key="movementKey(row)">
							<td>
								<strong>{{ row.item_name || row.item_variant || "—" }}</strong>
								<small class="item-code">{{ row.item_variant || "—" }}</small>
								<small v-if="attributeText(row)" class="attribute-copy">{{ attributeText(row) }}</small>
							</td>
							<td>
								<a v-if="row.source_grn" :href="deskLink('YRP Goods Received Note', row.source_grn)">{{ row.source_grn }}</a>
								<span v-else>—</span>
								<small v-if="row.source_grn_item" class="source-child">{{ row.source_grn_item }}</small>
							</td>
							<td><span class="type-pill">{{ row.received_type || "—" }}</span></td>
							<td class="number">{{ quantityWithUom(row.planned_qty, row.uom) }}</td>
							<td class="number actual">{{ quantityWithUom(row.actual_qty, row.uom) }}</td>
							<td class="number">{{ quantityWithUom(row.pending_qty, row.uom) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
			<p v-else class="section-empty">No deliverables are configured.</p>
		</section>

		<section class="summary-panel">
			<header>
				<div><span class="eyebrow">Production movement</span><h5>Expected outputs</h5></div>
				<span class="row-count">{{ data.receivables.rows.length }}</span>
			</header>
			<div v-if="data.receivables.rows.length" class="table-wrap">
				<table class="table summary-table">
					<thead>
						<tr>
							<th>Item</th>
							<th class="number">Planned</th>
							<th class="number">Received</th>
							<th class="number">Pending</th>
							<th class="number">Planned process cost</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in data.receivables.rows" :key="movementKey(row)">
							<td>
								<strong>{{ row.item_name || row.item_variant || "—" }}</strong>
								<small class="item-code">{{ row.item_variant || "—" }}</small>
								<small v-if="attributeText(row)" class="attribute-copy">{{ attributeText(row) }}</small>
							</td>
							<td class="number">{{ quantityWithUom(row.planned_qty, row.uom) }}</td>
							<td class="number actual">{{ quantityWithUom(row.actual_qty, row.uom) }}</td>
							<td class="number">{{ quantityWithUom(row.pending_qty, row.uom) }}</td>
							<td class="number">{{ money(row.planned_process_cost) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
			<p v-else class="section-empty">No receivables are configured.</p>
		</section>

		<section class="summary-panel">
			<header>
				<div><span class="eyebrow">Commercial adjustments</span><h5>Debits</h5></div>
				<span class="row-count">{{ data.debits.length }}</span>
			</header>
			<div v-if="data.debits.length" class="table-wrap">
				<table class="table summary-table debit-table">
					<thead><tr><th>Debit</th><th>Number</th><th>Type</th><th>Status</th><th>Reason</th><th class="number">Value</th></tr></thead>
					<tbody>
						<tr v-for="row in data.debits" :key="row.name">
							<td><a :href="deskLink('YRP Debit', row.name)">{{ row.name }}</a></td>
							<td>{{ row.debit_no || "—" }}</td>
							<td>{{ row.debit_type || "—" }}</td>
							<td><span class="status-pill" :class="statusClass(row.status)">{{ row.status || "—" }}</span></td>
							<td>{{ row.reason || "—" }}</td>
							<td class="number">{{ money(row.debit_value) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
			<p v-else class="section-empty">No debits have been raised for this Work Order.</p>
		</section>
	</div>
</template>

<script setup>
import { ref } from "vue";

const emptyMovement = () => ({ rows: [], totals: [], planned_process_cost: 0 });
const emptyValuation = () => ({ input_value: 0, process_value: 0, output_value: 0 });
const data = ref({
	deliverables: emptyMovement(),
	receivables: emptyMovement(),
	debits: [],
	debit_total: 0,
	planned_process_cost: 0,
	valuation: emptyValuation(),
});

function load_data(payload) {
	data.value = {
		deliverables: payload?.deliverables || emptyMovement(),
		receivables: payload?.receivables || emptyMovement(),
		debits: payload?.debits || [],
		debit_total: Number(payload?.debit_total || 0),
		planned_process_cost: Number(payload?.planned_process_cost || 0),
		valuation: payload?.valuation || emptyValuation(),
	};
}

function quantity(value) {
	return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 }).format(Number(value || 0));
}

function quantityWithUom(value, uom) {
	return `${quantity(value)} ${uom || ""}`.trim();
}

function money(value) {
	return new Intl.NumberFormat("en-IN", {
		style: "currency",
		currency: frappe.boot?.sysdefaults?.currency || "INR",
		maximumFractionDigits: 2,
	}).format(Number(value || 0));
}

function attributeText(row) {
	return (row.attributes || [])
		.map((attribute) => `${attribute.attribute}: ${attribute.value}`)
		.join(" · ");
}

function movementKey(row) {
	return [
		row.item_variant,
		row.uom,
		row.source_grn,
		row.source_grn_item,
		row.received_type,
	].filter(Boolean).join(":");
}

function deskLink(doctype, name) {
	const slug = String(doctype || "").trim().toLowerCase().replace(/\s+/g, "-");
	return `/app/${slug}/${encodeURIComponent(name)}`;
}

function statusClass(status) {
	if (status === "Approved") return "status-approved";
	if (status === "Cancelled") return "status-cancelled";
	return "status-pending";
}

defineExpose({ load_data });
</script>

<style scoped>
.essdee-work-order-summary { display: grid; gap: 14px; padding: 6px 0 20px; color: var(--text-color); }
.movement-overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.overview-card, .summary-panel { border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); }
.overview-card { min-height: 108px; padding: 14px 15px; }
.eyebrow { display: block; margin-bottom: 7px; color: var(--text-muted); font-size: 10px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.metric-list { display: grid; gap: 8px; }
.metric-line, .value-card { display: grid; gap: 2px; }
.metric-line strong, .value-card strong { font-size: 17px; line-height: 1.2; }
.metric-line small, .value-card small, .empty-copy, .valuation-note { color: var(--text-muted); font-size: 11px; }
.empty-copy { margin: 12px 0 0; }
.summary-panel { overflow: hidden; }
.summary-panel > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--border-color); }
.summary-panel h5 { margin: 0; font-size: 14px; font-weight: 600; }
.row-count, .posted-badge { padding: 3px 8px; border-radius: 99px; background: var(--control-bg); color: var(--text-muted); font-size: 10px; font-weight: 700; }
.valuation-flow { display: grid; grid-template-columns: 1fr auto 1fr auto 1fr; align-items: center; gap: 12px; padding: 16px; }
.valuation-flow > div { display: grid; gap: 4px; }
.valuation-flow span { color: var(--text-muted); font-size: 11px; }
.valuation-flow strong { font-size: 19px; }
.valuation-flow .operator { font-size: 18px; font-weight: 700; }
.valuation-flow .output-value strong { color: var(--green-600); }
.valuation-note { margin: 0; padding: 0 16px 14px; }
.table-wrap { overflow-x: auto; }
.summary-table { min-width: 860px; margin: 0; font-size: 12px; }
.summary-table th { border-top: 0 !important; background: var(--subtle-fg); color: var(--text-muted); font-size: 10px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; }
.summary-table td, .summary-table th { padding: 9px 10px !important; vertical-align: top; }
.summary-table .number { text-align: right; white-space: nowrap; }
.summary-table .actual { color: var(--green-600); font-weight: 600; }
.item-code, .attribute-copy, .source-child { display: block; margin-top: 2px; color: var(--text-muted); font-size: 10px; }
.item-code, .source-child { font-family: var(--font-stack-monospace); }
.type-pill, .status-pill { display: inline-block; padding: 2px 7px; border-radius: 99px; background: var(--control-bg); font-size: 10px; font-weight: 600; }
.status-approved { background: var(--green-100); color: var(--green-700); }
.status-cancelled { background: var(--red-100); color: var(--red-700); }
.status-pending { background: var(--yellow-100); color: var(--yellow-700); }
.section-empty { margin: 0; padding: 20px 14px; color: var(--text-muted); text-align: center; }
@media (max-width: 991px) { .movement-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 575px) { .movement-overview { grid-template-columns: 1fr; } .valuation-flow { grid-template-columns: 1fr; } .valuation-flow .operator { display: none; } }
</style>
