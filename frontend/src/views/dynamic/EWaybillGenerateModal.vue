<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		class="ewb-gen-dialog"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		header="Generate e-Waybill"
		@show="initForm"
	>
		<!-- Part A ---------------------------------------------------------->
		<section class="ewb-section">
			<h4 class="ewb-section__title">Part A</h4>

			<div class="ewb-field">
				<label class="field-label">Transporter</label>
				<LinkField
					v-model="form.transporter"
					target-doctype="Supplier"
					:filters="{ is_transporter: 1 }"
					placeholder="Search Transporter…"
					@item-select="onTransporterSelect"
				/>
			</div>

			<div class="ewb-field">
				<label class="field-label">Distance (in km)</label>
				<InputNumber
					v-model="form.distance"
					:min="0"
					:maxFractionDigits="0"
					:useGrouping="false"
					fluid
					placeholder="0"
				/>
				<small class="ewb-note">
					Set as zero to let the e-Waybill portal auto-calculate the distance (if available).
				</small>
			</div>

			<div class="ewb-field">
				<label class="field-label">GST Transporter ID</label>
				<InputText v-model="form.gst_transporter_id" fluid placeholder="GST Transporter ID" />
			</div>

			<!-- The form field is read-only (popup-driven, 2026-07-10) — this
			     dialog is the only writer. Drives the CGST/SGST vs IGST split
			     server-side (SEZ / Overseas / Unregistered parties). -->
			<div class="ewb-field">
				<label class="field-label">GST Category</label>
				<Select
					v-model="form.gst_category"
					:options="GST_CATEGORY_OPTIONS"
					fluid
					placeholder="Select GST Category"
				/>
			</div>
		</section>

		<!-- Part B ---------------------------------------------------------->
		<section class="ewb-section">
			<h4 class="ewb-section__title">Part B</h4>

			<div class="ewb-field">
				<label class="field-label">Vehicle No</label>
				<InputText v-model="form.vehicle_no" fluid placeholder="Vehicle No" />
			</div>

			<div class="ewb-field">
				<label class="field-label">Transport Receipt No</label>
				<InputText v-model="form.lr_no" fluid placeholder="Transport Receipt No" />
			</div>

			<div class="ewb-field">
				<label class="field-label">
					Transport Receipt Date
					<span v-if="form.lr_no" class="ewb-reqd">*</span>
				</label>
				<DatePicker
					v-model="form.lr_date"
					dateFormat="yy-mm-dd"
					showIcon
					fluid
					placeholder="Select Date"
				/>
			</div>

			<div class="ewb-field">
				<label class="field-label">Mode Of Transport</label>
				<Select
					v-model="form.mode_of_transport"
					:options="MODE_OPTIONS"
					fluid
					placeholder="Select Mode"
					@change="onModeChange"
				/>
			</div>

			<div v-if="showVehicleType" class="ewb-field">
				<label class="field-label">GST Vehicle Type</label>
				<Select
					v-model="form.gst_vehicle_type"
					:options="VEHICLE_TYPE_OPTIONS"
					:disabled="form.mode_of_transport === 'Ship'"
					fluid
					placeholder="Select Vehicle Type"
				/>
			</div>
		</section>

		<template #footer>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="generating"
				@click="dialogVisible = false"
			/>
			<Button
				:label="generateLabel"
				icon="pi pi-file-export"
				:loading="generating"
				@click="onGenerate"
			/>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Generate e-Waybill — /web port of the Desk dialog `show_generate_dialog`
 * in yrp_ewaybill_api/public/js/ewaybill_actions.js. Field set, labels, option
 * lists and defaults mirror the Desk dialog exactly (Part A / Part B), including
 * the transporter → GST Transporter ID auto-fill and the dynamic primary-action
 * label ("Generate" vs "Generate (Part A)").
 *
 * Backend: yrp_ewaybill_api.ewaybill.actions.generate_e_waybill(doctype, docname,
 * values). `values` is passed as a plain object (dict) — the server's
 * `_parse_values` accepts a dict directly, exactly like the Desk's frappe.call.
 * generate_e_waybill does NOT throw on a GSP failure: it returns a dict, so this
 * is treated as success ONLY when the returned `.ewaybill` is truthy.
 */
import { computed, reactive, ref } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputText from "primevue/inputtext"
import InputNumber from "primevue/inputnumber"
import DatePicker from "primevue/datepicker"
import Button from "primevue/button"
import LinkField from "@/components/LinkField.vue"
import { callMethod, getDoc } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	docname: { type: String, default: "" },
	// The loaded Delivery Challan — used for the dialog's field defaults.
	doc: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "generated"])

const toast = useAppToast()
const generating = ref(false)

// Option lists mirror the Desk dialog exactly.
const MODE_OPTIONS = ["Road", "Air", "Rail", "Ship"]
const VEHICLE_TYPE_OPTIONS = ["Regular", "Over Dimensional Cargo (ODC)"]
const GST_CATEGORY_OPTIONS = ["Registered Regular", "Unregistered", "SEZ", "Overseas"]

const form = reactive({
	transporter: "",
	distance: 0,
	gst_transporter_id: "",
	vehicle_no: "",
	lr_no: "",
	lr_date: null,
	mode_of_transport: "Road",
	gst_vehicle_type: "Regular",
	gst_category: "Registered Regular",
})

const dialogVisible = computed({
	get: () => props.visible,
	set: (v) => emit("update:visible", v),
})

