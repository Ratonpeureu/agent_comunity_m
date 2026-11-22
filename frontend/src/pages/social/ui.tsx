// src/pages/social/ui.tsx
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { BASE_URL } from '../../lib/api'
import { errMsg, mediaSrc, pmeta, PLATFORMS, Platform, STATUS_META, waitJob } from '../../lib/social'
/* ───────── Contexte : toasts, jobs en cours, rafraîchissement ───────── */
interface Ctx {
  ok: (m: string) => void
  err: (m: string) => void
  info: (m: string) => void
  /** Lance un job Celery et attend sa fin. `starter` doit retourner { job_id }. Retourne le résultat ou null. */
  runJob: (label: string, starter: () => Promise<any>) => Promise<any | null>
  /** Compteur incrémenté à chaque job terminé : à mettre dans les deps des useLoad pour recharger. */
  tick: number
  bump: () => void
}
const SocialCtx = createContext<Ctx>({ ok() {}, err() {}, info() {}, runJob: async () => null, tick: 0, bump() {} })
export const useSocial = () => useContext(SocialCtx)

export function SocialProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<{ id: number; kind: string; msg: string }[]>([])
  const [jobs, setJobs] = useState<{ id: number; label: string }[]>([])
  const [tick, setTick] = useState(0)
  const seq = useRef(0)

  const push = useCallback((kind: string, msg: string) => {
    const id = ++seq.current
    setToasts(t => [...t, { id, kind, msg }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), kind === 'err' ? 8000 : 4200)
  }, [])
  const bump = useCallback(() => setTick(t => t + 1), [])

  const runJob = useCallback(async (label: string, starter: () => Promise<any>) => {
    const id = ++seq.current
    setJobs(j => [...j, { id, label }])
    try {
      const start = await starter()
      if (!start || !start.job_id) return null
      const job = await waitJob(start.job_id)
      const res = job.resultat || {}
      if (res.message) push('info', String(res.message))
      else push('ok', `${label} : terminé`)
      if (res.avertissement) push('info', String(res.avertissement))
      if (Array.isArray(res.erreurs) && res.erreurs.length) push('err', `${res.erreurs.length} erreur(s) : ${res.erreurs[0].erreur}`)
      bump()
      return res
    } catch (e) {
      push('err', `${label} : ${errMsg(e)}`)
      return null
    } finally {
      setJobs(j => j.filter(x => x.id !== id))
    }
  }, [push, bump])

  const value = useMemo<Ctx>(() => ({
    ok: m => push('ok', m), err: m => push('err', m), info: m => push('info', m), runJob, tick, bump,
  }), [push, runJob, tick, bump])

  return (
    <SocialCtx.Provider value={value}>
      {children}
      <div className="sm-jobs">{jobs.map(j => <div key={j.id} className="sm-job"><Spinner />{j.label}…</div>)}</div>
      <div className="sm-toasts">{toasts.map(t => <div key={t.id} className={`sm-toast ${t.kind}`}>{t.msg}</div>)}</div>
    </SocialCtx.Provider>
  )
}

