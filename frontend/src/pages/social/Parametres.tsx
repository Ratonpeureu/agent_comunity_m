// src/pages/social/Parametres.tsx
import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Compte, Configuration } from './Configuration'
import { ai, AiKey, AiOverview, Budget, Gauge, ModelInfo, RateInfo } from '../../lib/ai'
import { ALLOWED_FORMATS, errMsg, Format, FORMAT_LABEL, fmtDate, fmtDateTime, fmtNum, Platform, PLATFORMS, pmeta, social } from '../../lib/social'
import { social2 } from '../../lib/social2'
import { Badge, BarList, Empty, Field, GroqLogo, LineChart, Loading, Modal, PageHead, Pills, PlatformIcon, Spinner, Stat, Switch, useLoad, useSocial } from './ui'


type Tab = 'conso' | 'cles' | 'limites' | 'modeles' | 'formats' | 'config' | 'compte' | 'systeme'
const TABS: Tab[] = ['conso', 'cles', 'limites', 'modeles', 'formats', 'config', 'compte', 'systeme']

const ST: Record<string, { l: string; t: string }> = {
  actif: { l: 'Active', t: 'green' }, epuise: { l: 'Épuisée', t: 'amber' }, invalide: { l: 'Invalide', t: 'red' },
  expire: { l: 'Expirée', t: 'red' }, desactive: { l: 'Désactivée', t: 'gray' },
}
const GL: Record<string, string> = { tokens_jour: 'Tokens / jour', tokens_mois: 'Tokens / mois', requetes_jour: 'Requêtes / jour', cout_mois_usd: 'Coût / mois ($)' }

export function Parametres() {
  const { tick } = useSocial()
  const [sp] = useSearchParams()
  const first = sp.get('tab') as Tab | null
  const [tab, setTab] = useState<Tab>(first && TABS.includes(first) ? first : 'conso')
  const { data, loading, reload } = useLoad(() => ai.overview(), [tick])
  if (loading && !data) return <Loading />
  if (!data) return <Empty title="Données indisponibles">Impossible de charger les paramètres IA.</Empty>
  return (
    <div>
      <PageHead title="Paramètres" sub="Consommation réelle, budgets, clés API, modèles et formats par défaut.">
        <GroqLogo height={26} />
        <button className="sm-btn" onClick={reload}>Actualiser</button>
      </PageHead>
      {data.alertes.map((a, i) => <div key={i} className={a.niveau === 'err' ? 'sm-err' : 'sm-note'}>{a.texte}</div>)}
      <Pills<Tab> items={[{ id: 'conso', label: 'Consommation' }, { id: 'cles', label: 'Clés API' }, { id: 'limites', label: 'Budgets & limites' }, { id: 'modeles', label: 'Modèles & tarifs' }, { id: 'formats', label: 'Formats par défaut' }, { id: 'config', label: 'Configuration' }, { id: 'compte', label: 'Compte admin' }, { id: 'systeme', label: 'Système' }]} value={tab} onChange={setTab} />
      {tab === 'conso' && <Conso d={data} />}
      {tab === 'cles' && <Cles d={data} reload={reload} />}
      {tab === 'limites' && <Limites d={data} reload={reload} />}
      {tab === 'modeles' && <Modeles d={data} reload={reload} />}
      {tab === 'formats' && <Formats />}
      {tab === 'config' && <Configuration />}
      {tab === 'compte' && <Compte />}
      {tab === 'systeme' && <Systeme goConfig={() => setTab('config')} />}
    </div>
  )
}

/* ───────── Consommation ───────── */
function GaugeBar({ name, g, seuil }: { name: string; g: Gauge; seuil: number }) {
  const cost = name === 'cout_mois_usd'
  const f = (n: number) => (cost ? n.toFixed(2) : fmtNum(n))
  const col = g.pct >= 100 ? 'var(--err)' : g.pct >= seuil ? '#d97706' : 'var(--ok)'
  return (
    <div className="sm-gauge">
      <div className="top"><b>{GL[name]}</b><span>{f(g.used)} / {f(g.limit)} · {g.pct} %</span></div>
      <div className="sm-progress"><i style={{ width: `${Math.min(100, g.pct)}%`, background: col }} /></div>
    </div>
  )
}

