<template>
	<div class="wo-summary">
		<div v-if="loading" class="wo-summary__state" role="status">
			<i class="pi pi-spin pi-spinner" /> Loading summary…
		</div>
		<div v-else-if="error" class="wo-summary__state wo-summary__state--error" role="alert">
			<span>{{ error }}</span>
			<Button label="Retry" size="small" severity="secondary" outlined @click="load" />
		</div>
		<template v-else>
			<div class="wo-summary__totals">
				<SummaryTotal
					title="Delivered"
					icon="pi pi-send"
					:totals="summary.deliverables.totals"
					actual-label="Delivered"
				/>
				<SummaryTotal
					title="Received"
					icon="pi pi-download"
					:totals="summary.receivables.totals"
					actual-label="Received"
				/>
			</div>

			<MovementTable
				title="Deliverables"
				actual-label="Delivered"
				:rows="summary.deliverables.rows"
			/>
			<MovementTable
				title="Receivables"
				actual-label="Received"
				:rows="summary.receivables.rows"
			/>

			<section class="wo-summary__section">
				<header class="wo-summary__section-head">
					<div>
						<h3>Debits</h3>
						<p>Debit requests raised against this Work Order.</p>
					</div>
					<span class="wo-summary__count">{{ summary.debits.length }}</span>
				</header>
				<div v-if="summary.debits.length" class="wo-summary__table-wrap">
					<table class="wo-summary__table">
						<thead>
							<tr>
								<th>Debit</th>
								<th>Debit No</th>
								<th>Type</th>
								<th class="num">Value</th>
								<th>Status</th>
								<th>Reason</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in summary.debits" :key="row.name">
								<td>
									<button class="wo-summary__link" type="button" @click="openDebit(row.name)">
										{{ row.name }}
									</button>
								</td>
								<td>{{ row.debit_no || "—" }}</td>
								<td>{{ row.debit_type || "—" }}</td>
								<td class="num">{{ money(row.debit_value) }}</td>
								<td><span class="wo-summary__status" :class="statusClass(row.status)">{{ row.status || "—" }}</span></td>
								<td>{{ row.reason || "—" }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-else class="wo-summary__empty">No debits have been raised.</div>
			</section>
		</template>
	</div>
</template>

<script setup>
import { defineComponent, h, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import Button from "primevue/button"
import { callMethod, errorLines } from "@/api/client"

const props = defineProps({
	workOrder: { type: String, required: true },
})

const router = useRouter()
const loading = ref(true)
const error = ref("")
const emptyMovement = () => ({ rows: [], totals: [] })
const summary = ref({ deliverables: emptyMovement(), receivables: emptyMovement(), debits: [] })

function number(value) {
	return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 3 }).format(Number(value || 0))
}

function money(value) {
	return new Intl.NumberFormat("en-IN", {
		style: "currency",
		currency: "INR",
		maximumFractionDigits: 2,
	}).format(Number(value || 0))
}

function statusClass(status) {
	return `wo-summary__status--${String(status || "").toLowerCase().replace(/[^a-z]+/g, "-")}`
}

function openDebit(name) {
	router.push(`/debit/${encodeURIComponent(name)}`)
}

async function load() {
	if (!props.workOrder) return
	loading.value = true
	error.value = ""
	try {
		const result = await callMethod("essdee_yrp.api.work_order.get_work_order_summary", {
			work_order: props.workOrder,
		})
		summary.value = {
			deliverables: result?.deliverables || emptyMovement(),
			receivables: result?.receivables || emptyMovement(),
			debits: result?.debits || [],
		}
	} catch (e) {
		error.value = errorLines(e)[0] || "Could not load the Work Order summary."
	} finally {
		loading.value = false
	}
}

const SummaryTotal = defineComponent({
	props: {
		title: String,
		icon: String,
		totals: { type: Array, default: () => [] },
		actualLabel: String,
	},
	setup(componentProps) {
		return () => h("section", { class: "wo-summary__total-card" }, [
			h("div", { class: "wo-summary__total-title" }, [
				h("i", { class: componentProps.icon }),
				h("span", componentProps.title),
			]),
			componentProps.totals.length
				? componentProps.totals.map((row) => h("div", { class: "wo-summary__total-line" }, [
					h("strong", `${number(row.actual_qty)} ${row.uom || ""}`.trim()),
					h("span", `${componentProps.actualLabel} of ${number(row.planned_qty)} ${row.uom || ""}`.trim()),
					h("small", `${number(row.pending_qty)} pending`),
				]))
				: h("div", { class: "wo-summary__empty wo-summary__empty--card" }, "No planned items."),
		])
	},
})

