import json
import math
import os
from PIL import Image
from extract_refs import REF_SHEET_PATH, extract_references

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets")

# グローバル環境のNumPyにWin32 DLL不整合があるため、外部バイナリに依存しない標準ライブラリとPillowのみで3Dボリュームを生成する
W, H, D = 52, 52, 36

# 髪は自然なアイボリー〜温かみのあるベージュ影(#F8F4E8/#EFE7D4/#D9CEB8/#C4B7A1)へ統一し、
# ジト目の紫グラデ(#5F5763/#8D84A8/#B9B2D0/#D8D3EA)・頬紅(#E8C6C8)・猫耳の温かみあるトープ毛並み(#A39286/#8A796D/#6F6056)を専用スロットに分離する
PALETTE_HEX = [
    "#FFFFFF",  # 0: C_WHITE_HI (純白ハイライト・猫耳内毛・瞳ハイライト)
    "#F4F6FC",  # 1: C_DRESS (白ドレス本体・猫耳内毛淡影)
    "#E3E6F2",  # 2: C_DRESS_SH1 (ドレス淡影)
    "#CBD0E2",  # 3: C_DRESS_SH2 (ドレス影)
    "#A6ABB8",  # 4: C_UNDER_SKIRT (スカート裏地・靴)
    "#7B727E",  # 5: C_LINE_MID (衣装・リボン・靴の中間主線)
    "#F8F4E8",  # 6: C_HAIR_HI (髪ハイライト・頭頂)
    "#EFE7D4",  # 7: C_HAIR (髪ベース)
    "#D9CEB8",  # 8: C_HAIR_SH1 (髪淡影・前髪毛先影)
    "#C4B7A1",  # 9: C_HAIR_SH2 (髪影・前髪中央束の縁アクセント)
    "#988C92",  # 10: C_LINE_SOFT (柔らか輪郭線)
    "#5F5763",  # 11: C_LINE_DARK (首・裾・靴底の引き締め線)
    "#FDF8F3",  # 12: C_SKIN (肌ベース)
    "#EEE0D6",  # 13: C_SKIN_SH (顎下・脚の肌影)
    "#F2D8D7",  # 14: C_BLUSH_LIGHT (淡いチーク)
    "#E8C6C8",  # 15: C_BLUSH_DEEP (目尻下の柔らかピンクチーク)
    "#D8D3EA",  # 16: C_EYE_WHITE (瞳下部・目頭寄りの淡ラベンダー光沢)
    "#B9B2D0",  # 17: C_EYE_LOW (瞳中段ラベンダー)
    "#8D84A8",  # 18: C_EYE_HIGH (瞳上段ラベンダーバイオレット)
    "#5F5763",  # 19: C_EYE_LASH (ジト目のくすみ暗色まつ毛バー)
    "#635A64",  # 20: C_DARK_TRIM (濃いアクセント線)
    "#A39286",  # 21: C_CAT_FUR_HI (猫耳外毛ハイライト)
    "#8A796D",  # 22: C_CAT_FUR (猫耳外毛メイン・温トープ)
    "#6F6056",  # 23: C_CAT_FUR_SH (猫耳外毛影・カチューシャ帯)
]

C_WHITE_HI = 0
C_DRESS = 1
C_DRESS_SH1 = 2
C_DRESS_SH2 = 3
C_UNDER_SKIRT = 4
C_LINE_MID = 5
C_HAIR_HI = 6
C_HAIR = 7
C_HAIR_SH1 = 8
C_HAIR_SH2 = 9
C_LINE_SOFT = 10
C_LINE_DARK = 11
C_SKIN = 12
C_SKIN_SH = 13
C_BLUSH_LIGHT = 14
C_BLUSH_DEEP = 15
C_EYE_WHITE = 16
C_EYE_LOW = 17
C_EYE_HIGH = 18
C_EYE_LASH = 19
C_DARK_TRIM = 20
C_CAT_FUR_HI = 21
C_CAT_FUR = 22
C_CAT_FUR_SH = 23

PARTS_DEF = [
    {"id": "hair", "label": "髪"},
    {"id": "skin", "label": "肌・顔"},
    {"id": "eyes", "label": "目"},
    {"id": "outfit", "label": "服"},
    {"id": "ribbon", "label": "リボン"},
    {"id": "shoes", "label": "靴"},
    {"id": "cat_ears", "label": "猫耳"},
]

P_HAIR = 0
P_SKIN = 1
P_EYES = 2
P_OUTFIT = 3
P_RIBBON = 4
P_SHOES = 5
P_CAT_EARS = 6


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
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


