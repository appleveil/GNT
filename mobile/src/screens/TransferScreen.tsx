import React, { useMemo, useRef, useState } from 'react';
import { Alert, FlatList, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { useHeaderHeight } from '@react-navigation/elements';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import type { Player } from '../types';
import {
  Banner,
  Field,
  KeyboardAvoidingScreen,
  MoneyInput,
  PrimaryButton,
  TextField,
  balanceColor,
  signedNaira,
} from '../components/ui';
import { insertDeal } from '../db/deals';
import { getPlayers } from '../api/players';
import { getEffectiveBalance, withEffectiveBalances } from '../db/effectiveBalance';
import { useKeyboardVisible } from '../hooks/useKeyboardVisible';
import { colors, radii, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<DealsStackParamList, 'Transfer'>;

export default function TransferScreen({ route, navigation }: Props) {
  const { player } = route.params;
  const headerHeight = useHeaderHeight();
  const [sourceBalance, setSourceBalance] = useState(player.balance);
  const available = Math.max(sourceBalance, 0);

  const [otherPlayers, setOtherPlayers] = useState<Player[]>([]);
  const [search, setSearch] = useState('');
  const [target, setTarget] = useState<Player | null>(null);
  const [amountText, setAmountText] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  // Tied to the keyboard itself, not to which field is focused — the list
  // gives up its space and the footer gets scroll slack for exactly as
  // long as the keyboard is on screen, then both snap back to their
  // normal, full resting layout the instant it's gone, however it closed
  // (Reason field blurred, Cancel tapped, tapped outside, back gesture).
  const keyboardVisible = useKeyboardVisible();
  const footerScrollRef = useRef<ScrollView>(null);

  React.useEffect(() => {
    getEffectiveBalance(player).then(setSourceBalance);
    getPlayers().then(async ({ players }) => {
      const withAdjustments = await withEffectiveBalances(players.filter((p) => p.id !== player.id));
      setOtherPlayers(withAdjustments);
    });
  }, [player.id]);

  const filteredTargets = useMemo(
    () => otherPlayers.filter((p) => !search || p.displayName.toLowerCase().includes(search.toLowerCase())),
    [otherPlayers, search],
  );

  // Once real progress has been made (an amount or reason typed in),
  // switching the recipient by mistake would silently misattribute it —
  // confirm first, and only then clear the fields for the new recipient.
  // With nothing entered yet, switching freely is fine.
  function onPickTarget(candidate: Player) {
    if (target && candidate.id !== target.id && (amountText.trim() || reason.trim())) {
      Alert.alert(
        'Change recipient?',
        `This will clear the amount and reason you've entered for ${target.displayName}.`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Change',
            style: 'destructive',
            onPress: () => {
              setTarget(candidate);
              setAmountText('');
              setReason('');
            },
          },
        ],
      );
      return;
    }
    setTarget(candidate);
  }

  const amount = parseFloat(amountText) || 0;
  const over = amount > available;
  const canSubmit = !!target && amount > 0 && !over && reason.trim().length > 0;

  async function onSubmit() {
    if (!canSubmit || !target) return;
    setSaving(true);
    try {
      await insertDeal({
        kind: 'TRANSFER',
        sourcePlayerId: player.id,
        sourcePlayerName: player.displayName,
        destinationPlayerId: target.id,
        destinationPlayerName: target.displayName,
        amount,
        reason: reason.trim(),
      });
      Alert.alert('Transfer saved', `${signedNaira(amount)} moved from ${player.displayName} to ${target.displayName}.`, [
        { text: 'OK', onPress: () => navigation.popToTop() },
      ]);
    } catch (e: any) {
      Alert.alert('Transfer failed', e?.message ?? 'Something went wrong saving this transfer. Please try again.');
    } finally {
      setSaving(false);
    }
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
    <KeyboardAvoidingScreen verticalOffset={headerHeight}>
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
        // At rest (keyboard down), this matches a plain flex:1 — same as
        // the footer, so nothing shrinks and the list looks exactly like it
        // always did. Only while the keyboard is actually up does it become
        // far more willing to shrink than the footer, so the keyboard eats
        // into the (scrollable) list instead of the (fixed) footer.
        style={{ flexGrow: 1, flexShrink: keyboardVisible ? 20 : 1, flexBasis: 0 }}
        contentContainerStyle={{ padding: spacing.lg }}
        data={filteredTargets}
        keyExtractor={(p) => String(p.id)}
        keyboardShouldPersistTaps="handled"
        onScroll={(e) => setScrolled(e.nativeEvent.contentOffset.y > 2)}
        scrollEventThrottle={16}
        ListHeaderComponent={
          <Text style={styles.sectionLabel}>
            Transfer to <Text style={styles.req}>*</Text>
          </Text>
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() => onPickTarget(item)}
            style={[styles.targetRow, target?.id === item.id && styles.targetRowSelected]}
          >
            <Text style={styles.targetName}>{item.displayName}</Text>
            <Text style={[styles.targetBalance, { color: balanceColor(item.balance) }]}>{signedNaira(item.balance)}</Text>
          </Pressable>
        )}
      />

      {/* flexShrink (not just a fixed height) is the point: when the
          keyboard eats space, this panel can be compressed below its
          natural content height instead of overflowing past the visible
          screen — and being a ScrollView, whatever gets compressed out
          (the Reason field, usually) is still reachable by scrolling
          inside it. A plain View can't do that; it would just clip. */}
      <ScrollView
        ref={footerScrollRef}
        style={styles.footer}
        // Extra bottom padding only while the keyboard is up — at rest
        // this is the same small padding it's always had. Static,
        // permanent slack here was the bug: a big fixed paddingBottom
        // inflates this ScrollView's own measured size even with the
        // keyboard down, which is what was stealing space from the list
        // permanently, not just while typing.
        contentContainerStyle={[styles.footerContent, keyboardVisible && styles.footerContentFocused]}
        keyboardShouldPersistTaps="handled"
      >
        <Field label="Amount" required error={over ? "Can't exceed the available balance." : undefined}>
          <MoneyInput value={amountText} onChangeText={setAmountText} />
        </Field>
        <Field label="Reason" required>
          <TextField
            value={reason}
            onChangeText={setReason}
            placeholder="Why is this being transferred?"
            multiline
            onFocus={() => footerScrollRef.current?.scrollToEnd({ animated: true })}
          />
        </Field>
        <PrimaryButton title="Transfer" onPress={onSubmit} disabled={!canSubmit} loading={saving} />
      </ScrollView>
    </KeyboardAvoidingScreen>
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
  // flexGrow: 0 + flexShrink: 1 — never grows to steal space from the
  // target list above, but WILL shrink below its own content height under
  // pressure rather than overflow. In practice this rarely needs to
  // shrink at all, since the list (flexShrink: 20, while the keyboard is
  // up) gives way first — it's a last-resort safety valve, not the
  // primary mechanism.
  footer: { flexGrow: 0, flexShrink: 1, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border },
  footerContent: { padding: spacing.lg },
  // Slack to scroll into so the OS's own focus-scroll (or our explicit
  // scrollToEnd on Reason) has somewhere to actually reveal — applied
  // only while the keyboard is actually up (see keyboardVisible), not
  // permanently.
  footerContentFocused: { paddingBottom: spacing.lg + 220 },
});
