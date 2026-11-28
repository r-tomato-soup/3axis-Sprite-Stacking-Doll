"""
新キャラクター（黒髪ハーフツイン×片方はだけ黒パーカー萌え袖×左右非対称ニーハイ＆白絆創膏×厚底靴）
3Dボクセル・3軸スライス・拡張Modジェネレーター

- グリッド: 58 x 56 x 42（最大ストリップ幅 56*58=3248 <= 4096、モバイルWebGL2安全圏）
- ベース: 下向きショート・ハーフツイン + アホ毛 + ばってん＆白うさぎヘアピン + フラット接地厚底靴
- 拡張Mods:
  - beret (黒ベレー帽: 斜め深め被り、アホ毛と差し替え、全髪型と組み合わせ可能)
  - hair_flare (高め外ハネショート, group="hair_style")
  - hair_twin_high (高め腰丈ツインテ＋ハート十字リボン, group="hair_style")
  - hair_twin_arc (細身軽やかカーブツインテ, group="hair_style")
"""

from __future__ import annotations
from collections import deque
import json
import math
import os
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets", "char3")

W, H, D = 58, 56, 42

# 二次元リッチな色相シフトパレット（外周黒枠は焼き込まず後加工2Dアウトラインへ委譲）
PALETTE_HEX = [
    "#262030",  # 0: C_HAIR_SH2 (黒髪 深影・毛束割れ)
    "#352E42",  # 1: C_HAIR_SH1 (黒髪 影)
    "#473E58",  # 2: C_HAIR (黒髪 ベース)
    "#625777",  # 3: C_HAIR_HI (黒髪 天使の輪・明部)
    "#82769A",  # 4: C_HAIR_SPEC (黒髪 ツヤ芯)
    "#FDF8F3",  # 5: C_SKIN (肌ベース・Char2準拠)
    "#EEE0D6",  # 6: C_SKIN_SH (肌影・顎下・脚影・Char2準拠)
    "#F2D8D7",  # 7: C_BLUSH_LIGHT (淡チーク・Char2準拠)
    "#E8C6C8",  # 8: C_BLUSH_DEEP (濃チーク・Char2準拠)
    "#5F5763",  # 9: C_EYE_LASH (ジト目まつ毛バー・Char2準拠)
    "#8D84A8",  # 10: C_EYE_HIGH (瞳上段ラベンダーバイオレット・Char2準拠)
    "#B9B2D0",  # 11: C_EYE_LOW (瞳中段ラベンダー・Char2準拠)
    "#D8D3EA",  # 12: C_EYE_WHITE (瞳下部・目頭淡ラベンダー光沢・Char2準拠)
    "#23212E",  # 13: C_DARK (パーカー深影・靴底・ガーターストラップ)
    "#323041",  # 14: C_HOODIE_SH (パーカー影・ニーハイ本体・厚底側面)
    "#454357",  # 15: C_HOODIE (パーカーベース・革靴ベース)
    "#5E5B73",  # 16: C_HOODIE_HI (萌え袖膨らみ・ベレー明部・ソール縁)
    "#7B7792",  # 17: C_HOODIE_SPEC (エナメル靴艶・ベレー光沢)
    "#9490A1",  # 18: C_GRAY_SH (グレーインナー影・銀暗)
    "#BEBACB",  # 19: C_GRAY (グレーインナー本体・銀金具)
    "#E2E0EC",  # 20: C_GRAY_HI (グレーインナー明・銀光沢)
    "#FAF8FD",  # 21: C_WHITE (白うさぎ・ばってん・白絆創膏・白レース・十字架)
    "#D6D0E2",  # 22: C_WHITE_SH (白アクセ影・白絆創膏枠)
    "#42384E",  # 23: C_ACC_DARK (うさぎ目ドット・細部引き締め)
    "#E8AEC2",  # 24: C_PINK_BAND (白絆創膏の中央ピンクガーゼ)
    "#C49EDE",  # 25: C_LAVENDER_GEM (ツインテリボン中央の淡紫ハート宝石)
    "#FFFFFF",  # 26: C_EYE_SPARKLE (瞳純白ハイライト・Char2準拠)
]

(
    C_HAIR_SH2,
    C_HAIR_SH1,
    C_HAIR,
    C_HAIR_HI,
    C_HAIR_SPEC,
    C_SKIN,
    C_SKIN_SH,
    C_BLUSH_LIGHT,
    C_BLUSH_DEEP,
    C_EYE_LASH,
    C_EYE_HIGH,
    C_EYE_LOW,
    C_EYE_WHITE,
    C_DARK,
    C_HOODIE_SH,
    C_HOODIE,
    C_HOODIE_HI,
    C_HOODIE_SPEC,
    C_GRAY_SH,
    C_GRAY,
    C_GRAY_HI,
    C_WHITE,
    C_WHITE_SH,
    C_ACC_DARK,
    C_PINK_BAND,
    C_LAVENDER_GEM,
    C_EYE_SPARKLE,
) = range(len(PALETTE_HEX))

PARTS_DEF = [
    {"id": "hair", "label": "髪"},
    {"id": "skin", "label": "肌・顔"},
    {"id": "eyes", "label": "目"},
    {"id": "outfit", "label": "パーカー・服"},
    {"id": "socks", "label": "タイツ・靴下"},
    {"id": "shoes", "label": "厚底靴"},
    {"id": "accessories", "label": "アクセ・リボン"},
    {"id": "beret", "label": "黒ベレー帽"},
]

(
    P_HAIR,
    P_SKIN,
    P_EYES,
    P_OUTFIT,
    P_SOCKS,
    P_SHOES,
    P_ACC,
    P_BERET,
) = range(len(PARTS_DEF))

CX = (W - 1) * 0.5  # 28.5 (Char2 cx0=25.5 に対し厳密に +3.0)
CZ_BODY = 20.5
# Char2 cz_head=19.6 に対し厳密な整数シフト(+1.0)に合わせ、頭・顔・前髪・目のボクセル丸めを完全一致させる
CZ_HEAD = 20.6


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(e0: float, e1: float, x: float) -> float:
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def catmull_rom_interp(points: list[tuple[float, float]], y_q: float) -> float:
    if y_q <= points[0][0]:
        return points[0][1]
    if y_q >= points[-1][0]:
        return points[-1][1]
    for i in range(len(points) - 1):
        y0, v0 = points[i]
        y1, v1 = points[i + 1]
        if y0 <= y_q <= y1:
            t = (y_q - y0) / (y1 - y0)
            p_prev = points[max(0, i - 1)][1]
            p_next = points[min(len(points) - 1, i + 2)][1]
            t2 = t * t
            t3 = t2 * t
            return 0.5 * (
                (2.0 * v0)
                + (-p_prev + v1) * t
                + (2.0 * p_prev - 5.0 * v0 + 4.0 * v1 - p_next) * t2
                + (-p_prev + 3.0 * v0 - 3.0 * v1 + p_next) * t3
            )
    return points[-1][1]


def interp_profile(pts: list[tuple[float, float]], y: float) -> float:
    if y <= pts[0][0]:
        return pts[0][1]
    if y >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        y0, v0 = pts[i]
        y1, v1 = pts[i + 1]
        if y0 <= y <= y1:
            t = (y - y0) / (y1 - y0)
            return v0 + (v1 - v0) * t
    return pts[-1][1]


def new_grid() -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    part = [[[-1] * D for _ in range(H)] for _ in range(W)]
    return vol, part


def set_vox(vol: list, part: list, x: int, y: int, z: int, c: int, p: int) -> None:
    if 0 <= x < W and 0 <= y < H and 0 <= z < D:
        vol[x][y][z] = c
        part[x][y][z] = p


