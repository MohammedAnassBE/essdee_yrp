<template>
	<section class="rework-entry" :aria-label="title">
		<header class="rework-entry__header">
			<div><strong>{{ title }}</strong><span v-if="subtitle">{{ subtitle }}</span></div>
			<span class="rework-entry__type">{{ receivedType }}</span>
		</header>
		<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`${title} sizes`">
			<table class="finishing-table">
				<thead>
					<tr><th>Size</th><th v-for="item in items" :key="item.row_name" class="erp-number">{{ item[sizeField] }}</th><th class="erp-number">Total</th></tr>
				</thead>
				<tbody>
					<tr><td>Total {{ receivedType }}</td><td v-for="item in items" :key="item.row_name" class="erp-number"><strong>{{ formatQuantity(item.rework_qty) }}</strong></td><td class="erp-number finishing-table__row-total">{{ formatQuantity(totals.rework_qty) }}</td></tr>
					<tr v-if="editable">
						<td>Rejection</td>
						<td v-for="item in items" :key="item.row_name"><input v-model="item.rejected" type="number" min="0" :max="item.rework_qty" class="finishing-entry-input" :aria-label="`${title} ${item[sizeField]} rejection`" :disabled="busy" @input="emit('changed')" /></td>
						<td class="erp-number finishing-table__row-total">{{ formatQuantity(totals.rejected) }}</td>
					</tr>
					<tr v-if="editable">
						<td>Reworked</td>
						<td v-for="item in items" :key="item.row_name"><input v-model="item.rework" type="number" min="0" :max="item.rework_qty" class="finishing-entry-input" :aria-label="`${title} ${item[sizeField]} reworked`" :disabled="busy" @input="emit('changed')" /></td>
						<td class="erp-number finishing-table__row-total">{{ formatQuantity(totals.rework) }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-if="editable" class="rework-entry__actions" role="group" :aria-label="`${title} actions`">
			<Button label="Update Rejection Qty" severity="secondary" outlined size="small" :disabled="busy" @click="emit('update-rejection')" />
			<Button label="Complete Rework" icon="pi pi-check" severity="danger" outlined size="small" :disabled="busy" @click="emit('complete')" />
			<Button label="Update Reworked Piece" icon="pi pi-replay" size="small" :disabled="busy" @click="emit('update-reworked')" />
		</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"

import { computed } from "vue"

import { reworkTotals } from "../finishingEntryTotals.js"
import { formatQuantity } from "../finishingViews.js"

const props = defineProps({
	title: { type: String, required: true },
	subtitle: { type: String, default: "" },
	receivedType: { type: String, default: "" },
	sizeField: { type: String, required: true },
	items: { type: Array, required: true },
	editable: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["changed", "update-rejection", "update-reworked", "complete"])
const totals = computed(() => reworkTotals(props.items))
</script>

<style scoped>
.rework-entry { display: grid; gap: var(--erp-space-2); min-width: 0; padding: 10px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.rework-entry__header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; }
.rework-entry__header div { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
.rework-entry__header strong { color: var(--erp-text); font-size: var(--erp-font-size-table); }
.rework-entry__header span { color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
.rework-entry__type { padding: 2px 8px; color: var(--erp-attention-text, #92400e) !important; background: var(--erp-attention-soft, #fef3c7); border-radius: var(--erp-pill-radius); font-weight: 700; }
.rework-entry__actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: var(--erp-space-2); }
</style>
