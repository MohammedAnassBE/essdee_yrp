<template>
	<Tabs v-model:value="activeTab" class="cutting-order-tabs erp-tabs">
		<TabList><Tab value="details">Details</Tab><Tab value="summary">Summary</Tab><Tab value="planned">Planned Detail</Tab></TabList>
		<TabPanels>
			<TabPanel value="details">
				<div class="tab-stack">
					<DocumentOverview :fields="overviewFields" :definitions="overviewDefinitions" include-empty aria-label="Cutting Order overview" id-prefix="cutting-order-overview" />
					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<DataSection v-else title="Planned Quantities" :count="rowCount(orderGroups)">
						<QuantityTable v-for="(group, index) in orderGroups" :key="index" :group="group" />
						<EmptyState v-if="!orderGroups.length" text="No planned quantities." />
					</DataSection>
				</div>
			</TabPanel>

			<TabPanel value="summary">
				<div class="tab-stack">
					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<template v-else>
						<DataSection title="Completed Cut Quantity" :count="rowCount(completedGroups)" icon="pi pi-check-circle">
							<CompletionTable v-for="(group, index) in completedGroups" :key="index" :group="group" completed />
							<EmptyState v-if="!completedGroups.length" text="No completed cut quantities." />
						</DataSection>
						<DataSection title="Excess Cut Quantity" :count="rowCount(incompleteGroups)" icon="pi pi-chart-line">
							<CompletionTable v-for="(group, index) in incompleteGroups" :key="index" :group="group" />
							<EmptyState v-if="!incompleteGroups.length" text="No excess cut quantities." />
						</DataSection>
					</template>
				</div>
			</TabPanel>

			<TabPanel value="planned">
				<div class="tab-stack">
					<LoadingState v-if="loading" />
					<Message v-else-if="error" severity="error" :closable="false">{{ error }}</Message>
					<DataSection v-else title="Planned vs Completed" :count="rowCount(plannedGroups)" icon="pi pi-chart-bar">
						<div v-for="(group, groupIndex) in plannedGroups" :key="groupIndex" class="table-scroll" role="region" tabindex="0" :aria-label="`Planned versus completed quantities group ${groupIndex + 1}`">
							<table class="data-table planned-table">
								<thead><tr><th>S.No.</th><th v-for="attribute in groupAttributes(group)" :key="attribute">{{ attribute }}</th><th>Details</th><th v-for="size in sizes(group)" :key="size">{{ size }}</th><th>Total</th></tr></thead>
								<tbody>
									<template v-for="(row, rowIndex) in group.items || []" :key="rowIndex">
										<tr class="planned-row"><td rowspan="2">{{ rowIndex + 1 }}</td><td v-for="attribute in groupAttributes(group)" :key="attribute" rowspan="2">{{ row.attributes?.[attribute] || '—' }}</td><td><span class="detail-kind detail-kind--planned"><i></i>Planned</span></td><td v-for="size in sizes(group)" :key="size" class="number-cell">{{ numeric(row.values?.[size]?.qty) }}</td><td class="number-cell strong-cell">{{ numeric(row.total_qty) }}</td></tr>
										<tr class="completed-row"><td><span class="detail-kind detail-kind--completed"><i></i>Completed</span></td><td v-for="size in sizes(group)" :key="size" class="number-cell">{{ numeric(row.values?.[size]?.received) }}</td><td class="number-cell strong-cell">{{ numeric(row.total_received) }}</td></tr>
									</template>
									<tr class="total-row"><td :rowspan="2">Total</td><td v-for="attribute in groupAttributes(group)" :key="attribute" :rowspan="2"></td><td>Planned</td><td v-for="size in sizes(group)" :key="size" class="number-cell">{{ numeric(group.total_details?.[size]?.planned) }}</td><td class="number-cell">{{ numeric(group.overall_planned) }}</td></tr>
									<tr class="total-row"><td>Completed</td><td v-for="size in sizes(group)" :key="size" class="number-cell">{{ numeric(group.total_details?.[size]?.received) }}</td><td class="number-cell">{{ numeric(group.overall_received) }}</td></tr>
								</tbody>
							</table>
						</div>
						<EmptyState v-if="!plannedGroups.length" text="No planned comparison details." />
					</DataSection>
				</div>
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
import { computed, defineComponent, h, ref } from "vue"

import DocumentOverview from "../../../components/documents/DocumentOverview.vue"

