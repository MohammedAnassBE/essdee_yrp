<template>
	<Tabs v-model:value="activeTab" class="cutting-tabs erp-tabs">
		<TabList>
			<Tab value="details">Details</Tab>
			<Tab value="summary">Summary</Tab>
			<Tab value="planned">Planned Detail</Tab>
			<Tab v-if="canReadMovement" value="cpm">CPM</Tab>
			<Tab v-if="canReadStockTransfers" value="stock-transfers">Stock Transfers</Tab>
		</TabList>

		<TabPanels ref="tabPanels">
			<TabPanel value="details">
				<div class="tab-stack">
					<DocumentOverview :fields="overviewFields" :definitions="overviewDefinitions" include-empty aria-label="Cutting Plan overview" id-prefix="cutting-plan-overview" />

					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<template v-else>
						<DataSection title="Lot Planned Quantity" :count="plannedItemCount">
							<div v-for="(group, groupIndex) in itemGroups" :key="groupIndex" class="table-scroll" role="region" tabindex="0" :aria-label="`Lot planned quantity group ${groupIndex + 1}`">
								<table class="data-table matrix-table">
									<thead>
										<tr>
											<th>S.No.</th>
											<th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th>
											<th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th>
										</tr>
									</thead>
									<tbody>
										<tr v-for="(item, itemIndex) in group.items || []" :key="itemIndex">
											<td>{{ itemIndex + 1 }}</td>
											<td v-for="attribute in group.attributes || []" :key="attribute">
												{{ displayAttribute(item, attribute) }}
											</td>
											<td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">
												{{ displayQuantity(item.values?.[value], "qty") }}
											</td>
										</tr>
									</tbody>
								</table>
							</div>
							<EmptyState v-if="!itemGroups.length" text="No planned quantities." />
						</DataSection>

						<DataSection class="cloth-details-section" title="Cloth Details" :count="data.cloth_details?.length || 0">
							<MaterialRequirementGroups v-if="data.cloth_details?.length" :rows="data.cloth_details" :columns="requirementColumns" />
							<EmptyState v-if="!data.cloth_details?.length" text="No cloth details." />
						</DataSection>

						<DataSection class="accessory-details-section" title="Accessory Details" :count="data.accessory_details?.length || 0">
							<MaterialRequirementGroups v-if="data.accessory_details?.length" :rows="data.accessory_details" :columns="requirementColumns" kind="accessory" />
							<EmptyState v-if="!data.accessory_details?.length" text="No accessory details." />
						</DataSection>

						<DataSection title="Grammage Change Log" :count="data.grammage_change_logs?.length || 0">
							<div class="table-scroll" role="region" tabindex="0" aria-label="Grammage change log">
								<table class="data-table">
									<thead><tr><th>S.No.</th><th>From Grammage Allowance (kg)</th><th>To Grammage Allowance (kg)</th><th>Changed By</th><th>Changed On</th></tr></thead>
									<tbody>
										<tr v-for="(row, index) in data.grammage_change_logs || []" :key="row.name || index">
											<td>{{ index + 1 }}</td><td>{{ decimal(row.from_grammage_allowance, 4) }}</td><td>{{ decimal(row.to_grammage_allowance, 4) }}</td>
											<td>{{ row.changed_by || "—" }}</td><td>{{ row.changed_on || "—" }}</td>
										</tr>
									</tbody>
								</table>
							</div>
							<EmptyState v-if="!data.grammage_change_logs?.length" text="No grammage changes." />
						</DataSection>
					</template>
				</div>
			</TabPanel>

			<TabPanel value="summary">
				<div class="tab-stack">
					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<template v-else>
						<DataSection class="completed-quantity-section" title="Completed Cut Quantity" :count="completedItemCount" icon="pi pi-box">
							<template v-for="(group, groupIndex) in completedGroups" :key="groupIndex">
								<div v-if="panelNames(group).length" class="panel-strip"><strong>Panels</strong><span>{{ panelNames(group).join(", ") }}</span></div>
								<div class="table-scroll" role="region" tabindex="0" :aria-label="`Completed cut quantity group ${groupIndex + 1}`">
									<table class="data-table matrix-table">
										<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th><th>Total</th></tr></thead>
										<tbody>
											<tr v-for="(item, itemIndex) in group.items || []" :key="itemIndex">
												<td>{{ itemIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ displayAttribute(item, attribute) }}</td>
												<td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ displayQuantity(item.values?.[value]) }}</td>
												<td class="number-cell strong-cell">{{ rowTotal(item, group.primary_attribute_values) }}</td>
											</tr>
											<tr class="total-row"><td>Total</td><td v-for="attribute in group.attributes || []" :key="attribute"></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ completedColumnTotal(group, value) }}</td><td class="number-cell">{{ completedGrandTotal(group) }}</td></tr>
										</tbody>
									</table>
								</div>
							</template>
							<EmptyState v-if="!completedGroups.length" text="No completed cut quantities." />
						</DataSection>

						<DataSection class="excess-quantity-section" title="Excess Cut Quantity" :count="incompleteItemCount" icon="pi pi-share-alt">
							<div v-for="(group, groupIndex) in incompleteGroups" :key="groupIndex" class="table-scroll" role="region" tabindex="0" :aria-label="`Excess cut quantity group ${groupIndex + 1}`">
								<table class="data-table matrix-table">
									<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th></tr></thead>
									<tbody><tr v-for="(item, itemIndex) in group.items || []" :key="itemIndex"><td>{{ itemIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ displayAttribute(item, attribute) }}</td><td v-for="value in group.primary_attribute_values || []" :key="value">{{ excessValue(item.values?.[value]) }}</td></tr></tbody>
								</table>
							</div>
							<EmptyState v-if="!incompleteGroups.length" text="No excess cut quantities." />
						</DataSection>

						<template v-if="canReadRecut">
							<RecutTable title="Recut Summary" :items="data.recut_details" />
							<RecutTable title="Print Panel Summary" :items="data.print_panel_details" print-panel />
						</template>
					</template>
				</div>
			</TabPanel>

			<TabPanel value="planned">
				<div class="tab-stack">
					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<Message v-else-if="data.planned_detail?.work_order_docstatus === 2" severity="warn" :closable="false">
						The Work Order is cancelled, so its planned quantities are not applicable.
					</Message>
					<template v-else>
						<DataSection title="Work Order Summary" :count="plannedSummaryCount" icon="pi pi-chart-bar">
							<div v-for="(group, groupIndex) in data.planned_detail?.item_detail || []" :key="groupIndex" class="table-scroll" role="region" tabindex="0" :aria-label="`Work Order summary group ${groupIndex + 1}`">
								<table class="data-table matrix-table">
									<thead><tr><th>S.No.</th><th>{{ group.pack_attr || "Item" }}</th><th v-if="group.is_set_item">{{ group.set_attr }}</th><th>Details</th><th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th><th>Total</th></tr></thead>
									<tbody>
										<template v-for="(item, itemIndex) in group.items || []" :key="itemIndex">
											<tr class="planned-row"><td rowspan="2">{{ itemIndex + 1 }}</td><td rowspan="2">{{ item.attributes?.[group.pack_attr] || "—" }}</td><td v-if="group.is_set_item" rowspan="2">{{ item.attributes?.[group.set_attr] || "—" }}</td><td><span class="detail-kind detail-kind--planned"><i></i>Planned</span></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ displayQuantity(item.values?.[value], "qty") }}</td><td class="number-cell strong-cell">{{ numeric(item.total_qty) }}</td></tr>
											<tr class="completed-row"><td><span class="detail-kind detail-kind--completed"><i></i>Completed</span></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ displayQuantity(item.values?.[value], "received") }}</td><td class="number-cell strong-cell">{{ numeric(item.total_received) }}</td></tr>
										</template>
										<tr class="total-row"><td rowspan="2">Total</td><td rowspan="2"></td><td v-if="group.is_set_item" rowspan="2"></td><td><span class="detail-kind detail-kind--planned"><i></i>Planned</span></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ numeric(group.total_details?.[value]?.planned) }}</td><td class="number-cell">{{ numeric(group.overall_planned) }}</td></tr>
										<tr class="total-row"><td><span class="detail-kind detail-kind--completed"><i></i>Completed</span></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ numeric(group.total_details?.[value]?.received) }}</td><td class="number-cell">{{ numeric(group.overall_received) }}</td></tr>
									</tbody>
								</table>
							</div>
							<EmptyState v-if="!plannedSummaryCount" :text="doc.work_order ? 'No planned Work Order details.' : 'No Work Order is linked.'" />
						</DataSection>
					</template>
				</div>
			</TabPanel>

			<TabPanel v-if="canReadMovement" value="cpm">
				<CuttingPlanCpm :cutting-plan="doc.name" @changed="emit('refresh')" />
			</TabPanel>

			<TabPanel v-if="canReadStockTransfers" value="stock-transfers">
				<CuttingPlanStockTransfers :cutting-plan="doc.name" @changed="emit('refresh')" />
			</TabPanel>
		</TabPanels>
	</Tabs>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import TabPanel from "primevue/tabpanel"
