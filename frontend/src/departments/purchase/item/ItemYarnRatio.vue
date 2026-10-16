<template>
	<ItemTableCard :label="field.label || 'Yarn Ratio'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add yarn" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled" @click="values.yarn_ratio_details.push({ yarn_item: '', ratio: null })" /></template>
		<Message v-for="problem in problems" :key="problem.message" severity="error" :closable="false">{{ problem.message }}</Message>
		<DataTable :value="values.yarn_ratio_details || []" size="small" scrollable class="erp-data-table">
			<Column :header="columnLabel('yarn_item', 'Yarn Item')"><template #body="{ data }">
				<LinkField v-if="editable" v-model="data.yarn_item" doctype="Item" :filters="yarnFilters" :aria-label="columnLabel('yarn_item', 'Yarn Item')" :show-open-button="false" :disabled="disabled" />
				<span v-else>{{ data.yarn_item }}</span>
			</template></Column>
			<Column :header="columnLabel('ratio', 'Ratio')"><template #body="{ data }">
				<InputNumber v-if="editable" v-model="data.ratio" :max-fraction-digits="3" suffix="%" :aria-label="`${data.yarn_item || 'Yarn'} ${columnLabel('ratio', 'Ratio')}`" :disabled="disabled" fluid />
				<span v-else>{{ data.ratio }}%</span>
			</template></Column>
			<Column v-if="editable" header="Actions"><template #body="{ index }"><Button icon="pi pi-trash" severity="danger" text :disabled="disabled" :aria-label="`Remove yarn ${index + 1}`" @click="values.yarn_ratio_details.splice(index, 1)" /></template></Column>
		</DataTable>
		<strong>Total: {{ yarnRatioTotal(values.yarn_ratio_details) }}%</strong>
	</ItemTableCard>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { computed } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import ItemTableCard from "./ItemTableCard.vue"
import { yarnRatioTotal } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, itemName: { type: String, default: "" }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback
const yarnFilters = computed(() => ({ disabled: 0, is_cloth_item: 0, variant_of: ["is", "not set"], ...(props.itemName ? { name: ["!=", props.itemName] } : {}) }))
</script>
