<template>
	<section data-sewing-report="dpr" aria-label="DPR">
		<ReportShell title="DPR" :loading="loading" :generated="generated" :has-results="blocked || groups.length > 0" copyable keep-results-while-loading @generate="load" @reset="reset">
			<template #filters>
				<div class="common-field"><label for="dpr-mode">DPR Mode</label><select id="dpr-mode" v-model="filters.mode" :disabled="loading"><option value="daily">Daily</option><option value="range">Date range</option></select></div>
				<DateField v-if="filters.mode === 'daily'" v-model="filters.date" label="DPR Date" :disabled="loading" />
				<template v-else><DateField v-model="filters.fromDate" label="From Date" :disabled="loading" /><DateField v-model="filters.toDate" label="To Date" :disabled="loading" /></template>
				<LinkField v-model="filters.workStation" doctype="YRP Work Station" label="Work Station" :show-open-button="false" show-clear :disabled="loading" />
				<LinkField v-model="filters.inputType" doctype="SD YRP Sewing Plan Input Type" label="Input Type" :show-open-button="false" show-clear :disabled="loading" />
			</template>
			<template v-if="blocked">
				<Message severity="warn" :closable="false">{{ result.message || 'Set FI dates for the listed Lots, Colours and Parts to generate this report.' }}</Message>
				<SewingReportMatrix label="Pending FI: blocking Lots, Colours and Parts" :columns="blockerColumns" :rows="blockers" />
			</template>
			<template v-else><section v-for="day in groups" :key="day.date" class="dpr-day">
				<h2>{{ day.date }}</h2>
				<article v-for="(group, index) in day.matrices" :key="index">
					<h3>{{ group.stage }} · {{ group.lot }} · {{ group.item }}</h3>
					<SewingReportMatrix :label="`${day.date} ${group.stage} ${group.lot}`" :columns="group.columns" :rows="group.rows" />
				</article>
			</section></template>
		</ReportShell>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</section>
</template>

<script setup>
import Message from "primevue/message"
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { getSewingDpr } from "../../../api/sewing.js"
import DateField from "../../../components/common/DateField.vue"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import ReportShell from "../../../components/reports/ReportShell.vue"
import SewingReportMatrix from "../components/SewingReportMatrix.vue"
import { useSewingContext } from "../useSewingContext.js"

const props = defineProps({ filters: { type: Object, required: true } })
const { supplier, beginRequest, isCurrent } = useSewingContext()
const result = ref({}), loading = ref(false), generated = ref(false), error = ref("")
let mounted = true
const blockerColumns = [{ key: "lot", label: "Lot" }, { key: "colour", label: "Colour" }, { key: "part", label: "Part" }]
const reports = computed(() => result.value.reports || (result.value.date ? [result.value] : []))
const blockers = computed(() => {
	const entries = [...(result.value.pending_fi || []), ...reports.value.flatMap(report => report.pending_fi || [])]
	return [...new Map(entries.map(row => [JSON.stringify([row.lot, row.colour, row.part]), row])).values()]
})
const blocked = computed(() => Boolean(result.value.blocked || result.value.status === "pending_fi" || blockers.value.length))
const groups = computed(() => reports.value.map(report => {
	const matrices = []
	for (const stage of report.headers || []) for (const [lot, group] of Object.entries(report.dpr_data?.[stage] || {})) {
		const rows = []
		for (const [station, types] of Object.entries(group.details || {})) for (const [type, colours] of Object.entries(types)) for (const colour of Object.values(colours)) {
			rows.push({ station, type, colour: colour.colour, part: colour.part, ...colour.values, total: colour.total })
		}
		matrices.push({ stage, lot, item: group.item, rows, columns: [
			{ key: "station", label: "Work Station" }, { key: "type", label: "Received Type" }, { key: "colour", label: "Colour" }, { key: "part", label: "Part" },
			...(group.primary_values || []).map(size => ({ key: size, label: size, numeric: true })), { key: "total", label: "Total", numeric: true },
		] })
	}
	return { date: report.date, matrices }
}).filter(day => day.matrices.length))
async function load() {
	if (loading.value || !supplier.value) return
	const filters = props.filters
	if (filters.mode === "daily" && !filters.date) { error.value = "Choose a DPR Date."; return }
	if (filters.mode === "range" && (!filters.fromDate || !filters.toDate)) { error.value = "Choose From Date and To Date."; return }
	if (filters.mode === "range" && filters.fromDate > filters.toDate) { error.value = "From Date cannot be after To Date."; return }
	const generation = beginRequest()
	loading.value = true; error.value = ""
	try {
		const data = await getSewingDpr(supplier.value, filters)
		if (mounted && isCurrent(generation)) { result.value = data || {}; generated.value = true }
	} catch (reason) {
		if (mounted && isCurrent(generation)) error.value = reason.message || "Unable to generate DPR."
	} finally { if (mounted && isCurrent(generation)) loading.value = false }
}
function reset() { Object.assign(props.filters, { mode: "daily", date: "", fromDate: "", toDate: "", workStation: "", inputType: "" }) }
watch(() => [props.filters.mode, props.filters.date, props.filters.fromDate, props.filters.toDate, props.filters.workStation, props.filters.inputType], () => { generated.value = false; result.value = {} })
onBeforeUnmount(() => { mounted = false; beginRequest() })
</script>

<style scoped>
.dpr-day, article { display: grid; min-width: 0; gap: 10px; }
.dpr-day { gap: 16px; }
h2, h3 { margin: 0; color: var(--erp-text); font-size: 15px; }
h3 { font-size: var(--erp-font-size-caption); overflow-wrap: anywhere; }
</style>
