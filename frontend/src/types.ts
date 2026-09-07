export type ModeId = "priority" | "max" | "weapons";

export interface PriorityStat {
  key: string;
  label: string;
}

export interface ClassesResponse {
  classes: string[];
  default_trio: string[];
  priority_stats: PriorityStat[];
  planner_slots: string[];
  modes: { id: ModeId; label: string }[];
  haste_note: string;
}

export interface ItemStats {
  [k: string]: number;
}

export interface RankedItem {
  name: string;
  itemID?: number | string;
  slot?: string;
  score: number;
  pval?: number;
  why?: string;
  zone?: string;
  drops_mobs?: string;
  classes?: string[];
  classes_str?: string;
  bis_for?: string[];
  bis_overlap?: number;
  ratio_plus0?: number | null;
  ratio_plus10?: number | null;
  url?: string;
  haste?: number;
  is_weapon?: boolean;
  level?: number;
  effect?: string;
  planner_slots?: string[];
  stats_plus0?: ItemStats;
  stats_plus10?: ItemStats;
}

export interface ItemsResponse {
  classes: string[];
  mode: ModeId;
  stat: string | null;
  upgrade: number;
  require_all: boolean;
  pool_size: number;
  by_slot: Record<string, RankedItem[]>;
  recommended?: Record<string, RankedItem | null>;
  recommended_haste_items?: { slot: string; name: string; haste: number }[];
  recommended_haste_ok?: boolean;
}

export interface RaceInfo {
  id: string;
  name: string;
  abbrev: string;
  bases: ItemStats;
}

export interface RacesResponse {
  source: { url: string; title: string; fetched: string; note: string };
  bases_available: boolean;
  races: RaceInfo[];
  note: string;
}

export interface SimulateResponse {
  race?: string;
  race_bases: ItemStats;
  race_note: string;
  equipped: Record<string, RankedItem>;
  totals: ItemStats;
  haste_applied: number;
  haste_pieces: { slot: string; name: string; haste: number }[];
  haste_warning: string | null;
  upgrade: number;
}
