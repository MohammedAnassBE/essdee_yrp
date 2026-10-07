<template>
	<section class="delivery-challan-return-panel" aria-label="Delivery Challan return">
		<header class="delivery-challan-return-panel__header">
			<div><span>Return</span><h2>Select return quantities</h2></div>
			<strong>{{ formatQty(selectedQuantity) }} selected</strong>
		</header>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

		<div class="delivery-challan-return-panel__controls">
			<LinkField
				v-if="context.has_received_type"
				v-model="receivedType"
				label="Received Type *"
				doctype="YRP Received Type"
				:show-open-button="false"
				:disabled="Boolean(acting)"
			/>
			<label v-if="variants.whole_bundle" class="delivery-challan-return-panel__toggle">
				<span><strong>Return whole bundles</strong><small>Use a dedicated Cut Panel Movement for the returned bundles.</small></span>
				<ToggleSwitch v-model="returnWholeBundles" :disabled="Boolean(acting)" />
			</label>
			<LinkField
				v-if="returnWholeBundles"
				v-model="cutPanelMovement"
				label="Return Cut Panel Movement *"
				doctype="SD YRP Cut Panel Movement"
				:filters="variants.cut_panel_movement_filters || {}"
				:show-open-button="false"
				:disabled="Boolean(acting)"
			/>
		</div>

		<div v-if="rows.length" class="erp-table-wrap delivery-challan-return-panel__table">
			<table class="erp-data-table">
				<thead>
					<tr>
						<th>Item Variant</th><th>UOM</th><th class="erp-number">Delivered</th>
						<th class="erp-number">Consumed</th><th class="erp-number">Returned</th>
						<th class="erp-number">Returnable</th><th class="erp-number">Return Qty</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row.delivery_challan_item || `${row.item_variant}-${index}`">
						<td><strong>{{ row.item_variant || row.item || "—" }}</strong></td>
						<td>{{ row.uom || "—" }}</td>
						<td class="erp-number">{{ formatQty(row.delivered_quantity) }}</td>
						<td class="erp-number">{{ formatQty(row.consumed_quantity) }}</td>
						<td class="erp-number">{{ formatQty(row.already_returned) }}</td>
						<td class="erp-number delivery-challan-return-panel__available">{{ formatQty(row.returnable_quantity) }}</td>
						<td class="erp-number">
							<InputNumber
								v-model="row.return_quantity"
								:min="0"
								:max="Number(row.returnable_quantity || 0)"
								:max-fraction-digits="3"
								:disabled="Boolean(acting)"
								fluid
							/>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="delivery-challan-return-panel__empty"><i class="pi pi-inbox" /><span>No quantity is available to return.</span></div>

		<footer>
			<Button label="Close Return" severity="secondary" text :disabled="Boolean(acting)" @click="emit('close')" />
			<Button label="Create Return GRN" icon="pi pi-replay" :disabled="!canCreate" :loading="acting === 'return'" @click="createReturn" />
		</footer>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import ToggleSwitch from "primevue/toggleswitch"
import { computed, ref, watch } from "vue"

import LinkField from "../../components/common/LinkField.vue"

const props = defineProps({
	context: { type: Object, default: () => ({}) },
	acting: { type: String, default: "" },
	error: { type: String, default: "" },
})
const emit = defineEmits(["create", "close"])

const rows = ref([])
const receivedType = ref("")
const returnWholeBundles = ref(false)
const cutPanelMovement = ref("")
const variants = computed(() => props.context.variants || {})
const selectedQuantity = computed(() => rows.value.reduce((total, row) => total + Number(row.return_quantity || 0), 0))
const canCreate = computed(() => Boolean(
	selectedQuantity.value > 0
	&& (!props.context.has_received_type || receivedType.value)
	&& (!returnWholeBundles.value || cutPanelMovement.value)
	&& !props.acting,
))

watch(
	() => props.context,
	(context) => {
		rows.value = clone(context.items || [])
		receivedType.value = context.default_received_type || ""
		returnWholeBundles.value = false
		cutPanelMovement.value = ""
	},
	{ immediate: true },
)

function createReturn() {
	if (!canCreate.value) return
	emit("create", {
		items: rows.value.filter((row) => Number(row.return_quantity || 0) > 0),
		received_type: receivedType.value || undefined,
		return_whole_bundles: returnWholeBundles.value ? 1 : 0,
		cut_panel_movement: returnWholeBundles.value ? cutPanelMovement.value : undefined,
	})
}
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
</script>

<style scoped>
.delivery-challan-return-panel { display: grid; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.delivery-challan-return-panel__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); border-left: 3px solid color-mix(in srgb, var(--erp-accent) 68%, white); background: color-mix(in srgb, var(--erp-surface-soft) 78%, white); }
.delivery-challan-return-panel__header > div { display: grid; gap: 2px; }
.delivery-challan-return-panel__header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .05em; text-transform: uppercase; }
.delivery-challan-return-panel__header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.delivery-challan-return-panel__header > strong { padding: 4px 8px; color: var(--erp-accent); font-size: var(--erp-font-size-caption); background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); }
.delivery-challan-return-panel__controls { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: end; gap: var(--erp-space-3); padding: var(--erp-space-3); }
.delivery-challan-return-panel__toggle { display: flex; min-height: 56px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 10px; border-left: 3px solid var(--erp-border-strong); background: var(--erp-surface-soft); }
.delivery-challan-return-panel__toggle > span { display: grid; gap: 2px; }
.delivery-challan-return-panel__toggle strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.delivery-challan-return-panel__toggle small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); line-height: 1.25; }
.delivery-challan-return-panel__table { margin: 0 var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.delivery-challan-return-panel__table table { min-width: 850px; }
.delivery-challan-return-panel__table :deep(.p-inputnumber) { min-width: 96px; }
.delivery-challan-return-panel__table :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.delivery-challan-return-panel__available { color: var(--erp-accent); font-weight: 800; }
.delivery-challan-return-panel__empty { display: grid; min-height: 110px; place-items: center; align-content: center; gap: 6px; color: var(--erp-text-muted); }
.delivery-challan-return-panel footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: var(--erp-space-3); }
@media (max-width: 900px) { .delivery-challan-return-panel__controls { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .delivery-challan-return-panel footer { align-items: stretch; flex-direction: column; } }
</style>
