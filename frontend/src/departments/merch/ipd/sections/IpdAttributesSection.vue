<template>
	<IpdSection :section-key="sectionKey">
		<div class="ipd-section-stack">
			<IpdFields :fields="fields" :section="sectionKey" />
			<div v-if="rows.length" class="ipd-table-scroll">
				<table id="ipd-edit-item_attributes" class="ipd-simple-table" tabindex="-1" aria-label="Item Attributes">
					<thead><tr><th scope="col">Attribute</th><th scope="col">Attribute Mapping</th></tr></thead>
					<tbody><tr v-for="(row, index) in rows" :key="row.name || index"><th scope="row">{{ row.attribute || '—' }}</th><td>{{ row.mapping || '—' }}</td></tr></tbody>
				</table>
			</div>
			<div v-if="!editor.isNew" class="ipd-chip-cards">
				<IpdAttributeChips
					v-for="card in cards"
					:key="card.attribute"
					:attribute="card.attribute"
					:values="card.values"
					:roles="card.roles"
					:editable="card.editable"
					:removable="card.removable"
					:note="card.note"
					:empty-text="card.emptyText"
					@remove="removeAttribute(card.attribute)"
				/>
			</div>
			<div v-if="!editor.readonly" class="ipd-inline-add">
				<LinkField v-model="newAttribute" doctype="Item Attribute" input-id="ipd-edit-new-attribute" placeholder="Add attribute" aria-label="Add attribute" :show-open-button="false" />
				<Button label="Add attribute" icon="pi pi-plus" size="small" outlined :disabled="!canAdd" @click="addAttribute" />
			</div>
			<p v-if="!editor.readonly" class="erp-help-text">Values are saved straight to this IPD's own attribute lists. New attributes get their list when the IPD is saved.</p>
			<template v-if="!editor.isNew && stages.length">
				<h3 class="ipd-subhead">Stages <small>Edited in Desk</small></h3>
				<div class="ipd-table-scroll">
					<table class="ipd-simple-table">
						<thead><tr><th scope="col">Stage</th><th scope="col">UOM</th><th scope="col">Display Name</th><th v-for="attribute in attributeNames" :key="attribute" scope="col">{{ attribute }}</th></tr></thead>
						<tbody><tr v-for="stage in stages" :key="stage.name"><th scope="row">{{ stage.name }}</th><td>{{ stage.uom }}</td><td>{{ stage.displayName }}</td><td v-for="attribute in attributeNames" :key="attribute"><span :aria-label="stage.attributes.includes(attribute) ? 'Yes' : 'No'">{{ stage.attributes.includes(attribute) ? "✓" : "—" }}</span></td></tr></tbody>
					</table>
				</div>
			</template>
			<IpdFields :fields="quantityFields" />
		</div>
	</IpdSection>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, ref } from "vue"

import LinkField from "../../../../components/common/LinkField.vue"
import IpdSection from "../IpdSection.vue"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import IpdAttributeChips from "./IpdAttributeChips.vue"
import IpdFields from "./IpdFields.vue"
import "./sections.css"

const ROLE_FIELDS = [["primary", "primary_item_attribute"], ["dependent", "dependent_attribute"], ["packing", "packing_attribute"], ["stitching", "stiching_attribute"], ["set", "set_item_attribute"]]

defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})
const editor = inject(IPD_EDITOR_KEY)
const newAttribute = ref("")
const rows = computed(() => editor.draft.item_attributes || [])
const attributeNames = computed(() => rows.value.map((row) => row.attribute).filter(Boolean))
const contextByAttribute = computed(() => new Map((editor.context?.attributes || []).map((entry) => [entry.attribute, entry])))
const canAdd = computed(() => Boolean(newAttribute.value) && !attributeNames.value.includes(newAttribute.value))
const fields = computed(() => [
	{ fieldname: "primary_item_attribute", label: "Primary Item Attribute", fieldtype: "Select", options: attributeNames.value, disabled: !editor.isNew },
	{ fieldname: "dependent_attribute", label: "Dependent Attribute", fieldtype: "Select", options: attributeNames.value, disabled: !editor.isNew },
])
const quantityFields = computed(() => [
	{ fieldname: "additional_cloth", label: "Additional Cloth %", fieldtype: "Float", disabled: Boolean(Number(editor.draft.is_cloth_item)) },
	{ fieldname: "stiching_attribute_quantity", label: "Stiching Attribute Quantity", fieldtype: "Int", disabled: Boolean(Number(editor.draft.is_cloth_item)) },
])
const stages = computed(() => Object.entries(editor.context?.dependent?.attr_list || {}).map(([name, detail]) => ({
	name, attributes: detail.attributes || [], displayName: detail.name || "", uom: detail.uom || "",
})))

const cards = computed(() => rows.value.filter((row) => row.attribute).map((row) => {
	const entry = contextByAttribute.value.get(row.attribute)
	const roles = ROLE_FIELDS.filter(([, fieldname]) => editor.draft[fieldname] === row.attribute).map(([role]) => role)
	return { attribute: row.attribute, values: entry?.values || [], roles, ...access(row, entry, roles) }
}))

function access(row, entry, roles) {
	if (editor.readonly) return { editable: false, removable: false, note: "", emptyText: "No values." }
	if (!entry || !row.mapping) return { editable: false, removable: !row.name, note: "", emptyText: "Save the IPD to start this value list." }
	if (entry.numeric) return { editable: false, removable: false, note: "Numeric values come from the attribute itself.", emptyText: "No values." }
	if (entry.is_shared) return { editable: false, removable: false, note: "This list is shared with another document. Edit it there.", emptyText: "No values." }
	if (roles.includes("dependent")) return { editable: false, removable: false, note: "Stages are edited in Desk.", emptyText: "No values." }
	return { editable: true, removable: false, note: "", emptyText: "No values yet." }
}
function addAttribute() {
	if (!canAdd.value) return
	editor.setValue("item_attributes", [...rows.value, { attribute: newAttribute.value }])
	newAttribute.value = ""
}
function removeAttribute(attribute) {
	editor.setValue("item_attributes", rows.value.filter((row) => row.name || row.attribute !== attribute))
}
</script>
