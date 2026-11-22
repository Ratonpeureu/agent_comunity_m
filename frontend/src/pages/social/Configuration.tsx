// src/pages/social/Configuration.tsx
import React, { useState } from 'react'
import { cfg, CfgField, CfgSection, UrlCheck, waitRestart } from '../../lib/config'
import { useAuth } from '../../lib/auth'
import { errMsg } from '../../lib/social'
import { Badge, Empty, Loading, Spinner, useLoad, useSocial } from './ui'

function UrlResult({ r }: { r: UrlCheck }) {
  if (!r.ok) return <div className="sm-err sm-xs">{r.erreur}</div>
  return (
    <div className={r.https ? 'sm-info sm-xs' : 'sm-note sm-xs'}>
      Joignable en {r.ms} ms : c'est bien cette application.
      {r.https ? '' : ' Attention : en HTTP, les réseaux qui téléchargent les médias (Meta, TikTok) exigent le HTTPS.'}
    </div>
  )
}

/* ═════════════════════ Configuration (ex-/setup) ═════════════════════ */
export function Configuration() {
  const { ok, err, info } = useSocial()
  const { data, loading, reload } = useLoad(() => cfg.get(), [])
  const [sec, setSec] = useState('')
  const [edit, setEdit] = useState<Record<string, string>>({})
  const [clear, setClear] = useState<string[]>([])
  const [show, setShow] = useState<Record<string, boolean>>({})
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState('')
  const [pending, setPending] = useState<string[]>([])
  const [url, setUrl] = useState<UrlCheck | null>(null)

  if (loading && !data) return <Loading />
  if (!data) return <Empty title="Configuration indisponible">Impossible de charger les paramètres.</Empty>

  const sections = data.sections
  const cur = sections.find(s => s.id === sec) || sections[0]
  const needle = q.trim().toLowerCase()
  const match = (f: CfgField) => !needle || `${f.label} ${f.key} ${f.hint}`.toLowerCase().includes(needle)
  const valueOf = (f: CfgField) => (f.key in edit ? edit[f.key] : f.secret ? '' : f.value)
  const isSet = (f: CfgField) => (clear.includes(f.key) ? false : f.key in edit ? !!edit[f.key] : f.set)
  const dirty = Object.keys(edit).length + clear.length
  const labelOf = (k: string) => sections.flatMap(s => s.fields).find(f => f.key === k)?.label || k

  const setVal = (f: CfgField, v: string) => {
    setEdit(e => {
      const n = { ...e }
      if ((f.secret && !v) || (!f.secret && v === f.value)) delete n[f.key]
      else n[f.key] = v
      return n
    })
    if (v) setClear(c => c.filter(k => k !== f.key))
  }
  const removeSecret = (f: CfgField) => {
    setClear(c => [...c, f.key])
    setEdit(e => { const n = { ...e }; delete n[f.key]; return n })
  }
  const discard = () => { setEdit({}); setClear([]) }

  const save = async () => {
    setBusy('save')
    try {
      const r = await cfg.put({ values: edit, clear })
      if (!r.changed.length) info('Aucune modification')
      else ok(`${r.changed.length} paramètre(s) enregistré(s)`)
      setPending(p => Array.from(new Set([...p, ...r.restart_required])))
      setEdit({}); setClear([]); reload()
    } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }

  const checkUrl = async (f: CfgField) => {
    setBusy('url')
    try { setUrl(await cfg.checkUrl(valueOf(f))) } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }

  const restart = async () => {
    if (!window.confirm('Redémarrer l\'application maintenant ? Les tâches en cours (montage vidéo, rédaction) seront interrompues.')) return
    setBusy('restart')
    try {
      const before = (await fetch('/health').then(r => r.json()).catch(() => ({}))).boot
      await cfg.restart()
      await waitRestart(before)
      ok('Application redémarrée')
      window.location.reload()
    } catch (e) { err(errMsg(e)); setBusy('') }
  }

  const renderField = (f: CfgField) => {
    const v = valueOf(f)
    const removed = clear.includes(f.key)
    return (
      <div className="sm-field" key={f.key}>
        <div className="cf-meta">
          <label className="sm-label">{f.label}</label>
          {f.secret && (removed ? <Badge tone="amber">Sera retiré</Badge>
            : f.set ? <Badge tone="green">Défini{f.last4 ? ` ····${f.last4}` : ''}</Badge> : <Badge>Non défini</Badge>)}
          {f.restart && <Badge tone="violet">Redémarrage</Badge>}
          <span className="cf-key">{f.key}</span>
        </div>
        <div className="cf-row">
          {f.kind === 'select' ? (
            <select className="sm-select" value={v} onChange={e => setVal(f, e.target.value)}>
              <option value="">Défaut</option>
              {f.options.map(o => <option key={o} value={o}>{o}</option>)}
            </select>
          ) : (
            <input className="sm-input" name={f.key} disabled={removed} autoComplete={f.secret ? 'new-password' : 'off'}
              type={f.secret ? (show[f.key] ? 'text' : 'password') : f.kind === 'number' ? 'number' : 'text'}
              placeholder={f.secret ? (f.set ? 'Laisser vide pour conserver' : 'Coller la clé') : f.placeholder}
              value={v} onChange={e => setVal(f, e.target.value)} />
          )}
          {f.secret && <button type="button" className="sm-btn" onClick={() => setShow({ ...show, [f.key]: !show[f.key] })}>{show[f.key] ? 'Masquer' : 'Afficher'}</button>}
          {f.secret && f.set && (removed
            ? <button type="button" className="sm-btn" onClick={() => setClear(c => c.filter(k => k !== f.key))}>Annuler</button>
            : <button type="button" className="sm-btn danger" onClick={() => removeSecret(f)}>Retirer</button>)}
          {f.key === 'PUBLIC_BASE_URL' && <button type="button" className="sm-btn" disabled={busy === 'url' || !v} onClick={() => checkUrl(f)}>{busy === 'url' ? <Spinner /> : 'Vérifier'}</button>}
        </div>
        {f.hint && <span className="sm-hint">{f.hint}</span>}
        {f.warn && <span className="sm-hint" style={{ color: 'var(--warn)' }}>{f.warn}</span>}
        {f.key === 'PUBLIC_BASE_URL' && url && <UrlResult r={url} />}
      </div>
    )
  }

  const fieldsOf = (s: CfgSection) => {
    let last: string | null | undefined
    return s.fields.filter(match).map(f => {
      const head = f.group && f.group !== last ? <p className="cf-grp" key={`g-${f.key}`}>{f.group}</p> : null
      last = f.group
      return <React.Fragment key={f.key}>{head}{renderField(f)}</React.Fragment>
    })
  }

  return (
    <div>
      {!!pending.length && (
        <div className="sm-note sm-row" style={{ justifyContent: 'space-between' }}>
          <span>Redémarrage nécessaire pour appliquer : {pending.map(labelOf).join(', ')}.</span>
          <button className="sm-btn pri xs" disabled={busy === 'restart'} onClick={restart}>{busy === 'restart' ? <><Spinner /> Redémarrage…</> : 'Redémarrer maintenant'}</button>
        </div>
      )}
      <div className="sm-row sm-mb">
        <input className="sm-input cf-search" placeholder="Rechercher un paramètre (nom, clé, mot-clé)…" value={q} onChange={e => setQ(e.target.value)} />
        <span className="sm-xs sm-mut">Les clés et réglages sont appliqués immédiatement, sauf ceux marqués « Redémarrage ».</span>
      </div>

      <div className="cf-layout">
        <nav className="cf-nav">
          {sections.map(s => (
            <button key={s.id} type="button" className={!needle && cur.id === s.id ? 'on' : ''} onClick={() => { setQ(''); setSec(s.id) }}>
              <span>{s.title}</span><em>{s.fields.filter(isSet).length}/{s.fields.length}</em>
            </button>
          ))}
        </nav>

        <div>
          {needle ? (
            sections.filter(s => s.fields.some(match)).map(s => (
              <div className="sm-card" key={s.id}><div className="sm-card-h"><h3>{s.title}</h3></div><div className="sm-card-b">{fieldsOf(s)}</div></div>
            ))
          ) : (
            <div className="sm-card">
              <div className="sm-card-h"><div><h3>{cur.title}</h3><p className="sm-xs sm-mut">{cur.desc}</p></div></div>
              <div className="sm-card-b">{fieldsOf(cur)}</div>
            </div>
          )}
          {needle && !sections.some(s => s.fields.some(match)) && <Empty title="Aucun résultat">Essaie un autre mot-clé.</Empty>}

          {dirty > 0 && (
            <div className="cf-bar">
              <span>{dirty} modification(s) non enregistrée(s)</span>
              <button className="sm-btn" onClick={discard}>Annuler</button>
              <button className="sm-btn ok" disabled={busy === 'save'} onClick={save}>{busy === 'save' ? <Spinner /> : 'Enregistrer'}</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ═════════════════════ Compte administrateur ═════════════════════ */
export function Compte() {
  const { ok, err } = useSocial()
  const { token, username, login } = useAuth()
  const [user, setUser] = useState(username || 'admin')
  const [cur, setCur] = useState(''); const [pw, setPw] = useState(''); const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false)
  const mismatch = !!pw && pw !== pw2
  const userChanged = user.trim() !== (username || 'admin') && user.trim().length >= 3
  const pwOk = !!pw && pw.length >= 8 && !mismatch
  const can = !!cur && (pwOk || (!pw && userChanged)) && !mismatch

  const save = async () => {
    setBusy(true)
    try {
      const r = await cfg.admin({ current_password: cur, username: user.trim(), new_password: pw })
      if (token) login(token, r.username)
      ok('Compte mis à jour'); setCur(''); setPw(''); setPw2('')
    } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }

  return (
    <div className="sm-card" style={{ maxWidth: 560 }}>
      <div className="sm-card-h"><div><h3>Compte administrateur</h3><p className="sm-xs sm-mut">Identifiant et mot de passe de connexion à l'interface.</p></div></div>
      <div className="sm-card-b">
        <div className="sm-field"><label className="sm-label">Identifiant</label>
          <input className="sm-input" value={user} onChange={e => setUser(e.target.value)} autoComplete="username" /></div>
        <div className="sm-field"><label className="sm-label">Nouveau mot de passe (vide = inchangé)</label>
          <input className="sm-input" type="password" value={pw} onChange={e => setPw(e.target.value)} autoComplete="new-password" />
          <span className="sm-hint">8 caractères minimum.</span></div>
        {!!pw && (
          <div className="sm-field"><label className="sm-label">Confirmer le nouveau mot de passe</label>
            <input className="sm-input" type="password" value={pw2} onChange={e => setPw2(e.target.value)} autoComplete="new-password" />
            {mismatch && <span className="sm-hint" style={{ color: 'var(--err)' }}>Les deux mots de passe ne correspondent pas.</span>}</div>
        )}
        <div className="sm-field"><label className="sm-label">Mot de passe actuel (obligatoire pour valider)</label>
          <input className="sm-input" type="password" value={cur} onChange={e => setCur(e.target.value)} autoComplete="current-password" /></div>
        <button className="sm-btn pri" disabled={busy || !can} onClick={save}>{busy ? <Spinner /> : 'Mettre à jour le compte'}</button>
        <p className="sm-hint sm-mt">Le changement est immédiat. Les sessions déjà ouvertes restent valides jusqu'à leur expiration.</p>
      </div>
    </div>
  )
}