/* ───────── Chargement de données ───────── */
export function useLoad<T>(fn: () => Promise<T>, deps: React.DependencyList) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const seq = useRef(0)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const load = useCallback(async () => {
    const id = ++seq.current
    setLoading(true); setError('')
    try { const d = await fn(); if (alive.current && id === seq.current) setData(d) }
    catch (e) { if (alive.current && id === seq.current) setError(errMsg(e)) }
    finally { if (alive.current && id === seq.current) setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { load() }, [load])
  return { data, loading, error, reload: load, setData }
}

/* ───────── Éléments de base ───────── */
export const Spinner = () => <span className="sm-spin" />
export const Loading = ({ text = 'Chargement…' }: { text?: string }) => <div className="sm-loading"><Spinner />{text}</div>
export const Badge = ({ tone = 'gray', children }: { tone?: string; children: React.ReactNode }) => <span className={`sm-badge ${tone}`}>{children}</span>
export const StatusBadge = ({ s }: { s: string }) => { const m = STATUS_META[s] || { label: s, tone: 'gray' }; return <Badge tone={m.tone}>{m.label}</Badge> }


const GLYPH: Record<string, string> = {
  facebook: 'M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z',
  linkedin: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z',
  tiktok: 'M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z',
  x: 'M18.901 1.153h3.68l-8.04 9.19L24 22.846h-7.406l-5.8-7.584-6.638 7.584H.474l8.6-9.83L0 1.154h7.594l5.243 6.932ZM17.61 20.644h2.039L6.486 3.24H4.298Z',
}

export function PlatformIcon({ p, size = 24 }: { p: string; size?: number }) {
  const m = pmeta(p)
  const bg = p === 'instagram' ? 'linear-gradient(45deg,#F9CE34 0%,#EE2A7B 50%,#6228D7 100%)' : m.color
  const g = Math.round(size * 0.62)
  return (
    <span className="sm-pdot" style={{ background: bg, width: size, height: size, borderRadius: Math.round(size * 0.3) }} title={m.label}>
      {p === 'instagram' ? (
        <svg viewBox="0 0 24 24" width={g} height={g} aria-label="Instagram">
          <rect x="3" y="3" width="18" height="18" rx="5" fill="none" stroke="#fff" strokeWidth="2" />
          <circle cx="12" cy="12" r="4" fill="none" stroke="#fff" strokeWidth="2" />
          <circle cx="17.3" cy="6.7" r="1.2" fill="#fff" />
        </svg>
      ) : GLYPH[p] ? (
        <svg viewBox="0 0 24 24" width={g} height={g} aria-label={m.label}><path d={GLYPH[p]} fill="#fff" /></svg>
      ) : <span style={{ fontSize: size * 0.4 }}>{m.short}</span>}
    </span>
  )
}
export const PlatformDot = ({ p }: { p: string }) => <PlatformIcon p={p} />

export function PlatformPicker({ value, onChange }: { value: string[]; onChange: (v: Platform[]) => void }) {
  return (
    <div className="sm-chips">
      {PLATFORMS.map(p => {
        const on = value.includes(p)
        return <button key={p} type="button" className={`sm-chip pl${on ? ' on' : ''}`} style={{ gap: 6, padding: '4px 12px 4px 6px' }}
          onClick={() => onChange((on ? value.filter(x => x !== p) : [...value, p]) as Platform[])}><PlatformIcon p={p} size={20} />{pmeta(p).label}</button>
      })}
    </div>
  )
}

export function Pills<T extends string>({ items, value, onChange }: { items: { id: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="sm-pills">
      {items.map(i => <button key={i.id} className={`sm-pill${value === i.id ? ' on' : ''}`} onClick={() => onChange(i.id)}>{i.label}{i.count != null && <em>{i.count}</em>}</button>)}
    </div>
  )
}

export function Field({ label, hint, children }: { label?: string; hint?: string; children: React.ReactNode }) {
  return <div className="sm-field">{label && <label className="sm-label">{label}</label>}{children}{hint && <span className="sm-hint">{hint}</span>}</div>
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: string; disabled?: boolean }) {
  return <label className="sm-switch"><input type="checkbox" checked={!!checked} disabled={disabled} onChange={e => onChange(e.target.checked)} /><span />{label && <em>{label}</em>}</label>
}

export function TagInput({ value, onChange, placeholder, hash }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; hash?: boolean }) {
  const [txt, setTxt] = useState('')
  const add = (raw: string) => {
    const parts = raw.split(/[,\n]/).map(s => s.trim()).filter(Boolean).map(s => (hash ? (s.startsWith('#') ? s : '#' + s.replace(/\s+/g, '')) : s))
    if (!parts.length) { setTxt(''); return }
    const next = [...value]
    parts.forEach(p => { if (!next.some(x => x.toLowerCase() === p.toLowerCase())) next.push(p) })
    onChange(next); setTxt('')
  }
  return (
    <div className="sm-tags">
      {value.map((t, i) => <span key={t + i} className="sm-chip">{t}<button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))}>×</button></span>)}
      <input value={txt} placeholder={value.length ? '' : placeholder} onChange={e => setTxt(e.target.value)} onBlur={() => add(txt)}
        onKeyDown={e => {
          if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); add(txt) }
          else if (e.key === 'Backspace' && !txt && value.length) onChange(value.slice(0, -1))
        }} />
    </div>
  )
}

