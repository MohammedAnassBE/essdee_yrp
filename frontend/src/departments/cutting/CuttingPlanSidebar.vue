<template>
	<aside class="operations-rail" :class="{ 'operations-rail--single': visibleSectionCount === 1 }">
		<Message v-if="error" class="rail-error" severity="error" :closable="false">{{ error }}</Message>

		<section v-if="permissions.can_read_marker" class="rail-section marker-section">
			<header class="rail-heading">
				<h3>Markers <span>{{ filteredCount(markers.length, filteredMarkers.length, markerFilters.length) }}</span></h3>
				<div class="rail-heading__actions">
					<Button
						class="rail-filter-button"
						:class="{ 'rail-filter-button--active': markerFilters.length }"
						icon="pi pi-filter"
						severity="secondary"
						outlined
						size="small"
						aria-label="Filter markers"
						:title="markerFilters.length ? `${markerFilters.length} marker filter${markerFilters.length === 1 ? '' : 's'} applied` : 'Filter markers'"
						@click="markerFiltersOpen = true"
					/>
					<Button
						v-if="permissions.can_create_marker"
						icon="pi pi-plus"
						label="Create New"
						size="small"
						:disabled="!permissions.can_start_marker"
						:title="permissions.can_start_marker ? 'Create a new marker' : 'This Cutting Plan is not ready for a new marker'"
						@click="openMarker('')"
					/>
				</div>
			</header>
			<div v-if="loading" class="rail-loading"><Skeleton v-for="index in 3" :key="index" height="5.2rem" /></div>
			<div v-else-if="filteredMarkers.length" class="rail-list">
				<button v-for="marker in filteredMarkers" :key="marker.name" type="button" class="rail-card marker-card" @click="openMarker(marker.name)">
					<div class="rail-card__top"><div><strong>{{ marker.marker_name || marker.name }}</strong><div class="marker-subline"><small>{{ marker.name }}</small><span class="marker-status" :class="`marker-status--${markerStatus(marker).toLowerCase()}`">{{ markerStatus(marker) }}</span></div></div><i class="pi pi-chevron-right"></i></div>
					<div class="marker-metrics">
						<span><small>Marker size</small><b>{{ decimal(marker.length, 3) }} m <i class="pi pi-times"></i> {{ decimal(marker.width, 3) }} in</b></span>
						<span><small>Piece weight</small><b>{{ decimal(marker.required_piece_weight, 4) }} kg</b></span>
					</div>
					<div class="panel-summary"><small>Panels</small><div class="panel-chips"><span v-for="panel in markerPanels(marker)" :key="panel" :title="panel">{{ panel }}</span><em v-if="!markerPanels(marker).length">No panels selected</em></div></div>
				</button>
			</div>
			<div v-else class="rail-empty">
				<i class="pi" :class="markerFilters.length && markers.length ? 'pi-filter-slash' : 'pi-vector'"></i>
				<span>{{ markerFilters.length && markers.length ? 'No markers match the applied filters.' : 'No markers for this Cutting Plan.' }}</span>
				<Button v-if="markerFilters.length && markers.length" label="Clear filters" severity="secondary" text size="small" @click="markerFilters = []" />
			</div>
		</section>

		<section v-if="permissions.can_read_laysheet" class="rail-section laysheet-section">
			<header class="rail-heading">
				<h3>Lay Sheets <span>{{ filteredCount(laysheets.length, filteredLaySheets.length, laySheetFilters.length) }}</span></h3>
				<div class="rail-heading__actions">
					<Button
						class="rail-filter-button"
						:class="{ 'rail-filter-button--active': laySheetFilters.length }"
						icon="pi pi-filter"
						severity="secondary"
						outlined
						size="small"
						aria-label="Filter Lay Sheets"
						:title="laySheetFilters.length ? `${laySheetFilters.length} Lay Sheet filter${laySheetFilters.length === 1 ? '' : 's'} applied` : 'Filter Lay Sheets'"
						@click="laySheetFiltersOpen = true"
					/>
					<Button
						v-if="permissions.can_create_laysheet"
						icon="pi pi-plus"
						label="Create New"
						size="small"
						:disabled="!permissions.can_start_laysheet"
						:title="permissions.can_start_laysheet ? 'Create a new Lay Sheet' : 'This Cutting Plan is not ready for a new Lay Sheet'"
						@click="openLaySheet('')"
					/>
				</div>
			</header>
			<div v-if="loading" class="rail-loading"><Skeleton v-for="index in 3" :key="index" height="4.5rem" /></div>
			<div v-else-if="filteredLaySheets.length" class="rail-list">
				<button v-for="sheet in filteredLaySheets" :key="sheet.name" type="button" class="rail-card laysheet-card" @click="openLaySheet(sheet.name)">
					<div class="rail-card__top"><div class="lay-title"><span class="lay-number">{{ sheet.lay_no }}</span><div><strong>{{ sheet.marker_name || sheet.cutting_marker || 'Marker' }}</strong><div class="lay-subline"><small>{{ sheet.name }}</small><span class="lay-status" :class="statusClass(sheet.status)">{{ sheet.status || '—' }}</span></div></div></div><div class="card-tail"><i class="pi pi-chevron-right"></i></div></div>
					<div class="lay-meta"><span><i class="pi pi-box"></i><span><small>Bundle date</small><b>{{ formatDate(sheet.bundle_generated_date, false, 'Not generated') }}</b></span></span><span class="print-state"><i class="pi pi-print"></i><span><small>Printed</small><b>{{ formatDate(sheet.printed_time, true, 'Not printed') }}</b></span></span></div>
					<div class="panel-summary"><small>Marker panels</small><div class="panel-chips"><span v-for="panel in laySheetPanels(sheet)" :key="`${sheet.name}-${panel}`" :title="panel">{{ panel }}</span><em v-if="!laySheetPanels(sheet).length">No panels selected</em></div></div>
				</button>
			</div>
			<div v-else class="rail-empty">
				<i class="pi" :class="laySheetFilters.length && laysheets.length ? 'pi-filter-slash' : 'pi-list'"></i>
				<span>{{ laySheetFilters.length && laysheets.length ? 'No Lay Sheets match the applied filters.' : 'No Lay Sheets for this Cutting Plan.' }}</span>
				<Button v-if="laySheetFilters.length && laysheets.length" label="Clear filters" severity="secondary" text size="small" @click="laySheetFilters = []" />
			</div>
		</section>

		<ListviewFilters v-model:visible="markerFiltersOpen" v-model="markerFilters" :fields="markerFilterFields" @apply="markerFilters = $event" />
		<ListviewFilters v-model:visible="laySheetFiltersOpen" v-model="laySheetFilters" :fields="laySheetFilterFields" @apply="laySheetFilters = $event" />

		<CuttingMarkerDialog v-if="permissions.can_read_marker" v-model:visible="markerOpen" :cutting-plan="cuttingPlan" :marker-name="selectedMarker" @changed="changed" />
		<CuttingLaySheetDialog v-if="permissions.can_read_laysheet" v-model:visible="laysheetOpen" :cutting-plan="cuttingPlan" :laysheet-name="selectedLaySheet" :can-create="Boolean(permissions.can_create_laysheet)" @changed="changed" />
	</aside>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, ref } from "vue"

