<template>
	<ReportShell title="Supplier Pending Report" generate-label="Show Report" :generated="generated" :loading="loading" :error="loadError" :has-results="report.items.length > 0" :generate-disabled="Boolean(hint)" copyable empty-title="No pending quantities were found for the selected Supplier and Process." empty-description="" @generate="load" @reset="reset">
		<template #filters>
			<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" required :show-open-button="false" show-clear />
			<LinkField v-model="filters.process" doctype="YRP Process" label="Process" required :show-open-button="false" show-clear />
			<small v-if="hint" class="erp-help-text" role="status">{{ hint }}</small>
		</template>
		<div class="supplier-pending">
			<h3 class="supplier-pending__supplier">{{ report.supplier_name || report.supplier }}</h3>
			<section v-for="item in report.items" :key="item.item" class="supplier-pending__item" :aria-label="`Item ${item.item}`">
				<h4>Item: {{ item.item }}</h4>
				<article v-for="lot in item.lots" :key="lot.lot" class="supplier-pending__lot">
					<p class="supplier-pending__lot-heading"><span>Lot</span> <strong>{{ lot.lot }}</strong> <small>{{ lot.rows.length }} pending {{ lot.rows.length === 1 ? "row" : "rows" }}</small></p>
					<div class="finishing-scroll" role="region" :aria-label="`Lot ${lot.lot}`" tabindex="0">
						<table class="finishing-table report-table">
							<thead><tr>
								<th class="report-cell--num">S.No</th><th class="report-cell--text">Colour</th><th v-if="lot.is_set_item" class="report-cell--text">{{ lot.set_attr || "Part" }}</th><th class="report-cell--text">Type</th>
								<th v-for="size in lot.primary_values" :key="size" class="report-cell--num report-align-right">{{ size }}</th>
								<th class="report-cell--num report-align-right">Total</th><th class="report-cell--date">First Date</th><th class="report-cell--date">Last Date</th><th class="report-cell--num report-align-right">Diff</th>
							</tr></thead>
							<tbody>
								<template v-for="(row, index) in lot.rows" :key="`${row.colour}-${row.part || ''}`">
									<tr v-for="kind in KINDS" :key="kind.key" :class="{ 'supplier-pending__difference': kind.key === 'difference' }">
										<template v-if="kind.key === 'delivered'"><td rowspan="3" class="report-cell--num">{{ index + 1 }}</td><td rowspan="3" class="report-cell--text">{{ row.colour }}</td><td v-if="lot.is_set_item" rowspan="3" class="report-cell--text">{{ row.part || "-" }}</td></template>
										<td class="report-cell--text">{{ kind.label }}</td>
										<td v-for="size in lot.primary_values" :key="size" :class="cellClass(kind, row.values[size])">{{ quantity(row.values[size]?.[kind.key]) }}</td>
										<td :class="['supplier-pending__total', cellClass(kind, row.totals)]">{{ quantity(row.totals[kind.key]) }}</td>
										<td class="report-cell--date">{{ rowDate(row.dates, kind, "first") }}</td><td class="report-cell--date">{{ rowDate(row.dates, kind, "last") }}</td>
										<td v-if="kind.key === 'delivered'" rowspan="3" class="report-cell--num report-align-right">{{ row.dates.diff_days ?? "-" }}</td>
									</tr>
								</template>
								<template v-for="total in lot.totals" :key="`total-${total.part || 'item'}`">
									<tr v-for="kind in KINDS" :key="kind.key" class="supplier-pending__summary">
										<template v-if="kind.key === 'delivered'"><td rowspan="3" /><td rowspan="3" class="report-cell--text"><strong>Total</strong></td><td v-if="lot.is_set_item" rowspan="3" class="report-cell--text"><strong>{{ total.part || "-" }}</strong></td></template>
										<td class="report-cell--text">{{ kind.label }}</td>
										<td v-for="size in lot.primary_values" :key="size" :class="cellClass(kind, total.values[size])">{{ quantity(total.values[size]?.[kind.key]) }}</td>
										<td :class="['supplier-pending__total', cellClass(kind, total.totals)]">{{ quantity(total.totals[kind.key]) }}</td>
										<td /><td /><td v-if="kind.key === 'delivered'" rowspan="3" />
									</tr>
								</template>
							</tbody>
						</table>
					</div>
				</article>
			</section>
		</div>
	</ReportShell>
</template>

<script setup>
import { useReportQueryPrefill } from "../../../composables/useReportQueryPrefill.js"
import { computed, reactive, ref, watch } from "vue"
import { getSupplierPendingReport } from "../../../api/planning.js"
import LinkField from "../../../components/common/LinkField.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { differenceTone, supplierPendingHint } from "./supplierPending.js"

const KINDS = [{ key: "delivered", label: "Delivered", date: "dc" }, { key: "received", label: "Received", date: "grn" }, { key: "difference", label: "Difference" }]
const emptyReport = () => ({ supplier: "", supplier_name: "", items: [] })
const filters = reactive({ supplier: "", process: "" })
const hint = computed(() => supplierPendingHint(filters))
const report = ref(emptyReport())
const loading = ref(false)
const generated = ref(false)
const loadError = ref("")
let request = 0

watch(filters, () => { ++request; report.value = emptyReport(); generated.value = false; loading.value = false; loadError.value = "" }, { deep: true, flush: "sync" })

async function load() {
	if (hint.value) return
	const current = ++request
	loading.value = true
	loadError.value = ""
	try {
		const result = await getSupplierPendingReport(filters.supplier, filters.process)
		if (current !== request) return
		report.value = { ...emptyReport(), ...result, items: Array.isArray(result?.items) ? result.items : [] }
		generated.value = true
	} catch (error) {
		if (current === request) loadError.value = error.message || "Unable to load the Supplier Pending Report."
	} finally {
		if (current === request) loading.value = false
	}
}

function reset() { Object.assign(filters, { supplier: "", process: "" }) }
function quantity(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 }) }
function rowDate(dates, kind, edge) { return kind.date ? formatDisplayDate(dates?.[`${edge}_${kind.date}_date`], "-") : "" }
function cellClass(kind, value) {
	const tone = kind.key === "difference" ? ` supplier-pending__tone--${differenceTone(value?.received, value?.delivered)}` : ""
	return `report-cell--num report-align-right${tone}`
}
useReportQueryPrefill(filters, ["supplier", "process"], load)
</script>

<style scoped>
.supplier-pending { display: grid; min-width: 0; gap: var(--erp-space-4); }
.supplier-pending :is(h3, h4, p) { margin: 0; }
.supplier-pending__item, .supplier-pending__lot { display: grid; min-width: 0; gap: var(--erp-space-2); }
.supplier-pending__lot-heading small { color: var(--erp-text-muted); }
.supplier-pending__summary td { background: var(--erp-surface-muted); font-weight: 600; }
.supplier-pending__total { font-weight: 600; }
.supplier-pending__tone--negative { background: var(--erp-danger-soft); }
.supplier-pending__tone--positive { background: var(--erp-success-soft); }
.supplier-pending__tone--zero { background: var(--erp-warning-soft); }
</style>
