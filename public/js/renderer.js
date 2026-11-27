import { buildVoxelMeshBuffers } from './mesh.js';
import { computeCameraBasis, createOrthoMatrix, createViewMatrix, DEG_TO_RAD, multiplyMat4, selectDominantAxis } from './math.js';

/**
 * 離散サブレイヤー板を複数枚重ねる従来手法では、顔の曲面段差（斜め隣接ボクセル境界）において
 * サブレイヤー間隔 1/K の隙間を視線がすり抜けて背後の肌ボクセルが1px縦割れとして露出してしまう。
 * 各スライスの前面クアッド1枚から厚み区間 [0, 1] を厳密な2D DDAで連続走査し、衝突位置の
 * gl_FragDepth を直接出力することで、全角度・全倍率で物理的な隙間発生をゼロにする。
 */
const SLICE_VS = `#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec2 aQuadUV;

uniform mat4 uViewProj;
uniform vec3 uVolumeSize;
uniform vec3 uCamBack;
uniform int uAxis;
uniform int uSliceCount;
uniform int uSliceOffset;
uniform int uFrontPositive;
uniform float uExplode;
uniform float uSlabThickness;
uniform int uSliceW;
uniform int uSliceH;
uniform float uPadTexels;

flat out int vSliceIndex;
out vec2 vTexelPos;
out float vDepthWorld;

void main() {
  int sliceIdx = (uFrontPositive == 1)
    ? (uSliceOffset + gl_InstanceID)
    : (uSliceCount - 1 - uSliceOffset - gl_InstanceID);

  float sliceCenter = (float(sliceIdx) + 0.5 - 0.5 * float(uSliceCount)) * uExplode;
  float posFront = sliceCenter + ((uFrontPositive == 1) ? 0.5 : -0.5) * uSlabThickness;

  float texU = -uPadTexels + aQuadUV.x * (float(uSliceW) + 2.0 * uPadTexels);
  float texV = -uPadTexels + aQuadUV.y * (float(uSliceH) + 2.0 * uPadTexels);

  vec3 worldPos;
  if (uAxis == 1) {
    worldPos = vec3(
      texU - 0.5 * uVolumeSize.x,
      posFront,
      texV - 0.5 * uVolumeSize.z
    );
  } else if (uAxis == 2) {
    worldPos = vec3(
      texU - 0.5 * uVolumeSize.x,
      0.5 * uVolumeSize.y - texV,
      posFront
    );
  } else {
    worldPos = vec3(
      posFront,
      0.5 * uVolumeSize.y - texV,
      texU - 0.5 * uVolumeSize.z
    );
  }

  vSliceIndex = sliceIdx;
  vTexelPos = vec2(texU, texV);
  vDepthWorld = -dot(worldPos, uCamBack);
  gl_Position = uViewProj * vec4(worldPos, 1.0);
}
`;

/**
 * 水平ストリップテクスチャに対して正規化UVの texture() を使うとスライス端で隣接スライス1pxが滲むため、
 * 整数クランプした texelFetch を用いる。また EXT_color_buffer_float 拡張に依存しないよう、
 * 輪郭線用の線形深度は標準 RGBA8 第2カラーアタッチメントのRG16bitへパックして出力する。
 */
