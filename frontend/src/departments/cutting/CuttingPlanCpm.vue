<template>
	<section ref="root" class="erp-cpm-workspace">
		<div v-if="loading && !loaded" class="erp-workspace-loading"><Skeleton v-for="index in 6" :key="index" height="4.8rem" /></div>
		<WorkspaceLoadError v-else-if="error && !loaded" title="Cut Panel Movement unavailable" :message="error" :loading="loading" @retry="load(true)" />
		<template v-else-if="loaded">
			<header class="erp-workspace-header">
				<h2>Cut Panel Movement</h2>
				<Button icon="pi pi-refresh" label="Refresh" severity="secondary" outlined size="small" :loading="loading" @click="load(true)" />
			</header>

			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>

			<div class="erp-panel-stack">
				<div class="erp-panel-heading"><h3>Movements</h3><Button v-if="workspace.permissions?.movement?.can_create" label="Create Movement" icon="pi pi-plus" size="small" @click="openMovement('')" /></div>
				<div v-if="workspace.movements?.length" class="erp-record-grid">
					<article v-for="movement in workspace.movements" :key="movement.name" class="erp-record-card">
						<header><strong>{{ movement.name }}</strong><DocumentStatusBadge :docstatus="movement.docstatus" :label="movement.status" /></header>
						<div class="erp-movement-time"><i class="pi pi-clock"></i><div><small>Movement date &amp; time</small><strong>{{ movementDateTime(movement) }}</strong></div></div>
						<div class="erp-record-metrics"><span><small>Exact bundles</small><b>{{ movement.totals?.exact_bundles || 0 }}</b></span><span><small>Panels</small><b>{{ movement.totals?.selected_panels || 0 }}</b></span><span><small>Collapsed</small><b>{{ movement.totals?.collapsed_rows || 0 }}</b></span><span><small>Accessories</small><b>{{ movement.totals?.accessory_rows || 0 }}</b></span></div>
						<div v-if="movement.against_id || movement.active_root_transactions?.length" class="erp-linked-note"><i class="pi pi-link"></i><span>{{ movement.against_id ? `${movement.against} · ${movement.against_id}` : `${movement.active_root_transactions[0].doctype} · ${movement.active_root_transactions[0].name}` }}</span></div>
						<footer><Button label="View" icon="pi pi-eye" severity="secondary" text size="small" @click="openMovement(movement.name)" /></footer>
					</article>
				</div>
				<div v-else class="erp-empty-state"><i class="pi pi-box"></i><strong>No cut-panel movements yet</strong><span>Generate the available bundles and save the first movement.</span></div>
			</div>
		</template>

		<CpmMovementDialog v-model:visible="movementOpen" :cutting-plan="cuttingPlan" :movement="selectedMovement" @changed="changed" />
	</section>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue"

import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import CpmMovementDialog from "./CpmMovementDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { getCpmWorkspace } from "./cpmApi.js"

const props = defineProps({ cuttingPlan: { type: String, required: true } })
const emit = defineEmits(["changed"])
const root = ref(null)
const loaded = ref(false)
const loading = ref(false)
const error = ref("")
const workspace = reactive({ context: {}, permissions: {}, movements: [], transactions: {} })
const movementOpen = ref(false)
const selectedMovement = ref("")
let observer = null
let loadSequence = 0

onMounted(async () => {
	await nextTick()
	if ("IntersectionObserver" in window) {
		observer = new IntersectionObserver((entries) => {
			if (entries.some((entry) => entry.isIntersecting)) load()
		}, { threshold: 0.01 })
		if (root.value) observer.observe(root.value)
	} else {
		load()
	}
})
onBeforeUnmount(() => observer?.disconnect())
watch(() => props.cuttingPlan, () => { loaded.value = false; load(true) })

async function load(force = false) {
	if ((!force && loaded.value) || loading.value || !props.cuttingPlan) return
	const sequence = ++loadSequence
	loading.value = true
	error.value = ""
	try {
		const data = await getCpmWorkspace(props.cuttingPlan)
		if (sequence !== loadSequence) return
		Object.assign(workspace, data || {})
		loaded.value = true
	} catch (reason) {
		if (sequence === loadSequence) error.value = reason.message || "Unable to load Cutting operations."
	} finally {
		if (sequence === loadSequence) loading.value = false
	}
}

function openMovement(name) { selectedMovement.value = name; movementOpen.value = true }
async function changed(value) { await load(true); emit("changed", value) }
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} · ${match[4]}:${match[5]}` : date }
function formatTime(value) { const match = String(value || "").match(/^(\d{1,2}):(\d{2})/); return match ? `${match[1].padStart(2, "0")}:${match[2]}` : "" }
function movementDateTime(movement) { const date = formatDate(movement.movement_date || movement.posting_date); const time = formatTime(movement.posting_time); return time ? `${date} · ${time}` : formatDate(movement.modified, true) }

defineExpose({ load, activate: () => load(true) })
</script>

<style scoped>
.erp-cpm-workspace { display: grid; gap: 14px; min-height: 360px; }
.erp-workspace-loading { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.erp-workspace-header, .erp-panel-heading, .erp-record-card > header, .erp-record-card > footer { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.erp-workspace-header h2 { margin: 0; color: var(--erp-text); font-size: 18px; letter-spacing: -0.015em; }
.erp-panel-stack { display: grid; gap: 12px; }
.erp-panel-heading h3 { margin: 0; color: var(--erp-text); font-size: 15px; }
.erp-record-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.erp-record-card { display: grid; gap: 10px; padding: 12px; background: var(--erp-surface); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); box-shadow: none; }
.erp-record-card > header strong { color: var(--erp-text); font-size: 13px; }
.erp-movement-time { display: flex; align-items: center; gap: 9px; padding: 8px 10px; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.erp-movement-time > i { display: grid; width: 28px; height: 28px; color: var(--erp-accent); background: var(--erp-accent-soft); border-radius: 7px; place-items: center; }
.erp-movement-time > div { display: grid; gap: 1px; }
.erp-movement-time small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 700; letter-spacing: 0.03em; text-transform: uppercase; }
.erp-movement-time strong { color: var(--erp-text); font-size: var(--erp-font-size-caption); font-variant-numeric: tabular-nums; }
.erp-record-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; background: var(--erp-surface-soft); border: 1px solid var(--erp-border); border-radius: var(--erp-control-radius); }
.erp-record-metrics span { display: grid; gap: 2px; padding: 8px; border-right: 1px solid var(--erp-border); }
.erp-record-metrics span:last-child { border-right: 0; }
.erp-record-metrics small { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.erp-record-metrics b { color: var(--erp-text); font-size: 13px; font-variant-numeric: tabular-nums; }
.erp-linked-note { display: flex; align-items: center; gap: 6px; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); }
.erp-linked-note i { color: var(--erp-accent); }
@media (max-width: 1050px) { .erp-record-grid { grid-template-columns: 1fr; } }
@media (max-width: 650px) { .erp-workspace-header, .erp-panel-heading { align-items: stretch; flex-direction: column; } .erp-record-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
