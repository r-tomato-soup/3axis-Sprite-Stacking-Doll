import { CAMERA_PRESETS, OrbitCamera } from './camera.js';
import { loadCharacterAsset, loadVersionManifest, rgbaBufferToDataUrl } from './loader.js';
import { normalizeHex, VoxelPainter } from './painter.js';
import {
  buildCategoriesForAsset,
  findColorLabel,
  getSavedPaintState,
  loadCustomColors,
  loadPartCustomColors,
  saveCustomColors,
  savePartCustomColors,
  saveSavedPaintState,
} from './palettes.js';
import { Pseudo3DRenderer } from './renderer.js';

const state = {
  mode: 'tri',
  classicExtrude: false,
  shading: 35,
  outline: true,
  outlineWidth: 1.5,
  pixelSnapSubdiv: 0,
  explode: 1.0,
  cutaway: 0,
  cutAxis: 'auto',
  bg: 'dark',
  showGrid: false,
  stripZoom: 2,
  characterId: 'char2',
  versionId: 'v4',
  paintMode: false,
  paintScope: 'part',
  paintConnected: true,
  paintTolerance: 24,
  paintPreserveShading: true,
  eyedropper: false,
  miniPaletteOpen: false,
  // 初期色を髪色(#F8F4E8)や白ドレス(#FFFFFF)と被らないパステルピンクにし、初回クリックで変化が即座に視認できるようにする
  paintColor: '#F48FB1',
  paletteCategory: 'hair',
  panelsCollapsed: false,
  mobileSheetOpen: false,
  mobileSheetTab: 'display',
};

const dom = {
  brandTitle: document.getElementById('brand-title'),
  statusBadge: document.getElementById('asset-status-badge'),
  characterSwitcher: document.getElementById('character-switcher'),
  versionSwitcher: document.getElementById('version-switcher'),
  bgSwitcher: document.getElementById('bg-switcher'),
  workspaceGrid: document.getElementById('workspace-grid'),
  leftSidebar: document.getElementById('left-sidebar'),
  refPanel: document.getElementById('ref-panel'),
  viewportContainer: document.getElementById('viewport-container'),
  canvas: document.getElementById('gl-canvas'),
  gizmoCanvas: document.getElementById('axis-gizmo'),

  topbarCharHost: document.getElementById('topbar-char-host'),
  topbarVersionHost: document.getElementById('topbar-version-host'),
  topbarBgHost: document.getElementById('topbar-bg-host'),
  topbarUtilHost: document.getElementById('topbar-util-host'),

  slotRender: document.getElementById('slot-render'),
  slotCamera: document.getElementById('slot-camera'),
  slotInspect: document.getElementById('slot-inspect'),
  slotReference: document.getElementById('slot-reference'),
  slotPaint: document.getElementById('slot-paint'),

  mobileBgHost: document.getElementById('mobile-bg-host'),
  mobileUtilHost: document.getElementById('mobile-util-host'),
  mobileRenderHost: document.getElementById('mobile-render-host'),
  mobileCameraHost: document.getElementById('mobile-camera-host'),
  mobileInspectHost: document.getElementById('mobile-inspect-host'),
  mobileCharHost: document.getElementById('mobile-char-host'),
  mobileVersionHost: document.getElementById('mobile-version-host'),
  mobileReferenceHost: document.getElementById('mobile-reference-host'),
  mobilePaintHost: document.getElementById('mobile-paint-host'),

  hudAxisPill: document.getElementById('hud-axis-pill'),
  hudAxisText: document.getElementById('hud-axis-text'),
  hudOutlinePill: document.getElementById('hud-outline-pill'),
  hudExtraPill: document.getElementById('hud-extra-pill'),
  hudPaintPill: document.getElementById('hud-paint-pill'),
  paintToast: document.getElementById('paint-toast'),
  hudYaw: document.getElementById('hud-yaw'),
  hudPitch: document.getElementById('hud-pitch'),
  hudZoom: document.getElementById('hud-zoom'),
  hudSlices: document.getElementById('hud-slices'),
  hudVolume: document.getElementById('hud-volume'),

  classicSub: document.getElementById('classic-subcontrols'),
  voxelSub: document.getElementById('voxel-subcontrols'),
  toggleClassicExtrude: document.getElementById('toggle-classic-extrude'),
  toggleOutline: document.getElementById('toggle-outline'),
  sliderOutlineWidth: document.getElementById('slider-outline-width'),
  valOutlineWidth: document.getElementById('val-outline-width'),
  sliderShading: document.getElementById('slider-shading'),
  valShading: document.getElementById('val-shading'),

  btnResetCamera: document.getElementById('btn-reset-camera'),
  toggleAutoSpin: document.getElementById('toggle-autospin'),

  btnResetInspect: document.getElementById('btn-reset-inspect'),
  sliderExplode: document.getElementById('slider-explode'),
  valExplode: document.getElementById('val-explode'),
  sliderCutaway: document.getElementById('slider-cutaway'),
  valCutaway: document.getElementById('val-cutaway'),
  selectCutAxis: document.getElementById('select-cut-axis'),

  toggleGrid: document.getElementById('toggle-grid'),
  btnCollapseAll: document.getElementById('btn-collapse-all'),
  floatingAutoSpin: document.getElementById('floating-autospin'),
  floatingColorFab: document.getElementById('floating-color-fab'),
  floatingOpenMenu: document.getElementById('floating-open-menu'),
  floatingMiniPalette: document.getElementById('floating-mini-palette'),
  miniBtnUndo: document.getElementById('mini-btn-undo'),
  miniBtnClose: document.getElementById('mini-btn-close'),
  miniIroHost: document.getElementById('mini-iro-host'),
  miniTabsHost: document.getElementById('mini-tabs-host'),
  miniSwatchesHost: document.getElementById('mini-swatches-host'),

  m3SheetOverlay: document.getElementById('m3-sheet-overlay'),
  m3SheetScrim: document.getElementById('m3-sheet-scrim'),
  m3SheetSurface: document.getElementById('m3-sheet-surface'),
  m3SheetHandleZone: document.getElementById('m3-sheet-handle-zone'),
  m3SheetClose: document.getElementById('m3-sheet-close'),
  m3TabDisplay: document.getElementById('m3-tab-display'),
  m3TabCompare: document.getElementById('m3-tab-compare'),
  m3TabPaint: document.getElementById('m3-tab-paint'),

  refSubLabel: document.getElementById('ref-sub-label'),
  refCard1Title: document.getElementById('ref-card1-title'),
  refCard1Btn: document.getElementById('ref-card1-btn'),
  refCard2Title: document.getElementById('ref-card2-title'),
  refCard2Btn: document.getElementById('ref-card2-btn'),
  refFrontImg: document.getElementById('ref-front-img'),
  refSideImg: document.getElementById('ref-side-img'),

  togglePaintMode: document.getElementById('toggle-paint-mode'),
  paintScopePart: document.getElementById('paint-scope-part'),
  paintScopeConnected: document.getElementById('paint-scope-connected'),
  paintScopeSingle: document.getElementById('paint-scope-single'),
  paintToleranceBlock: document.getElementById('paint-tolerance-block'),
  sliderPaintTolerance: document.getElementById('slider-paint-tolerance'),
  valPaintTolerance: document.getElementById('val-paint-tolerance'),
  togglePreserveShading: document.getElementById('toggle-preserve-shading'),
  paintIroAnchor: document.getElementById('paint-iro-anchor'),
  iroPickerWrap: document.getElementById('iro-picker-wrap'),
  paintColorSwatch: document.getElementById('paint-color-swatch'),
  paintHexInput: document.getElementById('paint-hex-input'),
  iroWheelMount: document.getElementById('iro-wheel-mount'),
  iroSlidersMount: document.getElementById('iro-sliders-mount'),
  toggleEyedropper: document.getElementById('toggle-eyedropper'),
  paintTabsAnchor: document.getElementById('paint-tabs-anchor'),
  paletteCategoryTabs: document.getElementById('palette-category-tabs'),
  paletteCatTitle: document.getElementById('palette-cat-title'),
  paletteCount: document.getElementById('palette-count'),
  paintSwatchesAnchor: document.getElementById('paint-swatches-anchor'),
  paletteSwatches: document.getElementById('palette-swatches'),
  btnPaintUndo: document.getElementById('btn-paint-undo'),
  btnPaintReset: document.getElementById('btn-paint-reset'),
  btnPaintExport: document.getElementById('btn-paint-export'),
  btnPaintImport: document.getElementById('btn-paint-import'),
  paintImportInput: document.getElementById('paint-import-input'),
  btnPaintSaveLocal: document.getElementById('btn-paint-save-local'),
  btnPaintLoadLocal: document.getElementById('btn-paint-load-local'),
  paintFeedback: document.getElementById('paint-feedback'),

  openStripModal: document.getElementById('open-strip-modal'),
  closeStripModal: document.getElementById('close-strip-modal'),
  stripModalBackdrop: document.getElementById('strip-modal-backdrop'),
  stripModal: document.getElementById('strip-modal'),
  stripImgY: document.getElementById('strip-img-y'),
  stripImgZ: document.getElementById('strip-img-z'),
  stripImgX: document.getElementById('strip-img-x'),
  metaSlicesY: document.getElementById('meta-slices-y'),
  metaSlicesZ: document.getElementById('meta-slices-z'),
  metaSlicesX: document.getElementById('meta-slices-x'),
  hoverSlicesY: document.getElementById('hover-slices-y'),
  hoverSlicesZ: document.getElementById('hover-slices-z'),
  hoverSlicesX: document.getElementById('hover-slices-x'),
};

