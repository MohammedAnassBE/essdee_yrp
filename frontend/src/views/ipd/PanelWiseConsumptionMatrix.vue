<template>
	<div v-if="localMatrix" class="pwc-card" data-testid="panel-wise-consumption-matrix">
		<div class="pwc-head">
			<h4>Panel-wise consumption matrix</h4>
			<span class="pwc-progress">{{ completeCount }} / {{ totalCount }} complete</span>
		</div>

		<div class="pwc-tabs" role="tablist" aria-label="Panels">
			<button
				v-for="panel in localMatrix.panels || []"
				:key="panel.panel_value"
				type="button"
				class="pwc-tab"
				:class="{ active: panel.panel_value === activePanel }"
				@click="activePanel = panel.panel_value"
			>
				{{ panel.panel_value }}
			</button>
		</div>

		<div v-if="currentPanel" class="pwc-toolbar">
			<div>
				<strong>{{ currentPanel.panel_value }}</strong>
				<span>{{ currentPanel.rows.length }} {{ localMatrix.attributes.primary }} rows</span>
			</div>
			<Button
				v-if="editing && currentPackingValues.length > 1"
				:label="`Copy ${currentPackingValues[0]} across this panel`"
				size="small"
				severity="secondary"
				outlined
				@click="copyFirstPackingToPanel"
			/>
		</div>

		<div v-if="currentPanel" class="pwc-scroll">
			<table class="pwc-table">
				<thead>
					<tr>
						<th class="pwc-primary">{{ localMatrix.attributes.primary }}</th>
						<th v-for="packing in currentPackingValues" :key="packing">
							{{ packing }}
							<small>Dia · kg / piece</small>
						</th>
						<th v-if="editing" class="pwc-action">Action</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in currentPanel.rows" :key="row.primary_value">
						<td class="pwc-primary-value">{{ row.primary_value }}</td>
						<td v-for="packing in currentPackingValues" :key="packing">
							<div v-if="editing" class="pwc-cell">
								<LinkField
									:model-value="cellFor(row, packing).dia || ''"
									target-doctype="YRP Item Attribute Value"
									:filters="DIA_FILTERS"
									:dropdown="false"
									placeholder="Select Dia"
									class="pwc-dia-link"
									@item-select="(event) => setDia(row, packing, event.value)"
								/>
								<input
									class="pwc-input pwc-weight"
									type="text"
									inputmode="decimal"
									:value="formatKg(cellFor(row, packing).weight)"
									placeholder="0.030"
									@change="setWeight(row, packing, $event)"
								/>
							</div>
							<span v-else>
								{{ cellFor(row, packing).dia || "—" }} ·
								{{ formatKg(cellFor(row, packing).weight) || "—" }}
							</span>
						</td>
						<td v-if="editing" class="pwc-action">
							<Button
								label="Fill →"
								size="small"
								severity="secondary"
								text
								v-tooltip.top="`Copy ${currentPackingValues[0]} across this row`"
								@click="copyFirstPackingToRow(row)"
							/>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import Button from "primevue/button"
import Tooltip from "primevue/tooltip"
import LinkField from "@/components/LinkField.vue"
import { useAppToast } from "@/composables/useToast"

const vTooltip = Tooltip
const toast = useAppToast()
const DIA_FILTERS = Object.freeze({ attribute_name: "Dia" })
const props = defineProps({
	matrix: { type: Object, default: null },
	diaValues: { type: Array, default: () => [] },
	editing: { type: Boolean, default: false },
})
const emit = defineEmits(["update:matrix"])

const clone = (value) => (value ? JSON.parse(JSON.stringify(value)) : null)
const localMatrix = ref(clone(props.matrix))
const activePanel = ref("")

watch(
	() => props.matrix,
	(value) => {
		localMatrix.value = clone(value)
		const panels = localMatrix.value?.panels || []
		if (!panels.some((panel) => panel.panel_value === activePanel.value)) {
			activePanel.value = panels[0]?.panel_value || ""
		}
	},
	{ immediate: true },
)

