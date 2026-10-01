<template>
	<section class="child-table-field">
		<header class="child-table-field__header">
			<div>
				<h3>{{ field.label || field.fieldname }}</h3>
				<small v-if="field.description">{{ field.description }}</small>
			</div>
			<Button
				v-if="!isDisabled"
				icon="pi pi-plus"
				label="Add Row"
				severity="secondary"
				outlined
				size="small"
				@click="addRow"
			/>
		</header>

		<DataTable
			:value="modelValue"
			show-gridlines
			striped-rows
			scrollable
			size="small"
			class="child-table-field__table"
		>
			<Column header="#" frozen class="child-table-field__index">
				<template #body="{ index }">{{ index + 1 }}</template>
			</Column>
			<Column
				v-for="column in columns"
				:key="column.fieldname"
				:header="column.label || column.fieldname"
				:style="{ minWidth: columnWidth(column) }"
			>
				<template #body="{ data, index }">
					<FormField
						:field="column"
						:model-value="data[column.fieldname]"
						:form="data"
						:disabled="isDisabled"
						:required="Boolean(column.reqd)"
						:invalid="Boolean(errors[`${index}.${column.fieldname}`])"
						:error="errors[`${index}.${column.fieldname}`] || ''"
						:show-label="false"
						:show-open-button="false"
						@update:model-value="setCell(index, column.fieldname, $event)"
					/>
				</template>
			</Column>
			<Column v-if="!isDisabled" header="" frozen align-frozen="right">
				<template #body="{ index }">
					<Button
						icon="pi pi-trash"
						severity="danger"
						text
						rounded
						:aria-label="`Remove row ${index + 1}`"
						@click="removeRow(index)"
					/>
				</template>
			</Column>
			<template #empty>
				<div class="child-table-field__empty">No rows added.</div>
			</template>
		</DataTable>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Column from "primevue/column"
import DataTable from "primevue/datatable"
import { computed } from "vue"

import FormField from "./FormField.vue"

const props = defineProps({
	field: { type: Object, required: true },
	modelValue: { type: Array, default: () => [] },
	childMeta: { type: Object, default: null },
	disabled: { type: Boolean, default: false },
	errors: { type: Object, default: () => ({}) },
})

const emit = defineEmits(["update:modelValue", "change"])

const excludedFieldtypes = new Set([
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Heading",
	"Fold",
	"Table",
	"Table MultiSelect",
	"Image",
	"Attach Image",
	"Signature",
])

const isDisabled = computed(() => props.disabled || Boolean(props.field.read_only))
const eligibleColumns = computed(() =>
	(props.childMeta?.fields || []).filter(
		(column) =>
			column.fieldname &&
			!column.hidden &&
			!excludedFieldtypes.has(column.fieldtype),
	),
)
const columns = computed(() => {
	const preferred = eligibleColumns.value.filter(
		(column) => column.in_list_view || column.reqd || column.read_only,
	)
	return preferred.length ? preferred : eligibleColumns.value.slice(0, 6)
})

function updateRows(rows) {
	emit("update:modelValue", rows)
	emit("change", rows)
}

function setCell(index, fieldname, value) {
	const rows = props.modelValue.map((row, rowIndex) =>
		rowIndex === index ? { ...row, [fieldname]: value } : row,
	)
	updateRows(rows)
}

function addRow() {
	const row = {
		doctype: props.field.options,
		idx: props.modelValue.length + 1,
	}
	for (const column of eligibleColumns.value) {
		if (column.default !== undefined && column.default !== null) {
			row[column.fieldname] = column.fieldtype === "Check" ? Number(column.default) : column.default
		}
	}
	updateRows([...props.modelValue, row])
}

function removeRow(index) {
	updateRows(
		props.modelValue
			.filter((_, rowIndex) => rowIndex !== index)
			.map((row, rowIndex) => ({ ...row, idx: rowIndex + 1 })),
	)
}

function columnWidth(column) {
	if (["Text", "Long Text", "Text Editor", "Code"].includes(column.fieldtype)) return "260px"
	if (["Link", "Dynamic Link", "Data"].includes(column.fieldtype)) return "210px"
	return "150px"
}
</script>

<style scoped>
.child-table-field {
	display: grid;
	gap: 12px;
	min-width: 0;
}

.child-table-field__header {
	display: flex;
	align-items: end;
	justify-content: space-between;
	gap: 16px;
}

.child-table-field__header h3 {
	margin: 0;
	font-size: 0.95rem;
}

.child-table-field__header small {
	display: block;
	margin-top: 4px;
	color: #77827c;
}

.child-table-field__table {
	border-radius: 12px;
	overflow: hidden;
}

.child-table-field__index {
	width: 54px;
	min-width: 54px;
}

.child-table-field__empty {
	padding: 24px;
	color: #77827c;
	text-align: center;
}

.child-table-field__table :deep(.p-datatable-tbody > tr > td) {
	vertical-align: top;
}
</style>
