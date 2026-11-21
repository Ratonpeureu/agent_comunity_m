// src/lib/social.ts
import { apiFetch, apiFetchForm } from './api' // ← adapte ce chemin si besoin

/* ───────────── Constantes ───────────── */
export const PLATFORMS = ['linkedin', 'facebook', 'instagram', 'x', 'tiktok'] as const

export type Platform = (typeof PLATFORMS)[number]

export const PLATFORM_META: Record<Platform, { label: string; short: string; color: string; max: number }> = {
  linkedin: { label: 'LinkedIn', short: 'in', color: '#0A66C2', max: 3000 },
  facebook: { label: 'Facebook', short: 'f', color: '#1877F2', max: 5000 },
  instagram: { label: 'Instagram', short: 'ig', color: '#D6249F', max: 2200 },
  tiktok: { label: 'TikTok', short: 'tt', color: '#111827', max: 150 },
  x: { label: 'X', short: 'x', color: '#111111', max: 280 },
}
export const pmeta = (p: string) =>
  PLATFORM_META[p as Platform] || { label: p, short: (p || '?').slice(0, 2), color: '#667085', max: 3000 }

export const STATUS_META: Record<string, { label: string; tone: string }> = {
  brouillon: { label: 'Brouillon', tone: 'gray' },
  a_valider: { label: 'À valider', tone: 'amber' },
  programme: { label: 'Programmé', tone: 'blue' },
  publication: { label: 'Publication…', tone: 'violet' },
  publie: { label: 'Publié', tone: 'green' },
  echec: { label: 'Échec', tone: 'red' },
  rejete: { label: 'Rejeté', tone: 'gray' },
}

export const TEMPLATES = [
  { id: 'capture_cadree', label: 'Capture cadrée', hint: 'Capture dans un cadre navigateur / téléphone' },
  { id: 'capture_zoom', label: 'Capture + zoom', hint: 'Zoom sur la zone clé de la capture' },
  { id: 'carrousel', label: 'Carrousel', hint: '3 à 5 captures enchaînées' },
  { id: 'photo_overlay', label: 'Photo + titre', hint: 'Photo Unsplash/Pexels avec titre' },
  { id: 'carte', label: 'Carte de marque', hint: 'Titre sur fond aux couleurs de la marque' },
  { id: 'aucun', label: 'Aucun visuel', hint: 'Texte seul (LinkedIn / Facebook)' },
  { id: 'tilt', label: 'Capture 3D', hint: 'Capture en perspective sur fond dégradé' },
  { id: 'glass', label: 'Verre dépoli', hint: 'Fond flouté + carte translucide' },
  { id: 'duo', label: 'Duo de captures', hint: 'Deux écrans superposés' },
  { id: 'checklist', label: 'Liste de points', hint: 'Titre + points clés + capture' },
  { id: 'bold', label: 'Titre géant', hint: 'Affiche typographique + zoom' },
  { id: 'quote', label: 'Citation', hint: 'Phrase forte sur fond de marque' },
  { id: 'video', label: 'Vidéo animée + musique', hint: 'TikTok / Reels : scènes animées, musique, transitions' },
]

