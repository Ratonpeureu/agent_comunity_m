// src/pages/social/Ideas.tsx
import React, { useState } from 'react'

import { ALLOWED_FORMATS, DEFAULT_FORMAT, errMsg, Format, FORMAT_LABEL, Idea, Platform, pmeta, prettify, social } from '../../lib/social'
import { Badge, Empty, Field, Loading, Modal, PageHead, PlatformDot, PlatformIcon, PlatformPicker, Pills, Switch, useLoad, useSocial } from './ui'


const OBJ: Record<string, string> = { notoriete: 'Notoriété', engagement: 'Engagement', conversion: 'Conversion', autorite: 'Autorité' }

export function Ideas() {
  const { tick, runJob, ok, err } = useSocial()
  const [statut, setStatut] = useState('propose')
  const [gen, setGen] = useState(false)
  const [writing, setWriting] = useState<Idea | null>(null)
  const { data, loading, reload } = useLoad(() => social.ideas(statut), [statut, tick])

  const patch = async (i: Idea, s: string) => {
    let motif: string | undefined
    if (s === 'rejete') { const m = window.prompt('Pourquoi rejeter cette idée ? (aide l\'IA à mieux cibler)'); if (m === null) return; motif = m }
    try { await social.patchIdea(i.id, { statut: s, motif_rejet: motif }); ok(s === 'rejete' ? 'Idée rejetée' : 'Idée acceptée'); reload() } catch (e) { err(errMsg(e)) }
  }

  return (
    <div>
      <PageHead title="Idées de publications" sub="Basées sur ton identité, les actualités du secteur, tes stats et tes captures disponibles.">
        <button className="sm-btn pri" onClick={() => setGen(true)}>Générer des idées</button>
      </PageHead>
      <Pills items={[{ id: 'propose', label: 'Proposées' }, { id: 'accepte', label: 'Acceptées' }, { id: 'redige', label: 'Rédigées' }, { id: 'rejete', label: 'Rejetées' }]} value={statut} onChange={setStatut} />

      {loading && !data ? <Loading /> : !data?.length ? <Empty title="Aucune idée ici">Clique sur « Générer des idées » : l'agent en propose une dizaine, dédoublonnées.</Empty> : (
        <div className="sm-auto" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(340px,1fr))' }}>
          {data.map(i => (
            <div className="sm-idea" key={i.id}>
              <div className="sm-row">
                <Badge tone="violet">{prettify(i.pilier) || 'Libre'}</Badge><Badge tone="blue">{OBJ[i.objectif] || i.objectif}</Badge>
                <Badge>{prettify(i.format_conseille)}</Badge>{i.urgence === 'actualite' && <Badge tone="amber">Actualité</Badge>}
              </div>
              <h4>{i.titre}</h4>
              <p className="sm-mut">{i.angle}</p>
              {i.accroche && <div className="acc">« {i.accroche} »</div>}
              <details><summary className="sm-xs sm-mut" style={{ cursor: 'pointer' }}>Pourquoi cette idée</summary><p className="sm-xs sm-mt">{i.justification}</p>
                {i.source_tendance_url && <a className="sm-xs" href={i.source_tendance_url} target="_blank" rel="noreferrer">Source de l'actualité ↗</a>}</details>
              <div className="sm-row">
                <div className="sm-chips">{i.plateformes.map(p => <PlatformDot key={p} p={p} />)}</div>
                <span className="sm-flex1" />
                <span className="sm-xs sm-mut" title="Potentiel estimé par l'IA">Potentiel {Math.round(i.score_potentiel)}/100</span>
              </div>
              <div className="act">
                <button className="sm-btn pri xs" onClick={() => setWriting(i)}>Rédiger les posts</button>
                {i.statut === 'propose' && <button className="sm-btn xs" onClick={() => patch(i, 'accepte')}>Accepter</button>}
                {i.statut !== 'rejete' && <button className="sm-btn danger xs" onClick={() => patch(i, 'rejete')}>Rejeter</button>}
              </div>
            </div>
          ))}
        </div>
      )}

      {gen && <GenerateModal onClose={() => setGen(false)} onGo={(b) => { setGen(false); runJob('Génération d\'idées', () => social.genIdeas(b)) }} />}
      {writing && <WriteModal idea={writing} onClose={() => setWriting(null)} onGo={(pl, ins, fm) => { const id = writing.id; setWriting(null); runJob('Rédaction des posts', () => social.writeIdea(id, pl, ins, fm)).then(r => { if (r?.posts_crees) ok(`${r.posts_crees} post(s) créé(s) — onglet Posts › À valider`) }) }} />}
    </div>
  )
}