import TabPanels from "primevue/tabpanels"
import Tabs from "primevue/tabs"
import { computed, defineComponent, h, nextTick, ref, watch } from "vue"

import DocumentOverview from "../../components/documents/DocumentOverview.vue"
import CuttingPlanCpm from "./CuttingPlanCpm.vue"
import CuttingPlanStockTransfers from "./CuttingPlanStockTransfers.vue"
import MaterialRequirementGroups from "./shared/MaterialRequirementGroups.vue"

const props = defineProps({
	doc: { type: Object, required: true },
	meta: { type: Object, default: null },
	data: { type: Object, default: () => ({}) },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
})
const emit = defineEmits(["refresh"])

const activeTab = ref("details")
const tabPanels = ref(null)
const detailFieldnames = computed(() => [
	"is_manual_entry",
	"maximum_no_of_plys",
	"maximum_allow_percent",
	"piece_weight_tolerance",
	"cutting_start_date",
	"cutting_end_date",
	"cutting_location",
	"work_order",
	"no_of_colours",
	"no_of_colours_completed",
	"open_status",
])
const overviewDefinitions = [
	{ key: "identity", label: "Plan identity", description: "Plan source and entry mode", icon: "pi pi-id-card", fields: ["work_order", "is_manual_entry"] },
	{ key: "planning", label: "Planning", description: "Lay limits and quantity controls", icon: "pi pi-sliders-h", fields: ["maximum_no_of_plys", "maximum_allow_percent", "piece_weight_tolerance", "no_of_colours", "no_of_colours_completed"] },
	{ key: "schedule", label: "Schedule", description: "Planned cutting window", icon: "pi pi-calendar", fields: ["cutting_start_date", "cutting_end_date"] },
	{ key: "status", label: "Status & notes", description: "Location and operating status", icon: "pi pi-clipboard", fields: ["cutting_location", "open_status"] },
]
const fallbackLabels = {
	is_manual_entry: "Is Manual Entry", maximum_no_of_plys: "Maximum No of Plys",
	no_of_colours: "No of Colours", maximum_allow_percent: "Maximum Allow Percent",
	piece_weight_tolerance: "Piece Weight Tolerance (kg)", cutting_location: "Cutting Location", work_order: "Work Order",
	no_of_colours_completed: "No of Colours Completed",
}