def build_base_volume(sharp_jaw_hair: bool = False) -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    """v5ベース本体（猫耳なし）を生成する。sharp_jaw_hair=True時は顎下1行を削り頭部を1ボクセル下げ、垂れ横髪を追加する。"""
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    part_vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    cx0 = (W - 1) * 0.5
    cz_body = 19.2
    cz_head = 19.6
    # sharp_jaw_hair有効時は頭部・リボン・ツインテール付け根を1ボクセル下げ、余分な顎下丸み行(旧y=26)を取り除く
    head_dy = -1 if sharp_jaw_hair else 0

    def set_vox(x: int, y: int, z: int, c: int, p: int) -> None:
        if 0 <= x < W and 0 <= y < H and 0 <= z < D:
            vol[x][y][z] = c
            part_vol[x][y][z] = p

    def set_sym(x_left: int, y: int, z: int, c: int, p: int) -> None:
        set_vox(x_left, y, z, c, p)
        set_vox(W - 1 - x_left, y, z, c, p)

    # 1. 両脚・靴 (y=0..12)
    leg_dx = 2.35
    for y in range(0, 13):
        for side in (-1.0, 1.0):
            lx = cx0 + side * leg_dx
            if y <= 2:
                cz_shoe = cz_body + (0.65 if y <= 1 else 0.25)
                rx_s = 1.70 if y <= 1 else 1.54
                rz_s = 2.35 if y <= 1 else 1.95
                for x in range(W):
                    if abs(x - cx0) < 0.90:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_s
                        nz = (z - cz_shoe) / rz_s
                        d_s = (nx * nx) ** 1.25 + (nz * nz) ** 1.25
                        if d_s <= 1.0:
                            if y == 0:
                                col = C_LINE_DARK
                            elif y == 1:
                                col = C_LINE_MID if d_s > 0.52 else C_UNDER_SKIRT
                            else:
                                col = C_DRESS_SH2 if (z >= cz_shoe + 0.15 and abs(x - lx) <= 0.85) else (
                                    C_LINE_MID if d_s > 0.68 else C_SKIN
                                )
                            set_vox(x, y, z, col, P_SKIN if col == C_SKIN else P_SHOES)
            else:
                rx_l = 1.46
                rz_l = 1.68
                for x in range(W):
                    if abs(x - cx0) < 0.90:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_l
                        nz = (z - cz_body) / rz_l
                        if nx * nx + nz * nz <= 1.0:
                            if y >= 9:
                                col = C_SKIN_SH
                            elif z >= cz_body + 0.20 and abs(x - lx) <= 0.85:
                                col = C_SKIN
                            else:
                                col = C_SKIN_SH
                            set_vox(x, y, z, col, P_SKIN)

    # 2. Aライン白ドレス (y=9..24)
    skirt_rx_pts = [
        (9.0, 10.7),
        (10.5, 11.7),
        (12.5, 10.4),
        (15.5, 7.6),
        (18.5, 5.4),
        (21.5, 3.8),
        (24.0, 2.7),
    ]
    skirt_rz_pts = [
        (9.0, 8.5),
        (10.5, 9.3),
        (12.5, 8.4),
        (15.5, 6.6),
        (18.5, 4.9),
        (21.5, 3.6),
        (24.0, 2.5),
    ]

    for y in range(9, 25):
        fy = float(y)
        rx_skirt = catmull_rom_interp(skirt_rx_pts, fy)
        rz_skirt = catmull_rom_interp(skirt_rz_pts, fy)

        for x in range(W):
            for z in range(D):
                dx = x - cx0
                dz = z - cz_body
                ang = math.atan2(dz, dx)
                pleat_amp = 0.62 * smoothstep(20.0, 10.5, fy)
                wave = math.cos(8.0 * ang)
                rx_eff = rx_skirt + pleat_amp * wave
                rz_eff = rz_skirt + pleat_amp * 0.85 * wave

                y_hem_local = 9.0 + 0.65 * ((abs(dx) / 11.7) ** 2) - 0.24 * wave
                if y < y_hem_local:
                    continue

                rad = math.sqrt((dx / rx_eff) ** 2 + (dz / rz_eff) ** 2)
                if rad <= 1.0:
                    if y <= 12:
                        inner_hollow = 0.72 - 0.12 * (y - 9)
                        if rad < inner_hollow:
                            if vol[x][y][z] == -1 and y == 12:
                                set_vox(x, y, z, C_UNDER_SKIRT, P_OUTFIT)
                            continue

                    is_bottom_edge = (y - y_hem_local) < 1.0
                    if is_bottom_edge and rad >= 0.80:
                        col = C_LINE_SOFT if (wave < -0.20 or y <= 9.4) else C_DRESS_SH2
                    elif is_bottom_edge:
                        col = C_UNDER_SKIRT
                    elif y == 23 and rad >= 0.76:
                        col = C_DRESS_SH2 if (abs(dx) <= 2.5 and dz > 0) else C_DRESS_SH1
                    elif y == 24:
                        col = C_WHITE_HI if (rad >= 0.55 and int(round(abs(dx))) % 2 == 0) else C_DRESS_SH1
                    elif rad >= 0.82:
                        if y == 10 and wave < -0.15:
                            col = C_DRESS_SH2
                        elif wave < -0.42 and y <= 15:
                            col = C_UNDER_SKIRT if y <= 12 else C_DRESS_SH2
                        elif wave < -0.28 and y <= 20:
                            col = C_DRESS_SH2 if y <= 15 else C_DRESS_SH1
                        elif wave > 0.34 and dz >= -2.5:
                            col = C_WHITE_HI
                        elif dz < -1.5 and abs(dx) >= 1.2 and int(round(abs(dx))) in (2, 5):
                            col = C_DRESS_SH2 if y <= 15 else C_DRESS_SH1
                        else:
                            col = C_DRESS
                    else:
                        col = C_DRESS_SH1
                    set_vox(x, y, z, col, P_OUTFIT)

    # 3. 華奢なベルスリーブ両腕 (y=12..23)
    arm_x_pts = [
        (13.0, 10.6),
        (14.8, 11.2),
        (17.0, 10.0),
        (19.5, 7.6),
        (21.5, 5.4),
        (23.2, 3.6),
    ]
    arm_z_pts = [
        (13.0, cz_body + 0.70),
        (15.5, cz_body + 0.80),
        (18.5, cz_body + 0.50),
        (21.0, cz_body + 0.25),
        (23.2, cz_body + 0.05),
    ]
    arm_rx_pts = [
        (13.0, 1.65),
        (14.5, 2.60),
        (16.2, 2.65),
        (18.5, 1.95),
        (21.0, 1.55),
        (23.2, 1.45),
    ]
    arm_rz_pts = [
        (13.0, 1.85),
        (14.5, 2.95),
        (16.2, 3.05),
        (18.5, 2.20),
        (21.0, 1.75),
        (23.2, 1.65),
    ]

    for y in range(12, 24):
        fy = float(y)
        if y == 12:
            ax_off = 10.4
            az = cz_body + 0.65
            for side in (-1.0, 1.0):
                ax = cx0 + side * ax_off
                for x in range(W):
                    for z in range(D):
                        if ((x - ax) / 1.10) ** 2 + ((z - az) / 1.10) ** 2 <= 1.0:
                            set_vox(x, y, z, C_SKIN, P_SKIN)
            continue

        arm_x_off = catmull_rom_interp(arm_x_pts, fy)
        arm_z = catmull_rom_interp(arm_z_pts, fy)
        r_arm_x = catmull_rom_interp(arm_rx_pts, fy)
        r_arm_z = catmull_rom_interp(arm_rz_pts, fy)
        skirt_rx_here = catmull_rom_interp(skirt_rx_pts, fy)

        for side in (-1.0, 1.0):
            ax = cx0 + side * arm_x_off
            for x in range(W):
                dx_abs = abs(x - cx0)
                for z in range(D):
                    nx = (x - ax) / r_arm_x
                    nz = (z - arm_z) / r_arm_z
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        near_body_seam = (dx_abs <= skirt_rx_here + 1.30) and (y <= 22)
                        is_inner_wall = ((side < 0 and nx >= 0.35) or (side > 0 and nx <= -0.35)) and (y <= 22)
                        is_back_fold_rim = (abs(nz) >= 0.72) and ((side * nx) <= -0.10) and (r2 >= 0.65) and (14 <= y <= 21)
                        if y == 13:
                            if r2 <= 0.34:
                                col = C_SKIN
                            elif r2 >= 0.70:
                                col = C_LINE_SOFT
                            else:
                                col = C_DRESS_SH2
                        elif y == 14 and r2 >= 0.76 and ((side * nx) <= 0.20 or abs(nz) >= 0.68):
                            col = C_DRESS_SH2 if (side * nx) > 0.0 else C_UNDER_SKIRT
                        elif near_body_seam and is_inner_wall:
                            col = C_UNDER_SKIRT if y >= 16 else C_DRESS_SH2
                        elif is_back_fold_rim:
                            col = C_DRESS_SH2 if (14 <= y <= 20) else C_DRESS_SH1
                        elif (side * nx) >= 0.05 and abs(nz) <= 0.75:
                            col = C_WHITE_HI
                        elif nz < -0.45:
                            col = C_DRESS_SH1
                        else:
                            col = C_DRESS
                        set_vox(x, y, z, col, P_SKIN if (y == 13 and col == C_SKIN) else P_OUTFIT)

    # 4. 首 (y=25)
    for x in range(W):
        for z in range(D):
            nx = (x - cx0) / 2.65
            nz = (z - cz_body) / 2.35
            if nx * nx + nz * nz <= 1.0:
                set_vox(x, 25, z, C_LINE_DARK, P_SKIN)

    # 5. 頭部ベース (ベース: y=26..46, sharp_jaw_hair時: 旧y=26を省き y=27..46 を y-1 -> y=26..45 へ配置)
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

    head_y_start = 27 if sharp_jaw_hair else 26
    for y_raw in range(head_y_start, 47):
        fy = float(y_raw)
        y = y_raw + head_dy
        rx_h = catmull_rom_interp(rx_profile, fy)
        rz_f = catmull_rom_interp(rz_front_profile, fy)
        rz_b = catmull_rom_interp(rz_back_profile, fy)
        # sharp_jaw_hair時は下顎(y_raw=27)の幅をわずかにすっきり絞ってアニメ調のクリーンな顎ラインにする
        if sharp_jaw_hair and y_raw == 27:
            rx_h = 8.1

        for x in range(W):
            dx = x - cx0
            adx = abs(dx)
            for z in range(D):
                dz = z - cz_head
                rz_h = rz_f if dz >= 0.0 else rz_b
                nx = abs(dx) / rx_h
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
                        if y_raw == 26:
                            col = C_SKIN_SH
                        elif y_raw == 27 and (r_ell >= 0.72 or adx >= 6.8 or sharp_jaw_hair):
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
                        if y_raw >= 42:
                            col = C_HAIR_SH1 if (y_raw == 46 and r_ell <= 0.24) else C_HAIR_HI
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
                    set_vox(x, y, z, col, P_SKIN if is_face_zone else P_HAIR)

    # 6. 重めレイヤー前髪
    for y_raw in range(32, 46):
        fy = float(y_raw)
        y = y_raw + head_dy
        rx_h = catmull_rom_interp(rx_profile, fy) + 0.32 * smoothstep(32.5, 38.0, fy)
        rz_f = catmull_rom_interp(rz_front_profile, fy)
        bang_arch = smoothstep(31.5, 38.5, fy) * (1.0 - 0.70 * smoothstep(41.5, 45.5, fy))
        bang_extra_z = 0.42 + 0.92 * bang_arch

        for x in range(W):
            dx = x - cx0
            adx = abs(dx)
            if adx > 11.2:
                continue
            if y_raw in (32, 33) and adx > 2.6:
                continue
            if y_raw == 34 and (3.2 <= adx <= 4.8):
                continue
            if y_raw == 35 and (3.2 <= adx <= 4.7):
                continue
            if y_raw == 36 and (3.3 <= adx <= 4.1):
                continue

            for z in range(int(cz_head + 1), D):
                dz = z - cz_head
                nx = abs(dx) / rx_h
                nz = dz / (rz_f + bang_extra_z)
                p_b = 2.15
                r_b = (nx ** p_b + nz ** p_b) ** (1.0 / p_b)
                if 0.77 <= r_b <= 1.0:
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
                    set_vox(x, y, z, col, P_HAIR)

    # 7. 顔周りの横髪 — sharp_jaw_hair時は頬から約1ボクセルの自然な隙間を空け、顎下まで約2ボクセル垂れ下がる柔らかい毛束にする
    for y_raw in range(28, 42):
        y = y_raw + head_dy
        for side in (-1.0, 1.0):
            for x in range(W):
                dx_s = (x - cx0) * side
                if not (9.3 <= dx_s <= 13.5):
                    continue
                for z in range(int(cz_head - 2), int(cz_head + 6)):
                    dz = z - cz_head
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
                        set_vox(x, y, z, col, P_HAIR)

    if sharp_jaw_hair:
        # 頬輪郭に張り付かせず1ボクセルほど隙間を空けて自然に垂れ下がる左右の顔周り毛束 (y=25..29, 顎下約2ボクセル分)
        for y in range(25, 30):
            t_hang = clamp((29.0 - y) / 4.0, 0.0, 1.0)
            # 上部は頬外縁の横髪(adx≈11.5)と滑らかに接続し、下端(y=25)へわずかに外寄り〜すぼみながら垂れる
            lock_cx = 11.55 - 0.35 * t_hang
            lock_rx = 1.65 - 0.55 * (t_hang ** 1.2)
            lock_cz = cz_head + 2.35 - 0.35 * t_hang
            lock_rz = 1.75 - 0.45 * t_hang
            for side in (-1.0, 1.0):
                cx_s = cx0 + side * lock_cx
                for x in range(W):
                    adx = abs(x - cx0)
                    # 下顎(adx<=8.5)との間に自然な約1ボクセルの抜け感を残す
                    if y <= 27 and adx < 10.0:
                        continue
                    for z in range(int(cz_head), int(cz_head + 7)):
                        nx = (x - cx_s) / max(0.75, lock_rx)
                        nz = (z - lock_cz) / max(0.75, lock_rz)
                        if nx * nx + nz * nz <= 1.0:
                            if y == 25:
                                col = C_HAIR_SH2
                            elif y == 26:
                                col = C_HAIR_SH1 if (z >= lock_cz - 0.2) else C_HAIR_SH2
                            elif (side * (x - cx_s)) > 0.35 and z < lock_cz:
                                col = C_HAIR_SH1
                            else:
                                col = C_HAIR
                            set_vox(x, y, z, col, P_HAIR)

    # 8. 眠たげジト目 (y_raw=30..33 -> y=y_raw+head_dy, lx=16..21)
    for eye_y_raw in range(30, 34):
        eye_y = eye_y_raw + head_dy
        z_surfs: dict[int, int] = {}
        for lx in range(16, 22):
            zs = -1
            for z in range(D - 1, int(cz_head), -1):
                if vol[lx][eye_y][z] != -1:
                    zs = z
                    break
            z_surfs[lx] = zs

        for lx in range(16, 22):
            z_surf = z_surfs[lx]
            if z_surf == -1:
                continue
            local_u = lx - 16
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
                    col = C_WHITE_HI
                elif local_u == 5:
                    col = C_EYE_WHITE
                else:
                    col = C_EYE_LOW
            else:
                col = C_EYE_WHITE if 1 <= local_u <= 4 else C_SKIN

            neighbor_min_z = min(
                z_surfs.get(lx - 1, z_surf),
                z_surfs.get(lx + 1, z_surf),
                z_surf - 1,
            )
            fill_min_z = max(int(cz_head) + 2, neighbor_min_z)
            eye_part = P_SKIN if col == C_SKIN else P_EYES
            for z_fill in range(fill_min_z, z_surf + 1):
                set_sym(lx, eye_y, z_fill, col, eye_part)

    return vol, part_vol


