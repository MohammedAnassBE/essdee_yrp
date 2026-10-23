<template>
	<div class="report-workspace" :class="{ 'report-workspace--single': !hasList }">
		<nav v-if="hasList" class="report-workspace__nav" :aria-label="label">
			<div class="report-workspace__search">
				<i class="pi pi-search" aria-hidden="true" />
				<InputText v-model="search" type="search" placeholder="Search reports" :aria-label="`Search ${label.toLowerCase()}`" autocomplete="off" fluid @keydown="onSearchKeydown" />
			</div>
			<div class="report-workspace__list">
				<template v-for="group in groups" :key="group.label">
					<p v-if="group.label" class="report-workspace__group">{{ group.label }}</p>
					<button
						v-for="report in group.reports"
						:key="report.value"
						:ref="element => setItemElement(report.value, element)"
						type="button"
						class="report-workspace__item"
						:class="{ 'is-selected': report.value === selected, 'is-highlighted': report.value === highlighted && report.value !== selected }"
						:aria-current="report.value === selected ? 'page' : undefined"
						:title="report.label"
						@click="selected = report.value"
					><i :class="report.icon || 'pi pi-table'" aria-hidden="true" /><span>{{ report.label }}</span></button>
				</template>
				<p v-if="!groups.length" class="report-workspace__empty">No report matches “{{ search }}”.</p>
			</div>
		</nav>
		<div v-if="hasList" class="report-workspace__mobile common-field">
			<label :for="mobileInputId">Report</label>
			<Select v-model="selected" :input-id="mobileInputId" :options="reports" option-label="label" option-value="value" filter filter-placeholder="Search reports" aria-label="Report" fluid />
		</div>
		<section v-if="current" class="report-workspace__content" :aria-label="current.label">
			<div v-if="$slots.default" :key="current.value"><slot :report="current" /></div>
			<KeepAlive v-else-if="keepAlive"><component :is="current.component" :key="current.value" v-bind="current.props" /></KeepAlive>
			<component :is="current.component" v-else :key="current.value" v-bind="current.props" />
		</section>
	</div>
</template>

<script setup>
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { chooseReport, readRememberedReport, rememberReport, reportGroups, stepReport } from "./reportWorkspace.js"

/** Master-detail report picker: searchable list on the left, selected report on the right, kept in the URL. */
const props = defineProps({
	reports: { type: Array, required: true },
	label: { type: String, default: "Reports" },
	queryKey: { type: String, default: "report" },
	storageKey: { type: String, default: "" },
	keepAlive: { type: Boolean, default: false },
})
const route = useRoute()
const router = useRouter()
const storageId = computed(() => props.storageKey || route.path || "reports")
const mobileInputId = `report-workspace-${Math.random().toString(36).slice(2, 8)}`
const remembered = ref(readRememberedReport(storageId.value))
const search = ref("")
const highlighted = ref("")
const itemElements = new Map()

const hasList = computed(() => props.reports.length > 1)
const groups = computed(() => reportGroups(props.reports, search.value))
const visibleValues = computed(() => groups.value.flatMap(group => group.reports.map(report => report.value)))
const selected = computed({
	get: () => chooseReport(props.reports, route.query?.[props.queryKey], remembered.value),
	set: value => {
		remembered.value = value
		highlighted.value = value
		rememberReport(storageId.value, value)
		router.replace({ query: { ...route.query, [props.queryKey]: value }, hash: route.hash })
	},
})
const current = computed(() => props.reports.find(report => report.value === selected.value))

watch(search, () => { highlighted.value = visibleValues.value[0] || "" })

function setItemElement(value, element) {
	if (element) itemElements.set(value, element)
	else itemElements.delete(value)
}

