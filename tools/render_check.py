import json
import math
import os
import sys
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets")
DEFAULT_OUT = os.environ.get(
    "SCULPT_CHECK_OUT",
    os.path.join(PROJECT_ROOT, "tmp", "sculpt_check.png"),
)


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def verify_contract(model: dict, assets_dir: str) -> None:
    W = model["size"]["x"]
    H = model["size"]["y"]
    D = model["size"]["z"]
    palette = [hex_to_rgb(c) for c in model["palette"]]

    parts = model.get("parts")
    has_parts = parts is not None
    if has_parts:
        assert isinstance(parts, list) and len(parts) > 0, "parts must be a non-empty list"
        part_color_counts: list[dict[int, int]] = [{} for _ in parts]

    grid: dict[tuple[int, int, int], tuple[int, int, int]] = {}
    for vox in model["voxels"]:
        if has_parts:
            assert len(vox) == 5, f"Expected 5-tuple voxel with partIdx, got {vox}"
            vx, vy, vz, pi, part_i = vox
            assert 0 <= part_i < len(parts), f"Invalid partIdx {part_i}"
            part_color_counts[part_i][pi] = part_color_counts[part_i].get(pi, 0) + 1
        else:
            assert len(vox) in (4, 5), f"Unexpected voxel tuple length: {vox}"
            vx, vy, vz, pi = vox[:4]
        assert 0 <= vx < W and 0 <= vy < H and 0 <= vz < D, f"Out of bounds voxel {(vx, vy, vz)}"
        assert 0 <= pi < len(palette), f"Invalid palette index {pi}"
        assert (vx, vy, vz) not in grid, f"Duplicate voxel {(vx, vy, vz)}"
        grid[(vx, vy, vz)] = palette[pi]

    if has_parts:
        for idx, pdef in enumerate(parts):
            assert isinstance(pdef.get("id"), str) and pdef["id"], f"Missing part id at {idx}"
            assert isinstance(pdef.get("label"), str) and pdef["label"], f"Missing part label at {idx}"
            expected_ci = [
                ci
                for ci, _cnt in sorted(
                    part_color_counts[idx].items(),
                    key=lambda kv: (-kv[1], kv[0]),
                )
            ]
            assert len(expected_ci) > 0, f"Part {pdef['id']} has 0 voxels"
            assert pdef.get("colorIndices") == expected_ci, (
                f"Part {pdef['id']} colorIndices mismatch: {pdef.get('colorIndices')} vs {expected_ci}"
            )

    # 3軸スライスPNGとボクセル座標の対応が1pxでも狂うと軸切替時に反転やジャンプが起きるため全画素を厳密照合する
    sy_meta = model["slices"]["y"]
    assert (sy_meta["count"], sy_meta["sliceWidth"], sy_meta["sliceHeight"]) == (H, W, D)
    im_y = Image.open(os.path.join(assets_dir, sy_meta["file"])).convert("RGBA")
    assert im_y.size == (H * W, D), f"slices_y size mismatch: {im_y.size}"
    py_px = im_y.load()
    for y in range(H):
        x_off = y * W
        for z in range(D):
            for x in range(W):
                rgba = py_px[x_off + x, z]
                exp = grid.get((x, y, z))
                if exp is None:
                    assert rgba[3] == 0, f"slices_y unexpected solid at {(x,y,z)}"
                else:
                    assert rgba == (*exp, 255), f"slices_y mismatch at {(x,y,z)}: {rgba} vs {exp}"

    sz_meta = model["slices"]["z"]
    assert (sz_meta["count"], sz_meta["sliceWidth"], sz_meta["sliceHeight"]) == (D, W, H)
    im_z = Image.open(os.path.join(assets_dir, sz_meta["file"])).convert("RGBA")
    assert im_z.size == (D * W, H), f"slices_z size mismatch: {im_z.size}"
    pz_px = im_z.load()
    for z in range(D):
        x_off = z * W
        for y in range(H):
            py = H - 1 - y
            for x in range(W):
                rgba = pz_px[x_off + x, py]
                exp = grid.get((x, y, z))
                if exp is None:
                    assert rgba[3] == 0, f"slices_z unexpected solid at {(x,y,z)}"
                else:
                    assert rgba == (*exp, 255), f"slices_z mismatch at {(x,y,z)}: {rgba} vs {exp}"

    sx_meta = model["slices"]["x"]
    assert (sx_meta["count"], sx_meta["sliceWidth"], sx_meta["sliceHeight"]) == (W, D, H)
    im_x = Image.open(os.path.join(assets_dir, sx_meta["file"])).convert("RGBA")
    assert im_x.size == (W * D, H), f"slices_x size mismatch: {im_x.size}"
    px_px = im_x.load()
    for x in range(W):
        x_off = x * D
        for y in range(H):
            py = H - 1 - y
            for z in range(D):
                rgba = px_px[x_off + z, py]
                exp = grid.get((x, y, z))
                if exp is None:
                    assert rgba[3] == 0, f"slices_x unexpected solid at {(x,y,z)}"
                else:
                    assert rgba == (*exp, 255), f"slices_x mismatch at {(x,y,z)}: {rgba} vs {exp}"

    print(f"[OK] Contract verified: {W}x{H}x{D}, {len(grid)} voxels, palette={len(palette)}, all 3 slice strips exact.")


