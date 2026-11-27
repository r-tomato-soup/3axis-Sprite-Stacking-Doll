import json
import math
import os
import sys
from collections import deque
from PIL import Image, ImageDraw
from render_check import hex_to_rgb, render_ortho_dda, verify_contract

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets")
BUNNY_DIR = os.path.join(ASSETS_DIR, "bunny")
REF_SHEET_PATH = os.environ.get("BUNNY_REF_SHEET_PATH", "")
CHECK_OUT = os.environ.get(
    "BUNNY_CHECK_OUT",
    os.path.join(PROJECT_ROOT, "tmp", "bunny_check.png"),
)

# CHARACTER 2と同一の52x52x36座標契約を守ることで、キャラ切替時にカメラ距離やスライス描画設定が一切崩れないようにする
W, H, D = 52, 52, 36

PALETTE_HEX = [
    "#6C6170",
    "#7B7080",
    "#5B515F",
    "#4C4350",
    "#857489",
    "#FFFFFF",
    "#F6F1F8",
    "#E7DFEC",
    "#F2D8EC",
    "#E7C2DF",
    "#D4A7CA",
    "#B898B5",
    "#967895",
]

C_BASE = 0
C_HI = 1
C_SH1 = 2
C_CREASE = 3
C_CHEEK = 4
C_WHITE = 5
C_STITCH = 6
C_LACE_SH = 7
C_BOW_HI = 8
C_BOW_MID = 9
C_BOW_SH = 10
C_BOW_KNOT = 11
C_BOW_DEEP = 12

PARTS_DEF = [
    {"id": "body", "label": "体・手足"},
    {"id": "ears", "label": "耳"},
    {"id": "face", "label": "顔"},
    {"id": "ribbon", "label": "リボン"},
    {"id": "frill", "label": "襟フリル"},
]

P_BODY = 0
P_EARS = 1
P_FACE = 2
P_RIBBON = 3
P_FRILL = 4


def clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def extract_bunny_refs() -> tuple[Image.Image, Image.Image]:
    os.makedirs(BUNNY_DIR, exist_ok=True)
    sheet = Image.open(REF_SHEET_PATH).convert("RGB")

    def crop_largest_component(box: tuple[int, int, int, int]) -> Image.Image:
        sub = sheet.crop(box)
        w, h = sub.size
        px = sub.load()
        # 参照シートの周囲にある浮遊ハートや吹き出しを除外し、うさぎ本体のみを最大の非白連結成分として切り出す
        is_bg = [[False] * w for _ in range(h)]
        q: deque[tuple[int, int]] = deque()
        for x in range(w):
            for y in (0, h - 1):
                if min(px[x, y]) >= 238:
                    is_bg[y][x] = True
                    q.append((x, y))
        for y in range(h):
            for x in (0, w - 1):
                if min(px[x, y]) >= 238 and not is_bg[y][x]:
                    is_bg[y][x] = True
                    q.append((x, y))
        while q:
            cx, cy = q.popleft()
            for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                if 0 <= nx < w and 0 <= ny < h and not is_bg[ny][nx] and min(px[nx, ny]) >= 235:
                    is_bg[ny][nx] = True
                    q.append((nx, ny))

        visited = [[False] * w for _ in range(h)]
        best_comp: list[tuple[int, int]] = []
        for y in range(h):
            for x in range(w):
                if not is_bg[y][x] and not visited[y][x]:
                    comp: list[tuple[int, int]] = []
                    cq: deque[tuple[int, int]] = deque([(x, y)])
                    visited[y][x] = True
                    while cq:
                        ux, uy = cq.popleft()
                        comp.append((ux, uy))
                        for nx, ny in ((ux - 1, uy), (ux + 1, uy), (ux, uy - 1), (ux, uy + 1)):
                            if 0 <= nx < w and 0 <= ny < h and not is_bg[ny][nx] and not visited[ny][nx]:
                                visited[ny][nx] = True
                                cq.append((nx, ny))
                    if len(comp) > len(best_comp):
                        best_comp = comp

        rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rp = rgba.load()
        xs, ys = [], []
        for ux, uy in best_comp:
            r, g, b = px[ux, uy]
            rp[ux, uy] = (r, g, b, 255)
            xs.append(ux)
            ys.append(uy)
        cropped = rgba.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
        padded = Image.new("RGBA", (cropped.width + 6, cropped.height + 6), (0, 0, 0, 0))
        padded.paste(cropped, (3, 3))
        return padded

    ref_front = crop_largest_component((118, 816, 232, 962))
    ref_back = crop_largest_component((342, 658, 434, 792))
    ref_front.save(os.path.join(BUNNY_DIR, "ref_front.png"))
    ref_back.save(os.path.join(BUNNY_DIR, "ref_back.png"))
    print(f"Saved bunny ref_front.png ({ref_front.size}) and ref_back.png ({ref_back.size})")
    return ref_front, ref_back


