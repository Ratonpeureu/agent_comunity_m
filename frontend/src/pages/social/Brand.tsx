// src/pages/social/Brand.tsx
import React, { useEffect, useState } from 'react'
import { asArr, Brand as BrandT, errMsg, fmtDate, pmeta, PLATFORMS, prettify, social } from '../../lib/social'
import { Badge, Empty, Field, Loading, PageHead, PlatformPicker, Pills, Spinner, Switch, TagInput, useLoad, useSocial } from './ui'

type Tab = 'site' | 'identite' | 'voix' | 'piliers' | 'exemples' | 'reglages'
const ANALYSE: Record<string, { l: string; t: string }> = { non_analyse: { l: 'Non analysée', t: 'gray' }, en_cours: { l: 'Analyse en cours', t: 'amber' }, pret: { l: 'Analysée', t: 'green' }, erreur: { l: 'Erreur', t: 'red' } }

export function Brand() {
  const { tick, runJob, ok, err } = useSocial()
  const [tab, setTab] = useState<Tab>('site')
  const { data, loading, reload } = useLoad(() => social.brand(), [tick])
  const [b, setB] = useState<BrandT | null>(null)
  const [saving, setSaving] = useState(false)
  useEffect(() => { if (data) setB(JSON.parse(JSON.stringify(data))) }, [data])
  if (loading && !b) return <Loading />
  if (!b) return null

  const sec = (s: 'identite' | 'ton' | 'config', k: string, v: unknown) => setB({ ...b, [s]: { ...(b[s] as object), [k]: v } } as BrandT)
  const save = async (patch: Record<string, unknown>, msg = 'Enregistré') => {
    setSaving(true)
    try { await social.saveBrand(patch); ok(msg); reload() } catch (e) { err(errMsg(e)) } finally { setSaving(false) }
  }
  const st = ANALYSE[b.statut_analyse] || ANALYSE.non_analyse
  const SaveBtn = ({ patch }: { patch: Record<string, unknown> }) => <button className="sm-btn pri" disabled={saving} onClick={() => save(patch)}>{saving ? <Spinner /> : 'Enregistrer'}</button>

  return (
    <div>
      <PageHead title={`Marque — ${b.nom}`} sub="C'est ici que l'agent apprend qui tu es. Plus c'est précis, plus les posts sonnent comme toi.">
        <Badge tone={st.t}>{st.l}</Badge>
      </PageHead>
      <Pills<Tab> items={[{ id: 'site', label: 'Site & analyse' }, { id: 'identite', label: 'Identité' }, { id: 'voix', label: 'Voix & ton' }, { id: 'piliers', label: 'Piliers' }, { id: 'exemples', label: 'Exemples & apprentissages' }, { id: 'reglages', label: 'Réglages' }]} value={tab} onChange={setTab} />

      {/* ───────── SITE ───────── */}
      {tab === 'site' && (
        <div className="sm-card"><div className="sm-card-b">
          {b.erreur_analyse && <div className="sm-err">Dernière analyse en erreur : {b.erreur_analyse}</div>}
          <Field label="Site principal" hint="L'agent lit ce site (page d'accueil, sitemap, pages clés) pour comprendre ta marque."><input className="sm-input" value={b.site_url} onChange={e => setB({ ...b, site_url: e.target.value })} /></Field>
          <Field label="Pages supplémentaires (une URL par ligne)"><textarea className="sm-textarea" value={(b.urls_supplementaires || []).join('\n')} onChange={e => setB({ ...b, urls_supplementaires: e.target.value.split('\n').map(s => s.trim()).filter(Boolean) })} placeholder="https://nagora.site\nhttps://rhmanager.site/blog" /></Field>
          <Field label="Brief manuel" hint="À remplir si ton site est une application web (peu de texte lisible) : décris ta marque, ton offre, ton public.">
            <textarea className="sm-textarea" style={{ minHeight: 150 }} value={b.config.brief_manuel || ''} onChange={e => sec('config', 'brief_manuel', e.target.value)} />
          </Field>
          <div className="sm-row">
            <button className="sm-btn pri" disabled={saving} onClick={async () => {
              await save({ site_url: b.site_url, urls_supplementaires: b.urls_supplementaires, config: { brief_manuel: b.config.brief_manuel || '' } }, 'Source enregistrée')
              runJob('Analyse de la marque', () => social.analyzeBrand())
            }}>✨ Enregistrer & analyser avec l'IA</button>
            <button className="sm-btn" disabled={saving} onClick={() => save({ site_url: b.site_url, urls_supplementaires: b.urls_supplementaires, config: { brief_manuel: b.config.brief_manuel || '' } })}>Enregistrer seulement</button>
            {b.derniere_analyse && <span className="sm-xs sm-mut">Dernière analyse : {fmtDate(b.derniere_analyse)}</span>}
          </div>
        </div></div>
      )}

      {/* ───────── IDENTITÉ ───────── */}
      {tab === 'identite' && (
        <div className="sm-card"><div className="sm-card-b">
          {!Object.keys(b.identite || {}).length && <div className="sm-info">Lance d'abord l'analyse dans « Site & analyse », puis ajuste ici.</div>}
          <Field label="Mission"><textarea className="sm-textarea" value={b.identite.mission || ''} onChange={e => sec('identite', 'mission', e.target.value)} /></Field>
          <Field label="Proposition de valeur"><textarea className="sm-textarea" value={b.identite.proposition_valeur || ''} onChange={e => sec('identite', 'proposition_valeur', e.target.value)} /></Field>
          <Field label="Marché / zone"><input className="sm-input" value={b.identite.marche || ''} onChange={e => sec('identite', 'marche', e.target.value)} /></Field>
          <div className="sm-grid g2">
            {([['produits_services', 'Produits & services'], ['public_cible', 'Public cible'], ['differenciateurs', 'Différenciateurs'], ['valeurs', 'Valeurs'], ['concurrents_probables', 'Concurrents probables'], ['secteurs', 'Requêtes de veille (actualités)'], ['sujets_interdits', 'Sujets interdits']] as const).map(([k, l]) => (
              <Field key={k} label={l}><TagInput value={asArr(b.identite[k])} onChange={v => sec('identite', k, v)} /></Field>
            ))}
            <Field label="Hashtags de marque"><TagInput hash value={asArr(b.identite.hashtags_marque)} onChange={v => sec('identite', 'hashtags_marque', v)} /></Field>
          </div>
          {!!b.identite.personas?.length && <><p className="sm-label">Personas détectés</p><div className="sm-auto sm-mb">{b.identite.personas.map((p: any, i: number) => <div className="sm-stat" key={i}><b>{p.nom}</b><p className="sm-xs sm-mut">Besoins : {p.besoins}</p><p className="sm-xs sm-mut">Douleurs : {p.douleurs}</p></div>)}</div></>}
          <SaveBtn patch={{ identite: b.identite }} />
        </div></div>
      )}

      {/* ───────── VOIX ───────── */}
      {tab === 'voix' && (
        <div className="sm-card"><div className="sm-card-b">
          <div className="sm-row sm-mb"><button className="sm-btn" onClick={() => runJob('Réapprentissage du ton', () => social.refreshTone())}>🎙 Réapprendre le ton depuis mes exemples</button><span className="sm-xs sm-mut">Demande au moins 3 exemples (onglet suivant). Tes corrections de posts comptent double.</span></div>
          <div className="sm-grid g2">
            <Field label="Qui parle ?"><input className="sm-input" value={b.ton.persona || ''} onChange={e => sec('ton', 'persona', e.target.value)} /></Field>
            <Field label="Formalité"><input className="sm-input" value={b.ton.formalite || ''} onChange={e => sec('ton', 'formalite', e.target.value)} placeholder="vouvoiement, ton professionnel chaleureux" /></Field>
            <Field label="Usage des emojis"><input className="sm-input" value={b.ton.emojis || ''} onChange={e => sec('ton', 'emojis', e.target.value)} /></Field>
            <Field label="Longueur des phrases"><input className="sm-input" value={b.ton.longueur_phrases || ''} onChange={e => sec('ton', 'longueur_phrases', e.target.value)} /></Field>
            <Field label="Humour"><input className="sm-input" value={b.ton.humour || ''} onChange={e => sec('ton', 'humour', e.target.value)} /></Field>
            <Field label="Adjectifs du ton"><TagInput value={asArr(b.ton.adjectifs)} onChange={v => sec('ton', 'adjectifs', v)} /></Field>
            <Field label="Vocabulaire favori"><TagInput value={asArr(b.ton.vocabulaire_favori)} onChange={v => sec('ton', 'vocabulaire_favori', v)} /></Field>
            <Field label="Mots à éviter"><TagInput value={asArr(b.ton.mots_a_eviter)} onChange={v => sec('ton', 'mots_a_eviter', v)} /></Field>
            <Field label="Modèles d'accroche"><TagInput value={asArr(b.ton.structures_accroche)} onChange={v => sec('ton', 'structures_accroche', v)} /></Field>
            <Field label="Types d'appel à l'action"><TagInput value={asArr(b.ton.types_cta)} onChange={v => sec('ton', 'types_cta', v)} /></Field>
          </div>
          <Field label="Guide éditorial" hint="Ce texte est donné tel quel au rédacteur IA. Tu peux l'éditer librement."><textarea className="sm-textarea" style={{ minHeight: 220 }} value={b.style_guide || ''} onChange={e => setB({ ...b, style_guide: e.target.value })} /></Field>
          <SaveBtn patch={{ ton: b.ton, style_guide: b.style_guide }} />
        </div></div>
      )}

      {/* ───────── PILIERS ───────── */}
      {tab === 'piliers' && (() => {
        const total = b.piliers.reduce((s, p) => s + (+p.poids || 0), 0)
        const upd = (i: number, k: string, v: unknown) => setB({ ...b, piliers: b.piliers.map((p, j) => (j === i ? { ...p, [k]: v } : p)) })
        return (
          <div className="sm-card"><div className="sm-card-b">
            <p className="sm-mb">Poids total : <b style={{ color: total === 100 ? 'var(--ok)' : 'var(--warn)' }}>{total}</b>/100 — répartition du contenu entre tes grands thèmes.</p>
            {!b.piliers.length && <Empty title="Aucun pilier">Lance l'analyse de la marque ou ajoute-en un.</Empty>}
            {b.piliers.map((p, i) => (
              <div className="sm-card" key={i}><div className="sm-card-b">
                <div className="sm-grid g3">
                  <Field label="Code"><input className="sm-input" value={p.code} onChange={e => upd(i, 'code', e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, '-'))} /></Field>
                  <Field label="Titre"><input className="sm-input" value={p.titre} onChange={e => upd(i, 'titre', e.target.value)} /></Field>
                  <Field label={`Poids : ${p.poids}`}><input type="range" min={0} max={100} value={p.poids} onChange={e => upd(i, 'poids', +e.target.value)} /></Field>
                </div>
                <Field label="Description"><input className="sm-input" value={p.description} onChange={e => upd(i, 'description', e.target.value)} /></Field>
                <button className="sm-btn xs danger" onClick={() => setB({ ...b, piliers: b.piliers.filter((_, j) => j !== i) })}>Supprimer</button>
              </div></div>
            ))}
            <div className="sm-row">
              <button className="sm-btn" onClick={() => setB({ ...b, piliers: [...b.piliers, { code: 'nouveau', titre: '', description: '', poids: 10 }] })}>+ Ajouter un pilier</button>
              <button className="sm-btn" disabled={!total} onClick={() => setB({ ...b, piliers: b.piliers.map(p => ({ ...p, poids: Math.round((p.poids / total) * 100) })) })}>Normaliser à 100</button>
              <SaveBtn patch={{ piliers: b.piliers }} />
            </div>
          </div></div>
        )
      })()}

      {tab === 'exemples' && <Samples brand={b} />}

      {/* ───────── RÉGLAGES ───────── */}
      {tab === 'reglages' && <Settings b={b} sec={sec} save={() => save({ config: b.config })} saving={saving} />}
    </div>
  )
}

