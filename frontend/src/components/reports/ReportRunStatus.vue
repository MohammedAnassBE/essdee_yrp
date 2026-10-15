<template>
	<article
		v-if="isRunning"
		class="report-run-status report-run-status--running"
		role="status"
		aria-live="polite"
	>
		<span class="report-run-status__spinner" aria-hidden="true"><i class="pi pi-spin pi-spinner" /></span>
		<div class="report-run-status__body">
			<p class="report-run-status__eyebrow">{{ state === "queued" ? "Queued" : `Running · ${elapsed}` }}</p>
			<h2>Running in the background, please wait…</h2>
			<p>The result will appear here automatically when it is ready. You can keep working while it runs.</p>
			<div class="report-run-status__progress">
				<ProgressBar v-if="determinate" :value="progress" :show-value="true" />
				<ProgressBar v-else mode="indeterminate" />
			</div>
		</div>
	</article>

	<article v-else-if="state === 'expired'" class="report-run-status report-run-status--expired" role="alert">
		<i class="pi pi-history" aria-hidden="true" />
		<div class="report-run-status__body">
			<p class="report-run-status__eyebrow">Result unavailable</p>
			<h2>Permissions changed or result too old — Rebuild</h2>
			<p>This saved result can no longer be shown safely. Build a fresh result with the current filters.</p>
			<Button label="Rebuild" icon="pi pi-refresh" class="erp-action-button" @click="$emit('rebuild')" />
		</div>
	</article>

	<article v-else-if="state === 'error'" class="report-run-status report-run-status--error" role="alert">
		<i class="pi pi-exclamation-triangle" aria-hidden="true" />
		<div class="report-run-status__body">
			<p class="report-run-status__eyebrow">Report stopped</p>
			<h2>We couldn’t finish this report</h2>
			<p>{{ error || "The background report failed. Please try again." }}</p>
			<Button label="Retry" icon="pi pi-refresh" class="erp-action-button" @click="$emit('rebuild')" />
		</div>
	</article>

	<div v-else-if="showGenerated" class="report-run-status__generated" role="status">
		<span><i class="pi pi-check-circle" />Generated {{ generatedAgo }}</span>
		<Button label="Rebuild" icon="pi pi-refresh" severity="secondary" outlined class="erp-action-button" @click="$emit('rebuild')" />
	</div>
	<p v-if="hasLinkedColumns && state === 'ready'" class="report-run-status__linked">
		<i class="pi pi-info-circle" /> Linked columns show current values.
	</p>
</template>

<script setup>
import Button from "primevue/button"
import ProgressBar from "primevue/progressbar"
import { computed, onBeforeUnmount, ref } from "vue"

const props = defineProps({
	state: { type: String, default: "idle" },
	job: { type: Object, default: null },
	generatedAt: { type: [String, Date], default: null },
	trackingStartedAt: { type: Number, default: null },
	determinate: { type: Boolean, default: false },
	showGenerated: { type: Boolean, default: false },
	error: { type: String, default: "" },
	hasLinkedColumns: { type: Boolean, default: false },
})

defineEmits(["rebuild"])

const clock = ref(Date.now())
const timer = window.setInterval(() => { clock.value = Date.now() }, 1_000)
const isRunning = computed(() => ["queued", "running"].includes(props.state))
const progress = computed(() => Math.max(0, Math.min(Number(props.job?.progress || 0), 100)))
const elapsed = computed(() => formatDuration(clock.value - (props.trackingStartedAt || clock.value)))
const generatedAgo = computed(() => relativeTime(props.generatedAt, clock.value))

onBeforeUnmount(() => window.clearInterval(timer))

function formatDuration(milliseconds) {
	const seconds = Math.max(0, Math.floor(milliseconds / 1_000))
	return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
}

function relativeTime(value, now) {
	if (!value) return "just now"
	const parsed = new Date(typeof value === "string" ? value.replace(" ", "T") : value)
	const seconds = Math.max(0, Math.floor((now - parsed.getTime()) / 1_000))
	if (!Number.isFinite(seconds) || seconds < 60) return "just now"
	if (seconds < 3_600) return `${Math.floor(seconds / 60)} min ago`
	if (seconds < 86_400) return `${Math.floor(seconds / 3_600)} h ago`
	return `${Math.floor(seconds / 86_400)} d ago`
}
</script>

<style scoped>
.report-run-status {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr);
	align-items: center;
	gap: var(--erp-space-4);
	min-height: 230px;
	padding: clamp(24px, 5vw, 54px);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-panel-radius);
	background: var(--erp-accent-soft);
}

.report-run-status > i {
	font-size: 2rem;
}

.report-run-status__spinner {
	display: grid;
	place-items: center;
	width: 64px;
	height: 64px;
	border-radius: 50%;
	background: var(--erp-surface);
	box-shadow: 0 0 0 1px var(--erp-accent-border);
	color: var(--erp-accent-dark);
}

.report-run-status__spinner .pi {
	font-size: 1.9rem;
}

.report-run-status__body {
	display: grid;
	max-width: 680px;
	gap: 9px;
}

.report-run-status__eyebrow,
.report-run-status__body h2,
.report-run-status__body p {
	margin: 0;
}

.report-run-status__eyebrow {
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-min);
	font-weight: 800;
	letter-spacing: .06em;
	text-transform: uppercase;
}

.report-run-status__body h2 {
	color: var(--erp-text);
	font-size: clamp(1.15rem, 2vw, 1.55rem);
	letter-spacing: -.025em;
}

.report-run-status__body > p:not(.report-run-status__eyebrow) {
	color: var(--erp-text-muted);
	line-height: 1.55;
}

.report-run-status__progress {
	max-width: 520px;
	margin-top: 7px;
}

.report-run-status__progress :deep(.p-progressbar) {
	height: 8px;
}

.report-run-status__progress :deep(.p-progressbar-determinate) {
	height: 18px;
}

.report-run-status__progress :deep(.p-progressbar) {
	height: 10px;
}

.report-run-status--expired {
	border-color: #ead9ad;
	background: #fffaf0;
}

.report-run-status--expired > i {
	color: #9a6a12;
}

.report-run-status--error {
	border-color: #f0c9ce;
	background: var(--erp-danger-soft);
}

.report-run-status--error > i {
	color: var(--erp-danger);
}

.report-run-status__generated {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: var(--erp-space-3);
	padding: var(--erp-space-3) var(--erp-space-4);
	border: 1px solid var(--erp-accent-border);
	border-radius: var(--erp-control-radius);
	background: var(--erp-mint);
	color: var(--erp-accent-dark);
	font-size: var(--erp-font-size-caption);
	font-weight: 750;
}

.report-run-status__generated span {
	display: inline-flex;
	align-items: center;
	gap: 7px;
}

.report-run-status__linked {
	margin: var(--erp-space-2) 0 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-run-status__linked i {
	margin-right: 4px;
	color: var(--erp-accent);
}

@media (max-width: 560px) {
	.report-run-status {
		grid-template-columns: minmax(0, 1fr);
		align-content: center;
	}

	.report-run-status__generated {
		align-items: stretch;
		flex-direction: column;
	}
}
</style>