function Conso({ d }: { d: AiOverview }) {
  const j = d.usage.jour, m = d.usage.mois
  return (
    <div>
      <div className="sm-info">Groq n'expose pas de solde de crédits par API : ces chiffres sont mesurés par l'application (champ <code>usage</code> de chaque réponse). Le solde et la facture réels restent sur console.groq.com.</div>
      <div className="sm-grid g4 sm-mb">
        <Stat label="Tokens aujourd'hui" value={fmtNum(j.tokens)} hint={`${fmtNum(j.prompt)} entrée · ${fmtNum(j.completion)} sortie`} />
        <Stat label="Requêtes aujourd'hui" value={fmtNum(j.requetes)} hint={j.erreurs ? `${j.erreurs} erreur(s)` : 'Aucune erreur'} trend={j.erreurs ? 'down' : 'up'} />
        <Stat label="Tokens ce mois" value={fmtNum(m.tokens)} hint={`${fmtNum(m.requetes)} requêtes`} />
        <Stat label="Coût estimé du mois" value={`${m.cout_usd.toFixed(2)} $`} hint={m.modeles_sans_prix.length ? `Tarif manquant : ${m.modeles_sans_prix.join(', ')}` : 'Selon tes tarifs'} trend={m.modeles_sans_prix.length ? 'down' : ''} />
      </div>
      {!!Object.keys(d.limites).length && (
        <div className="sm-card"><div className="sm-card-h"><h3>Limites configurées</h3></div><div className="sm-card-b">
          {Object.entries(d.limites).map(([k, g]) => <GaugeBar key={k} name={k} g={g} seuil={d.budget.alerte_pct} />)}
        </div></div>
      )}
      <div className="sm-card"><div className="sm-card-h"><h3>Tokens par jour (30 jours)</h3></div><div className="sm-card-b">
        <LineChart height={200} series={[{ name: 'Tokens', color: '#F55036', points: d.serie.map(s => ({ x: s.jour, y: s.tokens })) }]} />
      </div></div>
      <div className="sm-grid g2">
        <div className="sm-card"><div className="sm-card-h"><h3>Par modèle (mois)</h3></div><div className="sm-card-b">
          <BarList rows={d.par_modele.map(r => ({ label: r.modele || '?', value: r.tokens, n: r.requetes }))} fmt={fmtNum} color="#F55036" />
          {d.par_modele.map(r => <p key={r.modele} className="sm-xs sm-mut sm-mt">{r.modele} : {fmtNum(r.prompt)} entrée / {fmtNum(r.completion)} sortie · {r.cout_usd == null ? 'tarif non défini' : `${r.cout_usd.toFixed(4)} $`}</p>)}
        </div></div>
        <div className="sm-card"><div className="sm-card-h"><h3>Par clé (mois)</h3></div><div className="sm-card-b">
          {!d.par_cle.length ? <p className="sm-mut sm-xs">Aucune donnée.</p> : (
            <table className="sm-table"><thead><tr><th>Clé</th><th>Tokens</th><th>Req.</th><th>Erreurs</th></tr></thead>
              <tbody>{d.par_cle.map(c => <tr key={c.cle}><td>{c.cle}</td><td>{fmtNum(c.tokens)}</td><td>{fmtNum(c.requetes)}</td><td>{c.erreurs}</td></tr>)}</tbody></table>
          )}
        </div></div>
      </div>
      <div className="sm-card"><div className="sm-card-h"><h3>Derniers appels</h3></div><div className="sm-card-b" style={{ overflowX: 'auto' }}>
        {!d.derniers.length ? <p className="sm-mut sm-xs">Aucun appel enregistré pour l'instant.</p> : (
          <table className="sm-table"><thead><tr><th>Date</th><th>Type</th><th>Modèle</th><th>Clé</th><th>Tokens</th><th>État</th><th>Durée</th></tr></thead>
            <tbody>{d.derniers.map((r, i) => (
              <tr key={i}><td>{fmtDateTime(r.ts)}</td><td>{r.kind}</td><td>{r.modele}</td><td>{r.cle}</td><td>{fmtNum(r.tokens)}</td>
                <td>{r.ok ? <Badge tone="green">OK</Badge> : <span title={r.erreur}><Badge tone="red">{r.status || 'réseau'}</Badge></span>}</td><td>{r.ms} ms</td></tr>
            ))}</tbody></table>
        )}
      </div></div>
    </div>
  )
}

