import { clamp, computeCameraBasis, DEG_TO_RAD, normalizeSignedDeg } from './math.js';

export const CAMERA_PRESETS = {
  front: { yawDeg: 0, pitchDeg: 0, label: '正面 (Front)' },
  quarter: { yawDeg: 32, pitchDeg: 35, label: '斜め俯瞰 (Quarter 35°)' },
  side: { yawDeg: 90, pitchDeg: 0, label: '真横 (Side)' },
  back: { yawDeg: 180, pitchDeg: 0, label: '背面 (Back)' },
  top: { yawDeg: 0, pitchDeg: 90, label: '真上 (Top 90°)' },
  low: { yawDeg: 20, pitchDeg: -25, label: '見上げ (Low -25°)' },
};

export class OrbitCamera {
  constructor(onChange, onClickPick = null, isPaintActiveFn = null) {
    this.yawDeg = CAMERA_PRESETS.quarter.yawDeg;
    this.pitchDeg = CAMERA_PRESETS.quarter.pitchDeg;
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.autoSpin = false;
    this.activePreset = 'quarter';
    this.isDragging = false;
    this._dragMode = 'orbit';
    this._activePointers = new Map();
    this._hadMultiTouch = false;
    this._hasStartedDrag = false;
    this._downX = 0;
    this._downY = 0;
    this._downButton = 0;
    this._downShift = false;
    this._downPointerType = 'mouse';
    this._maxMoveDist = 0;
    this._lastX = 0;
    this._lastY = 0;
    this._pinchLastDist = 0;
    this._pinchLastMidX = 0;
    this._pinchLastMidY = 0;
    this._baseOrthoHeight = 76;
    this._onChange = onChange;
    this._onClickPick = onClickPick;
    this._isPaintActiveFn = isPaintActiveFn;
  }

  fitVolume(size) {
    const maxSpan = Math.max(size.x, size.y, size.z);
    this._baseOrthoHeight = Math.max(40, Math.round(maxSpan * 1.32));
    this._notify();
  }

  get baseOrthoHeight() {
    return this._baseOrthoHeight;
  }

  getBasis() {
    return computeCameraBasis(this.yawDeg * DEG_TO_RAD, this.pitchDeg * DEG_TO_RAD);
  }

  getTarget() {
    const { right, up } = this.getBasis();
    return [
      right[0] * this.panX + up[0] * this.panY,
      right[1] * this.panX + up[1] * this.panY,
      right[2] * this.panX + up[2] * this.panY,
    ];
  }

  /**
   * プリセット押下時にイージング補間を入れると、自動検証の click 直後のスクリーンショットが移動途中を撮影してしまうため即時反映とする。
   */
  applyPreset(presetKey) {
    const preset = CAMERA_PRESETS[presetKey];
    if (!preset) return;
    this.yawDeg = preset.yawDeg;
    this.pitchDeg = preset.pitchDeg;
    this.panX = 0;
    this.panY = 0;
    this.activePreset = presetKey;
    this._notify();
  }

  setAngles(yawDeg, pitchDeg) {
    this.yawDeg = normalizeSignedDeg(yawDeg);
    this.pitchDeg = clamp(pitchDeg, -90, 90);
    this.activePreset = null;
    this._notify();
  }

  reset() {
    this.yawDeg = CAMERA_PRESETS.quarter.yawDeg;
    this.pitchDeg = CAMERA_PRESETS.quarter.pitchDeg;
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.activePreset = 'quarter';
    this._notify();
  }

  stepAutoSpin(dtSeconds) {
    if (!this.autoSpin || this.isDragging) return false;
    // ユーザー要件に従いスライス遅延やバウンス揺れを一切入れず、剛体としての一定角速度回転のみ行う
    this.yawDeg = normalizeSignedDeg(this.yawDeg + dtSeconds * 24.0);
    this.activePreset = null;
    return true;
  }

  _syncPinchOrigin() {
    const pts = Array.from(this._activePointers.values());
    if (pts.length < 2) return;
    this._pinchLastDist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
    this._pinchLastMidX = (pts[0].x + pts[1].x) * 0.5;
    this._pinchLastMidY = (pts[0].y + pts[1].y) * 0.5;
  }