def build_twintails_mod(head_dy: int = -1) -> dict:
    """純白蝶リボン＋3D立体螺旋ツインテールの独立Modを生成する。"""
    cz_head = 19.6
    tt_map: dict[tuple[int, int, int], tuple[int, int]] = {}

    def set_vox(x: int, y: int, z: int, c: int, p: int) -> None:
        ny = y + head_dy
        if 0 <= x < W and 0 <= ny < H and 0 <= z < D:
            tt_map[(x, ny, z)] = (c, p)

    def set_sym(x_left: int, y: int, z: int, c: int, p: int) -> None:
        set_vox(x_left, y, z, c, p)
        set_vox(W - 1 - x_left, y, z, c, p)

    # 純白蝶リボン (y=39..44)
    z_knot = int(round(cz_head - 2.2))
    for y in range(39, 45):
        dy = y - 41
        for dz in range(-4, 5):
            z = z_knot + dz
            adz = abs(dz)
            if adz == 0:
                if -1 <= dy <= 1:
                    for lx in (10, 11, 12, 13):
                        set_sym(lx, y, z, C_LINE_DARK if dy == 0 else C_LINE_MID, P_RIBBON)
            else:
                y_min_w = -1 if adz >= 2 else 0
                y_max_w = 2 if adz in (2, 3) else 1
                if y_min_w <= dy <= y_max_w:
                    x_outer = 9 if (1 <= adz <= 3 and 0 <= dy <= 1) else 10
                    for lx in range(x_outer, 14):
                        is_hair_contact = lx == 13
                        is_inner_pinch = (adz == 1) and (dy == y_min_w or dy == y_max_w)
                        if is_hair_contact and (dy == y_min_w or dy == y_max_w or adz == 4):
                            col = C_LINE_MID
                        elif is_inner_pinch and lx >= 10:
                            col = C_LINE_MID
                        elif dy == y_min_w and lx >= 11:
                            col = C_LINE_MID if adz <= 2 else C_LINE_SOFT
                        elif dy == y_min_w:
                            col = C_DRESS_SH1
                        elif dy >= 1 or lx <= 10 or adz >= 3:
                            col = C_WHITE_HI
                        else:
                            col = C_DRESS
                        set_sym(lx, y, z, col, P_RIBBON)

    for tz_s in (-2, 2):
        set_sym(10, 38, z_knot + tz_s, C_WHITE_HI, P_RIBBON)
        set_sym(11, 38, z_knot + tz_s, C_LINE_MID, P_RIBBON)
        set_sym(10, 37, z_knot + tz_s, C_LINE_MID, P_RIBBON)

    # 3D立体螺旋の縦ロールツインテール (y=6..42)
    tail_x_pts = [
        (6.0, 6.8),
        (9.0, 5.5),
        (14.0, 4.5),
        (21.0, 4.3),
        (28.0, 4.8),
        (34.5, 6.2),
        (39.0, 8.4),
        (42.0, 10.7),
    ]
    tail_z_pts = [
        (6.0, cz_head - 6.8),
        (10.0, cz_head - 7.3),
        (16.0, cz_head - 6.0),
        (20.5, cz_head - 5.4),
        (26.0, cz_head - 6.9),
        (32.5, cz_head - 5.6),
        (38.0, cz_head - 3.8),
        (42.0, cz_head - 2.6),
    ]
    tail_r_pts = [
        (6.0, 0.95),
        (8.5, 1.85),
        (12.5, 3.00),
        (19.0, 3.50),
        (26.5, 3.60),
        (34.0, 3.45),
        (39.0, 2.90),
        (42.0, 2.25),
    ]

    coil_period = 8.6
    for y in range(6, 43):
        fy = float(y)
        tx_base = catmull_rom_interp(tail_x_pts, fy)
        tz_base = catmull_rom_interp(tail_z_pts, fy)
        r_base = catmull_rom_interp(tail_r_pts, fy)

        phase = (42.0 - fy) / coil_period * (2.0 * math.pi)
        taper_amp = smoothstep(7.0, 12.5, fy) * smoothstep(42.5, 38.5, fy)

        helix_amp = 0.92 * taper_amp
        hx = tx_base + helix_amp * math.cos(phase)
        hz = tz_base + helix_amp * math.sin(phase)

        tier_bulge = 1.0 + 0.16 * taper_amp * math.sin(phase)

        for x in range(0, 16):
            for z in range(0, 25):
                dx_b = x - tx_base
                dz_b = z - tz_base
                dx_h = x - hx
                dz_h = z - hz
                dist_h = math.sqrt(dx_h * dx_h + dz_h * dz_h)
                ang = math.atan2(dz_b, dx_b)

                w = math.atan2(math.sin(ang - phase), math.cos(ang - phase))
                cos_w = math.cos(w)
                ridge_mod = 0.54 * max(0.0, cos_w)
                valley_carve = 1.12 * taper_amp * (max(0.0, -cos_w - 0.15) ** 1.35)

                r_eff = max(0.8, r_base * tier_bulge + ridge_mod * taper_amp - valley_carve)
                if dist_h <= r_eff:
                    on_surface = dist_h >= r_eff - 1.1
                    in_valley = (cos_w < -0.30) and (taper_amp > 0.15)
                    under_tier = (math.sin(phase) < -0.45) and (taper_amp > 0.20)
                    on_crest = (cos_w > 0.25) and (math.sin(phase) > -0.15)

                    if y <= 7:
                        col = C_HAIR_SH2 if y == 6 else C_HAIR_SH1
                    elif on_surface and (in_valley and cos_w < -0.58):
                        col = C_HAIR_SH2
                    elif on_surface and (in_valley or under_tier):
                        col = C_HAIR_SH2 if (in_valley and under_tier) else C_HAIR_SH1
                    elif on_surface and on_crest and dz_h >= -1.0:
                        col = C_HAIR_HI
                    elif on_surface and dz_h < -1.2:
                        col = C_HAIR_SH1
                    else:
                        col = C_HAIR
                    set_sym(x, y, z, col, P_HAIR)

    add_list = [[x, y, z, c, p] for (x, y, z), (c, p) in sorted(tt_map.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0]))]
    return {
        "id": "twintails",
        "label": "ツインテ",
        "defaultEnabled": True,
        "remove": [],
        "add": add_list,
    }