def build_body_v4(vol: list, part: list) -> None:
    """
    v4 体格モデル:
    - キャラ2基準の華奢な肩幅(外側~6.1vox)・細身の胴体＆スカートで着ぶくれを解消
    - 厚底靴(y=0..3)と脚(y=4..10)をコンパクト化して腰位置を2px下げ、パーカー丈(y=13..25, 13vox)をゆとりあるバランスへ
    - 左肩はだけインナー＆V開き胸元を物理的に約1.1vox凹ませ、黒パーカー外殻との明確な3D段差を造形
    - ネックラインを広く開け、独立2行の首(y=26..27)で斜め俯瞰でも首がしっかり見えるよう+1px確保
    """
    # ==========================================================================
    # 1. コンパクト厚底プラットフォームゴス靴 (y=0..3) — フラット接地＆銀ハートバックル維持
    # ==========================================================================
    leg_dx = 3.65
    for side in (-1.0, 1.0):
        lx = CX + side * leg_dx
        for y in range(0, 4):
            if y <= 1:
                rx_s = 2.85
                rz_f = 4.10
                rz_b = 2.85
                cz_s = CZ_BODY + 0.65
                for x in range(W):
                    if abs(x - CX) < 0.80:
                        continue
                    for z in range(D):
                        dx = x - lx
                        dz = z - cz_s
                        rz = rz_f if dz >= 0 else rz_b
                        nx = abs(dx) / rx_s
                        nz = abs(dz) / rz
                        d_s = (nx ** 4.2 + nz ** 4.2) ** (1.0 / 4.2)
                        if d_s <= 1.0:
                            if y == 0:
                                col = C_DARK
                            else:
                                col = C_HOODIE_HI if (d_s > 0.78 and dz > -2.0) else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            elif y == 2:
                rx_u = 2.68
                rz_f = 3.65
                rz_b = 2.68
                cz_s = CZ_BODY + 0.45
                for x in range(W):
                    if abs(x - CX) < 0.80:
                        continue
                    for z in range(D):
                        dx = x - lx
                        dz = z - cz_s
                        rz = rz_f if dz >= 0 else rz_b
                        nx = abs(dx) / rx_u
                        nz = abs(dz) / rz
                        d_u = (nx ** 2.8 + nz ** 2.8) ** (1.0 / 2.8)
                        if d_u <= 1.0:
                            if dz > 0.9 and (-1.5 <= dx <= 0.5):
                                col = C_HOODIE_SPEC
                            elif dz > 0.1:
                                col = C_HOODIE
                            else:
                                col = C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            else:
                rx_a = 2.48
                rz_a = 2.60
                cz_a = CZ_BODY + 0.15
                for x in range(W):
                    if abs(x - CX) < 0.85:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_a
                        nz = (z - cz_a) / rz_a
                        if nx * nx + nz * nz <= 1.0:
                            col = C_HOODIE_HI if z >= cz_a + 0.5 else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)

        # 銀ハートバックル (y=1..3)
        hx_c = int(round(lx))
        for y_h, offsets in (
            (3, [(-1, C_GRAY_HI), (1, C_GRAY_HI)]),
            (2, [(-1, C_WHITE), (0, C_GRAY), (1, C_WHITE)]),
            (1, [(0, C_GRAY_HI)]),
        ):
            for ox, c_h in offsets:
                vx = hx_c + ox
                front_z = -1
                for z in range(D - 1, -1, -1):
                    if vol[vx][y_h][z] != -1:
                        front_z = z
                        break
                if front_z >= 0:
                    set_vox(vol, part, vx, y_h, front_z, c_h, P_SHOES)
                    set_vox(vol, part, vx, y_h, front_z - 1, c_h, P_SHOES)
                    if ox != 0 or y_h == 1:
                        set_vox(vol, part, vx, y_h, front_z + 1, c_h, P_SHOES)

    # ==========================================================================
    # 2. 華奢な両脚・左右非対称ニーハイ＆フリル・ガーターリング・白ピンク絆創膏 (y=4..13)
    #    スカート裾(y=11)下の露出脚は7vox、靴込み11voxで腰を低く可愛く見せる
    # ==========================================================================
    for y in range(4, 14):
        for side in (-1.0, 1.0):
            lx = CX + side * leg_dx
            t_leg = (y - 4.0) / 9.0
            rx_l = 1.98 + 0.28 * smoothstep(0.20, 0.90, t_leg)
            rz_l = 2.12 + 0.28 * smoothstep(0.20, 0.90, t_leg)

            for x in range(W):
                if abs(x - CX) < 1.05:
                    continue
                for z in range(D):
                    dx = x - lx
                    dz = z - CZ_BODY
                    nx = dx / rx_l
                    nz = dz / rz_l
                    if nx * nx + nz * nz <= 1.0:
                        if side < 0:
                            if y <= 8:
                                if dz >= 0.35 and -1.3 <= dx <= -0.1:
                                    col = C_HOODIE_HI if 5 <= y <= 7 else C_HOODIE
                                elif dz >= -0.35:
                                    col = C_HOODIE_SH
                                else:
                                    col = C_DARK
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                col = C_SKIN_SH if (y >= 12 or dz < -0.5 or dx > 1.0) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)
                        else:
                            if y == 4:
                                col = C_HOODIE_HI if dz > 0.2 else C_HOODIE_SH
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                col = C_SKIN_SH if (y >= 12 or dz < -0.5 or dx < -1.0) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)

    # 左脚ディテール: フリル帯(y=8) + 白レース上縁(y=9) + 外側黒リボン + ガーターストラップ(y=9..13) + 白十字(y=5..7)
    lx_l = CX - leg_dx
    for y_f in (8, 9):
        rx_f = 2.62 if y_f == 8 else 2.54
        rz_f = 2.72 if y_f == 8 else 2.64
        for x in range(W):
            if abs(x - CX) < 0.95:
                continue
            for z in range(D):
                dx = x - lx_l
                dz = z - CZ_BODY
                ang = math.atan2(dz, dx)
                scallop = 0.20 * math.cos(8.0 * ang)
                rad = math.sqrt((dx / (rx_f + scallop)) ** 2 + (dz / (rz_f + scallop)) ** 2)
                if 0.72 <= rad <= 1.0:
                    if y_f == 9:
                        if math.cos(8.0 * ang) > -0.1:
                            set_vox(vol, part, x, y_f, z, C_WHITE_SH if dz < 0 else C_WHITE, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_f, z, C_HOODIE_HI if (dz > 0 and math.cos(8.0 * ang) > 0) else C_HOODIE_SH, P_SOCKS)

    rib_x = int(round(lx_l - 2.6))
    rib_z = int(round(CZ_BODY + 0.4))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_DARK)):
        set_vox(vol, part, rib_x, 8 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_x, 8 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy == -1:
            set_vox(vol, part, rib_x - 1, 8 + dy, rib_z, c_r, P_SOCKS)

    sx_l = int(round(lx_l))
    for y_st in range(9, 14):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_st][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            col_st = C_GRAY_HI if y_st == 9 else C_DARK
            set_vox(vol, part, sx_l, y_st, front_z, col_st, P_SOCKS)
            set_vox(vol, part, sx_l, y_st, front_z + 1, col_st, P_SOCKS)

    for y_c in (5, 6, 7):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_c][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            set_vox(vol, part, sx_l, y_c, front_z, C_WHITE, P_SOCKS)

    # 右脚ディテール: 黒ガーターリング(y=6..7) + 外側リボン + 白ピンク絆創膏(y=8..10)
    lx_r = CX + leg_dx
    for y_g in (6, 7):
        rx_g = 2.62 if y_g == 7 else 2.55
        rz_g = 2.72 if y_g == 7 else 2.65
        for x in range(W):
            if abs(x - CX) < 0.95:
                continue
            for z in range(D):
                dx = x - lx_r
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_g) ** 2 + (dz / rz_g) ** 2)
                if 0.72 <= rad <= 1.0:
                    if y_g == 6 and dz > -0.5 and int(round(abs(dx) + abs(dz))) % 2 == 0:
                        set_vox(vol, part, x, y_g, z, C_WHITE_SH, P_SOCKS)
                    elif y_g == 7:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_HI if dz > 0.3 else C_HOODIE_SH, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_SH if dz > -0.5 else C_DARK, P_SOCKS)

    sx_r = int(round(lx_r))
    for z in range(D - 1, -1, -1):
        if vol[sx_r][7][z] != -1:
            set_vox(vol, part, sx_r, 7, z, C_GRAY_HI, P_SOCKS)
            set_vox(vol, part, sx_r, 7, z + 1, C_GRAY_HI, P_SOCKS)
            break

    rib_xr = int(round(lx_r + 2.6))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_DARK)):
        set_vox(vol, part, rib_xr, 7 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_xr, 7 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy == -1:
            set_vox(vol, part, rib_xr + 1, 7 + dy, rib_z, c_r, P_SOCKS)

    for y_b in (8, 9, 10):
        for ox in (-2, -1, 0, 1, 2):
            vx = sx_r + ox
            front_z = -1
            for z in range(D - 1, int(CZ_BODY) - 1, -1):
                if vol[vx][y_b][z] != -1:
                    front_z = z
                    break
            if front_z >= 0:
                if y_b in (8, 10) or ox in (-2, 2):
                    col_b = C_WHITE_SH
                elif ox in (0, 1):
                    col_b = C_PINK_BAND
                else:
                    col_b = C_WHITE
                set_vox(vol, part, vx, y_b, front_z, col_b, P_SOCKS)
                set_vox(vol, part, vx, y_b, front_z - 1, col_b, P_SOCKS)
        for bz in (int(CZ_BODY), int(CZ_BODY + 1)):
            outer_x = -1
            for x in range(W - 1, sx_r, -1):
                if vol[x][y_b][bz] != -1:
                    outer_x = x
                    break
            if outer_x >= 0:
                if y_b in (8, 10):
                    col_s = C_WHITE_SH
                elif bz == int(CZ_BODY + 1):
                    col_s = C_PINK_BAND
                else:
                    col_s = C_WHITE
                set_vox(vol, part, outer_x, y_b, bz, col_s, P_SOCKS)

    # ==========================================================================
    # 3. 細身プリーツミニスカート (y=11..14) — 低め腰位置＆着ぶくれを抑えた軽やか幅
    # ==========================================================================
    for y in range(11, 15):
        t = (y - 11.0) / 3.0
        rx_sk = 7.5 - 1.4 * t
        rz_sk = 5.5 - 0.9 * t
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                ang = math.atan2(dz, dx)
                pleat = 0.38 * (1.0 - 0.45 * t) * math.cos(10.0 * ang)
                rad = math.sqrt((dx / (rx_sk + pleat)) ** 2 + (dz / (rz_sk + pleat * 0.8)) ** 2)
                if rad <= 1.0:
                    if y <= 13 and rad < 0.65:
                        continue
                    if y == 11 or math.cos(10.0 * ang) < -0.35:
                        col = C_DARK
                    elif dz > 0 and math.cos(10.0 * ang) > 0.35:
                        col = C_HOODIE
                    else:
                        col = C_HOODIE_SH
                    set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 4A. 内側インナー＆広めネックライン (y=14..25)
    #     黒パーカー外殻より約1.1vox細身・薄身に造形し、はだけた左肩とV開き胸元を物理的に凹ませて3D立体感を出す
    # ==========================================================================
    in_rx_pts = [(14.0, 5.7), (18.0, 5.3), (21.0, 4.8), (23.5, 4.1), (25.0, 3.4)]
    in_rz_pts = [(14.0, 4.0), (18.0, 3.7), (21.0, 3.4), (23.5, 3.0), (25.0, 2.5)]

    for y in range(14, 26):
        rx_i = interp_profile(in_rx_pts, float(y))
        rz_i = interp_profile(in_rz_pts, float(y))
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_i) ** 2 + (dz / rz_i) ** 2)
                if rad <= 1.0:
                    # 広めのクルーネック襟ぐり: y=25 の1行だけ鎖骨〜左肩寄りまで広く肌を見せ、y=24 はリブにして首伸びを防ぐ
                    is_wide_neck_skin = (y == 25 and -3.5 <= dx <= 2.6 and dz > -0.3)
                    if is_wide_neck_skin:
                        col = C_SKIN if abs(dx) <= 2.2 else C_SKIN_SH
                        set_vox(vol, part, x, y, z, col, P_SKIN)
                    elif y == 24 and -3.5 <= dx <= 2.6 and dz > 0.6:
                        # 広げた襟ぐりに沿うクルーネックリブ影
                        set_vox(vol, part, x, y, z, C_GRAY_SH, P_OUTFIT)
                    else:
                        if dz >= 0.0:
                            col = C_GRAY_HI if (dx <= 0.2 and y >= 20) else C_GRAY
                        else:
                            col = C_GRAY if (dx <= -0.5 and y >= 21) else C_GRAY_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 4B. 外側黒パーカー外殻 (y=13..25) — インナーより約1.1vox外側に厚みを持ち、左肩は下にずり落ちる
    # ==========================================================================
    out_rx_pts = [(13.0, 7.0), (16.0, 6.6), (19.5, 6.0), (22.5, 5.3), (24.0, 4.7), (25.0, 4.0)]
    out_rz_pts = [(13.0, 5.1), (16.0, 4.8), (19.5, 4.4), (22.5, 3.9), (24.0, 3.5), (25.0, 3.1)]

    for y in range(13, 26):
        rx_b = interp_profile(out_rx_pts, float(y))
        rz_b = interp_profile(out_rz_pts, float(y))
        if y >= 18:
            u = (y - 18.0) / 7.0
            open_left = -(1.1 + 5.6 * (u ** 0.82))
            open_right = 1.2 + 2.4 * u
        else:
            open_left = 1.0
            open_right = -1.0

        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_b) ** 2 + (dz / rz_b) ** 2)
                if rad > 1.0:
                    continue

                # 前面のV開き領域では外側黒パーカーを描かず、約1.1vox凹んだ内側グレーインナー＆広めネックを露出させる
                if dz > -0.1 and open_left <= dx <= open_right:
                    continue
                # 向かって左肩(dx <= -0.6)の y>=22 はパーカーがずり落ちて脱げているため外殻を省き、3D段差で凹んだ肩を見せる
                if y >= 22 and dx <= -0.6 and dz >= -2.5:
                    continue
                # 襟ぐり直上(y=25)の中央〜広めネック周辺は肌を塞がない
                if y == 25 and -3.6 <= dx <= 2.8 and dz > -0.6:
                    continue

                # 黒パーカー外殻の陰影＆ずり落ちた襟縁の立体ハイライト
                is_slipped_top_rim = (y == 21 and dx <= -1.0 and dz >= -2.2 and rad >= 0.72)
                if y == 13:
                    col = C_DARK
                elif is_slipped_top_rim:
                    col = C_HOODIE_HI
                elif rad >= 0.84 and dz > 0.4 and dx < -0.4:
                    col = C_HOODIE
                elif dz < -1.0:
                    col = C_HOODIE_SH if y >= 20 else C_DARK
                else:
                    col = C_HOODIE if dx < 0 else C_HOODIE_SH
                set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # 銀ジッパー（下半分 y=13..17 の中央半上げジップ＆引き手 + V開き外殻フチに沿った銀前立て）
    for y in range(13, 25):
        if y <= 17:
            zx = int(round(CX))
            for z in range(D - 1, int(CZ_BODY), -1):
                if vol[zx][y][z] != -1:
                    col_z = C_WHITE if y == 17 else (C_GRAY_HI if y >= 15 else C_GRAY)
                    set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                    set_vox(vol, part, zx, y, z + 1, col_z, P_OUTFIT)
                    break
        else:
            u = (y - 18.0) / 7.0
            for zx_f in (CX - (1.4 + 5.2 * (u ** 0.82)), CX + (1.4 + 2.4 * u)):
                if y >= 22 and zx_f < CX:
                    continue
                zx = int(round(zx_f))
                for z in range(D - 1, int(CZ_BODY), -1):
                    if vol[zx][y][z] != -1 and part[zx][y][z] == P_OUTFIT:
                        col_z = C_GRAY_HI if y >= 21 else C_GRAY
                        set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                        break

    # ==========================================================================
    # 5. 華奢な肩付け根〜手元だけダボッと丸い萌え袖両腕 (y=12..24)
    #    左肩(side<0, y>=22)はインナー半袖として一回り細く凹ませ、y=21のずり落ち袖口との3D段差を作る
    # ==========================================================================
    arm_x_pts = [(12.0, 10.2), (14.0, 10.9), (16.5, 10.2), (19.0, 8.3), (21.5, 6.3), (24.0, 4.6)]
    arm_z_pts = [(12.0, CZ_BODY + 1.2), (16.0, CZ_BODY + 0.9), (20.5, CZ_BODY + 0.4), (24.0, CZ_BODY + 0.05)]
    arm_r_pts = [(12.0, 1.85), (13.0, 2.95), (14.5, 3.35), (16.5, 3.10), (19.0, 2.25), (21.5, 1.78), (24.0, 1.48)]

    for side in (-1.0, 1.0):
        for y in range(12, 25):
            fy = float(y)
            ax = CX + side * interp_profile(arm_x_pts, fy)
            az = interp_profile(arm_z_pts, fy)
            ra = interp_profile(arm_r_pts, fy)
            is_gray_shoulder = (side < 0 and y >= 22)
            is_slipped_cuff = (side < 0 and y == 21)
            if is_gray_shoulder:
                # 脱げている左肩側は物理的に内側へ凹ませて華奢な素肩・インナー袖の3D段差を強調する
                ra *= 0.80
                ax += 0.45  # side<0 なので +0.45 で体幹側へ寄る
            elif is_slipped_cuff:
                # ずり落ちた黒パーカー袖口はふっくら外へ張り出して段差の縁を作る
                ra *= 1.18

            for x in range(W):
                for z in range(D):
                    nx = (x - ax) / ra
                    nz = (z - az) / (ra * 1.02)
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        if is_gray_shoulder:
                            col = C_GRAY_HI if nz > -0.10 else C_GRAY
                        elif is_slipped_cuff and r2 > 0.48 and nz > -0.25:
                            col = C_HOODIE_HI
                        elif y == 12:
                            col = C_DARK
                        elif y == 15 and r2 > 0.72 and nz > -0.3:
                            col = C_DARK
                        elif y == 16 and r2 > 0.72 and nz > 0.0:
                            col = C_HOODIE_HI
                        elif 13 <= y <= 18 and ((side * nx) > 0.15 or nz > 0.35):
                            col = C_HOODIE_SPEC if (side < 0 and 14 <= y <= 16 and nz > 0.55) else C_HOODIE_HI
                        elif nz < -0.45:
                            col = C_DARK
                        else:
                            col = C_HOODIE if side < 0 else C_HOODIE_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 6. 首 (y=26) — 独立1行・キャラ2準拠の6px幅で首長ネッシー化を防ぎつつ華奢な首元をくっきり見せる
    # ==========================================================================
    for x in range(W):
        for z in range(D):
            nx = (x - CX) / 2.85
            nz = (z - (CZ_BODY + 0.35)) / 2.45
            if nx * nx + nz * nz <= 1.0:
                col = C_SKIN if (z >= CZ_BODY + 0.8 and abs(x - CX) <= 1.8) else C_SKIN_SH
                set_vox(vol, part, x, 26, z, col, P_SKIN)