/* ───────── Exemples de style + apprentissages ───────── */
function Samples({ brand }: { brand: BrandT }) {
  const { tick, ok, err } = useSocial()
  const [txt, setTxt] = useState(''); const [pl, setPl] = useState('')
  const { data, reload } = useLoad(() => social.samples(), [tick])
  const add = async () => {
    try { const r = await social.addSample(txt, pl || undefined); ok(r.ajoute ? 'Exemple ajouté' : 'Cet exemple existe déjà'); setTxt(''); reload() } catch (e) { err(errMsg(e)) }
  }
  return (
    <div>
      <div className="sm-card"><div className="sm-card-h"><h3>Ajouter un vrai post de ta marque</h3></div><div className="sm-card-b">
        <p className="sm-hint sm-mb">Colle 5 à 10 posts que tu aimes (les tiens). C'est le signal le plus fort pour imiter ta voix.</p>
        <textarea className="sm-textarea" style={{ minHeight: 120 }} value={txt} onChange={e => setTxt(e.target.value)} />
        <div className="sm-row sm-mt"><select className="sm-select" style={{ width: 170 }} value={pl} onChange={e => setPl(e.target.value)}><option value="">Tous réseaux</option>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select>
          <button className="sm-btn pri" disabled={!txt.trim()} onClick={add}>Ajouter</button></div>
      </div></div>
      <div className="sm-card"><div className="sm-card-h"><h3>Exemples enregistrés ({data?.length || 0})</h3></div><div className="sm-card-b">
        {!data?.length ? <p className="sm-mut">Aucun exemple.</p> : <div className="sm-list">{data.map(s => (
          <div className="sm-item" key={s.id} style={{ alignItems: 'flex-start' }}>
            <div className="sm-flex1"><p style={{ whiteSpace: 'pre-wrap' }}>{s.texte.slice(0, 280)}{s.texte.length > 280 ? '…' : ''}</p>
              <div className="sm-chips sm-mt"><Badge tone={s.source === 'edit_admin' ? 'violet' : s.source === 'post_performant' ? 'green' : 'gray'}>{prettify(s.source)}</Badge>{s.plateforme && <Badge>{pmeta(s.plateforme).label}</Badge>}<Badge tone="blue">poids {s.poids}</Badge></div></div>
            <button className="sm-btn xs danger" onClick={async () => { await social.delSample(s.id); reload() }}>×</button>
          </div>))}</div>}
      </div></div>
      <div className="sm-card"><div className="sm-card-h"><h3>Apprentissages de l'agent</h3></div><div className="sm-card-b">
        {!brand.apprentissages?.length ? <p className="sm-mut">Pas encore : ils proviennent des rapports hebdomadaires et de tes rejets.</p> : <div className="sm-list">{[...brand.apprentissages].reverse().map((a, i) => <div className="sm-item" key={i}><Badge tone="violet">{prettify(a.type)}</Badge><span className="sm-flex1">{a.texte}</span><span className="sm-xs sm-mut">{fmtDate(a.date)}</span></div>)}</div>}
      </div></div>
    </div>
  )
}

