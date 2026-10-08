<template>
	<section data-sewing-plan-tab="data-entry" class="sewing-data-entry" :aria-busy="loading || busy" aria-label="Sewing data entry">
		<header class="sewing-data-entry__header">
			<div><h2>Data Entry</h2><p>Record inputs against saved Sewing Plan rows.</p></div>
			<Button label="Refresh" aria-label="Refresh data entry" icon="pi pi-refresh" severity="secondary" :disabled="loading || busy" @click="load()" />
		</header>
		<div v-if="loading && !loaded" role="status"><p>Loading Sewing Plans</p><Skeleton height="180px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" :message="loadError" @retry="load()" />
		<template v-else>
			<Message v-if="loadError" severity="warn" :closable="false">{{ loadError }} <Button label="Retry" text :disabled="loading || busy" @click="load()" /></Message>
			<form novalidate @submit.prevent="saveEntry">
				<div class="sewing-data-entry__filters">
					<div class="common-field"><label for="sewing-lot">Lot</label><Select input-id="sewing-lot" v-model="filters.lot" :options="lots" aria-label="Lot" placeholder="All Lots" show-clear :disabled="loading || busy" fluid /><small>Lots for {{ supplier }} only. Optional filter.</small></div>
					<div class="common-field"><label for="sewing-plan">Sewing Plan <b aria-hidden="true">*</b></label><Select input-id="sewing-plan" v-model="filters.plan" :options="plans" option-label="name" option-value="name" aria-label="Sewing Plan" placeholder="Select a Sewing Plan" :disabled="loading || busy" :invalid="missing('plan')" :aria-invalid="missing('plan') || undefined" aria-required="true" fluid /><small v-if="missing('plan')" class="field-error">Select a Sewing Plan.</small></div>
					<div class="common-field"><label for="sewing-input">Input Type <b aria-hidden="true">*</b></label><Select input-id="sewing-input" v-model="filters.inputType" :options="response.input_types || []" aria-label="Input Type" placeholder="Select input type" :disabled="loading || busy" :invalid="missing('inputType')" :aria-invalid="missing('inputType') || undefined" aria-required="true" fluid /><small v-if="missing('inputType')" class="field-error">Select an Input Type.</small></div>
					<LinkField v-model="filters.workStation" doctype="YRP Work Station" label="Work Station *" aria-label="Work Station" placeholder="Select Work Station" :help-text="missing('workStation') ? 'Select a Work Station.' : 'Required for entry.'" required :invalid="missing('workStation')" :disabled="loading || busy" :show-open-button="false" :search-handler="text => search('YRP Work Station', text)" />
					<LinkField v-model="filters.receivedType" doctype="YRP Received Type" label="Received Type *" aria-label="Received Type" placeholder="Select Received Type" :help-text="missing('receivedType') ? 'Select a Received Type.' : 'Required for entry.'" required :invalid="missing('receivedType')" :disabled="loading || busy" :show-open-button="false" :search-handler="text => search('YRP Received Type', text)" />
					<DateField v-model="filters.date" label="Date" input-id="sewing-entry-date" required :invalid="missing('date')" :disabled="loading || busy" :error="missing('date') ? 'Choose a Date.' : ''" />
					<TimeField v-model="filters.time" label="Time" input-id="sewing-entry-time" required :invalid="missing('time')" :disabled="loading || busy" :error="missing('time') ? 'Choose a Time.' : ''" />
				</div>
				<p v-if="!Object.keys(response.data || {}).length" class="erp-empty-state">No Sewing Plans for this Sewing Unit.</p>
				<p v-else-if="!currentPlan" class="erp-empty-state">Select a Sewing Plan to enter quantities.</p>
				<template v-else>
					<div class="sewing-data-entry__context"><strong>{{ filters.plan }}</strong><span>Lot {{ currentPlan.details.lot }}</span><span>{{ currentPlan.details.item }}</span><span>{{ currentPlan.details.work_order }} · {{ currentPlan.details.work_order_status }}</span></div>
					<p id="sewing-entry-help" class="sewing-data-entry__help">{{ inputContext }} Remaining quantities are server-provided context; the server validates each save.</p>
					<SewingQuantityMatrix v-model="entryQuantities" :colours="currentPlan.colours" :primary-values="currentPlan.details.primary_values" :context-columns="contextColumns" :label="filters.plan" :disabled="busy || loading" :editable="canCreate" />
				</template>
				<div class="sewing-data-entry__actions">
					<Button type="submit" label="Save entry" icon="pi pi-check" :disabled="busy || loading || refreshRequired || !canCreate" />
					<small v-if="!canCreate">You do not have permission to create Sewing entries.</small>
					<small v-else>Enter at least one positive quantity. Required fields are marked *.</small>
				</div>
			</form>
			<Message v-if="success" severity="success" :closable="false" role="status">{{ success }}</Message>
			<section v-if="currentPlan" class="sewing-data-entry__inspection" aria-label="Inspection update">
				<div class="sewing-data-entry__inspection-heading"><div><h3>Inspection quantities</h3><p>Update saved totals. Revert clears the selected inspection for every row in this plan.</p></div><div class="common-field"><label for="sewing-inspection">Inspection Type</label><Select input-id="sewing-inspection" v-model="filters.inspectionType" :options="inspectionTypes" option-label="label" option-value="value" aria-label="Inspection Type" :disabled="busy || loading" fluid /></div></div>
				<SewingQuantityMatrix v-model="inspectionQuantities" :colours="currentPlan.colours" :primary-values="currentPlan.details.primary_values" :context-columns="[{ key: 'order_qty', label: 'Ordered' }]" :label="`${filters.plan} inspection`" quantity-label="Inspection quantity" :disabled="busy || loading" :editable="canWrite" />
				<div class="sewing-data-entry__actions"><Button label="Update inspection" severity="secondary" :disabled="busy || loading || refreshRequired || !canWrite" @click="saveInspection('update')" /><Button label="Revert inspection" severity="danger" outlined :disabled="busy || loading || refreshRequired || !canWrite" @click="saveInspection('revert')" /><small v-if="!canWrite">You do not have permission to update inspections.</small></div>
			</section>
		</template>
		<DocumentErrorDialog :message="error" @dismiss="dismissError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onUnmounted, ref, watch } from "vue"
