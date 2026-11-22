import { apiFetch } from './api'

const P = '/admin/social/config'
const req = (method: string, path: string, body?: unknown) =>
  apiFetch(`${P}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) })

export interface CfgField {
  key: string; label: string; kind: 'text' | 'url' | 'secret' | 'number' | 'select'; hint: string
  restart: boolean; placeholder: string; options: string[]; group: string | null; warn: string
  secret: boolean; set: boolean; value: string; last4: string
}
export interface CfgSection { id: string; title: string; desc: string; fields: CfgField[] }
export interface CfgResponse { sections: CfgSection[]; admin: { username: string } }
export interface UrlCheck { ok: boolean; https: boolean; ms: number; erreur: string }

export const cfg = {
  get: (): Promise<CfgResponse> => apiFetch(P),
  put: (b: { values: Record<string, string>; clear: string[] }): Promise<{ ok: boolean; changed: string[]; restart_required: string[] }> => req('PUT', '', b),
  checkUrl: (url: string): Promise<UrlCheck> => req('POST', '/check-url', { url }),
  restart: () => req('POST', '/restart'),
  admin: (b: { current_password: string; username: string; new_password: string }): Promise<{ ok: boolean; username: string }> => req('PUT', '/admin', b),
}

/** Attend que le serveur ait redémarré (l'identifiant de démarrage /health change). */
export async function waitRestart(before: string | undefined, timeoutMs = 90000): Promise<void> {
  const t0 = Date.now()
  await new Promise(r => setTimeout(r, 2500))
  while (Date.now() - t0 < timeoutMs) {
    try {
      const j = await (await fetch('/health', { cache: 'no-store' })).json()
      if (j.configured && j.boot && j.boot !== before) return
    } catch { /* serveur en cours de redémarrage */ }
    await new Promise(r => setTimeout(r, 1500))
  }
  throw new Error('Le redémarrage prend trop de temps : vérifie « docker compose ps » sur le serveur.')
}