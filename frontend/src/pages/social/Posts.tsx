// src/pages/social/Posts.tsx
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  errMsg, fmtDateTime, fmtPct, isVideo, PLATFORMS, pmeta, Post, prettify, Prediction, Slot, social, TEMPLATES, toInput, VisualSpec, Platform,
} from '../../lib/social'
import { social2 } from '../../lib/social2'
import { AssetPicker } from './AssetPicker'
import { AuthImg, Badge, Empty, Field, Loading, Modal, PageHead, PlatformDot, Pills, ScoreRing, Spinner, StatusBadge, Switch, TagInput, useSocial } from './ui'

const FILTERS = [
  { id: '', label: 'Tous' }, { id: 'a_valider', label: 'À valider' }, { id: 'programme', label: 'Programmés' },
  { id: 'publie', label: 'Publiés' }, { id: 'echec', label: 'Échecs' }, { id: 'brouillon', label: 'Brouillons' }, { id: 'rejete', label: 'Rejetés' },
]
const LIMIT = 24
const VIDEO_PLATFORMS = ['tiktok', 'instagram', 'facebook']
const TIKTOK_TPL = ['video', 'carrousel', 'photo_overlay']
const STYLE_TPL = ['tilt', 'glass', 'duo', 'checklist', 'quote', 'bold']
const NO_CAPTURE_TPL = ['carte', 'quote', 'aucun']

type Vis = VisualSpec & { voix?: boolean; sous_titres?: boolean; duree_cible?: number; duree?: number; erreur_montage?: string; cover?: string }
type EditTab = 'contenu' | 'visuel' | 'publication' | 'assistant'