def build_cat_ears_mod(vol_base: list[list[list[int]]], head_dy: int = -1) -> dict:
    """大きめ＆ふわふわの猫耳カチューシャModを生成する。"""
    cx0 = (W - 1) * 0.5
    cz_head = 19.6
    ear_map: dict[tuple[int, int, int], tuple[int, int]] = {}

    def put_ear(x: int, y: int, z: int, c: int) -> None:
        ny = y + head_dy
        if 0 <= x < W and 0 <= ny < H and 0 <= z < D:
            ear_map[(x, ny, z)] = (c, P_CAT_EARS)

    # 頭頂に沿う極細カチューシャ帯
    z_band = int(round(cz_head + 1.5))
    for x in range(W):
        dx = x - cx0
        adx = abs(dx)
        if adx > 10.6:
            continue
        t_arc = clamp(adx / 10.6, 0.0, 1.0)
        y_arc_f = 46.2 - 4.3 * (t_arc ** 2.05)
        y_arc = int(round(y_arc_f))
        if 0 <= z_band < D:
            col_b = C_CAT_FUR_SH if adx <= 4.0 else C_CAT_FUR
            put_ear(x, y_arc, z_band, col_b)
            ny_below = y_arc - 1 + head_dy
            if 0 <= ny_below < H and vol_base[x][ny_below][z_band] == -1 and adx <= 9.2:
                put_ear(x, y_arc - 1, z_band, C_CAT_FUR_SH)

    # 左右の大きめふんわり猫耳 (y=43..51): v5より根元を広く・背を高く・純白内毛と温トープ外毛を豊かに造形する
    for side in (-1.0, 1.0):
        for y in range(43, 52):
            t_h = clamp((y - 43.0) / 8.0, 0.0, 1.0)
            ear_cx = cx0 + side * (6.2 + 2.9 * (t_h ** 0.88))
            ear_cz = cz_head + 1.95 - 0.70 * t_h
            ear_rx = 4.35 * (1.0 - 0.72 * (t_h ** 1.18))
            ear_rz = 2.65 * (1.0 - 0.50 * (t_h ** 1.12))

            for x in range(W):
                for z in range(D):
                    ex = (x - ear_cx) / max(0.85, ear_rx)
                    ez = (z - ear_cz) / max(0.85, ear_rz)
                    r_ear = math.sqrt(ex * ex + ez * ez)
                    if r_ear <= 1.05:
                        if y == 43 and abs(x - cx0) < 5.5:
                            continue
                        if y == 44 and abs(x - cx0) < 3.6:
                            continue
                        is_front = ez >= 0.04
                        inner_thresh = 0.70 * (1.0 - 0.66 * t_h)
                        in_white_fur = (
                            is_front
                            and (44 <= y <= 49)
                            and (abs(ex) <= inner_thresh + 0.08)
                            and (ez >= 0.12)
                        )
                        if in_white_fur:
                            if y == 44 or abs(ex) >= inner_thresh - 0.06:
                                col = C_DRESS
                            else:
                                col = C_WHITE_HI
                        else:
                            if ez < -0.35 or y <= 43:
                                col = C_CAT_FUR_SH
                            elif (side * ex) > 0.40 or y >= 50:
                                col = C_CAT_FUR_HI if (ez >= -0.15) else C_CAT_FUR
                            elif ez >= 0.28 and abs(ex) > inner_thresh:
                                col = C_CAT_FUR_HI if y >= 46 else C_CAT_FUR
                            else:
                                col = C_CAT_FUR
                        put_ear(x, y, z, col)

    add_list = [[x, y, z, c, p] for (x, y, z), (c, p) in sorted(ear_map.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0]))]
    return {
        "id": "cat_ears",
        "label": "猫耳",
        "defaultEnabled": True,
        "remove": [],
        "add": add_list,
    }


