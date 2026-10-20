<template>
	<div v-if="itemSections.length" class="work-order-matrix-stack">
		<section v-for="section in itemSections" :key="section.key" class="work-order-item-group work-order-item-matrix">
			<header class="work-order-item-group__header">
				<div>
					<strong><DocumentLink doctype="Item" :name="section.name" :label="section.name || 'Unspecified item'" /></strong>
					<span v-if="section.lot"><DocumentLink doctype="SD YRP Lot" :name="section.lot" /></span>
					<template v-if="processCostViewRouteName">
						<RouterLink v-for="name in processCostNames(section.items)" :key="name" :to="{ name: processCostViewRouteName, params: { processCostId: name } }">Process Cost · {{ name }}</RouterLink>
					</template>
				</div>
				<span>{{ section.items.length }} {{ section.items.length === 1 ? "combination" : "combinations" }}</span>
			</header>
			<div class="erp-table-wrap work-order-item-matrix__scroll" role="region" tabindex="0" :aria-label="`${section.name || 'Work Order item'} quantities`">
				<table class="erp-data-table work-order-item-matrix__table">
					<thead>
						<tr v-if="mode === 'items' && !hasPrimaryBreakdown(section.group)">
							<th v-for="attribute in identityAttributes(section.group)" :key="attribute">{{ attribute }}</th>
							<th class="erp-number">Quantity</th>
							<th class="erp-number matrix-pending-heading">Pending</th>
							<th v-if="hasCost(section.group)" class="erp-number matrix-cost-heading">Unit Cost</th>
							<th v-if="hasTotalCost(section.group)" class="erp-number matrix-cost-heading">Total Cost</th>
							<th v-if="hasProcessCost(section.group)">Process Cost</th>
						</tr>
						<tr v-else-if="mode === 'items'">
							<th v-for="attribute in identityAttributes(section.group)" :key="attribute">{{ attribute }}</th>
							<th>Details</th>
							<th v-for="value in primaryValues(section.group)" :key="value" class="erp-number">{{ value }}</th>
							<th class="erp-number">Total</th>
						</tr>
						<tr v-else>
							<th v-for="attribute in identityAttributes(section.group)" :key="attribute">{{ attribute }}</th>
							<th>Details</th>
							<th v-for="value in primaryValues(section.group)" :key="value" class="erp-number">{{ value === "default" ? "Qty" : value }}</th>
							<th class="erp-number">Total</th>
						</tr>
					</thead>
					<tbody v-if="mode === 'items' && !hasPrimaryBreakdown(section.group)">
						<tr v-for="(item, itemIndex) in section.items" :key="`${section.key}-${itemIndex}`">
							<td v-for="attribute in identityAttributes(section.group)" :key="attribute">
								{{ attributeValue(item, attribute) }}
							</td>
							<td class="erp-number matrix-quantity"><strong>{{ quantity(metric(item, "default", "planned")) }}</strong></td>
							<td class="erp-number matrix-pending">{{ pendingQuantity(metric(item, "default", "pending")) }}</td>
							<td v-if="hasCost(section.group)" class="erp-number matrix-cost">{{ money(item.values?.default?.cost) }}</td>
							<td v-if="hasTotalCost(section.group)" class="erp-number matrix-cost">{{ money(item.values?.default?.total_cost) }}</td>
							<td v-if="hasProcessCost(section.group)" class="matrix-process-cost"><DocumentLink doctype="YRP Process Cost" :name="item.process_cost" :label="item.process_cost || '—'" /></td>
						</tr>
					</tbody>
					<tbody v-else-if="mode === 'items'">
						<template v-for="(item, itemIndex) in section.items" :key="`${section.key}-${itemIndex}`">
							<tr v-for="(stage, stageIndex) in itemStages(item, section.group)" :key="stage.key" :class="`matrix-stage matrix-stage--${stage.key}`">
								<template v-if="stageIndex === 0"><td v-for="attribute in identityAttributes(section.group)" :key="attribute" :rowspan="itemStages(item, section.group).length">{{ attributeValue(item, attribute) }}</td></template>
								<td class="matrix-stage-label"><span>{{ stage.label }}</span></td>
								<td v-for="value in primaryValues(section.group)" :key="value" class="erp-number">{{ stageValue(stage, value) }}</td>
								<td class="erp-number matrix-total">{{ stageTotal(stage) }}</td>
							</tr>
						</template>
					</tbody>
					<tbody v-else>
						<template v-for="(item, itemIndex) in section.items" :key="`${section.key}-${itemIndex}`">
							<tr v-for="(stage, stageIndex) in stageRows(item, section.group)" :key="stage.key" :class="`matrix-stage matrix-stage--${stage.key}`">
								<template v-if="stageIndex === 0">
									<td v-for="attribute in identityAttributes(section.group)" :key="attribute" :rowspan="stageRows(item, section.group).length">
										{{ attributeValue(item, attribute) }}
									</td>
								</template>
								<td class="matrix-stage-label"><span>{{ stage.label }}</span></td>
								<td v-for="value in primaryValues(section.group)" :key="value" class="erp-number">{{ quantity(stage.values[value]) }}</td>
								<td class="erp-number matrix-total">{{ quantity(stage.total) }}</td>
							</tr>
						</template>
					</tbody>
				</table>
			</div>
		</section>
	</div>
	<div v-else class="erp-empty-state work-order-matrix-empty">
		<div><i class="pi pi-inbox" /><strong>No item details</strong><span>No rows are available for this section.</span></div>
	</div>