const props = defineProps({ data: { type: Object, default: () => ({}) }, loading: Boolean, error: { type: String, default: "" } })
const activeTab = ref("details")
const orderGroups = computed(() => props.data.matrix?.groups || [])
const completedGroups = computed(() => normaliseGroups(props.data.completed_items))
const incompleteGroups = computed(() => normaliseGroups(props.data.incomplete_items))
const plannedGroups = computed(() => Array.isArray(props.data.planned_detail) ? props.data.planned_detail : props.data.planned_detail?.item_detail || [])
const overviewDefinitions = [
	{ key: "identity", label: "Order identity", description: "Order detail and finished item", icon: "pi pi-id-card", fields: ["cutting_order_detail", "item", "is_set_item"] },
	{ key: "planning", label: "Planning", description: "Lay and cutting limits", icon: "pi pi-sliders-h", fields: ["cutting_location", "lay_no", "maximum_no_of_plys", "maximum_allow_percent"] },
	{ key: "schedule", label: "Schedule", description: "Planned cutting window", icon: "pi pi-calendar", fields: ["cutting_start_date", "cutting_end_date"] },
	{ key: "status", label: "Status & notes", description: "Current order state", icon: "pi pi-clipboard", fields: ["status"] },
]
const overviewFields = computed(() => {
	const fields = [...(props.data.details || [])]
	const existing = new Set(fields.map((field) => field.fieldname))
	const metadata = {
		cutting_order_detail: ["Cutting Order Detail", "Link"], item: ["Item", "Link"], is_set_item: ["Set Item", "Check"],
		cutting_start_date: ["Cutting Start Date", "Date"], cutting_end_date: ["Cutting End Date", "Date"], status: ["Status", "Data"],
	}
	for (const [fieldname, [label, fieldtype]] of Object.entries(metadata)) {
		if (!existing.has(fieldname)) fields.push({ fieldname, label, fieldtype, value: props.data.record?.[fieldname] })
	}
	return fields
})

function normaliseGroups(value) { if (Array.isArray(value)) return value; if (value?.items) return [value]; if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items); return [] }
function sizes(group) { return group.primary_attribute_values || Object.keys(group.items?.[0]?.values || {}) }
function groupAttributes(group) { if (group.attributes?.length) return group.attributes; const list = [group.pack_attr]; if (group.is_set_item && group.set_attr) list.push(group.set_attr); return list.filter(Boolean) }
function rowCount(groups) { return groups.reduce((count, group) => count + (group.items?.length || 0), 0) }
function numeric(value) { const number = Number(value || 0); return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—" }
function valueTotal(value) { if (value && typeof value === "object" && !("qty" in value)) return Object.values(value).reduce((total, entry) => total + Number(entry || 0), 0); return Number(value?.qty ?? value ?? 0) }
function rowTotal(row, group) { return sizes(group).reduce((total, size) => total + valueTotal(row.values?.[size]), 0) }

const LoadingState = defineComponent({ setup: () => () => h("div", { class: "loading-state" }, [h(Skeleton, { height: "84px" }), h(Skeleton, { height: "190px" })]) })
const EmptyState = defineComponent({ props: { text: String }, setup: (componentProps) => () => h("div", { class: "empty-state" }, [h("i", { class: "pi pi-inbox" }), h("span", componentProps.text)]) })
const DataSection = defineComponent({
	props: { title: String, count: Number, icon: String },
	setup(componentProps, { slots }) { return () => h("section", { class: "data-section erp-card" }, [h("header", { class: "data-section__header" }, [h("div", [componentProps.icon ? h("i", { class: componentProps.icon }) : null, h("h3", componentProps.title)]), h("span", componentProps.count || 0)]), h("div", { class: "data-section__body" }, slots.default?.())]) },
})

const QuantityTable = defineComponent({
	props: { group: Object },
	setup(componentProps) { return () => h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": "Planned quantities" }, h("table", { class: "data-table" }, [
		h("thead", h("tr", [h("th", "S.No."), ...groupAttributes(componentProps.group).map((attribute) => h("th", attribute)), ...sizes(componentProps.group).map((size) => h("th", { class: "number-cell" }, size)), h("th", { class: "number-cell" }, "Total")])),
		h("tbody", (componentProps.group.items || []).map((row, index) => h("tr", { key: row._row_key || index }, [h("td", index + 1), ...groupAttributes(componentProps.group).map((attribute) => h("td", row.attributes?.[attribute] || "—")), ...sizes(componentProps.group).map((size) => h("td", { class: "number-cell" }, numeric(valueTotal(row.values?.[size])))), h("td", { class: "number-cell strong-cell" }, numeric(rowTotal(row, componentProps.group)))]))),
	])) },
})