def build_sharp_jaw_hair_mod(
    vol_base: list[list[list[int]]],
    part_base: list[list[list[int]]],
    vol_sharp: list[list[list[int]]],
    part_sharp: list[list[list[int]]],
) -> dict:
    """ベースとsharp_jaw_hair版の厳密差分を抽出し、トグル時に1ボクセルの誤差もなく切替可能にする。"""
    remove_list: list[list[int]] = []
    add_list: list[list[int]] = []
    for y in range(H):
        for z in range(D):
            for x in range(W):
                cb, pb = vol_base[x][y][z], part_base[x][y][z]
                cs, ps = vol_sharp[x][y][z], part_sharp[x][y][z]
                if cb >= 0 and cs < 0:
                    remove_list.append([x, y, z])
                elif cs >= 0 and (cb != cs or pb != ps):
                    add_list.append([x, y, z, cs, ps])
    return {
        "id": "sharp_jaw_hair",
        "label": "すっきり顎・垂れ髪",
        "defaultEnabled": True,
        "remove": remove_list,
        "add": add_list,
    }


def compose_mods(
    base_voxels: list[list[int]],
    mods: list[dict],
    active_ids: set[str],
) -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    """viewer側(loader.js)のcomposeAssetVoxelsと同一仕様でModを合成する。"""
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    part_vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    for vx, vy, vz, ci, pi in base_voxels:
        vol[vx][vy][vz] = ci
        part_vol[vx][vy][vz] = pi

    for mod in mods:
        if mod["id"] not in active_ids:
            continue
        dx = dy = dz = 0
        for other_id, off in mod.get("offsetWhen", {}).items():
            if other_id in active_ids:
                dx += off[0]
                dy += off[1]
                dz += off[2]
        for rx, ry, rz in mod.get("remove", []):
            nx, ny, nz = rx + dx, ry + dy, rz + dz
            if 0 <= nx < W and 0 <= ny < H and 0 <= nz < D:
                vol[nx][ny][nz] = -1
                part_vol[nx][ny][nz] = -1
        for ax, ay, az, ci, pi in mod.get("add", []):
            nx, ny, nz = ax + dx, ay + dy, az + dz
            if 0 <= nx < W and 0 <= ny < H and 0 <= nz < D:
                vol[nx][ny][nz] = ci
                part_vol[nx][ny][nz] = pi

    return vol, part_vol


