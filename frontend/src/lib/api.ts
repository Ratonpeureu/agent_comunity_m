export const BASE_URL = ''   // même origine : le front est servi par le conteneur

export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem('admin_token')
  const headers: Record<string, string> = { 'Content-Type': 'application/json', ...((options.headers as any) || {}) }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const response = await fetch(`${BASE_URL}${endpoint}`, { ...options, headers })
  if (!response.ok) {
    if (response.status === 401 && endpoint !== '/admin/login') {
      localStorage.removeItem('admin_token')
      window.location.href = '/login'
    }
    let msg = 'Une erreur est survenue'
    try { const d = await response.json(); msg = typeof d.detail === 'string' ? d.detail : msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return response.json()
}

/** FormData (multipart) : ne pas définir Content-Type. */
export async function apiFetchForm(endpoint: string, formData: FormData, method: 'POST' | 'PATCH' = 'POST') {
  const token = localStorage.getItem('admin_token')
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${BASE_URL}${endpoint}`, { method, headers, body: formData })
  if (!res.ok) {
    let msg = 'Une erreur est survenue'
    try { const d = await res.json(); msg = typeof d.detail === 'string' ? d.detail : msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json()
}

export async function apiDownload(endpoint: string, filename: string) {
  const token = localStorage.getItem('admin_token')
  const res = await fetch(`${BASE_URL}${endpoint}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new Error('Téléchargement impossible')
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}