<template>
	<button ref="trigger" type="button" class="pf-toggle" aria-haspopup="menu" :aria-expanded="open" @click="toggle">
		<i class="pi pi-chart-bar" aria-hidden="true" /><span>Reports</span>
	</button>
	<Popover ref="popover" class="pf-reports-popover" @show="onShow" @hide="onHide">
		<div class="pf-reports" :style="{ '--pf-reports-height': `${listHeight}px` }">
			<header class="pf-reports__head"><strong>Planning reports</strong><span>Opens in a new tab with filters from {{ context.process }}</span></header>
			<div class="pf-reports__search">
				<InputText ref="search" v-model="query" size="small" placeholder="Search reports…" aria-label="Search reports" aria-controls="pf-reports-list" :aria-activedescendant="matches.length ? `pf-report-${active}` : undefined" @keydown="onKeydown" />
			</div>
			<ul v-if="matches.length" id="pf-reports-list" ref="list" role="menu">
				<li v-for="(report, index) in matches" :key="report.key">
					<a :id="`pf-report-${index}`" role="menuitem" :class="{ 'is-active': index === active }" :href="href(report)" target="_blank" rel="noopener" @mouseenter="active = index">
						<i :class="report.icon || 'pi pi-table'" aria-hidden="true" />
						<span><strong>{{ report.label }}</strong><small>{{ prefillText(report) }}</small></span>
						<i class="pi pi-external-link" aria-hidden="true" />
					</a>
				</li>
			</ul>
			<p v-else class="pf-modal__none pf-reports__empty">{{ reports.length ? "No reports match" : "No Planning report is available to you." }}</p>
		</div>
	</Popover>
</template>
<script setup>
import InputText from "primevue/inputtext"
import Popover from "primevue/popover"
import { computed, nextTick, ref, watch } from "vue"
import { filterReports, reportHref, reportPrefill, reportsListHeight } from "../../../../utils/lotProcessFlow.js"
/** Searchable Planning production reports; each opens with the step's Lot, Process, Supplier and Item mapped to its own filters. */
const props = defineProps({
	reports: { type: Array, default: () => [] },
	context: { type: Object, required: true },
})
const REPORTS_PATH = "/web/planning/reports"
const popover = ref(null)
const trigger = ref(null)
const search = ref(null)
const list = ref(null)
const open = ref(false)
const query = ref("")
const active = ref(0)
const listHeight = ref(420)
const matches = computed(() => filterReports(props.reports, query.value))
const href = (report) => reportHref(REPORTS_PATH, report, props.context)
const prefillText = (report) => reportPrefill(report, props.context).map((filter) => `${filter.label} ${filter.value || "any"}`).join(" · ") || "No filters from this step"
watch(query, () => { active.value = 0 })
function toggle(event) {
	listHeight.value = reportsListHeight(trigger.value.getBoundingClientRect(), window.innerHeight)
	popover.value?.toggle(event)
}
async function onShow() {
	open.value = true
	await nextTick()
	search.value?.$el?.focus()
}
function onHide() {
	open.value = false
	query.value = ""
}
async function move(step) {
	if (!matches.value.length) return
	active.value = (active.value + step + matches.value.length) % matches.value.length
	await nextTick()
	list.value?.querySelector(".is-active")?.scrollIntoView?.({ block: "nearest" })
}
function onKeydown(event) {
	if (event.key === "ArrowDown" || event.key === "ArrowUp") {
		event.preventDefault()
		move(event.key === "ArrowDown" ? 1 : -1)
	} else if (event.key === "Enter" && matches.value.length) {
		event.preventDefault()
		window.open(href(matches.value[active.value]), "_blank", "noopener")
	} else if (event.key === "Escape") {
		// Esc clears the search first, then closes this list only (not a surrounding modal).
		event.preventDefault()
		event.stopPropagation()
		if (query.value) query.value = ""
		else popover.value?.hide()
	}
}
</script>
