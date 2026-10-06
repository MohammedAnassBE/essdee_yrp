<template>
	<div class="work-order-summary">
		<section class="work-order-summary__section erp-card">
			<header><h2>Work Order Summary</h2></header>
			<WorkOrderItemMatrix :groups="summary.item_detail || []" mode="summary" />
		</section>
		<section v-if="additionalDeliverables.length" class="work-order-summary__section erp-card">
			<header><h2>Additional Deliverables</h2></header>
			<WorkOrderItemMatrix :groups="additionalDeliverables" mode="additional" />
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"

import WorkOrderItemMatrix from "./WorkOrderItemMatrix.vue"

const props = defineProps({ summary: { type: Object, default: () => ({}) } })

const additionalDeliverables = computed(() => (props.summary.deliverables || []).map((group) => ({
	...group,
	items: (group.items || []).filter((item) => Object.values(item.values || {}).some((value) => Number(value?.pending_qty ?? value?.pending_quantity ?? 0) < 0)),
})).filter((group) => group.items.length))
</script>

<style scoped>
.work-order-summary { display: grid; gap: var(--erp-space-3); }
.work-order-summary__section { overflow: hidden; }
.work-order-summary__section > header { padding: 11px 13px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }
.work-order-summary__section h2 { margin: 0; font-size: 14px; }
.work-order-summary__section > :deep(.work-order-matrix-stack) { padding: var(--erp-space-3); }
</style>
