// src/pages/social/Analytics.tsx
import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BestTime, errMsg, fmtDate, fmtDateTime, fmtNum, fmtPct, Platform, PLATFORMS, pmeta, Prediction, prettify, Slot, social } from '../../lib/social'
import { Badge, BarList, Empty, Field, LineChart, Loading, PageHead, PlatformDot, Pills, Spinner, Stat, TagInput, useLoad, useSocial } from './ui'
import { PredictionCard } from './Posts'

type Tab = 'perf' | 'slots' | 'growth' | 'reports' | 'sim'
const COLORS: Record<string, string> = { linkedin: '#0A66C2', facebook: '#1877F2', instagram: '#D6249F', tiktok: '#111827' }

export function Analytics() {
  const [tab, setTab] = useState<Tab>('perf')
  return (
    <div>
      <PageHead title="Analytics & prédictions" sub="Performance réelle, créneaux optimaux, croissance, rapports IA et simulateur." />
      <Pills<Tab> items={[{ id: 'perf', label: 'Performance' }, { id: 'slots', label: 'Créneaux' }, { id: 'growth', label: 'Croissance' }, { id: 'reports', label: 'Rapports IA' }, { id: 'sim', label: 'Simulateur' }]} value={tab} onChange={setTab} />
      {tab === 'perf' && <Perf />}{tab === 'slots' && <Slots />}{tab === 'growth' && <Growth />}{tab === 'reports' && <Reports />}{tab === 'sim' && <Simulator />}
    </div>
  )
}

