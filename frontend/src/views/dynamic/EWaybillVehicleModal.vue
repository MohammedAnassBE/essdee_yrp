<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		:header="`Update Vehicle Information`"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		@show="onShow"
	>
		<div class="ewb-form">
			<!-- e-Waybill (read-only context) — mirrors the Desk dialog's first field. -->
			<div class="ewb-field">
				<label class="field-label">e-Waybill</label>
				<InputText :modelValue="props.doc?.ewaybill || ''" readonly disabled fluid />
			</div>

			<!-- Vehicle No — mandatory for Road / Ship. -->
			<div class="ewb-field">
				<label class="field-label">Vehicle No {{ reqVehicleNo ? "*" : "" }}</label>
				<InputText
					v-model="form.vehicle_no"
					:invalid="attempted && reqVehicleNo && !form.vehicle_no"
					placeholder="e.g. TN01AB1234"
					fluid
				/>
			</div>

			<!-- Transport Receipt No (LR No) — mandatory for Rail / Air / Ship. -->
			<div class="ewb-field">
				<label class="field-label">Transport Receipt No {{ reqLrNo ? "*" : "" }}</label>
				<InputText
					v-model="form.lr_no"
					:invalid="attempted && reqLrNo && !form.lr_no"
					placeholder="Transport receipt / LR number"
					fluid
				/>
			</div>

			<!-- Mode Of Transport — drives GST Vehicle Type + the mandatory rules. -->
			<div class="ewb-field">
				<label class="field-label">Mode Of Transport</label>
				<Select
					v-model="form.mode_of_transport"
					:options="MODE_OPTIONS"
					showClear
					fluid
					placeholder="Select Mode"
					@change="onModeChange"
				/>
			</div>

			<!-- GST Vehicle Type — only for Road / Ship; forced to ODC (read-only) for Ship. -->
			<div v-if="showGstVehicleType" class="ewb-field">
				<label class="field-label">GST Vehicle Type</label>
				<Select
					v-model="form.gst_vehicle_type"
					:options="GST_VEHICLE_TYPE_OPTIONS"
					:disabled="gstVehicleTypeReadOnly"
					fluid
					placeholder="Select Vehicle Type"
				/>
			</div>

			<!-- Transport Receipt Date (LR Date) — mandatory when a receipt no is set. -->
			<div class="ewb-field">
				<label class="field-label">Transport Receipt Date {{ reqLrDate ? "*" : "" }}</label>
				<DatePicker
					:modelValue="toDateObj(form.lr_date)"
					@update:modelValue="form.lr_date = fromDateObj($event)"
					:invalid="attempted && reqLrDate && !form.lr_date"
					dateFormat="dd-mm-yy"
					showIcon
					iconDisplay="input"
					fluid
				/>
			</div>

			<!-- Reason — always required (NIC update-vehicle reason code). -->
			<div class="ewb-field">
				<label class="field-label">Reason *</label>
				<Select
					v-model="form.reason"
					:options="REASON_OPTIONS"
					:invalid="attempted && !form.reason"
					fluid
					placeholder="Select Reason"
				/>
			</div>

			<!-- Remark — mandatory when Reason is 'Others'. -->
			<div class="ewb-field">
				<label class="field-label">Remark {{ reqRemark ? "*" : "" }}</label>
				<InputText
					v-model="form.remark"
					:invalid="attempted && reqRemark && !form.remark"
					placeholder="Additional remark"
					fluid
				/>
			</div>
		</div>

		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="loading" @click="dialogVisible = false" />
			<Button label="Update" icon="pi pi-truck" :loading="loading" @click="onSubmit" />
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Update Vehicle Info (Part B) — /web port of the Desk dialog
 * `yrp_ewaybill.show_update_vehicle_dialog` in
 * yrp_ewaybill_api/public/js/ewaybill_actions.js.
 *
 * Adds / updates Part-B transport info on an already-generated e-Waybill.
 * Field set, labels, option lists and defaults mirror the Desk dialog exactly;
 * the same conditional-mandatory rules are enforced client-side before submit.
 * Posts to `yrp_ewaybill_api.ewaybill.actions.update_vehicle_info` — the server
 * `_parse_values` does `frappe.parse_json(values)` on a string, so `values` is
 * sent as a JSON STRING.
 */
import { reactive, ref, computed } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import InputText from "primevue/inputtext"
import DatePicker from "primevue/datepicker"
import Button from "primevue/button"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	docname: { type: String, default: "" },
	doc: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update:visible", "updated"])

const toast = useAppToast()

// Option lists — replicated verbatim from the Desk dialog.
const MODE_OPTIONS = ["Road", "Air", "Rail", "Ship"]
const GST_VEHICLE_TYPE_OPTIONS = ["Regular", "Over Dimensional Cargo (ODC)"]
const REASON_OPTIONS = ["Due to Break Down", "Due to Trans Shipment", "First Time", "Others"]

