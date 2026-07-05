<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		class="ewb-cancel-dialog"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		:header="'Cancel e-Waybill'"
		@show="onShow"
	>
		<div class="ewb-fields">
			<!-- Read-only e-Waybill number (mirrors the Desk dialog's first field). -->
			<div class="ewb-field">
				<label class="field-label">e-Waybill</label>
				<InputText :value="ewaybillNo" readonly disabled fluid />
			</div>

			<div class="ewb-field">
				<label class="field-label">Reason *</label>
				<Select
					v-model="reason"
					:options="REASON_OPTIONS"
					fluid
					placeholder="Select Reason"
				/>
			</div>

			<div class="ewb-field">
				<label class="field-label">Remark{{ remarkRequired ? " *" : "" }}</label>
				<Textarea
					v-model="remark"
					:rows="2"
					fluid
					autoResize
					placeholder="Optional remark"
				/>
				<small v-if="remarkRequired" class="ewb-note">
					A remark is required when the reason is "Others".
				</small>
			</div>
		</div>

		<template #footer>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="loading"
				@click="dialogVisible = false"
			/>
			<Button
				label="Cancel e-Waybill"
				icon="pi pi-times-circle"
				severity="danger"
				:loading="loading"
				@click="onCancel"
			/>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Cancel e-Waybill — /web port of `yrp_ewaybill.show_cancel_dialog` in
 * yrp_ewaybill_api/public/js/ewaybill_actions.js. Field set, labels, option
 * list and the "Data Entry Mistake" default mirror the Desk dialog exactly.
 *
 * Posts the reason label (not the NIC code) as `values.reason`; the server
 * (`cancel_e_waybill`) maps it via CANCEL_REASON_CODES. The backend never
 * throws on a GSP rejection — it returns `{ status: "Failed" }` with a red
 * msgprint — so success is confirmed by `status === "Cancelled"`, not merely
 * by the absence of an exception.
 */
import { ref, computed } from "vue"
import Dialog from "primevue/dialog"
import Select from "primevue/select"
import Textarea from "primevue/textarea"
import InputText from "primevue/inputtext"
import Button from "primevue/button"
import { callMethod } from "@/api/client"
import { useAppToast } from "@/composables/useToast"

const props = defineProps({
	visible: { type: Boolean, default: false },
	doctype: { type: String, default: "" },
	docname: { type: String, default: "" },
	doc: { type: Object, default: null },
})
const emit = defineEmits(["update:visible", "cancelled"])

const toast = useAppToast()

// Reason options + default replicate the Desk dialog (and CANCEL_REASON_CODES).
const REASON_OPTIONS = ["Duplicate", "Order Cancelled", "Data Entry Mistake", "Others"]
const DEFAULT_REASON = "Data Entry Mistake"

const loading = ref(false)
const reason = ref(DEFAULT_REASON)
const remark = ref("")

const dialogVisible = computed({
	get: () => props.visible,
	set: (v) => emit("update:visible", v),
})

const ewaybillNo = computed(() => props.doc?.ewaybill || "")
const remarkRequired = computed(() => reason.value === "Others")

// Reset the form to its defaults each time the dialog opens.
function onShow() {
	reason.value = DEFAULT_REASON
	remark.value = ""
}

async function onCancel() {
	if (remarkRequired.value && !remark.value.trim()) {
		toast.warn("Remark required", 'Enter a remark when the reason is "Others".')
		return
	}

	loading.value = true
	try {
		const res = await callMethod(
			"yrp_ewaybill_api.ewaybill.actions.cancel_e_waybill",
			{
				doctype: props.doctype,
				docname: props.docname,
				values: { reason: reason.value, remark: remark.value || null },
			},
		)
		// The action returns status "Failed" (not an exception) on a GSP rejection.
		if (res && res.status === "Cancelled") {
			toast.success(
				"e-Waybill cancelled",
				`e-Waybill for ${props.docname} has been cancelled.`,
				6000,
			)
			emit("cancelled", res)
			dialogVisible.value = false
		} else {
			toast.error(
				"Cancellation failed",
				res?.error ||
					"The e-Waybill portal rejected the cancellation. Check the e-Waybill Log for details.",
			)
		}
	} catch (e) {
		toast.error("Cancellation failed", e.message)
	} finally {
		loading.value = false
	}
}
</script>

<style scoped>
.ewb-fields {
	display: flex;
	flex-direction: column;
	gap: 14px;
	padding: 4px 2px;
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
</style>
