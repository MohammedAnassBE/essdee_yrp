<template>
	<section v-if="entries.length" class="finishing-section source-entries" :aria-label="title">
		<header class="source-entries__header"><h3 class="finishing-section__title">{{ title }}</h3><span class="source-entries__count">{{ entries.length }}</span></header>
		<div class="finishing-scroll">
			<table class="finishing-table">
				<thead>
					<tr>
						<th>{{ documentLabel }}</th>
						<th>Date Time</th>
						<th class="erp-number">Qty</th>
						<th>Delivery Challan</th>
						<th v-if="canCancel" class="source-entries__action"><span class="sr-only">Actions</span></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="entry in entries" :key="entry.name">
						<td><button type="button" class="source-entries__open" :title="`Open ${entry.name}`" @click="emit('open', entry.doctype, entry.name)">{{ entry.name }}</button></td>
						<td class="source-entries__date">{{ entry.date || "—" }}</td>
						<td class="erp-number" :title="quantitySummary(entry)">{{ formatQuantity(entry.total_qty) }}</td>
						<td>
							<Button v-if="canCreateDc(entry, canCreate)" label="Create DC" icon="pi pi-truck" size="small" :disabled="busy" :aria-label="`Create DC for ${entry.name}`" @click="emit('create-dc', entry)" />
							<span v-else-if="isExistingDc(entry)" class="source-entries__existing">Before DC tracking</span>
							<button v-else-if="entry.dc" type="button" class="source-entries__open" :title="`Open ${entry.dc}`" @click="emit('open', 'YRP Delivery Challan', entry.dc)">{{ entry.dc }}</button>
							<span v-else>—</span>
						</td>
						<td v-if="canCancel" class="source-entries__action">
							<Button label="Cancel" icon="pi pi-ban" severity="danger" text size="small" :disabled="busy" :aria-label="`Cancel ${entry.name}`" @click="emit('cancel', entry.doctype, entry.name)" />
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"

import { formatQuantity } from "../finishingViews.js"
import { canCreateDc, isExistingDc } from "./finishingSourceEntries.js"

defineProps({
	title: { type: String, required: true },
	documentLabel: { type: String, required: true },
	entries: { type: Array, default: () => [] },
	canCreate: { type: Boolean, default: false },
	canCancel: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["open", "cancel", "create-dc"])

function quantitySummary(entry) {
	return Object.entries(entry.quantities || {})
		.map(([colour, sizes]) => `${colour}: ${Object.entries(sizes).map(([size, qty]) => `${size} ${formatQuantity(qty)}`).join(", ")}`)
		.join("\n")
}
</script>

<style scoped>
.source-entries__header { display: flex; align-items: center; gap: 8px; }
.source-entries__count { min-width: 22px; padding: 1px 7px; color: var(--erp-text-secondary); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 700; text-align: center; font-variant-numeric: tabular-nums; }
.source-entries__open { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.source-entries__open:hover, .source-entries__open:focus-visible { text-decoration: underline; }
.source-entries__date { color: var(--erp-text-secondary); font-variant-numeric: tabular-nums; }
.source-entries__existing { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.source-entries__action { width: 1%; text-align: right !important; padding-top: 2px !important; padding-bottom: 2px !important; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
