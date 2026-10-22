<template>
	<section class="fabric-stock-transfers" aria-label="Stock Transfers">
		<div class="stock-operation-grid" aria-label="Stock operation">
			<button
				v-for="operation in operations"
				:key="operation.key"
				type="button"
				class="stock-operation-card"
				:class="{ 'stock-operation-card--active': activeOperation === operation.key }"
				:aria-pressed="activeOperation === operation.key"
				@click="activeOperation = operation.key"
			>
				<i :class="operation.icon" aria-hidden="true" />
				<span>{{ operation.label }}</span>
			</button>
		</div>

		<ListView
			v-if="activeCapability"
			ref="listView"
			:key="activeOperation"
			:doctype="activeCapability.doctype"
			:title="activeCapability.label"
			:search-placeholder="`Search ${activeCapability.label}…`"
			:name-column-label="activeCapability.label"
			:row-mark="activeDefinition.mark"
			:min-table-width="activeDefinition.minWidth"
			:default-columns="activeDefinition.columns"
			template-item-filters
			viewport-bounded
			clickable
			@row-click="openDocument"
		>
			<template #toolbar-actions>
				<Button v-if="activeCapability.can_create" class="list-primary-action" label="Create New" icon="pi pi-plus" @click="createDocument" />
			</template>
		</ListView>

		<StockDocumentDialog
			v-if="activeCapability"
			v-model:visible="documentVisible"
			:operation="activeOperation"
			:doctype="activeCapability.doctype"
			:name="selectedDocument.name"
			:docstatus="selectedDocument.docstatus"
			:expected-modified="selectedDocument.modified"
			@changed="documentChanged"
		/>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import { computed, ref, watch } from "vue"

import ListView from "../../components/common/ListView.vue"
import StockDocumentDialog from "./StockDocumentDialog.vue"

const props = defineProps({ capability: { type: Object, required: true } })

const definitions = {
	stock_entry: { label: "Stock Entry", icon: "pi pi-sign-out", mark: "SE", columns: ["purpose", "posting_date", "from_warehouse", "to_warehouse"], minWidth: "980px" },
	stock_reconciliation: { label: "Stock Reconciliation", icon: "pi pi-equals", mark: "SR", columns: ["purpose", "posting_date", "default_warehouse", "default_supplier"], minWidth: "980px" },
	stock_update: { label: "Stock Update", icon: "pi pi-sync", mark: "SU", columns: ["update_type", "posting_date", "warehouse", "supplier"], minWidth: "900px" },
	lot_transfer: { label: "Lot Transfer", icon: "pi pi-arrow-right-arrow-left", mark: "LT", columns: ["posting_date", "posting_time", "modified_by"], minWidth: "820px" },
}

const operations = computed(() => Object.entries(props.capability.operations || {}).map(([key, value]) => ({
	key,
	...definitions[key],
	...value,
})))
const activeOperation = ref(operations.value[0]?.key || "")
const listView = ref(null)
const documentVisible = ref(false)
const selectedDocument = ref({ name: "", docstatus: 0, modified: "" })
const activeCapability = computed(() => props.capability.operations?.[activeOperation.value] || null)
const activeDefinition = computed(() => definitions[activeOperation.value] || { mark: "ST", columns: [], minWidth: "900px" })

watch(operations, (available) => {
	if (!available.some((operation) => operation.key === activeOperation.value)) activeOperation.value = available[0]?.key || ""
})

function createDocument() {
	selectedDocument.value = { name: "", docstatus: 0, modified: "" }
	documentVisible.value = true
}
function openDocument(row) {
	selectedDocument.value = { name: row.name, docstatus: Number(row.docstatus || 0), modified: row.modified || "" }
	documentVisible.value = true
}
function documentChanged() { listView.value?.refresh?.(true) }
</script>

<style scoped>
.fabric-stock-transfers {
	display: grid;
	gap: var(--erp-space-3);
	min-width: 0;
}

@media (min-width: 1025px) {
	.fabric-stock-transfers {
		height: calc(100dvh - var(--erp-shell-header-height) - 80px);
		min-height: 0;
		overflow: hidden;
		grid-template-rows: auto minmax(0, 1fr);
	}

	.fabric-stock-transfers :deep(.common-list-view--viewport-bounded) { height: 100%; }
}

.stock-operation-grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(150px, 1fr));
	gap: var(--erp-space-2);
}

.stock-operation-card {
	display: flex;
	min-height: 46px;
	align-items: center;
	gap: 9px;
	padding: 0 13px;
	color: var(--erp-text-muted);
	font: inherit;
	font-size: var(--erp-font-size-caption);
	font-weight: 750;
	text-align: left;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	cursor: pointer;
	transition: border-color 140ms ease, background 140ms ease, color 140ms ease;
}

.stock-operation-card i { color: #789087; }
.stock-operation-card:hover { border-color: #a8c7ba; }
.stock-operation-card--active {
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
	border-color: #92c9b2;
	box-shadow: inset 3px 0 0 var(--erp-accent);
}
.stock-operation-card--active i { color: var(--erp-accent); }

@media (max-width: 900px) {
	.stock-operation-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 520px) {
	.stock-operation-grid { gap: 7px; }
	.stock-operation-card { min-height: 44px; padding: 0 9px; font-size: 0.72rem; line-height: 1.15; }
}
</style>
