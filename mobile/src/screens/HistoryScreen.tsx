import React, { useCallback, useMemo, useState } from 'react';
import { Alert, FlatList, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { HistoryStackParamList } from '../navigation/types';
import type { DealKindFilter, DealRecord } from '../types';
import { getAllDeals } from '../db/deals';
import { exportDealsAsCsv, shareDealAsPdf, shareDealAsText } from '../db/export';
import { dealRowTitle, dealSummary, dealTitle } from '../db/dealText';
import { FixedIcon, TransferIcon, PercentCircleIcon, ShareIcon } from '../components/icons';
import { naira } from '../components/ui';
import { colors, radii, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<HistoryStackParamList, 'History'>;

const FILTERS: { label: string; value: DealKindFilter }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Fixed', value: 'FIXED' },
  { label: 'Transfer', value: 'TRANSFER' },
  { label: 'Stake and Profit splits', value: 'PROFIT_SPLIT' },
];

export default function HistoryScreen({ navigation }: Props) {
  const [deals, setDeals] = useState<DealRecord[]>([]);
  const [filter, setFilter] = useState<DealKindFilter>('ALL');
  const [exporting, setExporting] = useState(false);

  useFocusEffect(
    useCallback(() => {
      getAllDeals().then(setDeals);
    }, []),
  );

  const filtered = useMemo(() => {
    if (filter === 'ALL') return deals;
    if (filter === 'PROFIT_SPLIT') return deals.filter((d) => d.kind.startsWith('PROFIT_SPLIT'));
    return deals.filter((d) => d.kind === filter);
  }, [deals, filter]);

  async function onExportAll() {
    if (deals.length === 0) {
      Alert.alert('Nothing to export', 'No deals have been saved yet.');
      return;
    }
    setExporting(true);
    try {
      await exportDealsAsCsv(deals);
    } catch (e: any) {
      Alert.alert('Export failed', e?.message ?? 'Something went wrong.');
    } finally {
      setExporting(false);
    }
  }

  function onShareOne(record: DealRecord) {
    Alert.alert(dealTitle(record), 'Share this deal as…', [
      {
        text: 'Text (e.g. WhatsApp)',
        onPress: () => shareDealAsText(record).catch((e) => Alert.alert('Share failed', e?.message ?? 'Something went wrong.')),
      },
      {
        text: 'PDF',
        onPress: () => shareDealAsPdf(record).catch((e) => Alert.alert('Share failed', e?.message ?? 'Something went wrong.')),
      },
      { text: 'Cancel', style: 'cancel' },
    ]);
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <View style={styles.stickyHead}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
          {FILTERS.map((f) => (
            <Pressable
              key={f.value}
              onPress={() => setFilter(f.value)}
              style={[styles.chip, filter === f.value && styles.chipActive]}
            >
              <Text style={[styles.chipText, filter === f.value && styles.chipTextActive]}>{f.label}</Text>
            </Pressable>
          ))}
        </ScrollView>
        <Pressable onPress={onExportAll} disabled={exporting} style={styles.exportBtn}>
          <Text style={styles.exportBtnText}>{exporting ? 'Exporting…' : 'Export all'}</Text>
        </Pressable>
      </View>

      <FlatList
        contentContainerStyle={{ padding: spacing.lg }}
        data={filtered}
        keyExtractor={(d) => d.id}
        ListEmptyComponent={<Text style={styles.emptyText}>No deals of this type yet.</Text>}
        renderItem={({ item }) => {
          const isProfitSplit = item.kind === 'PROFIT_SPLIT_CREATED' || item.kind === 'PROFIT_SPLIT_ENDED';
          return (
            <HistoryRow
              record={item}
              onPress={
                item.kind === 'PROFIT_SPLIT_CREATED'
                  ? () => navigation.navigate('ProfitSplitDetail', { arrangementId: item.id })
                  : undefined
              }
              onShare={isProfitSplit ? () => onShareOne(item) : undefined}
            />
          );
        }}
      />
    </View>
  );
}

function HistoryRow({
  record,
  onPress,
  onShare,
}: {
  record: DealRecord;
  onPress?: () => void;
  /** Only Stake and Profit splits are shareable — Fixed/Transfer deals aren't. */
  onShare?: () => void;
}) {
  const when = new Date(record.createdAt).toLocaleString();
  const title = dealRowTitle(record);
  const sub = dealSummary(record);
  let icon: React.ReactNode;
  let iconBg: string;
  let amountNode: React.ReactNode = null;

  switch (record.kind) {
    case 'FIXED':
      icon = <FixedIcon color={colors.dangerText} />;
      iconBg = colors.dangerBg;
      amountNode = <Text style={[styles.amount, { color: colors.dangerText }]}>{'−' + naira(record.amount)}</Text>;
      break;
    case 'TRANSFER':
      icon = <TransferIcon color={colors.accentText} />;
      iconBg = colors.accentBg;
      amountNode = <Text style={styles.amount}>{naira(record.amount)}</Text>;
      break;
    case 'PROFIT_SPLIT_CREATED':
      icon = <PercentCircleIcon color={colors.successText} />;
      iconBg = colors.successBg;
      amountNode = (
        <View style={styles.tag}>
          <Text style={styles.tagText}>SET UP</Text>
        </View>
      );
      break;
    case 'PROFIT_SPLIT_ENDED':
      icon = <PercentCircleIcon color={colors.successText} />;
      iconBg = colors.successBg;
      amountNode = (
        <View style={[styles.tag, { backgroundColor: colors.disabledSurface }]}>
          <Text style={[styles.tagText, { color: colors.textTertiary }]}>ENDED</Text>
        </View>
      );
      break;
  }

  const Wrapper = onPress ? Pressable : View;
  return (
    <View style={styles.row}>
      <Wrapper onPress={onPress} style={styles.rowMain}>
        <View style={[styles.rowIcon, { backgroundColor: iconBg }]}>{icon}</View>
        <View style={{ flex: 1 }}>
          <Text style={styles.rowTitle}>{title}</Text>
          <Text style={styles.rowSub}>{sub}</Text>
          <Text style={styles.rowTime}>{when}</Text>
        </View>
        {amountNode}
      </Wrapper>
      {onShare ? (
        <Pressable onPress={onShare} style={styles.shareBtn} hitSlop={8}>
          <ShareIcon color={colors.textTertiary} size={16} />
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stickyHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.bg,
  },
  chip: {
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  chipActive: { borderColor: colors.accent, backgroundColor: colors.accent },
  chipText: { fontSize: 12.5, fontWeight: '600', color: colors.textSecondary },
  chipTextActive: { color: '#fff' },
  exportBtn: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  exportBtnText: { fontSize: 13, fontWeight: '700', color: colors.accentText },
  emptyText: { textAlign: 'center', color: colors.textTertiary, marginTop: spacing.xl },
  row: {
    flexDirection: 'row',
    alignItems: 'stretch',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    marginBottom: spacing.sm,
    overflow: 'hidden',
  },
  rowMain: { flex: 1, flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md, padding: spacing.md },
  rowIcon: { width: 32, height: 32, borderRadius: radii.sm, alignItems: 'center', justifyContent: 'center' },
  rowTitle: { fontSize: 13.5, fontWeight: '600', color: colors.textPrimary },
  rowSub: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  rowTime: { fontSize: 11, color: colors.textTertiary, marginTop: 4 },
  amount: { fontWeight: '600', fontSize: 13.5 },
  tag: { backgroundColor: colors.successBg, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  tagText: { fontSize: 10, fontWeight: '700', color: colors.successText },
  shareBtn: { width: 40, alignItems: 'center', justifyContent: 'center', borderLeftWidth: 1, borderLeftColor: colors.border },
});
