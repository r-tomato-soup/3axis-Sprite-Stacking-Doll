export function hexToRgbBytes(hex) {
  const clean = hex.replace('#', '');
  const num = parseInt(clean, 16);
  return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
}

/**
 * ストリップPNGの欠損時・ペイント編集直後・モッズ合成時・開発用プレースホルダー表示時に、
 * @sculptor との共有コントラクトと完全に一致する3軸ストリップ画素列をメモリ上で合成する。
 */
export function buildStripBuffersFromVoxels(size, paletteRgb, voxels) {
  const { x: W, y: H, z: D } = size;

  const yWidth = H * W;
  const yHeight = D;
  const yPixels = new Uint8Array(yWidth * yHeight * 4);

  const zWidth = D * W;
  const zHeight = H;
  const zPixels = new Uint8Array(zWidth * zHeight * 4);

  const xWidth = W * D;
  const xHeight = H;
  const xPixels = new Uint8Array(xWidth * xHeight * 4);

  for (let i = 0; i < voxels.length; i++) {
    const [vx, vy, vz, pIdx] = voxels[i];
    if (vx < 0 || vx >= W || vy < 0 || vy >= H || vz < 0 || vz >= D) continue;
    const rgb = paletteRgb[pIdx] || [255, 255, 255];

    const yIdx = (vz * yWidth + (vy * W + vx)) * 4;
    yPixels[yIdx] = rgb[0];
    yPixels[yIdx + 1] = rgb[1];
    yPixels[yIdx + 2] = rgb[2];
    yPixels[yIdx + 3] = 255;

    const pyZ = H - 1 - vy;
    const zIdx = (pyZ * zWidth + (vz * W + vx)) * 4;
    zPixels[zIdx] = rgb[0];
    zPixels[zIdx + 1] = rgb[1];
    zPixels[zIdx + 2] = rgb[2];
    zPixels[zIdx + 3] = 255;

    const pyX = H - 1 - vy;
    const xIdx = (pyX * xWidth + (vx * D + vz)) * 4;
    xPixels[xIdx] = rgb[0];
    xPixels[xIdx + 1] = rgb[1];
    xPixels[xIdx + 2] = rgb[2];
    xPixels[xIdx + 3] = 255;
  }

  return {
    y: { width: yWidth, height: yHeight, sliceWidth: W, sliceHeight: D, count: H, data: yPixels },
    z: { width: zWidth, height: zHeight, sliceWidth: W, sliceHeight: H, count: D, data: zPixels },
    x: { width: xWidth, height: xHeight, sliceWidth: D, sliceHeight: H, count: W, data: xPixels },
  };
}

export function rgbaBufferToDataUrl(width, height, rgbaBytes) {
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  const ctx = c.getContext('2d');
  const imgData = new ImageData(new Uint8ClampedArray(rgbaBytes.buffer.slice(0)), width, height);
  ctx.putImageData(imgData, 0, 0);
  return c.toDataURL('image/png');
}

function normalizeModsList(rawMods) {
  if (!Array.isArray(rawMods)) return [];
  return rawMods
    .filter((m) => m && typeof m === 'object' && m.id)
    .map((m) => ({
      id: String(m.id),
      label: String(m.label || m.id),
      defaultEnabled: Boolean(m.defaultEnabled),
      offsetWhen: m.offsetWhen && typeof m.offsetWhen === 'object' ? m.offsetWhen : null,
      remove: Array.isArray(m.remove) ? m.remove : [],
      add: Array.isArray(m.add) ? m.add : [],
      group: m.group ? String(m.group) : null,
    }));
}

/**
 * ベースボクセル配列へ有効なモッズ差分を順番に適用し、WebGL描画・ペイント用のボクセル配列と
 * 3軸ストリップバッファを再構築する。他の有効モッズに応じた offsetWhen オフセットも加算する。
 */
