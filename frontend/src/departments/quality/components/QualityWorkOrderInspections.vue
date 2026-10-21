<template>
	<section class="quality-wo-inspections" aria-label="Quality Inspections">
		<header><i class="pi pi-verified" aria-hidden="true" /><h2>Quality Inspections</h2><span v-if="!loading && canRead" class="quality-wo-inspections__muted">{{ inspections.length }}</span></header>
		<span v-if="loading" class="quality-wo-inspections__muted">Loading inspections…</span>
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<template v-else-if="canRead">
			<ul v-if="inspections.length">
				<li v-for="inspection in inspections" :key="inspection.name">
					<DocumentLink :doctype="INSPECTION_DOCTYPE" :name="inspection.name" current-path="/web/quality/work-orders" />
					<div class="quality-wo-inspections__meta"><span>{{ inspection.inspection_type }} · {{ formatDate(inspection.posting_date) }}</span><DocumentStatusBadge :docstatus="inspection.docstatus" /><DocumentStatusBadge v-if="inspection.result" :label="inspection.result" :tone="resultTone(inspection.result)" /></div>
				</li>
			</ul>
			<p v-else class="quality-wo-inspections__empty"><i class="pi pi-inbox" aria-hidden="true" /> No inspections yet.</p>
		</template>
		<span v-else class="quality-wo-inspections__muted">You do not have permission to view inspections.</span>
	</section>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from "vue"
import { getList } from "../../../api/frappe.js"
import { getQualityCapabilities } from "../../../api/quality.js"
import DocumentLink from "../../../components/common/DocumentLink.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { formatDate } from "../../../components/reports/reportUtils.js"
import { INSPECTION_DOCTYPE, resultTone } from "../qualityViews.js"

const props = defineProps({ workOrder: { type: String, required: true } })
const emit = defineEmits(["can-create"])
const loading = ref(true)
const error = ref("")
const canRead = ref(false)
const inspections = ref([])
let loadSequence = 0

async function load() {
	const sequence = ++loadSequence
	const name = props.workOrder
	loading.value = true
	error.value = ""
	inspections.value = []
	canRead.value = false
	emit("can-create", false)
	try {
		const capability = (await getQualityCapabilities())?.sections?.inspections || {}
		if (sequence !== loadSequence) return
		emit("can-create", Boolean(capability.can_create))
		canRead.value = Boolean(capability.can_read)
		if (!canRead.value || !name) return
		const rows = await getList(INSPECTION_DOCTYPE, {
			filters: [["against_id", "=", name]],
			fields: ["name", "inspection_type", "posting_date", "result", "docstatus"],
			orderBy: "posting_date desc, creation desc", pageLength: 0,
		})
		if (sequence === loadSequence) inspections.value = rows || []
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason?.message || "Unable to load Quality Inspections."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

watch(() => props.workOrder, load, { immediate: true })
onBeforeUnmount(() => { ++loadSequence })
</script>

<style scoped>
.quality-wo-inspections { display: grid; grid-column: 1 / -1; min-width: 0; gap: var(--erp-space-2); padding: var(--erp-space-3); border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); }
.quality-wo-inspections header { display: flex; align-items: center; gap: var(--erp-space-2); }
.quality-wo-inspections header > i { color: var(--erp-accent-ink); }
.quality-wo-inspections__empty { margin: 0; padding-block: var(--erp-space-3); color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.quality-wo-inspections h2 { margin: 0; font-size: var(--erp-font-size-body); }
.quality-wo-inspections ul { display: grid; gap: var(--erp-space-2); max-height: 320px; overflow: auto; margin: 0; padding: 0; list-style: none; }
.quality-wo-inspections li { display: grid; gap: var(--erp-space-1); padding-block: var(--erp-space-2); border-top: 1px solid var(--erp-border); overflow-wrap: anywhere; }
.quality-wo-inspections li :deep(a) { display: flex; align-items: center; min-height: 44px; }
.quality-wo-inspections__meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--erp-space-2); font-size: var(--erp-font-size-caption); }
.quality-wo-inspections__muted { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
</style>
