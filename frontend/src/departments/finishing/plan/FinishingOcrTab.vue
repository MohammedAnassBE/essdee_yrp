<template>
	<div class="finishing-ocr">
		<div class="finishing-ocr__switch" role="tablist" aria-label="OCR views">
			<button v-for="view in views" :key="view.value" type="button" role="tab" :aria-selected="active === view.value" class="finishing-ocr__switch-button" :class="{ 'is-active': active === view.value }" @click="active = view.value">{{ view.label }}</button>
		</div>

		<div v-if="active === 'details'" class="finishing-stack">
			<p v-if="!parts.length" class="finishing-empty">No OCR details yet.</p>
			<section v-for="part in parts" :key="part.name" class="finishing-ocr__part" :aria-label="`OCR ${part.title}`">
				<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`OCR quantities for ${part.title}`">
					<table class="finishing-table">
						<thead>
							<tr>
								<th colspan="2">{{ part.title }}</th>
								<th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th>
								<th class="erp-number">Total</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in part.model.summary" :key="row.label">
								<th colspan="2" scope="row">{{ row.label }}</th>
								<td v-for="(cell, index) in row.cells" :key="index" class="erp-number" :class="toneClass(cell.tone)">{{ formatQuantity(cell.value) }}</td>
								<td class="erp-number finishing-table__row-total" :class="toneClass(row.total.tone)">{{ formatQuantity(row.total.value) }}</td>
							</tr>
						</tbody>
						<tbody v-for="section in part.model.breakdowns" :key="section.label">
							<tr v-for="(row, rowIndex) in section.rows" :key="row.colour">
								<th v-if="rowIndex === 0" :rowspan="section.rows.length + 1" scope="rowgroup" class="finishing-ocr__group">{{ section.label }}</th>
								<th scope="row">{{ row.colour }}</th>
								<td v-for="(cell, index) in row.cells" :key="index" class="erp-number">{{ formatQuantity(cell.value) }}</td>
								<td class="erp-number finishing-table__row-total">{{ formatQuantity(row.total) }}</td>
							</tr>
							<tr class="finishing-ocr__subtotal">
								<th v-if="!section.rows.length" scope="rowgroup" class="finishing-ocr__group">{{ section.label }}</th>
								<th scope="row">Total</th>
								<td v-for="(value, index) in section.total.cells" :key="index" class="erp-number">{{ formatQuantity(value) }}</td>
								<td class="erp-number">{{ formatQuantity(section.total.total) }}</td>
							</tr>
						</tbody>
						<tbody>
							<tr>
								<th colspan="2" scope="row">{{ part.model.unaccountable.label }}</th>
								<td v-for="(cell, index) in part.model.unaccountable.cells" :key="index" class="erp-number" :class="toneClass(cell.tone)">{{ formatQuantity(cell.value) }}</td>
								<td class="erp-number finishing-table__row-total" :class="toneClass(part.model.unaccountable.total.tone)">{{ formatQuantity(part.model.unaccountable.total.value) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div class="finishing-scroll finishing-ocr__percentages" role="region" tabindex="0" :aria-label="`OCR percentages for ${part.title}`">
					<table class="finishing-table">
						<thead><tr><th>{{ part.name }}</th><th class="erp-number">Value</th><th class="erp-number">Difference</th></tr></thead>
						<tbody>
							<tr v-for="row in part.model.percentages" :key="row.label">
								<td>{{ row.label }}</td>
								<td class="erp-number">{{ row.value }}%</td>
								<td class="erp-number">{{ row.difference === "" ? "" : `${row.difference}%` }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>

		<template v-else>
			<div v-if="insight.loading" class="finishing-stack" :aria-label="`Loading ${activeLabel}`"><Skeleton height="40px" /><Skeleton height="180px" /></div>
			<WorkspaceLoadError v-else-if="insight.error" :title="`${activeLabel} unavailable`" :message="insight.error" @retry="loadInsight(active, true)" />
			<FinishingItemGroups v-else-if="active === 'consumption'" :sections="consumptionSections" />
			<FinishingItemGroups v-else :sections="stockSections" show-uom quantity-label="Balance Qty" />
		</template>
	</div>
</template>

<script setup>
import Skeleton from "primevue/skeleton"
import { computed, reactive, ref, watch } from "vue"

import { getFinishingPlanTab } from "../../../api/finishing.js"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import FinishingItemGroups from "../components/FinishingItemGroups.vue"
import { formatQuantity, ocrModel } from "../finishingViews.js"

const props = defineProps({
	name: { type: String, required: true },
	data: { type: Object, required: true },
})
const views = [
	{ value: "details", label: "OCR Details" },
	{ value: "consumption", label: "Consumption Details", tab: "ocr_consumption" },
	{ value: "stock", label: "Stock Balance", tab: "ocr_stock_balance" },
]
const active = ref("details")
const insights = reactive({})
const activeLabel = computed(() => views.find((view) => view.value === active.value)?.label || "")
const insight = computed(() => insights[active.value] || { loading: true })
const sizes = computed(() => props.data.primary_values || [])
const parts = computed(() => Object.entries(props.data.ocr_data || {}).map(([name, part]) => ({
	name,
	title: name === "Item" ? props.data.item : `${props.data.item} ${name}`,
	model: ocrModel(part, sizes.value),
})))
const consumptionSections = computed(() => (insights.consumption?.data?.processes || []).map((process) => ({ key: process.process, title: process.process, groups: process.groups || [] })))
const stockSections = computed(() => (insights.stock?.data?.warehouses || []).map((warehouse) => ({
	key: warehouse.warehouse,
	title: warehouse.warehouse_name && warehouse.warehouse_name !== warehouse.warehouse ? `${warehouse.warehouse_name} - ${warehouse.warehouse}` : warehouse.warehouse || warehouse.warehouse_name,
	groups: warehouse.groups || [],
})))
let token = 0

function toneClass(tone) {
	return tone ? `finishing-tone finishing-tone--${tone}` : ""
}

async function loadInsight(value, force = false) {
	const view = views.find((entry) => entry.value === value)
	if (!view?.tab || (insights[value] && !force)) return
	const requestToken = ++token
	const entry = { loading: true, error: "", data: null, token: requestToken }
	insights[value] = entry
	const plan = props.name
	try {
		const data = await getFinishingPlanTab(plan, view.tab)
		if (insights[value]?.token === requestToken && plan === props.name) Object.assign(insights[value], { data })
	} catch (reason) {
		if (insights[value]?.token === requestToken) insights[value].error = reason?.message || `Unable to load ${view.label}.`
	} finally {
		if (insights[value]?.token === requestToken) insights[value].loading = false
	}
}

watch(active, (value) => loadInsight(value))
watch(() => props.name, () => {
	Object.keys(insights).forEach((key) => delete insights[key])
	active.value = "details"
})
</script>

<style scoped>
.finishing-ocr { display: grid; min-width: 0; gap: 10px; }
.finishing-ocr__switch { display: flex; flex-wrap: wrap; gap: 4px; border-bottom: 1px solid var(--erp-border); }
.finishing-ocr__switch-button { min-height: var(--erp-control-height); padding: 8px 14px; color: var(--erp-text-secondary); background: none; border: 0; border-bottom: 2px solid transparent; font: inherit; font-size: var(--erp-font-size-table); font-weight: 650; cursor: pointer; }
.finishing-ocr__switch-button.is-active { color: var(--erp-accent-dark); border-bottom-color: var(--erp-accent); }
.finishing-ocr__part { display: grid; grid-template-columns: minmax(0, 3fr) minmax(240px, 1fr); align-items: start; gap: 12px; min-width: 0; }
.finishing-ocr__part th[scope="row"], .finishing-ocr__group { color: var(--erp-text); background: var(--erp-surface); font-weight: 650; text-align: left; }
.finishing-ocr__group { vertical-align: middle !important; white-space: normal !important; min-width: 120px; }
.finishing-ocr__subtotal > * { background: #e6e8eb !important; font-weight: 700; }
@media (max-width: 1100px) { .finishing-ocr__part { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 700px) { .finishing-ocr__switch { flex-wrap: nowrap; overflow-x: auto; } .finishing-ocr__switch-button { min-height: 44px; white-space: nowrap; } }
</style>