const mobileMediaQuery = window.matchMedia('(max-width: 900px)');

let needsRender = true;
let currentAsset = null;
let manifestData = { defaultCharacterId: 'char2', characters: [] };
let customColors = loadCustomColors();
let partCustomColors = loadPartCustomColors();
let activeCategories = [];
let iroPicker = null;
let iroSliders = null;
let isSyncingIro = false;
let stripModalNeedsRefresh = false;
let toastTimer = null;

const painter = new VoxelPainter();
const renderer = new Pseudo3DRenderer(dom.canvas);
const camera = new OrbitCamera(
  () => {
    syncPresetButtons();
    requestRender();
  },
  (clickInfo) => handleCanvasClick(clickInfo),
  () => state.paintMode || state.eyedropper
);
camera.attach(dom.canvas);

function requestRender() {
  needsRender = true;
}

function getActiveCharacter() {
  return manifestData.characters.find((c) => c.id === state.characterId)
    || manifestData.characters[0]
    || null;
}

function showPaintToast(message) {
  if (!message) return;
  dom.paintToast.textContent = message;
  dom.paintToast.hidden = false;
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.paintToast.hidden = true;
  }, 2400);
}

function drawAxisGizmo(basis) {
  const ctx = dom.gizmoCanvas.getContext('2d');
  const w = dom.gizmoCanvas.width;
  const h = dom.gizmoCanvas.height;
  const cx = w * 0.5;
  const cy = h * 0.5;
  const len = 24;

  ctx.clearRect(0, 0, w, h);

  const axes = [
    { label: 'X', world: [1, 0, 0], color: '#e06c75' },
    { label: 'Y', world: [0, 1, 0], color: '#7ec699' },
    { label: 'Z', world: [0, 0, 1], color: '#6cb6ff' },
  ].map((ax) => {
    const sx = ax.world[0] * basis.right[0] + ax.world[1] * basis.right[1] + ax.world[2] * basis.right[2];
    const sy = ax.world[0] * basis.up[0] + ax.world[1] * basis.up[1] + ax.world[2] * basis.up[2];
    const sz = ax.world[0] * basis.back[0] + ax.world[1] * basis.back[1] + ax.world[2] * basis.back[2];
    return { ...ax, sx, sy, sz };
  });

  axes.sort((a, b) => a.sz - b.sz);

  ctx.lineWidth = 2;
  ctx.font = '10px BestTenDOT, Consolas, monospace';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';

  for (const ax of axes) {
    const ex = cx + ax.sx * len;
    const ey = cy - ax.sy * len;

    ctx.strokeStyle = ax.color;
    ctx.globalAlpha = ax.sz < -0.2 ? 0.45 : 1.0;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(ex, ey);
    ctx.stroke();

    ctx.fillStyle = ax.color;
    ctx.beginPath();
    ctx.arc(ex, ey, 6.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#121318';
    ctx.fillText(ax.label, ex, ey + 0.5);
  }
  ctx.globalAlpha = 1.0;
}

function updateHud(renderInfo) {
  if (!renderInfo) return;
  dom.hudYaw.textContent = `${camera.yawDeg.toFixed(1)}°`;
  dom.hudPitch.textContent = `${camera.pitchDeg.toFixed(1)}°`;
  dom.hudZoom.textContent = `${camera.zoom.toFixed(2)}x`;
  dom.hudSlices.textContent = renderInfo.slicesText;

  const axisNames = {
    x: 'X-Stack (左右スライス)',
    y: 'Y-Stack (上下スライス)',
    z: 'Z-Stack (前後スライス)',
  };

  if (state.mode === 'tri') {
    dom.hudAxisPill.dataset.axis = renderInfo.activeAxis;
    dom.hudAxisText.textContent = `ACTIVE: ${axisNames[renderInfo.activeAxis]}`;
  } else if (state.mode === 'classic-y') {
    dom.hudAxisPill.dataset.axis = 'y';
    dom.hudAxisText.textContent = `LOCKED: Y-Stack (${state.classicExtrude ? '厚み補完 ON' : '従来1枚板 OFF'})`;
  } else {
    dom.hudAxisPill.dataset.axis = 'voxel';
    dom.hudAxisText.textContent = `VOXEL MESH (陰影 ${state.shading}%)`;
  }

  dom.hudOutlinePill.hidden = !state.outline;
  if (state.outline) {
    dom.hudOutlinePill.textContent = `2D Outline ${state.outlineWidth.toFixed(2)}`;
  }

  dom.hudExtraPill.hidden = state.pixelSnapSubdiv === 0;
  if (state.pixelSnapSubdiv > 0) {
    dom.hudExtraPill.textContent = `Pixel Snap ${state.pixelSnapSubdiv}x`;
  }

  dom.hudPaintPill.hidden = !state.paintMode;
  if (state.paintMode) {
    const scopeNames = {
      part: 'パーツ全体',
      connected: '連結同色',
      single: '1ドット',
    };
    dom.hudPaintPill.textContent = state.eyedropper
      ? 'スポイト選択中'
      : `塗り直し (${scopeNames[state.paintScope] || '連結同色'})`;
  }

  drawAxisGizmo(renderInfo.basis);
}

function renderNow() {
  needsRender = false;
  const info = renderer.render(camera, state);
  updateHud(info);
}

function syncPresetButtons() {
  document.querySelectorAll('.preset-btn').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.preset === camera.activePreset);
  });
}

function syncAutoSpinUi() {
  const on = camera.autoSpin;
  dom.toggleAutoSpin.setAttribute('aria-pressed', String(on));
  dom.toggleAutoSpin.textContent = on ? 'ON' : 'OFF';
  dom.floatingAutoSpin.setAttribute('aria-pressed', String(on));
  dom.floatingAutoSpin.textContent = `自動回転: ${on ? 'ON' : 'OFF'}`;
}

function setAutoSpin(enabled) {
  camera.autoSpin = Boolean(enabled);
  syncAutoSpinUi();
}

function setMiniPaletteOpen(open) {
  const wantOpen = Boolean(open) && !mobileMediaQuery.matches;
  state.miniPaletteOpen = wantOpen;
  dom.floatingColorFab.setAttribute('aria-expanded', String(wantOpen));

  if (wantOpen) {
    // 重複IDやiro.js二重生成を避け、単一DOMノードをミニパレットへ一時移動して完全同期を維持する
    dom.miniIroHost.appendChild(dom.iroPickerWrap);
    dom.miniTabsHost.appendChild(dom.paletteCategoryTabs);
    dom.miniSwatchesHost.appendChild(dom.paletteSwatches);
    dom.floatingMiniPalette.hidden = false;
  } else {
    dom.paintIroAnchor.appendChild(dom.iroPickerWrap);
    dom.paintTabsAnchor.appendChild(dom.paletteCategoryTabs);
    dom.paintSwatchesAnchor.appendChild(dom.paletteSwatches);
    dom.floatingMiniPalette.hidden = true;
  }
}

