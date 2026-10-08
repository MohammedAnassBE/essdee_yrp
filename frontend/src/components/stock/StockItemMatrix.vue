<template>
	<section class="item-matrix" :class="{ 'item-matrix--grouped-by-item': groupByItem }">
		<header class="item-matrix__header">
			<div>
				<span class="item-matrix__eyebrow">Item breakdown</span>
				<h3>Items by attributes</h3>
			</div>
			<div class="item-matrix__counts">
				<span>{{ logicalRowCount }} {{ logicalRowCount === 1 ? "item" : "items" }}</span>
				<small v-if="physicalRowCount">{{ physicalRowCount }} quantity {{ physicalRowCount === 1 ? "line" : "lines" }}</small>
			</div>
		</header>

		<div class="item-matrix__body">
			<article v-for="(group, groupIndex) in displayGroups" :key="groupKey(group, groupIndex)" class="item-matrix__group">
				<header class="item-matrix__group-header">
					<div>
						<i v-if="!groupByItem" class="pi pi-th-large"></i>
						<strong>{{ groupByItem ? group.itemIdentity : group.primary_attribute ? `${group.primary_attribute} matrix` : "Quantity" }}</strong>
						<small v-if="groupByItem && group.itemLot && !showLotColumn">{{ group.itemLot }}</small>
						<small v-if="isPurchaseOrder && groupByItem && group.itemComment" class="item-matrix__item-comment">{{ group.itemComment }}</small>
					</div>
					<span>{{ group.items?.length || 0 }} {{ group.items?.length === 1 ? "row" : "rows" }}</span>
				</header>

				<div class="item-matrix__scroll" tabindex="0" role="region" :aria-label="`${groupByItem ? group.itemIdentity || 'Item' : 'Item'} quantity matrix`">
					<table>
						<thead>
							<tr>
								<th v-if="!groupByItem" class="item-matrix__index">#</th>
								<th v-if="!groupByItem">Item</th>
								<th v-for="column in leadingContextColumns(group)" :key="column.key">{{ column.label }}</th>
								<th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th>
								<th v-for="column in trailingContextColumns(group)" :key="column.key">{{ column.label }}</th>
								<th v-for="value in primaryValues(group)" :key="value" class="item-matrix__number">{{ primaryValueLabel(group, value) }}</th>
								<th v-if="showTotalColumn(group)" class="item-matrix__number">Total</th>
								<th>UOM</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td v-if="!groupByItem" class="item-matrix__index">{{ rowIndex + 1 }}</td>
								<td v-if="!groupByItem" class="item-matrix__item"><strong>{{ row.name || "—" }}</strong><small v-if="row.primary_attribute">{{ row.primary_attribute }}</small><small v-if="isPurchaseOrder && normalizedComment(row.comments)" class="item-matrix__item-comment">{{ normalizedComment(row.comments) }}</small></td>
								<td v-for="column in leadingContextColumns(group)" :key="column.key">{{ contextDisplay(row, column) }}</td>
								<td v-for="attribute in group.attributes || []" :key="attribute"><span class="item-matrix__attribute">{{ display(row.attributes?.[attribute]) }}</span></td>
								<td v-for="column in trailingContextColumns(group)" :key="column.key">{{ contextDisplay(row, column) }}</td>
								<td v-for="value in primaryValues(group)" :key="value" class="item-matrix__number item-matrix__qty">
									<strong>{{ formatQty(row.values?.[value]?.qty) }}</strong>
									<small v-if="secondaryQty(row.values?.[value])">{{ formatQty(row.values[value].secondary_qty) }} {{ row.values[value].secondary_uom || row.secondary_uom }}</small>
									<small v-if="showFulfillment && showReceived && hasFulfillment(row.values?.[value])" class="item-matrix__received">Received {{ formatQty(receivedQty(row.values[value])) }}</small>
									<small v-if="showAvailability && hasAvailability(row.values?.[value])" class="item-matrix__available">Available {{ formatQty(availabilityQty(row.values[value])) }}</small>
									<small v-if="showFulfillment && !pricingBeforeFulfillment && hasFulfillment(row.values?.[value])" class="item-matrix__pending">{{ fulfillmentLabel(row.values[value]) }}</small>
									<small v-if="showPricing" class="item-matrix__price">Rate {{ formatMoney(row.values?.[value]?.rate) }}</small>
									<small v-if="showPricing && showAmount" class="item-matrix__price">Amount {{ formatMoney(cellAmount(row.values?.[value])) }}</small>
									<small v-if="showFulfillment && pricingBeforeFulfillment && hasFulfillment(row.values?.[value])" class="item-matrix__pending">{{ fulfillmentLabel(row.values[value]) }}</small>
								</td>
								<td v-if="showTotalColumn(group)" class="item-matrix__number item-matrix__total item-matrix__qty"><strong>{{ formatQty(rowTotal(row)) }}</strong><small v-if="showFulfillment && showReceived && rowHasFulfillment(row)" class="item-matrix__received">Received {{ formatQty(rowMetricTotal(row, receivedQty)) }}</small><small v-if="showFulfillment && rowHasFulfillment(row)" class="item-matrix__pending">{{ fulfillmentTotalLabel(row) }}</small><small v-if="showPricing && showAmount" class="item-matrix__price">Amount {{ formatMoney(rowAmount(row)) }}</small></td>
								<td><span class="item-matrix__uom">{{ row.default_uom || "—" }}</span></td>
							</tr>
						</tbody>
					</table>
				</div>
			</article>
		</div>
	</section>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	groups: { type: Array, default: () => [] },
	doctype: { type: String, default: "" },
	physicalRowCount: { type: Number, default: 0 },
	groupByItem: { type: Boolean, default: false },
	showLotColumn: { type: Boolean, default: false },
	showPricing: { type: Boolean, default: false },
	showFulfillment: { type: Boolean, default: false },
	showAvailability: { type: Boolean, default: false },
	showReceived: { type: Boolean, default: true },
	showAmount: { type: Boolean, default: true },
	pricingBeforeFulfillment: { type: Boolean, default: false },
	currency: { type: String, default: "" },
})

