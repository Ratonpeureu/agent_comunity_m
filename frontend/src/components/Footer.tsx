import React, { useEffect, useState } from 'react'

export const DONATION = {
  phone: '+221784788015',
  display: '+221 78 478 80 15',
  waveLink: '',
}

const SPOTIFY_SRC = 'https://open.spotify.com/embed/playlist/7kT2EnaROEpfXiy2tmFMJQ?utm_source=generator&si=bf4fa99a00e54720'


const MESSAGES = [
  'Cet outil est développé avec passion, pour toi.',
  'Un café = une nouvelle fonctionnalité en route.',
  'Chaque soutien aide à garder l\'outil vivant et gratuit.',
  'Merci d\'utiliser Agent Social. Ça fait vraiment plaisir.',
]

function useDakarClock() {
  const fmt = () => new Intl.DateTimeFormat('fr-FR', { timeZone: 'Africa/Dakar', hour: '2-digit', minute: '2-digit' }).format(new Date())
  const [t, setT] = useState(fmt)
  useEffect(() => { const i = setInterval(() => setT(fmt()), 20000); return () => clearInterval(i) }, [])
  return t
}

export function CoffeeCup({ size = 28 }: { size?: number }) {
  return (
    <svg className="ft-cup" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <path className="ft-steam s1" d="M11 9c-1.5-1.6 1.5-3 0-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path className="ft-steam s2" d="M16 9c-1.5-1.6 1.5-3 0-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path className="ft-steam s3" d="M21 9c-1.5-1.6 1.5-3 0-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M6 12h18v6a8 8 0 0 1-8 8h-2a8 8 0 0 1-8-8v-6z" fill="currentColor" />
      <path d="M24 14h2.5a3.5 3.5 0 0 1 0 7H23.4" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

export function Footer({ onDonate }: { onDonate: () => void }) {
  const [i, setI] = useState(0)
  const clock = useDakarClock()
  useEffect(() => { const t = setInterval(() => setI(n => (n + 1) % MESSAGES.length), 4000); return () => clearInterval(t) }, [])

  return (
    <footer className="ft" style={{ padding: '16px 0', minHeight: 'auto' }}>
      <div className="ft-glow" aria-hidden="true" />
      <div className="ft-in" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', maxWidth: '1200px', margin: '0 auto', padding: '0 24px', gap: '24px' }}>
        
        {/* Section Gauche compactée */}
        <div className="ft-brand" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="ft-logo"><span>S</span></div>
            <h3 style={{ margin: 0, fontSize: '1.1rem', lineHeight: 1 }}>Agent Social</h3>
          </div>
          <p key={i} className="ft-msg" style={{ margin: '4px 0', fontSize: '0.85rem', opacity: 0.8 }}>{MESSAGES[i]}</p>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
            <button type="button" className="ft-donate" onClick={onDonate} style={{ padding: '6px 14px', display: 'flex', alignItems: 'center', gap: '8px', height: '36px' }}>
              <CoffeeCup size={20} />
              <span>Offrir un café</span>
              <i className="ft-shine" aria-hidden="true" />
            </button>
            <div className="ft-pay" style={{ display: 'flex', gap: '6px' }}>
              <span className="wave">Wave</span><span className="om">Orange Money</span>
            </div>
          </div>
        </div>

        {/* Section Droite calée sur les 152px du lecteur */}
        <div className="ft-player" style={{ display: 'flex', flexDirection: 'column', width: '100%', maxWidth: '400px' }}>
          <div className="ft-label" style={{ marginBottom: '6px', fontSize: '0.8rem' }}>
            <span className="ft-eq" aria-hidden="true"><i /><i /><i /><i /></span>
            Ma playlist pendant que tu travailles
          </div>
          <iframe
            title="Playlist Spotify"
            data-testid="embed-iframe"
            style={{ borderRadius: 12, width: '100%', height: '152px' }}
            src={SPOTIFY_SRC}
            frameBorder="0"
            allowFullScreen
            allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture"
            loading="lazy"
          />
        </div>

      </div>
    </footer>
  )
}

/* ═════════════════════ Fenêtre de don ═════════════════════ */
type Method = 'wave' | 'om'
const AMOUNTS = [500, 1000, 2000, 5000]

export function DonateModal({ onClose }: { onClose: () => void }) {
  const [m, setM] = useState<Method>('wave')
  const [amount, setAmount] = useState<number | null>(1000)
  const [copied, setCopied] = useState(false)
  const [hearts, setHearts] = useState<{ id: number; x: number; d: number; s: number }[]>([])

  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', h); document.body.style.overflow = prev }
  }, [onClose])

  const burst = () => {
    const base = Date.now()
    const list = Array.from({ length: 14 }, (_, k) => ({ id: base + k, x: 8 + Math.random() * 84, d: Math.random() * 0.5, s: 0.8 + Math.random() * 0.9 }))
    setHearts(h => [...h, ...list])
    setTimeout(() => setHearts(h => h.filter(x => !list.some(l => l.id === x.id))), 2200)
  }

  const copy = async () => {
    try { await navigator.clipboard.writeText(DONATION.phone) }
    catch {
      const a = document.createElement('textarea'); a.value = DONATION.phone; document.body.appendChild(a); a.select()
      document.execCommand('copy'); a.remove()
    }
    setCopied(true); burst()
    setTimeout(() => setCopied(false), 2200)
  }

  const steps = m === 'wave'
    ? ['Ouvre l\'application Wave.', 'Choisis « Envoyer » puis saisis le numéro ci-dessus.', `Entre le montant${amount ? ` (${amount.toLocaleString('fr-FR')} FCFA)` : ''} et valide.`]
    : ['Ouvre l\'application Orange et Moi, ou compose #144#.', 'Choisis « Transfert d\'argent » puis saisis le numéro ci-dessus.', `Entre le montant${amount ? ` (${amount.toLocaleString('fr-FR')} FCFA)` : ''} et valide avec ton code secret.`]

  return (
    <div className="ft-back" onMouseDown={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="ft-modal" role="dialog" aria-modal="true" aria-label="Offrir un café au développeur">
        <div className="ft-hearts" aria-hidden="true">
          {hearts.map(h => <span key={h.id} style={{ left: `${h.x}%`, animationDelay: `${h.d}s`, fontSize: `${14 * h.s + 8}px` }}>♥</span>)}
        </div>
        <button className="ft-x" onClick={onClose} aria-label="Fermer">×</button>

        <div className="ft-hero">
          <div className="ft-bigcup"><CoffeeCup size={56} /></div>
          <h2>Offre un café au développeur</h2>
          <p>Si cet outil te fait gagner du temps, un petit geste m'aide à continuer de l'améliorer. Merci du fond du cœur.</p>
        </div>

        <div className="ft-amounts">
          {AMOUNTS.map(a => (
            <button key={a} type="button" className={amount === a ? 'on' : ''} onClick={() => setAmount(a)}>{a.toLocaleString('fr-FR')} <small>FCFA</small></button>
          ))}
          <button type="button" className={amount === null ? 'on' : ''} onClick={() => setAmount(null)}>Libre</button>
        </div>

        <div className="ft-tabs">
          <button type="button" className={`wave${m === 'wave' ? ' on' : ''}`} onClick={() => setM('wave')}>Wave</button>
          <button type="button" className={`om${m === 'om' ? ' on' : ''}`} onClick={() => setM('om')}>Orange Money</button>
        </div>

        <div className={`ft-number ${m}`}>
          <small>Envoyer au numéro</small>
          <b>{DONATION.display}</b>
          <button type="button" className="ft-copy" onClick={copy}>{copied ? 'Copié ✓' : 'Copier le numéro'}</button>
        </div>

        <ol className="ft-steps">{steps.map(s => <li key={s}>{s}</li>)}</ol>

        <div className="ft-actions">
          {m === 'wave' && DONATION.waveLink && <a className="ft-go wave" href={DONATION.waveLink} target="_blank" rel="noreferrer">Ouvrir Wave</a>}
          <a className="ft-go" href={`tel:${DONATION.phone}`}>Appeler le numéro</a>
        </div>
        <p className="ft-thanks">Chaque don, petit ou grand, compte. Merci ♥</p>
      </div>
    </div>
  )
}