const CompletionTable = defineComponent({
	props: { group: Object, completed: Boolean },
	setup(componentProps) { return () => h("div", { class: "table-scroll", role: "region", tabindex: 0, "aria-label": componentProps.completed ? "Completed cut quantities" : "Excess cut quantities" }, h("table", { class: "data-table" }, [
		h("thead", h("tr", [h("th", "S.No."), ...groupAttributes(componentProps.group).map((attribute) => h("th", attribute)), ...sizes(componentProps.group).map((size) => h("th", { class: "number-cell" }, size)), h("th", { class: "number-cell" }, "Total"), componentProps.completed ? h("th", "Status") : null])),
		h("tbody", (componentProps.group.items || []).map((row, index) => h("tr", { key: index }, [h("td", index + 1), ...groupAttributes(componentProps.group).map((attribute) => h("td", row.attributes?.[attribute] || "—")), ...sizes(componentProps.group).map((size) => h("td", { class: "number-cell" }, numeric(valueTotal(row.values?.[size])))), h("td", { class: "number-cell strong-cell" }, numeric(rowTotal(row, componentProps.group))), componentProps.completed ? h("td", h("span", { class: ["completion-state", row.completed ? "completion-state--done" : ""] }, [h("i", { class: row.completed ? "pi pi-check-circle" : "pi pi-circle" }), row.completed ? "Completed" : "Open"])) : null]))),
	])) },
})
</script>

<style scoped>
.cutting-order-tabs { display: flex; min-height: 0; flex: 1; flex-direction: column; }
.cutting-order-tabs :deep(.p-tablist-tab-list) { flex: 0 0 auto; padding-inline: 3px; }
.cutting-order-tabs :deep(.p-tabpanels) { min-height: 0; padding: 12px 0 0; overflow-y: auto; }
.tab-stack { display: grid; gap: 12px; min-width: 0; padding-right: 3px; }
.cutting-order-tabs :deep(.data-section) { min-width: 0; padding: 0; overflow: hidden; }
.cutting-order-tabs :deep(.data-section__header) { display: flex; align-items: center; justify-content: space-between; min-height: 45px; padding: 9px 12px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }
.cutting-order-tabs :deep(.data-section__header > div) { display: flex; align-items: center; gap: 8px; }
.cutting-order-tabs :deep(.data-section__header h3) { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-body); }
.cutting-order-tabs :deep(.data-section__header i) { color: var(--erp-accent); }
.cutting-order-tabs :deep(.data-section__header > span) { padding: 3px 7px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; background: var(--erp-surface-muted); border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); }
.cutting-order-tabs :deep(.data-section__body) { display: grid; gap: 10px; padding: 10px; }
@media (max-width: 1050px) { .cutting-order-tabs :deep(.p-tabpanels) { overflow-y: visible; } }
.cutting-order-tabs :deep(.table-scroll) { max-width: 100%; overflow: auto; border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.cutting-order-tabs :deep(.data-table) { width: 100%; min-width: 720px; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
.cutting-order-tabs :deep(.data-table th), .cutting-order-tabs :deep(.data-table td) { padding: 8px 9px; text-align: left; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.cutting-order-tabs :deep(.data-table th) { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; background: var(--erp-surface-muted); }
.cutting-order-tabs :deep(.data-table th:last-child), .cutting-order-tabs :deep(.data-table td:last-child) { border-right: 0; }
.cutting-order-tabs :deep(.data-table tr:last-child td) { border-bottom: 0; }
.cutting-order-tabs :deep(.number-cell) { text-align: right !important; font-variant-numeric: tabular-nums; }
.cutting-order-tabs :deep(.strong-cell) { color: var(--erp-accent-hover); font-weight: 770; }
.cutting-order-tabs :deep(.completion-state) { display: inline-flex; align-items: center; gap: 5px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; }
.cutting-order-tabs :deep(.completion-state--done) { color: var(--erp-accent-dark); }
.planned-row { background: var(--erp-surface-soft); }
.completed-row { background: var(--erp-success-soft); }
.total-row td { color: var(--erp-text); font-weight: 760; background: var(--erp-accent-soft); }
.detail-kind { display: inline-flex; align-items: center; gap: 6px; font-size: var(--erp-font-size-min); font-weight: 720; }
.detail-kind i { width: 7px; height: 7px; background: var(--erp-text-muted); border-radius: 50%; }
.detail-kind--completed i { background: var(--erp-success); }
.cutting-order-tabs :deep(.empty-state) { display: grid; min-height: 100px; color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); place-items: center; align-content: center; gap: 8px; }
.cutting-order-tabs :deep(.empty-state i) { color: var(--erp-accent); font-size: 1.1rem; }
.cutting-order-tabs :deep(.loading-state) { display: grid; gap: 10px; }
@media (max-width: 780px) { .cutting-order-tabs :deep(.table-scroll) { -webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%); } }
</style>
