<template>
	<dl v-if="editor.readonly" class="ipd-facts">
		<div v-for="field in visibleFields" :id="`ipd-edit-${field.fieldname}`" :key="field.fieldname" tabindex="-1">
			<dt>{{ field.label }}</dt>
			<dd><DocumentLink v-if="target(field)" v-bind="target(field)" :label="display(field)" /><template v-else>{{ display(field) }}</template></dd>
		</div>
	</dl>
	<div v-else class="ipd-fields">
		<div v-for="field in visibleFields" :key="field.fieldname" class="ipd-field" tabindex="-1">
			<FormField
				:field="schema(field)"
				:model-value="value(field)"
				:disabled="Boolean(field.disabled)"
				:required="Boolean(field.required ?? editor.fields?.[field.fieldname]?.reqd)"
				:invalid="Boolean(problem(field.fieldname))"
				:error="problem(field.fieldname)"
				:input-id="`ipd-edit-${field.fieldname}`"
				compact
				@update:model-value="update(field.fieldname, $event)"
			/>
			<p v-if="field.help" class="erp-help-text">{{ field.help }}</p>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted } from "vue"

import DocumentLink from "../../../../components/common/DocumentLink.vue"
import { linkFieldTarget } from "../../../../utils/linkTarget.js"

import FormField from "../../../../components/common/FormField.vue"
import { ipdAttributeLinkName } from "../ipdLinks.js"
import { stableStringify } from "../ipdEditor.js"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"

const props = defineProps({
	fields: { type: Array, required: true },
	section: { type: String, default: "" },
	apply: { type: Function, default: null },
})
const editor = inject(IPD_EDITOR_KEY)
const visibleFields = computed(() => props.fields.filter((field) => !field.hidden))

function schema(field) {
	const stored = editor.fields?.[field.fieldname] || {}
	const options = Array.isArray(field.options) ? withCurrent(field).join("\n") : field.options ?? stored.options
	return { ...stored, fieldname: field.fieldname, label: field.label || stored.label, fieldtype: field.fieldtype || stored.fieldtype || "Data", options, precision: field.precision, link_filters: field.filters ?? stored.link_filters }
}
function withCurrent(field) {
	const current = editor.draft[field.fieldname]
	return current && !field.options.includes(current) ? [...field.options, current] : field.options
}
function value(field) { return editor.draft[field.fieldname] ?? editor.record?.[field.fieldname] }
function target(field) {
	const meta = editor.fields?.[field.fieldname] || schema(field)
	const current = value(field)
	const link_name = meta.options === "YRP Item Attribute Value" ? ipdAttributeLinkName(editor, field.fieldname, current) : undefined
	return linkFieldTarget({ ...meta, value: current, link_name }, { ...editor.record, ...editor.draft })
}
function display(field) {
	const current = value(field)
	if (field.fieldtype === "Check") return Number(current) ? "Yes" : "No"
	return current === null || current === undefined || current === "" ? "—" : String(current)
}
function problem(fieldname) {
	return (editor.checks?.problems || []).find((entry) => entry.field === fieldname && !entry.row_key)?.message || ""
}
const unregister = []
onMounted(() => {
	for (const field of props.fields) unregister.push(editor.registerFocus(field.fieldname, () => {
		const element = document.getElementById(`ipd-edit-${field.fieldname}`)
		if (!element) return false
		element.scrollIntoView({ block: 'nearest', inline: 'nearest' })
		const target = element.disabled ? element.closest('.ipd-field') : element
		target?.focus({ preventScroll: true })
		return Boolean(target && document.activeElement === target)
	}))
})
onBeforeUnmount(() => unregister.forEach((remove) => remove()))
function update(fieldname, value) {
	if (stableStringify(value ?? null) === stableStringify(editor.draft[fieldname] ?? null)) return
	if (props.apply) props.apply(fieldname, value)
	else editor.setValue(fieldname, value)
}
</script>
