<template>
	<section ref="root" class="erp-transfer-workspace">
		<div v-if="loading && !loaded" class="erp-workspace-loading"><Skeleton v-for="index in 5" :key="index" height="4.6rem" /></div>
		<WorkspaceLoadError v-else-if="error && !loaded" title="Stock Transfers unavailable" :message="error" :loading="loading" @retry="load(true)" />
		<template v-else-if="loaded">
			<header class="erp-workspace-header">
				<h2>Stock Transfers</h2>
				<Button icon="pi pi-refresh" label="Refresh" severity="secondary" outlined size="small" :loading="loading" @click="load(true)" />
			</header>

			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

			<nav v-if="visibleTabs.length" class="erp-activity-overview" :style="{ '--activity-columns': Math.min(visibleTabs.length, 5) }" aria-label="Stock transfer summary">
				<button v-for="item in visibleTabs" :key="item.value" type="button" :class="{ 'erp-activity-card--active': activeTab === item.value }" class="erp-activity-card" @click="activeTab = item.value">
					<i :class="item.icon"></i><span><small>{{ item.label }}</small><strong>{{ transactions(item.value).length }}</strong></span>
				</button>
			</nav>

			<div v-if="visibleTabs.length" class="erp-panel-stack">
				<div v-if="showCreateActions" class="erp-create-actions">
					<Button v-if="activeItem.movementSource && workspace.permissions?.movement?.can_read && workspace.permissions?.[activeItem.value]?.can_create" :label="activeItem.sourceAction" icon="pi pi-box" severity="secondary" outlined size="small" :disabled="!eligibleMovements.length" @click="openMovementTransaction(null, activeItem.value)" />
					<Button v-if="activeItem.workOrderSource && workspace.permissions?.[activeItem.value]?.can_create" :label="activeItem.workOrderAction" icon="pi pi-briefcase" size="small" @click="workOrderDeliveryOpen = true" />
					<Button v-if="activeItem.creatable && workspace.permissions?.[activeItem.value]?.can_create" :label="activeItem.createLabel" icon="pi pi-plus" size="small" @click="openStockOperation(activeItem.value)" />
				</div>

				<Message v-if="activeItem.movementSource && workspace.permissions?.movement?.can_read && !eligibleMovements.length" severity="info" :closable="false">A submitted, unlinked Cut Panel Movement is required for this action.</Message>

				<div v-if="activeTransactions.length" class="erp-transaction-list">
					<button v-for="record in activeTransactions" :key="record.name" type="button" class="erp-transaction-card" @click="openTransaction(record)">
						<i :class="activeItem.icon"></i><span><strong>{{ record.name }}</strong><small>{{ record.purpose || record.update_type || activeItem.label }} · {{ formatDate(record.modified, true) }}</small></span><DocumentStatusBadge :docstatus="record.docstatus" :label="record.status" /><i class="pi pi-chevron-right"></i>
					</button>
				</div>
				<div v-else class="erp-empty-state"><i :class="activeItem.icon"></i><strong>No {{ activeItem.label.toLowerCase() }} records</strong><span>{{ activeItem.emptyText }}</span></div>
			</div>
			<div v-else class="erp-empty-state"><i class="pi pi-lock"></i><strong>No permitted stock-transfer records</strong></div>
		</template>

		<CpmStockOperationDialog v-model:visible="stockOperationOpen" :cutting-plan="cuttingPlan" :operation="selectedOperation" :permissions="workspace.permissions?.[selectedOperation] || {}" @changed="changed" />
		<CpmMovementTransactionDialog v-model:visible="movementTransactionOpen" :cutting-plan="cuttingPlan" :movement="movementTransactionSource" :movements="eligibleMovements" :operation="movementTransactionOperation" :context="workspace.context || {}" :permissions="workspace.permissions?.[movementTransactionOperation] || {}" @changed="changed" />
		<WorkOrderDeliveryDialog v-model:visible="workOrderDeliveryOpen" :cutting-plan="cuttingPlan" :permissions="workspace.permissions?.delivery_challan || {}" @changed="changed" />
		<CpmTransactionDialog v-model:visible="transactionOpen" :cutting-plan="cuttingPlan" :transaction="selectedTransaction" @changed="changed" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import CpmMovementTransactionDialog from "./CpmMovementTransactionDialog.vue"
