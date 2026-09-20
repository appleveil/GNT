import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import type { NativeStackScreenProps } from '@react-navigation/native-stack';
import type { DealsStackParamList } from '../navigation/types';
import type { Player } from '../types';
import { getPlayers, getCacheAge } from '../api/players';
import { getActiveProfitSplitPlayerIds } from '../db/deals';
import { colors, radii, spacing } from '../theme/tokens';
import { balanceColor, signedNaira } from '../components/ui';

type Props = NativeStackScreenProps<DealsStackParamList, 'DealsHome'>;

export default function DealsHomeScreen({ navigation }: Props) {
  const [players, setPlayers] = useState<Player[]>([]);
  const [activeIds, setActiveIds] = useState<Set<number>>(new Set());
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [stale, setStale] = useState(false);
  const [cacheAge, setCacheAge] = useState<Date | null>(null);
  const [scrolled, setScrolled] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [{ players, stale }, ids, age] = await Promise.all([
      getPlayers(),
      getActiveProfitSplitPlayerIds(),
      getCacheAge(),
    ]);
    setPlayers(players);
    setStale(stale);
    setActiveIds(ids);
    setCacheAge(age);
    setLoading(false);
  }, []);

  // Refresh every time this screen regains focus — e.g. coming back after
  // ending a Profit Split arrangement, so the "active" tag updates.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const filtered = useMemo(
    () => players.filter((p) => !query || p.displayName.toLowerCase().includes(query.toLowerCase())),
    [players, query],
  );

  return (
    <View style={styles.screen}>
      <View style={[styles.stickyHead, scrolled && styles.stickyHeadShadow]}>
        <View style={styles.search}>
          <TextInput
            style={styles.searchInput}
            placeholder="Search players…"
            placeholderTextColor={colors.textTertiary}
            value={query}
            onChangeText={setQuery}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </View>
        {stale ? (
          <Text style={styles.staleNote}>
            Showing saved data{cacheAge ? ` from ${cacheAge.toLocaleString()}` : ''} — couldn't reach the server.
          </Text>
        ) : null}
      </View>

      {loading ? (
        <ActivityIndicator style={{ marginTop: spacing.xl }} color={colors.accent} />
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(p) => String(p.id)}
          contentContainerStyle={styles.list}
          onScroll={(e) => setScrolled(e.nativeEvent.contentOffset.y > 2)}
          scrollEventThrottle={16}
          ListEmptyComponent={<Text style={styles.emptyText}>No players found.</Text>}
          renderItem={({ item }) => (
            <Pressable
              style={styles.row}
              onPress={() => navigation.navigate('DealTypePicker', { player: item })}
            >
              <View style={styles.avatar}>
                <Text style={styles.avatarText}>{initials(item.displayName)}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.name}>{item.displayName}</Text>
                {activeIds.has(item.id) ? <Text style={styles.activeTag}>Profit split active</Text> : null}
              </View>
              <Text style={[styles.balance, { color: balanceColor(item.balance) }]}>{signedNaira(item.balance)}</Text>
            </Pressable>
          )}
        />
      )}
    </View>
  );
}

function initials(name: string): string {
  return name
    .split(' ')
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  stickyHead: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, backgroundColor: colors.bg, zIndex: 1 },
  stickyHeadShadow: {
    shadowColor: '#1C222B',
    shadowOpacity: 0.12,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
  },
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
  staleNote: { fontSize: 11.5, color: colors.warningText, marginTop: spacing.sm },
  list: { paddingHorizontal: spacing.lg, paddingBottom: spacing.xl },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
  },
  avatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.accentBg,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: colors.accentText, fontWeight: '600', fontSize: 14 },
  name: { fontSize: 14.5, fontWeight: '600', color: colors.textPrimary },
  activeTag: { fontSize: 11, color: colors.accentText, fontWeight: '600', marginTop: 1 },
  balance: { fontWeight: '600', fontSize: 13.5 },
  emptyText: { textAlign: 'center', color: colors.textTertiary, marginTop: spacing.xl },
});
