<template>
	<div class="home">
		<!-- Greeting + primary create CTA (mockup dashboard header) -->
		<header class="home-head">
			<div class="home-head__text">
				<h1 class="home-title">{{ greeting }}</h1>
				<p class="home-sub">Here's your floor today.</p>
			</div>

			<div
				v-if="primaryCreate"
				class="home-cta"
				:class="{ split: moreCreates.length }"
				@keydown.esc="moreOpen = false"
			>
				<button class="cta-primary" @click="goCreate(primaryCreate)">
					<i class="pi pi-plus" />
					<span>New {{ primaryCreate.label }}</span>
				</button>
				<button
					v-if="moreCreates.length"
					class="cta-more"
					aria-label="More create options"
					:aria-expanded="moreOpen"
					@click="moreOpen = !moreOpen"
				>
					<i class="pi pi-chevron-down" />
				</button>
				<div v-if="moreOpen" class="cta-backdrop" @click="moreOpen = false" />
				<div v-if="moreOpen" class="cta-menu">
					<button
						v-for="qc in moreCreates"
						:key="qc.doctype"
						class="cta-menu__item"
						@click="goCreate(qc)"
					>
						<i :class="qc.icon" />
						<span>New {{ qc.label }}</span>
					</button>
				</div>
			</div>
		</header>

		<!-- My Work Today — live queues as big stat cards. Each deep-links to its
		     DocType list pre-filtered (openQueue); failures show a retryable dash. -->
		<div v-if="visibleQueues.length" class="stat-grid">
			<button
				v-for="q in visibleQueues"
				:key="q.key"
				class="stat-card"
				:aria-label="countState(q) === 'error' ? `Retry loading ${q.label}` : q.label"
				@click="countState(q) === 'error' ? retryQueue(q) : openQueue(q)"
			>
				<i class="pi pi-arrow-right stat-arrow" />
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

		<!-- Recent records — tabbed table over the key submittable doctypes. -->
		<div v-if="recentTabs.length" class="esd-card recent-card">
			<div class="recent-bar">
				<div class="recent-tabs">
					<button
						v-for="t in recentTabs"
						:key="t.doctype"
						class="recent-tab"
						:class="{ active: t.doctype === activeTab }"
						@click="selectTab(t.doctype)"
					>
						Recent {{ t.label }}
					</button>
				</div>
				<button class="recent-viewall" @click="viewAll">View all <i class="pi pi-arrow-right" /></button>
			</div>

			<div class="recent-scroll">
				<table class="recent-table">
					<thead>
						<tr>
							<th>Code</th>
							<th>Status</th>
							<th>Updated</th>
						</tr>
					</thead>
					<tbody>
						<template v-if="recentLoading">
							<tr v-for="n in 4" :key="`sk-${n}`" class="recent-skel-row">
								<td><div class="recent-skel" style="width: 130px" /></td>
								<td><div class="recent-skel" style="width: 72px" /></td>
								<td><div class="recent-skel" style="width: 48px" /></td>
							</tr>
						</template>
						<template v-else-if="recentRows.length">
							<tr v-for="r in recentRows" :key="r.name" @click="openRecord(r.name)">
								<td>
									<router-link
										v-if="recordPath(r.name)"
										:to="recordPath(r.name)"
										class="recent-code"
										@click.stop
									>{{ r.name }}</router-link>
									<span v-else class="recent-code">{{ r.name }}</span>
								</td>
								<td>
									<span class="badge" :class="docStatusClass(r.docstatus)">
										{{ docStatusLabel(r.docstatus) }}
									</span>
								</td>
								<td class="recent-date">{{ fmtDate(r.modified) }}</td>
							</tr>
						</template>
						<tr v-else>
							<td colspan="3" class="recent-empty">Nothing recent yet</td>
						</tr>
					</tbody>
				</table>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue"
import { useRouter, useRoute } from "vue-router"
import { useAuth } from "@/composables/useAuth"
import { usePermissions } from "@/composables/usePermissions"
import { getRegistryByDoctype } from "@/config/doctypes"
import { useHomeQueues } from "@/composables/useHomeQueues"
import { getList } from "@/api/client"

const router = useRouter()
const route = useRoute()
const { fullName } = useAuth()
const { canRead, canCreate } = usePermissions()
const { visibleQueues: queueVisible, loadCounts } = useHomeQueues()

const greeting = computed(() => {
	const h = new Date().getHours()
	const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"
	const name = (fullName.value || "").split(" ")[0]
	return name ? `${part}, ${name}` : `${part}`
})

