<template>
	<div class="pf-lanes">
		<section v-for="lane in lanes" :key="lane.cloth_item" class="pf-lane" :aria-label="lane.cloth_item">
			<div class="pf-lane__fabric">
				<h4><a :href="documentHref('Item', lane.cloth_item)" target="_blank" rel="noopener">{{ lane.cloth_item }}</a></h4>
				<p>
					<a v-if="lane.fabric_ipd" :href="documentHref('YRP Item Production Detail', lane.fabric_ipd)" target="_blank" rel="noopener">{{ lane.fabric_ipd }}</a>
					<span v-else>No fabric IPD</span>
					· {{ formatNumber(summary(lane).programKg) }} Kg<template v-if="summary(lane).uses"> · {{ summary(lane).uses }}</template>
				</p>
				<div class="pf-lane__colours">
					<span v-for="colour in summary(lane).colours" :key="colour" class="pf-swatch"><i :style="{ background: colourSwatch(colour) }" />{{ colour }}</span>
				</div>
			</div>
			<div v-if="lane.steps.length" class="pf-lane__steps">
				<template v-for="(step, index) in lane.steps" :key="step.process">
					<i v-if="index" class="pi pi-arrow-right pf-lane__arrow" aria-hidden="true" />
					<component
						:is="step.work_orders.length ? 'button' : 'div'"
						:type="step.work_orders.length ? 'button' : undefined"
						class="pf-lane-step"
						:class="[`pf-lane-step--${step.status}`, { 'is-clickable': step.work_orders.length }]"
						:aria-haspopup="step.work_orders.length ? 'dialog' : undefined"
						:title="step.work_orders.length ? `Show ${step.process} detail` : undefined"
						@click="step.work_orders.length && emit('open-work-order', step.work_orders[0])"
					>
						<span class="pf-lane-step__head"><LotFlowStatus :status="step.status" /><strong>{{ step.process }}</strong><span>{{ STATUS_LABELS[step.status] }}</span></span>
						<span v-for="row in step.work_orders" :key="row.name" class="pf-lane-step__wo">
							<span class="pf-wo__name" role="link" tabindex="-1" @click.stop="emit('open-work-order', row)">{{ row.name }}</span>
							<DocumentStatusBadge :docstatus="row.docstatus" :label="row.status" />
							<span class="pf-lane-step__supplier">{{ row.supplier_name }}</span>
						</span>
						<span v-if="!step.work_orders.length" class="pf-lane-step__none">No Work Order</span>
						<span class="pf-lane-step__qty"><span>Rcv <b>{{ formatNumber(step.received) }}</b> / {{ formatNumber(summary(lane).programKg) }} Kg</span><span>{{ Math.round(percent(step.received, summary(lane).programKg)) }}%</span></span>
						<span class="pf-track"><span class="pf-fill" :class="`pf-fill--${step.status}`" :style="{ width: `${Math.min(percent(step.received, summary(lane).programKg), 100)}%` }" /></span>
						<span v-if="step.work_orders.length" class="pf-lane-step__more">View detail <i class="pi pi-angle-right" aria-hidden="true" /></span>
					</component>
				</template>
			</div>
			<p v-else class="pf-empty-note">No fabric processes in the fabric IPD.</p>
		</section>
	</div>
</template>
<script setup>
import DocumentStatusBadge from "../../../../components/documents/DocumentStatusBadge.vue"
import LotFlowStatus from "./LotFlowStatus.vue"
import { STATUS_LABELS, colourSwatch, documentHref, fabricSummary, formatNumber, percent } from "../../../../utils/lotProcessFlow.js"
/** One row per cloth item: Cloth Program facts and a tile per fabric IPD process. */
const props = defineProps({
	lanes: { type: Array, required: true },
	fabrics: { type: Array, default: () => [] },
})
const emit = defineEmits(["open-work-order"])
const summary = (lane) => fabricSummary(props.fabrics.find((fabric) => fabric.cloth_item === lane.cloth_item))
</script>
