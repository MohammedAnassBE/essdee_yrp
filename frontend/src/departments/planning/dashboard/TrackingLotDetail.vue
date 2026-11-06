<template>
	<div class="pd-drill">
		<p class="pd-drill__note">{{ facts }}</p>
		<div class="pd-drill__panel">
			<table class="pd-process-table">
				<thead>
					<tr>
						<th>#</th>
						<th>Process</th>
						<th>First DC</th>
						<th class="pd-number">Planned pcs</th>
						<th class="pd-number">Delivered pcs</th>
						<th class="pd-number">Received pcs</th>
						<th class="pd-number" title="Received ÷ Planned">Received / Planned</th>
						<th v-if="hasPacking" class="pd-number">Dispatch pcs</th>
						<th title="From the state of the process's Work Orders, not from %">Status</th>
						<th />
					</tr>
				</thead>
				<tbody>
					<tr v-for="(step, index) in row.processes" :key="step.name" :data-process="step.name">
						<td class="pd-muted">{{ index + 1 }}</td>
						<td><b>{{ step.name }}</b></td>
						<td class="pd-muted">{{ step.first_dc ? formatDisplayDate(step.first_dc) : "No DC yet" }}</td>
						<td v-if="step.kind === 'cloth'" class="pd-number pd-muted" title="Cloth is in Kg; see Colour-wise">—</td>
						<td v-else-if="step.kind === 'packing'" class="pd-number" :data-planned="row.qty" title="Packing % uses lot order pcs">{{ formatQuantity(row.qty) }}<small class="pd-sub">lot order</small></td>
						<td v-else class="pd-number" :data-planned="step.planned">{{ formatQuantity(step.planned) }}</td>
						<td class="pd-number">
							<span v-if="step.kind === 'cloth' || step.kind === 'cutting'" class="pd-muted" title="Not in pcs; Kg is in the Size-wise and Colour-wise popups">—</span>
							<template v-else>{{ formatQuantity(step.delivered) }}</template>
						</td>
						<td class="pd-number" :data-received="step.kind === 'cloth' ? '' : step.received">
							<span v-if="step.kind === 'cloth'" class="pd-muted" title="Not in pcs; Kg is in the Colour-wise popup">—</span>
							<template v-else>{{ formatQuantity(step.received) }}</template>
						</td>
						<td class="pd-number" data-percent>{{ processMeasure(row, step).percent.toFixed(1) }}%<small v-if="step.kind === 'cloth'" class="pd-sub">by Kg</small></td>
						<td v-if="hasPacking" class="pd-number">{{ step.kind === "packing" ? formatQuantity(step.dispatch) : "" }}</td>
						<td :title="step.work_orders.map((order) => `${order.name}: ${order.status}`).join('\n')">
							<span class="pd-state" :class="`pd-state--${step.status}`">{{ PROCESS_STATUS_LABELS[step.status] }}</span>
							<small class="pd-sub">{{ step.reason }}</small>
						</td>
						<td class="pd-number">
							<button type="button" class="pd-details" aria-haspopup="menu" :data-menu="step.name" @click="openMenu($event, step)">Details ▾</button>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<Menu ref="menu" :model="menuItems" popup />
		<ProcessReportsPopover ref="reportsPopover" :reports="reports" />
		<ProcessDetailDialog v-model:visible="dialogVisible" :row="row" :step="dialogStep" :mode="dialogMode" />
	</div>
</template>

<script setup>
import Menu from "primevue/menu"
import { computed, ref } from "vue"

import { formatDisplayDate } from "../../../utils/dateFormat.js"
import ProcessDetailDialog from "./ProcessDetailDialog.vue"
import ProcessReportsPopover from "./ProcessReportsPopover.vue"
import { formatQuantity } from "./dashboardFormat.js"
import { PROCESS_STATUS_LABELS, processMeasure } from "./trackingRows.js"

/** A lot's processes in first-DC order with a Details menu: Size-wise, Colour-wise and Reports. */
const props = defineProps({
	row: { type: Object, required: true },
	reports: { type: Array, default: () => [] },
})
const menu = ref(null)
const reportsPopover = ref(null)
const activeStep = ref(null)
const anchor = ref(null)
const dialogVisible = ref(false)
const dialogStep = ref(null)
const dialogMode = ref("size")

const hasPacking = computed(() => props.row.processes.some((step) => step.kind === "packing"))
const facts = computed(() => [
	`Order ${formatQuantity(props.row.qty)} pcs`,
	props.row.cut_pcs ? `Cut ${formatQuantity(props.row.cut_pcs)} pcs` : "Not cut yet",
	`${props.row.processes.length} ${props.row.processes.length === 1 ? "process" : "processes"}, in order of first DC`,
].join(" · "))
const menuItems = computed(() => [
	{ label: "Size-wise", icon: "pi pi-th-large", disabled: activeStep.value?.kind === "cloth", command: () => openDialog("size") },
	{ label: "Colour-wise", icon: "pi pi-palette", command: () => openDialog("colour") },
	{ label: "Reports", icon: "pi pi-chart-bar", command: openReports },
])

function openMenu(event, step) {
	activeStep.value = step
	anchor.value = event.currentTarget
	menu.value?.toggle(event)
}

function openDialog(mode) {
	dialogStep.value = activeStep.value
	dialogMode.value = mode
	dialogVisible.value = true
}

function openReports() {
	reportsPopover.value?.show(anchor.value, { lot: props.row.lot, item: props.row.item, step: activeStep.value })
}
</script>
