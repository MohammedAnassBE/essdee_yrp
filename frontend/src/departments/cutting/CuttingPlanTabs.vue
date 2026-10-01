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
					<section class="content-card detail-fields-card erp-card">
						<div class="detail-field-columns">
							<div v-for="(column, columnIndex) in detailColumns" :key="columnIndex" class="detail-field-column">
								<FormField
									v-for="fieldname in column"
									:key="fieldname"
									:field="field(fieldname)"
									:model-value="doc[fieldname]"
									:form="doc"
									disabled
									:required="Boolean(field(fieldname).reqd)"
									:show-open-button="false"
								/>
							</div>
						</div>
					</section>

					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<template v-else>
						<DataSection title="Lot Planned Quantity" :count="plannedItemCount">
							<div v-for="(group, groupIndex) in itemGroups" :key="groupIndex" class="table-scroll">
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

						<DataSection title="Cloth Details" :count="data.cloth_details?.length || 0">
							<div class="table-scroll">
								<table class="data-table">
									<thead>
										<tr>
											<th>S.No.</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Dia</th>
											<th>Required Weight</th><th>Received Weight</th><th>Used Weight</th><th>Balance Weight</th>
										</tr>
									</thead>
									<tbody>
										<tr v-for="(item, index) in data.cloth_details || []" :key="index">
											<td>{{ index + 1 }}</td><td>{{ item.cloth_item_variant || "—" }}</td><td>{{ item.cloth_type || "—" }}</td>
											<td>{{ item.colour || "—" }}</td><td>{{ item.dia || "—" }}</td><td class="number-cell">{{ weight(item.required_weight) }}</td>
											<td class="number-cell">{{ weight(item.weight) }}</td><td class="number-cell">{{ weight(item.used_weight) }}</td>
											<td class="number-cell">{{ weight(item.balance_weight) }}</td>
										</tr>
									</tbody>
								</table>
							</div>
							<EmptyState v-if="!data.cloth_details?.length" text="No cloth details." />
						</DataSection>

						<DataSection title="Accessory Details" :count="data.accessory_details?.length || 0">
							<div class="table-scroll">
								<table class="data-table">
									<thead>
										<tr>
											<th>S.No.</th><th>Accessory</th><th>Cloth</th><th>Cloth Type</th><th>Colour</th><th>Dia</th>
											<th>Required Weight</th><th>Used Weight</th>
										</tr>
									</thead>
									<tbody>
										<tr v-for="(item, index) in data.accessory_details || []" :key="index">
											<td>{{ index + 1 }}</td><td>{{ item.accessory || "—" }}</td><td>{{ item.cloth_item_variant || "—" }}</td>
											<td>{{ item.cloth_type || "—" }}</td><td>{{ item.colour || "—" }}</td><td>{{ item.dia || "—" }}</td>
											<td class="number-cell">{{ weight(item.required_weight) }}</td><td class="number-cell">{{ weight(item.used_weight) }}</td>
										</tr>
									</tbody>
								</table>
							</div>
							<EmptyState v-if="!data.accessory_details?.length" text="No accessory details." />
						</DataSection>

						<DataSection title="Grammage Change Log" :count="data.grammage_change_logs?.length || 0">
							<div class="table-scroll">
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
						<DataSection title="Completed Cut Quantity" :count="completedItemCount" icon="pi pi-box">
							<template v-for="(group, groupIndex) in completedGroups" :key="groupIndex">
								<div v-if="panelNames(group).length" class="panel-strip"><strong>Panels</strong><span>{{ panelNames(group).join(", ") }}</span></div>
								<div class="table-scroll">
									<table class="data-table matrix-table">
										<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th><th>Total</th><th>Completed</th></tr></thead>
										<tbody>
											<tr v-for="(item, itemIndex) in group.items || []" :key="itemIndex">
												<td>{{ itemIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ displayAttribute(item, attribute) }}</td>
												<td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ displayQuantity(item.values?.[value]) }}</td>
												<td class="number-cell strong-cell">{{ rowTotal(item, group.primary_attribute_values) }}</td>
												<td><i class="pi" :class="item.completed ? 'pi-check-circle complete-icon' : 'pi-circle incomplete-icon'"></i></td>
											</tr>
											<tr class="total-row"><td>Total</td><td v-for="attribute in group.attributes || []" :key="attribute"></td><td v-for="value in group.primary_attribute_values || []" :key="value" class="number-cell">{{ completedColumnTotal(group, value) }}</td><td></td><td></td></tr>
										</tbody>
									</table>
								</div>
							</template>
							<EmptyState v-if="!completedGroups.length" text="No completed cut quantities." />
						</DataSection>

						<DataSection title="Excess Cut Quantity" :count="incompleteItemCount" icon="pi pi-share-alt">
							<div v-for="(group, groupIndex) in incompleteGroups" :key="groupIndex" class="table-scroll">
								<table class="data-table matrix-table">
									<thead><tr><th>S.No.</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="value in group.primary_attribute_values || []" :key="value">{{ value }}</th></tr></thead>
									<tbody><tr v-for="(item, itemIndex) in group.items || []" :key="itemIndex"><td>{{ itemIndex + 1 }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ displayAttribute(item, attribute) }}</td><td v-for="value in group.primary_attribute_values || []" :key="value">{{ excessValue(item.values?.[value]) }}</td></tr></tbody>
								</table>
							</div>
							<EmptyState v-if="!incompleteGroups.length" text="No excess cut quantities." />
						</DataSection>

						<RecutTable title="Recut Summary" :items="data.recut_details" />
						<RecutTable title="Print Panel Summary" :items="data.print_panel_details" print-panel />
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
							<div v-for="(group, groupIndex) in data.planned_detail?.item_detail || []" :key="groupIndex" class="table-scroll">
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