export function composeAssetVoxels(asset, activeModIds = null) {
  const size = asset?.size || { x: 0, y: 0, z: 0 };
  const { x: W, y: H, z: D } = size;
  const total = W * H * D;
  const baseVoxels = Array.isArray(asset?.baseVoxels)
    ? asset.baseVoxels
    : (Array.isArray(asset?.voxels) ? asset.voxels : []);
  const mods = Array.isArray(asset?.mods) ? asset.mods : [];
  const paletteRgb = Array.isArray(asset?.basePaletteRgb)
    ? asset.basePaletteRgb
    : (Array.isArray(asset?.paletteRgb) ? asset.paletteRgb : []);

  const activeSet = activeModIds == null
    ? new Set(mods.filter((m) => m.defaultEnabled).map((m) => m.id))
    : new Set(activeModIds);

  const colorGrid = new Int16Array(total).fill(-1);
  const partGrid = new Int16Array(total).fill(-1);
  let hasParts = Array.isArray(asset?.parts) && asset.parts.length > 0;

  for (let i = 0; i < baseVoxels.length; i++) {
    const v = baseVoxels[i];
    if (!Array.isArray(v) || v.length < 4) continue;
    const vx = v[0];
    const vy = v[1];
    const vz = v[2];
    const cIdx = v[3];
    if (vx < 0 || vx >= W || vy < 0 || vy >= H || vz < 0 || vz >= D || cIdx < 0) continue;
    const flat = (vy * D + vz) * W + vx;
    colorGrid[flat] = cIdx;
    if (v.length >= 5 && Number.isInteger(v[4])) {
      partGrid[flat] = v[4];
      if (v[4] >= 0) hasParts = true;
    }
  }

  const appliedModIds = [];
  for (let mIdx = 0; mIdx < mods.length; mIdx++) {
    const mod = mods[mIdx];
    if (!activeSet.has(mod.id)) continue;
    appliedModIds.push(mod.id);

    let dx = 0;
    let dy = 0;
    let dz = 0;
    if (mod.offsetWhen && typeof mod.offsetWhen === 'object') {
      for (const [otherId, off] of Object.entries(mod.offsetWhen)) {
        if (activeSet.has(otherId) && Array.isArray(off)) {
          dx += Number(off[0]) || 0;
          dy += Number(off[1]) || 0;
          dz += Number(off[2]) || 0;
        }
      }
    }

    const removeList = Array.isArray(mod.remove) ? mod.remove : [];
    for (let i = 0; i < removeList.length; i++) {
      const r = removeList[i];
      if (!Array.isArray(r) || r.length < 3) continue;
      const nx = r[0] + dx;
      const ny = r[1] + dy;
      const nz = r[2] + dz;
      if (nx < 0 || nx >= W || ny < 0 || ny >= H || nz < 0 || nz >= D) continue;
      const flat = (ny * D + nz) * W + nx;
      colorGrid[flat] = -1;
      partGrid[flat] = -1;
    }

    const addList = Array.isArray(mod.add) ? mod.add : [];
    for (let i = 0; i < addList.length; i++) {
      const a = addList[i];
      if (!Array.isArray(a) || a.length < 4) continue;
      const nx = a[0] + dx;
      const ny = a[1] + dy;
      const nz = a[2] + dz;
      const cIdx = a[3];
      if (nx < 0 || nx >= W || ny < 0 || ny >= H || nz < 0 || nz >= D || cIdx < 0) continue;
      const flat = (ny * D + nz) * W + nx;
      colorGrid[flat] = cIdx;
      if (a.length >= 5 && Number.isInteger(a[4])) {
        partGrid[flat] = a[4];
        if (a[4] >= 0) hasParts = true;
      } else {
        partGrid[flat] = -1;
      }
    }
  }

  const voxels = [];
  for (let y = 0; y < H; y++) {
    for (let z = 0; z < D; z++) {
      const rowBase = (y * D + z) * W;
      for (let x = 0; x < W; x++) {
        const flat = rowBase + x;
        const c = colorGrid[flat];
        if (c >= 0) {
          if (hasParts) {
            voxels.push([x, y, z, c, partGrid[flat]]);
          } else {
            voxels.push([x, y, z, c]);
          }
        }
      }
    }
  }

  const synthStrips = buildStripBuffersFromVoxels(size, paletteRgb, voxels);
  return {
    voxels,
    activeModIds: appliedModIds,
    strips: {
      y: { ...synthStrips.y, image: null },
      z: { ...synthStrips.z, image: null },
      x: { ...synthStrips.x, image: null },
    },
  };
}

