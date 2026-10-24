"""
THIS IS THE FILE YOU IMPLEMENT.

Breakpoint reflow: scale in proportion when the aspect ratio is close;
rearrange into a row or column when it isn't. Same elements, no stretching.
"""

from copy import deepcopy
from typing import Any

# --- knobs you may want to tweak -------------------------------------------
RATIO_BOUNDARY = 1.35   # how far aspect may drift before we rearrange
MIN_UNIFORM = 0.45      # if everything would shrink more than this, rearrange
MIN_FONT = 12.0
MIN_GRID_ROW = 48.0
MARGIN_FRAC = 0.05      # padding as a fraction of the smaller canvas side
GAP_FRAC = 0.03
# ---------------------------------------------------------------------------


def resize(source: dict[str, Any], target_canvas: dict[str, Any]) -> dict[str, Any]:
    sw = float(source["canvas"]["width"])
    sh = float(source["canvas"]["height"])
    tw = float(target_canvas["width"])
    th = float(target_canvas["height"])

    elements = [deepcopy(el) for el in source["elements"]]

    sx, sy = tw / sw, th / sh
    uniform = min(sx, sy)
    stretch = max(sx / sy, sy / sx)

    if stretch <= RATIO_BOUNDARY and uniform >= MIN_UNIFORM:
        _similar(elements, sw, sh, tw, th, uniform, sx, sy)
    elif (tw / th) >= (sw / sh):
        _row(elements, sw, sh, tw, th)
    else:
        _column(elements, sw, sh, tw, th)

    for el in elements:
        _clamp(el, tw, th)
        if el["type"] == "text":
            el["font_size"] = max(1.0, float(el["font_size"]))

    return {
        "canvas": {
            "width": int(target_canvas["width"]),
            "height": int(target_canvas["height"]),
        },
        "elements": elements,
    }


# --- similar aspect: one scale, keep relative placement ----------------------

def _similar(elements, sw, sh, tw, th, s, sx, sy):
    for el in elements:
        if _is_bg(el, sw, sh):
            el["x"], el["y"] = 0.0, 0.0
            el["width"], el["height"] = tw, th
            continue
        cx = (el["x"] + el["width"] / 2.0) / sw
        cy = (el["y"] + el["height"] / 2.0) / sh
        if el["type"] == "text":
            el["width"] *= sx
            el["height"] *= sy
            el["font_size"] = max(MIN_FONT, el["font_size"] * s)
        else:
            el["width"] *= s
            el["height"] *= s
            if "corner_radius" in el:
                el["corner_radius"] *= s
        el["x"] = cx * tw - el["width"] / 2.0
        el["y"] = cy * th - el["height"] / 2.0


# --- past the boundary: rearrange --------------------------------------------

