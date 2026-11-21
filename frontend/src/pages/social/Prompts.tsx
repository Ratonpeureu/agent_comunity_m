// src/pages/social/Prompts.tsx
import React, { useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'
import { errMsg } from '../../lib/social'
import { Badge, Loading, PageHead, Pills, Spinner, useLoad, useSocial } from './ui'

interface P { key: string; label: string; group: string; help: string; default: string; value: string; modifie: boolean }

export function Prompts() {
  const { ok, err } = useSocial()
  const { data, loading, reload } = useLoad(() => apiFetch('/admin/social/prompts') as Promise<P[]>, [])
  const [group, setGroup] = useState('')
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')
  useEffect(() => { if (data) setVals(Object.fromEntries(data.map(p => [p.key, p.value]))) }, [data])
  if (loading && !data) return <Loading />
  const groups = Array.from(new Set((data || []).map(p => p.group)))
  const shown = (data || []).filter(p => !group || p.group === group)

  const save = async (p: P) => {
    setBusy(p.key)
    try { await apiFetch(`/admin/social/prompts/${p.key}`, { method: 'PUT', body: JSON.stringify({ value: vals[p.key] }) }); ok('Prompt enregistré, actif immédiatement'); reload() }
    catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const reset = async (p: P) => {
    if (!window.confirm('Revenir au texte d\'origine ?')) return
    try { await apiFetch(`/admin/social/prompts/${p.key}`, { method: 'DELETE' }); ok('Texte d\'origine restauré'); reload() } catch (e) { err(errMsg(e)) }
  }

  return (
    <div>
      <PageHead title="Prompts et consignes" sub="Modifiez les instructions données à l'IA. Les changements s'appliquent immédiatement et survivent aux redémarrages." />
      <Pills items={[{ id: '', label: 'Tous' }, ...groups.map(g => ({ id: g, label: g }))]} value={group} onChange={setGroup} />
      {shown.map(p => (
        <div className="sm-card" key={p.key}>
          <div className="sm-card-h"><h3>{p.label}</h3>{p.modifie && <Badge tone="violet">Personnalisé</Badge>}</div>
          <div className="sm-card-b">
            {p.help && <p className="sm-hint sm-mb">{p.help}</p>}
            <textarea className="sm-textarea" style={{ minHeight: 180, fontFamily: 'ui-monospace,Consolas,monospace', fontSize: 12.5 }} value={vals[p.key] ?? ''} onChange={e => setVals({ ...vals, [p.key]: e.target.value })} />
            <div className="sm-row sm-mt">
              <button className="sm-btn pri" disabled={busy === p.key || vals[p.key] === p.value} onClick={() => save(p)}>{busy === p.key ? <Spinner /> : 'Enregistrer'}</button>
              {p.modifie && <button className="sm-btn" onClick={() => reset(p)}>Restaurer l'original</button>}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}