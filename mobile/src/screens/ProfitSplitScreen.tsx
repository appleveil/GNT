import React, { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import type { PayoutBasis, PayoutSplitMethod, ResetCadence } from '../types';
import {
  Field,
  MoneyInput,
  OutlineDangerButton,
  PrimaryButton,
  RadioOption,
  SectionCard,
  SegmentedControl,
  naira,
} from '../components/ui';
import { getActiveProfitSplit, insertDeal } from '../db/deals';
import { colors, radii, spacing } from '../theme/tokens';
import { PercentCircleIcon, PayoutIcon } from '../components/icons';

type Props = NativeStackScreenProps<DealsStackParamList, 'ProfitSplit'>;
type ActiveArrangement = Extract<Awaited<ReturnType<typeof getActiveProfitSplit>>, { kind: 'PROFIT_SPLIT_CREATED' }>;

const CADENCE_OPTIONS: { label: string; value: ResetCadence }[] = [
  { label: 'One-off', value: 'ONE_OFF' },
  { label: 'Daily', value: 'DAILY' },
  { label: 'Weekly', value: 'WEEKLY' },
  { label: 'Monthly', value: 'MONTHLY' },
];

export default function ProfitSplitScreen({ route }: Props) {
  const { player } = route.params;
  const [active, setActive] = useState<ActiveArrangement | null>(null);

  const [stakeOn, setStakeOn] = useState(false);
  const [stakePct, setStakePct] = useState('50');
  const [cap, setCap] = useState('20000');
  const [renews, setRenews] = useState<ResetCadence>('ONE_OFF');
  const [until, setUntil] = useState('');
  const [maxTimes, setMaxTimes] = useState('');
  const [maxValue, setMaxValue] = useState('');

  const [payoutOn, setPayoutOn] = useState(false);
  const [payoutBasis, setPayoutBasis] = useState<PayoutBasis>('AFTER_BUYIN');
  const [splitMethod, setSplitMethod] = useState<PayoutSplitMethod>('STAKE_RATIO');
  const [customRatioPct, setCustomRatioPct] = useState('');
  const [fixedAmount, setFixedAmount] = useState('');
  const [fixedOffset, setFixedOffset] = useState('');

  const [saving, setSaving] = useState(false);

  function resetForm() {
    setStakeOn(false);
    setStakePct('50');
    setCap('20000');
    setRenews('ONE_OFF');
    setUntil('');
    setMaxTimes('');
    setMaxValue('');
    setPayoutOn(false);
    setPayoutBasis('AFTER_BUYIN');
    setSplitMethod('STAKE_RATIO');
    setCustomRatioPct('');
    setFixedAmount('');
    setFixedOffset('');
  }

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      getActiveProfitSplit(player.id).then((a) => {
        if (!cancelled) setActive(a as ActiveArrangement | null);
      });
      resetForm();
      return () => {
        cancelled = true;
      };
    }, [player.id]),
  );

  async function onEnd() {
    if (!active) return;
    await insertDeal({
      kind: 'PROFIT_SPLIT_ENDED',
      playerId: player.id,
      playerName: player.displayName,
      arrangementId: active.id,
    });
    setActive(null);
  }

  const stakeValid = !stakeOn || (parseFloat(stakePct) > 0 && cap.trim().length > 0);
  const payoutValid =
    !payoutOn ||
    (splitMethod === 'CUSTOM_RATIO' ? customRatioPct.trim().length > 0 : true) &&
      (splitMethod === 'FIXED' ? fixedAmount.trim().length > 0 : true);
  const canSubmit = (stakeOn || payoutOn) && stakeValid && payoutValid;

  async function onSubmit() {
    if (!canSubmit) return;
    setSaving(true);
    await insertDeal({
      kind: 'PROFIT_SPLIT_CREATED',
      playerId: player.id,
      playerName: player.displayName,
      stakeOn,
      stakePct: stakeOn ? parseFloat(stakePct) || 0 : null,
      cap: stakeOn ? parseFloat(cap) || 0 : null,
      renews: stakeOn ? renews : null,
      until: stakeOn && renews !== 'ONE_OFF' && until ? until : null,
      maxTimes: stakeOn && renews !== 'ONE_OFF' && maxTimes ? parseInt(maxTimes, 10) : null,
      maxValue: stakeOn && renews !== 'ONE_OFF' && maxValue ? parseFloat(maxValue) : null,
      payoutOn,
      payoutBasis: payoutOn ? payoutBasis : null,
      payoutSplitMethod: payoutOn ? splitMethod : null,
      customRatioPct: payoutOn && splitMethod === 'CUSTOM_RATIO' ? parseFloat(customRatioPct) || 0 : null,
      fixedAmount: payoutOn && splitMethod === 'FIXED' ? parseFloat(fixedAmount) || 0 : null,
      fixedOffset: payoutOn && splitMethod === 'FIXED' && fixedOffset ? parseFloat(fixedOffset) : null,
    });
    setSaving(false);
    resetForm();
  }

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
        {active ? (
          <View style={styles.statusCard}>
            <View style={styles.statusTop}>
              <Text style={styles.statusTitle}>Current arrangement</Text>
              <View style={styles.activeBadge}>
                <Text style={styles.activeBadgeText}>ACTIVE</Text>
              </View>
            </View>
            {active.stakeOn ? (
              <Text style={styles.statusRow}>
                House stake: {active.stakePct}% · cap {naira(active.cap ?? 0)}/period · renews {active.renews}
              </Text>
            ) : (
              <Text style={styles.statusRow}>No stake set.</Text>
            )}
            <OutlineDangerButton title="End arrangement" onPress={onEnd} />
          </View>
        ) : null}

        <SectionCard
          icon={<PercentCircleIcon color={colors.accentText} />}
          title="Stake"
          subtitle="How much of buy-in the house covers"
        >
          <RadioOption
            title="No stake"
            subtitle="House doesn't cover any of the buy-in — the default."
            checked={!stakeOn}
            onPress={() => setStakeOn(false)}
          />
          <RadioOption
            title="Set a stake"
            subtitle="House covers part of the buy-in, up to a cap."
            checked={stakeOn}
            onPress={() => setStakeOn(true)}
          />

          {stakeOn ? (
            <View style={{ marginTop: spacing.md }}>
              <Field label="House stake %" required>
                <MoneyInput value={stakePct} onChangeText={setStakePct} prefix="" placeholder="0" />
              </Field>
              <Field label="Cap" required helper="Max the house covers per period.">
                <MoneyInput value={cap} onChangeText={setCap} />
              </Field>
              <Field label="Renews">
                <SegmentedControl options={CADENCE_OPTIONS} value={renews} onChange={setRenews} />
              </Field>
              {renews !== 'ONE_OFF' ? (
                <View style={styles.conditional}>
                  <Field label="Until" optional>
                    <MoneyInput value={until} onChangeText={setUntil} prefix="" placeholder="YYYY-MM-DD" />
                  </Field>
                  <Field label="Number of times" optional>
                    <MoneyInput value={maxTimes} onChangeText={setMaxTimes} prefix="" placeholder="Unlimited" />
                  </Field>
                  <Field
                    label="Max value"
                    optional
                    helper="Whichever of these is reached first ends the arrangement."
                  >
                    <MoneyInput value={maxValue} onChangeText={setMaxValue} placeholder="Unlimited" />
                  </Field>
                </View>
              ) : null}
            </View>
          ) : null}
        </SectionCard>

        <SectionCard
          icon={<PayoutIcon color={colors.accentText} />}
          title="Payout"
          subtitle="Applies when chips are returned"
        >
          <RadioOption
            title="No payout split"
            subtitle="Player keeps everything they cash out — the default."
            checked={!payoutOn}
            onPress={() => setPayoutOn(false)}
          />
          <RadioOption
            title="Set a payout split"
            subtitle="House takes a cut of what the player returns."
            checked={payoutOn}
            onPress={() => setPayoutOn(true)}
          />

          {payoutOn ? (
            <View style={{ marginTop: spacing.md }}>
              <RadioOption
                title="After buy-in"
                subtitle="Buy-in is deducted first, then the remainder is split."
                checked={payoutBasis === 'AFTER_BUYIN'}
                onPress={() => setPayoutBasis('AFTER_BUYIN')}
              />
              <RadioOption
                title="Before buy-in"
                subtitle="All chips returned are split, before accounting for buy-in."
                checked={payoutBasis === 'BEFORE_BUYIN'}
                onPress={() => setPayoutBasis('BEFORE_BUYIN')}
              />

              <Text style={styles.subLabel}>Split method</Text>
              <RadioOption
                title="Ratio: according to stake"
                subtitle={
                  stakeOn ? `Matches the house stake of ${stakePct || 0}% above.` : 'No stake is set above — pick a different method, or set a stake first.'
                }
                checked={splitMethod === 'STAKE_RATIO'}
                onPress={() => setSplitMethod('STAKE_RATIO')}
              />
              <RadioOption
                title="Ratio: house percentage"
                subtitle="Set an independent house percentage."
                checked={splitMethod === 'CUSTOM_RATIO'}
                onPress={() => setSplitMethod('CUSTOM_RATIO')}
              />
              <RadioOption
                title="Fixed amount"
                subtitle="House takes a flat amount off the top."
                checked={splitMethod === 'FIXED'}
                onPress={() => setSplitMethod('FIXED')}
              />

              {splitMethod === 'CUSTOM_RATIO' ? (
                <View style={styles.conditional}>
                  <Field label="House percentage" required>
                    <MoneyInput value={customRatioPct} onChangeText={setCustomRatioPct} prefix="" placeholder="0" />
                  </Field>
                </View>
              ) : null}
              {splitMethod === 'FIXED' ? (
                <View style={styles.conditional}>
                  <Field label="Amount" required>
                    <MoneyInput value={fixedAmount} onChangeText={setFixedAmount} />
                  </Field>
                  <Field
                    label="Off-set"
                    optional
                    helper="Player keeps this much first; the house's fixed amount comes out of what's above it."
                  >
                    <MoneyInput value={fixedOffset} onChangeText={setFixedOffset} />
                  </Field>
                </View>
              ) : null}
            </View>
          ) : null}
        </SectionCard>

        {!canSubmit ? (
          <Text style={styles.noopNote}>Set a stake, a payout split, or both, to save an arrangement.</Text>
        ) : null}
      </ScrollView>
      <View style={styles.footer}>
        <PrimaryButton title="Save arrangement" onPress={onSubmit} disabled={!canSubmit} loading={saving} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  statusCard: {
    borderWidth: 1.5,
    borderColor: colors.accent,
    backgroundColor: colors.accentBg,
    borderRadius: radii.md,
    padding: spacing.md + 2,
    marginBottom: spacing.lg,
  },
  statusTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
  statusTitle: { fontSize: 13.5, fontWeight: '600', color: colors.textPrimary },
  activeBadge: { backgroundColor: colors.success, borderRadius: 20, paddingHorizontal: 8, paddingVertical: 3 },
  activeBadgeText: { color: '#fff', fontSize: 10.5, fontWeight: '700' },
  statusRow: { fontSize: 13, color: colors.accentText, marginBottom: spacing.xs },
  subLabel: { fontSize: 12.5, fontWeight: '600', color: colors.textSecondary, marginTop: spacing.sm, marginBottom: spacing.sm },
  conditional: { borderLeftWidth: 2, borderLeftColor: colors.borderStrong, paddingLeft: spacing.md, marginLeft: 4, marginBottom: spacing.md },
  noopNote: { fontSize: 12, color: colors.textTertiary, textAlign: 'center', marginTop: -4 },
  footer: { padding: spacing.lg, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border },
});
