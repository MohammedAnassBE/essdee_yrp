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
import { initializeTheme } from "./utils/themePreference.js"
import "./styles/main.css"
import "./styles/enterprise.css"

initializeTheme()

const EssdeeAura = definePreset(Aura, {
	semantic: {
		primary: {
			50: "var(--erp-accent-50)",
			100: "var(--erp-accent-100)",
			200: "var(--erp-accent-200)",
			300: "var(--erp-accent-300)",
			400: "var(--erp-accent-400)",
			500: "var(--erp-accent-500)",
			600: "var(--erp-accent-600)",
			700: "var(--erp-accent-700)",
			800: "var(--erp-accent-800)",
			900: "var(--erp-accent-900)",
			950: "var(--erp-accent-950)",
		},
		colorScheme: {
			light: {
				surface: {
					0: "var(--erp-surface)",
					50: "var(--erp-bg)",
					100: "var(--erp-surface-muted)",
					200: "var(--erp-border)",
					300: "var(--erp-border-strong)",
					400: "var(--erp-neutral-400)",
					500: "var(--erp-text-muted)",
					600: "var(--erp-neutral-600)",
					700: "var(--erp-text-secondary)",
					800: "var(--erp-neutral-800)",
					900: "var(--erp-text)",
					950: "var(--erp-neutral-950)",
				},
				primary: {
					color: "var(--erp-accent)",
					contrastColor: "var(--erp-surface)",
					hoverColor: "var(--erp-accent-hover)",
					activeColor: "var(--erp-accent-700)",
				},
				highlight: {
					background: "var(--erp-accent-50)",
					focusBackground: "var(--erp-accent-100)",
					color: "var(--erp-accent-ink)",
					focusColor: "var(--erp-accent-ink)",
				},
			},
		},
	},
	components: {
		button: {
			root: {
				borderRadius: "var(--erp-control-radius)",
				paddingX: "0.85rem",
				paddingY: "0.5rem",
				label: { fontWeight: "600" },
				focusRing: { width: "2px", offset: "2px" },
			},
			colorScheme: {
				light: {
					root: {
						warn: {
							background: "var(--erp-attention)",
							hoverBackground: "var(--erp-attention-hover)",
							activeBackground: "var(--erp-attention-hover)",
							borderColor: "var(--erp-attention)",
							hoverBorderColor: "var(--erp-attention-hover)",
							activeBorderColor: "var(--erp-attention-hover)",
							color: "var(--erp-surface)",
							hoverColor: "var(--erp-surface)",
							activeColor: "var(--erp-surface)",
							focusRing: { color: "var(--erp-attention)" },
						},
						success: {
							background: "var(--erp-success)",
							hoverBackground: "color-mix(in srgb, var(--erp-success) 86%, black)",
							activeBackground: "color-mix(in srgb, var(--erp-success) 86%, black)",
							borderColor: "var(--erp-success)",
							hoverBorderColor: "color-mix(in srgb, var(--erp-success) 86%, black)",
							activeBorderColor: "color-mix(in srgb, var(--erp-success) 86%, black)",
							color: "var(--erp-surface)",
							hoverColor: "var(--erp-surface)",
							activeColor: "var(--erp-surface)",
							focusRing: { color: "var(--erp-success)" },
						},
					},
					outlined: {
						warn: {
							borderColor: "var(--erp-attention-border)",
							color: "var(--erp-attention-text)",
							hoverBackground: "var(--erp-attention-soft)",
							activeBackground: "var(--erp-attention-soft)",
						},
						success: {
							borderColor: "var(--erp-success-soft)",
							color: "var(--erp-success-text)",
							hoverBackground: "var(--erp-success-soft)",
							activeBackground: "var(--erp-success-soft)",
						},
					},
					text: {
						warn: {
							color: "var(--erp-attention-text)",
							hoverBackground: "var(--erp-attention-soft)",
							activeBackground: "var(--erp-attention-soft)",
						},
						success: {
							color: "var(--erp-success-text)",
							hoverBackground: "var(--erp-success-soft)",
							activeBackground: "var(--erp-success-soft)",
						},
					},
				},
			},
		},
		datatable: {
			headerCell: {
				padding: "0.6rem 0.875rem",
				background: "var(--erp-surface-muted)",
				color: "var(--erp-text-muted)",
				borderColor: "var(--erp-border)",
			},
			columnTitle: { fontWeight: "600" },
			bodyCell: {
				padding: "0.65rem 0.875rem",
				borderColor: "var(--erp-border-subtle)",
			},
			row: { hoverBackground: "var(--erp-surface-hover)" },
		},
		inputtext: {
			root: {
				borderRadius: "var(--erp-control-radius)",
				paddingX: "0.7rem",
				paddingY: "0.5rem",
			},
		},
		tabs: {
			tab: {
				fontWeight: "500",
				padding: "0.6rem 0.9rem",
				activeColor: "{primary.color}",
			},
			activeBar: { height: "2px", background: "{primary.color}" },
		},
		tag: {
			root: {
				fontWeight: "600",
				padding: "0.2rem 0.55rem",
				borderRadius: "999px",
			},
			colorScheme: {
				light: {
					primary: {
						background: "var(--erp-accent-soft)",
						color: "var(--erp-accent-ink)",
					},
					info: {
						background: "var(--erp-accent-soft)",
						color: "var(--erp-accent-ink)",
					},
					success: {
						background: "var(--erp-success-soft)",
						color: "var(--erp-success-text)",
					},
					warn: {
						background: "var(--erp-warning-soft)",
						color: "var(--erp-attention-text)",
					},
					danger: {
						background: "var(--erp-danger-soft)",
						color: "var(--erp-danger)",
					},
					secondary: {
						background: "var(--erp-surface-muted)",
						color: "var(--erp-text-muted)",
					},
				},
			},
		},
		dialog: {
			root: { borderRadius: "var(--erp-panel-radius)" },
			header: { padding: "1rem 1.25rem" },
			content: { padding: "0 1.25rem 1.25rem" },
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
