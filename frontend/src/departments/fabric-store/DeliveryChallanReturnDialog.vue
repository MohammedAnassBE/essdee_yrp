<template>
	<Dialog
		:visible="visible"
		modal
		dismissable-mask
		:header="`Return Items from ${deliveryChallan}`"
		class="dc-return-dialog erp-entity-dialog erp-dialog--lg"
		@update:visible="requestVisibility"
	>
		<div class="dc-return-content">
			<div v-if="loading" class="dc-return-loading"><Skeleton v-for="index in 4" :key="index" height="3rem" /></div>
			<template v-else>
				<div class="dc-return-context">
					<div><span>Delivery Challan</span><strong>{{ deliveryChallan }}</strong></div>
					<div><span>Selected quantity</span><strong>{{ formatQty(selectedQuantity) }}</strong></div>
				</div>
				<LinkField
					v-if="editor.has_received_type"
					v-model="receivedType"
					label="Received Type *"
					doctype="YRP Received Type"
					:show-open-button="false"
					show-clear
				/>
				<div class="erp-table-wrap dc-return-table" role="region" tabindex="0" aria-label="Returnable Delivery Challan quantities">
					<table class="erp-data-table">
						<thead><tr><th>Item Variant</th><th>UOM</th><th class="erp-number">DC Qty</th><th class="erp-number">Consumed</th><th class="erp-number">Returned</th><th class="erp-number">Returnable</th><th class="erp-number">Return Qty</th></tr></thead>
						<tbody>
							<tr v-for="row in rows" :key="row.delivery_challan_item">
								<td><strong>{{ row.item_variant }}</strong></td>
								<td>{{ row.uom || "—" }}</td>
								<td class="erp-number">{{ formatQty(row.delivered_quantity) }}</td>
								<td class="erp-number">{{ formatQty(row.consumed_quantity) }}</td>
								<td class="erp-number">{{ formatQty(row.already_returned) }}</td>
								<td class="erp-number dc-return-available">{{ formatQty(row.returnable_quantity) }}</td>
								<td class="erp-number"><InputNumber v-model="row.return_quantity" :aria-label="`Return quantity for ${row.item_variant || 'item'}`" :min="0" :max="Number(row.returnable_quantity || 0)" :max-fraction-digits="3" fluid /></td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-if="!rows.length" class="dc-return-empty"><i class="pi pi-inbox" /><span>No quantity is available to return.</span></div>
			</template>
		</div>
		<template #footer>
			<div class="dc-return-footer">
				<Button label="Close" severity="secondary" text :disabled="saving" @click="requestVisibility(false)" />
				<Button v-if="editor.permissions?.can_create" label="Create Return GRN" icon="pi pi-replay" :disabled="!canCreate" :loading="saving" @click="createReturn" />
			</div>
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Delivery Challan return could not be completed" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { createDeliveryChallanReturn, getDeliveryChallanReturnEditor } from "../../api/fabricStore.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	deliveryChallan: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "created"])

const loading = ref(false)
const saving = ref(false)
const error = ref("")
const editor = ref({ permissions: {} })
const rows = ref([])
const receivedType = ref("")
const selectedQuantity = computed(() => rows.value.reduce((sum, row) => sum + Number(row.return_quantity || 0), 0))
const canCreate = computed(() => selectedQuantity.value > 0 && (!editor.value.has_received_type || receivedType.value))

watch(() => [props.visible, props.deliveryChallan], ([visible]) => { if (visible && props.deliveryChallan) load() }, { immediate: true })

async function load() {
	loading.value = true
	error.value = ""
	try {
		editor.value = await getDeliveryChallanReturnEditor(props.deliveryChallan) || { permissions: {} }
		rows.value = clone(editor.value.items || [])
		receivedType.value = editor.value.default_received_type || ""
	} catch (reason) {
		error.value = reason?.message || "Unable to load returnable items."
	} finally {
		loading.value = false
	}
}

async function createReturn() {
	if (!canCreate.value) return
	saving.value = true
	error.value = ""
	try {
		const selected = rows.value.filter((row) => Number(row.return_quantity || 0) > 0)
		const created = await createDeliveryChallanReturn(props.deliveryChallan, selected, receivedType.value)
		emit("created", created)
		emit("update:visible", false)
	} catch (reason) {
		error.value = reason?.message || "Unable to create the Return GRN."
	} finally {
		saving.value = false
	}
}

function requestVisibility(value) { if (!value && !saving.value) emit("update:visible", false) }
function formatQty(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }
function clone(value) { return JSON.parse(JSON.stringify(value || [])) }
</script>

<style scoped>
.dc-return-content, .dc-return-loading { display: grid; gap: var(--erp-space-3); }
.dc-return-content { min-height: 180px; overflow-y: visible; padding: 2px 1px; }
.dc-return-context { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); overflow: hidden; background: color-mix(in srgb, var(--erp-surface-soft) 76%, white); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.dc-return-context > div { display: grid; gap: 3px; padding: 9px 12px; border-right: 1px solid var(--erp-border); }
.dc-return-context > div:last-child { border-right: 0; }
.dc-return-context span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.dc-return-context strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.dc-return-table { border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 5px 16px rgb(28 61 45 / 4%); }
.dc-return-table table { min-width: 860px; }
.dc-return-table :deep(.p-inputnumber) { min-width: 96px; }
.dc-return-table :deep(.p-inputnumber-input) { height: 32px; padding: 5px 8px; text-align: right; }
.dc-return-available { color: var(--erp-accent-dark); font-weight: 800; }
.dc-return-empty { display: grid; min-height: 140px; place-items: center; align-content: center; gap: 7px; color: var(--erp-text-muted); }
.dc-return-footer { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: var(--erp-space-3); }
@media (max-width: 560px) { .dc-return-context { grid-template-columns: 1fr; } .dc-return-footer { align-items: stretch; flex-direction: column; } }
@media (max-width: 1024px), (pointer: coarse) { .dc-return-table :deep(.p-inputnumber-input) { height: 44px; min-height: 44px; } }
</style>
