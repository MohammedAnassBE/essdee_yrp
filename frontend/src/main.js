import Aura from "@primeuix/themes/aura"
import { definePreset } from "@primeuix/themes"
import { createApp } from "vue"
import ConfirmationService from "primevue/confirmationservice"
import PrimeVue from "primevue/config"
import ToastService from "primevue/toastservice"
import "@fontsource-variable/inter"
import "primeicons/primeicons.css"

import App from "./App.vue"
import router from "./router/index.js"
import "./styles/main.css"
import "./styles/enterprise.css"

const EssdeeAura = definePreset(Aura, {
	semantic: {
		primary: {
			50: "#ecfdf5",
			100: "#d1fae5",
			200: "#a7f3d0",
			300: "#6ee7b7",
			400: "#34d399",
			500: "#10b981",
			600: "#059669",
			700: "#047857",
			800: "#065f46",
			900: "#064e3b",
			950: "#022c22",
		},
		colorScheme: {
			light: {
				surface: {
					0: "#ffffff",
					50: "#fbfcfd",
					100: "#f7f8fa",
					200: "#eaecf0",
					300: "#dfe3e8",
					400: "#98a2b3",
					500: "#667085",
					600: "#475467",
					700: "#344054",
					800: "#1d2939",
					900: "#101828",
					950: "#0c111d",
				},
			},
		},
	},
})

createApp(App)
	.use(PrimeVue, {
		theme: {
			preset: EssdeeAura,
			options: {
				darkModeSelector: false,
			},
		},
		pt: {
			dialog: {
				pcMaximizeButton: ({ state }) => {
					const label = state.maximized ? "Restore dialog" : "Maximize dialog"
					return { root: { "aria-label": label, title: label } }
				},
			},
		},
	})
	.use(ToastService)
	.use(ConfirmationService)
	.use(router)
	.mount("#app")
