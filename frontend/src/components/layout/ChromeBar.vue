<!-- ChromeBar — the Demo-7 header strip (layout `chrome` knob, spec extension
     2026-07-15). Rendered by AppLayout INSTEAD of AppTopbar when the active
     layout carries a `chrome` object; layouts without the knob never mount
     this component (parity law — the Default keeps AppTopbar untouched).

     Composition mirrors "custom ui/demos/_template.html" .strip / .chrome-*:
       left : brand dot + app title
       right: ● Live indicator (real socket state — useRealtime().connected;
              gated on the layout's realtime.enabled knob; NO "Simulate event"
              button — events here are real), "Search… ⌘K" palette trigger
              (chrome.search), REAL user first-name + primary-role chip (from
              boot — the layout's chrome.user text is ignored on purpose: a
              layout must never relabel the session user), theme toggle
              (chrome.themeToggle), and a logout button.
     Accepted deviation from the demo: logout is a REAL control (the demo only
     toasts "simulated") — a real app must keep a way out. -->
<template>
	<header class="esd-chrome">
		<div class="chrome-left">
			<!-- Mobile drawer hamburger — ONLY in the sidebar shell (hasDrawer):
			     under 768px the rail collapses to a drawer and this is the only
			     way to open it. The topnav shell has no drawer (pills scroll)
			     and never passes hasDrawer, so no dead control renders there.
			     Wired exactly like AppTopbar's hamburger. -->
			<button
				v-if="hasDrawer"
				class="chrome-hamburger"
				type="button"
				aria-label="Open navigation menu"
				:aria-expanded="drawerOpen"
				@click="$emit('toggle-drawer')"
			>
				<i class="pi pi-bars" />
			</button>
			<span class="chrome-dot" aria-hidden="true" />
			<strong class="chrome-title">Essdee YRP</strong>
		</div>

		<div class="chrome-right">
			<!-- Real realtime state: pulsing green while the socket is connected,
			     muted "Live · off" otherwise. Shown only when the layout enables
			     the realtime knob (demo semantics). -->
			<span
				v-if="realtimeEnabled"
				class="chrome-live"
				:class="{ off: !connected }"
				:title="connected ? 'Realtime connected — lists and home update live' : 'Realtime not connected'"
			>
				<i class="chrome-live__dot" />
				{{ connected ? "Live" : "Live · off" }}
			</span>

			<!-- Global search — opens the existing Ctrl/Cmd+K palette. -->
			<button
				v-if="showSearch"
				class="chrome-btn chrome-search"
				type="button"
				title="Search — Ctrl/Cmd + K"
				aria-label="Open search (Ctrl or Cmd + K)"
				@click="openPalette"
			>
				Search… <span class="chrome-kbd">⌘K</span>
			</button>

			<!-- SM-only §10 View-as trigger (renders nothing for everyone else). -->
			<ViewAsControl chrome />

			<!-- REAL session user: first name + primary role (read-only, from boot). -->
			<span class="chrome-user" :title="roleTitle">
				<span class="chrome-av">{{ initials }}</span>
				<span class="chrome-name">{{ firstName }}</span>
				<span class="chrome-role">{{ primaryRole }}</span>
			</span>

			<button
				v-if="showThemeToggle"
				class="chrome-btn"
				type="button"
				:title="isDark ? 'Light mode' : 'Dark mode'"
				:aria-label="isDark ? 'Switch to light theme' : 'Switch to dark theme'"
				@click="toggleTheme"
			>
				<i :class="isDark ? 'pi pi-sun' : 'pi pi-moon'" />
			</button>

			<button
				class="chrome-btn"
				type="button"
				title="Log out"
				aria-label="Log out"
				@click="onLogout"
			>
				<i class="pi pi-sign-out" />
			</button>
		</div>
	</header>
</template>

<script setup>
import { computed, onMounted } from "vue"
import { useUiConfigStore } from "@yrp/web-engine"
import ViewAsControl from "./ViewAsControl.vue"
import { useAuth } from "@/composables/useAuth"
import { useTheme } from "@/composables/useTheme"
import { useCommandPalette } from "@/composables/useCommandPalette"
import { useRealtime } from "@/composables/useRealtime"

// hasDrawer: the hosting shell has a mobile nav drawer to toggle (sidebar
// shell only — AppLayout passes it there and wires toggle-drawer, mirroring
// its AppTopbar wiring). The topnav shell omits it → no hamburger.
defineProps({ drawerOpen: Boolean, hasDrawer: Boolean })
defineEmits(["toggle-drawer"])

const ui = useUiConfigStore()
const { fullName, logout } = useAuth()
const { isDark, toggleTheme } = useTheme()
const { openPalette } = useCommandPalette()
const { connected, ensureConnected } = useRealtime()

const chrome = computed(() => ui.active.chrome || {})
const showSearch = computed(() => chrome.value.search !== false)
const showThemeToggle = computed(() => chrome.value.themeToggle !== false)
const realtimeEnabled = computed(() => Boolean(ui.active.realtime?.enabled))

