<template>
	<section data-sewing-plan-tab="data-entry" class="sewing-data-entry" :aria-busy="loading || busy" aria-label="Sewing data entry">
		<div v-if="loading && !loaded" role="status"><p>Loading Sewing Plans</p><Skeleton height="180px" /></div>
		<WorkspaceLoadError v-else-if="loadError && !loaded" message="Retry to load Sewing Plans." @retry="load()" />
		<template v-else>
			<p v-if="loading && loaded" role="status">Refreshing Sewing Plans…</p>
			<Message v-if="loadError && !editor" severity="warn" :closable="false">Displayed Sewing Plans may be out of date. <Button label="Retry" text :disabled="loading || busy" @click="load()" /></Message>
			<div class="sewing-data-entry__toolbar">
				<div class="common-field"><label for="sewing-lot">Lot</label><Select input-id="sewing-lot" v-model="filters.lot" :options="lots" aria-label="Lot" placeholder="All Lots" show-clear :disabled="loading || busy" fluid /></div>
				<Button label="Refresh" aria-label="Refresh data entry" icon="pi pi-refresh" severity="secondary" :disabled="loading || busy" @click="load()" />
				<span v-if="plans.length" class="sewing-data-entry__count">{{ plans.length }} {{ plans.length === 1 ? 'plan' : 'plans' }}</span>
			</div>
			<p v-if="!Object.keys(response.data || {}).length" class="erp-empty-state">No Sewing Plans for this Sewing Unit.</p>
			<p v-else-if="!plans.length" class="erp-empty-state">No Sewing Plans match this Lot.</p>
			<div v-else class="sewing-data-entry__groups">
				<section v-for="group in planGroups" :key="group.lot" class="sewing-data-entry__lot" :aria-labelledby="group.headingId">
					<header class="sewing-data-entry__lot-header"><h3 :id="group.headingId">{{ group.lot }}</h3><small>{{ group.plans.length }} {{ group.plans.length === 1 ? 'plan' : 'plans' }}</small></header>
					<div class="sewing-data-entry__cards">
						<article v-for="plan in group.plans" :key="plan.name" class="sewing-data-entry__plan-card erp-card" :data-sewing-plan-card="plan.name">
							<header><div><h4 class="sewing-data-entry__work-order">{{ plan.data.details?.work_order || 'No Work Order' }}</h4><strong class="sewing-data-entry__item">{{ plan.data.details?.item || 'Item unavailable' }}</strong><p class="sewing-data-entry__plan-reference">{{ plan.name }} · {{ plan.data.details?.work_order_status || 'Status unavailable' }}</p></div><span class="erp-status erp-status--success">Ready</span></header>
							<div class="sewing-data-entry__stats">
								<span><small>Colours</small><strong>{{ Object.keys(plan.data.colours || {}).length }}</strong></span>
								<span><small>Sizes</small><strong>{{ plan.data.details?.primary_values?.length || 0 }}</strong></span>
								<span><small>Ordered</small><strong>{{ planTotal(plan.data).toLocaleString(undefined, { maximumFractionDigits: 3 }) }}</strong></span>
							</div>
							<footer><Button :label="canCreate ? 'Record Entry' : 'View Entry'" :icon="canCreate ? 'pi pi-plus' : 'pi pi-eye'" :aria-label="`${canCreate ? 'Record entry' : 'View entry'} for ${plan.name}`" :disabled="busy || loading" @click="openEditor(plan, 'entry')" /><Button :label="canWrite ? 'Update Inspection' : 'View Inspection'" :icon="canWrite ? 'pi pi-pencil' : 'pi pi-eye'" severity="secondary" outlined :aria-label="`${canWrite ? 'Update inspection' : 'View inspection'} for ${plan.name}`" :disabled="busy || loading" @click="openEditor(plan, 'inspection')" /></footer>
						</article>
					</div>
				</section>
			</div>
			<Message v-if="success && !editor" severity="success" :closable="false" role="status"><span>{{ success }}</span> <Button label="Dismiss save notice" text @click="dismissSuccess" /></Message>

			<Dialog v-model:visible="entryVisible" modal maximizable :dismissable-mask="!busy" :closable="!busy" :header="currentPlan ? `${canCreate ? 'Record Sewing entry' : 'View Sewing entry'} · ${filters.plan}` : (canCreate ? 'Record Sewing entry' : 'View Sewing entry')" class="sewing-plan-dialog erp-dialog--xl">
				<div class="sewing-data-entry__dialog-notices" aria-live="polite">
					<Message v-if="success" severity="success" :closable="false" role="status"><span>{{ success }}</span> <Button label="Dismiss save notice" text @click="dismissSuccess" /></Message>
					<Message v-if="loadError || refreshRequired" severity="warn" :closable="false"><span>{{ refreshRequired ? 'Saved values could not be refreshed. Refresh this plan before recording more quantities.' : 'Displayed plan values may be out of date.' }}</span> <Button label="Refresh plan" text :disabled="loading || busy" @click="load()" /></Message>
				</div>
				<form v-if="currentPlan" id="sewing-entry-form" class="sewing-data-entry__dialog-body" novalidate @submit.prevent="saveEntry">
					<div class="sewing-data-entry__context"><strong>{{ filters.plan }}</strong><span>Lot {{ currentPlan.details.lot }}</span><span>{{ currentPlan.details.item }}</span><span>{{ currentPlan.details.work_order }} · {{ currentPlan.details.work_order_status }}</span></div>
					<div class="sewing-data-entry__filters">
						<div class="common-field"><label for="sewing-input">Input Type <b aria-hidden="true">*</b></label><Select input-id="sewing-input" v-model="filters.inputType" :options="response.input_types || []" aria-label="Input Type" placeholder="Select input type" :disabled="loading || busy" :invalid="missing('inputType')" :aria-invalid="missing('inputType') || undefined" aria-required="true" fluid /><small v-if="missing('inputType')" class="field-error">Select an Input Type.</small></div>
						<LinkField v-model="filters.workStation" doctype="YRP Work Station" label="Work Station *" aria-label="Work Station" placeholder="Select Work Station" :help-text="missing('workStation') ? 'Select a Work Station.' : 'Required for entry.'" required :invalid="missing('workStation')" :disabled="loading || busy" :show-open-button="false" :search-handler="text => search('YRP Work Station', text)" />
						<LinkField v-model="filters.receivedType" doctype="YRP Received Type" label="Received Type *" aria-label="Received Type" placeholder="Select Received Type" :help-text="missing('receivedType') ? 'Select a Received Type.' : 'Required for entry.'" required :invalid="missing('receivedType')" :disabled="loading || busy" :show-open-button="false" :search-handler="text => search('YRP Received Type', text)" />
						<DateField v-model="filters.date" label="Date" input-id="sewing-entry-date" required :invalid="missing('date')" :disabled="loading || busy" :error="missing('date') ? 'Choose a Date.' : ''" />
						<TimeField v-model="filters.time" label="Time" input-id="sewing-entry-time" required :invalid="missing('time')" :disabled="loading || busy" :error="missing('time') ? 'Choose a Time.' : ''" />
					</div>
					<p id="sewing-entry-help" class="sewing-data-entry__help">{{ inputContext }} Remaining quantities are server-provided context; the server validates each save.</p>
					<SewingQuantityMatrix v-model="entryQuantities" :colours="currentPlan.colours" :primary-values="currentPlan.details.primary_values" :context-columns="contextColumns" :label="filters.plan" :disabled="busy || loading" :editable="canCreate" />
				</form>
				<template #footer><div class="sewing-data-entry__actions"><small v-if="!canCreate">You do not have permission to create Sewing entries.</small><small v-else>Enter at least one positive quantity. Required fields are marked *.</small><Button type="button" label="Close entry" severity="secondary" text :disabled="busy" @click="entryVisible = false" /><Button type="submit" form="sewing-entry-form" label="Save entry" icon="pi pi-check" :disabled="busy || loading || refreshRequired || !canCreate" /></div></template>
			</Dialog>

			<Dialog v-model:visible="inspectionVisible" modal maximizable :dismissable-mask="!busy" :closable="!busy" :header="currentPlan ? `${canWrite ? 'Update inspection' : 'View inspection'} · ${filters.plan}` : (canWrite ? 'Update inspection' : 'View inspection')" class="sewing-plan-dialog erp-dialog--xl">
				<div class="sewing-data-entry__dialog-notices" aria-live="polite">
					<Message v-if="success" severity="success" :closable="false" role="status"><span>{{ success }}</span> <Button label="Dismiss save notice" text @click="dismissSuccess" /></Message>
					<Message v-if="loadError || refreshRequired" severity="warn" :closable="false"><span>{{ refreshRequired ? 'Saved values could not be refreshed. Refresh this plan before recording more quantities.' : 'Displayed plan values may be out of date.' }}</span> <Button label="Refresh plan" text :disabled="loading || busy" @click="load()" /></Message>
				</div>
				<section v-if="currentPlan" class="sewing-data-entry__dialog-body" aria-label="Inspection update">
					<div class="sewing-data-entry__inspection-heading"><div><h3>Inspection quantities</h3><p>Update saved totals. Revert clears the selected inspection for every row in this plan.</p></div><div class="common-field"><label for="sewing-inspection">Inspection Type</label><Select input-id="sewing-inspection" v-model="filters.inspectionType" :options="inspectionTypes" option-label="label" option-value="value" aria-label="Inspection Type" :disabled="busy || loading" fluid /></div></div>
					<SewingQuantityMatrix v-model="inspectionQuantities" :colours="currentPlan.colours" :primary-values="currentPlan.details.primary_values" :context-columns="[{ key: 'order_qty', label: 'Ordered' }]" :label="`${filters.plan} inspection`" quantity-label="Inspection quantity" :disabled="busy || loading" :editable="canWrite" />
				</section>
				<template #footer><div class="sewing-data-entry__actions"><small v-if="!canWrite">You do not have permission to update inspections.</small><Button label="Close inspection" severity="secondary" text :disabled="busy" @click="inspectionVisible = false" /><Button label="Update inspection" severity="secondary" :disabled="busy || loading || refreshRequired || !canWrite" @click="saveInspection('update')" /><Button label="Revert inspection" severity="danger" outlined :disabled="busy || loading || refreshRequired || !canWrite" @click="saveInspection('revert')" /></div></template>
			</Dialog>
		</template>
		<DocumentErrorDialog :message="error || mutationError" @dismiss="dismissError" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, onUnmounted, ref, toRefs, watch } from "vue"
