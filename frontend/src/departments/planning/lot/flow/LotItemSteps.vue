<template>
	<ol class="pf-flow">
		<li v-for="(step, index) in steps" :id="`pf-node-${index}`" :key="step.key" class="pf-node" :class="[`pf-node--${step.status}`, { 'is-flash': flash === step.key }]">
			<div class="pf-rail"><span class="pf-dot"><LotFlowStatus :status="step.status" /></span><span class="pf-line" /></div>
			<article class="pf-card">
				<header class="pf-card__head">
					<span class="pf-index">{{ index + 1 }}</span>
					<button type="button" class="pf-step-open" aria-haspopup="dialog" :title="`Show ${step.process} detail`" @click="emit('open-step', step)">
						{{ step.process }}<i class="pi pi-angle-right" aria-hidden="true" />
					</button>
					<span class="pf-stage">{{ step.stage }}</span>
					<LotFlowStatus :status="step.status" chip />
					<span class="pf-spacer" />
					<button type="button" class="pf-toggle" :aria-expanded="open.includes(step.key)" @click="toggle(step)">
						<i :class="open.includes(step.key) ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" aria-hidden="true" /><span>Size-wise detail</span>
					</button>
					<LotFlowReports :reports="reports" :context="stepReportContext(lot, item, step.process, step.work_orders, lotDate)" />
				</header>
				<div class="pf-card__body">
					<div>
						<ul v-if="step.work_orders.length" class="pf-wos">
							<li v-for="row in step.work_orders" :key="row.name" class="pf-wo">
								<button type="button" class="pf-wo__name" aria-haspopup="dialog" @click="emit('open-work-order', row)">{{ row.name }}</button>
								<DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" />
								<span class="pf-wo__supplier" :title="row.supplier_name">{{ row.supplier_name }}</span>
								<span class="pf-wo__dates">
									<template v-if="row.first_dc || row.last_grn"><span><em>First DC</em> {{ formatDisplayDate(row.first_dc) }}</span><span>·</span><span><em>Last GRN</em> {{ formatDisplayDate(row.last_grn) }}</span></template>
									<span v-else>No DC or GRN yet · WO {{ formatDisplayDate(row.wo_date) }}</span>
								</span>
							</li>
						</ul>
						<p v-else class="pf-note"><i class="pi pi-info-circle" aria-hidden="true" /> No Work Order raised yet</p>
						<p v-if="step.covers.length" class="pf-note"><i class="pi pi-sitemap" aria-hidden="true" /> Covers IPD processes: {{ step.covers.join(" · ") }}</p>
						<p v-if="step.also_covered_by.length" class="pf-note"><i class="pi pi-link" aria-hidden="true" /> Also covered by {{ step.also_covered_by.join(", ") }}</p>
					</div>
					<LotStepRing :meters="step.meters" :status="step.status" />
				</div>
				<div v-if="open.includes(step.key)" class="pf-detail">
					<p v-if="details[step.key]?.loading" class="pf-modal__none"><i class="pi pi-spin pi-spinner" aria-hidden="true" /> Loading…</p>
					<Message v-else-if="details[step.key]?.error" severity="error" :closable="false">{{ details[step.key].error }}</Message>
					<LotStepTables v-else-if="details[step.key]?.data" :kind="step.kind" v-bind="tableProps(details[step.key].data)" />
				</div>
			</article>
		</li>
	</ol>
</template>
<script setup>
import Message from "primevue/message"
import { reactive, ref } from "vue"
import { getLotStepDetail } from "../../../../api/planning.js"
import DocumentStatusBadge from "../../../../components/documents/DocumentStatusBadge.vue"
import { formatDisplayDate } from "../../../../utils/dateFormat.js"
import LotFlowReports from "./LotFlowReports.vue"
import LotFlowStatus from "./LotFlowStatus.vue"
import LotStepRing from "./LotStepRing.vue"
import LotStepTables from "./LotStepTables.vue"
import { stepReportContext } from "../../../../utils/lotProcessFlow.js"
/** Item process timeline: one card per step with Work Orders, a progress ring tile and a lazy size-wise detail. */
const props = defineProps({
	steps: { type: Array, required: true },
	lot: { type: String, required: true },
	item: { type: String, default: "" },
	lotDate: { type: String, default: "" },
	reports: { type: Array, default: () => [] },
	flash: { type: String, default: "" },
})
const emit = defineEmits(["open-step", "open-work-order"])
const open = ref([])
const details = reactive({})
function tableProps(data) {
	return { sizes: data.sizes, grid: data.grid, cloth: data.cloth, packing: data.packing, hasOrders: data.work_orders.some((row) => row.docstatus === 1) }
}
async function toggle(step) {
	if (open.value.includes(step.key)) {
		open.value = open.value.filter((key) => key !== step.key)
		return
	}
	open.value = [...open.value, step.key]
	if (details[step.key]?.data) return
	details[step.key] = { loading: true }
	try {
		details[step.key] = { data: await getLotStepDetail(props.lot, step.key) }
	} catch (reason) {
		details[step.key] = { error: reason?.message || "Unable to load the size-wise detail." }
	}
}
</script>
