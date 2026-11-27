export const DEG_TO_RAD = Math.PI / 180;
export const RAD_TO_DEG = 180 / Math.PI;

export function clamp(value, min, max) {
  return value < min ? min : value > max ? max : value;
}

export function normalizeSignedDeg(deg) {
  let wrapped = ((deg + 180) % 360 + 360) % 360 - 180;
  if (Object.is(wrapped, -0)) wrapped = 0;
  return wrapped;
}

/**
 * 汎用的な lookAt(eye, target, [0,1,0]) は Pitch = ±90°（真上・真下）で視線と上ベクトルが平行になり
 * 外積ゼロ（ジンバルロック反転・NaN）を起こすため、球面角 (yaw, pitch) から正規直交基底を解析的に直接構成する。
 */
export function computeCameraBasis(yawRad, pitchRad) {
  const sy = Math.sin(yawRad);
  const cy = Math.cos(yawRad);
  const sp = Math.sin(pitchRad);
  const cp = Math.cos(pitchRad);

  const right = [cy, 0, -sy];
  const up = [-sp * sy, cp, -sp * cy];
  const back = [cp * sy, sp, cp * cy];

  return { right, up, back };
}

export function createViewMatrix(basis, target, distance) {
  const { right, up, back } = basis;
  const eyeX = target[0] + back[0] * distance;
  const eyeY = target[1] + back[1] * distance;
  const eyeZ = target[2] + back[2] * distance;

  const tx = -(right[0] * eyeX + right[1] * eyeY + right[2] * eyeZ);
  const ty = -(up[0] * eyeX + up[1] * eyeY + up[2] * eyeZ);
  const tz = -(back[0] * eyeX + back[1] * eyeY + back[2] * eyeZ);

  return new Float32Array([
    right[0], up[0], back[0], 0,
    right[1], up[1], back[1], 0,
    right[2], up[2], back[2], 0,
    tx,       ty,    tz,      1,
  ]);
}

export function createOrthoMatrix(left, right, bottom, top, near, far) {
  const lr = 1 / (left - right);
  const bt = 1 / (bottom - top);
  const nf = 1 / (near - far);

  return new Float32Array([
    -2 * lr, 0, 0, 0,
    0, -2 * bt, 0, 0,
    0, 0, 2 * nf, 0,
    (left + right) * lr, (top + bottom) * bt, (far + near) * nf, 1,
  ]);
}

export function multiplyMat4(a, b) {
  const out = new Float32Array(16);
  for (let col = 0; col < 4; col++) {
    const b0 = b[col * 4 + 0];
    const b1 = b[col * 4 + 1];
    const b2 = b[col * 4 + 2];
    const b3 = b[col * 4 + 3];
    out[col * 4 + 0] = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
    out[col * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
    out[col * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
    out[col * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
  }
  return out;
}

/**
 * 厳密な45°境界上で浮動小数点誤差によりフレームごとに軸がチャタリングするのを防ぐため、
 * 現在選択中の軸に対して微小なヒステリシス（1e-4）を持たせた argmax(|vx|, |vy|, |vz|) を用いる。
 */
export function selectDominantAxis(viewVec, previousAxis = 'z') {
  const ax = Math.abs(viewVec[0]);
  const ay = Math.abs(viewVec[1]);
  const az = Math.abs(viewVec[2]);
  const eps = 1e-4;

  const bx = previousAxis === 'x' ? ax + eps : ax;
  const by = previousAxis === 'y' ? ay + eps : ay;
  const bz = previousAxis === 'z' ? az + eps : az;

  if (bz >= bx && bz >= by) return 'z';
  if (by >= bx && by >= bz) return 'y';
  return 'x';
}