const logicalRowCount = computed(() => props.groups.reduce((total, group) => total + (group.items?.length || 0), 0))
const isPurchaseOrder = computed(() => props.doctype === "Purchase Order")
const displayGroups = computed(() => {
	if (!props.groupByItem) return props.groups
	return props.groups.flatMap((group, groupIndex) => {
		const sections = new Map()
		for (const item of group.items || []) {
			const itemIdentity = item.name || "Unspecified item"
			const itemLot = item.dimensions?.lot || item.lot || ""
			const key = `${groupIndex}-${itemIdentity}-${itemLot}`
			if (!sections.has(key)) sections.set(key, { ...group, items: [], itemIdentity, itemLot, itemComments: [], itemGroupKey: key })
			const section = sections.get(key)
			section.items.push(item)
			const comment = normalizedComment(item.comments)
			if (comment && !section.itemComments.includes(comment)) section.itemComments.push(comment)
		}
		return Array.from(sections.values()).map((section) => ({ ...section, itemComment: section.itemComments.join(" · ") }))
	})
})

const fieldLabels = {
	lot: "Lot",
	received_type: "Received Type",
	warehouse: "Warehouse",
	from_lot: "From Lot",
	to_lot: "To Lot",
	delivery_location: "Delivery Location",
	schedule_date: "Required By",
	discount_percentage: "Discount",
}

const contextualFields = {
	"SD YRP Lot Transfer": ["from_lot", "to_lot", "warehouse", "received_type"],
	"Purchase Order": ["delivery_location", "schedule_date", "discount_percentage"],
}

