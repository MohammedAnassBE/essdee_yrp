<template>
	<div class="lot-tab-stack">
		<DocumentFieldGroupGrid :groups="editableGroups" wide-last-odd aria-label="Lot fields">
			<template #default="{ group }">
				<template v-for="fieldname in group.fields" :key="fieldname">
					<FormField v-if="fieldname !== 'production_detail' || form.item" :field="fieldSchema(fieldname)" :model-value="form[fieldname]" :form="form" :required="Boolean(fieldSchema(fieldname).reqd)" :invalid="attemptedSave && Boolean(fieldSchema(fieldname).reqd) && !form[fieldname]" :disabled="disabled" compact :input-id="`lot-edit-${fieldname}`" @update:model-value="emit('set-field', fieldname, $event)" />
				</template>
			</template>
		</DocumentFieldGroupGrid>
		<DocumentFieldGroupGrid :groups="derivedGroups" wide-last-odd facts aria-label="Derived Lot facts">
			<template #default="{ group }"><div v-for="fieldname in group.fields" :key="fieldname" class="lot-edit-fact"><span>{{ DERIVED_LABELS[fieldname] }}</span><strong><DocumentLink v-if="derivedTarget(fieldname)" v-bind="derivedTarget(fieldname)" :label="derived[fieldname] ?? '—'" /><template v-else>{{ derived[fieldname] ?? '—' }}</template></strong></div></template>
		</DocumentFieldGroupGrid>
		<section class="lot-section">
			<header><div><span>Fabric</span><h2>Fabric Details</h2></div><span class="lot-count">{{ countLabel(form.lot_fabric_details.length, 'row') }}</span></header>
			<div class="lot-section__body">
				<ChildTableField parent-doctype="SD YRP Lot" :field="{ fieldname: 'lot_fabric_details', label: 'Fabric Details', options: 'SD YRP Lot Fabric Detail' }" :model-value="form.lot_fabric_details" :child-meta="fabricMeta" :column-filters="fabricColumnFilters" :disabled="disabled" :errors="fabricErrors" @update:model-value="emit('fabric-rows', $event)" />
			</div>
		</section>
	</div>
</template>
<script setup>
import { computed } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import ChildTableField from "../../../components/common/ChildTableField.vue"
import FormField from "../../../components/common/FormField.vue"
import DocumentFieldGroupGrid from "../../../components/documents/DocumentFieldGroupGrid.vue"
import { DERIVED_LABELS, LOT_EDIT_GROUPS, fabricColumnFilters, lotFieldDescription, lotLinkFilters } from "./lotEditor.js"
import { countLabel } from "./lotViews.js"
const props = defineProps({ form: { type: Object, required: true }, derived: { type: Object, required: true }, fields: { type: Array, required: true }, fabricMeta: { type: Object, required: true }, attemptedSave: Boolean, disabled: Boolean })
const emit = defineEmits(["set-field", "fabric-rows"])
const editableGroups = LOT_EDIT_GROUPS.filter((group) => group.key !== "derived")
const derivedGroups = LOT_EDIT_GROUPS.filter((group) => group.key === "derived")
const fabricErrors = computed(() => Object.fromEntries(props.form.lot_fabric_details.flatMap((row, index) => props.attemptedSave && !row.cloth_item ? [[`${index}.cloth_item`, "Cloth Item is required."]] : [])))
function derivedTarget(fieldname) {
	if (!props.derived[fieldname]) return null
	if (["uom", "packing_uom"].includes(fieldname)) return { doctype: "UOM", name: props.derived[fieldname] }
	if (["pack_in_stage", "pack_out_stage"].includes(fieldname) && props.derived[`${fieldname}_name`]) return { doctype: "YRP Item Attribute Value", name: props.derived[`${fieldname}_name`] }
	return null
}
function fieldSchema(fieldname) {
	const field = props.fields.find((field) => field.fieldname === fieldname)
	if (!field) throw new Error(`Missing Lot field: ${fieldname}`)
	return { ...field, description: lotFieldDescription(field), link_filters: lotLinkFilters(fieldname, props.form) }
}
</script>