def build_core_body(vol: list, part: list, bangs_style: str = "yu_mix", body_style: str = "v3") -> int:
    """ベース本体を構築し、頭部Yオフセット(v4=-1, v3=0)を返す。"""
    if body_style == "v4":
        build_body_v4(vol, part)
        y_off = -1
    else:
        build_body_v3(vol, part)
        y_off = 0
    build_head_and_face(vol, part, bangs_style=bangs_style, slim_back_bob=(body_style == "v4"), y_off=y_off)
    return y_off


def build_body_v3(vol: list, part: list) -> None:
    """v2/v3 用の体格モデル（比較用に維持）。"""

    # ==========================================================================
    # 1. 厚底プラットフォームゴス靴 (y=0..4) — キャラ2基準のちび等身に合わせてコンパクト化＋フラット接地維持
    # ==========================================================================
    leg_dx = 4.35
    for side in (-1.0, 1.0):
        lx = CX + side * leg_dx
        for y in range(0, 5):
            if y <= 1:
                # プラットフォームソール (2vox厚): スーパー楕円(p=4.2)で靴底に丸みのないフラット＆シャキッとした接地形状
                rx_s = 3.35
                rz_f = 4.65  # つま先側が前にしっかり出る
                rz_b = 3.35  # かかと側が真っ直ぐ垂直に落ちる
                cz_s = CZ_BODY + 0.75
                for x in range(W):
                    if abs(x - CX) < 0.85:
                        continue
                    for z in range(D):
                        dx = x - lx
                        dz = z - cz_s
                        rz = rz_f if dz >= 0 else rz_b
                        nx = abs(dx) / rx_s
                        nz = abs(dz) / rz
                        d_s = (nx ** 4.2 + nz ** 4.2) ** (1.0 / 4.2)
                        if d_s <= 1.0:
                            if y == 0:
                                col = C_DARK
                            else:
                                # ソール上縁の立体エッジハイライト
                                col = C_HOODIE_HI if (d_s > 0.80 and dz > -2.3) else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            elif y <= 3:
                # 靴甲 (y=2..3): つま先に向けて滑らかにカーブ＋エナメル艶＋前面に大きめ銀ハートバックル
                t = float(y - 2)
                rx_u = 3.15 - 0.18 * t
                rz_f = 4.35 - 0.65 * t
                rz_b = 3.15 - 0.12 * t
                cz_s = CZ_BODY + 0.65 - 0.25 * t
                for x in range(W):
                    if abs(x - CX) < 0.85:
                        continue
                    for z in range(D):
                        dx = x - lx
                        dz = z - cz_s
                        rz = rz_f if dz >= 0 else rz_b
                        nx = abs(dx) / rx_u
                        nz = abs(dz) / rz
                        d_u = (nx ** 2.8 + nz ** 2.8) ** (1.0 / 2.8)
                        if d_u <= 1.0:
                            if y == 3 and dz > 1.0 and (-1.8 <= dx <= 0.6):
                                col = C_HOODIE_SPEC  # エナメル革靴ツヤ
                            elif dz > 0.2:
                                col = C_HOODIE
                            else:
                                col = C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            else:
                # 足首ベルト＆履き口 (y=4)
                rx_a = 2.90
                rz_a = 3.05
                cz_a = CZ_BODY + 0.20
                for x in range(W):
                    if abs(x - CX) < 0.90:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_a
                        nz = (z - cz_a) / rz_a
                        if nx * nx + nz * nz <= 1.0:
                            col = C_HOODIE_HI if z >= cz_a + 0.6 else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)

        # 靴の銀金具（甲ハートバックル y=2..4）
        # 表面から2vox奥まで埋めて斜め角度でも途切れないようにする
        hx_c = int(round(lx))
        for y_h, offsets in (
            (4, [(-1, C_GRAY_HI), (1, C_GRAY_HI)]),
            (3, [(-1, C_WHITE), (0, C_GRAY), (1, C_WHITE)]),
            (2, [(0, C_GRAY_HI)]),
        ):
            for ox, c_h in offsets:
                vx = hx_c + ox
                front_z = -1
                for z in range(D - 1, -1, -1):
                    if vol[vx][y_h][z] != -1:
                        front_z = z
                        break
                if front_z >= 0:
                    set_vox(vol, part, vx, y_h, front_z, c_h, P_SHOES)
                    set_vox(vol, part, vx, y_h, front_z - 1, c_h, P_SHOES)
                    if ox != 0 or y_h == 2:
                        set_vox(vol, part, vx, y_h, front_z + 1, c_h, P_SHOES)

    # ==========================================================================
    # 2. 両脚・左右非対称ニーハイ＆フリル・ガーターベルト・白い可愛い絆創膏 (y=5..15)
    #    スカート裾(y=13)下の露出脚は8vox、靴込み13voxでキャラ2準拠のちびバランスに収める
    # ==========================================================================
    for y in range(5, 16):
        for side in (-1.0, 1.0):
            lx = CX + side * leg_dx
            t_leg = (y - 5.0) / 10.0
            rx_l = 2.30 + 0.30 * smoothstep(0.20, 0.90, t_leg)
            rz_l = 2.45 + 0.30 * smoothstep(0.20, 0.90, t_leg)

            for x in range(W):
                if abs(x - CX) < 1.25:
                    continue
                for z in range(D):
                    dx = x - lx
                    dz = z - CZ_BODY
                    nx = dx / rx_l
                    nz = dz / rz_l
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        is_left_view = side < 0  # 向かって左脚＝黒ニーハイ＋ガーターストラップ
                        if is_left_view:
                            if y <= 9:
                                # 黒ニーハイ本体（前面左寄りに光沢縦ハイライト）
                                if dz >= 0.4 and -1.5 <= dx <= -0.1:
                                    col = C_HOODIE_HI if 6 <= y <= 8 else C_HOODIE
                                elif dz >= -0.4:
                                    col = C_HOODIE_SH
                                else:
                                    col = C_DARK
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                # 色白太もも
                                col = C_SKIN_SH if (y >= 14 or dz < -0.6 or dx > 1.1) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)
                        else:
                            # 向かって右脚（キャラ左脚）: 下黒ソックス(y=5) + 絶対領域白肌 + ガーターリング(y=7..8) + 白太もも＋白絆創膏(y=9..11)
                            if y == 5:
                                col = C_HOODIE_HI if dz > 0.2 else C_HOODIE_SH
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                col = C_SKIN_SH if (y >= 14 or dz < -0.6 or dx < -1.1) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)

    # --- 左脚ディテール: フリル帯(y=9) + 白レース上縁(y=10) + 外側リボン + 細黒ガーターストラップ(y=10..15) + 白十字 ---
    lx_l = CX - leg_dx
    for y_f in (9, 10):
        rx_f = 2.95 if y_f == 9 else 2.85
        rz_f = 3.05 if y_f == 9 else 2.95
        for x in range(W):
            if abs(x - CX) < 1.05:
                continue
            for z in range(D):
                dx = x - lx_l
                dz = z - CZ_BODY
                ang = math.atan2(dz, dx)
                scallop = 0.22 * math.cos(8.0 * ang)
                rad = math.sqrt((dx / (rx_f + scallop)) ** 2 + (dz / (rz_f + scallop)) ** 2)
                if 0.72 <= rad <= 1.0:
                    if y_f == 10:
                        if math.cos(8.0 * ang) > -0.1:
                            set_vox(vol, part, x, y_f, z, C_WHITE_SH if dz < 0 else C_WHITE, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_f, z, C_HOODIE_HI if (dz > 0 and math.cos(8.0 * ang) > 0) else C_HOODIE_SH, P_SOCKS)

    # 左脚外側の垂れ黒リボン (x=lx_l-3.0, y=7..9)
    rib_x = int(round(lx_l - 3.0))
    rib_z = int(round(CZ_BODY + 0.5))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_DARK)):
        set_vox(vol, part, rib_x, 9 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_x, 9 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy == -1:
            set_vox(vol, part, rib_x - 1, 9 + dy, rib_z, c_r, P_SOCKS)

    # 左脚前面の細い黒ガーターストラップ (y=10..15) + 銀クリップ
    sx_l = int(round(lx_l))
    for y_st in range(10, 16):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_st][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            col_st = C_GRAY_HI if y_st == 10 else C_DARK
            set_vox(vol, part, sx_l, y_st, front_z, col_st, P_SOCKS)
            set_vox(vol, part, sx_l, y_st, front_z + 1, col_st, P_SOCKS)

    # 左ニーハイ前面の繊細白十字ワンポイント (y=6..8)
    for y_c in (6, 7, 8):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_c][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            set_vox(vol, part, sx_l, y_c, front_z, C_WHITE, P_SOCKS)

    # --- 右脚ディテール: 黒ガーターリング(y=7..8) + 外側リボン + 白い可愛い絆創膏(y=9..11) ---
    lx_r = CX + leg_dx
    for y_g in (7, 8):
        rx_g = 2.95 if y_g == 8 else 2.88
        rz_g = 3.05 if y_g == 8 else 2.98
        for x in range(W):
            if abs(x - CX) < 1.05:
                continue
            for z in range(D):
                dx = x - lx_r
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_g) ** 2 + (dz / rz_g) ** 2)
                if 0.72 <= rad <= 1.0:
                    if y_g == 7 and dz > -0.5 and int(round(abs(dx) + abs(dz))) % 2 == 0:
                        set_vox(vol, part, x, y_g, z, C_WHITE_SH, P_SOCKS)
                    elif y_g == 8:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_HI if dz > 0.3 else C_HOODIE_SH, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_SH if dz > -0.5 else C_DARK, P_SOCKS)
    # ガーターリング前面銀バックル
    sx_r = int(round(lx_r))
    for z in range(D - 1, -1, -1):
        if vol[sx_r][8][z] != -1:
            set_vox(vol, part, sx_r, 8, z, C_GRAY_HI, P_SOCKS)
            set_vox(vol, part, sx_r, 8, z + 1, C_GRAY_HI, P_SOCKS)
            break
    # 右脚外側の垂れ黒リボン (x=lx_r+3.0, y=6..8)
    rib_xr = int(round(lx_r + 3.0))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_DARK)):
        set_vox(vol, part, rib_xr, 8 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_xr, 8 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy == -1:
            set_vox(vol, part, rib_xr + 1, 8 + dy, rib_z, c_r, P_SOCKS)

    # 右太もも前面〜外側の「白いちょっと可愛い絆創膏」 (y=9..11, スカート裾y=13との間に1px白肌を確保)
    for y_b in (9, 10, 11):
        for ox in (-2, -1, 0, 1, 2):
            vx = sx_r + ox
            front_z = -1
            for z in range(D - 1, int(CZ_BODY) - 1, -1):
                if vol[vx][y_b][z] != -1:
                    front_z = z
                    break
            if front_z >= 0:
                if y_b in (9, 11) or ox in (-2, 2):
                    col_b = C_WHITE_SH
                elif ox in (0, 1):
                    col_b = C_PINK_BAND
                else:
                    col_b = C_WHITE
                set_vox(vol, part, vx, y_b, front_z, col_b, P_SOCKS)
                set_vox(vol, part, vx, y_b, front_z - 1, col_b, P_SOCKS)
        for bz in (int(CZ_BODY), int(CZ_BODY + 1)):
            outer_x = -1
            for x in range(W - 1, sx_r, -1):
                if vol[x][y_b][bz] != -1:
                    outer_x = x
                    break
            if outer_x >= 0:
                if y_b in (9, 11):
                    col_s = C_WHITE_SH
                elif bz == int(CZ_BODY + 1):
                    col_s = C_PINK_BAND
                else:
                    col_s = C_WHITE
                set_vox(vol, part, outer_x, y_b, bz, col_s, P_SOCKS)

    # ==========================================================================
    # 3. 黒プリーツミニスカート (y=13..17) — 萌え袖と干渉せずくびれシルエットが出る幅に設計
    # ==========================================================================
    for y in range(13, 18):
        t = (y - 13.0) / 4.0
        rx_sk = 8.8 - 1.5 * t
        rz_sk = 6.8 - 1.1 * t
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                ang = math.atan2(dz, dx)
                pleat = 0.44 * (1.0 - 0.5 * t) * math.cos(10.0 * ang)
                rad = math.sqrt((dx / (rx_sk + pleat)) ** 2 + (dz / (rz_sk + pleat * 0.8)) ** 2)
                if rad <= 1.0:
                    if y <= 15 and rad < 0.65:
                        continue
                    if y == 13 or math.cos(10.0 * ang) < -0.35:
                        col = C_DARK
                    elif dz > 0 and math.cos(10.0 * ang) > 0.35:
                        col = C_HOODIE
                    else:
                        col = C_HOODIE_SH
                    set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 4. 片方はだけた黒パーカー＋ライトグレーインナー＋半上げ銀ジップ (y=15..26)
    #    首行(y=27)と一切重ならないよう y=26 で肩・襟をすっきり止める
    # ==========================================================================
    body_rx_pts = [(15.0, 8.2), (18.0, 7.7), (22.0, 7.0), (25.0, 6.2), (26.0, 4.9)]
    body_rz_pts = [(15.0, 6.2), (18.0, 5.8), (22.0, 5.2), (25.0, 4.4), (26.0, 3.4)]

    for y in range(15, 27):
        rx_b = interp_profile(body_rx_pts, float(y))
        rz_b = interp_profile(body_rz_pts, float(y))
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_b) ** 2 + (dz / rz_b) ** 2)
                if rad <= 1.0:
                    is_front = dz > 0.0
                    # V開き（上半分 y=20..26 はグレーインナー露出、下半分 y=15..19 はチャック少し上げて閉じる）
                    if y >= 20:
                        u = (y - 20.0) / 6.0
                        open_left = -(1.4 + 6.2 * (u ** 0.85))
                        open_right = 1.2 + 2.6 * u
                    else:
                        open_left = 1.0
                        open_right = -1.0

                    # 肩上(y=23..26)の左側は背中寄りまでグレーインナー肩が見える
                    is_off_shoulder_gray = (y >= 23 and dx <= -1.2 and dx >= -rx_b and dz >= -2.6)

                    if is_front and open_left <= dx <= open_right:
                        # 襟元の鎖骨・首付け根の肌 (y=26 中央付近)
                        if y == 26 and abs(dx) <= 2.3 and dz > 0.6:
                            set_vox(vol, part, x, y, z, C_SKIN, P_SKIN)
                            continue
                        elif y == 25 and abs(dx) <= 2.8 and dz > 1.2:
                            # クルーネック襟リブ
                            col = C_GRAY_SH
                        elif dx <= 0.0:
                            col = C_GRAY_HI if y >= 22 else C_GRAY
                        else:
                            col = C_GRAY if y >= 22 else C_GRAY_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)
                    elif is_off_shoulder_gray:
                        col = C_GRAY_HI if dz > -0.4 else C_GRAY
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)
                    else:
                        if y == 15:
                            col = C_DARK
                        elif rad >= 0.85 and dz > 0.5 and dx < -0.5:
                            col = C_HOODIE
                        elif dz < -1.2:
                            col = C_HOODIE_SH if y >= 21 else C_DARK
                        else:
                            col = C_HOODIE if dx < 0 else C_HOODIE_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # 銀ジッパー（V字前立て＋下半分 y=15..19 の中央半上げジップ＆引き手）
    for y in range(15, 27):
        if y <= 19:
            zx = int(round(CX))
            for z in range(D - 1, int(CZ_BODY), -1):
                if vol[zx][y][z] != -1:
                    col_z = C_WHITE if y == 19 else (C_GRAY_HI if y >= 17 else C_GRAY)
                    set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                    set_vox(vol, part, zx, y, z + 1, col_z, P_OUTFIT)
                    break
        else:
            u = (y - 20.0) / 6.0
            for zx_f in (CX - (1.5 + 5.8 * (u ** 0.85)), CX + (1.4 + 2.6 * u)):
                zx = int(round(zx_f))
                if y >= 23 and zx_f < CX:
                    continue
                for z in range(D - 1, int(CZ_BODY), -1):
                    if vol[zx][y][z] != -1:
                        col_z = C_GRAY_HI if y >= 23 else C_GRAY
                        set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                        break

    # 後ろフードは側面で後ろ髪の飛び出しに見えやすいため配置せず、ボブ〜黒パーカー背面のすっきりしたシルエットを優先する

    # ==========================================================================
    # 5. 手元で布がダボッと丸く膨らんだ萌え袖両腕 (y=13..25)
    # ==========================================================================
    arm_x_pts = [(13.0, 12.2), (15.0, 13.1), (17.5, 12.6), (20.5, 10.8), (23.0, 8.6), (25.0, 6.6)]
    arm_z_pts = [(13.0, CZ_BODY + 1.4), (17.0, CZ_BODY + 1.0), (21.0, CZ_BODY + 0.5), (25.0, CZ_BODY + 0.1)]
    arm_r_pts = [(13.0, 2.1), (14.0, 3.4), (15.5, 4.10), (17.5, 3.95), (20.5, 2.90), (23.0, 2.35), (25.0, 2.10)]

    for side in (-1.0, 1.0):
        for y in range(13, 26):
            fy = float(y)
            ax = CX + side * interp_profile(arm_x_pts, fy)
            az = interp_profile(arm_z_pts, fy)
            ra = interp_profile(arm_r_pts, fy)
            is_gray_shoulder = (side < 0 and y >= 23)
            is_slipped_cuff = (side < 0 and y == 22)
            for x in range(W):
                for z in range(D):
                    nx = (x - ax) / ra
                    nz = (z - az) / (ra * 1.04)
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        if is_gray_shoulder:
                            col = C_GRAY_HI if nz > -0.15 else C_GRAY
                        elif is_slipped_cuff and r2 > 0.55 and nz > -0.2:
                            col = C_HOODIE_HI
                        elif y == 13:
                            col = C_DARK
                        elif y == 16 and r2 > 0.72 and nz > -0.3:
                            col = C_DARK
                        elif y == 17 and r2 > 0.72 and nz > 0.0:
                            col = C_HOODIE_HI
                        elif 14 <= y <= 19 and ((side * nx) > 0.15 or nz > 0.35):
                            col = C_HOODIE_SPEC if (side < 0 and 15 <= y <= 17 and nz > 0.55) else C_HOODIE_HI
                        elif nz < -0.45:
                            col = C_DARK
                        else:
                            col = C_HOODIE if side < 0 else C_HOODIE_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 6. 首 (y=27) — パーカー襟(y=26)と顎(y=28)の間に独立した1vox首を配置し、全角度でくっきり見せる
    # ==========================================================================
    for x in range(W):
        for z in range(D):
            nx = (x - CX) / 2.7
            nz = (z - (CZ_BODY + 0.35)) / 2.5
            if nx * nx + nz * nz <= 1.0:
                col = C_SKIN if (z >= CZ_BODY + 0.6 and abs(x - CX) <= 1.7) else C_SKIN_SH
                set_vox(vol, part, x, 27, z, col, P_SKIN)


