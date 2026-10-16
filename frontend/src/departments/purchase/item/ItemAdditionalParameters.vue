<template>
	<ItemTableCard :label="field.label || 'YRP Additional Parameters'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add parameter" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled" @click="values.additional_parameters.push({ additional_parameter_key: '', additional_parameter_value: '' })" /></template>
		<Message v-if="!editable && problems.length" severity="warn" :closable="false">{{ uniqueProblemMessages(problems).join(' ') }}</Message>
		<DataTable :value="values.additional_parameters || []" size="small" scrollable class="erp-data-table">
			<Column :header="columnLabel('additional_parameter_key', 'Additional Parameter Key')"><template #body="{ data, index }">
				<LinkField v-if="editable" :model-value="data.additional_parameter_key" doctype="YRP Additional Parameter Key" :aria-label="columnLabel('additional_parameter_key', 'Additional Parameter Key')" :search-handler="(text) => searchItemEditorLinks('YRP Additional Parameter Key', text)" :show-open-button="false" :disabled="disabled" :invalid="problems.some((problem) => problem.row === index)" @update:model-value="changeKey(data, $event)" />
				<span v-else>{{ data.additional_parameter_key }}</span>
				<small v-for="problem in problems.filter((problem) => problem.row === index)" :key="problem.message" class="item-row-problem">{{ problem.message }}</small>
			</template></Column>
			<Column :header="columnLabel('additional_parameter_value', 'Additional Parameter Value')"><template #body="{ data }">
				<LinkField v-if="editable" v-model="data.additional_parameter_value" doctype="YRP Additional Parameter Value" :aria-label="columnLabel('additional_parameter_value', 'Additional Parameter Value')" :filters="{ key: data.additional_parameter_key }" :search-handler="(text) => searchItemEditorLinks('YRP Additional Parameter Value', text, data.additional_parameter_key)" show-clear :show-open-button="false" :disabled="disabled || !data.additional_parameter_key" />
				<span v-else :aria-label="additionalParameterWording(data)">{{ data.additional_parameter_value || '(chosen per PO)' }}</span>
			</template></Column>
			<Column v-if="editable" header="Actions"><template #body="{ index }"><Button icon="pi pi-trash" severity="danger" text :disabled="disabled" :aria-label="`Remove parameter ${index + 1}`" @click="values.additional_parameters.splice(index, 1)" /></template></Column>
			<template #empty>No additional parameters.</template>
		</DataTable>
		<p class="item-table-hint">Leave the value empty to choose it on each PO line.</p>
	</ItemTableCard>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import Message from "primevue/message"
import { searchItemEditorLinks } from "../../../api/purchase.js"
import LinkField from "../../../components/common/LinkField.vue"
import ItemTableCard from "./ItemTableCard.vue"
import { additionalParameterWording, uniqueProblemMessages } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback

function changeKey(row, key) {
	if (row.additional_parameter_key === key) return
	row.additional_parameter_key = key
	row.additional_parameter_value = ""
}
</script>
