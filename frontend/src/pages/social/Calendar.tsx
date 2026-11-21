// src/pages/social/Calendar.tsx
import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { dayKey, errMsg, fmtDateTime, hhmm, naiveUtc, PLATFORMS, pmeta, Post, social, Slot, BestTime } from '../../lib/social'
import { Badge, Empty, Loading, PageHead, PlatformDot, Pills, StatusBadge, useSocial } from './ui'
import { PostEditor } from './Posts'

const MONTHS = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
const DOW = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const MOVABLE = ['a_valider', 'programme', 'echec', 'brouillon']

export function Calendar() {
  const { tick, ok, err } = useSocial()
  const nav = useNavigate()
  const now = new Date()
  const [ym, setYm] = useState({ y: now.getUTCFullYear(), m: now.getUTCMonth() })
  const [view, setView] = useState<'mois' | 'liste'>('mois')
  const [plat, setPlat] = useState('')
  const [posts, setPosts] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState<string | null>(null)
  const [over, setOver] = useState('')
  const [sp, setSp] = useState('linkedin')
  const [side, setSide] = useState<{ slots: Slot[]; best: BestTime[] }>({ slots: [], best: [] })
  const [rev, setRev] = useState(0)

  const days = useMemo(() => {
    const first = new Date(Date.UTC(ym.y, ym.m, 1))
    const start = new Date(Date.UTC(ym.y, ym.m, 1 - ((first.getUTCDay() + 6) % 7)))
    return Array.from({ length: 42 }, (_, i) => new Date(start.getTime() + i * 86400000))
  }, [ym])

  useEffect(() => {
    let alive = true
    setLoading(true)
    social.calendar(naiveUtc(days[0]), naiveUtc(new Date(days[41].getTime() + 86400000)))
      .then(r => { if (alive) setPosts(r) }).catch(e => err(errMsg(e))).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, tick, rev])

  useEffect(() => {
    Promise.all([social.slots(sp, 3).catch(() => []), social.bestTimes(sp, 4).catch(() => [])]).then(([slots, best]) => setSide({ slots, best }))
  }, [sp, tick])

  const byDay = useMemo(() => {
    const m: Record<string, Post[]> = {}
    posts.filter(p => !plat || p.plateforme === plat).forEach(p => { const k = dayKey(p.scheduled_at); (m[k] = m[k] || []).push(p) })
    Object.values(m).forEach(a => a.sort((x, y) => (x.scheduled_at || '').localeCompare(y.scheduled_at || '')))
    return m
  }, [posts, plat])

  const today = dayKey(new Date().toISOString())
  const move = (m: number) => setYm(({ y, m: cur }) => { const d = new Date(Date.UTC(y, cur + m, 1)); return { y: d.getUTCFullYear(), m: d.getUTCMonth() } })

  const drop = async (key: string, id: string) => {
    setOver('')
    const p = posts.find(x => x.id === id)
    if (!p || !MOVABLE.includes(p.statut) || dayKey(p.scheduled_at) === key) return
    if (key < today && !window.confirm('Cette date est passée : le post sera replanifié au prochain créneau valide. Continuer ?')) return
    try { await social.patchPost(id, { scheduled_at: `${key}T${hhmm(p.scheduled_at) || '09:00'}` }); ok('Post déplacé'); setRev(r => r + 1) } catch (e) { err(errMsg(e)) }
  }

  const Chip = ({ p }: { p: Post }) => (
    <div className={`sm-ev${p.statut === 'publie' ? ' dim' : ''}`} style={{ borderColor: pmeta(p.plateforme).color }} draggable={MOVABLE.includes(p.statut)}
      onDragStart={e => e.dataTransfer.setData('text/plain', p.id)} onClick={() => setOpen(p.id)} title={p.contenu}>
      <b>{hhmm(p.scheduled_at)}</b><span>{p.contenu}</span>
    </div>
  )

  const listDays = Object.keys(byDay).sort()

  return (
    <div>
      <PageHead title="Calendrier éditorial" sub="Glisse-dépose un post pour le replanifier (l'heure est conservée).">
        <button className="sm-btn pri" onClick={() => nav('/social-agent/posts?new=1')}>+ Nouveau post</button>
      </PageHead>

      <div className="sm-row sm-mb" style={{ justifyContent: 'space-between' }}>
        <div className="sm-row">
          <button className="sm-btn" onClick={() => move(-1)}>◀</button>
          <h3 style={{ minWidth: 170, textAlign: 'center' }}>{MONTHS[ym.m]} {ym.y}</h3>
          <button className="sm-btn" onClick={() => move(1)}>▶</button>
          <button className="sm-btn" onClick={() => setYm({ y: now.getUTCFullYear(), m: now.getUTCMonth() })}>Aujourd'hui</button>
        </div>
        <div className="sm-row">
          <select className="sm-select" style={{ width: 160 }} value={plat} onChange={e => setPlat(e.target.value)}><option value="">Tous les réseaux</option>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select>
          <Pills items={[{ id: 'mois', label: 'Mois' }, { id: 'liste', label: 'Liste' }]} value={view} onChange={setView} />
        </div>
      </div>

      <div className="sm-grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 280px', alignItems: 'start' }}>
        <div>
          {loading && !posts.length ? <Loading /> : view === 'mois' ? (
            <div className="sm-cal">
              {DOW.map(d => <div key={d} className="sm-cal-w">{d}</div>)}
              {days.map(dt => {
                const key = dt.toISOString().slice(0, 10)
                const list = byDay[key] || []
                return (
                  <div key={key} className={`sm-day${dt.getUTCMonth() !== ym.m ? ' out' : ''}${key === today ? ' today' : ''}${over === key ? ' over' : ''}`}
                    onDragOver={e => { e.preventDefault(); setOver(key) }} onDragLeave={() => setOver('')}
                    onDrop={e => { e.preventDefault(); drop(key, e.dataTransfer.getData('text/plain')) }}>
                    <span className="n">{dt.getUTCDate()}</span>
                    {list.slice(0, 3).map(p => <Chip key={p.id} p={p} />)}
                    {list.length > 3 && <div className="sm-xs sm-mut" style={{ padding: '2px 6px' }}>+{list.length - 3} autres</div>}
                  </div>
                )
              })}
            </div>
          ) : !listDays.length ? <Empty title="Aucune publication ce mois-ci" /> : (
            <div>{listDays.map(k => (
              <div className="sm-card" key={k}><div className="sm-card-h"><h3>{new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' }).format(new Date(k + 'T00:00:00Z'))}</h3></div>
                <div className="sm-card-b"><div className="sm-list">{byDay[k].map(p => (
                  <div className="sm-item" key={p.id} style={{ cursor: 'pointer' }} onClick={() => setOpen(p.id)}>
                    <b style={{ width: 48 }}>{hhmm(p.scheduled_at)}</b><PlatformDot p={p.plateforme} />
                    <span className="sm-flex1" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.contenu}</span><StatusBadge s={p.statut} />
                  </div>))}</div></div></div>
            ))}</div>
          )}
          <div className="sm-row sm-mt sm-xs sm-mut">{PLATFORMS.map(p => <span key={p} className="sm-row" style={{ gap: 5 }}><PlatformDot p={p} />{pmeta(p).label}</span>)}</div>
        </div>

        <div className="sm-card"><div className="sm-card-h"><h3>Créneaux conseillés</h3></div><div className="sm-card-b">
          <select className="sm-select sm-mb" value={sp} onChange={e => setSp(e.target.value)}>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select>
          <p className="sm-label">Prochains créneaux libres</p>
          <div className="sm-list sm-mb">{side.slots.map(s => <div className="sm-item" key={s.scheduled_at} title={s.justification}><span className="sm-flex1">{fmtDateTime(s.scheduled_at)}</span><Badge tone="green">{Math.round(s.score * 100)}%</Badge></div>)}</div>
          <p className="sm-label">Meilleurs horaires</p>
          <div className="sm-chips">{side.best.map((b, i) => <Badge key={i} tone={b.observations ? 'green' : 'gray'}>{b.jour.slice(0, 3)} {b.heure}h</Badge>)}</div>
        </div></div>
      </div>

      {open && <PostEditor id={open} onClose={() => setOpen(null)} onChanged={() => setRev(r => r + 1)} />}
    </div>
  )
}