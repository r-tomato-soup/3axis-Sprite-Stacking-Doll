const CUSTOM_STORAGE_KEY = 'char2_viewer_custom_colors_v1';
const PART_CUSTOM_STORAGE_KEY = 'char2_viewer_part_custom_colors_v2';
const SAVED_PAINT_STORAGE_KEY = 'char2_viewer_saved_paint_v1';

const DEFAULT_ACCENT_LABELS = {
  '#F48FB1': '桜ピンク',
};

const CHARACTER_PART_GROUPS = {
  char2: [
    { id: 'hair', label: '髪', partIds: ['hair'] },
    { id: 'face', label: '顔', partIds: ['skin', 'eyes'] },
    { id: 'outfit', label: '服', partIds: ['outfit', 'ribbon', 'shoes'] },
  ],
  bunny: [
    { id: 'body_ears', label: '体・耳', partIds: ['body', 'ears'] },
    { id: 'face', label: '顔', partIds: ['face'] },
    { id: 'ribbon', label: 'リボン', partIds: ['ribbon', 'frill'] },
  ],
};

function sanitizeColorList(rawList) {
  if (!Array.isArray(rawList)) return [];
  return rawList
    .filter((item) => item && typeof item.hex === 'string' && /^#[0-9A-Fa-f]{6}$/.test(item.hex))
    .map((item) => ({
      name: String(item.name || 'カスタム色'),
      hex: item.hex.toUpperCase(),
    }));
}

export function loadCustomColors() {
  try {
    const raw = localStorage.getItem(CUSTOM_STORAGE_KEY);
    if (!raw) return [];
    return sanitizeColorList(JSON.parse(raw));
  } catch {
    // プライベートブラウズ等で localStorage が例外を投げてもパレット機能を停止させない
    return [];
  }
}

export function saveCustomColors(colors) {
  try {
    localStorage.setItem(CUSTOM_STORAGE_KEY, JSON.stringify(colors));
  } catch {
    // ストレージ容量上限や無効化環境ではメモリ保持のみへフォールバックする
  }
}

export function loadPartCustomColors() {
  try {
    const raw = localStorage.getItem(PART_CUSTOM_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    const clean = {};
    for (const [key, list] of Object.entries(parsed)) {
      const sanitized = sanitizeColorList(list);
      if (sanitized.length > 0) {
        clean[key] = sanitized;
      }
    }
    return clean;
  } catch {
    return {};
  }
}

export function savePartCustomColors(map) {
  try {
    localStorage.setItem(PART_CUSTOM_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // ストレージ制限環境ではメモリ保持のみへフォールバックする
  }
}

export function loadSavedPaintMap() {
  try {
    const raw = localStorage.getItem(SAVED_PAINT_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return parsed;
  } catch {
    return {};
  }
}

export function saveSavedPaintState(storageKey, snapshot) {
  try {
    const all = loadSavedPaintMap();
    all[storageKey] = snapshot;
    localStorage.setItem(SAVED_PAINT_STORAGE_KEY, JSON.stringify(all));
    return true;
  } catch {
    return false;
  }
}

export function getSavedPaintState(storageKey) {
  const all = loadSavedPaintMap();
  return all[storageKey] || null;
}

function derivePartColorIndices(asset, partIdx) {
  const counts = new Map();
  const voxels = asset?.voxels || [];
  for (let i = 0; i < voxels.length; i++) {
    const v = voxels[i];
    if (v.length >= 5 && v[4] === partIdx) {
      counts.set(v[3], (counts.get(v[3]) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([cIdx]) => cIdx);
}

/**
 * モデルのパーツ配列をUI表示用の3グループ＋カスタム（計4タブ1行）へ集約する。
 * model.json側の粒度は維持したまま表示カテゴリだけを統合し、過去版(v1..v3)では「元色＋カスタム」へフォールバックする。
 */
export function buildCategoriesForAsset(
  asset,
  originalPalette = [],
  partCustomMap = {},
  globalCustomColors = [],
  liveColorsResolver = null
) {
  const charId = asset?.characterId || 'char2';
  const normPalette = originalPalette.map((h) => String(h || '#FFFFFF').toUpperCase());
  const categories = [];

  if (asset && Array.isArray(asset.parts) && asset.parts.length > 0) {
    const partById = new Map();
    asset.parts.forEach((part, partIdx) => {
      partById.set(String(part.id || `part_${partIdx}`), { part, partIdx });
    });

    const presetGroups = CHARACTER_PART_GROUPS[charId] || null;
    const groups = presetGroups
      ? presetGroups.filter((g) => g.partIds.some((pid) => partById.has(pid)))
      : asset.parts.map((part, idx) => ({
          id: String(part.id || `part_${idx}`),
          label: String(part.label || part.id || `部位${idx + 1}`),
          partIds: [String(part.id || `part_${idx}`)],
        }));

    groups.forEach((group) => {
      const storageKey = `${charId}:${group.id}`;
      const memberPartIndices = [];

      group.partIds.forEach((pid) => {
        const entry = partById.get(pid);
        if (entry) memberPartIndices.push(entry.partIdx);
      });

      let originalItems = [];
      const liveList = liveColorsResolver ? liveColorsResolver(memberPartIndices) : null;
      if (Array.isArray(liveList) && liveList.length > 0) {
        originalItems = liveList.map((entry, idx) => ({
          name: `${group.label} #${idx + 1}`,
          hex: entry.hex.toUpperCase(),
          isOriginal: true,
          isEdited: Boolean(entry.isEdited),
        }));
      } else {
        const seenHex = new Set();
        group.partIds.forEach((pid) => {
          const entry = partById.get(pid);
          if (!entry) return;
          const { part, partIdx } = entry;
          const rawIndices = Array.isArray(part.colorIndices) && part.colorIndices.length > 0
            ? part.colorIndices
            : derivePartColorIndices(asset, partIdx);

          rawIndices.forEach((cIdx) => {
            const hex = normPalette[cIdx];
            if (!hex || seenHex.has(hex)) return;
            seenHex.add(hex);
            originalItems.push({
              name: `${part.label || group.label} #${originalItems.length + 1}`,
              hex,
              colorIdx: cIdx,
              partIdx,
              isOriginal: true,
              isEdited: false,
            });
          });
        });
      }

      const customItems = (partCustomMap[storageKey] || []).map((c) => ({
        name: c.name,
        hex: c.hex.toUpperCase(),
        isOriginal: false,
        isEdited: false,
      }));

      categories.push({
        id: group.id,
        label: group.label,
        partIdx: memberPartIndices[0] ?? -1,
        partIndices: memberPartIndices,
        storageKey,
        isPart: memberPartIndices.length > 0,
        isCustomTab: false,
        originalItems,
        customItems,
        items: [...originalItems, ...customItems],
      });
    });
  } else {
    const storageKey = `${charId}:model`;
    const liveList = liveColorsResolver ? liveColorsResolver([]) : null;
    const originalItems = (Array.isArray(liveList) && liveList.length > 0)
      ? liveList.map((entry, idx) => ({
          name: `モデル色 #${idx + 1}`,
          hex: entry.hex.toUpperCase(),
          isOriginal: true,
          isEdited: Boolean(entry.isEdited),
        }))
      : normPalette.map((hex, idx) => ({
          name: `元色 #${idx + 1}`,
          hex,
          colorIdx: idx,
          partIdx: -1,
          isOriginal: true,
          isEdited: false,
        }));
    const customItems = (partCustomMap[storageKey] || []).map((c) => ({
      name: c.name,
      hex: c.hex.toUpperCase(),
      isOriginal: false,
      isEdited: false,
    }));
    categories.push({
      id: 'model',
      label: '元色',
      partIdx: -1,
      partIndices: [],
      storageKey,
      isPart: false,
      isCustomTab: false,
      originalItems,
      customItems,
      items: [...originalItems, ...customItems],
    });
  }

  const globalItems = globalCustomColors.map((c) => ({
    name: c.name,
    hex: c.hex.toUpperCase(),
    isOriginal: false,
  }));
  categories.push({
    id: 'custom',
    label: 'カスタム',
    partIdx: -1,
    partIndices: [],
    storageKey: 'custom',
    isPart: false,
    isCustomTab: true,
    originalItems: [],
    customItems: globalItems,
    items: globalItems,
  });

  return categories;
}

export function findColorLabel(hex, categories = [], originalPalette = []) {
  const upper = String(hex || '').toUpperCase();
  for (const cat of categories) {
    if (cat.isCustomTab) continue;
    const origHit = cat.originalItems.find((c) => c.hex === upper);
    if (origHit) return origHit.name;
  }
  for (const cat of categories) {
    const customHit = cat.customItems.find((c) => c.hex === upper);
    if (customHit) return customHit.name;
  }
  if (DEFAULT_ACCENT_LABELS[upper]) return DEFAULT_ACCENT_LABELS[upper];
  const modelIdx = originalPalette.findIndex((h) => String(h).toUpperCase() === upper);
  if (modelIdx >= 0) return `元色 #${modelIdx + 1}`;
  return 'カスタム色';
}
