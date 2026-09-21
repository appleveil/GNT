import React, { useCallback, useRef, useState } from 'react';
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { useFocusEffect } from '@react-navigation/native';
import { useHeaderHeight } from '@react-navigation/elements';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import type { PayoutBasis, PayoutLifespan, PayoutSplitMethod, ResetCadence } from '../types';
import {
  Banner,
  Field,
  KeyboardAvoidingScreen,
  LinkButton,
  MoneyInput,
  OutlineDangerButton,
  PrimaryButton,
  RadioOption,
  SectionCard,
  SegmentedControl,
  TextField,
  naira,
} from '../components/ui';
import { getActiveProfitSplit, insertDeal } from '../db/deals';
import { getEffectiveBalance } from '../db/effectiveBalance';
import { useKeyboardVisible } from '../hooks/useKeyboardVisible';
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

// `until` is stored as a plain YYYY-MM-DD string (matches the read-only
// detail screen and every export/share) — these just convert at the edges
// so the picker can work in real Date objects.
function toIsoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function fromIsoDate(iso: string): Date {
  const d = new Date(iso + 'T00:00:00');
  return isNaN(d.getTime()) ? new Date() : d;
}

function formatIsoDate(iso: string): string {
  return fromIsoDate(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export default function ProfitSplitScreen({ route }: Props) {
  const { player } = route.params;
  const headerHeight = useHeaderHeight();
  const scrollRef = useRef<ScrollView>(null);
  const [active, setActive] = useState<ActiveArrangement | null>(null);
  // Ending is deliberately two-step: revealing the reason field is not
  // itself the end action, and the reason is required before the final
  // confirm dialog is even offered — see onConfirmEnd.
  const [endingOpen, setEndingOpen] = useState(false);
  const [endReason, setEndReason] = useState('');

  const [stakeOn, setStakeOn] = useState(false);
  const [stakePct, setStakePct] = useState('50');
  const [cap, setCap] = useState('20000');
  const [renews, setRenews] = useState<ResetCadence>('ONE_OFF');
  const [until, setUntil] = useState('');
  const [showUntilPicker, setShowUntilPicker] = useState(false);
  const [maxTimes, setMaxTimes] = useState('');
  const [maxValue, setMaxValue] = useState('');

  const [payoutOn, setPayoutOn] = useState(false);
  const [payoutBasis, setPayoutBasis] = useState<PayoutBasis>('AFTER_BUYIN');
  const [splitMethod, setSplitMethod] = useState<PayoutSplitMethod>('STAKE_RATIO');
  const [customRatioPct, setCustomRatioPct] = useState('');
  const [fixedAmount, setFixedAmount] = useState('');
  const [fixedOffset, setFixedOffset] = useState('');
  const [payoutLifespan, setPayoutLifespan] = useState<PayoutLifespan>('INDEFINITE');
  const [payoutCapAmount, setPayoutCapAmount] = useState('');

  // For the "until debt clears" nudge below — refreshed on every focus,
  // same as `active`, so it reflects Deals saved elsewhere in the meantime.
  const [balance, setBalance] = useState(player.balance);

  const [saving, setSaving] = useState(false);
  // Extra bottom scroll-slack is only needed while the keyboard is
  // actually up. Tied to the keyboard itself rather than to which field
  // is focused — a focus/blur-gated version restores too early (tabbing
  // between fields) or not at all (keyboard dismissed some other way,
  // e.g. tapping outside) — and gating it permanently on instead left a
  // large dead gap at the bottom of the form even at rest.
  const keyboardVisible = useKeyboardVisible();
  const onBottomFieldFocus = () => scrollRef.current?.scrollToEnd({ animated: true });

  function resetForm() {
    setStakeOn(false);
    setStakePct('50');
    setCap('20000');
    setRenews('ONE_OFF');
    setUntil('');
    setShowUntilPicker(false);
    setMaxTimes('');
    setMaxValue('');
    setPayoutOn(false);
    setPayoutBasis('AFTER_BUYIN');
    setSplitMethod('STAKE_RATIO');
    setCustomRatioPct('');
    setFixedAmount('');
    setFixedOffset('');
    setPayoutLifespan('INDEFINITE');
    setPayoutCapAmount('');
  }

  useFocusEffect(
    useCallback(() => {
      let cancelled = false;
      getActiveProfitSplit(player.id).then((a) => {
        if (!cancelled) setActive(a as ActiveArrangement | null);
      });
      getEffectiveBalance(player).then((b) => {
        if (!cancelled) setBalance(b);
      });
      resetForm();
      setEndingOpen(false);
      setEndReason('');
      return () => {
        cancelled = true;
      };
    }, [player.id]),
  );

  async function onEnd(reason: string) {
    if (!active) return;
    try {
      await insertDeal({
        kind: 'PROFIT_SPLIT_ENDED',
        playerId: player.id,
        playerName: player.displayName,
        arrangementId: active.id,
        reason,
      });
      setActive(null);
      setEndingOpen(false);
      setEndReason('');
      Alert.alert('Arrangement ended', `${player.displayName}'s Profit Split arrangement has been ended.`);
    } catch (e: any) {
      Alert.alert('Failed to end arrangement', e?.message ?? 'Something went wrong. Please try again.');
    }
  }

  // The reason field's Field-level "required" marker already stops an
  // empty submit from doing anything visible; this Alert is the actual
  // confirmation step, since ending an arrangement can't be undone.
  function onConfirmEnd() {
    if (!endReason.trim() || !active) return;
    Alert.alert(
      'End this arrangement?',
      `This ends ${player.displayName}'s Stake and Profit splits arrangement. This can't be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'End arrangement', style: 'destructive', onPress: () => onEnd(endReason.trim()) },
      ],
    );
  }

  // Turning the stake off makes "Ratio: according to stake" meaningless —
  // see the disabled RadioOption below. Switch away from it automatically
  // so the form never sits on an invalid/inapplicable selection.
  function onStakeToggle(on: boolean) {
    setStakeOn(on);
    if (!on && splitMethod === 'STAKE_RATIO') setSplitMethod('CUSTOM_RATIO');
  }

  const stakeValid = !stakeOn || (parseFloat(stakePct) > 0 && cap.trim().length > 0);
  const splitMethodApplicable = splitMethod !== 'STAKE_RATIO' || stakeOn;
  const payoutValid =
    !payoutOn ||
    (splitMethodApplicable &&
      (splitMethod === 'CUSTOM_RATIO' ? customRatioPct.trim().length > 0 : true) &&
      (splitMethod === 'FIXED' ? fixedAmount.trim().length > 0 : true) &&
      (payoutLifespan === 'CAPPED' ? payoutCapAmount.trim().length > 0 : true));
  const canSubmit = (stakeOn || payoutOn) && stakeValid && payoutValid;

  async function onSubmit() {
    if (!canSubmit) return;
    setSaving(true);
    try {
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
        payoutLifespan: payoutOn ? payoutLifespan : null,
        payoutCapAmount: payoutOn && payoutLifespan === 'CAPPED' ? parseFloat(payoutCapAmount) || 0 : null,
      });
      Alert.alert('Arrangement saved', `A Profit Split arrangement has been set up for ${player.displayName}.`);
      resetForm();
      getActiveProfitSplit(player.id).then((a) => setActive(a as ActiveArrangement | null));
    } catch (e: any) {
      Alert.alert('Save failed', e?.message ?? 'Something went wrong saving this arrangement. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <KeyboardAvoidingScreen verticalOffset={headerHeight}>
      <ScrollView
        ref={scrollRef}
        contentContainerStyle={[styles.scrollContent, keyboardVisible && styles.scrollContentFocused]}
        keyboardShouldPersistTaps="handled"
      >
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
            {active.payoutOn && active.payoutLifespan === 'DEBT_CLEARED' && balance >= 0 ? (
              <Banner tone="info">
                {player.displayName}'s balance has cleared — the payout split was set to run only until then.
                Consider ending this arrangement below.
              </Banner>
            ) : null}
            {endingOpen ? (
              <View style={{ marginTop: spacing.sm }}>
                <Field label="Reason for ending" required>
                  <TextField
                    value={endReason}
                    onChangeText={setEndReason}
                    placeholder="Why is this arrangement ending?"
                    multiline
                  />
                </Field>
                <View style={styles.endActions}>
                  <LinkButton
                    title="Cancel"
                    onPress={() => {
                      setEndingOpen(false);
                      setEndReason('');
                    }}
                  />
                  <View style={{ flex: 1 }}>
                    <OutlineDangerButton
                      title="End arrangement"
                      onPress={onConfirmEnd}
                      disabled={!endReason.trim()}
                    />
                  </View>
                </View>
              </View>
            ) : (
              <OutlineDangerButton title="End arrangement" onPress={() => setEndingOpen(true)} />
            )}
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
            onPress={() => onStakeToggle(false)}
          />
          <RadioOption
            title="Set a stake"
            subtitle="House covers part of the buy-in, up to a cap."
            checked={stakeOn}
            onPress={() => onStakeToggle(true)}
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
                  <Field label="Until" optional helper="Can't be in the past.">
                    <Pressable onPress={() => setShowUntilPicker(true)} style={styles.dateInput}>
                      <Text style={until ? styles.dateInputText : styles.dateInputPlaceholder}>
                        {until ? formatIsoDate(until) : 'No end date'}
                      </Text>
                    </Pressable>
                    {showUntilPicker ? (
                      <View style={styles.dateInputPickerWrap}>
                        <DateTimePicker
                          value={until ? fromIsoDate(until) : new Date()}
                          mode="date"
                          minimumDate={new Date()}
                          display={Platform.OS === 'ios' ? 'inline' : 'calendar'}
                          onValueChange={(_event, selectedDate) => {
                            setUntil(toIsoDate(selectedDate));
                            if (Platform.OS === 'android') setShowUntilPicker(false);
                          }}
                          onDismiss={() => setShowUntilPicker(false)}
                        />
                        {Platform.OS === 'ios' ? (
                          <LinkButton title="Done" onPress={() => setShowUntilPicker(false)} />
                        ) : null}
                      </View>
                    ) : null}
                  </Field>
                  <Field label="Number of times" optional>
                    <MoneyInput value={maxTimes} onChangeText={setMaxTimes} prefix="" placeholder="Unlimited" />
                  </Field>
                  <Field
                    label="Max value"
                    optional
                    helper="Whichever of these is reached first ends the arrangement."
                  >
                    <MoneyInput
                      value={maxValue}
                      onChangeText={setMaxValue}
                      placeholder="Unlimited"
                      onFocus={onBottomFieldFocus}
                    />
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
                  stakeOn ? `Matches the house stake of ${stakePct || 0}% above.` : "Not applicable — no stake is set above."
                }
                checked={splitMethod === 'STAKE_RATIO'}
                onPress={() => setSplitMethod('STAKE_RATIO')}
                disabled={!stakeOn}
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
                    <MoneyInput
                      value={customRatioPct}
                      onChangeText={setCustomRatioPct}
                      prefix=""
                      placeholder="0"
                      onFocus={onBottomFieldFocus}
                    />
                  </Field>
                </View>
              ) : null}
              {splitMethod === 'FIXED' ? (
                <View style={styles.conditional}>
                  <Field label="Amount" required>
                    <MoneyInput
                      value={fixedAmount}
                      onChangeText={setFixedAmount}
                      onFocus={onBottomFieldFocus}
                    />
                  </Field>
                  <Field
                    label="Off-set"
                    optional
                    helper="Player keeps this much first; the house's fixed amount comes out of what's above it."
                  >
                    <MoneyInput
                      value={fixedOffset}
                      onChangeText={setFixedOffset}
                      onFocus={onBottomFieldFocus}
                    />
                  </Field>
                </View>
              ) : null}

              {splitMethodApplicable ? (
                <>
                  <Text style={styles.subLabel}>Lifespan</Text>
                  <RadioOption
                    title="Indefinite"
                    subtitle="Applies until the arrangement is ended — the default."
                    checked={payoutLifespan === 'INDEFINITE'}
                    onPress={() => setPayoutLifespan('INDEFINITE')}
                  />
                  <RadioOption
                    title="Until debt clears"
                    subtitle={`Stops applying once ${player.displayName}'s balance is no longer negative.`}
                    checked={payoutLifespan === 'DEBT_CLEARED'}
                    onPress={() => setPayoutLifespan('DEBT_CLEARED')}
                  />
                  <RadioOption
                    title="Until a set amount is reached"
                    subtitle="Stops once the house has taken this much in total. Not tracked automatically — a reminder, not a limit the app enforces."
                    checked={payoutLifespan === 'CAPPED'}
                    onPress={() => setPayoutLifespan('CAPPED')}
                  />
                  {payoutLifespan === 'CAPPED' ? (
                    <View style={styles.conditional}>
                      <Field
                        label="Cap"
                        required
                        helper="House's cumulative take across every payout, before the split stops."
                      >
                        <MoneyInput
                          value={payoutCapAmount}
                          onChangeText={setPayoutCapAmount}
                          onFocus={onBottomFieldFocus}
                        />
                      </Field>
                    </View>
                  ) : null}
                </>
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
    </KeyboardAvoidingScreen>
  );
}

const styles = StyleSheet.create({
  scrollContent: { padding: spacing.lg },
  // Slack to scroll into so scrollToEnd (or the OS's own focus-scroll) has
  // somewhere to actually reveal the focused field — applied only while
  // one of the form's bottom-most fields is focused (see
  // keyboardVisible), not permanently.
  scrollContentFocused: { paddingBottom: spacing.lg + 220 },
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
  endActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  dateInput: {
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 11,
    backgroundColor: colors.surface,
  },
  dateInputText: { fontSize: 14.5, color: colors.textPrimary },
  dateInputPlaceholder: { fontSize: 14.5, color: colors.textTertiary },
  dateInputPickerWrap: {
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    padding: spacing.sm,
    alignItems: 'flex-end',
  },
  subLabel: { fontSize: 12.5, fontWeight: '600', color: colors.textSecondary, marginTop: spacing.sm, marginBottom: spacing.sm },
  conditional: { borderLeftWidth: 2, borderLeftColor: colors.borderStrong, paddingLeft: spacing.md, marginLeft: 4, marginBottom: spacing.md },
  noopNote: { fontSize: 12, color: colors.textTertiary, textAlign: 'center', marginTop: -4 },
  footer: { padding: spacing.lg, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border },
});
