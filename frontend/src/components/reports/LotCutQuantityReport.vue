<template>
	<ReportShell :export-source="{ doctype: 'SD YRP Lot' }"
		class="lot-cut-quantity-report"
		title="Lot Cut Quantity"
		:generated="generated"
		:loading="loading"
		:error="error"
		:has-results="resultLots.length > 0"
		:generate-disabled="Boolean(lotValidation)"
		copyable
		@generate="generate"
		@reset="reset"
	>
		<template #filters>
			<AsyncLinkMultiSelect
				v-model="selectedLots"
				doctype="SD YRP Lot"
				label="Lot"
				placeholder="Search and add Lots…"
				:help-text="lotHelpText"
			/>
		</template>

		<template #metrics>
			<div class="report-metric"><i class="pi pi-tags" /><div><span>Lots</span><strong>{{ number(resultLots.length) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-file" /><div><span>Cutting Plans</span><strong>{{ number(planCount) }}</strong></div></div>
			<div class="report-metric"><i class="pi pi-check-circle" /><div><span>Completed rows</span><strong>{{ number(rowCounts.completed) }} / {{ number(rowCounts.total) }}</strong></div></div>
		</template>

		<div class="lot-cut-quantity-report__lots">
			<section v-for="lot in resultLots" :key="lot.lot" class="lot-cut-quantity-report__lot">
				<header class="lot-cut-quantity-report__lot-header">
					<div>
						<span>Lot</span>
						<h2>{{ lot.lot }}</h2>
					</div>
					<p><span>Item</span><strong>{{ firstPlanItem(lot) || "—" }}</strong></p>
				</header>

				<div v-if="!lot.cutting_plans?.length" class="lot-cut-quantity-report__no-plan">
					<i class="pi pi-info-circle" aria-hidden="true" />
					<span>No Cutting Plan for this Lot.</span>
				</div>
				<div v-else class="lot-cut-quantity-report__plans">
					<section v-for="plan in lot.cutting_plans" :key="plan.name" class="lot-cut-quantity-report__plan">
						<header class="lot-cut-quantity-report__plan-header">
							<div>
								<span>Cutting Plan</span>
								<RouterLink v-if="canReadCuttingPlan" :to="{ name: 'cutting-plan', params: { cuttingPlanId: plan.name } }">{{ plan.name }}</RouterLink>
								<strong v-else>{{ plan.name }}</strong>
							</div>
							<p v-if="plan.item && plan.item !== firstPlanItem(lot)">{{ plan.item }}</p>
						</header>
						<CuttingCompletedReport
							:doc="planDoc(lot, plan)"
							:groups="plan.completed_items"
							:generated-at="generatedAt"
							:reference-value="plan.name"
							show-completion
							:show-meta="false"
						/>
					</section>
				</div>
			</section>
		</div>
	</ReportShell>
</template>

<script setup>
import { computed, ref } from "vue"

import { getLotCutQuantity } from "../../api/purchaseReports.js"
import CuttingCompletedReport from "../../departments/cutting/CuttingCompletedReport.vue"
import { normaliseCompletedGroups } from "../../departments/cutting/cuttingCompletedReport.js"
import AsyncLinkMultiSelect from "../../departments/cutting/reports/AsyncLinkMultiSelect.vue"
import ReportShell from "./ReportShell.vue"
import { errorMessage, number } from "./reportUtils.js"
import { formatDisplayDatetime } from "../../utils/dateFormat.js"

const props = defineProps({
	canReadCuttingPlan: { type: Boolean, default: false },
})

const maximumLots = 20
const selectedLots = ref([])
const resultLots = ref([])
const generated = ref(false)
const loading = ref(false)
const error = ref("")
const generatedAt = ref("")
const lotValidation = computed(() => {
	if (!selectedLots.value.length) return "Select at least one Lot to generate the report."
	if (selectedLots.value.length > maximumLots) return `Select no more than ${maximumLots} Lots.`
	return ""
})
const lotHelpText = computed(() => lotValidation.value || `Choose up to ${maximumLots} Lots. Blocks follow the selected order.`)
const planCount = computed(() => resultLots.value.reduce((count, lot) => count + (lot.cutting_plans?.length || 0), 0))
const rowCounts = computed(() => resultLots.value.reduce((counts, lot) => {
	for (const plan of lot.cutting_plans || []) {
		for (const group of normaliseCompletedGroups(plan.completed_items)) {
			for (const item of group.items || []) {
				counts.total += 1
				if (item.completed) counts.completed += 1
			}
		}
	}
	return counts
}, { completed: 0, total: 0 }))

async function generate() {
	if (lotValidation.value) {
		error.value = lotValidation.value
		return
	}
	error.value = ""
	loading.value = true
	try {
		const response = await getLotCutQuantity(selectedLots.value) || {}
		resultLots.value = response.lots || []
		generatedAt.value = formatDisplayDatetime(new Date())
		generated.value = true
	} catch (exception) {
		error.value = errorMessage(exception, "Unable to generate the Lot Cut Quantity report.")
	} finally {
		loading.value = false
	}
}

function reset() {
	selectedLots.value = []
	resultLots.value = []
	generated.value = false
	error.value = ""
	generatedAt.value = ""
}

function firstPlanItem(lot) {
	return lot.cutting_plans?.[0]?.item || ""
}

function planDoc(lot, plan) {
	return { name: plan.name, lot: lot.lot, item: plan.item, version: plan.version }
}
</script>

<style scoped>
.lot-cut-quantity-report__lots,
.lot-cut-quantity-report__plans {
	display: grid;
	gap: var(--erp-space-3);
}

.lot-cut-quantity-report__lot {
	min-width: 0;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	overflow: hidden;
}

.lot-cut-quantity-report__lot-header,
.lot-cut-quantity-report__plan-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
}

.lot-cut-quantity-report__lot-header {
	padding: var(--erp-space-3) var(--erp-space-4);
	background: var(--erp-accent-soft);
	border-bottom: 1px solid var(--erp-border);
}

.lot-cut-quantity-report__lot-header > div,
.lot-cut-quantity-report__lot-header p,
.lot-cut-quantity-report__plan-header > div {
	display: grid;
	gap: 3px;
	margin: 0;
}

.lot-cut-quantity-report__lot-header span,
.lot-cut-quantity-report__plan-header div > span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: .035em;
	text-transform: uppercase;
}

