<template>
	<section class="supplier-notification-panel" :aria-label="`Send ${channelLabel}`">
		<header>
			<div><span>Supplier notification</span><h2>Send {{ channelLabel }}</h2></div>
			<Button icon="pi pi-times" severity="secondary" text rounded aria-label="Close notification" :disabled="Boolean(acting)" @click="emit('close')" />
		</header>

		<div class="supplier-notification-panel__recipient">
			<div><span>Supplier</span><strong>{{ context.supplier || "—" }}</strong></div>
			<label><span>Send to *</span><Select v-model="mobileNo" :options="numberOptions" editable fluid :disabled="Boolean(acting)" /></label>
			<label><span>Template *</span><Select v-model="templateKey" :options="templateOptions" option-label="label" option-value="value" fluid :disabled="Boolean(acting)" @update:model-value="resetVariables" /></label>
		</div>

		<section class="supplier-notification-panel__variables">
			<header><span>Template inputs</span><strong>{{ variableRows.length }}</strong></header>
			<div v-if="variableRows.length" class="supplier-notification-panel__variable-list">
				<div v-for="variable in variableRows" :key="variable.key" class="supplier-notification-panel__variable">
					<code>{{ variable.label }}</code>
					<label><span>Map to field</span><Select v-model="variable.fieldname" :options="fieldOptions" option-label="label" option-value="value" show-clear fluid :disabled="Boolean(acting)" /></label>
					<label><span>Manual value</span><InputText v-model="variable.manual" fluid :disabled="Boolean(acting) || Boolean(variable.fieldname)" /></label>
				</div>
			</div>
			<p v-else>This template has no inputs.</p>
		</section>

		<label v-if="selectedTemplate?.needs_media" class="supplier-notification-panel__media">
			<span>{{ selectedTemplate.header_type || "Media" }} header File URL *</span>
			<InputText v-model="headerFile" placeholder="/private/files/example.jpg" fluid :disabled="Boolean(acting)" />
			<small>Select an uploaded File URL that you can read.</small>
		</label>

		<section v-if="channel === 'whatsapp' && selectedTemplate" class="supplier-notification-panel__preview">
			<span>Preview</span><div><p>{{ renderedBody }}</p><small v-if="selectedTemplate.footer_text">{{ selectedTemplate.footer_text }}</small></div>
		</section>

		<footer>
			<Button label="Close" severity="secondary" text :disabled="Boolean(acting)" @click="emit('close')" />
			<Button :label="`Send ${channelLabel}`" :icon="channel === 'sms' ? 'pi pi-envelope' : 'pi pi-comments'" :loading="acting === `send_${channel}`" :disabled="!canSend" @click="send" />
		</footer>
	</section>
	<DocumentErrorDialog :message="error" :title="`${channelLabel} could not be sent`" />
</template>

<script setup>
import Button from "primevue/button"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"

import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	preparation: { type: Object, required: true },
	documentValues: { type: Object, default: () => ({}) },
	acting: { type: String, default: "" },
	error: { type: String, default: "" },
})
const emit = defineEmits(["send", "close"])

const mobileNo = ref("")
const templateKey = ref("")
const headerFile = ref("")
const variableRows = ref([])
const channel = computed(() => props.preparation.channel === "whatsapp" ? "whatsapp" : "sms")
const channelLabel = computed(() => channel.value === "whatsapp" ? "WhatsApp" : "SMS")
const context = computed(() => props.preparation.context || {})
const numberOptions = computed(() => context.value.numbers?.length ? context.value.numbers : [context.value.mobile].filter(Boolean))
const templateOptions = computed(() => (context.value.templates || []).map((template) => ({
	value: template.name,
	label: template.template_name || template.name,
})))
const selectedTemplate = computed(() => (context.value.templates || []).find((template) => template.name === templateKey.value) || null)
const fieldOptions = computed(() => context.value.doc_fields || [])
const canSend = computed(() => Boolean(
	!props.acting
	&& mobileNo.value
	&& selectedTemplate.value
	&& (!selectedTemplate.value.needs_media || headerFile.value),
))
const renderedBody = computed(() => {
	let body = String(selectedTemplate.value?.body_text || "")
	for (const variable of variableRows.value) {
		if (!variable.key.startsWith("body:")) continue
		body = body.replace(new RegExp(`\\{\\{\\s*${variable.key.split(":")[1]}\\s*\\}\\}`, "g"), variableValue(variable) || `{{${variable.key.split(":")[1]}}}`)
	}
	return body
})

watch(() => props.preparation, initialize, { immediate: true })