function setPanelsCollapsed(collapsed) {
  state.panelsCollapsed = Boolean(collapsed);
  if (!state.panelsCollapsed && state.miniPaletteOpen) {
    setMiniPaletteOpen(false);
  }
  document.body.classList.toggle('panels-collapsed', state.panelsCollapsed);
  dom.floatingOpenMenu.textContent = mobileMediaQuery.matches ? 'メニュー' : 'メニューを開く';
  requestAnimationFrame(() => renderNow());
}

function setMobileSheetTab(tabKey) {
  state.mobileSheetTab = tabKey;
  document.querySelectorAll('.m3-tab').forEach((tab) => {
    const active = tab.dataset.sheetTab === tabKey;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  dom.m3TabDisplay.hidden = tabKey !== 'display';
  dom.m3TabCompare.hidden = tabKey !== 'compare';
  dom.m3TabPaint.hidden = tabKey !== 'paint';
}

function setMobileSheetOpen(open) {
  state.mobileSheetOpen = Boolean(open);
  if (state.mobileSheetOpen) {
    dom.m3SheetOverlay.hidden = false;
    dom.m3SheetSurface.style.transform = '';
    // hidden解除と同一フレームでクラスを付けるとCSSトランジションが走らないため1フレーム遅らせる
    requestAnimationFrame(() => {
      dom.m3SheetOverlay.classList.add('is-open');
    });
  } else {
    dom.m3SheetOverlay.classList.remove('is-open');
    dom.m3SheetSurface.style.transform = '';
    setTimeout(() => {
      if (!state.mobileSheetOpen) {
        dom.m3SheetOverlay.hidden = true;
      }
    }, 240);
  }
}

/**
 * デスクトップ用とモバイルボトムシート用でDOMを複製するとID重複・状態不整合の原因になるため、
 * ブレイクポイント切替時に同一のコントロールノード群を移動して単一イベント系を維持する。
 */
function syncResponsiveLayout() {
  const isMobile = mobileMediaQuery.matches;
  if (isMobile) {
    if (state.miniPaletteOpen) {
      setMiniPaletteOpen(false);
    }
    dom.mobileBgHost.appendChild(dom.bgSwitcher);
    dom.mobileUtilHost.appendChild(dom.toggleGrid);
    dom.mobileUtilHost.appendChild(dom.openStripModal);
    dom.mobileRenderHost.appendChild(dom.slotRender);
    dom.mobileCameraHost.appendChild(dom.slotCamera);
    dom.mobileInspectHost.appendChild(dom.slotInspect);
    dom.mobileCharHost.appendChild(dom.characterSwitcher);
    dom.mobileVersionHost.appendChild(dom.versionSwitcher);
    dom.mobileReferenceHost.appendChild(dom.slotReference);
    dom.mobilePaintHost.appendChild(dom.slotPaint);
    dom.floatingOpenMenu.textContent = 'メニュー';
  } else {
    dom.topbarCharHost.appendChild(dom.characterSwitcher);
    dom.topbarVersionHost.appendChild(dom.versionSwitcher);
    dom.topbarBgHost.appendChild(dom.bgSwitcher);
    dom.topbarUtilHost.appendChild(dom.toggleGrid);
    dom.topbarUtilHost.appendChild(dom.openStripModal);
    dom.leftSidebar.appendChild(dom.slotRender);
    dom.leftSidebar.appendChild(dom.slotCamera);
    dom.leftSidebar.appendChild(dom.slotInspect);
    dom.refPanel.appendChild(dom.slotReference);
    dom.refPanel.appendChild(dom.slotPaint);
    if (state.mobileSheetOpen) {
      state.mobileSheetOpen = false;
      dom.m3SheetOverlay.classList.remove('is-open');
      dom.m3SheetOverlay.hidden = true;
    }
    dom.floatingOpenMenu.textContent = 'メニューを開く';
  }
  requestAnimationFrame(() => renderNow());
}

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll('.mode-card').forEach((card) => {
    const active = card.dataset.mode === mode;
    card.classList.toggle('is-active', active);
    card.setAttribute('aria-checked', String(active));
  });
  dom.classicSub.hidden = mode !== 'classic-y';
  dom.voxelSub.hidden = mode !== 'voxel';
  renderNow();
}

function setOutline(enabled) {
  state.outline = Boolean(enabled);
  dom.toggleOutline.setAttribute('aria-pressed', String(state.outline));
  dom.toggleOutline.textContent = state.outline ? 'ON' : 'OFF';
  renderNow();
}

function setOutlineWidth(width) {
  const clamped = Math.max(0.5, Math.min(3.5, Number(width)));
  if (Number.isNaN(clamped)) return;
  state.outlineWidth = clamped;
  dom.sliderOutlineWidth.value = clamped.toFixed(2);
  dom.valOutlineWidth.textContent = clamped.toFixed(2);
  renderNow();
}

function setPixelSnap(subdiv) {
  state.pixelSnapSubdiv = Number(subdiv) || 0;
  document.querySelectorAll('.snap-mode-btn').forEach((b) => {
    b.classList.toggle('is-active', Number(b.dataset.snap) === state.pixelSnapSubdiv);
  });
  renderNow();
}

function initIroColorPicker() {
  if (iroPicker || !dom.iroWheelMount || !dom.iroSlidersMount || typeof window.iro === 'undefined') return;
  // 左プレビュー・中央ホイール・右(スポイト＋彩度/明度2本縦スライダ)の3列構成で高さを圧縮しつつ全色域を無制限操作可能にする
  iroPicker = new window.iro.ColorPicker(dom.iroWheelMount, {
    width: 96,
    color: state.paintColor,
    borderWidth: 1,
    borderColor: '#43485c',
    handleRadius: 5,
    padding: 2,
    layout: [
      { component: window.iro.ui.Wheel },
    ],
  });

  iroSliders = new window.iro.ColorPicker(dom.iroSlidersMount, {
    width: 72,
    color: state.paintColor,
    borderWidth: 1,
    borderColor: '#43485c',
    handleRadius: 5,
    padding: 2,
    margin: 6,
    layoutDirection: 'horizontal',
    layout: [
      { component: window.iro.ui.Slider, options: { sliderType: 'saturation', sliderSize: 15 } },
      { component: window.iro.ui.Slider, options: { sliderType: 'value', sliderSize: 15 } },
    ],
  });

  iroPicker.on('color:change', (color) => {
    if (isSyncingIro) return;
    setPaintColor(color.hexString, null, { source: 'wheel' });
  });

  iroSliders.on('color:change', (color) => {
    if (isSyncingIro) return;
    setPaintColor(color.hexString, null, { source: 'sliders' });
  });
}

function getActiveCategoryObj() {
  return activeCategories.find((c) => c.id === state.paletteCategory)
    || activeCategories[0]
    || null;
}

function setPaintColor(hex, explicitName = null, { source = null } = {}) {
  const norm = normalizeHex(hex);
  state.paintColor = norm;
  dom.paintColorSwatch.style.backgroundColor = norm;
  dom.floatingColorFab.style.backgroundColor = norm;
  const label = explicitName || findColorLabel(norm, activeCategories, painter.originalPalette);
  dom.paintColorSwatch.title = `${label} (${norm})`;
  if (source !== 'hexInput' && dom.paintHexInput) {
    dom.paintHexInput.value = norm;
  }
  isSyncingIro = true;
  try {
    if (source !== 'wheel' && iroPicker) {
      iroPicker.color.hexString = norm;
    }
    if (source !== 'sliders' && iroSliders) {
      iroSliders.color.hexString = norm;
    }
  } finally {
    isSyncingIro = false;
  }
  syncPaletteSelection();
  return norm;
}

function setPaintScope(scope, { silent = false } = {}) {
  let resolved = ['part', 'connected', 'single'].includes(scope) ? scope : 'connected';
  const hasParts = painter.hasParts;
  dom.paintScopePart.disabled = !hasParts;
  dom.paintScopePart.title = hasParts
    ? 'クリックしたボクセルと同一パーツ全体を陰影付きで一括塗り直し'
    : 'この版にはパーツ情報がありません（v4 / うさぎで利用可能）';

  if (resolved === 'part' && !hasParts) {
    resolved = 'connected';
  }
  state.paintScope = resolved;
  state.paintConnected = resolved !== 'single';

  dom.paintScopePart.classList.toggle('is-active', resolved === 'part');
  dom.paintScopeConnected.classList.toggle('is-active', resolved === 'connected');
  dom.paintScopeSingle.classList.toggle('is-active', resolved === 'single');
  dom.paintToleranceBlock.hidden = resolved !== 'connected';

  if (!silent) {
    renderNow();
  }
}

function addGlobalCustomColor(hex, name = null) {
  const norm = normalizeHex(hex);
  if (!customColors.some((c) => c.hex === norm)) {
    const label = name || `カスタム #${customColors.length + 1}`;
    customColors.push({ name: label, hex: norm });
    saveCustomColors(customColors);
    rebuildCategoriesForCurrentAsset();
    return true;
  }
  return false;
}

function addCustomColorToActiveCategory(hex = state.paintColor, explicitName = null) {
  const norm = normalizeHex(hex);
  const cat = getActiveCategoryObj();
  if (!cat || cat.isCustomTab) {
    const added = addGlobalCustomColor(norm, explicitName);
    setPaintColor(norm);
    return { added, categoryLabel: 'カスタム' };
  }

  const list = partCustomColors[cat.storageKey] ? [...partCustomColors[cat.storageKey]] : [];
  if (cat.items.some((item) => item.hex === norm)) {
    setPaintColor(norm);
    return { added: false, categoryLabel: cat.label };
  }

  const label = explicitName || `${cat.label}カスタム #${list.length + 1}`;
  list.push({ name: label, hex: norm });
  partCustomColors[cat.storageKey] = list;
  savePartCustomColors(partCustomColors);
  rebuildCategoriesForCurrentAsset();
  setPaintColor(norm, label);
  return { added: true, categoryLabel: cat.label };
}

function removeCustomColorFromActiveCategory(hex) {
  const norm = normalizeHex(hex);
  const cat = getActiveCategoryObj();
  if (!cat) return false;

  if (cat.isCustomTab) {
    const next = customColors.filter((c) => c.hex !== norm);
    if (next.length === customColors.length) return false;
    customColors = next;
    saveCustomColors(customColors);
  } else {
    const list = partCustomColors[cat.storageKey] || [];
    const next = list.filter((c) => c.hex !== norm);
    if (next.length === list.length) return false;
    if (next.length > 0) {
      partCustomColors[cat.storageKey] = next;
    } else {
      delete partCustomColors[cat.storageKey];
    }
    savePartCustomColors(partCustomColors);
  }

  rebuildCategoriesForCurrentAsset();
  const msg = `「${cat.label}」から追加色 ${norm} を削除しました`;
  dom.paintFeedback.textContent = msg;
  showPaintToast(msg);
  return true;
}

function getPartCategoriesSummary() {
  return activeCategories.map((cat) => ({
    id: cat.id,
    label: cat.label,
    partIdx: cat.partIdx,
    isPart: cat.isPart,
    isCustomTab: cat.isCustomTab,
    originalColors: cat.originalItems.map((i) => i.hex),
    customColors: cat.customItems.map((i) => i.hex),
    colors: cat.items.map((i) => ({
      hex: i.hex,
      name: i.name,
      isOriginal: Boolean(i.isOriginal),
    })),
  }));
}

function setPaintMode(enabled) {
  state.paintMode = Boolean(enabled);
  dom.togglePaintMode.setAttribute('aria-pressed', String(state.paintMode));
  dom.togglePaintMode.textContent = state.paintMode ? 'ON' : 'OFF';
  dom.canvas.classList.toggle('is-painting', state.paintMode);
  if (!state.paintMode) {
    setEyedropper(false);
  } else {
    const label = findColorLabel(state.paintColor, activeCategories, painter.originalPalette);
    const msg = `塗り直しON（${label} ${state.paintColor}）: キャラをクリックして塗装`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
  }
  renderNow();
}

function setEyedropper(enabled) {
  state.eyedropper = Boolean(enabled);
  dom.toggleEyedropper.setAttribute('aria-pressed', String(state.eyedropper));
  dom.toggleEyedropper.classList.toggle('is-active', state.eyedropper);
  renderNow();
}

function syncUndoUi() {
  dom.btnPaintUndo.disabled = !painter.canUndo;
  dom.btnPaintUndo.textContent = painter.canUndo ? `戻す (${painter.undoCount})` : '元に戻す';
  dom.miniBtnUndo.disabled = !painter.canUndo;
  dom.miniBtnUndo.textContent = painter.canUndo ? `戻す(${painter.undoCount})` : '戻す';
}

function getCurrentStorageKey() {
  return `${state.characterId}:${state.versionId}`;
}

function syncStorageUi() {
  const hasSaved = Boolean(getSavedPaintState(getCurrentStorageKey()));
  dom.btnPaintLoadLocal.disabled = !hasSaved;
  dom.btnPaintLoadLocal.title = hasSaved
    ? 'ブラウザに保管した配色を復元'
    : 'このキャラの保管配色はまだありません';
}

function saveColorState() {
  const snapshot = painter.buildStorageSnapshot();
  const ok = saveSavedPaintState(getCurrentStorageKey(), snapshot);
  syncStorageUi();
  const msg = ok
    ? `現在の配色をブラウザに保管しました（変更 ${snapshot.diffs.length.toLocaleString()} ボクセル）`
    : 'ブラウザストレージへの保管に失敗しました';
  dom.paintFeedback.textContent = msg;
  showPaintToast(msg);
  return ok;
}

function restoreColorState() {
  const snapshot = getSavedPaintState(getCurrentStorageKey());
  if (!snapshot) {
    const msg = 'このキャラの保管配色はありません';
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return false;
  }
  const res = painter.applyStorageSnapshot(snapshot);
  if (!res.ok) {
    const msg = `復元エラー: ${res.reason}`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return false;
  }
  applyEditedVoxelsToRenderer('保管していた配色を復元しました', { refreshCategories: true });
  return true;
}

function importPaintedJson(jsonText) {
  try {
    const parsed = JSON.parse(String(jsonText || ''));
    const res = painter.importFromJsonObject(parsed);
    if (!res.ok) {
      const msg = `JSON読込失敗: ${res.reason}`;
      dom.paintFeedback.textContent = msg;
      showPaintToast(msg);
      return false;
    }
    if (!res.sameSize) {
      camera.fitVolume(painter.size);
      dom.hudVolume.textContent = `${painter.size.x}×${painter.size.y}×${painter.size.z}`;
    }
    setPaintScope(painter.hasParts ? 'part' : 'connected', { silent: true });
    applyEditedVoxelsToRenderer(
      `JSONを読み込みました（${res.voxelCount.toLocaleString()} ボクセル）`
    );
    return true;
  } catch {
    const msg = 'JSON読込失敗: JSON構文が不正です';
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return false;
  }
}

function syncPaletteSelection() {
  dom.paletteSwatches.querySelectorAll('.swatch-chip[data-hex]').forEach((chip) => {
    chip.classList.toggle('is-selected', chip.dataset.hex === state.paintColor);
  });
}

function renderPaletteCategoryTabs() {
  dom.paletteCategoryTabs.innerHTML = '';
  activeCategories.forEach((cat) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'palette-cat-btn';
    btn.role = 'tab';
    btn.dataset.paletteCat = cat.id;
    btn.textContent = cat.label;
    btn.title = cat.isCustomTab ? '保存済みカスタム色' : `${cat.label}の元色と追加色`;
    const active = cat.id === state.paletteCategory;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', String(active));
    btn.addEventListener('click', () => setPaletteCategory(cat.id));
    dom.paletteCategoryTabs.appendChild(btn);
  });
}

