import React, { useState } from 'react'
import { useAuth } from '../lib/auth'
import { apiFetch } from '../lib/api'

export function Login() {
  const { login } = useAuth()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      const d = await apiFetch('/admin/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      login(d.access_token, d.username)
    } catch (err: any) { setError(err.message) } finally { setLoading(false) }
  }

  return (
    <div className="lg-wrap">
      <form className="lg-card" onSubmit={submit}>
        <h1>Agent Social</h1>
        <p>Connexion administrateur</p>
        {error && <div className="lg-err">{error}</div>}
        <label>Identifiant<input value={username} onChange={e => setUsername(e.target.value)} required autoFocus /></label>
        <label>Mot de passe<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>
        <button disabled={loading}>{loading ? 'Connexion…' : 'Se connecter'}</button>
      </form>
    </div>
  )
}