def _row(elements, sw, sh, tw, th):
    """Wide/short canvas: use a half-width image panel with readable overlays."""
    if th <= 160:
        margin = max(2.0, th * 0.02)
        gap = max(1.0, th * 0.015)
    else:
        margin = max(8.0, min(tw, th) * MARGIN_FRAC)
        gap = max(6.0, min(tw, th) * GAP_FRAC)
    inner_h = max(1.0, th - 2 * margin)
    bgs, units = _units(elements, sw, sh)
    _fill_bgs(bgs, tw, th)

    logos = [u for u in units if _is_logo(u)]
    units = [u for u in units if not _is_logo(u)]
    if logos and th > 160:
        logo = logos.pop(0)
        logo_aspect = logo["w"] / max(logo["h"], 1.0)
        logo_w = min(tw * 0.18, inner_h * 0.10 * logo_aspect)
        logo_h = logo_w / max(logo_aspect, 1e-6)
        _place_unit(logo, tw - margin - logo_w, margin, logo_w, logo_h)
        units.extend(logos)

    texts = [u for u in units if u["is_text"]]
    others = [u for u in units if not u["is_text"]]
    others.sort(key=lambda u: (u["y"], u["x"]))

    images = [
        unit for unit in others
        if len(unit["members"]) == 1 and unit["members"][0]["type"] == "image"
    ]
    hero = max(images, key=lambda unit: unit["w"] * unit["h"], default=None)
    if hero is not None:
        others.remove(hero)
        hero_element = hero["members"][0]
        panel_w = tw * 0.5
        lower_z = max(
            (el.get("z_index", 0) for el in bgs),
            default=min(
                (member.get("z_index", 0)
                 for unit in units for member in unit["members"]),
                default=0,
            ) - 1,
        )
        hero_element["x"], hero_element["y"] = 0.0, 0.0
        hero_element["width"], hero_element["height"] = panel_w, th
        hero_element["fit"] = "cover"
        hero_element["z_index"] = lower_z + 1

        if texts:
            heading = max(
                texts,
                key=lambda unit: max(
                    float(member.get("font_size", 0))
                    for member in unit["members"]
                ),
            )
            following = [
                unit for unit in texts
                if unit is not heading and unit["y"] >= heading["y"]
            ]
            paragraph = min(following, key=lambda unit: unit["y"], default=None)
            overlay = [heading]
            if paragraph is not None:
                overlay.append(paragraph)
            texts = [unit for unit in texts if unit not in overlay]

            overlay_x = margin
            overlay_w = max(1.0, panel_w - 2 * margin)
            overlay_gap = max(2.0, inner_h * 0.04)
            heading_h = max(1.0, (inner_h - overlay_gap) * 0.55)
            paragraph_h = max(1.0, inner_h - overlay_gap - heading_h)
            _place_unit(
                heading, overlay_x, margin, overlay_w, heading_h
            )
            for member in heading["members"]:
                member["z_index"] = max(
                    member.get("z_index", 0), hero_element["z_index"] + 1
                )
            if paragraph is not None:
                _place_unit(
                    paragraph,
                    overlay_x,
                    margin + heading_h + overlay_gap,
                    overlay_w,
                    paragraph_h,
                )
                for member in paragraph["members"]:
                    member["z_index"] = max(
                        member.get("z_index", 0), hero_element["z_index"] + 1
                    )

        if th <= 160:
            compact_units = sorted(
                logos + others + texts, key=lambda unit: (unit["y"], unit["x"])
            )
            if not compact_units:
                return
            columns = min(3, len(compact_units))
            rows = (len(compact_units) + columns - 1) // columns
            grid_margin = max(2.0, th * 0.02)
            grid_gap = max(1.0, th * 0.015)
            grid_x = panel_w + grid_margin
            grid_y = grid_margin
            grid_w = max(1.0, tw - grid_x - grid_margin)
            grid_h = max(1.0, th - 2 * grid_margin)
            cell_w = (grid_w - grid_gap * (columns - 1)) / columns
            cell_h = (grid_h - grid_gap * (rows - 1)) / rows
            for index, unit in enumerate(compact_units):
                column, row = index % columns, index // columns
                _place_compact_unit(
                    unit,
                    grid_x + column * (cell_w + grid_gap),
                    grid_y + row * (cell_h + grid_gap),
                    cell_w,
                    cell_h,
                )
            return

        content_x = panel_w + margin
        inner_w = max(1.0, tw - content_x - margin)
    else:
        content_x = margin
        inner_w = max(1.0, tw - 2 * margin)

    for u in others:
        h = inner_h * 0.72
        aspect = u["w"] / max(u["h"], 1)
        u["pw"], u["ph"] = h * aspect, h

    n = len(others) + (1 if texts else 0)
    gaps = gap * max(0, n - 1)
    others_w = sum(u["pw"] for u in others)
    text_w = max(inner_w * 0.35, 120.0) if texts else 0.0
    budget = max(1.0, inner_w - gaps)
    if others_w + text_w > budget and others_w > 0:
        scale = max(0.25, (budget - text_w) / others_w)
        for u in others:
            u["pw"] *= scale
            u["ph"] *= scale
        others_w = sum(u["pw"] for u in others)
    if texts:
        text_w = max(80.0, budget - others_w)

    x = content_x
    placed_text = False
    first_image_done = False
    for u in others:
        y = margin + (inner_h - u["ph"]) / 2.0
        _place_unit(u, x, y, min(u["pw"], max(1.0, tw - margin - x)), u["ph"])
        x += u["pw"] + gap
        if _looks_like_image(u):
            first_image_done = True
        if texts and not placed_text and first_image_done:
            _place_text_column(texts, x, margin, text_w, inner_h)
            x += text_w + gap
            placed_text = True
    if texts and not placed_text:
        _place_text_column(texts, x, margin, text_w, inner_h)


