import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, ViewStyle } from 'react-native';
import { colors, radii, spacing } from '../theme/tokens';

/** Formats a Naira amount the same way the mockup does: "₦12,345" — no decimals, sign handled by the caller. */
export function naira(amount: number): string {
  return '₦' + Math.abs(Math.round(amount)).toLocaleString('en-NG');
}

export function signedNaira(amount: number): string {
  if (amount === 0) return '₦0';
  return (amount > 0 ? '+' : '−') + naira(amount);
}

export function balanceColor(amount: number): string {
  if (amount > 0) return colors.successText;
  if (amount < 0) return colors.dangerText;
  return colors.textTertiary;
}

export function Screen({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionCard({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.sectionHead}>
        <View style={styles.sectionIcon}>{icon}</View>
        <View style={{ flex: 1 }}>
          <Text style={styles.sectionTitle}>{title}</Text>
          <Text style={styles.sectionSubtitle}>{subtitle}</Text>
        </View>
      </View>
      {children}
    </View>
  );
}

export function Field({
  label,
  required,
  optional,
  helper,
  error,
  children,
}: {
  label: string;
  required?: boolean;
  optional?: boolean;
  helper?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>
        {label}
        {required ? <Text style={styles.req}> *</Text> : null}
        {optional ? <Text style={styles.opt}> (optional)</Text> : null}
      </Text>
      {children}
      {error ? <Text style={styles.errorText}>{error}</Text> : helper ? <Text style={styles.helper}>{helper}</Text> : null}
    </View>
  );
}

export function MoneyInput({
  value,
  onChangeText,
  placeholder = '0.00',
  prefix = '₦',
}: {
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  prefix?: string;
}) {
  return (
    <View style={styles.moneyInput}>
      <Text style={styles.moneyPrefix}>{prefix}</Text>
      <TextInput
        style={styles.moneyInputText}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.textTertiary}
        keyboardType="decimal-pad"
      />
    </View>
  );
}

export function TextField({
  value,
  onChangeText,
  placeholder,
  multiline,
}: {
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
}) {
  return (
    <TextInput
      style={[styles.textInput, multiline && styles.textArea]}
      value={value}
      onChangeText={onChangeText}
      placeholder={placeholder}
      placeholderTextColor={colors.textTertiary}
      multiline={multiline}
    />
  );
}

export function PrimaryButton({
  title,
  onPress,
  disabled,
  loading,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={[styles.primaryButton, (disabled || loading) && styles.primaryButtonDisabled]}
    >
      {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryButtonText}>{title}</Text>}
    </Pressable>
  );
}

export function LinkButton({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} hitSlop={8}>
      <Text style={styles.linkButtonText}>{title}</Text>
    </Pressable>
  );
}

export function OutlineDangerButton({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={styles.dangerOutlineButton}>
      <Text style={styles.dangerOutlineText}>{title}</Text>
    </Pressable>
  );
}

export function Banner({ tone, children }: { tone: 'warn' | 'info' | 'danger'; children: React.ReactNode }) {
  const toneStyles = {
    warn: { backgroundColor: colors.warningBg, color: colors.warningText },
    info: { backgroundColor: colors.accentBg, color: colors.accentText },
    danger: { backgroundColor: colors.dangerBg, color: colors.dangerText },
  }[tone];
  return (
    <View style={[styles.banner, { backgroundColor: toneStyles.backgroundColor }]}>
      <Text style={[styles.bannerText, { color: toneStyles.color }]}>{children}</Text>
    </View>
  );
}

export function RadioOption({
  title,
  subtitle,
  checked,
  onPress,
}: {
  title: string;
  subtitle: string;
  checked: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={[styles.radioOpt, checked && styles.radioOptChecked]}>
      <View style={[styles.radioDot, checked && styles.radioDotChecked]}>
        {checked ? <View style={styles.radioDotInner} /> : null}
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.radioTitle}>{title}</Text>
        <Text style={styles.radioSubtitle}>{subtitle}</Text>
      </View>
    </Pressable>
  );
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { label: string; value: T }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <View style={styles.segmented}>
      {options.map((opt) => (
        <Pressable
          key={opt.value}
          onPress={() => onChange(opt.value)}
          style={[styles.segmentBtn, value === opt.value && styles.segmentBtnActive]}
        >
          <Text style={[styles.segmentText, value === opt.value && styles.segmentTextActive]}>{opt.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.lg },
  sectionIcon: {
    width: 32,
    height: 32,
    borderRadius: radii.sm,
    backgroundColor: colors.accentBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sectionTitle: { fontSize: 14.5, fontWeight: '600', color: colors.textPrimary },
  sectionSubtitle: { fontSize: 11.5, color: colors.textSecondary, marginTop: 1 },

  field: { marginBottom: spacing.lg },
  fieldLabel: { fontSize: 12.5, fontWeight: '600', color: colors.textSecondary, marginBottom: spacing.sm },
  req: { color: colors.dangerText, fontWeight: '700' },
  opt: { color: colors.textTertiary, fontWeight: '500' },
  helper: { fontSize: 12, color: colors.textTertiary, marginTop: spacing.sm, lineHeight: 16 },
  errorText: { fontSize: 12, color: colors.dangerText, marginTop: spacing.sm, lineHeight: 16 },

  moneyInput: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    height: 48,
  },
  moneyPrefix: { color: colors.textTertiary, fontWeight: '600', marginRight: spacing.xs },
  moneyInputText: { flex: 1, fontSize: 16, fontWeight: '600', color: colors.textPrimary, padding: 0 },

  textInput: {
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 11,
    fontSize: 14.5,
    color: colors.textPrimary,
    backgroundColor: colors.surface,
  },
  textArea: { minHeight: 72, textAlignVertical: 'top' },

  primaryButton: {
    height: 52,
    borderRadius: radii.md,
    backgroundColor: colors.accent,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonDisabled: { backgroundColor: colors.muted },
  primaryButtonText: { color: '#fff', fontSize: 15, fontWeight: '600' },

  dangerOutlineButton: {
    height: 44,
    borderRadius: radii.md,
    borderWidth: 1.5,
    borderColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
  },
  dangerOutlineText: { color: colors.dangerText, fontSize: 13.5, fontWeight: '600' },
  linkButtonText: { color: colors.accentText, fontWeight: '600', fontSize: 13, paddingVertical: spacing.xs },

  banner: { borderRadius: radii.sm, padding: spacing.md, marginBottom: spacing.lg },
  bannerText: { fontSize: 12.5, lineHeight: 18 },

  radioOpt: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: 11,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radii.sm,
    backgroundColor: colors.surface,
    marginBottom: spacing.sm,
  },
  radioOptChecked: { borderColor: colors.accent, backgroundColor: colors.accentBg },
  radioDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 2,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioDotChecked: { borderColor: colors.accent },
  radioDotInner: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  radioTitle: { fontSize: 13.5, fontWeight: '600', color: colors.textPrimary },
  radioSubtitle: { fontSize: 11.5, color: colors.textSecondary, marginTop: 1 },

  segmented: {
    flexDirection: 'row',
    gap: spacing.xs,
    backgroundColor: colors.disabledSurface,
    padding: 4,
    borderRadius: radii.sm,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.md,
  },
  segmentBtn: { flex: 1, paddingVertical: 9, borderRadius: 6, alignItems: 'center' },
  segmentBtnActive: { backgroundColor: colors.surface },
  segmentText: { fontSize: 12.5, fontWeight: '600', color: colors.textSecondary },
  segmentTextActive: { color: colors.accentText },
});