/* ───────── Performance ───────── */
function Perf() {
  const { tick } = useSocial()
  const nav = useNavigate()
  const [days, setDays] = useState('30')
  const { data, loading } = useLoad(async () => ({ ov: await social.overview(+days), rep: await social.assets.report().catch(() => null) }), [days, tick])
  if (loading && !data) return <Loading />
  const ov = data!.ov, rep = data!.rep
  const t = ov.totaux || {}
  const rows = (o: Record<string, any> | undefined, lab?: (k: string) => string) => Object.entries(o || {}).map(([k, v]: [string, any]) => ({ label: lab ? lab(k) : prettify(k), value: v.er_moyen, n: v.n })).sort((a, b) => b.value - a.value)
  const evo = ov.evolution_er_vs_periode_precedente_pct
  return (
    <div>
      <Pills items={[{ id: '7', label: '7 jours' }, { id: '30', label: '30 jours' }, { id: '90', label: '90 jours' }, { id: '180', label: '6 mois' }, { id: '365', label: '1 an' }]} value={days} onChange={setDays} />
      {!ov.nb_posts ? <Empty title="Pas encore de posts publiés sur la période">Les statistiques apparaissent après la première publication (collecte automatique toutes les 3 h).</Empty> : <>
        <div className="sm-grid g4 sm-mb">
          <Stat label="Posts publiés" value={ov.nb_posts} />
          <Stat label="Engagement moyen" value={fmtPct(ov.er_moyen)} hint={evo != null ? `${evo >= 0 ? '▲' : '▼'} ${Math.abs(evo)} % vs période préc.` : ''} trend={evo == null ? '' : evo >= 0 ? 'up' : 'down'} />
          <Stat label="Impressions" value={fmtNum(t.impressions)} hint={`Portée ${fmtNum(t.reach)}`} />
          <Stat label="Clics" value={fmtNum(t.clicks)} hint={`${fmtNum(t.saves)} enregistrements`} />
        </div>
        <div className="sm-grid g4 sm-mb">
          <Stat label="J'aime" value={fmtNum(t.likes)} /><Stat label="Commentaires" value={fmtNum(t.comments)} /><Stat label="Partages" value={fmtNum(t.shares)} />
          <div className="sm-stat"><div className="l">Tendance par réseau</div><div className="sm-chips" style={{ marginTop: 8 }}>{Object.entries(ov.tendance || {}).map(([p, v]) => <Badge key={p} tone={v === 'hausse' ? 'green' : v === 'baisse' ? 'red' : 'gray'}>{pmeta(p).label} {v === 'hausse' ? '▲' : v === 'baisse' ? '▼' : '='}</Badge>)}</div></div>
        </div>
        <div className="sm-grid g2">
          <div className="sm-card"><div className="sm-card-h"><h3>Engagement par réseau</h3></div><div className="sm-card-b"><BarList rows={rows(ov.par_plateforme, k => pmeta(k).label)} fmt={fmtPct} /></div></div>
          <div className="sm-card"><div className="sm-card-h"><h3>Par pilier éditorial</h3></div><div className="sm-card-b"><BarList rows={rows(ov.par_pilier)} fmt={fmtPct} /></div></div>
          <div className="sm-card"><div className="sm-card-h"><h3>Par format</h3></div><div className="sm-card-b"><BarList rows={rows(ov.par_format)} fmt={fmtPct} color="#0891b2" /></div></div>
          <div className="sm-card"><div className="sm-card-h"><h3>Par tranche horaire</h3></div><div className="sm-card-b"><BarList rows={rows(ov.par_tranche_horaire)} fmt={fmtPct} color="#d97706" /></div></div>
          <div className="sm-card"><div className="sm-card-h"><h3>Par type de visuel</h3></div><div className="sm-card-b"><BarList rows={rows(ov.par_visuel)} fmt={fmtPct} color="#7c3aed" /></div></div>
          <div className="sm-card"><div className="sm-card-h"><h3>Par module du logiciel (captures)</h3></div><div className="sm-card-b"><BarList rows={rows(rep?.par_module)} fmt={fmtPct} color="#059669" /></div></div>
        </div>
        <div className="sm-grid g2">
          <PostList title="Meilleurs posts" rows={ov.top_posts} onOpen={id => nav(`/social-agent/posts?open=${id}`)} />
          <PostList title="Posts à analyser (moins bons)" rows={ov.flop_posts} onOpen={id => nav(`/social-agent/posts?open=${id}`)} />
        </div>
        {!!ov.anomalies?.length && <div className="sm-card"><div className="sm-card-h"><h3>Anomalies détectées</h3></div><div className="sm-card-b"><div className="sm-list">
          {ov.anomalies.map((a: any) => <div className="sm-item" key={a.post_id} style={{ cursor: 'pointer' }} onClick={() => nav(`/social-agent/posts?open=${a.post_id}`)}><PlatformDot p={a.plateforme} /><Badge tone={a.type === 'surperformance' ? 'green' : 'red'}>{prettify(a.type)}</Badge><span className="sm-mut">z = {a.z}</span></div>)}
        </div></div></div>}
      </>}
    </div>
  )
}
function PostList({ title, rows, onOpen }: { title: string; rows?: any[]; onOpen: (id: string) => void }) {
  return (
    <div className="sm-card"><div className="sm-card-h"><h3>{title}</h3></div><div className="sm-card-b">
      {!rows?.length ? <p className="sm-mut">—</p> : <div className="sm-list">{rows.map(r => (
        <div className="sm-item" key={r.id} style={{ cursor: 'pointer' }} onClick={() => onOpen(r.id)}><PlatformDot p={r.plateforme} />
          <span className="sm-flex1" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.extrait}</span><Badge tone="blue">{fmtPct(r.er)}</Badge></div>))}</div>}
    </div></div>
  )
}

/* ───────── Créneaux ───────── */
function Slots() {
  const { tick } = useSocial()
  const [p, setP] = useState<Platform>('linkedin')
  const { data, loading } = useLoad(async () => ({ grid: await social.bestTimes(p, 200), slots: await social.slots(p, 5).catch(() => [] as Slot[]) }), [p, tick])
  const J = ['lundi', 'mardi', 'mercredi', 'jeudi', 'vendredi', 'samedi', 'dimanche']
  const hours = Array.from({ length: 17 }, (_, i) => i + 6)
  const map = new Map<string, BestTime>()
  data?.grid.forEach(b => map.set(`${b.weekday}-${b.heure}`, b))
  return (
    <div>
      <div className="sm-chips sm-mb">{PLATFORMS.map(x => <button key={x} className={`sm-chip pl${p === x ? ' on' : ''}`} onClick={() => setP(x)}>{pmeta(x).label}</button>)}</div>
      {loading && !data ? <Loading /> : <>
        <div className="sm-card"><div className="sm-card-h"><h3>Carte des meilleurs horaires — {pmeta(p).label}</h3></div><div className="sm-card-b">
          <div className="sm-heat">
            <span />{hours.map(h => <span key={h} className="h">{h}h</span>)}
            {J.map((j, wd) => <React.Fragment key={j}><span className="l">{j.slice(0, 3)}</span>
              {hours.map(h => { const b = map.get(`${wd}-${h}`); const s = b?.score || 0
                return <span key={h} className="c" title={`${j} ${h}h — score ${s}${b?.observations ? ` (${b.observations} obs.)` : ' (référence sectorielle)'}`}
                  style={{ background: `rgba(79,70,229,${Math.min(1, s * 1.05)})`, outline: b?.observations ? '2px solid #059669' : undefined }} /> })}</React.Fragment>)}
          </div>
          <p className="sm-hint sm-mt">Plus c'est foncé, meilleur est le créneau. Contour vert = calculé avec tes propres données ; sinon c'est la référence sectorielle (elle est remplacée progressivement par tes stats).</p>
        </div></div>
        <div className="sm-card"><div className="sm-card-h"><h3>Prochains créneaux recommandés</h3></div><div className="sm-card-b"><div className="sm-list">
          {data!.slots.map(s => <div className="sm-item" key={s.scheduled_at}><b style={{ width: 150 }}>{fmtDateTime(s.scheduled_at)}</b><span className="sm-flex1 sm-mut">{s.justification}</span><Badge tone="green">{Math.round(s.score * 100)}%</Badge></div>)}
        </div></div></div>
      </>}
    </div>
  )
}