import { searchLink } from "../../../api/frappe.js"
import { getSewingDataEntry, submitSewingDataEntry, updateSewingInspection } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import TimeField from "../../../components/common/TimeField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import SewingQuantityMatrix from "../components/SewingQuantityMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ filters: { type: Object, required: true }, actions: { type: Object, default: () => ({}) } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const response = ref({}), loaded = ref(false), loading = ref(false), loadError = ref(""), busy = ref(false), error = ref(""), success = ref(""), attempted = ref(false)
const entryDrafts = ref({}), inspectionDrafts = ref({})
const refreshRequired = ref(false)
let rejectedPlan = null
let acknowledgedPlan = null
let mounted = true
const searchSequences = new Map()
const canCreate = computed(() => Boolean(props.actions?.entry?.can_create))
const canWrite = computed(() => Boolean(props.actions?.plan?.can_write))
const lots = computed(() => Object.keys(response.value.data || {}))
const plans = computed(() => Object.entries(response.value.data || {}).filter(([lot]) => !props.filters.lot || lot === props.filters.lot).flatMap(([, plans]) => Object.entries(plans).map(([name, data]) => ({ name, data }))))
const currentPlan = computed(() => plans.value.find(plan => plan.name === props.filters.plan)?.data)
const inputKey = computed(() => props.filters.inputType.trim().toLowerCase().replaceAll(' ', '_'))
const predecessorKey = computed(() => response.value.diff?.[inputKey.value])
const contextColumns = computed(() => [
	{ key: "order_qty", label: "Ordered" },
	...(predecessorKey.value && predecessorKey.value !== "order_qty" ? [{ key: predecessorKey.value, label: "Previous stage" }] : []),
	...(inputKey.value ? [{ key: inputKey.value, label: "Entered" }, { key: `${inputKey.value}_remaining`, label: "Remaining" }] : []),
])
const inputContext = computed(() => props.filters.inputType ? `${props.filters.inputType} · Allowance ${response.value.allowances?.[inputKey.value] ?? 0}%.` : "Choose an Input Type to see stage context.")
const inspectionTypes = [{ value: "pre_final", label: "Pre Final" }, { value: "final_inspection", label: "Final Inspection" }]
const entryQuantities = computed({ get: () => entryDrafts.value[props.filters.plan] || {}, set: value => { entryDrafts.value[props.filters.plan] = value } })
const inspectionDraftKey = computed(() => `${props.filters.plan}:${props.filters.inspectionType}`)
const inspectionQuantities = computed({ get: () => inspectionDrafts.value[inspectionDraftKey.value] || {}, set: value => { inspectionDrafts.value[inspectionDraftKey.value] = value } })
const required = ["plan", "inputType", "workStation", "receivedType", "date", "time"]
function missing(field) { return attempted.value && !props.filters[field] }
function values(plan = currentPlan.value) { return Object.values(plan?.colours || {}).flatMap(colour => Object.values(colour.values || {})) }
function validQuantities(quantities) { return Object.values(quantities).every(value => Number.isFinite(Number(value)) && Number(value) >= 0) }
function initializeInspection() {
	if (currentPlan.value && !inspectionDrafts.value[inspectionDraftKey.value]) inspectionDrafts.value[inspectionDraftKey.value] = Object.fromEntries(values().map(value => [value.order_detail, value[props.filters.inspectionType] || 0]))
}
watch([currentPlan, () => props.filters.inspectionType], initializeInspection)
watch(() => props.filters.lot, () => { if (!plans.value.some(plan => plan.name === props.filters.plan)) props.filters.plan = "" })