import ListviewFilters from "../../components/common/ListviewFilters.vue"
import CuttingLaySheetDialog from "./CuttingLaySheetDialog.vue"
import CuttingMarkerDialog from "./CuttingMarkerDialog.vue"

const props = defineProps({
	cuttingPlan: { type: String, required: true },
	data: { type: Object, default: () => ({}) },
	loading: Boolean,
	error: { type: String, default: "" },
})
const emit = defineEmits(["refresh"])

const markerOpen = ref(false)
const selectedMarker = ref("")
const laysheetOpen = ref(false)
const selectedLaySheet = ref("")
const markerFiltersOpen = ref(false)
const laySheetFiltersOpen = ref(false)
const markerFilters = ref([])
const laySheetFilters = ref([])
const markers = computed(() => props.data.markers || [])
const laysheets = computed(() => props.data.laysheets || [])
const permissions = computed(() => props.data.permissions || {})
const visibleSectionCount = computed(() => Number(Boolean(permissions.value.can_read_marker)) + Number(Boolean(permissions.value.can_read_laysheet)))
const markersByName = computed(() => new Map(markers.value.map((marker) => [marker.name, marker])))
const markerFilterFields = computed(() => [
	{ fieldname: "marker_name", label: "Marker Name", fieldtype: "Data" },
	{
		fieldname: "name",
		label: "Marker ID",
		fieldtype: "Link",
		options: "SD YRP Cutting Marker",
		link_filters: { cutting_plan: props.cuttingPlan },
	},
	{ fieldname: "length", label: "Length", fieldtype: "Float", precision: 3 },
	{ fieldname: "width", label: "Width", fieldtype: "Float", precision: 3 },
	{ fieldname: "required_piece_weight", label: "Required Piece Weight", fieldtype: "Float", precision: 4 },
	{ fieldname: "panels", label: "Panel", fieldtype: "Data" },
])
const laySheetFilterFields = computed(() => [
	{ fieldname: "lay_no", label: "Lay No", fieldtype: "Int" },
	{ fieldname: "marker_name", label: "Marker Name", fieldtype: "Data" },
	{
		fieldname: "cutting_marker",
		label: "Marker ID",
		fieldtype: "Link",
		options: "SD YRP Cutting Marker",
		link_filters: { cutting_plan: props.cuttingPlan },
	},
	{
		fieldname: "status",
		label: "Status",
		fieldtype: "Select",
		options: "Started\nCompleted\nBundles Generated\nApproval Pending\nLabel Printed\nCancelled",
	},
	{ fieldname: "bundle_generated_date", label: "Bundle Generated Date", fieldtype: "Date" },
	{ fieldname: "printed_time", label: "Printed Time", fieldtype: "Datetime" },
	{ fieldname: "panels", label: "Marker Panel", fieldtype: "Data" },
])
const filteredMarkers = computed(() => markers.value.filter((marker) => matchesFilters(marker, markerFilters.value, markerValue)))
const filteredLaySheets = computed(() => laysheets.value.filter((sheet) => matchesFilters(sheet, laySheetFilters.value, laySheetValue)))