/* ───────────── Types ───────────── */
export interface Box { x: number; y: number; w: number; h: number }
export interface Prediction {
  er_predit: number; er_bas: number; er_haut: number; confiance: number; percentile_historique: number
  qualite_llm: number | null; score_global: number; nb_posts_reference: number
  facteurs: { critere: string; valeur: string; multiplicateur: number }[]
}
export interface VisualSpec {
  template?: string; asset_ids?: string[]; titre_carte?: string; sous_titre?: string; badge?: string
  unsplash_query?: string; slides?: { asset_id: string; titre?: string; sous_titre?: string }[]
  ratio?: string | null; credits?: string[]
  points?: string[]; style?: string | null; cover?: string; musique?: string; duree?: number
}
export interface Post {
  id: string; brand_id: string; idea_id: string | null; groupe_id: string | null; variante: string | null
  plateforme: Platform; format: string; contenu: string; hashtags: string[]; media_urls: string[]
  lien: string | null; pilier: string; visuel_spec: VisualSpec | null; script_video: string | null
  statut: string; scheduled_at: string | null; published_at: string | null
  external_id: string | null; external_url: string | null; prediction: Prediction | null
  horaire_justification: string | null; erreur: string | null; nb_tentatives: number
  genere_par_ia: boolean; rejet_motif: string | null; created_at: string
}
export interface Idea {
  id: string; titre: string; angle: string; accroche: string; pilier: string; objectif: string
  format_conseille: string; plateformes: Platform[]; justification: string
  source_tendance_url: string | null; urgence: string; score_potentiel: number; statut: string; created_at: string
}
export interface Brand {
  id: string; slug: string; nom: string; site_url: string; urls_supplementaires: string[]
  identite: Record<string, any>; ton: Record<string, any>; style_guide: string
  piliers: { code: string; titre: string; description: string; poids: number }[]
  apprentissages: { date: string; type: string; texte: string }[]
  config: Record<string, any>; statut_analyse: string; erreur_analyse: string | null; derniere_analyse: string | null
}
export interface Asset {
  id: string; fichier: string; type_image?: string; module?: string; ecran?: string; titre_court?: string
  description?: string; hashtags?: string[]; mots_cles?: string[]; appareil?: string; orientation?: string
  dimensions?: { largeur: number; hauteur: number }
  qualite?: { lisibilite: number; esthetique: number; utilisable_social: boolean }
  exclu?: boolean; donnees_personnelles_visibles?: boolean; plateformes_recommandees?: string[]
  analyse_le?: string; modele?: string; notes_admin?: string; usage_30j?: number; sensible_non_masque?: boolean
}
export interface AssetFull extends Asset {
  fonctionnalites_visibles?: string[]; benefices?: string[]; problemes_resolus?: string[]; public_cible?: string[]
  angles_posts?: { pilier: string; accroche: string; legende_courte: string }[]
  legendes_montage?: { titre: string; sous_titre: string }[]
  zone_focus?: Box | null; zones_sensibles?: (Box & { nature?: string })[]
  texte_visible?: string[]; couleurs_dominantes?: string[]; original?: string
}
export interface Job {
  id: string; kind: string; statut: 'en_attente' | 'en_cours' | 'termine' | 'echec'
  resultat: any; erreur: string | null
}
export interface Slot { scheduled_at: string; score: number; justification: string }
export interface BestTime { jour: string; weekday: number; heure: number; score: number; observations: number; source: string }



export interface MediaItem {
  id: string
  kind: 'capture' | 'logo' | 'montage' | 'video' | 'stock' | 'audio'
  title: string
  description: string
  module: string | null
  tags: string[]
  private_path: string | null
  url: string | null
  poster: string | null
  created_at: string | null
  size: number | null
  post: { id: string; plateforme: Platform; statut: string; template?: string; extrait: string; erreur_montage?: string } | null
  usage_30j?: number
  sensible?: boolean
  exclu?: boolean
}
export interface AssetDiag {
  assets_dir: string; photos_dir: string; yml: number; valides: number; orphelins: number
  photos_a_analyser: number; raisons: Record<string, number>; modele: string
}

/* ───────────── Utilitaires ───────────── */
export const errMsg = (e: unknown): string => (e instanceof Error ? e.message : String(e || 'Erreur inconnue'))
export const isVideo = (u: string) => /\.(mp4|mov)(\?|$)/i.test(u || '')
export const fmtNum = (n?: number | null) => (n == null ? '—' : new Intl.NumberFormat('fr-FR').format(Math.round(n)))
export const fmtPct = (x?: number | null, d = 2) => (x == null ? '—' : `${(x * 100).toFixed(d)} %`)
export const prettify = (s?: string) => (s || '').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
export const asArr = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : v ? [String(v)] : [])