function contextColumns(group) {
	const dimensionKeys = []
	for (const row of group.items || []) {
		for (const [key, value] of Object.entries(row.dimensions || {})) {
			if (value !== null && value !== undefined && value !== "" && !dimensionKeys.includes(key)) dimensionKeys.push(key)
		}
	}
	const extras = (contextualFields[props.doctype] || []).filter((key) => {
		if (dimensionKeys.includes(key)) return false
		return (group.items || []).some((row) => row[key] !== null && row[key] !== undefined && row[key] !== "")
	})
	return [...dimensionKeys, ...extras]
		.filter((key) => !(props.groupByItem && key === "lot" && !props.showLotColumn))
		.map((key) => ({ key, label: fieldLabels[key] || titleCase(key), dimension: dimensionKeys.includes(key) }))
}

function leadingContextColumns(group) { return contextColumns(group).filter((column) => !isPurchaseOrder.value || column.dimension) }
function trailingContextColumns(group) { return contextColumns(group).filter((column) => isPurchaseOrder.value && !column.dimension) }
function contextValue(row, column) { return column.dimension ? row.dimensions?.[column.key] : row[column.key] }
function contextDisplay(row, column) {
	const value = contextValue(row, column)
	if (isPurchaseOrder.value && column.key === "schedule_date") return formatDate(value)
	if (isPurchaseOrder.value && column.key === "discount_percentage") return value === null || value === undefined || value === "" ? "—" : `${formatQty(value)}%`
	return display(value)
}
function primaryValues(group) { return group.primary_attribute ? (group.primary_attribute_values || []) : ["default"] }
function primaryValueLabel(group, value) { return group.primary_attribute ? value : "Quantity" }
function showTotalColumn(group) { return primaryValues(group).length > 1 }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function cellAmount(value) { return Number(value?.total_amount ?? value?.amount ?? (Number(value?.qty || 0) * Number(value?.rate || 0))) }
function rowAmount(row) { return Object.values(row.values || {}).reduce((total, value) => total + cellAmount(value), 0) }
function hasFulfillment(value) { return value && ["received_qty", "received_quantity", "pending_qty", "pending_quantity"].some((key) => value[key] !== undefined && value[key] !== null) }
function hasAvailability(value) { return value && ["max_receivable_quantity", "pending_qty", "pending_quantity"].some((key) => value[key] !== undefined && value[key] !== null) }
function rowHasFulfillment(row) { return Object.values(row.values || {}).some(hasFulfillment) }
function receivedQty(value) { return Number(value?.received_qty ?? value?.received_quantity ?? 0) }
function availabilityQty(value) { return Number(value?.max_receivable_quantity ?? value?.pending_qty ?? value?.pending_quantity ?? 0) }
function pendingQty(value) { return Number(value?.pending_qty ?? value?.pending_quantity ?? 0) }
function fulfillmentLabel(value) { const quantity = pendingQty(value); return quantity < 0 ? `Over-received ${formatQty(Math.abs(quantity))}` : `Pending ${formatQty(quantity)}` }
function fulfillmentTotalLabel(row) { const quantity = rowMetricTotal(row, pendingQty); return quantity < 0 ? `Over-received ${formatQty(Math.abs(quantity))}` : `Pending ${formatQty(quantity)}` }
function rowMetricTotal(row, getter) { return Object.values(row.values || {}).reduce((total, value) => total + getter(value), 0) }
function secondaryQty(value) { return Number(value?.secondary_qty || 0) !== 0 }
function display(value) { return value === null || value === undefined || value === "" ? "—" : String(value) }
function formatDate(value) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})/); return match ? `${match[3]}-${match[2]}-${match[1]}` : display(value) }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function formatMoney(value) { return `${props.currency ? `${props.currency} ` : ""}${Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}` }
function normalizedComment(value) { return String(value || "").trim() }
function titleCase(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()) }
function groupKey(group, index) { return group.itemGroupKey || `${group.primary_attribute || "quantity"}-${(group.attributes || []).join("-")}-${index}` }
</script>

