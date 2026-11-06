<template>
	<section class="pd-panel pd-section" aria-label="Lots">
		<header class="pd-toolbar">
			<div>
				<h2>Lots</h2>
				<p data-summary>{{ plural(lots.length, "lot") }} shown<template v-if="hiddenCount"> · {{ hiddenCount }} dispatched hidden</template></p>
			</div>
			<div class="pd-toolbar__end">
				<span class="pd-key" aria-label="Progress key"><span v-for="(label, status) in PROCESS_STATUS_LABELS" :key="status"><i :class="`pd-seg--${status}`" />{{ label }}</span></span>
				<label class="pd-switch">
					<ToggleSwitch :model-value="showDispatched" input-id="pd-show-dispatched" @update:model-value="emit('update:showDispatched', $event)" />
					<span>Show dispatched</span><em data-dispatched-count>{{ hiddenCount }}</em>
				</label>
				<Button label="Copy CSV" size="small" severity="secondary" outlined :disabled="!lots.length" @click="copy" />
			</div>
		</header>
		<div class="pd-table-wrap">
			<table class="pd-table pd-lots-table">
				<colgroup><col style="width:2.4%"><col style="width:11%"><col style="width:13.6%"><col style="width:14.5%"><col style="width:7.3%"><col style="width:7.3%"><col style="width:7.3%"><col style="width:8%"><col style="width:7.6%"><col style="width:21%"></colgroup>
				<thead>
					<tr class="pd-head-group">
						<th rowspan="2" aria-label="Expand" />
						<th rowspan="2">Lot</th>
						<th rowspan="2">Status</th>
						<th rowspan="2">Delivery</th>
						<th colspan="5" class="pd-super">Quantities (pcs)</th>
						<th rowspan="2" title="Lot: one segment per process, in First DC order. PPO: dispatched ÷ PPO pcs">Progress</th>
					</tr>
					<tr>
						<th class="pd-number" title="PPO quantity: boxes × pieces per box">PPO</th>
						<th class="pd-number" title="Lot order pcs. PPO row: sum over its lots with Work Orders">Lot</th>
						<th class="pd-number" title="Pieces received from Cutting Work Orders">Cut</th>
						<th class="pd-number" title="Pieces dispatched. PPO row: all its lots, including hidden dispatched lots">Dispatched</th>
						<th class="pd-number" title="Lot: Cut − Dispatched (Lot before cutting). PPO: PPO − Dispatched">Balance</th>
					</tr>
				</thead>
				<tbody>
					<template v-for="[ppo, rows] in groups" :key="ppo">
						<TrackingPpoRow :ppo="ppo" :info="ppos[ppo] || {}" :rows="rows" :open="!collapsed.has(ppo)" :show-dispatched="showDispatched" @toggle="toggle(collapsed, ppo)" @show-dispatched="emit('update:showDispatched', true)" />
						<template v-if="!collapsed.has(ppo)">
							<template v-for="row in rows" :key="row.lot">
								<TrackingLotRow :row="row" :ppo-items="ppoItems(ppo)" :as-of="asOf" :open="expanded.has(row.lot)" @toggle="toggle(expanded, row.lot)" />
								<tr v-if="expanded.has(row.lot)" class="pd-drill-row"><td colspan="10" class="pd-drill-cell"><TrackingLotDetail :row="row" :reports="reports" /></td></tr>
							</template>
						</template>
					</template>
					<tr v-if="!lots.length"><td colspan="10" class="pd-empty">{{ emptyText }}</td></tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import ToggleSwitch from "primevue/toggleswitch"
import { useToast } from "primevue/usetoast"
import { computed, reactive } from "vue"

import TrackingLotDetail from "./TrackingLotDetail.vue"
import TrackingLotRow from "./TrackingLotRow.vue"
import TrackingPpoRow from "./TrackingPpoRow.vue"
import { copyCsv } from "./copyCsv.js"
import { plural } from "./dashboardFormat.js"
import { PROCESS_STATUS_LABELS, groupLotsByPpo, trackingCsv } from "./trackingRows.js"

/** PPO Tracking lots grouped under collapsible PPO rows; a lot row expands into its processes. */
const props = defineProps({
	lots: { type: Array, required: true },
	hiddenCount: { type: Number, default: 0 },
	ppos: { type: Object, required: true },
	asOf: { type: String, default: "" },
	showDispatched: Boolean,
	reports: { type: Array, default: () => [] },
})
const emit = defineEmits(["update:showDispatched"])
const toast = useToast()
const collapsed = reactive(new Set())
const expanded = reactive(new Set())
const groups = computed(() => groupLotsByPpo(props.lots))
const emptyText = computed(() => (props.hiddenCount
	? `No lots to show. ${plural(props.hiddenCount, "dispatched lot")} hidden; turn on Show dispatched.`
	: "No lots match these filters."))

const ppoItems = (ppo) => [props.ppos[ppo]?.item, props.ppos[ppo]?.item_name].flatMap((value) => String(value || "").split(", ")).filter(Boolean)
const toggle = (set, key) => (set.has(key) ? set.delete(key) : set.add(key))

function copy() {
	copyCsv(toast, trackingCsv(props.lots, props.ppos), props.lots.length, "lot")
}
</script>
