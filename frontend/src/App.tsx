import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { Login } from './pages/Login'
import { Layout } from './components/Layout'
import { Social, SocialOAuthReturn } from './pages/social/Social'
import Portfolio from './pages/Portfolio'
function Protected({ children }: { children: React.ReactNode }) {
  const { token } = useAuth()
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function AppRoutes() {
  const { token } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/" element={<Protected><Layout /></Protected>}>
        <Route index element={<Navigate to="/social-agent" replace />} />
        <Route path="social-agent/*" element={<Social />} />
        <Route path="admin/social" element={<SocialOAuthReturn />} />
        <Route path="*" element={<Navigate to="/social-agent" replace />} />
      </Route>
      <Route path="/portfolio" element={<Portfolio />} />
    </Routes>
  )
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  )
}