/* ───────── Clés API ───────── */
function Rl({ rl }: { rl: RateInfo | null }) {
  if (!rl) return <p className="sm-xs sm-mut">Limites Groq non mesurées : clique sur « Tester ».</p>
  return (
    <dl className="sm-kv sm-xs">
      <dt>Requêtes / jour</dt><dd>{rl.remaining_requests ?? '—'} restantes sur {rl.limit_requests ?? '—'} · reset dans {rl.reset_requests ?? '—'}</dd>
      <dt>Tokens / minute</dt><dd>{rl.remaining_tokens ?? '—'} restants sur {rl.limit_tokens ?? '—'} · reset dans {rl.reset_tokens ?? '—'}</dd>
    </dl>
  )
}

function Cles({ d, reload }: { d: AiOverview; reload: () => void }) {
  const { ok, err } = useSocial()
  const [label, setLabel] = useState(''); const [key, setKey] = useState(''); const [exp, setExp] = useState('')
  const [busy, setBusy] = useState(''); const [edit, setEdit] = useState<AiKey | null>(null)
  const all = [...d.env, ...d.cles]

  const add = async () => {
    setBusy('add')
    try { await ai.addKey({ label, key, expire_le: exp || null }); ok('Clé ajoutée (chiffrée)'); setLabel(''); setKey(''); setExp(''); reload() }
    catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const test = async (k: AiKey) => {
    setBusy(k.id)
    try { const r = await ai.testKey(k.id); r.ok ? ok(`Clé valide (${r.ms} ms, modèle ${r.modele})`) : err(`Clé refusée (${r.status}) : ${r.erreur || ''}`); reload() }
    catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const toggle = async (k: AiKey) => { try { await ai.patchKey(k.id, { statut: k.statut === 'desactive' ? 'actif' : 'desactive' }); reload() } catch (e) { err(errMsg(e)) } }
  const del = async (k: AiKey) => { if (!window.confirm(`Supprimer la clé « ${k.label} » ?`)) return; try { await ai.delKey(k.id); ok('Clé supprimée'); reload() } catch (e) { err(errMsg(e)) } }

  return (
    <div>
      <div className="sm-info">Les clés sont utilisées dans l'ordre. Une clé refusée (401/403) est marquée invalide, une clé qui a atteint son quota journalier est marquée épuisée jusqu'au reset, et l'application bascule automatiquement sur la suivante. La clé définie dans l'onglet Configuration sert de secours.</div>
      {!all.length && <Empty title="Aucune clé">Ajoute ta première clé Groq ci-dessous.</Empty>}
      {all.map(k => {
        const st = ST[k.statut] || { l: k.statut, t: 'gray' }
        return (
          <div className="sm-card" key={k.id}><div className="sm-card-b">
            <div className="sm-row" style={{ justifyContent: 'space-between' }}>
              <div className="sm-row"><GroqLogo height={18} /><b>{k.label}</b><code>•••• {k.last4}</code><Badge tone={st.t}>{st.l}</Badge>{k.source === 'setup' && <Badge>Configuration</Badge>}</div>
              <div className="sm-row">
                <button className="sm-btn xs" disabled={busy === k.id} onClick={() => test(k)}>{busy === k.id ? <Spinner /> : 'Tester'}</button>
                {k.source === 'pool' && <>
                  <button className="sm-btn xs" onClick={() => setEdit(k)}>Modifier</button>
                  <button className="sm-btn xs" onClick={() => toggle(k)}>{k.statut === 'desactive' ? 'Activer' : 'Désactiver'}</button>
                  <button className="sm-btn xs danger" onClick={() => del(k)}>Supprimer</button></>}
              </div>
            </div>
            <p className="sm-xs sm-mut sm-mt">
              {k.expire_le ? `Expire le ${fmtDate(k.expire_le)}` : 'Pas de date d\'expiration saisie'}
              {k.reset_at ? ` · réactivation automatique ${fmtDateTime(k.reset_at)}` : ''}
            </p>
            {k.erreur && <div className="sm-err sm-xs sm-mt">{k.erreur}</div>}
            <div className="sm-mt"><Rl rl={k.rl} /></div>
          </div></div>
        )
      })}
      <div className="sm-card"><div className="sm-card-h"><h3>Ajouter une clé</h3></div><div className="sm-card-b">
        <div className="sm-grid g3">
          <Field label="Nom"><input className="sm-input" value={label} onChange={e => setLabel(e.target.value)} placeholder="Compte principal" /></Field>
          <Field label="Clé API (gsk_…)"><input className="sm-input" type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} /></Field>
          <Field label="Date d'expiration (optionnel)" hint="Alerte 7 jours avant, désactivation automatique après."><input className="sm-input" type="date" value={exp} onChange={e => setExp(e.target.value)} /></Field>
        </div>
        <button className="sm-btn pri" disabled={busy === 'add' || key.trim().length < 20} onClick={add}>{busy === 'add' ? <Spinner /> : 'Ajouter'}</button>
      </div></div>
      {edit && <KeyEditor k={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload() }} />}
    </div>
  )
}

