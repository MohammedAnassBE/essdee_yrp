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

		<ChildGridTable
			:rows="modelValue"
			:columns="gridColumns"
			:title="field.label || field.fieldname"
			:parent-doctype="parentDoctype || field.parent || ''"
			:child-doctype="field.options || ''"
			:can-add="!isDisabled"
			:add="addRow"
			:remove-row="isDisabled ? null : removeRow"
			show-index
			class="child-table-field__table"
		>
			<template v-for="column in columns" :key="column.fieldname" #[`cell-${column.fieldname}`]="{ data, index }">
				<DocumentLink v-if="(isDisabled || column.read_only) && cellTarget(column, data)" v-bind="cellTarget(column, data)" :label="data[column.fieldname]" />
				<FormField
					v-else
					:field="childTableColumnField(column, columnFilters, data)"
					:model-value="data[column.fieldname]"
					:form="data"
					:disabled="isDisabled"
					:required="Boolean(column.reqd)"
					:invalid="Boolean(errors[`${index}.${column.fieldname}`])"
					:error="errors[`${index}.${column.fieldname}`] || ''"
					:show-label="false"
					:show-open-button="false"
					:input-id="`${field.fieldname}-${index + 1}-${column.fieldname}`"
					:aria-label="`${column.label || column.fieldname}, row ${index + 1}`"
					@update:model-value="setCell(index, column.fieldname, $event)"
				/>
			</template>
			<template #empty>
				<div class="child-table-field__empty">
					<i class="pi pi-table" aria-hidden="true"></i>
					<strong>{{ isDisabled ? "No rows." : "No rows added" }}</strong>
					<span v-if="!isDisabled">Use Add Row to create the first line.</span>
				</div>
			</template>
		</ChildGridTable>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed } from "vue"

import FormField from "./FormField.vue"
import DocumentLink from "./DocumentLink.vue"
import { linkFieldTarget } from "../../utils/linkTarget.js"
import { childTableColumnField } from "./childTableFields.js"
import ChildGridTable from "./childGrid/ChildGridTable.vue"

const props = defineProps({
	field: { type: Object, required: true },
	modelValue: { type: Array, default: () => [] },
	childMeta: { type: Object, default: null },
	columnFilters: { type: Function, default: null },
	disabled: { type: Boolean, default: false },
	errors: { type: Object, default: () => ({}) },
	parentDoctype: { type: String, default: "" },
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
const preferredColumns = computed(() => eligibleColumns.value.filter(
	(column) => column.in_list_view || column.reqd || column.read_only,
))
const columns = computed(() => preferredColumns.value.length ? eligibleColumns.value : eligibleColumns.value.slice(0, 6))

const gridColumns = computed(() => columns.value.map((column) => ({
	key: column.fieldname,
	label: column.label || column.fieldname,
	fieldtype: column.fieldtype,
	reqd: column.reqd,
	readonly: Boolean(column.read_only),
	hidden: preferredColumns.value.length > 0 && !preferredColumns.value.includes(column),
})))

function cellTarget(column, data) {
	return linkFieldTarget({ ...column, value: data[column.fieldname] }, data)
}

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
	color: var(--erp-text);
	font-size: var(--erp-font-size-table);
	font-weight: var(--erp-font-weight-semibold);
}

.child-table-field__header small {
	display: block;
	margin-top: 4px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.child-table-field__table {
	background: var(--erp-surface);
	border: 1px solid var(--erp-border-strong);
	border-radius: var(--erp-panel-radius);
	overflow: hidden;
	box-shadow: var(--erp-shadow-xs);
}

.child-table-field__table :deep(.p-datatable-table-container:focus-visible) {
	outline: 2px solid var(--erp-accent);
	outline-offset: -2px;
}

.child-table-field__index {
	width: 54px;
	min-width: 54px;
}

.child-table-field__empty {
	display: grid;
	justify-items: center;
	gap: 4px;
	padding: 34px 24px;
	color: var(--erp-text-muted);
	text-align: center;
}

.child-table-field__empty i {
	margin-bottom: 4px;
	color: var(--erp-accent);
	font-size: var(--erp-font-size-hero);
}

.child-table-field__empty strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.child-table-field__empty span {
	font-size: var(--erp-font-size-min);
}

.child-table-field__table :deep(.p-datatable-thead > tr > th) {
	padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-semibold);
	letter-spacing: .06em;
	text-transform: uppercase;
	background: var(--erp-surface-muted);
}

.child-table-field__table :deep(.p-datatable-tbody > tr > td) {
	padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x);
	border-bottom: 1px solid var(--erp-border-subtle);
	vertical-align: top;
}

.child-table-field__table :deep(.p-datatable-tbody > tr:hover) {
	background: var(--erp-surface-hover);
}

@media (max-width: 620px) {
	.child-table-field__table :deep(.p-datatable-table-container) {
		-webkit-mask-image: linear-gradient(to right, var(--erp-text) 0, var(--erp-text) calc(100% - 18px), transparent 100%);
		mask-image: linear-gradient(to right, var(--erp-text) 0, var(--erp-text) calc(100% - 18px), transparent 100%);
	}
	.child-table-field__header {
		align-items: stretch;
		flex-direction: column;
	}

	.child-table-field__header :deep(.p-button) {
		width: 100%;
	}
}
</style>
