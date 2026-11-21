// src/pages/social/Replies.tsx
import React, { useState } from 'react'
import { errMsg, Platform, PLATFORMS, pmeta, social } from '../../lib/social'
import { Badge, Empty, Field, PageHead, Spinner, copyText, useSocial } from './ui'

const TYPES: Record<string, { l: string; t: string }> = { question: { l: 'Question', t: 'blue' }, compliment: { l: 'Compliment', t: 'green' }, critique: { l: 'Critique', t: 'red' }, spam: { l: 'Spam', t: 'gray' }, lead: { l: 'Prospect', t: 'violet' } }

export function Replies() {
  const { err, info } = useSocial()
  const [pl, setPl] = useState<Platform>('linkedin'); const [com, setCom] = useState(''); const [ctx, setCtx] = useState('')
  const [res, setRes] = useState<Awaited<ReturnType<typeof social.replySuggestions>> | null>(null); const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try { setRes(await social.replySuggestions({ plateforme: pl, commentaire: com, contexte_post: ctx })) } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  const t = res ? TYPES[res.type_commentaire] || { l: res.type_commentaire, t: 'gray' } : null
  return (
    <div>
      <PageHead title="Assistant de réponses" sub="Colle un commentaire reçu : l'agent propose 3 réponses dans la voix de ta marque." />
      <div className="sm-split">
        <div className="sm-card"><div className="sm-card-b">
          <Field label="Réseau"><select className="sm-select" value={pl} onChange={e => setPl(e.target.value as Platform)}>{PLATFORMS.map(p => <option key={p} value={p}>{pmeta(p).label}</option>)}</select></Field>
          <Field label="Commentaire reçu"><textarea className="sm-textarea" value={com} onChange={e => setCom(e.target.value)} /></Field>
          <Field label="Contexte : texte du post concerné (optionnel)"><textarea className="sm-textarea" value={ctx} onChange={e => setCtx(e.target.value)} /></Field>
          <button className="sm-btn pri" disabled={busy || !com.trim()} onClick={go}>{busy ? <Spinner /> : 'Proposer des réponses'}</button>
        </div></div>
        <div>
          {!res ? <Empty title="Réponses suggérées">Les critiques et plaintes déclenchent une désescalade et un passage en privé.</Empty> : <>
            <div className="sm-row sm-mb">{t && <Badge tone={t.t}>{t.l}</Badge>}<span className="sm-mut">{res.action_recommandee}</span></div>
            {res.reponses.map((r, i) => (
              <div className="sm-card" key={i}><div className="sm-card-b"><p style={{ whiteSpace: 'pre-wrap' }}>{r}</p>
                <button className="sm-btn xs sm-mt" onClick={async () => { await copyText(r); info('Réponse copiée') }}>Copier</button></div></div>
            ))}
          </>}
        </div>
      </div>
    </div>
  )
}