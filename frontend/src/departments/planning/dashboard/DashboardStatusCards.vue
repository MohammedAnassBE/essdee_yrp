<template>
	<section class="pd-panel pd-section" aria-label="Lots by status">
		<header class="pd-toolbar">
			<div>
				<h2>Lots by status</h2>
				<p>{{ formatQuantity(totals.open.length) }} open + {{ formatQuantity(totals.lots.length - totals.open.length) }} dispatched + {{ formatQuantity(totals.notStarted.length) }} with no Work Order = {{ formatQuantity(totals.rows.length) }} lots · pcs = Cut pcs, else Lot pcs · click a card to filter by it</p>
			</div>
		</header>
		<div v-if="cards.length" class="pd-status-cards">
			<button
				v-for="card in cards"
				:key="card.status"
				type="button"
				class="pd-status-card"
				:class="[card.isNoWorkOrder ? 'pd-status-card--muted' : `pd-status-card--${LADDER_TONE[card.status]}`, { 'is-active': active.includes(card.status) }]"
				:aria-pressed="active.includes(card.status)"
				:data-status-card="card.status"
				:title="active.includes(card.status) ? 'Remove this Status filter' : 'Filter the dashboard to this status'"
				@click="emit('toggle', card.status)"
			>
				<LotStatusPill :status="card.status" />
				<b>{{ formatQuantity(card.count) }}</b>
				<small>lots · {{ formatQuantity(card.pieces) }} pcs{{ card.isNoWorkOrder ? " planned" : "" }}</small>
			</button>
		</div>
		<p v-else class="pd-empty">No lots match these filters.</p>
	</section>
</template>

<script setup>
import { computed } from "vue"

import LotStatusPill from "./LotStatusPill.vue"
import { formatQuantity } from "./dashboardFormat.js"
import { LADDER_TONE, statusCards } from "./dashboardRows.js"

/** One card per lot status; a click sets (or clears) the Status filter. */
const props = defineProps({
	totals: { type: Object, required: true },
	active: { type: Array, default: () => [] },
})
const emit = defineEmits(["toggle"])
const cards = computed(() => statusCards(props.totals.rows))
</script>