const fieldsByName = computed(() => Object.fromEntries((props.meta?.fields || []).map((item) => [item.fieldname, item])))
const overviewFields = computed(() => detailFieldnames.value.map((fieldname) => ({ ...field(fieldname), value: props.doc[fieldname] })))
const itemGroups = computed(() => normaliseGroups(props.data.item_details))
const completedGroups = computed(() => filterGroups(props.data.completed_items, (item) => Boolean(item.completed)))
const incompleteGroups = computed(() => filterGroups(props.data.incomplete_items, hasExcess))
const requirementColumns = [
	{ field: "colour", label: "Colour" },
	{ field: "dia", label: "Dia" },
	{ field: "required_weight", label: "Required Weight", numeric: true, format: (value) => weight(value) },
	{ field: "weight", label: "Received Weight", numeric: true, format: (value) => weight(value) },
	{ field: "used_weight", label: "Used Weight", numeric: true, format: (value) => weight(value) },
	{ field: "balance_weight", label: "Balance Weight", numeric: true, format: (value) => weight(value), cellClass: (row) => `requirement-balance ${balanceClass(row.balance_weight)}` },
]
const plannedItemCount = computed(() => countItems(itemGroups.value))
const completedItemCount = computed(() => countItems(completedGroups.value))
const incompleteItemCount = computed(() => countItems(incompleteGroups.value))
const plannedSummaryCount = computed(() => countItems(props.data.planned_detail?.item_detail || []))
const canReadMovement = computed(() => Boolean(props.data.permissions?.can_read_movement))
const canReadStockTransfers = computed(() => Boolean(props.data.permissions?.can_read_stock_transfers))
const canReadRecut = computed(() => Boolean(props.data.permissions?.can_read_recut))
const availableTabs = computed(() => [
	"details",
	"summary",
	"planned",
	...(canReadMovement.value ? ["cpm"] : []),
	...(canReadStockTransfers.value ? ["stock-transfers"] : []),
])