async function search(doctype, text) {
	// A delayed AutoComplete timer can fire after Save disables the control.
	// Lookups observe the business/scope generation; they never advance it.
	if (!mounted || busy.value || loading.value) return []
	const generation = requestGeneration.value
	const selectedSupplier = supplier.value
	const sequence = (searchSequences.get(doctype) || 0) + 1
	searchSequences.set(doctype, sequence)
	const rows = await searchLink(doctype, text)
	return mounted && !busy.value && !loading.value && selectedSupplier === supplier.value
		&& isCurrent(generation) && searchSequences.get(doctype) === sequence ? rows : []
}

async function load(savedPlan = "", savedLot = "", resetInspection = true) {
	if (!supplier.value) return false
	// Acknowledged writes remain tied to their plan until authoritative recovery
	// succeeds, including when the operator retries with the Refresh button.
	const targetPlan = savedPlan || acknowledgedPlan?.plan || ""
	const targetLot = savedLot || acknowledgedPlan?.lot || ""
	const generation = beginRequest()
	loading.value = true; loadError.value = ""
	try {
		const data = await getSewingDataEntry(supplier.value, targetLot)
		if (!mounted || !isCurrent(generation)) return false
		if (targetPlan) {
			const authoritative = data?.data?.[targetLot]?.[targetPlan]
			if (!authoritative) throw new Error("The saved plan is no longer available. Refresh to view current Sewing Plans.")
			response.value.data[targetLot][targetPlan] = authoritative
			// Refresh only this plan's business records and inspection drafts.
			if (resetInspection) for (const type of inspectionTypes) delete inspectionDrafts.value[`${targetPlan}:${type.value}`]
			if (acknowledgedPlan?.plan === targetPlan && acknowledgedPlan.lot === targetLot) {
				for (const type of inspectionTypes) inspectionDrafts.value[`${targetPlan}:${type.value}`] = Object.fromEntries(values(authoritative).map(value => [value.order_detail, value[type.value] || 0]))
				acknowledgedPlan = null
			}
			initializeInspection()
		} else {
			response.value = data || {}
			if (!plans.value.some(plan => plan.name === props.filters.plan)) props.filters.plan = ""
			if (!response.value.input_types?.includes(props.filters.inputType)) props.filters.inputType = ""
			if (!loaded.value && !props.filters.receivedType) props.filters.receivedType = data?.default_received_type || ""
		}
		loaded.value = true
		refreshRequired.value = false
		return true
	} catch (reason) {
		if (mounted && isCurrent(generation)) loadError.value = reason.message || "Unable to load Sewing Plans."
		return false
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}

function dismissError() {
	error.value = ""
	const rejected = rejectedPlan
	rejectedPlan = null
	// Read current balances after acknowledgement without discarding either edit.
	if (rejected && mounted) load(rejected.plan, rejected.lot, false)
}

async function saveEntry() {
	if (busy.value || loading.value || refreshRequired.value || !canCreate.value) return
	attempted.value = true; success.value = ""
	if (required.some(field => !props.filters[field]) || !currentPlan.value) { error.value = "Complete all required entry fields."; return }
	if (!validQuantities(entryQuantities.value)) { error.value = "Quantities must be finite and non-negative."; return }
	if (!values().some(value => Number(entryQuantities.value[value.order_detail]) > 0)) { error.value = "Enter a quantity for at least one Sewing Plan item."; return }
	const quantities = { colours: Object.fromEntries(Object.entries(currentPlan.value.colours).map(([key, colour]) => [key, { values: Object.fromEntries(Object.entries(colour.values).map(([size, value]) => [size, { order_detail: value.order_detail, data_entry: Number(entryQuantities.value[value.order_detail] || 0) }])) }])) }
	const payload = { supplier: supplier.value, lot: currentPlan.value.details.lot, plan: props.filters.plan, input_type: props.filters.inputType, work_station: props.filters.workStation, received_type: props.filters.receivedType, date: props.filters.date, time: props.filters.time, quantities }
	await mutate(() => submitSewingDataEntry(payload), payload.plan, payload.lot, "Entry saved.", true)
}

async function saveInspection(action) {
	if (busy.value || loading.value || refreshRequired.value || !canWrite.value || !currentPlan.value) return
	if (!inspectionTypes.some(type => type.value === props.filters.inspectionType)) return
	if (action === "update" && !validQuantities(inspectionQuantities.value)) { error.value = "Quantities must be finite and non-negative."; return }
	const inspectionType = props.filters.inspectionType
	const rows = Object.values(currentPlan.value.colours).map(colour => ({ colour: colour.variant_colour, part: colour.part, set_combination: colour.set_combination, qty: Object.fromEntries(Object.entries(colour.values).map(([size, value]) => [size, { order_detail: value.order_detail, [inspectionType]: action === "revert" ? 0 : Number(inspectionQuantities.value[value.order_detail] || 0) }])) }))
	const payload = { supplier: supplier.value, lot: currentPlan.value.details.lot, plan: props.filters.plan, inspection_type: inspectionType, action, rows }
	await mutate(() => updateSewingInspection(payload), payload.plan, payload.lot, action === "revert" ? "Inspection reverted." : "Inspection updated.")
}

async function mutate(request, plan, lot, message, resetEntry = false) {
	const generation = beginRequest()
	busy.value = true; error.value = ""; success.value = ""
	try {
		await request()
		if (!mounted || !isCurrent(generation)) return
		acknowledgedPlan = { plan, lot }
		refreshRequired.value = true
		if (resetEntry) entryDrafts.value[plan] = {}
		const refreshed = await load(plan, lot)
		if (mounted) success.value = refreshed ? message : `${message} Refresh the plan before recording more quantities.`
	} catch (reason) {
		if (mounted && isCurrent(generation)) {
			rejectedPlan = { plan, lot }
			error.value = reason.message || "Unable to save Sewing quantities."
		}
	} finally { if (mounted) busy.value = false }
}

const now = new Date(), pad = value => String(value).padStart(2, "0")
if (!props.filters.date) props.filters.date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
if (!props.filters.time) props.filters.time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
watch(supplier, () => load(), { immediate: true })
onUnmounted(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-data-entry { min-width: 0; max-width: 100%; }
.sewing-data-entry__header, .sewing-data-entry__inspection-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h2, h3 { margin: 0; color: var(--erp-text); font-size: 16px; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-data-entry__filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; align-items: start; margin-bottom: 18px; }
.common-field { min-width: 0; display: grid; gap: 6px; }
label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
label b, .field-error { color: var(--erp-danger); }
small { color: var(--erp-text-muted); font-size: 11px; }
.sewing-data-entry__context { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; margin: 12px 0 6px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
.sewing-data-entry__help { margin: 0 0 10px; }
.sewing-data-entry__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding-block: 14px; }
.sewing-data-entry__inspection { border-top: 1px solid var(--erp-border); margin-top: 14px; padding-top: 18px; }
.sewing-data-entry__inspection-heading .common-field { width: 220px; flex-shrink: 0; }
:deep(.p-select) { min-width: 0; }
:deep(.p-button) { min-height: 38px; }
@media (max-width: 1000px) { .sewing-data-entry__filters { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .sewing-data-entry__filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sewing-data-entry__inspection-heading { align-items: flex-start; flex-direction: column; } .sewing-data-entry__inspection-heading .common-field { width: 100%; } }
@media (max-width: 430px) { .sewing-data-entry__filters { grid-template-columns: minmax(0, 1fr); } }
</style>
