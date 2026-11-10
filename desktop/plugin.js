// Sabbath — the Desktop half: your week at a glance, the rest in progress, what sleeps and what waits.
// Built from the app's own UI kit and theme tokens; talks only to its own backend through ctx.rest.
import {
  Badge, Button, Codicon, CopyButton, Input, Loader, ROUTES_AREA, SIDEBAR_NAV_AREA, StatusDot, Switch, host
} from '@hermes/plugin-sdk'
import { useCallback, useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'sabbath'
const PATH = '/sabbath'
const WEEK = 7 * 86400

const h = (tag, props, ...kids) => {
  const children = kids.flat().filter(k => k !== null && k !== undefined && k !== false && k !== '')
  return (children.length > 1 ? jsxs : jsx)(tag, { ...(props || {}), children: children.length > 1 ? children : children[0] })
}

// A candle. Strokes only, so it takes any theme colour.
const CANDLE = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2.2c1.9 2.1 2.7 3.6 2.7 4.9a2.7 2.7 0 0 1-5.4 0c0-1.3.8-2.8 2.7-4.9z"/><path d="M12 10.2v1.8"/><rect x="8.6" y="12" width="6.8" height="9.4" rx="1"/><path d="M5.5 21.4h13"/></svg>'
const CANDLE_URL = `url("data:image/svg+xml,${encodeURIComponent(CANDLE)}")`
// ponytail: the sidebar only takes codicon names, so `codicon-sabbath` is drawn by this mask rule.
const NAV_CSS = `.codicon.codicon-sabbath::before{content:"";display:inline-block;width:1em;height:1em;background:currentColor;-webkit-mask:${CANDLE_URL} center/contain no-repeat;mask:${CANDLE_URL} center/contain no-repeat}`

const CSS = `
.sab{container-type:inline-size;max-width:1000px;margin:0 auto;padding:32px clamp(1.25rem,4vw,4rem) 80px;color:var(--ui-text-primary);font-size:13px;line-height:1.55}
.sab *{box-sizing:border-box}
.sab .mark{width:44px;height:44px;flex:none;background:var(--ui-accent);-webkit-mask:${CANDLE_URL} center/contain no-repeat;mask:${CANDLE_URL} center/contain no-repeat}
.sab .head{display:flex;gap:16px;align-items:flex-start}
.sab .head h1{font-size:18px;font-weight:600;margin:4px 0 4px;letter-spacing:-.015em}
.sab .lede{color:var(--ui-text-secondary);font-size:13.5px;max-width:660px;margin:0}
.sab .why{margin:10px 0 0;padding:10px 14px;border-left:2px solid var(--ui-accent);color:var(--ui-text-secondary);max-width:660px;background:color-mix(in srgb,var(--ui-accent) 6%,transparent);border-radius:0 6px 6px 0}
.sab .why b{color:var(--ui-text-primary);font-weight:600}
.sab .pill{margin-left:auto;display:inline-flex;gap:8px;align-items:center;color:var(--ui-text-secondary);white-space:nowrap;font-size:12px;padding-top:6px}
.sab .card{border-top:1px solid var(--ui-stroke-tertiary);padding-top:20px;margin-top:32px}
.sab .label{font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--ui-text-tertiary)}
.sab .row{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.sab .muted{color:var(--ui-text-tertiary)}
.sab .sec{color:var(--ui-text-secondary)}
.sab .small{font-size:12px}
/* the week */
.sab .week{position:relative;margin-top:16px;height:74px;border-radius:8px;overflow:hidden;background:color-mix(in srgb,var(--ui-text-primary) 3.5%,transparent)}
.sab .days{position:absolute;inset:0;display:grid;grid-template-columns:repeat(7,minmax(0,1fr))}
.sab .days>div{border-left:1px solid var(--ui-stroke-tertiary);padding:8px clamp(4px,1.2cqi,10px);overflow:hidden;font-size:11px;color:var(--ui-text-tertiary);letter-spacing:.04em;text-transform:uppercase}
.sab .days>div:first-child{border-left:none}
.sab .band{position:absolute;top:0;bottom:0;background:linear-gradient(180deg,color-mix(in srgb,var(--ui-accent) 34%,transparent),color-mix(in srgb,var(--ui-accent) 14%,transparent));border-left:2px solid var(--ui-accent);border-right:2px solid color-mix(in srgb,var(--ui-accent) 50%,transparent)}
.sab .band[data-on=true]{animation:sab-breathe 4s ease-in-out infinite}
@keyframes sab-breathe{50%{filter:brightness(1.25)}}
.sab .band span{position:absolute;bottom:8px;left:10px;font-size:11.5px;font-weight:600;color:var(--ui-text-primary);white-space:nowrap}
.sab .nowline{position:absolute;top:0;bottom:0;width:2px;background:var(--ui-text-primary);opacity:.7}
.sab .nowline:after{content:"now";position:absolute;top:6px;left:5px;font-size:10px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ui-text-secondary)}
.sab .hero{display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-top:18px}
.sab .big{font-size:26px;font-weight:600;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.sab .flame{width:26px;height:34px;flex:none;background:var(--ui-accent);-webkit-mask:${CANDLE_URL} center/contain no-repeat;mask:${CANDLE_URL} center/contain no-repeat;animation:sab-flicker 2.8s ease-in-out infinite;transform-origin:50% 90%}
@keyframes sab-flicker{30%{transform:scaleY(1.04) rotate(-1deg)}60%{transform:scaleY(.97) rotate(1deg)}}
/* the steps */
.sab .flow{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px}
@container (max-width:680px){.sab .flow{grid-template-columns:1fr 1fr}.sab .head .mark{width:32px;height:32px}}
@container (max-width:420px){.sab .flow{grid-template-columns:1fr}.sab .days>div{font-size:9.5px;letter-spacing:0}}
.sab .fl{padding-left:12px;border-left:2px solid var(--ui-stroke-secondary);transition:border-color .4s}
.sab .fl[data-on=true]{border-left-color:var(--ui-accent)}
.sab .fl h4{margin:0 0 2px;font-size:12.5px;font-weight:600;display:flex;gap:6px;align-items:center}
.sab .fl p{margin:0;font-size:11.5px;color:var(--ui-text-tertiary);line-height:1.45}
/* lists */
.sab .two{display:grid;grid-template-columns:1fr 1fr;gap:0 48px}
@container (max-width:760px){.sab .two{grid-template-columns:1fr}}
.sab .items{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-direction:column}
.sab .items li{display:grid;grid-template-columns:18px 1fr auto;gap:10px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--ui-stroke-tertiary)}
.sab .items li:last-child{border-bottom:none}
.sab .items .meta{font-size:11px;color:var(--ui-text-tertiary)}
.sab .empty{margin-top:12px;color:var(--ui-text-tertiary);font-size:12.5px;max-width:460px}
.sab .add{display:flex;gap:8px;margin-top:12px}
.sab .dots{display:flex;gap:6px;margin-top:12px;flex-wrap:wrap}
.sab .dot{width:16px;height:16px;border-radius:50%;background:color-mix(in srgb,var(--ui-text-primary) 8%,transparent)}
.sab .dot[data-k=true]{background:var(--ui-accent)}
.sab .log{margin:10px 0 0;padding:0;list-style:none;font-size:12px;color:var(--ui-text-secondary)}
.sab .log li{display:grid;grid-template-columns:130px 1fr;gap:10px;padding:3px 0}
@media (prefers-reduced-motion:reduce){.sab *{animation:none!important;transition:none!important}}
`

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
const errText = e => String(e?.message || e)
function left(sec) {
  if (sec < 60) return `${Math.max(0, Math.round(sec))} s`
  const hh = Math.floor(sec / 3600), mm = Math.floor((sec % 3600) / 60)
  return hh ? `${hh} h ${String(mm).padStart(2, '0')} m` : `${mm} min ${String(Math.floor(sec % 60)).padStart(2, '0')} s`
}
function mondayOf(ts) {
  const d = new Date(ts * 1000)
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  return d.getTime() / 1000
}

// Your week, Monday to Sunday: the rest is the gold band; the line is now.
function Week({ s, now }) {
  const mon = mondayOf(now)
  const r = s.rest
  const start = r ? r.started_at : s.window.start
  const end = r ? r.ends_at : s.window.end
  const segs = []
  for (const shift of [-WEEK, 0, WEEK]) { // a rest that crosses Sunday night shows on both ends
    const a = Math.max(0, (start + shift - mon) / WEEK), b = Math.min(1, (end + shift - mon) / WEEK)
    if (b > a && b > 0 && a < 1) segs.push([a, b])
  }
  return h('div', { className: 'week', role: 'img', 'aria-label': r ? `Rest until ${r.ends_label}` : `Rest ${s.window.start_label} to ${s.window.end_label}` },
    h('div', { className: 'days' }, DAYS.map(d => h('div', { key: d }, d))),
    (s.keeping || r) ? segs.map(([a, b], i) => h('div', { key: i, className: 'band', 'data-on': String(!!r), style: { left: `${a * 100}%`, width: `${(b - a) * 100}%` } },
      i === segs.length - 1 && (b - a) > 0.08 ? h('span', null, r ? (r.kind === 'try' ? 'Trying it' : 'Resting') : 'Sabbath') : null)) : null,
    h('div', { className: 'nowline', style: { left: `${((now - mon) / WEEK) * 100}%` } }))
}

const FLOW = [
  { icon: 'comment', t: 'Goodnight', p: 'Hermes writes to you on your phone: the week’s work is done.' },
  { icon: 'debug-pause', t: 'Its jobs sleep', p: 'Hermes pauses its own scheduled jobs. Only the ones you exempt keep running.' },
  { icon: 'heart', t: 'Anything but work', p: 'Talk about people, meals, books, walks, prayer, play. What can wait is set aside.' },
  { icon: 'mail', t: 'Good morning', p: 'One gentle digest: what waited, what you set aside. The jobs catch up.' }
]

function Page({ ctx }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [why, setWhy] = useState(false)
  const [item, setItem] = useState('')
  const [showLog, setShowLog] = useState(false)
  const [now, setNow] = useState(Date.now() / 1000)

  const load = useCallback(() => ctx.rest('/state').then(v => { setS(v); setErr('') }).catch(e => setErr(errText(e))), [ctx])
  const resting = !!s?.rest
  useEffect(() => {
    load()
    const stop = ctx.setInterval(load, resting ? 4000 : 15000)
    const tick = ctx.setInterval(() => setNow(Date.now() / 1000), 1000)
    const off = host.onEvent(`plugin.${ID}.state.changed`, load)
    return () => { stop && stop(); tick && tick(); off && off() }
  }, [load, resting])

  const post = async (path, body = {}) => {
    setBusy(true)
    try { const r = await ctx.rest(path, { method: 'POST', body }); await load(); if (r?.message) host.notify?.({ kind: 'info', message: r.message }); return r }
    catch (e) { host.notifyError ? host.notifyError(e, 'Sabbath could not reach Hermes') : setErr(errText(e)); return null }
    finally { setBusy(false) }
  }

  if (!s) return h('div', { className: 'sab' }, h('style', null, CSS), err ? h('p', { className: 'muted' }, err) : jsx(Loader, { label: 'Sabbath' }))

  const r = s.rest
  const leftSec = r ? Math.max(0, r.ends_at - now) : 0
  const winErr = s.window.error
  const status = r ? ['good', r.ox_active ? 'Lifted for something urgent' : `Resting · until ${r.ends_label}`]
    : s.keeping ? ['muted', `Next rest ${s.window.start_label}`] : ['muted', 'Weekly rest is off']
  const kept = s.history.filter(x => x.kind !== 'try')
  const lastWeeks = Array.from({ length: 12 }, (_, i) => {
    const mon = mondayOf(now) - (11 - i) * WEEK
    return kept.some(x => x.started_at >= mon - 86400 && x.started_at < mon + WEEK - 86400)
  })
  const basket = r ? r.basket : (s.loose_basket || [])
  const lastRest = !r && s.history.length ? s.history[s.history.length - 1] : null
  const jobs = r ? r.held : (s.jobs || [])
  const exempt = new Set((s.keep_running || []).map(x => x.toLowerCase()))

  return h('div', { className: 'sab' },
    h('style', null, CSS),

    h('div', { className: 'head' },
      h('div', { className: 'mark', role: 'img', 'aria-label': 'Candle' }),
      h('div', { style: { flex: 1 } },
        h('div', { className: 'row', style: { alignItems: 'flex-start' } },
          h('h1', null, 'Sabbath'),
          h('span', { className: 'pill' }, jsx(StatusDot, { tone: status[0] }), status[1])),
        h('p', { className: 'lede' },
          'Your agent never rests. Now it rests with you. Once a week Hermes keeps a day of rest: it says goodnight, its scheduled jobs sleep, ' +
          'it keeps you company in anything but work, and it sets aside what can wait until the rest is over.'),
        jsx(Button, { variant: 'text', size: 'inline', onClick: () => setWhy(!why), style: { marginTop: 6 }, children: why ? 'Why “Sabbath”? ▴' : 'Why “Sabbath”? ▾' }),
        why ? h('div', { className: 'why small' },
          h('b', null, 'Six days you shall labour, and the seventh is a rest. '),
          'The Sabbath isn’t idleness: it is a day set apart for delight, for the people you love, for gratitude and for beauty. ',
          'An agent that never sleeps can quietly make sure you never do either. This one keeps the day with you, and if something truly can’t wait, ',
          'the old rule still holds: when the ox falls into the well, you pull it out (', h('i', null, 'Luke 14:5'), '). Send ', h('b', null, '/sabbath ox'), '.')
          : null)),

    // Your week and the rest in progress.
    h('div', { className: 'card' },
      h('div', { className: 'row' },
        h('span', { className: 'label' }, 'Your week'),
        h('label', { className: 'row small sec', style: { gap: 8, cursor: 'pointer' } },
          jsx(Switch, { checked: !!s.keeping, disabled: busy || !!winErr, onCheckedChange: v => post('/keep', { keeping: v }) }), 'Keep it every week')),
      winErr ? h('p', { className: 'small', style: { color: 'var(--ui-red)' } }, winErr) : jsx(Week, { s, now }),
      h('div', { className: 'hero' },
        r ? h('div', { className: 'row', style: { gap: 14, justifyContent: 'flex-start' } },
          h('div', { className: 'flame', 'aria-hidden': true }),
          h('div', null,
            h('div', { className: 'big' }, left(leftSec)),
            h('div', { className: 'sec small' }, r.ox_active ? 'The ox is in the well: Hermes helps fully for the hour, then the rest goes on.' : `of rest left · ${plural(r.held.length, 'job')} asleep · ${plural(r.basket.length, 'thing')} set aside`)))
          : h('div', null,
            h('div', { className: 'big' }, s.keeping ? s.window.start_label.replace(/^./, c => c.toUpperCase()) : 'Not this week'),
            h('div', { className: 'sec small' }, s.keeping ? `Your next rest begins then, for ${plural(s.hours, 'hour')}. Change it in Settings › Plugins › Sabbath.` : `Turn on “Keep it every week” to rest ${s.window.start_label} for ${plural(s.hours, 'hour')}, or try it now.`)),
        r ? h('div', { className: 'row', style: { gap: 6 } },
          r.ox_active ? null : jsx(Button, { variant: 'ghost', disabled: busy, onClick: () => post('/ox', {}), children: 'The ox is in the well' }),
          jsx(Button, { variant: 'secondary', disabled: busy, onClick: () => post('/end'), children: 'End the rest' }))
          : h('div', { className: 'row', style: { gap: 6 } },
            jsx(Button, { variant: 'ghost', disabled: busy, onClick: () => post('/begin', { try: true }), children: [jsx(Codicon, { name: 'play-circle' }, 'i'), 'Try a two-minute Sabbath'] }),
            jsx(Button, { disabled: busy, onClick: () => post('/begin', { hours: s.hours }), children: 'Begin now' }))),
      h('div', { className: 'flow' }, FLOW.map((f, i) => h('div', { key: f.t, className: 'fl', 'data-on': String(!!r && i < 3) },
        h('h4', null, jsx(Codicon, { name: f.icon }), f.t), h('p', null, f.p))))),

    // Setup, only while something is missing.
    s.owner.channels.length ? null : h('div', { className: 'card' },
      h('div', { className: 'row' },
        h('div', { style: { maxWidth: 560 } },
          h('div', { style: { fontWeight: 600 } }, 'Tell Hermes where to say goodnight'),
          h('div', { className: 'small muted' }, 'From your phone, send /sabbath here to your Hermes (Telegram, Signal, WhatsApp…). The goodnight and the morning digest arrive in that chat.')),
        jsx(CopyButton, { text: '/sabbath here', label: 'Copy /sabbath here', buttonVariant: 'default' }))),

    h('div', { className: 'two' },
      h('div', { className: 'card' },
        h('div', { className: 'row' },
          h('span', { className: 'label' }, r ? 'Asleep now' : 'What will sleep'),
          h('span', { className: 'muted small' }, plural(jobs.length, 'scheduled job'))),
        jobs.length
          ? h('ul', { className: 'items' }, jobs.map(j => {
            const ex = !r && (exempt.has(String(j.id).toLowerCase()) || exempt.has(String(j.name).toLowerCase()))
            return h('li', { key: j.id }, jsx(Codicon, { name: r ? 'debug-pause' : ex ? 'sync' : 'clock' }),
              h('span', null, j.name, h('div', { className: 'meta' }, j.schedule || '')),
              ex ? jsx(Badge, { children: 'Never rests' }) : r ? jsx(Badge, { children: 'Asleep' }) : h('span'))
          }))
          : h('div', { className: 'empty' }, 'Hermes has no scheduled jobs right now. When it does (a morning briefing, a newsletter digest), they sleep through your rest and catch up after.')),

      h('div', { className: 'card' },
        h('div', { className: 'row' },
          h('span', { className: 'label' }, 'Set aside'),
          h('span', { className: 'muted small' }, r ? 'comes back in the morning digest' : lastRest ? `last rest: ${plural(lastRest.basket, 'thing')}` : '')),
        basket.length
          ? h('ul', { className: 'items' }, basket.map((b, i) => h('li', { key: i }, jsx(Codicon, { name: 'inbox' }), h('span', null, b.text), h('span', { className: 'meta' }, new Date(b.at * 1000).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })))))
          : h('div', { className: 'empty' }, 'When work comes up during your rest, Hermes offers to set it aside instead. Everything here comes back to you, in one list, when the rest ends.'),
        h('form', { className: 'add', onSubmit: e => { e.preventDefault(); if (item.trim()) post('/set-aside', { item }).then(x => x && setItem('')) } },
          jsx(Input, { value: item, placeholder: 'Something that can wait…', onChange: e => setItem(e.target.value) }),
          jsx(Button, { type: 'submit', variant: 'secondary', disabled: busy || !item.trim(), children: 'Set aside' })))),

    h('div', { className: 'card' },
      h('div', { className: 'row' },
        h('span', { className: 'label' }, 'Rests kept'),
        h('span', { className: 'muted small' }, kept.length ? `${plural(kept.length, 'rest')} · ${s.hours_rested} hours in all` : 'none yet')),
      h('div', { className: 'dots', 'aria-label': 'The last twelve weeks' }, lastWeeks.map((k, i) => h('div', { key: i, className: 'dot', 'data-k': String(k) }))),
      h('div', { className: 'small muted', style: { marginTop: 6 } }, 'The last twelve weeks. Gold where you rested.')),

    (s.log || []).length ? h('div', { style: { marginTop: 14 } },
      jsx(Button, { variant: 'text', size: 'inline', onClick: () => setShowLog(!showLog), children: showLog ? 'Hide activity ▴' : 'Activity ▾' }),
      showLog ? h('ul', { className: 'log' }, s.log.slice().reverse().map((e, i) =>
        jsxs('li', { children: [h('span', { className: 'muted' }, new Date(e.at * 1000).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })), h('span', null, e.text)] }, i))) : null) : null,
    err ? h('p', { className: 'small', style: { color: 'var(--ui-red)', marginTop: 12 } }, err) : null)
}

export default {
  id: ID,
  name: 'Sabbath',
  register(ctx) {
    const style = document.createElement('style')
    style.dataset.plugin = ID
    style.textContent = NAV_CSS
    document.head.appendChild(style)
    ctx.onDispose(() => style.remove())
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: PATH }, render: () => jsx(Page, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: PATH, label: 'Sabbath', codicon: 'sabbath' } }
    ])
  }
}
