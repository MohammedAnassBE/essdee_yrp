<template>
	<Dialog
		:visible="visible"
		modal
		:dismissable-mask="!saving"
		:closable="!saving"
		header="Update Attribute Values"
		class="po-attribute-dialog erp-entity-dialog erp-dialog--lg"
		@update:visible="close"
	>
		<div class="po-attribute-dialog__content">
			<div v-if="loading" class="po-attribute-dialog__loading"><Skeleton v-for="index in 3" :key="index" height="3rem" /></div>
			<template v-else>
				<Message severity="secondary" :closable="false">Quantity, rate and amount stay as saved. Each changed row moves to the Item variant matching its new attribute values.</Message>
				<div v-if="rows.length" class="erp-table-wrap" role="region" tabindex="0" aria-label="Purchase Order item attribute values">
					<table class="erp-data-table">
						<thead><tr><th>#</th><th>Item</th><th>Attribute values</th><th class="erp-number">Qty</th><th>UOM</th><th class="erp-number">Rate</th><th class="erp-number">Amount</th></tr></thead>
						<tbody>
							<tr v-for="row in rows" :key="row.name">
								<td>{{ row.idx }}</td>
								<td><strong>{{ row.item_code }}</strong></td>
								<td>
									<div class="po-attribute-dialog__fields">
										<template v-for="entry in row.attributes" :key="entry.attribute">
											<LinkField
												v-if="entry.options.length"
												v-model="draft[row.name][entry.attribute]"
												:label="`${entry.attribute} *`"
												doctype="Item Attribute Value"
												:search-handler="(text) => searchAttributeOptions(entry.options, text)"
												:allow-create="false"
												:show-open-button="false"
												:disabled="saving || !entry.editable"
											/>
											<label v-else class="po-attribute-dialog__text"><span>{{ entry.attribute }} *</span><InputText v-model="draft[row.name][entry.attribute]" :aria-label="entry.attribute" :disabled="saving || !entry.editable" fluid /></label>
										</template>
									</div>
								</td>
								<td class="erp-number">{{ formatNumber(row.qty) }}</td>
								<td>{{ row.uom || "—" }}</td>
								<td class="erp-number">{{ formatNumber(row.rate) }}</td>
								<td class="erp-number">{{ formatNumber(row.amount) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<div v-else class="po-attribute-dialog__empty"><i class="pi pi-inbox" /><span>No item row on this Purchase Order has variant attributes.</span></div>
			</template>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="saving" @click="close(false)" />
			<Button label="Save Changes" icon="pi pi-save" :disabled="loading || !changes.length" :loading="saving" @click="save" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="error" title="Attribute values could not be updated" @dismiss="error = ''" />
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref, watch } from "vue"

import { getPurchaseOrderAttributeRows, updatePurchaseOrderAttributeValues } from "../../api/fabricStore.js"
import LinkField from "../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import { createAttributeDraft, getAttributeChanges, getEditableAttributeRows, getMissingAttributeMessage, searchAttributeOptions } from "./purchaseOrderAttributeValues.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	purchaseOrder: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "saved"])
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const rows = ref([])
const draft = ref({})
const changes = computed(() => getAttributeChanges(rows.value, draft.value))

async function load() {
	loading.value = true
	error.value = ""
	rows.value = []
	draft.value = {}
	try {
		const data = await getPurchaseOrderAttributeRows(props.purchaseOrder) || {}
		rows.value = getEditableAttributeRows(data.rows)
		draft.value = createAttributeDraft(rows.value)
	}
	catch (reason) { error.value = reason?.message || "Unable to load the item attribute values." }
	finally { loading.value = false }
}

async function save() {
	const missing = getMissingAttributeMessage(rows.value, draft.value)
	if (missing) { error.value = missing; return }
	saving.value = true
	try {
		const result = await updatePurchaseOrderAttributeValues(props.purchaseOrder, changes.value)
		emit("saved", result)
		emit("update:visible", false)
	}
	catch (reason) { error.value = reason?.message || "Unable to update the attribute values." }
	finally { saving.value = false }
}

function close(value) { if (!value && !saving.value) emit("update:visible", false) }
function formatNumber(value) { return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 }) }

watch(() => props.visible, (visible) => { if (visible && props.purchaseOrder) load() }, { immediate: true })
</script>

<style scoped>
.po-attribute-dialog__content { display: grid; gap: 12px; }
.po-attribute-dialog__loading { display: grid; gap: 8px; }
.po-attribute-dialog__fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; min-width: 220px; }
.po-attribute-dialog__text { display: grid; gap: 4px; font-size: var(--erp-font-size-sm, 13px); }
.po-attribute-dialog__empty { display: flex; align-items: center; gap: 8px; color: var(--erp-text-muted, #6b7280); }
</style>