import FormField from "../../components/common/FormField.vue"
import CuttingPlanCpm from "./CuttingPlanCpm.vue"
import CuttingPlanStockTransfers from "./CuttingPlanStockTransfers.vue"

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
const detailColumns = computed(() => [
	[
		"is_manual_entry",
		"lot",
		"maximum_no_of_plys",
		"lay_no",
		...(hasValue(props.doc.cutting_start_date) ? ["cutting_start_date"] : []),
		"cp_status",
		"no_of_colours",
	],
	[
		"item",
		"maximum_allow_percent",
		"piece_weight_tolerance",
		"cutting_location",
		...(hasValue(props.doc.cutting_end_date) ? ["cutting_end_date"] : []),
		"work_order",
		...(hasValue(props.doc.open_status) ? ["open_status"] : []),
		"no_of_colours_completed",
	],
])
const fallbackLabels = {
	is_manual_entry: "Is Manual Entry", lot: "Lot", maximum_no_of_plys: "Maximum No of Plys", lay_no: "Lay No",
	cp_status: "CP Status", no_of_colours: "No of Colours", item: "Item", maximum_allow_percent: "Maximum Allow Percent",
	piece_weight_tolerance: "Piece Weight Tolerance (kg)", cutting_location: "Cutting Location", work_order: "Work Order",
	no_of_colours_completed: "No of Colours Completed",
}

const fieldsByName = computed(() => Object.fromEntries((props.meta?.fields || []).map((item) => [item.fieldname, item])))
const itemGroups = computed(() => normaliseGroups(props.data.item_details))
const completedGroups = computed(() => normaliseGroups(props.data.completed_items))
const incompleteGroups = computed(() => normaliseGroups(props.data.incomplete_items))
const plannedItemCount = computed(() => countItems(itemGroups.value))
const completedItemCount = computed(() => countItems(completedGroups.value))
const incompleteItemCount = computed(() => countItems(incompleteGroups.value))
const plannedSummaryCount = computed(() => countItems(props.data.planned_detail?.item_detail || []))
const canReadMovement = computed(() => Boolean(props.data.permissions?.can_read_movement))
const canReadStockTransfers = computed(() => Boolean(props.data.permissions?.can_read_stock_transfers))
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
	if (!item.completed) return 0
	return primaryValues.reduce((total, value) => total + numeric(item.values?.[value]), 0)
}

