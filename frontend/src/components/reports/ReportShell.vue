<template>
	<section ref="reportRoot" class="report-shell erp-card" :aria-label="title" :aria-busy="loading">
		<header v-if="showInlineHeading" class="report-shell__heading erp-page-header">
			<InlinePageNavigation :title-target="headingId" />
			<h1 :id="headingId">{{ title }}</h1>
		</header>
		<form class="report-shell__filters" @submit.prevent="$emit('generate')">
			<div class="report-filter-grid"><slot name="filters" /></div>
			<div class="report-shell__commands erp-command-bar">
				<Button
					type="submit"
					:label="generateLabel"
					icon="pi pi-play"
					class="erp-action-button erp-action-button--primary"
					:loading="loading"
					:disabled="generateDisabled"
				/>
				<Button
					v-if="copyable"
					type="button"
					:label="copying ? 'Copying' : copied ? 'Copied' : 'Copy Report'"
					:icon="copied ? 'pi pi-check' : 'pi pi-copy'"
					:severity="copied ? 'success' : 'secondary'"
					outlined
					class="erp-action-button report-shell__copy-button"
					:loading="copying"
					:disabled="loading || copying || !generated || !hasResults"
					@click="copyReport"
				/>
				<slot name="actions" />
				<ReportActions :items="moreActions" />
				<ReportExportButton
					v-if="exportSource"
					ref="exporter"
					hide-button
					:title="title"
					:source="exportSource"
					:get-rows="getRenderedRows"
				/>
			</div>
		</form>
		<Message v-if="error" severity="error" :closable="false" class="report-shell__message">
			{{ error }}
		</Message>
		<div v-if="$slots.status" class="report-shell__status"><slot name="status" /></div>

		<template v-if="!statusOnly">
			<p v-if="loading && keepResultsWhileLoading && generated" class="report-shell__refreshing" role="status">Refreshing report. Previously generated values remain visible.</p>
			<div v-if="loading && !(keepResultsWhileLoading && generated)" class="report-shell__loading" aria-live="polite">
				<Skeleton width="100%" height="62px" border-radius="10px" />
				<Skeleton width="100%" height="210px" border-radius="10px" />
			</div>
			<div v-else-if="!generated" class="erp-empty-state report-shell__empty">
				<div>
					<i class="pi pi-sliders-h" aria-hidden="true" />
					<strong>Set the report filters</strong>
					<span>No report data is requested until you choose {{ generateLabel }}.</span>
				</div>
			</div>
			<div v-else-if="!hasResults" class="erp-empty-state report-shell__empty">
				<div>
					<i class="pi pi-inbox" aria-hidden="true" />
					<strong>{{ emptyTitle }}</strong>
					<span v-if="emptyDescription">{{ emptyDescription }}</span>
				</div>
			</div>
			<div v-else ref="resultsRoot" class="report-shell__results">
				<div v-if="$slots.metrics" class="report-metrics"><slot name="metrics" /></div>
				<slot />
			</div>
		</template>
	</section>
</template>

<script setup>
import { computed, nextTick, ref } from "vue"
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"

import { copyElementAsImage, copyPendingImage } from "./copyElementAsImage.js"
import { useCopyFeedback } from "../../composables/useCopyFeedback.js"
import ReportActions from "./ReportActions.vue"
import ReportExportButton from "./ReportExportButton.vue"
import { renderedReportRows } from "./reportExport.js"
import InlinePageNavigation from "../navigation/InlinePageNavigation.vue"
import { usePageNavigation } from "../navigation/pageNavigationContext.js"

const props = defineProps({
	title: { type: String, required: true },
	generated: { type: Boolean, default: false },
	loading: { type: Boolean, default: false },
	error: { type: String, default: "" },
	hasResults: { type: Boolean, default: false },
	copyable: { type: Boolean, default: false },
	/** Runs before Copy Report captures; may mount hidden rows and return a function that undoes it. */
	beforeCopy: { type: Function, default: null },
	/** Secondary actions for the "⋯" menu, as PrimeVue Menu items. Keep only record operations in the #actions slot. */
	actions: { type: Array, default: () => [] },
	exportSource: { type: Object, default: null },
	keepResultsWhileLoading: { type: Boolean, default: false },
	generateDisabled: { type: Boolean, default: false },
	generateLabel: { type: String, default: "Generate" },
	statusOnly: { type: Boolean, default: false },
	emptyTitle: { type: String, default: "No matching records" },
	emptyDescription: { type: String, default: "Try a different date, location, item, lot, or status." },
})

const headingId = computed(() => `${props.title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-report-title`)
const pageNavigation = usePageNavigation()
const showInlineHeading = computed(() => Boolean(pageNavigation?.inline?.value))

const emit = defineEmits(["generate", "reset"])

const exporter = ref(null)
const moreActions = computed(() => [
	{ label: "Reset", icon: "pi pi-refresh", disabled: props.loading, command: () => emit("reset") },
	props.exportSource && { label: "Export", icon: "pi pi-download", visible: Boolean(exporter.value?.canExport), disabled: props.loading || !props.generated || !props.hasResults, command: () => exporter.value.open() },
	...props.actions,
])

