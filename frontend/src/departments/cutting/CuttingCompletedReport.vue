<template>
	<article class="completed-report">
		<header class="completed-report__meta">
			<div class="completed-report__meta-item">
				<span>{{ referenceLabel }}</span>
				<strong>{{ referenceValue || doc.lot || "—" }}</strong>
			</div>
			<div class="completed-report__meta-item">
				<span>Item</span>
				<strong>{{ doc.item || "—" }}</strong>
			</div>
			<div class="completed-report__meta-item completed-report__meta-item--time">
				<span>Generated</span>
				<strong class="completed-report__generated">{{ generatedAt }}</strong>
			</div>
		</header>

		<div v-if="sections.length" class="completed-report__sections">
			<section v-for="(section, sectionIndex) in sections" :key="section.key" class="completed-report__group">
				<h3 :id="`completed-report-section-${sectionIndex}`" class="completed-report__sr-only">
					{{ section.part ? `Completed cut quantity for ${section.part}` : "Completed cut quantity" }}
				</h3>
				<header v-if="section.part || section.panels.length" class="completed-report__group-header">
					<div v-if="section.part" class="completed-report__part">
						<span>Part</span>
						<strong>{{ section.part }}</strong>
					</div>
					<div v-if="section.panels.length" class="completed-report__panels">
						<span>Panels</span>
						<div class="completed-report__panel-list">
							<span v-for="panel in section.panels" :key="panel" class="completed-report__panel">{{ panel }}</span>
						</div>
					</div>
				</header>

				<div class="completed-report__table-wrap">
					<table class="completed-report__table" :aria-labelledby="`completed-report-section-${sectionIndex}`">
						<thead>
							<tr>
								<th scope="col">S.No.</th>
								<th v-for="attribute in section.attributes" :key="attribute" scope="col">{{ attribute }}</th>
								<th v-for="value in section.primaryValues" :key="value" scope="col" class="number-cell">{{ value }}</th>
								<th scope="col" class="number-cell">Total</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(item, itemIndex) in section.items" :key="item.name || itemIndex" class="completed-report__item-row">
								<td>{{ itemIndex + 1 }}</td>
								<td v-for="attribute in section.attributes" :key="attribute">{{ displayAttribute(item, attribute, section.group) }}</td>
								<td v-for="value in section.primaryValues" :key="value" class="number-cell">{{ displayQuantity(item.values?.[value]) }}</td>
								<td class="number-cell completed-report__row-total">{{ rowTotal(item, section.primaryValues) }}</td>
							</tr>
							<tr class="completed-report__total-row">
								<th scope="row">Total</th>
								<td v-for="attribute in section.attributes" :key="attribute"></td>
								<td v-for="value in section.primaryValues" :key="value" class="number-cell">{{ columnTotal(section.items, value) }}</td>
								<td class="number-cell">{{ sectionTotal(section) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>

		<div v-else class="completed-report__empty">
			<i class="pi pi-inbox" aria-hidden="true" />
			<strong>No completed cut quantities</strong>
			<span>Completed rows will appear here after they are updated.</span>
		</div>
	</article>
</template>

<script setup>
import { computed } from "vue"

const props = defineProps({
	doc: { type: Object, required: true },
	groups: { type: [Array, Object], default: () => [] },
	generatedAt: { type: String, required: true },
	referenceLabel: { type: String, default: "Lot" },
	referenceValue: { type: String, default: "" },
})

const sections = computed(() => normaliseGroups(props.groups).flatMap((group, groupIndex) => {
	const completedItems = (group.items || []).filter((item) => Boolean(item.completed))
	if (!completedItems.length) return []

	const attributes = Array.from(group.attributes || [])
	const primaryValues = Array.from(group.primary_attribute_values || [])
	if (!group.is_set_item) {
		return [{
			key: `group-${groupIndex}`,
			group,
			attributes,
			primaryValues,
			items: completedItems,
			part: "",
			panels: normalisePanels(group?.[group?.stiching_attr]),
		}]
	}

	const partAttribute = group.set_item_attr || completedItems[0]?.set_attr
	const panelMap = group?.[group?.stiching_attr] || {}
	const parts = Array.from(new Set([
		...Object.keys(panelMap && !Array.isArray(panelMap) ? panelMap : {}),
		...completedItems.map((item) => item.attributes?.[partAttribute]).filter(Boolean),
	]))

	return parts.flatMap((part) => {
		const items = completedItems.filter((item) => item.attributes?.[partAttribute] === part)
		if (!items.length) return []
		return [{
			key: `group-${groupIndex}-part-${part}`,
			group,
			attributes,
			primaryValues,
			items,
			part,
			panels: [],
		}]
	})
}))

function normaliseGroups(value) {
	if (Array.isArray(value)) return value.filter((group) => group?.items)
	if (value?.items) return [value]
	if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items)
	return []
}

function normalisePanels(value) {
	if (Array.isArray(value)) return value.filter(Boolean)
	if (typeof value === "string") return value.split(",").map((panel) => panel.trim()).filter(Boolean)
	return []
}

function numeric(value) {
	const number = Number(value || 0)
	return Number.isFinite(number) ? number : 0
}

function displayQuantity(value) {
	return numeric(value) || "—"
}

function displayAttribute(item, attribute, group) {
	const value = item.attributes?.[attribute]
	if (!value) return "—"
	if (!["V2", "V3"].includes(props.doc.version) || attribute !== "Colour") return value

	const majorColour = item.item_keys?.major_colour
	const setAttribute = group.set_item_attr || item.set_attr
	const differsFromMajorPart = item.is_set_item && item.attributes?.[setAttribute] !== item.major_attr_value
	const differsFromMajorColour = !item.is_set_item && value !== majorColour
	return majorColour && (differsFromMajorPart || differsFromMajorColour) ? `${value} (${majorColour})` : value
}

function rowTotal(item, primaryValues) {
	return primaryValues.reduce((total, value) => total + numeric(item.values?.[value]), 0)
}

function columnTotal(items, value) {
	return items.reduce((total, item) => total + numeric(item.values?.[value]), 0)
}

function sectionTotal(section) {
	return section.items.reduce((total, item) => total + rowTotal(item, section.primaryValues), 0)
}
</script>

<style scoped>
.completed-report {
	display: grid;
	gap: 12px;
	min-width: 0;
	padding: 2px;
	color: var(--erp-text);
	background: #fff;
}

.completed-report__meta {
	display: grid;
	grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr) auto;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-surface-soft);
	overflow: hidden;
}