def render_ortho_dda(
    vol: list[list[list[int]]],
    palette: list[tuple[int, int, int]],
    W: int,
    H: int,
    D: int,
    yaw_deg: float,
    pitch_deg: float,
    shade_strength: float = 0.0,
    canvas_w: int = 64,
    canvas_h: int = 64,
) -> Image.Image:
    # 高解像度キャンバスへ直接回転描画するとドットが斜めダイヤ型(Mixel)に歪むため、ネイティブ解像度の正射影DDAで走査してから整数拡大する
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    fx = math.sin(yaw) * math.cos(pitch)
    fy = math.sin(pitch)
    fz = math.cos(yaw) * math.cos(pitch)

    rx = math.cos(yaw)
    ry = 0.0
    rz = -math.sin(yaw)

    ux = -math.sin(yaw) * math.sin(pitch)
    uy = math.cos(pitch)
    uz = -math.cos(yaw) * math.sin(pitch)

    dx, dy, dz = -fx, -fy, -fz

    cx0 = W * 0.5
    cy0 = H * 0.5
    cz0 = D * 0.5

    out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    opx = out.load()

    step_x = 1 if dx >= 0 else -1
    step_y = 1 if dy >= 0 else -1
    step_z = 1 if dz >= 0 else -1
    inv_dx = 1.0 / abs(dx) if abs(dx) > 1e-9 else 1e12
    inv_dy = 1.0 / abs(dy) if abs(dy) > 1e-9 else 1e12
    inv_dz = 1.0 / abs(dz) if abs(dz) > 1e-9 else 1e12

    half_u = canvas_w * 0.5
    half_v = canvas_h * 0.5
    dist_start = 80.0

    for py in range(canvas_h):
        v = half_v - (py + 0.5)
        for px in range(canvas_w):
            u = (px + 0.5) - half_u
            ox = cx0 + u * rx + v * ux + dist_start * fx
            oy = cy0 + u * ry + v * uy + dist_start * fy
            oz = cz0 + u * rz + v * uz + dist_start * fz

            tmin, tmax = -1e9, 1e9
            for o_val, d_val, bmax in ((ox, dx, W), (oy, dy, H), (oz, dz, D)):
                if abs(d_val) < 1e-9:
                    if o_val < 0.0 or o_val >= bmax:
                        tmin, tmax = 1.0, -1.0
                        break
                else:
                    t1 = (0.0 - o_val) / d_val
                    t2 = (bmax - o_val) / d_val
                    if t1 > t2:
                        t1, t2 = t2, t1
                    if t1 > tmin:
                        tmin = t1
                    if t2 < tmax:
                        tmax = t2
            if tmin > tmax or tmax < 0.0:
                continue

            t_enter = max(0.0, tmin) + 1e-5
            px_p = ox + t_enter * dx
            py_p = oy + t_enter * dy
            pz_p = oz + t_enter * dz

            ix = max(0, min(W - 1, int(math.floor(px_p))))
            iy = max(0, min(H - 1, int(math.floor(py_p))))
            iz = max(0, min(D - 1, int(math.floor(pz_p))))

            if abs(dx) > 1e-9:
                next_x = (ix + 1 - px_p) * inv_dx if step_x > 0 else (px_p - ix) * inv_dx
            else:
                next_x = 1e12
            if abs(dy) > 1e-9:
                next_y = (iy + 1 - py_p) * inv_dy if step_y > 0 else (py_p - iy) * inv_dy
            else:
                next_y = 1e12
            if abs(dz) > 1e-9:
                next_z = (iz + 1 - pz_p) * inv_dz if step_z > 0 else (pz_p - iz) * inv_dz
            else:
                next_z = 1e12

            face_axis = 2
            for _ in range(W + H + D + 4):
                if 0 <= ix < W and 0 <= iy < H and 0 <= iz < D:
                    pi = vol[ix][iy][iz]
                    if pi >= 0:
                        r, g, b = palette[pi]
                        if shade_strength > 0.0:
                            if face_axis == 1:
                                fac = 1.04 if step_y < 0 else 0.86
                            elif face_axis == 2:
                                fac = 1.00 if step_z < 0 else 0.93
                            else:
                                fac = 0.95
                            mul = 1.0 + (fac - 1.0) * shade_strength
                            r = max(0, min(255, int(round(r * mul))))
                            g = max(0, min(255, int(round(g * mul))))
                            b = max(0, min(255, int(round(b * mul))))
                        opx[px, py] = (r, g, b, 255)
                        break
                else:
                    break

                if next_x <= next_y and next_x <= next_z:
                    ix += step_x
                    next_x += inv_dx
                    face_axis = 0
                elif next_y <= next_z:
                    iy += step_y
                    next_y += inv_dy
                    face_axis = 1
                else:
                    iz += step_z
                    next_z += inv_dz
                    face_axis = 2

    return out


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT
    model_path = os.path.join(ASSETS_DIR, "model.json")
    with open(model_path, "r", encoding="utf-8") as f:
        model = json.load(f)

    verify_contract(model, ASSETS_DIR)

    W, H, D = model["size"]["x"], model["size"]["y"], model["size"]["z"]
    palette = [hex_to_rgb(c) for c in model["palette"]]
    vol = [[[-1] * D for _ in range(H)] for _ in range(W)]
    for vox in model["voxels"]:
        vx, vy, vz, pi = vox[:4]
        vol[vx][vy][vz] = pi

    ref_front = Image.open(os.path.join(ASSETS_DIR, model["referenceViews"]["front"])).convert("RGBA")
    ref_side = Image.open(os.path.join(ASSETS_DIR, model["referenceViews"]["side"])).convert("RGBA")

    cw, ch = 64, 64

    def center_pad(im: Image.Image) -> Image.Image:
        c = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        c.paste(im, ((cw - im.width) // 2, (ch - im.height) // 2), im)
        return c

    # 実ビューアの初期斜め俯瞰プリセット(yaw=32°, pitch=35°)と同一角度で両ツインテールの可視性を事前検証する
    panels = [
        ("REF FRONT (Original)", center_pad(ref_front)),
        ("3D FRONT (Flat 0%)", render_ortho_dda(vol, palette, W, H, D, 0.0, 0.0, 0.0, cw, ch)),
        ("REF SIDE (Original)", center_pad(ref_side)),
        ("3D SIDE +90 deg (Left)", render_ortho_dda(vol, palette, W, H, D, 90.0, 0.0, 0.0, cw, ch)),
        ("3D BACK 180 deg (Flat)", render_ortho_dda(vol, palette, W, H, D, 180.0, 0.0, 0.0, cw, ch)),
        ("QUARTER 32/35 (Flat)", render_ortho_dda(vol, palette, W, H, D, 32.0, 35.0, 0.0, cw, ch)),
        ("QUARTER -32/35 (Shaded)", render_ortho_dda(vol, palette, W, H, D, -32.0, 35.0, 0.50, cw, ch)),
        ("BACK-QTR 145/25", render_ortho_dda(vol, palette, W, H, D, 145.0, 25.0, 0.45, cw, ch)),
        ("TOP 90 deg (+Y)", render_ortho_dda(vol, palette, W, H, D, 0.0, 89.9, 0.35, cw, ch)),
        ("LOW -25 deg (Look-Up)", render_ortho_dda(vol, palette, W, H, D, 20.0, -25.0, 0.45, cw, ch)),
    ]

    scale = 4
    pw = cw * scale
    ph = ch * scale
    header_h = 28
    pad = 16
    cols = 5
    rows = 2

    sheet_w = pad + cols * (pw + pad)
    sheet_h = 46 + rows * (ph + header_h + pad)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (34, 37, 46))
    draw = ImageDraw.Draw(sheet)
    draw.text(
        (pad, 14),
        f"CHARACTER 2 - 3D Voxel & Tri-Axis Slice Diagnostic ({W}x{H}x{D}, {len(model['voxels'])} voxels)",
        fill=(235, 238, 246),
    )

    for idx, (label, panel_im) in enumerate(panels):
        r = idx // cols
        c = idx % cols
        x0 = pad + c * (pw + pad)
        y0 = 46 + r * (ph + header_h + pad)

        # 純白リボンと淡色髪の輪郭が背景と同化して見落とすのを防ぐため暗色チェッカー盤の上に描画する
        card = Image.new("RGB", (pw, ph), (54, 59, 72))
        cp = card.load()
        for yy in range(ph):
            for xx in range(pw):
                if ((xx // 16) + (yy // 16)) % 2 == 1:
                    cp[xx, yy] = (64, 70, 84)
        up = panel_im.resize((pw, ph), Image.NEAREST)
        card.paste(up, (0, 0), up)
        sheet.paste(card, (x0, y0 + header_h))
        draw.rectangle([x0 - 1, y0 + header_h - 1, x0 + pw, y0 + header_h + ph], outline=(92, 98, 116))
        draw.text((x0 + 4, y0 + 7), label, fill=(210, 216, 230))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path)
    print(f"[OK] Saved diagnostic sheet -> {out_path}")


if __name__ == "__main__":
    main()