const SLICE_FS = `#version 300 es
precision highp float;
precision highp int;

flat in int vSliceIndex;
in vec2 vTexelPos;
in float vDepthWorld;

uniform sampler2D uStripTex;
uniform int uAxis;
uniform int uSliceW;
uniform int uSliceH;
uniform int uCutAxis;
uniform int uCutSliceTotal;
uniform int uCutVisibleSlices;
uniform int uCutFrontPositive;
uniform vec2 uRayTexelDelta;
uniform float uSlabRayLength;
uniform float uDepthPerWorldUnit;
uniform int uMaxDdaSteps;

layout(location = 0) out vec4 fragColor;
layout(location = 1) out vec4 fragMeta;

vec2 packDepth16(float depthWorld) {
  float norm = clamp((depthWorld + 128.0) / 256.0, 0.0, 1.0);
  float scaled = floor(norm * 65535.0 + 0.5);
  float hi = floor(scaled / 256.0);
  float lo = scaled - hi * 256.0;
  return vec2(hi / 255.0, lo / 255.0);
}

bool isSliceVoxelVisible(int px, int py, int sliceIdx) {
  ivec3 vox;
  if (uAxis == 1) {
    vox = ivec3(px, sliceIdx, py);
  } else if (uAxis == 2) {
    vox = ivec3(px, uSliceH - 1 - py, sliceIdx);
  } else {
    vox = ivec3(sliceIdx, uSliceH - 1 - py, px);
  }
  int cCoord = (uCutAxis == 0) ? vox.x : ((uCutAxis == 1) ? vox.y : vox.z);
  return (uCutFrontPositive == 1)
    ? (cCoord < uCutVisibleSlices)
    : (cCoord >= (uCutSliceTotal - uCutVisibleSlices));
}

void main() {
  vec2 cur = vTexelPos;
  vec2 stepVec = uRayTexelDelta;
  ivec2 cell = ivec2(floor(cur));
  ivec2 stepDir = ivec2(stepVec.x >= 0.0 ? 1 : -1, stepVec.y >= 0.0 ? 1 : -1);

  vec2 invAbs = vec2(
    abs(stepVec.x) > 1e-6 ? 1.0 / abs(stepVec.x) : 1e9,
    abs(stepVec.y) > 1e-6 ? 1.0 / abs(stepVec.y) : 1e9
  );
  vec2 nextBoundary = vec2(
    stepVec.x >= 0.0 ? (float(cell.x + 1) - cur.x) : (cur.x - float(cell.x)),
    stepVec.y >= 0.0 ? (float(cell.y + 1) - cur.y) : (cur.y - float(cell.y))
  );
  vec2 tMax = nextBoundary * invAbs;

  float tHit = 0.0;
  bool hit = false;
  vec4 hitTexel = vec4(0.0);

  for (int iter = 0; iter < 32; iter++) {
    if (iter >= uMaxDdaSteps) break;
    if (cell.x >= 0 && cell.x < uSliceW && cell.y >= 0 && cell.y < uSliceH) {
      if (isSliceVoxelVisible(cell.x, cell.y, vSliceIndex)) {
        vec4 texel = texelFetch(uStripTex, ivec2(vSliceIndex * uSliceW + cell.x, cell.y), 0);
        if (texel.a >= 0.5) {
          hit = true;
          hitTexel = texel;
          break;
        }
      }
    }
    if (tMax.x < tMax.y) {
      tHit = tMax.x;
      if (tHit > 1.0005) break;
      cell.x += stepDir.x;
      tMax.x += invAbs.x;
    } else {
      tHit = tMax.y;
      if (tHit > 1.0005) break;
      cell.y += stepDir.y;
      tMax.y += invAbs.y;
    }
  }

  if (!hit) discard;

  float hitAdvance = min(tHit, 1.0) * uSlabRayLength;
  gl_FragDepth = clamp(gl_FragCoord.z + hitAdvance * uDepthPerWorldUnit, 0.0, 1.0);
  fragColor = vec4(hitTexel.rgb, 1.0);
  fragMeta = vec4(packDepth16(vDepthWorld + hitAdvance), 1.0, 1.0);
}
`;

const VOXEL_VS = `#version 300 es
precision highp float;
precision highp int;

layout(location = 0) in vec3 aCornerOffset;
layout(location = 1) in vec3 aVoxelCoord;
layout(location = 2) in vec3 aNormal;
layout(location = 3) in vec4 aColorAndFlag;

uniform mat4 uViewProj;
uniform vec3 uVolumeSize;
uniform vec3 uCamBack;
uniform float uExplode;
uniform int uCutAxis;
uniform int uCutSliceTotal;
uniform int uCutVisibleSlices;
uniform int uCutFrontPositive;

out vec3 vColor;
out vec3 vNormal;
out float vDepthWorld;

bool isCoordVisible(ivec3 c) {
  if (c.x < 0 || c.y < 0 || c.z < 0 ||
      c.x >= int(uVolumeSize.x) || c.y >= int(uVolumeSize.y) || c.z >= int(uVolumeSize.z)) {
    return false;
  }
  int v = (uCutAxis == 0) ? c.x : ((uCutAxis == 1) ? c.y : c.z);
  if (uCutFrontPositive == 1) {
    return v < uCutVisibleSlices;
  }
  return v >= (uCutSliceTotal - uCutVisibleSlices);
}

void main() {
  ivec3 voxel = ivec3(floor(aVoxelCoord + 0.5));
  if (!isCoordVisible(voxel)) {
    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
    return;
  }

  if (aColorAndFlag.a > 0.5 && uExplode <= 1.001) {
    ivec3 neighbor = voxel + ivec3(round(aNormal));
    if (isCoordVisible(neighbor)) {
      gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
      return;
    }
  }

  vec3 voxelCenter = (aVoxelCoord + 0.5 - 0.5 * uVolumeSize) * uExplode;
  float cubeScale = (uExplode > 1.001)
    ? mix(1.0, 0.52, clamp((uExplode - 1.0) / 1.0, 0.0, 1.0))
    : 1.0;

  vec3 worldPos = voxelCenter + aCornerOffset * cubeScale;
  vColor = aColorAndFlag.rgb;
  vNormal = aNormal;
  vDepthWorld = -dot(worldPos, uCamBack);
  gl_Position = uViewProj * vec4(worldPos, 1.0);
}
`;

const VOXEL_FS = `#version 300 es
precision highp float;
precision highp int;

in vec3 vColor;
in vec3 vNormal;
in float vDepthWorld;

uniform vec3 uLightDir;
uniform float uShadeStrength;

layout(location = 0) out vec4 fragColor;
layout(location = 1) out vec4 fragMeta;

vec2 packDepth16(float depthWorld) {
  float norm = clamp((depthWorld + 128.0) / 256.0, 0.0, 1.0);
  float scaled = floor(norm * 65535.0 + 0.5);
  float hi = floor(scaled / 256.0);
  float lo = scaled - hi * 256.0;
  return vec2(hi / 255.0, lo / 255.0);
}

void main() {
  float ndotl = dot(normalize(vNormal), uLightDir);
  float studioFactor = mix(0.79, 1.02, ndotl * 0.5 + 0.5);
  vec3 rgb = clamp(vColor * mix(1.0, studioFactor, uShadeStrength), 0.0, 1.0);
  fragColor = vec4(rgb, 1.0);
  fragMeta = vec4(packDepth16(vDepthWorld), 1.0, 1.0);
}
`;

