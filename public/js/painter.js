import { buildStripBuffersFromVoxels, hexToRgbBytes } from './loader.js';

export function normalizeHex(hex) {
  const clean = String(hex || '#FFFFFF').trim().replace(/^#/, '');
  if (/^[0-9a-fA-F]{6}$/.test(clean)) {
    return `#${clean.toUpperCase()}`;
  }
  return '#FFFFFF';
}

function rgbBytesToHex(r, g, b) {
  const to2 = (v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0');
  return `#${to2(r)}${to2(g)}${to2(b)}`.toUpperCase();
}

function relativeLuminance(rgb) {
  return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2];
}

function computeShadedHex(targetRgb, seedLum, voxelRgb) {
  const voxLum = relativeLuminance(voxelRgb);
  const ratio = voxLum / Math.max(12, seedLum);
  if (Math.abs(ratio - 1.0) < 0.015) {
    return rgbBytesToHex(targetRgb[0], targetRgb[1], targetRgb[2]);
  }
  if (ratio > 1.0) {
    // 基準色より明るいハイライト画素は単純乗算だと色相が飽和しやすいため、白方向へ滑らかに持ち上げる
    const lift = Math.min(0.65, (ratio - 1.0) * 1.45);
    return rgbBytesToHex(
      targetRgb[0] + (255 - targetRgb[0]) * lift,
      targetRgb[1] + (255 - targetRgb[1]) * lift,
      targetRgb[2] + (255 - targetRgb[2]) * lift
    );
  }
  const scale = Math.max(0.52, ratio);
  return rgbBytesToHex(targetRgb[0] * scale, targetRgb[1] * scale, targetRgb[2] * scale);
}

export class VoxelPainter {
  constructor() {
    this.size = { x: 0, y: 0, z: 0 };
    this.grid = new Int16Array(0);
    this.originalGrid = new Int16Array(0);
    this.partGrid = new Int16Array(0);
    this.palette = [];
    this.originalPalette = [];
    this.originalPaletteRgb = [];
    this.parts = [];
    this.hasParts = false;
    this.undoStack = [];
    this.baseAsset = null;
  }

  loadFromAsset(asset) {
    this.baseAsset = asset;
    this.size = { ...asset.size };
    const { x: W, y: H, z: D } = this.size;
    const total = W * H * D;
    this.grid = new Int16Array(total).fill(-1);
    this.partGrid = new Int16Array(total).fill(-1);

    let detectedPartIdx = false;
    for (let i = 0; i < asset.voxels.length; i++) {
      const v = asset.voxels[i];
      const vx = v[0];
      const vy = v[1];
      const vz = v[2];
      const cIdx = v[3];
      const pIdx = v.length >= 5 && Number.isInteger(v[4]) ? v[4] : -1;
      if (vx >= 0 && vx < W && vy >= 0 && vy < H && vz >= 0 && vz < D) {
        const flat = (vy * D + vz) * W + vx;
        this.grid[flat] = cIdx;
        this.partGrid[flat] = pIdx;
        if (pIdx >= 0) detectedPartIdx = true;
      }
    }

    this.originalGrid = new Int16Array(this.grid);
    this.palette = asset.palette.map(normalizeHex);
    this.originalPalette = [...this.palette];
    this.originalPaletteRgb = this.originalPalette.map(hexToRgbBytes);
    this.parts = Array.isArray(asset.parts) && asset.parts.length > 0
      ? asset.parts.map((part, idx) => ({
          ...part,
          partIdx: idx,
          colorIndices: Array.isArray(part.colorIndices) ? [...part.colorIndices] : [],
        }))
      : [];
    this.hasParts = this.parts.length > 0 && detectedPartIdx;
    this.undoStack = [];
    this._liveSlotSession = null;
  }

  getPartSlotCurrentHex(partIdx, origColorIdx) {
    const usePart = this.hasParts && partIdx >= 0;
    const freq = new Map();
    for (let flat = 0; flat < this.grid.length; flat++) {
      const c = this.grid[flat];
      if (c < 0) continue;
      if (this.originalGrid[flat] !== origColorIdx) continue;
      if (usePart && this.partGrid[flat] !== partIdx) continue;
      freq.set(c, (freq.get(c) || 0) + 1);
    }
    if (freq.size === 0) {
      return this.originalPalette[origColorIdx] || null;
    }
    let bestIdx = -1;
    let bestCount = -1;
    for (const [cIdx, cnt] of freq.entries()) {
      if (cnt > bestCount) {
        bestCount = cnt;
        bestIdx = cIdx;
      }
    }
    return this.palette[bestIdx] || this.originalPalette[origColorIdx] || null;
  }

  /**
   * 指定パーツ群（レガシー時はモデル全体）が現在実際に使用しているライブ色一覧をボクセル数降順で返す。
   * 連結塗り・1ドット塗りで生まれた新規色も含めてスウォッチへ即時反映しつつ、元色との差分有無(isEdited)を判定する。
   */
  getLiveColorsForParts(partIndices = []) {
    const filterByPart = this.hasParts && Array.isArray(partIndices) && partIndices.length > 0;
    const partSet = filterByPart ? new Set(partIndices) : null;
    const liveCounts = new Map();
    const origHexSet = new Set();

    for (let flat = 0; flat < this.grid.length; flat++) {
      const cIdx = this.grid[flat];
      if (cIdx < 0) continue;
      if (partSet && !partSet.has(this.partGrid[flat])) continue;

      const liveHex = this.palette[cIdx];
      if (liveHex) {
        liveCounts.set(liveHex, (liveCounts.get(liveHex) || 0) + 1);
      }
      const origIdx = this.originalGrid[flat];
      if (origIdx >= 0 && this.originalPalette[origIdx]) {
        origHexSet.add(this.originalPalette[origIdx]);
      }
    }

    return [...liveCounts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([hex, count]) => ({
        hex,
        count,
        isEdited: !origHexSet.has(hex),
      }));
  }

  beginLiveSlotEdit(partIdx, origColorIdx) {
    const usePart = this.hasParts && partIdx >= 0;
    const region = [];
    for (let flat = 0; flat < this.grid.length; flat++) {
      if (this.grid[flat] < 0) continue;
      if (this.originalGrid[flat] !== origColorIdx) continue;
      if (usePart && this.partGrid[flat] !== partIdx) continue;
      region.push(flat);
    }
    const indices = new Int32Array(region.length);
    const oldIndices = new Int16Array(region.length);
    for (let i = 0; i < region.length; i++) {
      indices[i] = region[i];
      oldIndices[i] = this.grid[region[i]];
    }
    this._liveSlotSession = {
      partIdx,
      origColorIdx,
      indices,
      oldIndices,
      prevPaletteLen: this.palette.length,
      changed: false,
    };
  }

  commitLiveSlotEdit() {
    const sess = this._liveSlotSession;
    this._liveSlotSession = null;
    if (!sess || sess.indices.length === 0) return false;

    let anyDiff = false;
    for (let i = 0; i < sess.indices.length; i++) {
      if (this.grid[sess.indices[i]] !== sess.oldIndices[i]) {
        anyDiff = true;
        break;
      }
    }
    if (!anyDiff) {
      this.palette.length = sess.prevPaletteLen;
      return false;
    }

    this.undoStack.push({
      indices: sess.indices,
      oldIndices: sess.oldIndices,
      prevPaletteLen: sess.prevPaletteLen,
    });
    if (this.undoStack.length > 64) {
      this.undoStack.shift();
    }
    return true;
  }

  /**
   * 部位内の特定オリジナル色スロットだけを直接置換する。
   * カラーホイールドラッグ中は beginLiveSlotEdit/commitLiveSlotEdit と組み合わせて1回の操作を1 Undo に束ねる。
   */
  replacePartColorSlot(partIdx, origColorIdx, hexColor, { liveDrag = false } = {}) {
    const targetHex = normalizeHex(hexColor);
    if (liveDrag && this._liveSlotSession
      && this._liveSlotSession.partIdx === partIdx
      && this._liveSlotSession.origColorIdx === origColorIdx) {
      const sess = this._liveSlotSession;
      if (sess.indices.length === 0) return 0;
      const newIdx = this._getOrAddPaletteIndex(targetHex);
      let changed = 0;
      for (let i = 0; i < sess.indices.length; i++) {
        const flat = sess.indices[i];
        if (this.grid[flat] !== newIdx) {
          this.grid[flat] = newIdx;
          changed++;
        }
      }
      if (changed > 0) sess.changed = true;
      return changed;
    }

    const usePart = this.hasParts && partIdx >= 0;
    const prevPaletteLen = this.palette.length;
    const newIdx = this._getOrAddPaletteIndex(targetHex);
    const region = [];
    for (let flat = 0; flat < this.grid.length; flat++) {
      if (this.grid[flat] < 0) continue;
      if (this.originalGrid[flat] !== origColorIdx) continue;
      if (usePart && this.partGrid[flat] !== partIdx) continue;
      region.push(flat);
    }
    if (region.length === 0) {
      this.palette.length = prevPaletteLen;
      return 0;
    }

    const changedIndices = new Int32Array(region.length);
    const oldIndices = new Int16Array(region.length);
    let actualChanges = 0;
    for (let i = 0; i < region.length; i++) {
      const flat = region[i];
      const oldIdx = this.grid[flat];
      if (oldIdx !== newIdx) {
        changedIndices[actualChanges] = flat;
        oldIndices[actualChanges] = oldIdx;
        this.grid[flat] = newIdx;
        actualChanges++;
      }
    }

    if (actualChanges === 0) {
      this.palette.length = prevPaletteLen;
      return 0;
    }

    this.undoStack.push({
      indices: changedIndices.slice(0, actualChanges),
      oldIndices: oldIndices.slice(0, actualChanges),
      prevPaletteLen,
    });
    if (this.undoStack.length > 64) {
      this.undoStack.shift();
    }
    return actualChanges;
  }

  buildStorageSnapshot() {
    const diffs = [];
    for (let flat = 0; flat < this.grid.length; flat++) {
      const c = this.grid[flat];
      if (c >= 0 && c !== this.originalGrid[flat]) {
        diffs.push([flat, c]);
      }
    }
    return {
      version: 1,
      size: { ...this.size },
      palette: [...this.palette],
      diffs,
      savedAt: Date.now(),
    };
  }

  applyStorageSnapshot(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.palette) || !Array.isArray(snapshot.diffs)) {
      return { ok: false, reason: '保管データの形式が不正です' };
    }
    const s = snapshot.size;
    if (!s || s.x !== this.size.x || s.y !== this.size.y || s.z !== this.size.z) {
      return { ok: false, reason: 'モデル寸法が一致しません' };
    }

    const prevPalette = [...this.palette];
    const prevPaletteLen = this.palette.length;
    const prevGrid = new Int16Array(this.grid);
    const restoredPalette = snapshot.palette.map(normalizeHex);
    const nextGrid = new Int16Array(this.originalGrid);

    for (let i = 0; i < snapshot.diffs.length; i++) {
      const pair = snapshot.diffs[i];
      if (!Array.isArray(pair) || pair.length < 2) continue;
      const flat = pair[0];
      const cIdx = pair[1];
      if (flat >= 0 && flat < nextGrid.length && cIdx >= 0 && cIdx < restoredPalette.length) {
        nextGrid[flat] = cIdx;
      }
    }

    const changedIndices = [];
    const oldIndices = [];
    for (let flat = 0; flat < nextGrid.length; flat++) {
      if (nextGrid[flat] !== prevGrid[flat]) {
        changedIndices.push(flat);
        oldIndices.push(prevGrid[flat]);
      }
    }

    this.palette = restoredPalette;
    this.grid.set(nextGrid);

    if (changedIndices.length > 0) {
      this.undoStack.push({
        indices: Int32Array.from(changedIndices),
        oldIndices: Int16Array.from(oldIndices),
        prevPaletteLen,
        prevPalette,
      });
      if (this.undoStack.length > 64) {
        this.undoStack.shift();
      }
    }
    return { ok: true, changedCount: changedIndices.length };
  }

  importFromJsonObject(data) {
    if (!data || typeof data !== 'object') {
      return { ok: false, reason: 'JSONオブジェクトではありません' };
    }
    const rawSize = data.size || data.dimensions;
    const W = Number(rawSize?.x);
    const H = Number(rawSize?.y);
    const D = Number(rawSize?.z);
    if (!Number.isInteger(W) || !Number.isInteger(H) || !Number.isInteger(D) || W <= 0 || H <= 0 || D <= 0 || W * H * D > 1_000_000) {
      return { ok: false, reason: 'size / dimensions が不正です' };
    }
    if (!Array.isArray(data.palette) || data.palette.length === 0) {
      return { ok: false, reason: 'palette が空または不正です' };
    }
    if (!Array.isArray(data.voxels) || data.voxels.length === 0) {
      return { ok: false, reason: 'voxels が空または不正です' };
    }

    const importedPalette = data.palette.map(normalizeHex);
    const sameSize = W === this.size.x && H === this.size.y && D === this.size.z;

    if (sameSize && this.grid.length === W * H * D) {
      const prevPalette = [...this.palette];
      const prevPaletteLen = this.palette.length;
      const prevGrid = new Int16Array(this.grid);
      const nextGrid = new Int16Array(W * H * D).fill(-1);
      const nextPartGrid = new Int16Array(this.partGrid);
      let hasImportedParts = false;

      for (let i = 0; i < data.voxels.length; i++) {
        const v = data.voxels[i];
        if (!Array.isArray(v) || v.length < 4) continue;
        const vx = v[0];
        const vy = v[1];
        const vz = v[2];
        const cIdx = v[3];
        if (vx < 0 || vx >= W || vy < 0 || vy >= H || vz < 0 || vz >= D) continue;
        if (cIdx < 0 || cIdx >= importedPalette.length) continue;
        const flat = (vy * D + vz) * W + vx;
        nextGrid[flat] = cIdx;
        if (v.length >= 5 && Number.isInteger(v[4])) {
          nextPartGrid[flat] = v[4];
          hasImportedParts = true;
        }
      }

      const changedIndices = [];
      const oldIndices = [];
      for (let flat = 0; flat < nextGrid.length; flat++) {
        if (nextGrid[flat] !== prevGrid[flat]) {
          changedIndices.push(flat);
          oldIndices.push(prevGrid[flat]);
        }
      }

      this.palette = importedPalette;
      this.grid.set(nextGrid);
      if (hasImportedParts && Array.isArray(data.parts) && data.parts.length > 0) {
        this.partGrid.set(nextPartGrid);
        this.parts = data.parts.map((p, idx) => ({
          ...p,
          partIdx: idx,
          colorIndices: Array.isArray(p.colorIndices) ? [...p.colorIndices] : [],
        }));
        this.hasParts = true;
      }

      if (changedIndices.length > 0) {
        this.undoStack.push({
          indices: Int32Array.from(changedIndices),
          oldIndices: Int16Array.from(oldIndices),
          prevPaletteLen,
          prevPalette,
        });
        if (this.undoStack.length > 64) {
          this.undoStack.shift();
        }
      }
      return { ok: true, voxelCount: data.voxels.length, sameSize: true };
    }

    // 寸法が異なるカスタムJSONの場合は新規モデルとして読み込み直す
    const syntheticAsset = {
      ...this.baseAsset,
      isFallback: false,
      name: String(data.name || 'Imported Model'),
      size: { x: W, y: H, z: D },
      palette: importedPalette,
      paletteRgb: importedPalette.map(hexToRgbBytes),
      parts: Array.isArray(data.parts) && data.parts.length > 0 ? data.parts : null,
      voxels: data.voxels,
    };
    this.loadFromAsset(syntheticAsset);
    return { ok: true, voxelCount: data.voxels.length, sameSize: false };
  }

  get canUndo() {
    return this.undoStack.length > 0;
  }

  get undoCount() {
    return this.undoStack.length;
  }

  getVoxelColorHex(x, y, z) {
    const { x: W, y: H, z: D } = this.size;
    if (x < 0 || x >= W || y < 0 || y >= H || z < 0 || z >= D) return null;
    const pIdx = this.grid[(y * D + z) * W + x];
    if (pIdx < 0) return null;
    return this.palette[pIdx] || null;
  }

  getVoxelPartIndex(x, y, z) {
    const { x: W, y: H, z: D } = this.size;
    if (!this.hasParts || x < 0 || x >= W || y < 0 || y >= H || z < 0 || z >= D) return -1;
    return this.partGrid[(y * D + z) * W + x];
  }

  getPartMeta(partIdx) {
    if (!this.hasParts || partIdx < 0 || partIdx >= this.parts.length) return null;
    return this.parts[partIdx];
  }

  /**
   * 描画時にレンダラが確定させた投影・スナップ・断面カット座標系をそのまま逆変換し、
   * 3D Amanatides & Woo DDA で可視ボクセルを厳密に特定することで Mode 1/2/3 および全DPRでズレないピッキングを実現する。
   */
  raycastClientPoint(clientX, clientY, canvas, metrics) {
    if (!metrics || !this.baseAsset) return null;
    const { x: W, y: H, z: D } = this.size;
    if (W <= 0 || H <= 0 || D <= 0) return null;

    const rect = canvas.getBoundingClientRect();
    const dprX = metrics.canvasW / Math.max(1, rect.width);
    const dprY = metrics.canvasH / Math.max(1, rect.height);
    const glX = (clientX - rect.left) * dprX;
    // WebGLの原点（左下）とDOMのclientY原点（左上）の上下反転を補正する
    const glY = metrics.canvasH - (clientY - rect.top) * dprY;

    const fboX = (glX - metrics.blitOriginX) / metrics.pixelScale;
    const fboY = (glY - metrics.blitOriginY) / metrics.pixelScale;
    if (fboX < 0 || fboY < 0 || fboX >= metrics.renderW || fboY >= metrics.renderH) {
      return null;
    }

    const uFrac = fboX / metrics.renderW;
    const vFrac = fboY / metrics.renderH;
    const viewX = (-metrics.orthoW * 0.5 + metrics.frustumShiftX) + uFrac * metrics.orthoW;
    const viewY = (-metrics.orthoH * 0.5 + metrics.frustumShiftY) + vFrac * metrics.orthoH;

    const { right, up, back } = metrics.basis;
    const dist = metrics.distance;
    const oxW = metrics.target[0] + right[0] * viewX + up[0] * viewY + back[0] * dist;
    const oyW = metrics.target[1] + right[1] * viewX + up[1] * viewY + back[1] * dist;
    const ozW = metrics.target[2] + right[2] * viewX + up[2] * viewY + back[2] * dist;

    const invExplode = 1.0 / Math.max(1.0, metrics.explode || 1.0);
    const ox = oxW * invExplode + W * 0.5;
    const oy = oyW * invExplode + H * 0.5;
    const oz = ozW * invExplode + D * 0.5;

    const dx = -back[0];
    const dy = -back[1];
    const dz = -back[2];

    const slabAxis = (o, d, minB, maxB) => {
      if (Math.abs(d) < 1e-8) {
        return o >= minB && o <= maxB ? [-Infinity, Infinity] : [Infinity, -Infinity];
      }
      const t0 = (minB - o) / d;
      const t1 = (maxB - o) / d;
      return t0 < t1 ? [t0, t1] : [t1, t0];
    };

    const [tx0, tx1] = slabAxis(ox, dx, 0, W);
    const [ty0, ty1] = slabAxis(oy, dy, 0, H);
    const [tz0, tz1] = slabAxis(oz, dz, 0, D);
    const tEnter = Math.max(tx0, ty0, tz0);
    const tExit = Math.min(tx1, ty1, tz1);
    if (tEnter > tExit || tExit < 0) return null;

    const tStart = Math.max(0, tEnter) + 1e-4;
    const sx = ox + dx * tStart;
    const sy = oy + dy * tStart;
    const sz = oz + dz * tStart;

    let vx = Math.min(W - 1, Math.max(0, Math.floor(sx)));
    let vy = Math.min(H - 1, Math.max(0, Math.floor(sy)));
    let vz = Math.min(D - 1, Math.max(0, Math.floor(sz)));

    const stepX = dx >= 0 ? 1 : -1;
    const stepY = dy >= 0 ? 1 : -1;
    const stepZ = dz >= 0 ? 1 : -1;

    const tDeltaX = Math.abs(dx) > 1e-8 ? Math.abs(1 / dx) : Infinity;
    const tDeltaY = Math.abs(dy) > 1e-8 ? Math.abs(1 / dy) : Infinity;
    const tDeltaZ = Math.abs(dz) > 1e-8 ? Math.abs(1 / dz) : Infinity;

    let tMaxX = Math.abs(dx) > 1e-8
      ? ((dx > 0 ? vx + 1 - sx : sx - vx) * tDeltaX)
      : Infinity;
    let tMaxY = Math.abs(dy) > 1e-8
      ? ((dy > 0 ? vy + 1 - sy : sy - vy) * tDeltaY)
      : Infinity;
    let tMaxZ = Math.abs(dz) > 1e-8
      ? ((dz > 0 ? vz + 1 - sz : sz - vz) * tDeltaZ)
      : Infinity;

    const isCutVisible = (x, y, z) => {
      const coord = metrics.cutAxisInt === 0 ? x : metrics.cutAxisInt === 1 ? y : z;
      if (metrics.cutFrontPositive === 1) {
        return coord < metrics.cutVisibleSlices;
      }
      return coord >= (metrics.cutTotal - metrics.cutVisibleSlices);
    };

    const maxSteps = W + H + D + 8;
    for (let i = 0; i < maxSteps; i++) {
      if (vx < 0 || vx >= W || vy < 0 || vy >= H || vz < 0 || vz >= D) break;
      if (isCutVisible(vx, vy, vz)) {
        const flat = (vy * D + vz) * W + vx;
        const cIdx = this.grid[flat];
        if (cIdx >= 0) {
          return {
            x: vx,
            y: vy,
            z: vz,
            paletteIndex: cIdx,
            partIdx: this.hasParts ? this.partGrid[flat] : -1,
            hex: this.palette[cIdx],
          };
        }
      }

      if (tMaxX <= tMaxY && tMaxX <= tMaxZ) {
        vx += stepX;
        tMaxX += tDeltaX;
      } else if (tMaxY <= tMaxZ) {
        vy += stepY;
        tMaxY += tDeltaY;
      } else {
        vz += stepZ;
        tMaxZ += tDeltaZ;
      }
    }

    return null;
  }

  _getOrAddPaletteIndex(hexColor) {
    const targetHex = normalizeHex(hexColor);
    const existing = this.palette.indexOf(targetHex);
    if (existing >= 0) return existing;
    this.palette.push(targetHex);
    return this.palette.length - 1;
  }

  paintPart(partIdx, hexColor, preserveShading = true) {
    if (!this.hasParts || partIdx < 0 || partIdx >= this.parts.length) return 0;

    const targetHex = normalizeHex(hexColor);
    const targetRgb = hexToRgbBytes(targetHex);
    const prevPaletteLen = this.palette.length;

    const regionIndices = [];
    const origFreq = new Map();
    for (let flat = 0; flat < this.grid.length; flat++) {
      if (this.grid[flat] >= 0 && this.partGrid[flat] === partIdx) {
        regionIndices.push(flat);
        const origIdx = this.originalGrid[flat];
        origFreq.set(origIdx, (origFreq.get(origIdx) || 0) + 1);
      }
    }
    if (regionIndices.length === 0) return 0;

    // パーツ内の最頻原色を基準輝度にすることで、影ピクセルをクリックしても全体が白飛びせず、
    // さらに複数回の色変えでも原画由来の陰影階調が劣化しないようにする
    let dominantOrigIdx = -1;
    let maxFreq = -1;
    for (const [origIdx, freq] of origFreq.entries()) {
      if (freq > maxFreq) {
        maxFreq = freq;
        dominantOrigIdx = origIdx;
      }
    }
    const dominantRgb = this.originalPaletteRgb[dominantOrigIdx] || [255, 255, 255];
    const refLum = relativeLuminance(dominantRgb);

    const mappedOrigCache = new Map();
    const resolveForFlat = (flat) => {
      if (!preserveShading) {
        return this._getOrAddPaletteIndex(targetHex);
      }
      const origIdx = this.originalGrid[flat];
      if (mappedOrigCache.has(origIdx)) return mappedOrigCache.get(origIdx);
      const outHex = origIdx === dominantOrigIdx
        ? targetHex
        : computeShadedHex(targetRgb, refLum, this.originalPaletteRgb[origIdx] || dominantRgb);
      const newIdx = this._getOrAddPaletteIndex(outHex);
      mappedOrigCache.set(origIdx, newIdx);
      return newIdx;
    };

    const changedIndices = new Int32Array(regionIndices.length);
    const oldIndices = new Int16Array(regionIndices.length);
    let actualChanges = 0;

    for (let i = 0; i < regionIndices.length; i++) {
      const flat = regionIndices[i];
      const oldIdx = this.grid[flat];
      const newIdx = resolveForFlat(flat);
      if (newIdx !== oldIdx) {
        changedIndices[actualChanges] = flat;
        oldIndices[actualChanges] = oldIdx;
        this.grid[flat] = newIdx;
        actualChanges++;
      }
    }

    if (actualChanges === 0) {
      this.palette.length = prevPaletteLen;
      return 0;
    }

    this.undoStack.push({
      indices: changedIndices.slice(0, actualChanges),
      oldIndices: oldIndices.slice(0, actualChanges),
      prevPaletteLen,
    });
    if (this.undoStack.length > 64) {
      this.undoStack.shift();
    }
    return actualChanges;
  }

  paintAt(x, y, z, hexColor, scopeOrConnected = 'part', tolerance = 24, preserveShading = true) {
    const { x: W, y: H, z: D } = this.size;
    if (x < 0 || x >= W || y < 0 || y >= H || z < 0 || z >= D) return 0;

    const startFlat = (y * D + z) * W + x;
    const seedIdx = this.grid[startFlat];
    if (seedIdx < 0) return 0;

    let scope = 'connected';
    if (typeof scopeOrConnected === 'string') {
      scope = scopeOrConnected;
    } else {
      scope = scopeOrConnected ? 'connected' : 'single';
    }

    if (scope === 'part') {
      const partIdx = this.partGrid[startFlat];
      if (this.hasParts && partIdx >= 0) {
        return this.paintPart(partIdx, hexColor, preserveShading);
      }
      scope = 'connected';
    }

    const connected = scope === 'connected';
    const targetHex = normalizeHex(hexColor);
    const seedHex = this.palette[seedIdx] || '#FFFFFF';
    if (targetHex === seedHex) return 0;

    const prevPaletteLen = this.palette.length;
    const oldPaletteRgb = this.palette.map(hexToRgbBytes);
    const seedRgb = oldPaletteRgb[seedIdx] || [255, 255, 255];
    const seedLum = relativeLuminance(seedRgb);
    const targetRgb = hexToRgbBytes(targetHex);
    const tolSq = Math.max(0, Number(tolerance) || 0) ** 2;

    const matchedPalette = new Uint8Array(this.palette.length);
    for (let i = 0; i < oldPaletteRgb.length; i++) {
      if (tolSq <= 0) {
        matchedPalette[i] = i === seedIdx ? 1 : 0;
      } else {
        const rgb = oldPaletteRgb[i];
        const dr = rgb[0] - seedRgb[0];
        const dg = rgb[1] - seedRgb[1];
        const db = rgb[2] - seedRgb[2];
        matchedPalette[i] = (dr * dr + dg * dg + db * db <= tolSq) ? 1 : 0;
      }
    }

    const regionIndices = [];
    if (!connected) {
      regionIndices.push(startFlat);
    } else {
      // 6近傍のみだと縦ロールやスカートの斜め階段境界で塗りが途切れるため、26近傍（斜め隣接込み）の反復DFSで連結領域を拾う
      const visited = new Uint8Array(W * H * D);
      const stack = [startFlat];
      visited[startFlat] = 1;
      regionIndices.push(startFlat);

      const sliceStride = D * W;
      while (stack.length > 0) {
        const cur = stack.pop();
        const cy = Math.floor(cur / sliceStride);
        const rem = cur - cy * sliceStride;
        const cz = Math.floor(rem / W);
        const cx = rem - cz * W;

        for (let dy = -1; dy <= 1; dy++) {
          const ny = cy + dy;
          if (ny < 0 || ny >= H) continue;
          const yBase = ny * sliceStride;
          for (let dz = -1; dz <= 1; dz++) {
            const nz = cz + dz;
            if (nz < 0 || nz >= D) continue;
            const zBase = yBase + nz * W;
            for (let dx = -1; dx <= 1; dx++) {
              if (dx === 0 && dy === 0 && dz === 0) continue;
              const nx = cx + dx;
              if (nx < 0 || nx >= W) continue;
              const nFlat = zBase + nx;
              if (visited[nFlat]) continue;
              const nColor = this.grid[nFlat];
              if (nColor >= 0 && matchedPalette[nColor] === 1) {
                visited[nFlat] = 1;
                regionIndices.push(nFlat);
                stack.push(nFlat);
              }
            }
          }
        }
      }
    }

    const mappedIdxCache = new Map();
    const resolveNewIdx = (oldIdx) => {
      if (mappedIdxCache.has(oldIdx)) return mappedIdxCache.get(oldIdx);
      let outHex = targetHex;
      if (preserveShading && tolSq > 0 && oldIdx !== seedIdx) {
        outHex = computeShadedHex(targetRgb, seedLum, oldPaletteRgb[oldIdx] || seedRgb);
      }
      const newIdx = this._getOrAddPaletteIndex(outHex);
      mappedIdxCache.set(oldIdx, newIdx);
      return newIdx;
    };

    const changedIndices = new Int32Array(regionIndices.length);
    const oldIndices = new Int16Array(regionIndices.length);
    let actualChanges = 0;

    for (let i = 0; i < regionIndices.length; i++) {
      const flat = regionIndices[i];
      const oldIdx = this.grid[flat];
      const newIdx = resolveNewIdx(oldIdx);
      if (newIdx !== oldIdx) {
        changedIndices[actualChanges] = flat;
        oldIndices[actualChanges] = oldIdx;
        this.grid[flat] = newIdx;
        actualChanges++;
      }
    }

    if (actualChanges === 0) {
      this.palette.length = prevPaletteLen;
      return 0;
    }

    // 許容範囲ありの塗り直しでは複数パレット番号が同時に書き換わるため、ボクセル単位で旧色番号を保持して完全復元を保証する
    this.undoStack.push({
      indices: changedIndices.slice(0, actualChanges),
      oldIndices: oldIndices.slice(0, actualChanges),
      prevPaletteLen,
    });
    if (this.undoStack.length > 64) {
      this.undoStack.shift();
    }

    return actualChanges;
  }

  undo() {
    if (this.undoStack.length === 0) return false;
    const entry = this.undoStack.pop();
    const { indices, oldIndices, prevPaletteLen, prevPalette } = entry;
    for (let i = 0; i < indices.length; i++) {
      this.grid[indices[i]] = oldIndices[i];
    }
    if (prevPalette) {
      this.palette = [...prevPalette];
    } else {
      this.palette.length = prevPaletteLen;
    }
    return true;
  }

  reset() {
    if (this.originalGrid.length === 0) return false;
    this.grid.set(this.originalGrid);
    this.palette = [...this.originalPalette];
    this.undoStack = [];
    return true;
  }

  _collectVoxels() {
    const { x: W, y: H, z: D } = this.size;
    const voxels = [];
    for (let y = 0; y < H; y++) {
      for (let z = 0; z < D; z++) {
        const rowBase = (y * D + z) * W;
        for (let x = 0; x < W; x++) {
          const flat = rowBase + x;
          const c = this.grid[flat];
          if (c >= 0) {
            if (this.hasParts) {
              voxels.push([x, y, z, c, this.partGrid[flat]]);
            } else {
              voxels.push([x, y, z, c]);
            }
          }
        }
      }
    }
    return voxels;
  }

  buildUpdatedAsset() {
    const voxels = this._collectVoxels();
    const paletteRgb = this.palette.map(hexToRgbBytes);
    const strips = buildStripBuffersFromVoxels(this.size, paletteRgb, voxels);

    return {
      ...this.baseAsset,
      palette: [...this.palette],
      paletteRgb,
      parts: this.hasParts ? this.baseAsset.parts : null,
      voxels,
      strips: {
        y: { ...strips.y, image: null },
        z: { ...strips.z, image: null },
        x: { ...strips.x, image: null },
      },
      isEdited: true,
    };
  }

  buildExportJsonString() {
    const { x: W, y: H, z: D } = this.size;
    const voxels = this._collectVoxels();

    const payload = {
      name: this.baseAsset?.name || 'Character 2',
      size: { x: W, y: H, z: D },
      palette: [...this.palette],
      ...(this.hasParts ? { parts: this.baseAsset.parts } : {}),
      voxels,
      slices: {
        y: { file: 'slices_y.png', count: H, sliceWidth: W, sliceHeight: D },
        z: { file: 'slices_z.png', count: D, sliceWidth: W, sliceHeight: H },
        x: { file: 'slices_x.png', count: W, sliceWidth: D, sliceHeight: H },
      },
      referenceViews: this.baseAsset?.referenceViews || {
        front: 'ref_front.png',
        side: 'ref_side.png',
      },
    };
    return JSON.stringify(payload);
  }
}
