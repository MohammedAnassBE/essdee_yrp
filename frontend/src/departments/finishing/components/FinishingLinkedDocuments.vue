<template>
	<div v-if="visibleGroups.length" class="finishing-linked">
		<section v-for="group in visibleGroups" :key="group.key" class="finishing-linked__group" :aria-label="group.label">
			<header class="finishing-linked__header">
				<h3>{{ group.label }}</h3>
				<span class="finishing-linked__count">{{ group.documents.length }}</span>
			</header>
			<div class="finishing-scroll">
				<table class="finishing-table">
					<thead>
						<tr>
							<th>{{ documentLabel(group.doctype) }}</th>
							<th v-if="group.documents.some((document) => document.date)">Date Time</th>
							<th v-if="showCancel(group)" class="finishing-linked__action"><span class="sr-only">Actions</span></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="document in group.documents" :key="document.name">
							<td>
								<button type="button" class="finishing-linked__open" :title="`Open ${document.name}`" @click="emit('open', group.doctype, document.name)">{{ document.name }}</button>
							</td>
							<td v-if="group.documents.some((entry) => entry.date)" class="finishing-linked__date">{{ formatDisplayDatetime(document.date, { seconds: true }) }}</td>
							<td v-if="showCancel(group)" class="finishing-linked__action">
								<Button label="Cancel" icon="pi pi-ban" severity="danger" text size="small" :disabled="busy" :aria-label="`Cancel ${document.name}`" @click="emit('cancel', group.doctype, document.name)" />
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"

import { formatDisplayDatetime } from "../../../utils/dateFormat.js"

const props = defineProps({
	groups: { type: Array, default: () => [] },
	keys: { type: Array, required: true },
	canCancel: { type: Boolean, default: false },
	busy: { type: Boolean, default: false },
})
const emit = defineEmits(["open", "cancel"])
const visibleGroups = computed(() => props.keys
	.map((key) => props.groups.find((group) => group.key === key))
	.filter((group) => group?.documents?.length))
const documentLabels = {
	"YRP Delivery Challan": "Delivery Challan",
	"YRP Goods Received Note": "Goods Received Note",
	"YRP Stock Entry": "Stock Entry",
	"SD YRP Lot Transfer": "Lot Transfer",
}

function documentLabel(doctype) {
	return documentLabels[doctype] || doctype
}

function showCancel(group) {
	return props.canCancel && group.cancellable
}
</script>

<style scoped>
.finishing-linked { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr)); gap: 12px; min-width: 0; }
.finishing-linked__group { display: grid; align-content: start; gap: 6px; min-width: 0; }
.finishing-linked__header { display: flex; align-items: center; gap: 8px; }
.finishing-linked__header h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 700; }
.finishing-linked__count { min-width: 22px; padding: 1px 7px; color: var(--erp-text-secondary); background: var(--erp-surface-muted); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 700; text-align: center; font-variant-numeric: tabular-nums; }
.finishing-linked .finishing-scroll { max-height: 236px; }
.finishing-linked__open { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-weight: 650; cursor: pointer; }
.finishing-linked__open:hover, .finishing-linked__open:focus-visible { text-decoration: underline; }
.finishing-linked__date { color: var(--erp-text-secondary); font-variant-numeric: tabular-nums; }
.finishing-linked__action { width: 1%; text-align: right !important; padding-top: 2px !important; padding-bottom: 2px !important; }
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
</style>