const currentPanel = computed(() =>
	(localMatrix.value?.panels || []).find((panel) => panel.panel_value === activePanel.value),
)
const packingValuesFor = (panel) =>
	panel?.packing_values || localMatrix.value?.packing_values || []
const currentPackingValues = computed(() => packingValuesFor(currentPanel.value))
const totalCount = computed(() =>
	(localMatrix.value?.panels || []).reduce(
		(total, panel) =>
			total + (panel.rows || []).length * packingValuesFor(panel).length,
		0,
	),
)
const completeCount = computed(() =>
	(localMatrix.value?.panels || []).reduce(
		(total, panel) =>
			total +
			(panel.rows || []).reduce(
				(rowTotal, row) =>
					rowTotal +
					packingValuesFor(panel).filter(
						(packing) => {
							const cell = cellFor(row, packing)
							return cell.dia && Number(cell.weight) > 0
						},
					).length,
				0,
			),
		0,
	),
)

function commit() {
	emit("update:matrix", clone(localMatrix.value))
}
function cellFor(row, packing) {
	row.values ||= {}
	row.values[packing] ||= { dia: null, weight: null }
	return row.values[packing]
}
function setDia(row, packing, value) {
	cellFor(row, packing).dia = value || null
	commit()
}
function parseWeight(value) {
	const normalized = String(value ?? "").trim()
	if (!normalized) return null
	if (!/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(normalized)) return NaN
	const parsed = Number(normalized)
	return Number.isFinite(parsed) && parsed > 0 ? Number(parsed.toFixed(6)) : NaN
}
function formatKg(value) {
	if (value === null || value === undefined || value === "") return ""
	const parsed = Number(value)
	if (!Number.isFinite(parsed)) return ""
	const trimmed = parsed.toFixed(6).replace(/0+$/, "")
	const [whole, decimal = ""] = trimmed.split(".")
	return `${whole}.${decimal.padEnd(3, "0")}`
}
function setWeight(row, packing, event) {
	const value = parseWeight(event.target.value)
	if (Number.isNaN(value)) {
		toast.error("Invalid consumption", "Enter a positive kg value, for example 0.030.")
		event.target.value = formatKg(cellFor(row, packing).weight)
		return
	}
	cellFor(row, packing).weight = value
	event.target.value = formatKg(value)
	commit()
}
function copyFirstPackingToRow(row) {
	const first = currentPackingValues.value[0]
	const source = cellFor(row, first)
	if (!source.dia || !(Number(source.weight) > 0)) {
		toast.warn("Missing values", `Enter ${first} Dia and consumption first.`)
		return
	}
	for (const packing of currentPackingValues.value) {
		row.values[packing] = { dia: source.dia, weight: source.weight }
	}
	commit()
}
function copyFirstPackingToPanel() {
	const first = currentPackingValues.value[0]
	const missing = currentPanel.value.rows.find((row) => {
		const cell = cellFor(row, first)
		return !cell.dia || !(Number(cell.weight) > 0)
	})
	if (missing) {
		toast.warn(
			"Missing values",
			`Enter ${first} Dia and consumption for ${missing.primary_value} first.`,
		)
		return
	}
	for (const row of currentPanel.value.rows) {
		const source = cellFor(row, first)
		for (const packing of currentPackingValues.value) {
			row.values[packing] = { dia: source.dia, weight: source.weight }
		}
	}
	commit()
}
</script>