// ── My Work Today queues (unchanged logic — restyled to stat cards) ──
const visibleQueues = computed(() => queueVisible())

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

// ── Primary create CTA + overflow (folds in the old Quick Create list) ──
const QUICK_CREATE = ["Lot", "Work Order", "Delivery Challan"]
const quickCreates = computed(() =>
	QUICK_CREATE.filter((dt) => canCreate(dt))
		.map((dt) => {
			const reg = getRegistryByDoctype(dt)
			return { doctype: dt, label: dt, icon: reg?.icon || "pi pi-plus", route: reg?.route || "" }
		})
		.filter((qc) => qc.route)
)
const primaryCreate = computed(() => quickCreates.value[0] || null)
const moreCreates = computed(() => quickCreates.value.slice(1))
const moreOpen = ref(false)
// Close the overflow menu on any route change (cheap insurance).
watch(() => route.fullPath, () => { moreOpen.value = false })

function goCreate(qc) {
	moreOpen.value = false
	router.push(`/${qc.route}/new`)
}

// ── Recent records (tabbed; key submittable doctypes so docstatus is meaningful) ──
const RECENT = ["Work Order", "Delivery Challan", "Goods Received Note", "Stock Entry"]
const recentTabs = computed(() =>
	// Gate on isSubmittable so the docstatus badge can never silently mislabel a
	// non-submittable doctype as "Draft" if RECENT is edited later.
	RECENT.filter((dt) => canRead(dt) && getRegistryByDoctype(dt)?.isSubmittable)
		.map((dt) => ({ doctype: dt, label: dt, route: getRegistryByDoctype(dt)?.route || "" }))
		.filter((t) => t.route)
)
const activeTab = ref("")
const recentRows = ref([])
const recentLoading = ref(false)

async function selectTab(dt) {
	activeTab.value = dt
	recentLoading.value = true
	recentRows.value = []
	try {
		const res = await getList(dt, {
			fields: ["name", "docstatus", "modified"],
			order_by: "modified desc",
			limit_page_length: 6,
		})
		recentRows.value = res.data || []
	} catch (e) {
		recentRows.value = []
	} finally {
		recentLoading.value = false
	}
}

function activeRoute() {
	return recentTabs.value.find((t) => t.doctype === activeTab.value)?.route || ""
}

function recordPath(name) {
	const r = activeRoute()
	return r ? `/${r}/${encodeURIComponent(name)}` : ""
}

function openRecord(name) {
	const path = recordPath(name)
	if (path) router.push(path)
}

function viewAll() {
	const route = activeRoute()
	if (route) router.push(`/${route}`)
}

function docStatusLabel(ds) {
	return ds === 2 ? "Cancelled" : ds === 1 ? "Submitted" : "Draft"
}
function docStatusClass(ds) {
	return ds === 2 ? "is-cancelled" : ds === 1 ? "is-submitted" : "is-draft"
}
function fmtDate(s) {
	if (!s) return "—"
	const d = new Date(String(s).replace(" ", "T"))
	if (isNaN(d.getTime())) return s
	return d.toLocaleDateString(undefined, { day: "2-digit", month: "short" })
}

onMounted(() => {
	loadCounts()
	if (recentTabs.value.length) selectTab(recentTabs.value[0].doctype)
})
</script>

<style scoped>
.home {
	display: flex;
	flex-direction: column;
	max-width: 1180px;
	margin: 0 auto;
	width: 100%;
}

/* ── Header ── */
.home-head {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 16px;
	margin-bottom: 18px;
	flex-wrap: wrap;
}

.home-title {
	font-size: 20px;
	font-weight: 800;
	margin: 0;
	letter-spacing: -0.02em;
}

.home-sub {
	margin: 4px 0 0;
	font-size: 13px;
	color: var(--esd-muted);
}

.home-cta {
	position: relative;
	display: flex;
	flex-shrink: 0;
}

.cta-primary {
	display: inline-flex;
	align-items: center;
	gap: 7px;
	background: var(--esd-accent);
	color: #fff;
	border: 0;
	border-radius: var(--radius-sm);
	padding: 9px 15px;
	font-size: 13px;
	font-weight: 600;
	cursor: pointer;
	font-family: inherit;
	transition: filter 0.14s;
}
.cta-primary:hover {
	filter: brightness(1.07);
}
.home-cta.split .cta-primary {
	border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}