/**
 * assets/model.json が未生成の開発初期段階のみ使用する最小フォールバック。
 * 404画像リクエストによるコンソールエラーを避けるため、ストリップ画像もDataURLで自己完結させる。
 */
export function buildFallbackAsset() {
  const W = 40;
  const H = 50;
  const D = 28;
  const palette = [
    '#6E6460',
    '#F4EFE6',
    '#E5DECF',
    '#FFFFFF',
    '#E6E4EC',
    '#FAF2EC',
    '#8E84A8',
  ];
  const paletteRgb = palette.map(hexToRgbBytes);
  const grid = new Int16Array(W * H * D).fill(-1);
  const setV = (x, y, z, c) => {
    if (x >= 0 && x < W && y >= 0 && y < H && z >= 0 && z < D) {
      grid[(y * D + z) * W + x] = c;
    }
  };

  const cx = 19.5;
  const cz = 14.0;

  for (let y = 1; y <= 10; y++) {
    for (const lx of [16, 17, 22, 23]) {
      for (let z = 13; z <= 15; z++) {
        setV(lx, y, z, y <= 3 ? 3 : 5);
      }
    }
  }
  for (let y = 9; y <= 24; y++) {
    const t = (24 - y) / 15;
    const rx = 3.5 + t * 6.2;
    const rz = 3.0 + t * 4.8;
    for (let x = 8; x < 32; x++) {
      for (let z = 6; z < 23; z++) {
        const d2 = ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2;
        if (d2 <= 1.0) {
          setV(x, y, z, d2 > 0.72 && z < cz ? 4 : 3);
        }
      }
    }
  }
  for (let y = 25; y <= 44; y++) {
    const dy = (y - 34.5) / 9.8;
    for (let x = 8; x < 32; x++) {
      for (let z = 5; z < 23; z++) {
        const dx = (x - cx) / 10.2;
        const dz = (z - cz) / 8.2;
        const r2 = dx * dx + dy * dy + dz * dz;
        if (r2 <= 1.0) {
          const isHair = y >= 34 || z < 15 || Math.abs(x - cx) > 6.8;
          setV(x, y, z, isHair ? 1 : 5);
        }
      }
    }
  }

  const voxels = [];
  for (let y = 0; y < H; y++) {
    for (let z = 0; z < D; z++) {
      for (let x = 0; x < W; x++) {
        const c = grid[(y * D + z) * W + x];
        if (c >= 0) voxels.push([x, y, z, c]);
      }
    }
  }

  const size = { x: W, y: H, z: D };
  const strips = buildStripBuffersFromVoxels(size, paletteRgb, voxels);

  return {
    isFallback: true,
    characterId: 'char2',
    versionId: 'v5',
    name: 'Character 2 (Placeholder)',
    size,
    palette,
    paletteRgb,
    basePalette: [...palette],
    basePaletteRgb: paletteRgb,
    parts: null,
    baseVoxels: voxels,
    mods: [],
    activeModIds: [],
    voxels,
    strips,
    stripUrls: {
      y: rgbaBufferToDataUrl(strips.y.width, strips.y.height, strips.y.data),
      z: rgbaBufferToDataUrl(strips.z.width, strips.z.height, strips.z.data),
      x: rgbaBufferToDataUrl(strips.x.width, strips.x.height, strips.x.data),
    },
  };
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.decoding = 'sync';
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`画像読込失敗: ${url}`));
    img.src = url;
  });
}