</template>

<script setup>
import { computed } from "vue"
import DocumentLink from "../../components/common/DocumentLink.vue"

const props = defineProps({
	groups: { type: Array, default: () => [] },
	mode: { type: String, default: "items" },
	processCostViewRouteName: { type: String, default: "" },
})

const itemSections = computed(() => props.groups.flatMap((group, groupIndex) => {
	const sections = new Map()
	for (const item of group.items || []) {
		const name = item.name || ""
		const lot = item.dimensions?.lot || item.lot || ""
		const key = `${groupIndex}-${name || "item"}-${lot}`
		if (!sections.has(key)) sections.set(key, { group, name, lot, key, items: [] })
		sections.get(key).items.push(item)
	}
	return Array.from(sections.values())
}))

function primaryValues(group) {
	return group.primary_attribute_values?.length ? group.primary_attribute_values : ["default"]
}

function processCostNames(items) {
	return [...new Set(items.map((item) => item.process_cost).filter(Boolean))]
}

function hasPrimaryBreakdown(group) {
	const values = primaryValues(group)
	return values.length > 1 || values[0] !== "default"
}

function hasValueField(group, fieldname) {
	return (group.items || []).some((item) => Object.values(item.values || {}).some((value) => value?.[fieldname] !== undefined && value?.[fieldname] !== null))
}

function hasCost(group) { return hasValueField(group, "cost") }
function hasTotalCost(group) { return hasValueField(group, "total_cost") }
function hasProcessCost(group) { return (group.items || []).some((item) => Boolean(item.process_cost)) }

function identityAttributes(group) {
	const values = [...(group.attributes || [])]
	if (group.pack_attr && !values.includes(group.pack_attr)) values.unshift(group.pack_attr)
	return values.filter((value) => value && value !== group.primary_attribute)
}

function attributeValue(item, attribute) {
	const value = item.attributes?.[attribute]
	if (!value) return "—"
	const major = item.item_keys?.major_colour
	return attribute === "Colour" && major && major !== value ? `${value} (${major})` : value
}

function metric(item, primary, key) {
	const values = item.values?.[primary] || {}
	if (props.mode === "additional") return Math.abs(Math.min(0, Number(values.pending_qty ?? values.pending_quantity ?? 0)))
	if (key === "pending") {
		if (props.mode === "summary") return Number(values.delivered || 0) - Number(values.received || 0)
		return values.pending_qty ?? values.pending_quantity ?? 0
	}
	if (key === "planned") return values.qty ?? values.quantity ?? 0
	return values[key] ?? 0
}

function metricTotal(item, group, key) {
	if (props.mode === "summary") {
		if (key === "planned") return item.total_qty
		if (key === "delivered") return item.total_delivered
		if (key === "received") return item.total_received
		if (key === "pending") return Number(item.total_delivered || 0) - Number(item.total_received || 0)
	}
	return primaryValues(group).reduce((total, value) => total + Number(metric(item, value, key) || 0), 0)
}

function valueTotal(item, group, key) {
	return primaryValues(group).reduce((total, value) => total + Number(item.values?.[value]?.[key] || 0), 0)
}

