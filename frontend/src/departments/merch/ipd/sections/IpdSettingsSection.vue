<template>
	<IpdSection :section-key="sectionKey" class="ipd-settings">
		<IpdFields :fields="fields" :section="sectionKey" :apply="apply" />
	</IpdSection>
</template>

<script setup>
import { computed, inject } from 'vue'
import IpdSection from '../IpdSection.vue'
import { IPD_EDITOR_KEY } from '../useIpdEditor.js'
import { attributeNames } from './attributeValues.js'
import IpdFields from './IpdFields.vue'
import { packingChanges } from './packingSection.js'

const props = defineProps({ sectionKey: { type: String, required: true }, part: { type: String, required: true } })
const editor = inject(IPD_EDITOR_KEY)
const fields = computed(() => {
	const draft = editor.draft
	const process = (fieldname, label) => ({ fieldname, label, fieldtype: 'Link', options: 'YRP Process' })
	const attribute = (fieldname, label) => ({ fieldname, label, fieldtype: 'Select', options: attributeNames(draft) })
	const stage = (fieldname, label, hidden) => ({ fieldname, label, fieldtype: 'Select', options: editor.context?.stage_values || [], hidden })
	if (props.part === 'packing') return [
		process('packing_process', 'Packing Process'),
		{ ...attribute('packing_attribute', 'Packing Attribute'), help: 'Attribute based on which Packing Depends' },
		{ ...stage('pack_in_stage', 'Pack In Stage', editor.isNew || !draft.dependent_attribute_mapping), help: 'The stage which is used for packing.' },
		stage('pack_out_stage', 'Pack Out Stage', editor.isNew || !draft.dependent_attribute_mapping),
	]
	if (props.part === 'stitching') return [
		process('stiching_process', 'Stiching Process'),
		attribute('stiching_attribute', 'Stiching Attribute'),
		stage('stiching_in_stage', 'Stiching In Stage', editor.isNew || !draft.stiching_attribute),
		stage('stiching_out_stage', 'Stiching Out Stage', editor.isNew || !draft.stiching_attribute),
	]
	return [process('cutting_process', 'Cutting Process')]
})
function apply(fieldname, value) {
	if (props.part === 'packing') editor.setValues(packingChanges(editor.draft, { [fieldname]: value }))
	else editor.setValue(fieldname, value)
}
</script>