function setPaletteCategory(categoryId) {
  const valid = activeCategories.some((c) => c.id === categoryId);
  if (!valid) return;
  state.paletteCategory = categoryId;
  dom.paletteCategoryTabs.querySelectorAll('.palette-cat-btn').forEach((btn) => {
    const active = btn.dataset.paletteCat === categoryId;
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-selected', String(active));
  });
  renderPaletteSwatches();
}

function rebuildCategoriesForCurrentAsset({ resetToFirst = false } = {}) {
  const liveResolver = (partIndices) => painter.getLiveColorsForParts(partIndices);
  activeCategories = buildCategoriesForAsset(
    currentAsset,
    painter.originalPalette,
    partCustomColors,
    customColors,
    liveResolver
  );
  if (resetToFirst || !activeCategories.some((c) => c.id === state.paletteCategory)) {
    state.paletteCategory = activeCategories[0]?.id || 'custom';
  }
  renderPaletteCategoryTabs();
  renderPaletteSwatches();
}

function renderPaletteSwatches() {
  const cat = getActiveCategoryObj();
  if (!cat) {
    dom.paletteCatTitle.textContent = 'パレット';
    dom.paletteCount.textContent = '0色';
    dom.paletteSwatches.innerHTML = '';
    return;
  }

  const items = cat.items || [];
  let titleText = '';
  if (cat.isCustomTab) {
    titleText = 'カスタム色';
  } else if (cat.isPart) {
    titleText = `${cat.label}の色` + (cat.customItems.length > 0 ? ` (+${cat.customItems.length})` : '');
  } else {
    titleText = 'モデルの元色' + (cat.customItems.length > 0 ? ` (+${cat.customItems.length})` : '');
  }

  dom.paletteCatTitle.textContent = titleText;
  dom.paletteCount.textContent = `${items.length}色`;
  dom.paletteSwatches.innerHTML = '';

  items.forEach((item) => {
    const hex = normalizeHex(item.hex);
    const chip = document.createElement('button');
    chip.type = 'button';
    const classes = ['swatch-chip'];
    if (!item.isOriginal) classes.push('is-custom');
    if (item.isOriginal && item.isEdited) classes.push('is-edited');
    chip.className = classes.join(' ');
    chip.dataset.hex = hex;
    chip.dataset.origin = item.isOriginal ? 'original' : 'custom';
    chip.style.backgroundColor = hex;
    chip.title = item.isOriginal
      ? `${item.name} (${hex})${item.isEdited ? ' [変更済]' : ''}`
      : `${item.name} (${hex}) — 右クリック/長押しで削除`;
    chip.setAttribute('aria-label', `${item.name} ${hex}`);

    let longPressTimer = null;
    let suppressNextClick = false;
    if (!item.isOriginal) {
      chip.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        removeCustomColorFromActiveCategory(hex);
      });
      chip.addEventListener('pointerdown', (e) => {
        if (e.button === 2) return;
        longPressTimer = setTimeout(() => {
          suppressNextClick = true;
          removeCustomColorFromActiveCategory(hex);
        }, 500);
      });
      const cancelLongPress = () => {
        if (longPressTimer) {
          clearTimeout(longPressTimer);
          longPressTimer = null;
        }
      };
      chip.addEventListener('pointerup', cancelLongPress);
      chip.addEventListener('pointerleave', cancelLongPress);
      chip.addEventListener('pointercancel', cancelLongPress);
    }

    chip.addEventListener('click', () => {
      if (suppressNextClick) {
        suppressNextClick = false;
        return;
      }
      // スウォッチ押下は描画色の選択のみにとどめ、誤って他箇所の色まで一括置換しないようにする
      setPaintColor(hex, item.name);
      setEyedropper(false);
      dom.paintFeedback.textContent = state.paintMode
        ? `塗り色を ${item.name} (${hex}) に設定しました`
        : `${item.name} (${hex}) を選択（塗り直しONにしてキャラをクリックで塗装）`;
    });
    dom.paletteSwatches.appendChild(chip);
  });

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.id = 'btn-add-swatch';
  addBtn.className = 'swatch-chip swatch-add-btn';
  addBtn.textContent = '+';
  addBtn.title = `現在の色 (${state.paintColor}) を「${cat.label}」に追加`;
  addBtn.setAttribute('aria-label', `${cat.label}に色を追加`);
  addBtn.addEventListener('click', () => {
    const { added, categoryLabel } = addCustomColorToActiveCategory(state.paintColor);
    const msg = added
      ? `${state.paintColor} を「${categoryLabel}」に追加しました`
      : `${state.paintColor} はすでに「${categoryLabel}」に登録済みです`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
  });
  dom.paletteSwatches.appendChild(addBtn);

  syncPaletteSelection();
}

