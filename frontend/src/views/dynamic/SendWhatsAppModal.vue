<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		class="wa-dialog"
		:header="header"
		:position="dialogPosition"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		@show="loadContext"
	>
		<div v-if="loading" class="wa-loading">
			<i class="pi pi-spin pi-spinner" /> Loading WhatsApp context…
		</div>

		<div v-else-if="!ctx" class="esd-empty">
			<i class="pi pi-info-circle" />
			<p class="esd-empty__text">Couldn't load the WhatsApp context for this document.</p>
		</div>

		<div v-else class="wa-body">
			<!-- who we're messaging -->
			<div class="wa-recipient">
				<span>Supplier: <b>{{ ctx.supplier }}</b></span>
				<span v-if="ctx.contact"> · Contact: {{ ctx.contact }}</span>
			</div>

			<!-- (1) mobile: pick a contact number OR type one (editable) -->
			<div class="wa-field">
				<label class="field-label">Send to *</label>
				<Select
					v-model="mobileNo"
					editable
					:options="numberOptions"
					fluid
					placeholder="Pick or type a number"
				/>
				<small class="wa-hint">Pick a number above or type/edit one.</small>
			</div>

			<!-- (2) template: APPROVED WhatsApp template configured for this doctype -->
			<div class="wa-field">
				<label class="field-label">Template *</label>
				<Select
					v-model="templateKey"
					:options="templateOptions"
					optionLabel="displayLabel"
					optionValue="name"
					fluid
					placeholder="Select a template"
				/>
			</div>

			<!-- read-only body so the user sees where each placeholder lands -->
			<div v-if="selectedTemplate && selectedTemplate.body_text" class="wa-preview">
				{{ selectedTemplate.body_text }}
				<div v-if="selectedTemplate.footer_text" class="wa-preview__footer">
					{{ selectedTemplate.footer_text }}
				</div>
			</div>

			<!-- (3) header media upload — only when the template's header needs it -->
			<div v-if="needsMedia" class="wa-field">
				<label class="field-label">Header Media *</label>
				<input
					type="file"
					accept="image/*,application/pdf"
					:disabled="uploading"
					@change="onHeaderFileChange"
				/>
				<small v-if="uploading" class="wa-hint">
					<i class="pi pi-spin pi-spinner" /> Uploading…
				</small>
				<small v-else-if="headerFileUrl" class="wa-hint">Uploaded: {{ headerFileName }}</small>
				<small v-else class="wa-hint">Required for this template (image or PDF).</small>
			</div>

			<!-- (4) one row per template variable: name · map-to-field · manual value -->
			<div v-if="variables.length" class="wa-vars">
				<div class="wa-vars__label">Template Inputs</div>
				<div class="wa-vars__head">
					<span>Template Input</span>
					<span>Map to Field</span>
					<span>Manual Value</span>
				</div>
				<div v-for="(v, i) in variables" :key="i" class="wa-var-row">
					<code class="wa-var-name">{{ v.name }}</code>
					<Select
						v-model="varStates[i].field"
						:options="fieldOptions"
						optionLabel="label"
						optionValue="value"
						filter
						fluid
						placeholder="— manual —"
					/>
					<InputText
						v-model="varStates[i].manual"
						fluid
						placeholder="Manual value"
					/>
				</div>
			</div>
			<div v-else-if="selectedTemplate" class="wa-hint wa-novars">
				This template has no inputs.
			</div>
		</div>

		<template #footer>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="sending"
				@click="dialogVisible = false"
			/>
			<Button
				label="Send"
				icon="pi pi-whatsapp"
				:loading="sending"
				:disabled="loading || !ctx || !templateKey || uploading || (needsMedia && !headerFileUrl)"
				@click="onSend"
			/>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Send WhatsApp — /web port of the Send SMS dialog (SendSmsModal.vue), backed
 * by yrp.whatsapp_notification instead of yrp.notification.
 *
 * @show loads the WhatsApp context (numbers, APPROVED templates pre-filtered
 * to this doctype, per-template {{n}} variables, and the doc's mappable
 * fields). For each variable the user either maps a document field OR types a
 * manual value; the value sent is the manual value when non-empty, else the
 * mapped field's live value — same contract as SendSmsModal.
 *
 * Templates carry BOTH a docname (`name`, used as the Select's unique key)
 * and Meta's own identifying pair (`template_name` + `language_code`, which is
 * what the server needs to actually send). `params` is posted as a JSON
 * string keyed `"body:n"` / `"header:n"` (a FLAT map, same parse_json contract
 * as the SMS `params`). Media templates (`needs_media`) additionally require a
 * `header_file` — a File uploaded via the new `uploadFile` helper — before Send
 * is enabled.
 */
