<template>
	<section class="wo-delivery-matrix">
		<header>
			<div><span>Work Order deliverables</span><h3>{{ title }}</h3></div>
			<strong>{{ editableCellCount }} {{ editableCellCount === 1 ? "line" : "lines" }}</strong>
		</header>
		<div v-if="groups.length" class="wo-delivery-matrix__groups">
			<div v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="wo-delivery-matrix__card">
				<div class="wo-delivery-matrix__scroll">
					<table>
						<thead>
							<tr>
								<th>Item</th>
								<th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th>
								<th v-for="value in valueColumns(group)" :key="value" class="wo-delivery-matrix__qty">{{ value === "default" ? "Quantity" : value }}</th>
								<th class="wo-delivery-matrix__qty">Entered</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td><strong>{{ row.name }}</strong><small v-if="dimensionText(row)">{{ dimensionText(row) }}</small></td>
								<td v-for="attribute in group.attributes || []" :key="attribute">{{ row.attributes?.[attribute] || "—" }}</td>
								<td v-for="value in valueColumns(group)" :key="value" class="wo-delivery-matrix__qty">
									<div v-if="cell(row, value)?.ref_docname && !['0', 0].includes(cell(row, value)?.ref_docname)" class="wo-delivery-matrix__cell">
										<small>Pending {{ formatQty(cell(row, value)?.pending_quantity) }}</small>
										<input :value="quantity(cell(row, value)?.ref_docname)" type="number" min="0" step="0.001" aria-label="Delivery Quantity" @input="update(cell(row, value)?.ref_docname, $event.target.value)" />
									</div>
									<span v-else>—</span>
								</td>
								<td class="wo-delivery-matrix__qty wo-delivery-matrix__total">{{ formatQty(rowTotal(row)) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</div>
		</div>
		<div v-else class="wo-delivery-matrix__empty"><i class="pi pi-inbox"></i><span>No deliverables are available.</span></div>
	</section>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	title: { type: String, default: "Deliverables" },
	groups: { type: Array, default: () => [] },
	quantities: { type: Object, default: () => ({}) },
})
const emit = defineEmits(["update"])

const editableCellCount = computed(() => props.groups.reduce((count, group) => count + (group.items || []).reduce((rowCount, row) => rowCount + Object.values(row.values || {}).filter((value) => value?.ref_docname && !["0", 0].includes(value.ref_docname)).length, 0), 0))

function valueColumns(group) {
	return group.primary_attribute ? (group.primary_attribute_values || []) : ["default"]
}
function cell(row, value) { return row.values?.[value] || null }
function quantity(reference) { return Number(props.quantities?.[reference] || 0) }
function update(reference, value) { emit("update", reference, Math.max(0, Number(value || 0))) }
function rowTotal(row) { return Object.values(row.values || {}).reduce((sum, value) => sum + quantity(value?.ref_docname), 0) }
function formatQty(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 3 }) }
function groupKey(group, index) { return `${group.primary_attribute || "quantity"}-${(group.attributes || []).join("-")}-${index}` }
function dimensionText(row) {
	return Object.values(row.dimensions || {}).filter(Boolean).join(" · ")
}
</script>

<style scoped>
.wo-delivery-matrix{overflow:hidden;border:1px solid #dce7e1;border-radius:11px;background:#fff}.wo-delivery-matrix>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 13px;border-bottom:1px solid #e3ebe7;background:#fbfdfc}.wo-delivery-matrix>header div{display:grid;gap:2px}.wo-delivery-matrix>header span{color:#0a8351;font-size:.61rem;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.wo-delivery-matrix h3{margin:0;color:#233b2f;font-size:.86rem}.wo-delivery-matrix>header>strong{padding:4px 8px;border-radius:999px;background:#e7f5ed;color:#08794a;font-size:.66rem}.wo-delivery-matrix__groups{display:grid;gap:10px;padding:10px;background:#f7faf8}.wo-delivery-matrix__card{overflow:hidden;border:1px solid #dce7e1;border-radius:9px;background:#fff}.wo-delivery-matrix__scroll{overflow:auto;max-height:320px}.wo-delivery-matrix table{width:100%;min-width:760px;border-collapse:collapse;font-size:.7rem}.wo-delivery-matrix th{position:sticky;top:0;z-index:1;padding:7px 8px;background:#f1f6f3;color:#59675f;font-size:.61rem;letter-spacing:.02em;text-align:left;text-transform:uppercase;white-space:nowrap}.wo-delivery-matrix td{padding:8px;border-top:1px solid #e7edea;color:#374a40;vertical-align:middle;white-space:nowrap}.wo-delivery-matrix td:first-child{min-width:170px}.wo-delivery-matrix td:first-child strong,.wo-delivery-matrix td:first-child small{display:block}.wo-delivery-matrix td:first-child strong{color:#21382c;font-size:.72rem}.wo-delivery-matrix td:first-child small{margin-top:2px;color:#78847d;font-size:.61rem}.wo-delivery-matrix__qty{text-align:right!important;font-variant-numeric:tabular-nums}.wo-delivery-matrix__cell{display:grid;justify-items:end;gap:3px;min-width:92px}.wo-delivery-matrix__cell small{color:#748179;font-size:.58rem}.wo-delivery-matrix__cell input{width:84px;height:31px;padding:4px 7px;border:1px solid #cfdbd4;border-radius:6px;color:#24382d;font:inherit;text-align:right}.wo-delivery-matrix__cell input:focus{border-color:#52ad83;outline:2px solid rgb(11 143 85 / 10%)}.wo-delivery-matrix__total{color:#087a4a!important;font-weight:800}.wo-delivery-matrix__empty{display:flex;align-items:center;justify-content:center;gap:8px;min-height:90px;color:#77847c;font-size:.7rem}.wo-delivery-matrix__empty i{color:#0a8551}
</style>
