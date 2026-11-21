// src/pages/social/Accounts.tsx
import React, { useState } from 'react'
import { errMsg, fmtDate, Platform, pmeta, social } from '../../lib/social'
import { Badge, Loading, PageHead, PlatformDot, Spinner, copyText, useLoad, useSocial } from './ui'

interface Guide { key: string; plat: Platform; title: string; lead: string; need: string[]; env: string; redirect?: string; note?: string }

const GUIDES: Guide[] = [
  { key: 'linkedin', plat: 'linkedin', title: 'LinkedIn', lead: 'Profil personnel accepté.', need: ['Aucune Page nécessaire'], env: 'LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET', redirect: 'linkedin' },
  { key: 'x', plat: 'x', title: 'X (Twitter)', lead: 'Compte personnel accepté.', need: ['Compte développeur X avec crédits', 'Posts sans lien : ~0,015 $ · avec lien : ~0,20 $'], env: 'X_CLIENT_ID (+ X_CLIENT_SECRET)', redirect: 'x', note: "X n'a plus de palier gratuit : l'agent évite les liens dans les posts X." },
  { key: 'instagram', plat: 'instagram', title: 'Instagram', lead: 'Compte Professionnel ou Créateur, sans Page Facebook.', need: ['Instagram → Paramètres → Type de compte → Passer à un compte professionnel (gratuit)', 'En mode développement : ajoute-toi comme « Instagram Tester » dans l\'app Meta'], env: 'INSTAGRAM_APP_ID / INSTAGRAM_APP_SECRET', redirect: 'instagram' },
  { key: 'facebook', plat: 'facebook', title: 'Facebook', lead: 'Pages uniquement (Meta interdit la publication sur un profil personnel).', need: ['Une Page, même vide : facebook.com/pages/create', 'Coche ta Page dans la fenêtre d\'autorisation Meta'], env: 'META_APP_ID / META_APP_SECRET', redirect: 'facebook' },
]

