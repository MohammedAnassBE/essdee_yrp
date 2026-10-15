<template>
	<section v-if="visibleFields.length || visibleTables.length" class="pd-fields erp-card">
		<div v-if="visibleFields.length" class="pd-fields__grid">
			<FormField
				v-for="field in visibleFields"
				:key="field.fieldname"
				:field="field"
				:model-value="form[field.fieldname]"
				:form="form"
				:disabled="disabled || Boolean(field.read_only) || isFieldReadOnly(field.fieldname, isNew)"
				:required="Boolean(field.reqd)"
				@update:model-value="emit('update', field.fieldname, $event)"
			/>
		</div>
		<ChildTableField
			v-for="table in visibleTables"
			:key="table.fieldname"
			:field="table"
			:model-value="form[table.fieldname] || []"
			:child-meta="childMetaFor(table)"
			:disabled="disabled"
			@update:model-value="emit('update', table.fieldname, $event)"
		/>
	</section>
</template>

<script setup>
import { computed } from "vue"

import ChildTableField from "../../../components/common/ChildTableField.vue"
import FormField from "../../../components/common/FormField.vue"
import { isFieldReadOnly, visibleForSetItem } from "../pdViews.js"

const props = defineProps({
	fields: { type: Array, default: () => [] },
	tables: { type: Array, default: () => [] },
	form: { type: Object, required: true },
	isNew: { type: Boolean, default: false },
	metaByName: { type: Object, default: () => ({}) },
	linkFilters: { type: Object, default: () => ({}) },
	disabled: { type: Boolean, default: false },
})

const emit = defineEmits(["update"])
const productMeta = computed(() => props.metaByName["SD YRP Product"] || {})
const fieldsByName = computed(() => Object.fromEntries(
	(productMeta.value.fields || []).filter((field) => field.fieldname).map((field) => [field.fieldname, field]),
))
const isSetItem = computed(() => Boolean(Number(props.form.is_set_item)))
const visibleFields = computed(() => props.fields.map(fieldFor).filter(isVisible))
const visibleTables = computed(() => props.tables.map(fieldFor).filter(isVisible))

function fieldFor(fieldname) {
	const field = fieldsByName.value[fieldname]
	if (!field) return null
	const filters = props.linkFilters[fieldname]
	return filters ? { ...field, link_filters: filters } : field
}

function isVisible(field) {
	return Boolean(field && !Number(field.hidden) && visibleForSetItem(field.fieldname, isSetItem.value))
}

function childMetaFor(table) {
	const childMeta = props.metaByName[table.options]
	if (!childMeta) return null
	return {
		...childMeta,
		fields: (childMeta.fields || []).map((field) => childFieldFor(table.fieldname, field)),
	}
}

function childFieldFor(tableName, field) {
	const filters = props.linkFilters[`${tableName}.${field.fieldname}`]
	return filters ? { ...field, link_filters: filters } : field
}
</script>