const GRID_VS = `#version 300 es
precision highp float;
precision highp int;
layout(location = 0) in vec3 aPos;
uniform mat4 uViewProj;
uniform float uFloorOffsetY;
void main() {
  gl_Position = uViewProj * vec4(aPos.x, aPos.y + uFloorOffsetY, aPos.z, 1.0);
}
`;

const GRID_FS = `#version 300 es
precision highp float;
precision highp int;
uniform vec4 uGridColor;
layout(location = 0) out vec4 fragColor;
layout(location = 1) out vec4 fragMeta;
void main() {
  fragColor = uGridColor;
  // B=0.0 でキャラクターと明確に分離し、台座グリッド自身に輪郭線が乗ったり靴へ誤段差線が入るのを防ぐ
  fragMeta = vec4(0.0, 0.0, 0.0, 1.0);
}
`;

const POST_VS = `#version 300 es
precision highp float;
precision highp int;
void main() {
  vec2 pos = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  gl_Position = vec4(pos * 2.0 - 1.0, 0.0, 1.0);
}
`;

/**
 * 画面解像度がFBO解像度の非整数倍でもバンディング歪みを起こさない整数 texelFetch 拡大と、
 * 太さ可変の2Dピクセルアート輪郭線（外周シルエット + パーツ重なり深度段差線）を単一ポストパスで合成する。
 */
const POST_FS = `#version 300 es
precision highp float;
precision highp int;

uniform sampler2D uColorTex;
uniform sampler2D uMetaTex;
uniform ivec2 uBlitOrigin;
uniform ivec2 uFboSize;
uniform int uPixelScale;
uniform int uOutlineEnabled;
uniform float uOutlineRadiusF;
uniform int uCreaseEnabled;
uniform int uCreaseRadius;
uniform float uCreaseThreshold;
uniform vec3 uOutlineColor;

out vec4 fragColor;

float unpackDepth16(vec2 rg) {
  float scaled = floor(rg.r * 255.0 + 0.5) * 256.0 + floor(rg.g * 255.0 + 0.5);
  return (scaled / 65535.0) * 256.0 - 128.0;
}

vec4 fetchMetaClamped(ivec2 p) {
  if (p.x < 0 || p.y < 0 || p.x >= uFboSize.x || p.y >= uFboSize.y) {
    return vec4(0.0);
  }
  return texelFetch(uMetaTex, p, 0);
}

void main() {
  ivec2 rel = ivec2(gl_FragCoord.xy) - uBlitOrigin;
  if (rel.x < 0 || rel.y < 0) discard;
  ivec2 fboCoord = rel / uPixelScale;
  if (fboCoord.x < 0 || fboCoord.y < 0 || fboCoord.x >= uFboSize.x || fboCoord.y >= uFboSize.y) {
    discard;
  }

  vec4 c = texelFetch(uColorTex, fboCoord, 0);
  vec4 m = texelFetch(uMetaTex, fboCoord, 0);
  bool isChar = m.b > 0.5;
  bool isOpaque = c.a >= 0.5;

  if (uOutlineEnabled == 1) {
    if (!isChar) {
      bool nearChar = false;
      int rInt = min(6, int(ceil(uOutlineRadiusF)));
      float rSq = uOutlineRadiusF * uOutlineRadiusF;
      for (int dy = -6; dy <= 6; dy++) {
        if (abs(dy) > rInt) continue;
        for (int dx = -6; dx <= 6; dx++) {
          if (abs(dx) > rInt) continue;
          if (dx == 0 && dy == 0) continue;
          if (float(dx * dx + dy * dy) <= rSq) {
            if (fetchMetaClamped(fboCoord + ivec2(dx, dy)).b > 0.5) {
              nearChar = true;
              break;
            }
          }
        }
        if (nearChar) break;
      }
      if (nearChar) {
        fragColor = vec4(uOutlineColor, 1.0);
        return;
      }
    } else if (uCreaseEnabled == 1) {
      // 前景パーツを侵食せず背景側ピクセルのみに段差線を落とし、探索半径を最大2pxへ抑えて太線設定時の顔・瞳ノイズを防ぐ
      float dCenter = unpackDepth16(m.rg);
      int cr = max(1, min(2, uCreaseRadius));
      float maxJump = 0.0;
      ivec2 offsets[4] = ivec2[4](
        ivec2(cr, 0),
        ivec2(-cr, 0),
        ivec2(0, cr),
        ivec2(0, -cr)
      );
      for (int i = 0; i < 4; i++) {
        vec4 nm = fetchMetaClamped(fboCoord + offsets[i]);
        if (nm.b > 0.5) {
          float jump = dCenter - unpackDepth16(nm.rg);
          if (jump > maxJump) maxJump = jump;
        }
      }
      if (maxJump > uCreaseThreshold) {
        float strength = smoothstep(uCreaseThreshold, uCreaseThreshold + 2.5, maxJump) * 0.68;
        fragColor = vec4(mix(c.rgb, uOutlineColor, strength), 1.0);
        return;
      }
    }
  }

  if (!isOpaque) discard;
  fragColor = vec4(c.rgb, 1.0);
}
`;