function field(fieldname) {
	return fieldsByName.value[fieldname] || { fieldname, label: fallbackLabels[fieldname] || fieldname, fieldtype: "Data" }
}

function hasValue(value) {
	return value !== null && value !== undefined && value !== ""
}

function normaliseGroups(value) {
	if (Array.isArray(value)) return value.filter((group) => group?.items)
	if (value?.items) return [value]
	if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items)
	return []
}

function filterGroups(value, predicate) {
	return normaliseGroups(value)
		.map((group) => ({ ...group, items: (group.items || []).filter(predicate) }))
		.filter((group) => group.items.length)
}

function hasExcess(item) {
	return Object.values(item?.values || {}).some((value) => {
		if (value && typeof value === "object") return Object.values(value).some((quantity) => numeric(quantity) > 0)
		return numeric(value) > 0
	})
}

function countItems(groups) {
	return groups.reduce((total, group) => total + (group.items?.length || 0), 0)
}

function displayAttribute(item, attribute) {
	return item?.attributes?.[attribute] || "—"
}

function numeric(value) {
	const number = Number(value || 0)
	return Number.isFinite(number) ? number : 0
}

function displayQuantity(value, key) {
	const quantity = value && typeof value === "object" ? value[key] : value
	return numeric(quantity) || "—"
}

function rowTotal(item, primaryValues = []) {
	return primaryValues.reduce((total, value) => total + numeric(item.values?.[value]), 0)
}

function completedColumnTotal(group, value) {
	return (group.items || []).reduce((total, item) => total + numeric(item.values?.[value]), 0)
}

function completedGrandTotal(group) {
	return (group.primary_attribute_values || []).reduce((total, value) => total + completedColumnTotal(group, value), 0)
}

function panelNames(group) {
	const panels = group?.[group?.stiching_attr]
	return Array.isArray(panels) ? panels : []
}

function excessValue(value) {
	if (!value || typeof value !== "object") return numeric(value) || "—"
	const entries = Object.entries(value).filter(([, quantity]) => numeric(quantity) > 0)
	return entries.length ? entries.map(([panel, quantity]) => `${panel} ${numeric(quantity)}`).join(", ") : "—"
}

function decimal(value, precision) {
	return Number(value || 0).toFixed(precision)
}

function weight(value) {
	return decimal(value, 3)
}

function activate(tab) {
	if (availableTabs.value.includes(tab)) activeTab.value = tab
}

watch(availableTabs, (tabs) => {
	if (!tabs.includes(activeTab.value)) activeTab.value = tabs[0] || "details"
})

watch(activeTab, async () => {
	await nextTick()
	const element = tabPanels.value?.$el
	if (element) element.scrollTop = 0
})

defineExpose({ activate })

