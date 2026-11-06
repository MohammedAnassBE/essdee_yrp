<template>
	<Dialog :visible="visible" modal header="Production Orders" class="fabric-action-dialog erp-dialog--md" :closable="!busy" @update:visible="emit('update:visible', $event)">
		<div class="purchase-order-ppo-dialog">
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<table class="erp-data-table">
				<thead><tr><th>PPO</th><th>Item Name</th><th aria-label="Actions"></th></tr></thead>
				<tbody>
					<tr v-for="row in draft" :key="row.production_order">
						<td><DocumentLink doctype="YRP Production Order" :name="row.production_order" :label="row.production_order" /></td>
						<td>{{ row.item_name || "—" }}</td>
						<td class="purchase-order-ppo-dialog__actions"><Button v-if="canRemove || !savedNames.has(row.production_order)" icon="pi pi-times" severity="secondary" text rounded size="small" :disabled="busy" :aria-label="`Remove ${row.production_order}`" @click="draft = removeProductionOrderRow(draft, row.production_order)" /></td>
					</tr>
					<tr v-if="!draft.length"><td colspan="3" class="purchase-order-ppo-dialog__empty">No PPOs linked</td></tr>
				</tbody>
			</table>
			<LinkField v-model="candidate" :reset-version="candidateVersion" label="Add PPO" doctype="YRP Production Order" placeholder="Search PPO ID or item…" :search-handler="searchProductionOrders" :allow-create="false" :show-open-button="false" :disabled="busy" @select="addRow" />
		</div>
		<template #footer><Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" /><Button label="Save" icon="pi pi-save" :disabled="!changed" :loading="busy" @click="emit('save', productionOrderNames(draft))" /></template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { computed, ref, watch } from "vue"

import { callRead } from "../../api/frappe.js"
import DocumentLink from "../../components/common/DocumentLink.vue"
import LinkField from "../../components/common/LinkField.vue"
import { addProductionOrderRow, hasProductionOrderChanges, productionOrderNames, productionOrderRows, removeProductionOrderRow } from "./purchaseOrderProductionOrders.js"

/** Edit a Purchase Order's PPOs as a PPO + Item Name table; saved rows are removable only with canRemove. Save emits the PPO names. */
const props = defineProps({
	visible: { type: Boolean, default: false },
	rows: { type: Array, default: () => [] },
	busy: { type: Boolean, default: false },
	error: { type: String, default: "" },
	canRemove: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "save"])
const draft = ref([])
const candidate = ref("")
const candidateVersion = ref(0)
const savedNames = computed(() => new Set(productionOrderNames(productionOrderRows(props.rows))))
const changed = computed(() => hasProductionOrderChanges(productionOrderRows(props.rows), draft.value))

watch(() => props.visible, (visible) => { if (visible) draft.value = productionOrderRows(props.rows) }, { immediate: true })

function searchProductionOrders(text) {
	return callRead("essdee_yrp.purchase_order_against.search_production_orders", { txt: text })
}

function addRow(event) {
	draft.value = addProductionOrderRow(draft.value, event?.row || event)
	candidate.value = ""
	candidateVersion.value += 1
}
</script>

<style scoped>
.purchase-order-ppo-dialog { display: grid; gap: var(--erp-space-3); }
.purchase-order-ppo-dialog table { width: 100%; }
.purchase-order-ppo-dialog__actions { width: 1%; text-align: right; }
.purchase-order-ppo-dialog__empty { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>
