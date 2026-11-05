<template>
	<span v-if="chip" class="pf-chip" :class="`pf-chip--${status}`"><LotFlowStatus :status="status" />{{ STATUS_LABELS[status] }}</span>
	<svg v-else viewBox="0 0 20 20" class="pf-icon" :class="`pf-icon--${status}`" aria-hidden="true">
		<template v-if="status === 'done'">
			<circle cx="10" cy="10" r="9" fill="currentColor" />
			<path d="M6 10.4l2.6 2.6L14 7.6" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
		</template>
		<template v-else>
			<circle class="pf-icon__ring" cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" />
			<path v-if="status === 'partial'" d="M10 4a6 6 0 0 1 0 12z" fill="currentColor" />
		</template>
	</svg>
</template>
<script setup>
import { STATUS_LABELS } from "./processFlow.js"
/** Step status icon (done / partial / idle), or a labelled chip. */
defineProps({ status: { type: String, default: "idle" }, chip: Boolean })
</script>