<style scoped>
.pwc-card {
	margin-top: 14px;
	overflow: hidden;
	border: 1px solid var(--esd-line);
	border-radius: calc(var(--esd-radius) + 2px);
	background: var(--esd-surface);
	box-shadow: 0 8px 24px var(--esd-shadow);
}
.pwc-head,
.pwc-toolbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 14px 16px;
}
.pwc-head {
	border-bottom: 1px solid var(--esd-line);
	background: color-mix(in srgb, var(--esd-accent) 7%, var(--esd-surface));
}
.pwc-head h4 {
	margin: 0;
	font-size: 0.95rem;
}
.pwc-progress {
	flex: 0 0 auto;
	padding: 5px 9px;
	border: 1px solid color-mix(in srgb, var(--esd-accent) 24%, var(--esd-line));
	border-radius: 999px;
	background: color-mix(in srgb, var(--esd-accent) 10%, var(--esd-surface));
	color: var(--esd-accent);
	font-size: 0.72rem;
	font-weight: 700;
}
.pwc-tabs {
	display: flex;
	gap: 6px;
	overflow-x: auto;
	padding: 10px 14px;
	border-bottom: 1px solid var(--esd-line);
	background: var(--esd-surface2);
}
.pwc-tab {
	padding: 7px 11px;
	border: 1px solid transparent;
	border-radius: calc(var(--esd-radius) - 2px);
	background: transparent;
	color: var(--esd-muted);
	font: inherit;
	font-size: 0.78rem;
	font-weight: 650;
	white-space: nowrap;
	cursor: pointer;
}
.pwc-tab.active {
	border-color: color-mix(in srgb, var(--esd-accent) 28%, var(--esd-line));
	background: var(--esd-surface);
	color: var(--esd-accent);
	box-shadow: 0 2px 7px var(--esd-shadow);
}
.pwc-toolbar strong,
.pwc-toolbar span {
	display: block;
}
.pwc-toolbar strong {
	font-size: 0.86rem;
}
.pwc-toolbar span {
	margin-top: 2px;
	color: var(--esd-muted);
	font-size: 0.7rem;
}
.pwc-scroll {
	overflow-x: auto;
	padding: 0 14px 14px;
}
.pwc-cell {
	display: grid;
	grid-template-columns: minmax(120px, 1fr) minmax(90px, 0.65fr);
	gap: 7px;
	align-items: center;
}
.pwc-table {
	min-width: 760px;
	width: 100%;
	border: 1px solid var(--esd-line);
	border-collapse: separate;
	border-spacing: 0;
	border-radius: var(--esd-radius);
	overflow: hidden;
}
.pwc-table th,
.pwc-table td {
	padding: 9px;
	border-right: 1px solid var(--esd-line);
	border-bottom: 1px solid var(--esd-line);
	text-align: left;
	vertical-align: middle;
}
.pwc-table th {
	background: var(--esd-surface2);
	color: var(--esd-muted);
	font-size: 0.72rem;
	font-weight: 700;
}
.pwc-table th small {
	display: block;
	margin-top: 2px;
	font-size: 0.62rem;
	font-weight: 500;
}
.pwc-table tr:last-child td {
	border-bottom: 0;
}
.pwc-table th:last-child,
.pwc-table td:last-child {
	border-right: 0;
}
.pwc-primary {
	width: 116px;
}
.pwc-primary-value {
	color: var(--esd-text);
	font-weight: 650;
}
.pwc-dia {
	width: 126px;
}
.pwc-dia-link {
	width: 100%;
	min-width: 108px;
}
.pwc-dia-link :deep(.link-field),
.pwc-dia-link :deep(.p-autocomplete),
.pwc-dia-link :deep(input) {
	width: 100%;
}
.pwc-action {
	width: 82px;
	text-align: center !important;
}
.pwc-input {
	box-sizing: border-box;
	width: 100%;
	min-width: 100px;
	padding: 7px 9px;
	border: 1px solid var(--esd-line);
	border-radius: calc(var(--esd-radius) - 3px);
	background: var(--esd-surface2);
	color: var(--esd-text);
	font: inherit;
	font-size: 0.8rem;
	outline: none;
}
.pwc-input:focus {
	border-color: var(--esd-accent);
	box-shadow: 0 0 0 2px color-mix(in srgb, var(--esd-accent) 14%, transparent);
}
@media (max-width: 720px) {
	.pwc-head,
	.pwc-toolbar {
		align-items: flex-start;
		flex-direction: column;
	}
	.pwc-scroll {
		padding-inline: 8px;
	}
}
</style>
