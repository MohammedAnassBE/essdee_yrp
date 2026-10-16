<template>
	<ItemTableCard :label="field.label || 'UOM Conversion Details'" :editable="editable">
		<template #actions><Button v-if="editable" label="Add UOM" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="disabled || !values.stock_uom" @click="values.uoms.push({ uom: '', conversion_factor: null })" /></template>
		<Message v-for="message in uniqueProblemMessages(problems)" :key="message" severity="error" :closable="false">{{ message }}</Message>
		<DataTable :value="rows" size="small" scrollable class="erp-data-table">
			<Column :header="columnLabel('uom', 'UOM')"><template #body="{ data }">
				<LinkField v-if="editable && !isDefaultRow(data)" v-model="data.uom" doctype="UOM" :aria-label="columnLabel('uom', 'UOM')" :show-open-button="false" :disabled="disabled" :invalid="!data.uom" />
				<span v-else>{{ data.uom }}<small v-if="isDefaultRow(data)"> · Default</small></span>
			</template></Column>
			<Column :header="columnLabel('conversion_factor', 'Conversion Factor')"><template #body="{ data }">
				<InputNumber v-if="editable" v-model="data.conversion_factor" :max-fraction-digits="9" :use-grouping="false" :disabled="disabled || isDefaultRow(data)" :aria-label="`${data.uom || 'UOM'} ${columnLabel('conversion_factor', 'Conversion Factor')}`" fluid />
				<span v-else>{{ data.conversion_factor }}</span>
			</template></Column>
			<Column header="Conversion"><template #body="{ data }">{{ uomConversionWording(data, values.stock_uom) }}</template></Column>
			<Column v-if="editable" header="Actions"><template #body="{ data, index }"><Button v-if="!isDefaultRow(data)" icon="pi pi-trash" severity="danger" text :disabled="disabled" :aria-label="`Remove ${data.uom || 'UOM'} conversion`" @click="values.uoms.splice(index, 1)" /></template></Column>
		</DataTable>
		<p v-if="!values.stock_uom" class="item-table-hint">Choose the Default Unit of Measure to start the conversion table.</p>
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
import { stockUomRows, uniqueProblemMessages, uomConversionWording } from "./itemTables.js"

const props = defineProps({ values: { type: Object, required: true }, field: { type: Object, default: () => ({}) }, editable: Boolean, disabled: Boolean, problems: { type: Array, default: () => [] } })
const rows = computed(() => props.editable ? props.values.uoms || [] : stockUomRows(props.values.uoms || [], props.values.stock_uom))
const isDefaultRow = (row) => row.uom === props.values.stock_uom && row === rows.value.find((entry) => entry.uom === props.values.stock_uom)
const columnLabel = (name, fallback) => props.field.columns?.[name]?.label || fallback
</script>
