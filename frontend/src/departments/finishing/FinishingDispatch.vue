<template>
	<DepartmentPage title="Finishing Plan Dispatch" back-to="/finishing/dispatches" back-label="Finishing Plan Dispatches" :show-title="false" flat full-width inline-navigation>
		<div v-if="loading && !ready" class="finishing-plan__probe erp-workspace" aria-label="Loading Finishing Plan Dispatch"><Skeleton height="64px" /><Skeleton height="360px" /></div>
		<div v-else-if="loadError && !ready" class="finishing-plan__probe erp-workspace">
			<WorkspaceLoadError title="Finishing Plan Dispatch unavailable" :message="loadError" :loading="loading" @retry="load" />
		</div>
		<section v-else class="finishing-dispatch erp-workspace erp-card" aria-label="Finishing Plan Dispatch" :aria-busy="loading || busy">
			<header class="finishing-dispatch__header">
				<InlinePageNavigation title-target="finishing-dispatch-title" :show-document-navigation="Boolean(dispatchId)" :current-name="dispatchId" document-label="Finishing Plan Dispatch" :navigation-disabled="loading || busy" />
				<div class="finishing-dispatch__identity">
					<div class="finishing-dispatch__title"><h1 id="finishing-dispatch-title">Finishing Plan Dispatch</h1><span>{{ record.name || `New · ${record.naming_series || ""}` }}</span></div>
					<div class="finishing-dispatch__meta">
						<DocumentStatusBadge :docstatus="record.docstatus" :label="statusLabel" />
						<span class="finishing-plan__fact"><small>Plans</small><strong>{{ rows.length }}</strong></span>
						<span v-if="record.stock_entry" class="finishing-plan__fact"><small>Stock Entry</small><button type="button" class="finishing-dispatch__link" @click="openStockEntry">{{ record.stock_entry }}</button></span>
					</div>
				</div>
				<div class="finishing-dispatch__actions">
					<template v-if="draft">
						<Button label="Fetch Items" icon="pi pi-refresh" severity="secondary" outlined :disabled="busy" @click="confirmFetch" />
						<DocumentSaveButton v-if="permissions.can_write" :show-submit="Boolean(permissions.can_submit)" :loading="busy" @save="save(false)" @submit="save(true)" />
					</template>
					<template v-else>
						<DocumentPrintButton v-if="permissions.can_print" doctype="SD YRP Finishing Plan Dispatch" :name="record.name" :formats="workspace.print_formats || []" :disabled="busy" />
						<Button v-if="permissions.can_dispatch_stock" label="Dispatch Stock" icon="pi pi-truck" :disabled="busy" @click="dispatchOpen = true" />
						<Button v-if="permissions.can_cancel" label="Cancel" icon="pi pi-ban" severity="danger" outlined :disabled="busy" @click="confirmCancel" />
					</template>
				</div>
			</header>
			<p v-if="!rows.length" class="finishing-empty">{{ draft ? "No Finishing Plans have packed boxes waiting for dispatch." : "This dispatch has no Finishing Plan rows." }}</p>
			<section v-for="row in rows" :key="`${row.doc_name}-${rowsVersion}`" class="finishing-section" :aria-label="`${row.lot} ${row.item}`">
				<h2 class="finishing-dispatch__plan">
					<span>{{ row.lot }}-{{ row.item }}</span>
					<RouterLink :to="`/finishing/plans/${encodeURIComponent(row.doc_name)}`" class="finishing-dispatch__link">{{ row.doc_name }}</RouterLink>
				</h2>
				<FinishingDispatchEntry
					:ref="(component) => setEntry(row.doc_name, component)"
					:sizes="dispatchEntrySource(row).sizes"
					:packed="dispatchEntrySource(row).packed"
					:config="row.packing_config || {}"
					:initial="dispatchInitialState(row)"
					:show-packed="false"
					:readonly="!draft"
					:disabled="!draft || busy || !permissions.can_write"
				/>
			</section>
		</section>
		<Dialog v-model:visible="dispatchOpen" modal header="Dispatch Stock" class="erp-dialog--sm" :closable="!busy">
			<form class="finishing-dispatch__form" @submit.prevent="dispatchStock">
				<LinkField :model-value="stock.from_supplier" doctype="Supplier" label="From Supplier" required :show-open-button="false" :disabled="busy" @update:model-value="(value) => setSupplier('from', value)" />
				<LinkField v-model="stock.from_warehouse" doctype="Warehouse" label="From Warehouse" required :filters="warehouseFilters(stock.from_supplier)" :show-open-button="false" :disabled="busy" />
				<LinkField :model-value="stock.to_supplier" doctype="Supplier" label="To Supplier" required :show-open-button="false" :disabled="busy" @update:model-value="(value) => setSupplier('to', value)" />
				<LinkField v-model="stock.to_warehouse" doctype="Warehouse" label="To Warehouse" required :filters="warehouseFilters(stock.to_supplier)" :show-open-button="false" :disabled="busy" />
				<label class="common-field"><span class="finishing-field-label">Goods Value</span><InputNumber v-model="stock.goods_value" :max-fraction-digits="2" fluid :disabled="busy" /></label>
				<label class="common-field"><span class="finishing-field-label">Vehicle No</span><InputText v-model="stock.vehicle_no" fluid :disabled="busy" /></label>
			</form>
			<template #footer>
				<Button label="Close" severity="secondary" text :disabled="busy" @click="dispatchOpen = false" />
				<Button label="Dispatch" icon="pi pi-truck" :loading="busy" @click="dispatchStock" />
			</template>
		</Dialog>
		<DocumentTransactionDialog v-model:visible="stockEntryOpen" doctype="YRP Stock Entry" :name="stockEntryName" :show-edit="false" @changed="load" />
		<DocumentErrorDialog :message="actionError" title="Finishing Plan Dispatch action failed" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, reactive, ref, watch } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"

