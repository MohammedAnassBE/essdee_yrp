<template>
	<div class="purchase-invoice-editor__body">
		<div class="purchase-invoice-editor__main">
			<DocumentFieldGroupGrid
				:groups="mainGroups"
				aria-label="Purchase Invoice fields"
				root-class="purchase-invoice-editor__groups"
				content-class="purchase-invoice-editor__fields"
			>
				<template #default="{ group }">
					<FormField
						v-for="field in group.fields"
						:key="field.fieldname"
						:model-value="form[field.fieldname]"
						:field="field"
						:form="form"
						:required="Boolean(field.reqd)"
						:disabled="busy"
						@update:model-value="emit('update-field', field.fieldname, $event)"
					/>
				</template>
			</DocumentFieldGroupGrid>

			<div class="purchase-invoice-editor__grn-row">
				<PurchaseInvoiceGrnPicker
					:model-value="grns"
					:supplier="form.supplier"
					:against="form.against"
					:purchase-invoice="currentName"
					:bill-tracking="form.bill_tracking"
					:disabled="busy"
					@update:model-value="emit('update:grns', $event)"
				/>
				<Button
					label="Fetch GRN"
					icon="pi pi-download"
					:loading="fetching"
					:disabled="busy || !grns.length"
					@click="emit('fetch')"
				/>
			</div>

			<section class="purchase-invoice-editor__items" aria-labelledby="purchase-invoice-editor-items-title">
				<header>
					<div>
						<span>Commercial lines</span>
						<h2 id="purchase-invoice-editor-items-title">Grouped Items ({{ items.length }})</h2>
					</div>
					<small>Only Rate can be edited.</small>
				</header>
				<Message
					v-if="fetchWarnings.length"
					class="purchase-invoice-editor__warnings"
					severity="warn"
					:closable="false"
					role="status"
				>
					<strong>Some GRN rows were not billed</strong>
					<ul>
						<li v-for="warning in fetchWarnings" :key="`${warning.work_order}-${(warning.grns || []).join('-')}-${warning.reason}`">
							{{ warning.work_order }} · {{ (warning.grns || []).join(", ") }} — {{ warning.reason }}
						</li>
					</ul>
				</Message>
				<PurchaseInvoiceGroupedItems
					:rows="items"
					:editable="isRateEditable"
					:erp-sync-enabled="erpSyncEnabled"
					@update:rows="emit('update:items', $event)"
				/>
			</section>

			<DocumentFieldGroupGrid
				v-if="notesGroups.length"
				:groups="notesGroups"
				aria-label="Purchase Invoice remarks"
				root-class="purchase-invoice-editor__notes"
				content-class="purchase-invoice-editor__fields"
			>
				<template #default="{ group }">
					<FormField
						v-for="field in group.fields"
						:key="field.fieldname"
						:model-value="form[field.fieldname]"
						:field="field"
						:form="form"
						:required="Boolean(field.reqd)"
						:disabled="busy"
						@update:model-value="emit('update-field', field.fieldname, $event)"
					/>
				</template>
			</DocumentFieldGroupGrid>
		</div>

		<aside class="purchase-invoice-editor__rail" aria-label="Purchase Invoice totals">
			<div v-for="total in previewTotals" :key="total.key" class="purchase-invoice-editor__metric">
				<span>{{ total.label }}</span>
				<strong>{{ total.value }}</strong>
			</div>
		</aside>
	</div>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { computed } from "vue"

import FormField from "../../../components/common/FormField.vue"
import DocumentFieldGroupGrid from "../../../components/documents/DocumentFieldGroupGrid.vue"
import PurchaseInvoiceGrnPicker from "./PurchaseInvoiceGrnPicker.vue"
import PurchaseInvoiceGroupedItems from "./PurchaseInvoiceGroupedItems.vue"

const props = defineProps({
	groups: { type: Array, required: true },
	form: { type: Object, required: true },
	grns: { type: Array, required: true },
	items: { type: Array, required: true },
	fetchWarnings: { type: Array, default: () => [] },
	previewTotals: { type: Array, required: true },
	currentName: { type: String, default: "" },
	busy: { type: Boolean, default: false },
	fetching: { type: Boolean, default: false },
	isRateEditable: { type: Boolean, default: false },
	erpSyncEnabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update-field", "update:grns", "update:items", "fetch"])
const mainGroups = computed(() => props.groups.filter((group) => group.key !== "notes"))
const notesGroups = computed(() => props.groups.filter((group) => group.key === "notes"))
</script>

<style scoped>
.purchase-invoice-editor__body { display: grid; width: 100%; min-width: 0; grid-template-columns: minmax(0, 1fr) minmax(260px, 288px); align-items: start; gap: clamp(12px, 1.3vw, 20px); }
.purchase-invoice-editor__main { display: grid; min-width: 0; gap: var(--erp-space-3); }
.purchase-invoice-editor__notes :deep([data-group="notes"]) { grid-column: 1 / -1; }
.purchase-invoice-editor__fields { align-items: end; }
.purchase-invoice-editor__grn-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: var(--erp-space-3); }
.purchase-invoice-editor__grn-row > .p-button { min-width: 132px; margin-bottom: 12px; }
.purchase-invoice-editor__items { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.purchase-invoice-editor__items > header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.purchase-invoice-editor__items > header > div { display: grid; gap: 2px; }
.purchase-invoice-editor__items > header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.purchase-invoice-editor__items h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.purchase-invoice-editor__items > header small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.purchase-invoice-editor__warnings { margin: var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-warning) 30%, transparent); background: var(--erp-warning-soft); color: var(--erp-warning); }
.purchase-invoice-editor__warnings strong { display: block; margin-bottom: var(--erp-space-2); }
.purchase-invoice-editor__warnings ul { display: grid; gap: var(--erp-space-1); margin: 0; padding-left: 20px; }
.purchase-invoice-editor__items :deep(.purchase-invoice-items) { border: 0; border-radius: 0; box-shadow: none; }
.purchase-invoice-editor__rail { position: sticky; top: calc(var(--erp-shell-header-height) + 65px); overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.purchase-invoice-editor__metric { display: grid; min-height: 70px; align-content: center; gap: 4px; padding: 11px 13px; border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-editor__metric:last-child { border-bottom: 0; }
.purchase-invoice-editor__metric span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }
.purchase-invoice-editor__metric strong { color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 700; letter-spacing: -.01em; text-align: right; font-variant-numeric: tabular-nums; }
@media (max-width: 1000px) { .purchase-invoice-editor__body { grid-template-columns: 1fr; } .purchase-invoice-editor__rail { position: static; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); } .purchase-invoice-editor__metric { min-height: 62px; border-right: 1px solid var(--erp-border); border-bottom: 0; } .purchase-invoice-editor__metric:last-child { border-right: 0; } }
@media (max-width: 700px) { .purchase-invoice-editor__grn-row { grid-template-columns: 1fr; } .purchase-invoice-editor__grn-row > .p-button { width: 100%; margin-bottom: 0; } .purchase-invoice-editor__rail { grid-template-columns: repeat(2, minmax(0, 1fr)); } .purchase-invoice-editor__metric:nth-child(2) { border-right: 0; } .purchase-invoice-editor__metric:nth-child(-n + 2) { border-bottom: 1px solid var(--erp-border); } .purchase-invoice-editor__items > header small { display: none; } }
</style>