export function Modal({ title, onClose, children, footer, wide }: { title: React.ReactNode; onClose: () => void; children: React.ReactNode; footer?: React.ReactNode; wide?: boolean }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="sm-back" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`sm-modal${wide ? ' wide' : ''}`}>
        <div className="sm-modal-h"><h3>{title}</h3><button className="sm-x" onClick={onClose}>×</button></div>
        <div className="sm-modal-b">{children}</div>
        {footer && <div className="sm-modal-f">{footer}</div>}
      </div>
    </div>
  )
}

export const Empty = ({ title, children }: { title: string; children?: React.ReactNode }) => <div className="sm-empty"><b>{title}</b>{children}</div>

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: React.ReactNode }) {
  return <div className="sm-head"><div><h2 className="sm-title">{title}</h2>{sub && <p className="sm-sub">{sub}</p>}</div><div className="sm-actions">{children}</div></div>
}

export function Stat({ label, value, hint, trend }: { label: string; value: React.ReactNode; hint?: string; trend?: 'up' | 'down' | '' }) {
  return <div className="sm-stat"><div className="l">{label}</div><div className="v">{value}</div>{hint && <div className={`h ${trend || ''}`}>{hint}</div>}</div>
}

export function ScoreRing({ value, size = 56 }: { value?: number | null; size?: number }) {
  const v = Math.max(0, Math.min(100, value ?? 0))
  const col = v >= 70 ? '#059669' : v >= 45 ? '#d97706' : '#dc2626'
  const r = (size - 8) / 2, c = 2 * Math.PI * r
  return (
    <span className="sm-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f4" strokeWidth={5} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={5} strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} />
      </svg>
      <b style={{ color: col, fontSize: size < 44 ? 10 : 13 }}>{value == null ? '—' : Math.round(v)}</b>
    </span>
  )
}

export function BarList({ rows, fmt, color }: { rows: { label: string; value: number; n?: number }[]; fmt?: (v: number) => string; color?: string }) {
  if (!rows.length) return <p className="sm-mut sm-xs">Pas encore de données.</p>
  const max = Math.max(...rows.map(r => r.value), 1e-9)
  return (
    <div className="sm-bars">
      {rows.map(r => (
        <div className="sm-barrow" key={r.label} title={r.n != null ? `${r.n} post(s)` : ''}>
          <span className="t">{r.label}</span>
          <span className="b"><i style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: color }} /></span>
          <span className="n">{fmt ? fmt(r.value) : r.value}</span>
        </div>
      ))}
    </div>
  )
}

