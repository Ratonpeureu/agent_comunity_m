// src/pages/social/Accounts.tsx
import React, { useState } from 'react'
import { errMsg, fmtDate, Platform, pmeta, social } from '../../lib/social'
import { social2 } from '../../lib/social2'
import { Badge, Field, Loading, PageHead, PlatformIcon, Spinner, copyText, useLoad, useSocial } from './ui'

type Acc = Awaited<ReturnType<typeof social.accounts>>[number]

/* ───────── Carte générique ───────── */
function AccountCard({ plat, title, lead, steps, acc, onChanged, children }: {
  plat: Platform; title: string; lead: string; steps: string[]; acc?: Acc; onChanged: () => void; children: React.ReactNode
}) {
  const { ok, err } = useSocial()
  const [busy, setBusy] = useState('')
  const test = async () => {
    setBusy('t')
    try { const r = await social.testAccount(plat); r.ok ? ok(`Connexion valide : ${r.compte || title}`) : err(r.erreur || 'Échec du test'); onChanged() }
    catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const remove = async () => {
    if (!window.confirm(`Déconnecter ${title} ?`)) return
    try { await social.delAccount(plat); ok('Compte déconnecté'); onChanged() } catch (e) { err(errMsg(e)) }
  }
  const on = !!acc?.connecte
  return (
    <section className="ac-card">
      <header className="ac-head">
        <PlatformIcon p={plat} size={30} />
        <div className="sm-flex1">
          <h3>{title}</h3>
          <p className="sm-mut sm-xs">{on ? <>{acc?.nom || 'Compte connecté'}{acc?.expire_le && <> · expire le {fmtDate(acc.expire_le)}</>}</> : lead}</p>
        </div>
        {on ? <Badge tone={acc?.statut === 'actif' ? 'green' : 'red'}>{acc?.statut === 'actif' ? 'Connecté' : acc?.statut || 'Erreur'}</Badge> : <Badge>Non connecté</Badge>}
      </header>
      {acc?.erreur && <div className="sm-err sm-xs">{acc.erreur}</div>}
      <ol className="ac-steps">{steps.map(s => <li key={s}>{s}</li>)}</ol>
      <div className="ac-form">{children}</div>
      {on && (
        <footer className="ac-foot">
          <button className="sm-btn xs" disabled={!!busy} onClick={test}>{busy === 't' ? <Spinner /> : 'Tester la connexion'}</button>
          <button className="sm-btn xs danger" onClick={remove}>Déconnecter</button>
        </footer>
      )}
    </section>
  )
}

/* ───────── Facebook ───────── */
function FacebookForm({ done }: { done: () => void }) {
  const { ok, err, info } = useSocial()
  const [mode, setMode] = useState<'user' | 'page'>('user')
  const [tok, setTok] = useState(''); const [pid, setPid] = useState('')
  const [pages, setPages] = useState<{ id: string; name: string }[]>([]); const [busy, setBusy] = useState(false)
  const submit = async (pageId?: string) => {
    setBusy(true)
    try {
      const body = mode === 'user' ? { user_token: tok.trim(), page_id: (pageId || pid).trim() } : { page_token: tok.trim(), page_id: pid.trim() }
      const r = await social2.facebook(body)
      if (!r.ok) { setPages(r.pages || []); info(r.message || 'Choisissez une Page'); return }
      setPages([]); setTok(''); ok(`Facebook connecté : ${r.nom}`); if (r.avertissement) info(r.avertissement); done()
    } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <>
      <div className="ac-tabs">
        <button className={`sm-pill${mode === 'user' ? ' on' : ''}`} onClick={() => setMode('user')}>Jeton utilisateur</button>
        <button className={`sm-pill${mode === 'page' ? ' on' : ''}`} onClick={() => setMode('page')}>Jeton de Page</button>
      </div>
      <Field label={mode === 'user' ? 'Jeton d\'accès utilisateur' : 'Jeton d\'accès de la Page'}>
        <textarea className="sm-textarea" style={{ minHeight: 70 }} value={tok} onChange={e => setTok(e.target.value)} placeholder="EAAB..." />
      </Field>
      <Field label={mode === 'page' ? 'ID de la Page (obligatoire)' : 'ID de la Page (optionnel)'}>
        <input className="sm-input" value={pid} onChange={e => setPid(e.target.value)} placeholder="1234567890" />
      </Field>
      {!!pages.length && <div className="sm-chips sm-mb">{pages.map(p => <button key={p.id} className="sm-btn xs" onClick={() => submit(p.id)}>{p.name} ({p.id})</button>)}</div>}
      <button className="sm-btn pri" disabled={busy || !tok.trim() || (mode === 'page' && !pid.trim())} onClick={() => submit()}>{busy ? <Spinner /> : 'Enregistrer'}</button>
    </>
  )
}

/* ───────── Instagram ───────── */
function InstagramForm({ done }: { done: () => void }) {
  const { ok, err } = useSocial()
  const [tok, setTok] = useState(''); const [busy, setBusy] = useState('')
  const save = async () => {
    setBusy('s')
    try { const r = await social2.instagram(tok.trim()); ok(`Instagram connecté : ${r.nom}`); setTok(''); done() } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const fromFb = async () => {
    setBusy('f')
    try { const r = await social2.instagramFromFacebook(); ok(`Instagram connecté via la Page : ${r.nom}`); done() } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  return (
    <>
      <Field label="Jeton Instagram (Instagram Login)"><textarea className="sm-textarea" style={{ minHeight: 70 }} value={tok} onChange={e => setTok(e.target.value)} placeholder="IGAA..." /></Field>
      <div className="sm-row">
        <button className="sm-btn pri" disabled={!!busy || !tok.trim()} onClick={save}>{busy === 's' ? <Spinner /> : 'Enregistrer'}</button>
        <button className="sm-btn" disabled={!!busy} onClick={fromFb}>{busy === 'f' ? <Spinner /> : 'Utiliser la Page Facebook déjà connectée'}</button>
      </div>
    </>
  )
}

/* ───────── LinkedIn ───────── */
function LinkedInForm({ done }: { done: () => void }) {
  const { ok, err } = useSocial()
  const [tok, setTok] = useState(''); const [org, setOrg] = useState(''); const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try { const r = await social2.linkedin(tok.trim(), org.trim()); ok(`LinkedIn connecté : ${r.nom}`); setTok(''); done() } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <>
      <Field label="Jeton d'accès"><textarea className="sm-textarea" style={{ minHeight: 70 }} value={tok} onChange={e => setTok(e.target.value)} /></Field>
      <Field label="ID de la Page entreprise (optionnel)" hint="Vide = publication depuis le profil personnel.">
        <input className="sm-input" value={org} onChange={e => setOrg(e.target.value)} placeholder="12345678" />
      </Field>
      <button className="sm-btn pri" disabled={busy || !tok.trim()} onClick={save}>{busy ? <Spinner /> : 'Enregistrer'}</button>
    </>
  )
}

/* ───────── X ───────── */
function XForm({ done }: { done: () => void }) {
  const { ok, err } = useSocial()
  const [tok, setTok] = useState(''); const [rt, setRt] = useState(''); const [user, setUser] = useState(''); const [busy, setBusy] = useState(false)
  const save = async () => {
    setBusy(true)
    try {
      const u = user.trim().replace(/^@/, '')
      await social.setAccount('x', { access_token: tok.trim(), refresh_token: rt.trim() || null, username: u, exp_ts: 0 }, u ? `@${u}` : 'X')
      ok('X connecté'); setTok(''); setRt(''); done()
    } catch (e) { err(errMsg(e)) } finally { setBusy(false) }
  }
  return (
    <>
      <Field label="Jeton d'accès (OAuth 2.0 utilisateur)"><textarea className="sm-textarea" style={{ minHeight: 70 }} value={tok} onChange={e => setTok(e.target.value)} /></Field>
      <div className="sm-grid g2">
        <Field label="Nom d'utilisateur"><input className="sm-input" value={user} onChange={e => setUser(e.target.value)} placeholder="@mamarque" /></Field>
        <Field label="Jeton de rafraîchissement (optionnel)"><input className="sm-input" value={rt} onChange={e => setRt(e.target.value)} /></Field>
      </div>
      <button className="sm-btn pri" disabled={busy || !tok.trim()} onClick={save}>{busy ? <Spinner /> : 'Enregistrer'}</button>
    </>
  )
}

/* ───────── TikTok ───────── */
function TikTokForm({ done, qpostReady, qpostSeen }: { done: () => void; qpostReady: boolean; qpostSeen: string }) {
  const { ok, err } = useSocial()
  const [tok, setTok] = useState(''); const [priv, setPriv] = useState('SELF_ONLY'); const [busy, setBusy] = useState('')
  const sync = async () => {
    setBusy('q')
    try {
      const r = await social.connect.qpostSync('tiktok')
      r.synchronises.length ? ok(`Synchronisé depuis QPost : ${r.synchronises.join(', ')}`) : err(`Pas encore connecté dans QPost : ${r.absents.join(', ')}`)
      done()
    } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const save = async () => {
    setBusy('s')
    try { await social.setAccount('tiktok', { access_token: tok.trim(), privacy_level: priv, post_mode: 'DIRECT_POST' }, 'TikTok'); ok('TikTok connecté'); setTok(''); done() }
    catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  return (
    <>
      <div className="sm-row sm-mb">
        <a className="sm-btn xs" href="https://qpost.dev" target="_blank" rel="noreferrer">Ouvrir QPost</a>
        <button className="sm-btn pri xs" disabled={!qpostReady || !!busy} onClick={sync}>{busy === 'q' ? <Spinner /> : 'Synchroniser depuis QPost'}</button>
        {!qpostReady && <span className="sm-xs sm-mut">Ajoutez QPOST_API_KEY dans les réglages.</span>}
      </div>
      {qpostSeen && <p className="sm-xs sm-mut sm-mb">Comptes vus dans QPost : {qpostSeen}</p>}
      <details className="ac-adv"><summary>Jeton TikTok direct (avancé)</summary>
        <Field label="Jeton d'accès"><input className="sm-input" value={tok} onChange={e => setTok(e.target.value)} /></Field>
        <Field label="Visibilité"><select className="sm-select" value={priv} onChange={e => setPriv(e.target.value)}><option value="SELF_ONLY">Privé (app non auditée)</option><option value="PUBLIC_TO_EVERYONE">Public</option></select></Field>
        <button className="sm-btn" disabled={!!busy || !tok.trim()} onClick={save}>{busy === 's' ? <Spinner /> : 'Enregistrer le jeton'}</button>
      </details>
    </>
  )
}

/* ───────── Page ───────── */
export function Accounts() {
  const { tick, err, info } = useSocial()
  const { data, loading, reload } = useLoad(async () => ({
    acc: await social.accounts(), st: await social.connect.status(),
    qp: await social.connect.qpostAccounts().catch(() => null),
  }), [tick])
  if (loading && !data) return <Loading />
  const acc = (p: string) => data!.acc.find(a => a.plateforme === p)
  const conf = data!.st.configure
  const oauth = async (p: Platform) => { try { window.location.href = (await social.oauthUrl(p)).url } catch (e) { err(errMsg(e)) } }
  const oauthList: { p: Platform; key: string }[] = [{ p: 'facebook', key: 'facebook' }, { p: 'instagram', key: 'instagram' }, { p: 'linkedin', key: 'linkedin' }, { p: 'x', key: 'x' }]

  return (
    <div>
      <PageHead title="Comptes connectés" sub="Méthode recommandée : collez un jeton d'accès. Aucune application OAuth à configurer. Les jetons sont chiffrés côté serveur." />
      <div className="ac-grid">
        <AccountCard plat="facebook" title="Facebook" lead="Pages uniquement." acc={acc('facebook')} onChanged={reload}
          steps={['Ouvrez developers.facebook.com/tools/explorer et choisissez votre application.', 'Générez un jeton avec pages_show_list, pages_manage_posts et pages_read_engagement.', 'Collez-le ci-dessous. Le serveur le convertit en jeton de Page longue durée.']}>
          <FacebookForm done={reload} />
        </AccountCard>
        <AccountCard plat="instagram" title="Instagram" lead="Compte Professionnel ou Créateur." acc={acc('instagram')} onChanged={reload}
          steps={['Passez le compte en Professionnel (Paramètres > Type de compte).', 'Dans votre application Meta, section Instagram, générez un jeton d\'accès.', 'Ou, si la Page Facebook est déjà connectée, utilisez le bouton dédié.']}>
          <InstagramForm done={reload} />
        </AccountCard>
        <AccountCard plat="linkedin" title="LinkedIn" lead="Profil ou Page." acc={acc('linkedin')} onChanged={reload}
          steps={['Dans linkedin.com/developers, générez un jeton avec openid, profile et w_member_social.', 'Pour publier en tant que Page, ajoutez w_organization_social et saisissez l\'ID de la Page.']}>
          <LinkedInForm done={reload} />
        </AccountCard>
        <AccountCard plat="x" title="X" lead="Compte développeur avec crédits." acc={acc('x')} onChanged={reload}
          steps={['Dans developer.x.com, générez un jeton OAuth 2.0 utilisateur (tweet.write, users.read, media.write).', 'Les publications sans lien coûtent beaucoup moins cher : l\'agent évite les liens sur X.']}>
          <XForm done={reload} />
        </AccountCard>
        <AccountCard plat="tiktok" title="TikTok" lead="Via QPost (recommandé)." acc={acc('tiktok')} onChanged={reload}
          steps={['Créez un compte sur qpost.dev et connectez votre TikTok.', 'Créez une clé API et renseignez QPOST_API_KEY dans les réglages.', 'Cliquez sur « Synchroniser depuis QPost ».']}>
          <TikTokForm done={reload} qpostReady={!!conf.qpost} qpostSeen={(data!.qp || []).map(q => `${q.platform} (${q.name})`).join(', ')} />
        </AccountCard>
      </div>

      <details className="sm-card sm-mt"><summary className="sm-card-h" style={{ cursor: 'pointer' }}><h3>Connexion OAuth (avancé)</h3><span className="sm-xs sm-mut">Nécessite les clés d'application dans les réglages</span></summary>
        <div className="sm-card-b">
          <div className="sm-chips sm-mb">
            {oauthList.map(o => <button key={o.p} className="sm-btn xs" disabled={!conf[o.key]} onClick={() => oauth(o.p)}>{pmeta(o.p).label}{conf[o.key] ? '' : ' (clés manquantes)'}</button>)}
          </div>
          <p className="sm-label">URL de redirection à déclarer dans chaque console développeur</p>
          {Object.entries(data!.st.redirects).map(([p, u]) => (
            <div className="sm-item" key={p}><b style={{ width: 90 }}>{p}</b><code className="sm-flex1" style={{ wordBreak: 'break-all' }}>{u}</code>
              <button className="sm-btn xs" onClick={async () => { await copyText(u); info('Copié') }}>Copier</button></div>
          ))}
        </div>
      </details>
    </div>
  )
}