export function Accounts() {
  const { tick, ok, err, info } = useSocial()
  const [busy, setBusy] = useState('')
  const [tools, setTools] = useState<any>(null)
  const { data, loading, reload } = useLoad(async () => ({
    acc: await social.accounts(), st: await social.connect.status(),
    qp: await social.connect.qpostAccounts().catch(() => null),
  }), [tick])

  if (loading && !data) return <Loading />
  const acc = (p: string) => data!.acc.find(a => a.plateforme === p)
  const conf = data!.st.configure

  const connect = async (p: Platform) => {
    setBusy('c' + p)
    try { window.location.href = (await social.oauthUrl(p)).url } catch (e) { err(errMsg(e)); setBusy('') }
  }
  const test = async (p: Platform) => {
    setBusy('t' + p)
    try { const r = await social.testAccount(p); r.ok ? ok(`Connexion OK : ${r.compte || p}`) : err(r.erreur || 'Échec du test'); reload() } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }
  const remove = async (p: Platform) => { if (!window.confirm(`Déconnecter ${pmeta(p).label} ?`)) return; try { await social.delAccount(p); ok('Compte déconnecté'); reload() } catch (e) { err(errMsg(e)) } }
  const sync = async (platforms: string) => {
    setBusy('q' + platforms)
    try {
      const r = await social.connect.qpostSync(platforms)
      r.synchronises.length ? ok(`Synchronisé depuis QPost : ${r.synchronises.join(', ')}`) : err(`Pas encore connecté dans QPost : ${r.absents.join(', ')}`)
      reload()
    } catch (e) { err(errMsg(e)) } finally { setBusy('') }
  }

  const tiktok = acc('tiktok')
  return (
    <div>
      <PageHead title="Comptes connectés" sub="Chaque réseau a ses règles : lis la carte avant de connecter. Les identifiants sont chiffrés côté serveur." />
      <div className="sm-auto" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(330px,1fr))' }}>
        {GUIDES.map(g => {
          const a = acc(g.plat)
          const ready = conf[g.key === 'facebook' ? 'facebook' : g.key]
          return (
            <div className="sm-card" key={g.key} style={{ marginBottom: 0 }}><div className="sm-card-b">
              <div className="sm-row sm-mb"><PlatformDot p={g.plat} /><h3 className="sm-flex1">{g.title}</h3>
                {a?.connecte ? <Badge tone={a.statut === 'actif' ? 'green' : 'red'}>{a.statut === 'actif' ? 'Connecté' : a.statut}</Badge> : <Badge>Non connecté</Badge>}</div>
              <p className="sm-bold sm-mb">{g.lead}</p>
              <ul className="sm-xs sm-mut" style={{ paddingLeft: 18, margin: '0 0 10px' }}>{g.need.map(n => <li key={n}>{n}</li>)}</ul>
              {g.note && <div className="sm-note sm-xs">{g.note}</div>}
              {!ready && <div className="sm-err sm-xs">Clés manquantes dans le .env : {g.env}</div>}
              {a?.connecte && <p className="sm-mb"><b>{a.nom || '—'}</b>{a.expire_le && <span className="sm-xs sm-mut"> · renouvelé automatiquement (expire le {fmtDate(a.expire_le)})</span>}</p>}
              {a?.erreur && <div className="sm-err sm-xs">{a.erreur}</div>}
              <div className="sm-row">
                <button className="sm-btn pri xs" disabled={!ready || !!busy} onClick={() => connect(g.plat)}>{busy === 'c' + g.plat ? <Spinner /> : a?.connecte ? 'Reconnecter' : 'Connecter'}</button>
                {a?.connecte && <button className="sm-btn xs" disabled={!!busy} onClick={() => test(g.plat)}>{busy === 't' + g.plat ? <Spinner /> : 'Tester'}</button>}
                {a?.connecte && <button className="sm-btn xs danger" onClick={() => remove(g.plat)}>Déconnecter</button>}
                {g.plat === 'instagram' && conf.qpost && <button className="sm-btn xs" disabled={!!busy} onClick={() => sync('instagram')}>Plutôt via QPost</button>}
              </div>
            </div></div>
          )
        })}

        <div className="sm-card" style={{ marginBottom: 0 }}><div className="sm-card-b">
          <div className="sm-row sm-mb"><PlatformDot p="tiktok" /><h3 className="sm-flex1">TikTok (via QPost)</h3>
            {tiktok?.connecte ? <Badge tone="green">Connecté</Badge> : <Badge>Non connecté</Badge>}</div>
          <p className="sm-bold sm-mb">Compte personnel accepté. QPost gère l'autorisation TikTok.</p>
          <ol className="sm-xs sm-mut" style={{ paddingLeft: 18, margin: '0 0 10px' }}>
            <li>Crée un compte sur qpost.dev et connecte ton TikTok</li>
            <li>Génère une clé (API Keys) → <code>QPOST_API_KEY</code> dans le .env</li>
            <li>Clique sur « Synchroniser depuis QPost »</li>
          </ol>
          {!conf.qpost && <div className="sm-err sm-xs">Clé manquante dans le .env : QPOST_API_KEY</div>}
          {data!.qp && <p className="sm-xs sm-mut sm-mb">Comptes vus dans QPost : {data!.qp.map(q => `${q.platform} (${q.name})`).join(', ') || 'aucun'}</p>}
          <div className="sm-row">
            <a className="sm-btn xs" href="https://qpost.dev" target="_blank" rel="noreferrer">Ouvrir QPost ↗</a>
            <button className="sm-btn pri xs" disabled={!conf.qpost || !!busy} onClick={() => sync('tiktok')}>{busy === 'qtiktok' ? <Spinner /> : 'Synchroniser depuis QPost'}</button>
            {tiktok?.connecte && <button className="sm-btn xs" disabled={!!busy} onClick={() => test('tiktok')}>Tester</button>}
            {tiktok?.connecte && <button className="sm-btn xs danger" onClick={() => remove('tiktok')}>Déconnecter</button>}
            {conf.qpost && <button className="sm-btn xs ghost" onClick={async () => { try { setTools(await social.connect.qpostTools()) } catch (e) { err(errMsg(e)) } }}>Voir le schéma API</button>}
          </div>
          {tools && <pre className="sm-xs" style={{ maxHeight: 240, overflow: 'auto', background: '#f5f6fa', padding: 10, borderRadius: 8, marginTop: 10 }}>{JSON.stringify(tools.find((t: any) => t.name === 'create_post')?.inputSchema ?? tools, null, 1)}</pre>}
        </div></div>
      </div>

      <div className="sm-card sm-mt"><div className="sm-card-h"><h3>URL de redirection à déclarer dans chaque console développeur</h3></div><div className="sm-card-b">
        {Object.entries(data!.st.redirects).map(([p, u]) => (
          <div className="sm-item" key={p}><b style={{ width: 90 }}>{p === 'facebook' ? 'Meta (FB)' : p === 'instagram' ? 'Instagram' : pmeta(p).label}</b>
            <code className="sm-flex1" style={{ wordBreak: 'break-all' }}>{u}</code>
            <button className="sm-btn xs" onClick={async () => { await copyText(u); info('Copié') }}>Copier</button></div>
        ))}
      </div></div>
    </div>
  )
}