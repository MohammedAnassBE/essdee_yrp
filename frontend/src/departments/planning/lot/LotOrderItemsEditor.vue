<template>
	<div class="lot-tab-stack">
		<Message v-if="productionOrder && hasOrderDetails" severity="secondary" :closable="false">Box quantities are recalculated from Lot Order Details when you save.</Message>
		<template v-if="itemDetails">
			<LotOrderItemsTab :order-items="boxOrderView(itemDetails)" />
			<Button v-if="!composerOpen" label="Add row" icon="pi pi-plus" severity="secondary" outlined :disabled="disabled" @click="emit('update:composerOpen', true)" />
			<section v-else class="lot-group lot-order-composer" aria-label="Add box quantity row">
				<header class="lot-group__header"><strong>Add row</strong></header>
				<div class="lot-section__body">
					<div class="lot-composer-attributes">
						<div v-for="attribute in itemDetails.final_state_attr" :key="attribute"><label :for="`lot-row-${attribute}`">{{ attribute }}</label><LinkField doctype="Item Attribute Value" v-model="entry.attributes[attribute]" :input-id="`lot-row-${attribute}`" :aria-label="attribute" :search-handler="attributeSearch(attribute)" :show-open-button="false" :disabled="disabled" /></div>
					</div>
					<div v-if="itemDetails.primary_attribute" class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="New box quantities">
						<table class="erp-data-table lot-table"><thead><tr><th>Details</th><th v-for="size in itemDetails.primary_attribute_values" :key="size" class="erp-number">{{ size }} {{ itemDetails.default_uom }}</th></tr></thead>
							<tbody><tr v-for="stage in stages" :key="stage.key"><td class="lot-stage-label"><span>{{ stage.label }}</span></td><td v-for="size in itemDetails.primary_attribute_values" :key="size" class="erp-number"><InputNumber v-model="entry.values[size][stage.key]" :aria-label="`${stage.label} ${size} ${itemDetails.default_uom}`" :max-fraction-digits="3" :disabled="disabled" fluid /></td></tr></tbody>
						</table>
					</div>
					<div v-else class="lot-composer-values"><div v-for="stage in stages" :key="stage.key"><label :for="`lot-row-${stage.key}`">{{ stage.label }}{{ stage.key === 'qty' ? ` ${itemDetails.default_uom}` : '' }}</label><InputNumber v-model="entry.values[stage.key]" :input-id="`lot-row-${stage.key}`" :aria-label="stage.label" :max-fraction-digits="3" :disabled="disabled" fluid /></div></div>
					<Button label="Add row" icon="pi pi-plus" :disabled="disabled" @click="addRow" />
				</div>
			</section>
		</template>
		<LotEmptyState v-else title="No order items" reason="Choose an Item Production Detail with a final state to load box quantities." />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</div>
</template>
<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { ref, watch } from "vue"
import { callMethod } from "../../../api/frappe.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import LotEmptyState from "./LotEmptyState.vue"
import LotOrderItemsTab from "./LotOrderItemsTab.vue"
import { addLotOrderRow, boxOrderView, lotOrderEntry } from "./lotEditor.js"
const props = defineProps({ itemDetails: { type: Object, default: null }, composerOpen: Boolean, productionOrder: { type: String, default: "" }, hasOrderDetails: Boolean, disabled: Boolean })
const emit = defineEmits(["update:itemDetails", "update:composerOpen"])
const entry = ref(null)
const error = ref("")
const stages = [{ key: "qty", label: "Qty" }, { key: "ratio", label: "Ratio" }, { key: "mrp", label: "MRP" }]
watch(() => props.itemDetails, (details) => { entry.value = details ? lotOrderEntry(details) : null }, { immediate: true })
function attributeSearch(attribute) {
	return async (text) => (await callMethod("yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values", { txt: text, attribute, item: props.itemDetails.item })).map((value) => ({ name: value, label: value }))
}
function addRow() {
	try {
		emit("update:itemDetails", addLotOrderRow(props.itemDetails, entry.value))
		emit("update:composerOpen", false)
		error.value = ""
	} catch (reason) { error.value = reason.message }
}
</script>
