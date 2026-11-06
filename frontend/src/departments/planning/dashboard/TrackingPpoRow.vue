<template>
	<tr class="pd-ppo-row" :data-ppo-row="ppo">
		<td colspan="4">
			<button type="button" class="pd-ppo-toggle" :aria-expanded="open" @click="emit('toggle')"><i class="pi pi-chevron-right" :class="{ 'is-open': open }" aria-hidden="true" /><b>{{ ppo }}</b></button>
			<span class="pd-ppo-meta">
				<span class="pd-ppo-item" :title="itemName">{{ itemName }}</span>
				<span> · {{ plural(rows.length, "lot") }}</span>
				<span v-if="hidden" :title="`${formatQuantity(hidden.pieces)} dispatched pcs are in ${plural(hidden.count, 'lot')} not shown`" :data-hidden-dispatch="hidden.pieces">
					· {{ hidden.count }} hidden · {{ formatQuantity(hidden.pieces) }} pcs<template v-if="hidden.canShow"> · <button type="button" class="pd-linkish" @click="emit('show-dispatched')">show</button></template>
				</span>
			</span>
		</td>
		<td class="pd-number" data-ppo-col="qty" :title="`${formatQuantity(figures.boxes, true)} boxes × ${figures.piecesPerBox ?? '?'} pcs per box`">{{ figures.pieces ? formatQuantity(figures.pieces) : "—" }}</td>
		<td class="pd-number" data-ppo-col="lot">{{ formatQuantity(figures.lotPieces) }}</td>
		<td class="pd-number" data-ppo-col="cut" :class="{ 'is-over': figures.isCutOver }">
			{{ formatQuantity(figures.cut) }}<span v-if="figures.isCutOver" class="pd-over" data-cut-over :title="`Cut over PPO: ${formatQuantity(figures.cut)} cut against ${formatQuantity(figures.pieces)} PPO pcs (+${formatQuantity(figures.cut - figures.pieces)})`">▲</span>
		</td>
		<td class="pd-number" data-ppo-col="dispatch">{{ formatQuantity(figures.dispatch) }}</td>
		<td class="pd-number" data-ppo-col="balance" :class="{ 'is-negative': figures.balance !== null && figures.balance < 0 }" title="PPO pcs − Dispatched">{{ figures.balance === null ? "—" : formatQuantity(figures.balance) }}</td>
		<td>
			<span v-if="figures.pieces" class="pd-ppo-progress">
				<span class="pd-ppo-bar" :title="`Dispatched ${formatQuantity(figures.dispatch)} of PPO ${formatQuantity(figures.pieces)} pcs`"><i :style="{ width: `${Math.min(figures.share, 1) * 100}%` }" /></span>
				<b data-ppo-col="progress">{{ (figures.share * 100).toFixed(0) }}%</b><span class="pd-muted">dispatched of PPO</span>
			</span>
		</td>
	</tr>
</template>

<script setup>
import { computed } from "vue"

import { formatQuantity, plural } from "./dashboardFormat.js"
import { hiddenDispatchNote, ppoFigures } from "./trackingRows.js"

/** PPO band: PPO, Lot, Cut and Dispatched over all its lots, Balance against PPO pcs, dispatched share. */
const props = defineProps({
	ppo: { type: String, required: true },
	info: { type: Object, required: true },
	rows: { type: Array, required: true },
	open: Boolean,
	showDispatched: Boolean,
})
const emit = defineEmits(["toggle", "show-dispatched"])
const figures = computed(() => ppoFigures(props.info))
const hidden = computed(() => hiddenDispatchNote(props.info, props.rows, props.showDispatched))
const itemName = computed(() => props.info.item_name || props.info.item || "")
</script>
