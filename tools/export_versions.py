import json
import math
import os
import subprocess
from PIL import Image
from build_model import ASSETS_DIR, PROJECT_ROOT, catmull_rom_interp, clamp, hex_to_rgb, smoothstep
from render_check import verify_contract

VERSIONS_DIR = os.path.join(ASSETS_DIR, "versions")

# Round 1初期版はQA不合格のためGit未コミットだったが、比較用に初期プロトタイプ(52x52x36)の造形を再現してv1スナップショットを生成する
V1_PALETTE_HEX = [
    "#FCFDFE",
    "#F2F4FA",
    "#E1E4F0",
    "#C9CEE0",
    "#AAB0C2",
    "#898393",
    "#F9F4EA",
    "#EFE7DA",
    "#E2D8C9",
    "#CFC1B2",
    "#B2A297",
    "#867977",
    "#FDF8F3",
    "#EEE1D7",
    "#F1D9D7",
    "#DFBFC0",
    "#E5E2F1",
    "#B6AFD2",
    "#8B83A7",
    "#595264",
    "#686066",
]


def build_v1_snapshot(out_dir: str) -> None:
    W, H, D = 52, 52, 36
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    cx0 = (W - 1) * 0.5
    cz_body = 22.0
    cz_head = 22.3

    def set_vox(x: int, y: int, z: int, c: int) -> None:
        if 0 <= x < W and 0 <= y < H and 0 <= z < D:
            vol[x][y][z] = c

    def set_sym(x_left: int, y: int, z: int, c: int) -> None:
        set_vox(x_left, y, z, c)
        set_vox(W - 1 - x_left, y, z, c)

    for y in range(0, 14):
        for side in (-1.0, 1.0):
            lx = cx0 + side * 2.45
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
                                col = 20
                            elif y == 1:
                                col = 5 if d_s > 0.55 else 4
                            elif y == 2:
                                col = 3 if (z >= cz_shoe + 0.2 and abs(x - lx) <= 0.9) else 4
                            else:
                                col = 5 if z >= cz_shoe + 0.6 else 12
                            set_vox(x, y, z, col)
            else:
                for x in range(W):
                    if abs(x - cx0) < 0.95:
                        continue
                    for z in range(D):
                        if ((x - lx) / 1.52) ** 2 + ((z - cz_body) / 1.75) ** 2 <= 1.0:
                            col = 13 if y >= 10 else (12 if (z >= cz_body + 0.20 and abs(x - lx) <= 0.90) else 13)
                            set_vox(x, y, z, col)

    for y in range(10, 28):
        t = (y - 10) / 17.0
        flare = (1.0 - t) ** 1.12
        hem_round = -0.75 * max(0.0, (11.6 - y) / 1.6) ** 1.6 if y < 11.6 else 0.55 * math.exp(-((y - 12.6) / 2.2) ** 2)
        rx_skirt = 3.5 + 8.1 * flare + hem_round
        rz_skirt = 3.0 + 5.9 * flare + hem_round * 0.8
        for x in range(W):
            for z in range(D):
                dx = x - cx0
                dz = z - cz_body
                ang = math.atan2(dz, dx)
                pleat_amp = 0.52 * smoothstep(22.0, 11.5, float(y))
                wave = math.cos(8.0 * ang)
                rx_eff = rx_skirt + pleat_amp * wave
                rz_eff = rz_skirt + pleat_amp * 0.85 * wave
                y_hem_local = 10.0 + 0.95 * ((abs(dx) / 11.5) ** 2) - 0.25 * wave
                if y < y_hem_local:
                    continue
                rad = math.sqrt((dx / rx_eff) ** 2 + (dz / rz_eff) ** 2)
                if rad <= 1.0:
                    if y <= 13:
                        inner_hollow = 0.72 - 0.12 * (y - 10)
                        if rad < inner_hollow:
                            if vol[x][y][z] == -1 and y == 13:
                                set_vox(x, y, z, 4)
                            continue
                    is_bottom_edge = (y - y_hem_local) < 1.05
                    if is_bottom_edge and rad >= 0.80:
                        col = 20
                    elif is_bottom_edge:
                        col = 4
                    elif y == 27:
                        col = 0 if (rad >= 0.58 and int(round(abs(dx))) % 2 == 0) else 3
                    elif y == 26 and rad >= 0.75 and abs(dx) <= 2.6 and dz > 0:
                        col = 3
                    elif rad >= 0.82:
                        if wave < -0.35 and y <= 23:
                            col = 3 if y <= 16 else 2
                        elif wave > 0.42 and dz >= -2.5:
                            col = 0
                        elif dz < -1.5 and abs(dx) >= 1.2 and int(round(abs(dx))) in (2, 5):
                            col = 3 if y <= 16 else 2
                        else:
                            col = 1
                    else:
                        col = 2
                    set_vox(x, y, z, col)

    for y in range(14, 27):
        ta = (26.0 - y) / 12.0
        arm_x_off = 3.6 + 6.9 * (ta ** 1.04)
        arm_z = cz_body + 0.30 * math.sin(ta * math.pi)
        cuff_swell = smoothstep(0.55, 0.90, ta) * (1.0 - 0.32 * smoothstep(0.90, 1.0, ta))
        r_arm_x = 1.60 + 0.85 * cuff_swell
        r_arm_z = 1.80 + 0.95 * cuff_swell
        for side in (-1.0, 1.0):
            ax = cx0 + side * arm_x_off
            for x in range(W):
                for z in range(D):
                    nx = (x - ax) / r_arm_x
                    nz = (z - arm_z) / r_arm_z
                    r2 = nx * nx + nz * nz
                    if r2 <= 1.0:
                        is_inner_seam = (side < 0 and x >= ax + r_arm_x * 0.32) or (side > 0 and x <= ax - r_arm_x * 0.32)
                        is_profile_edge = abs(z - arm_z) >= r_arm_z * 0.68 and r2 >= 0.62 and y <= 24
                        if y == 14:
                            col = 12 if r2 <= 0.38 else 5
                        elif y == 15 and r2 >= 0.70:
                            col = 5 if abs(z - arm_z) >= r_arm_z * 0.5 else 3
                        elif is_inner_seam and y <= 25 and r2 >= 0.48:
                            col = 5 if y >= 17 else 3
                        elif is_profile_edge:
                            col = 5 if (16 <= y <= 22) else 3
                        elif z >= arm_z + 0.25 and r2 >= 0.42:
                            col = 0
                        else:
                            col = 1
                        set_vox(x, y, z, col)

    for x in range(W):
        for z in range(D):
            if ((x - cx0) / 2.55) ** 2 + ((z - cz_body) / 2.35) ** 2 <= 1.0:
                set_vox(x, 28, z, 20)

    rx_profile = [(29.0, 6.2), (30.0, 8.9), (31.5, 11.3), (33.5, 12.7), (36.5, 13.1), (40.5, 13.0), (44.5, 12.4), (48.0, 10.9), (50.0, 8.9), (51.0, 6.4)]
    rz_front_profile = [(29.0, 5.4), (30.5, 7.4), (33.0, 8.6), (36.0, 8.8), (40.0, 8.9), (44.5, 8.6), (48.5, 7.3), (50.0, 5.7), (51.0, 4.0)]
    rz_back_profile = [(29.0, 5.6), (31.0, 8.0), (35.0, 9.6), (40.0, 10.1), (45.0, 9.5), (48.5, 7.9), (50.0, 5.9), (51.0, 4.1)]

    for y in range(29, 52):
        rx_h = catmull_rom_interp(rx_profile, float(y))
        rz_f = catmull_rom_interp(rz_front_profile, float(y))
        rz_b = catmull_rom_interp(rz_back_profile, float(y))
        for x in range(W):
            dx = x - cx0
            adx = abs(dx)
            for z in range(D):
                dz = z - cz_head
                r_ell = math.sqrt((dx / rx_h) ** 2 + (dz / (rz_f if dz >= 0.0 else rz_b)) ** 2)
                if r_ell <= 1.0:
                    is_face_zone = (dz > 1.2) and (y <= 37) and (adx <= 9.9 - 0.18 * max(0.0, 33.0 - y))
                    if is_face_zone:
                        if y <= 30 and r_ell >= 0.76:
                            col = 13
                        elif 32 <= y <= 34 and 6.8 <= adx <= 9.4 and r_ell >= 0.75:
                            col = 15 if (y == 32 and adx >= 8.0) else 14
                        elif r_ell >= 0.86 and adx >= 8.3:
                            col = 13
                        else:
                            col = 12
                    else:
                        if y >= 47:
                            col = 8 if (y == 51 and r_ell <= 0.25) else 6
                        elif y >= 40:
                            col = 7 if dz < 2.0 else 6
                        elif y >= 33:
                            col = 8 if dz < -1.0 else 7
                        else:
                            col = 11 if (y == 29 and r_ell >= 0.84 and dz < 0.5) else 9
                        if dz < -3.5 and r_ell >= 0.84 and 31 <= y <= 45:
                            curve_target = 2.2 + 3.6 * (((y - 31.0) / 14.0) ** 0.8)
                            if abs(adx - curve_target) < 0.55 or (y <= 37 and adx < 0.65):
                                col = 9 if y >= 35 else 10
                    set_vox(x, y, z, col)

    for y in range(37, 50):
        rx_h = catmull_rom_interp(rx_profile, float(y)) + 0.50
        rz_f = catmull_rom_interp(rz_front_profile, float(y))
        bang_extra_z = 0.90 if y == 37 else 1.75 * math.sin(clamp((y - 35.5) / 14.0, 0.0, 1.0) * math.pi * 0.85)
        for x in range(W):
            adx = abs(x - cx0)
            if adx > 11.2 or (y == 37 and abs(adx - 3.8) < 0.45):
                continue
            for z in range(int(cz_head + 1), D):
                r_b = math.sqrt(((x - cx0) / rx_h) ** 2 + ((z - cz_head) / (rz_f + bang_extra_z)) ** 2)
                if 0.74 <= r_b <= 1.0:
                    if y >= 46:
                        col = 6
                    elif y == 37 and r_b >= 0.86:
                        col = 9 if int(round(adx)) in (1, 6, 9) else 8
                    elif r_b >= 0.85 and (abs(adx - 1.5) < 0.5 or abs(adx - 5.8) < 0.5) and 38 <= y <= 44:
                        col = 8 if y >= 41 else 10
                    else:
                        col = 7 if y <= 43 else 6
                    set_vox(x, y, z, col)

    for y in range(32, 45):
        for side in (-1.0, 1.0):
            for x in range(W):
                dx_s = (x - cx0) * side
                if not (9.2 <= dx_s <= 13.8):
                    continue
                for z in range(int(cz_head - 1), int(cz_head + 8)):
                    dz = z - cz_head
                    if y <= 36 and dz > 3.8:
                        continue
                    r_l = math.sqrt((dx_s / (13.55 if y >= 34 else 13.25)) ** 2 + (dz / 9.10) ** 2)
                    if 0.80 <= r_l <= 1.02 and dz >= -0.4 + 0.25 * max(0.0, 36.0 - y):
                        if y == 32:
                            col = 20
                        elif y == 33:
                            col = 9
                        elif (dz <= 1.4 or (y <= 36 and dz >= 3.0)) and r_l >= 0.88:
                            col = 10
                        elif y >= 41:
                            col = 7
                        else:
                            col = 8 if dx_s >= 12.2 else 7
                        set_vox(x, y, z, col)

    for eye_y in range(33, 37):
        for lx in range(16, 22):
            local_u = lx - 16
            z_surf = -1
            for z in range(D - 1, int(cz_head), -1):
                if vol[lx][eye_y][z] != -1:
                    z_surf = z
                    break
            if z_surf == -1:
                continue
            if local_u == 0:
                for z_off in (0, 1):
                    c_side = 19 if eye_y == 36 else ((18 if z_off == 0 else 17) if eye_y == 35 else ((17 if z_off == 0 else 0) if eye_y == 34 else 16))
                    set_sym(lx, eye_y, z_surf - z_off, c_side)
                continue
            col = 19 if eye_y == 36 else (18 if eye_y == 35 else ((0 if local_u == 1 else (16 if local_u == 5 else 17)) if eye_y == 34 else (16 if 2 <= local_u <= 4 else 12)))
            set_sym(lx, eye_y, z_surf, col)

    z_knot = 20.5
    for y in range(44, 50):
        dy = y - 46
        for z in range(16, 26):
            adz = abs(int(round(z - z_knot)))
            if adz == 0 and -1 <= dy <= 1:
                for lx in (10, 11, 12, 13):
                    set_sym(lx, y, z, 11 if abs(dy) == 1 else 5)
            elif 1 <= adz <= 4:
                y_max_w = 2 if adz >= 2 else 1
                if -1 <= dy <= y_max_w:
                    is_z_tip = adz == 4
                    is_y_border = (dy == -1) or (dy == y_max_w)
                    x_outer = 9 if (2 <= adz <= 3 and 0 <= dy <= 1) else 10
                    for lx in range(x_outer, 14):
                        if lx == 9 or (is_z_tip and lx == 10 and 0 <= dy <= 1):
                            col = 0
                        elif is_z_tip or is_y_border:
                            col = 11 if lx <= 11 else 5
                        else:
                            col = 0 if dy >= 0 else 2
                        set_sym(lx, y, z, col)
    for tz_s in (-2, 2):
        set_sym(10, 43, int(z_knot) + tz_s, 11)
        set_sym(11, 43, int(z_knot) + tz_s, 0)

    tail_x_pts = [(8.0, 7.2), (11.0, 6.2), (16.0, 5.2), (23.0, 4.6), (30.0, 4.9), (37.0, 6.2), (42.5, 8.3), (46.0, 10.6)]
    tail_z_pts = [(8.0, 5.6), (11.0, 7.2), (15.0, 6.4), (21.0, 9.2), (28.0, 7.2), (35.0, 10.8), (41.5, 16.0), (46.0, 19.8)]
    tail_r_pts = [(8.0, 1.05), (10.0, 1.65), (13.5, 3.15), (20.0, 3.65), (28.0, 3.75), (36.0, 3.60), (42.5, 3.10), (46.0, 2.35)]
    for y in range(8, 47):
        fy = float(y)
        phase = (46.0 - fy) / 8.6 * (2.0 * math.pi)
        r_eff = catmull_rom_interp(tail_r_pts, fy) * (1.0 + 0.15 * math.sin(phase) if y >= 12 else 1.0)
        tx = catmull_rom_interp(tail_x_pts, fy) + (0.38 * math.cos(phase) if y >= 12 else 0.0)
        tz = catmull_rom_interp(tail_z_pts, fy) + (0.36 * math.sin(phase) if y >= 12 else 0.0)
        for x in range(0, 17):
            for z in range(0, 26):
                dist = math.sqrt((x - tx) ** 2 + (z - tz) ** 2)
                if dist <= r_eff:
                    ang = math.atan2(z - tz, x - tx)
                    groove_delta = math.atan2(math.sin(ang - phase * 0.5), math.cos(ang - phase * 0.5))
                    on_surface = dist >= r_eff - 1.05
                    if y <= 9:
                        col = 11 if y == 8 else 9
                    elif on_surface and abs(groove_delta) <= 0.34 and y >= 11:
                        col = 11 if abs(groove_delta) <= 0.17 else 10
                    elif on_surface and math.sin(phase) < -0.70:
                        col = 9
                    elif on_surface and math.sin(phase) > 0.22 and (z - tz) >= -0.8:
                        col = 6
                    elif (z - tz) < -1.0 and on_surface:
                        col = 8
                    else:
                        col = 7
                    set_sym(x, y, z, col)

    os.makedirs(out_dir, exist_ok=True)
    palette_rgb = [hex_to_rgb(c) for c in V1_PALETTE_HEX]
    voxels = []
    im_y = Image.new("RGBA", (H * W, D), (0, 0, 0, 0))
    im_z = Image.new("RGBA", (D * W, H), (0, 0, 0, 0))
    im_x = Image.new("RGBA", (W * D, H), (0, 0, 0, 0))
    py_y, py_z, py_x = im_y.load(), im_z.load(), im_x.load()

    for y in range(H):
        inv_y = H - 1 - y
        for z in range(D):
            for x in range(W):
                pi = vol[x][y][z]
                if pi >= 0:
                    voxels.append([x, y, z, pi])
                    rgba = (*palette_rgb[pi], 255)
                    py_y[y * W + x, z] = rgba
                    py_z[z * W + x, inv_y] = rgba
                    py_x[x * D + z, inv_y] = rgba

    im_y.save(os.path.join(out_dir, "slices_y.png"))
    im_z.save(os.path.join(out_dir, "slices_z.png"))
    im_x.save(os.path.join(out_dir, "slices_x.png"))

    model_data = {
        "name": "Character 2 (v1)",
        "size": {"x": W, "y": H, "z": D},
        "palette": V1_PALETTE_HEX,
        "voxels": voxels,
        "slices": {
            "y": {"file": "slices_y.png", "count": H, "sliceWidth": W, "sliceHeight": D},
            "z": {"file": "slices_z.png", "count": D, "sliceWidth": W, "sliceHeight": H},
            "x": {"file": "slices_x.png", "count": W, "sliceWidth": D, "sliceHeight": H},
        },
        "referenceViews": {"front": "../../ref_front.png", "side": "../../ref_side.png"},
    }
    with open(os.path.join(out_dir, "model.json"), "w", encoding="utf-8") as f:
        json.dump(model_data, f, separators=(",", ":"))
    print(f"[OK] Built v1 snapshot -> {out_dir} ({len(voxels)} voxels)")