const reportRoot = ref(null)
const resultsRoot = ref(null)
const getRenderedRows = () => renderedReportRows(resultsRoot.value)
const { copying, copied, runCopy } = useCopyFeedback({ success: "Report copied to clipboard" })
const COPY_HIDDEN = [".report-shell__filters", ".report-shell__refreshing"]

function copyReport() {
	return runCopy(async () => {
		if (copyPendingImage(reportRoot.value)) return
		const restoreState = props.beforeCopy ? await props.beforeCopy() : null
		await nextTick()
		try {
			await copyElementAsImage(reportRoot.value, { hide: COPY_HIDDEN })
		} finally {
			restoreState?.()
		}
	})
}
</script>

<style scoped>
.report-shell {
	min-width: 0;
	overflow: hidden;
}

.report-shell__heading {
	display: flex;
	min-height: 48px;
	align-items: center;
	gap: 10px;
	padding: 5px var(--erp-space-4);
	border-bottom: 1px solid var(--erp-border);
}

.report-shell__filters {
	display: flex;
	align-items: flex-end;
	gap: var(--erp-space-3);
	padding: 14px 18px;
	background: var(--erp-surface-soft);
	border-bottom: 1px solid var(--erp-border);
}

.report-filter-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
	gap: 16px 20px;
	min-width: 0;
	flex: 1;
	align-items: end;
}

.report-filter-grid :deep(label) {
	min-width: 0;
}

.report-filter-grid :deep(.p-inputtext) {
	width: 100%;
	min-height: var(--erp-control-height);
	font-size: var(--erp-font-size-table);
}

.report-shell__commands {
	flex: 0 0 auto;
	padding-bottom: 1px;
}

.report-shell__copy-button {
	min-width: 108px;
}

.report-shell__message {
	margin: var(--erp-space-3) var(--erp-space-4) 0;
}

.report-shell__status {
	padding: var(--erp-space-4);
}

.report-shell__status:empty {
	display: none;
}

.report-shell__loading {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-5);
}

.report-shell__refreshing {
	margin: 0;
	padding: var(--erp-space-3) var(--erp-space-4) 0;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
}

.report-shell__empty {
	min-height: 260px;
	margin: var(--erp-space-4);
}

.report-shell__empty div {
	display: grid;
	justify-items: center;
	gap: 7px;
}

.report-shell__results {
	display: grid;
	gap: var(--erp-space-3);
	padding: var(--erp-space-4) var(--erp-space-4) var(--erp-space-5);
}

.report-metrics {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
	gap: 1px;
	background: var(--erp-border);
	border: 1px solid var(--erp-border);
	border-radius: var(--erp-panel-radius);
	overflow: hidden;
}

.report-metrics :deep(.report-metric) {
	display: flex;
	align-items: center;
	gap: var(--erp-space-2);
	min-height: 54px;
	padding: 9px 11px;
	background: var(--erp-surface);
	border: 0;
	border-radius: 0;
}

.report-metrics :deep(.report-metric i) {
	color: var(--erp-accent);
	font-size: var(--erp-font-size-md);
}

.report-metrics :deep(.report-metric span) {
	display: block;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-min);
	font-weight: var(--erp-font-weight-bold);
	letter-spacing: .07em;
	text-transform: uppercase;
}

.report-metrics :deep(.report-metric strong) {
	display: block;
	margin-top: 2px;
	font-size: var(--erp-font-size-section);
	letter-spacing: -.01em;
	font-variant-numeric: tabular-nums;
	font-weight: var(--erp-font-weight-bold);
	color: var(--erp-text);
}

.report-shell :deep(.erp-table-wrap),
.report-shell :deep(.production-table-wrap) {
	scrollbar-gutter: stable;
}

.report-shell :deep(.report-table-frame) {
	max-height: max(320px, calc(100dvh - var(--erp-shell-header-height) - 128px));
	overscroll-behavior: contain;
}

@media (max-width: 800px) {
	.report-shell__filters {
		align-items: stretch;
		flex-direction: column;
	}

	.report-filter-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.report-shell__commands {
		width: 100%;
	}

	.report-shell__commands :deep(.p-button) {
		flex: 1;
	}

	.report-shell__commands :deep(.report-actions__trigger) {
		flex: 0 0 auto;
	}
}

@media (max-width: 360px) {
	.report-filter-grid {
		grid-template-columns: minmax(0, 1fr);
	}

	.report-shell__commands {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
	}

	.report-shell__commands :deep(.p-button) {
		width: 100%;
		min-width: 0;
		min-height: 44px;
	}

	.report-shell__commands :deep(.p-button:first-child) {
		grid-column: 1 / -1;
	}

	.report-shell__commands :deep(.report-actions__trigger) {
		width: auto;
		min-width: 44px;
	}

	.report-shell__copy-button {
		min-width: 0;
	}
}

@media (min-width: 361px) and (max-width: 430px) {
	.report-shell__commands { gap: 6px; }
	.report-shell__commands :deep(.p-button) {
		padding-inline: 8px;
		font-size: var(--erp-font-size-caption);
	}
	.report-shell__commands :deep(.p-button-label) { white-space: nowrap; }
	.report-shell__copy-button { min-width: 0; }
}
@media (pointer: coarse) {
	.report-filter-grid :deep(.p-inputtext) {
		font-size: var(--erp-font-size-section);
	}
}
</style>
