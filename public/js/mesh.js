const FACES = [
  {
    normal: [1, 0, 0],
    corners: [
      [0.5, -0.5, 0.5],
      [0.5, -0.5, -0.5],
      [0.5, 0.5, -0.5],
      [0.5, -0.5, 0.5],
      [0.5, 0.5, -0.5],
      [0.5, 0.5, 0.5],
    ],
  },
  {
    normal: [-1, 0, 0],
    corners: [
      [-0.5, -0.5, -0.5],
      [-0.5, -0.5, 0.5],
      [-0.5, 0.5, 0.5],
      [-0.5, -0.5, -0.5],
      [-0.5, 0.5, 0.5],
      [-0.5, 0.5, -0.5],
    ],
  },
  {
    normal: [0, 1, 0],
    corners: [
      [-0.5, 0.5, 0.5],
      [0.5, 0.5, 0.5],
      [0.5, 0.5, -0.5],
      [-0.5, 0.5, 0.5],
      [0.5, 0.5, -0.5],
      [-0.5, 0.5, -0.5],
    ],
  },
  {
    normal: [0, -1, 0],
    corners: [
      [-0.5, -0.5, -0.5],
      [0.5, -0.5, -0.5],
      [0.5, -0.5, 0.5],
      [-0.5, -0.5, -0.5],
      [0.5, -0.5, 0.5],
      [-0.5, -0.5, 0.5],
    ],
  },
  {
    normal: [0, 0, 1],
    corners: [
      [-0.5, -0.5, 0.5],
      [0.5, -0.5, 0.5],
      [0.5, 0.5, 0.5],
      [-0.5, -0.5, 0.5],
      [0.5, 0.5, 0.5],
      [-0.5, 0.5, 0.5],
    ],
  },
  {
    normal: [0, 0, -1],
    corners: [
      [0.5, -0.5, -0.5],
      [-0.5, -0.5, -0.5],
      [-0.5, 0.5, -0.5],
      [0.5, -0.5, -0.5],
      [-0.5, 0.5, -0.5],
      [0.5, 0.5, -0.5],
    ],
  },
];

/**
 * 通常時は外表面のみ描画してオーバードローを最小化しつつ、断面カットや分解表示時に内部が空洞に見えないよう、
 * 同一VBOの前半に外表面、後半に内部隣接面を分離配置してスライダ操作中のCPUメッシュ再構築を不要にする。
 */
export function buildVoxelMeshBuffers(size, paletteRgb, voxels) {
  const { x: W, y: H, z: D } = size;
  const occupancy = new Uint8Array(W * H * D);

  for (let i = 0; i < voxels.length; i++) {
    const [vx, vy, vz] = voxels[i];
    if (vx >= 0 && vx < W && vy >= 0 && vy < H && vz >= 0 && vz < D) {
      occupancy[(vy * D + vz) * W + vx] = 1;
    }
  }

  let exteriorFaces = 0;
  let interiorFaces = 0;

  for (let i = 0; i < voxels.length; i++) {
    const [vx, vy, vz] = voxels[i];
    for (let f = 0; f < 6; f++) {
      const [nx, ny, nz] = FACES[f].normal;
      const ax = vx + nx;
      const ay = vy + ny;
      const az = vz + nz;
      const hasNeighbor =
        ax >= 0 && ax < W && ay >= 0 && ay < H && az >= 0 && az < D &&
        occupancy[(ay * D + az) * W + ax] === 1;
      if (hasNeighbor) interiorFaces++;
      else exteriorFaces++;
    }
  }

  const totalVerts = (exteriorFaces + interiorFaces) * 6;
  const strideBytes = 40;
  const rawBuffer = new ArrayBuffer(totalVerts * strideBytes);
  const f32 = new Float32Array(rawBuffer);
  const u8 = new Uint8Array(rawBuffer);

  let extCursor = 0;
  let intCursor = exteriorFaces * 6;

  const writeFace = (vertCursor, vx, vy, vz, face, rgb, isInteriorFlag) => {
    const { normal, corners } = face;
    for (let k = 0; k < 6; k++) {
      const vIdx = vertCursor + k;
      const fBase = vIdx * 10;
      const bBase = vIdx * 40 + 36;
      const c = corners[k];

      f32[fBase + 0] = c[0];
      f32[fBase + 1] = c[1];
      f32[fBase + 2] = c[2];

      f32[fBase + 3] = vx;
      f32[fBase + 4] = vy;
      f32[fBase + 5] = vz;

      f32[fBase + 6] = normal[0];
      f32[fBase + 7] = normal[1];
      f32[fBase + 8] = normal[2];

      u8[bBase + 0] = rgb[0];
      u8[bBase + 1] = rgb[1];
      u8[bBase + 2] = rgb[2];
      u8[bBase + 3] = isInteriorFlag;
    }
  };

  for (let i = 0; i < voxels.length; i++) {
    const [vx, vy, vz, pIdx] = voxels[i];
    const rgb = paletteRgb[pIdx] || [255, 255, 255];

    for (let f = 0; f < 6; f++) {
      const face = FACES[f];
      const [nx, ny, nz] = face.normal;
      const ax = vx + nx;
      const ay = vy + ny;
      const az = vz + nz;
      const hasNeighbor =
        ax >= 0 && ax < W && ay >= 0 && ay < H && az >= 0 && az < D &&
        occupancy[(ay * D + az) * W + ax] === 1;

      if (hasNeighbor) {
        writeFace(intCursor, vx, vy, vz, face, rgb, 255);
        intCursor += 6;
      } else {
        writeFace(extCursor, vx, vy, vz, face, rgb, 0);
        extCursor += 6;
      }
    }
  }

  return {
    buffer: rawBuffer,
    exteriorVertexCount: exteriorFaces * 6,
    totalVertexCount: totalVerts,
    exteriorFaceCount: exteriorFaces,
  };
}
