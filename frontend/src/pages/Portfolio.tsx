import React, { useEffect, useRef, useState } from 'react'
import nagoraLogo from '../assets/Nagora_logo.jpg'
import rhLogo from '../assets/logo_rh_manager.png'

const EMAIL = 'gorasow026@gmail.com'
const LINKEDIN = 'https://www.linkedin.com/in/mak-gora-b7a6a2176'
const RH_URL = 'https://rhmanager.site'

/* Apparition au défilement */
function useInView<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') { setSeen(true); return }
    const io = new IntersectionObserver(es => {
      if (es.some(e => e.isIntersecting)) { setSeen(true); io.disconnect() }
    }, { threshold: 0.15 })
    io.observe(el)
    const t = setTimeout(() => setSeen(true), 5000)
    return () => { io.disconnect(); clearTimeout(t) }
  }, [])
  return [ref, seen] as const
}

function Reveal({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  const [ref, seen] = useInView<HTMLDivElement>()
  return <div ref={ref} className={`pf-rv ${seen ? 'in' : ''} ${className}`}>{children}</div>
}

/* Compteur animé */
function Count({ to, plus = false }: { to: number; plus?: boolean }) {
  const [ref, seen] = useInView<HTMLElement>()
  const [v, setV] = useState(0)
  useEffect(() => {
    if (!seen) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setV(to); return }
    let raf = 0
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min((t - t0) / 1500, 1)
      setV(Math.round(to * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [seen, to])
  return <b ref={ref}>{v}{plus && v === to ? '+' : ''}</b>
}

export default function Portfolio() {
  const [copied, setCopied] = useState(false)
  const [barRef, barSeen] = useInView<HTMLDivElement>()

  const copy = async () => {
    try { await navigator.clipboard.writeText(EMAIL) }
    catch {
      const a = document.createElement('textarea'); a.value = EMAIL
      document.body.appendChild(a); a.select(); document.execCommand('copy'); a.remove()
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="pf">
      <style>{CSS}</style>

      <header className="pf-top">
        <div className="pf-wrap pf-top-in">
          <a href="/" className="pf-brand"><i />Gora Mak Sow</a>
          <nav>
            <a href="#logiciel">RH Manager</a>
            <a href="#histoire">Pourquoi</a>
            <a href="#nagora">Nagora SARL</a>
            <a href="#contact">Contact</a>
          </nav>
        </div>
      </header>

      {/* ───────── Hero ───────── */}
      <section className="pf-hero">
        <div className="pf-orb o1" aria-hidden="true" />
        <div className="pf-orb o2" aria-hidden="true" />
        <div className="pf-wrap pf-hero-in">
          <div className="pf-logos">
            <img src={nagoraLogo} alt="Logo Nagora SARL" />
            <img src={rhLogo} alt="Logo RH Manager" />
          </div>
          <h1 aria-label="Gora Mak Sow">
            <span>Gora</span> <span className="g">Mak</span> <span>Sow</span>
          </h1>
          <p className="pf-lead">Je crée des logiciels. Le plus important : <b>RH Manager</b>.</p>
          <div className="pf-cta">
            <a className="pf-btn p" href={RH_URL} target="_blank" rel="noreferrer">Découvrir RH Manager <span>→</span></a>
            <a className="pf-btn" href={LINKEDIN} target="_blank" rel="noreferrer">Mon profil LinkedIn <span>↗</span></a>
          </div>
        </div>
      </section>

      {/* ───────── RH Manager ───────── */}
      <section id="logiciel" className="pf-sec">
        <div className="pf-wrap pf-flag">
          <Reveal>
            <div className="pf-eye">Le logiciel phare</div>
            <h2>J'ai beaucoup de logiciels. Un seul est en tête.</h2>
            <p>RH Manager est celui que je mets en avant. Il est né d'un besoin réel, d'abord le mien, puis celui de mon entreprise.</p>
          </Reveal>
          <Reveal>
            <a className="pf-card" href={RH_URL} target="_blank" rel="noreferrer">
              <span className="pf-tag">Logiciel phare</span>
              <div className="pf-tile"><img src={rhLogo} alt="RH Manager" /></div>
              <h3>RH Manager</h3>
              <span className="pf-url">rhmanager.site ↗</span>
            </a>
          </Reveal>
        </div>
      </section>

      {/* ───────── Histoire ───────── */}
      <section id="histoire" className="pf-sec alt">
        <div className="pf-wrap">
          <Reveal>
            <div className="pf-eye">Pourquoi ce logiciel existe</div>
            <h2>Tout est parti de LinkedIn.</h2>
            <p>Avant RH Manager, j'avais déjà une version personnelle, utilisée uniquement pour LinkedIn. Elle m'a permis de publier plus de 87 posts et de faire passer mon compte de 150 à 1450 relations.</p>
          </Reveal>

          <Reveal className="pf-nums">
            <div className="pf-num"><Count to={87} plus /><small>posts LinkedIn publiés</small></div>
            <div className="pf-num"><Count to={150} /><small>relations au départ</small></div>
            <div className="pf-num"><Count to={1450} /><small>relations après les posts</small></div>
          </Reveal>

          <div ref={barRef} className={`pf-bars ${barSeen ? 'in' : ''}`} role="img" aria-label="Relations LinkedIn : de 150 à 1450">
            <div className="pf-bar"><span>Avant</span><div className="pf-track"><div className="pf-fill a">150</div></div></div>
            <div className="pf-bar"><span>Après</span><div className="pf-track"><div className="pf-fill b">1450</div></div></div>
          </div>

          <ol className="pf-steps">
            <li><Reveal><h3>Une version personnelle</h3><p>Un outil pour moi seul, dédié à LinkedIn.</p></Reveal></li>
            <li><Reveal><h3>87+ posts, 1450 relations</h3><p>Publier plus a fait passer mon compte de 150 à 1450 relations.</p></Reveal></li>
            <li><Reveal><h3>Nagora SARL grandit</h3><p>Il a fallu gérer l'image de la société et sa présence sur les réseaux sociaux.</p></Reveal></li>
            <li><Reveal><h3>RH Manager</h3><p>Le logiciel qui répond à ce besoin et que je mets aujourd'hui en avant.</p></Reveal></li>
          </ol>
        </div>
      </section>

      {/* ───────── Nagora ───────── */}
      <section id="nagora" className="pf-sec">
        <div className="pf-wrap pf-flag">
          <Reveal>
            <div className="pf-eye">Ma société</div>
            <h2>Nagora SARL</h2>
            <p>En grandissant, Nagora SARL a demandé de gérer son image et sa présence sur les réseaux sociaux. C'est ce besoin qui a donné RH Manager.</p>
          </Reveal>
          <Reveal>
            <div className="pf-card static">
              <div className="pf-tile"><img src={nagoraLogo} alt="Nagora SARL" /></div>
              <h3>Nagora SARL</h3>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ───────── Contact ───────── */}
      <section id="contact" className="pf-sec alt">
        <div className="pf-wrap">
          <Reveal>
            <div className="pf-eye">Contact</div>
            <h2>Parlons-en.</h2>
            <div className="pf-mail">
              <span className="pf-addr">{EMAIL}</span>
              <button type="button" className="pf-cp" onClick={copy}>{copied ? 'Copié ✓' : 'Copier'}</button>
            </div>
            <div className="pf-cta" style={{ marginTop: 24 }}>
              <a className="pf-btn p" href={`mailto:${EMAIL}`}>Écrire un email <span>→</span></a>
              <a className="pf-btn" href={LINKEDIN} target="_blank" rel="noreferrer">LinkedIn <span>↗</span></a>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="pf-foot">
        <div className="pf-wrap pf-foot-in">
          <span>Gora Mak Sow · Nagora SARL</span>
          <a href={RH_URL} target="_blank" rel="noreferrer">rhmanager.site</a>
        </div>
      </footer>
    </div>
  )
}

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Inter:wght@400;500;600&display=swap');
.pf{
  --bg:#08100E; --bg2:#0D1915; --fg:#E8F2ED; --muted:#93AAA1; --line:#1C2D27;
  --accent:#34D8A4; --accent-ink:#04140E; --warm:#F2B33D; --card:#101E19;
  --d:'Bricolage Grotesque','Segoe UI',system-ui,sans-serif;
  background:var(--bg); color:var(--fg); min-height:100vh; overflow-x:hidden;
  font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif; font-size:17px; line-height:1.65;
}
.pf *{box-sizing:border-box}
.pf a{color:inherit}
.pf a:focus-visible,.pf button:focus-visible{outline:3px solid var(--accent);outline-offset:3px;border-radius:8px}
.pf-wrap{max-width:1040px;margin:0 auto;padding:0 20px}
.pf h1,.pf h2,.pf h3{font-family:var(--d);line-height:1.05;margin:0;letter-spacing:-.02em;text-wrap:balance}
.pf p{margin:0 0 1em;max-width:60ch;color:var(--muted)}
.pf-eye{font-size:.78rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--accent)}
.pf h2{font-size:clamp(2rem,5vw,3.4rem);font-weight:800;margin:10px 0 20px;max-width:18ch}

.pf-top{position:sticky;top:0;z-index:20;background:rgba(8,16,14,.8);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
.pf-top-in{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:12px;padding-bottom:12px}
.pf-brand{display:flex;align-items:center;gap:10px;text-decoration:none;font-family:var(--d);font-weight:800}
.pf-brand i{width:12px;height:12px;border-radius:50%;background:var(--accent);animation:pfPulse 2.4s infinite}
@keyframes pfPulse{0%{box-shadow:0 0 0 0 rgba(52,216,164,.6)}70%{box-shadow:0 0 0 12px rgba(52,216,164,0)}100%{box-shadow:0 0 0 0 rgba(52,216,164,0)}}
.pf-top nav{display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end}
.pf-top nav a{text-decoration:none;font-size:.9rem;color:var(--muted);padding:6px 10px;border-radius:999px}
.pf-top nav a:hover{color:var(--fg);background:var(--bg2)}

.pf-hero{position:relative;overflow:hidden;padding:clamp(48px,9vw,110px) 0 clamp(48px,8vw,96px);border-bottom:1px solid var(--line)}
.pf-orb{position:absolute;border-radius:50%;filter:blur(70px);opacity:.5;pointer-events:none}
.pf-orb.o1{width:420px;height:420px;background:#0f8f6a;top:-140px;right:-100px;animation:pfFloat 9s ease-in-out infinite}
.pf-orb.o2{width:320px;height:320px;background:#8a5a00;bottom:-140px;left:-80px;opacity:.28;animation:pfFloat 11s ease-in-out infinite reverse}
@keyframes pfFloat{50%{transform:translate(-30px,34px) scale(1.12)}}
.pf-hero-in{position:relative;display:grid;gap:22px}
.pf-logos{display:flex;gap:14px;align-items:center;animation:pfUp .8s both}
.pf-logos img{height:56px;width:auto;max-width:140px;object-fit:contain;background:#fff;border-radius:14px;padding:8px}
.pf-hero h1{font-size:clamp(3rem,11vw,7.4rem);font-weight:800}
.pf-hero h1 span{display:inline-block;animation:pfUp .9s cubic-bezier(.2,.8,.2,1) both}
.pf-hero h1 span:nth-child(2){animation-delay:.12s}
.pf-hero h1 span:nth-child(3){animation-delay:.24s}
.pf-hero h1 .g{color:var(--accent)}
@keyframes pfUp{from{opacity:0;transform:translateY(36px)}to{opacity:1;transform:none}}
.pf-lead{font-size:clamp(1.15rem,2.4vw,1.5rem);max-width:30ch;animation:pfUp .9s .4s both}
.pf-lead b{color:var(--fg);font-weight:600}
.pf-cta{display:flex;gap:12px;flex-wrap:wrap;animation:pfUp .9s .55s both}
.pf-btn{display:inline-flex;align-items:center;gap:8px;padding:13px 22px;border-radius:999px;text-decoration:none;font-weight:600;border:1.5px solid var(--fg);transition:transform .2s,box-shadow .2s}
.pf-btn:hover{transform:translateY(-3px)}
.pf-btn.p{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.pf-btn.p:hover{box-shadow:0 10px 30px -8px rgba(52,216,164,.7)}
.pf-btn span{transition:transform .2s}.pf-btn:hover span{transform:translateX(4px)}

.pf-sec{padding:clamp(56px,9vw,100px) 0}
.pf-sec.alt{background:var(--bg2);border-block:1px solid var(--line)}
.pf-flag{display:grid;grid-template-columns:1.1fr .9fr;gap:clamp(24px,5vw,60px);align-items:center}
.pf-flag>*{min-width:0}

.pf-card{display:block;position:relative;overflow:hidden;text-decoration:none;border:1px solid var(--line);background:var(--card);border-radius:22px;padding:clamp(22px,4vw,36px);transition:transform .35s,box-shadow .35s}
.pf-card:not(.static):hover{transform:translateY(-6px);box-shadow:0 30px 60px -30px rgba(52,216,164,.5)}
.pf-card::after{content:"";position:absolute;width:240px;height:240px;right:-90px;top:-90px;border-radius:50%;background:radial-gradient(circle,rgba(52,216,164,.3),transparent 70%);animation:pfFloat 7s ease-in-out infinite}
.pf-card h3{position:relative;font-size:clamp(2rem,4.6vw,2.8rem);font-weight:800;margin-top:18px}
.pf-tag{position:relative;display:inline-block;font-size:.74rem;font-weight:600;letter-spacing:.1em;text-transform:uppercase;padding:5px 12px;border-radius:999px;background:var(--accent);color:var(--accent-ink);margin-bottom:16px}
.pf-tile{position:relative;display:inline-flex;background:#fff;border-radius:18px;padding:14px}
.pf-tile img{display:block;height:84px;width:auto;max-width:100%;object-fit:contain}
.pf-url{position:relative;display:inline-block;margin-top:10px;font-family:var(--d);font-weight:800;color:var(--accent)}

.pf-nums{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px;margin-top:32px}
.pf-num{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:22px}
.pf-num b{display:block;font-family:var(--d);font-size:clamp(2.6rem,6vw,3.8rem);line-height:1;font-weight:800;color:var(--accent);font-variant-numeric:tabular-nums}
.pf-num small{display:block;margin-top:8px;color:var(--muted);font-size:.95rem}
.pf-bars{display:grid;gap:14px;margin-top:16px;border:1px solid var(--line);background:var(--card);border-radius:18px;padding:22px}
.pf-bar{display:grid;grid-template-columns:70px 1fr;gap:14px;align-items:center}
.pf-bar>span{font-size:.9rem;color:var(--muted)}
.pf-track{height:34px;border-radius:999px;background:var(--bg2);overflow:hidden}
.pf-fill{height:100%;width:0;border-radius:999px;display:flex;align-items:center;justify-content:flex-end;padding-right:12px;font-weight:700;font-size:.9rem;color:var(--accent-ink);transition:width 1.6s cubic-bezier(.2,.8,.2,1)}
.pf-fill.a{background:var(--warm);min-width:56px}
.pf-fill.b{background:var(--accent)}
.pf-bars.in .pf-fill.a{width:10.34%}
.pf-bars.in .pf-fill.b{width:100%}

.pf-steps{list-style:none;margin:36px 0 0;padding:0;position:relative}
.pf-steps::before{content:"";position:absolute;left:11px;top:8px;bottom:8px;width:2px;background:linear-gradient(var(--accent),var(--warm))}
.pf-steps li{position:relative;padding:0 0 30px 48px}
.pf-steps li:last-child{padding-bottom:0}
.pf-steps li::before{content:"";position:absolute;left:3px;top:6px;width:18px;height:18px;border-radius:50%;background:var(--bg2);border:3px solid var(--accent)}
.pf-steps h3{font-size:1.35rem;font-weight:800;margin-bottom:6px}
.pf-steps p{margin:0}

.pf-mail{display:flex;flex-wrap:wrap;gap:12px;align-items:center}
.pf-addr{font-family:var(--d);font-weight:800;font-size:clamp(1.3rem,4.4vw,2.3rem);word-break:break-all;user-select:all}
.pf-cp{cursor:pointer;font:inherit;font-size:.9rem;font-weight:600;padding:8px 16px;border-radius:999px;border:1.5px solid var(--fg);background:transparent;color:var(--fg)}
.pf-cp:hover{background:var(--fg);color:var(--bg)}

.pf-foot{border-top:1px solid var(--line);padding:26px 0;color:var(--muted);font-size:.9rem}
.pf-foot-in{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}

.pf-rv{opacity:0;transform:translateY(28px);transition:opacity .8s ease,transform .8s cubic-bezier(.2,.8,.2,1)}
.pf-rv.in{opacity:1;transform:none}

@media (max-width:760px){
  .pf-flag{grid-template-columns:1fr}
  .pf-bar{grid-template-columns:1fr;gap:6px}
  .pf-top nav a:not(:last-child){display:none}
}
@media (prefers-reduced-motion:reduce){
  .pf *,.pf *::after{animation:none!important;transition:none!important}
  .pf-rv{opacity:1;transform:none}
  .pf-fill.a{width:10.34%}.pf-fill.b{width:100%}
}
`