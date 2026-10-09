<template>
	<section data-finishing-report="rework-completion" aria-label="Rework Completion">
		<ReportShell title="Rework Completion" :generated="generated" :loading="loading" :has-results="colours.length > 0" copyable keep-results-while-loading @generate="generate" @reset="reset">
			<template #filters>
				<LinkField v-model="filters.lot" doctype="SD YRP Lot" label="Lot" placeholder="Search lot…" required :show-open-button="false" show-clear />
				<LinkField v-model="filters.process" doctype="YRP Process" label="Process" placeholder="Search process…" required :show-open-button="false" show-clear />
			</template>
			<template #metrics>
				<div class="report-metric"><i class="pi pi-palette" /><div><span>Colours</span><strong>{{ formatQuantity(colours.length) }}</strong></div></div>
				<div class="report-metric"><i class="pi pi-check-circle" /><div><span>Reworked Pieces</span><strong>{{ formatQuantity(grandTotal) }}</strong></div></div>
			</template>
			<div class="finishing-stack">
				<FinishingReportHeading title="Rework Completion" :period="period" />
				<div class="finishing-scroll" role="region" tabindex="0" aria-label="Rework completion by colour and size">
					<table class="finishing-table">
						<thead>
							<tr>
								<th class="finishing-table__index">S.No</th>
								<th class="finishing-table__colour">Colour</th>
								<th v-if="data.is_set_item">{{ data.set_attr }}</th>
								<th class="finishing-table__type">Types</th>
								<th v-for="size in data.primary_values" :key="size" class="erp-number">{{ size }}</th>
								<th class="erp-number">Total</th>
							</tr>
						</thead>
						<tbody v-for="(colour, index) in colours" :key="colour">
							<tr v-for="(type, typeIndex) in data.types" :key="type">
								<template v-if="typeIndex === 0">
									<td :rowspan="data.types.length + 1" class="finishing-table__index">{{ index + 1 }}</td>
									<td :rowspan="data.types.length + 1" class="finishing-table__colour">{{ colour }}</td>
									<td v-if="data.is_set_item" :rowspan="data.types.length + 1">{{ data.data[colour].part }}</td>
								</template>
								<td class="finishing-table__type">{{ type }}</td>
								<td v-for="size in data.primary_values" :key="size" class="erp-number">{{ formatQuantity(data.data[colour].values?.[size]?.[type] ?? 0) }}</td>
								<td class="erp-number finishing-table__row-total">{{ formatQuantity(data.data[colour].type_wise_total?.[type] ?? 0) }}</td>
							</tr>
							<tr class="finishing-table__total-row">
								<td class="finishing-table__type">Total</td>
								<td v-for="size in data.primary_values" :key="size" class="erp-number">{{ formatQuantity(data.data[colour].size_wise_total?.[size] ?? 0) }}</td>
								<td class="erp-number">{{ formatQuantity(data.data[colour].colour_total?.total) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		</ReportShell>
		<DocumentErrorDialog :message="error" title="Rework Completion could not be generated" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import { computed, reactive, ref } from "vue"

import { getReworkCompletion } from "../../../api/finishing.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import { formatQuantity } from "../finishingViews.js"
import FinishingReportHeading from "./FinishingReportHeading.vue"
import { useReportRequest } from "./useReportRequest.js"

const filters = reactive({ lot: "", process: "" })
const data = ref({})
const period = ref("")
const { loading, generated, error, run, clear } = useReportRequest()
const colours = computed(() => Object.keys(data.value.data || {}))
const grandTotal = computed(() => colours.value.reduce((sum, colour) => sum + Number(data.value.data[colour].colour_total?.total || 0), 0))

function generate() {
	const message = !filters.lot ? "Select a Lot" : !filters.process ? "Select a Process" : ""
	const request = { lot: filters.lot, process: filters.process }
	run(message, () => getReworkCompletion(request), (value) => {
		data.value = value || {}
		period.value = `${request.lot} · ${request.process}`
	})
}

function reset() {
	Object.assign(filters, { lot: "", process: "" })
	data.value = {}
	clear()
}
</script>