/* ───────── Réglages ───────── */
function Settings({ b, sec, save, saving }: { b: BrandT; sec: (s: 'identite' | 'ton' | 'config', k: string, v: unknown) => void; save: () => void; saving: boolean }) {
  const c = b.config
  const { data: assets } = useLoad(() => social.assets.list({ include_excluded: true }), [])
  const logos = (assets || []).filter(a => a.type_image === 'logo')
  const cad = c.cadence_hebdo || {}
  const col = c.couleurs || {}
  return (
    <div className="sm-card"><div className="sm-card-b">
      <h3 className="sm-mb">Réseaux & rythme</h3>
      <Field label="Réseaux actifs"><PlatformPicker value={c.plateformes_actives || []} onChange={v => sec('config', 'plateformes_actives', v)} /></Field>
      <div className="sm-grid g4">
        {PLATFORMS.map(p => <Field key={p} label={`${pmeta(p).label} / semaine`}><input className="sm-input" type="number" min={0} max={14} value={cad[p] ?? 0} onChange={e => sec('config', 'cadence_hebdo', { ...cad, [p]: +e.target.value })} /></Field>)}
      </div>
      <Field label="Max de posts par jour et par réseau"><input className="sm-input" style={{ maxWidth: 120 }} type="number" min={1} max={5} value={c.max_par_jour_par_plateforme ?? 1} onChange={e => sec('config', 'max_par_jour_par_plateforme', +e.target.value)} /></Field>

      <h3 className="sm-mb sm-mt">Validation & automatisation</h3>
      <div className="sm-mb"><Switch checked={c.validation_requise !== false} onChange={v => sec('config', 'validation_requise', v)} label="Validation humaine obligatoire avant publication" /></div>
      <div className="sm-mb"><Switch checked={!!c.autopilot_actif} onChange={v => sec('config', 'autopilot_actif', v)} label="Pilote automatique hebdomadaire (lundi 7 h)" /></div>
      <div className="sm-mb"><Switch checked={!!c.autopilot_publication_directe} disabled={c.validation_requise !== false} onChange={v => sec('config', 'autopilot_publication_directe', v)} label="Publication directe sans validation" /></div>
      <p className="sm-hint">La publication directe n'est effective que si la validation obligatoire est désactivée.</p>

      <h3 className="sm-mb sm-mt">Visuels</h3>
      <div className="sm-grid g2">
        <Field label="Mode visuel"><select className="sm-select" value={c.mode_visuel || 'auto'} onChange={e => sec('config', 'mode_visuel', e.target.value)}><option value="auto">Automatique (captures, photos, cartes)</option><option value="aucun">Aucun (hors Instagram / TikTok)</option></select></Field>
        <Field label="Slides max par carrousel"><input className="sm-input" type="number" min={2} max={8} value={c.carrousel_max_slides ?? 5} onChange={e => sec('config', 'carrousel_max_slides', +e.target.value)} /></Field>
        <Field label="Logo"><select className="sm-select" value={c.logo_asset_id || ''} onChange={e => sec('config', 'logo_asset_id', e.target.value || null)}><option value="">Détection automatique</option>{logos.map(l => <option key={l.id} value={l.id}>{l.titre_court || l.id}</option>)}</select></Field>
      </div>
      <div className="sm-grid g3">
        <Field label="Couleur primaire"><input className="sm-input" type="color" value={col.primaire || '#1B3A6B'} onChange={e => sec('config', 'couleurs', { ...col, primaire: e.target.value })} /></Field>
        <Field label="Couleur secondaire"><input className="sm-input" type="color" value={col.secondaire || '#2E5FA3'} onChange={e => sec('config', 'couleurs', { ...col, secondaire: e.target.value })} /></Field>
        <Field label="Couleur du texte"><input className="sm-input" type="color" value={col.texte || '#FFFFFF'} onChange={e => sec('config', 'couleurs', { ...col, texte: e.target.value })} /></Field>
      </div>
      <div className="sm-mb"><Switch checked={c.utiliser_captures !== false} onChange={v => sec('config', 'utiliser_captures', v)} label="Utiliser les captures du logiciel dans les posts" /></div>
      <div className="sm-mb"><Switch checked={!!c.autoriser_captures_sensibles} onChange={v => sec('config', 'autoriser_captures_sensibles', v)} label="Autoriser les captures avec données personnelles non floutées (déconseillé)" /></div>
      <div className="sm-mb"><Switch checked={c.utm !== false} onChange={v => sec('config', 'utm', v)} label="Ajouter des paramètres UTM aux liens (suivi des clics)" /></div>
      <button className="sm-btn pri sm-mt" disabled={saving} onClick={save}>{saving ? <Spinner /> : 'Enregistrer les réglages'}</button>
    </div></div>
  )
}