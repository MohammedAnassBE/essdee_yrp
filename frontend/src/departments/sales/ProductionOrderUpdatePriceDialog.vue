<template>
	<Dialog :visible="visible" modal header="Update Price" class="erp-dialog--xl ppo-price-dialog" :dismissable-mask="false" :closable="!busy" :close-on-escape="!busy" @update:visible="emit('update:visible', $event)">
		<div class="ppo-price-body" :aria-busy="loading || busy">
			<Message v-if="loadError || error" severity="error" :closable="false">{{ loadError || error }}</Message>
			<template v-if="loading"><Skeleton v-for="index in 5" :key="index" height="3rem" /></template>
			<template v-else-if="!loadError">
				<section class="ppo-price-panel">
					<div class="ppo-price-scroll" role="region" tabindex="0" aria-label="Production Order MRP by size">
						<table v-entry-table="{ fixed: false }" class="ppo-price-table">
							<thead><tr><th scope="col">Size</th><th v-for="size in primaryValues" :key="size" scope="col">{{ size }}</th><th scope="col">Total</th><th scope="col">Select</th></tr></thead>
							<tbody>
								<tr v-for="row in matrixRows" :key="row.key">
									<th scope="row">{{ row.label }}</th>
									<td v-for="size in primaryValues" :key="size"><input type="number" class="ppo-price-input" :value="displayValue(items[size][row.key])" :aria-label="`${size} ${row.label}`" disabled /></td>
									<td>{{ row.key === 'qty' ? totalQuantity : '' }}</td>
									<td>
										<div v-if="row.source" class="ppo-price-option" :class="{ 'ppo-price-option--disabled': !sourceAvailable(row.source) }">
											<RadioButton v-model="selectedSource" :input-id="`${dialogId}-${row.source}`" :name="`${dialogId}-source`" :value="row.source" :disabled="!sourceAvailable(row.source)" />
											<label :for="`${dialogId}-${row.source}`">Use</label>
										</div>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
				<section v-if="lots.length" class="ppo-price-panel">
					<header class="ppo-price-header">
						<strong>Lot-wise MRP</strong>
						<div class="ppo-price-bulk">
							<span>Update all:</span>
							<div v-for="source in lotSourceOptions" :key="source.value" class="ppo-price-option" :class="{ 'ppo-price-option--disabled': !lotSourceAvailable(source.value) }">
								<RadioButton v-model="bulkLotSource" :input-id="`${dialogId}-bulk-${source.value}`" :name="`${dialogId}-bulk`" :value="source.value" :disabled="!lotSourceAvailable(source.value)" />
								<label :for="`${dialogId}-bulk-${source.value}`">{{ source.label }}</label>
							</div>
							<Button label="Update All" size="small" :disabled="!bulkLotSource || !lotSourceAvailable(bulkLotSource) || !hasUnlockedLots()" @click="applyLotSourceToAll" />
							<span class="ppo-price-muted">Unprinted lots only</span>
						</div>
					</header>
					<div class="ppo-price-scroll" role="region" tabindex="0" aria-label="Lot-wise MRP">
						<table v-entry-table="{ fixed: false }" class="ppo-price-table">
							<thead><tr><th scope="col">Lot</th><th scope="col">Status</th><th scope="col">Price Source</th><th v-for="size in primaryValues" :key="size" scope="col">{{ size }}</th></tr></thead>
							<tbody>
								<tr v-for="(lot, lotIndex) in lots" :key="lot.lot">
									<th scope="row" class="ppo-price-lot">{{ lot.lot }}</th>
									<td><span class="ppo-price-status" :class="`ppo-price-status--${lot.locked ? 'danger' : lotHasCompletePrice(lot) ? 'success' : 'warning'}`">{{ lotStatusLabel(lot) }}</span></td>
									<td>
										<span v-if="lot.locked" class="ppo-price-muted">Sticker snapshot</span>
										<div v-else class="ppo-price-options">
											<div v-for="source in lotSourceOptions" :key="source.value" class="ppo-price-option" :class="{ 'ppo-price-option--disabled': !lotSourceAvailable(source.value) }">
												<RadioButton v-model="lot.selected_source" :input-id="`${dialogId}-lot-${lotIndex}-${source.value}`" :name="`${dialogId}-lot-${lotIndex}`" :value="source.value" :disabled="!lotSourceAvailable(source.value)" @change="applyLotSource(lot, source.value)" />
												<label :for="`${dialogId}-lot-${lotIndex}-${source.value}`">{{ source.label }}</label>
											</div>
											<span v-if="lot.selected_source === 'manual'" class="ppo-price-muted">Custom</span>
										</div>
									</td>
									<td v-for="size in primaryValues" :key="size">
										<strong v-if="lot.locked">{{ displayValue(lotPrice(lot, size).effective_mrp) }}</strong>
										<input v-else v-model="lotPrice(lot, size).override_mrp" type="number" min="0" step="0.01" class="ppo-price-input" :placeholder="String(selectedPpoMrp(size) || '')" :aria-label="`${lot.lot} ${size} MRP`" @input="markLotManual(lot)" />
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			</template>
		</div>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="emit('update:visible', false)" />
			<Button label="Submit" :loading="busy" :disabled="busy || loading || Boolean(loadError)" @click="submit" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import RadioButton from "primevue/radiobutton"
