<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		class="sms-dialog"
		:header="header"
		:position="dialogPosition"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		@show="loadContext"
	>
		<div v-if="loading" class="sms-loading">
			<i class="pi pi-spin pi-spinner" /> Loading SMS context…
		</div>

		<div v-else-if="!ctx" class="esd-empty">
			<i class="pi pi-info-circle" />
			<p class="esd-empty__text">Couldn't load the SMS context for this document.</p>
		</div>

		<div v-else class="sms-body">
			<!-- who we're texting -->
			<div class="sms-recipient">
				<span>Supplier: <b>{{ ctx.supplier }}</b></span>
			</div>

			<!-- (1) mobile: pick a contact number OR type one (editable) -->
			<div class="sms-field">
				<label class="field-label">Send to *</label>
				<Select
					v-model="mobileNo"
					editable
					:options="numberOptions"
					fluid
					placeholder="Pick or type a number"
				/>
			</div>

			<!-- (2) template: MSG91 Flow template configured in YRP SMS Settings -->
			<div class="sms-field">
				<label class="field-label">Template *</label>
				<Select
					v-model="templateName"
					:options="ctx.templates"
					optionLabel="name"
					optionValue="name"
					fluid
					placeholder="Select a template"
				/>
			</div>

			<!-- read-only body so the user sees where each placeholder lands -->
			<div v-if="selectedTemplate && selectedTemplate.body" class="sms-preview">
				{{ selectedTemplate.body }}
			</div>

			<!-- (3) one row per template variable: name · map-to-field · manual value -->
			<div v-if="variables.length" class="sms-vars">
				<div class="sms-vars__label">Template Inputs</div>
				<div class="sms-vars__head">
					<span>Template Input</span>
					<span>Map to Field</span>
					<span>Manual Value</span>
				</div>
				<div v-for="(v, i) in variables" :key="i" class="sms-var-row">
					<code class="sms-var-name">{{ v.name }}</code>
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
				icon="pi pi-send"
				:loading="sending"
				:disabled="loading || !ctx || !templateName"
				@click="onSend"
			/>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Send SMS — /web port of the Desk dialog in
 * essdee_yrp/public/js/supplier_notification.js (open_send_sms_dialog +
 * _render_sms_vars), backed by yrp.notification.
 *
 * @show loads the MSG91 Flow context (numbers, templates, per-template
 * {placeholder} variables, and the doc's mappable fields). For each variable the
 * user either maps a document field OR types a manual value; the value sent is
 * the manual value when non-empty, else the mapped field's live value.
 * `params` is posted as a JSON string because the server parse_json's it (same
 * contract as FabricDeliverablesModal's `rows` and the e-Waybill `values`).
 */
import { computed, ref, watch } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputText from "primevue/inputtext"
import Button from "primevue/button"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	docname: { type: String, default: "" },
	doc: { type: Object, default: () => ({}) },
	// Which link field on the doc names the supplier to text. DC/GRN/PO use the
	// default "supplier"; Stock Entry passes "to_supplier"/"from_supplier".
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
const ctx = ref(null)
const mobileNo = ref("")
const templateName = ref("")
// One state per selected-template variable, aligned to variables[]: { field, manual }.
const varStates = ref([])

const header = computed(() =>
	ctx.value?.supplier ? `Send SMS to ${ctx.value.supplier}` : "Send SMS",
)

// Contact numbers, primary first; fall back to the single primary mobile.
const numberOptions = computed(() => {
	const nums = ctx.value?.numbers || []
	if (nums.length) return nums
	return ctx.value?.mobile ? [ctx.value.mobile] : []
})

const selectedTemplate = computed(
	() => (ctx.value?.templates || []).find((t) => t.name === templateName.value) || null,
)
const variables = computed(() => selectedTemplate.value?.variables || [])

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
	templateName.value = ""
	varStates.value = []
	try {
		const r = await callMethod("yrp.notification.get_flow_sms_context", {
			doctype: props.doctype,
			docname: props.docname,
			supplier_key: props.supplierKey,
		})
		ctx.value = r || null
		if (!ctx.value || !(ctx.value.templates || []).length) {
			toast.warn("No SMS template", `No SMS template is configured for ${props.doctype}.`)
			dialogVisible.value = false
			return
		}
		mobileNo.value = numberOptions.value[0] || ""
		templateName.value = ctx.value.templates[0].name
		initVarStates()
	} catch (e) {
		toast.error("Couldn't load SMS context", e.message)
		dialogVisible.value = false
	} finally {
		loading.value = false
	}
}