const DataSection = defineComponent({
	props: { title: String, count: Number, icon: { type: String, default: "" } },
	setup(sectionProps, { slots }) {
		return () => h("section", { class: "content-card data-section erp-card" }, [
			h("header", { class: "section-heading" }, [
				h("h3", [
					sectionProps.icon ? h("i", { class: sectionProps.icon }) : null,
					h("span", sectionProps.title),
				]),
				h("span", { class: "row-count" }, `${sectionProps.count || 0} ${sectionProps.count === 1 ? "row" : "rows"}`),
			]),
			h("div", { class: "section-body" }, slots.default?.()),
		])
	},
})

const EmptyState = defineComponent({
	props: { text: String },
	setup(emptyProps) {
		return () => h("div", { class: "empty-state erp-empty-state" }, [
			h("i", { class: "pi pi-inbox" }),
			h("div", { class: "empty-state__copy" }, [
				h("strong", emptyProps.text),
				h("small", "There is no data available for this Cutting Plan."),
			]),
		])
	},
})

const LoadingState = defineComponent({
	setup() {
		return () => h("div", { class: "loading-state" }, [1, 2, 3].map((key) => h(Skeleton, { key, height: "3.25rem" })))
	},
})

function balanceClass(value) {
	const balance = numeric(value)
	if (balance < 0) return "requirement-balance--negative"
	if (balance === 0) return "requirement-balance--zero"
	return "requirement-balance--positive"
}

const RecutTable = defineComponent({
	props: { title: String, items: { type: Object, default: () => ({}) }, printPanel: Boolean },
	setup(tableProps) {
		return () => {
			const rows = Object.values(tableProps.items || {})
			return h(DataSection, {
				title: tableProps.title,
				count: rows.length,
				icon: tableProps.printPanel ? "pi pi-print" : "pi pi-replay",
			}, {
				default: () => rows.length
					? h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": tableProps.title }, [h("table", { class: "data-table" }, [
						h("thead", [h("tr", ["S.No.", "Cloth Type", "Colour", "Dia", "Shade", "Weight in Kg", "No of Rolls", ...(tableProps.printPanel ? ["Panel Count"] : [])].map((label) => h("th", label)))]),
						h("tbody", rows.map((row, index) => h("tr", [h("td", index + 1), h("td", row.cloth_type || "—"), h("td", row.colour || "—"), h("td", row.dia || "—"), h("td", row.shade || "—"), h("td", weight(row.weight)), h("td", numeric(row.no_of_rolls)), ...(tableProps.printPanel ? [h("td", numeric(row.panel_count))] : [])]))),
					])])
					: h(EmptyState, { text: `No ${tableProps.title.toLowerCase()} details.` }),
			})
		}
	},
})
</script>

<style scoped>
.cutting-tabs {
	display: grid;
	grid-template-rows: auto minmax(0, 1fr);
	min-width: 0;
	min-height: 0;
	overflow: hidden;
}

.cutting-tabs :deep(.p-tablist) {
	position: sticky;
	top: 0;
	z-index: var(--erp-layer-sticky);
	min-width: 0;
	background: var(--erp-surface);
}

.cutting-tabs :deep(.p-tablist-tab-list) {
	gap: 18px;
	padding: 0 2px;
	background: transparent;
	border-bottom: 1px solid var(--erp-border);
}

.cutting-tabs :deep(.p-tab) {
	padding: 12px 2px 11px;
	color: var(--erp-text-muted);
	border-color: transparent;
	font-size: 0.82rem;
	font-weight: 680;
	transition: color 140ms ease, background 140ms ease;
}

.cutting-tabs :deep(.p-tab:hover) {
	color: var(--erp-accent-hover);
	background: transparent;
}

.cutting-tabs :deep(.p-tab-active) {
	color: var(--erp-accent);
	font-weight: 780;
}

.cutting-tabs :deep(.p-tablist-active-bar) {
	height: 2px;
	background: var(--erp-accent);
	border-radius: 2px 2px 0 0;
}

.cutting-tabs :deep(.p-tabpanels) {
	min-height: 0;
	padding: 12px 0 2px;
	overflow-y: auto;
	overscroll-behavior: contain;
	scrollbar-color: var(--erp-border-strong) transparent;
	scrollbar-width: thin;
	background: transparent;
}

.tab-stack {
	display: grid;
	gap: 12px;
	padding-bottom: 2px;
}

