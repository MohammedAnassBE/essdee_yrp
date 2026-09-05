<template>
	<div class="essdee-wo-summary">
		<div class="summary-totals">
			<section class="total-card">
				<h5><i class="fa fa-truck" /> Delivered</h5>
				<div v-for="row in data.deliverables.totals" :key="'d-' + row.uom" class="total-line">
					<strong>{{ number(row.actual_qty) }} {{ row.uom }}</strong>
					<span>of {{ number(row.planned_qty) }} · {{ number(row.pending_qty) }} pending</span>
				</div>
				<div v-if="!data.deliverables.totals.length" class="empty">No planned items.</div>
			</section>
			<section class="total-card">
				<h5><i class="fa fa-download" /> Received</h5>
				<div v-for="row in data.receivables.totals" :key="'r-' + row.uom" class="total-line">
					<strong>{{ number(row.actual_qty) }} {{ row.uom }}</strong>
					<span>of {{ number(row.planned_qty) }} · {{ number(row.pending_qty) }} pending</span>
				</div>
				<div v-if="!data.receivables.totals.length" class="empty">No planned items.</div>
			</section>
		</div>

		<MovementTable title="Deliverables" actual-label="Delivered" :rows="data.deliverables.rows" />
		<MovementTable title="Receivables" actual-label="Received" :rows="data.receivables.rows" />

		<section class="summary-section">
			<header><h5>Debits</h5><span>{{ data.debits.length }}</span></header>
			<div v-if="data.debits.length" class="table-wrap">
				<table class="table table-bordered summary-table">
					<thead><tr><th>Debit</th><th>Debit No</th><th>Type</th><th class="number">Value</th><th>Status</th><th>Reason</th></tr></thead>
					<tbody>
						<tr v-for="row in data.debits" :key="row.name">
							<td><a :href="deskDebitUrl(row.name)">{{ row.name }}</a></td>
							<td>{{ row.debit_no || "—" }}</td>
							<td>{{ row.debit_type || "—" }}</td>
							<td class="number">{{ money(row.debit_value) }}</td>
							<td><span class="indicator-pill" :class="indicatorClass(row.status)">{{ row.status || "—" }}</span></td>
							<td>{{ row.reason || "—" }}</td>
						</tr>
					</tbody>
				</table>
			</div>
			<div v-else class="empty section-empty">No debits have been raised.</div>
		</section>
	</div>
</template>

<script setup>
import { defineComponent, h, ref } from "vue";

const emptyMovement = () => ({ rows: [], totals: [] });
const data = ref({ deliverables: emptyMovement(), receivables: emptyMovement(), debits: [] });

function load_data(payload) {
	data.value = {
		deliverables: payload?.deliverables || emptyMovement(),
		receivables: payload?.receivables || emptyMovement(),
		debits: payload?.debits || [],
	};
}

function number(value) {
	return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 }).format(Number(value || 0));
}

function money(value) {
	return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
}

function deskDebitUrl(name) {
	return `/app/debit/${encodeURIComponent(name)}`;
}

function indicatorClass(status) {
	if (status === "Approved") return "green";
	if (status === "Cancelled") return "red";
	return "orange";
}

const MovementTable = defineComponent({
	props: {
		title: String,
		actualLabel: String,
		rows: { type: Array, default: () => [] },
	},
	setup(props) {
		const attributes = (row) => (row.attributes || [])
			.map((attr) => `${attr.attribute}: ${attr.value}`)
			.join(" · ");
		return () => h("section", { class: "summary-section" }, [
			h("header", [h("h5", props.title), h("span", String(props.rows.length))]),
			props.rows.length
				? h("div", { class: "table-wrap" }, [h("table", { class: "table table-bordered summary-table" }, [
					h("thead", [h("tr", [
						h("th", "Item"), h("th", "Variant / Attributes"),
						h("th", { class: "number" }, "Planned"),
						h("th", { class: "number" }, props.actualLabel),
						h("th", { class: "number" }, "Pending"),
					])]),
					h("tbody", props.rows.map((row) => h("tr", { key: `${row.item_variant}:${row.uom}` }, [
						h("td", [h("strong", row.item || row.item_variant || "—")]),
						h("td", [h("div", { class: "variant" }, row.item_variant || "—"), attributes(row) ? h("small", attributes(row)) : null]),
						h("td", { class: "number" }, `${number(row.planned_qty)} ${row.uom || ""}`.trim()),
						h("td", { class: "number actual" }, `${number(row.actual_qty)} ${row.uom || ""}`.trim()),
						h("td", { class: "number" }, `${number(row.pending_qty)} ${row.uom || ""}`.trim()),
					]))),
				])])
				: h("div", { class: "empty section-empty" }, `No ${props.title.toLowerCase()} configured.`),
		]);
	},
});

defineExpose({ load_data });
</script>

<style scoped>
.essdee-wo-summary { display: grid; gap: 15px; padding: 5px 0 20px; }
.summary-totals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }
.total-card, .summary-section { border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); overflow: hidden; }
.total-card { padding: 14px 16px; }
.total-card h5 { margin: 0 0 10px; color: var(--text-muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.total-card h5 i { margin-right: 5px; color: var(--primary); }
.total-line { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 4px 0; }
.total-line strong { font-size: 16px; }
.total-line span, .empty, .variant + small { color: var(--text-muted); }
.summary-section > header { display: flex; align-items: center; justify-content: space-between; padding: 12px 15px; border-bottom: 1px solid var(--border-color); }
.summary-section > header h5 { margin: 0; font-size: 14px; }
.summary-section > header span { min-width: 24px; padding: 2px 7px; border-radius: 99px; text-align: center; background: var(--control-bg); color: var(--text-muted); font-size: 11px; font-weight: 600; }
.table-wrap { overflow-x: auto; }
.summary-table { min-width: 720px; margin: 0; font-size: 12px; }
.summary-table th { color: var(--text-muted); background: var(--subtle-fg); font-size: 11px; text-transform: uppercase; letter-spacing: .03em; }
.summary-table td, .summary-table th { padding: 9px 10px !important; vertical-align: top; }
.summary-table .number { text-align: right; white-space: nowrap; }
.summary-table .actual { color: var(--green-600); font-weight: 600; }
.variant { font-family: var(--font-stack-monospace); }
.variant + small { display: block; margin-top: 2px; }
.section-empty { padding: 18px; text-align: center; }
@media (max-width: 767px) { .summary-totals { grid-template-columns: 1fr; } }
</style>
