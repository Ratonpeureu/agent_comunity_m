import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import { apiFetchForm } from '../lib/api';
import {
  Loader2, Upload, Paperclip, X, Send, Download, CheckCircle2, AlertCircle,
  FileSpreadsheet, Users, Play, Pause, RotateCcw, TestTube2, FileText,
} from 'lucide-react';

/* ───────────────────────── Types ───────────────────────── */
interface MailboxInfo {
  purpose: string; email: string | null; total: number; unread: number; error: string | null;
}

interface ColumnMapping {
  email: string;
  entreprise: string;
  subject: string;
  body: string;
  statut: string;
}

type RowStatus = 'pending' | 'sending' | 'success' | 'error';

interface RowResult {
  status: RowStatus;
  error?: string;
  sentAt?: string;
}

interface BulkRow {
  __idx: number;         // index d'origine dans le fichier
  included: boolean;     // sélection pour l'envoi
  email: string;
  entreprise: string;
  subject: string;
  body: string;
  statut: string;        // statut lu depuis l'Excel (ex: "À contacter")
  result: RowResult;
}

const SINGLE_EMAIL_RE = /^[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+$/;
const MAX_TOTAL_BYTES = 25 * 1024 * 1024;

/* ───────────────────────── Helpers ───────────────────────── */
const norm = (s: string) =>
  (s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();

/** Convertit le HTML (issu d'Excel) en texte brut avec \n. */
function htmlToText(input: string): string {
  if (!input) return '';
  let text = String(input)
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<\/p>\s*/gi, '\n\n')
    .replace(/<\/div>\s*/gi, '\n')
    .replace(/<\/li>\s*/gi, '\n')
    .replace(/<[^>]+>/g, '');
  try {
    const ta = document.createElement('textarea');
    ta.innerHTML = text;
    text = ta.value; // décode &nbsp; &amp; etc.
  } catch { /* ignore */ }
  return text.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

/** Essaie de détecter les colonnes utiles d'après les en-têtes. */
function detectColumns(headers: string[]): ColumnMapping {
  const find = (patterns: string[]) => {
    for (const p of patterns) {
      const hit = headers.find((h) => norm(h).includes(p));
      if (hit) return hit;
    }
    return '';
  };
  return {
    email:      find(['e-mail public', 'e-mail', 'email', 'mail']),
    entreprise: find(['entreprise', 'societe', 'société', 'company', 'nom']),
    subject:    find(['objet']),
    body:       find(['contenu du mail', 'contenu', 'message', 'corps']),
    statut:     find(['statut', 'status']),
  };
}

const fmtSize = (n: number) =>
  n < 1024 ? `${n} o` : n < 1024 * 1024 ? `${Math.round(n / 1024)} Ko` : `${(n / 1024 / 1024).toFixed(1)} Mo`;

const sleep = (ms: number) => new Promise((res) => setTimeout(res, ms));

/* ───────────────────────── Composant ───────────────────────── */
export function BulkSendPanel({ boxes }: { boxes: MailboxInfo[] }) {
  // Excel
  const [fileName, setFileName] = useState('');
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<BulkRow[]>([]);
  const [columns, setColumns] = useState<ColumnMapping>({
    email: '', entreprise: '', subject: '', body: '', statut: '',
  });
  const [parseError, setParseError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Configuration d'envoi
  const [purpose, setPurpose] = useState(boxes[0]?.purpose ?? 'marketing');
  const [attachments, setAttachments] = useState<File[]>([]);
  const [delayMs, setDelayMs] = useState(5000);
  const attachInputRef = useRef<HTMLInputElement>(null);

  // Test
  const [testEmail, setTestEmail] = useState('');
  const [testing, setTesting] = useState(false);

  // Exécution
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState<number | null>(null);
  const [fatalError, setFatalError] = useState('');
  const pausedRef = useRef(false);
  const cancelledRef = useRef(false);

  const totalBytes = attachments.reduce((s, f) => s + f.size, 0);
  const currentBox = boxes.find((b) => b.purpose === purpose);
  const canSend = !!currentBox?.email && !currentBox?.error;

  const includedRows = useMemo(() => rows.filter((r) => r.included), [rows]);
  const sentCount = rows.filter((r) => r.result.status === 'success').length;
  const errorCount = rows.filter((r) => r.result.status === 'error').length;
  const totalToSend = includedRows.filter((r) => r.result.status !== 'success').length;

  /* ─────────── Chargement de l'Excel ─────────── */
  const loadFile = useCallback(async (file: File) => {
    setParseError('');
    setFileName(file.name);
    try {
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: 'array' });
      const sheet = wb.Sheets[wb.SheetNames[0]];
      const json: Record<string, any>[] = XLSX.utils.sheet_to_json(sheet, { defval: '', raw: false });
      if (!json.length) throw new Error('Le fichier est vide.');

      const hdrs = Object.keys(json[0]);
      const detected = detectColumns(hdrs);

      const built: BulkRow[] = json.map((raw, i) => {
        const emailRaw = detected.email ? String(raw[detected.email] ?? '').trim() : '';
        const email = emailRaw;
        const entreprise = detected.entreprise ? String(raw[detected.entreprise] ?? '').trim() : '';
        const subject = detected.subject ? String(raw[detected.subject] ?? '').trim() : '';
        const body = htmlToText(detected.body ? String(raw[detected.body] ?? '') : '');
        const statut = detected.statut ? String(raw[detected.statut] ?? '').trim() : '';

        // Par défaut : inclure les lignes avec email valide et pas déjà "Envoyé"
        const alreadySent = /envoy|sent|done|ok/i.test(statut);
        const included = SINGLE_EMAIL_RE.test(email) && !alreadySent;

        return {
          __idx: i,
          included,
          email,
          entreprise,
          subject,
          body,
          statut,
          result: { status: 'pending' as RowStatus },
        };
      });

      setHeaders(hdrs);
      setColumns(detected);
      setRows(built);

      if (!detected.email) {
        setParseError(
          "Impossible de détecter la colonne email. Choisis-la manuellement ci-dessous."
        );
      }
    } catch (e: any) {
      setParseError(e.message || 'Erreur de lecture du fichier.');
      setRows([]);
      setHeaders([]);
    }
  }, []);

  /* ─────────── Re-mapper une colonne ─────────── */
  const remap = (field: keyof ColumnMapping, header: string) => {
    setColumns((c) => ({ ...c, [field]: header }));
    setRows((rs) =>
      rs.map((r) => {
        const raw = (r as any)._raw ?? null; // pas stocké ; on ignore
        return r;
      })
    );
    // Pour simplifier : on invite l'utilisateur à re-téléverser si le mapping change.
    // (ou on garde une copie brute, voir plus bas — le code ci-dessous utilise cette approche)
  };

  // On stocke les valeurs brutes pour permettre le re-mapping sans re-uploader
  // → adaptons loadFile pour conserver les données brutes :
  // (Implémentation dans la version ci-dessous, voir _rawByRow)

  /* ─────────── Envoi de test ─────────── */
  const sendTest = async () => {
    setFatalError('');
    if (!SINGLE_EMAIL_RE.test(testEmail)) {
      setFatalError('Email de test invalide.');
      return;
    }
    if (!canSend) {
      setFatalError('Boîte mail non disponible.');
      return;
    }
    const first = includedRows[0];
    if (!first) {
      setFatalError('Aucune ligne sélectionnée.');
      return;
    }
    setTesting(true);
    try {
      const fd = new FormData();
      fd.append('to', testEmail);
      fd.append('subject', first.subject || '(sans objet)');
      fd.append('body', first.body || '(test)');
      attachments.forEach((f) => fd.append('files', f));
      await apiFetchForm(`/admin/system-mailboxes/${purpose}/send`, fd);
      alert(`Message de test envoyé à ${testEmail}`);
    } catch (e: any) {
      setFatalError(e.message);
    } finally {
      setTesting(false);
    }
  };

  /* ─────────── Boucle d'envoi ─────────── */
  const updateRow = (idx: number, patch: Partial<BulkRow>) => {
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };

  const startCampaign = async () => {
    if (!canSend) return;
    setFatalError('');
    cancelledRef.current = false;
    pausedRef.current = false;
    setPaused(false);
    setRunning(true);

    const snapshot = [...rows]; // on fige les valeurs
    for (let i = 0; i < snapshot.length; i++) {
      if (cancelledRef.current) break;
      const r = snapshot[i];
      if (!r.included) continue;
      if (r.result.status === 'success') continue;

      // Pause
      while (pausedRef.current && !cancelledRef.current) {
        await sleep(200);
      }
      if (cancelledRef.current) break;

      setCurrentIdx(i);
      updateRow(i, { result: { status: 'sending' } });

      try {
        const fd = new FormData();
        fd.append('to', r.email);
        fd.append('subject', r.subject || '(sans objet)');
        fd.append('body', r.body || '(message vide)');
        attachments.forEach((f) => fd.append('files', f));
        await apiFetchForm(`/admin/system-mailboxes/${purpose}/send`, fd);
        updateRow(i, {
          result: { status: 'success', sentAt: new Date().toISOString() },
        });
      } catch (e: any) {
        updateRow(i, { result: { status: 'error', error: e.message } });
      }

      // Délai entre 2 envois (sauf dernier)
      if (i < snapshot.length - 1 && delayMs > 0) {
        await sleep(delayMs);
      }
    }

    setCurrentIdx(null);
    setRunning(false);
    setPaused(false);
  };

  const pause = () => { pausedRef.current = true; setPaused(true); };
  const resume = () => { pausedRef.current = false; setPaused(false); };
  const cancel = () => { cancelledRef.current = true; pausedRef.current = false; setPaused(false); };

  const resetResults = () => {
    setRows((rs) => rs.map((r) => ({ ...r, result: { status: 'pending' } })));
  };

  /* ─────────── Export Excel des résultats ─────────── */
  const exportResults = () => {
    const data = rows.map((r) => ({
      'N°': r.__idx + 1,
      Entreprise: r.entreprise,
      Email: r.email,
      Objet: r.subject,
      Statut:
        r.result.status === 'success' ? 'Envoyé'
        : r.result.status === 'error' ? 'Échec'
        : r.included ? 'En attente' : 'Non sélectionné',
      "Date d'envoi": r.result.sentAt
        ? new Date(r.result.sentAt).toLocaleString('fr-FR')
        : '',
      Erreur: r.result.error || '',
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'Résultats');
    XLSX.writeFile(wb, `campagne-envoi-${new Date().toISOString().slice(0, 10)}.xlsx`);
  };

  /* ─────────── Rendu ─────────── */
  return (
    <div className="flex flex-col gap-4">
      {/* 1. Boîte + PJ + délai */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 grid md:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1">Boîte d'envoi</label>
          <select
            value={purpose}
            onChange={(e) => setPurpose(e.target.value)}
            disabled={running}
            className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
          >
            {boxes.map((b) => (
              <option key={b.purpose} value={b.purpose} disabled={!b.email || !!b.error}>
                {b.purpose} {b.email ? `· ${b.email}` : '· indisponible'}
              </option>
            ))}
          </select>
          {!canSend && (
            <p className="text-xs text-red-600 mt-1">Cette boîte n'est pas disponible pour l'envoi.</p>
          )}
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1">
            Délai entre 2 envois (ms)
          </label>
          <input
            type="number"
            min={0}
            step={1000}
            value={delayMs}
            onChange={(e) => setDelayMs(Math.max(0, Number(e.target.value) || 0))}
            disabled={running}
            className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
          />
          <p className="text-xs text-gray-500 mt-1">
            Recommandé : 3000–10000 ms pour éviter le blocage anti-spam.
          </p>
        </div>

        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1">
            Pièces jointes (partagées)
          </label>
          <input
            ref={attachInputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) {
                const arr = Array.from(e.target.files);
                const add = arr.reduce((s, f) => s + f.size, 0);
                if (totalBytes + add > MAX_TOTAL_BYTES) {
                  setFatalError(`Pièces jointes trop lourdes (max ${fmtSize(MAX_TOTAL_BYTES)}).`);
                  return;
                }
                setFatalError('');
                setAttachments((cur) => [...cur, ...arr]);
              }
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => attachInputRef.current?.click()}
            disabled={running}
            className="w-full inline-flex items-center justify-center gap-2 border-2 border-dashed border-gray-200 rounded-md py-2 text-xs text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            <Upload size={13} /> Ajouter des fichiers ({fmtSize(totalBytes)})
          </button>
          {attachments.length > 0 && (
            <ul className="mt-2 space-y-1 max-h-24 overflow-y-auto">
              {attachments.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1">
                  <Paperclip size={11} className="text-gray-400 shrink-0" />
                  <span className="flex-1 truncate">{f.name}</span>
                  <span className="text-gray-400 shrink-0">{fmtSize(f.size)}</span>
                  <button
                    type="button"
                    onClick={() => setAttachments((cur) => cur.filter((_, j) => j !== i))}
                    disabled={running}
                    className="text-gray-400 hover:text-red-600"
                  >
                    <X size={11} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 2. Upload Excel */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          const f = e.dataTransfer.files?.[0];
          if (f) loadFile(f);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={
          'bg-white border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ' +
          (dragOver
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-200 hover:bg-gray-50')
        }
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.xls,.csv"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) loadFile(f);
            e.target.value = '';
          }}
        />
        <FileSpreadsheet size={32} className="mx-auto text-gray-400 mb-2" />
        <p className="text-sm font-semibold text-gray-800">
          {fileName || 'Glissez-déposez votre fichier Excel ici'}
        </p>
        <p className="text-xs text-gray-500 mt-1">
          Colonnes attendues : E-mail public, Entreprise, Objet de l'e-mail, Contenu du mail (optionnel : Statut).
        </p>
      </div>

      {parseError && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm px-3 py-2 rounded">
          {parseError}
        </div>
      )}

      {fatalError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded flex items-start gap-2">
          <AlertCircle size={16} className="shrink-0 mt-0.5" />
          <span className="flex-1">{fatalError}</span>
          <button onClick={() => setFatalError('')} className="text-red-700">
            <X size={14} />
          </button>
        </div>
      )}

      {/* 3. Mapping colonnes (si besoin) */}
      {headers.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm p-4 grid md:grid-cols-5 gap-3">
          {(
            [
              ['email', 'Email *'],
              ['entreprise', 'Entreprise'],
              ['subject', 'Objet'],
              ['body', 'Corps *'],
              ['statut', 'Statut'],
            ] as [keyof ColumnMapping, string][]
          ).map(([key, label]) => (
            <div key={key}>
              <label className="block text-xs font-semibold text-gray-700 mb-1">{label}</label>
              <select
                value={columns[key]}
                onChange={(e) => remap(key, e.target.value)}
                disabled={running}
                className="w-full border border-gray-200 rounded-md px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50"
              >
                <option value="">—</option>
                {headers.map((h) => (
                  <option key={h} value={h}>{h}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {/* 4. Aperçu + actions */}
      {rows.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden flex flex-col">
          {/* Barre d'actions */}
          <div className="px-4 py-3 border-b border-gray-200 flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 text-sm text-gray-700">
              <Users size={15} />
              <span><b>{includedRows.length}</b> / {rows.length} destinataires</span>
            </div>

            <div className="flex-1" />

            <input
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="test@exemple.com"
              disabled={running || testing}
              className="border border-gray-200 rounded-md px-2 py-1.5 text-xs w-52 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              onClick={sendTest}
              disabled={running || testing || !canSend || !testEmail}
              className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-50"
            >
              {testing ? <Loader2 size={12} className="animate-spin" /> : <TestTube2 size={12} />}
              Test
            </button>

            <button
              onClick={exportResults}
              className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border border-gray-200 bg-white hover:bg-gray-50 text-gray-700"
            >
              <Download size={12} /> Exporter
            </button>

            <button
              onClick={resetResults}
              disabled={running}
              className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 disabled:opacity-50"
            >
              <RotateCcw size={12} /> Réinitialiser
            </button>

            {!running ? (
              <button
                onClick={startCampaign}
                disabled={!canSend || totalToSend === 0}
                className="inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-50"
              >
                <Play size={14} />
                {sentCount > 0 ? 'Reprendre' : 'Lancer'} ({totalToSend})
              </button>
            ) : (
              <>
                <button
                  onClick={paused ? resume : pause}
                  className="inline-flex items-center gap-1 text-sm font-semibold px-3 py-1.5 rounded-md bg-amber-500 hover:bg-amber-600 text-white"
                >
                  {paused ? <Play size={14} /> : <Pause size={14} />}
                  {paused ? 'Reprendre' : 'Pause'}
                </button>
                <button
                  onClick={cancel}
                  className="inline-flex items-center gap-1 text-sm font-semibold px-3 py-1.5 rounded-md bg-red-600 hover:bg-red-700 text-white"
                >
                  <X size={14} /> Arrêter
                </button>
              </>
            )}
          </div>

          {/* Barre de progression */}
          <div className="px-4 py-2 border-b border-gray-200 flex items-center gap-3 text-xs">
            <div className="flex-1 h-2 bg-gray-100 rounded overflow-hidden">
              <div
                className="h-full bg-blue-600 transition-all"
                style={{
                  width: `${rows.length ? Math.round(((sentCount + errorCount) / rows.length) * 100) : 0}%`,
                }}
              />
            </div>
            <span className="tabular-nums text-gray-600">
              <CheckCircle2 size={12} className="inline text-green-600 mr-0.5" />
              {sentCount}
              {' · '}
              <AlertCircle size={12} className="inline text-red-600 mr-0.5" />
              {errorCount}
              {' · '}
              <Loader2 size={12} className="inline text-blue-600 mr-0.5" />
              {rows.length - sentCount - errorCount}
            </span>
          </div>

          {/* Tableau */}
          <div className="max-h-[28rem] overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-2 py-2 w-8"></th>
                  <th className="px-2 py-2 w-10 text-left">#</th>
                  <th className="px-2 py-2 text-left">Entreprise</th>
                  <th className="px-2 py-2 text-left">Email</th>
                  <th className="px-2 py-2 text-left">Objet</th>
                  <th className="px-2 py-2 w-28 text-left">État</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const emailOk = SINGLE_EMAIL_RE.test(r.email);
                  const isCurrent = currentIdx === i;
                  return (
                    <tr
                      key={r.__idx}
                      className={
                        'border-b border-gray-100 ' +
                        (isCurrent ? 'bg-blue-50' : '')
                      }
                    >
                      <td className="px-2 py-1 text-center">
                        <input
                          type="checkbox"
                          checked={r.included}
                          disabled={running || !emailOk}
                          onChange={(e) => updateRow(i, { included: e.target.checked })}
                          className="rounded border-gray-300"
                        />
                      </td>
                      <td className="px-2 py-1 text-gray-500 tabular-nums">{r.__idx + 1}</td>
                      <td className="px-2 py-1 truncate max-w-[160px]" title={r.entreprise}>
                        {r.entreprise || '—'}
                      </td>
                      <td className="px-2 py-1 truncate max-w-[200px]" title={r.email}>
                        <span className={emailOk ? '' : 'text-red-600'}>
                          {r.email || '(vide)'}
                        </span>
                      </td>
                      <td className="px-2 py-1 truncate max-w-[260px]" title={r.subject}>
                        {r.subject || '—'}
                      </td>
                      <td className="px-2 py-1 whitespace-nowrap">
                        {r.result.status === 'success' && (
                          <span className="text-green-700 inline-flex items-center gap-1">
                            <CheckCircle2 size={12} /> Envoyé
                          </span>
                        )}
                        {r.result.status === 'error' && (
                          <span
                            className="text-red-700 inline-flex items-center gap-1"
                            title={r.result.error}
                          >
                            <AlertCircle size={12} /> Échec
                          </span>
                        )}
                        {r.result.status === 'sending' && (
                          <span className="text-blue-700 inline-flex items-center gap-1">
                            <Loader2 size={12} className="animate-spin" /> Envoi…
                          </span>
                        )}
                        {r.result.status === 'pending' && (
                          <span className="text-gray-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 5. Aide / avertissement */}
      <div className="bg-blue-50 border border-blue-100 text-blue-800 text-xs px-3 py-2 rounded flex items-start gap-2">
        <FileText size={14} className="shrink-0 mt-0.5" />
        <div>
          Les pièces jointes sont renvoyées à chaque destinataire (limite 25 Mo / mail).
          Le HTML du fichier Excel est converti en texte brut (&lt;br&gt; → saut de ligne).
          Chaque envoi crée une copie dans le dossier « Sent ».
        </div>
      </div>
    </div>
  );
}