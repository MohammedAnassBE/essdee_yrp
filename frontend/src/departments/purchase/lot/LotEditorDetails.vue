<template>
	<DocumentFieldGroupGrid :groups="headerGroups" wide-last-odd aria-label="Lot fields">
		<template #default="{ group }">
			<template v-for="fieldname in group.fields" :key="fieldname">
				<div v-if="fieldname === 'version'" class="lot-edit-fact"><span>Version</span><strong>{{ derived.version || '—' }}</strong></div>
				<FormField v-else-if="fieldname !== 'production_detail' || form.item" :field="fieldSchema(fieldname)" :model-value="form[fieldname]" :form="form" :required="Boolean(fieldSchema(fieldname).reqd)" :invalid="isMissing(fieldname)" :error="isMissing(fieldname) ? `${fieldSchema(fieldname).label} is required.` : ''" :disabled="disabled" compact :input-id="`lot-edit-${fieldname}`" @update:model-value="emit('set-field', fieldname, $event)" />
			</template>
		</template>
	</DocumentFieldGroupGrid>
</template>
<script setup>
import FormField from "../../../components/common/FormField.vue"
import DocumentFieldGroupGrid from "../../../components/documents/DocumentFieldGroupGrid.vue"
import { LOT_EDIT_GROUPS, lotFieldDescription, lotLinkFilters } from "./lotEditor.js"
/** Editable Lot header fields; Version is shown read-only beside the production settings. */
const props = defineProps({ form: { type: Object, required: true }, derived: { type: Object, required: true }, fields: { type: Array, required: true }, attemptedSave: Boolean, disabled: Boolean })
const emit = defineEmits(["set-field"])
const headerGroups = LOT_EDIT_GROUPS.filter((group) => group.key !== "derived").map((group) => (group.key === "production" ? { ...group, fields: [...group.fields, "version"] } : group))
function isMissing(fieldname) {
	return props.attemptedSave && Boolean(fieldSchema(fieldname).reqd) && !props.form[fieldname]
}
function fieldSchema(fieldname) {
	const field = props.fields.find((field) => field.fieldname === fieldname)
	if (!field) throw new Error(`Missing Lot field: ${fieldname}`)
	return { ...field, description: lotFieldDescription(field), link_filters: lotLinkFilters(fieldname, props.form) }
}
</script>
