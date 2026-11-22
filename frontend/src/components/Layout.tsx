import React, { useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { GroqLogo } from '../pages/social/ui'
import { CoffeeCup, DonateModal, Footer } from './Footer'

export function Layout() {
  const { username, logout } = useAuth()
  const [donate, setDonate] = useState(false)
  return (
    <div className="app-shell">
      <header className="app-top">
        <span className="app-logo">S</span>
        <b className="app-brand">Agent Social</b>
        <span className="app-flex" />
        <GroqLogo height={20} />
        <button type="button" className="app-coffee" onClick={() => setDonate(true)}><CoffeeCup size={16} />Soutenir</button>
        <Link className="app-link" to="/social-agent/settings?tab=config">Configuration</Link>
        <span className="app-user">{username}</span>
        <button className="app-out" onClick={logout}>Déconnexion</button>
      </header>
      <main className="app-main"><Outlet /></main>
      <Footer onDonate={() => setDonate(true)} />
      {donate && <DonateModal onClose={() => setDonate(false)} />}
    </div>
  )
}