import Skeleton from "primevue/skeleton"
import { computed, ref, useId, watch } from "vue"

import { getPriceUpdateContext } from "../../api/sales.js"
import { vEntryTable } from "../../components/common/childGrid/entryTable.js"

const props = defineProps({ visible: Boolean, productionOrder: { type: String, required: true }, busy: Boolean, error: { type: String, default: "" } })
const emit = defineEmits(["update:visible", "submit"])
const dialogId = useId()
const loading = ref(false)
const loadError = ref("")
const primaryValues = ref([])
const items = ref({})
const lots = ref([])
const selectedSource = ref("production_order_mrp")
const bulkLotSource = ref(null)
let loadSequence = 0
const matrixRows = [
	{ key: "qty", label: "Qty" },
	{ key: "ratio", label: "Ratio" },
	{ key: "sales_mrp", label: "Sales Item MRP", source: "sales_mrp" },
	{ key: "box_sticker_mrp", label: "Box Sticker MRP", source: "box_sticker_mrp" },
	{ key: "production_order_mrp", label: "Production Order MRP", source: "production_order_mrp" },
]
const lotSourceOptions = [{ value: "sales_mrp", label: "Sales Item" }, { value: "box_sticker_mrp", label: "Box Sticker" }]
const totalQuantity = computed(() => primaryValues.value.reduce((total, size) => total + items.value[size].qty, 0))

watch(() => [props.visible, props.productionOrder], ([visible]) => {
	const sequence = ++loadSequence
	if (visible) load(sequence)
}, { immediate: true })