import CpmStockOperationDialog from "./CpmStockOperationDialog.vue"
import CpmTransactionDialog from "./CpmTransactionDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import WorkOrderDeliveryDialog from "./WorkOrderDeliveryDialog.vue"
import { getCpmWorkspace } from "./cpmApi.js"

const props = defineProps({ cuttingPlan: { type: String, required: true } })
const emit = defineEmits(["changed"])
const root = ref(null)
const loaded = ref(false)
const loading = ref(false)
const error = ref("")
const activeTab = ref("stock_entry")
const workspace = reactive({ context: {}, permissions: {}, movements: [], transactions: {} })
const stockOperationOpen = ref(false)
const selectedOperation = ref("stock_entry")
const movementTransactionOpen = ref(false)
const movementTransactionSource = ref(null)
const movementTransactionOperation = ref("stock_entry")
const workOrderDeliveryOpen = ref(false)
const transactionOpen = ref(false)
const selectedTransaction = ref(null)
let observer = null
let loadSequence = 0

const tabs = [
	{ value: "stock_entry", label: "Stock Entry", icon: "pi pi-arrow-right-arrow-left", creatable: true, movementSource: true, createLabel: "Plan Stock Entry", sourceAction: "From CPM", description: "Issue, consume, or send current Cutting Plan stock.", emptyText: "No Stock Entries were created from this Cutting Plan." },
	{ value: "stock_update", label: "Stock Update", icon: "pi pi-chart-line", creatable: true, createLabel: "New Stock Update", description: "Add or reduce stock with controlled item entry.", emptyText: "No Stock Updates were created from this Cutting Plan." },
	{ value: "stock_reconciliation", label: "Stock Reconciliation", icon: "pi pi-sliders-h", creatable: true, createLabel: "New Reconciliation", description: "Record counted stock by item, attributes, and stock dimensions.", emptyText: "No stock reconciliation was created from this Cutting Plan." },
	{ value: "lot_transfer", label: "Lot Transfer", icon: "pi pi-directions-alt", creatable: true, createLabel: "New Lot Transfer", description: "Enter item quantities to move between lots.", emptyText: "No Lot Transfers were created from this Cutting Plan." },
	{ value: "delivery_challan", label: "Delivery Challan", icon: "pi pi-truck", movementSource: true, sourceAction: "From CPM", workOrderSource: true, workOrderAction: "From Work Order", description: "Create same-location Work Order dispatches from a movement or deliverables.", emptyText: "No Delivery Challans were created from this Cutting Plan." },
]

const visibleTabs = computed(() => tabs.filter((item) => workspace.permissions?.[item.value]?.can_read))
const eligibleMovements = computed(() => (workspace.movements || []).filter((movement) => movement.docstatus === 1 && !movement.against_id && !movement.active_root_transactions?.length))
const activeItem = computed(() => visibleTabs.value.find((item) => item.value === activeTab.value) || visibleTabs.value[0] || tabs[0])
const activeTransactions = computed(() => transactions(activeItem.value.value))
const showCreateActions = computed(() => Boolean(
	(activeItem.value.movementSource || activeItem.value.workOrderSource || activeItem.value.creatable)
	&& workspace.permissions?.[activeItem.value.value]?.can_create
))

onMounted(async () => {
	await nextTick()
	if ("IntersectionObserver" in window) {
		observer = new IntersectionObserver((entries) => { if (entries.some((entry) => entry.isIntersecting)) load() }, { threshold: 0.01 })
		if (root.value) observer.observe(root.value)
	} else load()
})
onBeforeUnmount(() => observer?.disconnect())
watch(() => props.cuttingPlan, () => { loaded.value = false; load(true) })
watch(visibleTabs, (items) => {
	if (!items.some((item) => item.value === activeTab.value)) activeTab.value = items[0]?.value || ""
})