const TZ = 'Africa/Dakar'
export function parseUtc(iso?: string | null): Date | null {
  if (!iso) return null
  const s = /(Z|[+-]\d{2}:?\d{2})$/.test(iso) && iso.includes('T') ? iso : iso + 'Z'
  const d = new Date(s)
  return isNaN(+d) ? null : d
}
export function fmtDateTime(iso?: string | null): string {
  const d = parseUtc(iso)
  if (!d) return 'Non planifié'
  return new Intl.DateTimeFormat('fr-FR', { timeZone: TZ, weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(d)
}
export function fmtDate(iso?: string | null): string {
  const d = parseUtc(iso)
  return d ? new Intl.DateTimeFormat('fr-FR', { timeZone: TZ, day: '2-digit', month: 'long', year: 'numeric' }).format(d) : '—'
}
/** ISO UTC → "YYYY-MM-DDTHH:mm" en heure de Dakar (valeur d'un <input type="datetime-local">) */
export function toInput(iso?: string | null): string {
  const d = parseUtc(iso)
  if (!d) return ''
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d)
  const g = (t: string) => parts.find(p => p.type === t)?.value || '00'
  return `${g('year')}-${g('month')}-${g('day')}T${g('hour') === '24' ? '00' : g('hour')}:${g('minute')}`
}
export const dayKey = (iso?: string | null) => toInput(iso).slice(0, 10)
export const hhmm = (iso?: string | null) => toInput(iso).slice(11, 16)
export const naiveUtc = (d: Date) => d.toISOString().slice(0, 19)

const qs = (o: Record<string, unknown>) => {
  const p = new URLSearchParams()
  Object.entries(o).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== '') p.set(k, String(v)) })
  const s = p.toString()
  return s ? `?${s}` : ''
}
const P = '/admin/social'
const jpost = (path: string, body?: unknown) => apiFetch(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
const jput = (path: string, body: unknown) => apiFetch(path, { method: 'PUT', body: JSON.stringify(body) })
const jpatch = (path: string, body: unknown) => apiFetch(path, { method: 'PATCH', body: JSON.stringify(body) })
const jdel = (path: string) => apiFetch(path, { method: 'DELETE' })

/* ───────────── API ───────────── */
export const social = {
  job: (id: string): Promise<Job> => apiFetch(`${P}/jobs/${id}`),

  brand: (): Promise<Brand> => apiFetch(`${P}/brand`),
  saveBrand: (b: Record<string, unknown>): Promise<Brand> => jput(`${P}/brand`, b),
  analyzeBrand: () => jpost(`${P}/brand/analyze`),
  refreshTone: () => jpost(`${P}/brand/tone/refresh`),
  samples: (): Promise<{ id: string; plateforme: string | null; texte: string; source: string; poids: number; created_at: string }[]> => apiFetch(`${P}/brand/style-samples`),
  addSample: (texte: string, plateforme?: string) => jpost(`${P}/brand/style-samples`, { texte, plateforme: plateforme || null }),
  delSample: (id: string) => jdel(`${P}/brand/style-samples/${id}`),

  accounts: (): Promise<{ plateforme: Platform; connecte: boolean; nom: string | null; statut: string | null; expire_le: string | null; erreur: string | null }[]> => apiFetch(`${P}/accounts`),
  setAccount: (p: string, credentials: Record<string, unknown>, nom?: string) => jput(`${P}/accounts/${p}`, { credentials, nom: nom || '' }),
  testAccount: (p: string): Promise<{ ok: boolean; compte?: string; erreur?: string }> => jpost(`${P}/accounts/${p}/test`),
  delAccount: (p: string) => jdel(`${P}/accounts/${p}`),
  oauthUrl: (p: string): Promise<{ url: string }> => apiFetch(`${P}/oauth/${p}/url`),

  ideas: (statut?: string): Promise<Idea[]> => apiFetch(`${P}/ideas${qs({ statut, limit: 100 })}`),
  genIdeas: (b: { nb: number; thematique?: string; avec_tendances: boolean }) => jpost(`${P}/ideas/generate`, b),
  patchIdea: (id: string, b: { statut?: string; motif_rejet?: string }): Promise<Idea> => jpatch(`${P}/ideas/${id}`, b),
  writeIdea: (id: string, plateformes: string[], instruction: string) => jpost(`${P}/ideas/${id}/write`, { plateformes, instruction }),

  posts: (p: { statut?: string; plateforme?: string; limit?: number; offset?: number }): Promise<Post[]> => apiFetch(`${P}/posts${qs(p)}`),
  post: (id: string): Promise<Post> => apiFetch(`${P}/posts/${id}`),
  createPost: (b: Record<string, unknown>): Promise<Post> => jpost(`${P}/posts`, b),
  patchPost: (id: string, b: Record<string, unknown>): Promise<Post> => jpatch(`${P}/posts/${id}`, b),
  delPost: (id: string) => jdel(`${P}/posts/${id}`),
  uploadMedia: (id: string, file: File) => { const fd = new FormData(); fd.append('file', file); return apiFetchForm(`${P}/posts/${id}/media`, fd) },
  removeMedia: (id: string, url: string) => jpost(`${P}/posts/${id}/media/remove`, { url }),
  validate: (id: string, scheduled_at?: string): Promise<Post> => jpost(`${P}/posts/${id}/validate`, { scheduled_at: scheduled_at || null }),
  reject: (id: string, motif: string): Promise<Post> => jpost(`${P}/posts/${id}/reject`, { motif }),
  unschedule: (id: string): Promise<Post> => jpost(`${P}/posts/${id}/unschedule`),
  publishNow: (id: string) => jpost(`${P}/posts/${id}/publish-now`),
  regenerate: (id: string, motif: string) => jpost(`${P}/posts/${id}/regenerate`, { motif }),
  variants: (id: string, n = 2) => jpost(`${P}/posts/${id}/variants${qs({ n })}`),
  score: (id: string) => jpost(`${P}/posts/${id}/score`),
  replySuggestions: (b: { plateforme: string; commentaire: string; contexte_post: string }): Promise<{ type_commentaire: string; reponses: string[]; action_recommandee: string }> => jpost(`${P}/reply-suggestions`, b),
  calendar: (from: string, to: string): Promise<Post[]> => apiFetch(`${P}/calendar${qs({ date_from: from, date_to: to })}`),

  overview: (days: number): Promise<any> => apiFetch(`${P}/analytics/overview${qs({ days })}`),
  bestTimes: (platform: string, top = 8): Promise<BestTime[]> => apiFetch(`${P}/analytics/best-times${qs({ platform, top })}`),
  growth: (days: number): Promise<Record<string, any>> => apiFetch(`${P}/analytics/growth${qs({ days })}`),
  predict: (b: Record<string, unknown>): Promise<Prediction> => jpost(`${P}/analytics/predict`, b),
  slots: (platform: string, n = 3): Promise<Slot[]> => apiFetch(`${P}/analytics/slots${qs({ platform, n })}`),
  syncMetrics: () => jpost(`${P}/analytics/sync`),
  genReport: (days: number) => jpost(`${P}/analytics/reports/generate${qs({ days })}`),
  reports: (): Promise<{ id: string; periode_debut: string; periode_fin: string; analyse: any; faits: any; created_at: string }[]> => apiFetch(`${P}/analytics/reports`),
  autopilot: () => jpost(`${P}/autopilot/run`),

  assets: {
    list: (o: { include_excluded?: boolean } = {}): Promise<Asset[]> => apiFetch(`${P}/assets${qs({ include_excluded: o.include_excluded ?? true })}`),
    get: (id: string): Promise<AssetFull> => apiFetch(`${P}/assets/${id}`),
    fileUrl: (id: string) => `${P}/assets/${id}/file`,
    patch: (id: string, b: Record<string, unknown>): Promise<AssetFull> => jpatch(`${P}/assets/${id}`, b),
    del: (id: string) => jdel(`${P}/assets/${id}`),
    reanalyze: (id: string) => jpost(`${P}/assets/${id}/reanalyze`),
    analyze: (b: { move?: boolean | null; force?: boolean; max_images?: number | null } = {}) => jpost(`${P}/assets/analyze`, b),
    upload: (files: File[], analyze = true): Promise<{ enregistres: string[]; job: { job_id: string } | null }> => {
      const fd = new FormData(); files.forEach(f => fd.append('files', f)); return apiFetchForm(`${P}/assets/upload${qs({ analyze })}`, fd)
    },
    modules: (): Promise<{ resume: string; par_module: Record<string, any>; usage_30j: Record<string, number> }> => apiFetch(`${P}/assets/modules`),
    report: (): Promise<any> => apiFetch(`${P}/assets/report`),
    preview: (b: Record<string, unknown>): Promise<{ urls: string[]; spec: VisualSpec }> => jpost(`${P}/assets/preview`, b),
    rebuild: (postId: string, b: Record<string, unknown>): Promise<Post> => jpost(`${P}/assets/rebuild/${postId}`, b),
    stock: (query: string, orientation: string): Promise<{ source: string; id: string; thumb: string; author: string; page_url: string; alt: string }[]> =>
      apiFetch(`${P}/assets/stock/search${qs({ query, orientation })}`),

    media: (): Promise<{ items: MediaItem[]; counts: Record<string, number> }> => apiFetch(`${P}/assets/media`),
    diagnostic: (): Promise<AssetDiag> => apiFetch(`${P}/assets/diagnostic`),
  },

  connect: {
    status: (): Promise<{ configure: Record<string, boolean>; redirects: Record<string, string> }> => apiFetch(`${P}/connect/status`),
    qpostAccounts: (): Promise<{ platform: string; name: string; status: string }[]> => apiFetch(`${P}/connect/qpost/accounts`),
    qpostSync: (platforms = 'tiktok'): Promise<{ synchronises: string[]; absents: string[] }> => jpost(`${P}/connect/qpost/sync${qs({ platforms })}`),
    qpostTools: (): Promise<any> => apiFetch(`${P}/connect/qpost/tools`),
  },
}

/** Attend la fin d'un job Celery (polling). Lève si le job échoue. */

export class JobError extends Error {}
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

/** Attend la fin d'un job. S'arrête dès « termine » ou « echec ». Backoff 2 s → 10 s, 15 s si l'onglet est caché. */
export async function waitJob(id: string, timeoutMs = 10 * 60 * 1000): Promise<Job> {
  const t0 = Date.now()
  let delay = 2000
  let netFails = 0
  for (;;) {
    let j: Job | null = null
    try {
      j = await social.job(id)
      netFails = 0
    } catch (e) {
      if (/introuvable/i.test(errMsg(e))) throw new JobError('Job introuvable')
      if (++netFails >= 5) throw e
    }
    if (j) {
      if (j.statut === 'termine') return j
      if (j.statut === 'echec') throw new JobError(j.erreur || 'Traitement en échec')
    }
    if (Date.now() - t0 > timeoutMs) throw new JobError('Délai dépassé')
    await sleep(document.hidden ? 15000 : delay)
    delay = Math.min(Math.round(delay * 1.5), 10000)
  }
}



