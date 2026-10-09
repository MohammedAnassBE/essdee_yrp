<template>
	<div class="ppo-report">
		<ReportShell
			title="PPO Report"
			:generated="generated"
			:loading="loading"
			:has-results="orders.length > 0"
			keep-results-while-loading
			@generate="generate"
			@reset="reset"
		>
			<template #filters>
				<div class="common-field">
					<label for="ppo-report-status">Status</label>
					<Select input-id="ppo-report-status" v-model="filters.status" :options="statusOptions" option-label="label" option-value="value" aria-label="Status" fluid />
				</div>
				<LinkField v-model="filters.productCategory" doctype="SD YRP Product Category" label="Product Category" placeholder="Search category…" :show-open-button="false" show-clear />
				<DateField v-model="filters.fromDate" label="From Date" />
				<DateField v-model="filters.toDate" label="To Date" />
			</template>

			<template #metrics>
				<div class="report-metric"><i class="pi pi-file" /><div><span>Production Orders</span><strong>{{ number(summary.total_orders) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-chart-bar" /><div><span>Total Quantity</span><strong>{{ number(summary.total_quantity) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-th-large" /><div><span>Size Coverage</span><strong>{{ number(summary.size_groups) }} size groups</strong></div></div>
			</template>

			<div class="ppo-report__heading">
				<div>
					<strong>Production order matrix</strong>
					<span>{{ periodLabel }}</span>
				</div>
				<Button v-if="canExport" label="Download Excel" icon="pi pi-download" severity="secondary" outlined class="erp-action-button" :loading="downloading" @click="download" />
			</div>

			<div class="ppo-report__matrix-wrap" role="region" aria-label="PPO Report matrix" tabindex="0">
				<table class="ppo-report__matrix" :style="matrixStyle">
					<thead>
						<tr>
							<th rowspan="2" class="ppo-report__toggle-column"><span class="sr-only">Dispatch</span></th>
							<th rowspan="2" class="ppo-report__sticky ppo-report__sticky--ppo">PPO</th>
							<th rowspan="2" class="ppo-report__sticky ppo-report__sticky--item">Item</th>
							<th rowspan="2">Fabric</th><th rowspan="2">Dia</th><th rowspan="2">GSM</th>
							<th rowspan="2">Posting</th><th rowspan="2">Delivery</th><th rowspan="2">Don't deliver after</th>
							<th rowspan="2" class="erp-number">Lead</th><th rowspan="2">Status</th>
							<th v-for="group in sizeGroups" :key="`group-${group.label}`" :colspan="maxColumns" class="ppo-report__size-group">{{ String(group.label || "Sizes").toUpperCase() }}</th>
							<th rowspan="2" class="erp-number">Total</th><th rowspan="2">Comments</th>
						</tr>
						<tr>
							<template v-for="group in sizeGroups" :key="`sizes-${group.label}`">
								<th v-for="index in maxColumns" :key="`${group.label}-${index}`" class="erp-number ppo-report__size">{{ group.sizes?.[index - 1] || "—" }}</th>
							</template>
						</tr>
					</thead>
					<tbody>
						<template v-for="order in orders" :key="order.name">
							<tr>
								<td class="ppo-report__toggle-column"><Button text rounded size="small" :icon="expanded === order.name ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" :aria-label="`${expanded === order.name ? 'Hide' : 'Show'} dispatch for ${order.name}`" :loading="dispatchLoading === order.name" @click="toggleDispatch(order.name)" /></td>
								<th scope="row" class="ppo-report__sticky ppo-report__sticky--ppo"><RouterLink :to="`/sales/production-orders/${encodeURIComponent(order.name)}`">{{ order.name }}</RouterLink></th>
								<td class="ppo-report__sticky ppo-report__sticky--item"><strong>{{ order.item || "—" }}</strong><small v-if="order.production_term">{{ order.production_term }}</small></td>
								<td>{{ order.fabric || "—" }}</td><td>{{ order.dia || "—" }}</td><td class="erp-number">{{ displayNumber(order.gsm) }}</td>
								<td>{{ formatDate(order.posting_date) }}</td><td>{{ formatDate(order.delivery_date) }}</td><td>{{ formatDate(order.dont_deliver_after) }}</td>
								<td class="erp-number">{{ number(order.lead_time) }}d</td><td><Tag :value="order.status || '—'" :severity="statusSeverity(order.status)" /></td>
								<template v-for="group in sizeGroups" :key="`${order.name}-${group.label}`">
									<td v-for="index in maxColumns" :key="`${order.name}-${group.label}-${index}`" class="erp-number ppo-report__quantity">{{ order.group_label === group.label ? displayQuantity(order.qty_by_position?.[index - 1]) : "—" }}</td>
								</template>
								<td class="erp-number ppo-report__total">{{ number(order.total) }}</td><td class="ppo-report__comments">{{ order.comments || "—" }}</td>
							</tr>
							<tr v-if="expanded === order.name" class="ppo-report__dispatch-row">
								<td :colspan="columnCount"><div class="ppo-report__dispatch"><DispatchSummary :payload="dispatchByOrder[order.name]" /></div></td>
							</tr>
						</template>
					</tbody>
					<tfoot><tr><th :colspan="11">Total</th><template v-for="group in sizeGroups" :key="`total-${group.label}`"><td v-for="index in maxColumns" :key="`${group.label}-${index}`" class="erp-number">{{ displayQuantity(groupTotal(group.label, index - 1)) }}</td></template><td class="erp-number">{{ number(summary.total_quantity) }}</td><td></td></tr></tfoot>
				</table>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="PPO Report could not be generated" @dismiss="error = ''" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Select from "primevue/select"
import Tag from "primevue/tag"
import { computed, defineComponent, h, reactive, ref } from "vue"

import { downloadPpoReport, getPpoDispatchSummary, getPpoReport } from "../../api/sales.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { formatDate, number } from "../../components/reports/reportUtils.js"

defineProps({ canExport: { type: Boolean, default: false } })

const statusOptions = [
	{ label: "All statuses", value: "" }, { label: "Draft", value: "Draft" }, { label: "PPO Request", value: "PPO Request" },
	{ label: "Open", value: "Open" }, { label: "Pending Request", value: "Pending Request" }, { label: "Closed", value: "Closed" },
	{ label: "Cancelled", value: "Cancelled" },
]
const filters = reactive(defaultFilters())
const applied = ref({})
const payload = ref(emptyPayload())
const generated = ref(false)
const loading = ref(false)
const downloading = ref(false)
const error = ref("")
const expanded = ref("")
const dispatchLoading = ref("")
const dispatchByOrder = reactive({})
const orders = computed(() => payload.value.orders || [])
const sizeGroups = computed(() => payload.value.size_groups || [])
const maxColumns = computed(() => Number(payload.value.max_columns || 0))
const summary = computed(() => payload.value.summary || emptyPayload().summary)
const columnCount = computed(() => 13 + (sizeGroups.value.length * maxColumns.value))
const matrixStyle = computed(() => ({ minWidth: `${Math.max(1380, 1090 + (sizeGroups.value.length * maxColumns.value * 68))}px` }))
const periodLabel = computed(() => {
	const from = applied.value.from_date ? formatDate(applied.value.from_date) : "Beginning"
	const to = applied.value.to_date ? formatDate(applied.value.to_date) : "Today"
	return `${from} — ${to}`
})

function defaultFilters() { return { status: "", productCategory: "", fromDate: "", toDate: "" } }
function emptyPayload() { return { orders: [], size_groups: [], max_columns: 0, summary: { total_orders: 0, total_quantity: 0, size_groups: 0 } } }
function requestFilters() { return { status: filters.status, product_category: filters.productCategory, from_date: filters.fromDate, to_date: filters.toDate } }
function displayQuantity(value) { return Number(value || 0) === 0 ? "—" : number(value) }
function displayNumber(value) { return value === null || value === undefined || value === "" || Number(value) === 0 ? "—" : number(value) }
function statusSeverity(status) { return ({ Open: "success", "PPO Request": "warn", Closed: "secondary", Cancelled: "danger" })[status] || "info" }
function groupTotal(label, index) { return orders.value.reduce((total, order) => total + (order.group_label === label ? Number(order.qty_by_position?.[index] || 0) : 0), 0) }

async function generate() {
	loading.value = true
	error.value = ""
	try {
		const request = requestFilters()
		payload.value = await getPpoReport(request) || emptyPayload()
		applied.value = request
		generated.value = true
		expanded.value = ""
	} catch (reason) {
		error.value = reason?.message || "Unable to generate the PPO Report."
	} finally {
		loading.value = false
	}
}

async function toggleDispatch(name) {
	if (expanded.value === name) { expanded.value = ""; return }
	expanded.value = name
	if (dispatchByOrder[name]) return
	dispatchLoading.value = name
	try {
		dispatchByOrder[name] = await getPpoDispatchSummary(name) || { sizes: [], rows: [] }
	} catch (reason) {
		expanded.value = ""
		error.value = reason?.message || `Unable to load dispatch details for ${name}.`
	} finally {
		dispatchLoading.value = ""
	}
}

async function download() {
	downloading.value = true
	error.value = ""
	try { await downloadPpoReport(applied.value) }
	catch (reason) { error.value = reason?.message || "Unable to download the PPO Report." }
	finally { downloading.value = false }
}

function reset() {
	Object.assign(filters, defaultFilters())
	payload.value = emptyPayload()
	applied.value = {}
	generated.value = false
	expanded.value = ""
	error.value = ""
}

const DispatchSummary = defineComponent({
	props: { payload: { type: Object, default: () => ({ sizes: [], rows: [] }) } },
	setup(props) {
		return () => {
			const sizes = props.payload?.sizes || [], rows = props.payload?.rows || []
			if (!rows.length) return h("div", { class: "ppo-report__dispatch-empty" }, [h("i", { class: "pi pi-truck" }), h("span", "No submitted dispatches for this Production Order.")])
			return h("div", [h("strong", { class: "ppo-report__dispatch-title" }, "Dispatch summary"), h("table", { class: "ppo-report__dispatch-table" }, [
				h("thead", [h("tr", [h("th", "Posting date"), h("th", "Lot"), ...sizes.map((size) => h("th", { class: "erp-number" }, size)), h("th", { class: "erp-number" }, "Total")])]),
				h("tbody", rows.map((row) => h("tr", [h("td", formatDate(row.date)), h("td", row.lot || "—"), ...sizes.map((size) => h("td", { class: "erp-number" }, displayQuantity(row.sizes?.[size]))), h("td", { class: "erp-number" }, number(row.total))]))),
			])])
		}
	},
})
</script>

<style scoped>
.ppo-report { min-width: 0; }
.ppo-report__heading { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.ppo-report__heading > div { display: grid; gap: 2px; }
.ppo-report__heading strong { color: var(--erp-text); font-size: 14px; }
.ppo-report__heading span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.ppo-report__matrix-wrap { width: 100%; max-width: 100%; overflow-x: auto; overflow-y: visible; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); overscroll-behavior-x: contain; }
.ppo-report__matrix { width: 100%; border-collapse: separate; border-spacing: 0; color: var(--erp-text); font-size: var(--erp-font-size-table); }
.ppo-report__matrix th, .ppo-report__matrix td { min-width: 68px; padding: 9px 10px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); vertical-align: middle; white-space: nowrap; }
.ppo-report__matrix thead th { color: var(--erp-text-muted); background: #f0f4f3; font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .035em; text-transform: uppercase; }
.ppo-report__matrix thead tr:first-child th { position: sticky; z-index: 3; top: 0; }
.ppo-report__matrix thead tr:nth-child(2) th { position: sticky; z-index: 3; top: 35px; }
.ppo-report__matrix tbody tr:hover > td, .ppo-report__matrix tbody tr:hover > th { background: #f7fbf9; }
.ppo-report__matrix tbody th { text-align: left; }
.ppo-report__matrix tbody small { display: block; margin-top: 2px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 500; }
.ppo-report__matrix tfoot th, .ppo-report__matrix tfoot td { background: #edf8f3; border-bottom: 0; font-weight: 800; }
.ppo-report__matrix tfoot th { color: #087654; text-align: right; text-transform: uppercase; }
.ppo-report__toggle-column { width: 44px; min-width: 44px !important; max-width: 44px; padding: 3px !important; text-align: center; }
.ppo-report__toggle-column :deep(.p-button) { width: 32px; height: 32px; color: #087654; }
.ppo-report__sticky { position: sticky; z-index: 2; background: var(--erp-surface); }
.ppo-report__sticky--ppo { left: 0; min-width: 132px !important; }
.ppo-report__sticky--item { left: 132px; min-width: 190px !important; }
.ppo-report__matrix thead .ppo-report__sticky { z-index: 5; background: #f0f4f3; }
.ppo-report__sticky--ppo a { color: #076c51; font-weight: 800; text-decoration: none; }
.ppo-report__sticky--ppo a:hover { text-decoration: underline; }
.ppo-report__size-group { color: #087654 !important; background: #e7f6ef !important; text-align: center; }
.ppo-report__size { text-align: center; }
.ppo-report__quantity { background: #f4fbf7; font-weight: 700; }
.ppo-report__total { color: #087654; font-weight: 850; }
.ppo-report__comments { min-width: 190px !important; max-width: 260px; white-space: normal !important; }
.ppo-report__dispatch-row > td { padding: 0 !important; background: #f8fbfa; }
.ppo-report__dispatch { padding: 12px 16px 14px; }
.ppo-report__dispatch-title { display: block; margin-bottom: 8px; color: #315147; font-size: 12px; text-transform: uppercase; letter-spacing: .035em; }
.ppo-report__dispatch-table { width: min(760px, 100%); border-collapse: collapse; background: var(--erp-surface); }
.ppo-report__dispatch-table th, .ppo-report__dispatch-table td { min-width: 78px; padding: 7px 9px; border: 1px solid var(--erp-border); font-size: 12px; }
.ppo-report__dispatch-table th { color: var(--erp-text-muted); background: #eef3f1; text-transform: uppercase; }
.ppo-report__dispatch-empty { display: flex; align-items: center; gap: 8px; color: var(--erp-text-muted); font-size: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

@media (max-width: 700px) {
	.ppo-report__heading { align-items: stretch; flex-direction: column; }
	.ppo-report__heading :deep(.p-button) { width: 100%; }
	.ppo-report__sticky--ppo { min-width: 118px !important; }
	.ppo-report__sticky--item { left: 118px; min-width: 160px !important; }
}
</style>
