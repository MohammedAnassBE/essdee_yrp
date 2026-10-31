<template>
	<LotMainTab :sections="sections" :expanded="expanded" :scroll-to="scrollTo" @update:expanded="emit('update:expanded', $event)">
		<template #header>
			<LotEditorDetails :form="form" :derived="derived" :fields="fields" :attempted-save="attemptedSave" :disabled="disabled" @set-field="(fieldname, value) => emit('set-field', fieldname, value)" />
		</template>
		<template #quantities><slot name="quantities" /></template>
		<template #order-details>
			<div class="lot-tab-stack">
				<LotFacts :facts="derivedFacts(derived, LOT_ORDER_DETAIL_FIELDS)" aria-label="Order detail facts" />
				<slot name="order-details" />
			</div>
		</template>
		<template #fabric-details>
			<ChildTableField parent-doctype="SD YRP Lot" :field="{ fieldname: 'lot_fabric_details', label: 'Fabric Details', options: 'SD YRP Lot Fabric Detail' }" :model-value="form.lot_fabric_details" :child-meta="fabricMeta" :column-filters="fabricColumnFilters" :disabled="disabled" :errors="fabricErrors" @update:model-value="emit('fabric-rows', $event)" />
		</template>
		<template #ipd><LotFacts :facts="derivedFacts(derived, ipdFields)" aria-label="Facts from Item Production Detail" /></template>
		<template #transfer><LotFacts :facts="derivedFacts(derived, LOT_TRANSFER_FIELDS)" aria-label="Transfer facts" /></template>
	</LotMainTab>
</template>
<script setup>
import { computed } from "vue"
import ChildTableField from "../../../components/common/ChildTableField.vue"
import LotEditorDetails from "./LotEditorDetails.vue"
import LotFacts from "./LotFacts.vue"
import LotMainTab from "./LotMainTab.vue"
import { fabricColumnFilters, lotFabricErrors } from "./lotEditor.js"
import { LOT_IPD_FIELDS, LOT_ORDER_DETAIL_FIELDS, LOT_TRANSFER_FIELDS, derivedFacts, hasLotTransfer, lotSections, orderDetailRowCount } from "./lotLayout.js"
/** Editable Lot tab shared by the Purchase, Planning and Merch editors. */
const props = defineProps({
	form: { type: Object, required: true },
	derived: { type: Object, required: true },
	fields: { type: Array, required: true },
	fabricMeta: { type: Object, required: true },
	orderItemDetails: { type: Array, default: () => [] },
	ipdFields: { type: Array, default: () => LOT_IPD_FIELDS },
	expanded: { type: Array, default: () => [] },
	scrollTo: { type: String, default: "" },
	attemptedSave: Boolean,
	disabled: Boolean,
})
const emit = defineEmits(["set-field", "fabric-rows", "update:expanded"])
const fabricErrors = computed(() => lotFabricErrors(props.form.lot_fabric_details, props.attemptedSave))
const sections = computed(() => lotSections({
	"order-details": props.orderItemDetails.length > 0,
	"fabric-details": true,
	ipd: true,
	transfer: hasLotTransfer(props.derived),
}, {
	"order-details": orderDetailRowCount(props.orderItemDetails),
	"fabric-details": props.form.lot_fabric_details.length,
}))
</script>
