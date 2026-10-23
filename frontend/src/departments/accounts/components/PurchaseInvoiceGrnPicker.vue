<template>
	<section class="purchase-invoice-grn-picker" aria-labelledby="purchase-invoice-grn-picker-title">
		<header>
			<div>
				<span>Receipts</span>
				<h2 id="purchase-invoice-grn-picker-title">Goods Received Notes</h2>
			</div>
			<small>{{ selectedNames.length }} selected</small>
		</header>
		<div class="purchase-invoice-grn-picker__body">
			<label class="purchase-invoice-grn-picker__search-label" :for="inputId">Search GRNs</label>
			<span class="purchase-invoice-grn-picker__search">
				<i class="pi pi-search" aria-hidden="true"></i>
				<InputText
					:id="inputId"
					v-model="searchText"
					aria-label="Search GRNs"
					placeholder="Search by GRN, Against or Supplier Doc No"
					:disabled="!hasDependencies"
					fluid
				/>
			</span>

			<fieldset class="purchase-invoice-grn-picker__selection" :disabled="selectionDisabled">
				<DataTable
					:selection="selectedRows"
					:value="filteredRows"
					:loading="loading"
					:table-props="{ 'aria-label': 'Eligible GRNs' }"
					:table-style="{ minWidth: '900px' }"
					:pt="{ tableContainer: { tabindex: 0, role: 'region', 'aria-label': 'Eligible GRNs' } }"
					class="purchase-invoice-grn-picker__table"
					data-key="name"
					scrollable
					scroll-height="360px"
					size="small"
					row-hover
				>
					<Column header-style="width: 44px" body-style="width: 44px; text-align: center">
						<template #header>
							<Checkbox
								:model-value="allFilteredSelected"
								binary
								aria-label="Select all eligible GRNs"
								:disabled="selectionDisabled || !selectableFilteredRows.length"
								@update:model-value="toggleFilteredRows"
							/>
						</template>
						<template #body="{ data }">
							<Checkbox
								:model-value="selectedNameSet.has(data.name)"
								binary
								:aria-label="`Select ${data.name}`"
								:disabled="selectionDisabled || !isRowSelectable(data)"
								@update:model-value="toggleRow(data, $event)"
							/>
						</template>
					</Column>
					<Column field="name" header="GRN" style="min-width: 150px">
						<template #body="{ data }"><strong>{{ data.name }}</strong></template>
					</Column>
					<Column field="posting_date" header="Date" style="min-width: 112px">
						<template #body="{ data }">{{ formatDisplayDate(data.posting_date) }}</template>
					</Column>
					<Column field="against_id" header="Against" style="min-width: 150px">
						<template #body="{ data }">{{ data.against_id || "—" }}</template>
					</Column>
					<Column field="supplier_document_no" header="Supplier Doc No" style="min-width: 155px">
						<template #body="{ data }">{{ data.supplier_document_no || "—" }}</template>
					</Column>
					<Column field="total_received_quantity" header="Qty" header-class="purchase-invoice-grn-picker__number" body-class="purchase-invoice-grn-picker__number" style="min-width: 90px">
						<template #body="{ data }">{{ number(data.total_received_quantity) }}</template>
					</Column>
					<Column field="selected" header="Status" style="min-width: 125px">
						<template #body="{ data }">
							<Tag
								:value="data.selected ? 'On this invoice' : 'Available'"
								:severity="data.selected ? 'success' : 'secondary'"
							/>
						</template>
					</Column>
					<template #empty>
						<div class="purchase-invoice-grn-picker__empty">{{ emptyMessage }}</div>
					</template>
				</DataTable>
			</fieldset>

			<small v-if="!hasDependencies" class="purchase-invoice-grn-picker__message">
				Select Supplier and Against first
			</small>
			<small v-else-if="error" class="purchase-invoice-grn-picker__error" role="alert">{{ error }}</small>
			<small v-else class="purchase-invoice-grn-picker__message">
				{{ selectedNames.length >= MAXIMUM_GRNS ? "A maximum of 200 GRNs can be selected." : "Select up to 200 GRNs." }}
			</small>
		</div>
	</section>
</template>

<script setup>
import Column from "primevue/column"
import Checkbox from "primevue/checkbox"
import DataTable from "primevue/datatable"
import InputText from "primevue/inputtext"
import Tag from "primevue/tag"
import { computed, onBeforeUnmount, ref, useId, watch } from "vue"

