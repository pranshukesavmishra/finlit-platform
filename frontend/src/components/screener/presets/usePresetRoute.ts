// The prebuilt screen in the address: which screen is open and which of its options are on. Choosing, toggling and clearing push history entries, so back and forward work.
import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { orderGroups, presetParams, readPresetUrl, resolveChips, usePresetList, type Preset, type PresetGroup, type PresetTab } from "../../../lib/presets";

export function usePresetRoute(tab: PresetTab = "advanced") {
  const [params, setParams] = useSearchParams();
  const url = useMemo(() => readPresetUrl(params), [params.toString()]);   // eslint-disable-line react-hooks/exhaustive-deps
  const list = usePresetList(true, tab);
  const groups: PresetGroup[] = useMemo(() => orderGroups(list.data?.groups ?? []), [list.data]);
  const preset: Preset | null = useMemo(() => groups.flatMap((g) => g.presets).find((p) => p.id === url.preset) ?? null, [groups, url.preset]);
  const chips = useMemo(() => resolveChips(url, preset), [url, preset]);
  const choose = (id: string) => setParams((prev) => presetParams(prev, id, null, null));
  const setChips = (next: string[]) => setParams((prev) => presetParams(prev, url.preset, next, preset));
  const toggleChip = (id: string) => setChips(chips.includes(id) ? chips.filter((c) => c !== id) : [...chips, id]);
  const clear = () => setParams((prev) => presetParams(prev, null, null, null));
  return { tab, id: url.preset, preset, chips, groups, list, choose, toggleChip, clear };
}
export type PresetRoute = ReturnType<typeof usePresetRoute>;