def _place_compact_unit(unit, x, y, w, h):
    for member in unit["members"]:
        if member["type"] == "text":
            member["x"] = x + 2.0
            member["y"] = y
            member["width"] = max(1.0, w - 4.0)
            member["height"] = h
            member["font_size"] = max(
                MIN_FONT,
                min(float(member.get("font_size", MIN_FONT)), h / 2.4),
            )
        else:
            if member["type"] == "image":
                aspect = float(member["width"]) / max(float(member["height"]), 1e-6)
                image_w = min(w, h * aspect)
                image_h = image_w / max(aspect, 1e-6)
                member["x"] = x + (w - image_w) / 2.0
                member["y"] = y + (h - image_h) / 2.0
                member["width"], member["height"] = image_w, image_h
                member["fit"] = "contain"
            else:
                member["x"], member["y"] = x, y
                member["width"], member["height"] = w, h
            if "corner_radius" in member:
                member["corner_radius"] = min(
                    h / 2.0, float(member["corner_radius"])
                )


def _column(elements, sw, sh, tw, th):
    """Tall canvas: pin the logo, then stack content in responsive grid rows."""
    margin = max(8.0, min(tw, th) * MARGIN_FRAC)
    gap = max(6.0, min(tw, th) * GAP_FRAC)
    inner_w, inner_h = tw - 2 * margin, th - 2 * margin
    bgs, units = _units(elements, sw, sh)
    _promote_background(bgs, units)
    _fill_bgs(bgs, tw, th)
    units.sort(key=lambda u: (u["y"], u["x"]))

    logos = [u for u in units if _is_logo(u)]
    units = [u for u in units if not _is_logo(u)]
    logo_height = 0.0
    if logos:
        logo = logos.pop(0)
        logo_aspect = logo["w"] / max(logo["h"], 1.0)
        logo_w = min(inner_w * 0.38, inner_h * 0.10 * logo_aspect)
        logo_h = logo_w / max(logo_aspect, 1e-6)
        _place_unit(logo, tw - margin - logo_w, margin, logo_w, logo_h)
        logo_height = logo_h + gap
        units.extend(logos)

    # Short grouped units (for example, badges) share a row instead of
    # being reduced to a narrow full-width column.
    rows = []
    index = 0
    while index < len(units):
        unit = units[index]
        compact = unit["members"][0].get("group_id") and unit["h"] <= sh * 0.06
        if compact and index + 1 < len(units):
            next_unit = units[index + 1]
            next_compact = (
                next_unit["members"][0].get("group_id")
                and next_unit["h"] <= sh * 0.06
            )
            if next_compact:
                rows.append([unit, next_unit])
                index += 2
                continue
        rows.append([unit])
        index += 1

    shares = [max(unit["h"] for unit in row) for row in rows]
    total = sum(shares) or 1.0
    available_h = max(1.0, inner_h - logo_height)
    gaps = gap * max(0, len(rows) - 1)
    budget = max(1.0, available_h - gaps)
    row_floor = min(MIN_GRID_ROW, budget / max(1, len(rows)))
    extra_height = max(0.0, budget - row_floor * len(rows))
    row_heights = [
        row_floor + extra_height * (share / total)
        for share in shares
    ]

    y = margin + logo_height
    for row, h in zip(rows, row_heights):
        if len(row) == 2:
            cell_w = (inner_w - gap) / 2.0
            for column, unit in enumerate(row):
                _place_unit(unit, margin + column * (cell_w + gap), y, cell_w, h)
        else:
            unit = row[0]
            if unit["is_text"]:
                w, x = inner_w, margin
            else:
                aspect = unit["w"] / max(unit["h"], 1)
                w = min(inner_w, h * aspect)
                x = margin + (inner_w - w) / 2.0
            _place_unit(unit, x, y, w, h)
        y += h + gap


