"""
新キャラクター（黒髪ハーフツイン×片方はだけ黒パーカー萌え袖×左右非対称ニーハイ＆白絆創膏×厚底靴）
3Dボクセル・3軸スライス・拡張Modジェネレーター

- グリッド: 58 x 64 x 42（最大ストリップ幅 64*58=3712 <= 4096、モバイルWebGL2安全圏）
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

W, H, D = 58, 64, 42

# 二次元リッチな色相シフトパレット（外周黒枠は焼き込まず後加工2Dアウトラインへ委譲）
PALETTE_HEX = [
    "#262030",  # 0: C_HAIR_SH2 (黒髪 深影・毛束割れ)
    "#352E42",  # 1: C_HAIR_SH1 (黒髪 影)
    "#473E58",  # 2: C_HAIR (黒髪 ベース)
    "#625777",  # 3: C_HAIR_HI (黒髪 天使の輪・明部)
    "#82769A",  # 4: C_HAIR_SPEC (黒髪 ツヤ芯)
    "#FDF5F2",  # 5: C_SKIN (肌ベース)
    "#EBD7D1",  # 6: C_SKIN_SH (肌影・顎下・前髪落とし影)
    "#F5D5DC",  # 7: C_BLUSH_LIGHT (淡チーク)
    "#E8B6C5",  # 8: C_BLUSH_DEEP (濃チーク)
    "#2E2737",  # 9: C_EYE_LASH (ジト目まつ毛バー)
    "#574C6D",  # 10: C_EYE_HIGH (瞳上段スレート紫)
    "#857AA1",  # 11: C_EYE_MID (瞳中段ラベンダー)
    "#BBB2D3",  # 12: C_EYE_LOW (瞳下段淡ラベンダー・白ハイライトなし)
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
    C_EYE_MID,
    C_EYE_LOW,
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

CX = (W - 1) * 0.5  # 28.5
CZ_BODY = 20.5
CZ_HEAD = 21.0


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(e0: float, e1: float, x: float) -> float:
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


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


def build_core_body(vol: list, part: list) -> None:
    """ベース本体（靴・脚・スカート・片方はだけ黒パーカー＆萌え袖＆後ろフード・首・もちっと頭＆顔＆前髪＆アクセ）を構築する。"""

    # ==========================================================================
    # 1. 厚底プラットフォームゴス靴 (y=0..7) — ソール底面を丸めずフラット接地！
    # ==========================================================================
    leg_dx = 4.6
    for side in (-1.0, 1.0):
        lx = CX + side * leg_dx
        for y in range(0, 8):
            if y <= 2:
                # プラットフォームソール: スーパー楕円(p=4.2)で靴底に丸みのないフラット＆シャキッとした接地形状
                rx_s = 3.55
                rz_f = 4.95  # つま先側が前にしっかり出る
                rz_b = 3.55  # かかと側が真っ直ぐ垂直に落ちる
                cz_s = CZ_BODY + 0.85
                for x in range(W):
                    if abs(x - CX) < 0.85:
                        continue
                    for z in range(D):
                        dx = x - lx
                        dz = z - cz_s
                        rz = rz_f if dz >= 0 else rz_b
                        nx = abs(dx) / rx_s
                        nz = abs(dz) / rz
                        # p=4.2 の角張りスーパー楕円で通常の靴ソールらしいフラットな箱形シルエットを作る
                        d_s = (nx ** 4.2 + nz ** 4.2) ** (1.0 / 4.2)
                        if d_s <= 1.0:
                            if y == 0:
                                col = C_DARK
                            elif y == 1:
                                col = C_DARK if d_s > 0.86 else C_HOODIE_SH
                            else:
                                # ソール上縁の立体エッジハイライト
                                col = C_HOODIE_HI if (d_s > 0.80 and dz > -2.5) else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            elif y <= 5:
                # 靴甲 (y=3..5): つま先に向けて滑らかにカーブ＋エナメル艶＋前面に大きめ銀ハートバックル
                t = (y - 3.0) / 2.0
                rx_u = 3.35 - 0.25 * t
                rz_f = 4.70 - 0.75 * t
                rz_b = 3.35 - 0.15 * t
                cz_s = CZ_BODY + 0.75 - 0.25 * t
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
                            if y == 4 and dz > 1.2 and (-2.0 <= dx <= 0.6):
                                col = C_HOODIE_SPEC  # エナメル革靴ツヤ
                            elif dz > 0.2:
                                col = C_HOODIE
                            else:
                                col = C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)
            else:
                # 足首ベルト＆履き口 (y=6..7)
                rx_a = 3.10 if y == 6 else 2.95
                rz_a = 3.25 if y == 6 else 3.05
                cz_a = CZ_BODY + 0.20
                for x in range(W):
                    if abs(x - CX) < 0.90:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_a
                        nz = (z - cz_a) / rz_a
                        if nx * nx + nz * nz <= 1.0:
                            col = C_HOODIE_HI if (y == 6 and z >= cz_a + 0.6) else C_HOODIE_SH
                            set_vox(vol, part, x, y, z, col, P_SHOES)

        # 靴の銀金具（大きめ甲ハートバックル y=3..5 + 足首ベルト銀バックル y=6..7）
        # 表面から2vox奥まで埋めて斜め角度でも途切れないようにする
        hx_c = int(round(lx))
        for y_h, offsets in (
            (5, [(-1, C_GRAY_HI), (1, C_GRAY_HI)]),
            (4, [(-1, C_WHITE), (0, C_GRAY), (1, C_WHITE)]),
            (3, [(0, C_GRAY_HI)]),
        ):
            for ox, c_h in offsets:
                vx = hx_c + ox
                # 前面表面Zを探して塗り込み＋1vox手前へ立体レリーフ
                front_z = -1
                for z in range(D - 1, -1, -1):
                    if vol[vx][y_h][z] != -1:
                        front_z = z
                        break
                if front_z >= 0:
                    set_vox(vol, part, vx, y_h, front_z, c_h, P_SHOES)
                    set_vox(vol, part, vx, y_h, front_z - 1, c_h, P_SHOES)
                    if ox != 0 or y_h == 3:
                        set_vox(vol, part, vx, y_h, front_z + 1, c_h, P_SHOES)
        # 足首ストラップ銀バックル (y=6..7)
        for y_b in (6, 7):
            for ox in (0, 1 if side < 0 else -1):
                vx = hx_c + ox
                front_z = -1
                for z in range(D - 1, -1, -1):
                    if vol[vx][y_b][z] != -1:
                        front_z = z
                        break
                if front_z >= 0:
                    c_b = C_GRAY_HI if y_b == 7 else C_GRAY
                    set_vox(vol, part, vx, y_b, front_z, c_b, P_SHOES)
                    set_vox(vol, part, vx, y_b, front_z + 1, c_b, P_SHOES)

    # ==========================================================================
    # 2. 両脚・左右非対称ニーハイ＆フリル・ガーターベルト・白い可愛い絆創膏 (y=8..22)
    # ==========================================================================
    for y in range(8, 23):
        for side in (-1.0, 1.0):
            lx = CX + side * leg_dx
            # ふくらはぎ〜太ももへごく緩やかに太くなる可愛い脚ライン
            t_leg = (y - 8.0) / 14.0
            rx_l = 2.45 + 0.35 * smoothstep(0.25, 0.90, t_leg)
            rz_l = 2.60 + 0.35 * smoothstep(0.25, 0.90, t_leg)

            for x in range(W):
                if abs(x - CX) < 1.35:
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
                            if y <= 16:
                                # 黒ニーハイ本体（前面左寄りに光沢縦ハイライト）
                                if dz >= 0.4 and -1.6 <= dx <= -0.1:
                                    col = C_HOODIE_HI if 11 <= y <= 14 else C_HOODIE
                                elif dz >= -0.4:
                                    col = C_HOODIE_SH
                                else:
                                    col = C_DARK
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                # 色白太もも
                                col = C_SKIN_SH if (y >= 21 or dz < -0.6 or dx > 1.2) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)
                        else:
                            # 向かって右脚（キャラ左脚）: 下黒ソックス(y=8..9) + 絶対領域白肌 + ガーターリング(y=12..14) + 白太もも＋白絆創膏(y=16..19)
                            if y <= 9:
                                col = C_HOODIE_HI if y == 9 and dz > 0 else (C_HOODIE if dz >= 0.2 and dx <= 0.2 else C_HOODIE_SH)
                                set_vox(vol, part, x, y, z, col, P_SOCKS)
                            else:
                                col = C_SKIN_SH if (y >= 21 or dz < -0.6 or dx < -1.2) else C_SKIN
                                set_vox(vol, part, x, y, z, col, P_SKIN)

    # --- 左脚ディテール: フリル帯(y=15..17) + 外側リボン + 細黒ガーターストラップ(y=17..22) + 白十字 ---
    lx_l = CX - leg_dx
    # ニーハイ上端の360度黒フリル帯 (y=15..16) + 白レース上縁 (y=17)
    for y_f in (15, 16, 17):
        rx_f = 3.15 if y_f == 16 else (3.00 if y_f == 15 else 2.95)
        rz_f = 3.25 if y_f == 16 else (3.10 if y_f == 15 else 3.05)
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
                    if y_f == 17:
                        # 白レース縁のスカラップ
                        if math.cos(8.0 * ang) > -0.1:
                            set_vox(vol, part, x, y_f, z, C_WHITE_SH if dz < 0 else C_WHITE, P_SOCKS)
                    elif y_f == 16:
                        set_vox(vol, part, x, y_f, z, C_HOODIE_HI if (dz > 0 and math.cos(8.0 * ang) > 0) else C_HOODIE_SH, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_f, z, C_DARK if dz < -0.5 else C_HOODIE_SH, P_SOCKS)

    # 左脚外側の垂れ黒リボン (x=lx_l-3.5, y=13..16)
    rib_x = int(round(lx_l - 3.2))
    rib_z = int(round(CZ_BODY + 0.5))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_HOODIE_SH), (-3, C_DARK)):
        set_vox(vol, part, rib_x, 16 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_x, 16 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy in (-1, -2):
            set_vox(vol, part, rib_x - 1, 16 + dy, rib_z, c_r, P_SOCKS)

    # 左脚前面の細い黒ガーターストラップ (y=17..22) + 銀クリップ
    sx_l = int(round(lx_l))
    for y_st in range(17, 23):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_st][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            col_st = C_GRAY_HI if y_st == 17 else C_DARK
            set_vox(vol, part, sx_l, y_st, front_z, col_st, P_SOCKS)
            set_vox(vol, part, sx_l, y_st, front_z + 1, col_st, P_SOCKS)

    # 左ニーハイ前面の繊細白十字ワンポイント (y=11..13)
    for y_c in (11, 12, 13):
        front_z = -1
        for z in range(D - 1, -1, -1):
            if vol[sx_l][y_c][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            set_vox(vol, part, sx_l, y_c, front_z, C_WHITE, P_SOCKS)

    # --- 右脚ディテール: 黒ガーターリング(y=12..14) + 外側リボン + 白い可愛い絆創膏(y=16..19) ---
    # 右ガーターリングを左ニーハイ上端より下げて配置し、スカート裾(y=20)との間に絆創膏が映える白肌ウィンドウを確保する
    lx_r = CX + leg_dx
    for y_g in (12, 13, 14):
        rx_g = 3.15 if y_g == 13 else 3.05
        rz_g = 3.25 if y_g == 13 else 3.15
        for x in range(W):
            if abs(x - CX) < 1.05:
                continue
            for z in range(D):
                dx = x - lx_r
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_g) ** 2 + (dz / rz_g) ** 2)
                if 0.72 <= rad <= 1.0:
                    if y_g == 12 and dz > -0.5 and int(round(abs(dx) + abs(dz))) % 2 == 0:
                        set_vox(vol, part, x, y_g, z, C_WHITE_SH, P_SOCKS)
                    elif y_g == 14:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_HI if dz > 0.3 else C_HOODIE_SH, P_SOCKS)
                    else:
                        set_vox(vol, part, x, y_g, z, C_HOODIE_SH if dz > -0.5 else C_DARK, P_SOCKS)
    # ガーターリング前面銀バックル
    sx_r = int(round(lx_r))
    for z in range(D - 1, -1, -1):
        if vol[sx_r][13][z] != -1:
            set_vox(vol, part, sx_r, 13, z, C_GRAY_HI, P_SOCKS)
            set_vox(vol, part, sx_r, 13, z + 1, C_GRAY_HI, P_SOCKS)
            break
    # 右脚外側の垂れ黒リボン (x=lx_r+3.2, y=11..14)
    rib_xr = int(round(lx_r + 3.2))
    for dy, c_r in ((0, C_HOODIE_HI), (-1, C_HOODIE), (-2, C_HOODIE_SH), (-3, C_DARK)):
        set_vox(vol, part, rib_xr, 14 + dy, rib_z, c_r, P_SOCKS)
        set_vox(vol, part, rib_xr, 14 + dy, rib_z - 1, C_DARK, P_SOCKS)
        if dy in (-1, -2):
            set_vox(vol, part, rib_xr + 1, 14 + dy, rib_z, c_r, P_SOCKS)

    # 右太もも前面〜外側の「白いちょっと可愛い絆創膏」 (y=16..19)
    # 淡肌色(C_SKIN)に埋没しないよう上下左右の縁を C_WHITE_SH で縁取り、中央2x2にピンクガーゼを配置して正面・側面両方で鮮明に見せる
    for y_b in (16, 17, 18, 19):
        for ox in (-2, -1, 0, 1, 2):
            vx = sx_r + ox
            front_z = -1
            for z in range(D - 1, int(CZ_BODY) - 1, -1):
                if vol[vx][y_b][z] != -1:
                    front_z = z
                    break
            if front_z >= 0:
                if y_b in (16, 19) or ox in (-2, 2):
                    col_b = C_WHITE_SH
                elif ox in (0, 1):
                    col_b = C_PINK_BAND
                else:
                    col_b = C_WHITE
                set_vox(vol, part, vx, y_b, front_z, col_b, P_SOCKS)
                set_vox(vol, part, vx, y_b, front_z - 1, col_b, P_SOCKS)
        # 側面(+90度)からも白ピンク絆創膏が可愛く見えるよう外側面カーブにも1列巻き込む
        for bz in (int(CZ_BODY), int(CZ_BODY + 1)):
            outer_x = -1
            for x in range(W - 1, sx_r, -1):
                if vol[x][y_b][bz] != -1:
                    outer_x = x
                    break
            if outer_x >= 0:
                if y_b in (16, 19):
                    col_s = C_WHITE_SH
                elif bz == int(CZ_BODY + 1):
                    col_s = C_PINK_BAND
                else:
                    col_s = C_WHITE
                set_vox(vol, part, outer_x, y_b, bz, col_s, P_SOCKS)

    # ==========================================================================
    # 3. 黒プリーツミニスカート (y=20..24) — 萌え袖と干渉せずくびれシルエットが出る幅に設計
    # ==========================================================================
    for y in range(20, 25):
        t = (y - 20.0) / 4.0
        rx_sk = 9.0 - 1.5 * t
        rz_sk = 7.0 - 1.1 * t
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                ang = math.atan2(dz, dx)
                pleat = 0.44 * (1.0 - 0.5 * t) * math.cos(10.0 * ang)
                rad = math.sqrt((dx / (rx_sk + pleat)) ** 2 + (dz / (rz_sk + pleat * 0.8)) ** 2)
                if rad <= 1.0:
                    # 裾内部を空洞にして脚を貫通させる
                    if y <= 22 and rad < 0.65:
                        continue
                    if y == 20 or math.cos(10.0 * ang) < -0.35:
                        col = C_DARK
                    elif dz > 0 and math.cos(10.0 * ang) > 0.35:
                        col = C_HOODIE
                    else:
                        col = C_HOODIE_SH
                    set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 4. 片方はだけた黒パーカー＋ライトグレーインナー＋半上げ銀ジップ＋後ろフード (y=22..34)
    # ==========================================================================
    body_rx_pts = [(22.0, 8.4), (25.0, 7.9), (29.0, 7.2), (32.0, 6.5), (34.0, 5.2)]
    body_rz_pts = [(22.0, 6.4), (25.0, 6.0), (29.0, 5.4), (32.0, 4.9), (34.0, 4.1)]

    for y in range(22, 35):
        rx_b = interp_profile(body_rx_pts, float(y))
        rz_b = interp_profile(body_rz_pts, float(y))
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_BODY
                rad = math.sqrt((dx / rx_b) ** 2 + (dz / rz_b) ** 2)
                if rad <= 1.0:
                    # 片方（向かって左肩 dx < 0）がずり落ちてライトグレーインナーが見える領域判定
                    is_front = dz > 0.0
                    # V開き（上半分はグレーインナー露出、下半分 y=22..26 はチャック少し上げて閉じる！）
                    if y >= 27:
                        # y=27(中心)〜y=34(上)へ向かってV字＋左肩は大きくはだける
                        u = (y - 27.0) / 7.0
                        open_left = -(1.4 + 6.4 * (u ** 0.85))  # 向かって左は肩まで広くはだける！
                        open_right = 1.2 + 2.7 * u              # 向かって右は通常の襟開き
                    else:
                        open_left = 1.0
                        open_right = -1.0

                    # 肩上(y=30..34)の左側は背中寄りまでグレーインナー肩が見える
                    is_off_shoulder_gray = (y >= 30 and dx <= -1.2 and dx >= -rx_b and dz >= -2.8)

                    if is_front and open_left <= dx <= open_right:
                        # 襟元の肌チラ見え (y=33..34, 中央付近)
                        if y >= 33 and abs(dx) <= 2.3 and dz > 1.2:
                            col = C_SKIN if y == 34 else C_SKIN_SH
                            set_vox(vol, part, x, y, z, col, P_SKIN)
                            continue
                        elif y == 32 and abs(dx) <= 2.8 and dz > 1.4:
                            # クルーネック襟リブ
                            col = C_GRAY_SH
                        elif dx <= 0.0:
                            col = C_GRAY_HI if y >= 29 else C_GRAY
                        else:
                            col = C_GRAY if y >= 29 else C_GRAY_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)
                    elif is_off_shoulder_gray:
                        col = C_GRAY_HI if dz > -0.4 else C_GRAY
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)
                    else:
                        # 黒パーカー本体
                        if y == 22:
                            col = C_DARK
                        elif rad >= 0.85 and dz > 0.5 and dx < -0.5:
                            col = C_HOODIE
                        elif dz < -1.2:
                            col = C_HOODIE_SH if y >= 28 else C_DARK
                        else:
                            col = C_HOODIE if dx < 0 else C_HOODIE_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # 銀ジッパー（V字前立て＋下半分 y=22..26 の中央半上げジップ＆引き手）
    for y in range(22, 34):
        if y <= 26:
            # 半上げ中央銀ジップ
            zx = int(round(CX))
            for z in range(D - 1, int(CZ_BODY), -1):
                if vol[zx][y][z] != -1:
                    col_z = C_WHITE if y == 26 else (C_GRAY_HI if y >= 24 else C_GRAY)
                    set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                    set_vox(vol, part, zx, y, z + 1, col_z, P_OUTFIT)
                    break
        else:
            u = (y - 27.0) / 7.0
            for zx_f in (CX - (1.5 + 6.0 * (u ** 0.85)), CX + (1.4 + 2.7 * u)):
                zx = int(round(zx_f))
                if y >= 30 and zx_f < CX:
                    continue  # 左肩ははだけて下にずり落ちた襟へ
                for z in range(D - 1, int(CZ_BODY), -1):
                    if vol[zx][y][z] != -1:
                        col_z = C_GRAY_HI if y >= 30 else C_GRAY
                        set_vox(vol, part, zx, y, z, col_z, P_OUTFIT)
                        break

    # 後ろフード（首後ろ〜背中にふわっと畳まれた立体パーカーフード y=26..34, z<CZ_BODY-3）
    for y in range(26, 35):
        t = (y - 26.0) / 8.0
        rx_hd = 6.2 + 1.9 * math.sin(t * math.pi * 0.85)
        rz_hd = 2.8 + 1.7 * math.sin(t * math.pi * 0.80)
        cz_hd = CZ_BODY - 5.0 - 1.4 * math.sin(t * math.pi * 0.78)
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - cz_hd
                if dz > 2.2:
                    continue
                rad = math.sqrt((dx / rx_hd) ** 2 + (dz / rz_hd) ** 2)
                if rad <= 1.0:
                    if y in (32, 33) and rad > 0.70 and dz < 0.4:
                        col = C_HOODIE_HI  # 後ろフード上縁のふんわり立ち上がりハイライト
                    elif y == 28 and rad > 0.76 and dz < -0.2:
                        col = C_HOODIE  # 下折り段の丸み
                    elif y <= 27 or dz < -rz_hd * 0.68:
                        col = C_DARK
                    elif y in (29, 30) and dz < -0.4:
                        col = C_DARK  # フード中央の折り目影
                    else:
                        col = C_HOODIE_SH
                    set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 5. 手元で布がダボッと丸く膨らんだ萌え袖両腕 (y=20..33)
    #    スカート裾との間に明確なクビレの隙間を作り、袖先の丸みを引き立てる
    # ==========================================================================
    arm_x_pts = [(20.0, 12.6), (22.0, 13.5), (24.5, 13.0), (27.5, 11.1), (30.5, 8.8), (32.5, 6.8)]
    arm_z_pts = [(20.0, CZ_BODY + 1.5), (24.0, CZ_BODY + 1.1), (28.5, CZ_BODY + 0.5), (32.5, CZ_BODY + 0.1)]
    arm_r_pts = [(20.0, 2.2), (21.0, 3.5), (22.5, 4.25), (24.5, 4.10), (27.5, 3.00), (30.5, 2.40), (32.5, 2.15)]

    for side in (-1.0, 1.0):
        for y in range(20, 34):
            fy = float(y)
            ax = CX + side * interp_profile(arm_x_pts, fy)
            az = interp_profile(arm_z_pts, fy)
            ra = interp_profile(arm_r_pts, fy)
            # 向かって左肩(side<0)ははだけているため、y=30..33をライトグレーのインナー半袖にする
            is_gray_shoulder = (side < 0 and y >= 30)
            is_slipped_cuff = (side < 0 and y == 29)
            for x in range(W):
                for z in range(D):
                    nx = (x - ax) / ra
                    nz = (z - az) / (ra * 1.04)
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        if is_gray_shoulder:
                            col = C_GRAY_HI if nz > -0.15 else C_GRAY
                        elif is_slipped_cuff and r2 > 0.55 and nz > -0.2:
                            # はだけた黒パーカー肩口のリブ縁
                            col = C_HOODIE_HI
                        elif y == 20:
                            col = C_DARK
                        elif y == 23 and r2 > 0.72 and nz > -0.3:
                            col = C_DARK  # 手首の布だまりシワ影
                        elif y == 24 and r2 > 0.72 and nz > 0.0:
                            col = C_HOODIE_HI  # 布だまりハイライト
                        elif 21 <= y <= 26 and ((side * nx) > 0.15 or nz > 0.35):
                            col = C_HOODIE_SPEC if (side < 0 and 22 <= y <= 24 and nz > 0.55) else C_HOODIE_HI
                        elif nz < -0.45:
                            col = C_DARK
                        else:
                            col = C_HOODIE if side < 0 else C_HOODIE_SH
                        set_vox(vol, part, x, y, z, col, P_OUTFIT)

    # ==========================================================================
    # 6. 首 (y=34) — よくんの指定通り1pxしっかり残して、もちっと顎を自然に支える！
    # ==========================================================================
    for x in range(W):
        for z in range(D):
            nx = (x - CX) / 2.8
            nz = (z - CZ_BODY) / 2.5
            if nx * nx + nz * nz <= 1.0:
                col = C_SKIN if (z >= CZ_BODY + 0.5 and abs(x - CX) <= 1.6) else C_SKIN_SH
                set_vox(vol, part, x, 34, z, col, P_SKIN)

    # ==========================================================================
    # 7. 頭部・もちっと顎（余分な顎下1行なし）・顔・ジト目・前髪・ばってん＆白うさぎピン (y=35..54)
    # ==========================================================================
    # 顎底 y=35（丸くもちっと締まる）〜頭頂 y=54（高さ20vox、幅25vox）
    rx_head_pts = [
        (35.0, 7.6),
        (36.5, 10.6),
        (38.5, 12.1),
        (41.5, 12.6),
        (45.5, 12.6),
        (49.0, 11.9),
        (51.5, 10.2),
        (53.0, 7.6),
        (54.0, 4.4),
    ]
    rz_front_pts = [
        (35.0, 6.2),
        (37.0, 7.8),
        (40.0, 8.6),
        (44.5, 8.7),
        (49.0, 8.2),
        (52.0, 6.4),
        (54.0, 3.4),
    ]
    rz_back_pts = [
        (35.0, 6.8),
        (38.0, 8.8),
        (42.5, 9.8),
        (47.0, 9.6),
        (50.5, 8.4),
        (53.0, 5.8),
        (54.0, 3.4),
    ]

    for y in range(35, 55):
        fy = float(y)
        rx_h = interp_profile(rx_head_pts, fy)
        rz_f = interp_profile(rz_front_pts, fy)
        rz_b = interp_profile(rz_back_pts, fy)

        for x in range(W):
            dx = x - CX
            adx = abs(dx)
            for z in range(D):
                dz = z - CZ_HEAD
                rz_h = rz_f if dz >= 0 else rz_b
                nx = adx / rx_h
                nz = abs(dz) / rz_h
                p_exp = 2.05 + 0.15 * smoothstep(0.0, 3.0, dz) * smoothstep(35.0, 38.0, fy)
                r_ell = (nx ** p_exp + nz ** p_exp) ** (1.0 / p_exp)
                if r_ell <= 1.0:
                    face_w = 9.4 - 0.15 * max(0.0, 38.0 - fy)
                    is_face = (dz > 1.6) and (
                        (y <= 42 and adx <= face_w)
                        or (43 <= y <= 45 and adx <= 5.5)
                    )
                    if is_face:
                        if y == 35:
                            col = C_SKIN_SH  # もちっと顎下の柔らか影
                        elif y == 37 and 6.2 <= adx <= 8.8 and r_ell >= 0.72:
                            col = C_BLUSH_DEEP if (6.8 <= adx <= 8.2) else C_BLUSH_LIGHT
                        elif y == 36 and 6.5 <= adx <= 8.5 and r_ell >= 0.80:
                            col = C_BLUSH_LIGHT
                        elif r_ell >= 0.88 and adx >= 7.8:
                            col = C_SKIN_SH
                        else:
                            col = C_SKIN
                        set_vox(vol, part, x, y, z, col, P_SKIN)
                    else:
                        # 黒髪ドーム＋360度天使の輪ツヤ帯 (y=49..51)
                        if 49 <= y <= 51 and r_ell >= 0.80:
                            if y == 50 and dx <= 2.0 and dz >= -4.0:
                                col = C_HAIR_SPEC
                            elif y in (49, 50) and int(round(adx)) not in (2, 7):
                                col = C_HAIR_HI
                            else:
                                col = C_HAIR
                        elif y >= 52:
                            col = C_HAIR_HI if dx <= 2.5 else C_HAIR
                        elif y >= 43:
                            col = C_HAIR if dz >= -1.5 else C_HAIR_SH1
                        else:
                            col = C_HAIR_SH1 if dz >= -3.0 else C_HAIR_SH2
                        # 後ろ髪の縦毛束割れアクセント
                        if dz < -4.0 and r_ell >= 0.85 and 36 <= y <= 48:
                            if int(round(adx)) in (0, 4, 8):
                                col = C_HAIR_SH2
                        set_vox(vol, part, x, y, z, col, P_HAIR)

    # 後ろ髪ボブの下がり (y=32..36, 頭後ろ〜首後ろの丸みボブ)
    for y in range(32, 37):
        t = (36.0 - y) / 4.0
        rx_bk = 11.4 - 0.6 * t
        rz_bk = 9.2 - 0.8 * t
        for x in range(W):
            for z in range(D):
                dx = x - CX
                dz = z - CZ_HEAD
                if dz > -1.0:
                    continue
                rad = math.sqrt((dx / rx_bk) ** 2 + (dz / rz_bk) ** 2)
                if 0.62 <= rad <= 1.0:
                    col = C_HAIR_SH2 if (y <= 33 or int(round(abs(dx))) in (0, 4, 8)) else C_HAIR_SH1
                    set_vox(vol, part, x, y, z, col, P_HAIR)

    # 柔らかいジト目 (y=38..41, 表面から3vox奥まで埋めて斜め縦割れを完全防止！白ハイライトなし)
    for side in (-1.0, 1.0):
        # 左目 x=21..24, 右目 x=33..36（目幅4vox、目間8voxで幼く可愛いバランス）
        ex_range = range(21, 25) if side < 0 else range(33, 37)
        outer_x = 21 if side < 0 else 36
        for x in ex_range:
            for y in range(38, 42):
                # 表面Z探索
                front_z = -1
                for z in range(D - 1, int(CZ_HEAD), -1):
                    if vol[x][y][z] != -1 and part[x][y][z] == P_SKIN:
                        front_z = z
                        break
                if front_z >= 0:
                    if y == 41:
                        col_e = C_EYE_LASH
                    elif y == 40:
                        col_e = C_EYE_LASH if x == outer_x else C_EYE_HIGH
                    elif y == 39:
                        col_e = C_EYE_MID
                    else:
                        col_e = C_EYE_LOW
                    for depth in range(3):
                        set_vox(vol, part, x, y, front_z - depth, col_e, P_EYES)

    # 重めレイヤー前髪（目の上に空気感の肌見せ隙間＋縦毛束割れ影） (y=41..53)
    for y in range(41, 54):
        fy = float(y)
        rx_h = interp_profile(rx_head_pts, fy) + 0.30 * smoothstep(41.0, 47.0, fy)
        rz_f = interp_profile(rz_front_pts, fy)
        # 斜め3/4角度で目を覆いすぎないよう前髪厚みは程よいカーブに抑える
        bang_extra_z = 0.38 + 0.62 * smoothstep(41.0, 47.0, fy) * (1.0 - 0.65 * smoothstep(50.0, 54.0, fy))
        for x in range(W):
            dx = x - CX
            adx = abs(dx)
            if adx > 11.4:
                continue
            # 目の上の肌見せ隙間（水平パッツンを避ける可愛い束感！）
            if y == 41 and (adx > 2.2 and adx < 8.4):
                continue
            if y == 42 and (2.0 <= adx <= 3.1 or 5.2 <= adx <= 6.4):
                continue
            if y == 43 and (2.2 <= adx <= 2.9 or 5.5 <= adx <= 6.2):
                continue
            for z in range(int(CZ_HEAD + 2), D):
                dz = z - CZ_HEAD
                nx = adx / rx_h
                nz = dz / (rz_f + bang_extra_z)
                r_b = (nx ** 2.1 + nz ** 2.1) ** (1.0 / 2.1)
                if 0.76 <= r_b <= 1.0:
                    if 49 <= y <= 51 and adx <= 7.5:
                        col = C_HAIR_SPEC if (y == 50 and -4.5 <= dx <= 0.5) else C_HAIR_HI
                    elif y <= 45 and int(round(adx)) in (2, 5, 8):
                        col = C_HAIR_SH2  # 縦の毛束割れ影
                    elif y == 41 or y == 42:
                        col = C_HAIR_SH1
                    else:
                        col = C_HAIR if dx <= 2.0 else C_HAIR_SH1
                    set_vox(vol, part, x, y, z, col, P_HAIR)

    # 顔周りの垂れ横髪（頬から約1vox空気感を保って顎下 y=33 まで垂れる姫カット／ボブ横髪！）
    for side in (-1.0, 1.0):
        for y in range(33, 46):
            t = (45.0 - y) / 12.0
            sx = CX + side * (11.6 - 0.8 * (t ** 1.1))
            sz = CZ_HEAD + 3.4 - 0.8 * t
            rx_s = 1.65 - 0.45 * t
            rz_s = 2.45 - 0.65 * t
            for x in range(W):
                for z in range(D):
                    nx = (x - sx) / rx_s
                    nz = (z - sz) / rz_s
                    if nx * nx + nz * nz <= 1.0:
                        col = C_HAIR_SH2 if y <= 34 else (C_HAIR if side < 0 else C_HAIR_SH1)
                        set_vox(vol, part, x, y, z, col, P_HAIR)

    # 前髪ヘアアクセ2種（front_z+1へ突き出させず前髪曲面に沿って埋め込むことで、斜め3/4のトゲ化を防ぎ側面でも自然な曲線上に見える）
    # (1) ばってん(✕)ヘアピン (x=31..33, y=47..49・ベレー帽縁の下にすっきり収まる高さ)
    b_pts = [(31, 49), (33, 49), (32, 48), (31, 47), (33, 47)]
    for bx, by in b_pts:
        front_z = -1
        for z in range(D - 1, int(CZ_HEAD), -1):
            if vol[bx][by][z] != -1:
                front_z = z
                break
        if front_z >= 0:
            set_vox(vol, part, bx, by, front_z, C_WHITE, P_ACC)
            set_vox(vol, part, bx, by, front_z - 1, C_WHITE, P_ACC)

    # (2) 小さい白いうさぎ顔ピン (x=33..37, y=42..45・目まつ毛y=41と1px離して視認性向上)
    u_pattern = [
        (45, [(34, C_WHITE), (36, C_WHITE)]),
        (44, [(33, C_WHITE), (34, C_WHITE), (35, C_WHITE), (36, C_WHITE), (37, C_WHITE)]),
        (43, [(33, C_WHITE), (34, C_ACC_DARK), (35, C_WHITE), (36, C_ACC_DARK), (37, C_WHITE)]),
        (42, [(34, C_WHITE_SH), (35, C_WHITE_SH), (36, C_WHITE_SH)]),
    ]
    for uy, row_items in u_pattern:
        for ux, uc in row_items:
            front_z = -1
            for z in range(D - 1, int(CZ_HEAD), -1):
                if vol[ux][uy][z] != -1:
                    front_z = z
                    break
            if front_z >= 0:
                set_vox(vol, part, ux, uy, front_z, uc, P_ACC)
                set_vox(vol, part, ux, uy, front_z - 1, uc, P_ACC)


def stamp_ahoge(vol: list, part: list) -> list[tuple[int, int, int, int, int]]:
    """頭頂(y=54)からぴょこんとカーブする可愛いアホ毛（ベレー帽ON時にremoveできるよう座標リストも返す）。"""
    pts = [
        (28, 55, 21),
        (28, 56, 21),
        (27, 57, 21),
        (26, 58, 20),
        (25, 58, 20),
        (24, 57, 20),
    ]
    added = []
    for x, y, z in pts:
        # 6連結を保証するため前後の1voxブリッジも含めて繊細に繋ぐ
        set_vox(vol, part, x, y, z, C_HAIR_SH2, P_HAIR)
        added.append((x, y, z, C_HAIR_SH2, P_HAIR))
    # (28,56,21)と(27,57,21)などの斜めを6連結にするため角1voxを繋ぐ
    bridges = [
        (28, 57, 21),
        (27, 58, 21),
        (26, 58, 21),
        (25, 57, 20),
    ]
    for x, y, z in bridges:
        set_vox(vol, part, x, y, z, C_HAIR_SH1, P_HAIR)
        added.append((x, y, z, C_HAIR_SH1, P_HAIR))
    return added


def paint_half_twin_down(vol: list, part: list) -> None:
    """ベース髪型：ピンク丸位置（頭上サイド）から1vox空気スリットを空けて下向き＆毛先ハネのショートハーフツイン。"""
    for side in (-1.0, 1.0):
        # 頭との接続ブリッジ（y=47..49, 滑らかな弧で繋いで水平角張りを防ぎつつ6連結維持）
        for x_off in (11.2, 12.2, 13.2):
            bx = int(round(CX + side * x_off))
            for by in (47, 48):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)
        # 小さな黒結びリボン（外下）
        rx_k = int(round(CX + side * 13.8))
        for by in (47, 48):
            set_vox(vol, part, rx_k, by, int(CZ_HEAD + 1), C_HOODIE_HI, P_ACC)

        # 下向きショート毛束 (y=32..48): 頭から1vox空気スリットを保ちつつ下向き＋毛先ハネ！
        for y in range(32, 49):
            t = (48.0 - y) / 16.0
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
                        if y <= 33:
                            col = C_HAIR_SH2
                        elif nz > 0.15 and 41 <= y <= 43:
                            col = C_HAIR_HI
                        elif nz > -0.2:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)
            # 外側の軽い2又ハネ房
            if 0.55 <= t <= 0.90:
                fx = int(round(xc + side * (1.3 + 0.9 * (t - 0.55))))
                fz = int(round(zc - 0.8))
                for dx_f in (0, -int(side)):
                    set_vox(vol, part, fx + dx_f, y, fz, C_HAIR_SH1 if t < 0.78 else C_HAIR_SH2, P_HAIR)


def paint_half_flare(vol: list, part: list) -> None:
    """オプション髪型①（高め外ハネショート）：v1案Aの外ハネショートを約5px上の位置で結んだ軽やかシルエット。"""
    for side in (-1.0, 1.0):
        # 頭との接続ブリッジ (y=47..49)
        for x_off in (11.2, 12.2, 13.2):
            bx = int(round(CX + side * x_off))
            for by in (47, 48):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)

        # 外・後ろへふわっと弧を描いて2又に跳ねるショート毛束 (y=34..48)
        for y in range(34, 49):
            t = (48.0 - y) / 14.0
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
                        if y <= 35:
                            col = C_HAIR_SH2
                        elif nz > 0.1 and 42 <= y <= 44:
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


def paint_twin_high(vol: list, part: list) -> None:
    """オプション髪型②（高め腰丈ツインテ＋ふっくら黒リボン＆淡紫ハート宝石＆白十字チャーム）。"""
    for side in (-1.0, 1.0):
        # 頭との接続ブリッジ (y=48..50)
        for x_off in (10.5, 11.5, 12.5, 13.5):
            bx = int(round(CX + side * x_off))
            for by in (48, 49, 50):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)

        # 膨らみ控えめ・腰丈(y=19..49)のスラッと可愛い黒ツインテ
        for y in range(19, 50):
            t = (49.0 - y) / 30.0
            x_off = 13.8 + 2.8 * math.sin(t * math.pi * 0.78) + 0.7 * math.sin(t * math.pi * 2.1)
            z_off = -1.6 - 5.6 * (t ** 0.88) - 1.2 * math.sin(t * math.pi * 2.0)
            r_t = 2.15 + 0.82 * math.sin(t * math.pi * 0.82)
            if y <= 24:
                r_t *= max(0.42, 1.0 - (25.0 - y) / 7.2)
            xc = CX + side * x_off
            zc = CZ_HEAD + z_off
            for x in range(W):
                for z in range(D):
                    nx = (x - xc) / r_t
                    nz = (z - zc) / (r_t * 1.05)
                    if nx * nx + nz * nz <= 1.0:
                        if y <= 20:
                            col = C_HAIR_SH2
                        elif nz > 0.2 and y in (43, 44, 33, 34, 26, 27):
                            col = C_HAIR_HI
                        elif nz > -0.2:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1
                        set_vox(vol, part, x, y, z, col, P_HAIR)

        # ふっくら黒リボン＋中央淡紫ハート宝石＋垂れ白十字チャーム（黒髪と同化しないようリボン羽に明るめハイライトを添える）
        rx_c = int(round(CX + side * 13.2))
        ry_c = 49
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
        # 中央の淡紫ハート宝石＋繊細白枠（白四角になりすぎないよう中央3voxを宝石色＋四隅抜きで可愛く見せる）
        for dy_g in (-1, 0, 1):
            for dx_g in (-1, 0, 1):
                if abs(dx_g) == 1 and dy_g == -1:
                    continue
                c_g = C_LAVENDER_GEM if (dx_g == 0 and dy_g in (0, -1)) else C_WHITE
                set_vox(vol, part, rx_c + dx_g, ry_c + dy_g, rz_c + 1, c_g, P_ACC)
        # 垂れ白十字チャーム (y=45..47)
        for dy_c in (-2, -3, -4):
            set_vox(vol, part, rx_c, ry_c + dy_c, rz_c + 1, C_WHITE, P_ACC)
            set_vox(vol, part, rx_c, ry_c + dy_c, rz_c, C_WHITE_SH, P_ACC)
        set_vox(vol, part, rx_c - 1, ry_c - 3, rz_c + 1, C_WHITE, P_ACC)
        set_vox(vol, part, rx_c + 1, ry_c - 3, rz_c + 1, C_WHITE, P_ACC)


def paint_twin_arc(vol: list, part: list) -> None:
    """オプション髪型③（細身軽やかカーブツインテ・v1案C寄り：中腹で膨らみ毛先で柔らかく内側へ収まる弧）。"""
    for side in (-1.0, 1.0):
        # 頭との接続ブリッジ（やや中〜高め y=44..46）
        for x_off in (11.5, 12.5, 13.5):
            bx = int(round(CX + side * x_off))
            for by in (44, 45):
                for bz in (int(CZ_HEAD - 2), int(CZ_HEAD - 1), int(CZ_HEAD)):
                    set_vox(vol, part, bx, by, bz, C_HAIR_SH2, P_HAIR)
        # 小さめ黒結びリボン
        rx_k = int(round(CX + side * 13.6))
        for dx_k in (0, int(side)):
            for dy_k in (0, 1):
                set_vox(vol, part, rx_k + dx_k, 45 + dy_k, int(CZ_HEAD + 1), C_HOODIE_HI, P_ACC)
                set_vox(vol, part, rx_k + dx_k, 45 + dy_k, int(CZ_HEAD), C_HOODIE_SH, P_ACC)

        # 細身で外へ膨らみつつ毛先で柔らかく内側へ包む括弧カーブ (y=21..45)
        for y in range(21, 46):
            t = (45.0 - y) / 24.0
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
                        if y <= 22:
                            col = C_HAIR_SH2
                        elif nz > 0.15 and y in (37, 38, 29, 30):
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


def build_beret_mod(vol_base: list, ahoge_list: list[tuple[int, int, int, int, int]]) -> dict:
    """
    斜め＆深め被りの立体黒ベレー帽Mod：
    - 正面では向かって左へ斜め傾けて頭にすっぽり被せ（右のばってんy=47..49＆うさぎピンを邪魔しない）
    - 側面では額ラインにしっかり被さりつつ、高くなりすぎない平べったいベレー形を保って後ろへふわっと垂れる
    - 縁のギャザー編み目＋右サイドの白十字架＋左縁の白レース付き小リボン
    """
    beret_map: dict[tuple[int, int, int], tuple[int, int]] = {}
    cx_b = CX - 1.0
    cz_b = CZ_HEAD - 2.0

    for x in range(W):
        for z in range(D):
            ux = (x - cx_b) / 14.6
            uz = (z - cz_b) / 13.6
            r2 = ux * ux + uz * uz
            if r2 > 1.02:
                continue
            r = math.sqrt(r2)
            # 斜めチルト: 左(ux<0)へ約1.9vox深く被り、後ろ(uz<0)へ約1.8voxふわっと垂れる
            tilt = 1.9 * ux + 1.8 * uz
            dome = math.sqrt(max(0.0, 1.0 - min(1.0, r2 / 1.02)))
            # 高さを抑えた丸みベレー冠（縦長シルクハット化を防ぐ）
            y_top = int(round(52.0 + tilt + 4.7 * (dome ** 0.72)))
            # 縁(r>0.82)は下側を少しすぼめて頭にフィットさせる
            brim_tuck = 1.2 * smoothstep(0.75, 1.0, r)
            y_bot = int(round(49.2 + tilt + brim_tuck))
            if y_top < y_bot:
                continue
            for y in range(max(44, y_bot), min(H, y_top + 1)):
                # 頭の内部に完全埋没するボクセルはスキップし、表面〜外殻だけ上書き
                if vol_base[x][y][z] != -1 and r < 0.78 and y < y_top - 1:
                    continue
                if y == y_bot:
                    col = C_DARK
                elif y == y_bot + 1:
                    # ギャザー編み目
                    ang_i = int(round((math.atan2(uz, ux) + math.pi) * 6.0))
                    col = C_HOODIE if (ang_i % 2 == 0) else C_DARK
                elif y >= y_top - 1 and -0.45 <= ux <= 0.35 and -0.35 <= uz <= 0.55:
                    col = C_HOODIE_SPEC if (y == y_top and -0.25 <= ux <= 0.15) else C_HOODIE_HI
                elif uz >= -0.15:
                    col = C_HOODIE
                else:
                    col = C_HOODIE_SH
                beret_map[(x, y, z)] = (col, P_BERET)

    # ベレー帽向かって右前サイドの白十字架ワンポイント（表面フラッシュ埋め込みで側面からの出っ張りを防ぐ）
    cross_cx, cross_cy = int(round(CX + 7.2)), 53
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

    # 左縁の小さな黒リボン＆白レース添え（表面フラッシュ＋1vox最小厚で側面シルエットを綺麗に保つ）
    rib_lx, rib_ly = int(round(CX - 11.8)), 49
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
        "name": "黒髪パーカーちゃん",
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


def main() -> None:
    # 共通コア本体（髪型オプション差し替え前のベース）
    vol_core, part_core = new_grid()
    build_core_body(vol_core, part_core)
    ahoge_list = stamp_ahoge(vol_core, part_core)

    # 1) デフォルトベース（下向きショート・ハーフツイン）
    vol_base = [[row[:] for row in plane] for plane in vol_core]
    part_base = [[row[:] for row in plane] for plane in part_core]
    paint_half_twin_down(vol_base, part_base)
    pruned_base = prune_floating_voxels(vol_base, part_base)
    if pruned_base:
        print(f"[info] pruned floating in base: {pruned_base}")

    # 2) オプション髪型①: 高め外ハネショート
    vol_flare = [[row[:] for row in plane] for plane in vol_core]
    part_flare = [[row[:] for row in plane] for plane in part_core]
    paint_half_flare(vol_flare, part_flare)
    prune_floating_voxels(vol_flare, part_flare)

    # 3) オプション髪型②: 高め腰丈ツインテ（リボン＋紫ハート＋白十字）
    vol_th = [[row[:] for row in plane] for plane in vol_core]
    part_th = [[row[:] for row in plane] for plane in part_core]
    paint_twin_high(vol_th, part_th)
    prune_floating_voxels(vol_th, part_th)

    # 4) オプション髪型③: 細身軽やかカーブツインテ
    vol_ta = [[row[:] for row in plane] for plane in vol_core]
    part_ta = [[row[:] for row in plane] for plane in part_core]
    paint_twin_arc(vol_ta, part_ta)
    prune_floating_voxels(vol_ta, part_ta)

    mods = [
        build_beret_mod(vol_base, ahoge_list),
        extract_diff_mod("hair_flare", "外ハネショート", "hair_style", vol_base, part_base, vol_flare, part_flare),
        extract_diff_mod("hair_twin_high", "腰丈ツインテ", "hair_style", vol_base, part_base, vol_th, part_th),
        extract_diff_mod("hair_twin_arc", "細身ツインテ", "hair_style", vol_base, part_base, vol_ta, part_ta),
    ]

    export_assets(vol_base, part_base, mods)


if __name__ == "__main__":
    main()
