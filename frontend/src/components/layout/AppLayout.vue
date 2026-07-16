<template>
	<!-- Topbar-pill shell (layout nav.position === "topbar", 2026-07-15 Demo-7
	     skin): chrome strip + pill nav stacked over the main column; the sidebar
	     is not mounted at all. Only layouts that OPT IN via the knob get this. -->
	<div v-if="topbarNav" class="esd-shell esd-shell--topnav">
		<!-- No drawer exists in this shell (pills scroll horizontally on narrow
		     screens), so neither header gets a hamburger: ChromeBar only shows
		     one when has-drawer is passed, and AppTopbar's is switched off —
		     it was a dead control here (no toggle-drawer handler). -->
		<ChromeBar v-if="hasChrome" />
		<AppTopbar v-else :drawer-open="false" :show-hamburger="false" />
		<NavTopbar />
		<main class="esd-main esd-main--topnav">
			<router-view v-slot="{ Component }">
				<transition name="route-fade" mode="out-in">
					<component :is="Component" :key="$route.path" />
				</transition>
			</router-view>
		</main>
		<CommandPalette />
		<!-- Self-service knobs (locked 2026-07-15): shown to every user in every
		     layout; renders nothing visually different until a knob is touched. -->
		<KnobsPanel />
	</div>

	<!-- Default shell — today's sidebar + topbar grid, unchanged (parity law).
	     ChromeBar swaps in for AppTopbar only when the layout has a chrome knob. -->
	<div v-else class="esd-shell" :class="{ pinned, 'drawer-open': drawerOpen }">
		<!-- Reserves the rail's width in the grid; the real sidebar is positioned
		     absolutely over it so it can expand into a flyout without reflowing. -->
		<div class="rail-spacer" aria-hidden="true" />
		<AppSidebar
			:pinned="pinned"
			:drawer-open="drawerOpen"
			@toggle-pin="togglePin"
			@navigate="drawerOpen = false"
		/>
		<!-- Sidebar shell: whichever header renders must be able to open the
		     mobile drawer — under 768px it is the ONLY way into the nav. -->
		<ChromeBar
			v-if="hasChrome"
			has-drawer
			:drawer-open="drawerOpen"
			@toggle-drawer="drawerOpen = !drawerOpen"
		/>
		<AppTopbar v-else :drawer-open="drawerOpen" @toggle-drawer="drawerOpen = !drawerOpen" />
		<main class="esd-main">
			<!-- Key by path so each DocType/record gets a fresh instance — the
			     dynamic views capture their doctype at setup (useDoc/useDocList),
			     so reusing the instance across routes would load stale data. -->
			<router-view v-slot="{ Component }">
				<transition name="route-fade" mode="out-in">
					<component :is="Component" :key="$route.path" />
				</transition>
			</router-view>
		</main>
		<!-- Mobile drawer scrim (closes the drawer on tap). -->
		<div class="esd-scrim" @click="drawerOpen = false" />
		<CommandPalette />
		<KnobsPanel />
	</div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue"
import { useUiConfigStore, KnobsPanel } from "@yrp/web-engine"
import AppSidebar from "./AppSidebar.vue"
import AppTopbar from "./AppTopbar.vue"
import ChromeBar from "./ChromeBar.vue"
import NavTopbar from "./NavTopbar.vue"
import CommandPalette from "@/components/CommandPalette.vue"
import { useAuth } from "@/composables/useAuth"

// Layout-driven shell knobs (2026-07-15). Both default OFF: a layout without
// them — the Default — renders today's DOM exactly (parity law). Reactive to
// the store so View-as / Refresh UI reshapes the shell live.
const ui = useUiConfigStore()
const hasChrome = computed(() => {
	const c = ui.active.chrome
	return c !== null && typeof c === "object" && !Array.isArray(c)
})
const topbarNav = computed(() => ui.active.nav?.position === "topbar")

// Rail is slim by default (hover to expand); "pin" keeps it expanded and pushes
// content. Persisted per-browser so a user's preference survives reloads.
// localStorage can throw (Safari private mode, sandboxed iframe) — never let that
// crash the shell mount; persistence just degrades to per-session.
const PIN_KEY = "essdee.sidebar.pinned"
function readPinned() {
	try {
		return localStorage.getItem(PIN_KEY) === "1"
	} catch {
		return false
	}
}
function writePinned(v) {
	try {
		localStorage.setItem(PIN_KEY, v ? "1" : "0")
	} catch {
		/* non-fatal — persistence degrades to this session only */
	}
}

const pinned = ref(readPinned())
const drawerOpen = ref(false)

function togglePin() {
	pinned.value = !pinned.value
	writePinned(pinned.value)
}

// Esc closes the mobile drawer.
function onKeydown(e) {
	if (e.key === "Escape" && drawerOpen.value) drawerOpen.value = false
}

const { checkAuth } = useAuth()
onMounted(() => {
	checkAuth()
	document.addEventListener("keydown", onKeydown)
})
onBeforeUnmount(() => document.removeEventListener("keydown", onKeydown))
</script>

<style scoped>
.esd-shell {
	position: relative;
	display: grid;
	grid-template-columns: var(--rail-w) 1fr;
	grid-template-rows: var(--topbar-height) 1fr;
	grid-template-areas:
		"rail topbar"
		"rail main";
	height: 100vh;
	--rail-w: var(--sidebar-collapsed-width);
}

/* Topbar-pill shell (opt-in): simple column — chrome strip, pill row, main. */
.esd-shell--topnav {
	display: flex;
	flex-direction: column;
}
.esd-main--topnav {
	flex: 1;
	min-height: 0;
}

/* Pinned → grid reserves the full sidebar width; content is pushed (no overlay). */
.esd-shell.pinned {
	--rail-w: var(--sidebar-width);
}

/* Sidebar shell only: shift the engine's Knobs FAB right of the rail so it
   never covers the rail-footer collapse chevron (pin button). Rides --rail-w,
   so it also clears the pinned full-width sidebar and collapses back to the
   demo 18px on mobile (--rail-w: 0px). The topbar shell has no rail and keeps
   the engine's default position (matches the Demo 7 skin). */
.esd-shell:not(.esd-shell--topnav) {
	--yrp-knobs-left: calc(var(--rail-w) + 18px);
}

.rail-spacer {
	grid-area: rail;
}

.esd-main {
	grid-area: main;
	overflow-y: auto;
	padding: 22px 28px 60px;
	background: var(--esd-bg);
}

/* Scrim only exists on mobile when the drawer is open. */
.esd-scrim {
	display: none;
}

@media (max-width: 768px) {
	.esd-shell {
		grid-template-columns: 1fr;
		grid-template-areas:
			"topbar"
			"main";
		--rail-w: 0px;
	}
	.rail-spacer {
		display: none;
	}
	.esd-shell.drawer-open .esd-scrim {
		display: block;
		position: fixed;
		inset: 0;
		background: rgb(var(--c-ink) / 0.42);
		z-index: 25;
	}
}

/* Subtle cross-fade between routes so navigation feels smooth, not a hard cut.
   Short + opacity-only so it never delays interaction. */
.route-fade-enter-active,
.route-fade-leave-active {
	transition: opacity 0.15s ease;
}
.route-fade-enter-from,
.route-fade-leave-to {
	opacity: 0;
}
</style>
