// src/pages/social/Overview.tsx
import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errMsg, fmtDateTime, fmtNum, fmtPct, naiveUtc, PLATFORMS, pmeta, Post, prettify, social } from '../../lib/social'
import { Badge, Empty, LineChart, Loading, PageHead, PlatformDot, ScoreRing, Stat, StatusBadge, Switch, useLoad, useSocial } from './ui'

const COLORS: Record<string, string> = { linkedin: '#0A66C2', facebook: '#1877F2', instagram: '#D6249F', tiktok: '#111827' }

export function Overview() {
  const { tick, runJob, ok, err } = useSocial()
  const nav = useNavigate()
  const [busy, setBusy] = useState('')

  const { data, loading, reload } = useLoad(async () => {
    const now = new Date()
    const [brand, accounts, toValidate, upcoming, ov, assets] = await Promise.all([
      social.brand().catch(() => null),
      social.accounts().catch(() => []),
      social.posts({ statut: 'a_valider', limit: 6 }).catch(() => [] as Post[]),
      social.calendar(naiveUtc(now), naiveUtc(new Date(now.getTime() + 14 * 86400000))).catch(() => [] as Post[]),
      social.overview(30).catch(() => null),
      social.assets.list({ include_excluded: false }).catch(() => []),
    ])
    const times: Record<string, any[]> = {}
    await Promise.all(PLATFORMS.map(async p => { times[p] = await social.bestTimes(p, 3).catch(() => []) }))
    return { brand, accounts, toValidate, upcoming: upcoming.filter(p => p.statut === 'programme').slice(0, 6), ov, assets, times }
  }, [tick])

  if (loading && !data) return <Loading />
  const d = data!
  const cfg = d.brand?.config || {}
  const connected = d.accounts.filter(a => a.connecte)
  const steps = [
    { done: d.brand?.statut_analyse === 'pret', label: 'Faire analyser la marque (site, ton, piliers)', to: '/social-agent/brand' },
    { done: connected.length > 0, label: 'Connecter au moins un réseau social', to: '/social-agent/accounts' },
    { done: d.assets.length > 0, label: 'Analyser les captures du logiciel', to: '/social-agent/library' },
    { done: (d.ov?.nb_posts || 0) > 0 || d.toValidate.length > 0 || d.upcoming.length > 0, label: 'Générer des idées et créer un premier post', to: '/social-agent/ideas' },
  ]
  const doneCount = steps.filter(s => s.done).length

  const ov = d.ov
  const tot = ov?.totaux || {}
  const inter = (tot.likes || 0) + (tot.comments || 0) + (tot.shares || 0) + (tot.saves || 0)
  const growth: Record<string, any> = ov?.croissance || {}
  const followers = Object.values(growth).reduce((s: number, g: any) => s + (g.followers || 0), 0)
  const evo = ov?.evolution_er_vs_periode_precedente_pct

  const setCfg = async (k: string, v: boolean) => {
    try { await social.saveBrand({ config: { [k]: v } }); ok('Réglage enregistré'); reload() } catch (e) { err(errMsg(e)) }
  }
  const validate = async (id: string) => {
    setBusy(id)
    try { await social.validate(id); ok('Post validé et programmé'); reload() } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }

  return (
    <div>
      <PageHead title="Agent social media" sub="Ton community manager IA : il apprend ta marque, propose, rédige, programme et mesure.">
        <button className="sm-btn" onClick={() => runJob('Synchronisation des métriques', () => social.syncMetrics())}>Synchroniser les stats</button>
        <button className="sm-btn pri" onClick={() => runJob('Pilote automatique', () => social.autopilot())}>Lancer le pilote auto</button>
      </PageHead>

      {doneCount < steps.length && (
        <div className="sm-card"><div className="sm-card-b">
          <div className="sm-row" style={{ justifyContent: 'space-between' }}>
            <h3>Démarrage — {doneCount}/{steps.length}</h3><span className="sm-mut sm-xs">Quelques minutes pour être opérationnel</span>
          </div>
          <div className="sm-progress sm-mb sm-mt"><i style={{ width: `${(doneCount / steps.length) * 100}%` }} /></div>
          {steps.map(s => (
            <div key={s.label} className={`sm-check${s.done ? ' done' : ''}`}>
              <div className="c">✓</div><span className="sm-flex1">{s.label}</span>
              {!s.done && <Link className="sm-btn xs" to={s.to}>Ouvrir</Link>}
            </div>
          ))}
        </div></div>
      )}

      <div className="sm-grid g4 sm-mb">
        <Stat label="Posts publiés (30 j)" value={fmtNum(ov?.nb_posts || 0)} />
        <Stat label="Engagement moyen" value={fmtPct(ov?.er_moyen)} hint={evo != null ? `${evo > 0 ? '▲' : '▼'} ${Math.abs(evo)} % vs période préc.` : 'Pas de comparaison'} trend={evo == null ? '' : evo >= 0 ? 'up' : 'down'} />
        <Stat label="Impressions / portée" value={fmtNum(tot.impressions)} hint={`Portée ${fmtNum(tot.reach)}`} />
        <Stat label="Interactions · Abonnés" value={`${fmtNum(inter)}`} hint={`${fmtNum(followers)} abonnés au total`} />
      </div>

      <div className="sm-grid g2">
        <div className="sm-card">
          <div className="sm-card-h"><h3>À valider ({d.toValidate.length})</h3><Link className="sm-btn xs" to="/social-agent/posts?statut=a_valider">Tout voir</Link></div>
          <div className="sm-card-b">
            {!d.toValidate.length ? <Empty title="Rien en attente">Génère des idées, l'agent rédige, tu valides ici.</Empty> : (
              <div className="sm-list">
                {d.toValidate.map(p => (
                  <div className="sm-item" key={p.id}>
                    <PlatformDot p={p.plateforme} />
                    <div className="sm-flex1" style={{ minWidth: 0, cursor: 'pointer' }} onClick={() => nav(`/social-agent/posts?open=${p.id}`)}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.contenu}</div>
                      <div className="sm-xs sm-mut">{fmtDateTime(p.scheduled_at)}</div>
                    </div>
                    {p.prediction && <ScoreRing size={34} value={p.prediction.score_global} />}
                    <button className="sm-btn ok xs" disabled={busy === p.id} onClick={() => validate(p.id)}>Valider</button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="sm-card">
          <div className="sm-card-h"><h3>Prochaines publications</h3><Link className="sm-btn xs" to="/social-agent/calendar">Calendrier</Link></div>
          <div className="sm-card-b">
            {!d.upcoming.length ? <Empty title="Aucune publication programmée" /> : (
              <div className="sm-list">
                {d.upcoming.map(p => (
                  <div className="sm-item" key={p.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/social-agent/posts?open=${p.id}`)}>
                    <PlatformDot p={p.plateforme} />
                    <div className="sm-flex1" style={{ minWidth: 0 }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.contenu}</div>
                      <div className="sm-xs sm-mut">{fmtDateTime(p.scheduled_at)}</div>
                    </div>
                    <StatusBadge s={p.statut} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="sm-grid g2">
        <div className="sm-card">
          <div className="sm-card-h"><h3>Pilote automatique</h3>{cfg.autopilot_actif ? <Badge tone="green">Actif</Badge> : <Badge>Inactif</Badge>}</div>
          <div className="sm-card-b">
            <p className="sm-mut sm-mb">Chaque lundi à 7 h : rapport de performance, idées, rédaction des posts de la semaine.</p>
            <div className="sm-mb"><Switch checked={!!cfg.autopilot_actif} onChange={v => setCfg('autopilot_actif', v)} label="Activer le pilote hebdomadaire" /></div>
            <div className="sm-mb"><Switch checked={cfg.validation_requise !== false} onChange={v => setCfg('validation_requise', v)} label="Je valide chaque post avant publication" /></div>
            <Switch checked={!!cfg.autopilot_publication_directe} disabled={cfg.validation_requise !== false}
              onChange={v => { if (!v || window.confirm("L'agent publiera SANS ta validation. Confirmer ?")) setCfg('autopilot_publication_directe', v) }}
              label="Publication directe (sans validation)" />
            {cfg.validation_requise === false && cfg.autopilot_publication_directe && <p className="sm-note sm-mt">Publication directe active : relis régulièrement les posts publiés.</p>}
          </div>
        </div>

        <div className="sm-card">
          <div className="sm-card-h"><h3>Meilleurs créneaux</h3><Link className="sm-btn xs" to="/social-agent/analytics">Détails</Link></div>
          <div className="sm-card-b">
            {PLATFORMS.map(p => (
              <div className="sm-item" key={p}>
                <PlatformDot p={p} /><b style={{ width: 80 }}>{pmeta(p).label}</b>
                <div className="sm-chips sm-flex1">
                  {(d.times[p] || []).slice(0, 3).map((t, i) => <Badge key={i} tone={t.observations ? 'green' : 'gray'}>{t.jour.slice(0, 3)} {t.heure}h</Badge>)}
                </div>
              </div>
            ))}
            <p className="sm-hint sm-mt">Vert = déduit de tes propres stats, gris = référence sectorielle (démarrage).</p>
          </div>
        </div>
      </div>

      <div className="sm-grid g2">
        <div className="sm-card">
          <div className="sm-card-h"><h3>Croissance des abonnés</h3></div>
          <div className="sm-card-b">
            <LineChart series={Object.entries(growth).map(([p, g]: [string, any]) => ({ name: pmeta(p).label, color: COLORS[p] || '#4f46e5', points: (g.serie || []).map((s: any) => ({ x: s.jour, y: s.followers })) }))} />
          </div>
        </div>
        <div className="sm-card">
          <div className="sm-card-h"><h3>Top posts (30 j)</h3></div>
          <div className="sm-card-b">
            {!(ov?.top_posts || []).length ? <Empty title="Pas encore de statistiques">Les métriques sont collectées automatiquement après publication.</Empty> : (
              <div className="sm-list">
                {ov.top_posts.map((t: any) => (
                  <div className="sm-item" key={t.id} style={{ cursor: 'pointer' }} onClick={() => nav(`/social-agent/posts?open=${t.id}`)}>
                    <PlatformDot p={t.plateforme} />
                    <div className="sm-flex1" style={{ minWidth: 0 }}>
                      <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.extrait}</div>
                      <div className="sm-xs sm-mut">{prettify(t.pilier)}</div>
                    </div>
                    <Badge tone="green">{fmtPct(t.er)}</Badge>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {!!d.brand?.apprentissages?.length && (
        <div className="sm-card">
          <div className="sm-card-h"><h3>Ce que l'agent a appris</h3></div>
          <div className="sm-card-b">
            <div className="sm-list">
              {d.brand.apprentissages.slice(-5).reverse().map((a, i) => <div className="sm-item" key={i}><Badge tone="violet">{prettify(a.type)}</Badge><span>{a.texte}</span></div>)}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}