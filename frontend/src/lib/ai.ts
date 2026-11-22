import { apiFetch } from './api'

const P = '/admin/social/ai'
const req = (method: string, path: string, body?: unknown) =>
  apiFetch(`${P}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) })

export interface RateInfo {
  limit_requests?: string | null; limit_tokens?: string | null
  remaining_requests?: string | null; remaining_tokens?: string | null
  reset_requests?: string | null; reset_tokens?: string | null; ts?: number
}
export interface AiKey {
  id: string; label: string; last4: string; statut: string; expire_le: string | null
  reset_at: string | null; erreur: string | null; source: 'pool' | 'setup'; rl: RateInfo | null
}
export interface Gauge { used: number; limit: number; pct: number }
export interface Budget { tokens_jour: number; tokens_mois: number; requetes_jour: number; cout_mois_usd: number; alerte_pct: number; bloquer: boolean }
export interface Totals { prompt: number; completion: number; tokens: number; requetes: number; erreurs: number; cout_usd?: number; modeles_sans_prix?: string[] }
export interface AiOverview {
  budget: Budget
  prix: Record<string, { in: number; out: number }>
  retention_jours: number
  modeles: { texte: string; vision: string; texte_effectif: string; vision_effectif: string }
  usage: { jour: Totals; mois: Required<Totals> }
  limites: Record<string, Gauge>
  alertes: { niveau: 'warn' | 'err'; texte: string }[]
  serie: { jour: string; tokens: number; requetes: number }[]
  par_modele: { modele: string; requetes: number; prompt: number; completion: number; tokens: number; cout_usd: number | null }[]
  par_cle: { cle: string; tokens: number; requetes: number; erreurs: number }[]
  derniers: { ts: string; kind: string; modele: string; cle: string; tokens: number; ok: boolean; status: number; ms: number; erreur: string }[]
  cles: AiKey[]
  env: AiKey[]
}
export interface ModelInfo { id: string; owned_by?: string; context_window?: number; active?: boolean }
export interface TestResult { ok: boolean; status: number; ms: number; modele: string; erreur?: string; rl: RateInfo | null }

export const ai = {
  overview: (): Promise<AiOverview> => apiFetch(`${P}/overview`),
  saveSettings: (b: { budget?: Budget; prix?: Record<string, { in: number; out: number }>; modeles?: { texte: string; vision: string }; retention_jours?: number }) => req('PUT', '/settings', b),
  addKey: (b: { label: string; key: string; expire_le: string | null }): Promise<AiKey> => req('POST', '/keys', b),
  patchKey: (id: string, b: { label?: string; expire_le?: string | null; statut?: 'actif' | 'desactive' }): Promise<AiKey> => req('PATCH', `/keys/${id}`, b),
  delKey: (id: string) => req('DELETE', `/keys/${id}`),
  testKey: (id: string): Promise<TestResult> => req('POST', `/keys/${id}/test`),
  models: (): Promise<ModelInfo[]> => apiFetch(`${P}/models`),
}