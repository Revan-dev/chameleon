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
        hero_element["z_index"] = lower_z + 1
        if th > 160:
            image_slot_x = panel_w * 0.5
            image_slot_w = panel_w - image_slot_x - margin
            scale = min(
                image_slot_w / max(hero["w"], 1e-6),
                (th - 2 * margin) / max(hero["h"], 1e-6),
            )
            image_w, image_h = hero["w"] * scale, hero["h"] * scale
            hero_element["x"] = image_slot_x + (image_slot_w - image_w) / 2.0
            hero_element["y"] = (th - image_h) / 2.0
            hero_element["width"], hero_element["height"] = image_w, image_h
            hero_element["fit"] = "contain"

        legal = [
            unit for unit in texts
            if any("legal" in str(member.get("id", "")).lower()
                   for member in unit["members"])
        ]
        texts = [unit for unit in texts if unit not in legal]
        footer_h = min(20.0, th * 0.24) if legal and th <= 160 else 0.0
        footer_gap = max(1.0, th * 0.015) if footer_h else 0.0
        overlay_h = max(1.0, inner_h - footer_h - footer_gap)
        heading = None
        paragraph = None

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
            heading_share = 0.52 if th <= 160 else 0.55
            heading_h = max(1.0, (overlay_h - overlay_gap) * heading_share)
            paragraph_h = max(1.0, overlay_h - overlay_gap - heading_h)
            if th > 160:
                _place_unit(
                    heading, overlay_x, margin, overlay_w, heading_h
                )
                for member in heading["members"]:
                    member["z_index"] = max(
                        member.get("z_index", 0), hero_element["z_index"] + 1
                    )
            if paragraph is not None:
                if th > 160:
                    text_w = max(1.0, panel_w * 0.44)
                    text_x = margin
                    text_gap = max(8.0, inner_h * 0.04)
                    heading_h = max(1.0, inner_h * 0.4)
                    paragraph_y = margin + heading_h + text_gap
                    paragraph_h = max(
                        1.0, th - margin - paragraph_y
                    )
                    _place_unit(
                        heading, text_x, margin, text_w, heading_h
                    )
                    _place_unit(
                        paragraph, text_x, paragraph_y, text_w, paragraph_h
                    )
                    for unit in (heading, paragraph):
                        for member in unit["members"]:
                            member["z_index"] = max(
                                member.get("z_index", 0),
                                hero_element["z_index"] + 1,
                            )
                    texts = [
                        unit for unit in texts
                        if unit not in (heading, paragraph)
                    ]

        if th <= 160:
            compact_units = sorted(
                logos + others + texts, key=lambda unit: (unit["y"], unit["x"])
            )
            _place_short_banner(
                hero, bgs, compact_units, heading, paragraph, legal,
                tw, th,
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
        if float(member.get("rotation", 0)):
            member["rotation"] = 0
        if member["type"] == "text":
            member["x"] = x + 2.0
            member["y"] = y
            member["width"] = max(1.0, w - 4.0)
            member["height"] = h
            member["font_size"] = 8.0
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


def _place_short_banner(hero, backgrounds, units, heading, paragraph, legal, tw, th):
    margin = max(1.0, th * 0.02)
    hero_element = hero["members"][0]
    background_z = max(
        (el.get("z_index", 0) for el in backgrounds),
        default=min(
            (member.get("z_index", 0)
             for unit in units for member in unit["members"]),
            default=0,
        ) - 1,
    )
    hero_element["z_index"] = max(
        hero_element.get("z_index", 0), background_z + 1
    )
    if not backgrounds:
        hero_element["x"], hero_element["y"] = 0.0, 0.0
        hero_element["width"], hero_element["height"] = tw, th
        hero_element["fit"] = "cover"

    text_y = margin
    text_h = max(1.0, th * 0.57)
    text_w = max(1.0, tw * 0.41)
    for index, unit in enumerate((heading, paragraph)):
        if unit is None:
            continue
        x = margin if index == 0 else tw - margin - text_w
        _place_unit(unit, x, text_y, text_w, text_h)
        for member in unit["members"]:
            member["z_index"] = max(
                member.get("z_index", 0), hero_element["z_index"] + 1
            )
            member["font_size"] = min(
                float(member.get("font_size", MIN_FONT)), 8.0
            )

    supporting_units = [
        unit for unit in units
        if unit is not heading and unit is not paragraph
    ]
    middle_images = [
        unit for unit in supporting_units if _looks_like_image(unit)
    ]
    if backgrounds:
        middle_images.append(hero)
    support_units = [
        unit for unit in supporting_units if unit not in middle_images
    ]
    support_gap = max(1.0, tw * 0.005)
    support_y = th * 0.66
    support_h = th * 0.16
    footer_y = th * 0.82
    footer_h = max(1.0, th - footer_y - margin)
    image_gap = max(1.0, th * 0.015)
    image_w = tw * 0.18
    image_x = (tw - image_w) / 2.0
    main_images = [unit for unit in middle_images if unit is hero]
    small_images = [unit for unit in middle_images if unit is not hero]
    image_y = margin
    if small_images:
        small_h = max(
            1.0,
            (th * 0.26 - image_gap * max(0, len(small_images) - 1))
            / len(small_images),
        )
        for unit in small_images:
            _place_compact_unit(
                unit, image_x, image_y, image_w, small_h
            )
            image_y += small_h + image_gap
            for member in unit["members"]:
                member["z_index"] = max(
                    member.get("z_index", 0), hero_element["z_index"] + 1
                )
    for unit in main_images:
        main_h = max(1.0, th * 0.30)
        _place_compact_unit(
            unit, image_x, (th - main_h) / 2.0, image_w, main_h
        )
        for member in unit["members"]:
            member["z_index"] = max(
                member.get("z_index", 0), hero_element["z_index"]
            )
    if support_units:
        cell_w = (tw - 2 * margin - support_gap * (len(support_units) - 1)) / len(support_units)
        for index, unit in enumerate(support_units):
            _place_compact_unit(
                unit,
                margin + index * (cell_w + support_gap),
                support_y,
                cell_w,
                support_h,
            )
            for member in unit["members"]:
                member["z_index"] = max(
                    member.get("z_index", 0), hero_element["z_index"] + 1
                )

    for unit in legal:
        _place_compact_unit(unit, margin, footer_y, tw - 2 * margin, footer_h)
        for member in unit["members"]:
            if member["type"] == "text":
                member["font_size"] = min(
                    float(member.get("font_size", MIN_FONT)), 8.0
                )
                member["z_index"] = max(
                    member.get("z_index", 0), hero_element["z_index"] + 1
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