import { executeDispatchCommand, fetchDispatchItems, getDispatchWorkspace, saveDispatch } from "../../api/finishing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentPrintButton from "../../components/documents/DocumentPrintButton.vue"
import DocumentSaveButton from "../../components/documents/DocumentSaveButton.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import DocumentTransactionDialog from "../../components/documents/DocumentTransactionDialog.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import { useActionConfirmation } from "../../utils/useActionConfirmation.js"
import FinishingDispatchEntry from "./components/FinishingDispatchEntry.vue"
import { dispatchEntrySource, dispatchInitialState } from "./finishingEntries.js"
import { setDispatchSupplier, warehouseFilters } from "./supplierWarehouse.js"
import "./finishing.css"

const route = useRoute()
const router = useRouter()
const toast = useToast()
const confirmAction = useActionConfirmation()
const dispatchId = computed(() => String(route.params.dispatchId || ""))
const workspace = ref({})
const rows = ref([])
const loading = ref(true)
const ready = ref(false)
const loadError = ref("")
const busy = ref(false)
const actionError = ref("")
const dispatchOpen = ref(false)
const stockEntryOpen = ref(false)
const stockEntryName = ref("")
const stock = reactive({ from_supplier: "", from_warehouse: "", to_supplier: "", to_warehouse: "", goods_value: null, vehicle_no: "" })
const entries = new Map()
const rowsVersion = ref(0)
const record = computed(() => workspace.value.record || {})
const permissions = computed(() => workspace.value.permissions || {})
const draft = computed(() => Number(record.value.docstatus || 0) === 0)
const statusLabel = computed(() => {
	if (Number(record.value.docstatus) === 2) return "Cancelled"
	if (Number(record.value.docstatus) === 1) return record.value.stock_entry ? "Dispatched" : "Submitted"
	return "Draft"
})
let loadSequence = 0

function setEntry(planName, component) {
	if (component) entries.set(planName, component)
	else entries.delete(planName)
}

function applyWorkspace(data) {
	workspace.value = data || {}
	rows.value = data?.items || []
	rowsVersion.value += 1
	ready.value = true
}

