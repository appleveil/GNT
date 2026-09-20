import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { dealsToCsv } from './deals';
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
