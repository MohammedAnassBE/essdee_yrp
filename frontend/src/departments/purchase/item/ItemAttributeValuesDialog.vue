<template>
	<Dialog :visible="visible" modal :header="`${attribute} values`" class="erp-entity-dialog erp-dialog--md attribute-values-dialog" :dismissable-mask="false" :closable="true" @update:visible="emit('update:visible', $event)">
		<div class="attribute-values-dialog__body">
			<div v-if="!draft.length" class="attribute-values__all"><strong>All {{ attribute }} values are allowed.</strong><span>Add values below to restrict this item.</span></div>
			<div v-else class="attribute-values-dialog__state"><span>{{ draft.length }} selected</span><Button label="Allow all values" severity="secondary" text size="small" @click="draft = []" /></div>
			<div v-if="draft.length" class="attribute-values-dialog__chips">
				<span v-for="value in draft" :key="value" :class="{ 'is-new': draftNewValues.includes(value) }">{{ value }}<small v-if="draftNewValues.includes(value)">New</small><Button icon="pi pi-times" severity="secondary" text rounded :aria-label="`Remove ${value}`" @click="draft = removeAttributeValueDraft(draft, value)" /></span>
			</div>
			<div @keydown.escape="keepDialogOpen">
				<LinkField v-model="candidate" label="Add value" doctype="Item Attribute Value" :search-handler="searchValues" :show-open-button="false" :placeholder="`Search ${attribute}…`" @select="addValue($event.label)" />
			</div>
			<div v-if="canCreate" class="attribute-values-dialog__add">
				<InputText v-model="newValue" :placeholder="`New ${attribute} value`" :aria-label="`New ${attribute} value`" fluid @keydown.enter.prevent="createValue" />
				<Button label="Create" icon="pi pi-plus" severity="secondary" outlined :loading="creating" :disabled="!newValue.trim()" @click="createValue" />
			</div>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text @click="emit('update:visible', false)" />
			<Button label="Apply" icon="pi pi-check" :disabled="!changed || creating" @click="apply" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { computed, nextTick, ref, watch } from "vue"

import { searchItemAttributeValues } from "../../../api/purchase.js"
import LinkField from "../../../components/common/LinkField.vue"
import { addAttributeValueDraft, isSameAttributeValue, matchingAttributeValue, removeAttributeValueDraft } from "../purchaseViews.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	attribute: { type: String, default: "" },
	values: { type: Array, default: () => [] },
	newValues: { type: Array, default: () => [] },
	canCreate: { type: Boolean, default: false },
})
const emit = defineEmits(["update:visible", "apply"])

const draft = ref([])
const stagedValues = ref([])
const candidate = ref("")
const newValue = ref("")
const creating = ref(false)
const error = ref("")
let openSequence = 0

const draftNewValues = computed(() => stagedValues.value.filter((value) => draft.value.includes(value)))
const changed = computed(() => draft.value.length !== props.values.length || draft.value.some((value, index) => value !== props.values[index]))

watch(() => props.visible, (visible) => {
	openSequence += 1
	creating.value = false
	if (!visible) return
	draft.value = [...props.values]
	stagedValues.value = [...props.newValues]
	candidate.value = ""
	newValue.value = ""
	error.value = ""
})

async function searchValues(text) {
	const rows = await searchItemAttributeValues(props.attribute, text)
	return (rows || []).filter((row) => !draft.value.some((value) => isSameAttributeValue(value, row.label)))
}

function addValue(label) {
	draft.value = addAttributeValueDraft(draft.value, label)
	nextTick(() => { candidate.value = "" })
}

async function createValue() {
	const label = newValue.value.trim()
	if (!label || creating.value) return
	const sequence = openSequence
	creating.value = true
	error.value = ""
	try {
		const rows = await searchItemAttributeValues(props.attribute, label)
		if (sequence !== openSequence) return
		const existing = matchingAttributeValue(rows, label)
		const next = addAttributeValueDraft(draft.value, existing || label)
		if (!existing && next !== draft.value) stagedValues.value = [...stagedValues.value, label]
		draft.value = next
		newValue.value = ""
	} catch (reason) {
		if (sequence === openSequence) error.value = reason?.message || `Unable to check ${props.attribute} values.`
	} finally {
		if (sequence === openSequence) creating.value = false
	}
}

function keepDialogOpen(event) {
	if (event.target?.getAttribute?.("aria-expanded") === "true") event.stopPropagation()
}

function apply() {
	emit("apply", [...draft.value], draftNewValues.value)
	emit("update:visible", false)
}
</script>

<style scoped>
.attribute-values-dialog__body { display: grid; min-width: 0; gap: var(--erp-space-3); }
.attribute-values-dialog__state { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-2); color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.attribute-values-dialog__chips { display: flex; min-width: 0; flex-wrap: wrap; gap: calc(var(--erp-space-1) + 2px); }
.attribute-values-dialog__chips > span { display: inline-flex; max-width: 100%; align-items: center; gap: var(--erp-space-1); padding-left: var(--erp-space-3); overflow-wrap: anywhere; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); background: var(--erp-surface-soft); }
.attribute-values-dialog__chips > span.is-new { border-style: dashed; }
.attribute-values-dialog__chips small { flex-shrink: 0; white-space: nowrap; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; text-transform: uppercase; }
.attribute-values-dialog__add { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: end; gap: var(--erp-space-2); }
.attribute-values__all { display: grid; min-width: 0; gap: var(--erp-space-1); padding: var(--erp-space-2) var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-accent) 24%, var(--erp-border)); border-radius: var(--erp-control-radius); background: var(--erp-accent-soft); }
.attribute-values__all strong { color: var(--erp-accent-hover); font-size: var(--erp-font-size-caption); }
.attribute-values__all span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
@media (max-width: 650px) { .attribute-values-dialog__add { grid-template-columns: minmax(0, 1fr); } }
</style>