async function load() {
	const sequence = ++loadSequence
	loading.value = true
	loadError.value = ""
	try {
		const data = await getDispatchWorkspace(dispatchId.value)
		if (sequence === loadSequence) applyWorkspace(data)
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load this Finishing Plan Dispatch."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function collectItems() {
	return rows.value.map((row) => {
		const values = entries.get(row.doc_name)?.values?.() || { quantities: {}, colour_details: {}, packing_batch_dispatches: [] }
		return {
			...row,
			values: Object.fromEntries(Object.entries(row.values || {}).map(([size, value]) => [size, { ...value, dispatch_qty: Number(values.quantities[size]) || 0 }])),
			batch_dispatches: values.packing_batch_dispatches.map(({ batch_row: batchRow, box_quantity: boxQuantity }) => ({ batch_row: batchRow, box_quantity: boxQuantity })),
			colour_grid: values.colour_details,
		}
	})
}

async function run(request, message, after = null) {
	if (busy.value) return null
	busy.value = true
	actionError.value = ""
	try {
		const data = await request()
		toast.add({ severity: "success", summary: message, detail: data?.record?.name || "", life: 3500 })
		if (after) await after(data)
		return data
	} catch (reason) {
		actionError.value = reason?.message || "Unable to complete this Finishing Plan Dispatch action."
		return null
	} finally {
		busy.value = false
	}
}

function save(submit) {
	run(() => saveDispatch(collectItems(), dispatchId.value, submit, record.value.modified), submit ? "Finishing Plan Dispatch submitted" : "Finishing Plan Dispatch saved", async (data) => {
		applyWorkspace(data)
		if (!dispatchId.value && data?.record?.name) await router.replace({ name: "finishing-dispatch", params: { dispatchId: data.record.name }, state: preserveListNavigationState(data.record.name, data.record.modified) })
	})
}

function confirmFetch() {
	confirmAction({ header: "Fetch Items?", message: "Fetch the latest packed balances? Quantities entered on this page are replaced.", acceptLabel: "Fetch Items", acceptIcon: "pi pi-refresh", acceptSeverity: "primary", rejectLabel: "Keep Entries", accept: () => run(fetchDispatchItems, "Finishing Plans fetched", (items) => { rows.value = items || []; rowsVersion.value += 1 }) })
}

async function setSupplier(side, supplier) {
	const message = await setDispatchSupplier(stock, side, supplier)
	if (message) actionError.value = message
}

function dispatchStock() {
	const missing = [["from_supplier", "From Supplier"], ["from_warehouse", "From Warehouse"], ["to_supplier", "To Supplier"], ["to_warehouse", "To Warehouse"], ["goods_value", "Goods Value"], ["vehicle_no", "Vehicle No"]].filter(([field]) => stock[field] === null || stock[field] === "").map(([, label]) => label)
	if (missing.length) {
		actionError.value = `Enter ${missing.join(", ")}.`
		return
	}
	run(() => executeDispatchCommand(record.value.name, "dispatch_stock", { ...stock }, record.value.modified), "Stock dispatched", (data) => {
		applyWorkspace(data)
		dispatchOpen.value = false
	})
}

function confirmCancel() {
	confirmAction({ header: "Cancel dispatch?", message: `Cancel ${record.value.name}? Its submitted Stock Entry is cancelled too.`, acceptLabel: "Cancel Dispatch", acceptIcon: "pi pi-ban", accept: () => run(() => executeDispatchCommand(record.value.name, "cancel", {}, record.value.modified), "Finishing Plan Dispatch cancelled", applyWorkspace) })
}

function openStockEntry(name = record.value.stock_entry) {
	stockEntryName.value = name
	stockEntryOpen.value = true
}

watch(dispatchId, () => {
	ready.value = false
	entries.clear()
	load()
}, { immediate: true })
</script>

<style scoped>
.finishing-dispatch { display: grid; min-width: 0; gap: var(--erp-space-4); padding: 12px 14px; }
.finishing-dispatch__header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--erp-border); }
.finishing-dispatch__identity { display: flex; flex: 1 1 auto; flex-wrap: wrap; align-items: center; gap: 10px 14px; min-width: 0; }
.finishing-dispatch__title { display: grid; gap: 3px; }
.finishing-dispatch__title h1 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-title); font-weight: 760; letter-spacing: -0.025em; line-height: 1.05; white-space: nowrap; }
.finishing-dispatch__title span { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 620; font-variant-numeric: tabular-nums; }
.finishing-dispatch__meta { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; }
.finishing-dispatch__actions { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; }
.finishing-dispatch__plan { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px; margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: 700; }
.finishing-dispatch__link { padding: 0; color: var(--erp-accent-dark); background: none; border: 0; font: inherit; font-size: var(--erp-font-size-table); font-weight: 650; cursor: pointer; text-decoration: none; }
.finishing-dispatch__link:hover, .finishing-dispatch__link:focus-visible { text-decoration: underline; }
.finishing-dispatch__form { display: grid; gap: 12px; }
.finishing-plan__probe { display: grid; gap: var(--erp-space-3); }
.finishing-plan__fact { display: grid; gap: 2px; padding-left: 12px; border-left: 1px solid var(--erp-border); }
.finishing-plan__fact small { color: var(--erp-text-muted); font-size: var(--erp-font-size-label); font-weight: 720; letter-spacing: .035em; text-transform: uppercase; }
.finishing-plan__fact strong { color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: 730; }
</style>