.content-card {
	overflow: hidden;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	box-shadow: none;
}


.cutting-tabs :deep(.section-heading) {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	min-height: 42px;
	padding: 10px 14px;
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.cutting-tabs :deep(.section-heading h3) {
	display: flex;
	align-items: center;
	gap: 9px;
	margin: 0;
	color: var(--erp-text);
	font-size: 0.91rem;
	font-weight: 780;
}

.cutting-tabs :deep(.section-heading h3 i) {
	color: var(--erp-accent);
	font-size: 0.98rem;
}

.cutting-tabs :deep(.section-heading .row-count) {
	padding: 3px 7px;
	color: var(--erp-text-muted);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: 999px;
	font-size: var(--erp-font-size-min);
	font-weight: 650;
	white-space: nowrap;
}

.cutting-tabs :deep(.section-body) {
	display: grid;
	gap: 9px;
	padding: 10px 12px 12px;
}

.requirement-groups {
	display: grid;
	gap: 10px;
}

.requirement-group {
	overflow: hidden;
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
	border-radius: 9px;
}

.requirement-group__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 14px;
	min-height: 48px;
	padding: 8px 10px 8px 12px;
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.requirement-group__identity {
	display: grid;
	gap: 2px;
	min-width: 0;
}

.requirement-group__identity strong {
	overflow: hidden;
	color: var(--erp-text);
	font-size: 13px;
	font-weight: 770;
	line-height: 1.25;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.requirement-template {
	overflow: hidden;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	font-weight: 590;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.requirement-group__meta {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	flex: 0 0 auto;
	gap: 6px;
}

.requirement-type,
.requirement-count {
	display: inline-flex;
	align-items: center;
	min-height: 24px;
	padding: 3px 8px;
	border-radius: var(--erp-pill-radius);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
	white-space: nowrap;
}

.requirement-type {
	color: var(--erp-accent-hover);
	background: var(--erp-accent-soft);
	border: 1px solid var(--erp-accent-border);
}

.requirement-count {
	color: var(--erp-text-muted);
	background: var(--erp-surface);
	border: 1px solid var(--erp-border);
}

.cutting-tabs :deep(.table-scroll) {
	overflow-x: auto;
	border: 1px solid var(--erp-border);
	border-radius: 10px;
	scrollbar-color: var(--erp-border-strong) transparent;
	scrollbar-width: thin;
}

.cutting-tabs :deep(.table-scroll:focus-visible) {
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: -2px;
}

.cutting-tabs :deep(.requirement-table-scroll) {
	border: 0;
	border-top: 1px solid var(--erp-border);
	border-radius: 0;
}

.cutting-tabs :deep(.requirement-table) {
	min-width: 690px;
}

.cutting-tabs :deep(.requirement-table th:first-child),
.cutting-tabs :deep(.requirement-table td:first-child) {
	width: 22%;
}

.cutting-tabs :deep(.requirement-table th:nth-child(2)),
.cutting-tabs :deep(.requirement-table td:nth-child(2)) {
	width: 12%;
}

.cutting-tabs :deep(.requirement-table th:nth-child(n + 3)) {
	text-align: right;
}

.cutting-tabs :deep(.requirement-table .requirement-attribute) {
	font-weight: 650;
}

.cutting-tabs :deep(.requirement-table .requirement-balance) {
	font-weight: 780;
}

.cutting-tabs :deep(.requirement-table .requirement-balance--positive) {
	color: var(--erp-success-text);
	background: var(--erp-success-soft);
}

.cutting-tabs :deep(.requirement-table .requirement-balance--negative) {
	color: var(--erp-danger);
	background: var(--erp-danger-soft);
}

.cutting-tabs :deep(.requirement-table .requirement-balance--zero) {
	color: var(--erp-text-muted);
	background: var(--erp-surface-soft);
}

.cutting-tabs :deep(.data-table) {
	width: 100%;
	min-width: 760px;
	border-collapse: collapse;
	color: var(--erp-text);
	font-size: 13px;
	font-variant-numeric: tabular-nums;
}

.cutting-tabs :deep(.matrix-table) {
	min-width: 900px;
}

.cutting-tabs :deep(.data-table th),
.cutting-tabs :deep(.data-table td) {
	padding: 8px 10px;
	text-align: left;
	vertical-align: middle;
	border-right: 1px solid var(--erp-border);
	border-bottom: 1px solid var(--erp-border);
	overflow-wrap: anywhere;
}

.cutting-tabs :deep(.data-table th:last-child),
.cutting-tabs :deep(.data-table td:last-child) {
	border-right: 0;
}

.cutting-tabs :deep(.data-table tbody tr:last-child td) {
	border-bottom: 0;
}

.cutting-tabs :deep(.data-table th) {
	white-space: nowrap;
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: 780;
	letter-spacing: 0.035em;
	background: var(--erp-surface-muted);
}

.cutting-tabs :deep(.data-table tbody tr:nth-child(even):not(.total-row) td) {
	background: var(--erp-surface-soft);
}

.cutting-tabs :deep(.data-table tbody tr:hover:not(.total-row) td) {
	background: var(--erp-surface-hover);
}

.cutting-tabs :deep(.number-cell) {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.cutting-tabs :deep(.strong-cell),
.cutting-tabs :deep(.total-row td) {
	color: var(--erp-text);
	font-weight: 780;
}

.cutting-tabs :deep(.total-row td) {
	background: var(--erp-accent-soft);
	border-color: var(--erp-accent-border);
}

.panel-strip {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 8px 10px;
	color: var(--erp-text-muted);
	font-size: 0.75rem;
	background: var(--erp-surface-soft);
	border: 1px solid var(--erp-border);
	border-radius: 8px;
}

.panel-strip strong {
	color: var(--erp-accent-hover);
}

.complete-icon {
	color: var(--erp-success);
}

.incomplete-icon {
	color: var(--erp-text-subtle);
}

.cutting-tabs :deep(.empty-state) {
	display: grid;
	align-items: center;
	justify-content: center;
	grid-template-columns: auto auto;
	gap: 10px;
	min-height: 62px;
	padding: 12px;
	color: var(--erp-text-muted);
	background: var(--erp-surface-soft);
	border: 1px dashed var(--erp-border-strong);
	border-radius: 9px;
	font-size: 0.76rem;
}

.cutting-tabs :deep(.empty-state > i) {
	color: var(--erp-accent);
	font-size: 1rem;
}

.cutting-tabs :deep(.empty-state__copy) {
	display: grid;
	gap: 2px;
}

.cutting-tabs :deep(.empty-state__copy strong) {
	color: var(--erp-text);
	font-size: 0.76rem;
	font-weight: 650;
}

.cutting-tabs :deep(.empty-state__copy small) {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.cutting-tabs :deep(.loading-state) {
	display: grid;
	gap: 10px;
}

.detail-kind {
	display: inline-flex;
	align-items: center;
	gap: 7px;
	font-weight: 650;
	white-space: nowrap;
}

.detail-kind i {
	display: inline-block;
	width: 8px;
	height: 8px;
	border-radius: 50%;
}

.detail-kind--planned i {
	background: var(--erp-success);
	box-shadow: 0 0 0 3px var(--erp-success-soft);
}

.detail-kind--completed i {
	background: var(--erp-info);
	box-shadow: 0 0 0 3px var(--erp-info-soft);
}

.completed-row td {
	background: var(--erp-surface-muted) !important;
}

@media (max-width: 1050px) {
	.cutting-tabs {
		display: block;
		overflow: visible;
	}

	.cutting-tabs :deep(.p-tabpanels) {
		padding-inline: 0;
		overflow: visible;
	}

}

@media (max-width: 780px) {
	.requirement-group__header {
		align-items: flex-start;
		flex-direction: column;
	}

	.requirement-group__meta {
		justify-content: flex-start;
	}

	.cutting-tabs :deep(.p-tab) {
		padding-inline: 8px;
		font-size: var(--erp-font-size-caption);
	}

	.cutting-tabs :deep(.p-tablist-tab-list) {
		gap: 8px;
	}

	.cutting-tabs :deep(.table-scroll) {
		-webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
		mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
	}
}
</style>
