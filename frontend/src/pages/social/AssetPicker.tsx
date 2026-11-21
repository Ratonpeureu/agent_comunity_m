// src/pages/social/AssetPicker.tsx
import React, { useMemo, useState } from 'react'
import { Asset, prettify, social } from '../../lib/social'
import { AuthImg, Badge, Empty, Loading, Modal, Pills, useLoad } from './ui'

export function AssetPicker({ selected, multi, onConfirm, onClose }: {
  selected: string[]; multi: boolean; onConfirm: (ids: string[]) => void; onClose: () => void
}) {
  const [sel, setSel] = useState<string[]>(selected)
  const [q, setQ] = useState('')
  const [mod, setMod] = useState('')
  const { data, loading } = useLoad(() => social.assets.list({ include_excluded: false }), [])

  const items = useMemo(() => (data || []).filter(a => a.type_image !== 'logo'), [data])
  const modules = useMemo(() => Array.from(new Set(items.map(a => a.module || 'autre'))).sort(), [items])
  const shown = items.filter(a => {
    if (mod && (a.module || 'autre') !== mod) return false
    const t = q.trim().toLowerCase()
    return !t || [a.titre_court, a.ecran, a.module, (a.hashtags || []).join(' '), (a.mots_cles || []).join(' ')].join(' ').toLowerCase().includes(t)
  })

  const toggle = (a: Asset) => {
    if (a.sensible_non_masque) return
    setSel(s => multi ? (s.includes(a.id) ? s.filter(x => x !== a.id) : [...s, a.id]) : [a.id])
  }

  return (
    <Modal wide title={multi ? 'Choisir les captures (ordre = ordre des slides)' : 'Choisir une capture'} onClose={onClose}
      footer={<>
        <button className="sm-btn" onClick={onClose}>Annuler</button>
        <button className="sm-btn pri" disabled={!sel.length} onClick={() => onConfirm(sel)}>Valider ({sel.length})</button>
      </>}>
      <input className="sm-input sm-mb" placeholder="Rechercher une capture (module, mot-clé, hashtag…)" value={q} onChange={e => setQ(e.target.value)} />
      <Pills items={[{ id: '', label: 'Tous' }, ...modules.map(m => ({ id: m, label: prettify(m) }))]} value={mod} onChange={setMod} />
      {loading ? <Loading /> : !shown.length ? <Empty title="Aucune capture">Analyse d'abord tes captures dans l'onglet « Captures ».</Empty> : (
        <div className="sm-assets">
          {shown.map(a => {
            const idx = sel.indexOf(a.id)
            return (
              <div key={a.id} className={`sm-asset${idx >= 0 ? ' sel' : ''}${a.sensible_non_masque ? ' dis' : ''}`} onClick={() => toggle(a)}
                title={a.sensible_non_masque ? 'Données personnelles non floutées : corrige-la dans « Captures »' : ''}>
                <div className="im"><AuthImg path={social.assets.fileUrl(a.id)} alt={a.titre_court} /></div>
                <div className="b">
                  <span className="t">{a.titre_court || a.id}</span>
                  <div className="sm-row"><Badge tone="blue">{prettify(a.module)}</Badge>{a.sensible_non_masque && <Badge tone="red">Données perso</Badge>}</div>
                </div>
                {idx >= 0 && multi && <span className="tag sm-badge violet">#{idx + 1}</span>}
              </div>
            )
          })}
        </div>
      )}
    </Modal>
  )
}