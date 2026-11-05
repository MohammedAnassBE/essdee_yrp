<template>
	<button type="button" class="pf-toggle" aria-haspopup="menu" :aria-expanded="open" @click="toggle">
		<i class="pi pi-chart-bar" aria-hidden="true" /><span>Reports</span>
	</button>
	<Popover ref="popover" class="pf-reports-popover" @show="open = true" @hide="open = false">
		<div class="pf-reports">
			<header class="pf-reports__head"><strong>Merch reports</strong><span>Opens in a new tab · {{ process }}</span></header>
			<ul v-if="reports.length" role="menu">
				<li v-for="report in reports" :key="report.key">
					<a role="menuitem" :href="reportHref(report, lot, process)" target="_blank" rel="noopener">
						<i :class="report.icon || 'pi pi-table'" aria-hidden="true" />
						<span><strong>{{ report.label }}</strong><small>{{ report.key === "inhouse_quantity" ? `Lot ${lot} · Process ${process}` : "Set filters in the report" }}</small></span>
						<i class="pi pi-external-link" aria-hidden="true" />
					</a>
				</li>
			</ul>
			<p v-else class="pf-modal__none pf-reports__empty">No Merch report is available to you.</p>
		</div>
	</Popover>
</template>
<script setup>
import Popover from "primevue/popover"
import { ref } from "vue"
import { reportHref } from "./processFlow.js"
/** Readable Merch reports; In-house Quantity opens with this Lot and Process filled in. */
defineProps({
	reports: { type: Array, default: () => [] },
	lot: { type: String, required: true },
	process: { type: String, default: "" },
})
const popover = ref(null)
const open = ref(false)
const toggle = (event) => popover.value?.toggle(event)
</script>
