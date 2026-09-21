import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { HistoryStackParamList } from '../navigation/types';
import type { DealRecord } from '../types';
import { getAllDeals } from '../db/deals';
import { payoutLifespanLabel } from '../db/dealText';
import { Banner, SectionCard, naira } from '../components/ui';
import { PercentCircleIcon, PayoutIcon } from '../components/icons';
import { colors, radii, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<HistoryStackParamList, 'ProfitSplitDetail'>;
type Created = Extract<DealRecord, { kind: 'PROFIT_SPLIT_CREATED' }>;
type Ended = Extract<DealRecord, { kind: 'PROFIT_SPLIT_ENDED' }>;

/**
 * Read-only, deliberately — reached only from History. No inputs, no
 * buttons: to change an active arrangement, open it from the player's
 * Deals page instead (ProfitSplitScreen). See PLAN.md's mobile-app entry.
 */
export default function ProfitSplitDetailScreen({ route }: Props) {
  const { arrangementId } = route.params;
  const [created, setCreated] = useState<Created | null>(null);
  const [ended, setEnded] = useState<Ended | null>(null);

  useEffect(() => {
    getAllDeals().then((all) => {
      const c = all.find((d) => d.id === arrangementId && d.kind === 'PROFIT_SPLIT_CREATED') as Created | undefined;
      const e = all.find((d) => d.kind === 'PROFIT_SPLIT_ENDED' && (d as Ended).arrangementId === arrangementId) as
        | Ended
        | undefined;
      setCreated(c ?? null);
      setEnded(e ?? null);
    });
  }, [arrangementId]);

  if (!created) return null;

  return (
    <ScrollView style={{ flex: 1, backgroundColor: colors.bg }} contentContainerStyle={{ padding: spacing.lg }}>
      <Banner tone="info">
        This is a read-only record from History. To change an active arrangement, open it from the player's Deals
        page instead.
      </Banner>

      <View style={styles.card}>
        <View style={styles.statusRow}>
          <Text style={styles.statusLabel}>Status</Text>
          <View style={[styles.badge, ended ? styles.badgeEnded : styles.badgeActive]}>
            <Text style={styles.badgeText}>{ended ? 'ENDED' : 'ACTIVE'}</Text>
          </View>
        </View>
        <KvRow k="Set up" v={new Date(created.createdAt).toLocaleString()} />
        {ended ? <KvRow k="Ended" v={new Date(ended.createdAt).toLocaleString()} /> : null}
        {ended ? <KvRow k="Reason for ending" v={ended.reason} /> : null}
      </View>

      <SectionCard icon={<PercentCircleIcon color={colors.accentText} />} title="Stake" subtitle="How much of buy-in the house covered">
        {created.stakeOn ? (
          <>
            <KvRow k="House stake" v={`${created.stakePct}%`} />
            <KvRow k="Cap" v={`${naira(created.cap ?? 0)} / period`} />
            <KvRow k="Renews" v={created.renews ?? '—'} />
            {created.until ? <KvRow k="Until" v={created.until} /> : null}
            {created.maxTimes ? <KvRow k="Number of times" v={String(created.maxTimes)} /> : null}
            {created.maxValue ? <KvRow k="Max value" v={naira(created.maxValue)} /> : null}
          </>
        ) : (
          <Text style={styles.emptyNote}>No stake was set on this arrangement.</Text>
        )}
      </SectionCard>

      <SectionCard icon={<PayoutIcon color={colors.accentText} />} title="Payout" subtitle="Applied when chips were returned">
        {created.payoutOn ? (
          <>
            <KvRow k="Basis" v={created.payoutBasis === 'BEFORE_BUYIN' ? 'Before buy-in' : 'After buy-in'} />
            <KvRow k="Split method" v={splitMethodLabel(created)} />
            <KvRow k="Lifespan" v={payoutLifespanLabel(created)} />
          </>
        ) : (
          <Text style={styles.emptyNote}>No payout split was set on this arrangement.</Text>
        )}
      </SectionCard>
    </ScrollView>
  );
}

function splitMethodLabel(created: Created): string {
  if (created.payoutSplitMethod === 'STAKE_RATIO') return `Ratio: according to stake (${created.stakePct}%)`;
  if (created.payoutSplitMethod === 'CUSTOM_RATIO') return `Ratio: house percentage (${created.customRatioPct}%)`;
  if (created.payoutSplitMethod === 'FIXED') {
    return `Fixed amount (${naira(created.fixedAmount ?? 0)}${created.fixedOffset ? `, off-set ${naira(created.fixedOffset)}` : ''})`;
  }
  return '—';
}

function KvRow({ k, v }: { k: string; v: string }) {
  return (
    <View style={styles.kvRow}>
      <Text style={styles.kvKey}>{k}</Text>
      <Text style={styles.kvValue}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  statusRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
  statusLabel: { fontSize: 13.5, fontWeight: '600', color: colors.textPrimary },
  badge: { borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3 },
  badgeActive: { backgroundColor: colors.success },
  badgeEnded: { backgroundColor: colors.textTertiary },
  badgeText: { color: '#fff', fontSize: 10.5, fontWeight: '700' },
  kvRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  kvKey: { fontSize: 13, color: colors.textSecondary },
  kvValue: { fontSize: 13, fontWeight: '600', color: colors.textPrimary },
  emptyNote: { fontSize: 12.5, color: colors.textTertiary },
});
