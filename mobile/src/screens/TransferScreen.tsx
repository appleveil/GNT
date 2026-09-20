import React, { useMemo, useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import type { Player } from '../types';
import { Banner, Field, MoneyInput, PrimaryButton, TextField, balanceColor, signedNaira } from '../components/ui';
import { insertDeal } from '../db/deals';
import { getPlayers } from '../api/players';
import { colors, radii, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<DealsStackParamList, 'Transfer'>;

export default function TransferScreen({ route, navigation }: Props) {
  const { player } = route.params;
  const available = Math.max(player.balance, 0);

  const [otherPlayers, setOtherPlayers] = useState<Player[]>([]);
  const [search, setSearch] = useState('');
  const [target, setTarget] = useState<Player | null>(null);
  const [amountText, setAmountText] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  React.useEffect(() => {
    getPlayers().then(({ players }) => setOtherPlayers(players.filter((p) => p.id !== player.id)));
  }, [player.id]);

  const filteredTargets = useMemo(
    () => otherPlayers.filter((p) => !search || p.displayName.toLowerCase().includes(search.toLowerCase())),
    [otherPlayers, search],
  );

  const amount = parseFloat(amountText) || 0;
  const over = amount > available;
  const canSubmit = !!target && amount > 0 && !over && reason.trim().length > 0;

  async function onSubmit() {
    if (!canSubmit || !target) return;
    setSaving(true);
    await insertDeal({
      kind: 'TRANSFER',
      sourcePlayerId: player.id,
      sourcePlayerName: player.displayName,
      destinationPlayerId: target.id,
      destinationPlayerName: target.displayName,
      amount,
      reason: reason.trim(),
    });
    setSaving(false);
    navigation.popToTop();
  }

  if (available <= 0) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, padding: spacing.lg, paddingTop: spacing.xl }}>
        <Banner tone="danger">
          {player.displayName} has no available balance — a Transfer requires a positive balance to give away.
        </Banner>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[styles.stickyHead, scrolled && styles.stickyHeadShadow]}>
        <View style={styles.balanceBanner}>
          <Text style={styles.bbLabel}>Available to transfer</Text>
          <Text style={[styles.bbAmount, { color: colors.successText }]}>{signedNaira(available)}</Text>
        </View>
        <View style={styles.search}>
          <TextInput
            style={styles.searchInput}
            placeholder="Search players to transfer to…"
            placeholderTextColor={colors.textTertiary}
            value={search}
            onChangeText={setSearch}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
      </View>

      <FlatList
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg }}
        data={filteredTargets}
        keyExtractor={(p) => String(p.id)}
        onScroll={(e) => setScrolled(e.nativeEvent.contentOffset.y > 2)}
        scrollEventThrottle={16}
        ListHeaderComponent={
          <Text style={styles.sectionLabel}>
            Transfer to <Text style={styles.req}>*</Text>
          </Text>
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() => setTarget(item)}
            style={[styles.targetRow, target?.id === item.id && styles.targetRowSelected]}
          >
            <Text style={styles.targetName}>{item.displayName}</Text>
            <Text style={[styles.targetBalance, { color: balanceColor(item.balance) }]}>{signedNaira(item.balance)}</Text>
          </Pressable>
        )}
      />

      <View style={styles.footer}>
        <Field label="Amount" required error={over ? "Can't exceed the available balance." : undefined}>
          <MoneyInput value={amountText} onChangeText={setAmountText} />
        </Field>
        <Field label="Reason" required>
          <TextField value={reason} onChangeText={setReason} placeholder="Why is this being transferred?" multiline />
        </Field>
        <PrimaryButton title="Transfer" onPress={onSubmit} disabled={!canSubmit} loading={saving} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  stickyHead: { padding: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.bg, zIndex: 1 },
  stickyHeadShadow: {
    shadowColor: '#1C222B',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
  balanceBanner: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  bbLabel: { fontSize: 12, color: colors.textTertiary, fontWeight: '600' },
  bbAmount: { fontFamily: undefined, fontSize: 19, fontWeight: '700' },
  search: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    height: 44,
    justifyContent: 'center',
  },
  searchInput: { fontSize: 15, color: colors.textPrimary, padding: 0 },
  sectionLabel: { fontSize: 12, fontWeight: '700', textTransform: 'uppercase', color: colors.textTertiary, marginBottom: spacing.sm },
  req: { color: colors.dangerText },
  targetRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    borderRadius: radii.sm,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
  },
  targetRowSelected: { borderColor: colors.accent, backgroundColor: colors.accentBg },
  targetName: { fontSize: 13.5, fontWeight: '600', color: colors.textPrimary },
  targetBalance: { fontWeight: '600', fontSize: 13 },
  footer: { padding: spacing.lg, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border },
});
