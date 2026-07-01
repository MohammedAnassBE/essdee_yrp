# SD YRP — Session Status & Monday Handoff

- **Date:** 2026-06-27 (Sat)
- **Resume:** Monday 2026-06-29
- **Owner:** Mohammed Anas (anas@essdee.fit)
- **One-line state:** App + site + full sync implementation are **DONE**; the only thing left is the **live Kafka round-trip test**, which is **not yet run** (consumer config write was blocked pending explicit approval for touching the production broker).

---

## 1. What this work is

A one-way **master-data sync**: `production_api` (Frappe-15 bench, site `mrp3.site`) → `essdee_yrp.site` (Frappe-16 bench), over **Kafka/Spine** on a **dedicated topic `sd_yrp_master`**, isolated from the existing ERP sync. Full spec: `apps/essdee_yrp/docs/sd_yrp_sync_plan.md`.

`essdee_yrp` is a new company-specific customization app on base `yrp` (sibling of `mgk_clothing_yrp` / `yrp_essdee`).

---

## 2. Infra done this session ✅

| Item | Result |
|---|---|
| App `essdee_yrp` | created, `uv pip install -e`, built, branch `develop` |
| GitHub repo | **https://github.com/MohammedAnassBE/essdee_yrp** (public, default branch `develop`) |
| Site `essdee_yrp.site` | created = **frappe + yrp + essdee_yrp**; `/etc/hosts` mapped (v4+v6); serves on **:8003**; Desk loads as Administrator |

---

## 3. sd_yrp sync — implementation status ✅ (mostly built by the peer agent)