function applyEditedVoxelsToRenderer(feedbackMsg) {
  const editedAsset = painter.buildUpdatedAsset();
  currentAsset = editedAsset;
  renderer.setAsset(editedAsset);
  syncUndoUi();
  rebuildCategoriesForCurrentAsset();
  stripModalNeedsRefresh = true;
  if (!dom.stripModal.hidden) {
    refreshStripModalImages();
  }
  if (feedbackMsg) {
    dom.paintFeedback.textContent = feedbackMsg;
    showPaintToast(feedbackMsg);
  }
  renderNow();
}

function setPaintTolerance(value) {
  const clamped = Math.max(0, Math.min(60, Math.round(Number(value) || 0)));
  state.paintTolerance = clamped;
  dom.sliderPaintTolerance.value = String(clamped);
  dom.valPaintTolerance.textContent = String(clamped);
}

function setPreserveShading(enabled) {
  state.paintPreserveShading = Boolean(enabled);
  dom.togglePreserveShading.setAttribute('aria-pressed', String(state.paintPreserveShading));
  dom.togglePreserveShading.textContent = state.paintPreserveShading ? 'ON' : 'OFF';
}

function paintPartByIndex(
  partIdx,
  hexColor = state.paintColor,
  preserveShading = state.paintPreserveShading
) {
  const partMeta = painter.getPartMeta(partIdx);
  if (!partMeta) return 0;
  const count = painter.paintPart(partIdx, hexColor, preserveShading);
  if (count <= 0) {
    const msg = `「${partMeta.label}」はすでに同じ色です（別の色を選んでください）`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return 0;
  }
  const hex = normalizeHex(hexColor);
  const label = findColorLabel(hex, activeCategories, painter.originalPalette);
  applyEditedVoxelsToRenderer(
    `パーツ全体「${partMeta.label}」 ${count.toLocaleString()} ボクセルを ${label}(${hex}) に変更`
  );
  return count;
}

function paintAtVoxel(
  x,
  y,
  z,
  hexColor = state.paintColor,
  scopeOrConnected = state.paintScope,
  tolerance = state.paintTolerance,
  preserveShading = state.paintPreserveShading
) {
  const scope = typeof scopeOrConnected === 'string'
    ? scopeOrConnected
    : (scopeOrConnected ? 'connected' : 'single');
  const partIdx = scope === 'part' ? painter.getVoxelPartIndex(x, y, z) : -1;
  const partMeta = partIdx >= 0 ? painter.getPartMeta(partIdx) : null;

  const count = painter.paintAt(x, y, z, hexColor, scope, tolerance, preserveShading);
  if (count <= 0) return 0;
  const hex = normalizeHex(hexColor);
  const label = findColorLabel(hex, activeCategories, painter.originalPalette);
  let scopePrefix = '単体';
  if (scope === 'part' && partMeta) {
    scopePrefix = `パーツ全体「${partMeta.label}」`;
  } else if (scope === 'connected' || scope === 'part') {
    scopePrefix = `連結(許容${tolerance})`;
  }
  applyEditedVoxelsToRenderer(
    `${scopePrefix} ${count.toLocaleString()} ボクセルを ${label}(${hex}) に変更`
  );
  return count;
}

function undoPaint() {
  if (!painter.undo()) return false;
  applyEditedVoxelsToRenderer('直前のカラー変更を元に戻しました');
  return true;
}

function resetPaint() {
  if (!painter.reset()) return false;
  applyEditedVoxelsToRenderer('カラー編集を初期状態へ戻しました');
  return true;
}

