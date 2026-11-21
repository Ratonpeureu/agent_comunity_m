// src/pages/social/Library.tsx
import React, { useEffect, useMemo, useRef, useState } from 'react'
import { asArr, AssetFull, Asset, Box, errMsg, PLATFORMS,isVideo, Platform, pmeta, prettify, social, TEMPLATES } from '../../lib/social'
import { AssetPicker } from './AssetPicker'
import { AuthImg, Badge, Empty, Field, Loading, Modal, PageHead, Pills, PlatformPicker, Spinner, Stat, Switch, TagInput, useLoad, useSocial } from './ui'

export function Library() {
  const { tick, runJob, ok, err } = useSocial()
  const [q, setQ] = useState(''); const [mod, setMod] = useState(''); const [showEx, setShowEx] = useState(true)
  const [open, setOpen] = useState<string | null>(null)
  const [studio, setStudio] = useState(false)
  const [stock, setStock] = useState(false)
  const [drag, setDrag] = useState(false)
  const [up, setUp] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const { data, loading } = useLoad(async () => ({ items: await social.assets.list({ include_excluded: true }), mods: await social.assets.modules().catch(() => null) }), [tick])
  const items = data?.items || []
  const modules = useMemo(() => Array.from(new Set(items.map(a => a.module || 'autre'))).sort(), [items])
  const shown = items.filter(a => {
    if (!showEx && a.exclu) return false
    if (mod && (a.module || 'autre') !== mod) return false
    const t = q.trim().toLowerCase()
    return !t || [a.titre_court, a.ecran, a.module, a.description, (a.hashtags || []).join(' '), (a.mots_cles || []).join(' ')].join(' ').toLowerCase().includes(t)
  })

  const upload = async (files: FileList | File[] | null) => {
    const arr = Array.from(files || []); if (!arr.length) return
    setUp(true)
    try {
      const r = await social.assets.upload(arr, true)
      ok(`${r.enregistres.length} fichier(s) ajouté(s)`)
      if (r.job?.job_id) await runJob('Analyse des captures', async () => r.job)
    } catch (e) { err(errMsg(e)) } finally { setUp(false) }
  }

  const sensitive = items.filter(a => a.sensible_non_masque).length
  const excluded = items.filter(a => a.exclu).length

  return (
    <div>
      <PageHead title="Captures du logiciel" sub="L'IA décrit chaque capture, la renomme, choisit les hashtags et propose les zones à flouter / zoomer.">
        <button className="sm-btn" onClick={() => setStock(true)}>Photos libres</button>
        <button className="sm-btn" onClick={() => setStudio(true)}>Studio de montage</button>
        <button className="sm-btn" onClick={() => runJob('Analyse des captures', () => social.assets.analyze({ max_images: 15 }))}>Analyser les nouvelles</button>
        <input ref={fileRef} type="file" hidden multiple accept="image/png,image/jpeg,image/webp" onChange={e => { upload(e.target.files); e.target.value = '' }} />
        <button className="sm-btn pri" disabled={up} onClick={() => fileRef.current?.click()}>{up ? <Spinner /> : '+ Ajouter des captures'}</button>
      </PageHead>

      <div className="sm-grid g4 sm-mb">
        <Stat label="Captures" value={items.length} /><Stat label="Modules couverts" value={modules.length} />
        <Stat label="Exclues" value={excluded} /><Stat label="Données perso non floutées" value={sensitive} hint={sensitive ? 'Non utilisées tant que non corrigées' : 'RAS'} trend={sensitive ? 'down' : 'up'} />
      </div>
      {sensitive > 0 && <div className="sm-note">{sensitive} capture(s) montrent des données personnelles sans zone floutée. Elles sont automatiquement écartées des posts : ouvre-les pour dessiner les zones à flouter.</div>}

      <div className={`sm-drop sm-mb${drag ? ' on' : ''}`} onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={e => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files) }}>
        Glisse tes captures ici (PNG / JPG / WebP) — elles sont analysées automatiquement
      </div>

      <div className="sm-row sm-mb">
        <input className="sm-input" style={{ maxWidth: 340 }} placeholder="Rechercher…" value={q} onChange={e => setQ(e.target.value)} />
        <Switch checked={showEx} onChange={setShowEx} label="Afficher les exclues" />
      </div>
      <Pills items={[{ id: '', label: 'Tous' }, ...modules.map(m => ({ id: m, label: prettify(m), count: items.filter(a => (a.module || 'autre') === m).length }))]} value={mod} onChange={setMod} />

      {loading && !data ? <Loading /> : !shown.length ? <Empty title="Aucune capture">Dépose tes captures dans <code>data/branding_rh_manager/photos</code> ou ajoute-les ci-dessus.</Empty> : (
        <div className="sm-assets">
          {shown.map(a => (
            <div className="sm-asset" key={a.id} onClick={() => setOpen(a.id)}>
              <div className="im"><AuthImg path={social.assets.fileUrl(a.id)} alt={a.titre_court} /></div>
              <div className="b">
                <span className="t">{a.titre_court || a.id}</span>
                <div className="sm-row"><Badge tone="blue">{prettify(a.module)}</Badge>{a.type_image === 'logo' && <Badge tone="violet">Logo</Badge>}
                  {a.exclu && <Badge>Exclue</Badge>}{a.sensible_non_masque && <Badge tone="red">Données perso</Badge>}</div>
                <div className="sm-xs sm-mut">Utilisée {a.usage_30j || 0}× en 30 j</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {open && <AssetEditor id={open} onClose={() => setOpen(null)} />}
      {studio && <MontageStudio onClose={() => setStudio(false)} />}
      {stock && <StockSearch onClose={() => setStock(false)} />}
    </div>
  )
}

/* ═════════════════════════ Édition d'une capture ═════════════════════════ */
function AssetEditor({ id, onClose }: { id: string; onClose: () => void }) {
  const { ok, err, runJob } = useSocial()
  const [a, setA] = useState<AssetFull | null>(null)
  const [saving, setSaving] = useState(false)
  const [mode, setMode] = useState<'' | 'focus' | 'blur'>('')
  const [tmp, setTmp] = useState<Box | null>(null)
  const [studio, setStudio] = useState(false)
  const start = useRef<{ x: number; y: number } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => { social.assets.get(id).then(setA).catch(e => { err(errMsg(e)); onClose() }) /* eslint-disable-next-line */ }, [id])
  if (!a) return <Modal title="Chargement…" onClose={onClose}><Loading /></Modal>
  const set = (k: keyof AssetFull, v: any) => setA({ ...a, [k]: v })

  const pt = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect()
    return { x: Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100)), y: Math.max(0, Math.min(100, ((e.clientY - r.top) / r.height) * 100)) }
  }
  const r1 = (n: number) => Math.round(n * 10) / 10
  const down = (e: React.PointerEvent) => { if (!mode) return; e.preventDefault(); (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); start.current = pt(e); setTmp({ ...start.current, w: 0, h: 0 }) }
  const move = (e: React.PointerEvent) => { if (!start.current) return; const p = pt(e), s = start.current; setTmp({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) }) }
  const up = () => {
    if (start.current && tmp && tmp.w > 1 && tmp.h > 1) {
      const z = { x: r1(tmp.x), y: r1(tmp.y), w: r1(tmp.w), h: r1(tmp.h) }
      if (mode === 'focus') set('zone_focus', z)
      else set('zones_sensibles', [...(a.zones_sensibles || []), { ...z, nature: 'autre' }])
    }
    start.current = null; setTmp(null); setMode('')
  }

  const save = async () => {
    setSaving(true)
    try {
      const body: Record<string, unknown> = {}
      ;(['module', 'ecran', 'titre_court', 'description', 'fonctionnalites_visibles', 'mots_cles', 'hashtags', 'legendes_montage', 'zone_focus', 'zones_sensibles', 'donnees_personnelles_visibles', 'plateformes_recommandees', 'exclu', 'notes_admin', 'type_image'] as (keyof AssetFull)[])
        .forEach(k => { if (a[k] !== undefined && a[k] !== null) body[k] = a[k] })
      setA(await social.assets.patch(id, body)); ok('Capture enregistrée')
    } catch (e) { err(errMsg(e)) } finally { setSaving(false) }
  }
  const del = async () => { if (!window.confirm('Supprimer cette capture et son fichier ?')) return; try { await social.assets.del(id); ok('Capture supprimée'); onClose() } catch (e) { err(errMsg(e)) } }
  const reanalyze = async () => { await runJob('Ré-analyse de la capture', () => social.assets.reanalyze(id)); setA(await social.assets.get(id)) }

  const zones = a.zones_sensibles || []
  const lm = a.legendes_montage || []

  return (
    <Modal wide title={a.titre_court || a.id} onClose={onClose} footer={<>
      <button className="sm-btn danger" onClick={del}>Supprimer</button><span className="sm-flex1" />
      <button className="sm-btn" onClick={reanalyze}>Ré-analyser (IA)</button>
      <button className="sm-btn" onClick={() => setStudio(true)}>Tester un montage</button>
      <button className="sm-btn pri" disabled={saving} onClick={save}>{saving ? <Spinner /> : 'Enregistrer'}</button></>}>
      <div className="sm-split">
        <div>
          <div className="sm-row sm-mb">
            <button className={`sm-btn xs${mode === 'focus' ? ' pri' : ''}`} onClick={() => setMode(mode === 'focus' ? '' : 'focus')}>▭ Dessiner la zone de zoom</button>
            <button className={`sm-btn xs${mode === 'blur' ? ' danger' : ''}`} onClick={() => setMode(mode === 'blur' ? '' : 'blur')}>▨ Ajouter une zone à flouter</button>
          </div>
          {mode && <p className="sm-info">Trace un rectangle sur l'image avec la souris.</p>}
          <div ref={box} className={`sm-imgbox${mode ? ' draw' : ''}`} onPointerDown={down} onPointerMove={move} onPointerUp={up}>
            <AuthImg path={social.assets.fileUrl(id)} />
            {a.zone_focus && <div className="sm-zone" style={{ left: `${a.zone_focus.x}%`, top: `${a.zone_focus.y}%`, width: `${a.zone_focus.w}%`, height: `${a.zone_focus.h}%` }} />}
            {zones.map((z, i) => <div key={i} className="sm-zone blur" style={{ left: `${z.x}%`, top: `${z.y}%`, width: `${z.w}%`, height: `${z.h}%` }} />)}
            {tmp && <div className={`sm-zone${mode === 'blur' ? ' blur' : ''}`} style={{ left: `${tmp.x}%`, top: `${tmp.y}%`, width: `${tmp.w}%`, height: `${tmp.h}%` }} />}
          </div>
          <div className="sm-mt">
            <p className="sm-label">Zone de zoom (violet)</p>
            {a.zone_focus ? <div className="sm-row"><span className="sm-xs">x {a.zone_focus.x}% · y {a.zone_focus.y}% · {a.zone_focus.w}×{a.zone_focus.h}%</span>
              <button className="sm-btn xs" onClick={() => set('zone_focus', { x: 0, y: 0, w: 100, h: 100 })}>Réinitialiser (image entière)</button></div> : <span className="sm-xs sm-mut">Aucune — l'image entière est utilisée.</span>}
            <p className="sm-label sm-mt">Zones floutées (rouge) — {zones.length}</p>
            {zones.map((z, i) => (
              <div className="sm-row sm-mb" key={i}>
                <select className="sm-select" style={{ width: 140 }} value={z.nature || 'autre'} onChange={e => set('zones_sensibles', zones.map((x, j) => (j === i ? { ...x, nature: e.target.value } : x)))}>
                  {['nom', 'visage', 'salaire', 'telephone', 'email', 'adresse', 'identifiant', 'autre'].map(n => <option key={n}>{n}</option>)}</select>
                <span className="sm-xs sm-mut sm-flex1">{z.x}% / {z.y}% — {z.w}×{z.h}%</span>
                <button className="sm-btn xs danger" onClick={() => set('zones_sensibles', zones.filter((_, j) => j !== i))}>×</button>
              </div>
            ))}
            <Switch checked={!!a.donnees_personnelles_visibles} onChange={v => set('donnees_personnelles_visibles', v)} label="Cette capture contient des données personnelles" />
            <p className="sm-hint sm-mt">Si cochée sans zone floutée, la capture n'est jamais utilisée dans un post.</p>
          </div>
        </div>

        <div>
          <div className="sm-grid g2">
            <Field label="Module"><input className="sm-input" value={a.module || ''} onChange={e => set('module', e.target.value)} /></Field>
            <Field label="Type"><select className="sm-select" value={a.type_image || 'capture_logiciel'} onChange={e => set('type_image', e.target.value)}>
              {['capture_logiciel', 'logo', 'schema', 'illustration', 'photo', 'autre'].map(t => <option key={t}>{t}</option>)}</select></Field>
          </div>
          <Field label="Titre court"><input className="sm-input" value={a.titre_court || ''} onChange={e => set('titre_court', e.target.value)} /></Field>
          <Field label="Écran"><input className="sm-input" value={a.ecran || ''} onChange={e => set('ecran', e.target.value)} /></Field>
          <Field label="Description"><textarea className="sm-textarea" value={a.description || ''} onChange={e => set('description', e.target.value)} /></Field>
          <Field label="Fonctionnalités visibles"><TagInput value={asArr(a.fonctionnalites_visibles)} onChange={v => set('fonctionnalites_visibles', v)} /></Field>
          <Field label="Mots-clés (servent à la sélection automatique)"><TagInput value={asArr(a.mots_cles)} onChange={v => set('mots_cles', v)} /></Field>
          <Field label="Hashtags"><TagInput hash value={asArr(a.hashtags)} onChange={v => set('hashtags', v)} /></Field>
          <Field label="Réseaux recommandés"><PlatformPicker value={asArr(a.plateformes_recommandees)} onChange={v => set('plateformes_recommandees', v)} /></Field>
          <Field label="Titres de montage proposés">
            {lm.map((l, i) => (
              <div className="sm-row sm-mb" key={i}>
                <input className="sm-input sm-flex1" placeholder="Titre" value={l.titre} onChange={e => set('legendes_montage', lm.map((x, j) => (j === i ? { ...x, titre: e.target.value } : x)))} />
                <input className="sm-input sm-flex1" placeholder="Sous-titre" value={l.sous_titre} onChange={e => set('legendes_montage', lm.map((x, j) => (j === i ? { ...x, sous_titre: e.target.value } : x)))} />
                <button className="sm-btn xs danger" onClick={() => set('legendes_montage', lm.filter((_, j) => j !== i))}>×</button>
              </div>))}
            <button className="sm-btn xs" style={{ alignSelf: 'flex-start' }} onClick={() => set('legendes_montage', [...lm, { titre: '', sous_titre: '' }])}>+ Ajouter</button>
          </Field>
          <Field label="Notes admin"><input className="sm-input" value={a.notes_admin || ''} onChange={e => set('notes_admin', e.target.value)} /></Field>
          <Switch checked={!!a.exclu} onChange={v => set('exclu', v)} label="Exclure cette capture des posts" />
          {!!a.qualite && <p className="sm-hint sm-mt">Qualité estimée : lisibilité {a.qualite.lisibilite}/100 · esthétique {a.qualite.esthetique}/100 · modèle {a.modele}</p>}
        </div>
      </div>
      {studio && <MontageStudio initialAssets={[id]} onClose={() => setStudio(false)} />}
    </Modal>
  )
}

/* ═════════════════════════ Studio de montage ═════════════════════════ */
export function MontageStudio({ initialAssets = [], onClose }: { initialAssets?: string[]; onClose: () => void }) {
  const { err, runJob } = useSocial()
  const [plat, setPlat] = useState<Platform>('instagram')
  const [tpl, setTpl] = useState('capture_cadree')
  const [ids, setIds] = useState<string[]>(initialAssets)
  const [titre, setTitre] = useState(''); const [sous, setSous] = useState(''); const [badge, setBadge] = useState(''); const [uq, setUq] = useState(''); const [ratio, setRatio] = useState('')
  const [urls, setUrls] = useState<string[]>([]); const [busy, setBusy] = useState(false); const [pick, setPick] = useState(false)

  const run = async () => {
    setBusy(true)
    try {
      const body: Record<string, unknown> = { plateforme: plat, template: tpl, asset_ids: ids, titre_carte: titre, sous_titre: sous, badge, unsplash_query: uq, slides: tpl === 'carrousel' ? ids.map(a => ({ asset_id: a })) : [] }
      if (ratio) body.ratio = ratio
      const res: any = await social.assets.preview(body)
      if (res.job_id) { const r = await runJob('Montage vidéo', async () => res); setUrls(r?.urls || []) }
      else setUrls(res.urls)
    } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <Modal wide title="Studio de montage" onClose={onClose} footer={<button className="sm-btn" onClick={onClose}>Fermer</button>}>
      <div className="sm-split">
        <div>
          <div className="sm-grid g2">
            <Field label="Réseau"><select className="sm-select" value={plat} onChange={e => setPlat(e.target.value as Platform)}>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select></Field>
            <Field label="Modèle"><select className="sm-select" value={tpl} onChange={e => setTpl(e.target.value)}>{TEMPLATES.filter(t => t.id !== 'aucun').map(t => <option key={t.id} value={t.id}>{t.label}</option>)}</select></Field>
          </div>
          <Field label="Captures"><div className="sm-row">
            {ids.map(i => <div key={i} style={{ width: 84, height: 54, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--line)' }}><AuthImg path={social.assets.fileUrl(i)} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} /></div>)}
            <button className="sm-btn xs" onClick={() => setPick(true)}>Choisir…</button></div></Field>
          <Field label="Titre"><input className="sm-input" value={titre} onChange={e => setTitre(e.target.value)} placeholder="Bulletins validés en 1 clic" /></Field>
          <Field label="Sous-titre"><input className="sm-input" value={sous} onChange={e => setSous(e.target.value)} /></Field>
          <div className="sm-grid g2">
            <Field label="Badge"><input className="sm-input" value={badge} onChange={e => setBadge(e.target.value)} placeholder="PAIE" /></Field>
            <Field label="Format"><select className="sm-select" value={ratio} onChange={e => setRatio(e.target.value)}><option value="">Défaut du réseau</option><option value="carre">Carré</option><option value="portrait">Portrait</option><option value="paysage">Paysage</option></select></Field>
          </div>
          {tpl === 'photo_overlay' && <Field label="Recherche photo (anglais)"><input className="sm-input" value={uq} onChange={e => setUq(e.target.value)} placeholder="hr team office" /></Field>}
          <button className="sm-btn pri" disabled={busy} onClick={run}>{busy ? <><Spinner /> Génération…</> : 'Générer l\'aperçu'}</button>
        </div>
        <div>
          {urls.length ? (
            <div className="sm-prevs">
              {urls.map(u =>
                isVideo(u) ? (
                  <video
                    key={u}
                    src={u}
                    controls
                    playsInline
                    preload="metadata"
                    style={{ width: '100%', borderRadius: 10, display: 'block' }}
                  />
                ) : (
                  <img key={u} src={u} alt="aperçu" />
                )
              )}
            </div>
          ) : (
            <Empty title="Aperçu">Aucun visuel pour l'instant. Aucun post n'est créé : c'est un test.</Empty>
          )}
        </div>

      </div>
      {pick && <AssetPicker multi={tpl === 'carrousel'} selected={ids} onClose={() => setPick(false)} onConfirm={v => { setIds(v); setPick(false) }} />}
    </Modal>
  )
}

/* ═════════════════════════ Photos libres ═════════════════════════ */
function StockSearch({ onClose }: { onClose: () => void }) {
  const { err } = useSocial()
  const [q, setQ] = useState(''); const [o, setO] = useState('landscape'); const [res, setRes] = useState<any[]>([]); const [busy, setBusy] = useState(false)
  const go = async () => { if (!q.trim()) return; setBusy(true); try { setRes(await social.assets.stock(q, o)) } catch (e) { err(errMsg(e)) } finally { setBusy(false) } }
  return (
    <Modal wide title="Photos libres de droits (Unsplash / Pexels)" onClose={onClose}>
      <div className="sm-row sm-mb"><input className="sm-input sm-flex1" placeholder="Mots-clés en anglais : team meeting, african office…" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && go()} />
        <select className="sm-select" style={{ width: 140 }} value={o} onChange={e => setO(e.target.value)}><option value="landscape">Paysage</option><option value="portrait">Portrait</option><option value="squarish">Carré</option></select>
        <button className="sm-btn pri" onClick={go} disabled={busy}>{busy ? <Spinner /> : 'Chercher'}</button></div>
      <p className="sm-hint sm-mb">Aperçu de ce que renverra le montage « Photo + titre ». Le crédit du photographe est ajouté automatiquement au visuel.</p>
      <div className="sm-assets">{res.map(r => <div className="sm-asset" key={r.source + r.id}><div className="im"><img src={r.thumb} alt={r.alt} /></div><div className="b"><span className="sm-xs">{r.author} · {r.source}</span><a className="sm-xs" href={r.page_url} target="_blank" rel="noreferrer">Voir ↗</a></div></div>)}</div>
    </Modal>
  )
}