  attach(canvas) {
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    canvas.addEventListener('pointerdown', (e) => {
      this._activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      this.isDragging = true;
      try {
        canvas.setPointerCapture(e.pointerId);
      } catch {
        // 合成イベント等で pointerId が未登録の場合でも操作を継続できるように握りつぶす
      }

      if (this._activePointers.size === 1) {
        this._downX = e.clientX;
        this._downY = e.clientY;
        this._downButton = e.button;
        this._downShift = e.shiftKey;
        this._downPointerType = e.pointerType || 'mouse';
        this._maxMoveDist = 0;
        this._hadMultiTouch = false;
        this._hasStartedDrag = false;
        this._lastX = e.clientX;
        this._lastY = e.clientY;
        this._dragMode = (e.button === 2 || e.button === 1 || e.shiftKey) ? 'pan' : 'orbit';
      } else if (this._activePointers.size === 2) {
        this._hadMultiTouch = true;
        this._hasStartedDrag = true;
        this._syncPinchOrigin();
      }
    });

    canvas.addEventListener('pointermove', (e) => {
      if (!this._activePointers.has(e.pointerId)) return;
      this._activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

      if (this._activePointers.size === 2) {
        const pts = Array.from(this._activePointers.values());
        const dist = Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y);
        const midX = (pts[0].x + pts[1].x) * 0.5;
        const midY = (pts[0].y + pts[1].y) * 0.5;

        if (this._pinchLastDist > 4 && dist > 4) {
          this.zoom = clamp(this.zoom * (dist / this._pinchLastDist), 0.35, 5.0);
        }

        const rect = canvas.getBoundingClientRect();
        const aspect = rect.width / Math.max(1, rect.height);
        const effOrthoH = aspect < 1.0
          ? (this._baseOrthoHeight / this.zoom) / Math.max(0.42, aspect)
          : (this._baseOrthoHeight / this.zoom);
        const worldPerPixel = effOrthoH / Math.max(1, rect.height);
        this.panX -= (midX - this._pinchLastMidX) * worldPerPixel;
        this.panY += (midY - this._pinchLastMidY) * worldPerPixel;

        this._pinchLastDist = dist;
        this._pinchLastMidX = midX;
        this._pinchLastMidY = midY;
        this._notify();
        return;
      }

      if (this._activePointers.size !== 1 || this._hadMultiTouch) return;

      const totalDist = Math.hypot(e.clientX - this._downX, e.clientY - this._downY);
      if (totalDist > this._maxMoveDist) this._maxMoveDist = totalDist;

      // 塗り直しモード中はクリック時の僅かな手ブレでカメラが揺れたりクリック判定が取り消されるのを防ぐためデッドゾーンを設ける
      const isPaint = Boolean(this._isPaintActiveFn && this._isPaintActiveFn());
      const dragStartThreshold = isPaint ? (this._downPointerType === 'touch' ? 9 : 6) : 0;
      if (!this._hasStartedDrag) {
        if (totalDist < dragStartThreshold) {
          this._lastX = e.clientX;
          this._lastY = e.clientY;
          return;
        }
        this._hasStartedDrag = true;
      }

      const dx = e.clientX - this._lastX;
      const dy = e.clientY - this._lastY;
      this._lastX = e.clientX;
      this._lastY = e.clientY;
      if (dx === 0 && dy === 0) return;

      if (this._dragMode === 'pan' || e.shiftKey) {
        const rect = canvas.getBoundingClientRect();
        const aspect = rect.width / Math.max(1, rect.height);
        const effOrthoH = aspect < 1.0
          ? (this._baseOrthoHeight / this.zoom) / Math.max(0.42, aspect)
          : (this._baseOrthoHeight / this.zoom);
        const worldPerPixel = effOrthoH / Math.max(1, rect.height);
        this.panX -= dx * worldPerPixel;
        this.panY += dy * worldPerPixel;
      } else {
        this.yawDeg = normalizeSignedDeg(this.yawDeg - dx * 0.45);
        this.pitchDeg = clamp(this.pitchDeg + dy * 0.45, -90, 90);
        this.activePreset = null;
      }
      this._notify();
    });

    const endPointer = (e, isCancel) => {
      if (!this._activePointers.has(e.pointerId)) return;
      this._activePointers.delete(e.pointerId);
      try {
        if (canvas.hasPointerCapture(e.pointerId)) {
          canvas.releasePointerCapture(e.pointerId);
        }
      } catch {
        // 合成ポインタイベント互換用
      }

      if (this._activePointers.size === 1) {
        // 2本指ピンチから片方の指だけ離した瞬間に残りの指位置へカメラが飛び跳ねるのを防ぐ
        const remaining = Array.from(this._activePointers.values())[0];
        this._lastX = remaining.x;
        this._lastY = remaining.y;
        return;
      }

      if (this._activePointers.size === 0) {
        this.isDragging = false;
        const clickLimit = this._downPointerType === 'touch' ? 10 : 6;
        if (
          !isCancel &&
          !this._hadMultiTouch &&
          this._downButton === 0 &&
          this._maxMoveDist < clickLimit &&
          this._onClickPick
        ) {
          this._onClickPick({
            clientX: e.clientX,
            clientY: e.clientY,
            shiftKey: this._downShift || e.shiftKey,
          });
        }
        this._hadMultiTouch = false;
        this._hasStartedDrag = false;
      }
    };

    canvas.addEventListener('pointerup', (e) => endPointer(e, false));
    canvas.addEventListener('pointercancel', (e) => endPointer(e, true));

    canvas.addEventListener(
      'wheel',
      (e) => {
        e.preventDefault();
        const factor = Math.exp(-e.deltaY * 0.0012);
        this.zoom = clamp(this.zoom * factor, 0.35, 5.0);
        this._notify();
      },
      { passive: false }
    );
  }

  _notify() {
    if (this._onChange) this._onChange();
  }
}