function handleCanvasClick({ clientX, clientY, shiftKey }) {
  if (!state.paintMode && !state.eyedropper) return;

  // レイアウト変化直後でもクリック時点の最新キャンバス解像度と投影行列でレイキャストできるよう同期する
  renderNow();
  const hit = painter.raycastClientPoint(clientX, clientY, dom.canvas, renderer.lastFrameMetrics);
  if (!hit) {
    const msg = 'キャラの上をクリックしてください';
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return;
  }

  const partMeta = hit.partIdx >= 0 ? painter.getPartMeta(hit.partIdx) : null;
  if (state.eyedropper || shiftKey) {
    addGlobalCustomColor(hit.hex, partMeta ? `抽出(${partMeta.label}) ${hit.hex}` : `抽出 ${hit.hex}`);
    setPaintColor(hit.hex);
    setEyedropper(false);
    const partSuffix = partMeta ? ` [${partMeta.label}]` : '';
    const msg = `スポイト抽出${partSuffix}: (${hit.x},${hit.y},${hit.z}) → ${hit.hex}`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
    return;
  }

  const changed = paintAtVoxel(hit.x, hit.y, hit.z, state.paintColor, state.paintScope);
  if (changed === 0) {
    const msg = `すでに同じ色です（別の色を選んでください: ${hit.hex}）`;
    dom.paintFeedback.textContent = msg;
    showPaintToast(msg);
  }
}

function applyStripZoom() {
  if (!currentAsset) return;
  const z = state.stripZoom;
  for (const [key, imgEl] of [
    ['y', dom.stripImgY],
    ['z', dom.stripImgZ],
    ['x', dom.stripImgX],
  ]) {
    const s = currentAsset.strips[key];
    imgEl.style.width = `${s.count * s.sliceWidth * z}px`;
    imgEl.style.height = `${s.sliceHeight * z}px`;
  }
}

function refreshStripModalImages() {
  if (!currentAsset) return;
  stripModalNeedsRefresh = false;

  // ペイント編集後はメモリ上の編集済みバッファをDataURL化してモーダルへ反映し、未編集時は実PNG URLを直接使う
  if (currentAsset.isEdited) {
    const sy = currentAsset.strips.y;
    const sz = currentAsset.strips.z;
    const sx = currentAsset.strips.x;
    dom.stripImgY.src = rgbaBufferToDataUrl(sy.width, sy.height, sy.data);
    dom.stripImgZ.src = rgbaBufferToDataUrl(sz.width, sz.height, sz.data);
    dom.stripImgX.src = rgbaBufferToDataUrl(sx.width, sx.height, sx.data);
  } else {
    dom.stripImgY.src = currentAsset.stripUrls.y;
    dom.stripImgZ.src = currentAsset.stripUrls.z;
    dom.stripImgX.src = currentAsset.stripUrls.x;
  }

  const sy = currentAsset.strips.y;
  const sz = currentAsset.strips.z;
  const sx = currentAsset.strips.x;
  dom.metaSlicesY.textContent = `${sy.count}枚 × (${sy.sliceWidth}×${sy.sliceHeight}px) = ${sy.count * sy.sliceWidth}×${sy.sliceHeight}px`;
  dom.metaSlicesZ.textContent = `${sz.count}枚 × (${sz.sliceWidth}×${sz.sliceHeight}px) = ${sz.count * sz.sliceWidth}×${sz.sliceHeight}px`;
  dom.metaSlicesX.textContent = `${sx.count}枚 × (${sx.sliceWidth}×${sx.sliceHeight}px) = ${sx.count * sx.sliceWidth}×${sx.sliceHeight}px`;
  applyStripZoom();
}

function renderCharacterSwitcher() {
  dom.characterSwitcher.innerHTML = '<span class="group-caption">キャラ</span>';
  manifestData.characters.forEach((ch) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'seg-btn char-btn';
    btn.dataset.charId = ch.id;
    btn.textContent = ch.shortLabel;
    btn.title = ch.description || ch.label;
    btn.classList.toggle('is-active', ch.id === state.characterId);
    btn.addEventListener('click', () => {
      setCharacter(ch.id);
    });
    dom.characterSwitcher.appendChild(btn);
  });
}

function renderVersionSwitcher() {
  const ch = getActiveCharacter();
  const versions = ch?.versions || [];
  dom.versionSwitcher.innerHTML = '<span class="group-caption">版比較</span>';
  versions.forEach((ver) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'seg-btn version-btn';
    btn.dataset.versionId = ver.id;
    btn.textContent = ver.label;
    btn.title = ver.description || ver.fullLabel || ver.label;
    btn.classList.toggle('is-active', ver.id === state.versionId);
    btn.addEventListener('click', () => {
      setVersion(ver.id);
    });
    dom.versionSwitcher.appendChild(btn);
  });
}

function applyReferenceViewsUi(asset, charEntry) {
  const views = asset.refViews || [];
  const charLabel = charEntry?.label || asset.name || 'CHARACTER 2';
  dom.refSubLabel.textContent = `${charLabel} 抽出原画`;

  const v1 = views[0] || { title: 'FRONT', buttonLabel: '正面', preset: 'front', url: './assets/ref_front.png' };
  const v2 = views[1] || { title: 'SIDE', buttonLabel: '真横', preset: 'side', url: './assets/ref_side.png' };

  dom.refCard1Title.textContent = v1.title;
  dom.refCard1Btn.textContent = v1.buttonLabel;
  dom.refCard1Btn.dataset.preset = v1.preset;
  dom.refFrontImg.src = v1.url;

  dom.refCard2Title.textContent = v2.title;
  dom.refCard2Btn.textContent = v2.buttonLabel;
  dom.refCard2Btn.dataset.preset = v2.preset;
  dom.refSideImg.src = v2.url;
}

function applyAssetToUi(asset, { preserveCamera = false } = {}) {
  const ch = getActiveCharacter();
  const hadPartsBefore = painter.hasParts;
  currentAsset = asset;
  painter.loadFromAsset(asset);
  renderer.setAsset(asset);
  if (!preserveCamera) {
    camera.fitVolume(asset.size);
  }

  dom.hudVolume.textContent = `${asset.size.x}×${asset.size.y}×${asset.size.z}`;
  dom.brandTitle.innerHTML = `${ch ? ch.shortLabel : asset.name} <span>立体ドット絵ビューア</span>`;

  if (asset.isFallback) {
    dom.statusBadge.dataset.state = 'fallback';
    dom.statusBadge.textContent = 'プレースホルダー表示中 (model.json 待機)';
  } else {
    dom.statusBadge.dataset.state = 'ready';
    const verMeta = ch?.versions?.find((v) => v.id === asset.versionId);
    const verPrefix = verMeta ? `${verMeta.id} · ` : '';
    dom.statusBadge.textContent = `${verPrefix}${asset.name} (${asset.voxels.length.toLocaleString()} voxels)`;
  }

  // パーツ付きモデルへ切り替えたときは標準スコープの「パーツ全体」を優先し、非対応の過去版では「連結同色」へ安全にフォールバックする
  const nextScope = painter.hasParts
    ? (!hadPartsBefore || state.paintScope === 'part' ? 'part' : state.paintScope)
    : (state.paintScope === 'part' ? 'connected' : state.paintScope);
  setPaintScope(nextScope, { silent: true });

  applyReferenceViewsUi(asset, ch);
  rebuildCategoriesForCurrentAsset({ resetToFirst: true });
  setPaintColor(state.paintColor);
  syncUndoUi();
  syncStorageUi();
  stripModalNeedsRefresh = true;
  refreshStripModalImages();
  renderNow();
}

async function setCharacter(characterId) {
  const ch = manifestData.characters.find((c) => c.id === characterId);
  if (!ch) return false;

  state.characterId = ch.id;
  state.versionId = ch.defaultVersion;
  renderCharacterSwitcher();
  renderVersionSwitcher();

  const verEntry = ch.versions.find((v) => v.id === state.versionId) || ch.versions[0];
  const asset = await loadCharacterAsset(verEntry, ch);
  applyAssetToUi(asset, { preserveCamera: true });
  dom.paintFeedback.textContent = `キャラクターを「${ch.label}」へ切替えました`;
  return !asset.isFallback;
}

async function setVersion(versionId) {
  const ch = getActiveCharacter();
  const entry = ch?.versions?.find((v) => v.id === versionId);
  if (!entry) return false;

  state.versionId = entry.id;
  dom.versionSwitcher.querySelectorAll('.version-btn').forEach((btn) => {
    btn.classList.toggle('is-active', btn.dataset.versionId === entry.id);
  });

  const asset = await loadCharacterAsset(entry, ch);
  applyAssetToUi(asset, { preserveCamera: true });
  dom.paintFeedback.textContent = `${entry.label}（${entry.description || asset.voxels.length + ' voxels'}）へ切替えました`;
  return !asset.isFallback;
}

