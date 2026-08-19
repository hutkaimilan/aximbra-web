/**
 * Hivas-osszefoglalo kikuldese.
 *
 * Resend-et hasznalunk SMTP helyett: nincs kapcsolat-kezeles, nincs port
 * 25/587 blokkolas a hosztolonal, egyetlen HTTPS POST az egesz.
 *
 * Fail-soft: ha az email nem megy ki, azt naplozzuk, de nem dobunk hibat.
 * Egy sikertelen ertesites nem indokolja, hogy a hivas feldolgozasa
 * elszalljon - az atirat a logban akkor is megmarad.
 */

import { env } from './env.js';
import type { Summary, Turn } from './llm.js';

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function badgeColor(rating: string): string {
  switch (rating.toUpperCase().charAt(0)) {
    case 'A':
      return '#0F766E';
    case 'B':
      return '#2563EB';
    case 'C':
      return '#B45309';
    default:
      return '#6B7280';
  }
}

function buildHtml(
  summary: Summary | null,
  history: Turn[],
  meta: { from: string; durationSec: number; callSid: string },
): string {
  const rows: Array<[string, string]> = summary
    ? [
        ['Név', summary.nev],
        ['Cég', summary.ceg],
        ['Iparág', summary.iparag],
        ['Feladat', summary.feladat],
        ['Mennyiség', summary.mennyiseg],
        ['Elérhetőség', summary.elerhetoseg],
        ['Javasolt kategória', summary.javasolt_kategoria],
        ['Indoklás', summary.indoklas],
        ['Következő lépés', summary.kovetkezo_lepes],
      ]
    : [['Összefoglaló', 'Nem készült el — lásd az átiratot lentebb.']];

  const table = rows
    .map(
      ([k, v]) =>
        `<tr>` +
        `<td style="padding:8px 14px;border-bottom:1px solid #E5E7EB;color:#6B7280;font-size:13px;white-space:nowrap;vertical-align:top">${escapeHtml(k)}</td>` +
        `<td style="padding:8px 14px;border-bottom:1px solid #E5E7EB;color:#111827;font-size:14px">${escapeHtml(v)}</td>` +
        `</tr>`,
    )
    .join('');

  const transcript = history
    .map((t) => {
      const who = t.role === 'user' ? 'HÍVÓ' : 'AGENT';
      const color = t.role === 'user' ? '#111827' : '#6B7280';
      return `<p style="margin:0 0 8px;font-size:13px;line-height:1.55;color:${color}"><strong>${who}:</strong> ${escapeHtml(t.content)}</p>`;
    })
    .join('');

  const rating = summary?.minosites ?? '—';
  const mins = Math.floor(meta.durationSec / 60);
  const secs = meta.durationSec % 60;

  return `<!DOCTYPE html>
<html lang="hu"><body style="margin:0;background:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
  <div style="background:#fff;border-radius:12px;overflow:hidden;border:1px solid #E5E7EB">
    <div style="padding:20px 22px;background:#0B0E1C;color:#fff">
      <div style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#8792BC">AXIMBRA · beérkezett hívás</div>
      <div style="font-size:20px;font-weight:600;margin-top:6px">${escapeHtml(meta.from)}</div>
      <div style="font-size:12px;color:#8792BC;margin-top:4px">${mins} perc ${secs} másodperc · ${escapeHtml(meta.callSid)}</div>
    </div>

    <div style="padding:16px 22px;border-bottom:1px solid #E5E7EB">
      <span style="display:inline-block;padding:5px 12px;border-radius:20px;background:${badgeColor(rating)};color:#fff;font-size:12px;font-weight:600;letter-spacing:.05em">
        MINŐSÍTÉS: ${escapeHtml(rating)}
      </span>
    </div>

    <table style="width:100%;border-collapse:collapse">${table}</table>

    <div style="padding:18px 22px;background:#F9FAFB">
      <div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#6B7280;margin-bottom:12px">Teljes átirat</div>
      ${transcript || '<p style="font-size:13px;color:#9CA3AF">Nem hangzott el semmi.</p>'}
    </div>
  </div>
  <p style="text-align:center;font-size:11px;color:#9CA3AF;margin-top:16px">
    Automatikus értesítés az AXIMBRA telefonos agenttől.
  </p>
</div>
</body></html>`;
}

export async function sendSummary(
  summary: Summary | null,
  history: Turn[],
  meta: { from: string; durationSec: number; callSid: string },
): Promise<void> {
  const cfg = env();

  const header =
    `[hívás] ${meta.from} · ${meta.durationSec}s · ` +
    `${summary ? `${summary.nev} / ${summary.ceg} / ${summary.minosites}` : 'nincs összefoglaló'}`;

  // A log mindig megy, fuggetlenul attol, hogy az email sikerul-e. Ez a
  // vegso mentohalo: ha minden mas elromlik, a Railway logbol visszakereshto.
  console.log(header);
  console.log('[átirat]', JSON.stringify(history));

  if (!cfg.notifyEmail || !cfg.resendApiKey) return;

  try {
    const res = await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${cfg.resendApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: cfg.resendFrom,
        to: [cfg.notifyEmail],
        subject: summary
          ? `Hívás: ${summary.ceg} — ${summary.minosites} minősítés`
          : `Hívás: ${meta.from}`,
        html: buildHtml(summary, history, meta),
      }),
      signal: AbortSignal.timeout(15_000),
    });

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      console.error(`[email] sikertelen (${res.status}): ${body.slice(0, 300)}`);
    }
  } catch (err) {
    console.error('[email] kivetel:', err);
  }
}