function KeyEditor({ k, onClose, onSaved }: { k: AiKey; onClose: () => void; onSaved: () => void }) {
  const { ok, err } = useSocial()
  const [label, setLabel] = useState(k.label); const [exp, setExp] = useState(k.expire_le || ''); const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { await ai.patchKey(k.id, { label, expire_le: exp || null }); ok('Clé mise à jour'); onSaved() } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title={`Modifier « ${k.label} »`} onClose={onClose} footer={<><button className="sm-btn" onClick={onClose}>Annuler</button><button className="sm-btn pri" disabled={busy} onClick={save}>{busy ? <Spinner /> : 'Enregistrer'}</button></>}>
      <Field label="Nom"><input className="sm-input" value={label} onChange={e => setLabel(e.target.value)} /></Field>
      <Field label="Date d'expiration" hint="Vide = aucune. Repousser la date réactive une clé expirée."><input className="sm-input" type="date" value={exp} onChange={e => setExp(e.target.value)} /></Field>
    </Modal>
  )
}

/* ───────── Budgets & limites ───────── */
function Limites({ d, reload }: { d: AiOverview; reload: () => void }) {
  const { ok, err } = useSocial()
  const [f, setF] = useState<Budget>({ ...d.budget }); const [ret, setRet] = useState(d.retention_jours); const [busy, setBusy] = useState(false)
  const num = (k: 'tokens_jour' | 'tokens_mois' | 'requetes_jour' | 'cout_mois_usd' | 'alerte_pct', step = 1) =>
    <input className="sm-input" type="number" min={0} step={step} value={f[k]} onChange={e => setF({ ...f, [k]: +e.target.value })} />
  const save = async () => {
    setBusy(true)
    try { await ai.saveSettings({ budget: f, retention_jours: ret }); ok('Limites enregistrées'); reload() } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <div className="sm-card"><div className="sm-card-b">
      <p className="sm-hint sm-mb">0 = illimité. Ces plafonds sont ceux de l'application, en plus des limites de ton plan Groq. Le jour est calculé en UTC (identique à Dakar).</p>
      <div className="sm-grid g2">
        <Field label="Tokens par jour"><>{num('tokens_jour')}</></Field>
        <Field label="Tokens par mois"><>{num('tokens_mois')}</></Field>
        <Field label="Requêtes par jour"><>{num('requetes_jour')}</></Field>
        <Field label="Budget mensuel estimé ($)" hint="Calculé avec les tarifs de l'onglet « Modèles & tarifs »."><>{num('cout_mois_usd', 0.5)}</></Field>
        <Field label="Seuil d'alerte (%)"><>{num('alerte_pct')}</></Field>
        <Field label="Conservation du journal (jours)"><input className="sm-input" type="number" min={7} max={3650} value={ret} onChange={e => setRet(+e.target.value)} /></Field>
      </div>
      <div className="sm-mb"><Switch checked={f.bloquer} onChange={v => setF({ ...f, bloquer: v })} label="Bloquer les appels IA quand une limite est atteinte" /></div>
      <p className="sm-hint sm-mb">Désactivé : les dépassements sont seulement signalés par une alerte.</p>
      <button className="sm-btn pri" disabled={busy} onClick={save}>{busy ? <Spinner /> : 'Enregistrer'}</button>
    </div></div>
  )
}

