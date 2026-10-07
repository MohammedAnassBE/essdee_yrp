<template>
	<ReportShell
		title="Cut Bundle Balance"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="rows.length > 0"
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="All lots" :show-open-button="false" show-clear />
			<LinkField v-model="filters.supplier" doctype="Supplier" label="Supplier" placeholder="All suppliers" :show-open-button="false" show-clear />
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-list" /><div><span>Balance rows</span><strong>{{ number(rows.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-box" /><div><span>Bundle quantity</span><strong>{{ number(totalQuantity) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-tags" /><div><span>Lots</span><strong>{{ number(uniqueLots) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-building" /><div><span>Suppliers</span><strong>{{ number(uniqueSuppliers) }}</strong></div></div>
		</template>

		<div class="erp-table-wrap cut-bundle-balance__table-wrap" role="region" aria-label="Cut Bundle Balance results" tabindex="0">
			<table class="erp-data-table cut-bundle-balance__table">
				<thead>
					<tr><th v-for="column in columns" :key="column.fieldname" :class="{ 'erp-number': numericColumn(column) }">{{ column.label }}</th></tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.name">
						<td v-for="column in columns" :key="column.fieldname" :class="{ 'erp-number': numericColumn(column) }">
							<strong v-if="column.fieldname === 'qty'">{{ number(row[column.fieldname]) }}</strong>
							<span v-else>{{ row[column.fieldname] || "—" }}</span>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</ReportShell>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getCutBundleBalance } from "../../api/cutPanelStore.js"
import LinkField from "../../components/common/LinkField.vue"
import ReportShell from "../../components/reports/ReportShell.vue"
import { errorMessage, number } from "../../components/reports/reportUtils.js"

const filters = reactive(defaultFilters())
const rows = ref([])
const columns = ref([])
const loading = ref(false)
const generated = ref(false)
const error = ref("")

const totalQuantity = computed(() => rows.value.reduce((total, row) => total + Number(row.qty || 0), 0))
const uniqueLots = computed(() => new Set(rows.value.map((row) => row.lot).filter(Boolean)).size)
const uniqueSuppliers = computed(() => new Set(rows.value.map((row) => row.supplier).filter(Boolean)).size)

function defaultFilters() {
	return { lot: "", supplier: "" }
}

function numericColumn(column) {
	return ["Int", "Float", "Currency"].includes(column?.fieldtype)
}

async function generate() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getCutBundleBalance({ lot: filters.lot, supplier: filters.supplier }) || {}
		columns.value = payload.columns || []
		rows.value = payload.result || []
		generated.value = true
	} catch (reason) {
		error.value = errorMessage(reason, "Unable to generate the Cut Bundle Balance report.")
	} finally {
		loading.value = false
	}
}

function reset() {
	Object.assign(filters, defaultFilters())
	rows.value = []
	columns.value = []
	generated.value = false
	error.value = ""
}
</script>

<style scoped>
.cut-bundle-balance__table-wrap{max-width:100%;overflow:auto}.cut-bundle-balance__table{min-width:1120px}.cut-bundle-balance__table td{max-width:220px}.cut-bundle-balance__table td span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.cut-bundle-balance__table td strong{color:var(--erp-accent-hover);font-variant-numeric:tabular-nums}
</style>