function completedColumnTotal(group, value) {
	return (group.items || []).reduce((total, item) => total + (item.completed ? numeric(item.values?.[value]) : 0), 0)
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
					? h("div", { class: "table-scroll" }, [h("table", { class: "data-table" }, [
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
	position: relative;
	z-index: 2;
	min-width: 0;
	background: #fff;
}

.cutting-tabs :deep(.p-tablist-tab-list) {
	gap: 8px;
	padding: 0 4px;
	background: transparent;
	border-bottom: 1px solid #dbe6e0;
}

.cutting-tabs :deep(.p-tab) {
	padding: 12px 15px 11px;
	color: #5d6c76;
	border-color: transparent;
	font-size: 0.82rem;
	font-weight: 680;
	transition: color 140ms ease, background 140ms ease;
}

.cutting-tabs :deep(.p-tab:hover) {
	color: #18704f;
	background: #f8fbf9;
}

.cutting-tabs :deep(.p-tab-active) {
	color: #087c57;
	font-weight: 780;
}

.cutting-tabs :deep(.p-tablist-active-bar) {
	height: 2px;
	background: #0ca678;
	border-radius: 2px 2px 0 0;
}

.cutting-tabs :deep(.p-tabpanels) {
	min-height: 0;
	padding: 12px 2px 2px;
	overflow-y: auto;
	overscroll-behavior: contain;
	scrollbar-color: #9eb6aa transparent;
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
	background: #fff;
	border: 1px solid #dbe7e1;
	border-radius: 12px;
	box-shadow: 0 3px 12px rgb(28 70 48 / 4%);
}

.detail-fields-card {
	padding: 14px 16px 15px;
	background: linear-gradient(145deg, #fff 0%, #fcfefd 100%);
}

.detail-field-columns {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 26px;
}

.detail-field-column {
	display: grid;
	align-content: start;
	gap: 10px;
	min-width: 0;
}

.detail-fields-card :deep(.form-field) {
	gap: 5px;
}

.detail-fields-card :deep(.form-field__label) {
	color: #203247;
	font-size: 0.77rem;
	font-weight: 720;
}

.detail-fields-card :deep(.p-inputtext),
.detail-fields-card :deep(.p-inputnumber-input),
.detail-fields-card :deep(.p-select-label) {
	min-height: 36px;
	padding: 7px 10px;
	color: #38536f;
	font-size: 0.82rem;
	font-weight: 520;
}

.detail-fields-card :deep(.p-inputtext:disabled),
.detail-fields-card :deep(.p-inputnumber-input:disabled),
.detail-fields-card :deep(.p-autocomplete.p-disabled .p-autocomplete-input),
.detail-fields-card :deep(.p-select.p-disabled) {
	opacity: 1;
	color: #46627f;
	background: linear-gradient(135deg, #f1f6fa, #e9f1f7);
	border-color: #d6e2eb;
	box-shadow: 0 1px 1px rgb(32 63 87 / 2%) inset;
}

.detail-fields-card :deep(.p-toggleswitch.p-disabled) {
	opacity: 1;
}

.detail-fields-card :deep(.p-autocomplete-dropdown) {
	display: none;
}

.detail-fields-card :deep(.p-autocomplete-input) {
	border-radius: 6px;
}

.cutting-tabs :deep(.section-heading) {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	min-height: 42px;
	padding: 10px 14px;
	background: linear-gradient(100deg, #f0f8f4 0%, #f8fbf9 100%);
	border-bottom: 1px solid #dce8e2;
}

.cutting-tabs :deep(.section-heading h3) {
	display: flex;
	align-items: center;
	gap: 9px;
	margin: 0;
	color: #0d5f43;
	font-size: 0.91rem;
	font-weight: 780;
}

.cutting-tabs :deep(.section-heading h3 i) {
	color: #078f64;
	font-size: 0.98rem;
}

.cutting-tabs :deep(.section-heading .row-count) {
	padding: 3px 7px;
	color: #657870;
	background: rgb(255 255 255 / 64%);
	border: 1px solid #dfebe5;
	border-radius: 999px;
	font-size: 0.66rem;
	font-weight: 650;
	white-space: nowrap;
}

.cutting-tabs :deep(.section-body) {
	display: grid;
	gap: 9px;
	padding: 10px 12px 12px;
}

.cutting-tabs :deep(.table-scroll) {
	overflow-x: auto;
	border: 1px solid #dfe8e3;
	border-radius: 10px;
	scrollbar-color: #b4c7bd transparent;
	scrollbar-width: thin;
}

.cutting-tabs :deep(.data-table) {
	width: 100%;
	min-width: 760px;
	border-collapse: collapse;
	color: #2f4358;
	font-size: 0.77rem;
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
	border-right: 1px solid #e3ebe7;
	border-bottom: 1px solid #e3ebe7;
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
	color: #475b59;
	font-size: 0.68rem;
	font-weight: 780;
	letter-spacing: 0.035em;
	background: #f3f8f6;
}

.cutting-tabs :deep(.data-table tbody tr:nth-child(even):not(.total-row) td) {
	background: #fbfdfc;
}

.cutting-tabs :deep(.data-table tbody tr:hover:not(.total-row) td) {
	background: #f6faf8;
}

.cutting-tabs :deep(.number-cell) {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.cutting-tabs :deep(.strong-cell),
.cutting-tabs :deep(.total-row td) {
	color: #20364d;
	font-weight: 780;
}

.cutting-tabs :deep(.total-row td) {
	background: #edf7f2;
	border-color: #d8e8df;
}

.panel-strip {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 8px 10px;
	color: #465c54;
	font-size: 0.75rem;
	background: #f6faf8;
	border: 1px solid #dfe9e4;
	border-radius: 8px;
}

.panel-strip strong {
	color: #176b4c;
}

.complete-icon {
	color: #2f7d57;
}

.incomplete-icon {
	color: #adb7b1;
}

.cutting-tabs :deep(.empty-state) {
	display: grid;
	align-items: center;
	justify-content: center;
	grid-template-columns: auto auto;
	gap: 10px;
	min-height: 62px;
	padding: 12px;
	color: #7b8780;
	background: #fcfefd;
	border: 1px dashed #d9e6df;
	border-radius: 9px;
	font-size: 0.76rem;
}

.cutting-tabs :deep(.empty-state > i) {
	color: #4f7462;
	font-size: 1rem;
}

.cutting-tabs :deep(.empty-state__copy) {
	display: grid;
	gap: 2px;
}

.cutting-tabs :deep(.empty-state__copy strong) {
	color: #40534a;
	font-size: 0.76rem;
	font-weight: 650;
}

.cutting-tabs :deep(.empty-state__copy small) {
	color: #8a9891;
	font-size: 0.67rem;
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
	background: #45bf96;
	box-shadow: 0 0 0 3px #e8f7f1;
}

.detail-kind--completed i {
	background: #91a8bd;
	box-shadow: 0 0 0 3px #eef2f6;
}

.completed-row td {
	background: #f8fafc !important;
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
	.detail-field-columns {
		grid-template-columns: 1fr;
		gap: 10px;
	}

	.cutting-tabs :deep(.p-tab) {
		padding-inline: 10px;
		font-size: 0.78rem;
	}
}
</style>