def build_bunny_volume() -> tuple[list[list[list[int]]], list[list[list[int]]]]:
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    part_vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    cx0 = (W - 1) * 0.5
    cz0 = 17.5

    def set_vox(x: int, y: int, z: int, c: int, p: int) -> None:
        if 0 <= x < W and 0 <= y < H and 0 <= z < D:
            vol[x][y][z] = c
            part_vol[x][y][z] = p

    def set_sym(x_left: int, y: int, z: int, c: int, p: int) -> None:
        set_vox(x_left, y, z, c, p)
        set_vox(W - 1 - x_left, y, z, c, p)

    def fill_plush_color(nx: float, ny: float, nz: float, r_norm: float) -> int:
        if ny < -0.58 and r_norm >= 0.72:
            return C_CREASE
        if ny < -0.25 or nz < -0.45:
            return C_SH1
        if ny > 0.42 and nz > -0.15 and r_norm >= 0.60:
            return C_HI
        return C_BASE

    for x in range(W):
        dx = x - cx0
        for y in range(1, 20):
            t_y = (y - 1.0) / 18.0
            rx_b = 10.6 - 2.6 * (t_y ** 1.25) + 0.9 * math.sin(t_y * math.pi)
            rz_b = 9.0 - 2.0 * (t_y ** 1.2) + 0.7 * math.sin(t_y * math.pi)
            ny_b = (y - 9.5) / 9.5
            for z in range(D):
                dz = z - cz0
                nx = dx / rx_b
                nz = dz / rz_b
                r2 = nx * nx + nz * nz + (ny_b * ny_b) * 0.48
                if r2 <= 1.0:
                    r_n = math.sqrt(r2)
                    if y <= 2:
                        col = C_CREASE if r_n >= 0.65 else C_SH1
                    elif y >= 18:
                        col = C_CREASE
                    elif dz >= 3.5 and abs(dx) <= 3.0 and 5 <= y <= 14:
                        col = C_HI if r_n >= 0.62 else C_BASE
                    else:
                        col = fill_plush_color(nx, ny_b, nz, r_n)
                    set_vox(x, y, z, col, P_BODY)

    # お座りポーズの丸い両足を前(+Z)かつわずかに外向きへ張り出し、床接地(y=0)を安定させる
    for side in (-1.0, 1.0):
        fx0 = cx0 + side * 6.8
        fy0 = 4.2
        fz0 = cz0 + 6.5
        yaw_foot = side * 0.24
        cos_f, sin_f = math.cos(yaw_foot), math.sin(yaw_foot)
        for x in range(W):
            for y in range(0, 10):
                for z in range(D):
                    ux = x - fx0
                    uz = z - fz0
                    lx = ux * cos_f - uz * sin_f
                    lz = ux * sin_f + uz * cos_f
                    ny = (y - fy0) / 4.2
                    nx = lx / 4.2
                    nz = lz / 5.7
                    d_foot = (nx * nx) ** 1.15 + (nz * nz) ** 1.15 + (ny * ny) ** 1.25
                    if d_foot <= 1.0:
                        r_n = math.sqrt(d_foot)
                        if y == 0:
                            col = C_CREASE
                        elif lz < -3.2 and y <= 6 and r_n >= 0.72:
                            col = C_CREASE
                        elif lz >= 3.2 and abs(lx) <= 2.2 and 2 <= y <= 6:
                            col = C_HI
                        else:
                            col = fill_plush_color(nx, ny, nz, r_n)
                        set_vox(x, y, z, col, P_BODY)

    # 短い腕が上向きに跳ね上がって見えないよう、肩(y=15)から斜め下外側(y=10)へ丸く垂れる角度で造形する
    for side in (-1.0, 1.0):
        ax0 = cx0 + side * 11.2
        ay0 = 12.6
        az0 = cz0 + 1.8
        for x in range(W):
            for y in range(7, 18):
                for z in range(D):
                    dx_a = (x - ax0) * side
                    dy_a = y - ay0
                    dz_a = z - az0
                    lx = dx_a * 0.84 + dy_a * 0.54
                    ly = -dx_a * 0.54 + dy_a * 0.84
                    r2 = (lx / 3.2) ** 2 + (ly / 4.6) ** 2 + (dz_a / 3.1) ** 2
                    if r2 <= 1.0:
                        r_n = math.sqrt(r2)
                        if dx_a < -1.1 and r_n >= 0.70:
                            col = C_CREASE
                        elif dy_a < -1.5 and r_n >= 0.72:
                            col = C_SH1
                        elif dy_a > 1.2 and dz_a > 0.0:
                            col = C_HI
                        else:
                            col = C_BASE
                        set_vox(x, y, z, col, P_BODY)

    # 背面リボンの下に隠れず真横・背面双方でぽんぽん感が出るよう、しっぽ球を少し大きめに後方(-Z)へ張り出す
    ty0, tz0 = 5.0, cz0 - 9.9
    for x in range(W):
        for y in range(1, 11):
            for z in range(D):
                nx = (x - cx0) / 3.9
                ny = (y - ty0) / 3.8
                nz = (z - tz0) / 3.9
                r2 = nx * nx + ny * ny + nz * nz
                if r2 <= 1.0:
                    r_n = math.sqrt(r2)
                    if ny < -0.45 and r_n >= 0.70:
                        col = C_CREASE
                    elif nz > 0.58 and r_n >= 0.72:
                        col = C_CREASE
                    elif ny > 0.30 and r_n >= 0.52:
                        col = C_HI
                    else:
                        col = C_BASE
                    set_vox(x, y, z, col, P_BODY)

    # 真横から厚い白いチョーカー帯に見えないよう、首元の白レース襟は前後リボン下に小さく覗く1〜2層に留める
    for y in (17, 18):
        for x in range(W):
            for z in range(D):
                dx = x - cx0
                dz = z - cz0
                ang = math.atan2(dz, dx)
                scallop = 0.55 * math.cos(10.0 * ang)
                rx_c = (8.3 if y == 18 else 7.6) + scallop
                rz_c = (6.9 if y == 18 else 6.4) + scallop * 0.85
                rad = math.sqrt((dx / rx_c) ** 2 + (dz / rz_c) ** 2)
                if 0.78 <= rad <= 1.0:
                    set_vox(x, y, z, C_WHITE if (y == 18 and math.cos(10.0 * ang) > -0.1) else C_LACE_SH, P_FRILL)

    hy0 = 26.8
    for x in range(W):
        dx = x - cx0
        adx = abs(dx)
        for y in range(18, 37):
            dy = y - hy0
            cheek_swell = 1.75 * math.exp(-((y - 23.2) / 3.8) ** 2)
            rx_h = 11.4 + cheek_swell
            ry_h = 9.2
            rz_h = 9.8 + cheek_swell * 0.55
            for z in range(D):
                dz = z - cz0
                nx = dx / rx_h
                ny = dy / ry_h
                nz = dz / rz_h
                r2 = nx * nx + ny * ny + nz * nz
                if r2 <= 1.0:
                    r_n = math.sqrt(r2)
                    if y == 18 and r_n >= 0.68:
                        col = C_CREASE
                    elif y <= 20 and r_n >= 0.80:
                        col = C_SH1
                    elif 21 <= y <= 23 and 5.8 <= adx <= 8.8 and dz >= 5.5 and r_n >= 0.78:
                        col = C_CHEEK
                    else:
                        col = fill_plush_color(nx, ny, nz, r_n)
                    set_vox(x, y, z, col, P_BODY)

    # 細長くなりすぎないようふっくら丸い幅広楕円の立ちうさ耳とし、背面側にハイライト粒が滲まないよう表面方向で陰影を分ける
    for side in (-1.0, 1.0):
        ex_base = cx0 + side * 6.2
        ey_base = 34.0
        ez_base = cz0 - 0.3
        tilt = side * 0.28
        cos_e, sin_e = math.cos(tilt), math.sin(tilt)
        for x in range(W):
            for y in range(32, 51):
                for z in range(D):
                    ux = x - ex_base
                    uy = y - ey_base
                    uz = z - ez_base
                    lx = ux * cos_e - uy * sin_e
                    ly = ux * sin_e + uy * cos_e
                    if ly < -1.5 or ly > 16.5:
                        continue
                    t_ear = clamp(ly / 15.8, 0.0, 1.0)
                    r_ex = 4.0 + 1.45 * math.sin(t_ear * math.pi * 0.88)
                    r_ez = 3.0 + 0.70 * math.sin(t_ear * math.pi * 0.90)
                    tip_squash = (ly - 7.8) / 8.5
                    r_ear = (lx / r_ex) ** 2 + (uz / r_ez) ** 2 + (tip_squash ** 2) * 0.72
                    if r_ear <= 1.0:
                        r_n = math.sqrt(r_ear)
                        in_hollow = (uz > 0.8) and (abs(lx) <= r_ex * 0.45) and (2.5 <= ly <= 12.0) and (r_n >= 0.72)
                        if ly <= 1.0 and r_n >= 0.78:
                            col = C_CREASE
                        elif in_hollow:
                            col = C_SH1
                        elif uz < -0.6 and r_n >= 0.68:
                            col = C_SH1
                        elif ly >= 10.0 and uz >= 0.8 and r_n >= 0.55:
                            col = C_HI
                        else:
                            col = C_BASE
                        set_vox(x, y, z, col, P_EARS)

    # 斜め俯瞰(Quarter 32°/35°)でも顎下に隠れず、かつ斜め視点で割れないよう目口をy=23..26へ配置し奥行2〜3層まで連続充填する
    def paint_face_stitch(px_x: int, px_y: int, col: int, sym: bool = True) -> None:
        z_surf = -1
        for z in range(D - 1, int(cz0), -1):
            if vol[px_x][px_y][z] != -1:
                z_surf = z
                break
        if z_surf == -1:
            return
        for z_off in (0, 1, 2):
            if sym:
                set_sym(px_x, px_y, z_surf - z_off, col, P_FACE)
            else:
                set_vox(px_x, px_y, z_surf - z_off, col, P_FACE)

    eye_cx, eye_cy = 19, 25
    for ox, oy in ((-1, -1), (1, -1), (0, 0), (-1, 1), (1, 1)):
        paint_face_stitch(eye_cx + ox, eye_cy + oy, C_WHITE if (ox == 0 and oy == 0) else C_STITCH, sym=True)

    paint_face_stitch(25, 24, C_WHITE, sym=True)
    paint_face_stitch(24, 23, C_STITCH, sym=True)

    def sculpt_butterfly_bow(z_sign: float, y_center: float, wing_span: float, wing_h: float, tail_len: int) -> None:
        z_anchor = -1
        for step in range(D):
            zc = (D - 1 - step) if z_sign > 0 else step
            if vol[int(cx0)][int(round(y_center))][zc] != -1:
                z_anchor = zc
                break
        if z_anchor == -1:
            return

        for y in range(int(y_center - wing_h - 1), int(y_center + wing_h + 2)):
            dy = y - y_center
            for x in range(W):
                dx = x - cx0
                adx = abs(dx)
                if adx < 1.1 or adx > wing_span + 0.5:
                    continue
                t_w = (adx - 1.1) / (wing_span - 1.1)
                h_local = 1.05 + (wing_h - 0.85) * math.sin(clamp(t_w * 0.92 + 0.08, 0.0, 1.0) * math.pi * 0.72)
                if abs(dy) <= h_local:
                    curve_back = 1.4 * (t_w ** 1.6)
                    z_surf_bow = z_anchor + z_sign * (2.6 - curve_back)
                    thick = 2.1 if (0.20 <= t_w <= 0.82 and abs(dy) <= h_local * 0.75) else 1.5
                    for dz_i in range(-2, 4):
                        z = int(round(z_surf_bow - z_sign * dz_i))
                        if not (0 <= z < D):
                            continue
                        dist_z = abs((z - z_surf_bow) * z_sign)
                        if dist_z <= thick:
                            is_inner_fold = (t_w <= 0.28 and abs(dy) <= 0.8) or (abs(dy) >= h_local - 0.55 and dy < 0)
                            is_outer_rim = (abs(dy) >= h_local - 0.45) or (t_w >= 0.88)
                            if is_inner_fold:
                                col = C_BOW_KNOT
                            elif is_outer_rim and dist_z >= 0.8:
                                col = C_BOW_SH
                            elif dy >= 0.25 and dist_z <= 0.9:
                                col = C_BOW_HI
                            else:
                                col = C_BOW_MID
                            set_vox(x, y, z, col, P_RIBBON)

        for y in range(int(y_center - 1), int(y_center + 2)):
            for x in range(int(cx0 - 1), int(cx0 + 3)):
                dx = abs(x - cx0)
                dy = abs(y - y_center)
                if dx <= 1.25 and dy <= 1.25:
                    for off in (0, 1, 2):
                        z = int(round(z_anchor + z_sign * (2.8 - off)))
                        if dx <= 0.6 and dy <= 0.6 and off == 0:
                            col = C_WHITE
                        elif dy >= 0.9 or off == 2:
                            col = C_BOW_DEEP
                        else:
                            col = C_BOW_KNOT
                        set_vox(x, y, z, col, P_RIBBON)

        for step_y in range(1, tail_len + 1):
            ty = int(round(y_center - 1.2 - step_y))
            t_t = step_y / float(tail_len)
            tx_center = 1.4 + 2.9 * t_t
            half_w = 1.25 + 0.35 * t_t
            for side in (-1.0, 1.0):
                for x in range(W):
                    local_x = (x - cx0) * side - tx_center
                    if abs(local_x) <= half_w:
                        if step_y == tail_len and abs(local_x) <= 0.45:
                            continue
                        z_t = int(round(z_anchor + z_sign * (2.1 - 0.4 * t_t)))
                        for off in (0, 1):
                            z = int(round(z_t - z_sign * off))
                            col = C_BOW_SH if (off == 1 or step_y == tail_len) else (C_BOW_HI if local_x * side <= 0.2 else C_BOW_MID)
                            set_vox(x, ty, z, col, P_RIBBON)

    sculpt_butterfly_bow(z_sign=+1.0, y_center=15.4, wing_span=7.4, wing_h=2.7, tail_len=5)
    # 背面リボンは丸しっぽ上端と被らない高さ(y=15.6)へ上げて両方くっきり見せる
    sculpt_butterfly_bow(z_sign=-1.0, y_center=15.6, wing_span=8.8, wing_h=3.1, tail_len=5)

    return vol, part_vol