def build_head_and_face(
    vol: list,
    part: list,
    bangs_style: str = "yu_mix",
    slim_back_bob: bool = False,
    y_off: int = 0,
) -> None:
    # ==========================================================================
    # 7. 頭部・顔・前髪・垂れ横髪・ジト目・ばってん＆白うさぎピン (y=28+y_off..47+y_off)
    #    Char2 (sharp_jaw_hair=True, y_raw=27..46 -> y=y_raw+1+y_off) の輪郭・顔面・チーク・
    #    前髪束＆目頭スリット・垂れ横髪・6x4ジト目を1:1座標で完全移植し、ゆの黒髪パレットで塗る
    # ==========================================================================
    head_y_shift = 1 + y_off

    rx_profile = [
        (26.0, 5.8),
        (27.0, 8.8),
        (28.5, 11.4),
        (30.5, 12.6),
        (33.5, 12.9),
        (37.5, 12.8),
        (41.0, 12.0),
        (43.5, 10.2),
        (45.0, 7.6),
        (46.0, 4.3),
    ]
    rz_front_profile = [
        (26.0, 4.9),
        (27.5, 7.0),
        (30.0, 8.3),
        (33.0, 8.6),
        (37.0, 8.7),
        (41.0, 8.2),
        (43.8, 6.7),
        (45.0, 5.0),
        (46.0, 3.0),
    ]
    rz_back_profile = [
        (26.0, 5.1),
        (28.0, 7.5),
        (32.0, 9.2),
        (37.0, 9.7),
        (41.5, 9.0),
        (44.2, 7.1),
        (45.2, 5.2),
        (46.0, 3.2),
    ]

    for y_raw in range(27, 47):
        fy = float(y_raw)
        y = y_raw + head_y_shift
        rx_h = catmull_rom_interp(rx_profile, fy)
        rz_f = catmull_rom_interp(rz_front_profile, fy)
        rz_b = catmull_rom_interp(rz_back_profile, fy)
        # Char2 sharp_jaw_hair=True 同一のすっきりもちっと下顎ライン
        if y_raw == 27:
            rx_h = 8.1

        for x in range(W):
            dx = x - CX
            adx = abs(dx)
            for z in range(D):
                dz = z - CZ_HEAD
                rz_h = rz_f if dz >= 0.0 else rz_b
                nx = adx / rx_h
                nz = abs(dz) / rz_h
                p_exp = 2.0 + 0.18 * smoothstep(0.0, 3.0, dz) * smoothstep(26.0, 29.0, fy) * smoothstep(44.0, 38.0, fy)
                r_ell = (nx ** p_exp + nz ** p_exp) ** (1.0 / p_exp)
                if r_ell <= 1.0:
                    face_width_limit = 9.9 - 0.16 * max(0.0, 30.0 - fy)
                    is_face_zone = (dz > 1.7) and (
                        (y_raw <= 33 and adx <= face_width_limit)
                        or (34 <= y_raw <= 36 and adx <= 5.6)
                    )
                    if is_face_zone:
                        if y_raw == 27:
                            col = C_SKIN_SH
                        elif y_raw == 29 and 6.8 <= adx <= 9.2 and r_ell >= 0.74:
                            col = C_BLUSH_DEEP if (7.2 <= adx <= 8.6) else C_BLUSH_LIGHT
                        elif y_raw == 28 and 7.2 <= adx <= 8.8 and r_ell >= 0.84:
                            col = C_BLUSH_LIGHT
                        elif r_ell >= 0.89 and adx >= 8.3:
                            col = C_SKIN_SH
                        else:
                            col = C_SKIN
                    else:
                        if bangs_style == "yu_mix":
                            y_ref = y - y_off
                            # v3/v4: 元の黒髪ドーム配色（頭頂は落ち着いた黒、y_ref=42..44に横長の天使の輪ツヤ帯）
                            if 42 <= y_ref <= 44 and r_ell >= 0.80:
                                if y_ref == 43 and -4.5 <= dx <= 1.5 and dz >= -4.0:
                                    col = C_HAIR_SPEC
                                elif y_ref in (42, 43) and int(round(adx)) not in (2, 7):
                                    col = C_HAIR_HI
                                else:
                                    col = C_HAIR
                            elif y_ref >= 45:
                                col = C_HAIR_SH1 if (y_ref == 47 and r_ell <= 0.24) else C_HAIR
                            elif y_ref >= 36:
                                col = C_HAIR if dz >= -1.5 else C_HAIR_SH1
                            else:
                                col = C_HAIR_SH1 if dz >= -3.0 else C_HAIR_SH2
                        else:
                            if y_raw >= 42:
                                if y_raw == 46 and r_ell <= 0.24:
                                    col = C_HAIR_SH1
                                elif y_raw in (43, 44) and r_ell >= 0.85 and -3.5 <= dx <= 1.5 and dz < 4.5:
                                    col = C_HAIR_SPEC
                                else:
                                    col = C_HAIR_HI
                            elif y_raw >= 37:
                                col = C_HAIR if dz < 1.8 else C_HAIR_HI
                            elif y_raw >= 30:
                                col = C_HAIR_SH1 if dz < -1.2 else C_HAIR
                            else:
                                col = C_HAIR_SH2

                        if dz < -3.4 and r_ell >= 0.84 and 28 <= y_raw <= 41:
                            t_back = (y_raw - 28.0) / 13.0
                            curve_target = 2.2 + 3.5 * (t_back ** 0.8)
                            if abs(adx - curve_target) < 0.52 or (y_raw <= 33 and adx < 0.60):
                                col = C_HAIR_SH2
                    set_vox(vol, part, x, y, z, col, P_SKIN if is_face_zone else P_HAIR)

    # 後ろ髪ボブの襟足カーブ (y=26+y_off..28+y_off, 正面の顎〜垂れ横髪間の抜け感を塞がないよう肩幅内に収める)
    for y_ref in range(26, 29):
        y = y_ref + y_off
        t = (28.0 - y_ref) / 2.0
        rx_bk = 7.4 - 2.4 * t
        rz_bk = 7.6 - 1.4 * t
        z_cut = -2.6 if (slim_back_bob and y_ref <= 27) else -2.0
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_HEAD
                if dz > z_cut:
                    continue
                rad = math.sqrt((dx / rx_bk) ** 2 + (dz / rz_bk) ** 2)
                if 0.60 <= rad <= 1.0:
                    col = C_HAIR_SH2 if (y_ref == 26 or int(round(abs(dx))) in (0, 4)) else C_HAIR_SH1
                    set_vox(vol, part, x, y, z, col, P_HAIR)

    # 前髪造形: v2('char2') はChar2完全1:1、v3('yu_mix') は黒髪らしい繊細スリット＋細身中央束＋天使の輪ツヤ帯
    for y_raw in range(32, 46):
        fy = float(y_raw)
        y = y_raw + head_y_shift
        rx_h = catmull_rom_interp(rx_profile, fy) + 0.32 * smoothstep(32.5, 38.0, fy)
        rz_f = catmull_rom_interp(rz_front_profile, fy)
        bang_arch = smoothstep(31.5, 38.5, fy) * (1.0 - 0.70 * smoothstep(41.5, 45.5, fy))
        bang_extra_z = 0.42 + 0.92 * bang_arch

        for x in range(W):
            dx = x - CX
            adx = abs(dx)
            if adx > 11.2:
                continue

            if bangs_style == "yu_mix":
                # v3: Char2の縦長2x4白スリットを抑え、黒髪向け繊細レイヤー前髪（細身中央束＋1〜2px抜けスリット＋左目上1px抜け）にする
                if y_raw == 32:
                    continue
                if y_raw == 33 and adx > 1.2:
                    # 眉間中央にごく細い2px毛先 (x=28,29) だけ垂らし、目元をすっきり開ける
                    continue
                if y_raw == 34 and ((2.2 <= adx <= 3.8) or (-5.8 <= dx <= -5.2)):
                    # 中央束(x=27..30)の両脇に柔らかな2px抜け(x=25..26, 31..32) + 左目上に1px抜け(x=23, adx=5.5<=5.6で肌が見える)
                    continue
                if y_raw == 35 and ((2.2 <= adx <= 2.8) or (-5.8 <= dx <= -5.2)):
                    # 上段は1pxの繊細な抜け先(x=26, 31 と左目上 x=23)へ収束させ、額の縦割れ感を抑える
                    continue
            else:
                if y_raw in (32, 33) and adx > 2.6:
                    continue
                if y_raw == 34 and (3.2 <= adx <= 4.8):
                    continue
                if y_raw == 35 and (3.2 <= adx <= 4.7):
                    continue
                if y_raw == 36 and (3.3 <= adx <= 4.1):
                    continue

            for z in range(int(CZ_HEAD + 1), D):
                dz = z - CZ_HEAD
                nx = adx / rx_h
                nz = dz / (rz_f + bang_extra_z)
                p_b = 2.15
                r_b = (nx ** p_b + nz ** p_b) ** (1.0 / p_b)
                if 0.77 <= r_b <= 1.0:
                    if bangs_style == "yu_mix":
                        y_ref = y - y_off
                        if 42 <= y_ref <= 44 and adx <= 8.5:
                            if y_ref == 43 and -4.5 <= dx <= 1.5:
                                col = C_HAIR_SPEC
                            elif y_ref in (42, 43) and int(round(adx)) not in (2, 7):
                                col = C_HAIR_HI
                            elif y_ref == 44 and -5.5 <= dx <= 2.5 and int(round(adx)) not in (2, 7):
                                col = C_HAIR_HI
                            else:
                                col = C_HAIR
                        elif y_ref >= 45:
                            col = C_HAIR
                        elif y_ref == 34:
                            col = C_HAIR_SH2
                        elif y_ref == 35:
                            if abs(adx - 1.5) < 0.45 or abs(adx - 4.5) < 0.45 or abs(dx + 6.5) < 0.45:
                                col = C_HAIR_SH2
                            else:
                                col = C_HAIR_SH1
                        elif 36 <= y_ref <= 38 and (
                            abs(adx - 1.5) < 0.45
                            or abs(adx - 4.5) < 0.45
                            or abs(dx + 7.5) < 0.45
                        ):
                            col = C_HAIR_SH2 if y_ref <= 37 else C_HAIR_SH1
                        elif adx >= 8.5 and y_ref <= 41:
                            col = C_HAIR_SH1
                        else:
                            col = C_HAIR
                    else:
                        if y_raw >= 42:
                            col = C_HAIR_HI
                        elif y_raw in (32, 33, 34) and abs(adx - 2.5) < 0.45:
                            col = C_HAIR_SH2
                        elif y_raw == 35 and abs(adx - 2.5) < 0.45:
                            col = C_HAIR_SH1
                        elif y_raw == 34 and abs(adx - 5.5) < 0.45:
                            col = C_HAIR_SH2
                        elif y_raw == 35 and abs(adx - 5.5) < 0.45:
                            col = C_HAIR_SH1
                        elif y_raw == 34 and 5.8 <= adx <= 9.6 and r_b >= 0.86:
                            col = C_HAIR_SH1
                        elif y_raw == 32 and adx <= 2.1:
                            col = C_HAIR
                        elif 33 <= y_raw <= 41 and r_b >= 0.87 and (
                            (abs(dx + 0.5) < 0.45 and y_raw >= 33)
                            or (abs(adx - 4.5) < 0.45 and y_raw >= 37)
                            or (abs(adx - 7.5) < 0.45 and y_raw >= 36)
                        ):
                            col = C_HAIR_HI
                        elif y_raw == 41:
                            col = C_HAIR_HI if (int(round(adx)) % 2 == 0 or adx <= 2.5) else C_HAIR
                        else:
                            col = C_HAIR
                    set_vox(vol, part, x, y, z, col, P_HAIR)

    # Char2 1:1移植: 顔周りの横髪 (y_raw=28..41 -> y=36..49) + 顎下垂れ毛束 (y_c2=25..29 -> y=34..38)
    for y_raw in range(28, 42):
        y = y_raw + head_y_shift
        for side in (-1.0, 1.0):
            for x in range(W):
                dx_s = (x - CX) * side
                if not (9.3 <= dx_s <= 13.5):
                    continue
                for z in range(int(CZ_HEAD - 2), int(CZ_HEAD + 6)):
                    dz = z - CZ_HEAD
                    z_front_limit = 2.3 if y_raw <= 33 else 4.2
                    if dz > z_front_limit or dz < -1.4:
                        continue
                    rx_lock = 13.25 if y_raw >= 31 else (12.85 if y_raw == 30 else 12.25)
                    rz_lock = 8.95
                    r_l = math.sqrt((dx_s / rx_lock) ** 2 + (dz / rz_lock) ** 2)
                    if 0.80 <= r_l <= 1.02:
                        if y_raw == 28:
                            col = C_HAIR_SH2
                        elif y_raw == 29:
                            col = C_HAIR_SH1 if dx_s < 11.8 else C_HAIR_SH2
                        elif y_raw >= 38:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1 if (dx_s >= 12.1 and dz < 0.5) else C_HAIR
                        set_vox(vol, part, x, y, z, col, P_HAIR)

    for y_c2 in range(25, 30):
        y = y_c2 + 2 + y_off  # Char2 sharp_jaw_hair の y=25..29 -> char3 y=27+y_off..31+y_off
        t_hang = clamp((29.0 - y_c2) / 4.0, 0.0, 1.0)
        lock_cx = 11.55 - 0.35 * t_hang
        lock_rx = 1.65 - 0.55 * (t_hang ** 1.2)
        lock_cz = CZ_HEAD + 2.35 - 0.35 * t_hang
        lock_rz = 1.75 - 0.45 * t_hang
        for side in (-1.0, 1.0):
            cx_s = CX + side * lock_cx
            for x in range(W):
                adx = abs(x - CX)
                if y_c2 <= 27 and adx < 10.0:
                    continue
                for z in range(int(CZ_HEAD), int(CZ_HEAD + 7)):
                    nx = (x - cx_s) / max(0.75, lock_rx)
                    nz = (z - lock_cz) / max(0.75, lock_rz)
                    if nx * nx + nz * nz <= 1.0:
                        if y_c2 == 25:
                            col = C_HAIR_SH2
                        elif y_c2 == 26:
                            col = C_HAIR_SH1 if (z >= lock_cz - 0.2) else C_HAIR_SH2
                        elif (side * (x - cx_s)) > 0.35 and z < lock_cz:
                            col = C_HAIR_SH1
                        else:
                            col = C_HAIR
                        set_vox(vol, part, x, y, z, col, P_HAIR)

    # Char2 1:1移植: 眠たげジト目 (y_raw=30..33 -> y=38..41, lx=19..24 対称ミラー, 3vox深め埋め込み)
    def set_sym(x_left: int, y_pos: int, z_pos: int, c_idx: int, p_idx: int) -> None:
        set_vox(vol, part, x_left, y_pos, z_pos, c_idx, p_idx)
        set_vox(vol, part, W - 1 - x_left, y_pos, z_pos, c_idx, p_idx)

    for eye_y_raw in range(30, 34):
        eye_y = eye_y_raw + head_y_shift
        z_surfs: dict[int, int] = {}
        for lx in range(19, 25):
            zs = -1
            for z in range(D - 1, int(CZ_HEAD), -1):
                if vol[lx][eye_y][z] != -1:
                    zs = z
                    break
            z_surfs[lx] = zs

        for lx in range(19, 25):
            z_surf = z_surfs[lx]
            if z_surf == -1:
                continue
            local_u = lx - 19
            if local_u == 0:
                for z_off in (0, 1, 2):
                    if eye_y_raw == 33:
                        c_side = C_EYE_LASH
                    elif eye_y_raw == 32:
                        c_side = C_EYE_HIGH
                    elif eye_y_raw == 31:
                        c_side = C_EYE_LOW if z_off == 0 else C_EYE_WHITE
                    else:
                        c_side = C_SKIN
                    set_sym(lx, eye_y, z_surf - z_off, c_side, P_SKIN if c_side == C_SKIN else P_EYES)
                continue

            if eye_y_raw == 33:
                col = C_EYE_LASH
            elif eye_y_raw == 32:
                col = C_EYE_HIGH
            elif eye_y_raw == 31:
                if local_u == 1:
                    col = C_EYE_SPARKLE
                elif local_u == 5:
                    col = C_EYE_WHITE
                else:
                    col = C_EYE_LOW
            else:
                col = C_EYE_WHITE if 1 <= local_u <= 4 else C_SKIN

            neighbor_min_z = min(
                z_surfs.get(lx - 1, z_surf),
                z_surfs.get(lx + 1, z_surf),
                z_surf - 2,
            )
            fill_min_z = max(int(CZ_HEAD) + 2, neighbor_min_z)
            eye_part = P_SKIN if col == C_SKIN else P_EYES
            for z_fill in range(fill_min_z, z_surf + 1):
                set_sym(lx, eye_y, z_fill, col, eye_part)

    # 前髪ヘアアクセ2種（目頭スリットおよび目まつ毛 y=34 を一切塞がず、ベレー帽縁の下に収める）
    if bangs_style == "yu_mix":
        # v3: 天使の輪ツヤ帯(y=42..44)の下、暗い前髪上で白ピンが最もくっきり映える位置
        b_pts = [(31, 42), (33, 42), (32, 41), (31, 40), (33, 40)]
        u_pattern = [
            (39, [(35, C_WHITE), (37, C_WHITE)]),
            (38, [(34, C_WHITE), (35, C_WHITE), (36, C_WHITE), (37, C_WHITE), (38, C_WHITE)]),
            (37, [(34, C_WHITE), (35, C_ACC_DARK), (36, C_WHITE), (37, C_ACC_DARK), (38, C_WHITE)]),
            (36, [(35, C_WHITE_SH), (36, C_WHITE_SH), (37, C_WHITE_SH)]),
        ]
    else:
        # v2: Char2の縦長目頭スリット(x=32..33, y=35..37)を避けて配置
        b_pts = [(30, 42), (32, 42), (31, 41), (30, 40), (32, 40)]
        u_pattern = [
            (40, [(35, C_WHITE), (37, C_WHITE)]),
            (39, [(34, C_WHITE), (35, C_WHITE), (36, C_WHITE), (37, C_WHITE), (38, C_WHITE)]),
            (38, [(34, C_WHITE), (35, C_ACC_DARK), (36, C_WHITE), (37, C_ACC_DARK), (38, C_WHITE)]),
            (37, [(35, C_WHITE_SH), (36, C_WHITE_SH), (37, C_WHITE_SH)]),
        ]

    for bx, by_ref in b_pts:
        by = by_ref + y_off
        front_z = -1
        for z in range(D - 1, int(CZ_HEAD), -1):
            if vol[bx][by][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            set_vox(vol, part, bx, by, front_z, C_WHITE, P_ACC)
            set_vox(vol, part, bx, by, front_z - 1, C_WHITE, P_ACC)

    for uy_ref, row_items in u_pattern:
        uy = uy_ref + y_off
        for ux, uc in row_items:
            front_z = -1
            for z in range(D - 1, int(CZ_HEAD), -1):
                if vol[ux][uy][z] != -1:
                    front_z = z
                    break
            if front_z >= 0:
                set_vox(vol, part, ux, uy, front_z, uc, P_ACC)
                set_vox(vol, part, ux, uy, front_z - 1, uc, P_ACC)


def stamp_ahoge(vol: list, part: list, y_off: int = 0) -> list[tuple[int, int, int, int, int]]:
    """頭頂(y=47+y_off)からぴょこんとカーブする可愛いアホ毛（ベレー帽ON時にremoveできるよう座標リストも返す）。"""
    pts = [
        (28, 48 + y_off, 21),
        (28, 49 + y_off, 21),
        (27, 50 + y_off, 21),
        (26, 51 + y_off, 20),
        (25, 51 + y_off, 20),
        (24, 50 + y_off, 20),
    ]
    added = []
    for x, y, z in pts:
        set_vox(vol, part, x, y, z, C_HAIR_SH2, P_HAIR)
        added.append((x, y, z, C_HAIR_SH2, P_HAIR))
    bridges = [
        (28, 50 + y_off, 21),
        (27, 51 + y_off, 21),
        (26, 51 + y_off, 21),
        (25, 50 + y_off, 20),
    ]
    for x, y, z in bridges:
        set_vox(vol, part, x, y, z, C_HAIR_SH1, P_HAIR)
        added.append((x, y, z, C_HAIR_SH1, P_HAIR))
    return added


def paint_half_twin_down(vol: list, part: list, y_off: int = 0) -> None:
    """ベース髪型：ピンク丸位置（頭上サイド）から1vox空気スリットを空けて下向き＆毛先ハネのショートハーフツイン。"""
    for side in (-1.0, 1.0):
        for x_off in (11.2, 12.2, 13.2):
            bx = int(round(CX + side * x_off))
            for by in (40 + y_off, 41 + y_off):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)
        rx_k = int(round(CX + side * 13.8))
        for by in (40 + y_off, 41 + y_off):
            set_vox(vol, part, rx_k, by, int(CZ_HEAD + 1), C_HOODIE_HI, P_ACC)

        for y_ref in range(25, 42):
            y = y_ref + y_off
            t = (41.0 - y_ref) / 16.0
            x_off = 13.6 + 1.6 * math.sin(t * math.pi * 0.65) + (1.5 * ((t - 0.55) ** 1.4) if t > 0.55 else 0.0)
            z_off = -1.5 - 3.6 * (t ** 1.15) - (1.4 * ((t - 0.60) ** 1.4) if t > 0.60 else 0.0)
            r_t = 1.95 * (1.0 - 0.45 * (t ** 1.35))
            if t < 0.18:
                r_t = 1.45 + 0.50 * (t / 0.18)
            xc = CX + side * x_off
            zc = CZ_HEAD + z_off
            for x in range(W):
                for z in range(D):
                    nx = (x - xc) / r_t
                    nz = (z - zc) / (r_t * 1.05)
                    if nx * nx + nz * nz <= 1.0:
                        if y_ref <= 26:
                            col = C_HAIR_SH2
                        elif nz > 0.15 and 34 <= y_ref <= 36:
                            col = C_HAIR_HI
                        elif nz > -0.2:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)
            if 0.55 <= t <= 0.90:
                fx = int(round(xc + side * (1.3 + 0.9 * (t - 0.55))))
                fz = int(round(zc - 0.8))
                for dx_f in (0, -int(side)):
                    set_vox(vol, part, fx + dx_f, y, fz, C_HAIR_SH1 if t < 0.78 else C_HAIR_SH2, P_HAIR)


