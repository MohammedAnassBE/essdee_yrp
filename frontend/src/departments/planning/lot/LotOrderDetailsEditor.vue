<template>
	<div class="lot-tab-stack">
		<template v-if="isLocked"><Message severity="warn" :closable="false">Locked: Time &amp; Action exists or the Lot was transferred.</Message><LotOrderDetailsTab :order-details="readonlyDetails" /></template>
		<template v-else>
			<section v-for="(group, groupIndex) in groups" :key="groupIndex" class="lot-section">
				<header><div><span>Order details</span><h2>{{ group.attributes.join(' · ') }}</h2></div><span class="lot-count">{{ countLabel(group.items.length, 'row') }}</span></header>
				<div class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" :aria-label="`Lot order detail group ${groupIndex + 1}`">
					<table class="erp-data-table lot-table">
						<thead><tr><th>S.No</th><th v-for="attribute in group.attributes" :key="attribute">{{ attribute }}</th><th v-for="size in groupSizes(group)" :key="size" class="erp-number">{{ size }}</th><th class="erp-number">Total</th></tr></thead>
						<tbody v-for="(item, index) in group.items" :key="index"><tr><td>{{ index + 1 }}</td><td v-for="attribute in group.attributes" :key="attribute">{{ item.attributes[attribute] || '—' }}<small v-if="attribute === colourAttribute && setColourNote(item, version)">({{ setColourNote(item, version) }})</small></td><td v-for="size in groupSizes(group)" :key="size" class="erp-number"><InputNumber v-model="item.values[size].qty" :min="0" :max-fraction-digits="3" fluid :disabled="disabled" :aria-label="`Order quantity ${size}, row ${index + 1}`" /></td><td class="erp-number lot-total">{{ quantityTotal(orderQuantityTotal([item])) }}</td></tr></tbody>
						<tfoot><tr><th :colspan="group.attributes.length + 1">Total</th><td v-for="size in groupSizes(group)" :key="size" class="erp-number">{{ quantityTotal(orderQuantityTotal(group.items, size)) }}</td><td class="erp-number lot-total">{{ quantityTotal(orderQuantityTotal(group.items)) }}</td></tr></tfoot>
					</table>
				</div>
			</section>
		</template>
	</div>
</template>
<script setup>
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { computed } from "vue"
import LotOrderDetailsTab from "./LotOrderDetailsTab.vue"
import { orderDetailsView, orderQuantityTotal, setColourNote } from "./lotEditor.js"
import { countLabel, quantityTotal } from "./lotViews.js"
const props = defineProps({ groups: { type: Array, required: true }, colourAttribute: { type: String, required: true }, version: { type: String, default: "" }, isLocked: Boolean, disabled: Boolean })
function groupSizes(group) { return group.primary_attribute ? group.primary_attribute_values : ["default"] }
const readonlyDetails = computed(() => orderDetailsView(props.groups, props.version, props.colourAttribute))
</script>
