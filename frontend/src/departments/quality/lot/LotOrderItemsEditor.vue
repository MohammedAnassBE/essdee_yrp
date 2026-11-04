<template>
	<div class="lot-tab-stack">
		<Message v-if="isLocked" severity="warn" :closable="false">Locked: Time &amp; Action exists or the Lot was transferred.</Message>
		<Message v-else-if="productionOrder && hasOrderDetails" severity="secondary" :closable="false">Box quantities are recalculated from Lot Order Details when you save.</Message>
		<template v-if="itemDetails">
			<section class="lot-section">
				<header><div><span>Order quantities</span><h2>Box quantities ({{ itemDetails.default_uom || "—" }})</h2></div><span class="lot-count">{{ countLabel(itemDetails.items.length, "row") }}</span></header>
				<div v-if="itemDetails.items.length" class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="Lot order quantities">
					<table v-entry-table class="erp-data-table lot-table lot-order-quantities">
						<thead><tr><th>S.No</th><th v-for="attribute in attributes" :key="attribute">{{ attribute }}</th><th>Details</th><th v-for="size in sizes" :key="String(size)" class="erp-number">{{ size === null ? "Value" : `${size} ${itemDetails.default_uom || ""}` }}</th><th class="erp-number">Total</th></tr></thead>
						<tbody v-for="(item, index) in itemDetails.items" :key="index">
							<tr v-for="(stage, stageIndex) in ORDER_STAGES" :key="stage.key">
								<td class="lot-order-quantities__lead">{{ stageIndex ? "" : index + 1 }}</td>
								<td v-for="attribute in attributes" :key="attribute" class="lot-order-quantities__lead">{{ stageIndex ? "" : item.attributes?.[attribute] || "—" }}</td>
								<td class="lot-stage-label"><span>{{ stage.label }}</span></td>
								<td v-for="size in sizes" :key="String(size)" class="erp-number">
									<template v-if="locked">{{ formatQuantity(orderCell(item, size)?.[stage.key]) }}</template>
									<InputNumber v-else :model-value="orderCell(item, size)?.[stage.key] ?? 0" :min="0" :max-fraction-digits="3" fluid :disabled="disabled" :aria-label="`${stage.label} ${size ?? ''} row ${index + 1}`" @update:model-value="setOrderCell(item, size, stage.key, $event)" />
								</td>
								<td class="erp-number lot-total">{{ stage.key === "qty" ? quantityTotal(orderRowTotal(item, sizes)) : "" }}</td>
							</tr>
						</tbody>
					</table>
				</div>
				<LotEmptyState v-else title="No order quantities" reason="Add a row to enter box quantities." />
			</section>
			<template v-if="!locked && attributes.length">
				<Button v-if="!composerOpen" label="Add row" icon="pi pi-plus" severity="secondary" outlined :disabled="disabled" @click="emit('update:composerOpen', true)" />
			<section v-else class="lot-group lot-order-composer" aria-label="Add box quantity row" @keydown.enter="addOnLastEnter">
				<header class="lot-group__header"><strong>Add row</strong></header>
				<div class="lot-section__body">
					<div class="lot-composer-attributes">
						<div v-for="attribute in itemDetails.final_state_attr" :key="attribute"><label :for="`lot-row-${attribute}`">{{ attribute }}</label><LinkField doctype="Item Attribute Value" v-model="entry.attributes[attribute]" :input-id="`lot-row-${attribute}`" :aria-label="attribute" :search-handler="attributeSearch(attribute)" :show-open-button="false" :disabled="disabled" /></div>
					</div>
					<div v-if="itemDetails.primary_attribute" class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" aria-label="New box quantities">
						<table v-entry-table class="erp-data-table lot-table"><thead><tr><th>Details</th><th v-for="size in itemDetails.primary_attribute_values" :key="size" class="erp-number">{{ size }} {{ itemDetails.default_uom }}</th></tr></thead>
							<tbody><tr v-for="stage in stages" :key="stage.key"><td class="lot-stage-label"><span>{{ stage.label }}</span></td><td v-for="size in itemDetails.primary_attribute_values" :key="size" class="erp-number"><InputNumber v-model="entry.values[size][stage.key]" :aria-label="`${stage.label} ${size} ${itemDetails.default_uom}`" :max-fraction-digits="3" :disabled="disabled" fluid /></td></tr></tbody>
						</table>
					</div>
					<div v-else class="lot-composer-values"><div v-for="stage in stages" :key="stage.key"><label :for="`lot-row-${stage.key}`">{{ stage.label }}{{ stage.key === 'qty' ? ` ${itemDetails.default_uom}` : '' }}</label><InputNumber v-model="entry.values[stage.key]" :input-id="`lot-row-${stage.key}`" :aria-label="stage.label" :max-fraction-digits="3" :disabled="disabled" fluid /></div></div>
					<Button label="Add row" icon="pi pi-plus" :disabled="disabled" @click="addRow" />
				</div>
			</section>
			</template>
			<Button v-else-if="!locked && !itemDetails.items.length" label="Add row" icon="pi pi-plus" severity="secondary" outlined :disabled="disabled" @click="emit('update:itemDetails', { ...itemDetails, items: [blankOrderRow(itemDetails)] })" />
		</template>
		<LotEmptyState v-else title="No order quantities" reason="Choose an Item Production Detail with a final state to load box quantities." />
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</div>
</template>
<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { computed, ref, watch } from "vue"
import { callMethod } from "../../../api/frappe.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { vEntryTable } from "../../../components/common/childGrid/entryTable.js"
import LotEmptyState from "./LotEmptyState.vue"
import { ORDER_STAGES, addLotOrderRow, blankOrderRow, isBoxLocked, lotOrderEntry, orderCell, orderRowTotal, orderSizes, setOrderCell } from "./lotEditor.js"
import { countLabel, formatQuantity, quantityTotal } from "./lotViews.js"
/** The one editable Order Quantities grid (Qty/Ratio/MRP rows × sizes), bound to the Lot's box quantities. */
const props = defineProps({ itemDetails: { type: Object, default: null }, composerOpen: Boolean, productionOrder: { type: String, default: "" }, hasOrderDetails: Boolean, isLocked: Boolean, boxLocked: Boolean, disabled: Boolean })
const emit = defineEmits(["update:itemDetails", "update:composerOpen"])
const entry = ref(null)
const error = ref("")
const stages = ORDER_STAGES
const attributes = computed(() => props.itemDetails?.final_state_attr || [])
const sizes = computed(() => (props.itemDetails ? orderSizes(props.itemDetails) : []))
const locked = computed(() => props.boxLocked || isBoxLocked({ order_details: props.isLocked }, props.productionOrder, props.hasOrderDetails))
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
/** Enter on the composer's last input adds the row, like clicking Add row. */
function addOnLastEnter(event) {
	if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
	const inputs = event.currentTarget.querySelectorAll("input:not([type=hidden]):not(:disabled)")
	if (event.target !== inputs[inputs.length - 1]) return
	event.preventDefault()
	addRow()
}
</script>
