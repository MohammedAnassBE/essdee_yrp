import { createApp } from "vue"
import PrimeVue from "primevue/config"
import ToastService from "primevue/toastservice"
import ConfirmationService from "primevue/confirmationservice"

import router from "./router"
import App from "./App.vue"
import EssdeePreset from "./theme"
import { initTheme } from "./composables/useTheme"

import "@fontsource-variable/inter"
import "primeicons/primeicons.css"
import "./assets/styles/global.css"

// Apply the persisted/OS theme BEFORE mount so the first paint is already
// correct (no light→dark flash). `.dark` on <html> drives both the --esd-*
// overrides and PrimeVue's colorScheme.dark.
initTheme()

const app = createApp(App)

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

app.mount("#app")
