<template>
	<DepartmentPage title="Sales Item Price" back-to="/sales" back-label="Sales" :show-title="false" flat full-width inline-navigation>
		<section class="sales-item-price erp-workspace" aria-label="Sales Item Price">
			<div class="sales-item-price__filters erp-card">
				<LinkField v-model="item" doctype="Item" label="Item" placeholder="Search item…" :filters="{ has_variants: 1 }" :show-open-button="false" show-clear />
				<div class="common-field">
					<label for="sales-item-price-rate-type" class="erp-field-label">Rate Type<span class="erp-required-mark" aria-hidden="true">*</span></label>
					<Select v-model="rateType" input-id="sales-item-price-rate-type" :options="rateTypes" option-label="label" option-value="value" aria-label="Rate Type" fluid />
				</div>
				<div class="common-field">
					<label for="sales-item-price-uom" class="erp-field-label">UOM</label>
					<InputText id="sales-item-price-uom" :model-value="uom" readonly fluid />
				</div>
				<div class="sales-item-price__actions">
					<Button label="Save" icon="pi pi-check" size="small" :disabled="!changeCount" :loading="saving" @click="save" />
				</div>
			</div>

			<Skeleton v-if="loading" height="320px" />
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!items.length" severity="info" :closable="false">{{ item ? "This Item has no sales variants." : "No Sales Item Price found." }}</Message>
			<template v-else>
				<Message v-if="!editable" severity="secondary" :closable="false">{{ permissions.can_write ? "Select an Item to edit its prices." : "You do not have permission to update Sales Item Price." }}</Message>
				<p v-else-if="changeCount" class="sales-item-price__pending">{{ changeCount }} unsaved {{ changeCount === 1 ? "change" : "changes" }}</p>
				<div v-for="group in groups" :key="group.key" class="sales-item-price__table-wrap erp-card" role="region" :aria-label="`${rateLabel} per ${uom}`" tabindex="0">
					<table v-entry-table="{ fixed: false }">
						<thead><tr><th scope="col">Item</th><th v-for="size in group.sizes" :key="size" scope="col">{{ size }}</th></tr></thead>
						<tbody>
							<tr v-for="row in group.items" :key="row.item">
								<th scope="row">{{ row.item_name }}<small v-if="row.item_name !== row.item">{{ row.item }}</small></th>
								<td v-for="size in group.sizes" :key="size">
									<InputNumber v-if="editable" v-model="row.prices[rateType][size]" :min="0" :max-fraction-digits="2" :use-grouping="false" :disabled="isMissing(row, size) && !permissions.can_create" :input-aria-label="`${row.item_name} ${size} ${rateLabel}`" fluid />
									<span v-else>{{ formatRate(row.prices[rateType][size]) }}</span>
								</td>
							</tr>
						</tbody>
					</table>
				</div>
			</template>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, onMounted, ref, watch } from "vue"

import { getSalesItemPriceGrid, saveSalesItemPrices } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import LinkField from "../../components/common/LinkField.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import { vEntryTable } from "../../components/common/childGrid/entryTable.js"
import { DEFAULT_RATE_TYPE, changedPrices, groupBySizes, isPriceEditable } from "./salesItemPrices.js"

const toast = useToast()
const item = ref("")
const rateType = ref(DEFAULT_RATE_TYPE)
const rateTypes = ref([])
const uom = ref("Piece")
const permissions = ref({})
const original = ref([])
const items = ref([])
const loading = ref(true)
const saving = ref(false)
const loadError = ref("")
let loadId = 0

const groups = computed(() => groupBySizes(items.value))
const editable = computed(() => isPriceEditable(item.value, permissions.value))
const changes = computed(() => changedPrices(original.value, items.value, rateType.value))
const changeCount = computed(() => Object.keys(changes.value).length)
const rateLabel = computed(() => rateTypes.value.find((row) => row.value === rateType.value)?.label || "Rate")

function isMissing(row, size) {
	return row.missing.includes(size)
}

function formatRate(value) {
	return Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

async function load() {
	const current = ++loadId
	loading.value = true
	loadError.value = ""
	try {
		const payload = await getSalesItemPriceGrid(item.value)
		if (current !== loadId) return
		rateTypes.value = payload.price_types || []
		uom.value = payload.uom || "Piece"
		permissions.value = payload.permissions || {}
		original.value = payload.items || []
		items.value = structuredClone(payload.items || [])
	} catch (reason) {
		if (current === loadId) loadError.value = reason?.message || "Unable to load Sales Item Price."
	} finally {
		if (current === loadId) loading.value = false
	}
}

async function save() {
	saving.value = true
	try {
		const result = await saveSalesItemPrices(rateType.value, changes.value)
		toast.add({ severity: "success", summary: `${rateLabel.value} saved`, detail: `${result.updated} updated, ${result.created} created`, life: 3500 })
		await load()
	} finally {
		saving.value = false
	}
}

watch(item, load)
onMounted(load)
</script>

<style scoped>
.sales-item-price { display: grid; gap: var(--erp-space-3); width: 100%; min-width: 0; padding: var(--erp-space-2) 0 var(--erp-space-5); }
.sales-item-price__filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); align-items: end; gap: var(--erp-space-3); padding: var(--erp-space-3); }
.sales-item-price__actions { display: flex; justify-content: flex-end; }
.sales-item-price__pending { margin: 0; color: var(--erp-warning-text, #92400e); font-size: var(--erp-font-size-caption); font-weight: 700; }
.sales-item-price__table-wrap { min-width: 0; overflow-x: auto; padding: 0; }
.sales-item-price table { width: 100%; border-collapse: collapse; }
.sales-item-price th, .sales-item-price td { height: 43px; padding: 6px 10px; color: var(--erp-text-secondary); font-size: var(--erp-font-size-caption); text-align: center; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); font-variant-numeric: tabular-nums; }
.sales-item-price thead th { height: 34px; color: var(--erp-text); font-size: var(--erp-font-size-min); font-weight: 780; letter-spacing: .035em; text-transform: uppercase; background: var(--erp-surface-soft); }
.sales-item-price tbody th { min-width: 220px; color: var(--erp-text); font-weight: 720; text-align: left; background: var(--erp-surface-soft); }
.sales-item-price tbody th small { display: block; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 500; }
.sales-item-price tbody tr:hover td { background: var(--erp-surface-hover); }
.sales-item-price :deep(.p-inputnumber) { min-width: 82px; }
.sales-item-price :deep(.p-inputnumber-input) { height: 32px; padding-inline: 8px; text-align: center; }
</style>