.completed-report__meta-item {
	display: grid;
	gap: 3px;
	min-width: 0;
	padding: 10px 12px;
	border-right: 1px solid var(--erp-border);
}

.completed-report__meta-item:last-child { border-right: 0; }

.completed-report__meta-item span,
.completed-report__part span,
.completed-report__panels > span {
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: 750;
	letter-spacing: 0.035em;
	text-transform: uppercase;
}

.completed-report__meta-item strong {
	min-width: 0;
	overflow: hidden;
	font-size: var(--erp-font-size-body);
	font-weight: 720;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.completed-report__meta-item--time strong {
	font-variant-numeric: tabular-nums;
	white-space: nowrap;
}

.completed-report__sections { display: grid; gap: 12px; }

.completed-report__sr-only {
	position: absolute;
	width: 1px;
	height: 1px;
	padding: 0;
	margin: -1px;
	overflow: hidden;
	clip: rect(0, 0, 0, 0);
	white-space: nowrap;
	border: 0;
}

.completed-report__group {
	min-width: 0;
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	background: #fff;
	overflow: hidden;
}

.completed-report__group-header {
	display: flex;
	align-items: flex-start;
	gap: 16px;
	padding: 9px 11px;
	background: var(--erp-accent-soft);
	border-bottom: 1px solid var(--erp-border);
}

.completed-report__part {
	display: grid;
	gap: 2px;
	min-width: 100px;
}

.completed-report__part strong { color: var(--erp-accent-hover); font-size: var(--erp-font-size-body); }

.completed-report__panels {
	display: grid;
	gap: 5px;
	min-width: 0;
}

.completed-report__panel-list { display: flex; gap: 5px; flex-wrap: wrap; }

.completed-report__panel {
	padding: 2px 7px;
	color: #3e5549;
	background: #fff;
	border: 1px solid color-mix(in srgb, var(--erp-accent) 18%, var(--erp-border));
	border-radius: 999px;
	font-size: var(--erp-font-size-min);
	font-weight: 650;
}

.completed-report__table-wrap { max-width: 100%; overflow-x: auto; }

.completed-report__table {
	width: 100%;
	min-width: 680px;
	border-collapse: collapse;
	font-size: var(--erp-font-size-caption);
}

.completed-report__table th,
.completed-report__table td {
	padding: 8px 10px;
	border-right: 1px solid var(--erp-border);
	border-bottom: 1px solid var(--erp-border);
	text-align: left;
	white-space: nowrap;
}

.completed-report__table th:last-child,
.completed-report__table td:last-child { border-right: 0; }

.completed-report__table thead th {
	color: #4d5d54;
	background: #f6f9f7;
	font-size: var(--erp-font-size-min);
	font-weight: 750;
}

.completed-report__table .number-cell {
	text-align: right;
	font-variant-numeric: tabular-nums;
}

.completed-report__row-total { color: var(--erp-accent-hover); font-weight: 760; }

.completed-report__total-row th,
.completed-report__total-row td {
	color: #30483b;
	background: #edf6f1;
	border-bottom: 0;
	font-weight: 780;
}

.completed-report__empty {
	display: grid;
	place-items: center;
	gap: 5px;
	min-height: 150px;
	padding: 24px;
	color: var(--erp-text-muted);
	text-align: center;
}

.completed-report__empty i { color: var(--erp-accent); font-size: 1.4rem; }
.completed-report__empty strong { color: var(--erp-text); }
.completed-report__empty span { font-size: var(--erp-font-size-caption); }

@media (max-width: 760px) {
	.completed-report__meta { grid-template-columns: 1fr; }
	.completed-report__meta-item { border-right: 0; border-bottom: 1px solid var(--erp-border); }
	.completed-report__meta-item:last-child { border-bottom: 0; }
	.completed-report__group-header { display: grid; }
}
</style>
