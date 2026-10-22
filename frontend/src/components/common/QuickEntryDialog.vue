<template>
	<Dialog
		:visible="visible"
		modal
		:header="`New ${doctype}`"
		class="erp-dialog--sm quick-entry-dialog"
		:closable="!busy"
		@update:visible="emit('update:visible', $event)"
	>
		<form :id="formId" class="quick-entry-dialog__form" novalidate @submit.prevent="submit">
			<i v-if="loading" class="pi pi-spin pi-spinner" aria-label="Loading" />
			<FormField
				v-for="field in plan.fields"
				:key="field.fieldname"
				:field="field"
				:model-value="values[field.fieldname]"
				:form="values"
				:required="Boolean(field.reqd)"
				:disabled="busy || plan.locked.includes(field.fieldname)"
				:show-open-button="false"
				:input-id="`${formId}-${field.fieldname}`"
				@update:model-value="values[field.fieldname] = $event"
			/>
			<Message v-if="!loading && !plan.supported" severity="info" :closable="false">
				{{ doctype }} needs more details than a quick entry. <a :href="deskNewPath" target="_blank" rel="noopener">Open the full form</a>.
			</Message>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button type="submit" :form="formId" label="Save" icon="pi pi-check" :loading="busy" :disabled="loading || !plan.supported" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import { computed, reactive, ref, useId, watch } from "vue"

import { createDoc, getMeta } from "../../api/frappe.js"
import { deskDocumentPath } from "../../utils/linkTarget.js"
import { quickEntryPlan } from "../../utils/quickEntry.js"
import FormField from "./FormField.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, required: true },
	presets: { type: Object, default: () => ({}) },
	query: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "created"])

const formId = `quick-entry-${useId()}`
const plan = ref({ supported: true, fields: [], locked: [], values: {} })
const values = reactive({})
const meta = ref(null)
const loading = ref(false)
const busy = ref(false)
const error = ref("")
const deskNewPath = computed(() => deskDocumentPath(props.doctype, "new"))

async function load() {
	loading.value = true
	error.value = ""
	for (const key of Object.keys(values)) delete values[key]
	try {
		meta.value = (await getMeta(props.doctype)).find((doc) => doc.name === props.doctype)
		plan.value = quickEntryPlan(meta.value, props.presets, props.query)
		Object.assign(values, plan.value.values)
	} catch (failure) {
		error.value = failure.message
	} finally {
		loading.value = false
	}
}

watch(() => props.visible, (visible) => { if (visible) load() }, { immediate: true })

async function submit() {
	const missing = plan.value.fields.find((field) => field.reqd && (values[field.fieldname] ?? "") === "")
	if (missing) {
		error.value = `${missing.label || missing.fieldname} is required.`
		return
	}
	busy.value = true
	error.value = ""
	try {
		const doc = await createDoc(props.doctype, { ...values })
		emit("created", { doc, label: doc?.[meta.value?.title_field] || doc?.name })
		emit("update:visible", false)
	} catch (failure) {
		error.value = failure.message
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.quick-entry-dialog__form { display: grid; gap: var(--erp-space-3, 12px); }
</style>
