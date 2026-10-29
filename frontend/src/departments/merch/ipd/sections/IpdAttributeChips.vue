<template>
	<article class="ipd-chip-card" :aria-label="`${attribute} values`">
		<header>
			<h3>{{ attribute }}</h3>
			<span v-for="role in roles" :key="role" class="erp-count-badge erp-count-badge--active">{{ ROLE_LABELS[role] }}</span>
			<Button v-if="removable" icon="pi pi-trash" text rounded severity="secondary" size="small" :aria-label="`Remove ${attribute}`" @click="emit('remove')" />
		</header>
		<ul ref="chipList" class="ipd-chip-list" :aria-label="`${attribute} values`">
			<li v-for="(value, index) in values" :key="value" v-bind="chipProps(value, index)" class="ipd-chip" :class="{ 'ipd-chip--removable': editable, 'is-selected': selectedIndex === index }">
				{{ value }}
				<Button v-if="editable" icon="pi pi-times" text rounded severity="secondary" size="small" :aria-label="`Remove ${value}`" :disabled="busy" @click="remove(value)" />
			</li>
			<li v-for="value in pending" :key="`new-${value}`" class="ipd-chip is-new">{{ value }}<small>Saving</small></li>
			<li v-if="editable" class="ipd-chip-add" @keydown="onKeydown" @paste.capture="onPaste">
				<LinkField
					ref="input"
					v-model="text"
					doctype="Item Attribute Value"
					:search-handler="searchValues"
					create-doctype="YRP Item Attribute Value"
					:create-values="{ attribute_name: attribute }"
					create-value-field="attribute_value"
					:reset-version="resetVersion"
					:show-open-button="false"
					:placeholder="`+ add ${attribute}`"
					:aria-label="`Add ${attribute} values`"
					:disabled="busy"
					@select="addSelected"
				/>
			</li>
		</ul>
		<p v-if="editable && !busy && values.length > 1" class="erp-help-text">Drag to reorder, or Alt + ← / →.</p>
		<p v-if="!values.length && !pending.length && !editable" class="erp-help-text">{{ emptyText }}</p>
		<p v-if="note" class="erp-help-text">{{ note }}</p>
		<p class="ipd-chip-meta" role="status">{{ meta }}</p>
		<p v-if="error" class="ipd-grid-notice ipd-grid-notice--error" role="alert"><i class="pi pi-exclamation-circle" aria-hidden="true" />{{ error }}</p>
		<DocumentConfirmationDialog
			v-model:visible="confirmVisible"
			:title="`Remove ${confirmValue}?`"
			:message="confirmMessage"
			confirm-label="Remove value"
			confirm-icon="pi pi-trash"
			cancel-label="Keep value"
			severity="warn"
			:busy="busy"
			@confirm="confirmRemove"
		/>
	</article>
</template>

<script setup>
import Button from "primevue/button"
import { computed, inject, nextTick, ref } from "vue"

import { searchItemAttributeValues } from "../../../../api/purchase.js"
import LinkField from "../../../../components/common/LinkField.vue"
import { useChipReorder } from "../../../../components/common/useChipReorder.js"
import DocumentConfirmationDialog from "../../../../components/documents/DocumentConfirmationDialog.vue"
import { parseValueList, usageMessage, valueListMessage } from "../ipdEditor.js"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"

const ROLE_LABELS = { primary: "Primary", dependent: "Dependent", packing: "Packing", stitching: "Stitching", set: "Set" }

const props = defineProps({
	attribute: { type: String, required: true },
	values: { type: Array, default: () => [] },
	roles: { type: Array, default: () => [] },
	editable: { type: Boolean, default: false },
	removable: { type: Boolean, default: false },
	note: { type: String, default: "" },
	emptyText: { type: String, default: "No values yet." },
})
const emit = defineEmits(["remove"])
const editor = inject(IPD_EDITOR_KEY)
const input = ref(null)
const text = ref("")
const resetVersion = ref(0)
const pending = ref([])
const busy = ref(false)
const meta = ref("")
const error = ref("")
const selectedIndex = ref(-1)
const confirmVisible = ref(false)
const confirmValue = ref("")
const confirmMessage = ref("")

const known = computed(() => [...props.values, ...pending.value])
const chipList = ref(null)
const { chipProps } = useChipReorder({
	items: () => props.values,
	enabled: () => props.editable && !busy.value,
	container: chipList,
	onReorder: values => { selectedIndex.value = -1; return save(values) },
	announce: message => { meta.value = message },
})

async function save(values) {
	busy.value = true
	meta.value = ""
	error.value = ""
	try {
		await editor.saveAttributeValues(props.attribute, values)
		return true
	} catch (reason) {
		error.value = reason?.message || `Unable to save the ${props.attribute} values.`
		return false
	} finally {
		busy.value = false
		pending.value = []
	}
}
async function addSelected({ label }) {
	if (busy.value || !label || known.value.some((value) => value.toLowerCase() === label.toLowerCase())) return
	pending.value = [label]
	await save([...props.values, label])
	await resetInput()
}
async function resetInput() {
	text.value = ""
	resetVersion.value += 1
	selectedIndex.value = -1
	await nextTick()
	input.value?.focus()
}
async function searchValues(query) {
	const rows = await searchItemAttributeValues(props.attribute, query)
	const present = new Set(known.value.map((value) => value.toLowerCase()))
	return (rows || []).map((row) => ({ name: row.label || row.name, label: row.label || row.name }))
		.filter((row) => !present.has(row.label.toLowerCase()))
}
async function remove(value) {
	selectedIndex.value = -1
	meta.value = ""
	error.value = ""
	try {
		const usage = (await editor.valueUsage(props.attribute, [value]))?.[value] || []
		if (!usage.length) { await save(props.values.filter((candidate) => candidate !== value)); return }
		confirmValue.value = value
		confirmMessage.value = `${value} is used in ${usageMessage(usage)}. Removing it leaves those rows without this value.`
		confirmVisible.value = true
	} catch (reason) {
		error.value = reason?.message || "Unable to check where this value is used."
	}
}
async function confirmRemove() {
	const value = confirmValue.value
	if (await save(props.values.filter((candidate) => candidate !== value))) confirmVisible.value = false
}

function onKeydown(event) {
	if (busy.value || event.isComposing || event.keyCode === 229 || event.target?.tagName !== "INPUT") return
	if (event.key !== "Backspace" || event.target.value || !props.values.length) { selectedIndex.value = -1; return }
	event.preventDefault()
	const last = props.values.length - 1
	if (selectedIndex.value === last) remove(props.values[last])
	else selectedIndex.value = last
}
async function onPaste(event) {
	const pasted = event.clipboardData?.getData("text") || ""
	if (!/[,\n\r\t]/.test(pasted)) return
	event.preventDefault()
	if (busy.value) return
	const parsed = parseValueList(pasted, known.value)
	error.value = ""
	meta.value = ""
	if (parsed.values.length) {
		pending.value = parsed.values
		if (await save([...props.values, ...parsed.values])) meta.value = valueListMessage(parsed)
	} else meta.value = valueListMessage(parsed)
	await resetInput()
}
</script>
