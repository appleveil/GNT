import type { Player } from '../types';

export type DealsStackParamList = {
  DealsHome: undefined;
  DealTypePicker: { player: Player };
  Fixed: { player: Player };
  Transfer: { player: Player };
  ProfitSplit: { player: Player };
};

export type HistoryStackParamList = {
  History: undefined;
  // Looked up fresh from local storage by id — see ProfitSplitDetailScreen —
  // rather than passed through navigation, so it always reflects the
  // latest local state (e.g. an ended-since arrangement).
  ProfitSplitDetail: { arrangementId: string };
};
