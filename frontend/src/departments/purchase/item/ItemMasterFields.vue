<template>
	<ItemTableCard v-if="part !== 'description'" :label="label('yrp_details_section', 'YRP Details')" :editable="editable">
		<div class="item-master-grid">
			<template v-if="editable">
				<LinkField v-model="values.secondary_unit_of_measure" :label="label('secondary_unit_of_measure')" doctype="UOM" show-clear :show-open-button="false" :disabled="disabled" />
				<label class="item-master-field"><span class="erp-field-label">{{ label('po_excess_allowed_percentage') }}</span><InputNumber v-model="values.po_excess_allowed_percentage" :max-fraction-digits="3" suffix="%" fluid :disabled="disabled" :invalid="Number(values.po_excess_allowed_percentage) < 0" /></label>
				<LinkField v-model="values.product_category" :label="label('product_category')" doctype="SD YRP Product Category" :search-handler="(text) => searchItemEditorLinks('SD YRP Product Category', text)" show-clear :show-open-button="false" :disabled="disabled" />
				<label class="item-master-field"><span class="erp-field-label">{{ label('hsn_code') }}</span><InputText v-model="values.hsn_code" fluid :disabled="disabled" /></label>
				<MultiSelectField v-model="values.categories" :label="label('categories')" :options="categoryOptions" :disabled="disabled" />
				<label class="item-master-check"><Checkbox :model-value="Boolean(Number(values.is_ineligible_for_itc))" binary :disabled="disabled" @update:model-value="values.is_ineligible_for_itc = $event ? 1 : 0" /><span>{{ label('is_ineligible_for_itc') }}</span></label>
				<label class="item-master-check"><Checkbox :model-value="Boolean(Number(values.is_cloth_item))" binary :disabled="disabled" @update:model-value="values.is_cloth_item = $event ? 1 : 0" /><span>{{ label('is_cloth_item') }}</span></label>
			</template>
			<dl v-else v-for="field in viewFields" :key="field.name" class="item-master-value"><dt>{{ label(field.name) }}</dt><dd>{{ displayValue(field) }}</dd></dl>
		</div>
		<Message v-for="problem in problems" :key="problem.message" severity="error" :closable="false">{{ problem.message }}</Message>
	</ItemTableCard>
	<ItemTableCard v-if="part !== 'details'" :label="label('description')" :editable="editable">
		<label v-if="editable" class="item-master-field"><span class="erp-field-label">{{ label('description') }}</span><Textarea v-model="values.description" rows="5" fluid :disabled="disabled" /></label>
		<template v-else>
			<div class="item-master-grid"><dl v-for="field in ['brand', 'gst_hsn_code']" :key="field" class="item-master-value"><dt>{{ label(field) }}</dt><dd>{{ values[field] || '—' }}</dd></dl></div>
			<dl class="item-master-value"><dt>{{ label('description', 'Description') }}</dt><dd class="item-description">{{ formatDocumentOverviewValue({ value: values.description }) }}</dd></dl>
		</template>
	</ItemTableCard>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Textarea from "primevue/textarea"
import { computed } from "vue"
import { searchItemEditorLinks } from "../../../api/purchase.js"
import LinkField from "../../../components/common/LinkField.vue"
import MultiSelectField from "../../../components/common/MultiSelectField.vue"
import { formatDocumentOverviewValue } from "../../../utils/documentOverview.js"
import ItemTableCard from "./ItemTableCard.vue"

const props = defineProps({ values: { type: Object, required: true }, fields: { type: Object, default: () => ({}) }, categories: { type: Array, default: () => [] }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] }, part: { type: String, default: "" } })
const viewFields = [
	{ name: "secondary_unit_of_measure" }, { name: "po_excess_allowed_percentage", fieldtype: "Percent" },
	{ name: "product_category" }, { name: "hsn_code" }, { name: "categories" },
	{ name: "is_ineligible_for_itc", fieldtype: "Check" }, { name: "is_cloth_item", fieldtype: "Check" },
]
const categoryOptions = computed(() => [...new Set([...props.categories, ...(props.values.categories || [])])].map((value) => ({ value, label: value })))
const label = (name, fallback) => props.fields[name]?.label || fallback || name.replaceAll("_", " ")
const displayValue = (field) => formatDocumentOverviewValue({ ...field, value: field.name === "categories" ? (props.values.categories || []).join(", ") : props.values[field.name] })
</script>

<style scoped>
.item-master-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px 28px; align-items: end; }
.item-master-field, .item-master-value { display: grid; min-width: 0; gap: 6px; margin: 0; }
.item-master-check { display: flex; align-items: center; gap: 8px; min-height: var(--erp-control-height); }
.item-master-value dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.item-master-value dd { margin: 0; overflow-wrap: anywhere; }
.item-description { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 900px) { .item-master-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .item-master-grid { grid-template-columns: minmax(0, 1fr); } }
</style>
