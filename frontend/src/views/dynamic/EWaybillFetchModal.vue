<template>
	<Dialog
		v-model:visible="dialogVisible"
		modal
		class="ewb-fetch-dialog"
		:style="{ width: 'min(520px, calc(100vw - 32px))' }"
		header="Fetch e-Waybill"
		@show="onShow"
	>
		<div class="ewb-field">
			<label class="field-label">e-Waybill Date *</label>
			<DatePicker
				:model-value="toDateObj(eWaybillDate)"
				@update:model-value="eWaybillDate = fromDateObj($event)"
				dateFormat="dd-mm-yy"
				showIcon
				fluid
				:maxDate="new Date()"
				placeholder="Select date"
			/>
			<small class="ewb-note">
				The date the e-Waybill was generated on the portal.
			</small>
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
				label="Fetch"
				icon="pi pi-download"
				:loading="loading"
				@click="onFetch"
			/>
		</template>
	</Dialog>
</template>

<script setup>
/**
 * Fetch e-Waybill — /web port of the Desk dialog `yrp_ewaybill.show_fetch_dialog`
 * in yrp_ewaybill_api/public/js/ewaybill_actions.js.
 *
 * Recovers an e-Waybill already generated on the NIC portal for a submitted
 * Delivery Challan and links it back (matched by docNo on the given date). The
 * single field mirrors the Desk dialog exactly: an "e-Waybill Date" (required),
 * defaulting to the doc's posting_date. The server method CAN throw (e.g. the
 * doc already carries an e-Waybill), so the call is wrapped in try/catch.
 */
import { ref, computed } from "vue"
import Dialog from "primevue/dialog"
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
const emit = defineEmits(["update:visible", "fetched"])

const toast = useAppToast()
const loading = ref(false)
// Held as a Frappe-shaped "YYYY-MM-DD" string — the exact format the Desk sends
// as `e_waybill_date`. The DatePicker binds Date objects, so we bridge via
// toDateObj / fromDateObj (local-time safe, mirroring DocDetail's date helpers).
const eWaybillDate = ref("")

const dialogVisible = computed({
	get: () => props.visible,
	set: (v) => emit("update:visible", v),
})

// Seed the default date each time the dialog opens (Desk: posting_date || Today).
function onShow() {
	loading.value = false
	eWaybillDate.value = props.doc?.posting_date || todayStr()
}

async function onFetch() {
	if (!eWaybillDate.value) {
		toast.warn("Date required", "Select the date the e-Waybill was generated.")
		return
	}
	loading.value = true
	try {
		// values goes as a plain object (backend `_parse_values` accepts a dict);
		// matches the Desk's `values: { e_waybill_date: ... }` exactly.
		const res = await callMethod(
			"yrp_ewaybill_api.ewaybill.actions.fetch_e_waybill",
			{
				doctype: props.doctype,
				docname: props.docname,
				values: { e_waybill_date: eWaybillDate.value },
			},
		)
		const result = res || {}
		if (result.ewaybill) {
			toast.success("e-Waybill fetched", `Linked e-Waybill ${result.ewaybill}.`, 6000)
			emit("fetched", result)
			dialogVisible.value = false
		} else if (result.error) {
			// A real GSP/portal failure — distinct from a clean "nothing matched".
			toast.error("Fetch failed", result.error)
		} else {
			toast.info(
				"No e-Waybill found",
				"No matching e-Waybill was found on the portal for that date.",
			)
			emit("fetched", result)
			dialogVisible.value = false
		}
	} catch (e) {
		toast.error("Fetch failed", e.message)
	} finally {
		loading.value = false
	}
}

// ── date helpers (form string ↔ DatePicker Date) ──
// Build/parse from parts so a pure "YYYY-MM-DD" stays local (never the
// `new Date("2026-05-25")`-is-UTC day-shift in negative-offset timezones).
function todayStr() {
	return fromDateObj(new Date())
}
function toDateObj(val) {
	if (!val) return null
	const [y, m, d] = String(val).split(" ")[0].split("-").map(Number)
	if (!y || !m || !d) return null
	const obj = new Date(y, m - 1, d)
	return Number.isNaN(obj.getTime()) ? null : obj
}
function fromDateObj(d) {
	if (!d) return ""
	const pad = (n) => String(n).padStart(2, "0")
	return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
</script>

<style scoped>
.ewb-field {
	display: flex;
	flex-direction: column;
	gap: 6px;
	padding: 4px 2px;
}
.ewb-note {
	color: var(--esd-muted);
	font-size: 11.5px;
}
</style>