import { computed, ref, watch } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputText from "primevue/inputtext"
import Button from "primevue/button"
import { callMethod, uploadFile } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	docname: { type: String, default: "" },
	doc: { type: Object, default: () => ({}) },
	// Which link field on the doc names the supplier to message. DC/GRN/PO use
	// the default "supplier"; Stock Entry passes "to_supplier"/"from_supplier".
	supplierKey: { type: String, default: "supplier" },
	// actions.dialogPosition (item 9) — PrimeVue Dialog `position`. Default
	// "center" = PrimeVue's own default, so absent-knob renders identically.
	dialogPosition: { type: String, default: "center" },
})
const emit = defineEmits(["update:visible", "sent"])

const toast = useAppToast()

const dialogVisible = computed({
	get: () => props.visible,
	set: (v) => emit("update:visible", v),
})

const loading = ref(false)
const sending = ref(false)
const uploading = ref(false)
const ctx = ref(null)
const mobileNo = ref("")
// Selected template's docname (Select's unique key — see selectedTemplate).
const templateKey = ref("")
// One state per selected-template variable, aligned to variables[]: { field, manual }.
const varStates = ref([])
const headerFileUrl = ref("")
const headerFileName = ref("")

const header = computed(() =>
	ctx.value?.supplier ? `Send WhatsApp to ${ctx.value.supplier}` : "Send WhatsApp",
)

// Contact numbers, primary first; fall back to the single primary mobile.
const numberOptions = computed(() => {
	const nums = ctx.value?.numbers || []
	if (nums.length) return nums
	return ctx.value?.mobile ? [ctx.value.mobile] : []
})

// Templates can share a template_name across languages — disambiguate the
// dropdown label with the language code.
const templateOptions = computed(() =>
	(ctx.value?.templates || []).map((t) => ({
		...t,
		displayLabel: t.language_code ? `${t.template_name} (${t.language_code})` : t.template_name,
	})),
)

const selectedTemplate = computed(
	() => (ctx.value?.templates || []).find((t) => t.name === templateKey.value) || null,
)
const variables = computed(() => selectedTemplate.value?.variables || [])
const needsMedia = computed(() => !!selectedTemplate.value?.needs_media)

// "Map to field" options: an explicit "— manual —" (null) choice, then every
// mappable document field (value = fieldname, label = "Label (fieldname)").
const fieldOptions = computed(() => [
	{ value: null, label: "— manual —" },
	...(ctx.value?.doc_fields || []),
])

async function loadContext() {
	loading.value = true
	ctx.value = null
	mobileNo.value = ""
	templateKey.value = ""
	varStates.value = []
	headerFileUrl.value = ""
	headerFileName.value = ""
	uploading.value = false
	try {
		const r = await callMethod("yrp.whatsapp_notification.get_whatsapp_context", {
			doctype: props.doctype,
			docname: props.docname,
			supplier_key: props.supplierKey,
		})
		ctx.value = r || null
		if (!ctx.value || !(ctx.value.templates || []).length) {
			toast.warn("No WhatsApp template", `No WhatsApp template is configured for ${props.doctype}.`)
			dialogVisible.value = false
			return
		}
		mobileNo.value = numberOptions.value[0] || ""
		templateKey.value = ctx.value.templates[0].name
		initVarStates()
	} catch (e) {
		toast.error("Couldn't load WhatsApp context", e.message)
		dialogVisible.value = false
	} finally {
		loading.value = false
	}
}

// Rebuild the per-variable inputs for the selected template. Mirrors the SMS
// dialog: a variable whose token matches a document field is pre-mapped to
// that field (manual left blank so the LIVE field value is used); otherwise
// the server-resolved value pre-fills the manual box.
function initVarStates() {
	const fieldValues = new Set((ctx.value?.doc_fields || []).map((f) => f.value))
	varStates.value = variables.value.map((v) => {
		const autoMapped = fieldValues.has(v.name)
		return {
			field: autoMapped ? v.name : null,
			manual: autoMapped ? "" : v.value != null ? String(v.value) : "",
		}
	})
}

// Picking a different template re-renders its variable rows (and clears any
// in-flight header upload, since a new template may not need media, or need
// a different kind), discarding edits for the previous template.
watch(templateKey, () => {
	if (ctx.value) initVarStates()
	headerFileUrl.value = ""
	headerFileName.value = ""
})

