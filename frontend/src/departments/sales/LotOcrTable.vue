<template>
	<div class="ppo-lot-ocr__table-wrap" tabindex="0" role="region" aria-label="Lot OCR process quantities">
		<table>
			<thead>
				<tr><th>S.No</th><th>Process</th><th>Documents</th><th>Type</th><th v-for="size in sizes" :key="size">{{ size }}</th><th>Total</th></tr>
			</thead>
			<tbody>
				<template v-for="(process, processIndex) in processRows" :key="process.name">
					<tr class="ppo-lot-ocr__process-start">
						<td rowspan="3" class="ppo-lot-ocr__serial">{{ processIndex + 1 }}</td>
						<th rowspan="3" class="ppo-lot-ocr__process"><DocumentLink doctype="YRP Process" :name="process.name" /></th>
						<td rowspan="3" class="ppo-lot-ocr__documents">
							<div v-if="process.wo_list.length"><span>Work Orders</span><template v-for="document in process.wo_list" :key="document"><RouterLink v-if="linked" :to="webDocumentRoute('YRP Work Order', document)">{{ document }}</RouterLink><strong v-else>{{ document }}</strong></template></div>
							<div v-if="process.cp_list.length"><span>Cutting Plans</span><template v-for="document in process.cp_list" :key="document"><RouterLink v-if="linked" :to="webDocumentRoute('SD YRP Cutting Plan', document)">{{ document }}</RouterLink><strong v-else>{{ document }}</strong></template></div>
							<em v-if="!process.wo_list.length && !process.cp_list.length">—</em>
						</td>
						<th>Sent</th>
						<td v-for="size in sizes" :key="`${process.name}-sent-${size}`">{{ formatNumber(quantity(process, size, "sent")) }}</td>
						<td class="ppo-lot-ocr__total">{{ formatNumber(process.total_sent) }}</td>
					</tr>
					<tr>
						<th>Received</th>
						<td v-for="size in sizes" :key="`${process.name}-received-${size}`">{{ formatNumber(quantity(process, size, "received")) }}</td>
						<td class="ppo-lot-ocr__total">{{ formatNumber(process.total_received) }}</td>
					</tr>
					<tr class="ppo-lot-ocr__difference">
						<th>Difference</th>
						<td v-for="size in sizes" :key="`${process.name}-difference-${size}`" :class="differenceClass(difference(process, size))">{{ signedNumber(difference(process, size)) }}</td>
						<td class="ppo-lot-ocr__total" :class="differenceClass(totalDifference(process))">{{ signedNumber(totalDifference(process)) }}</td>
					</tr>
				</template>
				<tr v-if="!processRows.length" class="ppo-lot-ocr__empty"><td :colspan="sizes.length + 5">No submitted Work Order movement is available for this Lot.</td></tr>
				<tr class="ppo-lot-ocr__dispatch">
					<td class="ppo-lot-ocr__serial">—</td><th>Dispatch</th>
					<td class="ppo-lot-ocr__documents"><div v-if="finishingPlans.length"><span>Finishing Plans</span><template v-for="document in finishingPlans" :key="document"><RouterLink v-if="linked" :to="webDocumentRoute('SD YRP Finishing Plan', document)">{{ document }}</RouterLink><strong v-else>{{ document }}</strong></template></div><em v-else>—</em></td>
					<th>Dispatched</th>
					<td v-for="size in sizes" :key="`dispatch-${size}`">{{ formatNumber(dispatchDetail[size]) }}</td>
					<td class="ppo-lot-ocr__total">{{ formatNumber(view.totalDispatch) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../components/common/DocumentLink.vue"
import { RouterLink } from "vue-router"

import { webDocumentRoute } from "../../router/webDocumentRoutes.js"
import { lotOcrView } from "./lotOcrView.js"

const props = defineProps({
	payload: { type: Object, default: () => ({}) },
	linked: { type: Boolean, default: false },
})

const view = computed(() => lotOcrView(props.payload))
const sizes = computed(() => view.value.sizes)
const processRows = computed(() => view.value.processRows)
const dispatchDetail = computed(() => view.value.dispatchDetail)
const finishingPlans = computed(() => view.value.finishingPlans)

function number(value) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed : 0 }
function formatNumber(value) { return number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function quantity(process, size, field) { return number(process.data?.[size]?.[field]) }
function difference(process, size) { return quantity(process, size, "received") - quantity(process, size, "sent") }
function totalDifference(process) { return number(process.total_received) - number(process.total_sent) }
function signedNumber(value) { const numeric = number(value); return numeric > 0 ? `+${formatNumber(numeric)}` : formatNumber(numeric) }
function differenceClass(value) { return number(value) < 0 ? "ppo-lot-ocr__negative" : number(value) > 0 ? "ppo-lot-ocr__positive" : "" }
</script>

<style scoped>
.ppo-lot-ocr__documents span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: .045em; text-transform: uppercase; }
.ppo-lot-ocr__table-wrap { max-width: 100%; overflow: auto; }
.ppo-lot-ocr__table-wrap:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: -2px; }
.ppo-lot-ocr__table-wrap table { width: 100%; min-width: 820px; border-collapse: collapse; font-variant-numeric: tabular-nums; }
.ppo-lot-ocr__table-wrap th, .ppo-lot-ocr__table-wrap td { height: 39px; padding: 7px 9px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); text-align: right; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.ppo-lot-ocr__table-wrap th:last-child, .ppo-lot-ocr__table-wrap td:last-child { border-right: 0; }
.ppo-lot-ocr__table-wrap thead th { height: 35px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .035em; text-transform: uppercase; background: var(--erp-surface-muted); white-space: nowrap; }
.ppo-lot-ocr__table-wrap thead th:nth-child(-n + 4), .ppo-lot-ocr__table-wrap tbody th, .ppo-lot-ocr__table-wrap .ppo-lot-ocr__documents { text-align: left; }
.ppo-lot-ocr__serial { width: 54px; text-align: center !important; vertical-align: top; }
.ppo-lot-ocr__process { min-width: 135px; color: var(--erp-text) !important; font-weight: 780; vertical-align: top; background: var(--erp-surface-soft); }
.ppo-lot-ocr__documents { min-width: 190px; vertical-align: top; }
.ppo-lot-ocr__documents > div { display: grid; gap: 3px; margin-bottom: 8px; }
.ppo-lot-ocr__documents > div:last-child { margin-bottom: 0; }
.ppo-lot-ocr__documents strong, .ppo-lot-ocr__documents a { color: var(--erp-text); font-size: 11px; line-height: 1.35; overflow-wrap: anywhere; }
.ppo-lot-ocr__documents em { color: var(--erp-text-muted); font-style: normal; }
.ppo-lot-ocr__process-start > * { border-top: 2px solid color-mix(in srgb, var(--erp-border-strong) 70%, var(--erp-surface)); }
.ppo-lot-ocr__difference > * { background: color-mix(in srgb, var(--erp-surface-muted) 56%, var(--erp-surface)); }
.ppo-lot-ocr__total { color: var(--erp-text) !important; font-weight: 800; background: var(--erp-surface-soft); }
.ppo-lot-ocr__negative { color: var(--erp-danger) !important; font-weight: 780; }
.ppo-lot-ocr__positive { color: var(--erp-success-text) !important; font-weight: 780; }
.ppo-lot-ocr__dispatch > * { color: var(--erp-accent-hover); font-weight: 780; background: color-mix(in srgb, var(--erp-accent-soft) 54%, var(--erp-surface)); border-top: 2px solid var(--erp-accent-border); }
.ppo-lot-ocr__dispatch > th { text-align: left; }
.ppo-lot-ocr__empty td { height: 90px; color: var(--erp-text-muted); text-align: center; }
.ppo-lot-ocr__documents a { color: var(--erp-accent); text-decoration: none; }
</style>
