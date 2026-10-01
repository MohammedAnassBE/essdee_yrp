<template>
	<section ref="root" class="erp-cpm-workspace">
		<div v-if="loading && !loaded" class="erp-workspace-loading"><Skeleton v-for="index in 6" :key="index" height="4.8rem" /></div>
		<Message v-else-if="error && !loaded" severity="error" :closable="false">{{ error }}</Message>
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
						<header><strong>{{ movement.name }}</strong><span class="erp-status" :class="statusClass(movement.status)">{{ movement.status }}</span></header>
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

import CpmMovementDialog from "./CpmMovementDialog.vue"
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
function statusClass(status) { return `erp-status--${String(status || "").toLowerCase()}` }
function formatDate(value, includeTime = false) { const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/); if (!match) return value || "—"; const date = `${match[3]}-${match[2]}-${match[1]}`; return includeTime && match[4] ? `${date} · ${match[4]}:${match[5]}` : date }
function movementDateTime(movement) { const date = formatDate(movement.movement_date || movement.posting_date); const time = String(movement.posting_time || "").slice(0, 5); return time ? `${date} · ${time}` : formatDate(movement.modified, true) }

defineExpose({ load, activate: () => load(true) })
</script>

<style scoped>
.erp-cpm-workspace{display:grid;gap:14px;min-height:360px}.erp-workspace-loading{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.erp-workspace-header{display:flex;align-items:center;justify-content:space-between;gap:16px}.erp-workspace-header h2{margin:0;color:#1c3327;font-size:1.12rem;letter-spacing:-.015em}.erp-panel-stack{display:grid;gap:12px}.erp-panel-heading{display:flex;align-items:center;justify-content:space-between;gap:14px}.erp-panel-heading h3{margin:0;color:#233b2f;font-size:.92rem}.erp-record-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.erp-record-card{display:grid;gap:10px;padding:12px;border:1px solid #dce7e1;border-radius:10px;background:#fff;box-shadow:0 3px 12px rgb(34 74 53 / 4%)}.erp-record-card>header,.erp-record-card>footer{display:flex;align-items:center;justify-content:space-between;gap:10px}.erp-record-card>header strong{color:#20372b;font-size:.84rem}.erp-movement-time{display:flex;align-items:center;gap:9px;padding:8px 10px;border:1px solid #dfeae4;border-radius:8px;background:#f5faf7}.erp-movement-time>i{display:grid;width:28px;height:28px;place-items:center;border-radius:7px;background:#e1f3e9;color:#087c4b}.erp-movement-time>div{display:grid;gap:1px}.erp-movement-time small{color:#718078;font-size:.59rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase}.erp-movement-time strong{color:#213c2e;font-size:.76rem;font-variant-numeric:tabular-nums}.erp-status{display:inline-flex;width:max-content;padding:3px 8px;border-radius:999px;background:#eef2f0;color:#56635c;font-size:.62rem;font-style:normal;font-weight:750;text-transform:uppercase}.erp-status--submitted{background:#ddf6e9;color:#087848}.erp-status--cancelled{background:#fde8e8;color:#b42318}.erp-record-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));overflow:hidden;border:1px solid #e2eae6;border-radius:8px;background:#f9fbfa}.erp-record-metrics span{display:grid;gap:2px;padding:8px;border-right:1px solid #e4ebe7}.erp-record-metrics span:last-child{border-right:0}.erp-record-metrics small{color:#78847d;font-size:.59rem}.erp-record-metrics b{color:#263c30;font-size:.8rem}.erp-linked-note{display:flex;align-items:center;gap:6px;color:#5e6c64;font-size:.67rem}.erp-linked-note i{color:#078451}.erp-empty-state{display:grid;justify-items:center;gap:6px;padding:38px 18px;border:1px dashed #cfddd5;border-radius:10px;background:#fbfdfc;color:#738078;text-align:center}.erp-empty-state>i{display:grid;width:38px;height:38px;place-items:center;border-radius:10px;background:#e9f5ee;color:#0a8752}.erp-empty-state strong{color:#344a3e;font-size:.8rem}.erp-empty-state span{font-size:.71rem}@media(max-width:1050px){.erp-record-grid{grid-template-columns:1fr}}@media(max-width:650px){.erp-workspace-header,.erp-panel-heading{align-items:stretch;flex-direction:column}.erp-record-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>