.lot-cut-quantity-report__lot-header h2 {
	margin: 0;
	color: var(--erp-accent-hover);
	font-size: 18px;
}

.lot-cut-quantity-report__lot-header p { text-align: right; }
.lot-cut-quantity-report__lot-header strong { color: var(--erp-text); }

.lot-cut-quantity-report__plans { padding: var(--erp-space-3); }

.lot-cut-quantity-report__plan {
	min-width: 0;
	padding: var(--erp-space-3);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.lot-cut-quantity-report__plan-header { margin-bottom: var(--erp-space-3); }
.lot-cut-quantity-report__plan-header a,
.lot-cut-quantity-report__plan-header strong { color: var(--erp-accent-hover); font-weight: 750; }
.lot-cut-quantity-report__plan-header p { margin: 0; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }

.lot-cut-quantity-report__no-plan {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
	padding: var(--erp-space-4);
	color: var(--erp-text-muted);
}

.lot-cut-quantity-report__no-plan i { color: var(--erp-accent); }

@media (max-width: 600px) {
	.lot-cut-quantity-report__lot-header,
	.lot-cut-quantity-report__plan-header { align-items: flex-start; flex-direction: column; }
	.lot-cut-quantity-report__lot-header p { text-align: left; }
	.lot-cut-quantity-report__plans,
	.lot-cut-quantity-report__plan { padding: var(--erp-space-2); }
}
</style>