/* ───────── Croissance ───────── */
function Growth() {
  const { tick } = useSocial()
  const [days, setDays] = useState('60')
  const { data, loading } = useLoad(() => social.growth(+days), [days, tick])
  const entries = Object.entries(data || {})
  return (
    <div>
      <Pills items={[{ id: '30', label: '30 jours' }, { id: '60', label: '60 jours' }, { id: '180', label: '6 mois' }]} value={days} onChange={setDays} />
      {loading && !data ? <Loading /> : !entries.length ? <Empty title="Pas encore d'historique d'abonnés">Un instantané est pris chaque nuit pour chaque compte connecté.</Empty> : <>
        <div className="sm-grid g4 sm-mb">
          {entries.map(([p, g]: [string, any]) => <Stat key={p} label={pmeta(p).label} value={fmtNum(g.followers)} hint={`${g.delta >= 0 ? '+' : ''}${g.delta} (${g.delta_pct ?? 0} %) · proj. 30 j : ${fmtNum(g.projection_30j)}`} trend={g.delta >= 0 ? 'up' : 'down'} />)}
        </div>
        <div className="sm-card"><div className="sm-card-h"><h3>Évolution des abonnés</h3></div><div className="sm-card-b">
          <LineChart height={240} series={entries.map(([p, g]: [string, any]) => ({ name: pmeta(p).label, color: COLORS[p] || '#4f46e5', points: (g.serie || []).map((s: any) => ({ x: s.jour, y: s.followers })) }))} />
        </div></div>
      </>}
    </div>
  )
}