/* ───────── Modèles & tarifs ───────── */
function Modeles({ d, reload }: { d: AiOverview; reload: () => void }) {
  const { ok, err } = useSocial()
  const [t, setT] = useState(d.modeles.texte); const [v, setV] = useState(d.modeles.vision)
  const [rows, setRows] = useState(Object.entries(d.prix).map(([m, p]) => ({ m, in: p.in, out: p.out })))
  const [models, setModels] = useState<ModelInfo[]>([]); const [busy, setBusy] = useState('')
  const fetchModels = async () => { setBusy('m'); try { setModels(await ai.models()); ok('Liste récupérée depuis Groq') } catch (e) { err(errMsg(e)) } finally { setBusy('') } }
  const save = async () => {
    setBusy('s')
    try {
      const prix: Record<string, { in: number; out: number }> = {}
      rows.filter(r => r.m.trim()).forEach(r => { prix[r.m.trim()] = { in: +r.in || 0, out: +r.out || 0 } })
      await ai.saveSettings({ modeles: { texte: t, vision: v }, prix }); ok('Enregistré, actif immédiatement'); reload()
    } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  return (
    <div>
      <div className="sm-card"><div className="sm-card-h"><h3>Modèles utilisés</h3><button className="sm-btn xs" disabled={busy === 'm'} onClick={fetchModels}>{busy === 'm' ? <Spinner /> : 'Récupérer la liste depuis Groq'}</button></div><div className="sm-card-b">
        <datalist id="ai-models">{models.map(m => <option key={m.id} value={m.id}>{m.context_window ? `${m.context_window} tokens` : ''}</option>)}</datalist>
        <div className="sm-grid g2">
          <Field label="Modèle texte" hint={`Actuellement utilisé : ${d.modeles.texte_effectif || '—'}. Vide = valeur de la Configuration.`}>
            <input className="sm-input" list="ai-models" value={t} onChange={e => setT(e.target.value)} placeholder={d.modeles.texte_effectif} /></Field>
          <Field label="Modèle vision (analyse des captures)" hint={`Actuellement utilisé : ${d.modeles.vision_effectif || '—'}. Vide = valeur de la Configuration.`}>
            <input className="sm-input" list="ai-models" value={v} onChange={e => setV(e.target.value)} placeholder={d.modeles.vision_effectif} /></Field>
        </div>
      </div></div>
      <div className="sm-card"><div className="sm-card-h"><h3>Tarifs ($ par million de tokens)</h3></div><div className="sm-card-b">
        <p className="sm-hint sm-mb">Servent uniquement à estimer le coût. Vérifie les tarifs officiels sur console.groq.com/docs/pricing : ils ne sont pas lus automatiquement.</p>
        {rows.map((r, i) => (
          <div className="sm-row sm-mb" key={i}>
            <input className="sm-input sm-flex1" list="ai-models" placeholder="Modèle" value={r.m} onChange={e => setRows(rows.map((x, j) => (j === i ? { ...x, m: e.target.value } : x)))} />
            <input className="sm-input" style={{ width: 110 }} type="number" min={0} step={0.01} placeholder="Entrée" value={r.in} onChange={e => setRows(rows.map((x, j) => (j === i ? { ...x, in: +e.target.value } : x)))} />
            <input className="sm-input" style={{ width: 110 }} type="number" min={0} step={0.01} placeholder="Sortie" value={r.out} onChange={e => setRows(rows.map((x, j) => (j === i ? { ...x, out: +e.target.value } : x)))} />
            <button className="sm-btn xs danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>×</button>
          </div>
        ))}
        <div className="sm-row"><button className="sm-btn xs" onClick={() => setRows([...rows, { m: '', in: 0, out: 0 }])}>+ Ajouter un modèle</button>
          <button className="sm-btn pri" disabled={busy === 's'} onClick={save}>{busy === 's' ? <Spinner /> : 'Enregistrer'}</button></div>
      </div></div>
    </div>
  )
}

/* ───────── Formats par défaut (pilote automatique) ───────── */
function Formats() {
  const { ok, err } = useSocial()
  const { data: brand, loading } = useLoad(() => social.brand(), [])
  const [f, setF] = useState<Record<string, string>>({}); const [busy, setBusy] = useState(false)
  useEffect(() => { if (brand) setF({ ...(brand.config.formats_defaut || {}) }) }, [brand])
  if (loading && !brand) return <Loading />
  const save = async () => {
    setBusy(true)
    try { const clean: Record<string, string> = {}; Object.entries(f).forEach(([k, v]) => { if (v) clean[k] = v }); await social.saveBrand({ config: { formats_defaut: clean } }); ok('Formats par défaut enregistrés') }
    catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <div className="sm-card"><div className="sm-card-b">
      <p className="sm-hint sm-mb">Format utilisé quand tu ne le choisis pas toi-même (pilote automatique, ou « Rédiger » sans sélection). « Auto » laisse l'IA décider (TikTok reste en vidéo).</p>
      {PLATFORMS.map(p => (
        <div className="sm-item" key={p}>
          <PlatformIcon p={p} size={26} /><b style={{ width: 100 }}>{pmeta(p).label}</b>
          <select className="sm-select" style={{ maxWidth: 220 }} value={f[p] || ''} onChange={e => setF({ ...f, [p]: e.target.value })}>
            <option value="">Auto</option>
            {ALLOWED_FORMATS[p as Platform].map((x: Format) => <option key={x} value={x}>{FORMAT_LABEL[x]}</option>)}
          </select>
        </div>
      ))}
      <button className="sm-btn pri sm-mt" disabled={busy} onClick={save}>{busy ? <Spinner /> : 'Enregistrer'}</button>
    </div></div>
  )
}

/* ───────── Système ───────── */

function Systeme({ goConfig }: { goConfig: () => void }) {
  const { data, loading } = useLoad(() => social2.system(), [])
  if (loading && !data) return <Loading />
  if (!data) return <Empty title="Diagnostic indisponible" />
  const rows: [string, boolean, string][] = [
    ['ffmpeg (montage vidéo)', data.ffmpeg, 'Requis pour toutes les vidéos'],
    ['edge-tts (voix off)', data.edge_tts, 'Optionnel'],
    ['Clé IA détectée dans la configuration', data.llm, 'Les clés ajoutées dans l\'onglet « Clés API » fonctionnent aussi'],
    ['URL publique en HTTPS', data.public_https, data.public_base_url || 'PUBLIC_BASE_URL non défini : requis pour que les réseaux téléchargent images et vidéos'],
    ['Photos libres (Unsplash / Pexels)', data.unsplash, 'Optionnel'],
    ['QPost (TikTok)', data.qpost, 'Optionnel'],
    ['Serper (actualités)', data.serper, 'Optionnel'],
    ['Application Meta (App ID / Secret)', data.meta_app, 'Jetons Facebook/Instagram longue durée'],
  ]
  return (
    <div className="sm-card"><div className="sm-card-b">
      <div className="sm-list">{rows.map(([l, okv, h]) => (
        <div className="sm-item" key={l}><Badge tone={okv ? 'green' : 'gray'}>{okv ? 'OK' : 'Absent'}</Badge><b className="sm-flex1">{l}</b><span className="sm-xs sm-mut">{h}</span></div>
      ))}</div>
      <p className="sm-hint sm-mt">Les clés et variables d'environnement se modifient dans <button className="sm-btn xs" onClick={goConfig}>l'onglet Configuration</button>.</p>
    </div></div>
  )
}