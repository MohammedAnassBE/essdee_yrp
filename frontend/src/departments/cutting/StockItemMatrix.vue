<template>
	<section class="item-matrix">
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
			<article v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="item-matrix__group">
				<header class="item-matrix__group-header">
					<div>
						<i class="pi pi-th-large"></i>
						<strong>{{ group.primary_attribute ? `${group.primary_attribute} matrix` : "Quantity" }}</strong>
					</div>
					<span>{{ group.items?.length || 0 }} {{ group.items?.length === 1 ? "row" : "rows" }}</span>
				</header>

				<div class="item-matrix__scroll">
					<table>
						<thead>
							<tr>
								<th class="item-matrix__index">#</th>
								<th>Item</th>
								<th v-for="column in contextColumns(group)" :key="column.key">{{ column.label }}</th>
								<th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th>
								<th v-for="value in primaryValues(group)" :key="value" class="item-matrix__number">{{ primaryValueLabel(group, value) }}</th>
								<th class="item-matrix__number">Total</th>
								<th>UOM</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td class="item-matrix__index">{{ rowIndex + 1 }}</td>
								<td class="item-matrix__item"><strong>{{ row.name || "—" }}</strong><small v-if="row.primary_attribute">{{ row.primary_attribute }}</small></td>
								<td v-for="column in contextColumns(group)" :key="column.key">{{ display(contextValue(row, column)) }}</td>
								<td v-for="attribute in group.attributes || []" :key="attribute"><span class="item-matrix__attribute">{{ display(row.attributes?.[attribute]) }}</span></td>
								<td v-for="value in primaryValues(group)" :key="value" class="item-matrix__number item-matrix__qty">
									<strong>{{ formatQty(row.values?.[value]?.qty) }}</strong>
									<small v-if="secondaryQty(row.values?.[value])">{{ formatQty(row.values[value].secondary_qty) }} {{ row.values[value].secondary_uom || row.secondary_uom }}</small>
								</td>
								<td class="item-matrix__number item-matrix__total">{{ formatQty(rowTotal(row)) }}</td>
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
})

const logicalRowCount = computed(() => props.groups.reduce((total, group) => total + (group.items?.length || 0), 0))

const fieldLabels = {
	lot: "Lot",
	received_type: "Received Type",
	warehouse: "Warehouse",
	from_lot: "From Lot",
	to_lot: "To Lot",
}

const contextualFields = {
	"SD YRP Lot Transfer": ["from_lot", "to_lot", "warehouse", "received_type"],
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
	return [...dimensionKeys, ...extras].map((key) => ({ key, label: fieldLabels[key] || titleCase(key), dimension: dimensionKeys.includes(key) }))
}

function contextValue(row, column) { return column.dimension ? row.dimensions?.[column.key] : row[column.key] }
function primaryValues(group) { return group.primary_attribute ? (group.primary_attribute_values || []) : ["default"] }
function primaryValueLabel(group, value) { return group.primary_attribute ? value : "Quantity" }
function rowTotal(row) { return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0) }
function secondaryQty(value) { return Number(value?.secondary_qty || 0) !== 0 }
function display(value) { return value === null || value === undefined || value === "" ? "—" : String(value) }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function titleCase(value) { return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase()) }
function groupKey(group, index) { return `${group.primary_attribute || "quantity"}-${(group.attributes || []).join("-")}-${index}` }
</script>

<style scoped>
.item-matrix{overflow:hidden;border:1px solid #dce7e1;border-radius:11px;background:#fff;box-shadow:0 4px 16px rgb(26 77 52 / 4%)}.item-matrix__header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px;border-bottom:1px solid #dfe9e4;background:linear-gradient(180deg,#fbfdfc 0%,#f7fbf9 100%)}.item-matrix__eyebrow{color:#078451;font-size:.61rem;font-weight:800;letter-spacing:.09em;text-transform:uppercase}.item-matrix__header h3{margin:2px 0 0;color:#20382c;font-size:.9rem}.item-matrix__counts{display:flex;align-items:center;gap:8px}.item-matrix__counts span{padding:4px 8px;border-radius:999px;background:#e4f5eb;color:#08794a;font-size:.68rem;font-weight:750}.item-matrix__counts small{color:#748078;font-size:.66rem}.item-matrix__body{display:grid;gap:10px;padding:10px;background:#f7faf8}.item-matrix__group{overflow:hidden;border:1px solid #dce7e1;border-radius:9px;background:#fff}.item-matrix__group-header{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;border-bottom:1px solid #e4ebe7}.item-matrix__group-header>div{display:flex;align-items:center;gap:7px}.item-matrix__group-header i{color:#0b8b56;font-size:.72rem}.item-matrix__group-header strong{color:#2a4034;font-size:.74rem}.item-matrix__group-header span{color:#77847d;font-size:.64rem}.item-matrix__scroll{overflow:auto;max-height:360px}.item-matrix table{width:100%;min-width:760px;border-collapse:separate;border-spacing:0;font-size:.72rem}.item-matrix th{position:sticky;z-index:1;top:0;padding:8px 9px;border-bottom:1px solid #dfe8e3;background:#eef5f1;color:#58675f;font-size:.61rem;font-weight:750;letter-spacing:.025em;text-align:left;text-transform:uppercase;white-space:nowrap}.item-matrix td{padding:9px;border-bottom:1px solid #e7edea;color:#374a40;vertical-align:middle;white-space:nowrap}.item-matrix tbody tr:last-child td{border-bottom:0}.item-matrix tbody tr:hover td{background:#fbfdfc}.item-matrix__index{width:36px;color:#859189!important;text-align:center!important}.item-matrix__item{display:grid;gap:2px;min-width:170px;white-space:normal!important}.item-matrix__item strong{color:#20382c;font-size:.73rem}.item-matrix__item small{color:#77847d;font-size:.61rem}.item-matrix__attribute{display:inline-flex;padding:3px 7px;border:1px solid #dce8e1;border-radius:6px;background:#f7faf8;color:#40584b;font-size:.67rem}.item-matrix__number{text-align:right!important;font-variant-numeric:tabular-nums}.item-matrix__qty strong{color:#283e32;font-weight:700}.item-matrix__qty small{display:block;margin-top:2px;color:#7b877f;font-size:.58rem}.item-matrix__total{color:#087b4a!important;font-weight:800}.item-matrix__uom{color:#64736a;font-size:.66rem}@media(max-width:700px){.item-matrix__header{align-items:flex-start;flex-direction:column}.item-matrix__counts{width:100%;justify-content:space-between}}
</style>