/* ───────── Rapports IA ───────── */
function Reports() {
  const { tick, runJob, ok, err } = useSocial()
  const [days, setDays] = useState('30')
  const { data, loading } = useLoad(() => social.reports(10), [tick])
  const apply = async (c: Record<string, number>) => { try { await social.saveBrand({ config: { cadence_hebdo: c } }); ok('Cadence appliquée') } catch (e) { err(errMsg(e)) } }
  return (
    <div>
      <div className="sm-row sm-mb">
        <select className="sm-select" style={{ width: 160 }} value={days} onChange={e => setDays(e.target.value)}><option value="14">14 jours</option><option value="30">30 jours</option><option value="90">90 jours</option></select>
        <button className="sm-btn pri" onClick={() => runJob('Rapport de performance', () => social.genReport(+days))}>Générer un rapport IA</button>
      </div>
      {loading && !data ? <Loading /> : !data?.length ? <Empty title="Aucun rapport">Le rapport analyse tes stats réelles et en tire des apprentissages réinjectés dans les prochains posts.</Empty> : data.map((r, idx) => {
        const a = r.analyse || {}
        return (
          <details className="sm-card" key={r.id} open={idx === 0}>
            <summary className="sm-card-h" style={{ cursor: 'pointer' }}><h3>Rapport du {fmtDate(r.periode_debut)} au {fmtDate(r.periode_fin)}</h3><span className="sm-xs sm-mut">{r.faits?.nb_posts} posts</span></summary>
            <div className="sm-card-b">
              <p className="sm-mb" style={{ fontSize: 15 }}>{a.resume}</p>
              <div className="sm-grid g2">
                <div><p className="sm-label" style={{ color: 'var(--ok)' }}>Ce qui marche</p><ul style={{ paddingLeft: 18 }}>{(a.ce_qui_marche || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
                <div><p className="sm-label" style={{ color: 'var(--err)' }}>Ce qui ne marche pas</p><ul style={{ paddingLeft: 18 }}>{(a.ce_qui_ne_marche_pas || []).map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></div>
              </div>
              <p className="sm-label sm-mt">Recommandations</p>
              <div className="sm-list">{(a.recommandations || []).map((x: any, i: number) => <div className="sm-item" key={i}><Badge tone={x.priorite === 'haute' ? 'red' : x.priorite === 'moyenne' ? 'amber' : 'gray'}>{x.priorite}</Badge><div><b>{x.action}</b><div className="sm-xs sm-mut">{x.impact_attendu}</div></div></div>)}</div>
              {!!a.hypotheses_a_tester?.length && <><p className="sm-label sm-mt">Hypothèses à tester</p><ul style={{ paddingLeft: 18 }}>{a.hypotheses_a_tester.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></>}
              {a.cadence_recommandee && <div className="sm-info sm-mt sm-row">Cadence conseillée / semaine : {Object.entries(a.cadence_recommandee).map(([p, n]) => `${pmeta(p).label} ${n}`).join(' · ')}<span className="sm-flex1" /><button className="sm-btn xs pri" onClick={() => apply(a.cadence_recommandee)}>Appliquer</button></div>}
              {!!a.apprentissages_a_retenir?.length && <><p className="sm-label sm-mt">Retenu par l'agent</p><div className="sm-chips">{a.apprentissages_a_retenir.map((x: string, i: number) => <Badge key={i} tone="violet">{x}</Badge>)}</div></>}
            </div>
          </details>
        )
      })}
    </div>
  )
}

/* ───────── Simulateur ───────── */
function Simulator() {
  const { err } = useSocial()
  const [pl, setPl] = useState<Platform>('linkedin'); const [txt, setTxt] = useState(''); const [tags, setTags] = useState<string[]>([])
  const [fmt, setFmt] = useState('texte'); const [media, setMedia] = useState(false); const [when, setWhen] = useState(''); const [pilier, setPilier] = useState('')
  const [res, setRes] = useState<Prediction | null>(null); const [busy, setBusy] = useState(false)
  const { data: brand } = useLoad(() => social.brand(), [])
  const go = async () => {
    setBusy(true)
    try { setRes(await social.predict({ plateforme: pl, contenu: txt, hashtags: tags, media_urls: media ? ['x.jpg'] : [], pilier, format: fmt, scheduled_at: when || null })) } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <div className="sm-split">
      <div className="sm-card"><div className="sm-card-b">
        <div className="sm-grid g2">
          <Field label="Réseau"><select className="sm-select" value={pl} onChange={e => setPl(e.target.value as Platform)}>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select></Field>
          <Field label="Pilier"><select className="sm-select" value={pilier} onChange={e => setPilier(e.target.value)}><option value="">—</option>{(brand?.piliers || []).map(p => <option key={p.code} value={p.code}>{p.titre}</option>)}</select></Field>
          <Field label="Format"><select className="sm-select" value={fmt} onChange={e => setFmt(e.target.value)}>{['texte', 'image', 'carrousel', 'video'].map(f => <option key={f}>{f}</option>)}</select></Field>
          <Field label="Date (Dakar)"><input className="sm-input" type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} /></Field>
        </div>
        <Field label="Texte du post"><textarea className="sm-textarea" style={{ minHeight: 160 }} value={txt} onChange={e => setTxt(e.target.value)} /></Field>
        <Field label="Hashtags"><TagInput hash value={tags} onChange={setTags} /></Field>
        <label className="sm-switch sm-mb"><input type="checkbox" checked={media} onChange={e => setMedia(e.target.checked)} /><span /><em>Avec visuel</em></label><br />
        <button className="sm-btn pri sm-mt" disabled={busy || !txt.trim()} onClick={go}>{busy ? <Spinner /> : 'Prédire la performance'}</button>
      </div></div>
      <div>{res ? <PredictionCard p={res} /> : <Empty title="Simulateur">Teste un texte, un horaire ou un format avant de publier : la prédiction s'appuie sur ton historique.</Empty>}</div>
    </div>
  )
}