function bindSheetSwipeToDismiss() {
  let swipeStartY = 0;
  let swiping = false;
  let lastDeltaY = 0;

  dom.m3SheetHandleZone.addEventListener('pointerdown', (e) => {
    swiping = true;
    swipeStartY = e.clientY;
    lastDeltaY = 0;
    dom.m3SheetSurface.style.transition = 'none';
    try {
      dom.m3SheetHandleZone.setPointerCapture(e.pointerId);
    } catch {
      // 合成イベント互換用
    }
  });

  dom.m3SheetHandleZone.addEventListener('pointermove', (e) => {
    if (!swiping) return;
    lastDeltaY = Math.max(0, e.clientY - swipeStartY);
    dom.m3SheetSurface.style.transform = `translateY(${lastDeltaY}px)`;
  });

  const endSwipe = () => {
    if (!swiping) return;
    swiping = false;
    dom.m3SheetSurface.style.transition = '';
    if (lastDeltaY > 70) {
      setMobileSheetOpen(false);
    } else {
      dom.m3SheetSurface.style.transform = '';
    }
  };

  dom.m3SheetHandleZone.addEventListener('pointerup', endSwipe);
  dom.m3SheetHandleZone.addEventListener('pointercancel', endSwipe);
}

function bindEvents() {
  document.querySelectorAll('[data-bg]').forEach((btn) => {
    if (!btn.classList.contains('seg-btn')) return;
    btn.addEventListener('click', () => {
      state.bg = btn.dataset.bg;
      document.querySelectorAll('.seg-btn[data-bg]').forEach((b) => {
        b.classList.toggle('is-active', b === btn);
      });
      dom.viewportContainer.dataset.bg = state.bg;
      document.querySelectorAll('.ref-img-frame').forEach((frame) => {
        frame.dataset.bg = state.bg;
      });
      renderNow();
    });
  });

  document.querySelectorAll('.mode-card').forEach((card) => {
    card.addEventListener('click', () => setMode(card.dataset.mode));
  });

  dom.toggleClassicExtrude.addEventListener('click', () => {
    state.classicExtrude = !state.classicExtrude;
    dom.toggleClassicExtrude.setAttribute('aria-pressed', String(state.classicExtrude));
    dom.toggleClassicExtrude.textContent = state.classicExtrude ? 'ON' : 'OFF';
    renderNow();
  });

  dom.sliderShading.addEventListener('input', () => {
    state.shading = Number(dom.sliderShading.value);
    dom.valShading.textContent = `${state.shading}%`;
    renderNow();
  });

  document.querySelectorAll('[data-shade-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.shading = Number(btn.dataset.shadePreset);
      dom.sliderShading.value = String(state.shading);
      dom.valShading.textContent = `${state.shading}%`;
      renderNow();
    });
  });

  dom.toggleOutline.addEventListener('click', () => {
    setOutline(!state.outline);
  });

  dom.sliderOutlineWidth.addEventListener('input', () => {
    setOutlineWidth(dom.sliderOutlineWidth.value);
  });

  document.querySelectorAll('.snap-mode-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      setPixelSnap(Number(btn.dataset.snap));
    });
  });

  document.querySelectorAll('[data-preset]').forEach((btn) => {
    btn.addEventListener('click', () => {
      camera.applyPreset(btn.dataset.preset);
      syncPresetButtons();
      renderNow();
    });
  });

  dom.btnResetCamera.addEventListener('click', () => {
    camera.reset();
    syncPresetButtons();
    renderNow();
  });

  dom.toggleAutoSpin.addEventListener('click', () => setAutoSpin(!camera.autoSpin));
  dom.floatingAutoSpin.addEventListener('click', () => setAutoSpin(!camera.autoSpin));

  dom.btnCollapseAll.addEventListener('click', () => setPanelsCollapsed(true));
  dom.floatingColorFab.addEventListener('click', () => {
    if (mobileMediaQuery.matches) {
      setMobileSheetTab('paint');
      setMobileSheetOpen(true);
    } else {
      setMiniPaletteOpen(!state.miniPaletteOpen);
    }
  });
  dom.miniBtnClose.addEventListener('click', () => setMiniPaletteOpen(false));
  dom.miniBtnUndo.addEventListener('click', () => undoPaint());
  dom.floatingOpenMenu.addEventListener('click', () => {
    if (mobileMediaQuery.matches) {
      setMobileSheetOpen(true);
    } else {
      setPanelsCollapsed(false);
    }
  });

  dom.m3SheetScrim.addEventListener('click', () => setMobileSheetOpen(false));
  dom.m3SheetClose.addEventListener('click', () => setMobileSheetOpen(false));
  document.querySelectorAll('.m3-tab').forEach((tab) => {
    tab.addEventListener('click', () => setMobileSheetTab(tab.dataset.sheetTab));
  });
  bindSheetSwipeToDismiss();

  dom.sliderExplode.addEventListener('input', () => {
    state.explode = Number(dom.sliderExplode.value);
    dom.valExplode.textContent = `${state.explode.toFixed(2)}x`;
    renderNow();
  });

  dom.sliderCutaway.addEventListener('input', () => {
    state.cutaway = Number(dom.sliderCutaway.value);
    dom.valCutaway.textContent = `${state.cutaway}%`;
    renderNow();
  });

  dom.selectCutAxis.addEventListener('change', () => {
    state.cutAxis = dom.selectCutAxis.value;
    renderNow();
  });

  dom.btnResetInspect.addEventListener('click', () => {
    state.explode = 1.0;
    state.cutaway = 0;
    state.cutAxis = 'auto';
    dom.sliderExplode.value = '1.00';
    dom.valExplode.textContent = '1.00x';
    dom.sliderCutaway.value = '0';
    dom.valCutaway.textContent = '0%';
    dom.selectCutAxis.value = 'auto';
    renderNow();
  });

  dom.toggleGrid.addEventListener('click', () => {
    state.showGrid = !state.showGrid;
    dom.toggleGrid.setAttribute('aria-pressed', String(state.showGrid));
    dom.toggleGrid.textContent = `台座: ${state.showGrid ? 'ON' : 'OFF'}`;
    renderNow();
  });

  dom.togglePaintMode.addEventListener('click', () => {
    setPaintMode(!state.paintMode);
  });

  dom.paintScopePart.addEventListener('click', () => setPaintScope('part'));
  dom.paintScopeConnected.addEventListener('click', () => setPaintScope('connected'));
  dom.paintScopeSingle.addEventListener('click', () => setPaintScope('single'));

  dom.sliderPaintTolerance.addEventListener('input', () => {
    setPaintTolerance(dom.sliderPaintTolerance.value);
  });

  dom.togglePreserveShading.addEventListener('click', () => {
    setPreserveShading(!state.paintPreserveShading);
  });

  dom.paintHexInput.addEventListener('input', () => {
    const raw = dom.paintHexInput.value.trim().replace(/^#/, '');
    if (/^[0-9a-fA-F]{6}$/.test(raw)) {
      setPaintColor(`#${raw}`, null, { source: 'hexInput' });
    }
  });

  dom.paintHexInput.addEventListener('blur', () => {
    dom.paintHexInput.value = state.paintColor;
  });

  dom.toggleEyedropper.addEventListener('click', () => {
    if (!state.paintMode) setPaintMode(true);
    setEyedropper(!state.eyedropper);
  });

  dom.btnPaintUndo.addEventListener('click', () => undoPaint());
  dom.btnPaintReset.addEventListener('click', () => resetPaint());

  dom.btnPaintExport.addEventListener('click', () => {
    const jsonText = painter.buildExportJsonString();
    const blob = new Blob([jsonText], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.characterId}_${state.versionId}_edited.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    dom.paintFeedback.textContent = '編集済みモデルJSONをダウンロードしました';
  });

  dom.btnPaintImport.addEventListener('click', () => {
    dom.paintImportInput.value = '';
    dom.paintImportInput.click();
  });

  dom.paintImportInput.addEventListener('change', async () => {
    const file = dom.paintImportInput.files?.[0];
    if (!file) return;
    const text = await file.text();
    importPaintedJson(text);
  });

  dom.btnPaintSaveLocal.addEventListener('click', () => saveColorState());
  dom.btnPaintLoadLocal.addEventListener('click', () => restoreColorState());

  const setModalOpen = (open) => {
    dom.stripModal.hidden = !open;
    if (open) {
      if (stripModalNeedsRefresh) refreshStripModalImages();
      applyStripZoom();
    }
  };

  dom.openStripModal.addEventListener('click', () => setModalOpen(true));
  dom.closeStripModal.addEventListener('click', () => setModalOpen(false));
  dom.stripModalBackdrop.addEventListener('click', () => setModalOpen(false));
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (!dom.stripModal.hidden) setModalOpen(false);
      else if (state.mobileSheetOpen) setMobileSheetOpen(false);
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && state.paintMode) {
      e.preventDefault();
      undoPaint();
    }
  });

  document.querySelectorAll('.strip-zoom-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.stripZoom = Number(btn.dataset.stripZoom);
      document.querySelectorAll('.strip-zoom-btn').forEach((b) => {
        b.classList.toggle('is-active', b === btn);
      });
      applyStripZoom();
    });
  });

  document.querySelectorAll('.strip-stage').forEach((stage) => {
    const axis = stage.dataset.stripAxis;
    const highlight = stage.querySelector('.strip-highlight');
    const infoEl = axis === 'y' ? dom.hoverSlicesY : axis === 'z' ? dom.hoverSlicesZ : dom.hoverSlicesX;

    stage.addEventListener('pointermove', (e) => {
      if (!currentAsset) return;
      const rect = stage.getBoundingClientRect();
      const s = currentAsset.strips[axis];
      const relX = Math.max(0, Math.min(rect.width - 0.01, e.clientX - rect.left));
      const slicePxW = s.sliceWidth * state.stripZoom;
      const idx = Math.min(s.count - 1, Math.max(0, Math.floor(relX / slicePxW)));

      highlight.hidden = false;
      highlight.style.left = `${idx * slicePxW}px`;
      highlight.style.width = `${slicePxW}px`;
      infoEl.textContent = `Slice #${idx} / ${s.count - 1} (${axis.toUpperCase()} = ${idx})`;
    });

    stage.addEventListener('pointerleave', () => {
      highlight.hidden = true;
      infoEl.textContent = 'スライス上をホバーすると番号を表示';
    });
  });

  // パネル収納やモバイルURLバー変動でもキャンバスの実表示寸法とレイキャスト行列を即座に同期する
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => requestRender());
    ro.observe(dom.viewportContainer);
  }
  window.addEventListener('resize', () => requestRender());
  mobileMediaQuery.addEventListener('change', () => syncResponsiveLayout());
}

