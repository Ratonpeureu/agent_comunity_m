// src/pages/social/Media.tsx
import React, { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fmtDateTime, MediaItem, mediaSrc, prettify, social } from '../../lib/social'
import { AuthImg, Badge, Empty, Loading, MediaImg, Modal, PageHead, Pills, PlatformIcon, Stat, StatusBadge, useLoad, useSocial } from './ui'

const KINDS = [
  { id: '', label: 'Tout' }, { id: 'capture', label: 'Captures du logiciel' }, { id: 'logo', label: 'Logos' },
  { id: 'montage', label: 'Montages' }, { id: 'video', label: 'Vidéos' }, { id: 'stock', label: 'Photos libres' }, { id: 'audio', label: 'Audio' },
]
const KIND_LABEL: Record<string, string> = { capture: 'Capture', logo: 'Logo', montage: 'Montage', video: 'Vidéo', stock: 'Photo libre', audio: 'Audio' }
const fmtSize = (n?: number | null) => (n == null ? '' : n < 1048576 ? `${Math.round(n / 1024)} Ko` : `${(n / 1048576).toFixed(1)} Mo`)

function Thumb({ m, big }: { m: MediaItem; big?: boolean }) {
  if (m.kind === 'audio') return big
    ? <audio src={mediaSrc(m.url)} controls style={{ width: '100%' }} />
    : <div className="mm-audio"><span>♪</span><small>{m.title}</small></div>
  if (m.kind === 'video') return <video src={mediaSrc(m.url)} poster={m.poster ? mediaSrc(m.poster) : undefined} muted={!big} controls={big} loop playsInline preload={big ? 'auto' : 'none'}
    style={{ width: '100%', height: big ? 'auto' : '100%', objectFit: big ? 'contain' : 'cover', maxHeight: big ? '70vh' : undefined }} />
  if (m.private_path) return <AuthImg path={m.private_path} alt={m.title} style={big ? { width: '100%', height: 'auto', maxHeight: '70vh', objectFit: 'contain' } : undefined} />
  return <MediaImg src={m.url} alt={m.title} style={big ? { width: '100%', height: 'auto', maxHeight: '70vh', objectFit: 'contain' } : undefined} />
}

function Card({ m, onOpen }: { m: MediaItem; onOpen: () => void }) {
  const box = useRef<HTMLDivElement>(null)
  const vid = () => box.current?.querySelector('video') as HTMLVideoElement | null
  return (
    <div className="mm-card" onClick={onOpen}
      onMouseEnter={() => { vid()?.play().catch(() => {}) }} onMouseLeave={() => { const v = vid(); if (v) { v.pause(); v.currentTime = 0 } }}>
      <div className="mm-th" ref={box}>
        <Thumb m={m} />
        <span className="mm-kind">{KIND_LABEL[m.kind]}</span>
        {m.post && <span className="mm-plat"><PlatformIcon p={m.post.plateforme} size={24} /></span>}
        {m.kind === 'video' && <span className="mm-play">▶</span>}
        <div className="mm-pop">
          <b>{m.title}</b>
          <p>{m.description || 'Pas de description'}</p>
          {!!m.tags.length && <small>{m.tags.slice(0, 4).join(' ')}</small>}
        </div>
      </div>
      <div className="mm-meta">
        <span className="t">{m.title}</span>
        <span className="sm-xs sm-mut">{m.module ? prettify(m.module) : fmtDateTime(m.created_at)}</span>
      </div>
    </div>
  )
}

