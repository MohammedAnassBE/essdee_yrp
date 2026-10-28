<template>
	<ItemTableCard :label="field.label || 'UOM Conversion Details'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add UOM" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled || !values.stock_uom" @click="addRow" /></template>
		<Message v-for="message in uniqueProblemMessages(problems)" :key="message" severity="error" :closable="false">{{ message }}</Message>
		<ChildGridTable :rows="rows" :columns="columns" :title="field.label || 'UOM Conversion Details'" parent-doctype="Item" child-doctype="UOM Conversion Detail" :can-add="editable && !disabled && Boolean(values.stock_uom)" :add="addRow" :remove-row="editable && !disabled ? (index) => values.uoms.splice(index, 1) : null" :can-remove-row="(row) => !isDefaultRow(row)">
			<template #cell-uom="{ data }">
				<LinkField v-if="editable && !isDefaultRow(data)" v-model="data.uom" doctype="UOM" :aria-label="columnLabel('uom', 'UOM')" :show-open-button="false" :disabled="disabled" :invalid="!data.uom" />
				<span v-else>{{ data.uom }}<small v-if="isDefaultRow(data)"> · Default</small></span>
			</template>
			<template #cell-conversion_factor="{ data }">
				<InputNumber v-if="editable" v-model="data.conversion_factor" :max-fraction-digits="9" :use-grouping="false" :disabled="disabled || isDefaultRow(data)" :aria-label="`${data.uom || 'UOM'} ${columnLabel('conversion_factor', 'Conversion Factor')}`" fluid />
				<span v-else>{{ data.conversion_factor }}</span>
			</template>
			<template #cell-conversion="{ data }">{{ uomConversionWording(data, values.stock_uom) }}</template>
		</ChildGridTable>
		<p v-if="!values.stock_uom" class="item-table-hint">Choose the Default Unit of Measure to start the conversion table.</p>
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
import { stockUomRows, uniqueProblemMessages, uomConversionWording } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const rows = computed(() => props.editable ? props.values.uoms || [] : stockUomRows(props.values.uoms || [], props.values.stock_uom))
const isDefaultRow = (row) => row.uom === props.values.stock_uom && row === rows.value.find((entry) => entry.uom === props.values.stock_uom)
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback
const columns = computed(() => [
	{ key: "uom", label: columnLabel("uom", "UOM"), fieldtype: "Link", reqd: 1 },
	{ key: "conversion_factor", label: columnLabel("conversion_factor", "Conversion Factor"), fieldtype: "Float", width: 160 },
	{ key: "conversion", label: "Conversion", fieldtype: "Data", width: 220, configurable: false, readonly: true },
])
const addRow = () => props.values.uoms.push({ uom: "", conversion_factor: null })
</script>
