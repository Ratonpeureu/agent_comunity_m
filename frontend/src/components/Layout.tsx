import React from 'react'
import { Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export function Layout() {
  const { username, logout } = useAuth()
  return (
    <div className="app-shell">
      <header className="app-top">
        <b className="app-brand">📣 Agent Social</b>
        <span className="app-flex" />
        <a className="app-link" href="/setup" target="_blank" rel="noreferrer">⚙ Réglages</a>
        <span className="app-user">{username}</span>
        <button className="app-out" onClick={logout}>Déconnexion</button>
      </header>
      <main className="app-main"><Outlet /></main>
    </div>
  )
}