function openMarker(name) {
	selectedMarker.value = name
	markerOpen.value = true
}

function openLaySheet(name) {
	selectedLaySheet.value = name
	laysheetOpen.value = true
}

function changed() {
	emit("refresh")
}

function markerPanels(marker) {
	return String(marker.calculated_parts || "").split(",").map((panel) => panel.trim()).filter(Boolean)
}

function laySheetPanels(sheet) {
	return markerPanels(markersByName.value.get(sheet.cutting_marker) || sheet)
}

function markerValue(marker, fieldname) {
	if (fieldname === "panels") return markerPanels(marker).join(", ")
	return marker[fieldname]
}

function laySheetValue(sheet, fieldname) {
	if (fieldname === "panels") return laySheetPanels(sheet).join(", ")
	return sheet[fieldname]
}

function matchesFilters(record, filters, valueFor) {
	return filters.every(([fieldname, operator, expected]) => matchesFilter(valueFor(record, fieldname), operator, expected))
}

function matchesFilter(actual, operator, expected) {
	const actualText = String(actual ?? "").trim()
	const expectedValues = Array.isArray(expected)
		? expected
		: String(expected ?? "").split(",").map((value) => value.trim()).filter(Boolean)
	const comparableActual = actualText.toLocaleLowerCase()
	const comparableExpected = String(expected ?? "").trim().toLocaleLowerCase()

	if (operator === "is") return expected === "set" ? actualText !== "" : actualText === ""
	if (operator === "like") return comparableActual.includes(comparableExpected.replaceAll("%", ""))
	if (operator === "not like") return !comparableActual.includes(comparableExpected.replaceAll("%", ""))
	if (operator === "in" || operator === "not in") {
		const found = expectedValues.some((value) => comparableActual === String(value).trim().toLocaleLowerCase())
		return operator === "in" ? found : !found
	}
	if (operator === "=" || operator === "!=") {
		const expectedText = String(expected ?? "").trim()
		const bothAreDates = /^\d{4}-\d{2}-\d{2}/.test(actualText) && /^\d{4}-\d{2}-\d{2}/.test(expectedText)
		const equal = comparableActual === comparableExpected || (bothAreDates && actualText.slice(0, 10) === expectedText.slice(0, 10))
		return operator === "=" ? equal : !equal
	}
	if (operator === "Between") {
		if (!Array.isArray(expected) || expected.length < 2) return true
		const first = comparableValue(expected[0])
		const second = comparableValue(expected[1])
		const value = comparableValue(actual)
		return value >= first && value <= second
	}
	if (operator === "Timespan") return matchesTimespan(actual, expected)

	const left = comparableValue(actual)
	const right = comparableValue(expected)
	if (operator === ">") return left > right
	if (operator === "<") return left < right
	if (operator === ">=") return left >= right
	if (operator === "<=") return left <= right
	return true
}