async function load(sequence) {
	loading.value = true
	loadError.value = ""
	primaryValues.value = []; items.value = {}; lots.value = []
	selectedSource.value = "production_order_mrp"; bulkLotSource.value = null
	try {
		const payload = await getPriceUpdateContext(props.productionOrder)
		if (sequence === loadSequence) loadData(payload)
	} catch (reason) {
		if (sequence === loadSequence) loadError.value = reason?.message || "Unable to load price update details."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function normalizeKey(value) { return value === null || value === undefined ? "" : String(value).trim() }
function getNormalizedPrimaryValues(values, normalizedItems = {}) {
	const normalized = []
	const seen = new Set()
	function append(value) {
		const key = normalizeKey(value)
		if (!key || seen.has(key)) return
		seen.add(key); normalized.push(key)
	}
	for (const value of values || []) append(value)
	if (!normalized.length) Object.keys(normalizedItems || {}).forEach(append)
	return normalized
}
function getNormalizedItems(values = {}) {
	const normalized = {}
	Object.entries(values || {}).forEach(([key, value]) => {
		const normalizedKey = normalizeKey(key)
		if (normalizedKey) normalized[normalizedKey] = value || {}
	})
	return normalized
}
function loadData(data) {
	const payload = JSON.parse(JSON.stringify(data || {}))
	const normalizedItems = getNormalizedItems(payload.items)
	primaryValues.value = getNormalizedPrimaryValues(payload.primary_values, normalizedItems)
	items.value = {}
	primaryValues.value.forEach((size) => {
		const row = normalizedItems[size] || {}
		items.value[size] = {
			qty: Number(row.qty || 0),
			ratio: Number(row.ratio || 0),
			sales_mrp: row.sales_mrp,
			box_sticker_mrp: row.box_sticker_mrp,
			production_order_mrp: Number(row.production_order_mrp || 0),
			has_sales_mrp: Boolean(row.has_sales_mrp),
			has_box_sticker_mrp: Boolean(row.has_box_sticker_mrp),
			selected_source: row.selected_source || "production_order_mrp",
		}
	})
	selectedSource.value = getSelectedSourceFromRows() || "production_order_mrp"
	bulkLotSource.value = null
	lots.value = (payload.lots || []).map((lot) => {
		const prices = {}
		primaryValues.value.forEach((size) => {
			const price = (lot.prices || {})[size] || {}
			prices[size] = { ...price, override_mrp: price.override_mrp === null || price.override_mrp === undefined ? null : Number(price.override_mrp) }
		})
		const normalizedLot = { ...lot, prices, selected_source: null }
		normalizedLot.selected_source = inferLotSource(normalizedLot)
		return normalizedLot
	})
}
function displayValue(value) { return value === null || value === undefined ? "" : value }
function getSelectedSourceFromRows() {
	for (const size of primaryValues.value) {
		if (items.value[size]?.selected_source) return items.value[size].selected_source
	}
	return null
}
function sourceAvailable(source) {
	if (source === "production_order_mrp") return true
	return primaryValues.value.every((size) => items.value[size][`has_${source}`] && Number(items.value[size][source]) > 0)
}
function lotPrice(lot, size) {
	if (!lot.prices[size]) lot.prices[size] = { override_mrp: null, effective_mrp: selectedPpoMrp(size), printed_quantity: 0 }
	return lot.prices[size]
}
function selectedPpoMrp(size) {
	const row = items.value[size] || {}
	if (selectedSource.value === "sales_mrp" && row.has_sales_mrp) return row.sales_mrp
	if (selectedSource.value === "box_sticker_mrp" && row.has_box_sticker_mrp) return row.box_sticker_mrp
	return row.production_order_mrp
}
function lotSourceValue(source, size) {
	const row = items.value[size] || {}
	return source === "sales_mrp" ? row.sales_mrp : source === "box_sticker_mrp" ? row.box_sticker_mrp : null
}
function lotSourceAvailable(source) {
	return Boolean(primaryValues.value.length) && primaryValues.value.every((size) => Number(lotSourceValue(source, size)) > 0)
}
function applyLotSource(lot, source) {
	if (lot.locked || !lotSourceAvailable(source)) return
	lot.selected_source = source
	primaryValues.value.forEach((size) => {
		const price = lotPrice(lot, size)
		price.override_mrp = Number(lotSourceValue(source, size)); price.has_override = true
	})
}
function hasUnlockedLots() { return lots.value.some((lot) => !lot.locked) }
function applyLotSourceToAll() {
	const source = bulkLotSource.value
	if (!source || !lotSourceAvailable(source)) return
	lots.value.forEach((lot) => { if (!lot.locked) applyLotSource(lot, source) })
}
function markLotManual(lot) { lot.selected_source = "manual" }
function lotHasCompletePrice(lot) { return primaryValues.value.every((size) => Number(lotPrice(lot, size).override_mrp) > 0) }
function samePrice(left, right) { return Math.abs(Number(left) - Number(right)) < 0.000001 }
function inferLotSource(lot) {
	if (lot.locked) return "locked"
	if (!lotHasCompletePrice(lot)) return null
	for (const source of lotSourceOptions) {
		if (lotSourceAvailable(source.value) && primaryValues.value.every((size) => samePrice(lotPrice(lot, size).override_mrp, lotSourceValue(source.value, size)))) return source.value
	}
	return "manual"
}
function lotStatusLabel(lot) { return lot.locked ? "Printed · Locked" : lotHasCompletePrice(lot) ? "Price Set" : "Price Required" }
function getItems() {
	const copiedItems = JSON.parse(JSON.stringify(items.value))
	Object.keys(copiedItems).forEach((size) => { copiedItems[size].selected_source = selectedSource.value })
	const lot_price_overrides = {}
	lots.value.forEach((lot) => {
		lot_price_overrides[lot.lot] = {}
		primaryValues.value.forEach((size) => {
			const value = lotPrice(lot, size).override_mrp
			lot_price_overrides[lot.lot][size] = value === "" || value === null || value === undefined ? null : Number(value)
		})
	})
	return { items: copiedItems, lot_price_overrides }
}
function submit() {
	if (!props.busy && !loading.value && !loadError.value) emit("submit", { item_details: getItems() })
}
</script>

<style scoped>
.ppo-price-dialog { min-width: 0; overflow-x: hidden; }
.ppo-price-dialog :deep(.p-dialog-content) { min-width: 0; overflow-x: hidden; }
.ppo-price-body { display: grid; min-width: 0; max-width: 100%; gap: var(--erp-space-3); color: var(--erp-text); }
.ppo-price-body :deep(.p-message) { min-width: 0; overflow-wrap: anywhere; }
.ppo-price-panel { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.ppo-price-header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--erp-space-3); padding: 10px var(--erp-space-3); border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.ppo-price-bulk { display: flex; min-width: 0; flex-wrap: wrap; align-items: center; gap: var(--erp-space-2); font-size: var(--erp-font-size-caption); }
.ppo-price-scroll { max-width: 100%; overflow-x: auto; }
.ppo-price-scroll:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: -2px; }
.ppo-price-table { width: 100%; min-width: max-content; border-collapse: collapse; font-size: var(--erp-font-size-caption); font-variant-numeric: tabular-nums; }
.ppo-price-table th, .ppo-price-table td { padding: 7px var(--erp-space-2); border: 1px solid var(--erp-border); text-align: center; vertical-align: middle; }
.ppo-price-table thead th { background: var(--erp-surface-muted); color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); font-weight: 700; }
.ppo-price-table th:first-child { text-align: left; white-space: nowrap; }
.ppo-price-table tr > :first-child { border-left: 0; }
.ppo-price-table tr > :last-child { border-right: 0; }
.ppo-price-table thead tr:first-child > * { border-top: 0; }
.ppo-price-table tbody tr:last-child > * { border-bottom: 0; }
.ppo-price-input { box-sizing: border-box; width: 76px; padding: 6px var(--erp-space-1); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); background: var(--erp-surface); color: var(--erp-text); text-align: center; font: inherit; font-variant-numeric: tabular-nums; appearance: textfield; }
.ppo-price-input:disabled { background: var(--erp-surface-muted); color: var(--erp-text-secondary); opacity: 1; }
.ppo-price-input:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 1px; }
.ppo-price-input::placeholder { color: var(--erp-text-muted); }
.ppo-price-input::-webkit-inner-spin-button, .ppo-price-input::-webkit-outer-spin-button { margin: 0; appearance: none; }
.ppo-price-option { display: inline-flex; align-items: center; gap: var(--erp-space-1); white-space: nowrap; font-size: var(--erp-font-size-caption); }
.ppo-price-option label { cursor: pointer; }
.ppo-price-option--disabled { color: var(--erp-text-muted); opacity: .65; }
.ppo-price-option--disabled label { cursor: not-allowed; }
.ppo-price-options { display: grid; gap: var(--erp-space-1); text-align: left; }
.ppo-price-muted { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); white-space: nowrap; }
.ppo-price-lot { min-width: 86px; white-space: nowrap; }
.ppo-price-status { display: inline-block; padding: var(--erp-space-1) var(--erp-space-2); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 700; white-space: nowrap; }
.ppo-price-status--success { color: var(--erp-success-text); background: var(--erp-success-soft); }
.ppo-price-status--danger { color: var(--erp-danger); background: var(--erp-danger-soft); }
.ppo-price-status--warning { color: var(--erp-warning); background: var(--erp-warning-soft); }
</style>