import { searchLink } from "../../../api/frappe.js"
import { getSewingDataEntry } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import TimeField from "../../../components/common/TimeField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import SewingQuantityMatrix from "../components/SewingQuantityMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ state: { type: Object, required: true }, mutate: { type: Function, required: true }, filters: { type: Object, required: true }, actions: { type: Object, default: () => ({}) } })
const { supplier, requestGeneration, beginRequest, isCurrent } = useSewingContext()
const { response, loaded, loadError, busy, error, success, attempted, entryDrafts, inspectionDrafts, refreshRequired } = toRefs(props.state)
const loading = ref(false)
const editor = ref("")
const mutationError = computed(() => props.state.operation?.status === 'rejected' && !props.state.operation.acknowledged ? props.state.operation.error : '')
let mounted = true
const searchSequences = new Map()
const canCreate = computed(() => Boolean(props.actions?.entry?.can_create))
const canWrite = computed(() => Boolean(props.actions?.plan?.can_write))
const lots = computed(() => Object.keys(response.value.data || {}))
const planGroups = computed(() => Object.entries(response.value.data || {})
	.filter(([lot]) => !props.filters.lot || lot === props.filters.lot)
	.map(([lot, records], index) => ({ lot, headingId: `sewing-lot-${safeId(lot)}-${index}`, plans: Object.entries(records).map(([name, data]) => ({ name, data })) })))
