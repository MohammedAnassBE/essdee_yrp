<!-- home-queues block — "My Work Today" live queues as big stat cards.

     Extracted 1:1 from views/home/HomePage.vue (build step 4); wraps
     composables/useHomeQueues.js unchanged. Each card deep-links to its
     DocType list pre-filtered (openQueue); failures show a retryable dash.
     Queue visibility stays gated per-queue on canRead(doctype) inside
     useHomeQueues — arrangement never grants capability (spec §15).

     Knobs (2026-07-15 Demo-7 skin — defaults reproduce today's behavior):
       stats : Array<String> — metric-registry names ("open_lots", "open_wos",
               "draft_dcs", "draft_grns") selecting/ordering the cards. The
               registry (name → doctype + filters + route) is CODE-owned in
               useHomeQueues; a layout can only NAME metrics, never define
               them. Knob absent → today's full queue set in today's order.
               When the knob is present the arrow renders as the demo's ↗
               (pi-arrow-up-right); absent keeps today's pi-arrow-right so the
               Default stays pixel-identical.
     Realtime: every visible queue doctype is subscribed via subscribeList —
     counts refresh silently (no popup, old number stays until the new one
     lands) whenever any record of that doctype changes. -->
<template>
	<div v-if="visibleQueues.length" class="stat-grid">
		<button
			v-for="q in visibleQueues"
			:key="q.key"
			class="stat-card"
			:aria-label="countState(q) === 'error' ? `Retry loading ${q.label}` : q.label"
			@click="countState(q) === 'error' ? retryQueue(q) : openQueue(q)"
		>
			<i :class="[stats ? 'pi pi-arrow-up-right' : 'pi pi-arrow-right', 'stat-arrow']" />
			<div class="stat-n">
				<i v-if="countState(q) === 'loading'" class="pi pi-spin pi-spinner stat-spin" />
				<span v-else-if="countState(q) === 'error'" class="stat-dash">—</span>
				<template v-else>{{ q.count }}</template>
			</div>
			<div class="stat-l">{{ q.label }}</div>
			<div v-if="countState(q) === 'error'" class="stat-retry">
				<i class="pi pi-refresh" /> Retry
			</div>
		</button>
	</div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, watch } from "vue"
import { useRouter } from "vue-router"
import { useHomeQueues } from "@/composables/useHomeQueues"
import { useRealtime } from "@/composables/useRealtime"

defineOptions({ inheritAttrs: false })

const props = defineProps({
	// Metric-registry names (layout knob). null → today's full queue set.
	stats: { type: Array, default: null },
})

const router = useRouter()
const { visibleQueues: queueVisible, loadCounts } = useHomeQueues()

// Metric name (layout vocabulary, demo METRICS registry) → queue key (code).
const METRIC_TO_QUEUE = {
	open_lots: "open-lots",
	open_wos: "open-work-orders",
	draft_dcs: "draft-dcs",
	draft_grns: "draft-grns",
}

const visibleQueues = computed(() => {
	const readable = queueVisible()
	if (!Array.isArray(props.stats)) return readable
	// Knob present: select + order by the named metrics; unknown names drop.
	return props.stats
		.map((m) => readable.find((q) => q.key === METRIC_TO_QUEUE[m]))
		.filter(Boolean)
})

function countState(q) {
	if (q.error) return "error"
	if (q.count === null || q.count === undefined) return "loading"
	return "value"
}

function retryQueue(q) {
	q.error = false
	q.count = null
	loadCounts()
}

function openQueue(q) {
	if (!q.route) return
	const encoded = encodeURIComponent(JSON.stringify(q.filters))
	router.push(`/${q.route}?filters=${encoded}`)
}

// ── Realtime: silent count refresh on any change in a visible queue's doctype.
// subscribeList already debounces (>=500ms) per doctype; loadCounts leaves the
// old number on screen until the new one arrives — no flash, no popup.
const { subscribeList } = useRealtime()
let rtDisposers = []
function resubscribe() {
	rtDisposers.forEach((d) => d())
	rtDisposers = []
	const doctypes = [...new Set(visibleQueues.value.map((q) => q.doctype))]
	for (const dt of doctypes) rtDisposers.push(subscribeList(dt, () => loadCounts()))
}

// Card set can change reactively (knob via layout refresh / preview-as).
watch(visibleQueues, resubscribe)

onMounted(() => {
	loadCounts()
	resubscribe()
})
onUnmounted(() => {
	rtDisposers.forEach((d) => d())
	rtDisposers = []
})
</script>

<style scoped>
/* Styles lifted verbatim from HomePage.vue. */
.stat-grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
	gap: 14px;
}

.stat-card {
	position: relative;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	box-shadow: var(--esd-shadow-card);
	padding: 16px 18px;
	text-align: left;
	cursor: pointer;
	transition: transform 0.14s, box-shadow 0.14s;
}
.stat-card:hover {
	transform: translateY(-1px);
	box-shadow: var(--esd-shadow-pop);
}

.stat-arrow {
	position: absolute;
	top: 16px;
	right: 16px;
	color: var(--esd-muted-2);
	font-size: 13px;
	transition: color 0.14s;
}
.stat-card:hover .stat-arrow {
	color: var(--esd-accent);
}

.stat-n {
	font-size: 26px;
	font-weight: 800;
	line-height: 1;
	color: var(--esd-ink);
	letter-spacing: -0.02em;
	min-height: 26px;
}
.stat-l {
	margin-top: 8px;
	font-size: 12.5px;
	color: var(--esd-muted);
}
.stat-spin {
	font-size: 18px;
	color: var(--esd-muted);
}
.stat-dash {
	color: var(--esd-muted-2);
}
.stat-retry {
	margin-top: 6px;
	font-size: 12px;
	font-weight: 600;
	color: var(--esd-accent-700);
}
.stat-retry i {
	font-size: 11px;
}
</style>