.cta-more {
	background: var(--esd-accent);
	color: #fff;
	border: 0;
	border-left: 1px solid rgba(255, 255, 255, 0.25);
	border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
	padding: 0 11px;
	cursor: pointer;
	font-size: 12px;
}
.cta-more:hover {
	filter: brightness(1.07);
}

.cta-backdrop {
	position: fixed;
	inset: 0;
	z-index: 40;
}
.cta-menu {
	position: absolute;
	top: calc(100% + 6px);
	right: 0;
	z-index: 41;
	min-width: 210px;
	background: var(--esd-card);
	border: 1px solid var(--esd-line);
	border-radius: var(--radius);
	box-shadow: var(--esd-shadow-pop);
	padding: 6px;
}
.cta-menu__item {
	display: flex;
	align-items: center;
	gap: 9px;
	width: 100%;
	background: transparent;
	border: 0;
	border-radius: var(--radius-sm);
	padding: 8px 10px;
	font-size: 13px;
	font-weight: 500;
	color: var(--esd-ink-2);
	cursor: pointer;
	font-family: inherit;
	text-align: left;
}
.cta-menu__item:hover {
	background: var(--esd-slate-50);
}
.cta-menu__item i {
	color: var(--esd-accent);
	font-size: 13px;
}

/* ── Stat cards ── */
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

/* ── Recent records card ── */
.recent-card {
	margin-top: 18px;
}
.recent-bar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	border-bottom: 1px solid var(--esd-line);
	padding: 0 8px 0 6px;
}
.recent-tabs {
	display: flex;
	gap: 2px;
	overflow-x: auto;
}
.recent-tab {
	padding: 11px 13px;
	font-size: 13px;
	font-weight: 600;
	color: var(--esd-muted);
	background: transparent;
	border: 0;
	border-bottom: 2px solid transparent;
	margin-bottom: -1px;
	cursor: pointer;
	font-family: inherit;
	white-space: nowrap;
}
.recent-tab.active {
	color: var(--esd-accent-700);
	border-bottom-color: var(--esd-accent);
}
.recent-viewall {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	background: transparent;
	border: 0;
	color: var(--esd-accent-700);
	font-size: 12.5px;
	font-weight: 600;
	cursor: pointer;
	font-family: inherit;
	white-space: nowrap;
	flex-shrink: 0;
}
.recent-viewall i {
	font-size: 11px;
}
.recent-viewall:hover {
	text-decoration: underline;
}

.recent-scroll {
	overflow-x: auto;
}
.recent-table {
	width: 100%;
	border-collapse: collapse;
	font-size: 13px;
}
.recent-table th {
	text-align: left;
	padding: 9px 16px;
	font-size: 11px;
	text-transform: uppercase;
	letter-spacing: 0.04em;
	color: var(--esd-muted);
	font-weight: 700;
	border-bottom: 1px solid var(--esd-line);
}
.recent-table td {
	padding: 10px 16px;
	border-bottom: 1px solid var(--esd-line);
}
.recent-table tbody tr:last-child td {
	border-bottom: 0;
}
.recent-table tbody tr:not(.recent-skel-row) {
	cursor: pointer;
	transition: background 0.12s;
}
.recent-table tbody tr:not(.recent-skel-row):hover {
	background: var(--esd-slate-50);
}
.recent-code {
	font-weight: 600;
	color: var(--esd-accent-700);
}
.recent-date {
	color: var(--esd-muted);
}
.recent-empty {
	text-align: center;
	color: var(--esd-muted);
	padding: 26px;
}

.badge {
	display: inline-flex;
	align-items: center;
	font-size: 11.5px;
	font-weight: 700;
	padding: 3px 9px;
	border-radius: 999px;
}
.badge.is-submitted {
	color: var(--esd-success);
	background: var(--esd-success-50);
}
.badge.is-draft {
	color: var(--esd-muted);
	background: var(--esd-slate-50);
}
.badge.is-cancelled {
	color: var(--esd-danger);
	background: var(--esd-danger-50);
}

.recent-skel {
	height: 12px;
	border-radius: 6px;
	background: linear-gradient(90deg, var(--esd-slate-50), var(--esd-line), var(--esd-slate-50));
	background-size: 200% 100%;
	animation: recent-shimmer 1.2s infinite;
}
@keyframes recent-shimmer {
	from {
		background-position: 200% 0;
	}
	to {
		background-position: -200% 0;
	}
}

@media (max-width: 768px) {
	.home-cta {
		width: 100%;
	}
	.cta-primary {
		flex: 1;
		justify-content: center;
	}
}
</style>
