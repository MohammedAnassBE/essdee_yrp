import { createApp, watch } from "vue"
import { createPinia } from "pinia"
import PrimeVue from "primevue/config"
import ToastService from "primevue/toastservice"
import ConfirmationService from "primevue/confirmationservice"
import { installEngine, useUiConfigStore, applyTheme } from "@yrp/web-engine"

import router from "./router"
import App from "./App.vue"
import EssdeePreset from "./theme"
import { initTheme, applyMode } from "./composables/useTheme"
import { usePermissions } from "./composables/usePermissions"
import { callMethod } from "./api/client"
import { fallbackConfig } from "./config/defaultConfig"
import { getRegistryByDoctype } from "./config/doctypes"
// Registers every layout-addressable block with the engine (side-effect import,
// spec §6.3) — must run before the first ScreenRenderer render.
import "./blocks"

import "@fontsource-variable/inter"
import "primeicons/primeicons.css"
import "./assets/styles/global.css"

// Apply the persisted/OS theme BEFORE mount so the first paint is already
// correct (no light→dark flash). `.dark` on <html> drives both the --esd-*
// overrides and PrimeVue's colorScheme.dark.
initTheme()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)
app.use(PrimeVue, {
	theme: {
		preset: EssdeePreset,
		options: {
			// Dark scheme is opt-in via `.dark` on <html> (toggled by useTheme),
			// never auto-applied from the OS scheme by Aura itself.
			darkModeSelector: ".dark",
		},
	},
})
app.use(ToastService)
app.use(ConfirmationService)

// @yrp/web-engine host injection (spec §6.1): the engine's only window into
// the app — manager gate, class-only mode setter, API client, and router
// navigation for block deep-links. The engine never imports app code; these
// four services are everything it may touch.
const { isAdmin, hasRole } = usePermissions()
installEngine(app, {
	isManager: () => isAdmin.value || hasRole("System Manager"),
	applyMode,
	callMethod,
	// Block deep-links (summary-tiles ↗): { doctype, filters? } → the doctype's
	// list route with ?filters= in the triple shape DynamicListPage parses
	// (same encoding as HomeQueues' queue cards).
	goto: (target) => {
		const entry = getRegistryByDoctype(target?.doctype)
		if (!entry) {
			console.warn("[essdee-web] goto: doctype not in the /web registry", target)
			return
		}
		const filters = Array.isArray(target?.filters) && target.filters.length
			? `?filters=${encodeURIComponent(JSON.stringify(target.filters))}`
			: ""
		router.push(`/${entry.route}${filters}`)
	},
})

// Hydrate the UI-config store from boot (spec §8.2) — synchronous, zero extra
// round-trip: web.html sets frappe.boot before this bundle runs. A missing or
// rejected boot config leaves the compiled-in Default (= today's UI) active.
// Then apply the layout theme before first paint; the watch re-applies it on
// preview enter/exit and refresh.
const ui = useUiConfigStore(pinia)
ui.loadFromBoot(window.frappe?.boot?.ui_config, fallbackConfig)
applyTheme(ui.active.theme)
watch(() => ui.active.theme, applyTheme, { deep: true })

app.mount("#app")
