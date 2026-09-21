import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import { Card, balanceColor, signedNaira } from '../components/ui';
import { getActiveProfitSplit } from '../db/deals';
import { colors, radii, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<DealsStackParamList, 'DealTypePicker'>;

export default function DealTypePickerScreen({ route, navigation }: Props) {
  const { player } = route.params;
  const hasDebt = player.balance < 0;
  const hasFunds = player.balance > 0;

  // Re-checked on every focus, not just on mount, so ending an arrangement
  // on the ProfitSplit screen and coming straight back here (no full app
  // relaunch) still shows the badge's current state, not a stale one.
  const [hasActiveProfitSplit, setHasActiveProfitSplit] = useState(false);
  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      getActiveProfitSplit(player.id).then((a) => {
        if (!cancelled) setHasActiveProfitSplit(!!a);
      });
      return () => {
        cancelled = true;
      };
    }, [player.id]),
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={{ padding: spacing.lg }}>
      <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
        <Text style={styles.balanceLabel}>Balance</Text>
        <Text style={[styles.balanceAmount, { color: balanceColor(player.balance) }]}>
          {signedNaira(player.balance)}
        </Text>
      </Card>

      <DealTypeButton
        title="Fixed"
        description={
          hasDebt
            ? "Reduce this player's outstanding debt by a fixed amount. Can't be reversed."
            : 'No outstanding balance to forgive.'
        }
        disabled={!hasDebt}
        onPress={() => navigation.navigate('Fixed', { player })}
      />
      <DealTypeButton
        title="Transfer"
        description={
          hasFunds
            ? "Use this player's excess balance to help settle another player's debt."
            : 'No available balance to transfer.'
        }
        disabled={!hasFunds}
        onPress={() => navigation.navigate('Transfer', { player })}
      />
      <DealTypeButton
        title="Stake and Profit splits"
        description="A standing arrangement — house covers part of buy-in and/or takes a payout cut."
        badge={hasActiveProfitSplit ? 'ACTIVE' : undefined}
        onPress={() => navigation.navigate('ProfitSplit', { player })}
      />
    </ScrollView>
  );
}

function DealTypeButton({
  title,
  description,
  disabled,
  badge,
  onPress,
}: {
  title: string;
  description: string;
  disabled?: boolean;
  /** Short pill label (e.g. "ACTIVE") shown next to the title — for
   * surfacing that this deal type already has a live arrangement for this
   * player, so it's obvious without opening the form. */
  badge?: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={[styles.dealType, disabled && styles.dealTypeDisabled]}
    >
      <View>
        <View style={styles.dealTypeTitleRow}>
          <Text style={styles.dealTypeTitle}>{title}</Text>
          {badge ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{badge}</Text>
            </View>
          ) : null}
        </View>
        <Text style={styles.dealTypeDesc}>{description}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  balanceLabel: { fontSize: 12, color: colors.textTertiary, fontWeight: '600', textTransform: 'uppercase' },
  balanceAmount: { fontSize: 30, fontWeight: '600', marginTop: 4 },
  dealType: {
    backgroundColor: colors.surface,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md + 2,
    marginBottom: spacing.sm + 2,
  },
  dealTypeDisabled: { opacity: 0.45 },
  dealTypeTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: 2 },
  dealTypeTitle: { fontSize: 14.5, fontWeight: '600', color: colors.textPrimary },
  dealTypeDesc: { fontSize: 12.5, color: colors.textSecondary, lineHeight: 17 },
  badge: { backgroundColor: colors.success, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 2 },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '700' },
});