function GenerateModal({ onClose, onGo }: { onClose: () => void; onGo: (b: { nb: number; thematique?: string; avec_tendances: boolean }) => void }) {
  const [nb, setNb] = useState(8); const [th, setTh] = useState(''); const [tr, setTr] = useState(true)
  return (
    <Modal title="Générer des idées" onClose={onClose} footer={<><button className="sm-btn" onClick={onClose}>Annuler</button><button className="sm-btn pri" onClick={() => onGo({ nb, thematique: th || undefined, avec_tendances: tr })}>Générer</button></>}>
      <Field label="Nombre d'idées"><input className="sm-input" type="number" min={3} max={15} value={nb} onChange={e => setNb(+e.target.value)} /></Field>
      <Field label="Thématique imposée (optionnel)" hint="Ex : « paie de fin de mois », « rentrée scolaire », « nouveau module congés »"><input className="sm-input" value={th} onChange={e => setTh(e.target.value)} /></Field>
      <Switch checked={tr} onChange={setTr} label="S'inspirer des actualités du secteur (Serper)" />
    </Modal>
  )
}


function WriteModal({ idea, onClose, onGo }: { idea: Idea; onClose: () => void; onGo: (pl: string[], ins: string, fm: Record<string, Format>) => void }) {
  const initFmt = (p: Platform): Format => {
    const al = ALLOWED_FORMATS[p]
    const wanted = idea.format_conseille as Format
    if (al.includes(wanted)) return wanted
    return DEFAULT_FORMAT[p] ?? (al.includes('image') ? 'image' : al[0])
  }
  const [pl, setPl] = useState<string[]>(idea.plateformes || [])
  const [fm, setFm] = useState<Record<string, Format>>(() => Object.fromEntries((idea.plateformes || []).map(p => [p, initFmt(p as Platform)])))
  const [ins, setIns] = useState('')
  const onPl = (v: string[]) => {
    setPl(v)
    setFm(f => { const n = { ...f }; v.forEach(p => { if (!n[p]) n[p] = initFmt(p as Platform) }); return n })
  }
  const hasVideo = pl.some(p => fm[p] === 'video')
  return (
    <Modal title={`Rédiger : ${idea.titre}`} onClose={onClose} footer={<><button className="sm-btn" onClick={onClose}>Annuler</button><button className="sm-btn pri" disabled={!pl.length} onClick={() => onGo(pl, ins, Object.fromEntries(pl.map(p => [p, fm[p]])) as Record<string, Format>)}>Rédiger {pl.length} version(s)</button></>}>
      <Field label="Plateformes" hint="Une version native est écrite pour chaque réseau, avec son visuel et son créneau optimal."><PlatformPicker value={pl} onChange={onPl} /></Field>
      {!!pl.length && (
        <Field label="Format de chaque publication">
          <div className="sm-list">
            {pl.map(p => (
              <div className="sm-item" key={p}>
                <PlatformIcon p={p} size={26} /><b style={{ width: 90 }}>{pmeta(p).label}</b>
                <div className="sm-chips">
                  {ALLOWED_FORMATS[p as Platform].map(f => (
                    <button key={f} type="button" className={`sm-chip pl${fm[p] === f ? ' on' : ''}`} onClick={() => setFm({ ...fm, [p]: f })}>{FORMAT_LABEL[f]}</button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Field>
      )}
      {hasVideo && <div className="sm-note">Chaque vidéo prend 1 à 3 minutes à monter. La rédaction sera plus longue.</div>}
      <Field label="Instruction spéciale (optionnel)" hint="Ex : « ton plus décontracté », « insiste sur le gain de temps », « mentionne la signature électronique »">
        <textarea className="sm-textarea" value={ins} onChange={e => setIns(e.target.value)} />
      </Field>
      <p className="sm-hint">{pl.map(p => `${pmeta(p).label} : ${fm[p] ? FORMAT_LABEL[fm[p]] : '—'}`).join(' · ')}</p>
    </Modal>
  )
}



