import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import { Banner, Card, Field, LinkButton, MoneyInput, PrimaryButton, TextField } from '../components/ui';
import { insertDeal } from '../db/deals';
import { colors, spacing } from '../theme/tokens';

type Props = NativeStackScreenProps<DealsStackParamList, 'Fixed'>;

export default function FixedScreen({ route, navigation }: Props) {
  const { player } = route.params;
  const outstanding = Math.max(-player.balance, 0);

  const [amountText, setAmountText] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);

  const amount = parseFloat(amountText) || 0;
  const over = amount > outstanding;
  const canSubmit = amount > 0 && !over && reason.trim().length > 0 && outstanding > 0;

  async function onSubmit() {
    if (!canSubmit) return;
    setSaving(true);
    await insertDeal({
      kind: 'FIXED',
      playerId: player.id,
      playerName: player.displayName,
      amount,
      reason: reason.trim(),
    });
    setSaving(false);
    navigation.popToTop();
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
        <Card style={{ alignItems: 'center', paddingVertical: spacing.xl }}>
          <Text style={styles.label}>Outstanding</Text>
          <Text style={[styles.amount, { color: outstanding > 0 ? colors.dangerText : colors.textTertiary }]}>
            {'₦' + outstanding.toLocaleString('en-NG')}
          </Text>
        </Card>

        <Field label="Clear balance by" required error={over ? "Can't enter more than the outstanding balance." : undefined}>
          <MoneyInput value={amountText} onChangeText={setAmountText} />
        </Field>
        <LinkButton
          title={`Clear all (₦${outstanding.toLocaleString('en-NG')})`}
          onPress={() => setAmountText(String(outstanding))}
        />
        <View style={{ height: spacing.md }} />

        <Field label="Reason" required>
          <TextField value={reason} onChangeText={setReason} placeholder="Why is this being written off?" multiline />
        </Field>

        <Banner tone="warn">This can't be reversed once submitted.</Banner>
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton title="Apply write-off" onPress={onSubmit} disabled={!canSubmit} loading={saving} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  label: { fontSize: 12, color: colors.textTertiary, fontWeight: '600', textTransform: 'uppercase' },
  amount: { fontSize: 30, fontWeight: '600', marginTop: 4 },
  footer: { padding: spacing.lg, backgroundColor: colors.bg },
});