function comparableValue(value) {
	const text = String(value ?? "").trim()
	const number = Number(value)
	if (text !== "" && Number.isFinite(number)) return number
	const timestamp = /^\d{4}-\d{2}-\d{2}/.test(text) ? new Date(text.replace(" ", "T")).getTime() : NaN
	return Number.isFinite(timestamp) ? timestamp : text.toLocaleLowerCase()
}

function matchesTimespan(actual, expected) {
	const value = new Date(String(actual || "").replace(" ", "T"))
	if (Number.isNaN(value.getTime())) return false
	const range = timespanRange(String(expected || "").toLocaleLowerCase())
	return range ? value >= range[0] && value <= range[1] : false
}

function timespanRange(period) {
	const now = new Date()
	const start = new Date(now.getFullYear(), now.getMonth(), now.getDate())
	const end = new Date(start)
	end.setHours(23, 59, 59, 999)
	const amount = Number(period.match(/\d+/)?.[0] || 0)
	if (period.startsWith("last ") && amount) {
		start.setDate(start.getDate() - amount)
		return [start, end]
	}
	if (period.startsWith("next ") && amount) {
		end.setDate(end.getDate() + amount)
		return [start, end]
	}
	if (period === "yesterday" || period === "tomorrow") {
		const offset = period === "yesterday" ? -1 : 1
		start.setDate(start.getDate() + offset)
		end.setDate(end.getDate() + offset)
		return [start, end]
	}
	if (period === "today") return [start, end]

	const direction = period.startsWith("last ") ? -1 : period.startsWith("next ") ? 1 : 0
	if (period.endsWith("week")) {
		const mondayOffset = (start.getDay() + 6) % 7
		start.setDate(start.getDate() - mondayOffset + direction * 7)
		end.setTime(start.getTime())
		end.setDate(end.getDate() + 6)
		end.setHours(23, 59, 59, 999)
		return [start, end]
	}
	if (period.endsWith("month")) {
		start.setMonth(start.getMonth() + direction, 1)
		end.setFullYear(start.getFullYear(), start.getMonth() + 1, 0)
		end.setHours(23, 59, 59, 999)
		return [start, end]
	}
	if (period.endsWith("quarter")) {
		const quarterMonth = Math.floor(start.getMonth() / 3) * 3 + direction * 3
		start.setMonth(quarterMonth, 1)
		end.setFullYear(start.getFullYear(), start.getMonth() + 3, 0)
		end.setHours(23, 59, 59, 999)
		return [start, end]
	}
	if (period.endsWith("6 months")) {
		if (direction < 0) start.setMonth(start.getMonth() - 6)
		else if (direction > 0) end.setMonth(end.getMonth() + 6)
		return [start, end]
	}
	if (period.endsWith("year")) {
		start.setFullYear(start.getFullYear() + direction, 0, 1)
		end.setFullYear(start.getFullYear(), 11, 31)
		end.setHours(23, 59, 59, 999)
		return [start, end]
	}
	return null
}

function filteredCount(total, shown, activeFilters) {
	return activeFilters ? `${shown}/${total}` : total
}