function startLoop() {
  let lastTime = performance.now();
  const tick = (now) => {
    const dt = Math.min(0.1, (now - lastTime) / 1000);
    lastTime = now;

    if (camera.stepAutoSpin(dt)) {
      needsRender = true;
    }
    if (needsRender) {
      renderNow();
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/**
 * 開発初期のプレースホルダー表示中に @sculptor が assets/model.json を出力した際、
 * ページ手動リロードなしでも自動的に実モデルへ切り替える。
 */
function pollForRealAssetIfNeeded() {
  if (!currentAsset || !currentAsset.isFallback) return;
  const timer = setInterval(async () => {
    try {
      const res = await fetch('./assets/model.json', { method: 'HEAD', cache: 'no-store' });
      if (res.ok) {
        clearInterval(timer);
        manifestData = await loadVersionManifest();
        renderCharacterSwitcher();
        renderVersionSwitcher();
        const ch = getActiveCharacter();
        const entry = ch?.versions?.find((v) => v.id === state.versionId) || ch?.versions?.[0];
        const realAsset = await loadCharacterAsset(entry, ch);
        if (!realAsset.isFallback) {
          applyAssetToUi(realAsset);
        }
      }
    } catch {
      // アセット生成前のネットワーク失敗時はコンソール汚染を避けて待機を継続する
    }
  }, 3000);
}

async function init() {
  bindEvents();
  initIroColorPicker();
  syncResponsiveLayout();
  setPaintColor(state.paintColor, '桜ピンク');
  syncAutoSpinUi();

  manifestData = await loadVersionManifest();
  state.characterId = manifestData.defaultCharacterId;
  const initialChar = getActiveCharacter();
  state.versionId = initialChar?.defaultVersion || 'v4';
  renderCharacterSwitcher();
  renderVersionSwitcher();

  const initialEntry = initialChar?.versions?.find((v) => v.id === state.versionId)
    || initialChar?.versions?.[initialChar.versions.length - 1];
  const asset = await loadCharacterAsset(initialEntry, initialChar);
  applyAssetToUi(asset);
  startLoop();
  pollForRealAssetIfNeeded();

  // 自動ブラウザ検証でDOMイベント発火の非同期タイミング揺れに依存せず確定的な状態遷移を行えるようにする
  window.__char2Viewer = {
    state,
    camera,
    renderer,
    painter,
    iroPicker,
    iroSliders,
    setAngles: (yawDeg, pitchDeg) => {
      camera.setAngles(yawDeg, pitchDeg);
      renderNow();
    },
    setPreset: (presetKey) => {
      if (CAMERA_PRESETS[presetKey]) {
        camera.applyPreset(presetKey);
        syncPresetButtons();
        renderNow();
      }
    },
    setMode: (mode) => setMode(mode),
    setOutline: (enabled) => setOutline(enabled),
    setOutlineWidth: (w) => setOutlineWidth(w),
    setPixelSnap: (subdiv) => setPixelSnap(subdiv),
    setCharacter: (id) => setCharacter(id),
    setVersion: (id) => setVersion(id),
    setPaletteCategory: (cat) => setPaletteCategory(cat),
    getPartCategories: () => getPartCategoriesSummary(),
    setColorHex: (hex) => setPaintColor(hex),
    setMiniPaletteOpen: (open) => setMiniPaletteOpen(open),
    addCustomColorToActiveCategory: (hex) => addCustomColorToActiveCategory(hex ?? state.paintColor),
    removeCustomColorFromActiveCategory: (hex) => removeCustomColorFromActiveCategory(hex),
    setAutoSpin: (enabled) => setAutoSpin(enabled),
    setPanelsCollapsed: (collapsed) => setPanelsCollapsed(collapsed),
    setMobileSheetOpen: (open) => setMobileSheetOpen(open),
    setMobileSheetTab: (tab) => setMobileSheetTab(tab),
    setPaintMode: (enabled) => setPaintMode(enabled),
    setPaintScope: (scope) => setPaintScope(scope),
    setPaintTolerance: (val) => setPaintTolerance(val),
    setPreserveShading: (enabled) => setPreserveShading(enabled),
    paintPart: (partIdx, hex = state.paintColor, preserveShading = state.paintPreserveShading) =>
      paintPartByIndex(partIdx, hex, preserveShading),
    paintAtVoxel: (
      x,
      y,
      z,
      hex,
      scopeOrConnected = state.paintScope,
      tolerance = state.paintTolerance,
      preserveShading = state.paintPreserveShading
    ) => paintAtVoxel(x, y, z, hex, scopeOrConnected, tolerance, preserveShading),
    undoPaint: () => undoPaint(),
    resetPaint: () => resetPaint(),
    importJson: (jsonText) => importPaintedJson(jsonText),
    saveColorState: () => saveColorState(),
    restoreColorState: () => restoreColorState(),
    hasSavedColorState: () => Boolean(getSavedPaintState(getCurrentStorageKey())),
    reloadAsset: async () => {
      manifestData = await loadVersionManifest();
      renderCharacterSwitcher();
      renderVersionSwitcher();
      const ch = getActiveCharacter();
      const entry = ch?.versions?.find((v) => v.id === state.versionId) || ch?.versions?.[0];
      const fresh = await loadCharacterAsset(entry, ch);
      applyAssetToUi(fresh, { preserveCamera: true });
      return !fresh.isFallback;
    },
  };
}

init();