def paint_half_flare(vol: list, part: list, y_off: int = 0) -> None:
    """オプション髪型①（高め外ハネショート）：v1案Aの外ハネショートを約5px上の位置で結んだ軽やかシルエット。"""
    for side in (-1.0, 1.0):
        for x_off in (11.2, 12.2, 13.2):
            bx = int(round(CX + side * x_off))
            for by in (40 + y_off, 41 + y_off):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)

        for y_ref in range(27, 42):
            y = y_ref + y_off
            t = (41.0 - y_ref) / 14.0
            x_off = 13.4 + 3.7 * math.sin(t * math.pi * 0.70) + 1.1 * (t ** 1.45)
            z_off = -1.6 - 5.2 * math.sin(t * math.pi * 0.68) - 1.6 * (t ** 1.4)
            r_t = 2.25 * (0.82 + 0.26 * math.sin(t * math.pi * 0.62)) * (1.0 - 0.38 * (t ** 1.4))
            xc = CX + side * x_off
            zc = CZ_HEAD + z_off
            for x in range(W):
                for z in range(D):
                    nx = (x - xc) / r_t
                    nz = (z - zc) / (r_t * 1.05)
                    if nx * nx + nz * nz <= 1.0:
                        if y_ref <= 28:
                            col = C_HAIR_SH2
                        elif nz > 0.1 and 35 <= y_ref <= 37:
                            col = C_HAIR_HI
                        elif nz > -0.25:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)
            if 0.45 <= t <= 0.88:
                fx = int(round(xc + side * (1.4 + 1.1 * (t - 0.45))))
                fz = int(round(zc - 1.0))
                for dx_f in (0, -int(side)):
                    set_vox(vol, part, fx + dx_f, y, fz, C_HAIR_SH1 if t < 0.75 else C_HAIR_SH2, P_HAIR)


