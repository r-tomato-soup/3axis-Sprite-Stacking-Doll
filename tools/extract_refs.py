import os
from PIL import Image

REF_SHEET_PATH = os.environ.get("CHAR2_REF_SHEET_PATH", "")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_ROOT, "public", "assets")

# JPEGの量子化揺らぎで同色面がまだらになるのを防ぐため、元絵固有の代表色パレットへ吸着させる
CANONICAL_PALETTE = [
    (252, 252, 253),
    (244, 244, 247),
    (229, 230, 236),
    (208, 209, 217),
    (176, 175, 184),
    (251, 247, 241),
    (242, 237, 228),
    (231, 223, 213),
    (215, 204, 194),
    (238, 219, 216),
    (219, 196, 194),
    (222, 218, 234),
    (186, 180, 205),
    (152, 145, 169),
    (112, 105, 124),
    (150, 142, 141),
    (116, 109, 110),
    (82, 77, 80),
]


def sample_4x_grid(img: Image.Image, x0: int, y0: int, x1: int, y1: int, ox: int, oy: int) -> Image.Image:
    px = img.load()
    wc = (x1 - x0 - ox) // 4
    hc = (y1 - y0 - oy) // 4
    out = Image.new("RGB", (wc, hc))
    opx = out.load()
    for cy in range(hc):
        yy = y0 + oy + cy * 4
        for cx in range(wc):
            xx = x0 + ox + cx * 4
            # 4x4拡大ブロックの外周1pxはJPEGの8x8ブロック境界リンギングや隣色滲みを含むため中心2x2のみ平均する
            pts = (px[xx + 1, yy + 1], px[xx + 2, yy + 1], px[xx + 1, yy + 2], px[xx + 2, yy + 2])
            opx[cx, cy] = (
                int(round(sum(p[0] for p in pts) * 0.25)),
                int(round(sum(p[1] for p in pts) * 0.25)),
                int(round(sum(p[2] for p in pts) * 0.25)),
            )
    return out


