// Shared E2E helper for the essdee /web UI verification agents.
// Real interactions + RENDERED GEOMETRY assertions (never DOM-presence alone —
// a display:none subtree keeps its nodes, so we measure paint, not existence).
//
// Usage from a slice script:
//   import { launch, loginAs, shot, listGeo, realClickRow, geoOf, SITE } from './e2e-lib.mjs'
import { createRequire } from 'node:module'
import { readFileSync, mkdirSync } from 'node:fs'

const require = createRequire('/home/anas/.claude/playwright/package.json')
export const { chromium } = require('playwright')

export const SITE = 'http://essdee_yrp.site:8003'
const creds = readFileSync('/home/anas/.frappe-debug-creds-mrp3', 'utf8').trim().split('\n')
export const ADMIN = { usr: creds[0].trim(), pwd: creds[1].trim() }
export const WEBUSER = { usr: 'webuser@essdee.fit', pwd: 'webuser@1234' }

export const SHOT_DIR = '/home/anas/frappe-16/apps/essdee_yrp/docs/design/e2e-shots'
mkdirSync(SHOT_DIR, { recursive: true })

export async function launch() {
  return chromium.launch({ headless: true })
}

export async function loginAs(browser, who) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  const page = await ctx.newPage()
  page._errs = []
  page.on('pageerror', (e) => page._errs.push('PAGEERR: ' + e.message.slice(0, 160)))
  page.on('console', (m) => { if (m.type() === 'error') page._errs.push('CONSOLE: ' + m.text().slice(0, 160)) })
  await page.goto(SITE + '/login', { waitUntil: 'domcontentloaded' })
  await page.fill('#login_email', who.usr)
  await page.fill('#login_password', who.pwd)
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {}),
    page.click('.btn-login, button[type=submit]'),
  ])
  await page.waitForTimeout(2500)
  return { ctx, page }
}

export async function shot(page, name) {
  const path = `${SHOT_DIR}/${name}.png`
  await page.screenshot({ path }).catch(() => {})
  return path
}

// The rendered geometry of the first table that has data rows (or a named el).
export async function geoOf(page, selector) {
  return page.evaluate((sel) => {
    let el
    if (sel) el = document.querySelector(sel)
    else el = [...document.querySelectorAll('table')].find((t) => t.querySelector('tbody tr'))
    if (!el) return { found: false, w: 0, h: 0, painted: false }
    const r = el.getBoundingClientRect()
    return { found: true, w: Math.round(r.width), h: Math.round(r.height), painted: el.offsetParent !== null && r.width > 40 && r.height > 10 }
  }, selector)
}

export async function listGeo(page) {
  return page.evaluate(() => {
    const tbl = [...document.querySelectorAll('table')].find((t) => t.querySelector('tbody tr'))
    const rows = document.querySelectorAll('tbody tr').length
    const tabs = [...document.querySelectorAll('[role=tab]')].map((t) => t.textContent.trim())
    if (!tbl) return { rows, tabs, tableW: 0, painted: false }
    const r = tbl.getBoundingClientRect()
    return { rows, tabs, tableW: Math.round(r.width), painted: tbl.offsetParent !== null && r.width > 40 }
  })
}

// Real mouse click on a data row's 2nd cell (the name), returns the new pathname.
export async function realClickRow(page, idx = 1) {
  const before = new URL(page.url()).pathname
  const cell = page.locator('tbody tr').nth(idx).locator('td').nth(1)
  await cell.click({ force: true, timeout: 8000 }).catch(() => {})
  await page.waitForTimeout(2500)
  const after = new URL(page.url()).pathname
  return { before, after, navigated: after !== before }
}

// Wait for a list table to actually paint (not just exist).
export async function waitListPaint(page, timeout = 12000) {
  await page.waitForFunction(() => {
    const t = [...document.querySelectorAll('table')].find((x) => x.querySelector('tbody tr'))
    return t && t.offsetParent !== null && t.getBoundingClientRect().width > 40
  }, { timeout }).catch(() => {})
}

// Detail page: is the main content painted (tabs or cards present with size)?
export async function detailGeo(page) {
  return page.evaluate(() => {
    const tabs = [...document.querySelectorAll('[role=tab]')].map((t) => t.textContent.trim())
    const cards = [...document.querySelectorAll('.detail-card, .side-card, .esd-card, [class*=card]')]
      .filter((c) => c.getBoundingClientRect().width > 40 && c.offsetParent !== null)
    const main = document.querySelector('.detail-main, .detail-layout, main')
    const mainW = main ? Math.round(main.getBoundingClientRect().width) : 0
    const title = (document.querySelector('h1, .doc-title, .page-title, .crumb-cur')?.textContent || '').trim().slice(0, 60)
    const bodyText = (document.querySelector('.detail-layout, main')?.textContent || '').replace(/\s+/g, ' ').trim().length
    return { tabs, paintedCards: cards.length, mainW, title, bodyTextLen: bodyText }
  })
}
