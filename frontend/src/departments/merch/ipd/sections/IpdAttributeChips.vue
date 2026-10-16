<template>
	<article class="ipd-chip-card" :aria-label="`${attribute} values`">
		<header>
			<h3>{{ attribute }}</h3>
			<span v-for="role in roles" :key="role" class="erp-count-badge erp-count-badge--active">{{ ROLE_LABELS[role] }}</span>
			<Button v-if="removable" icon="pi pi-trash" text rounded severity="secondary" size="small" :aria-label="`Remove ${attribute}`" @click="emit('remove')" />
		</header>
		<ul class="ipd-chip-list" :aria-label="`${attribute} values`">
			<li v-for="(value, index) in values" :key="value" class="ipd-chip" :class="{ 'ipd-chip--removable': editable, 'is-selected': selectedIndex === index }">
				{{ value }}
				<Button v-if="editable" icon="pi pi-times" text rounded severity="secondary" size="small" :aria-label="`Remove ${value}`" :disabled="busy" @click="remove(value)" />
			</li>
			<li v-for="value in pending" :key="`new-${value}`" class="ipd-chip is-new">{{ value }}<small>Saving</small></li>
			<li v-if="editable">
				<input
					v-model="text"
					class="ipd-chip-input"
					:list="listId"
					:placeholder="values.length ? '+ add or paste a list' : '+ add values'"
					:aria-label="`Add ${attribute} values`"
					:disabled="busy"
					@keydown="onKeydown"
					@paste="onPaste"
					@input="suggest"
				>
				<datalist :id="listId"><option v-for="option in suggestions" :key="option" :value="option" /></datalist>
			</li>
		</ul>
		<p v-if="!values.length && !pending.length && !editable" class="erp-help-text">{{ emptyText }}</p>
		<p v-if="note" class="erp-help-text">{{ note }}</p>
		<p v-if="meta" class="ipd-chip-meta" role="status">{{ meta }}</p>
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
import { computed, inject, onBeforeUnmount, ref } from "vue"

import { searchItemAttributeValues } from "../../../../api/purchase.js"
import DocumentConfirmationDialog from "../../../../components/documents/DocumentConfirmationDialog.vue"
import { parseValueList, usageMessage, valueListMessage } from "../ipdEditor.js"
import { IPD_EDITOR_KEY } from "../useIpdEditor.js"

const ROLE_LABELS = { primary: "Primary", dependent: "Dependent", packing: "Packing", stitching: "Stitching", set: "Set" }
let chipSequence = 0

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
const listId = `ipd-chip-options-${++chipSequence}`
const text = ref("")
const pending = ref([])
const busy = ref(false)
const meta = ref("")
const error = ref("")
const suggestions = ref([])
const selectedIndex = ref(-1)
const confirmVisible = ref(false)
const confirmValue = ref("")
const confirmMessage = ref("")
let suggestTimer = null
let suggestSequence = 0

const known = computed(() => [...props.values, ...pending.value])

async function save(values) {
	busy.value = true
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
async function commit(source) {
	const parsed = parseValueList(source, known.value)
	text.value = ""
	meta.value = valueListMessage(parsed)
	if (!parsed.values.length) return
	pending.value = parsed.values
	await save([...props.values, ...parsed.values])
}
async function remove(value) {
	selectedIndex.value = -1
	error.value = ""
	meta.value = ""
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
	if (event.key === "Enter" || event.key === ",") {
		event.preventDefault()
		if (text.value.trim()) commit(text.value)
		return
	}
	if (event.key !== "Backspace" || text.value || !props.values.length) { selectedIndex.value = -1; return }
	event.preventDefault()
	const last = props.values.length - 1
	if (selectedIndex.value === last) remove(props.values[last])
	else selectedIndex.value = last
}
function onPaste(event) {
	const pasted = event.clipboardData?.getData("text") || ""
	if (!/[,\n\t]/.test(pasted)) return
	event.preventDefault()
	commit(`${text.value}${pasted}`)
}
function suggest() {
	clearTimeout(suggestTimer)
	const query = text.value.trim()
	if (!query) { suggestions.value = []; return }
	suggestTimer = setTimeout(async () => {
		const sequence = ++suggestSequence
		try {
			const rows = await searchItemAttributeValues(props.attribute, query)
			if (sequence === suggestSequence) suggestions.value = (rows || []).map((row) => row.label || row.name).filter((label) => !known.value.includes(label))
		} catch {
			suggestions.value = []
		}
	}, 250)
}
onBeforeUnmount(() => clearTimeout(suggestTimer))
</script>