def quantize_pixel(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    best_col = CANONICAL_PALETTE[0]
    best_dist = 1e18
    # 紫の瞳や暖色の髪がグレー系へ誤吸着しないよう、色差（R-B）の不一致に重みを課す
    rb_diff = r - b
    for pr, pg, pb in CANONICAL_PALETTE:
        p_rb = pr - pb
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2 + ((rb_diff - p_rb) ** 2) * 1.5
        if d < best_dist:
            best_dist = d
            best_col = (pr, pg, pb)
    return best_col


def extract_clean_sprite(raw_grid: Image.Image, clear_leg_slot: bool = False) -> Image.Image:
    w, h = raw_grid.size
    gp = raw_grid.load()

    def is_grey_bg(c: tuple[int, int, int]) -> bool:
        return 218 <= c[0] <= 236 and 218 <= c[1] <= 236 and 218 <= c[2] <= 236 and (max(c) - min(c) <= 7)

    def is_sticker_halo(c: tuple[int, int, int]) -> bool:
        return min(c) >= 212 and (max(c) - min(c) <= 12)

    # 内部の白い衣装やリボンへ浸食させないため、まず外周境界と接続するグレー背景のみをフラッドフィルする
    grey = [[False] * w for _ in range(h)]
    stack: list[tuple[int, int]] = []
    for x in range(w):
        for y in (0, h - 1):
            if is_grey_bg(gp[x, y]):
                grey[y][x] = True
                stack.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if is_grey_bg(gp[x, y]) and not grey[y][x]:
                grey[y][x] = True
                stack.append((x, y))

    while stack:
        cx, cy = stack.pop()
        for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
            if 0 <= nx < w and 0 <= ny < h and not grey[ny][nx] and is_grey_bg(gp[nx, ny]):
                grey[ny][nx] = True
                stack.append((nx, ny))

    # 参照シート特有の1ドット白ステッカー縁取りは、無制限膨張で白い衣装を削らないよう外部グレー背景の8近傍1層だけを剥がす
    trans = [row[:] for row in grey]
    for y in range(h):
        for x in range(w):
            if not trans[y][x] and is_sticker_halo(gp[x, y]):
                if any(
                    0 <= x + dx < w and 0 <= y + dy < h and grey[y + dy][x + dx]
                    for dy in (-1, 0, 1)
                    for dx in (-1, 0, 1)
                ):
                    trans[y][x] = True

    # SIDEの首後ろポケットのように外周と非接続な小背景穴は、リボン内の淡影を誤削除しないよう暗色主線で完全包囲された場合のみ抜く
    visited = [[False] * w for _ in range(h)]
    for sy in range(1, h - 1):
        for sx in range(1, w - 1):
            if not trans[sy][sx] and not visited[sy][sx] and is_grey_bg(gp[sx, sy]):
                comp = [(sx, sy)]
                visited[sy][sx] = True
                q = [(sx, sy)]
                grey_cnt = 1
                surrounded_by_outline = True
                while q:
                    cx, cy = q.pop()
                    for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                        if not (0 <= nx < w and 0 <= ny < h):
                            surrounded_by_outline = False
                            continue
                        c = gp[nx, ny]
                        if is_grey_bg(c) or is_sticker_halo(c):
                            if not visited[ny][nx]:
                                visited[ny][nx] = True
                                comp.append((nx, ny))
                                q.append((nx, ny))
                                if is_grey_bg(c):
                                    grey_cnt += 1
                        elif sum(c) / 3.0 > 185.0:
                            surrounded_by_outline = False
                if surrounded_by_outline and grey_cnt >= 2 and len(comp) <= 30:
                    for ux, uy in comp:
                        trans[uy][ux] = True

    # 毛先フック内側のようにグレー背景が直接届かない1px白ステッカー残りは、四方が背景と暗色主線のみで囲まれている場合だけ除去する
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if not trans[y][x] and min(gp[x, y]) >= 235 and (max(gp[x, y]) - min(gp[x, y]) <= 8):
                adj_trans = sum(1 for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)) if trans[y + dy][x + dx])
                adj_dark = sum(
                    1
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
                    if not trans[y + dy][x + dx] and sum(gp[x + dx, y + dy]) / 3.0 < 155.0
                )
                if adj_trans >= 1 and (adj_trans + adj_dark) == 4:
                    trans[y][x] = True

    if clear_leg_slot:
        # 両脚の間の2ドット隙間は左右の白ステッカー縁同士が接触してグレー背景が奥まで届かないため、脚主線に挟まれた無彩色隙間を下端から抜く
        mid_x = w // 2
        for y in range(h - 1, h // 2, -1):
            for x in range(mid_x - 2, mid_x + 2):
                c = gp[x, y]
                if not trans[y][x] and min(c) >= 198 and (max(c) - min(c) <= 12):
                    left_dark = sum(gp[x - 1, y]) / 3.0 < 145 or (
                        x >= 2 and min(gp[x - 1, y]) >= 198 and sum(gp[x - 2, y]) / 3.0 < 145
                    )
                    right_dark = sum(gp[x + 1, y]) / 3.0 < 145 or (
                        x + 2 < w and min(gp[x + 1, y]) >= 198 and sum(gp[x + 2, y]) / 3.0 < 300 and sum(gp[x + 2, y]) / 3.0 < 145
                    )
                    if left_dark and right_dark:
                        trans[y][x] = True

    rgba = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rp = rgba.load()
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if not trans[y][x]:
                qr, qg, qb = quantize_pixel(gp[x, y])
                rp[x, y] = (qr, qg, qb, 255)
                xs.append(x)
                ys.append(y)

    cropped = rgba.crop((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    # 比較パネルでの拡大表示時に端の1pxが見切れないよう最小限の透明余白を持たせる
    padded = Image.new("RGBA", (cropped.width + 2, cropped.height + 2), (0, 0, 0, 0))
    padded.paste(cropped, (1, 1))
    return padded


def extract_references() -> tuple[Image.Image, Image.Image]:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    sheet = Image.open(REF_SHEET_PATH).convert("RGB")

    # 上段左のFRONTのみ約4.7倍の非整数拡大で境界滲みがあるため、他ビューと同一の厳密4.0倍ドットグリッドを持つ中段FRONTを採用する
    front_grid = sample_4x_grid(sheet, 400, 304, 620, 512, ox=0, oy=2)
    side_grid = sample_4x_grid(sheet, 556, 76, 680, 286, ox=0, oy=2)

    ref_front = extract_clean_sprite(front_grid, clear_leg_slot=True)
    ref_side = extract_clean_sprite(side_grid, clear_leg_slot=False)

    ref_front.save(os.path.join(ASSETS_DIR, "ref_front.png"))
    ref_side.save(os.path.join(ASSETS_DIR, "ref_side.png"))
    print(f"Saved ref_front.png ({ref_front.size}) and ref_side.png ({ref_side.size})")
    return ref_front, ref_side


if __name__ == "__main__":
    extract_references()