function decimal(value, precision) {
	return Number(value || 0).toFixed(precision)
}

function formatDate(value, includeTime = false, fallback = "—") {
	if (!value) return fallback
	const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/)
	if (!match) return String(value)
	const date = `${match[3]}-${match[2]}-${match[1]}`
	return includeTime && match[4] ? `${date} ${match[4]}:${match[5]}` : date
}

function statusClass(status) {
	return `lay-status--${String(status || "").toLowerCase().replaceAll(" ", "-")}`
}

function markerStatus(marker) {
	return ["Draft", "Submitted", "Cancelled"][Number(marker?.docstatus || 0)] || "Draft"
}
</script>

<style scoped>
.operations-rail { position: sticky; top: 10px; display: grid; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: 10px; min-width: 0; height: 100%; min-height: 0; }
.operations-rail--single { grid-template-rows: minmax(0, 1fr); }
.rail-error { position: absolute; z-index: 3; top: 4px; right: 4px; left: 4px; }
.rail-section { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; overflow: hidden; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); box-shadow: var(--erp-shadow-card); }
.rail-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 52px; padding: 8px 10px 8px 14px; background: var(--erp-surface-soft); border-bottom: 1px solid var(--erp-border); }
.rail-heading h3 { display: flex; align-items: center; gap: 8px; margin: 0; color: var(--erp-text); font-size: 15px; font-weight: 760; letter-spacing: -0.01em; }
.rail-heading h3 span { display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 6px; color: #2d664c; background: var(--erp-accent-soft); border: 1px solid #d3e8dd; border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.rail-heading__actions { display: flex; align-items: center; gap: 6px; }
.rail-heading :deep(.p-button) { flex: 0 0 auto; min-height: var(--erp-control-height-compact); padding: 0.4rem 0.62rem; color: #fff; background: var(--erp-accent); border-color: var(--erp-accent); border-radius: var(--erp-control-radius); box-shadow: none; font-size: var(--erp-font-size-min); font-weight: 700; }
.rail-heading :deep(.p-button:hover) { background: var(--erp-accent-hover); border-color: var(--erp-accent-hover); }
.rail-heading :deep(.p-button:disabled) { opacity: 0.48; }
.rail-heading :deep(.rail-filter-button.p-button) { width: 34px; min-width: 34px; padding: 0; color: #397059; background: #fff; border-color: #cbded4; box-shadow: 0 2px 7px rgb(35 70 50 / 5%); }
.rail-heading :deep(.rail-filter-button.p-button:hover) { color: #086b4b; background: #eff9f4; border-color: #8fc5aa; }
.rail-heading :deep(.rail-filter-button--active.p-button) { color: #fff; background: #147d5b; border-color: #147d5b; box-shadow: 0 3px 9px rgb(20 125 91 / 18%); }
.rail-loading, .rail-list { display: grid; align-content: start; gap: 8px; min-height: 0; padding: 9px; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: #a5baaf transparent; }
.rail-card { display: grid; gap: 8px; width: 100%; padding: 10px 11px; color: inherit; text-align: left; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); cursor: pointer; box-shadow: none; transition: border-color var(--erp-transition-fast), background var(--erp-transition-fast); }
.marker-card { border-left: 3px solid #50bb8f; }
.laysheet-card { border-left: 3px solid #2b8b66; }
.rail-card:hover { background: var(--erp-surface-soft); border-color: #85bba1; box-shadow: none; }
.rail-card:focus-visible { border-color: #49a87f; outline: 3px solid rgb(73 168 127 / 15%); }
.rail-card__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rail-card__top > div { display: grid; gap: 2px; min-width: 0; }
.rail-card__top strong { overflow: hidden; color: #1d3146; font-size: 0.88rem; font-weight: 760; text-overflow: ellipsis; white-space: nowrap; }
.rail-card__top small { overflow: hidden; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 560; text-overflow: ellipsis; white-space: nowrap; }
.rail-card__top > i, .card-tail > i { display: inline-grid; place-items: center; flex: 0 0 auto; width: 24px; height: 24px; color: #4d7964; background: var(--erp-accent-soft); border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); }
.marker-subline { display: flex !important; align-items: center; gap: 6px !important; min-width: 0; }
.marker-subline small { flex: 1; min-width: 0; }
.marker-status { flex: 0 0 auto; padding: 2px 6px; color: #725612; background: #fff4cf; border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 740; }
.marker-status--submitted { color: #176344; background: #e2f4ea; }
.marker-status--cancelled { color: #963d3d; background: #fce8e8; }
.marker-metrics { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 5px; }
.marker-metrics > span { display: grid; gap: 2px; min-width: 0; padding: 6px 7px; background: #f4f8f5; border: 1px solid #e5ede8; border-radius: 7px; }
.marker-metrics small, .panel-summary > small, .lay-meta small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: 0.025em; text-transform: uppercase; }
.marker-metrics b { overflow: hidden; color: #2d4438; font-size: var(--erp-font-size-caption); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.marker-metrics i { margin: 0 1px; font-size: 0.48rem; }
.panel-summary { display: grid; gap: 4px; }
.panel-chips { display: flex; flex-wrap: wrap; gap: 4px; max-height: 42px; overflow: hidden; }
.panel-chips span { max-width: 108px; overflow: hidden; padding: 3px 7px; color: #245d43; background: #e6f4ed; border: 1px solid #d6ebdf; border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
.panel-chips em { color: #89958e; font-size: var(--erp-font-size-min); font-style: normal; }
.lay-title { display: flex !important; align-items: center; grid-template-columns: auto 1fr; gap: 8px !important; }
.lay-number { display: inline-grid; place-items: center; flex: 0 0 auto; width: 33px; height: 33px; color: #fff; background: var(--erp-accent); border-radius: var(--erp-control-radius); box-shadow: none; font-size: 13px; font-weight: 800; }
.lay-title > div { display: grid; gap: 2px; min-width: 0; }
.lay-subline { display: flex !important; align-items: center; gap: 6px !important; min-width: 0; }
.lay-subline small { flex: 1; min-width: 0; }
.card-tail { display: flex !important; align-items: center; gap: 5px !important; flex: 0 0 auto; }
.lay-meta { display: grid; gap: 5px; }
.lay-meta > span { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 6px 7px; background: #f4f8f5; border: 1px solid #e4ece7; border-radius: 7px; }
.lay-meta > span > span { display: flex; align-items: center; justify-content: space-between; gap: 8px; width: 100%; min-width: 0; }
.lay-meta i { flex: 0 0 auto; color: #5f7f6c; font-size: 0.72rem; }
.lay-meta b { overflow: hidden; color: #30483c; font-size: var(--erp-font-size-min); font-weight: 720; text-overflow: ellipsis; white-space: nowrap; }
.lay-status { padding: 3px 7px; color: #356046; background: #e7f2eb; border-radius: var(--erp-pill-radius); font-size: var(--erp-font-size-min); font-weight: 750; white-space: nowrap; }
.lay-status--started { color: #315f7a; background: #e5f2fa; }
.lay-status--completed, .lay-status--label-printed { color: #2c6642; background: #e2f2e8; }
.lay-status--bundles-generated { color: #63518a; background: #eee9f8; }
.lay-status--cancelled { color: #963d3d; background: #fce8e8; }
.lay-status--approval-pending { color: #875b12; background: #fff1ca; }
.rail-empty { display: grid; place-items: center; align-content: center; gap: 8px; min-height: 0; padding: 18px; color: #76857c; text-align: center; font-size: 0.77rem; }
.rail-empty i { display: inline-grid; place-items: center; width: 34px; height: 34px; color: #567262; background: #edf4f0; border-radius: 50%; font-size: 1rem; }
.rail-empty :deep(.p-button) { color: #0d7655; font-size: 0.72rem; }

@media (max-width: 1050px) {
	.operations-rail { position: static; grid-template-rows: none; grid-template-columns: repeat(2, minmax(0, 1fr)); height: auto; }
	.rail-section { max-height: 430px; }
}

@media (max-width: 650px) {
	.operations-rail { grid-template-columns: 1fr; }
}
</style>