import { getEligibleGrns } from "../../../api/accounts.js"
import { formatDisplayDate } from "../../../utils/dateFormat.js"
import {
	addGrnsWithinLimit,
	filterEligibleGrns,
	isMaskedValue,
	mergeKnownGrns,
} from "../accountsViews.js"

const MAXIMUM_GRNS = 200
const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	supplier: { type: String, default: "" },
	against: { type: String, default: "" },
	purchaseInvoice: { type: String, default: "" },
	billTracking: { type: String, default: "" },
	disabled: { type: Boolean, default: false },
})
const emit = defineEmits(["update:modelValue"])
const componentId = useId()
const knownRows = ref([])
const searchText = ref("")
const loading = ref(false)
const error = ref("")
let requestSequence = 0
let searchTimer = null
let suppressSearchReload = false

const inputId = computed(() => `purchase-invoice-grns-${componentId}`)
const hasDependencies = computed(() => Boolean(props.supplier && props.against))
const selectionDisabled = computed(() => props.disabled || !hasDependencies.value || loading.value)
const selectedNames = computed(() => addGrnsWithinLimit([], props.modelValue, MAXIMUM_GRNS))
const selectedNameSet = computed(() => new Set(selectedNames.value))
const rowsByName = computed(() => new Map(knownRows.value.map((row) => [row.name, row])))
const filteredRows = computed(() => filterEligibleGrns(knownRows.value, searchText.value, selectedNames.value))
const selectedRows = computed(() => selectedNames.value.map((name) => rowsByName.value.get(name)).filter(Boolean))
const selectableFilteredRows = computed(() => filteredRows.value.filter(isRowSelectable))
const allFilteredSelected = computed(() => Boolean(selectableFilteredRows.value.length)
	&& selectableFilteredRows.value.every((row) => selectedNameSet.value.has(row.name)))
const emptyMessage = computed(() => {
	if (!hasDependencies.value) return "Select Supplier and Against first"
	if (loading.value) return "Loading eligible GRNs…"
	if (error.value) return error.value
	if (searchText.value.trim()) return "No matching GRNs found"
	return "No eligible GRNs found"
})

watch(
	() => [props.supplier, props.against, props.purchaseInvoice, props.billTracking],
	() => {
		if (searchTimer) clearTimeout(searchTimer)
		requestSequence += 1
		suppressSearchReload = Boolean(searchText.value)
		searchText.value = ""
		knownRows.value = mergeKnownGrns([], [], selectedNames.value)
		loadEligibleGrns("")
	},
	{ immediate: true },
)

watch(searchText, (value) => {
	if (suppressSearchReload) {
		suppressSearchReload = false
		return
	}
	if (searchTimer) clearTimeout(searchTimer)
	requestSequence += 1
	if (!hasDependencies.value) return
	searchTimer = setTimeout(() => {
		searchTimer = null
		loadEligibleGrns(value)
	}, 300)
})

watch(selectedNames, (names) => {
	knownRows.value = mergeKnownGrns(knownRows.value, [], names)
})

onBeforeUnmount(() => {
	if (searchTimer) clearTimeout(searchTimer)
	requestSequence += 1
})

async function loadEligibleGrns(query = searchText.value) {
	const sequence = ++requestSequence
	error.value = ""
	loading.value = false
	if (!hasDependencies.value) return
	loading.value = true
	try {
		const result = await getEligibleGrns({
			supplier: isMaskedValue(props.supplier) ? undefined : props.supplier,
			against: props.against,
			purchaseInvoice: props.purchaseInvoice || undefined,
			billTracking: props.billTracking || undefined,
			searchText: String(query || "").trim() || undefined,
			limit: MAXIMUM_GRNS,
		})
		if (sequence !== requestSequence) return
		knownRows.value = mergeKnownGrns(
			knownRows.value,
			Array.isArray(result) ? result : [],
			selectedNames.value,
		)
	} catch (reason) {
		if (sequence !== requestSequence) return
		error.value = reason?.message || "Unable to load eligible GRNs."
	} finally {
		if (sequence === requestSequence) loading.value = false
	}
}