const dialogVisible = computed({
	get: () => props.visible,
	set: (v) => emit("update:visible", v),
})

const loading = ref(false)
const attempted = ref(false)
const form = reactive({
	vehicle_no: "",
	lr_no: "",
	lr_date: "",
	mode_of_transport: "",
	gst_vehicle_type: "",
	reason: "",
	remark: "",
})

// Conditional-mandatory rules (mirror the Desk `mandatory_depends_on` evals).
const reqVehicleNo = computed(() => ["Road", "Ship"].includes(form.mode_of_transport))
const reqLrNo = computed(() => ["Rail", "Air", "Ship"].includes(form.mode_of_transport))
const reqLrDate = computed(() => !!form.lr_no)
const reqRemark = computed(() => form.reason === "Others")
// GST Vehicle Type visibility / read-only (mirror Desk depends_on + read_only_depends_on).
const showGstVehicleType = computed(() => ["Road", "Ship"].includes(form.mode_of_transport))
const gstVehicleTypeReadOnly = computed(() => form.mode_of_transport === "Ship")

// Re-seed the form from the loaded Delivery Challan every time the dialog opens.
function onShow() {
	attempted.value = false
	const d = props.doc || {}
	Object.assign(form, {
		vehicle_no: d.vehicle_no || "",
		lr_no: d.lr_no || "",
		lr_date: d.lr_date || "",
		mode_of_transport: d.mode_of_transport || "",
		gst_vehicle_type: d.gst_vehicle_type || "",
		reason: "",
		remark: "",
	})
}

// Desk `update_vehicle_type`: Road→Regular, Ship→ODC, else cleared.
function vehicleTypeForMode(mode) {
	if (mode === "Road") return "Regular"
	if (mode === "Ship") return "Over Dimensional Cargo (ODC)"
	return ""
}
function onModeChange() {
	form.gst_vehicle_type = vehicleTypeForMode(form.mode_of_transport)
}

// DatePicker <-> "yyyy-mm-dd" string (backend `format_date(lr_date, "dd/mm/yyyy")`).
function toDateObj(val) {
	if (!val) return null
	const [y, m, d] = String(val).trim().split(/[ T]/)[0].split("-").map(Number)
	if (!y || !m || !d) return null
	const obj = new Date(y, m - 1, d)
	return Number.isNaN(obj.getTime()) ? null : obj
}
function fromDateObj(d) {
	if (!d) return ""
	const pad = (n) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function validate() {
	if (reqVehicleNo.value && !form.vehicle_no) return "Vehicle No is required for Road / Ship transport."
	if (reqLrNo.value && !form.lr_no) return "Transport Receipt No is required for Rail / Air / Ship transport."
	if (reqLrDate.value && !form.lr_date) return "Transport Receipt Date is required when a Transport Receipt No is set."
	if (!form.reason) return "Reason is required."
	if (reqRemark.value && !form.remark) return "Remark is required when Reason is 'Others'."
	return null
}

async function onSubmit() {
	attempted.value = true
	const err = validate()
	if (err) {
		toast.warn("Missing details", err)
		return
	}
	loading.value = true
	try {
		const res = await callMethod("yrp_ewaybill_api.ewaybill.actions.update_vehicle_info", {
			doctype: props.doctype,
			docname: props.docname,
			// `_parse_values` frappe.parse_json's a string → send a JSON string.
			values: JSON.stringify({
				vehicle_no: (form.vehicle_no || "").trim(),
				lr_no: (form.lr_no || "").trim(),
				lr_date: form.lr_date || "",
				mode_of_transport: form.mode_of_transport || "",
				gst_vehicle_type: form.gst_vehicle_type || "",
				reason: form.reason || "",
				remark: (form.remark || "").trim(),
			}),
		})
		// Never-throw failure policy: a GSP rejection returns status "Failed"
		// (with a red server msgprint) rather than raising. Surface it and keep
		// the dialog open so the user can correct + retry.
		if (res && res.status === "Failed") {
			toast.error("Vehicle info update failed", res?.error || "The e-Waybill portal rejected the update — see the e-Waybill Log for the NIC error.")
			return
		}
		toast.success(
			"Vehicle info updated",
			res?.ewaybill ? `e-Waybill ${res.ewaybill} — ${res.status || "updated"}` : undefined,
			6000,
		)
		emit("updated", res || {})
		dialogVisible.value = false
	} catch (e) {
		toast.error("Vehicle info update failed", e.message)
	} finally {
		loading.value = false
	}
}
</script>

<style scoped>
.ewb-form {
	display: flex;
	flex-direction: column;
	gap: 12px;
}
.ewb-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
}
</style>