function initialize() {
	mobileNo.value = numberOptions.value[0] || ""
	templateKey.value = templateOptions.value[0]?.value || ""
	headerFile.value = ""
	resetVariables()
}
function resetVariables() {
	const fields = new Set(fieldOptions.value.map((field) => field.value))
	variableRows.value = (selectedTemplate.value?.variables || []).map((variable) => {
		const number = String(variable.name || "").replace(/[^0-9]/g, "")
		const key = channel.value === "whatsapp" ? `${variable.type || "body"}:${number}` : variable.name
		return {
			key,
			label: channel.value === "whatsapp" ? `${variable.name} (${variable.type || "body"})` : variable.name,
			fieldname: channel.value === "sms" && fields.has(variable.name) ? variable.name : "",
			manual: channel.value === "sms" && fields.has(variable.name) ? "" : String(variable.value ?? ""),
		}
	})
	if (!selectedTemplate.value?.needs_media) headerFile.value = ""
}
function variableValue(variable) {
	const value = variable.fieldname ? props.documentValues?.[variable.fieldname] : variable.manual
	return value === null || value === undefined ? "" : String(value)
}
function send() {
	const template = selectedTemplate.value
	const payload = {
		template_name: channel.value === "whatsapp" ? template.template_name : template.name,
		mobile_no: mobileNo.value,
		params: Object.fromEntries(variableRows.value.map((variable) => [variable.key, variableValue(variable)])),
	}
	if (channel.value === "whatsapp") {
		payload.language_code = template.language_code
		payload.header_file = headerFile.value || null
	}
	emit("send", { channel: channel.value, payload })
}
</script>

<style scoped>
.supplier-notification-panel { display: grid; overflow: hidden; gap: var(--erp-space-3); border: 1px solid color-mix(in srgb, var(--erp-accent) 20%, var(--erp-border)); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.supplier-notification-panel > header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); border-left: 3px solid var(--erp-accent); background: color-mix(in srgb, var(--erp-accent-soft) 72%, white); }
.supplier-notification-panel > header > div { display: grid; gap: 2px; }
.supplier-notification-panel > header span, .supplier-notification-panel__recipient span, .supplier-notification-panel__variable label span, .supplier-notification-panel__media > span, .supplier-notification-panel__preview > span, .supplier-notification-panel__variables > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; letter-spacing: .035em; text-transform: uppercase; }
.supplier-notification-panel > header h2 { margin: 0; font-size: var(--erp-font-size-section); }
.supplier-notification-panel > :not(header, footer) { margin-right: var(--erp-space-3); margin-left: var(--erp-space-3); }
.supplier-notification-panel__recipient { display: grid; grid-template-columns: minmax(180px, .8fr) repeat(2, minmax(220px, 1fr)); gap: var(--erp-space-3); }
.supplier-notification-panel__recipient > div, .supplier-notification-panel label { display: grid; align-content: start; gap: 6px; }
.supplier-notification-panel__recipient > div { padding: 7px 0; }
.supplier-notification-panel__variables { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.supplier-notification-panel__variables > header { display: flex; justify-content: space-between; padding: 8px 10px; background: var(--erp-surface-soft); }
.supplier-notification-panel__variable-list { display: grid; }
.supplier-notification-panel__variable { display: grid; grid-template-columns: minmax(130px, .6fr) repeat(2, minmax(200px, 1fr)); align-items: end; gap: 10px; padding: 9px 10px; border-top: 1px solid var(--erp-border); }
.supplier-notification-panel__variable:first-child { border-top: 0; }
.supplier-notification-panel__variable code { align-self: center; color: var(--erp-accent-hover); }
.supplier-notification-panel__variables > p { margin: 0; padding: 12px; color: var(--erp-text-muted); }
.supplier-notification-panel__media small { color: var(--erp-text-muted); }
.supplier-notification-panel__preview { display: grid; gap: 6px; }
.supplier-notification-panel__preview > div { max-width: 680px; padding: 11px 13px; color: var(--erp-text); border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, var(--erp-border)); border-radius: var(--erp-control-radius); background: color-mix(in srgb, var(--erp-accent-soft) 76%, white); }
.supplier-notification-panel__preview p { margin: 0; white-space: pre-wrap; }
.supplier-notification-panel__preview small { display: block; margin-top: 6px; color: #52665a; }
.supplier-notification-panel > footer { display: flex; justify-content: flex-end; gap: 8px; padding: 0 var(--erp-space-3) var(--erp-space-3); }
@media (max-width: 800px) { .supplier-notification-panel__recipient, .supplier-notification-panel__variable { grid-template-columns: 1fr; } }
</style>
