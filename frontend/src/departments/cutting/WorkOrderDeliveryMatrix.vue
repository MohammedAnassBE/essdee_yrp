<template>
	<section class="wo-delivery-matrix">
		<header>
			<div><span>Work Order deliverables</span><h3>{{ title }}</h3></div>
			<strong>{{ editableCellCount }} {{ editableCellCount === 1 ? "line" : "lines" }}</strong>
		</header>
		<div v-if="groups.length" class="wo-delivery-matrix__groups">
			<div v-for="(group, groupIndex) in groups" :key="groupKey(group, groupIndex)" class="wo-delivery-matrix__card">
				<div class="wo-delivery-matrix__scroll" role="region" tabindex="0" :aria-label="`${title} group ${groupIndex + 1}`">
					<table>
						<thead>
							<tr>
								<th>Item</th>
								<th v-for="attribute in group.attributes || []" :key="attribute" class="wo-delivery-matrix__attribute-column">{{ attribute }}</th>
								<th v-for="value in valueColumns(group)" :key="value" class="wo-delivery-matrix__qty">{{ value === "default" ? "Quantity" : value }}</th>
								<th class="wo-delivery-matrix__qty">Entered</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, rowIndex) in group.items || []" :key="`${row.name}-${rowIndex}`">
								<td><strong>{{ row.name }}</strong><small v-if="dimensionText(row)">{{ dimensionText(row) }}</small><small v-if="attributeText(row, group)" class="wo-delivery-matrix__mobile-attributes">{{ attributeText(row, group) }}</small></td>
								<td v-for="attribute in group.attributes || []" :key="attribute" class="wo-delivery-matrix__attribute-column">{{ row.attributes?.[attribute] || "—" }}</td>
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
function attributeText(row, group) {
	return (group.attributes || []).map((attribute) => row.attributes?.[attribute]).filter(Boolean).join(" · ")
}
</script>

<style scoped>
.wo-delivery-matrix {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
}

.wo-delivery-matrix > header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: 10px var(--erp-space-3);
	border-bottom: 1px solid var(--erp-border);
	background: var(--erp-surface-soft);
}

.wo-delivery-matrix > header div {
	display: grid;
	gap: 2px;
}

.wo-delivery-matrix > header span {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: 0.055em;
	text-transform: uppercase;
}

.wo-delivery-matrix h3 {
	margin: 0;
	color: var(--erp-text);
	font-size: 14px;
}

.wo-delivery-matrix > header > strong {
	padding: 3px var(--erp-space-2);
	border-radius: var(--erp-pill-radius);
	background: var(--erp-accent-soft);
	color: var(--erp-accent);
	font-size: var(--erp-font-size-min);
}

.wo-delivery-matrix__groups {
	display: grid;
	gap: 10px;
	padding: 10px;
	background: var(--erp-surface-soft);
}

.wo-delivery-matrix__card {
	overflow: hidden;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface);
}

.wo-delivery-matrix__scroll {
	max-height: 320px;
	overflow: auto;
}

.wo-delivery-matrix__scroll:focus-visible {
	outline: 2px solid var(--erp-accent-dark);
	outline-offset: -2px;
}

.wo-delivery-matrix table {
	width: 100%;
	min-width: 760px;
	border-collapse: collapse;
	font-size: var(--erp-font-size-caption);
}

.wo-delivery-matrix th {
	position: sticky;
	z-index: 1;
	top: 0;
	padding: 7px var(--erp-space-2);
	background: var(--erp-surface-muted);
	border-bottom: 1px solid var(--erp-border-strong);
	color: var(--erp-text-secondary);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: 0.02em;
	text-align: left;
	text-transform: uppercase;
	white-space: nowrap;
}

.wo-delivery-matrix td {
	padding: var(--erp-space-2);
	border-top: 1px solid var(--erp-border);
	color: var(--erp-text-secondary);
	vertical-align: middle;
	white-space: nowrap;
}

.wo-delivery-matrix td:first-child {
	min-width: 170px;
}

@media (max-width: 620px) {
	.wo-delivery-matrix__groups {
		gap: 0;
		padding: 0;
		background: var(--erp-surface);
	}

	.wo-delivery-matrix__card {
		border: 0;
		border-radius: 0;
	}

	.wo-delivery-matrix__card + .wo-delivery-matrix__card {
		border-top: 1px solid var(--erp-border);
	}

	.wo-delivery-matrix__scroll {
		-webkit-mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
		mask-image: linear-gradient(to right, #000 0, #000 calc(100% - 18px), transparent 100%);
	}

	.wo-delivery-matrix__attribute-column {
		display: none;
	}

	.wo-delivery-matrix table {
		min-width: max(560px, 100%);
	}

	.wo-delivery-matrix th:first-child,
	.wo-delivery-matrix td:first-child {
		width: 170px;
		min-width: 170px;
		max-width: 170px;
		overflow: hidden;
	}

}

.wo-delivery-matrix td:first-child strong,
.wo-delivery-matrix td:first-child small {
	display: block;
}

.wo-delivery-matrix td:first-child strong {
	color: var(--erp-text);
	font-size: var(--erp-font-size-caption);
}

.wo-delivery-matrix td:first-child small,
.wo-delivery-matrix__cell small {
	margin-top: 2px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
}

.wo-delivery-matrix__mobile-attributes {
	display: none !important;
}

@media (max-width: 620px) {
	.wo-delivery-matrix__mobile-attributes {
		display: block !important;
		max-width: 165px;
		overflow: hidden;
		text-overflow: ellipsis;
	}
}

.wo-delivery-matrix__qty {
	font-variant-numeric: tabular-nums;
	text-align: right !important;
}

.wo-delivery-matrix__cell {
	display: grid;
	min-width: 92px;
	justify-items: end;
	gap: 3px;
}

.wo-delivery-matrix__cell input {
	width: 84px;
	height: var(--erp-control-height-compact);
	padding: 4px 7px;
	border: 1px solid var(--erp-border-strong);
	border-radius: 6px;
	color: var(--erp-text);
	font: inherit;
	font-size: 13px;
	font-variant-numeric: tabular-nums;
	text-align: right;
}

.wo-delivery-matrix__cell input:focus {
	border-color: var(--erp-accent);
	outline: 2px solid color-mix(in srgb, var(--erp-accent) 12%, transparent);
}

@media (max-width: 620px) {
	.wo-delivery-matrix__cell {
		justify-items: start;
	}
}

.wo-delivery-matrix__total {
	color: var(--erp-accent) !important;
	font-weight: 800;
}

.wo-delivery-matrix__empty {
	display: flex;
	min-height: 90px;
	align-items: center;
	justify-content: center;
	gap: var(--erp-space-2);
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.wo-delivery-matrix__empty i {
	color: var(--erp-accent);
}
</style>