function toggleFilteredRows(checked) {
	if (selectionDisabled.value) return
	const filteredNames = new Set(filteredRows.value.map((row) => row.name))
	if (!checked) {
		updateSelection(selectedNames.value.filter((name) => !filteredNames.has(name)))
		return
	}
	updateSelection(addGrnsWithinLimit(selectedNames.value, filteredNames, MAXIMUM_GRNS))
}

function toggleRow(row, checked) {
	if (selectionDisabled.value) return
	if (!checked) {
		updateSelection(selectedNames.value.filter((name) => name !== row.name))
		return
	}
	if (isRowSelectable(row)) updateSelection(addGrnsWithinLimit(selectedNames.value, [row.name], MAXIMUM_GRNS))
}

function updateSelection(values) {
	if (props.disabled) return
	emit("update:modelValue", addGrnsWithinLimit([], values, MAXIMUM_GRNS))
}

function isRowSelectable(row) {
	return selectedNameSet.value.has(row.name) || selectedNames.value.length < MAXIMUM_GRNS
}

function number(value) {
	if (value === null || value === undefined || value === "") return "—"
	const numericValue = Number(value)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "—"
}
</script>

<style scoped>
.purchase-invoice-grn-picker { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 5px 18px rgb(28 61 45 / 3.5%); }
.purchase-invoice-grn-picker > header { display: flex; min-height: 48px; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.purchase-invoice-grn-picker > header > div { display: grid; gap: 2px; }
.purchase-invoice-grn-picker > header span { color: var(--erp-accent-dark); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .055em; text-transform: uppercase; }
.purchase-invoice-grn-picker h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.purchase-invoice-grn-picker > header small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-variant-numeric: tabular-nums; }
.purchase-invoice-grn-picker__body { display: grid; gap: 8px; padding: 12px; }
.purchase-invoice-grn-picker__search-label { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.purchase-invoice-grn-picker__search { position: relative; display: block; }
.purchase-invoice-grn-picker__search > i { position: absolute; z-index: 1; top: 50%; left: 12px; color: var(--erp-text-muted); transform: translateY(-50%); }
.purchase-invoice-grn-picker__search :deep(.p-inputtext) { width: 100%; padding-left: 35px; border-color: var(--erp-border-strong); box-shadow: var(--erp-shadow-xs); }
.purchase-invoice-grn-picker__selection { min-width: 0; margin: 0; padding: 0; border: 0; }
.purchase-invoice-grn-picker__table { overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.purchase-invoice-grn-picker__table :deep(.p-datatable-table-container:focus-visible) { outline: 2px solid var(--erp-accent-dark); outline-offset: -2px; }
.purchase-invoice-grn-picker__table :deep(.p-datatable-thead > tr > th) { padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x); color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 800; letter-spacing: .04em; text-transform: uppercase; background: var(--erp-surface-muted); border-color: var(--erp-border); }
.purchase-invoice-grn-picker__table :deep(.p-datatable-tbody > tr) { background: var(--erp-surface); }
.purchase-invoice-grn-picker__table :deep(.p-datatable-tbody > tr > td) { padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x); color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); border-color: var(--erp-border-subtle); }
.purchase-invoice-grn-picker__table :deep(.p-datatable-tbody > tr:hover) { background: color-mix(in srgb, var(--erp-accent) 4%, var(--erp-surface)); }
.purchase-invoice-grn-picker__table :deep(.p-datatable-tbody > tr.p-datatable-row-selected) { background: color-mix(in srgb, var(--erp-accent) 9%, var(--erp-surface)); }
.purchase-invoice-grn-picker__table :deep(.p-tag) { padding: 3px 7px; font-size: var(--erp-font-size-min); white-space: nowrap; }
.purchase-invoice-grn-picker__table :deep(.purchase-invoice-grn-picker__number) { text-align: right !important; font-variant-numeric: tabular-nums; }
.purchase-invoice-grn-picker__table :deep(.purchase-invoice-grn-picker__number .p-datatable-column-header-content) { justify-content: flex-end; }
.purchase-invoice-grn-picker__empty { display: grid; min-height: 92px; color: var(--erp-text-muted); place-content: center; }
.purchase-invoice-grn-picker__message, .purchase-invoice-grn-picker__error { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.purchase-invoice-grn-picker__error { color: var(--erp-danger); }
</style>