def extract_git_snapshot(commit_sha: str, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    files = ("model.json", "slices_y.png", "slices_z.png", "slices_x.png")
    for fname in files:
        blob = subprocess.check_output(
            ["git", "-C", PROJECT_ROOT, "show", f"{commit_sha}:public/assets/{fname}"]
        )
        # 過去スナップショットからも比較用参照PNGを解決できるよう相対パスを補正して書き出す
        if fname == "model.json":
            data = json.loads(blob.decode("utf-8"))
            data["referenceViews"] = {"front": "../../ref_front.png", "side": "../../ref_side.png"}
            with open(os.path.join(out_dir, fname), "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
        else:
            with open(os.path.join(out_dir, fname), "wb") as f:
                f.write(blob)
    print(f"[OK] Extracted git {commit_sha} -> {out_dir}")


def export_all_versions() -> None:
    os.makedirs(VERSIONS_DIR, exist_ok=True)
    v1_dir = os.path.join(VERSIONS_DIR, "v1")
    v2_dir = os.path.join(VERSIONS_DIR, "v2")
    v3_dir = os.path.join(VERSIONS_DIR, "v3")

    build_v1_snapshot(v1_dir)
    extract_git_snapshot("ac077d2", v2_dir)
    extract_git_snapshot("c27b1e9", v3_dir)

    char2_versions = [
        {
            "id": "v1",
            "label": "v1: 初期版",
            "shortLabel": "v1",
            "description": "初期プロトタイプ（後方カーブのツインテール・枠付きリボン）",
            "basePath": "assets/versions/v1",
            "model": "assets/versions/v1/model.json",
        },
        {
            "id": "v2",
            "label": "v2: 造形改善",
            "shortLabel": "v2",
            "description": "ツインテール垂直軌道化・純白蝶リボン・丸頬バランス調整",
            "basePath": "assets/versions/v2",
            "model": "assets/versions/v2/model.json",
        },
        {
            "id": "v3",
            "label": "v3: 腕・線画強化",
            "shortLabel": "v3",
            "description": "独立ベルスリーブ腕・内部主線強調・斜め視点の目割れ防止",
            "basePath": "assets/versions/v3",
            "model": "assets/versions/v3/model.json",
        },
        {
            "id": "v4",
            "label": "v4: 最新(縦ロール)",
            "shortLabel": "v4 最新",
            "description": "3D立体螺旋の縦ロール造形・自然な髪色陰影（最新確定版）",
            "basePath": "assets",
            "model": "assets/model.json",
        },
    ]

    # 既存のv1〜v4単一キャラ読込との後方互換を保ちつつ、複数キャラ切替用のcharacters配列を併記する
    manifest = {
        "defaultCharacter": "char2",
        "defaultVersion": "v4",
        "versions": char2_versions,
        "characters": [
            {
                "id": "char2",
                "name": "CHARACTER 2",
                "shortLabel": "CHARACTER 2",
                "defaultVersion": "v4",
                "versions": char2_versions,
            },
            {
                "id": "bunny",
                "name": "うさぎのぬいぐるみ",
                "shortLabel": "うさぎ",
                "defaultVersion": "bunny_v1",
                "versions": [
                    {
                        "id": "bunny_v1",
                        "label": "v1: お座りぬいぐるみ",
                        "shortLabel": "v1",
                        "description": "くすみモーヴのうさぎぬいぐるみ（白い×目・前後リボン・丸しっぽ）",
                        "basePath": "./assets/bunny/",
                        "model": "./assets/bunny/model.json",
                    }
                ],
            },
        ],
    }

    manifest_path = os.path.join(VERSIONS_DIR, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[OK] Wrote {manifest_path}")

    for vid, vdir in (("v1", v1_dir), ("v2", v2_dir), ("v3", v3_dir), ("v4", ASSETS_DIR)):
        with open(os.path.join(vdir, "model.json"), "r", encoding="utf-8") as f:
            m = json.load(f)
        verify_contract(m, vdir)
        print(f"    -> verified {vid}: {len(m['voxels'])} voxels")


if __name__ == "__main__":
    export_all_versions()