def export_bunny(
    vol: list[list[list[int]]],
    part_vol: list[list[list[int]]],
) -> dict:
    os.makedirs(BUNNY_DIR, exist_ok=True)
    palette_rgb = [hex_to_rgb(c) for c in PALETTE_HEX]

    voxels: list[list[int]] = []
    part_color_counts: list[dict[int, int]] = [{} for _ in PARTS_DEF]
    im_y = Image.new("RGBA", (H * W, D), (0, 0, 0, 0))
    im_z = Image.new("RGBA", (D * W, H), (0, 0, 0, 0))
    im_x = Image.new("RGBA", (W * D, H), (0, 0, 0, 0))
    py_y, py_z, py_x = im_y.load(), im_z.load(), im_x.load()

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

    im_y.save(os.path.join(BUNNY_DIR, "slices_y.png"))
    im_z.save(os.path.join(BUNNY_DIR, "slices_z.png"))
    im_x.save(os.path.join(BUNNY_DIR, "slices_x.png"))

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
        "name": "うさぎのぬいぐるみ",
        "size": {"x": W, "y": H, "z": D},
        "palette": PALETTE_HEX,
        "parts": parts,
        "voxels": voxels,
        "slices": {
            "y": {"file": "slices_y.png", "count": H, "sliceWidth": W, "sliceHeight": D},
            "z": {"file": "slices_z.png", "count": D, "sliceWidth": W, "sliceHeight": H},
            "x": {"file": "slices_x.png", "count": W, "sliceWidth": D, "sliceHeight": H},
        },
        "referenceViews": {"front": "ref_front.png", "back": "ref_back.png"},
    }
    with open(os.path.join(BUNNY_DIR, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model_data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Exported bunny model.json & 3 slice strips: {W}x{H}x{D}, solid voxels={len(voxels)}, parts={len(parts)}")
    return model_data


def render_bunny_diagnostic(model: dict, ref_front: Image.Image, ref_back: Image.Image) -> None:
    palette = [hex_to_rgb(c) for c in model["palette"]]
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    for vox in model["voxels"]:
        vx, vy, vz, pi = vox[:4]
        vol[vx][vy][vz] = pi

    cw, ch = 64, 64

    def fit_ref(im: Image.Image) -> Image.Image:
        ratio = min((cw - 6) / im.width, (ch - 6) / im.height)
        nw = max(1, int(round(im.width * ratio)))
        nh = max(1, int(round(im.height * ratio)))
        res = im.resize((nw, nh), Image.LANCZOS)
        c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        c.paste(res, ((cw - nw) // 2, (ch - nh) // 2), res)
        return c

    panels = [
        ("REF FRONT (Sheet)", fit_ref(ref_front)),
        ("3D FRONT (Flat 0%)", render_ortho_dda(vol, palette, W, H, D, 0.0, 0.0, 0.0, cw, ch)),
        ("REF BACK (Sheet)", fit_ref(ref_back)),
        ("3D BACK 180 deg (Flat)", render_ortho_dda(vol, palette, W, H, D, 180.0, 0.0, 0.0, cw, ch)),
        ("3D SIDE +90 deg (Left)", render_ortho_dda(vol, palette, W, H, D, 90.0, 0.0, 0.0, cw, ch)),
        ("QUARTER 32/35 (Flat)", render_ortho_dda(vol, palette, W, H, D, 32.0, 35.0, 0.0, cw, ch)),
        ("QUARTER -32/20 (Shaded)", render_ortho_dda(vol, palette, W, H, D, -32.0, 20.0, 0.50, cw, ch)),
        ("BACK-QTR 145/22", render_ortho_dda(vol, palette, W, H, D, 145.0, 22.0, 0.45, cw, ch)),
        ("TOP 90 deg (+Y)", render_ortho_dda(vol, palette, W, H, D, 0.0, 89.9, 0.35, cw, ch)),
        ("LOW -22 deg (Look-Up)", render_ortho_dda(vol, palette, W, H, D, 20.0, -22.0, 0.45, cw, ch)),
    ]

    scale = 4
    pw, ph = cw * scale, ch * scale
    header_h, pad = 28, 16
    cols, rows = 5, 2
    sheet = Image.new("RGB", (pad + cols * (pw + pad), 46 + rows * (ph + header_h + pad)), (34, 37, 46))
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (pad, 14),
        f"PLUSH BUNNY - 3D Voxel & Tri-Axis Slice Diagnostic ({W}x{H}x{D}, {len(model['voxels'])} voxels)",
        fill=(235, 238, 246),
    )

    for idx, (label, panel_im) in enumerate(panels):
        r, c = idx // cols, idx % cols
        x0 = pad + c * (pw + pad)
        y0 = 46 + r * (ph + header_h + pad)
        # 暗いモーヴ色のぬいぐるみ輪郭が見やすいよう明色チェッカー盤の上に描画する
        card = Image.new("RGB", (pw, ph), (226, 224, 232))
        cp = card.load()
        for yy in range(ph):
            for xx in range(pw):
                if ((xx // 16) + (yy // 16)) % 2 == 1:
                    cp[xx, yy] = (214, 212, 222)
        up = panel_im.resize((pw, ph), Image.NEAREST)
        card.paste(up, (0, 0), up)
        sheet.paste(card, (x0, y0 + header_h))
        draw.rectangle([x0 - 1, y0 + header_h - 1, x0 + pw, y0 + header_h + ph], outline=(92, 98, 116))
        draw.text((x0 + 4, y0 + 7), label, fill=(210, 216, 230))

    os.makedirs(os.path.dirname(CHECK_OUT), exist_ok=True)
    sheet.save(CHECK_OUT)
    print(f"[OK] Saved bunny diagnostic sheet -> {CHECK_OUT}")


def main() -> None:
    ref_front, ref_back = extract_bunny_refs()
    vol, part_vol = build_bunny_volume()
    model = export_bunny(vol, part_vol)
    verify_contract(model, BUNNY_DIR)
    if "--no-render" not in sys.argv:
        render_bunny_diagnostic(model, ref_front, ref_back)


if __name__ == "__main__":
    main()