export function Media() {
  const { tick } = useSocial()
  const nav = useNavigate()
  const [kind, setKind] = useState('')
  const [q, setQ] = useState('')
  const [plat, setPlat] = useState('')
  const [open, setOpen] = useState<MediaItem | null>(null)
  const { data, loading } = useLoad(async () => ({ m: await social.assets.media(), d: await social.assets.diagnostic().catch(() => null) }), [tick])

  const items = data?.m.items || []
  const counts = data?.m.counts || {}
  const shown = useMemo(() => items.filter(i => {
    if (kind && i.kind !== kind) return false
    if (plat && i.post?.plateforme !== plat) return false
    const t = q.trim().toLowerCase()
    return !t || [i.title, i.description, i.module, i.tags.join(' ')].join(' ').toLowerCase().includes(t)
  }), [items, kind, q, plat])

  if (loading && !data) return <Loading />
  const d = data?.d
  const usable = d?.raisons?.utilisable ?? 0
  const blocked = d?.raisons?.donnees_perso_sans_zone_floutee ?? 0

  return (
    <div>
      <PageHead title="Médiathèque" sub="Tout ce que l'agent a utilisé ou produit : captures, logos, montages, vidéos, photos libres, audio. Survole une vignette pour sa description." />
      {d && (
        <div className="sm-grid g4 sm-mb">
          <Stat label="Captures utilisables" value={usable} hint={`${d.valides} analysées`} />
          <Stat label="Bloquées (données perso)" value={blocked} hint={blocked ? 'Dessine les zones à flouter' : 'RAS'} trend={blocked ? 'down' : 'up'} />
          <Stat label="Photos à analyser" value={d.photos_a_analyser} hint={d.photos_a_analyser ? 'Analyse au démarrage ou bouton' : 'À jour'} />
          <Stat label="Montages / vidéos" value={`${counts.montage || 0} / ${counts.video || 0}`} hint={`${counts.audio || 0} pistes audio`} />
        </div>
      )}
      {d && d.orphelins > 0 && <div className="sm-note">{d.orphelins} fiche(s) YAML sans fichier image dans <code>{d.assets_dir}</code> : le dossier <code>data</code> n'est probablement pas partagé entre api et worker.</div>}
      <div className="sm-row sm-mb">
        <input className="sm-input" style={{ maxWidth: 340 }} placeholder="Rechercher (titre, module, hashtag…)" value={q} onChange={e => setQ(e.target.value)} />
        <div className="sm-chips">
          <button className={`sm-chip pl${!plat ? ' on' : ''}`} onClick={() => setPlat('')}>Tous réseaux</button>
          {(['linkedin', 'facebook', 'instagram', 'x', 'tiktok'] as const).map(p => (
            <button key={p} className={`sm-chip pl${plat === p ? ' on' : ''}`} style={{ padding: '3px 10px 3px 4px', gap: 5 }} onClick={() => setPlat(p)}><PlatformIcon p={p} size={20} /></button>
          ))}
        </div>
      </div>
      <Pills items={KINDS.map(k => ({ ...k, count: k.id ? counts[k.id] || 0 : items.length }))} value={kind} onChange={setKind} />

      {!shown.length ? <Empty title="Aucun média">Les captures apparaissent après l'analyse ; les montages et vidéos après la rédaction d'un post.</Empty> : (
        <div className="mm-grid">{shown.map(m => <Card key={m.id} m={m} onOpen={() => setOpen(m)} />)}</div>
      )}

      {open && (
        <Modal wide title={open.title} onClose={() => setOpen(null)}
          footer={<>{open.post && <button className="sm-btn pri" onClick={() => nav(`/social-agent/posts?open=${open.post!.id}`)}>Ouvrir le post</button>}
            {open.url && <a className="sm-btn" href={mediaSrc(open.url)} target="_blank" rel="noreferrer">Ouvrir le fichier ↗</a>}
            <button className="sm-btn" onClick={() => setOpen(null)}>Fermer</button></>}>
          <div className="sm-split">
            <div style={{ background: '#0b1020', borderRadius: 12, padding: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Thumb m={open} big /></div>
            <div>
              <div className="sm-row sm-mb"><Badge tone="blue">{KIND_LABEL[open.kind]}</Badge>{open.module && <Badge>{prettify(open.module)}</Badge>}
                {open.sensible && <Badge tone="red">Données perso non floutées</Badge>}{open.exclu && <Badge>Exclue</Badge>}</div>
              <p style={{ whiteSpace: 'pre-wrap' }}>{open.description || 'Pas de description.'}</p>
              {!!open.tags.length && <div className="sm-chips sm-mt">{open.tags.map(t => <span key={t} className="sm-chip">{t}</span>)}</div>}
              <dl className="sm-kv sm-mt">
                {open.created_at && <><dt>Date</dt><dd>{fmtDateTime(open.created_at)}</dd></>}
                {open.size != null && <><dt>Taille</dt><dd>{fmtSize(open.size)}</dd></>}
                {open.usage_30j != null && <><dt>Utilisée</dt><dd>{open.usage_30j}× en 30 j</dd></>}
              </dl>
              {open.post && (
                <div className="sm-card sm-mt"><div className="sm-card-b">
                  <div className="sm-row sm-mb"><PlatformIcon p={open.post.plateforme} size={26} /><StatusBadge s={open.post.statut} />{open.post.template && <Badge tone="violet">{open.post.template}</Badge>}</div>
                  <p className="sm-xs" style={{ whiteSpace: 'pre-wrap' }}>{open.post.extrait}</p>
                  {open.post.erreur_montage && <div className="sm-err sm-xs sm-mt">Erreur de montage : {open.post.erreur_montage}</div>}
                </div></div>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}