// Prime every field from the loaded doc on @show (Desk: `default: doc.<field>`).
function initForm() {
	const doc = props.doc || {}
	form.transporter = doc.transporter || ""
	form.distance = doc.distance || 0
	form.gst_transporter_id = doc.gst_transporter_id || ""
	form.vehicle_no = doc.vehicle_no || ""
	form.lr_no = doc.lr_no || ""
	// Desk default: `doc.lr_date || "Today"`.
	form.lr_date = doc.lr_date ? new Date(doc.lr_date) : new Date()
	form.mode_of_transport = doc.mode_of_transport || "Road"
	form.gst_vehicle_type = doc.gst_vehicle_type || "Regular"
	form.gst_category = doc.gst_category || "Registered Regular"
}

// GST Vehicle Type shows only for Road / Ship (Desk: depends_on Road|Ship).
const showVehicleType = computed(() =>
	["Road", "Ship"].includes(form.mode_of_transport),
)

// Desk `get_vehicle_type`: Road → Regular, Ship → ODC, otherwise blank.
function getVehicleType(mode) {
	if (mode === "Road") return "Regular"
	if (mode === "Ship") return "Over Dimensional Cargo (ODC)"
	return ""
}
function onModeChange() {
	form.gst_vehicle_type = getVehicleType(form.mode_of_transport)
}

// Part-B transport details "available" → full "Generate"; else "Generate (Part A)".
// Mirrors Desk `transport_details_available` / `get_generate_label`.
function transportDetailsAvailable(f) {
	return !!(
		(f.mode_of_transport === "Road" && f.vehicle_no) ||
		(["Air", "Rail"].includes(f.mode_of_transport) && f.lr_no) ||
		(f.mode_of_transport === "Ship" && f.lr_no && f.vehicle_no)
	)
}
const generateLabel = computed(() =>
	transportDetailsAvailable(form) ? "Generate" : "Generate (Part A)",
)

// On transporter select, auto-fill GST Transporter ID from the chosen Supplier
// (Desk: frappe.db.get_value("Supplier", …, "gst_transporter_id")).
async function onTransporterSelect(e) {
	const name = e?.value || form.transporter
	if (!name) return
	try {
		const supplier = await getDoc("Supplier", name)
		if (supplier?.gst_transporter_id) {
			form.gst_transporter_id = supplier.gst_transporter_id
		}
	} catch (_) {
		// Non-fatal: the user can still type the GST Transporter ID by hand.
	}
}

function toDateStr(value) {
	if (!value) return ""
	const dt = value instanceof Date ? value : new Date(value)
	if (Number.isNaN(dt.getTime())) return ""
	const y = dt.getFullYear()
	const m = String(dt.getMonth() + 1).padStart(2, "0")
	const day = String(dt.getDate()).padStart(2, "0")
	return `${y}-${m}-${day}`
}

async function onGenerate() {
	// Part A only (no conveyance) requires a GST Transporter ID (Desk sets it
	// `reqd` when the label reads "Part A").
	if (generateLabel.value.includes("Part A") && !form.gst_transporter_id) {
		toast.warn(
			"GST Transporter ID required",
			"A Part A e-Waybill needs a transporter / GST Transporter ID.",
		)
		return
	}
	// Desk: lr_date is mandatory when a Transport Receipt No is entered.
	if (form.lr_no && !form.lr_date) {
		toast.warn("Transport Receipt Date required", "Enter the date for the Transport Receipt No.")
		return
	}

	// Same `values` shape the Desk dialog posts (passed as a plain object; the
	// server's `_parse_values` accepts a dict directly).
	const values = {
		transporter: form.transporter || "",
		distance: form.distance || 0,
		gst_transporter_id: form.gst_transporter_id || "",
		vehicle_no: form.vehicle_no || "",
		lr_no: form.lr_no || "",
		lr_date: toDateStr(form.lr_date),
		mode_of_transport: form.mode_of_transport || "",
		gst_vehicle_type: form.gst_vehicle_type || "",
		gst_category: form.gst_category || "",
	}

	generating.value = true
	try {
		const result = await callMethod(
			"yrp_ewaybill_api.ewaybill.actions.generate_e_waybill",
			{ doctype: props.doctype, docname: props.docname, values },
		)
		// generate_e_waybill never throws on a GSP failure — it returns a dict.
		// Success ONLY when a real e-Waybill number came back.
		if (result?.ewaybill) {
			toast.success(
				"e-Waybill generated",
				`${result.ewaybill}${result.status ? ` (${result.status})` : ""}`,
				6000,
			)
			emit("generated", result)
			dialogVisible.value = false
		} else {
			toast.error(
				"e-Waybill generation failed",
				result?.error || result?.status || "e-Waybill generation failed",
			)
		}
	} catch (e) {
		toast.error("e-Waybill generation failed", e.message)
	} finally {
		generating.value = false
	}
}
</script>

<style scoped>
.ewb-section {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 4px 0 12px;
}
.ewb-section + .ewb-section {
	border-top: 1px solid var(--esd-line);
	padding-top: 12px;
}
.ewb-section__title {
	margin: 0;
	font-size: 12px;
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
}
.ewb-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
.ewb-note {
	color: var(--esd-muted);
	font-size: 11.5px;
}
.ewb-reqd {
	color: var(--esd-danger, #d9534f);
}
</style>
