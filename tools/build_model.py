import json
import math
import os
from PIL import Image
from extract_refs import extract_references

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets")

# グローバル環境のNumPyにWin32 DLL不整合があるため、外部バイナリに依存しない標準ライブラリとPillowのみで3Dボリュームを生成する
W, H, D = 52, 52, 36

# ツインテールの縦ロールを暗い縞模様に見せないため、髪階調を自然なアイボリー〜温かみのあるベージュ影(#F8F4E8/#EFE7D4/#D9CEB8/#C4B7A1)へ統一し、暗色トープ(#5F5763/#7B727E)は衣装・リボン結び目・首・靴の境界線のみに限定する
PALETTE_HEX = [
    "#FFFFFF",
    "#F4F6FC",
    "#E3E6F2",
    "#CBD0E2",
    "#A6ABB8",
    "#7B727E",
    "#F8F4E8",
    "#EFE7D4",
    "#D9CEB8",
    "#C4B7A1",
    "#988C92",
    "#5F5763",
    "#FDF8F3",
    "#EEE0D6",
    "#F2D8D7",
    "#E0BEC0",
    "#E6E3F2",
    "#B5AED2",
    "#877EA5",
    "#524A5C",
    "#635A64",
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

PARTS_DEF = [
    {"id": "hair", "label": "髪"},
    {"id": "skin", "label": "肌・顔"},
    {"id": "eyes", "label": "目"},
    {"id": "outfit", "label": "服"},
    {"id": "ribbon", "label": "リボン"},
    {"id": "shoes", "label": "靴"},
]

P_HAIR = 0
P_SKIN = 1
P_EYES = 2
P_OUTFIT = 3
P_RIBBON = 4
P_SHOES = 5


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


def build_character2_volume() -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    # 4方向シルエットの単純交差では頭部が角張り腕・ツインテール・両脚が癒着するため、解剖学的パーツ単位の3D曲面で造形する
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    part_vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    cx0 = (W - 1) * 0.5
    # 斜め俯瞰(Quarter 32°/35°)で片側のツインテールが頭蓋裏に隠れないよう、頭部・体幹をボリューム奥行中央付近(z≈19.5)に配置する
    cz_body = 19.2
    cz_head = 19.6

    def set_vox(x: int, y: int, z: int, c: int, p: int) -> None:
        if 0 <= x < W and 0 <= y < H and 0 <= z < D:
            vol[x][y][z] = c
            part_vol[x][y][z] = p

    def set_sym(x_left: int, y: int, z: int, c: int, p: int) -> None:
        set_vox(x_left, y, z, c, p)
        set_vox(W - 1 - x_left, y, z, c, p)

    leg_dx = 2.45
    for y in range(0, 14):
        for side in (-1.0, 1.0):
            lx = cx0 + side * leg_dx
            if y <= 3:
                cz_shoe = cz_body + (0.65 if y <= 2 else 0.20)
                rx_s = 1.75 if y <= 2 else 1.58
                rz_s = 2.45 if y <= 2 else 2.00
                for x in range(W):
                    if abs(x - cx0) < 0.95:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_s
                        nz = (z - cz_shoe) / rz_s
                        d_s = (nx * nx) ** 1.25 + (nz * nz) ** 1.25
                        if d_s <= 1.0:
                            if y == 0:
                                col = C_LINE_DARK
                            elif y == 1:
                                col = C_LINE_MID if d_s > 0.55 else C_UNDER_SKIRT
                            elif y == 2:
                                col = C_DRESS_SH2 if (z >= cz_shoe + 0.2 and abs(x - lx) <= 0.9) else C_UNDER_SKIRT
                            else:
                                col = C_LINE_MID if (z >= cz_shoe + 0.4 or d_s > 0.72) else C_SKIN
                            # 足首の肌色ボクセルが靴パーツ一括塗り替えに巻き込まれないよう肌側へ分離する
                            set_vox(x, y, z, col, P_SKIN if col == C_SKIN else P_SHOES)
            else:
                rx_l = 1.52
                rz_l = 1.75
                for x in range(W):
                    if abs(x - cx0) < 0.95:
                        continue
                    for z in range(D):
                        nx = (x - lx) / rx_l
                        nz = (z - cz_body) / rz_l
                        if nx * nx + nz * nz <= 1.0:
                            if y >= 10:
                                col = C_SKIN_SH
                            elif z >= cz_body + 0.20 and abs(x - lx) <= 0.90:
                                col = C_SKIN
                            else:
                                col = C_SKIN_SH
                            set_vox(x, y, z, col, P_SKIN)

    # 両腕のパフ・ベルスリーブが身頃円錐に吸収されず明確に独立突出するよう、上半身(y=16..26)の身頃幅を華奢に絞り裾(y=10..13)だけふんわり広げる
    skirt_rx_pts = [
        (10.0, 10.6),
        (11.5, 11.4),
        (14.0, 9.6),
        (17.5, 6.8),
        (21.0, 4.9),
        (24.5, 3.6),
        (27.0, 2.7),
    ]
    skirt_rz_pts = [
        (10.0, 8.6),
        (11.5, 9.3),
        (14.0, 8.2),
        (17.5, 6.4),
        (21.0, 4.8),
        (24.5, 3.6),
        (27.0, 2.6),
    ]

    for y in range(10, 28):
        fy = float(y)
        rx_skirt = catmull_rom_interp(skirt_rx_pts, fy)
        rz_skirt = catmull_rom_interp(skirt_rz_pts, fy)

        for x in range(W):
            for z in range(D):
                dx = x - cx0
                dz = z - cz_body
                ang = math.atan2(dz, dx)
                pleat_amp = 0.55 * smoothstep(22.0, 11.5, fy)
                wave = math.cos(8.0 * ang)
                rx_eff = rx_skirt + pleat_amp * wave
                rz_eff = rz_skirt + pleat_amp * 0.85 * wave

                y_hem_local = 10.0 + 0.75 * ((abs(dx) / 11.4) ** 2) - 0.20 * wave
                if y < y_hem_local:
                    continue

                rad = math.sqrt((dx / rx_eff) ** 2 + (dz / rz_eff) ** 2)
                if rad <= 1.0:
                    # 見上げ角度(Low -25°)で平板な白い蓋に見えないようスカート裾内部を窪ませて暗色裏地にする
                    if y <= 13:
                        inner_hollow = 0.72 - 0.12 * (y - 10)
                        if rad < inner_hollow:
                            if vol[x][y][z] == -1 and y == 13:
                                set_vox(x, y, z, C_UNDER_SKIRT, P_OUTFIT)
                            continue

                    is_bottom_edge = (y - y_hem_local) < 1.0
                    if is_bottom_edge and rad >= 0.80:
                        col = C_LINE_DARK if y <= 10.6 else C_LINE_MID
                    elif is_bottom_edge:
                        col = C_UNDER_SKIRT
                    elif y == 26 and rad >= 0.76:
                        # 襟元の白フリルと身頃の区切りをトープ主線で引き締める
                        col = C_LINE_MID if (abs(dx) <= 2.6 and dz > 0) else C_DRESS_SH2
                    elif y == 27:
                        col = C_WHITE_HI if (rad >= 0.55 and int(round(abs(dx))) % 2 == 0) else C_DRESS_SH1
                    elif rad >= 0.82:
                        if wave < -0.42 and y <= 16:
                            col = C_LINE_SOFT if y <= 13 else C_DRESS_SH2
                        elif wave < -0.32 and y <= 22:
                            col = C_DRESS_SH2 if y <= 16 else C_DRESS_SH1
                        elif wave > 0.38 and dz >= -2.5:
                            col = C_WHITE_HI
                        elif dz < -1.5 and abs(dx) >= 1.2 and int(round(abs(dx))) in (2, 5):
                            col = C_DRESS_SH2 if y <= 16 else C_DRESS_SH1
                        else:
                            col = C_DRESS
                    else:
                        col = C_DRESS_SH1
                    set_vox(x, y, z, col, P_OUTFIT)

    # 腕がスカート円錐に埋没しないよう、肩(y=25)から外側へ張り出し中段〜袖口(y=15..19)で身頃から2〜3ボクセル明確に独立突出する丸いベルスリーブを造形する
    arm_x_pts = [
        (14.0, 10.8),
        (16.0, 11.3),
        (18.5, 10.4),
        (21.0, 8.2),
        (23.5, 5.8),
        (25.5, 3.8),
    ]
    arm_z_pts = [
        (14.0, cz_body + 0.75),
        (16.5, cz_body + 0.85),
        (19.5, cz_body + 0.55),
        (22.5, cz_body + 0.25),
        (25.5, cz_body + 0.05),
    ]
    arm_rx_pts = [
        (14.0, 1.55),
        (15.5, 2.55),
        (17.5, 2.75),
        (20.0, 2.10),
        (22.5, 1.65),
        (25.5, 1.55),
    ]
    arm_rz_pts = [
        (14.0, 1.80),
        (15.5, 3.05),
        (17.5, 3.25),
        (20.0, 2.35),
        (22.5, 1.85),
        (25.5, 1.75),
    ]

    for y in range(13, 26):
        fy = float(y)
        if y == 13:
            ax_off = 10.6
            az = cz_body + 0.70
            for side in (-1.0, 1.0):
                ax = cx0 + side * ax_off
                for x in range(W):
                    for z in range(D):
                        if ((x - ax) / 1.15) ** 2 + ((z - az) / 1.15) ** 2 <= 1.0:
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
                        # 正面・背面の白い袖表面に暗色ドットが散らないよう、身頃との接触溝(内側)と横向き輪郭の奥側折り返し部だけに主線を置く
                        near_body_seam = (dx_abs <= skirt_rx_here + 1.35) and (y <= 24)
                        is_inner_wall = ((side < 0 and nx >= 0.35) or (side > 0 and nx <= -0.35)) and (y <= 24)
                        is_back_fold_rim = (abs(nz) >= 0.72) and ((side * nx) <= -0.10) and (r2 >= 0.65) and (15 <= y <= 23)
                        if y == 14:
                            if r2 <= 0.34:
                                col = C_SKIN
                            elif r2 >= 0.68:
                                col = C_LINE_DARK
                            else:
                                col = C_DRESS_SH2
                        elif y == 15 and r2 >= 0.76 and ((side * nx) <= 0.25 or abs(nz) >= 0.65):
                            col = C_LINE_MID
                        elif near_body_seam and is_inner_wall:
                            col = C_LINE_DARK if y >= 17 else C_LINE_MID
                        elif is_back_fold_rim:
                            col = C_LINE_MID if (15 <= y <= 22) else C_LINE_SOFT
                        elif (side * nx) >= 0.05 and abs(nz) <= 0.75:
                            col = C_WHITE_HI
                        elif nz < -0.45:
                            col = C_DRESS_SH1
                        else:
                            col = C_DRESS
                        set_vox(x, y, z, col, P_SKIN if (y == 14 and col == C_SKIN) else P_OUTFIT)

    # 見上げ時に顎裏と二重線にならないよう首の引き締め主線は y=28 の1層に集中させつつ、正面・横から顎下ラインが明確に効く幅を確保する
    for x in range(W):
        for z in range(D):
            nx = (x - cx0) / 2.85
            nz = (z - cz_body) / 2.55
            if nx * nx + nz * nz <= 1.0:
                set_vox(x, 28, z, C_LINE_DARK, P_SKIN)

    rx_profile = [
        (29.0, 6.2),
        (30.0, 8.9),
        (31.5, 11.3),
        (33.5, 12.7),
        (36.5, 13.1),
        (40.5, 13.0),
        (44.5, 12.4),
        (48.0, 10.9),
        (50.0, 8.9),
        (51.0, 6.4),
    ]
    rz_front_profile = [
        (29.0, 5.5),
        (30.5, 7.5),
        (33.0, 8.7),
        (36.0, 8.9),
        (40.0, 9.0),
        (44.5, 8.7),
        (48.5, 7.4),
        (50.0, 5.7),
        (51.0, 4.0),
    ]
    rz_back_profile = [
        (29.0, 5.6),
        (31.0, 8.0),
        (35.0, 9.5),
        (40.0, 10.0),
        (45.0, 9.4),
        (48.5, 7.8),
        (50.0, 5.9),
        (51.0, 4.1),
    ]

    for y in range(29, 52):
        rx_h = catmull_rom_interp(rx_profile, float(y))
        rz_f = catmull_rom_interp(rz_front_profile, float(y))
        rz_b = catmull_rom_interp(rz_back_profile, float(y))

        for x in range(W):
            dx = x - cx0
            adx = abs(dx)
            for z in range(D):
                dz = z - cz_head
                rz_h = rz_f if dz >= 0.0 else rz_b
                nx = dx / rx_h
                nz = dz / rz_h
                r_ell = math.sqrt(nx * nx + nz * nz)
                if r_ell <= 1.0:
                    # 横ビューで頬中央に不自然な縦境界線が出ないよう、頬の肌領域を耳手前(dz > 1.6)まで滑らかに保つ
                    is_face_zone = (dz > 1.6) and (y <= 37) and (adx <= 10.1 - 0.16 * max(0.0, 33.0 - y))
                    if is_face_zone:
                        if y <= 30 and r_ell >= 0.78:
                            col = C_SKIN_SH
                        elif 32 <= y <= 34 and 6.8 <= adx <= 9.4 and r_ell >= 0.76:
                            col = C_BLUSH_DEEP if (y == 32 and adx >= 8.0) else C_BLUSH_LIGHT
                        elif r_ell >= 0.88 and adx >= 8.5:
                            col = C_SKIN_SH
                        else:
                            col = C_SKIN
                    else:
                        if y >= 47:
                            col = C_HAIR_SH1 if (y == 51 and r_ell <= 0.24) else C_HAIR_HI
                        elif y >= 40:
                            col = C_HAIR if dz < 2.0 else C_HAIR_HI
                        elif y >= 33:
                            col = C_HAIR_SH1 if dz < -1.2 else C_HAIR
                        else:
                            col = C_HAIR_SH2

                        if dz < -3.5 and r_ell >= 0.84 and 31 <= y <= 45:
                            t_back = (y - 31.0) / 14.0
                            curve_target = 2.2 + 3.6 * (t_back ** 0.8)
                            if abs(adx - curve_target) < 0.52 or (y <= 36 and adx < 0.60):
                                col = C_HAIR_SH2
                    set_vox(x, y, z, col, P_SKIN if is_face_zone else P_HAIR)

    # 横ビューで額から前髪下端(y=37)に四角い段差が出ないよう、張り出し量を smoothstep で毛先へ向けて滑らかに減衰させる
    for y in range(37, 50):
        fy = float(y)
        rx_h = catmull_rom_interp(rx_profile, fy) + 0.35 * smoothstep(36.5, 41.0, fy)
        rz_f = catmull_rom_interp(rz_front_profile, fy)
        bang_arch = smoothstep(36.2, 41.5, fy) * (1.0 - 0.65 * smoothstep(45.0, 50.0, fy))
        bang_extra_z = 0.45 + 0.95 * bang_arch

        for x in range(W):
            dx = x - cx0
            adx = abs(dx)
            if adx > 11.0:
                continue
            if y == 37 and abs(adx - 3.6) < 0.45:
                continue
            for z in range(int(cz_head + 1), D):
                dz = z - cz_head
                nx = dx / rx_h
                nz = dz / (rz_f + bang_extra_z)
                r_b = math.sqrt(nx * nx + nz * nz)
                if 0.76 <= r_b <= 1.0:
                    if y >= 46:
                        col = C_HAIR_HI
                    elif y in (37, 38) and r_b >= 0.86 and (abs(adx - 2.2) < 0.5 or abs(adx - 6.2) < 0.5):
                        # 長い直線バーコードを避けつつ前髪毛先の立体スリットを柔らかい髪影で整える
                        col = C_HAIR_SH2 if y == 37 else C_HAIR_SH1
                    elif y == 37 and r_b >= 0.88:
                        col = C_HAIR_SH1
                    else:
                        col = C_HAIR if y <= 43 else C_HAIR_HI
                    set_vox(x, y, z, col, P_HAIR)

    # 横ビューで頬を縦断する濃い線を作らないよう、姫カット横髪は耳前の側面帯(-1.4 <= dz <= 2.1)に収めつつ下端(y=32)のみ引き締める
    for y in range(32, 45):
        for side in (-1.0, 1.0):
            for x in range(W):
                dx_s = (x - cx0) * side
                if not (9.4 <= dx_s <= 13.7):
                    continue
                for z in range(int(cz_head - 2), int(cz_head + 6)):
                    dz = z - cz_head
                    z_front_limit = 2.1 if y <= 36 else 4.2
                    if dz > z_front_limit or dz < -1.4:
                        continue
                    rx_lock = 13.50 if y >= 34 else 13.20
                    rz_lock = 9.05
                    r_l = math.sqrt((dx_s / rx_lock) ** 2 + (dz / rz_lock) ** 2)
                    if 0.80 <= r_l <= 1.02:
                        if y == 32:
                            col = C_LINE_MID if dx_s >= 11.2 else C_HAIR_SH2
                        elif y == 33:
                            col = C_HAIR_SH1
                        elif y >= 41:
                            col = C_HAIR
                        else:
                            col = C_HAIR_SH1 if (dx_s >= 12.3 and dz < 0.5) else C_HAIR
                        set_vox(x, y, z, col, P_HAIR)

    # 顔曲面のZ段差で斜め視点(15°〜44°)から奥の肌色ボクセルが瞳の中央に縦割れ露出するのを防ぐため、各瞳列を表面から奥行2〜3層まで連続充填する
    for eye_y in range(33, 37):
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
                    if eye_y == 36:
                        c_side = C_EYE_LASH
                    elif eye_y == 35:
                        c_side = C_EYE_HIGH if z_off == 0 else C_EYE_LOW
                    elif eye_y == 34:
                        c_side = C_EYE_LOW if z_off == 0 else C_WHITE_HI
                    else:
                        c_side = C_EYE_WHITE
                    set_sym(lx, eye_y, z_surf - z_off, c_side, P_EYES)
                continue

            if eye_y == 36:
                col = C_EYE_LASH
            elif eye_y == 35:
                col = C_EYE_HIGH
            elif eye_y == 34:
                if local_u == 1:
                    col = C_WHITE_HI
                elif local_u == 5:
                    col = C_EYE_WHITE
                else:
                    col = C_EYE_LOW
            else:
                col = C_EYE_WHITE if 2 <= local_u <= 4 else C_SKIN

            neighbor_min_z = min(
                z_surfs.get(lx - 1, z_surf),
                z_surfs.get(lx + 1, z_surf),
                z_surf - 1,
            )
            fill_min_z = max(int(cz_head) + 2, neighbor_min_z)
            # 目尻下の肌色充填ボクセルを目パーツに含めると目一括塗り替えで顔肌が変色するため肌側へ帰属させる
            eye_part = P_SKIN if col == C_SKIN else P_EYES
            for z_fill in range(fill_min_z, z_surf + 1):
                set_sym(lx, eye_y, z_fill, col, eye_part)

    # 純白の羽根面(#FFFFFF)を潰さずに2D線画の明瞭さを出すため、中央結び目・髪との接地基部(lx=13)・下縁くびれのみに暗色トープ主線を配する
    z_knot = int(round(cz_head - 0.6))
    for y in range(44, 50):
        dy = y - 46
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
        set_sym(10, 43, z_knot + tz_s, C_WHITE_HI, P_RIBBON)
        set_sym(11, 43, z_knot + tz_s, C_LINE_MID, P_RIBBON)
        set_sym(10, 42, z_knot + tz_s, C_LINE_MID, P_RIBBON)

    # 暗い斜め縞を描き込むとゼブラ模様に見えるため、実際の3D螺旋オフセットと物理的に掘り込んだ巻き溝・重なり段差で縦ロールを造形し、自然な髪色陰影(#F8F4E8〜#C4B7A1)のみで塗り分ける
    tail_x_pts = [
        (8.0, 6.8),
        (11.0, 5.6),
        (16.0, 4.6),
        (23.5, 4.4),
        (31.0, 4.8),
        (38.0, 6.2),
        (43.0, 8.4),
        (46.0, 10.6),
    ]
    tail_z_pts = [
        (8.0, cz_head - 6.4),
        (12.0, cz_head - 7.0),
        (18.0, cz_head - 5.6),
        (22.5, cz_head - 5.0),
        (28.0, cz_head - 6.7),
        (35.0, cz_head - 5.2),
        (41.5, cz_head - 3.2),
        (46.0, cz_head - 1.7),
    ]
    tail_r_pts = [
        (8.0, 0.95),
        (10.5, 1.85),
        (14.5, 3.05),
        (21.0, 3.55),
        (29.0, 3.65),
        (37.0, 3.50),
        (43.0, 2.95),
        (46.0, 2.25),
    ]

    coil_period = 9.0
    for y in range(8, 47):
        fy = float(y)
        tx_base = catmull_rom_interp(tail_x_pts, fy)
        tz_base = catmull_rom_interp(tail_z_pts, fy)
        r_base = catmull_rom_interp(tail_r_pts, fy)

        phase = (46.0 - fy) / coil_period * (2.0 * math.pi)
        taper_amp = smoothstep(9.0, 14.5, fy) * smoothstep(46.5, 42.5, fy)

        helix_amp = 0.95 * taper_amp
        hx = tx_base + helix_amp * math.cos(phase)
        hz = tz_base + helix_amp * math.sin(phase)

        tier_bulge = 1.0 + 0.16 * taper_amp * math.sin(phase)

        for x in range(0, 16):
            for z in range(0, 26):
                dx_b = x - tx_base
                dz_b = z - tz_base
                dx_h = x - hx
                dz_h = z - hz
                dist_h = math.sqrt(dx_h * dx_h + dz_h * dz_h)
                ang = math.atan2(dz_b, dx_b)

                w = math.atan2(math.sin(ang - phase), math.cos(ang - phase))
                cos_w = math.cos(w)
                ridge_mod = 0.55 * max(0.0, cos_w)
                valley_carve = 1.15 * taper_amp * (max(0.0, -cos_w - 0.15) ** 1.35)

                r_eff = max(0.8, r_base * tier_bulge + ridge_mod * taper_amp - valley_carve)
                if dist_h <= r_eff:
                    on_surface = dist_h >= r_eff - 1.1
                    in_valley = (cos_w < -0.30) and (taper_amp > 0.15)
                    under_tier = (math.sin(phase) < -0.45) and (taper_amp > 0.20)
                    on_crest = (cos_w > 0.25) and (math.sin(phase) > -0.15)

                    if y <= 9:
                        col = C_HAIR_SH2 if y == 8 else C_HAIR_SH1
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

    return vol, part_vol


def export_assets(
    vol: list[list[list[int]]],
    part_vol: list[list[list[int]]],
    out_dir: str = ASSETS_DIR,
) -> None:
    os.makedirs(out_dir, exist_ok=True)
    palette_rgb = [hex_to_rgb(c) for c in PALETTE_HEX]

    voxels: list[list[int]] = []
    part_color_counts: list[dict[int, int]] = [{} for _ in PARTS_DEF]
    im_y = Image.new("RGBA", (H * W, D), (0, 0, 0, 0))
    py_y = im_y.load()

    im_z = Image.new("RGBA", (D * W, H), (0, 0, 0, 0))
    py_z = im_z.load()

    im_x = Image.new("RGBA", (W * D, H), (0, 0, 0, 0))
    py_x = im_x.load()

    for y in range(H):
        inv_y = H - 1 - y
        y_off = y * W
        for z in range(D):
            z_off = z * W
            for x in range(W):
                pi = vol[x][y][z]
                if pi >= 0:
                    part_i = part_vol[x][y][z]
                    assert part_i >= 0, f"Missing partIdx at {(x, y, z)}"
                    voxels.append([x, y, z, pi, part_i])
                    part_color_counts[part_i][pi] = part_color_counts[part_i].get(pi, 0) + 1
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
        "voxels": voxels,
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

    print(f"Exported model.json & 3 slice strips -> {out_dir}: {W}x{H}x{D}, solid voxels={len(voxels)}, parts={len(parts)}")


def main() -> None:
    extract_references()
    vol, part_vol = build_character2_volume()
    export_assets(vol, part_vol)


if __name__ == "__main__":
    main()