const plans = computed(() => planGroups.value.flatMap(group => group.plans))
const currentPlan = computed(() => plans.value.find(plan => plan.name === props.filters.plan)?.data)
const entryVisible = computed({ get: () => editor.value === "entry", set: visible => { if (!visible && editor.value === "entry") editor.value = "" } })
const inspectionVisible = computed({ get: () => editor.value === "inspection", set: visible => { if (!visible && editor.value === "inspection") editor.value = "" } })
const inputKey = computed(() => props.filters.inputType.trim().toLowerCase().replaceAll(' ', '_'))
const predecessorKey = computed(() => response.value.diff?.[inputKey.value])
const contextColumns = computed(() => [
	{ key: "order_qty", label: "Ordered" },
	...(predecessorKey.value && predecessorKey.value !== "order_qty" ? [{ key: predecessorKey.value, label: "Previous stage" }] : []),
	...(inputKey.value ? [{ key: inputKey.value, label: "Entered" }, { key: `${inputKey.value}_remaining`, label: "Remaining" }] : []),
])
const inputContext = computed(() => props.filters.inputType ? `${props.filters.inputType} · Allowance ${response.value.allowances?.[inputKey.value] ?? 0}%.` : "Choose an Input Type to see stage context.")
const inspectionTypes = [{ value: "pre_final", label: "Pre Final" }, { value: "final_inspection", label: "Final Inspection" }]
const entryDraftKey = computed(() => inputKey.value ? `${props.filters.plan}:${inputKey.value}` : "")
const entryQuantities = computed({
	get: () => entryDraftKey.value ? entryDrafts.value[entryDraftKey.value] || {} : {},
	set: value => { if (entryDraftKey.value) entryDrafts.value[entryDraftKey.value] = value },
})
const inspectionDraftKey = computed(() => `${props.filters.plan}:${props.filters.inspectionType}`)
const inspectionQuantities = computed({ get: () => inspectionDrafts.value[inspectionDraftKey.value] || {}, set: value => { inspectionDrafts.value[inspectionDraftKey.value] = value } })
const required = ["plan", "inputType", "workStation", "receivedType", "date", "time"]
function missing(field) { return attempted.value && !props.filters[field] }
function values(plan = currentPlan.value) { return Object.values(plan?.colours || {}).flatMap(colour => Object.values(colour.values || {})) }
function planTotal(plan) { return values(plan).reduce((total, value) => total + Number(value.order_qty || 0), 0) }
function safeId(value) { return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-") }
function openEditor(plan, mode) {
	props.filters.plan = plan.name
	attempted.value = false
	editor.value = mode
}
function validQuantities(quantities) { return Object.values(quantities).every(value => Number.isFinite(Number(value)) && Number(value) >= 0) }
function initializeEntry() {
	if (!currentPlan.value || !entryDraftKey.value || entryDrafts.value[entryDraftKey.value]) return
	const remainingKey = `${inputKey.value}_remaining`
	entryDrafts.value[entryDraftKey.value] = Object.fromEntries(values().map(value => [value.order_detail, Number(value[remainingKey] ?? 0)]))
}
function initializeInspection() {
	if (currentPlan.value && !inspectionDrafts.value[inspectionDraftKey.value]) inspectionDrafts.value[inspectionDraftKey.value] = Object.fromEntries(values().map(value => [value.order_detail, value[props.filters.inspectionType] || 0]))
}
watch([currentPlan, inputKey], initializeEntry)
watch([currentPlan, () => props.filters.inspectionType], initializeInspection)
watch(() => props.filters.lot, () => {
	if (!plans.value.some(plan => plan.name === props.filters.plan)) { props.filters.plan = ""; editor.value = "" }
})

async function search(doctype, text) {
	// A delayed AutoComplete timer can fire after Save disables the control.
	// Lookups observe the business/scope generation; they never advance it.
	if (!mounted || busy.value || loading.value) return []
	const generation = requestGeneration.value
	const selectedSupplier = supplier.value
	const sequence = (searchSequences.get(doctype) || 0) + 1
	searchSequences.set(doctype, sequence)
	const current = () => mounted && !busy.value && !loading.value && selectedSupplier === supplier.value && isCurrent(generation) && searchSequences.get(doctype) === sequence
	try {
		const rows = await searchLink(doctype, text)
		return current() ? rows : []
	} catch (reason) { if (current()) error.value = reason.message || 'Unable to load entry options.'; return [] }
}

async function load(savedPlan = "", savedLot = "", resetInspection = true) {
	if (!supplier.value || loading.value || busy.value) return false
	// Acknowledged writes remain tied to their plan until authoritative recovery
	// succeeds, including when the operator retries with the Refresh button.
	const operation = props.state.operation
	if (operation?.status === 'rejected' && !operation.acknowledged) return false
	const recovery = refreshRequired.value ? operation : null
	const targetPlan = savedPlan || recovery?.plan || ""
	const targetLot = savedLot || recovery?.lot || ""
	resetInspection = recovery ? recovery.status === 'succeeded' : resetInspection
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
			if (recovery?.status === 'succeeded') {
				for (const type of inspectionTypes) inspectionDrafts.value[`${targetPlan}:${type.value}`] = Object.fromEntries(values(authoritative).map(value => [value.order_detail, value[type.value] || 0]))
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
		if (mounted && isCurrent(generation)) { loadError.value = reason.message || "Unable to load Sewing Plans."; error.value = loadError.value }
		return false
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}

function dismissError() {
	error.value = ""
	const rejected = props.state.operation
	// Read current balances after acknowledgement without discarding either edit.
	if (rejected?.status === 'rejected' && !rejected.acknowledged) {
		rejected.acknowledged = true
		if (mounted) load(rejected.plan, rejected.lot, false)
	}
}
function dismissSuccess() { success.value = ''; if (props.state.operation) props.state.operation.acknowledged = true }

async function saveEntry() {
	if (busy.value || loading.value || refreshRequired.value || !canCreate.value) return
	attempted.value = true; success.value = ""
	if (required.some(field => !props.filters[field]) || !currentPlan.value) { error.value = "Complete all required entry fields."; return }
	if (!validQuantities(entryQuantities.value)) { error.value = "Quantities must be finite and non-negative."; return }
	if (!values().some(value => Number(entryQuantities.value[value.order_detail]) > 0)) { error.value = "Enter a quantity for at least one Sewing Plan item."; return }
	const quantities = { colours: Object.fromEntries(Object.entries(currentPlan.value.colours).map(([key, colour]) => [key, { values: Object.fromEntries(Object.entries(colour.values).map(([size, value]) => [size, { order_detail: value.order_detail, data_entry: Number(entryQuantities.value[value.order_detail] || 0) }])) }])) }
	const payload = { supplier: supplier.value, lot: currentPlan.value.details.lot, plan: props.filters.plan, input_type: props.filters.inputType, work_station: props.filters.workStation, received_type: props.filters.receivedType, date: props.filters.date, time: props.filters.time, quantities }
	await props.mutate(payload, "Entry saved.", true)
}

async function saveInspection(action) {
	if (busy.value || loading.value || refreshRequired.value || !canWrite.value || !currentPlan.value) return
	if (!inspectionTypes.some(type => type.value === props.filters.inspectionType)) return
	if (action === "update" && !validQuantities(inspectionQuantities.value)) { error.value = "Quantities must be finite and non-negative."; return }
	const inspectionType = props.filters.inspectionType
	const rows = Object.values(currentPlan.value.colours).map(colour => ({ colour: colour.variant_colour, part: colour.part, set_combination: colour.set_combination, qty: Object.fromEntries(Object.entries(colour.values).map(([size, value]) => [size, { order_detail: value.order_detail, [inspectionType]: action === "revert" ? 0 : Number(inspectionQuantities.value[value.order_detail] || 0) }])) }))
	const payload = { supplier: supplier.value, lot: currentPlan.value.details.lot, plan: props.filters.plan, inspection_type: inspectionType, action, rows }
	await props.mutate(payload, action === "revert" ? "Inspection reverted." : "Inspection updated.")
}

async function settle() {
	if (busy.value || !mounted) return
	const operation = props.state.operation
	if (operation?.status === 'rejected' && !operation.acknowledged) return
	if (operation?.status === 'succeeded' && refreshRequired.value) {
		const refreshed = await load(operation.plan, operation.lot)
		if (mounted && !operation.acknowledged) success.value = refreshed ? operation.message : `${operation.message} Refresh the plan before recording more quantities.`
	} else if (!loaded.value) await load()
}

const now = new Date(), pad = value => String(value).padStart(2, "0")
if (!props.filters.date) props.filters.date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
if (!props.filters.time) props.filters.time = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
onMounted(() => watch(() => props.state.busy, settle, { immediate: true }))
onUnmounted(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.sewing-data-entry { min-width: 0; max-width: 100%; }
.sewing-data-entry__inspection-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
h3 { margin: 0; color: var(--erp-text); font-size: 16px; }
h4 { margin: 0; color: var(--erp-text); font-size: 15px; }
p { margin: 5px 0 0; font-size: var(--erp-font-size-caption); color: var(--erp-text-muted); }
.sewing-data-entry__toolbar { display: flex; align-items: flex-end; justify-content: flex-start; gap: var(--erp-space-3); margin-bottom: var(--erp-space-3); padding-bottom: var(--erp-space-3); border-bottom: 1px solid var(--erp-border-subtle); }
.sewing-data-entry__toolbar .common-field { width: min(340px, 100%); }
.sewing-data-entry__toolbar > .p-button { flex: 0 0 auto; }
.sewing-data-entry__count { flex: 0 0 auto; margin-left: auto; padding: 4px 9px; color: var(--erp-accent-dark); font-size: 11px; font-weight: var(--erp-font-weight-bold); background: var(--erp-accent-soft); border: 1px solid var(--erp-accent-border); border-radius: var(--erp-pill-radius); }
.sewing-data-entry__groups { display: grid; gap: var(--erp-space-4); }
.sewing-data-entry__lot { min-width: 0; }
.sewing-data-entry__lot-header { display: flex; align-items: baseline; justify-content: space-between; gap: var(--erp-space-3); margin-bottom: 8px; padding-inline: 2px; }
.sewing-data-entry__lot-header h3 { font-size: 17px; letter-spacing: -0.02em; }
.sewing-data-entry__cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.sewing-data-entry__plan-card { display: grid; gap: 10px; min-width: 0; padding: 14px; box-shadow: var(--erp-shadow-xs); transition: border-color var(--erp-transition-base), box-shadow var(--erp-transition-base), transform var(--erp-transition-base); }
.sewing-data-entry__plan-card > header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--erp-space-3); }
.sewing-data-entry__plan-card > header > div { min-width: 0; }
.sewing-data-entry__work-order { overflow: hidden; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.sewing-data-entry__item { display: block; min-width: 0; margin-top: 3px; overflow: hidden; color: var(--erp-text-secondary); font-size: 13px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.sewing-data-entry__plan-reference { overflow: hidden; color: var(--erp-text-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.sewing-data-entry__stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); overflow: hidden; background: var(--erp-surface-soft); border: 1px solid var(--erp-border-subtle); border-radius: var(--erp-control-radius); }
.sewing-data-entry__stats > span { display: grid; gap: 2px; min-width: 0; padding: 9px 10px; border-right: 1px solid var(--erp-border-subtle); }
.sewing-data-entry__stats > span:last-child { border-right: 0; }
.sewing-data-entry__stats small { text-transform: uppercase; letter-spacing: 0.035em; }
.sewing-data-entry__stats strong { overflow: hidden; color: var(--erp-text); font-size: 14px; font-variant-numeric: tabular-nums; text-overflow: ellipsis; white-space: nowrap; }
.sewing-data-entry__plan-card > footer { display: flex; align-items: center; justify-content: flex-end; gap: var(--erp-space-2); flex-wrap: wrap; padding-top: 2px; }
.sewing-data-entry__filters { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; align-items: start; margin-bottom: 18px; }
.common-field { min-width: 0; display: grid; gap: 6px; }
label { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
label b, .field-error { color: var(--erp-danger); }
small { color: var(--erp-text-muted); font-size: 11px; }
.sewing-data-entry__context { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; margin: 12px 0 6px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); }
.sewing-data-entry__help { margin: 0 0 10px; }
.sewing-data-entry__dialog-notices { display: grid; gap: var(--erp-space-2); margin-bottom: var(--erp-space-3); }
.sewing-data-entry__dialog-notices:empty { display: none; }
.sewing-data-entry__actions { display: flex; flex: 1; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 12px; }
.sewing-data-entry__dialog-body { min-width: 0; }
.sewing-data-entry__inspection-heading .common-field { width: 220px; flex-shrink: 0; }
:deep(.p-select) { min-width: 0; }
:deep(.p-button) { min-height: 38px; }
:global(.sewing-plan-dialog .p-dialog-content) { padding-top: 0; }
@media (hover: hover) { .sewing-data-entry__plan-card:hover { border-color: var(--erp-accent-border); box-shadow: var(--erp-shadow-sm); transform: translateY(-1px); } }
@media (max-width: 1000px) { .sewing-data-entry__filters { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 760px) { .sewing-data-entry__cards { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .sewing-data-entry__inspection-heading { align-items: flex-start; flex-direction: column; } .sewing-data-entry__filters { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sewing-data-entry__inspection-heading .common-field { width: 100%; } }
@media (max-width: 540px) { .sewing-data-entry__toolbar { flex-wrap: wrap; } .sewing-data-entry__toolbar .common-field { width: 100%; } .sewing-data-entry__count { margin-left: 0; } }
@media (max-width: 430px) { .sewing-data-entry__filters { grid-template-columns: minmax(0, 1fr); } }
</style>