// Rebuild the per-variable inputs for the selected template. Mirrors the Desk
// dialog: a variable whose token matches a document field is pre-mapped to that
// field (manual left blank so the LIVE field value is used); otherwise the
// server-resolved value pre-fills the manual box.
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

// Picking a different template re-renders its variable rows (Desk parity), which
// discards any edits for the previous template.
watch(templateName, () => {
	if (ctx.value) initVarStates()
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

async function onSend() {
	const number = String(mobileNo.value || "").trim()
	if (!number) {
		toast.warn("Number required", "Pick or type a mobile number to send to.")
		return
	}
	if (!templateName.value) {
		toast.warn("Template required", "Select an SMS template to send.")
		return
	}
	// params: placeholder token -> resolved value (JSON string; server parse_json's it).
	const params = {}
	variables.value.forEach((v, i) => {
		params[v.name] = computedValue(i)
	})
	sending.value = true
	try {
		const res = await callMethod("yrp.notification.send_flow_sms_notification", {
			doctype: props.doctype,
			docname: props.docname,
			template_name: templateName.value,
			mobile_no: number,
			params: JSON.stringify(params),
			supplier_key: props.supplierKey,
		})
		// The backend never throws on a gateway failure — it returns the result
		// dict. Gate success on res.ok; keep the dialog open otherwise so the
		// user can fix the number/template and retry.
		if (!res || !res.ok) {
			toast.error("SMS failed", (res && (res.error || res.http_status)) || "Gateway error")
			return
		}
		toast.success(
			"SMS sent",
			`SMS sent to ${number}.${res.request_id ? ` (id ${res.request_id})` : ""}`,
		)
		emit("sent", res)
		dialogVisible.value = false
	} catch (e) {
		toast.error("SMS failed", e.message)
	} finally {
		sending.value = false
	}
}
</script>

<style scoped>
.sms-loading {
	display: flex;
	align-items: center;
	gap: 8px;
	color: var(--esd-muted);
	padding: 16px 4px;
}
.sms-body {
	display: flex;
	flex-direction: column;
	gap: 14px;
}
.sms-recipient {
	font-size: 12.5px;
	color: var(--esd-muted);
}
.sms-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.sms-hint {
	color: var(--esd-muted);
	font-size: 11.5px;
}
.sms-preview {
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	padding: 8px 10px;
	font-size: 12.5px;
	color: var(--esd-muted);
	white-space: pre-wrap;
	word-break: break-word;
}
.sms-vars {
	display: flex;
	flex-direction: column;
	gap: 6px;
}
.sms-vars__label {
	font-weight: 600;
	font-size: 12.5px;
}
.sms-vars__head,
.sms-var-row {
	display: grid;
	grid-template-columns: minmax(110px, 0.9fr) minmax(0, 1.3fr) minmax(0, 1.3fr);
	gap: 8px;
	align-items: center;
}
.sms-vars__head {
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.03em;
	color: var(--esd-muted);
	padding-bottom: 3px;
	border-bottom: 1px solid var(--esd-line);
}
.sms-var-name {
	font-size: 12px;
	word-break: break-word;
}
.sms-novars {
	padding: 4px 0;
}

/* Stack the three columns on narrow screens; label each input inline. */
@media (max-width: 480px) {
	.sms-vars__head {
		display: none;
	}
	.sms-var-row {
		grid-template-columns: 1fr;
		gap: 4px;
		padding: 8px 0;
		border-bottom: 1px solid var(--esd-line);
	}
	.sms-var-name {
		font-weight: 600;
	}
}
</style>
