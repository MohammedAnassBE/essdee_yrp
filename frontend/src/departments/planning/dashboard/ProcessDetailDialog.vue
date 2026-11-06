<template>
	<Dialog :visible="visible" modal dismissable-mask :draggable="false" class="pf-modal pd-detail" @update:visible="emit('update:visible', $event)">
		<template #header>
			<div v-if="step" class="pf-modal__heading">
				<div class="pf-modal__title"><h2>{{ step.name }} · {{ mode === "size" ? "Size-wise" : "Colour-wise" }}</h2></div>
				<p>{{ row.lot }} · {{ isClothView ? "cloth per fabric in Kg" : row.item }} · {{ PROCESS_STATUS_LABELS[step.status] }}</p>
			</div>
		</template>
		<template v-if="step">
			<div class="pf-stats">
				<div class="pf-stat"><span>Delivered</span><b>{{ withUnit(measure.delivered, measure.units[0]) }}</b></div>
				<div class="pf-stat"><span>Received</span><b>{{ withUnit(measure.received, measure.units[1]) }}</b><i>{{ measure.percent.toFixed(1) }}%</i></div>
				<div v-if="step.kind === 'packing'" class="pf-stat"><span>Dispatch</span><b>{{ formatQuantity(step.dispatch) }}</b><i>{{ (step.finishing_plans || []).join(", ") || "no Finishing Plan" }}</i></div>
				<div class="pf-stat"><span>First DC</span><b>{{ formatDisplayDate(step.first_dc) }}</b></div>
				<div class="pf-stat"><span>Last GRN</span><b>{{ formatDisplayDate(step.last_grn) }}</b></div>
				<div class="pf-stat"><span>Work Orders</span><b>{{ step.work_orders.length }}</b></div>
			</div>
			<div class="pd-detail__legend"><LotToneLegend /><span class="pd-muted">· {{ LEGEND_NOTES[step.kind] }}</span></div>
			<div v-if="loading" class="pf-modal__loading"><Skeleton v-for="index in 4" :key="index" height="2.5rem" /></div>
			<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
			<template v-else-if="detail">
				<ProcessMatrixTable v-if="!isClothView" :matrix="matrix" :first-label="mode === 'size' ? 'Colour' : 'Size'" />
				<div v-for="fabric in isClothView ? detail.fabrics : []" :key="fabric.fabric" class="pd-detail__section">
					<h4>{{ fabric.fabric }}<template v-if="fabric.input"> · from {{ fabric.input }}</template> (delivered {{ formatQuantity(fabric.delivered, true) }} Kg)</h4>
					<table class="erp-data-table pf-table">
						<thead><tr><th>Colour · Dia</th><th class="erp-number">Planned Kg</th><th class="erp-number">Received Kg</th><th class="erp-number">Difference</th></tr></thead>
						<tbody>
							<tr v-for="line in fabric.rows" :key="`${line.colour}-${line.dia}`">
								<td><b>{{ [line.colour, line.dia].filter(Boolean).join(" · ") || "—" }}</b></td>
								<td class="erp-number">{{ formatQuantity(line.planned, true) }}</td>
								<td class="erp-number" :class="toneClass(statusTone(line.received, line.planned))">{{ formatQuantity(line.received, true) }}</td>
								<td class="erp-number" :class="toneClass(diffTone(line.received - line.planned, line.planned))">{{ signed(line.received - line.planned) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-if="step.kind === 'cutting' && detail.cloth?.length" class="pd-detail__section">
					<h4>Cloth delivered to cutting (Kg)</h4>
					<table class="erp-data-table pf-table">
						<thead><tr><th>Cloth</th><th>Colour · Dia</th><th class="erp-number">Planned</th><th class="erp-number">Delivered</th></tr></thead>
						<tbody>
							<tr v-for="(line, index) in detail.cloth" :key="index">
								<td>{{ line.item }}</td><td>{{ line.attributes }}</td>
								<td class="erp-number">{{ formatQuantity(line.planned, true) }}</td>
								<td class="erp-number" :class="toneClass(statusTone(line.delivered, line.planned))">{{ formatQuantity(line.delivered, true) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<ProcessWorkOrders :step="step" :work-orders="detail.work_orders?.length ? detail.work_orders : step.work_orders" />
			</template>
		</template>
	</Dialog>
</template>

<script setup>
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { getPpoProcessDetail } from "../../../api/planning.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import { diffTone, statusTone } from "../../../utils/lotProcessFlow.js"
import LotToneLegend from "../lot/flow/LotToneLegend.vue"
import ProcessMatrixTable from "./ProcessMatrixTable.vue"
import ProcessWorkOrders from "./ProcessWorkOrders.vue"
import { formatQuantity } from "./dashboardFormat.js"
import { colourWiseMatrix, sizeWiseMatrix } from "./detailMatrix.js"
import { PROCESS_STATUS_LABELS, processMeasure } from "./trackingRows.js"

/** Centred Size-wise or Colour-wise detail of one lot process; closes on outside click, Esc and ×. */
const props = defineProps({
	visible: Boolean,
	row: { type: Object, required: true },
	step: { type: Object, default: null },
	mode: { type: String, default: "size" },
})
const emit = defineEmits(["update:visible"])
const LEGEND_NOTES = {
	cutting: "Received vs planned; cloth delivered is in Kg below",
	cloth: "Received vs planned Kg",
	packing: "Received and Dispatch exist per size only",
	item: "Delivered vs planned · received vs delivered",
}
const detail = ref(null)
const loading = ref(false)
const error = ref("")
let sequence = 0

const measure = computed(() => processMeasure(props.row, props.step))
const isClothView = computed(() => props.step?.kind === "cloth")
const matrix = computed(() => (props.mode === "size" ? sizeWiseMatrix(detail.value) : colourWiseMatrix(detail.value)))
const withUnit = (value, unit) => `${formatQuantity(value, unit === "Kg")}${unit === "Kg" ? " kg" : ""}`
const toneClass = (tone) => (tone ? `pf-tone-${tone}` : "")
const signed = (value) => `${value > 0 ? "+" : ""}${formatQuantity(value, true)}`

async function load() {
	const request = ++sequence
	loading.value = true
	error.value = ""
	detail.value = null
	try {
		const result = await getPpoProcessDetail(props.row.lot, props.step.name)
		if (request === sequence) detail.value = result
	} catch (reason) {
		if (request === sequence) error.value = reason?.message || "Unable to load the process detail."
	} finally {
		if (request === sequence) loading.value = false
	}
}

watch(() => [props.visible, props.step?.name], ([visible]) => visible && props.step && load())
</script>