Verified by a read-only audit **and** a manual ground-truth re-read (the audit was racing the peer's live edits, so trust the re-read).

**F16 consumer** — `apps/essdee_yrp/essdee_yrp/sd_yrp_sync.py` (**865 lines**), structurally complete & correct:
- `SYNC_DOCTYPES = EXACT_MATCH_DOCTYPES + CUSTOM_MAPPER_DOCTYPES`
- `HANDLER_PATH = "essdee_yrp.sd_yrp_sync.handle_sd_yrp_message"` (entry point + `handle_exact_match` wrapper)
- helpers present: `replace_child_table`, `get_item_default_uom`, `validate_required_link`
- all custom mappers: `upsert_item / lot_template / item_production_detail / production_order / lot` (+ child mappers, warehouse sync, `strip_lot_time_and_action_fields`)
- delete handler is **link-safe** (User/Supplier → disable; others `try`-wrapped, retryable) — **no `force=True`**

**F16 schema** — 16 replicated doctypes (Lot family stripped of Time/Action, packing/cutting/stitching IPD children, `product_category`, `product_season`); `hooks.py` (`required_apps=["yrp"]` + IPD `doc_events` onload/validate/on_update/on_trash); `fixtures/custom_field.json`; 6 patches — **all 6 patches ran on the site**.

**Consumer mappings** — **26 `Spine Consumer Handler Mapping` rows** created for topic `sd_yrp_master` (one per scoped DocType). `ensure_consumer_config()` ran.

**Base-yrp §5 changes** — `item.json` (+`over_delivery_receipt_allowance`, `price_section`, `price_html`), `process_detail` → `process_details` child rename (+ base patch), `production_term_details` mandatory relaxed. **Done AND migrated into the site DB** — but ⚠️ **uncommitted in the shared `apps/yrp` working tree** (see Open Decisions).

**F15 producer** — `/home/anas/frappe-15/apps/production_api/production_api/sd_yrp_sync.py` (**240 lines**): `SD_YRP_TOPIC`, `SD_YRP_INITIAL_SYNC_ORDER`, runtime handlers, `trigger_all/ordered_initial_sync`, `publish_sd_yrp_event` (target_topic), Lot strip. Hooks wired in `production_api/hooks.py` (7 events, no validation hooks).

---

## 4. Runtime status — ❌ NOT TESTED YET (this is Monday's work)

| Piece | State |
|---|---|
| Kafka broker | ✅ running at **`localhost:29092`** (shared with F15 ERP sync) |
| `essdee_yrp.site` kafka config | ❌ **MISSING** — the `set-config` write was **blocked by the auto-mode safety classifier** (touches the production broker; needs explicit approval) |
| Consumer workers (`eventdispatcher` + `jsonworker`) | ❌ not started (not in this bench's Procfile) |
| Round-trip publish→consume→apply | ❌ never exercised |
| Baseline | `UOM` count on `essdee_yrp.site` = **0** (so any UOM appearing = success) |

**Decision already made:** run via the **user's `!` prefix** (keeps a human in control of the prod broker + F15 daily-driver). Source site = **`mrp3.site`**.

---

## 5. Monday runbook (run each with `!`)

**① F16 — set consumer config** (isolated group/topic; `latest` keeps the first test controlled):
```
bench --site essdee_yrp.site set-config -p kafka '{"auto.offset.reset":"latest","bootstrap.servers":"localhost:29092","client.id":"sd_yrp.prod","consumer.min.commit.count":1,"default.topic.config":{"acks":"all"},"fetch.message.max.bytes":"81920","group.id":"spine-client-sd-yrp-production","request.required.acks":"1"}'
```

**② F16 — start the two consumer workers** (background + logs):
```
cd /home/anas/frappe-16 && nohup bench --site essdee_yrp.site eventdispatcher --queue kafka_events > /tmp/sdyrp-dispatcher.log 2>&1 & nohup bench --site essdee_yrp.site jsonworker --queue kafka_events > /tmp/sdyrp-worker.log 2>&1 & sleep 8 && tail -n 20 /tmp/sdyrp-dispatcher.log
```
Expect: dispatcher connects to broker / subscribes to `sd_yrp_master`, no Traceback.

**③ F15 — publish a controlled UOM batch** (daily-driver `mrp3.site`):
```
cd /home/anas/frappe-15 && bench --site mrp3.site execute production_api.sd_yrp_sync.trigger_initial_sync --kwargs "{'doctype':'UOM'}"
```

**④ F16 — verify** (wait ~30–60s):
```
bench --site essdee_yrp.site console <<'PY'
print("UOM_COUNT", frappe.db.count("UOM"))
PY
```
Success = `UOM_COUNT` > 0. Then widen per plan order: Item Attribute → Item → Item Production Detail → … → Lot.

**Teardown when done:** stop the two background workers (`pkill -f "essdee_yrp.site eventdispatcher"` and `… jsonworker`) — confirm before running.

---

## 6. Open decisions / risks for Monday

1. **Base-yrp uncommitted changes** — the §5 edits sit uncommitted in shared `apps/yrp`. Decide: **commit on a feature branch** vs **move to `essdee_yrp` Custom Fields** (keeps base untouched). Contradicts the standing "never edit base yrp" note — make it a conscious call.
2. **Production offset** — the test uses `auto.offset.reset=latest`; the **real full initial sync** should use **`smallest`** (per plan §1) so nothing is missed.
3. **F15 producer is live on the daily-driver** — once active on `mrp3.site`, scoped doc-saves publish to `sd_yrp_master`. Confirm this production behavior change is acceptable (it may already be active). There may be a **backlog** already in the topic.
4. **Permanent consumer** — for real use, add `eventdispatcher` + `jsonworker` to the **Procfile / supervisor** (currently absent → consumer doesn't run automatically).
5. **Only unverified thing** is the live Kafka round-trip — everything else is code-confirmed.

---

## 7. Notes / loose ends

- **C3/Telegram:** early in the session I mis-posted a status to the `sd_yrp` Telegram topic (msg 2377) — that was a misread of "connect with your agent"; the intended channel was **inter-terminal mode** (now exited). The peer agent that authored the plan **ran out of tokens** before we connected — but it had already finished the code, so nothing is blocked on it.
- **Harness docs updated this session:** `docs/claude/apps.md` (essdee_yrp entry), `docs/claude/commands.md` (new-app/new-site reference + MariaDB unix_socket note), memory `project_essdee_yrp`.
- **Audit artifact:** full report at the workflow task output (`/tmp/claude-1000/-home-anas-frappe-16/.../tasks/wtfvhoc3s.output`) — note its headline was distorted by snapshot-lag; section 3 above is the corrected truth.