function resolveVersionBaseDir(entry) {
  if (!entry) return './assets';
  const raw = String(entry.basePath ?? entry.path ?? entry.dir ?? entry.model ?? '').trim();
  if (!raw || raw === '.' || raw === './' || raw === 'assets' || raw === 'assets/' || raw === './assets' || raw === './assets/') {
    return './assets';
  }
  let cleaned = raw.replace(/\\/g, '/').replace(/\/model\.json$/i, '').replace(/\/+$/, '');
  if (cleaned === '.' || cleaned === '..' || cleaned === '../') {
    return './assets';
  }
  if (cleaned.startsWith('./assets/')) return cleaned;
  if (cleaned.startsWith('assets/')) return `./${cleaned}`;
  if (cleaned.startsWith('versions/')) return `./assets/${cleaned}`;
  if (cleaned.startsWith('./versions/')) return `./assets/${cleaned.slice(2)}`;
  return `./assets/versions/${cleaned.replace(/^\.\//, '')}`;
}

function normalizeVersionItem(item) {
  return {
    id: String(item.id || item.version || 'v5'),
    label: String(item.shortLabel || item.label || item.id || 'v5'),
    fullLabel: String(item.label || item.shortLabel || item.id || 'v5'),
    description: String(item.description || item.title || item.label || ''),
    baseDir: resolveVersionBaseDir(item),
  };
}

export async function loadVersionManifest() {
  const defaultChar2 = {
    id: 'char2',
    label: 'CHARACTER 2',
    shortLabel: 'CHARACTER 2',
    description: 'プラチナブロンド・縦ロールのキャラクター',
    defaultVersion: 'v5',
    refBaseDir: './assets',
    versions: [
      { id: 'v5', label: 'v5 最新', fullLabel: 'v5 最新', description: '最新ビルド', baseDir: './assets' },
    ],
  };

  const fallback = {
    defaultCharacterId: 'char2',
    characters: [defaultChar2],
  };

  try {
    const res = await fetch('./assets/versions/manifest.json', { cache: 'no-store' });
    if (!res.ok) return fallback;
    const raw = await res.json();

    if (Array.isArray(raw.characters) && raw.characters.length > 0) {
      const characters = raw.characters.map((ch) => {
        const versions = Array.isArray(ch.versions) && ch.versions.length > 0
          ? ch.versions.map(normalizeVersionItem)
          : [normalizeVersionItem(ch)];
        const defaultVersion = String(
          ch.defaultVersion || ch.default || versions[versions.length - 1].id
        );
        const defEntry = versions.find((v) => v.id === defaultVersion) || versions[versions.length - 1];
        const refBaseDir = ch.refBasePath
          ? resolveVersionBaseDir({ basePath: ch.refBasePath })
          : defEntry.baseDir;
        return {
          id: String(ch.id || 'char2'),
          label: String(ch.label || ch.name || ch.id || 'CHARACTER 2'),
          shortLabel: String(ch.shortLabel || ch.label || ch.name || ch.id || 'CHARACTER 2'),
          description: String(ch.description || ''),
          defaultVersion,
          refBaseDir,
          versions,
        };
      });
      const defaultCharacterId = String(raw.defaultCharacter || characters[0].id);
      return { defaultCharacterId, characters };
    }

    const list = Array.isArray(raw) ? raw : (raw.versions || []);
    if (!Array.isArray(list) || list.length === 0) return fallback;
    const versions = list.map(normalizeVersionItem);
    const defaultVersion = String(
      raw.defaultVersion || raw.default || raw.latest || versions[versions.length - 1].id
    );
    return {
      defaultCharacterId: 'char2',
      characters: [
        {
          ...defaultChar2,
          defaultVersion,
          versions,
        },
      ],
    };
  } catch {
    return fallback;
  }
}

