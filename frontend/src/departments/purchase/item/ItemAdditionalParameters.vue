<template>
	<ItemTableCard :label="field.label || 'YRP Additional Parameters'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add parameter" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled" @click="addRow" /></template>
		<Message v-if="!editable && problems.length" severity="warn" :closable="false">{{ uniqueProblemMessages(problems).join(' ') }}</Message>
		<ChildGridTable :rows="values.additional_parameters || []" :columns="columns" :title="field.label || 'YRP Additional Parameters'" parent-doctype="Item" child-doctype="YRP Additional Parameter" :can-add="editable && !disabled" :add="addRow" :remove-row="editable && !disabled ? (index) => values.additional_parameters.splice(index, 1) : null">
			<template #cell-additional_parameter_key="{ data, index }">
				<LinkField v-if="editable" :model-value="data.additional_parameter_key" doctype="YRP Additional Parameter Key" :aria-label="columnLabel('additional_parameter_key', 'Additional Parameter Key')" :search-handler="(text) => searchItemEditorLinks('YRP Additional Parameter Key', text)" :show-open-button="false" :disabled="disabled" :invalid="problems.some((problem) => problem.row === index)" @update:model-value="changeKey(data, $event)" />
				<span v-else>{{ data.additional_parameter_key }}</span>
				<small v-for="problem in problems.filter((problem) => problem.row === index)" :key="problem.message" class="item-row-problem">{{ problem.message }}</small>
			</template>
			<template #cell-additional_parameter_value="{ data }">
				<LinkField v-if="editable" v-model="data.additional_parameter_value" doctype="YRP Additional Parameter Value" :aria-label="columnLabel('additional_parameter_value', 'Additional Parameter Value')" :filters="{ key: data.additional_parameter_key }" :search-handler="(text) => searchItemEditorLinks('YRP Additional Parameter Value', text, data.additional_parameter_key)" show-clear :show-open-button="false" :disabled="disabled || !data.additional_parameter_key" />
				<span v-else :aria-label="additionalParameterWording(data)">{{ data.additional_parameter_value || '(chosen per PO)' }}</span>
			</template>
			<template #empty>No additional parameters.</template>
		</ChildGridTable>
		<p class="item-table-hint">Leave the value empty to choose it on each PO line.</p>
	</ItemTableCard>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { searchItemEditorLinks } from "../../../api/purchase.js"
import { computed } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import ChildGridTable from "../../../components/common/childGrid/ChildGridTable.vue"
import ItemTableCard from "./ItemTableCard.vue"
import { additionalParameterWording, uniqueProblemMessages } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback
const columns = computed(() => [
	{ key: "additional_parameter_key", label: columnLabel("additional_parameter_key", "Additional Parameter Key"), fieldtype: "Link", reqd: 1, width: 240 },
	{ key: "additional_parameter_value", label: columnLabel("additional_parameter_value", "Additional Parameter Value"), fieldtype: "Link", width: 240 },
])
const addRow = () => props.values.additional_parameters.push({ additional_parameter_key: "", additional_parameter_value: "" })

function changeKey(row, key) {
	if (row.additional_parameter_key === key) return
	row.additional_parameter_key = key
	row.additional_parameter_value = ""
}
</script>
