// essdee_yrp /web — block registration (spec §6.3). The ONLY registration site.
//
// Build-time static imports executed at module load — no dynamic plugin
// loading, no config-driven imports (that would be code injection, §15).
// Imported once (side-effect) from main.js BEFORE app.mount, so every block
// type is resolvable by the time ScreenRenderer first renders.
//
// Adding a genuinely new widget = one .vue file here + one registerBlock line
// + normal git deploy; instantly addressable from every layout as
// {"type": "<name>"} (addressable ≠ placed — layouts opt in explicitly).
import { registerBlock, SummaryTiles, CalculatorPanel } from "@yrp/web-engine" // engine-shipped blocks (registration stays a host decision, §6.3)
import HomeGreeting from "./HomeGreeting.vue" // greeting hero incl. the primary-create split CTA
import HomeQueues from "./HomeQueues.vue" // "My Work Today" stat cards (wraps useHomeQueues)
import HomeRecent from "./HomeRecent.vue" // tabbed recent table (or "tiles" variant)
import HomeQuickCreate from "./HomeQuickCreate.vue" // OPTIONAL standalone card — NOT in Default
import RecordList from "./RecordList.vue" // bounded doctype list embed (table/cards/kanban)
import Composite from "./Composite.vue" // bounded primitive-tree composition (Track 1 item 1)

registerBlock("home-greeting", { component: HomeGreeting, label: "Greeting bar" })
registerBlock("home-queues", { component: HomeQueues, label: "Work queues" })
registerBlock("home-recent", { component: HomeRecent, label: "Recent documents" })
registerBlock("home-quick-create", { component: HomeQuickCreate, label: "Quick create" })
registerBlock("record-list", { component: RecordList, label: "Record list" })
registerBlock("summary-tiles", { component: SummaryTiles, label: "KPI summary tiles" })
registerBlock("calculator-panel", { component: CalculatorPanel, label: "Calculator" })
registerBlock("composite", { component: Composite, label: "Composite" })