function itemStages(item, group) {
	const definitions = [["planned", "Quantity"], ["pending", "Pending"]]
	if (hasCost(group)) definitions.push(["cost", "Unit cost"])
	if (hasTotalCost(group)) definitions.push(["total_cost", "Total cost"])
	return definitions.map(([key, label]) => ({
		key,
		label,
		values: Object.fromEntries(primaryValues(group).map((value) => [value, key === "planned" || key === "pending" ? metric(item, value, key) : item.values?.[value]?.[key]])),
		total: key === "cost" ? null : key === "planned" || key === "pending" ? metricTotal(item, group, key) : valueTotal(item, group, key),
	}))
}
function stageValue(stage, value) { return ["cost", "total_cost"].includes(stage.key) ? money(stage.values[value]) : quantity(stage.values[value]) }
function stageTotal(stage) { return stage.total === null ? "—" : ["cost", "total_cost"].includes(stage.key) ? money(stage.total) : quantity(stage.total) }

function stageDefinitions() {
	if (props.mode === "additional") return [["additional", "Additional"]]
	if (props.mode === "recut") return [["planned", "Quantity"]]
	return props.mode === "summary"
		? [["planned", "Planned"], ["delivered", "Delivered"], ["received", "Received"], ["pending", "Pending"]]
		: [["planned", "Quantity"], ["pending", "Pending"]]
}

function stageRows(item, group) {
	return stageDefinitions().map(([key, label]) => ({
		key,
		label,
		values: Object.fromEntries(primaryValues(group).map((value) => [value, metric(item, value, key)])),
		total: metricTotal(item, group, key),
	}))
}

function quantity(value) {
	if (value === null || value === undefined || value === "") return "—"
	const parsed = Number(value)
	return parsed.toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

function pendingQuantity(value) {
	const parsed = Number(value || 0)
	return parsed.toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

function money(value) {
	if (value === null || value === undefined || value === "") return "—"
	return Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.work-order-matrix-stack { display: grid; min-width: 0; gap: var(--erp-space-3); }
.work-order-item-matrix { overflow: hidden; min-width: 0; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: 0 3px 10px rgb(28 61 45 / 3%); }
.work-order-item-group__header { display: flex; min-height: 42px; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 10px; background: color-mix(in srgb, var(--erp-surface-soft) 76%, var(--erp-surface)); border-bottom: 1px solid var(--erp-border); }
.work-order-item-group__header > div { display: grid; min-width: 0; gap: 2px; }
.work-order-item-group__header strong,
.work-order-item-group__header span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.work-order-item-group__header strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.work-order-item-group__header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; }
.work-order-item-group__header > span { flex: 0 0 auto; padding: 3px 7px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-pill-radius); }
.work-order-item-matrix__scroll { max-height: none; overflow-x: auto; overflow-y: visible; }
.work-order-item-matrix__table { min-width: 620px; }
.work-order-item-matrix__table th,
.work-order-item-matrix__table td { white-space: nowrap; }
.work-order-item-matrix__table :is(th, td) { padding-top: 7px; padding-bottom: 7px; }
.matrix-quantity { min-width: 76px; }
.matrix-quantity strong { display: block; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 750; }
.matrix-pending-heading, .matrix-pending { background: #fffaf0; }
.matrix-cost-heading, .matrix-cost { background: #f4faf7; }
.matrix-cost, .matrix-process-cost { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; }
.matrix-pending { min-width: 76px; color: #765b20; font-size: var(--erp-font-size-caption); font-weight: 750; }
.matrix-stage-label span { display: inline-flex; min-width: 68px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 750; }
.matrix-stage--pending td { background: #fffaf0; }
.matrix-stage--received .matrix-stage-label span,
.matrix-stage--delivered .matrix-stage-label span { color: var(--erp-success-text); }
.matrix-total { color: var(--erp-text); font-weight: 800; }
.work-order-matrix-empty { min-height: 130px; }
.work-order-matrix-empty div { display: grid; justify-items: center; gap: 6px; }
@media (max-width: 620px) {
	.work-order-matrix-empty { min-height: 78px; padding: 12px; }
	.work-order-matrix-empty div { grid-template-columns: auto 1fr; align-items: center; justify-items: start; column-gap: 9px; }
	.work-order-matrix-empty i { grid-row: 1 / span 2; }
	.work-order-matrix-empty span { text-align: left; }
}
</style>
