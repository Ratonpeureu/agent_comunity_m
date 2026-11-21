import { apiFetch } from './api'

const P = '/admin/social'
const post = (path: string, body?: unknown) =>
  apiFetch(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export interface SystemInfo {
  ffmpeg: boolean; edge_tts: boolean; llm: boolean; public_base_url: string; public_https: boolean
  unsplash: boolean; qpost: boolean; serper: boolean; meta_app: boolean
}

export const social2 = {
  /** Montage visuel : renvoie soit le post (rendu immédiat), soit { job_id } (vidéo). */
  visual: (postId: string, body: Record<string, unknown>): Promise<any> => post(`${P}/visual/${postId}`, body),
  system: (): Promise<SystemInfo> => apiFetch(`${P}/system`),
  facebook: (b: { user_token?: string; page_token?: string; page_id?: string }): Promise<{ ok: boolean; nom?: string; avertissement?: string | null; message?: string; pages?: { id: string; name: string }[] }> =>
    post(`${P}/manual/facebook`, b),
  instagram: (access_token: string): Promise<{ ok: boolean; nom: string }> => post(`${P}/manual/instagram`, { access_token }),
  instagramFromFacebook: (): Promise<{ ok: boolean; nom: string }> => post(`${P}/manual/instagram-from-facebook`, {}),
  linkedin: (access_token: string, org_id = ''): Promise<{ ok: boolean; nom: string; urn: string }> =>
    post(`${P}/manual/linkedin`, { access_token, org_id }),
}