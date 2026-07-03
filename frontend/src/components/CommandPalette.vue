<template>
	<Dialog
		:visible="open"
		modal
		position="top"
		:showHeader="false"
		:dismissableMask="true"
		:draggable="false"
		class="cmdk-dialog"
		@update:visible="(v) => { if (!v) closePalette() }"
		@show="onShow"
	>
		<div class="cmdk">
			<div class="cmdk-search">
				<i class="pi pi-search cmdk-search__icon" />
				<input
					ref="inputEl"
					v-model="query"
					type="text"
					class="cmdk-input"
					placeholder="Search documents and actions…"
					spellcheck="false"
					autocomplete="off"
					@keydown.down.prevent="move(1)"
					@keydown.up.prevent="move(-1)"
					@keydown.enter.prevent="runActive"
					@keydown.esc.prevent="closePalette"
				/>
			</div>

			<ul v-if="results.length" ref="listEl" class="cmdk-list">
				<li
					v-for="(r, i) in results"
					:key="r.id"
					class="cmdk-item"
					:class="{ active: i === activeIndex }"
					@mouseenter="activeIndex = i"
					@click="run(r)"
				>
					<i class="cmdk-item__icon" :class="r.icon" />
					<span class="cmdk-item__label">{{ r.label }}</span>
					<span class="cmdk-item__sub">{{ r.sub }}</span>
					<span v-if="i === activeIndex" class="cmdk-item__enter">↵</span>
				</li>
			</ul>
			<div v-else class="cmdk-empty">
				<i class="pi pi-inbox" />
				<span>No matches for “{{ query }}”.</span>
			</div>

			<div class="cmdk-foot">
				<span><b>↑↓</b> navigate</span>
				<span><b>↵</b> open</span>
				<span><b>esc</b> close</span>
			</div>
		</div>
	</Dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from "vue"
import { useRouter } from "vue-router"
import Dialog from "primevue/dialog"
import { DOCTYPES } from "@/config/doctypes"
import { usePermissions } from "@/composables/usePermissions"
import { useTheme } from "@/composables/useTheme"
import { useCommandPalette } from "@/composables/useCommandPalette"

const router = useRouter()
const { canRead, canCreate } = usePermissions()
const { isDark, toggleTheme } = useTheme()
const { open, openPalette, closePalette, togglePalette } = useCommandPalette()

const query = ref("")
const activeIndex = ref(0)
const inputEl = ref(null)
const listEl = ref(null)

// Command pool: Home + every readable DocType (open list) + every creatable
// DocType (new) + the theme toggle. Permission-gated, so users only see what
// they can reach.
const pool = computed(() => {
	const out = [
		{ id: "nav:home", label: "Home", sub: "Dashboard", icon: "pi pi-th-large", keywords: "home dashboard", run: () => router.push("/home") },
	]
	for (const d of DOCTYPES) {
		if (canRead(d.doctype))
			out.push({ id: "list:" + d.route, label: d.label, sub: "Open list", icon: d.icon, keywords: d.label + " " + d.group, run: () => router.push("/" + d.route) })
		if (canCreate(d.doctype))
			out.push({ id: "new:" + d.route, label: "New " + d.label, sub: "Create", icon: "pi pi-plus", keywords: "new create add " + d.label, run: () => router.push("/" + d.route + "/new") })
	}
	out.push({
		id: "act:theme",
		label: isDark.value ? "Switch to light theme" : "Switch to dark theme",
		sub: "Appearance",
		icon: isDark.value ? "pi pi-sun" : "pi pi-moon",
		keywords: "theme dark light mode appearance",
		run: () => toggleTheme(),
	})
	return out
})

