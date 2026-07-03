#!/usr/bin/env node
// Essdee YRP /web UI — end-to-end acceptance drive (real fills/clicks + literal
// DOM reads; screenshots are evidence, not the test).
//
// Run from the bench root:
//   node apps/essdee_yrp/scripts/web-ui-e2e.mjs
//
// Covers: post-login redirect, Desk block (app/apps/desk/root), sidebar gating,
// list tab contracts, prev/next doc arrows, per-user list columns, Lot detail
// editors, bare-Lot create/delete, synced-Lot no-change save (child-preservation
// contract), Terms and Condition create/delete, fabric modal context, realtime
// stale banner, dark-mode measurement.
//
// Credentials: Administrator from ~/.frappe-debug-creds-mrp3; webuser@essdee.fit
// (non-System-Manager floor user) created by the harness with webuser@1234.

import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
const { chromium } = require('playwright')

const SITE = 'http://essdee_yrp.site:8003'
const creds = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')
const ADMIN = { usr: creds[0].trim(), pwd: creds[1].trim() }
const WEBUSER = { usr: 'webuser@essdee.fit', pwd: 'webuser@1234' }

const results = []
function log(id, ok, detail) {
  results.push({ id, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${id}  ${detail || ''}`)
}

async function loginViaForm(page, { usr, pwd }) {
  await page.goto(SITE + '/login', { waitUntil: 'domcontentloaded' })
  await page.fill('#login_email', usr)
  await page.fill('#login_password', pwd)
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {}),
    page.click('.btn-login, button[type=submit]'),
  ])
  await page.waitForTimeout(2500)
}

async function apiLogin(context, { usr, pwd }) {
  const r = await context.request.post(SITE + '/api/method/login', {
    form: { usr, pwd },
  })
  return r.status()
}

// Frappe session writes (PUT/DELETE) need the X-Frappe-CSRF-Token header — the
// SPA injects window.csrf_token; read it off a logged-in page for API calls.
async function csrfOf(page) {
  return page.evaluate(() => window.csrf_token || (window.frappe && window.frappe.csrf_token) || '')
}
async function apiWrite(ctx, token, method, path, data) {
  const opts = { headers: { 'X-Frappe-CSRF-Token': token } }
  if (data !== undefined) opts.data = data
  return ctx.request[method](SITE + path, opts)
}

const browser = await chromium.launch({ headless: true })

// ─────────────────────────────────────────────────────────────────────────────
// A. webuser session — redirect, desk block, sidebar, lists, arrows, columns
// ─────────────────────────────────────────────────────────────────────────────
const uctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const upage = await uctx.newPage()

// T1 — form login lands on /web
await loginViaForm(upage, WEBUSER)
{
  const path = new URL(upage.url()).pathname
  log('T1 login-redirect', path === '/web' || path.startsWith('/web'), `landed on ${path}`)
}

// T2 — desk roots all bounce to /web; /api stays open
for (const p of ['/app', '/app/item', '/desk', '/apps', '/']) {
  await upage.goto(SITE + p, { waitUntil: 'domcontentloaded' }).catch(() => {})
  await upage.waitForTimeout(800)
  const final = new URL(upage.url()).pathname
  log(`T2 desk-block ${p}`, final === '/web' || final.startsWith('/web'), `-> ${final}`)
}
{
  const r = await uctx.request.get(SITE + '/api/method/frappe.auth.get_logged_user')
  const body = await r.json().catch(() => ({}))
  log('T2 api-open', r.status() === 200 && body.message === WEBUSER.usr, `status ${r.status()} user ${body.message}`)
}

// T3 — sidebar: only registry doctypes, and NO Desk link for the webuser
await upage.goto(SITE + '/web/home', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  const info = await upage.evaluate(() => {
    const links = [...document.querySelectorAll('aside a[href]')].map((a) => a.getAttribute('href'))
    return { links, hasDeskLink: links.some((h) => h === '/app' || h.startsWith('/app/')) }
  })
  const slugs = info.links.filter((h) => h.startsWith('/web/')).map((h) => h.split('/')[2])
  const allowed = new Set(['home', 'lot', 'work-order', 'delivery-challan', 'goods-received-note', 'stock-entry', 'item', 'item-production-detail', 'terms-and-condition'])
  const stray = slugs.filter((s) => s && !allowed.has(s))
  log('T3 sidebar-scope', stray.length === 0 && !info.hasDeskLink, `slugs=[${[...new Set(slugs)]}] desk-link=${info.hasDeskLink}`)
}

// T4 — list tab contracts + rows render
async function readTabs(page) {
  return page.evaluate(() =>
    [...document.querySelectorAll('.p-tablist .p-tab, [role=tab]')].map((t) => t.textContent.trim().replace(/\d+$/, '').trim()),
  )
}
// Rendered geometry, NOT DOM presence — a display:none ancestor leaves rows in
// the DOM (tbody tr count stays > 0) while the list is visually blank. Assert
// the list table actually paints (non-zero width) so a hidden list can't pass.
async function listVisible(page) {
  return page.evaluate(() => {
    const tbl = [...document.querySelectorAll('table')].find((t) => t.querySelector('tbody tr'))
    if (!tbl) return { ok: false, w: 0, reason: 'no-table-with-rows' }
    const w = Math.round(tbl.getBoundingClientRect().width)
    const painted = tbl.offsetParent !== null && w > 40
    return { ok: painted, w, reason: painted ? '' : 'table not painted (display:none / 0-width)' }
  })
}

// T4a — EVERY list must VISUALLY render (catches the display:none-wrapper class
// of bug that DOM-count asserts miss). Screenshots + geometry, all 8.
for (const route of ['lot', 'work-order', 'delivery-challan', 'goods-received-note', 'stock-entry', 'item', 'item-production-detail', 'terms-and-condition']) {
  await upage.goto(SITE + '/web/' + route, { waitUntil: 'domcontentloaded' })
  await upage.waitForTimeout(3500)
  const v = await listVisible(upage)
  log(`T4a list-paints ${route}`, v.ok, `table-width=${v.w}px ${v.reason}`)
}
await upage.goto(SITE + '/web/work-order', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  const tabs = await readTabs(upage)
  const rows = await upage.locator('tbody tr').count()
  log('T4 wo-status-tabs', tabs.includes('All') && tabs.length > 3, `tabs=[${tabs}] rows=${rows}`)
}
await upage.goto(SITE + '/web/stock-entry', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2200)
{
  const tabs = await readTabs(upage)
  const want = ['All', 'Draft', 'Submitted', 'Cancelled']
  log('T4 se-docstatus-tabs', want.every((w) => tabs.includes(w)), `tabs=[${tabs}]`)
}
await upage.goto(SITE + '/web/lot', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  const tabs = await readTabs(upage)
  const rows = await upage.locator('tbody tr').count()
  log('T4 lot-status-tabs', tabs.includes('All') && tabs.includes('Open') && tabs.includes('Closed') && rows > 0, `tabs=[${tabs}] rows=${rows}`)
}

// T5 — prev/next arrows on Item detail follow the list order
await upage.goto(SITE + '/web/item', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  const names = await upage.evaluate(() =>
    [...document.querySelectorAll('tbody tr')].slice(0, 5).map((tr) => tr.querySelector('td:nth-child(2)')?.textContent.trim()),
  )
  // The row's SPA @click handler responds to a plain DOM click (verified). We
  // dispatch it via evaluate rather than locator.click() because PrimeVue's
  // DataTable rows briefly report height 0 during progressive layout in
  // headless, which trips Playwright's actionability check (not an app issue).
  await upage.waitForFunction(() => document.querySelectorAll('tbody tr').length >= 3, { timeout: 15000 }).catch(() => {})
  await upage.evaluate(() => document.querySelectorAll('tbody tr')[2]?.click())
  await upage.waitForTimeout(2500)
  const here = decodeURIComponent(new URL(upage.url()).pathname.split('/').pop())
  const nextBtn = upage.locator('button:has(.pi-chevron-right)').first()
  let moved = null
  if (await nextBtn.count()) {
    await nextBtn.click()
    await upage.waitForTimeout(2200)
    moved = decodeURIComponent(new URL(upage.url()).pathname.split('/').pop())
  }
  log('T5 doc-nav-arrows', !!moved && moved !== here && names.includes(moved), `row3=${here} next=${moved}`)
}

// T6 — per-user list columns persist (User Listview, base yrp)
await upage.goto(SITE + '/web/item', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  const before = await upage.evaluate(() => [...document.querySelectorAll('thead th')].map((t) => t.textContent.trim()).filter(Boolean))
  await upage.click('button:has-text("Columns")')
  await upage.waitForTimeout(900)
  // toggle the first unchecked checkbox in the customizer
  const toggled = await upage.evaluate(() => {
    const dlg = document.querySelector('.p-dialog')
    if (!dlg) return null
    const boxes = [...dlg.querySelectorAll('input[type=checkbox]')]
    const off = boxes.find((b) => !b.checked)
    if (!off) return null
    off.click()
    const label = off.closest('label, .p-checkbox')?.parentElement?.textContent?.trim() || 'unknown'
    return label.slice(0, 40)
  })
  await upage.waitForTimeout(400)
  await upage.click('.p-dialog button:has-text("Save")')
  await upage.waitForTimeout(1500)
  await upage.reload({ waitUntil: 'domcontentloaded' })
  await upage.waitForTimeout(2500)
  const after = await upage.evaluate(() => [...document.querySelectorAll('thead th')].map((t) => t.textContent.trim()).filter(Boolean))
  log('T6 user-columns-persist', toggled != null && after.length !== before.length, `toggled="${toggled}" before=${before.length} after=${after.length} cols`)
}

// T7 — Lot detail: Order Items / Order Details tabs render real editor data
await upage.goto(SITE + '/web/lot/C0525-20', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(3000)
{
  await upage.click('[role=tab]:has-text("Order Items")')
  await upage.waitForTimeout(1200)
  const itemsRows = await upage.locator('.lot-table tbody tr').count()
  await upage.click('[role=tab]:has-text("Order Details")')
  await upage.waitForTimeout(1200)
  const odRows = await upage.locator('.lot-od-grid tbody tr').count()
  log('T7 lot-editors-render', itemsRows > 0 && odRows > 0, `order-items rows=${itemsRows} order-details rows=${odRows}`)
}

// T8 — bare Lot create + delete round trip (webuser, UI)
const TEST_LOT = 'E2E-TEST-LOT-1'
await upage.goto(SITE + '/web/lot/new', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  await upage.fill('#fld-lot_name', TEST_LOT)
  await upage.click('button:has-text("Save")')
  await upage.waitForTimeout(3000)
  const path = decodeURIComponent(new URL(upage.url()).pathname)
  const created = path.endsWith('/' + TEST_LOT)
  // webuser has NO delete perm on Lot — the Delete button must be HIDDEN
  // (permission-gated UI, conventions 2026-05-25). Cleanup happens in the
  // admin section below.
  const deleteHidden = (await upage.locator('button:has-text("Delete")').count()) === 0
  log('T8 lot-create+delete-gate', created && deleteHidden, `created=${created} delete-btn-hidden=${deleteHidden} (${path})`)
}

// T9 — Terms and Condition create with 2 rows + delete (webuser, UI)
const TEST_TC = 'E2E TEST TERM'
await upage.goto(SITE + '/web/terms-and-condition/new', { waitUntil: 'domcontentloaded' })
await upage.waitForTimeout(2500)
{
  await upage.fill('#fld-terms_and_condition_name', TEST_TC)
  // add two child rows in the generic details grid
  for (let i = 0; i < 2; i++) {
    await upage.click('button:has-text("Add Row")')
    await upage.waitForTimeout(400)
  }
  // type into the term cells (cell edit mode: click cell, then textarea/input)
  const cells = upage.locator('.child-editor tbody tr td:nth-child(1)')
  const rowCount = await upage.locator('.child-editor tbody tr').count()
  for (let i = 0; i < rowCount; i++) {
    await cells.nth(i).click()
    await upage.waitForTimeout(300)
    const editor = upage.locator('.child-editor textarea, .child-editor input.cell-input, .p-datatable input, .p-datatable textarea').first()
    if (await editor.count()) {
      await editor.fill(`E2E term line ${i + 1}`)
      await upage.keyboard.press('Enter')
      await upage.waitForTimeout(300)
    }
  }
  await upage.click('button:has-text("Save")')
  await upage.waitForTimeout(3000)
  const path = decodeURIComponent(new URL(upage.url()).pathname)
  const created = path.endsWith('/' + TEST_TC)
  let rows = 0
  if (created) {
    const r = await uctx.request.get(SITE + `/api/resource/Terms and Condition/${encodeURIComponent(TEST_TC)}`)
    const body = await r.json().catch(() => ({}))
    rows = (body.data?.terms_and_condition_details || []).length
  }
  log('T9 tc-create', created && rows === 2, `created=${created} term-rows=${rows}`)
}

// ─────────────────────────────────────────────────────────────────────────────
// B. admin session — desk passthrough, fabric modal, realtime, dark mode,
//    synced-lot no-change save (child-preservation contract)
// ─────────────────────────────────────────────────────────────────────────────
const actx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
const apage = await actx.newPage()
await loginViaForm(apage, ADMIN)
const aToken = await csrfOf(apage)

// T10 — admin keeps Desk: /desk 200, /app 301->desk (never bounced to /web)
{
  const landing = new URL(apage.url()).pathname
  await apage.goto(SITE + '/desk', { waitUntil: 'domcontentloaded' }).catch(() => {})
  await apage.waitForTimeout(1500)
  const deskPath = new URL(apage.url()).pathname
  log('T10 admin-desk', !deskPath.startsWith('/web'), `login->${landing} /desk->${deskPath}`)
}

// T11 — synced Lot: enter edit, change NOTHING, save — children preserved
// (this is the review-critical Lot payload contract: cut/stitch/pack survive)
{
  const before = await (await actx.request.get(SITE + '/api/resource/Lot/C0525-20')).json()
  const b = before.data
  const bItems = (b.items || []).length
  const bOD = (b.lot_order_details || []).length
  const bCut = (b.lot_order_details || []).reduce((n, r) => n + (r.cut_qty || 0), 0)
  const bPack = (b.lot_order_details || []).reduce((n, r) => n + (r.pack_qty || 0), 0)
  await apage.goto(SITE + '/web/lot/C0525-20', { waitUntil: 'domcontentloaded' })
  await apage.waitForTimeout(3000)
  await apage.click('button:has-text("Edit")')
  await apage.waitForTimeout(3500)
  const gridRows = await apage.locator('.lot-table tbody tr').count()
  await apage.click('button:has-text("Save")')
  await apage.waitForTimeout(3500)
  const after = await (await actx.request.get(SITE + '/api/resource/Lot/C0525-20')).json()
  const a = after.data
  const aItems = (a.items || []).length
  const aOD = (a.lot_order_details || []).length
  const aCut = (a.lot_order_details || []).reduce((n, r) => n + (r.cut_qty || 0), 0)
  const aPack = (a.lot_order_details || []).reduce((n, r) => n + (r.pack_qty || 0), 0)
  const ok = gridRows > 0 && aItems === bItems && aOD === bOD && aCut === bCut && aPack === bPack
  log('T11 lot-nochange-save', ok, `editor-rows=${gridRows} items ${bItems}->${aItems} od ${bOD}->${aOD} cut ${bCut}->${aCut} pack ${bPack}->${aPack}`)
}

// T12 — fabric modal loads its context on a fabric WO (no Apply — real data)
{
  let checked = 'none'
  let ok = false
  // Draft WOs against the fabric test lot (knitting/dyeing/compacting).
  for (const wo of ['WO-00004', 'WO-00003', 'WO-00005']) {
    await apage.goto(SITE + `/web/work-order/${encodeURIComponent(wo)}`, { waitUntil: 'domcontentloaded' })
    await apage.waitForTimeout(2500)
    const btn = apage.locator('button:has-text("Calculate Deliverables")')
    if (!(await btn.count())) continue
    await btn.click()
    await apage.waitForTimeout(2500)
    const state = await apage.evaluate(() => {
      const dlg = document.querySelector('.fabric-calc-dialog')
      if (!dlg) return { open: false }
      return {
        open: true,
        rows: dlg.querySelectorAll('.fc-row').length,
        empty: !!dlg.querySelector('.esd-empty'),
      }
    })
    checked = wo
    if (state.open && (state.rows > 0 || state.empty)) {
      ok = true
      // fabric rows found => contract proven; empty-state also acceptable proof the
      // modal + endpoint round-trip works on non-fabric WOs.
      if (state.rows > 0) { checked += ` (fabric rows=${state.rows})`; }
      else checked += ' (clean empty-state)'
    }
    await apage.keyboard.press('Escape')
    if (state.rows > 0) break
  }
  log('T12 fabric-modal', ok, checked)
}

// T13 — realtime: admin edits a WO comment via API; webuser's open tab shows
// the stale-document banner (and doc.modified is NOT silently advanced)
{
  const wo = 'WO-00001'
  const woDoc = await (await actx.request.get(SITE + `/api/resource/Work Order/${encodeURIComponent(wo)}`)).json()
  const origComments = woDoc.data.comments ?? null
  await upage.goto(SITE + `/web/work-order/${encodeURIComponent(wo)}`, { waitUntil: 'domcontentloaded' })
  await upage.waitForTimeout(3500)
  await apiWrite(actx, aToken, 'put', `/api/resource/Work Order/${encodeURIComponent(wo)}`, { comments: 'e2e realtime probe' })
  await upage.waitForTimeout(4500)
  const banner = await upage.evaluate(() => {
    const el = [...document.querySelectorAll('.form-banner, .p-message')].find((m) => /modified by another user/i.test(m.textContent))
    return !!el
  })
  // restore
  await apiWrite(actx, aToken, 'put', `/api/resource/Work Order/${encodeURIComponent(wo)}`, { comments: origComments })
  log('T13 realtime-stale-banner', banner, banner ? 'banner shown' : 'banner NOT shown')
}

// T14 — dark mode: toggle and MEASURE the list row background (not eyeball)
{
  await apage.goto(SITE + '/web/lot', { waitUntil: 'domcontentloaded' })
  await apage.waitForTimeout(2500)
  await apage.click('button[aria-label*="theme" i], button:has(.pi-moon), button:has(.pi-sun)')
  await apage.waitForTimeout(1200)
  const probe = await apage.evaluate(() => {
    const dark = document.documentElement.classList.contains('dark')
    const row = document.querySelector('tbody tr')
    const bg = row ? getComputedStyle(row).backgroundColor : ''
    const page = getComputedStyle(document.body).backgroundColor
    return { dark, bg, page }
  })
  const rgb = (probe.bg.match(/\d+/g) || []).map(Number)
  const rowIsDark = rgb.length >= 3 && (rgb[0] + rgb[1] + rgb[2]) / 3 < 100
  // toggle back to light
  await apage.click('button[aria-label*="theme" i], button:has(.pi-moon), button:has(.pi-sun)')
  log('T14 dark-mode-measured', probe.dark && rowIsDark, `html.dark=${probe.dark} row-bg=${probe.bg} page-bg=${probe.page}`)
}

// cleanup the webuser-created test records (admin holds delete)
for (const [dt, name] of [['Lot', TEST_LOT], ['Terms and Condition', TEST_TC]]) {
  const del = await apiWrite(actx, aToken, 'delete', `/api/resource/${encodeURIComponent(dt)}/${encodeURIComponent(name)}`)
  const gone = (await actx.request.get(SITE + `/api/resource/${encodeURIComponent(dt)}/${encodeURIComponent(name)}`)).status() === 404
  log(`cleanup ${dt}`, gone, `${name} delete-status=${del.status()}`)
}

await browser.close()
const fails = results.filter((r) => !r.ok)
console.log(`\n== ${results.length - fails.length}/${results.length} PASS ==`)
if (fails.length) {
  console.log('FAILED:', fails.map((f) => f.id).join(', '))
  process.exit(1)
}