async function load(force = false) {
	if ((!force && loaded.value) || loading.value || !props.cuttingPlan) return
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	try {
		const data = await getCpmWorkspace(props.cuttingPlan)
		if (sequence !== loadSequence) return
		Object.assign(workspace, data || {})
		loaded.value = true
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason.message || "Unable to load Stock Transfers."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function transactions(operation) { return workspace.transactions?.[operation] || [] }
function openStockOperation(operation) { selectedOperation.value = operation; stockOperationOpen.value = true }
function openMovementTransaction(movement, operation) { movementTransactionSource.value = movement; movementTransactionOperation.value = operation; movementTransactionOpen.value = true }
function openTransaction(record) { selectedTransaction.value = record; transactionOpen.value = true }
async function changed(value) { await load(true); emit("changed", value) }
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} ${match[4]}:${match[5]}` : date }

defineExpose({ load, activate: () => load(true) })
</script>

<style scoped>
.erp-transfer-workspace,
.erp-panel-stack {
	display: grid;
	min-height: 0;
	gap: var(--erp-space-3);
}

.erp-workspace-loading {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--erp-space-3);
}

.erp-workspace-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-4);
}

.erp-workspace-header h2 {
	margin: 0;
	color: var(--erp-text);
	font-size: 18px;
	font-weight: 760;
	letter-spacing: -0.015em;
}

.erp-create-actions {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: var(--erp-space-2);
}

.erp-activity-overview {
	display: grid;
	grid-template-columns: repeat(var(--activity-columns, 5), minmax(0, 1fr));
	gap: var(--erp-space-2);
}

.erp-activity-card {
	display: flex;
	min-height: 64px;
	align-items: center;
	gap: 10px;
	padding: 10px var(--erp-space-3);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	text-align: left;
	transition: background var(--erp-transition-fast), border-color var(--erp-transition-fast);
}

.erp-activity-card:hover,
.erp-activity-card--active {
	border-color: var(--erp-accent-border);
	background: var(--erp-mint);
}

.erp-activity-card--active {
	box-shadow: inset 3px 0 0 var(--erp-accent);
}

.erp-activity-card > i,
.erp-transaction-card > i:first-child {
	display: grid;
	width: 32px;
	height: 32px;
	flex: 0 0 32px;
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
	border-radius: var(--erp-control-radius);
	place-items: center;
}

.erp-activity-card span {
	display: grid;
	min-width: 0;
	gap: 2px;
}

.erp-activity-card small {
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.erp-activity-card strong {
	color: var(--erp-text);
	font-size: 15px;
	font-variant-numeric: tabular-nums;
}

.erp-transaction-list {
	display: grid;
	gap: var(--erp-space-2);
}

.erp-transaction-card {
	display: grid;
	grid-template-columns: 34px minmax(0, 1fr) auto 18px;
	align-items: center;
	gap: 10px;
	padding: 10px var(--erp-space-3);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	text-align: left;
	transition: background var(--erp-transition-fast), border-color var(--erp-transition-fast);
}

.erp-transaction-card:hover {
	border-color: var(--erp-accent-border);
	background: var(--erp-surface-soft);
}

.erp-transaction-card span {
	display: grid;
	min-width: 0;
	gap: 2px;
}

.erp-transaction-card strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.erp-transaction-card small {
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	text-overflow: ellipsis;
	white-space: nowrap;
}

.erp-transaction-card > i:last-child {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.erp-status {
	display: inline-flex;
	width: max-content;
	min-height: 22px;
	align-items: center;
	padding: 2px var(--erp-space-2);
	border-radius: var(--erp-pill-radius);
	background: var(--erp-surface-muted);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-style: normal;
	font-weight: 800;
	text-transform: uppercase;
}

.erp-status--submitted {
	background: var(--erp-success-soft);
	color: var(--erp-success);
}

.erp-status--cancelled {
	background: var(--erp-danger-soft);
	color: var(--erp-danger);
}

@media (max-width: 1050px) {
	.erp-activity-overview {
		grid-template-columns: repeat(3, minmax(0, 1fr));
	}
}

@media (max-width: 650px) {
	.erp-activity-overview {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.erp-workspace-header {
		align-items: stretch;
		flex-direction: column;
	}

	.erp-create-actions {
		align-items: stretch;
		flex-direction: column;
	}
}
</style>
