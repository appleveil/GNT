import { Share } from 'react-native';
import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import * as Print from 'expo-print';
import { dealsToCsv } from './deals';
import { dealFullText, dealTitle } from './dealText';
import type { DealRecord } from '../types';

/**
 * Writes the given deals to a CSV file in the cache directory and opens the
 * native share sheet — the "manual reconciliation" export requested once
 * the rest of the Owner app exists and this local log needs to be entered
 * into it by hand. Not a sync mechanism: this never talks to the backend,
 * it just hands the Owner a clean file to share (AirDrop, email, WhatsApp,
 * a Files app save, ...) however they choose.
 */
export async function exportDealsAsCsv(deals: DealRecord[]): Promise<void> {
  const csv = dealsToCsv(deals);
  const file = new File(Paths.cache, `lpc-deals-export-${Date.now()}.csv`);
  file.create({ overwrite: true });
  file.write(csv);

  const canShare = await Sharing.isAvailableAsync();
  if (!canShare) {
    throw new Error('Sharing is not available on this device.');
  }
  await Sharing.shareAsync(file.uri, {
    mimeType: 'text/csv',
    dialogTitle: 'Export Deals history',
    UTI: 'public.comma-separated-values-text',
  });
}

/**
 * Shares one Deal as plain text — the direct route to WhatsApp (or any
 * other messaging app): the OS share sheet lists whichever apps can handle
 * plain text, WhatsApp included, with no intermediate file. Uses React
 * Native's own Share API rather than expo-sharing, since there's no file
 * to point at.
 */
export async function shareDealAsText(record: DealRecord): Promise<void> {
  await Share.share({ message: dealFullText(record) });
}

/**
 * Shares one Deal as a one-page PDF — for when a file is preferred over a
 * plain-text bubble (WhatsApp still accepts it as a document attachment).
 * Built from a small inline HTML template via expo-print, matching the
 * app's own type/spacing rather than expo-print's plain default styling.
 */
export async function shareDealAsPdf(record: DealRecord): Promise<void> {
  const html = dealToHtml(record);
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (!canShare) {
    throw new Error('Sharing is not available on this device.');
  }
  await Sharing.shareAsync(uri, { mimeType: 'application/pdf', dialogTitle: dealTitle(record) });
}

function dealToHtml(record: DealRecord): string {
  const bodyLines = dealFullText(record)
    .split('\n')
    .slice(2) // drop the title/date — shown as a heading below instead
    .map((line) => `<p>${escapeHtml(line) || '&nbsp;'}</p>`)
    .join('');
  return `
    <html>
      <head><meta charset="utf-8" /></head>
      <body style="font-family: -apple-system, Roboto, sans-serif; color: #1C222B; padding: 32px;">
        <h2 style="margin-bottom: 4px;">${escapeHtml(dealTitle(record))}</h2>
        <p style="color: #5B6572; margin-top: 0;">${escapeHtml(new Date(record.createdAt).toLocaleString())}</p>
        <hr style="border: none; border-top: 1px solid #D7DEE5; margin: 16px 0;" />
        ${bodyLines}
      </body>
    </html>
  `;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