// Value sent for variable i: the manual value if non-empty, else the mapped
// document field's value (falls back to the server-resolved value when the
// loaded doc doesn't carry that field). Empty when nothing resolves.
function computedValue(i) {
	const st = varStates.value[i]
	if (!st) return ""
	const manual = st.manual == null ? "" : String(st.manual)
	if (manual !== "") return manual
	if (st.field) {
		if (props.doc && Object.prototype.hasOwnProperty.call(props.doc, st.field)) {
			const v = props.doc[st.field]
			return v == null ? "" : v
		}
		const v = variables.value[i]?.value
		return v == null ? "" : v
	}
	return ""
}

// The server posts `params` as a flat map keyed "body:n" / "header:n" — derive
// the key from the variable's {{n}} token and its "body"|"header" type.
function paramKey(v) {
	const num = String(v?.name || "").replace(/[^0-9]/g, "") || "1"
	return `${v?.type || "body"}:${num}`
}

async function onHeaderFileChange(e) {
	const file = e.target?.files && e.target.files[0]
	if (!file) return
	headerFileUrl.value = ""
	headerFileName.value = file.name
	uploading.value = true
	try {
		headerFileUrl.value = await uploadFile(file)
	} catch (err) {
		toast.error("Upload failed", err.message)
		headerFileUrl.value = ""
		headerFileName.value = ""
	} finally {
		uploading.value = false
	}
}

async function onSend() {
	const number = String(mobileNo.value || "").trim()
	if (!number) {
		toast.warn("Number required", "Pick or type a mobile number to send to.")
		return
	}
	if (!templateKey.value || !selectedTemplate.value) {
		toast.warn("Template required", "Select a WhatsApp template to send.")
		return
	}
	if (needsMedia.value && !headerFileUrl.value) {
		toast.warn("Media required", "Upload the header image/PDF for this template.")
		return
	}
	// params: "type:n" token -> resolved value (JSON string; server parse_json's it).
	const params = {}
	variables.value.forEach((v, i) => {
		params[paramKey(v)] = computedValue(i)
	})
	sending.value = true
	try {
		const args = {
			doctype: props.doctype,
			docname: props.docname,
			supplier_key: props.supplierKey,
			template_name: selectedTemplate.value.template_name,
			language_code: selectedTemplate.value.language_code,
			mobile_no: number,
			params: JSON.stringify(params),
		}
		if (needsMedia.value && headerFileUrl.value) args.header_file = headerFileUrl.value
		const res = await callMethod("yrp.whatsapp_notification.send_whatsapp_notification", args)
		// The backend never throws on a gateway failure — it returns the result
		// dict. Gate success on res.ok; keep the dialog open otherwise so the
		// user can fix the number/template/media and retry.
		if (!res || !res.ok) {
			toast.error("WhatsApp failed", (res && (res.error || res.http_status)) || "Gateway error")
			return
		}
		toast.success(
			"WhatsApp sent",
			`WhatsApp sent to ${number}.${res.request_id ? ` (id ${res.request_id})` : ""}`,
		)
		emit("sent", res)
		dialogVisible.value = false
	} catch (e) {
		toast.error("WhatsApp failed", e.message)
	} finally {
		sending.value = false
	}
}
</script>

<style scoped>
.wa-loading {
	display: flex;
	align-items: center;
	gap: 8px;
	color: var(--esd-muted);
	padding: 16px 4px;
}
.wa-body {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.wa-recipient {
	font-size: 12.5px;
	color: var(--esd-muted);
}
.wa-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.wa-hint {
	color: var(--esd-muted);
	font-size: 11.5px;
}
.wa-preview {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	padding: 8px 10px;
	font-size: 12.5px;
	color: var(--esd-muted);
	white-space: pre-wrap;
	word-break: break-word;
}
.wa-preview__footer {
	margin-top: 6px;
	padding-top: 6px;
	border-top: 1px dashed var(--esd-line);
	font-size: 11px;
	opacity: 0.85;
}
.wa-vars {
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.wa-vars__label {
	font-weight: 600;
	font-size: 12.5px;
}
.wa-vars__head,
.wa-var-row {
	display: grid;
	grid-template-columns: minmax(110px, 0.9fr) minmax(0, 1.3fr) minmax(0, 1.3fr);
	gap: 8px;
	align-items: center;
}
.wa-vars__head {
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.03em;
	color: var(--esd-muted);
	padding-bottom: 3px;
	border-bottom: 1px solid var(--esd-line);
}
.wa-var-name {
	font-size: 12px;
	word-break: break-word;
}
.wa-novars {
	padding: 4px 0;
}

/* Stack the three columns on narrow screens; label each input inline. */
@media (max-width: 480px) {
	.wa-vars__head {
		display: none;
	}
	.wa-var-row {
		grid-template-columns: 1fr;
		gap: 4px;
		padding: 8px 0;
		border-bottom: 1px solid var(--esd-line);
	}
	.wa-var-name {
		font-weight: 600;
	}
}
</style>
