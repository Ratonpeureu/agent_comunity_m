// src/pages/Social.tsx
import React, { useEffect } from 'react'
import { Navigate, NavLink, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import './social.css'
import { SocialProvider, useSocial } from './ui'
import { Overview } from './Overview'
import { Ideas } from './Ideas'
import { Posts } from './Posts'
import { Calendar } from './Calendar'
import { Library } from './Library'
import { Analytics } from './Analytics'
import { Brand } from './Brand'
import { Accounts } from './Accounts'
import { Replies } from './Replies'
import { Media } from './Media'

const TABS = [
  { to: '/social-agent', label: "Vue d'ensemble", end: true },
  { to: '/social-agent/ideas', label: 'Idées' },
  { to: '/social-agent/posts', label: 'Posts' },
  { to: '/social-agent/calendar', label: 'Calendrier' },
  { to: '/social-agent/library', label: 'Captures' },
  { to: '/social-agent/media', label: 'Médiathèque' },
  { to: '/social-agent/analytics', label: 'Analytics' },
  { to: '/social-agent/brand', label: 'Marque' },
  { to: '/social-agent/accounts', label: 'Comptes' },
  { to: '/social-agent/replies', label: 'Réponses' },
]

/** Affiche le résultat d'un retour OAuth (?connected=… / ?oauth_error=…) puis nettoie l'URL. */
function OAuthWatcher() {
  const [sp] = useSearchParams()
  const nav = useNavigate()
  const { ok, err } = useSocial()
  useEffect(() => {
    const c = sp.get('connected'), e = sp.get('oauth_error')
    if (c) { ok(`Compte ${c} connecté`); nav('/social-agent/accounts', { replace: true }) }
    else if (e) { err(`Connexion refusée : ${e}`); nav('/social-agent/accounts', { replace: true }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp])
  return null
}

export function Social() {
  return (
    <div className="sm">
      <SocialProvider>
        <OAuthWatcher />
        <nav className="sm-tabs">{TABS.map(t => <NavLink key={t.to} to={t.to} end={t.end} className="sm-tab">{t.label}</NavLink>)}</nav>
        <Routes>
          <Route index element={<Overview />} />
          <Route path="ideas" element={<Ideas />} />
          <Route path="posts" element={<Posts />} />
          <Route path="calendar" element={<Calendar />} />
          <Route path="library" element={<Library />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="brand" element={<Brand />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="replies" element={<Replies />} />
          <Route path="*" element={<Navigate to="/social-agent" replace />} />
          <Route path="media" element={<Media />} />
        </Routes>
      </SocialProvider>
    </div>
  )
}

/** Le backend redirige le retour OAuth vers /admin/social?… : on le renvoie vers la page Comptes. */
export function SocialOAuthReturn() {
  const [sp] = useSearchParams()
  const q = sp.toString()
  return <Navigate to={`/social-agent/accounts${q ? `?${q}` : ''}`} replace />
}