export function LineChart({ series, height = 170 }: { series: { name: string; color: string; points: { x: string; y: number }[] }[]; height?: number }) {
  const valid = series.filter(s => s.points.length >= 2)
  if (!valid.length) return <p className="sm-mut sm-xs">Pas assez de points pour tracer une courbe (il faut au moins 2 jours de données).</p>
  const xs = Array.from(new Set(valid.flatMap(s => s.points.map(p => p.x)))).sort()
  const ys = valid.flatMap(s => s.points.map(p => p.y))
  let min = Math.min(...ys), max = Math.max(...ys)
  if (min === max) { min -= 1; max += 1 }
  const W = 600, H = height, pt = 10, pb = 8
  const X = (x: string) => 6 + (xs.indexOf(x) / Math.max(1, xs.length - 1)) * (W - 12)
  const Y = (y: number) => pt + (1 - (y - min) / (max - min)) * (H - pt - pb)
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="sm-chart" style={{ height }}>
        {[0, 0.5, 1].map(t => <line key={t} x1={0} x2={W} y1={pt + t * (H - pt - pb)} y2={pt + t * (H - pt - pb)} stroke="#eef0f4" vectorEffect="non-scaling-stroke" />)}
        {valid.map(s => {
          const pts = s.points.map(p => `${X(p.x)},${Y(p.y)}`).join(' ')
          return <g key={s.name}>
            <polygon points={`${X(s.points[0].x)},${H - pb} ${pts} ${X(s.points[s.points.length - 1].x)},${H - pb}`} fill={s.color} opacity={0.07} />
            <polyline points={pts} fill="none" stroke={s.color} strokeWidth={2.5} strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
          </g>
        })}
      </svg>
      <div className="sm-row sm-xs sm-mut" style={{ justifyContent: 'space-between' }}><span>{xs[0]}</span><span>min {Math.round(min)} · max {Math.round(max)}</span><span>{xs[xs.length - 1]}</span></div>
      <div className="sm-legend">{valid.map(s => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
    </div>
  )
}

/* ───────── Image protégée par le token admin (chargée en blob, paresseusement) ───────── */


let _active = 0
const _wait: (() => void)[] = []
const acquire = () => new Promise<void>(res => { if (_active < 4) { _active++; res() } else _wait.push(() => { _active++; res() }) })
const release = () => { _active--; _wait.shift()?.() }

const blobCache = new Map<string, string>()
export function AuthImg({ path, alt = '', className, style }: { path: string; alt?: string; className?: string; style?: React.CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null)
  const [vis, setVis] = useState(false)
  const [src, setSrc] = useState<string | null>(blobCache.get(path) || null)
  const [bad, setBad] = useState(false)

  useEffect(() => { setSrc(blobCache.get(path) || null); setBad(false) }, [path])
  useEffect(() => {
    if (src || vis) return
    const el = ref.current
    if (!el || typeof IntersectionObserver === 'undefined') { setVis(true); return }
    const io = new IntersectionObserver(es => { if (es[0].isIntersecting) { setVis(true); io.disconnect() } }, { rootMargin: '250px' })
    io.observe(el)
    return () => io.disconnect()
  }, [src, vis])
  useEffect(() => {
    if (!vis || src || bad) return
    let alive = true
    const token = localStorage.getItem('admin_token')
    acquire().then(() =>
      fetch(`${BASE_URL}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
        .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.blob() })
        .then(b => { const u = URL.createObjectURL(b); blobCache.set(path, u); if (alive) setSrc(u) })
        .catch(() => { if (alive) setBad(true) })
        .finally(release))
    return () => { alive = false }
  }, [vis, src, bad, path])

  if (src) return <img src={src} alt={alt} className={className} style={style} />
  return <div ref={ref} className={`sm-imgph ${className || ''}`} style={style}>{bad ? '' : <Spinner />}</div>
}

/** Image de média publié : chemin relatif + message clair si le fichier est introuvable. */
export function MediaImg({ src, alt = '', className, style }: { src?: string | null; alt?: string; className?: string; style?: React.CSSProperties }) {
  const [bad, setBad] = useState(false)
  useEffect(() => { setBad(false) }, [src])
  const s = mediaSrc(src)
  if (!s || bad) return <div className={`sm-imgph ${className || ''}`} style={style} title={src || ''}>Visuel indisponible</div>
  return <img src={s} alt={alt} className={className} style={style} loading="lazy" onError={() => setBad(true)} />
}


/** Badge officiel « Powered by Groq » ; repli sur un pastille orange si l'image n'est pas joignable. */
export function GroqLogo({ height = 22 }: { height?: number }) {
  const [bad, setBad] = useState(false)
  if (!bad) return <img src="https://console.groq.com/powered-by-groq.svg" alt="Powered by Groq" height={height} style={{ display: 'block', height }} onError={() => setBad(true)} />
  return <span className="sm-groq"><span className="g">G</span><b>Groq</b></span>
}

export async function copyText(t: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(t); return true } catch {
    const a = document.createElement('textarea'); a.value = t; document.body.appendChild(a); a.select()
    const ok = document.execCommand('copy'); a.remove(); return ok
  }
}