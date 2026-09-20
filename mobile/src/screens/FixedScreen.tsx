import React, { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useHeaderHeight } from '@react-navigation/elements';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import { Banner, Card, Field, KeyboardAvoidingScreen, LinkButton, MoneyInput, PrimaryButton, TextField, naira } from '../components/ui';
import { insertDeal } from '../db/deals';
import { getEffectiveBalance } from '../db/effectiveBalance';
import { colors, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<DealsStackParamList, 'Fixed'>;

export default function FixedScreen({ route, navigation }: Props) {
  const { player } = route.params;
  const headerHeight = useHeaderHeight();
  const [balance, setBalance] = useState(player.balance);
  const outstanding = Math.max(-balance, 0);

  const [amountText, setAmountText] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    getEffectiveBalance(player).then(setBalance);
  }, [player.id]);

  const amount = parseFloat(amountText) || 0;
  const over = amount > outstanding;
  const canSubmit = amount > 0 && !over && reason.trim().length > 0 && outstanding > 0;

  async function onSubmit() {
    if (!canSubmit) return;
    setSaving(true);
    try {
      await insertDeal({
        kind: 'FIXED',
        playerId: player.id,
        playerName: player.displayName,
        amount,
        reason: reason.trim(),
      });
      Alert.alert('Write-off saved', `${naira(amount)} cleared from ${player.displayName}'s outstanding balance.`, [
        { text: 'OK', onPress: () => navigation.popToTop() },
      ]);
    } catch (e: any) {
      Alert.alert('Write-off failed', e?.message ?? 'Something went wrong saving this write-off. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingScreen verticalOffset={headerHeight}>
      <ScrollView ref={scrollRef} contentContainerStyle={{ padding: spacing.lg }} keyboardShouldPersistTaps="handled">
        <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
          <Text style={styles.label}>Outstanding</Text>
          <Text style={[styles.amount, { color: outstanding > 0 ? colors.dangerText : colors.textTertiary }]}>
            {naira(outstanding)}
          </Text>
        </Card>

        <Field label="Clear balance by" required error={over ? "Can't enter more than the outstanding balance." : undefined}>
          <MoneyInput value={amountText} onChangeText={setAmountText} />
        </Field>
        <LinkButton title={`Clear all (${naira(outstanding)})`} onPress={() => setAmountText(String(outstanding))} />
        <View style={{ height: spacing.md }} />

        <Field label="Reason" required>
          <TextField
            value={reason}
            onChangeText={setReason}
            placeholder="Why is this being written off?"
            multiline
            onFocus={() => scrollRef.current?.scrollToEnd({ animated: true })}
          />
        </Field>

        <Banner tone="warn">This can't be reversed once submitted.</Banner>
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton title="Apply write-off" onPress={onSubmit} disabled={!canSubmit} loading={saving} />
      </View>
    </KeyboardAvoidingScreen>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 12, color: colors.textTertiary, fontWeight: '600', textTransform: 'uppercase' },
  amount: { fontSize: 30, fontWeight: '600', marginTop: 4 },
  footer: { padding: spacing.lg, backgroundColor: colors.bg },
});