<style scoped>
.item-matrix {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.item-matrix__header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-4);
	padding: var(--erp-space-3) 14px;
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.item-matrix__eyebrow {
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.item-matrix__header h3 {
	margin: 2px 0 0;
	color: var(--erp-text);
	font-size: 14px;
}

.item-matrix__counts {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
}

.item-matrix__counts span {
	padding: 3px var(--erp-space-2);
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
}

.item-matrix__counts small,
.item-matrix__group-header span,
.item-matrix__item small,
.item-matrix__qty small,
.item-matrix__uom {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.item-matrix__price {
	color: var(--erp-text-secondary) !important;
	font-weight: 650;
}
.item-matrix__received { color: var(--erp-accent-dark) !important; font-weight: 700; }
.item-matrix__available { color: var(--erp-accent-dark) !important; font-weight: 700; }
.item-matrix__pending { color: var(--erp-attention-text) !important; font-weight: 700; }

.item-matrix__body {
	display: grid;
	gap: 10px;
	padding: 10px;
	background: var(--erp-surface-soft);
}

.item-matrix__group {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
	box-shadow: var(--erp-shadow-xs);
}

.item-matrix__group-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: var(--erp-space-2) 10px;
	border-bottom: 1px solid var(--erp-border);
}

.item-matrix__group-header > div {
	display: flex;
	align-items: center;
	gap: 7px;
}

.item-matrix--grouped-by-item .item-matrix__group-header > div {
	display: grid;
	gap: 2px;
}

.item-matrix__group-header small {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 700;
}

.item-matrix__item-comment {
	color: var(--erp-text-secondary) !important;
	font-weight: 500 !important;
	line-height: 1.35;
	overflow-wrap: anywhere;
	white-space: normal;
}

.item-matrix__group-header .item-matrix__item-comment {
	max-width: 72ch;
}

.item-matrix__group-header i {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-caption);
}

.item-matrix__group-header strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.item-matrix__scroll {
	max-height: 360px;
	overflow: auto;
}

.item-matrix--grouped-by-item .item-matrix__scroll {
	max-height: none;
	overflow-x: auto;
	overflow-y: visible;
}

.item-matrix table {
	width: 100%;
	min-width: 760px;
	border-collapse: separate;
	border-spacing: 0;
	font-size: var(--erp-font-size-caption);
}

.item-matrix th {
	position: sticky;
	z-index: 1;
	top: 0;
	padding: var(--erp-space-2) 9px;
	border-bottom: 1px solid var(--erp-border-strong);
	background: var(--erp-surface-muted);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: 0.025em;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
}

.item-matrix td {
	padding: 9px;
	border-bottom: 1px solid var(--erp-border-subtle);
	color: var(--erp-text-secondary);
	vertical-align: middle;
	white-space: nowrap;
}

.item-matrix tbody tr:last-child td {
	border-bottom: 0;
}

.item-matrix tbody tr:hover td {
	background: color-mix(in srgb, var(--erp-accent) 3%, white);
}

.item-matrix__index {
	width: 36px;
	color: var(--erp-text-muted) !important;
	text-align: center !important;
}

.item-matrix__item {
	display: grid;
	min-width: 170px;
	gap: 2px;
	white-space: normal !important;
}

.item-matrix__item strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.item-matrix__attribute {
	display: inline-flex;
	padding: 3px 7px;
	border: 1px solid var(--erp-border);
	border-radius: 6px;
	background: var(--erp-surface-soft);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
}

.item-matrix__number {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.item-matrix__qty strong {
	color: var(--erp-text);
	font-weight: 700;
}

.item-matrix__qty small {
	display: block;
	margin-top: 2px;
}

.item-matrix__total {
	color: var(--erp-accent) !important;
	font-weight: 800;
}

@media (max-width: 700px) {
	.item-matrix__header {
		align-items: flex-start;
		flex-direction: column;
	}

	.item-matrix__counts {
		width: 100%;
		justify-content: flex-start;
		flex-wrap: wrap;
	}
}
</style>