def paint_twin_high(vol: list, part: list, y_off: int = 0) -> None:
    """オプション髪型②（高め腰丈ツインテ＋ふっくら黒リボン＆淡紫ハート宝石＆白十字チャーム）。"""
    for side in (-1.0, 1.0):
        for x_off in (10.5, 11.5, 12.5, 13.5):
            bx = int(round(CX + side * x_off))
            for by in (41 + y_off, 42 + y_off, 43 + y_off):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)

        for y_ref in range(12, 43):
            y = y_ref + y_off
            t = (42.0 - y_ref) / 30.0
            x_off = 13.8 + 2.8 * math.sin(t * math.pi * 0.78) + 0.7 * math.sin(t * math.pi * 2.1)
            z_off = -1.6 - 5.6 * (t ** 0.88) - 1.2 * math.sin(t * math.pi * 2.0)
            r_t = 2.15 + 0.82 * math.sin(t * math.pi * 0.82)
            if y_ref <= 17:
                r_t *= max(0.42, 1.0 - (18.0 - y_ref) / 7.2)
            xc = CX + side * x_off
            zc = CZ_HEAD + z_off
            for x in range(W):
                for z in range(D):
                    nx = (x - xc) / r_t
                    nz = (z - zc) / (r_t * 1.05)
                    if nx * nx + nz * nz <= 1.0:
                        if y_ref <= 13:
                            col = C_HAIR_SH2
                        elif nz > 0.2 and y_ref in (36, 37, 26, 27, 19, 20):
                            col = C_HAIR_HI
                        elif nz > -0.2:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)

        rx_c = int(round(CX + side * 13.2))
        ry_c = 42 + y_off
        rz_c = int(CZ_HEAD + 0.5)
        for dx_r in range(-3, 4):
            for dy_r in range(-1, 2):
                for dz_r in range(-1, 2):
                    if abs(dx_r) == 3 and abs(dz_r) == 1:
                        continue
                    if abs(dx_r) >= 2 and dy_r == 1 and dz_r >= 0:
                        col_r = C_HOODIE_SPEC
                    elif dy_r == 1 and dz_r >= 0:
                        col_r = C_HOODIE_HI
                    elif dy_r == -1:
                        col_r = C_DARK
                    else:
                        col_r = C_HOODIE if dz_r >= 0 else C_HOODIE_SH
                    set_vox(vol, part, rx_c + dx_r, ry_c + dy_r, rz_c + dz_r, col_r, P_ACC)
        for dy_g in (-1, 0, 1):
            for dx_g in (-1, 0, 1):
                if abs(dx_g) == 1 and dy_g == -1:
                    continue
                c_g = C_LAVENDER_GEM if (dx_g == 0 and dy_g in (0, -1)) else C_WHITE
                set_vox(vol, part, rx_c + dx_g, ry_c + dy_g, rz_c + 1, c_g, P_ACC)
        for dy_c in (-2, -3, -4):
            set_vox(vol, part, rx_c, ry_c + dy_c, rz_c + 1, C_WHITE, P_ACC)
            set_vox(vol, part, rx_c, ry_c + dy_c, rz_c, C_WHITE_SH, P_ACC)
        set_vox(vol, part, rx_c - 1, ry_c - 3, rz_c + 1, C_WHITE, P_ACC)
        set_vox(vol, part, rx_c + 1, ry_c - 3, rz_c + 1, C_WHITE, P_ACC)