const MovementTable = defineComponent({
	props: {
		title: String,
		actualLabel: String,
		rows: { type: Array, default: () => [] },
	},
	setup(componentProps) {
		const attrs = (row) => (row.attributes || [])
			.map((attr) => `${attr.attribute}: ${attr.value}`)
			.join(" · ")
		return () => h("section", { class: "wo-summary__section" }, [
			h("header", { class: "wo-summary__section-head" }, [
				h("div", [h("h3", componentProps.title)]),
				h("span", { class: "wo-summary__count" }, String(componentProps.rows.length)),
			]),
			componentProps.rows.length
				? h("div", { class: "wo-summary__table-wrap" }, [
					h("table", { class: "wo-summary__table" }, [
						h("thead", [h("tr", [
							h("th", "Item"),
							h("th", "Variant / Attributes"),
							h("th", { class: "num" }, "Planned"),
							h("th", { class: "num" }, componentProps.actualLabel),
							h("th", { class: "num" }, "Pending"),
						])]),
						h("tbody", componentProps.rows.map((row) => h("tr", { key: `${row.item_variant}:${row.uom}` }, [
							h("td", [h("strong", row.item || row.item_variant || "—")]),
							h("td", [
								h("div", { class: "wo-summary__variant" }, row.item_variant || "—"),
								attrs(row) ? h("div", { class: "wo-summary__attrs" }, attrs(row)) : null,
							]),
							h("td", { class: "num" }, `${number(row.planned_qty)} ${row.uom || ""}`.trim()),
							h("td", { class: "num wo-summary__actual" }, `${number(row.actual_qty)} ${row.uom || ""}`.trim()),
							h("td", { class: "num" }, `${number(row.pending_qty)} ${row.uom || ""}`.trim()),
						]))),
					]),
				])
				: h("div", { class: "wo-summary__empty" }, `No ${componentProps.title.toLowerCase()} configured.`),
		])
	},
})

onMounted(load)
watch(() => props.workOrder, load)
</script>

<style scoped>
.wo-summary { display: grid; gap: 1rem; }
.wo-summary__state { min-height: 10rem; display: flex; align-items: center; justify-content: center; gap: .6rem; color: var(--esd-muted); }
.wo-summary__state--error { flex-direction: column; color: var(--p-red-600); }
.wo-summary__totals { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1rem; }
.wo-summary__total-card, .wo-summary__section { border: 1px solid var(--esd-line); border-radius: 10px; background: var(--esd-card); overflow: hidden; }
.wo-summary__total-card { padding: 1rem; }
.wo-summary__total-title { display: flex; gap: .55rem; align-items: center; color: var(--esd-muted); font-size: .82rem; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; margin-bottom: .8rem; }
.wo-summary__total-title i { color: var(--esd-accent); }
.wo-summary__total-line { display: grid; grid-template-columns: auto 1fr auto; gap: .65rem; align-items: baseline; padding: .35rem 0; }
.wo-summary__total-line strong { font-size: 1.05rem; }
.wo-summary__total-line span, .wo-summary__total-line small { color: var(--esd-muted); }
.wo-summary__section-head { display: flex; justify-content: space-between; align-items: center; padding: .9rem 1rem; border-bottom: 1px solid var(--esd-line); }
.wo-summary__section-head h3 { margin: 0; font-size: 1rem; }
.wo-summary__section-head p { margin: .2rem 0 0; color: var(--esd-muted); font-size: .8rem; }
.wo-summary__count { min-width: 1.7rem; padding: .15rem .45rem; text-align: center; border-radius: 999px; background: var(--esd-slate-50); color: var(--esd-muted); font-size: .75rem; font-weight: 700; }
.wo-summary__table-wrap { overflow-x: auto; }
.wo-summary__table { width: 100%; border-collapse: collapse; min-width: 46rem; font-size: .82rem; }
.wo-summary__table th { padding: .65rem .8rem; text-align: left; color: var(--esd-muted); background: var(--esd-slate-50); font-size: .72rem; text-transform: uppercase; letter-spacing: .035em; }
.wo-summary__table td { padding: .7rem .8rem; border-top: 1px solid var(--esd-line); vertical-align: top; }
.wo-summary__table tbody tr:first-child td { border-top: 0; }
.wo-summary__table .num { text-align: right; white-space: nowrap; }
.wo-summary__actual { color: var(--p-green-600); font-weight: 700; }
.wo-summary__variant { font-family: var(--esd-mono, monospace); font-size: .76rem; }
.wo-summary__attrs { margin-top: .2rem; color: var(--esd-muted); font-size: .75rem; }
.wo-summary__empty { padding: 1.25rem; color: var(--esd-muted); text-align: center; }
.wo-summary__empty--card { padding: .7rem 0; text-align: left; }
.wo-summary__link { border: 0; background: none; padding: 0; color: var(--esd-accent); font: inherit; font-family: var(--esd-mono, monospace); cursor: pointer; }
.wo-summary__status { display: inline-flex; border-radius: 999px; padding: .16rem .45rem; background: var(--esd-slate-50); white-space: nowrap; }
.wo-summary__status--approved { color: var(--p-green-700); background: var(--p-green-50); }
.wo-summary__status--debit-requested, .wo-summary__status--draft { color: var(--p-orange-700); background: var(--p-orange-50); }
.wo-summary__status--cancelled { color: var(--p-red-700); background: var(--p-red-50); }
@media (max-width: 760px) {
	.wo-summary__totals { grid-template-columns: 1fr; }
	.wo-summary__total-line { grid-template-columns: 1fr auto; }
	.wo-summary__total-line span { grid-column: 1 / -1; }
}
</style>