const FLOOR_GRID_COLORS = {
  dark: [0.27, 0.30, 0.40, 1.0],
  slate: [0.47, 0.50, 0.60, 1.0],
  light: [0.72, 0.69, 0.63, 1.0],
  checker: [0.36, 0.40, 0.53, 1.0],
};

// 原画のトープ輪郭に馴染む柔らかいチャコールトープ（純黒 #000000 の硬すぎる浮きを避ける）
const OUTLINE_INK_RGB = [75 / 255, 66 / 255, 72 / 255];

function compileProgram(gl, vsSource, fsSource) {
  const compile = (type, src) => {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(sh);
      gl.deleteShader(sh);
      throw new Error(`Shader compile error: ${info}`);
    }
    return sh;
  };

  const vs = compile(gl.VERTEX_SHADER, vsSource);
  const fs = compile(gl.FRAGMENT_SHADER, fsSource);
  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  gl.deleteShader(vs);
  gl.deleteShader(fs);

  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    const info = gl.getProgramInfoLog(prog);
    gl.deleteProgram(prog);
    throw new Error(`Program link error: ${info}`);
  }
  return prog;
}

export class Pseudo3DRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    /**
     * MSAAや乗算済みアルファが有効だとドット輪郭に半透明の黒縁・色滲みが生じるため、
     * antialias: false / premultipliedAlpha: false で100% sRGB純色を維持する。
     */
    const gl = canvas.getContext('webgl2', {
      alpha: true,
      premultipliedAlpha: false,
      antialias: false,
      depth: true,
      stencil: false,
      preserveDrawingBuffer: true,
    });
    if (!gl) {
      throw new Error('WebGL2 がサポートされていません。');
    }
    this.gl = gl;

    this.sliceProg = compileProgram(gl, SLICE_VS, SLICE_FS);
    this.voxelProg = compileProgram(gl, VOXEL_VS, VOXEL_FS);
    this.gridProg = compileProgram(gl, GRID_VS, GRID_FS);
    this.postProg = compileProgram(gl, POST_VS, POST_FS);

    this._initQuadVao();
    this.emptyVao = gl.createVertexArray();

    this.stripTextures = { x: null, y: null, z: null };
    this.voxelVao = null;
    this.voxelVbo = null;
    this.voxelCounts = { exteriorVertexCount: 0, totalVertexCount: 0, exteriorFaceCount: 0 };

    this.gridVao = null;
    this.gridVbo = null;
    this.gridVertexCount = 0;

    this.sceneFbo = null;
    this.sceneColorTex = null;
    this.sceneMetaTex = null;
    this.sceneDepthRb = null;
    this.sceneFboW = 0;
    this.sceneFboH = 0;

    this.asset = null;
    this.currentActiveAxis = 'z';
    this.lastFrameMetrics = null;
  }

  _initQuadVao() {
    const gl = this.gl;
    const vao = gl.createVertexArray();
    const vbo = gl.createBuffer();
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    const quadVerts = new Float32Array([
      0, 0,
      1, 0,
      1, 1,
      0, 0,
      1, 1,
      0, 1,
    ]);
    gl.bufferData(gl.ARRAY_BUFFER, quadVerts, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
    this.quadVao = vao;
  }

  _uploadStripTexture(stripObj) {
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);

    // ブラウザのICCカラープロファイル変換で原画PNGのHEX値が変わるのを防ぐため NONE を指定
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);

    if (stripObj.image) {
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, stripObj.image);
    } else {
      gl.texImage2D(
        gl.TEXTURE_2D,
        0,
        gl.RGBA8,
        stripObj.width,
        stripObj.height,
        0,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        stripObj.data
      );
    }

    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.bindTexture(gl.TEXTURE_2D, null);
    return tex;
  }

  _buildFloorGrid(size) {
    const gl = this.gl;
    const yFloor = -size.y * 0.5 - 0.15;
    const radius = Math.max(size.x, size.z) * 0.68;
    const verts = [];

    const segs = 48;
    for (let i = 0; i < segs; i++) {
      const a0 = (i / segs) * Math.PI * 2;
      const a1 = ((i + 1) / segs) * Math.PI * 2;
      verts.push(
        Math.cos(a0) * radius, yFloor, Math.sin(a0) * radius,
        Math.cos(a1) * radius, yFloor, Math.sin(a1) * radius
      );
    }

    const step = 4;
    const half = Math.ceil(radius / step) * step;
    for (let g = -half; g <= half; g += step) {
      const span = Math.sqrt(Math.max(0, radius * radius - g * g));
      if (span > 0.5) {
        verts.push(-span, yFloor, g, span, yFloor, g);
        verts.push(g, yFloor, -span, g, yFloor, span);
      }
    }

    if (!this.gridVao) {
      this.gridVao = gl.createVertexArray();
      this.gridVbo = gl.createBuffer();
    }
    gl.bindVertexArray(this.gridVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.gridVbo);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(verts), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);
    this.gridVertexCount = verts.length / 3;
  }

  setAsset(asset) {
    const gl = this.gl;
    this.asset = asset;

    for (const k of ['x', 'y', 'z']) {
      if (this.stripTextures[k]) gl.deleteTexture(this.stripTextures[k]);
      this.stripTextures[k] = this._uploadStripTexture(asset.strips[k]);
    }

    const mesh = buildVoxelMeshBuffers(asset.size, asset.paletteRgb, asset.voxels);
    this.voxelCounts = mesh;

    if (!this.voxelVao) {
      this.voxelVao = gl.createVertexArray();
      this.voxelVbo = gl.createBuffer();
    }
    gl.bindVertexArray(this.voxelVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.voxelVbo);
    gl.bufferData(gl.ARRAY_BUFFER, mesh.buffer, gl.STATIC_DRAW);

    const stride = 40;
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, stride, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, stride, 12);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 24);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 4, gl.UNSIGNED_BYTE, true, stride, 36);
    gl.bindVertexArray(null);

    this._buildFloorGrid(asset.size);
  }

  _ensureSceneFbo(w, h) {
    const gl = this.gl;
    if (this.sceneFbo && this.sceneFboW === w && this.sceneFboH === h) return;

    if (this.sceneFbo) gl.deleteFramebuffer(this.sceneFbo);
    if (this.sceneColorTex) gl.deleteTexture(this.sceneColorTex);
    if (this.sceneMetaTex) gl.deleteTexture(this.sceneMetaTex);
    if (this.sceneDepthRb) gl.deleteRenderbuffer(this.sceneDepthRb);

    this.sceneFboW = w;
    this.sceneFboH = h;

    const createRgbaTex = () => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      return tex;
    };

    const colorTex = createRgbaTex();
    const metaTex = createRgbaTex();

    const depthRb = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, depthRb);
    gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, w, h);

    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, colorTex, 0);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT1, gl.TEXTURE_2D, metaTex, 0);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depthRb);
    gl.drawBuffers([gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1]);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);

    this.sceneFbo = fbo;
    this.sceneColorTex = colorTex;
    this.sceneMetaTex = metaTex;
    this.sceneDepthRb = depthRb;
  }

  resizeIfNeeded() {
    // 125%拡大等の小数DPR環境では clientWidth が整数丸めされるため、getBoundingClientRect の実CSS幅から描画バッファを算出する
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = this.canvas.getBoundingClientRect();
    const cssW = rect.width > 0 ? rect.width : this.canvas.clientWidth;
    const cssH = rect.height > 0 ? rect.height : this.canvas.clientHeight;
    const displayW = Math.max(1, Math.round(cssW * dpr));
    const displayH = Math.max(1, Math.round(cssH * dpr));
    if (this.canvas.width !== displayW || this.canvas.height !== displayH) {
      this.canvas.width = displayW;
      this.canvas.height = displayH;
    }
  }

  render(camera, state) {
    if (!this.asset) return null;
    this.resizeIfNeeded();

    const gl = this.gl;
    const canvasW = this.canvas.width;
    const canvasH = this.canvas.height;
    let basis = camera.getBasis();

    // 従来型Y-Stack（Mode 2）では水平0°でXZ平面ポリゴンが面積ゼロに退化して完全消失するため、
    // ごく微小な見下ろし角（3.2°）を下限として従来のブラインド状の層隙間・押し出し比較を視認可能にする
    if (state.mode === 'classic-y' && Math.abs(camera.pitchDeg) < 3.2) {
      const grazedPitch = camera.pitchDeg >= 0 ? 3.2 : -3.2;
      basis = computeCameraBasis(camera.yawDeg * DEG_TO_RAD, grazedPitch * DEG_TO_RAD);
    }

    const dominantAxis = selectDominantAxis(basis.back, this.currentActiveAxis);
    this.currentActiveAxis = dominantAxis;

    const subdiv = state.pixelSnapSubdiv || 0;
    const useLowResSnap = subdiv > 0;

    let renderW = canvasW;
    let renderH = canvasH;
    const aspect = canvasW / Math.max(1, canvasH);
    const baseSpan = camera.baseOrthoHeight / camera.zoom;
    // 縦長モバイル画面で高さ基準のまま投影すると横幅が狭まりツインテール左右端が見切れるため、最小横幅も保証する
    const desiredOrthoH = aspect < 1.0 ? baseSpan / Math.max(0.42, aspect) : baseSpan;
    let orthoH = desiredOrthoH;
    let orthoW = orthoH * aspect;
    let pixelScale = 1;
    let blitOriginX = 0;
    let blitOriginY = 0;

    // パン移動時もドット角スナップ中はピクセルグリッド単位へ量子化してサブピクセルのチラつきを防ぐ
    let panX = camera.panX;
    let panY = camera.panY;

    if (useLowResSnap) {
      pixelScale = Math.max(1, Math.round(canvasH / (desiredOrthoH * subdiv)));
      renderW = Math.max(16, Math.ceil(canvasW / pixelScale));
      renderH = Math.max(16, Math.ceil(canvasH / pixelScale));
      // 偶数解像度に揃えることで、中心座標 0.0 が常にピクセル境界に乗るため正面0°での0.5px跨ぎボケを防ぐ
      if (renderW % 2 !== 0) renderW += 1;
      if (renderH % 2 !== 0) renderH += 1;

      const texelWorld = 1.0 / subdiv;
      orthoW = renderW * texelWorld;
      orthoH = renderH * texelWorld;

      panX = Math.round(panX / texelWorld) * texelWorld;
      panY = Math.round(panY / texelWorld) * texelWorld;

      blitOriginX = Math.floor((canvasW - renderW * pixelScale) * 0.5);
      blitOriginY = Math.floor((canvasH - renderH * pixelScale) * 0.5);
    }

    this._ensureSceneFbo(renderW, renderH);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.sceneFbo);
    gl.drawBuffers([gl.COLOR_ATTACHMENT0, gl.COLOR_ATTACHMENT1]);

    const target = [
      basis.right[0] * panX + basis.up[0] * panY,
      basis.right[1] * panX + basis.up[1] * panY,
      basis.right[2] * panX + basis.up[2] * panY,
    ];

    // 1x等倍スナップかつボリューム寸法が奇数の軸は、正面・真横0°で1:1一致するよう半ボクセル位相を合わせる
    let frustumShiftX = 0;
    let frustumShiftY = 0;
    if (subdiv === 1) {
      if (Math.abs(basis.back[2]) > 0.999) {
        frustumShiftX = (this.asset.size.x % 2) * 0.5;
        frustumShiftY = (this.asset.size.y % 2) * 0.5;
      } else if (Math.abs(basis.back[0]) > 0.999) {
        frustumShiftX = (this.asset.size.z % 2) * 0.5;
        frustumShiftY = (this.asset.size.y % 2) * 0.5;
      }
    }

    gl.viewport(0, 0, renderW, renderH);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.disable(gl.BLEND);

    const maxExtent = Math.max(this.asset.size.x, this.asset.size.y, this.asset.size.z) * state.explode * 2.5 + 80;
    const distance = maxExtent;
    const nearPlane = 1.0;
    const farPlane = maxExtent * 2.5;
    const depthPerWorldUnit = 1.0 / (farPlane - nearPlane);

    const viewMat = createViewMatrix(basis, target, distance);
    const projMat = createOrthoMatrix(
      -orthoW * 0.5 + frustumShiftX,
      orthoW * 0.5 + frustumShiftX,
      -orthoH * 0.5 + frustumShiftY,
      orthoH * 0.5 + frustumShiftY,
      nearPlane,
      farPlane
    );
    const viewProj = multiplyMat4(projMat, viewMat);

    if (state.showGrid && this.gridVertexCount > 0) {
      /**
       * ポストパスはドット輪郭の半透明フリンジを防ぐため a < 0.5 を破棄する仕様である。
       * 半透明ブレンドでFBOに描くとアルファ値が閾値未満となって消失するため、背景テーマ別の不透明色（a=1.0）+深度テストで描画する。
       */
      const gCol = FLOOR_GRID_COLORS[state.bg] || FLOOR_GRID_COLORS.dark;
      const floorDrop = -(state.explode - 1.0) * this.asset.size.y * 0.5;
      gl.useProgram(this.gridProg);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.gridProg, 'uViewProj'), false, viewProj);
      gl.uniform1f(gl.getUniformLocation(this.gridProg, 'uFloorOffsetY'), floorDrop);
      gl.uniform4f(gl.getUniformLocation(this.gridProg, 'uGridColor'), gCol[0], gCol[1], gCol[2], 1.0);
      gl.bindVertexArray(this.gridVao);
      gl.drawArrays(gl.LINES, 0, this.gridVertexCount);
      gl.bindVertexArray(null);
    }

    const axisKeyToInt = { x: 0, y: 1, z: 2 };
    const cutAxisKey = state.cutAxis === 'auto'
      ? (state.mode === 'classic-y' ? 'y' : dominantAxis)
      : state.cutAxis;
    const cutAxisInt = axisKeyToInt[cutAxisKey];
    const cutTotal = cutAxisInt === 0
      ? this.asset.size.x
      : cutAxisInt === 1
        ? this.asset.size.y
        : this.asset.size.z;
    const cutFrontPositive = state.cutAxis === 'auto'
      ? (basis.back[cutAxisInt] >= 0 ? 1 : 0)
      : 1;
    const effectiveCutaway = state.cutaway / 100;
    const cutVisibleSlices = effectiveCutaway <= 0.0001
      ? cutTotal
      : Math.max(1, Math.round(cutTotal * (1 - effectiveCutaway)));

    this.lastFrameMetrics = {
      canvasW,
      canvasH,
      renderW,
      renderH,
      blitOriginX,
      blitOriginY,
      pixelScale,
      orthoW,
      orthoH,
      frustumShiftX,
      frustumShiftY,
      basis,
      target,
      distance,
      cutAxisInt,
      cutTotal,
      cutVisibleSlices,
      cutFrontPositive,
      explode: state.explode,
    };

    let telemetrySlicesText = `${cutVisibleSlices} / ${cutTotal}`;
    let hudAxisKey = dominantAxis;

    if (state.mode === 'tri' || state.mode === 'classic-y') {
      const stackKey = state.mode === 'classic-y' ? 'y' : dominantAxis;
      hudAxisKey = stackKey;
      const axisInt = axisKeyToInt[stackKey];
      const strip = this.asset.strips[stackKey];
      const totalSlices = strip.count;
      const frontPositive = basis.back[axisInt] >= 0 ? 1 : 0;

      let slabThickness = 1.0;
      if (state.mode === 'classic-y' && !state.classicExtrude) {
        slabThickness = 0.08;
      } else if (state.explode > 1.01) {
        // 分解スライダ操作時に斜め視点で隣接スライスの押し出し厚みが癒着して見えるのを防ぐため、1.0x超では急速に薄層シートへ絞る
        const t = Math.min(1.0, (state.explode - 1.0) / 0.45);
        slabThickness = 1.0 - t * 0.88;
      }

      const cosNormal = Math.max(0.04, Math.abs(basis.back[axisInt]));
      const slabRayLength = slabThickness / cosNormal;
      const rayDirX = -basis.back[0];
      const rayDirY = -basis.back[1];
      const rayDirZ = -basis.back[2];

      let dU;
      let dV;
      if (axisInt === 1) {
        dU = rayDirX * slabRayLength;
        dV = rayDirZ * slabRayLength;
      } else if (axisInt === 2) {
        dU = rayDirX * slabRayLength;
        dV = -rayDirY * slabRayLength;
      } else {
        dU = rayDirZ * slabRayLength;
        dV = -rayDirY * slabRayLength;
      }

      const maxSpan = Math.max(Math.abs(dU), Math.abs(dV));
      const padTexels = Math.min(20.0, Math.ceil(maxSpan) + 1.0);
      const maxDdaSteps = Math.min(32, Math.max(4, Math.ceil(Math.abs(dU) + Math.abs(dV)) + 3));

      // カット軸とアクティブ積層軸が一致する場合はインスタンス数そのものを削減して無駄なオーバードローを省く
      let instanceSliceCount = totalSlices;
      let sliceOffset = 0;
      if (cutAxisInt === axisInt && effectiveCutaway > 0.0001) {
        instanceSliceCount = cutVisibleSlices;
        if (cutFrontPositive !== frontPositive) {
          sliceOffset = totalSlices - cutVisibleSlices;
        }
      }

      // 両面（+軸側・-軸側の両方）から同一のクアッドを見るため背面カリングは無効化する
      gl.disable(gl.CULL_FACE);
      gl.useProgram(this.sliceProg);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.sliceProg, 'uViewProj'), false, viewProj);
      gl.uniform3f(
        gl.getUniformLocation(this.sliceProg, 'uVolumeSize'),
        this.asset.size.x,
        this.asset.size.y,
        this.asset.size.z
      );
      gl.uniform3f(
        gl.getUniformLocation(this.sliceProg, 'uCamBack'),
        basis.back[0],
        basis.back[1],
        basis.back[2]
      );
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uAxis'), axisInt);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uSliceCount'), totalSlices);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uSliceOffset'), sliceOffset);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uFrontPositive'), frontPositive);
      gl.uniform1f(gl.getUniformLocation(this.sliceProg, 'uExplode'), state.explode);
      gl.uniform1f(gl.getUniformLocation(this.sliceProg, 'uSlabThickness'), slabThickness);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uSliceW'), strip.sliceWidth);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uSliceH'), strip.sliceHeight);
      gl.uniform1f(gl.getUniformLocation(this.sliceProg, 'uPadTexels'), padTexels);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uCutAxis'), cutAxisInt);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uCutSliceTotal'), cutTotal);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uCutVisibleSlices'), cutVisibleSlices);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uCutFrontPositive'), cutFrontPositive);
      gl.uniform2f(gl.getUniformLocation(this.sliceProg, 'uRayTexelDelta'), dU, dV);
      gl.uniform1f(gl.getUniformLocation(this.sliceProg, 'uSlabRayLength'), slabRayLength);
      gl.uniform1f(gl.getUniformLocation(this.sliceProg, 'uDepthPerWorldUnit'), depthPerWorldUnit);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uMaxDdaSteps'), maxDdaSteps);

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.stripTextures[stackKey]);
      gl.uniform1i(gl.getUniformLocation(this.sliceProg, 'uStripTex'), 0);

      gl.bindVertexArray(this.quadVao);
      gl.drawArraysInstanced(gl.TRIANGLES, 0, 6, instanceSliceCount);
      gl.bindVertexArray(null);

      if (cutAxisInt !== axisInt) {
        telemetrySlicesText = `${totalSlices} (${cutAxisKey.toUpperCase()}断面 ${cutVisibleSlices}/${cutTotal})`;
      }
    } else {
      hudAxisKey = 'voxel';
      // ワールド固定光源では背面180°へ回した際に白いドレスが暗く沈むため、カメラ追従型のスタジオキーライトを採用する
      const lx = basis.right[0] * 0.35 + basis.up[0] * 0.62 + basis.back[0] * 0.70;
      const ly = basis.right[1] * 0.35 + basis.up[1] * 0.62 + basis.back[1] * 0.70;
      const lz = basis.right[2] * 0.35 + basis.up[2] * 0.62 + basis.back[2] * 0.70;
      const lLen = Math.hypot(lx, ly, lz) || 1;

      gl.enable(gl.CULL_FACE);
      gl.cullFace(gl.BACK);
      gl.useProgram(this.voxelProg);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.voxelProg, 'uViewProj'), false, viewProj);
      gl.uniform3f(
        gl.getUniformLocation(this.voxelProg, 'uVolumeSize'),
        this.asset.size.x,
        this.asset.size.y,
        this.asset.size.z
      );
      gl.uniform3f(
        gl.getUniformLocation(this.voxelProg, 'uCamBack'),
        basis.back[0],
        basis.back[1],
        basis.back[2]
      );
      gl.uniform1f(gl.getUniformLocation(this.voxelProg, 'uExplode'), state.explode);
      gl.uniform1i(gl.getUniformLocation(this.voxelProg, 'uCutAxis'), cutAxisInt);
      gl.uniform1i(gl.getUniformLocation(this.voxelProg, 'uCutSliceTotal'), cutTotal);
      gl.uniform1i(gl.getUniformLocation(this.voxelProg, 'uCutVisibleSlices'), cutVisibleSlices);
      gl.uniform1i(gl.getUniformLocation(this.voxelProg, 'uCutFrontPositive'), cutFrontPositive);
      gl.uniform3f(gl.getUniformLocation(this.voxelProg, 'uLightDir'), lx / lLen, ly / lLen, lz / lLen);
      gl.uniform1f(gl.getUniformLocation(this.voxelProg, 'uShadeStrength'), state.shading / 100);

      gl.bindVertexArray(this.voxelVao);
      const useAllVerts = state.explode > 1.001 || state.cutaway > 0;
      const vertCount = useAllVerts
        ? this.voxelCounts.totalVertexCount
        : this.voxelCounts.exteriorVertexCount;
      gl.drawArrays(gl.TRIANGLES, 0, vertCount);
      gl.bindVertexArray(null);
      gl.disable(gl.CULL_FACE);
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvasW, canvasH);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.disable(gl.DEPTH_TEST);

    const pxPerVoxel = canvasH / Math.max(1, desiredOrthoH);
    const widthParam = state.outlineWidth ?? 1.5;
    let outlineRadiusF;
    if (!useLowResSnap) {
      outlineRadiusF = Math.min(6.0, Math.max(1.01, widthParam * (pxPerVoxel / 7.5)));
    } else if (subdiv === 1) {
      outlineRadiusF = Math.min(3.2, Math.max(1.01, 0.78 + widthParam * 0.46));
    } else if (subdiv === 2) {
      outlineRadiusF = Math.min(4.2, Math.max(1.01, 0.65 + widthParam * 0.68));
    } else {
      outlineRadiusF = Math.min(5.2, Math.max(1.01, 0.55 + widthParam * 1.00));
    }

    // 分解スライダ操作中はスライス間の段差に大量の内部線が乗って見づらくなるため、外周シルエットのみ残し内部段差線は止める
    const creaseEnabled = state.outline && state.explode <= 1.05 ? 1 : 0;
    const creaseRadius = Math.max(1, Math.min(2, Math.round(outlineRadiusF * 0.55)));

    gl.useProgram(this.postProg);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.sceneColorTex);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uColorTex'), 0);

    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, this.sceneMetaTex);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uMetaTex'), 1);

    gl.uniform2i(gl.getUniformLocation(this.postProg, 'uBlitOrigin'), blitOriginX, blitOriginY);
    gl.uniform2i(gl.getUniformLocation(this.postProg, 'uFboSize'), renderW, renderH);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uPixelScale'), pixelScale);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uOutlineEnabled'), state.outline ? 1 : 0);
    gl.uniform1f(gl.getUniformLocation(this.postProg, 'uOutlineRadiusF'), outlineRadiusF);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uCreaseEnabled'), creaseEnabled);
    gl.uniform1i(gl.getUniformLocation(this.postProg, 'uCreaseRadius'), creaseRadius);
    gl.uniform1f(gl.getUniformLocation(this.postProg, 'uCreaseThreshold'), 3.2);
    gl.uniform3f(
      gl.getUniformLocation(this.postProg, 'uOutlineColor'),
      OUTLINE_INK_RGB[0],
      OUTLINE_INK_RGB[1],
      OUTLINE_INK_RGB[2]
    );

    gl.bindVertexArray(this.emptyVao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);

    return {
      activeAxis: hudAxisKey,
      dominantAxis,
      slicesText: telemetrySlicesText,
      basis,
      pixelScale,
    };
  }
}