def paint_twin_arc(vol: list, part: list, y_off: int = 0) -> None:
    """オプション髪型③（細身軽やかカーブツインテ・v1案C寄り：中腹で膨らみ毛先で柔らかく内側へ収まる弧）。"""
    for side in (-1.0, 1.0):
        for x_off in (11.5, 12.5, 13.5):
            bx = int(round(CX + side * x_off))
            for by in (37 + y_off, 38 + y_off):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)
        rx_k = int(round(CX + side * 13.6))
        for dx_k in (0, int(side)):
            for dy_k in (0, 1):
                set_vox(vol, part, rx_k + dx_k, 38 + y_off + dy_k, int(CZ_HEAD + 1), C_HOODIE_HI, P_ACC)
                set_vox(vol, part, rx_k + dx_k, 38 + y_off + dy_k, int(CZ_HEAD), C_HOODIE_SH, P_ACC)

        for y_ref in range(14, 39):
            y = y_ref + y_off
            t = (38.0 - y_ref) / 24.0
            x_off = 13.6 + 5.2 * math.sin(t * math.pi * 0.90) - 0.8 * (t ** 2.2)
            z_off = -1.6 - 6.4 * math.sin(t * math.pi * 0.74) - 1.8 * (t ** 1.5)
            r_t = 2.05 * (0.78 + 0.28 * math.sin(t * math.pi * 0.65)) * (1.0 - 0.44 * (t ** 1.5))
            xc = CX + side * x_off
            zc = CZ_HEAD + z_off
            for x in range(W):
                for z in range(D):
                    nx = (x - xc) / r_t
                    nz = (z - zc) / (r_t * 1.05)
                    if nx * nx + nz * nz <= 1.0:
                        if y_ref <= 15:
                            col = C_HAIR_SH2
                        elif nz > 0.15 and y_ref in (30, 31, 22, 23):
                            col = C_HAIR_HI
                        elif nz > -0.25:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)
            if 0.48 <= t <= 0.86:
                fx = int(round(xc + side * (1.3 + 0.8 * (t - 0.48))))
                fz = int(round(zc - 1.0))
                for dx_f in (0, -int(side)):
                    set_vox(vol, part, fx + dx_f, y, fz, C_HAIR_SH1 if t < 0.74 else C_HAIR_SH2, P_HAIR)


def build_beret_mod(
    vol_base: list,
    ahoge_list: list[tuple[int, int, int, int, int]],
    y_off: int = 0,
) -> dict:
    """
    斜め＆深め被りの立体黒ベレー帽Mod：
    - 正面では向かって左へ斜め傾けて頭にすっぽり被せ（右のばってん＆うさぎピンを邪魔しない）
    - 側面では額ラインにしっかり被さりつつ、高くなりすぎない平べったいベレー形を保って後ろへふわっと垂れる
    - 縁のギャザー編み目＋右サイドの白十字架＋左縁の白レース付き小リボン
    """
    beret_map: dict[tuple[int, int, int], tuple[int, int]] = {}
    cx_b = CX - 1.0
    cz_b = CZ_HEAD - 1.4

    for x in range(W):
        for z in range(D):
            ux = (x - cx_b) / 14.6
            uz = (z - cz_b) / 14.0
            r2 = ux * ux + uz * uz
            if r2 > 1.02:
                continue
            r = math.sqrt(r2)
            tilt = 1.9 * ux + 1.8 * uz
            dome = math.sqrt(max(0.0, 1.0 - min(1.0, r2 / 1.02)))
            y_top = int(round(45.0 + y_off + tilt + 4.7 * (dome ** 0.72)))
            brim_tuck = 1.2 * smoothstep(0.75, 1.0, r)
            y_bot = int(round(42.2 + y_off + tilt + brim_tuck))
            if y_top < y_bot:
                continue
            for y in range(max(37 + y_off, y_bot), min(H, y_top + 1)):
                if vol_base[x][y][z] != -1 and r < 0.78 and y < y_top - 1:
                    continue
                if y == y_bot:
                    col = C_DARK
                elif y == y_bot + 1:
                    ang_i = int(round((math.atan2(uz, ux) + math.pi) * 6.0))
                    col = C_HOODIE if (ang_i % 2 == 0) else C_DARK
                elif y >= y_top - 1 and -0.45 <= ux <= 0.35 and -0.35 <= uz <= 0.55:
                    col = C_HOODIE_SPEC if (y == y_top and -0.25 <= ux <= 0.15) else C_HOODIE_HI
                elif uz >= -0.15:
                    col = C_HOODIE
                else:
                    col = C_HOODIE_SH
                beret_map[(x, y, z)] = (col, P_BERET)

    cross_cx, cross_cy = int(round(CX + 7.2)), 46 + y_off
    for dx_c, dy_c in ((0, -2), (0, -1), (0, 0), (0, 1), (0, 2), (-1, 0), (1, 0)):
        vx, vy = cross_cx + dx_c, cross_cy + dy_c
        best_z = -1
        for z in range(D - 1, -1, -1):
            if (vx, vy, z) in beret_map:
                best_z = z
                break
        if best_z >= 0:
            beret_map[(vx, vy, best_z)] = (C_WHITE, P_BERET)
            if best_z - 1 >= 0 and (vx, vy, best_z - 1) in beret_map:
                beret_map[(vx, vy, best_z - 1)] = (C_WHITE, P_BERET)

    rib_lx, rib_ly = int(round(CX - 11.8)), 42 + y_off
    for dx_r in (-1, 0, 1):
        for dy_r in (-1, 0, 1):
            vx, vy = rib_lx + dx_r, rib_ly + dy_r
            best_z = -1
            for z in range(D - 1, -1, -1):
                if (vx, vy, z) in beret_map:
                    best_z = z
                    break
            if best_z >= 0:
                c_r = C_WHITE if (dx_r == 0 and dy_r in (0, -1)) else C_HOODIE_HI
                beret_map[(vx, vy, best_z)] = (c_r, P_BERET)
                if best_z - 1 >= 0 and (vx, vy, best_z - 1) in beret_map:
                    beret_map[(vx, vy, best_z - 1)] = (c_r, P_BERET)

    remove_list = [[x, y, z] for x, y, z, _c, _p in ahoge_list if (x, y, z) not in beret_map]
    add_list = [
        [x, y, z, c, p]
        for (x, y, z), (c, p) in sorted(beret_map.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0]))
    ]
    return {
        "id": "beret",
        "label": "黒ベレー帽",
        "defaultEnabled": False,
        "remove": remove_list,
        "add": add_list,
    }


def extract_diff_mod(
    mod_id: str,
    label: str,
    group: str | None,
    vol_base: list,
    part_base: list,
    vol_target: list,
    part_target: list,
) -> dict:
    """ベースとターゲットボリュームの厳密差分を抽出し、1ボクセルの誤差もないModを生成する。"""
    remove_list: list[list[int]] = []
    add_list: list[list[int]] = []
    for y in range(H):
        for z in range(D):
            for x in range(W):
                cb, pb = vol_base[x][y][z], part_base[x][y][z]
                ct, pt = vol_target[x][y][z], part_target[x][y][z]
                if cb >= 0 and ct < 0:
                    remove_list.append([x, y, z])
                elif ct >= 0 and (cb != ct or pb != pt):
                    add_list.append([x, y, z, ct, pt])
    mod = {
        "id": mod_id,
        "label": label,
        "defaultEnabled": False,
        "remove": remove_list,
        "add": add_list,
    }
    if group:
        mod["group"] = group
    return mod