// Connect eagerly so the Live indicator is truthful even on screens that have
// no realtime subscription of their own yet (the socket is shared/singleton).
onMounted(() => {
	if (realtimeEnabled.value) ensureConnected()
})

// Real user identity from the session (same source as AppTopbar).
const bootUser = window.frappe?.boot?.user || {}
const roles = Array.isArray(bootUser.roles) ? bootUser.roles : []
const ROLE_PRIORITY = [
	"System Manager",
	"Production Manager",
	"Purchase Manager",
	"Stock Manager",
]
const primaryRole = computed(() => {
	for (const r of ROLE_PRIORITY) {
		if (roles.includes(r)) return r
	}
	return roles[0] || "User"
})
const roleTitle = computed(() => `Roles: ${roles.join(", ") || "—"}`)

const firstName = computed(() => (fullName.value || "User").trim().split(/\s+/)[0])
const initials = computed(() => {
	const n = (fullName.value || "U").trim()
	const parts = n.split(/\s+/)
	return parts.length >= 2
		? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
		: n.slice(0, 2).toUpperCase()
})

async function onLogout() {
	await logout()
}
</script>

<style scoped>
/* Demo .strip, on the app's theme tokens (the layout theme recolours these). */
.esd-chrome {
	grid-area: topbar; /* sidebar-shell slot; ignored by the flex topnav shell */
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	height: 46px;
	padding: 0 16px;
	background: var(--esd-card);
	border-bottom: 1px solid var(--esd-line);
	flex: none;
	z-index: 40;
}

.chrome-left {
	display: flex;
	align-items: center;
	gap: 10px;
	min-width: 0;
}

/* Mobile-only drawer button (sidebar shell) — same pattern as AppTopbar's
   .topbar-hamburger: hidden on desktop where the rail is always visible. */
.chrome-hamburger {
	display: none;
	background: transparent;
	border: 0;
	color: var(--esd-ink-2);
	font-size: 18px;
	padding: 6px 8px;
	border-radius: 8px;
	cursor: pointer;
}
.chrome-hamburger:hover {
	background: var(--esd-slate-50);
}
@media (max-width: 768px) {
	.chrome-hamburger {
		display: inline-flex;
		align-items: center;
	}
}
.chrome-dot {
	width: 10px;
	height: 10px;
	border-radius: 3px;
	background: var(--esd-accent);
	flex: none;
}
.chrome-title {
	font-size: 14px;
	font-weight: 700;
	letter-spacing: -0.01em;
	white-space: nowrap;
	color: var(--esd-ink);
}

.chrome-right {
	display: flex;
	align-items: center;
	min-width: 0;
}

/* ● Live — demo .live-ind, real socket state. */
.chrome-live {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	margin-right: 12px;
	font-size: 11px;
	font-weight: 700;
	color: #16a34a;
	white-space: nowrap;
}
.chrome-live__dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	background: #16a34a;
	flex: none;
	animation: chrome-live-pulse 1.6s ease-in-out infinite;
}
.chrome-live.off {
	color: var(--esd-muted);
}
.chrome-live.off .chrome-live__dot {
	background: var(--esd-muted);
	animation: none;
}
@keyframes chrome-live-pulse {
	0%,
	100% {
		box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.45);
	}
	50% {
		box-shadow: 0 0 0 5px rgba(22, 163, 74, 0);
	}
}

/* demo .chrome-btn */
.chrome-btn {
	background: none;
	border: 1px solid var(--esd-line);
	border-radius: 8px;
	padding: 3px 8px;
	cursor: pointer;
	margin-left: 8px;
	font-size: 12px;
	color: var(--esd-ink-2);
	font-family: inherit;
	line-height: 1.5;
	white-space: nowrap;
}
.chrome-btn:hover {
	border-color: var(--esd-accent);
}
.chrome-btn .pi {
	font-size: 12px;
	vertical-align: -1px;
}
.chrome-search {
	color: var(--esd-muted);
	font-size: 11px;
}
.chrome-kbd {
	font-weight: 700;
	color: var(--esd-muted-2);
}

/* demo .chrome-user / .chrome-av / .chrome-role */
.chrome-user {
	display: inline-flex;
	align-items: center;
	gap: 7px;
	margin-left: 12px;
	color: var(--esd-ink);
	font-weight: 600;
	flex: none;
	white-space: nowrap;
	font-size: 13px;
	user-select: none;
}
.chrome-av {
	width: 24px;
	height: 24px;
	border-radius: 50%;
	background: var(--esd-accent);
	color: #fff;
	display: inline-flex;
	align-items: center;
	justify-content: center;
	font-size: 9.5px;
	font-weight: 800;
	flex: none;
}
.chrome-role {
	font-size: 10px;
	color: var(--esd-muted);
	background: var(--esd-slate-50);
	padding: 2px 8px;
	border-radius: 999px;
	font-weight: 650;
}

@media (max-width: 768px) {
	/* Narrow screens: keep the essentials (Live, search, toggle, logout);
	   the identity chip is the first thing to give way. */
	.chrome-role,
	.chrome-name {
		display: none;
	}
	.chrome-search {
		display: none;
	}
}
</style>