const results = computed(() => {
	const q = query.value.trim().toLowerCase()
	if (!q) {
		// Empty query: Home + list shortcuts + theme (no "New …" spam), capped.
		return pool.value
			.filter((c) => c.id === "nav:home" || c.id.startsWith("list:") || c.id === "act:theme")
			.slice(0, 9)
	}
	const scored = []
	for (const c of pool.value) {
		const hay = (c.label + " " + c.keywords).toLowerCase()
		const idx = hay.indexOf(q)
		if (idx === -1) continue
		const labelStarts = c.label.toLowerCase().startsWith(q) ? 0 : 1
		scored.push({ c, score: labelStarts * 1000 + idx })
	}
	scored.sort((a, b) => a.score - b.score)
	return scored.slice(0, 10).map((s) => s.c)
})

watch([query, results], () => {
	if (activeIndex.value >= results.value.length) activeIndex.value = 0
})

function move(delta) {
	const n = results.value.length
	if (!n) return
	activeIndex.value = (activeIndex.value + delta + n) % n
	nextTick(() => {
		const el = listEl.value && listEl.value.children[activeIndex.value]
		if (el) el.scrollIntoView({ block: "nearest" })
	})
}
function run(r) {
	closePalette()
	r.run()
}
function runActive() {
	const r = results.value[activeIndex.value]
	if (r) run(r)
}
function onShow() {
	query.value = ""
	activeIndex.value = 0
	nextTick(() => inputEl.value && inputEl.value.focus())
}

// Global ⌘K / Ctrl+K toggle. Mounted once (AppLayout), so one listener app-wide.
function onKeydown(e) {
	if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
		e.preventDefault()
		togglePalette()
	}
}
onMounted(() => window.addEventListener("keydown", onKeydown))
onUnmounted(() => window.removeEventListener("keydown", onKeydown))
</script>

<style scoped>
.cmdk {
	width: min(92vw, 560px);
	display: flex;
	flex-direction: column;
}
.cmdk-search {
	display: flex;
	align-items: center;
	gap: var(--space-3);
	padding: 4px 4px 12px;
	border-bottom: 1px solid var(--esd-line);
}
.cmdk-search__icon {
	color: var(--esd-muted-2);
	font-size: var(--fs-lg);
}
.cmdk-input {
	flex: 1;
	border: none;
	outline: none;
	background: transparent;
	color: var(--esd-ink);
	font-size: var(--fs-lg);
	font-family: inherit;
}
.cmdk-input::placeholder {
	color: var(--esd-muted-2);
}
.cmdk-list {
	list-style: none;
	margin: 0;
	padding: 8px 0 0;
	max-height: 52vh;
	overflow-y: auto;
}
.cmdk-item {
	display: flex;
	align-items: center;
	gap: var(--space-3);
	padding: 9px 10px;
	border-radius: var(--radius-sm);
	cursor: pointer;
}
.cmdk-item.active {
	background: var(--esd-accent-50);
}
.cmdk-item__icon {
	color: var(--esd-accent-700);
	font-size: var(--fs-base);
	width: 18px;
	text-align: center;
	flex: 0 0 auto;
}
.cmdk-item__label {
	color: var(--esd-ink);
	font-size: var(--fs-base);
	font-weight: 500;
}
.cmdk-item__sub {
	margin-left: auto;
	color: var(--esd-muted-2);
	font-size: var(--fs-xs);
}
.cmdk-item.active .cmdk-item__sub {
	color: var(--esd-accent-700);
}
.cmdk-item__enter {
	color: var(--esd-accent-700);
	font-size: var(--fs-sm);
	margin-left: var(--space-2);
}
.cmdk-empty {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: var(--space-2);
	padding: 28px 16px;
	color: var(--esd-muted);
	font-size: var(--fs-sm);
}
.cmdk-empty .pi {
	font-size: 22px;
	color: var(--esd-muted-2);
}
.cmdk-foot {
	display: flex;
	gap: var(--space-4);
	padding: 10px 4px 2px;
	margin-top: 6px;
	border-top: 1px solid var(--esd-line);
	color: var(--esd-muted-2);
	font-size: var(--fs-2xs);
}
.cmdk-foot b {
	color: var(--esd-muted);
	font-weight: 700;
}
</style>
