import Aura from "@primeuix/themes/aura"
import { createApp } from "vue"
import PrimeVue from "primevue/config"
import "primeicons/primeicons.css"

import App from "./App.vue"
import router from "./router/index.js"
import "./styles/main.css"
import "./styles/enterprise.css"

createApp(App)
	.use(PrimeVue, {
		theme: {
			preset: Aura,
			options: {
				darkModeSelector: false,
			},
		},
	})
	.use(router)
	.mount("#app")