function onSearchKeydown(event) {
	const delta = { ArrowDown: 1, ArrowUp: -1 }[event.key]
	if (delta) {
		event.preventDefault()
		highlighted.value = stepReport(visibleValues.value, highlighted.value || selected.value, delta)
		itemElements.get(highlighted.value)?.scrollIntoView?.({ block: "nearest" })
	} else if (event.key === "Enter") {
		event.preventDefault()
		const value = visibleValues.value.includes(highlighted.value) ? highlighted.value : visibleValues.value[0]
		if (value) selected.value = value
	} else if (event.key === "Escape" && search.value) {
		event.preventDefault()
		search.value = ""
	}
}
</script>

<style scoped>
.report-workspace {
	--report-workspace-top: var(--erp-shell-header-height);
	display: grid;
	grid-template-columns: minmax(184px, 228px) minmax(0, 1fr);
	align-items: start;
	gap: var(--erp-space-4);
	min-width: 0;
}

.report-workspace--single {
	grid-template-columns: minmax(0, 1fr);
}

.report-workspace__nav {
	position: sticky;
	z-index: var(--erp-layer-sticky);
	top: calc(var(--report-workspace-top) + var(--erp-space-2));
	display: grid;
	grid-template-rows: auto minmax(0, 1fr);
	gap: var(--erp-space-2);
	max-height: calc(100vh - var(--report-workspace-top) - var(--erp-space-4));
	padding: var(--erp-space-2);
	border: 1px solid var(--erp-border-subtle);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-surface);
}

.report-workspace__search {
	position: relative;
}

.report-workspace__search > i {
	position: absolute;
	top: 50%;
	left: 10px;
	transform: translateY(-50%);
	color: var(--erp-text-subtle);
	font-size: var(--erp-font-size-caption);
	pointer-events: none;
}

.report-workspace__search :deep(.p-inputtext) {
	padding-left: 30px;
	font-size: var(--erp-font-size-caption);
}

.report-workspace__list {
	display: grid;
	align-content: start;
	gap: 1px;
	min-height: 0;
	overflow-y: auto;
	overscroll-behavior: contain;
}

.report-workspace__group {
	margin: var(--erp-space-2) 0 2px;
	padding: 0 8px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: 0.04em;
	text-transform: uppercase;
}

.report-workspace__item {
	display: flex;
	align-items: center;
	gap: 8px;
	width: 100%;
	min-height: 32px;
	padding: 5px 8px;
	border: 0;
	border-radius: var(--erp-control-radius);
	background: transparent;
	color: var(--erp-text-secondary);
	font: inherit;
	font-size: var(--erp-font-size-caption);
	text-align: left;
	cursor: pointer;
	transition: background var(--erp-transition-fast), color var(--erp-transition-fast);
}

.report-workspace__item i {
	flex: none;
	color: var(--erp-text-subtle);
	font-size: 0.78rem;
}

.report-workspace__item span {
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.report-workspace__item:hover,
.report-workspace__item.is-highlighted {
	background: var(--erp-surface-hover);
	color: var(--erp-text);
}

.report-workspace__item:focus-visible {
	outline: none;
	box-shadow: var(--erp-focus-ring);
}

.report-workspace__item.is-selected {
	background: var(--erp-accent-soft);
	color: var(--erp-accent-ink);
	font-weight: var(--erp-font-weight-semibold);
}

.report-workspace__item.is-selected i {
	color: var(--erp-accent-ink);
}

.report-workspace__empty {
	margin: var(--erp-space-2) 8px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-workspace__mobile {
	display: none;
}

.report-workspace__content {
	min-width: 0;
}

@media (max-width: 760px) {
	.report-workspace {
		grid-template-columns: minmax(0, 1fr);
		gap: var(--erp-space-2);
	}

	.report-workspace__nav {
		display: none;
	}

	.report-workspace__mobile {
		position: sticky;
		z-index: var(--erp-layer-sticky);
		top: var(--report-workspace-top);
		display: grid;
		gap: 6px;
		padding: var(--erp-space-2) 0;
		background: var(--erp-bg);
		font-size: var(--erp-font-size-caption);
		font-weight: 650;
	}
}
</style>
