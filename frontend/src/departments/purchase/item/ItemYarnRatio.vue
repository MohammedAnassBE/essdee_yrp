<template>
	<ItemTableCard :label="field.label || 'Yarn Ratio'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add yarn" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled" @click="addRow" /></template>
		<Message v-for="problem in problems" :key="problem.message" severity="error" :closable="false">{{ problem.message }}</Message>
		<ChildGridTable :rows="values.yarn_ratio_details || []" :columns="columns" :title="field.label || 'Yarn Ratio'" parent-doctype="Item" child-doctype="SD YRP Item Yarn Ratio" :can-add="editable && !disabled" :add="addRow">
			<template #cell-yarn_item="{ data }">
				<LinkField v-if="editable" v-model="data.yarn_item" doctype="Item" :filters="yarnFilters" :aria-label="columnLabel('yarn_item', 'Yarn Item')" :show-open-button="false" :disabled="disabled" />
				<span v-else>{{ data.yarn_item }}</span>
			</template>
			<template #cell-ratio="{ data }">
				<InputNumber v-if="editable" v-model="data.ratio" :max-fraction-digits="3" suffix="%" :aria-label="`${data.yarn_item || 'Yarn'} ${columnLabel('ratio', 'Ratio')}`" :disabled="disabled" fluid />
				<span v-else>{{ data.ratio }}%</span>
			</template>
			<template v-if="editable" #row-actions="{ index }"><Button icon="pi pi-trash" severity="danger" text :disabled="disabled" :aria-label="`Remove yarn ${index + 1}`" @click="values.yarn_ratio_details.splice(index, 1)" /></template>
		</ChildGridTable>
		<strong>Total: {{ yarnRatioTotal(values.yarn_ratio_details) }}%</strong>
	</ItemTableCard>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { computed } from "vue"
import LinkField from "../../../components/common/LinkField.vue"
import ChildGridTable from "../../../components/common/childGrid/ChildGridTable.vue"
import ItemTableCard from "./ItemTableCard.vue"
import { yarnRatioTotal } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, itemName: { type: String, default: "" }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback
const columns = computed(() => [
	{ key: "yarn_item", label: columnLabel("yarn_item", "Yarn Item"), fieldtype: "Link", reqd: 1, width: 260 },
	{ key: "ratio", label: columnLabel("ratio", "Ratio"), fieldtype: "Percent", reqd: 1, width: 120 },
])
const yarnFilters = computed(() => ({ disabled: 0, is_cloth_item: 0, variant_of: ["is", "not set"], ...(props.itemName ? { name: ["!=", props.itemName] } : {}) }))
const addRow = () => props.values.yarn_ratio_details.push({ yarn_item: "", ratio: null })
</script>