export async function loadCharacterAsset(versionEntry = null, characterEntry = null) {
  const baseDir = versionEntry?.baseDir || './assets';
  const versionId = versionEntry?.id || 'v5';
  const characterId = characterEntry?.id || 'char2';

  try {
    const res = await fetch(`${baseDir}/model.json`, { cache: 'no-store' });
    if (!res.ok) {
      return buildFallbackAsset();
    }

    const model = await res.json();
    const size = model.size;
    const palette = model.palette || [];
    const paletteRgb = palette.map(hexToRgbBytes);
    const parts = Array.isArray(model.parts) && model.parts.length > 0 ? model.parts : null;
    const baseVoxels = model.voxels || [];
    const mods = normalizeModsList(model.mods);

    const yFile = `${baseDir}/${model.slices?.y?.file || 'slices_y.png'}`;
    const zFile = `${baseDir}/${model.slices?.z?.file || 'slices_z.png'}`;
    const xFile = `${baseDir}/${model.slices?.x?.file || 'slices_x.png'}`;

    const baseAssetMeta = {
      size,
      palette,
      paletteRgb,
      basePalette: [...palette],
      basePaletteRgb: paletteRgb,
      parts,
      baseVoxels,
      mods,
    };

    if (mods.length > 0) {
      const defaultActiveIds = mods.filter((m) => m.defaultEnabled).map((m) => m.id);
      const composed = composeAssetVoxels(baseAssetMeta, defaultActiveIds);
      return {
        isFallback: false,
        characterId,
        versionId,
        name: model.name || characterEntry?.label || 'Character 2',
        ...baseAssetMeta,
        voxels: composed.voxels,
        activeModIds: composed.activeModIds,
        referenceViews: model.referenceViews || null,
        strips: composed.strips,
        stripUrls: {
          y: yFile,
          z: zFile,
          x: xFile,
        },
      };
    }

    // ネットワーク・キャッシュ不整合があっても即座に描画できるよう PNG 実画像とボクセル合成バッファの両方を用意する
    const synthStrips = buildStripBuffersFromVoxels(size, paletteRgb, baseVoxels);
    const [imgY, imgZ, imgX] = await Promise.all([
      loadImage(yFile).catch(() => null),
      loadImage(zFile).catch(() => null),
      loadImage(xFile).catch(() => null),
    ]);

    return {
      isFallback: false,
      characterId,
      versionId,
      name: model.name || characterEntry?.label || 'Character 2',
      ...baseAssetMeta,
      voxels: baseVoxels,
      activeModIds: [],
      referenceViews: model.referenceViews || null,
      strips: {
        y: {
          ...synthStrips.y,
          count: model.slices?.y?.count ?? size.y,
          sliceWidth: model.slices?.y?.sliceWidth ?? size.x,
          sliceHeight: model.slices?.y?.sliceHeight ?? size.z,
          image: imgY,
        },
        z: {
          ...synthStrips.z,
          count: model.slices?.z?.count ?? size.z,
          sliceWidth: model.slices?.z?.sliceWidth ?? size.x,
          sliceHeight: model.slices?.z?.sliceHeight ?? size.y,
          image: imgZ,
        },
        x: {
          ...synthStrips.x,
          count: model.slices?.x?.count ?? size.x,
          sliceWidth: model.slices?.x?.sliceWidth ?? size.z,
          sliceHeight: model.slices?.x?.sliceHeight ?? size.y,
          image: imgX,
        },
      },
      stripUrls: {
        y: imgY ? yFile : rgbaBufferToDataUrl(synthStrips.y.width, synthStrips.y.height, synthStrips.y.data),
        z: imgZ ? zFile : rgbaBufferToDataUrl(synthStrips.z.width, synthStrips.z.height, synthStrips.z.data),
        x: imgX ? xFile : rgbaBufferToDataUrl(synthStrips.x.width, synthStrips.x.height, synthStrips.x.data),
      },
    };
  } catch {
    return buildFallbackAsset();
  }
}