def compose_mods(base_voxels: list[list[int]], mods: list[dict], active_ids: set[str]) -> tuple[list, list]:
    vol, part = new_grid()
    for vx, vy, vz, ci, pi in base_voxels:
        vol[vx][vy][vz] = ci
        part[vx][vy][vz] = pi
    for mod in mods:
        if mod["id"] not in active_ids:
            continue
        for rx, ry, rz in mod.get("remove", []):
            if 0 <= rx < W and 0 <= ry < H and 0 <= rz < D:
                vol[rx][ry][rz] = -1
                part[rx][ry][rz] = -1
        for ax, ay, az, ci, pi in mod.get("add", []):
            if 0 <= ax < W and 0 <= ay < H and 0 <= az < D:
                vol[ax][ay][az] = ci
                part[ax][ay][az] = pi
    return vol, part


def count_6_connected_components(vol: list) -> tuple[int, list[int]]:
    visited = [[[False] * D for _ in range(H)] for _ in range(W)]
    sizes = []
    for x in range(W):
        for y in range(H):
            for z in range(D):
                if vol[x][y][z] < 0 or visited[x][y][z]:
                    continue
                q = deque([(x, y, z)])
                visited[x][y][z] = True
                cnt = 0
                while q:
                    cx, cy, cz = q.popleft()
                    cnt += 1
                    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                        nx, ny, nz = cx + dx, cy + dy, cz + dz
                        if 0 <= nx < W and 0 <= ny < H and 0 <= nz < D and not visited[nx][ny][nz] and vol[nx][ny][nz] >= 0:
                            visited[nx][ny][nz] = True
                            q.append((nx, ny, nz))
                sizes.append(cnt)
    sizes.sort(reverse=True)
    return len(sizes), sizes


def prune_floating_voxels(vol: list, part: list) -> int:
    """万一の微小な孤立ボクセルを検出し、最大連結成分のみ残す（安全網）。"""
    n_comp, sizes = count_6_connected_components(vol)
    if n_comp <= 1:
        return 0
    # 全連結成分を列挙して最大以外を削除
    visited = [[[False] * D for _ in range(H)] for _ in range(W)]
    comps = []
    for x in range(W):
        for y in range(H):
            for z in range(D):
                if vol[x][y][z] < 0 or visited[x][y][z]:
                    continue
                q = deque([(x, y, z)])
                visited[x][y][z] = True
                cells = []
                while q:
                    cx, cy, cz = q.popleft()
                    cells.append((cx, cy, cz))
                    for dx, dy, dz in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                        nx, ny, nz = cx + dx, cy + dy, cz + dz
                        if 0 <= nx < W and 0 <= ny < H and 0 <= nz < D and not visited[nx][ny][nz] and vol[nx][ny][nz] >= 0:
                            visited[nx][ny][nz] = True
                            q.append((nx, ny, nz))
                comps.append(cells)
    comps.sort(key=len, reverse=True)
    removed = 0
    for comp in comps[1:]:
        for cx, cy, cz in comp:
            vol[cx][cy][cz] = -1
            part[cx][cy][cz] = -1
            removed += 1
    return removed


def render_ref_orthos(vol: list, palette_rgb: list[tuple[int, int, int]], out_dir: str) -> None:
    """正面・側面のリファレンス画像を3Dボリュームから正確に書き出す（?dev=1 比較用）。"""
    # 正面 (+Zから-Zへ投影)
    im_f = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pf = im_f.load()
    for y in range(H):
        py = H - 1 - y
        for x in range(W):
            for z in range(D - 1, -1, -1):
                ci = vol[x][y][z]
                if ci >= 0:
                    pf[x, py] = (*palette_rgb[ci], 255)
                    break
    im_f.save(os.path.join(out_dir, "ref_front.png"))

    # 左向き側面 (+Xから-Xへ投影: Z大きい方が左=顔、Z小さい方が右=背中)
    im_s = Image.new("RGBA", (D, H), (0, 0, 0, 0))
    ps = im_s.load()
    for y in range(H):
        py = H - 1 - y
        for z in range(D):
            px = D - 1 - z
            for x in range(W - 1, -1, -1):
                ci = vol[x][y][z]
                if ci >= 0:
                    ps[px, py] = (*palette_rgb[ci], 255)
                    break
    im_s.save(os.path.join(out_dir, "ref_side.png"))


def export_assets(vol_base: list, part_base: list, mods: list[dict], out_dir: str = ASSETS_DIR) -> None:
    os.makedirs(out_dir, exist_ok=True)
    palette_rgb = [hex_to_rgb(c) for c in PALETTE_HEX]

    base_voxels: list[list[int]] = []
    part_color_counts: list[dict[int, int]] = [{} for _ in PARTS_DEF]
    for y in range(H):
        for z in range(D):
            for x in range(W):
                ci = vol_base[x][y][z]
                if ci >= 0:
                    pi = part_base[x][y][z]
                    assert pi >= 0, f"Missing partIdx at {(x, y, z)}"
                    base_voxels.append([x, y, z, ci, pi])
                    part_color_counts[pi][ci] = part_color_counts[pi].get(ci, 0) + 1

    for mod in mods:
        for _ax, _ay, _az, ci, pi in mod.get("add", []):
            part_color_counts[pi][ci] = part_color_counts[pi].get(ci, 0) + 1

    # 全有効組み合わせ（髪型4種 × ベレー帽ON/OFF = 8通り）で 6-connected components == 1 を厳密検証！
    hair_choices = [None, "hair_flare", "hair_twin_high", "hair_twin_arc"]
    for h_mod in hair_choices:
        for beret_on in (False, True):
            active = set()
            if h_mod:
                active.add(h_mod)
            if beret_on:
                active.add("beret")
            v_test, _p_test = compose_mods(base_voxels, mods, active)
            n_comp, sizes = count_6_connected_components(v_test)
            label_c = "+".join(sorted(active)) if active else "base"
            print(f"[6-conn] {label_c:24s}: components={n_comp}, sizes={sizes[:4]}")
            assert n_comp == 1, f"Floating voxels detected in combo {label_c}: {sizes}"

    default_active = {m["id"] for m in mods if m.get("defaultEnabled", False)}
    vol_default, _part_default = compose_mods(base_voxels, mods, default_active)

    im_y = Image.new("RGBA", (H * W, D), (0, 0, 0, 0))
    py_y = im_y.load()
    im_z = Image.new("RGBA", (D * W, H), (0, 0, 0, 0))
    py_z = im_z.load()
    im_x = Image.new("RGBA", (W * D, H), (0, 0, 0, 0))
    py_x = im_x.load()

    default_solid = 0
    for y in range(H):
        inv_y = H - 1 - y
        y_off = y * W
        for z in range(D):
            z_off = z * W
            for x in range(W):
                ci = vol_default[x][y][z]
                if ci >= 0:
                    default_solid += 1
                    rgba = (*palette_rgb[ci], 255)
                    py_y[y_off + x, z] = rgba
                    py_z[z_off + x, inv_y] = rgba
                    py_x[x * D + z, inv_y] = rgba

    im_y.save(os.path.join(out_dir, "slices_y.png"))
    im_z.save(os.path.join(out_dir, "slices_z.png"))
    im_x.save(os.path.join(out_dir, "slices_x.png"))
    render_ref_orthos(vol_default, palette_rgb, out_dir)

    parts = []
    for idx, pdef in enumerate(PARTS_DEF):
        color_indices = [
            ci
            for ci, _cnt in sorted(
                part_color_counts[idx].items(),
                key=lambda kv: (-kv[1], kv[0]),
            )
        ]
        parts.append({
            "id": pdef["id"],
            "label": pdef["label"],
            "colorIndices": color_indices,
        })

    model_data = {
        "name": "ゆ",
        "size": {"x": W, "y": H, "z": D},
        "palette": PALETTE_HEX,
        "parts": parts,
        "voxels": base_voxels,
        "mods": mods,
        "slices": {
            "y": {"file": "slices_y.png", "count": H, "sliceWidth": W, "sliceHeight": D},
            "z": {"file": "slices_z.png", "count": D, "sliceWidth": W, "sliceHeight": H},
            "x": {"file": "slices_x.png", "count": W, "sliceWidth": D, "sliceHeight": H},
        },
        "referenceViews": {"front": "ref_front.png", "side": "ref_side.png"},
    }

    with open(os.path.join(out_dir, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model_data, f, ensure_ascii=False, separators=(",", ":"))

    print(
        f"[OK] Exported char3 model.json (size={W}x{H}x{D}, base={len(base_voxels)}, mods={len(mods)}, default_solid={default_solid}) -> {out_dir}"
    )


def build_variant(bangs_style: str, out_dir: str, label: str, body_style: str = "v3") -> None:
    print(f"=== Building char3 {label} (bangs_style={bangs_style}, body_style={body_style}) -> {out_dir} ===")
    vol_core, part_core = new_grid()
    y_off = build_core_body(vol_core, part_core, bangs_style=bangs_style, body_style=body_style)
    ahoge_list = stamp_ahoge(vol_core, part_core, y_off=y_off)

    # 1) デフォルトベース（下向きショート・ハーフツイン）
    vol_base = [[row[:] for row in plane] for plane in vol_core]
    part_base = [[row[:] for row in plane] for plane in part_core]
    paint_half_twin_down(vol_base, part_base, y_off=y_off)
    pruned_base = prune_floating_voxels(vol_base, part_base)
    if pruned_base:
        print(f"[info] pruned floating in base ({label}): {pruned_base}")

    # 2) オプション髪型①: 高め外ハネショート
    vol_flare = [[row[:] for row in plane] for plane in vol_core]
    part_flare = [[row[:] for row in plane] for plane in part_core]
    paint_half_flare(vol_flare, part_flare, y_off=y_off)
    prune_floating_voxels(vol_flare, part_flare)

    # 3) オプション髪型②: 高め腰丈ツインテ（リボン＋紫ハート＋白十字）
    vol_th = [[row[:] for row in plane] for plane in vol_core]
    part_th = [[row[:] for row in plane] for plane in part_core]
    paint_twin_high(vol_th, part_th, y_off=y_off)
    prune_floating_voxels(vol_th, part_th)

    # 4) オプション髪型③: 細身軽やかカーブツインテ
    vol_ta = [[row[:] for row in plane] for plane in vol_core]
    part_ta = [[row[:] for row in plane] for plane in part_core]
    paint_twin_arc(vol_ta, part_ta, y_off=y_off)
    prune_floating_voxels(vol_ta, part_ta)

    mods = [
        build_beret_mod(vol_base, ahoge_list, y_off=y_off),
        extract_diff_mod("hair_flare", "外ハネショート", "hair_style", vol_base, part_base, vol_flare, part_flare),
        extract_diff_mod("hair_twin_high", "腰丈ツインテ", "hair_style", vol_base, part_base, vol_th, part_th),
        extract_diff_mod("hair_twin_arc", "細身ツインテ", "hair_style", vol_base, part_base, vol_ta, part_ta),
    ]

    export_assets(vol_base, part_base, mods, out_dir=out_dir)


def main() -> None:
    # v2: Char2顔・前髪1:1移植版 -> public/assets/char3/v2/
    build_variant("char2", os.path.join(ASSETS_DIR, "v2"), "v2 (Char2 1:1)", body_style="v3")
    # v3: Char2顔・目 × 元の黒髪前髪ニュアンス版（旧体格） -> public/assets/char3/
    build_variant("yu_mix", ASSETS_DIR, "v3 (Yu bangs mix / v3 body)", body_style="v3")
    # v4: 華奢シルエット・3Dはだけ段差・広めネック・2px首・低め腰＆コンパクト厚底版 -> public/assets/char3/v4/
    build_variant("yu_mix", os.path.join(ASSETS_DIR, "v4"), "v4 (Slim 3D off-shoulder)", body_style="v4")


if __name__ == "__main__":
    main()
