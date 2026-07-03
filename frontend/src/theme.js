/**
 * Essdee YRP PrimeVue preset — teal identity / cool slate surfaces.
 *
 * Built on Aura. The `primary` ramp is the Bright Workshop teal anchored on
 * #0D9488 (--esd-accent), so every Button CTA, status Tag, and highlight
 * inherits the teal identity. Surfaces are the cool slate ramp (#F6F8FA page
 * + white cards) — no warm/cream tints. Components (Button, DataTable, Tabs,
 * Paginator…) inherit these tokens automatically.
 */
import { definePreset } from "@primeuix/themes"
import Aura from "@primeuix/themes/aura"

const EssdeePreset = definePreset(Aura, {
	semantic: {
		// Bright Workshop teal primary ramp, anchored on #0D9488.
		primary: {
			50:  "#E7F3F1",
			100: "#D5EBE7",
			200: "#ABDCD3",
			300: "#6FC5B8",
			400: "#35A899",
			500: "#0E8C7F",   // --esd-accent
			600: "#0C7A6F",   // --esd-accent-600
			700: "#0A5F58",   // --esd-accent-700
			800: "#0A4F4A",
			900: "#0B413D",
			950: "#04302C",
		},
		// Pin form-field / content / overlay surfaces to the --esd-* tokens so
		// they flip correctly in dark. Aura's defaults reference high surface
		// levels that our chrome-oriented dark ramp renders LIGHT → white inputs,
		// cards, and dropdown/menu panels in dark. var() resolves per scheme, so
		// this is correct in both light and dark.
		formField: { background: "var(--esd-card)", color: "var(--esd-ink)" },
		content: { background: "var(--esd-card)", color: "var(--esd-ink)" },
		overlay: {
			select: { background: "var(--esd-card)", color: "var(--esd-ink)" },
			popover: { background: "var(--esd-card)", color: "var(--esd-ink)" },
			modal: { background: "var(--esd-card)", color: "var(--esd-ink)" },
		},
		list: { option: { color: "var(--esd-ink)", focusBackground: "var(--esd-slate-50)" } },
		colorScheme: {
			light: {
				primary: {
					color: "#0E8C7F",
					inverseColor: "#ffffff",
					hoverColor: "#0C7A6F",
					activeColor: "#0A5F58",
				},
				highlight: {
					background: "#E7F3F1",
					focusBackground: "#D5EBE7",
					color: "#0A5F58",
					focusColor: "#0A5F58",
				},
				// Cool slate surfaces (Bright Workshop) — no warm/cream tints.
				surface: {
					0:   "#ffffff",
					50:  "#F2F6F4",   // --esd-bg
					100: "#E9EFEC",   // --esd-slate-50
					200: "#DFE8E4",   // --esd-line
					300: "#C8D4CF",
					400: "#98A5A0",   // --esd-muted-2
					500: "#5F6E68",   // --esd-muted
					600: "#57655F",
					700: "#45524C",
					800: "#33413B",   // --esd-ink-2
					900: "#1B2620",
					950: "#0F1613",   // --esd-ink
				},
			},
			// Dark Bright Workshop — activated by `.dark` on <html> (darkModeSelector).
			// Brighter teal primary for contrast; deep cool-slate surfaces (0 = card
			// ground, low numbers = backgrounds, high numbers = light text).
			dark: {
				primary: {
					color: "#2FB8A6",        // brighter teal reads on dark
					inverseColor: "#04241F",
					hoverColor: "#5ACCBC",
					activeColor: "#9ADFD3",
				},
				highlight: {
					background: "rgba(47, 184, 166, 0.16)",
					focusBackground: "rgba(47, 184, 166, 0.24)",
					color: "#5ACCBC",
					focusColor: "#9ADFD3",
				},
				surface: {
					0:   "#17211C",   // component ground (cards, table, dialog)
					50:  "#1E2B25",   // row hover
					100: "#223129",   // header band / secondary surface
					200: "#2A3A33",   // borders / lines
					300: "#3A4C44",   // toggle OFF-track
					400: "#5F6E68",
					500: "#8C9A93",   // muted text
					600: "#A5B2AB",
					700: "#C0CDC7",
					800: "#D9E3DE",
					900: "#E9F1ED",
					950: "#F4F9F6",   // brightest text
				},
			},
		},
	},
	components: {
		button: {
			root: { borderRadius: "var(--radius-sm)" },
			paddingX: "0.85rem",
			paddingY: "0.5rem",
			sm: { paddingX: "0.7rem", paddingY: "0.4rem", fontSize: "0.8125rem" },
			label: { fontWeight: "600" },
			// Token refs so the focus ring tracks the active scheme's primary.
			focusRing: { width: "2px", style: "solid", color: "{primary.color}", offset: "2px" },
		},
		datatable: {
			headerCell: {
				padding: "0.6rem 0.875rem",
				background: "{surface.100}",            // slate header band (light) / dark band (dark)
				color: "{surface.500}",
				borderColor: "{surface.200}",
				fontWeight: "600",
			},
			bodyCell: { padding: "0.65rem 0.875rem", borderColor: "{surface.200}" },
			row: { hoverBackground: "{surface.50}" },
		},
		inputtext: {
			borderRadius: "var(--radius-sm)",
			paddingX: "0.7rem", paddingY: "0.5rem",
			background: "var(--esd-card)",
			color: "var(--esd-ink)",
			borderColor: "{surface.200}",
			focusBorderColor: "var(--esd-accent2)",
		},
		select: {
			borderRadius: "var(--radius-sm)",
			background: "var(--esd-card)",
			color: "var(--esd-ink)",
			borderColor: "{surface.200}",
			focusBorderColor: "var(--esd-accent2)",
			overlay: { background: "var(--esd-card)", color: "var(--esd-ink)", borderColor: "{surface.200}" },
			option: { color: "var(--esd-ink)", focusBackground: "var(--esd-slate-50)" },
		},
		datepicker: {
			borderRadius: "var(--radius-sm)",
			panel: { background: "var(--esd-card)", borderColor: "{surface.200}" },
		},
		inputnumber:  { borderRadius: "var(--radius-sm)" },
		textarea: {
			borderRadius: "var(--radius-sm)",
			background: "var(--esd-card)",
			color: "var(--esd-ink)",
			borderColor: "{surface.200}",
			focusBorderColor: "var(--esd-accent2)",
		},
		autocomplete: {
			overlay: { background: "var(--esd-card)", color: "var(--esd-ink)", borderColor: "{surface.200}" },
			option: { color: "var(--esd-ink)", focusBackground: "var(--esd-slate-50)" },
		},
		multiselect: {
			background: "var(--esd-card)",
			borderColor: "{surface.200}",
			overlay: { background: "var(--esd-card)", color: "var(--esd-ink)", borderColor: "{surface.200}" },
		},
		menu: {
			background: "var(--esd-card)",
			color: "var(--esd-ink)",
			borderColor: "{surface.200}",
		},
		popover: { background: "var(--esd-card)", color: "var(--esd-ink)", borderColor: "{surface.200}" },
		toggleswitch: {
			checkedBackground: "{primary.color}",
			checkedHoverBackground: "{primary.hoverColor}",
			background: "{surface.300}",                 // cool grey OFF-track, adapts per scheme
		},
		tabs: {
			tab: {
				fontWeight: "500",
				activeColor: "{primary.color}",
				color: "{surface.500}",
				padding: "0.6rem 0.9rem",
			},
			activeBar: { height: "2px", background: "{primary.color}" },
		},
		tag: {
			fontWeight: "600",
			padding: "0.2rem 0.55rem",
			borderRadius: "999px",
			// Status/teal tints use --esd-* vars (overridden under .dark in global.css).
			primary:   { background: "var(--esd-accent-50)", color: "var(--esd-accent-ink)" },
			info:      { background: "var(--esd-accent-50)", color: "var(--esd-accent-ink)" },
			success:   { background: "var(--esd-success-50)", color: "var(--esd-success)" },
			warn:      { background: "var(--esd-warn-50)",    color: "var(--esd-warn)" },
			danger:    { background: "var(--esd-danger-50)",  color: "var(--esd-danger)" },
			secondary: { background: "{surface.100}", color: "{surface.500}" },
		},
		dialog: {
			borderRadius: "var(--radius)",
			headerPadding: "1rem 1.25rem",
			contentPadding: "0 1.25rem 1.25rem",
		},
		// Pin Card surface to the --esd-card token (white light / #0F1A2A dark).
		// Aura's default dark Card bg references {surface.900}, which is light in
		// our ramp (we orient low=dark for the other component overrides) — that
		// made side-card values light-on-light in dark. Token flips per scheme.
		card: {
			root: { background: "var(--esd-card)", color: "var(--esd-ink)", borderRadius: "var(--radius)" },
			body: { padding: "0" },
		},
		paginator: { padding: "0.5rem 0.75rem" },
	},
})

export default EssdeePreset