def export_assets(
    vol_base: list[list[list[int]]],
    part_base: list[list[list[int]]],
    mods: list[dict],
    out_dir: str = ASSETS_DIR,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    palette_rgb = [hex_to_rgb(c) for c in PALETTE_HEX]

    base_voxels: list[list[int]] = []
    part_color_counts: list[dict[int, int]] = [{} for _ in PARTS_DEF]
    for y in range(H):
        for z in range(D):
            for x in range(W):
                pi = vol_base[x][y][z]
                if pi >= 0:
                    part_i = part_base[x][y][z]
                    assert part_i >= 0, f"Missing partIdx at {(x, y, z)}"
                    base_voxels.append([x, y, z, pi, part_i])
                    part_color_counts[part_i][pi] = part_color_counts[part_i].get(pi, 0) + 1

    # Mod専用パーツ(cat_ears等)のcolorIndicesもparts定義へ登録しておく
    for mod in mods:
        for _ax, _ay, _az, ci, part_i in mod.get("add", []):
            part_color_counts[part_i][ci] = part_color_counts[part_i].get(ci, 0) + 1

    # 静的スライスPNGは初期有効状態(defaultEnabled=True)を反映して書き出す
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
                pi = vol_default[x][y][z]
                if pi >= 0:
                    default_solid += 1
                    rgba = (*palette_rgb[pi], 255)
                    py_y[y_off + x, z] = rgba
                    py_z[z_off + x, inv_y] = rgba
                    py_x[x * D + z, inv_y] = rgba

    im_y.save(os.path.join(out_dir, "slices_y.png"))
    im_z.save(os.path.join(out_dir, "slices_z.png"))
    im_x.save(os.path.join(out_dir, "slices_x.png"))

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
        "name": "Character 2",
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

    model_path = os.path.join(out_dir, "model.json")
    with open(model_path, "w", encoding="utf-8") as f:
        json.dump(model_data, f, ensure_ascii=False, separators=(",", ":"))

    print(
        f"Exported model.json (base={len(base_voxels)}, mods={len(mods)}) & default-enabled slice strips (solid={default_solid}) -> {out_dir}"
    )


def main() -> None:
    if REF_SHEET_PATH and os.path.isfile(REF_SHEET_PATH):
        extract_references()
    # すっきり顎・垂れ髪をベース本体へ焼き込み、オプションModはツインテと猫耳の2種に集約する
    vol_base, part_base = build_base_volume(sharp_jaw_hair=True)
    mods = [
        build_twintails_mod(head_dy=-1),
        build_cat_ears_mod(vol_base, head_dy=-1),
    ]
    export_assets(vol_base, part_base, mods)


if __name__ == "__main__":
    main()