/* ═════════════════════════ Page liste ═════════════════════════ */
export function Posts() {
  const { tick, ok, err } = useSocial()
  const [sp, setSp] = useSearchParams()
  const statut = sp.get('statut') || ''
  const plat = sp.get('plateforme') || ''
  const openId = sp.get('open')
  const [items, setItems] = useState<Post[]>([])
  const [loading, setLoading] = useState(true)
  const [more, setMore] = useState(false)
  const [sel, setSel] = useState<string[]>([])
  const [creating, setCreating] = useState(sp.get('new') === '1')
  const [bulk, setBulk] = useState(false)
  const len = useRef(0)
  len.current = items.length

  const load = useCallback(async (reset: boolean) => {
    setLoading(true)
    try {
      const r = await social.posts({ statut, plateforme: plat, limit: LIMIT, offset: reset ? 0 : len.current })
      setItems(prev => (reset ? r : [...prev, ...r])); setMore(r.length === LIMIT)
    } catch (e) { err(errMsg(e)) } finally { setLoading(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statut, plat])

  useEffect(() => { setSel([]); load(true) }, [statut, plat, tick, load])

  const publishing = items.some(p => p.statut === 'publication')
  useEffect(() => {
    if (!publishing) return
    let n = 0
    const t = setInterval(() => {
      if (document.hidden) return
      if (++n > 20) { clearInterval(t); return }
      load(true)
    }, 8000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [publishing])

  const setParam = (k: string, v: string) => { const n = new URLSearchParams(sp); if (v) n.set(k, v); else n.delete(k); setSp(n, { replace: true }) }
  const toggle = (id: string) => setSel(s => (s.includes(id) ? s.filter(x => x !== id) : [...s, id]))

  const validateSel = async () => {
    setBulk(true); let n = 0
    for (const id of sel) { try { await social.validate(id); n++ } catch (e) { err(errMsg(e)) } }
    setBulk(false); setSel([]); ok(`${n} post(s) validé(s) et programmé(s)`); load(true)
  }

  return (
    <div>
      <PageHead title="Posts" sub="Relisez, corrigez (l'IA apprend de vos corrections), validez et programmez.">
        <button className="sm-btn pri" onClick={() => setCreating(true)}>Nouveau post</button>
      </PageHead>
      <Pills items={FILTERS} value={statut} onChange={v => setParam('statut', v)} />
      <div className="sm-chips sm-mb">
        <button className={`sm-chip pl${!plat ? ' on' : ''}`} onClick={() => setParam('plateforme', '')}>Tous les réseaux</button>
        {PLATFORMS.map(p => <button key={p} className={`sm-chip pl${plat === p ? ' on' : ''}`} onClick={() => setParam('plateforme', p)}>{pmeta(p).label}</button>)}
      </div>

      {!!sel.length && (
        <div className="sm-bulk">
          <b>{sel.length} sélectionné(s)</b><span className="sm-flex1" />
          <button className="sm-btn xs" onClick={() => setSel([])}>Annuler</button>
          <button className="sm-btn ok xs" disabled={bulk} onClick={validateSel}>{bulk ? 'Validation…' : 'Valider et programmer'}</button>
        </div>
      )}

      {loading && !items.length ? <Loading /> : !items.length ? <Empty title="Aucun post">Générez des idées puis faites rédiger les posts, ou créez un post manuellement.</Empty> : (
        <>
          <div className="sm-posts">
            {items.map(p => (
              <div key={p.id} className={`sm-post${sel.includes(p.id) ? ' sel' : ''}`} onClick={() => setParam('open', p.id)}>
                {p.statut === 'a_valider' && <input type="checkbox" className="sm-chk" checked={sel.includes(p.id)} onClick={e => e.stopPropagation()} onChange={() => toggle(p.id)} />}
                <div className="sm-thumb">
                  {p.media_urls[0] ? (isVideo(p.media_urls[0]) ? <video src={p.media_urls[0]} muted preload="metadata" /> : <img src={p.media_urls[0]} alt="" loading="lazy" />) : <span>Sans visuel</span>}
                  {p.media_urls.length > 1 && <span className="sm-count">{p.media_urls.length} slides</span>}
                  {p.media_urls[0] && isVideo(p.media_urls[0]) && <span className="sm-count">Vidéo</span>}
                  <span className="sm-thumb-p"><PlatformDot p={p.plateforme} /></span>
                </div>
                <div className="sm-post-b">
                  <div className="sm-row">
                    <StatusBadge s={p.statut} />{p.variante && <Badge tone="violet">Variante {p.variante}</Badge>}{!p.genere_par_ia && <Badge>Manuel</Badge>}
                    <span className="sm-flex1" />{p.prediction && <ScoreRing size={34} value={p.prediction.score_global} />}
                  </div>
                  <p className="sm-post-t">{p.contenu}</p>
                  <div className="sm-post-f"><span>{fmtDateTime(p.scheduled_at)}</span>{p.pilier && <Badge>{prettify(p.pilier)}</Badge>}</div>
                  {p.erreur && p.statut === 'echec' && <div className="sm-xs" style={{ color: 'var(--err)' }}>{p.erreur.slice(0, 90)}</div>}
                </div>
              </div>
            ))}
          </div>
          {more && <div className="sm-center sm-mt"><button className="sm-btn" disabled={loading} onClick={() => load(false)}>{loading ? 'Chargement…' : 'Charger plus'}</button></div>}
        </>
      )}

      {openId && <PostEditor id={openId} onClose={() => setParam('open', '')} onChanged={() => load(true)} />}
      {creating && <NewPost onClose={() => { setCreating(false); setParam('new', '') }} onCreated={id => { setCreating(false); const n = new URLSearchParams(sp); n.delete('new'); n.set('open', id); setSp(n, { replace: true }); load(true) }} />}
    </div>
  )
}

/* ═════════════════════════ Création manuelle ═════════════════════════ */
function NewPost({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { err, ok } = useSocial()
  const [pl, setPl] = useState<Platform>('linkedin')
  const [txt, setTxt] = useState(''); const [tags, setTags] = useState<string[]>([]); const [lien, setLien] = useState('')
  const [when, setWhen] = useState(''); const [files, setFiles] = useState<File[]>([]); const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      const p = await social.createPost({ plateforme: pl, contenu: txt, hashtags: tags, lien: lien || null, scheduled_at: when || null, format: files.length ? 'image' : 'texte' })
      for (const f of files) await social.uploadMedia(p.id, f)
      ok('Post créé'); onCreated(p.id)
    } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <Modal title="Nouveau post manuel" onClose={onClose} footer={<><button className="sm-btn" onClick={onClose}>Annuler</button><button className="sm-btn pri" disabled={busy || !txt.trim()} onClick={submit}>{busy ? 'Création…' : 'Créer'}</button></>}>
      <Field label="Réseau"><select className="sm-select" value={pl} onChange={e => setPl(e.target.value as Platform)}>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select></Field>
      <Field label="Texte"><textarea className="sm-textarea" style={{ minHeight: 140 }} value={txt} onChange={e => setTxt(e.target.value)} /></Field>
      <Field label="Hashtags"><TagInput hash value={tags} onChange={setTags} placeholder="Ajoutez un hashtag puis Entrée" /></Field>
      <Field label="Lien (Facebook / LinkedIn)"><input className="sm-input" value={lien} onChange={e => setLien(e.target.value)} placeholder="https://…" /></Field>
      <Field label="Date de publication (heure locale)"><input className="sm-input" type="datetime-local" value={when} onChange={e => setWhen(e.target.value)} /></Field>
      <Field label="Médias (images / vidéo)"><input type="file" multiple accept="image/*,video/mp4,video/quicktime" onChange={e => setFiles(Array.from(e.target.files || []))} /></Field>
    </Modal>
  )
}

/* ═════════════════════════ Éditeur de post ═════════════════════════ */
interface Draft { contenu: string; hashtags: string[]; lien: string; scheduled: string; script: string }
interface HydrateOpts { keepVis?: boolean; keepDraft?: boolean }

export function PostEditor({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged?: () => void }) {
  const { ok, err, runJob } = useSocial()
  const [post, setPost] = useState<Post | null>(null)
  const [d, setD] = useState<Draft>({ contenu: '', hashtags: [], lien: '', scheduled: '', script: '' })
  const [vis, setVisState] = useState<Vis>({})
  const [visDirty, setVisDirty] = useState(false)
  const [busy, setBusy] = useState('')
  const [tab, setTab] = useState<EditTab>('contenu')
  const [critique, setCritique] = useState<any>(null)
  const [slots, setSlots] = useState<Slot[]>([])
  const [picker, setPicker] = useState(false)
  const [instr, setInstr] = useState('')
  const [sys, setSys] = useState<{ ffmpeg: boolean; edge_tts: boolean; unsplash: boolean } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const setVis = (v: Vis) => { setVisState(v); setVisDirty(true) }

  const hydrate = (p: Post, o: HydrateOpts = {}) => {
    setPost(p)
    if (!o.keepVis) { setVisState((p.visuel_spec || {}) as Vis); setVisDirty(false) }
    if (!o.keepDraft) setD({ contenu: p.contenu || '', hashtags: p.hashtags || [], lien: p.lien || '', scheduled: toInput(p.scheduled_at), script: p.script_video || '' })
  }
  const reload = async (o: HydrateOpts = {}) => { const p = await social.post(id); hydrate(p, o); return p }

  useEffect(() => {
    reload().then(p => social.slots(p.plateforme, 4).then(setSlots).catch(() => {})).catch(e => { err(errMsg(e)); onClose() })
    social2.system().then(setSys).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  if (!post) return <Modal title="Chargement…" onClose={onClose}><Loading /></Modal>

  const editable = !['publie', 'publication'].includes(post.statut)
  const m = pmeta(post.plateforme)
  const dirty = d.contenu !== (post.contenu || '') || d.lien !== (post.lien || '') || d.scheduled !== toInput(post.scheduled_at) || d.script !== (post.script_video || '') || JSON.stringify(d.hashtags) !== JSON.stringify(post.hashtags || [])
  const changed = () => onChanged && onChanged()
  const tpl = vis.template || 'capture_cadree'
  const isVid = tpl === 'video'

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name)
    try { await fn() } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const saveBody = () => ({ contenu: d.contenu, hashtags: d.hashtags, lien: d.lien, scheduled_at: d.scheduled || undefined, script_video: d.script })

  const doApplyVisual = async (extra: Record<string, unknown> = {}): Promise<boolean> => {
    const body: Record<string, unknown> = {
      template: tpl, asset_ids: vis.asset_ids, titre_carte: vis.titre_carte, sous_titre: vis.sous_titre,
      badge: vis.badge, unsplash_query: vis.unsplash_query, ratio: vis.ratio || undefined,
      style: vis.style || undefined, points: vis.points,
      slides: tpl === 'carrousel' ? (vis.asset_ids || []).map(a => ({ asset_id: a, ...(vis.slides?.find(s => s.asset_id === a) || {}) })) : [],
      ...(isVid ? { sous_titres: vis.sous_titres !== false, voix: !!vis.voix, duree_cible: vis.duree_cible ?? 22 } : {}),
      ...extra,
    }
    Object.keys(body).forEach(k => { if (body[k] === undefined || body[k] === '' || body[k] === null) delete body[k] })
    const r: any = await social2.visual(id, body)
    if (r && r.job_id) {
      const res = await runJob(isVid ? 'Montage vidéo (1 à 3 min)' : 'Montage visuel', async () => r)
      if (res === null) return false
      await reload({ keepDraft: true })
    } else {
      setPost(p => p && ({ ...p, media_urls: r.media_urls, visuel_spec: r.visuel_spec }))
      setVisState((r.visuel_spec || {}) as Vis); setVisDirty(false)
    }
    changed()
    return true
  }

  const prepare = async () => {
    if (dirty) { const p = await social.patchPost(id, saveBody()); hydrate(p, { keepVis: true }) }
    if (visDirty) { const okv = await doApplyVisual(); if (!okv) throw new Error('Le montage visuel a échoué : corrigez-le avant de continuer.') }
  }

  const applyVisual = (extra: Record<string, unknown> = {}) => run('visuel', async () => { if (await doApplyVisual(extra)) ok(isVid ? 'Vidéo générée' : 'Visuel mis à jour') })
  const save = () => run('save', async () => { await prepare(); await reload(); ok('Enregistré : l\'IA retient vos corrections de style'); changed() })
  const validate = () => run('validate', async () => {
    await prepare()
    const p = await social.validate(id, d.scheduled || undefined); hydrate(p); ok(`Programmé : ${fmtDateTime(p.scheduled_at)}`); changed()
  })
  const publishNow = () => {
    if (!window.confirm(`Publier maintenant sur ${m.label} ?`)) return
    run('publish', async () => { await prepare(); await social.publishNow(id); ok('Publication lancée'); await reload(); changed() })
  }
  const reject = () => { const mo = window.prompt('Motif du rejet (l\'IA en tiendra compte) :'); if (mo === null) return; run('reject', async () => { hydrate(await social.reject(id, mo)); ok('Post rejeté'); changed() }) }
  const unschedule = () => run('unschedule', async () => { hydrate(await social.unschedule(id)); ok('Post déprogrammé'); changed() })
  const del = () => { if (!window.confirm('Supprimer définitivement ce post ?')) return; run('del', async () => { await social.delPost(id); ok('Post supprimé'); changed(); onClose() }) }
  const upload = (files: FileList | null) => {
    if (!files?.length) return
    run('upload', async () => { for (const f of Array.from(files)) await social.uploadMedia(id, f); await reload({ keepDraft: true, keepVis: true }); ok('Média ajouté'); changed() })
  }
  const rmMedia = (u: string) => run('media', async () => { await social.removeMedia(id, u); setPost(p => p && ({ ...p, media_urls: p.media_urls.filter(x => x !== u) })) })

  const score = async () => {
    setBusy('score')
    const r = await runJob('Analyse du post', () => social.score(id))
    setBusy('')
    if (r?.critique) { setCritique(r.critique); await reload({ keepDraft: true, keepVis: true }) }
  }
  const variants = async () => { await runJob('Variantes A/B', () => social.variants(id, 2)); changed() }
  const regenerate = async () => {
    const r = await runJob('Réécriture du post', () => social.regenerate(id, instr || 'améliore l\'accroche'))
    if (r) { setInstr(''); await reload({ keepVis: true }); changed() }
  }

  const maxLen = m.max
  const over = d.contenu.length > maxLen
  const tplList = TEMPLATES.filter(t => {
    if (t.id === 'video') return VIDEO_PLATFORMS.includes(post.plateforme)
    if (post.plateforme === 'tiktok') return TIKTOK_TPL.includes(t.id)
    return t.id !== 'aucun' || !['instagram', 'tiktok', 'x'].includes(post.plateforme)
  })
  const currentTpl = TEMPLATES.find(t => t.id === tpl)
  const working = busy === 'visuel'

  return (
    <Modal wide onClose={onClose}
      title={<span className="sm-row"><PlatformDot p={post.plateforme} />{m.label}<StatusBadge s={post.statut} />{post.variante && <Badge tone="violet">Variante {post.variante}</Badge>}</span>}
      footer={<>
        <button className="sm-btn danger" disabled={!!busy || post.statut === 'publication'} onClick={del}>Supprimer</button>
        {editable && post.statut !== 'rejete' && <button className="sm-btn" disabled={!!busy} onClick={reject}>Rejeter</button>}
        {editable && post.statut === 'programme' && <button className="sm-btn" disabled={!!busy} onClick={unschedule}>Déprogrammer</button>}
        <span className="sm-flex1" />
        {post.statut === 'publie' && post.external_url && <a className="sm-btn" href={post.external_url} target="_blank" rel="noreferrer">Voir le post</a>}
        {editable && <button className="sm-btn" disabled={!!busy || !(dirty || visDirty)} onClick={save}>{busy === 'save' ? <Spinner /> : 'Enregistrer'}</button>}
        {editable && <button className="sm-btn ok pe-big" disabled={!!busy} onClick={validate}>{busy === 'validate' ? <Spinner /> : post.statut === 'programme' ? 'Reprogrammer' : 'Valider et programmer'}</button>}
        {editable && <button className="sm-btn pri pe-big" disabled={!!busy} onClick={publishNow}>{busy === 'publish' ? <Spinner /> : 'Publier maintenant'}</button>}
        {!editable && <button className="sm-btn" onClick={onClose}>Fermer</button>}
      </>}>
      {post.erreur && <div className="sm-err">Erreur de publication (tentative {post.nb_tentatives}) : {post.erreur}</div>}
      {post.rejet_motif && post.statut === 'rejete' && <div className="sm-note">Rejeté : {post.rejet_motif}</div>}
      {post.statut === 'publication' && <div className="sm-info"><Spinner /> Publication en cours…</div>}
      {isVid && sys && !sys.ffmpeg && <div className="sm-err">ffmpeg est absent du conteneur : aucune vidéo ne peut être montée. Reconstruisez l'image Docker (le Dockerfile fourni l'installe).</div>}

      <div className="pe-layout">
        {/* ─── Aperçu (toujours visible) ─── */}
        <aside className="pe-side">
          {working && <div className="pe-busy"><Spinner /> {isVid ? 'Montage de la vidéo en cours (1 à 3 minutes)…' : 'Montage en cours…'}</div>}
          <Preview post={post} d={d} brand={post.plateforme} />
          <div className="sm-card sm-mt"><div className="sm-card-h"><h3>Médias</h3>
            {editable && <><input ref={fileRef} type="file" hidden multiple accept="image/*,video/mp4,video/quicktime" onChange={e => { upload(e.target.files); e.target.value = '' }} />
              <button className="sm-btn xs" disabled={!!busy} onClick={() => fileRef.current?.click()}>{busy === 'upload' ? <Spinner /> : 'Ajouter'}</button></>}
          </div><div className="sm-card-b">
            {!post.media_urls.length ? <p className="sm-mut sm-xs">Aucun média{['instagram', 'tiktok', 'x'].includes(post.plateforme) ? ' : ce réseau en exige un.' : '.'}</p> : (
              <div className="sm-media">{post.media_urls.map(u => (
                <div className="m" key={u}>{isVideo(u) ? <video src={u} /> : <img src={u} alt="" />}{editable && <button onClick={() => rmMedia(u)}>×</button>}</div>
              ))}</div>
            )}
          </div></div>
        </aside>

        {/* ─── Édition par onglets ─── */}
        <section className="pe-main">
          <Pills<EditTab> items={[{ id: 'contenu', label: 'Contenu' }, { id: 'visuel', label: 'Visuel' }, { id: 'publication', label: 'Publication' }, { id: 'assistant', label: 'Assistant IA' }]} value={tab} onChange={setTab} />

          {tab === 'contenu' && (
            <div>
              <Field label={`Texte (${d.contenu.length}/${maxLen})${post.plateforme === 'tiktok' ? ', légende recommandée' : ''}`}>
                <textarea className="sm-textarea" style={{ minHeight: 220, borderColor: over ? 'var(--err)' : undefined }} disabled={!editable} value={d.contenu} onChange={e => setD({ ...d, contenu: e.target.value })} />
                {over && <span className="sm-hint" style={{ color: 'var(--err)' }}>Dépasse la limite du réseau : le texte sera tronqué à la publication.</span>}
              </Field>
              <Field label="Hashtags"><TagInput hash value={d.hashtags} onChange={v => editable && setD({ ...d, hashtags: v })} placeholder="#hashtag" /></Field>
              {['facebook', 'linkedin'].includes(post.plateforme) && <Field label="Lien ajouté au post"><input className="sm-input" disabled={!editable} value={d.lien} onChange={e => setD({ ...d, lien: e.target.value })} /></Field>}
              {(isVid || post.plateforme === 'tiktok') && <Field label="Script vidéo" hint="Accroche, scènes, voix off, appel à l'action : base de la vidéo."><textarea className="sm-textarea" style={{ minHeight: 120 }} disabled={!editable} value={d.script} onChange={e => setD({ ...d, script: e.target.value })} /></Field>}
            </div>
          )}

          {tab === 'visuel' && (editable ? (
            <div>
              <div className="pe-bar">
                <div className="sm-row">{visDirty ? <Badge tone="amber">Modifié, à appliquer</Badge> : <Badge tone="green">À jour</Badge>}</div>
                <div className="sm-row">
                  <button className="sm-btn" disabled={!!busy} onClick={() => applyVisual({ reshuffle: true, slides: [] })}>Autre capture</button>
                  <button className="sm-btn pri" disabled={!!busy} onClick={() => applyVisual()}>{working ? <Spinner /> : isVid ? 'Générer la vidéo' : 'Appliquer'}</button>
                </div>
              </div>

              <p className="sm-label">Modèle</p>
              <div className="pe-tpls">
                {tplList.map(t => (
                  <button key={t.id} type="button" className={`pe-tpl${tpl === t.id ? ' on' : ''}`} onClick={() => setVis({ ...vis, template: t.id })}>
                    <b>{t.label}</b><span>{t.hint}</span>
                  </button>
                ))}
              </div>

              {isVid && (
                <div className="sm-card"><div className="sm-card-h"><h3>Options de la vidéo</h3></div><div className="sm-card-b">
                  <div className="pe-opts">
                    <Switch checked={vis.sous_titres !== false} onChange={v => setVis({ ...vis, sous_titres: v })} label="Sous-titres incrustés" />
                    <Switch checked={!!vis.voix} onChange={v => setVis({ ...vis, voix: v })} label="Voix off (edge-tts, connexion internet requise)" />
                    <Field label={`Durée cible : ${vis.duree_cible ?? 22} s`}>
                      <input type="range" min={12} max={40} value={vis.duree_cible ?? 22} onChange={e => setVis({ ...vis, duree_cible: +e.target.value })} />
                    </Field>
                  </div>
                  <p className="sm-hint sm-mt">Animations, transitions, musique générée et sous-titres sont inclus. Le rendu dure 1 à 3 minutes. Avec la voix off, la durée suit celle de la voix.</p>
                  {vis.erreur_montage && <div className="sm-err sm-mt">Dernière erreur de montage : {vis.erreur_montage}</div>}
                  {!vis.erreur_montage && !!vis.duree && <p className="sm-xs sm-mut sm-mt">Dernière vidéo : {vis.duree} s, musique « {vis.musique || '—'} »{vis.sous_titres ? ', sous-titrée' : ''}{vis.voix ? ', voix off' : ''}.</p>}
                </div></div>
              )}

              {!NO_CAPTURE_TPL.includes(tpl) && (
                <Field label={tpl === 'carrousel' || isVid || tpl === 'duo' ? 'Captures (dans l\'ordre)' : 'Capture utilisée'}>
                  <div className="sm-row">
                    {(vis.asset_ids || []).map(a => <div key={a} className="pe-thumb"><AuthImg path={social.assets.fileUrl(a)} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} /></div>)}
                    <button className="sm-btn xs" onClick={() => setPicker(true)}>Choisir</button>
                  </div>
                </Field>
              )}

              {!isVid && tpl !== 'carrousel' && (
                <div className="sm-grid g2">
                  <Field label="Titre du visuel"><input className="sm-input" value={vis.titre_carte || ''} onChange={e => setVis({ ...vis, titre_carte: e.target.value })} /></Field>
                  <Field label="Sous-titre"><input className="sm-input" value={vis.sous_titre || ''} onChange={e => setVis({ ...vis, sous_titre: e.target.value })} /></Field>
                  <Field label="Badge (module)"><input className="sm-input" value={vis.badge || ''} onChange={e => setVis({ ...vis, badge: e.target.value })} /></Field>
                  <Field label="Format"><select className="sm-select" value={vis.ratio || ''} onChange={e => setVis({ ...vis, ratio: e.target.value || null })}>
                    <option value="">Par défaut du réseau</option><option value="carre">Carré 1:1</option><option value="portrait">Portrait 4:5</option><option value="paysage">Paysage</option></select></Field>
                </div>
              )}
              {STYLE_TPL.includes(tpl) && (
                <Field label="Style de fond"><select className="sm-select" value={vis.style || ''} onChange={e => setVis({ ...vis, style: e.target.value || null })}>
                  <option value="">Automatique</option><option value="aurora">Aurore</option><option value="dark">Sombre</option><option value="mesh">Maillage</option><option value="light">Clair</option></select></Field>
              )}
              {tpl === 'checklist' && <Field label="Points affichés (4 max)"><TagInput value={vis.points || []} onChange={v => setVis({ ...vis, points: v.slice(0, 4) })} placeholder="Un point puis Entrée" /></Field>}
              {tpl === 'photo_overlay' && <Field label="Recherche photo (anglais, 2 à 4 mots)"><input className="sm-input" value={vis.unsplash_query || ''} onChange={e => setVis({ ...vis, unsplash_query: e.target.value })} placeholder="team meeting office" /></Field>}
              {!!vis.credits?.length && <p className="sm-hint">{vis.credits.join(' · ')}</p>}
              {currentTpl && <p className="sm-hint">{currentTpl.hint}. Le visuel est aussi régénéré automatiquement à la validation ou à la publication s'il a été modifié.</p>}
            </div>
          ) : <p className="sm-mut">Ce post est publié : le visuel n'est plus modifiable.</p>)}

          {tab === 'publication' && (
            <div>
              {editable ? (
                <>
                  <Field label="Date et heure de publication (heure locale)" hint={post.horaire_justification || undefined}>
                    <input className="sm-input" type="datetime-local" value={d.scheduled} onChange={e => setD({ ...d, scheduled: e.target.value })} />
                  </Field>
                  {!!slots.length && (
                    <Field label="Créneaux conseillés">
                      <div className="sm-chips">{slots.map(s => <button key={s.scheduled_at} type="button" className="sm-slot" title={s.justification} onClick={() => setD({ ...d, scheduled: toInput(s.scheduled_at) })}>{fmtDateTime(s.scheduled_at)} · {Math.round(s.score * 100)} %</button>)}</div>
                    </Field>
                  )}
                  {visDirty && <div className="pe-warn">Le montage visuel a été modifié : il sera régénéré avant la validation ou la publication.</div>}
                  <p className="sm-hint sm-mb">Utilisez les boutons « Valider et programmer » ou « Publier maintenant » en bas de la fenêtre.</p>
                </>
              ) : <p className="sm-mut">Ce post est déjà publié ou en cours de publication.</p>}
              <PredictionCard p={post.prediction} />
            </div>
          )}

          {tab === 'assistant' && (editable ? (
            <div>
              <Field label="Réécrire avec une consigne">
                <div className="sm-row"><input className="sm-input sm-flex1" value={instr} onChange={e => setInstr(e.target.value)} placeholder="Ex : plus court, plus direct, ajoute une question…" /><button className="sm-btn" onClick={regenerate}>Réécrire</button></div>
              </Field>
              <div className="sm-row"><button className="sm-btn" disabled={busy === 'score'} onClick={score}>Critique et score</button><button className="sm-btn" onClick={variants}>Variantes A/B</button></div>
              {critique && <Critique c={critique} onUse={t => { setD({ ...d, contenu: t }); setTab('contenu') }} />}
            </div>
          ) : <p className="sm-mut">Indisponible pour un post publié.</p>)}
        </section>
      </div>

      {picker && <AssetPicker multi={['carrousel', 'video', 'duo'].includes(tpl)} selected={vis.asset_ids || []} onClose={() => setPicker(false)}
        onConfirm={ids => { setVis({ ...vis, asset_ids: ids }); setPicker(false) }} />}
    </Modal>
  )
}

/* ───────── Sous-composants ───────── */
function Preview({ post, d, brand }: { post: Post; d: Draft; brand: string }) {
  const [i, setI] = useState(0)
  const media = post.media_urls || []
  const idx = Math.min(i, Math.max(0, media.length - 1))
  const m = pmeta(post.plateforme)
  const mediaEl = media.length ? (isVideo(media[idx]) ? <video className="sm-pv-m" src={media[idx]} controls playsInline /> : <img className="sm-pv-m" src={media[idx]} alt="" />) : null
  const body = (
    <div className="sm-pv-t">
      {d.contenu || <span className="sm-mut">Texte du post…</span>}
      {d.lien && ['facebook', 'linkedin'].includes(post.plateforme) && <div style={{ marginTop: 8, color: '#0a66c2' }}>{d.lien}</div>}
      {!!d.hashtags.length && <div style={{ marginTop: 8 }}>{d.hashtags.map(h => <span className="h" key={h}>{h} </span>)}</div>}
    </div>
  )
  return (
    <div className="sm-pv">
      <div className="sm-pv-h"><div className="sm-av" style={{ background: m.color }}>{m.label.slice(0, 1)}</div><div><b>{m.label}</b><div className="sm-xs sm-mut">{fmtDateTime(post.scheduled_at)}</div></div></div>
      {post.plateforme === 'instagram' || post.plateforme === 'tiktok' ? <>{mediaEl}{body}</> : <>{body}{mediaEl}</>}
      {media.length > 1 && <div className="sm-pv-nav"><button className="sm-btn xs" onClick={() => setI(Math.max(0, idx - 1))}>Préc.</button>{idx + 1} / {media.length}<button className="sm-btn xs" onClick={() => setI(Math.min(media.length - 1, idx + 1))}>Suiv.</button></div>}
      <span style={{ display: 'none' }}>{brand}</span>
    </div>
  )
}

export function PredictionCard({ p }: { p: Prediction | null }) {
  if (!p) return null
  return (
    <div className="sm-card"><div className="sm-card-h"><h3>Prédiction de performance</h3></div><div className="sm-card-b">
      <div className="sm-row" style={{ alignItems: 'flex-start', gap: 18 }}>
        <div className="sm-center"><ScoreRing size={74} value={p.score_global} /><div className="sm-xs sm-mut">Score global</div></div>
        <dl className="sm-kv sm-flex1">
          <dt>Engagement attendu</dt><dd><b>{fmtPct(p.er_predit)}</b> <span className="sm-mut">({fmtPct(p.er_bas)} à {fmtPct(p.er_haut)})</span></dd>
          <dt>Confiance</dt><dd>{Math.round(p.confiance * 100)} % <span className="sm-mut">({p.nb_posts_reference} posts de référence)</span></dd>
          <dt>Vs votre historique</dt><dd>Meilleur que {Math.round(p.percentile_historique)} % de vos posts</dd>
          {p.qualite_llm != null && <><dt>Qualité éditoriale</dt><dd>{Math.round(p.qualite_llm)}/100</dd></>}
        </dl>
      </div>
      {!!p.facteurs?.length && <div className="sm-chips sm-mt">{p.facteurs.map((f, i) => <Badge key={i} tone={f.multiplicateur >= 1 ? 'green' : 'red'}>{prettify(f.critere)} : {f.valeur} ×{f.multiplicateur}</Badge>)}</div>}
      {p.nb_posts_reference < 5 && <p className="sm-hint sm-mt">Estimation encore basée sur des moyennes sectorielles : elle s'affine avec vos publications.</p>}
    </div></div>
  )
}

function Critique({ c, onUse }: { c: any; onUse: (t: string) => void }) {
  const rows: [string, number][] = [['Accroche', c.accroche], ['Clarté', c.clarte], ['Appel à l\'action', c.cta], ['Adéquation marque', c.adequation_marque]]
  return (
    <div className="sm-mt">
      {rows.map(([l, v]) => <div className="sm-q" key={l}><span>{l}</span><div className="sm-progress"><i style={{ width: `${v || 0}%`, background: (v || 0) >= 70 ? 'var(--ok)' : (v || 0) >= 45 ? '#d97706' : 'var(--err)' }} /></div><b>{Math.round(v || 0)}</b></div>)}
      {!!c.risques?.length && <><p className="sm-label sm-mt">Risques</p><ul style={{ margin: '4px 0', paddingLeft: 18 }}>{c.risques.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></>}
      {!!c.ameliorations?.length && <><p className="sm-label sm-mt">Améliorations</p><ul style={{ margin: '4px 0', paddingLeft: 18 }}>{c.ameliorations.map((r: string, i: number) => <li key={i}>{r}</li>)}</ul></>}
      {c.version_amelioree && <div className="sm-info sm-mt"><p className="sm-xs sm-bold">Version améliorée proposée</p><p style={{ whiteSpace: 'pre-wrap', margin: '6px 0' }}>{c.version_amelioree}</p><button className="sm-btn xs pri" onClick={() => onUse(c.version_amelioree)}>Utiliser cette version</button></div>}
    </div>
  )
}