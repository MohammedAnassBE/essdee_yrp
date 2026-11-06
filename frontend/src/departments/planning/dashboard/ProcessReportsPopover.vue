<template>
	<Popover ref="popover" class="pf-reports-popover" @show="onShow" @hide="query = ''">
		<div class="pf-reports" :style="{ '--pf-reports-height': `${listHeight}px` }" role="dialog" aria-label="Planning reports">
			<header class="pf-reports__head"><strong>Planning reports</strong><span>Prefilled from {{ context.process }} · {{ context.lot }}</span></header>
			<div class="pf-reports__search">
				<InputText ref="search" v-model="query" size="small" placeholder="Search reports" aria-label="Search reports" @keydown="onKeydown" />
			</div>
			<ul v-if="matches.length" role="menu">
				<li v-for="(report, index) in matches" :key="report.key">
					<a role="menuitem" :class="{ 'is-active': index === active }" :href="href(report)" target="_blank" rel="noopener" @mouseenter="active = index">
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

import { filterReports, reportHref, reportPrefill, reportsListHeight, stepReportContext } from "../../../utils/lotProcessFlow.js"

/** Searchable Planning reports opened in a new tab with the lot, process and supplier of one process prefilled. */
const props = defineProps({ reports: { type: Array, default: () => [] } })
const REPORTS_PATH = "/web/planning/reports"
const popover = ref(null)
const search = ref(null)
const query = ref("")
const active = ref(0)
const listHeight = ref(420)
const context = ref({})
const matches = computed(() => filterReports(props.reports, query.value))
const href = (report) => reportHref(REPORTS_PATH, report, context.value)
const prefillText = (report) => reportPrefill(report, context.value).map((filter) => `${filter.label} ${filter.value || "any"}`).join(" · ") || "Opens with its own defaults"

watch(query, () => { active.value = 0 })

/** Opens beside `target` for `{ lot, item, step }`, after the menu click that asked for it has finished. */
function show(target, { lot, item, step }) {
	context.value = stepReportContext(lot, item, step.name, step.work_orders)
	listHeight.value = reportsListHeight(target.getBoundingClientRect(), window.innerHeight)
	setTimeout(() => popover.value?.show({ currentTarget: target }, target), 0)
}

async function onShow() {
	await nextTick()
	search.value?.$el?.focus()
}

function onKeydown(event) {
	if (event.key === "ArrowDown" || event.key === "ArrowUp") {
		event.preventDefault()
		if (matches.value.length) active.value = (active.value + (event.key === "ArrowDown" ? 1 : -1) + matches.value.length) % matches.value.length
	} else if (event.key === "Enter" && matches.value.length) {
		event.preventDefault()
		window.open(href(matches.value[active.value]), "_blank", "noopener")
	} else if (event.key === "Escape") {
		event.preventDefault()
		if (query.value) query.value = ""
		else popover.value?.hide()
	}
}

defineExpose({ show })
</script>
