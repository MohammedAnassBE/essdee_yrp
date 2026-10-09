<template>
	<div class="ppo-report">
		<ReportShell title="PPO Report" :generated="generated" :loading="loading" :has-results="orders.length > 0" keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<div class="common-field">
					<label for="ppo-report-status">Status</label>
					<Select input-id="ppo-report-status" v-model="filters.status" :options="statusOptions" option-label="label" option-value="value" aria-label="Status" fluid />
				</div>
				<LinkField v-model="filters.productCategory" doctype="SD YRP Product Category" label="Product Category" placeholder="Search category…" :show-open-button="false" show-clear />
				<AsyncLinkMultiSelect v-model="filters.items" doctype="Item" label="Item" placeholder="Search items…" :filters="{ has_variants: 1 }" />
				<DateField v-model="filters.fromDate" label="From Date" />
				<DateField v-model="filters.toDate" label="To Date" />
			</template>

			<template #metrics>
				<div class="report-metric"><i class="pi pi-file" /><div><span>Total Orders</span><strong>{{ number(summary.total_orders) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-chart-bar" /><div><span>Total Quantity</span><strong>{{ number(summary.total_quantity) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-th-large" /><div><span>Size Groups</span><strong>{{ number(summary.size_groups) }}</strong></div></div>
			</template>

			<div class="ppo-report__toolbar">
				<div class="ppo-report__heading">
					<strong>Production order matrix</strong>
					<span>{{ periodLabel }}</span>
				</div>
				<div class="ppo-report__controls" aria-label="Report display options">
					<label class="ppo-report__column-toggle" for="ppo-report-show-fabric"><Checkbox input-id="ppo-report-show-fabric" v-model="showFabric" binary /><span>Show Fabric</span></label>
					<label class="ppo-report__column-toggle" for="ppo-report-show-dia"><Checkbox input-id="ppo-report-show-dia" v-model="showDia" binary /><span>Show Dia</span></label>
					<label class="ppo-report__column-toggle" for="ppo-report-show-gsm"><Checkbox input-id="ppo-report-show-gsm" v-model="showGsm" binary /><span>Show GSM</span></label>
					<label class="ppo-report__column-toggle" :class="{ 'is-disabled': bulkLoading }" for="ppo-report-summarized"><Checkbox input-id="ppo-report-summarized" :model-value="allSummarized" binary :disabled="bulkLoading" @update:model-value="toggleAllSummaries" /><span>Summarized</span></label>
					<Button v-if="canExport" label="Download Excel" icon="pi pi-download" severity="secondary" outlined size="small" :loading="downloading" @click="download" />
				</div>
			</div>

			<div class="ppo-report__matrix-wrap" role="region" aria-label="PPO Report matrix" tabindex="0">
				<table class="ppo-report__matrix" :style="matrixStyle">
					<thead>
						<tr v-for="group in sizeGroups" :key="`group-${group.label}`" class="ppo-report__size-group-row">
							<th :colspan="fixedBeforeGroup" aria-hidden="true"></th>
							<th class="ppo-report__size-group">{{ String(group.label || "Sizes").toUpperCase() }}</th>
							<th v-for="index in maxColumns" :key="`${group.label}-${index}`" class="erp-number ppo-report__size-column">{{ group.sizes?.[index - 1] || "—" }}</th>
							<th colspan="3" aria-hidden="true"></th>
						</tr>
						<tr class="ppo-report__main-header">
							<th class="erp-number">#</th>
							<th><button type="button" class="ppo-report__sort" @click="sortBy('name')">PPO <i :class="sortIcon('name')" /></button></th>
							<th>Item</th>
							<th v-if="showFabric">Fabric</th>
							<th v-if="showDia">Dia</th>
							<th v-if="showGsm">GSM</th>
							<th><button type="button" class="ppo-report__sort" @click="sortBy('posting_date')">Posting <i :class="sortIcon('posting_date')" /></button></th>
							<th><button type="button" class="ppo-report__sort" @click="sortBy('delivery_date')">Delivery <i :class="sortIcon('delivery_date')" /></button></th>
							<th><button type="button" class="ppo-report__sort" @click="sortBy('dont_deliver_after')">Don't deliver after <i :class="sortIcon('dont_deliver_after')" /></button></th>
							<th class="erp-number">Lead time</th>
							<th>Status</th>
							<th>Action</th>
							<th>Size group</th>
							<th v-for="index in maxColumns" :key="`position-${index}`" class="erp-number ppo-report__size-column"><span class="sr-only">Size position {{ index }}</span></th>
							<th class="erp-number">Total</th>
							<th>Quantity transfer</th>
							<th>Comments</th>
						</tr>
					</thead>
					<tbody>
						<template v-for="(order, index) in sortedOrders" :key="order.name">
							<tr>
								<td class="erp-number ppo-report__index">{{ index + 1 }}</td>
								<th scope="row" class="ppo-report__ppo"><RouterLink :to="`/sales/production-orders/${encodeURIComponent(order.name)}`">{{ order.name }}</RouterLink></th>
								<td class="ppo-report__item"><strong>{{ order.item || "—" }}</strong><small v-if="order.production_term">{{ order.production_term }}</small></td>
								<td v-if="showFabric">{{ order.fabric || "—" }}</td>
								<td v-if="showDia">{{ order.dia || "—" }}</td>
								<td v-if="showGsm" class="erp-number">{{ displayNumber(order.gsm) }}</td>
								<td>{{ formatDate(order.posting_date) }}</td>
								<td>{{ formatDate(order.delivery_date) }}</td>
								<td>{{ formatDate(order.dont_deliver_after) }}</td>
								<td class="erp-number">{{ number(order.lead_time) }}d</td>
								<td><Tag :value="order.status || '—'" :severity="statusSeverity(order.status)" /></td>
								<td><Button label="Summarize" :icon="isExpanded(order.name) ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" text size="small" :loading="dispatchLoading === order.name" @click="toggleDispatch(order.name)" /></td>
								<td class="ppo-report__group-label">{{ order.group_label || "—" }}</td>
								<td v-for="position in maxColumns" :key="`${order.name}-${position}`" class="erp-number ppo-report__quantity">{{ displayQuantity(order.qty_by_position?.[position - 1]) }}</td>
								<td class="erp-number ppo-report__total">{{ number(order.total) }}</td>
								<td class="ppo-report__transfer">{{ order.transfer_summary || "—" }}</td>
								<td class="ppo-report__comments">{{ order.comments || "—" }}</td>
							</tr>
							<tr v-if="isExpanded(order.name)" class="ppo-report__dispatch-row">
								<td :colspan="columnCount">
									<div class="ppo-report__dispatch">
										<TransferSummary v-if="order.transfer_movements?.length" :movements="order.transfer_movements" />
										<DispatchSummary :payload="dispatchByOrder[order.name]" />
									</div>
								</td>
							</tr>
						</template>
					</tbody>
					<tfoot>
						<tr>
							<th :colspan="fixedBeforeGroup">Total</th>
							<td></td>
							<td v-for="index in maxColumns" :key="`total-${index}`" class="erp-number">{{ displayQuantity(positionTotal(index - 1)) }}</td>
							<td class="erp-number">{{ number(summary.total_quantity) }}</td><td></td><td></td>
						</tr>
					</tfoot>
				</table>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="PPO Report could not be generated" @dismiss="error = ''" />
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Select from "primevue/select"
import Tag from "primevue/tag"
import { computed, defineComponent, h, reactive, ref } from "vue"

import { downloadPpoReport, getPpoDispatchSummary, getPpoDispatchSummaryBulk, getPpoReport } from "../../api/sales.js"
import DateField from "../../components/common/DateField.vue"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { formatDate, number } from "../../components/reports/reportUtils.js"
import AsyncLinkMultiSelect from "../cutting/reports/AsyncLinkMultiSelect.vue"

defineProps({ canExport: { type: Boolean, default: false } })

const statusOptions = [
	{ label: "All statuses", value: "" },
	...["Draft", "PPO Request", "Open", "Pending Request", "Item Changed", "Not Processed", "Close Request", "Closed"].map((value) => ({ label: value, value })),
]
const filters = reactive(defaultFilters())
const applied = ref({})
const payload = ref(emptyPayload())
const generated = ref(false)
const loading = ref(false)
const downloading = ref(false)
const bulkLoading = ref(false)
const error = ref("")
const expandedOrders = ref(new Set())
const dispatchLoading = ref("")
const dispatchByOrder = reactive({})
const showFabric = ref(false)
const showDia = ref(false)
const showGsm = ref(false)
const sortState = reactive({ key: "delivery_date", direction: "asc" })

const orders = computed(() => payload.value.orders || [])
const sizeGroups = computed(() => payload.value.size_groups || [])
const maxColumns = computed(() => Number(payload.value.max_columns || 0))
const summary = computed(() => payload.value.summary || emptyPayload().summary)
const allSummarized = computed(() => orders.value.length > 0 && expandedOrders.value.size === orders.value.length)
const optionalColumnCount = computed(() => [showFabric.value, showDia.value, showGsm.value].filter(Boolean).length)
const fixedBeforeGroup = computed(() => 9 + optionalColumnCount.value)
const columnCount = computed(() => fixedBeforeGroup.value + 1 + maxColumns.value + 3)
const matrixStyle = computed(() => ({ minWidth: `${Math.max(1240, 1030 + optionalColumnCount.value * 92 + maxColumns.value * 66)}px` }))
const periodLabel = computed(() => {
	const from = applied.value.from_date ? formatDate(applied.value.from_date) : "Beginning"
	const to = applied.value.to_date ? formatDate(applied.value.to_date) : "Today"
	return `${from} — ${to}`
})
const sortedOrders = computed(() => {
	const rows = [...orders.value]
	const key = sortState.key
	const direction = sortState.direction === "asc" ? 1 : -1
	return rows.sort((left, right) => {
		const a = String(left?.[key] || ""), b = String(right?.[key] || "")
		if (!a && !b) return 0
		if (!a) return 1
		if (!b) return -1
		return a.localeCompare(b, undefined, { numeric: true }) * direction
	})
})

function defaultFilters() { return { status: "", productCategory: "", items: [], fromDate: "", toDate: "" } }
function emptyPayload() { return { orders: [], size_groups: [], max_columns: 0, summary: { total_orders: 0, total_quantity: 0, size_groups: 0 } } }
function requestFilters() { return { status: filters.status, product_category: filters.productCategory, item: [...filters.items], from_date: filters.fromDate, to_date: filters.toDate } }
function displayQuantity(value) { return Number(value || 0) === 0 ? "—" : number(value) }
function displayNumber(value) { return value === null || value === undefined || value === "" || Number(value) === 0 ? "—" : number(value) }
function statusSeverity(status) { return ({ Open: "success", "PPO Request": "warn", "Pending Request": "warn", "Close Request": "warn", Closed: "secondary", "Item Changed": "danger" })[status] || "info" }
function positionTotal(index) { return orders.value.reduce((total, order) => total + Number(order.qty_by_position?.[index] || 0), 0) }
function isExpanded(name) { return expandedOrders.value.has(name) }
function sortIcon(key) { return sortState.key !== key ? "pi pi-sort-alt" : sortState.direction === "asc" ? "pi pi-sort-amount-up-alt" : "pi pi-sort-amount-down" }
function sortBy(key) {
	if (sortState.key === key) sortState.direction = sortState.direction === "asc" ? "desc" : "asc"
	else { sortState.key = key; sortState.direction = "asc" }
}

async function generate() {
	loading.value = true
	error.value = ""
	try {
		const request = requestFilters()
		payload.value = await getPpoReport(request) || emptyPayload()
		applied.value = request
		generated.value = true
		expandedOrders.value = new Set()
		Object.keys(dispatchByOrder).forEach((key) => delete dispatchByOrder[key])
	} catch (reason) {
		error.value = reason?.message || "Unable to generate the PPO Report."
	} finally {
		loading.value = false
	}
}

async function toggleDispatch(name) {
	const next = new Set(expandedOrders.value)
	if (next.has(name)) { next.delete(name); expandedOrders.value = next; return }
	next.add(name)
	expandedOrders.value = next
	if (dispatchByOrder[name]) return
	dispatchLoading.value = name
	try {
		dispatchByOrder[name] = await getPpoDispatchSummary(name) || { sizes: [], rows: [] }
	} catch (reason) {
		next.delete(name)
		expandedOrders.value = new Set(next)
		error.value = reason?.message || `Unable to load dispatch details for ${name}.`
	} finally {
		dispatchLoading.value = ""
	}
}

async function toggleAllSummaries(checked) {
	if (!checked) { expandedOrders.value = new Set(); return }
	if (!orders.value.length || bulkLoading.value) return
	bulkLoading.value = true
	error.value = ""
	try {
		const names = orders.value.map((order) => order.name)
		const result = await getPpoDispatchSummaryBulk(names) || {}
		for (const name of names) dispatchByOrder[name] = result[name] || { sizes: [], rows: [] }
		expandedOrders.value = new Set(names)
	} catch (reason) {
		error.value = reason?.message || "Unable to summarize PPO dispatches."
	} finally {
		bulkLoading.value = false
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
	expandedOrders.value = new Set()
	Object.keys(dispatchByOrder).forEach((key) => delete dispatchByOrder[key])
	error.value = ""
}

const TransferSummary = defineComponent({
	props: { movements: { type: Array, default: () => [] } },
	setup(props) {
		return () => h("section", { class: "ppo-report__transfer-panel" }, [
			h("strong", "Quantity transfer"),
			...props.movements.map((movement) => h("div", { class: "ppo-report__transfer-movement" }, [
				h("span", { class: ["ppo-report__movement", movement.movement === "Reduced" ? "is-reduced" : "is-added"] }, movement.movement),
				h("b", number(movement.quantity)),
				h("span", `${movement.movement === "Reduced" ? "to" : "from"} ${movement.counterpart_production_order || "—"}`),
				h("small", Object.entries(movement.sizes || {}).map(([size, quantity]) => `${size}: ${number(quantity)}`).join(" · ")),
			])),
		])
	},
})

const DispatchSummary = defineComponent({
	props: { payload: { type: Object, default: () => ({ sizes: [], rows: [] }) } },
	setup(props) {
		return () => {
			const sizes = props.payload?.sizes || [], rows = props.payload?.rows || []
			if (!rows.length) return h("div", { class: "ppo-report__dispatch-empty" }, [h("i", { class: "pi pi-truck" }), h("span", "No submitted dispatches for this Production Order.")])
			return h("section", { class: "ppo-report__dispatch-panel" }, [h("strong", { class: "ppo-report__dispatch-title" }, "Dispatch summary"), h("table", { class: "ppo-report__dispatch-table" }, [
				h("thead", [h("tr", [h("th", "Posting date"), h("th", "Lot"), ...sizes.map((size) => h("th", { class: "erp-number" }, size)), h("th", { class: "erp-number" }, "Total")])]),
				h("tbody", rows.map((row) => h("tr", [h("td", formatDate(row.date)), h("td", row.lot || "—"), ...sizes.map((size) => h("td", { class: "erp-number" }, displayQuantity(row.sizes?.[size]))), h("td", { class: "erp-number" }, number(row.total))]))),
			])])
		}
	},
})
</script>

<style scoped>
.ppo-report { width: 100%; max-width: 100%; min-width: 0; overflow: hidden; }
.ppo-report__toolbar { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
.ppo-report__heading { display: grid; gap: 2px; }
.ppo-report__heading strong { color: var(--erp-text); font-size: 14px; }
.ppo-report__heading span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.ppo-report__controls { display: flex; align-items: center; justify-content: flex-end; gap: 4px 14px; flex-wrap: wrap; }
.ppo-report__column-toggle { display: inline-flex; align-items: center; gap: 7px; min-height: 32px; color: var(--erp-text-muted); font-size: 12px; font-weight: 650; cursor: pointer; user-select: none; }
.ppo-report__column-toggle:hover { color: var(--erp-text); }
.ppo-report__column-toggle.is-disabled { opacity: .6; cursor: wait; }
.ppo-report__column-toggle :deep(.p-checkbox) { width: 16px; height: 16px; }
.ppo-report__column-toggle :deep(.p-checkbox-box) { width: 16px; height: 16px; border-radius: 4px; }
.ppo-report__matrix-wrap { contain: layout paint inline-size; width: 100%; max-width: 100%; min-width: 0; max-height: calc(100vh - 360px); overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); overscroll-behavior: contain; scrollbar-color: #8ca39a #edf2f0; scrollbar-width: auto; }
.ppo-report__matrix-wrap::-webkit-scrollbar { width: 11px; height: 11px; }
.ppo-report__matrix-wrap::-webkit-scrollbar-track { background: #edf2f0; border-radius: 6px; }
.ppo-report__matrix-wrap::-webkit-scrollbar-thumb { background: #8ca39a; border: 2px solid #edf2f0; border-radius: 6px; }
.ppo-report__matrix-wrap::-webkit-scrollbar-thumb:hover { background: #617b71; }
.ppo-report__matrix { width: 100%; border-collapse: separate; border-spacing: 0; color: var(--erp-text); font-size: var(--erp-font-size-table); }
.ppo-report__matrix th, .ppo-report__matrix td { min-width: 66px; padding: 8px 9px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); vertical-align: middle; white-space: nowrap; }
.ppo-report__matrix thead th { color: var(--erp-text-muted); background: #f0f4f3; font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .035em; text-transform: uppercase; }
.ppo-report__size-group-row th { height: 29px; padding-top: 5px; padding-bottom: 5px; background: #f7faf9; }
.ppo-report__size-group-row .ppo-report__size-group, .ppo-report__size-group-row .ppo-report__size-column { color: #087654; background: #e8f7f0; text-align: center; }
.ppo-report__main-header th { border-top: 1px solid #dce6e2; }
.ppo-report__sort { display: inline-flex; align-items: center; gap: 5px; padding: 0; color: inherit; font: inherit; font-weight: inherit; letter-spacing: inherit; text-transform: inherit; background: transparent; border: 0; cursor: pointer; }
.ppo-report__sort i { color: #82958e; font-size: 10px; }
.ppo-report__matrix tbody tr:hover > td, .ppo-report__matrix tbody tr:hover > th { background: #f7fbf9; }
.ppo-report__matrix tbody th { text-align: left; }
.ppo-report__matrix tbody small { display: block; margin-top: 2px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 500; }
.ppo-report__matrix tfoot th, .ppo-report__matrix tfoot td { position: sticky; bottom: 0; z-index: 2; background: #edf8f3; border-top: 1px solid var(--erp-border-strong); border-bottom: 0; font-weight: 800; }
.ppo-report__matrix tfoot th { color: #087654; text-align: right; text-transform: uppercase; }
.ppo-report__index { color: var(--erp-text-muted); }
.ppo-report__ppo { min-width: 132px !important; }
.ppo-report__ppo a { color: #076c51; font-weight: 800; text-decoration: none; }
.ppo-report__ppo a:hover { text-decoration: underline; }
.ppo-report__item { min-width: 185px !important; }
.ppo-report__group-label { min-width: 112px !important; color: #315147; font-weight: 750; }
.ppo-report__size-column { text-align: center; }
.ppo-report__quantity { background: #f4fbf7; font-weight: 700; }
.ppo-report__total { color: #087654; font-weight: 850; }
.ppo-report__transfer, .ppo-report__comments { min-width: 190px !important; max-width: 280px; white-space: pre-line !important; }
.ppo-report__dispatch-row > td { padding: 0 !important; background: #f8fbfa; }
.ppo-report__dispatch { display: grid; grid-template-columns: minmax(260px, .7fr) minmax(440px, 1.3fr); gap: 18px; padding: 14px 16px 16px; }
.ppo-report__transfer-panel, .ppo-report__dispatch-panel { min-width: 0; }
.ppo-report__transfer-panel > strong, .ppo-report__dispatch-title { display: block; margin-bottom: 8px; color: #315147; font-size: 12px; text-transform: uppercase; letter-spacing: .035em; }
.ppo-report__transfer-movement { display: grid; grid-template-columns: auto auto 1fr; align-items: center; gap: 5px 8px; padding: 7px 8px; border: 1px solid var(--erp-border); border-radius: 7px; background: white; }
.ppo-report__transfer-movement + .ppo-report__transfer-movement { margin-top: 6px; }
.ppo-report__transfer-movement small { grid-column: 2 / -1; margin: 0; }
.ppo-report__movement { padding: 2px 6px; border-radius: 999px; font-size: 10px; font-weight: 800; text-transform: uppercase; }
.ppo-report__movement.is-reduced { color: #a53a32; background: #fff0ee; }
.ppo-report__movement.is-added { color: #087654; background: #e7f7ef; }
.ppo-report__dispatch-table { width: 100%; border-collapse: collapse; background: var(--erp-surface); }
.ppo-report__dispatch-table th, .ppo-report__dispatch-table td { min-width: 78px; padding: 7px 9px; border: 1px solid var(--erp-border); font-size: 12px; }
.ppo-report__dispatch-table th { color: var(--erp-text-muted); background: #eef3f1; text-transform: uppercase; }
.ppo-report__dispatch-empty { display: flex; align-items: center; gap: 8px; color: var(--erp-text-muted); font-size: 12px; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }

@media (max-width: 800px) {
	.ppo-report__toolbar { align-items: stretch; flex-direction: column; }
	.ppo-report__controls { justify-content: flex-start; }
	.ppo-report__dispatch { grid-template-columns: 1fr; }
}
</style>
