# Essdee ERP — Bright Ledger

## Product context

Essdee ERP is a high-frequency production and stock operations interface for apparel teams. The `/web` application covers administrator and department launchers, dense lists, Work Orders, Purchase Orders, Delivery Challans, Goods Received Notes, Cutting Orders, bulk lay sheets, lay-sheet optimization, stock operations, and operational reports. Operators need rapid scanning, safe transaction entry, unambiguous document state, and low dwell time.

## Direction

Bright Ledger combines consumer-grade interaction feedback with dense B2B clarity. It is bright, calm, precise, and operational—not decorative. Instagram contributes content-neutral chrome, direct touch feedback, and simplified hierarchy. Swiggy contributes quick action discovery and restrained warm attention cues. Neither product's brand styling is copied.

## Color system

- Canvas: `#f6f7f9`; primary surface: `#ffffff`; sunken surface: `#f1f3f6`; hover: `#f7f8fa`.
- Text: `#0f1729`; secondary: `#475467`; muted: `#667085`; subtle: `#98a2b3`.
- Borders: `#eceef2`, `#e3e6eb`, `#cfd4dc`.
- Brand emerald: 50 `#ecfdf5`, 100 `#d1fae5`, 200 `#a7f3d0`, 500 `#10b981`, 600 `#059669`, 700 `#047857`, 800 `#065f46`.
- Attention saffron: `#fc8019`, reserved for pending, overdue, or action-required state—not normal CTAs.
- Semantic: success `#067647`, warning `#b54708`, danger `#d92d20`, info `#175cd3`, each paired with a pale background and quiet border.

## Typography and density

- Use a reliable modern sans stack: Inter/Geist Sans when available, then `ui-sans-serif`, system fonts. IDs and quantities use tabular numerals.
- Weights are only 400, 500, 600, and 700.
- Sizes: 11px metadata, 12px labels/headers, 13px dense body, 14px controls/body, 15px section title, 18px record title, 22px page title, 28px administrator display.
- Sentence case is default; uppercase is limited to short table/fact labels with tracking.
- Desktop density target 7/10: 32px compact controls, 36px normal controls, 40px primary actions. Mobile touch target minimum 44px.

## Geometry, elevation, and motion

- Four-point spacing scale. Radii: 6px cells/chips, 8px controls, 12px cards/menus, 16px dialogs.
- Prefer whitespace and one clean surface hierarchy over nested borders. Use hairlines only where data alignment benefits.
- Shadows: xs for controls, sm for cards, md for floating menus, lg for dialogs. Shadows are neutral, never green-tinted.
- Motion: 120ms press, 180ms state transition, 260ms sheet/dialog. Cards lift 1px; buttons compress to `.98`; routes fade/slide 8px. Respect reduced motion.

## Component rules

- One emerald primary action per decision area. Secondary actions are neutral; destructive actions stay red and require the app confirmation dialog.
- Headers separate identity, state, facts, and actions. Sticky action bars remain compact and readable.
- Lists use a quiet toolbar, persistent active-filter chips, sticky headers, keyboard-focusable rows, and a clear selection action bar.
- Forms group fields by operator sequence. Labels, help, required state, and errors share one field rhythm. Errors sit by the affected group and use `role="alert"`.
- Document workspaces use a compact record header, a main content column, and an optional 260–300px totals/activity rail. Related documents open in the existing in-app workspace, never Desk redirects.
- Tables prioritize horizontal scan lines; numeric values align right with tabular figures. Empty states are concise and action-oriented.
- Dialogs have consistent 480/720/1040/1440 widths, one scroll body, sticky footer, a busy guard, and mobile full-screen/bottom-sheet treatment.

## Protected behavior

Cutting Plan, Stock Transfers, and Reports may inherit safe color, font, focus, radius, shadow, and contrast tokens only. Their calculations, filters, events, data flows, print behavior, and document lifecycle must not change.