def _place_text_column(texts, x, y, w, h):
    texts = sorted(texts, key=lambda u: u["y"])
    gap = max(4.0, h * 0.05)
    budget = max(1.0, h - gap * max(0, len(texts) - 1))
    total = sum(u["h"] for u in texts) or 1.0
    cy = y
    for u in texts:
        uh = budget * (u["h"] / total)
        _place_unit(u, x, cy, w, uh)
        cy += uh + gap


# --- units: groups stay glued; background is separate ------------------------

def _units(elements, sw, sh):
    bgs, grouped, singles = [], {}, []
    for el in elements:
        if _is_bg(el, sw, sh):
            bgs.append(el)
            continue
        gid = el.get("group_id")
        if gid:
            grouped.setdefault(gid, []).append(el)
        else:
            singles.append(el)

    units = []
    for members in grouped.values():
        units.append(_make_unit(members))
    for el in singles:
        units.append(_make_unit([el]))
    return bgs, units


def _make_unit(members):
    x0 = min(m["x"] for m in members)
    y0 = min(m["y"] for m in members)
    x1 = max(m["x"] + m["width"] for m in members)
    y1 = max(m["y"] + m["height"] for m in members)
    return {
        "members": members,
        "x": x0,
        "y": y0,
        "w": x1 - x0,
        "h": y1 - y0,
        "is_text": all(m["type"] == "text" for m in members),
    }


def _place_unit(unit, x, y, w, h):
    members = unit["members"]
    ox, oy = unit["x"], unit["y"]
    ow, oh = max(unit["w"], 1e-6), max(unit["h"], 1e-6)
    s = min(w / ow, h / oh)
    if unit["is_text"]:
        sx, sy = w / ow, h / oh
        s_font = min(sx, sy)
        for el in members:
            el["x"] = x + (el["x"] - ox) * sx
            el["y"] = y + (el["y"] - oy) * sy
            el["width"] *= sx
            el["height"] *= sy
            el["font_size"] = max(MIN_FONT, el["font_size"] * s_font)
        return
    used_w, used_h = ow * s, oh * s
    px = x + (w - used_w) / 2.0
    py = y + (h - used_h) / 2.0
    for el in members:
        el["x"] = px + (el["x"] - ox) * s
        el["y"] = py + (el["y"] - oy) * s
        el["width"] *= s
        el["height"] *= s
        if "corner_radius" in el:
            el["corner_radius"] *= s
        if el["type"] == "text":
            el["font_size"] = max(MIN_FONT, el["font_size"] * s)


def _fill_bgs(bgs, tw, th):
    for el in bgs:
        el["x"], el["y"] = 0.0, 0.0
        el["width"], el["height"] = tw, th


def _promote_background(bgs, units):
    if bgs:
        return
    candidates = [
        unit for unit in units
        if len(unit["members"]) == 1 and unit["members"][0]["type"] == "image"
    ]
    if not candidates:
        return

    background = max(candidates, key=lambda unit: unit["w"] * unit["h"])
    units.remove(background)
    element = background["members"][0]
    element["fit"] = "cover"
    other_z = [
        member.get("z_index", 0)
        for unit in units
        for member in unit["members"]
    ]
    element["z_index"] = min(other_z, default=element.get("z_index", 0)) - 1
    bgs.append(element)


def _is_bg(el, cw, ch):
    return (
        el["type"] == "image"
        and el["width"] >= 0.85 * cw
        and el["height"] >= 0.85 * ch
        and el["x"] <= 0.08 * cw
        and el["y"] <= 0.08 * ch
    )


def _looks_like_image(unit):
    return any(m["type"] == "image" for m in unit["members"])


def _is_logo(unit):
    return any(
        "logo" in str(member.get("id", "")).lower()
        or "logo" in str(member.get("asset_id", "")).lower()
        for member in unit["members"]
    )


def _clamp(el, tw, th):
    el["width"] = max(0.0, min(float(el["width"]), tw))
    el["height"] = max(0.0, min(float(el["height"]), th))
    el["x"] = max(0.0, min(float(el["x"]), tw - el["width"]))
    el["y"] = max(0.0, min(float(el["y"]), th - el["height"]))
