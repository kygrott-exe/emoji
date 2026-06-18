import asyncio, gzip, json, copy, io, os, random, string, logging
from pathlib import Path

import lottie
from lottie.utils.font import RawFontRenderer
from lottie import objects, NVector, Color
from lottie.objects.shapes import Fill

from aiogram import Bot, Dispatcher, F
from aiogram.types import (Message, CallbackQuery,
                            InlineKeyboardMarkup, InlineKeyboardButton,
                            BufferedInputFile)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR     = Path(__file__).parent.resolve()
LOTTIES_DIR  = BASE_DIR / "lotties"
DEFAULT_FONT = str(BASE_DIR / "Anton-Regular.ttf")

BOT_TOKEN    = os.getenv("BOT_TOKEN", "7231412092:AAHmyj1JJf6_lgHoFapdpAptfx4Dx_n_7Uo")
LOGO_ID      = "mylogo"
COLOR_BA     = "BA0047"
COLOR_FF     = "FF4A52"
COLOR_NEW    = "44BEF9"
COLOR_WHITE  = "FFFFFF"
ALLOWED_USER = 1899208318  # Your Telegram user ID

# ── Preset color palettes ──────────────────────────────────────────────────────
PRESET_COLORS = {
    "🔴 Red":     "FF0000",
    "🟠 Orange":  "FF6600",
    "🟡 Yellow":  "FFD700",
    "🟢 Green":   "00CC44",
    "🔵 Blue":    "0066FF",
    "🟣 Purple":  "8800CC",
    "⚫ Black":   "111111",
    "⚪ White":   "FFFFFF",
    "🩷 Pink":    "FF4499",
    "🩵 Cyan":    "00CCFF",
    "✏️ Custom":  "__custom__",
}

# ── Preset gradients (name → [hex_start, hex_end]) ────────────────────────────
PRESET_GRADIENTS = {
    "📸 Instagram":  ["F58529", "DD2A7B"],   # orange → magenta
    "🌅 Sunset":     ["FF6B6B", "FFD93D"],   # red → yellow
    "🌊 Ocean":      ["0099CC", "00CC88"],   # blue → teal
    "🔥 Fire":       ["FF4500", "FFD700"],   # deep orange → gold
    "🌌 Galaxy":     ["1A0533", "6B21A8"],   # dark → purple
    "🍬 Candy":      ["FF69B4", "FFB6C1"],   # hot pink → light pink
    "🌿 Nature":     ["228B22", "90EE90"],   # forest → light green
    "🌙 Midnight":   ["0F0C29", "302B63"],   # dark navy → deep purple
    "❄️ Ice":        ["74EBD5", "ACB6E5"],   # aqua → periwinkle
    "☀️ Gold":       ["F7971E", "FFD200"],   # amber → gold
    "⬛ None":       "__none__",             # no gradient
}

# ── Gradient directions ────────────────────────────────────────────────────────
GRADIENT_DIRS = {
    "⬇️ Top → Bottom":   {"sx": 0.5, "sy": 0.0, "ex": 0.5, "ey": 1.0},
    "➡️ Left → Right":   {"sx": 0.0, "sy": 0.5, "ex": 1.0, "ey": 0.5},
    "↘️ Diagonal ↘":     {"sx": 0.0, "sy": 0.0, "ex": 1.0, "ey": 1.0},
    "↗️ Diagonal ↗":     {"sx": 0.0, "sy": 1.0, "ex": 1.0, "ey": 0.0},
}

# ── Emoji categories ───────────────────────────────────────────────────────────
EMOJI_CATEGORIES = {
    "😀 Faces":      list(range(1, 21)),
    "🤙 Gestures":   list(range(21, 41)),
    "❤️ Hearts":     list(range(41, 56)),
    "🎉 Celebrate":  list(range(56, 71)),
    "🐾 Animals":    list(range(71, 86)),
    "✨ Effects":    list(range(86, 103)),
}

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


class S(StatesGroup):
    select            = State()
    pick_ba           = State()
    custom_ba         = State()
    pick_ff           = State()
    custom_ff         = State()
    json_file         = State()
    text_input        = State()
    svg_file          = State()
    logo_c1_pick      = State()
    logo_c1_custom    = State()
    logo_c2_pick      = State()
    logo_c2_custom    = State()
    # gradient bg
    grad_bg_pick      = State()
    grad_bg_dir       = State()
    # gradient border
    grad_border_pick  = State()
    grad_border_dir   = State()
    scale             = State()
    confirm           = State()


# ── Lottie utils ───────────────────────────────────────────────────────────────
def hex_to_rgba(h: str) -> list:
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(c*2 for c in h)
    if len(h) != 6: raise ValueError
    return [int(h[i:i+2], 16)/255 for i in (0, 2, 4)] + [1.0]


def rgba_to_hex(rgba: list) -> str:
    return "".join(f"{int(v*255):02X}" for v in rgba[:3])


def rgba_close(a: list, b: list, tol: float = 0.06) -> bool:
    return all(abs(a[i] - b[i]) < tol for i in range(3))


def color_exists(obj, target: list) -> bool:
    if isinstance(obj, dict):
        ty = obj.get("ty")
        if ty in ("fl", "st"):
            k = obj.get("c", {}).get("k")
            if isinstance(k, list):
                if len(k) == 4 and isinstance(k[0], (int, float)):
                    if rgba_close(k, target): return True
                else:
                    for kf in k:
                        if isinstance(kf, dict):
                            for fld in ("s", "e"):
                                v = kf.get(fld)
                                if isinstance(v, list) and len(v) >= 3:
                                    if rgba_close(v, target): return True
        if ty in ("gf", "gs"):
            gk = obj.get("g", {}).get("k", {})
            kvals = gk.get("k") if isinstance(gk, dict) else gk
            if isinstance(kvals, list) and len(kvals) >= 4:
                for i in range(0, len(kvals) - 3, 4):
                    rgb = [kvals[i+1], kvals[i+2], kvals[i+3]]
                    if rgba_close(rgb + [1.0], target): return True
        for v in obj.values():
            if color_exists(v, target): return True
    elif isinstance(obj, list):
        for item in obj:
            if color_exists(item, target): return True
    return False


def replace_color_smart(obj, target: list, new: list, only_stroke: bool = False):
    if isinstance(obj, dict):
        ty = obj.get("ty")
        if ty in ("fl", "st"):
            if not (only_stroke and ty != "st"):
                k = obj.get("c", {}).get("k")
                if isinstance(k, list):
                    if len(k) == 4 and isinstance(k[0], (int, float)):
                        if rgba_close(k, target): obj["c"]["k"] = new
                    else:
                        for kf in k:
                            if isinstance(kf, dict):
                                for fld in ("s", "e"):
                                    v = kf.get(fld)
                                    if isinstance(v, list) and len(v) >= 3:
                                        if rgba_close(v, target): kf[fld] = new
        elif ty in ("gf", "gs"):
            if not only_stroke:
                gk = obj.get("g", {}).get("k", {})
                kvals = gk.get("k") if isinstance(gk, dict) else None
                if isinstance(kvals, list) and len(kvals) >= 4:
                    p = obj.get("g", {}).get("p", len(kvals) // 4)
                    for i in range(0, p * 4, 4):
                        if i + 3 < len(kvals):
                            rgb = [kvals[i+1], kvals[i+2], kvals[i+3]]
                            if rgba_close(rgb + [1.0], target):
                                kvals[i+1] = new[0]; kvals[i+2] = new[1]; kvals[i+3] = new[2]
        for v in obj.values():
            replace_color_smart(v, target, new, only_stroke)
    elif isinstance(obj, list):
        for item in obj:
            replace_color_smart(item, target, new, only_stroke)


def recolor_logo(obj, new: list):
    """Flat-recolor every fill/stroke in the logo. Skipped when logo_original=True."""
    if isinstance(obj, dict):
        ty = obj.get("ty")
        if ty in ("fl", "st"):
            k = obj.get("c", {}).get("k")
            if isinstance(k, list):
                if len(k) == 4 and isinstance(k[0], (int, float)):
                    obj["c"]["k"] = new
                else:
                    for kf in k:
                        if isinstance(kf, dict):
                            for fld in ("s", "e"):
                                if isinstance(kf.get(fld), list) and len(kf[fld]) >= 3:
                                    kf[fld] = new
        elif ty in ("gf", "gs"):
            gk = obj.get("g", {}).get("k", {})
            kvals = gk.get("k") if isinstance(gk, dict) else None
            if isinstance(kvals, list) and len(kvals) >= 4:
                p = obj.get("g", {}).get("p", len(kvals) // 4)
                for i in range(0, p * 4, 4):
                    if i + 3 < len(kvals):
                        kvals[i+1] = new[0]; kvals[i+2] = new[1]; kvals[i+3] = new[2]
        for v in obj.values(): recolor_logo(v, new)
    elif isinstance(obj, list):
        for i in obj: recolor_logo(i, new)


# ── Gradient layer builders ────────────────────────────────────────────────────
def _gradient_stops(c1: list, c2: list) -> list:
    """Build lottie gradient k-array: [pos,r,g,b, pos,r,g,b] for 2 stops."""
    return [0.0, c1[0], c1[1], c1[2],
            1.0, c2[0], c2[1], c2[2]]


def make_gradient_bg_layer(c1: list, c2: list, direction: dict, op: int = 180) -> dict:
    """
    Returns a Lottie shape-layer dict with a gradient-fill rectangle
    covering the full 512×512 canvas. Inserted at the BOTTOM of the layer stack.
    direction keys: sx, sy, ex, ey  (0-1 normalised, relative to 512px canvas)
    """
    W, H = 512, 512
    sx, sy = direction["sx"] * W, direction["sy"] * H
    ex, ey = direction["ex"] * W, direction["ey"] * H
    stops = _gradient_stops(c1, c2)
    return {
        "ddd": 0, "ty": 4, "nm": "GradientBG", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0, "ip": 0, "op": op, "st": 0, "bm": 0,
        "shapes": [
            {
                "ty": "gr", "nm": "BG Group",
                "it": [
                    {   # Rectangle shape
                        "ty": "rc", "nm": "Rect",
                        "p": {"a": 0, "k": [W/2, H/2]},
                        "s": {"a": 0, "k": [W, H]},
                        "r": {"a": 0, "k": 0},
                    },
                    {   # Gradient fill
                        "ty": "gf", "nm": "GradFill",
                        "o": {"a": 0, "k": 100},
                        "r": 1,   # 1 = linear
                        "g": {
                            "p": 2,
                            "k": {"a": 0, "k": stops},
                        },
                        "s": {"a": 0, "k": [sx, sy]},
                        "e": {"a": 0, "k": [ex, ey]},
                    },
                    {"ty": "tr", "o": {"a": 0, "k": 100}, "p": {"a": 0, "k": [0, 0]},
                     "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]},
                     "r": {"a": 0, "k": 0}, "sk": {"a": 0, "k": 0}, "sa": {"a": 0, "k": 0}},
                ],
            }
        ],
    }


def make_gradient_border_layer(c1: list, c2: list, direction: dict,
                                thickness: float = 14.0, op: int = 180) -> dict:
    """
    Returns a Lottie shape-layer dict with a rounded-rect gradient stroke
    acting as a border around the 512×512 canvas.
    """
    W, H = 512, 512
    inset = thickness / 2
    sx, sy = direction["sx"] * W, direction["sy"] * H
    ex, ey = direction["ex"] * W, direction["ey"] * H
    stops = _gradient_stops(c1, c2)
    return {
        "ddd": 0, "ty": 4, "nm": "GradientBorder", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 100}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]},
            "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [100, 100, 100]},
        },
        "ao": 0, "ip": 0, "op": op, "st": 0, "bm": 0,
        "shapes": [
            {
                "ty": "gr", "nm": "Border Group",
                "it": [
                    {   # Rounded rectangle inset by half stroke width
                        "ty": "rc", "nm": "BorderRect",
                        "p": {"a": 0, "k": [W/2, H/2]},
                        "s": {"a": 0, "k": [W - thickness, H - thickness]},
                        "r": {"a": 0, "k": 24},   # corner radius
                    },
                    {   # Gradient stroke
                        "ty": "gs", "nm": "GradStroke",
                        "o": {"a": 0, "k": 100},
                        "lc": 2, "lj": 2,         # round cap/join
                        "w": {"a": 0, "k": thickness},
                        "r": 1,
                        "g": {
                            "p": 2,
                            "k": {"a": 0, "k": stops},
                        },
                        "s": {"a": 0, "k": [sx, sy]},
                        "e": {"a": 0, "k": [ex, ey]},
                    },
                    {"ty": "tr", "o": {"a": 0, "k": 100}, "p": {"a": 0, "k": [0, 0]},
                     "a": {"a": 0, "k": [0, 0]}, "s": {"a": 0, "k": [100, 100]},
                     "r": {"a": 0, "k": 0}, "sk": {"a": 0, "k": 0}, "sa": {"a": 0, "k": 0}},
                ],
            }
        ],
    }


def make_text_layers(text: str, color: list) -> list:
    r, g, b, a = color
    n = len(text)
    fs = 200 if n<=3 else 170 if n<=4 else 140 if n<=6 else 110 if n<=8 else 85
    renderer = RawFontRenderer(DEFAULT_FONT)
    group_measure = renderer.render(text, fs, NVector(0, 0))
    bbox = group_measure.bounding_box()
    if bbox is not None:
        bx = bbox.x1 if hasattr(bbox, 'x1') else bbox[0]
        by = bbox.y1 if hasattr(bbox, 'y1') else bbox[1]
        bw = (bbox.x2 if hasattr(bbox, 'x2') else bbox[2]) - bx
        bh = (bbox.y2 if hasattr(bbox, 'y2') else bbox[3]) - by
        x_pos = 256 - bx - bw / 2
        y_pos = 256 - by - bh / 2
    else:
        x_pos = max(8, (512 - n * fs * 0.58) / 2)
        y_pos = 256 + fs * 0.35
    anim = objects.Animation()
    anim.width = 512; anim.height = 512
    anim.frame_rate = 60; anim.in_point = 0; anim.out_point = 180
    layer = objects.ShapeLayer(); anim.add_layer(layer)
    group = renderer.render(text, fs, NVector(x_pos, y_pos))
    fill = Fill(); fill.color.value = Color(r, g, b, a)
    group.add_shape(fill); layer.add_shape(group)
    src = anim.to_dict()
    layers = src.get("layers", [])
    for lyr in layers:
        ks = lyr.setdefault("ks", {})
        ks["a"] = {"a": 0, "k": [256, 256, 0]}
        ks["p"] = {"a": 0, "k": [256, 256, 0]}
        lyr["ip"] = 0; lyr["op"] = 180; lyr["st"] = 0
    return layers


def make_svg_layers(svg_bytes: bytes) -> list:
    from lottie.parsers.svg import parse_svg_file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        tmp.write(svg_bytes); tmp_path = tmp.name
    try: anim = parse_svg_file(tmp_path)
    finally: os.unlink(tmp_path)
    src = anim.to_dict()
    src_layers = src.get("layers", [])
    svg_w, svg_h = src.get("w") or 512, src.get("h") or 512
    scale_pct = min(512 / svg_w, 512 / svg_h) * 100
    new_layers = []
    for lyr in src_layers:
        l = copy.deepcopy(lyr)
        ks = l.setdefault("ks", {})
        ks["a"] = {"a": 0, "k": [svg_w/2, svg_h/2, 0]}
        ks["p"] = {"a": 0, "k": [256, 256, 0]}
        ks["s"] = {"a": 0, "k": [scale_pct, scale_pct, 100]}
        l["ip"] = 0; l["op"] = 180; l["st"] = 0
        new_layers.append(l)
    return new_layers


# ── Core animation builder ─────────────────────────────────────────────────────
def build_anim(anim_data: dict, logo_layers: list, extra_assets: list,
               scale: float,
               ba_color: list | None, ff_color: list | None,
               logo_c1: list | None, logo_c2: list | None,
               logo_original: bool,
               grad_bg: dict | None,       # {"c1":rgba, "c2":rgba, "dir":dict}
               grad_border: dict | None,   # {"c1":rgba, "c2":rgba, "dir":dict}
               file_num: int = 1) -> dict:

    out = copy.deepcopy(anim_data)
    t_ba    = hex_to_rgba(COLOR_BA)
    t_ff    = hex_to_rgba(COLOR_FF)
    t_new   = hex_to_rgba(COLOR_NEW)
    t_white = hex_to_rgba(COLOR_WHITE)

    has_special = (color_exists(out, t_ba)
                   or color_exists(out, t_ff)
                   or (file_num >= 67 and color_exists(out, t_new)))
    logo_color = logo_c1 if has_special else logo_c2

    # ── Inject logo ────────────────────────────────────────────────────────────
    logo_asset = next((a for a in out.get("assets", [])
                       if "LOGO" in (a.get("nm") or "").upper()
                       or (a.get("id") or "").upper() == LOGO_ID.upper()), None)
    if not logo_asset:
        out.setdefault("assets", []).append({"id": LOGO_ID, "layers": []})
        logo_asset = out["assets"][-1]
    logo_id = logo_asset.get("id")

    def collect_ref_timing(layers):
        result = []
        for lyr in layers:
            if lyr.get("refId") == logo_id:
                result.append({"ip": lyr.get("ip"), "op": lyr.get("op"),
                                "st": lyr.get("st"), "_ref": lyr})
            if "layers" in lyr:
                result.extend(collect_ref_timing(lyr["layers"]))
        return result

    all_logo_refs = collect_ref_timing(out.get("layers", []))
    for asset in out.get("assets", []):
        if "layers" in asset:
            all_logo_refs.extend(collect_ref_timing(asset["layers"]))

    prepared = copy.deepcopy(logo_layers)
    # Only recolor if user did NOT choose "Keep Original Colors"
    if not logo_original and logo_color:
        recolor_logo(prepared, logo_color)

    for i, lyr in enumerate(prepared):
        ks = lyr.setdefault("ks", {})
        ks["s"] = {"a": 0, "k": [scale, scale, 100]}
        lyr["ip"] = 0; lyr["op"] = 9999; lyr["st"] = 0
        lyr["ind"] = i + 1
        lyr["nm"] = f"Injected Logo {i+1}"

    logo_asset["ip"] = 0
    logo_asset["op"] = 9999
    logo_asset["layers"] = prepared

    for ref in all_logo_refs:
        lyr = ref["_ref"]
        if ref["ip"] is not None: lyr["ip"] = ref["ip"]
        if ref["op"] is not None: lyr["op"] = ref["op"]
        if ref["st"] is not None: lyr["st"] = ref["st"]

    if extra_assets:
        ex_ids = {a.get("id") for a in out["assets"]}
        for a in extra_assets:
            if a.get("id") not in ex_ids:
                out["assets"].append(copy.deepcopy(a))

    # ── Theme color replacement ────────────────────────────────────────────────
    if ba_color:
        replace_color_smart(out, t_ba, ba_color)
        replace_color_smart(out, t_white, ba_color, only_stroke=True)
    if ff_color:
        replace_color_smart(out, t_ff, ff_color)
        replace_color_smart(out, t_new, ff_color)

    # ── Gradient background (inserted at END = bottom of stack) ───────────────
    if grad_bg:
        op = out.get("op", 180)
        bg_layer = make_gradient_bg_layer(grad_bg["c1"], grad_bg["c2"], grad_bg["dir"], op)
        out.setdefault("layers", []).append(bg_layer)

    # ── Gradient border (inserted at START = top of stack) ────────────────────
    if grad_border:
        op = out.get("op", 180)
        border_layer = make_gradient_border_layer(
            grad_border["c1"], grad_border["c2"], grad_border["dir"], op=op)
        out.setdefault("layers", []).insert(0, border_layer)

    return out


def protect_json(d: dict) -> dict:
    fake_layer = {
        "ddd": 0, "ind": 999, "ty": 4, "nm": ".", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 0}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0,0,0]}, "a": {"a": 0, "k": [0,0,0]},
            "s": {"a": 0, "k": [0,0,0]}
        },
        "ao": 0, "sh\u0430\u0440es": [{"ty": "gr", "it": [], "nm": "."}],
        "ip": d.get("ip", 0), "op": d.get("op", 180), "st": 0, "bm": 0
    }
    if d.get("assets"):
        for a in d["assets"]:
            if isinstance(a.get("layers"), list):
                a["layers"].insert(0, copy.deepcopy(fake_layer))
    if isinstance(d.get("layers"), list):
        d["layers"].insert(0, copy.deepcopy(fake_layer))
    return d


def to_tgs(d: dict) -> bytes:
    buf = io.BytesIO()
    data = copy.deepcopy(d); data["tgs"] = 1
    protect_json(data)
    with gzip.open(buf, "wb") as gz:
        gz.write(json.dumps(data, separators=(",", ":")).encode())
    return buf.getvalue()


def get_001() -> dict | None:
    files = sorted(LOTTIES_DIR.glob("*.json"))
    if not files: return None
    with open(files[0], encoding="utf-8") as f: return json.load(f)


def progress_bar(done: int, total: int, width: int = 16) -> str:
    filled = int(width * done / total) if total else 0
    bar = "▓" * filled + "░" * (width - filled)
    pct = int(100 * done / total) if total else 0
    return f"[{bar}] {done}/{total} ({pct}%)"


def color_label(rgba: list | None, default: str = "no change") -> str:
    if rgba is None: return f"⬜ {default}"
    return f"#{rgba_to_hex(rgba)}"


def gradient_label(g: dict | None) -> str:
    if g is None: return "None"
    return f"#{rgba_to_hex(g['c1'])} → #{rgba_to_hex(g['c2'])}"


# ── Keyboards ──────────────────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🖼 JSON Logo",  callback_data="json"),
        InlineKeyboardButton(text="✏️ Text Logo",  callback_data="text"),
        InlineKeyboardButton(text="🎨 SVG Logo",   callback_data="svg"),
    ]])


def category_kb(selected_cats: set):
    total = len(sorted(LOTTIES_DIR.glob("*.json")))
    rows = []
    for cat in EMOJI_CATEGORIES:
        label = f"✅ {cat}" if cat in selected_cats else cat
        rows.append([InlineKeyboardButton(text=label, callback_data=f"cat:{cat}")])
    rows.append([
        InlineKeyboardButton(text=f"🎯 ALL ({total})", callback_data="cat:ALL"),
        InlineKeyboardButton(text="🗑 Clear",           callback_data="cat:CLEAR"),
    ])
    rows.append([InlineKeyboardButton(text="▶️ Continue →", callback_data="cat:DONE")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def color_picker_kb(field: str, allow_skip=True, allow_original=False):
    rows = []
    row = []
    for label, hex_val in PRESET_COLORS.items():
        row.append(InlineKeyboardButton(text=label, callback_data=f"color:{field}:{hex_val}"))
        if len(row) == 2:
            rows.append(row); row = []
    if row: rows.append(row)
    if allow_original:
        rows.append([InlineKeyboardButton(
            text="🌈 Keep Original Colors", callback_data=f"color:{field}:__original__")])
    if allow_skip:
        rows.append([InlineKeyboardButton(
            text="⏭ Skip (no change)", callback_data=f"color:{field}:skip")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def gradient_picker_kb(field: str):
    """Preset gradient selector for bg/border."""
    rows = []
    for name, val in PRESET_GRADIENTS.items():
        cb = f"grad:{field}:{name}"
        rows.append([InlineKeyboardButton(text=name, callback_data=cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def direction_kb(field: str):
    rows = []
    for label in GRADIENT_DIRS:
        rows.append([InlineKeyboardButton(text=label, callback_data=f"dir:{field}:{label}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scale_kb(current: float):
    steps = ["-20", "-10", "-5", "+5", "+10", "+20"]
    r1 = [InlineKeyboardButton(text=s, callback_data=f"scale:{s}") for s in steps[:3]]
    r2 = [InlineKeyboardButton(text=s, callback_data=f"scale:{s}") for s in steps[3:]]
    return InlineKeyboardMarkup(inline_keyboard=[
        r1, r2,
        [InlineKeyboardButton(text=f"🔍 Current: {current:.0f}%", callback_data="scale:noop")],
        [InlineKeyboardButton(text="✅ Looks Good → Confirm", callback_data="scale:DONE")],
    ])


def confirm_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Build Pack!", callback_data="confirm:yes")],
        [InlineKeyboardButton(text="🔄 Start Over",  callback_data="confirm:restart")],
    ])


def done_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎨 Make Another Pack", callback_data="restart")],
    ])


# ── Helpers ────────────────────────────────────────────────────────────────────
async def _send_or_edit(target, text, parse_mode="HTML", reply_markup=None):
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    else:
        await target.answer(text, parse_mode=parse_mode, reply_markup=reply_markup)


async def ask_color(target, state, field, prompt, next_state,
                    allow_skip=True, allow_original=False):
    kb = color_picker_kb(field, allow_skip=allow_skip, allow_original=allow_original)
    hint = "Pick a preset"
    if allow_original: hint += ", keep original 🌈"
    hint += ", or ✏️ Custom for a HEX code"
    await _send_or_edit(target, f"🎨 <b>{prompt}</b>\n<i>{hint}</i>",
                        reply_markup=kb)
    await state.set_state(next_state)


async def ask_gradient(target, state, field, prompt, next_state):
    await _send_or_edit(
        target,
        f"🌈 <b>{prompt}</b>\n<i>Pick a preset gradient or ⬛ None to skip</i>",
        reply_markup=gradient_picker_kb(field))
    await state.set_state(next_state)


# ── /start ─────────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    await state.clear()
    await msg.answer("👋 <b>Emoji Pack Builder</b>\n\nChoose how you want to add your logo:",
                     parse_mode="HTML", reply_markup=main_kb())


@dp.callback_query(F.data == "restart")
async def cb_restart(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await state.clear(); await call.answer()
    await call.message.edit_text(
        "👋 <b>Emoji Pack Builder</b>\n\nChoose how you want to add your logo:",
        parse_mode="HTML", reply_markup=main_kb())


# ── Logo type ──────────────────────────────────────────────────────────────────
@dp.callback_query(F.data.in_(["json", "text", "svg"]))
async def cb_type(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    await state.update_data(mode=call.data, selected_cats=[], selected=[],
                             logo_original=False,
                             grad_bg=None, grad_border=None)
    await call.message.edit_text(
        "📂 <b>Pick emoji categories</b>\n<i>Tap to toggle, then press Continue</i>",
        parse_mode="HTML", reply_markup=category_kb(set()))
    await state.set_state(S.select)


# ── Category selection ─────────────────────────────────────────────────────────
@dp.callback_query(S.select, F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    d = await state.get_data()
    selected_cats = set(d.get("selected_cats", []))
    action = call.data[4:]

    if action == "ALL":
        selected_cats = set(EMOJI_CATEGORIES.keys())
    elif action == "CLEAR":
        selected_cats = set()
    elif action == "DONE":
        if not selected_cats:
            await call.answer("⚠️ Select at least one category!", show_alert=True); return
        nums = sorted(set(n for cat in selected_cats for n in EMOJI_CATEGORIES.get(cat, [])))
        await state.update_data(selected_cats=list(selected_cats), selected=nums)
        total = len(nums)
        await ask_color(call, state, "ba",
                        f"Color 1 — replaces dark red (BA0047) & white strokes\n📦 {total} emojis selected",
                        S.pick_ba)
        return
    else:
        selected_cats ^= {action}   # toggle

    await state.update_data(selected_cats=list(selected_cats))
    count = sum(len(EMOJI_CATEGORIES[c]) for c in selected_cats)
    status = f"✅ <b>{count} emojis selected</b>" if count else "Nothing selected yet"
    await call.message.edit_text(
        f"📂 <b>Pick emoji categories</b>\n{status}\n<i>Tap to toggle, then press Continue</i>",
        parse_mode="HTML", reply_markup=category_kb(selected_cats))


# ── Generic color callback (handles all color:field:value patterns) ────────────
@dp.callback_query(F.data.startswith("color:"))
async def cb_color(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    parts = call.data.split(":", 2)
    field, value = parts[1], parts[2]

    if value == "__custom__":
        await call.message.edit_text(
            f"✏️ Type HEX color for <b>{field}</b>:\n<i>Example: FF5500</i>",
            parse_mode="HTML")
        await state.set_state({
            "ba": S.custom_ba, "ff": S.custom_ff,
            "lc1": S.logo_c1_custom, "lc2": S.logo_c2_custom,
        }.get(field, S.custom_ba))
        return

    if value == "__original__":
        await state.update_data(logo_original=True, logo_c1=None, logo_c2=None)
        await _after_logo_colors(call, state)
        return

    color = None if value == "skip" else hex_to_rgba(value)
    await _apply_color(call, state, field, color)


async def _apply_color(target, state, field, color):
    d = await state.get_data()
    if field == "ba":
        await state.update_data(ba_color=color)
        await ask_color(target, state, "ff",
                        "Color 2 — replaces accent red/blue (FF4A52 & 44BEF9)", S.pick_ff)
    elif field == "ff":
        await state.update_data(ff_color=color)
        mode = d.get("mode")
        if mode == "json":
            await _send_or_edit(target, "📁 Send your logo <b>.json</b> file:", reply_markup=None)
            await state.set_state(S.json_file)
        elif mode == "svg":
            await _send_or_edit(target, "🎨 Send your logo <b>.svg</b> file:", reply_markup=None)
            await state.set_state(S.svg_file)
        else:
            await _send_or_edit(target, "✏️ Type the text for your emoji logo:", reply_markup=None)
            await state.set_state(S.text_input)
    elif field == "lc1":
        await state.update_data(logo_c1=color)
        await ask_color(target, state, "lc2",
                        "Logo Color 2 — for emojis WITHOUT the special colors",
                        S.logo_c2_pick, allow_skip=True)
    elif field == "lc2":
        await state.update_data(logo_c2=color)
        await _after_logo_colors(target, state)


async def _after_logo_colors(target, state):
    """After logo colors are done → go to gradient background picker."""
    await ask_gradient(target, state, "bg",
                       "Gradient Background — pick a style for the emoji background",
                       S.grad_bg_pick)


# ── Custom HEX text input ──────────────────────────────────────────────────────
async def _handle_custom_hex(msg: Message, state: FSMContext, field: str):
    if msg.from_user.id != ALLOWED_USER: return
    try:
        color = hex_to_rgba(msg.text.strip())
    except:
        await msg.answer("⚠️ Invalid HEX. Try again (e.g. <code>FF5500</code>):",
                         parse_mode="HTML"); return
    key = {"ba": "ba_color", "ff": "ff_color", "lc1": "logo_c1", "lc2": "logo_c2"}[field]
    await state.update_data(**{key: color})
    await _apply_color(msg, state, field, color)

@dp.message(S.custom_ba)
async def custom_ba(msg, state): await _handle_custom_hex(msg, state, "ba")

@dp.message(S.custom_ff)
async def custom_ff(msg, state): await _handle_custom_hex(msg, state, "ff")

@dp.message(S.logo_c1_custom)
async def custom_lc1(msg, state): await _handle_custom_hex(msg, state, "lc1")

@dp.message(S.logo_c2_custom)
async def custom_lc2(msg, state): await _handle_custom_hex(msg, state, "lc2")


# ── File / text inputs ─────────────────────────────────────────────────────────
@dp.message(S.json_file, F.document)
async def got_json(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    if not (msg.document.file_name or "").endswith(".json"):
        await msg.answer("⚠️ Please send a .json file!"); return
    f = await bot.get_file(msg.document.file_id)
    buf = io.BytesIO()
    await bot.download_file(f.file_path, buf); buf.seek(0)
    data = json.load(buf)
    await state.update_data(layers=data.get("layers", []),
                             extra=[a for a in data.get("assets", []) if a.get("id") != LOGO_ID])
    await ask_color(msg, state, "lc1",
                    "Logo Color 1 — for emojis WITH the special colors",
                    S.logo_c1_pick, allow_skip=True, allow_original=True)


@dp.message(S.svg_file, F.document)
async def got_svg(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    if not (msg.document.file_name or "").lower().endswith(".svg"):
        await msg.answer("⚠️ Please send a .svg file!"); return
    f = await bot.get_file(msg.document.file_id)
    buf = io.BytesIO()
    await bot.download_file(f.file_path, buf); buf.seek(0)
    layers = await asyncio.get_running_loop().run_in_executor(
        None, lambda: make_svg_layers(buf.read()))
    await state.update_data(layers=layers, extra=[])
    await ask_color(msg, state, "lc1",
                    "Logo Color 1 — for emojis WITH the special colors",
                    S.logo_c1_pick, allow_skip=True, allow_original=True)


@dp.message(S.text_input)
async def got_text(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    await state.update_data(user_text=msg.text.strip(), layers=None, extra=[])
    await ask_color(msg, state, "lc1",
                    "Logo Color 1 — for emojis WITH the special colors",
                    S.logo_c1_pick, allow_skip=True)


# ── Gradient bg picker ─────────────────────────────────────────────────────────
@dp.callback_query(S.grad_bg_pick, F.data.startswith("grad:bg:"))
async def cb_grad_bg(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    name = call.data[len("grad:bg:"):]
    val = PRESET_GRADIENTS.get(name)
    if val == "__none__":
        await state.update_data(grad_bg=None)
        await _go_to_grad_border(call, state)
        return
    # Store gradient name + colors, then ask direction
    c1, c2 = hex_to_rgba(val[0]), hex_to_rgba(val[1])
    await state.update_data(_pending_grad={"name": name, "c1": c1, "c2": c2, "for": "bg"})
    await call.message.edit_text(
        f"↕️ <b>Background direction</b> — <i>{name}</i>\nWhich way should the gradient flow?",
        parse_mode="HTML", reply_markup=direction_kb("bg"))
    await state.set_state(S.grad_bg_dir)


@dp.callback_query(S.grad_bg_dir, F.data.startswith("dir:bg:"))
async def cb_grad_bg_dir(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    dir_label = call.data[len("dir:bg:"):]
    direction = GRADIENT_DIRS.get(dir_label, list(GRADIENT_DIRS.values())[0])
    d = await state.get_data()
    pg = d.get("_pending_grad", {})
    await state.update_data(grad_bg={"c1": pg["c1"], "c2": pg["c2"], "dir": direction})
    await _go_to_grad_border(call, state)


async def _go_to_grad_border(target, state):
    await ask_gradient(target, state, "border",
                       "Gradient Border — pick a style for the emoji border/stroke",
                       S.grad_border_pick)


# ── Gradient border picker ─────────────────────────────────────────────────────
@dp.callback_query(S.grad_border_pick, F.data.startswith("grad:border:"))
async def cb_grad_border(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    name = call.data[len("grad:border:"):]
    val = PRESET_GRADIENTS.get(name)
    if val == "__none__":
        await state.update_data(grad_border=None)
        await _go_to_scale(call, state)
        return
    c1, c2 = hex_to_rgba(val[0]), hex_to_rgba(val[1])
    await state.update_data(_pending_grad={"name": name, "c1": c1, "c2": c2, "for": "border"})
    await call.message.edit_text(
        f"↕️ <b>Border direction</b> — <i>{name}</i>\nWhich way should the gradient flow?",
        parse_mode="HTML", reply_markup=direction_kb("border"))
    await state.set_state(S.grad_border_dir)


@dp.callback_query(S.grad_border_dir, F.data.startswith("dir:border:"))
async def cb_grad_border_dir(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    dir_label = call.data[len("dir:border:"):]
    direction = GRADIENT_DIRS.get(dir_label, list(GRADIENT_DIRS.values())[0])
    d = await state.get_data()
    pg = d.get("_pending_grad", {})
    await state.update_data(grad_border={"c1": pg["c1"], "c2": pg["c2"], "dir": direction})
    await _go_to_scale(call, state)


# ── Scale / preview ────────────────────────────────────────────────────────────
async def _go_to_scale(target, state):
    await state.update_data(scale=100.0)
    d = await state.get_data()
    if d.get("layers") is None:
        c = d.get("logo_c1") or d.get("logo_c2") or hex_to_rgba("FFFFFF")
        layers = await asyncio.get_running_loop().run_in_executor(
            None, lambda: make_text_layers(d["user_text"], c))
        await state.update_data(layers=layers)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text("⏳ Generating preview…")
        ref_msg = target.message
    else:
        ref_msg = await target.answer("⏳ Generating preview…")
    await _send_preview(ref_msg, state)
    await state.set_state(S.scale)


async def _send_preview(msg: Message, state: FSMContext):
    d = await state.get_data()
    anim = get_001()
    if not anim:
        await msg.answer("❌ No lottie files found!"); return
    mod = build_anim(anim, d["layers"], d.get("extra", []), d.get("scale", 100.0),
                     d.get("ba_color"), d.get("ff_color"),
                     d.get("logo_c1"), d.get("logo_c2"),
                     d.get("logo_original", False),
                     d.get("grad_bg"), d.get("grad_border"), 1)
    scale = d.get("scale", 100.0)
    await msg.answer_document(
        BufferedInputFile(to_tgs(mod), filename="preview.tgs"),
        caption=(f"👁 <b>Preview</b> — Scale: <b>{scale:.0f}%</b>\n\n"
                 f"Adjust logo size, or confirm when ready:"),
        parse_mode="HTML", reply_markup=scale_kb(scale))


@dp.callback_query(S.scale, F.data.startswith("scale:"))
async def cb_scale(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    action = call.data[6:]
    if action == "noop":
        await call.answer(); return
    if action == "DONE":
        await call.answer("✅ Confirmed!")
        await _show_confirm(call.message, await state.get_data())
        await state.set_state(S.confirm); return
    d = await state.get_data()
    cur = d.get("scale", 100.0)
    try:
        new_s = cur + float(action) if action[0] in "+-" else float(action)
        new_s = max(10.0, min(200.0, new_s))
    except:
        await call.answer(); return
    await state.update_data(scale=new_s)
    await call.answer(f"Scale → {new_s:.0f}%")
    anim = get_001()
    if not anim: return
    mod = build_anim(anim, d["layers"], d.get("extra", []), new_s,
                     d.get("ba_color"), d.get("ff_color"),
                     d.get("logo_c1"), d.get("logo_c2"),
                     d.get("logo_original", False),
                     d.get("grad_bg"), d.get("grad_border"), 1)
    await call.message.answer_document(
        BufferedInputFile(to_tgs(mod), filename="preview.tgs"),
        caption=(f"👁 <b>Preview</b> — Scale: <b>{new_s:.0f}%</b>\n\n"
                 f"Adjust logo size, or confirm when ready:"),
        parse_mode="HTML", reply_markup=scale_kb(new_s))


# ── Confirm ────────────────────────────────────────────────────────────────────
async def _show_confirm(msg: Message, d: dict):
    cats  = d.get("selected_cats", [])
    total = len(d.get("selected", []))
    mode  = d.get("mode", "?")
    mode_labels = {"json": "🖼 JSON Logo", "text": "✏️ Text Logo", "svg": "🎨 SVG Logo"}
    logo_col = "🌈 Original" if d.get("logo_original") else \
               f"{color_label(d.get('logo_c1'))} / {color_label(d.get('logo_c2'))}"
    bg_info     = gradient_label(d.get("grad_bg"))
    border_info = gradient_label(d.get("grad_border"))

    text = (
        "📋 <b>Build Summary</b>\n\n"
        f"Logo type:       <code>{mode_labels.get(mode, mode)}</code>\n"
        f"Categories:      <code>{', '.join(cats) or 'All'}</code>\n"
        f"Emojis:          <code>{total}</code>\n"
        f"Scale:           <code>{d.get('scale', 100):.0f}%</code>\n\n"
        f"🎨 Color 1 (BA): <code>{color_label(d.get('ba_color'))}</code>\n"
        f"🎨 Color 2 (FF): <code>{color_label(d.get('ff_color'))}</code>\n"
        f"🎨 Logo colors:  <code>{logo_col}</code>\n\n"
        f"🌈 BG gradient:  <code>{bg_info}</code>\n"
        f"✨ Border grad:  <code>{border_info}</code>\n\n"
        "Ready to build?"
    )
    await msg.answer(text, parse_mode="HTML", reply_markup=confirm_kb())


@dp.callback_query(S.confirm, F.data.startswith("confirm:"))
async def cb_confirm(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    if call.data == "confirm:restart":
        await state.clear(); await call.answer()
        await call.message.edit_text(
            "👋 <b>Emoji Pack Builder</b>\n\nChoose how you want to add your logo:",
            parse_mode="HTML", reply_markup=main_kb()); return
    await call.answer("🚀 Building!")
    d = await state.get_data()
    await run_pack(call.message, d)
    await state.clear()


# ── Pack builder ───────────────────────────────────────────────────────────────
async def run_pack(msg: Message, d: dict):
    uid = msg.chat.id
    me  = await bot.get_me()
    name = f"pk{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}_by_{me.username}"

    selected_set = set(d.get("selected", []))
    files = [(fp, int(fp.stem)) for fp in sorted(LOTTIES_DIR.glob("*.json"))
             if fp.stem.isdigit() and int(fp.stem) in selected_set]

    total = len(files)
    if total == 0:
        await msg.answer("❌ No matching emoji files found."); return

    stat = await msg.answer(
        f"⚙️ <b>Building pack…</b>\n<code>{name}</code>\n\n"
        f"{progress_bar(0, total)}\n<i>Starting…</i>",
        parse_mode="HTML")

    created = False; ok = 0; errors = 0; last_edit = 0

    for i, (fp, n) in enumerate(files):
        try:
            with open(fp, encoding="utf-8") as f: anim = json.load(f)
            mod = build_anim(anim, d["layers"], d.get("extra", []),
                             d.get("scale", 100.0),
                             d.get("ba_color"), d.get("ff_color"),
                             d.get("logo_c1"), d.get("logo_c2"),
                             d.get("logo_original", False),
                             d.get("grad_bg"), d.get("grad_border"), n)
            sd = {"sticker": BufferedInputFile(to_tgs(mod), filename="s.tgs"),
                  "emoji_list": ["⭐️"], "format": "animated"}
            if not created:
                await bot.create_new_sticker_set(user_id=uid, name=name,
                                                  title=f"Pack {name[:5]}",
                                                  stickers=[sd], sticker_type="custom_emoji")
                created = True
            else:
                await bot.add_sticker_to_set(user_id=uid, name=name, sticker=sd)
            ok += 1
        except Exception as e:
            errors += 1
            logger.error(f"#{n} error: {e}")

        if ok + errors - last_edit >= 5 or i == 0 or i == total - 1:
            last_edit = ok + errors
            try:
                await stat.edit_text(
                    f"⚙️ <b>Building pack…</b>\n<code>{name}</code>\n\n"
                    f"{progress_bar(ok + errors, total)}\n"
                    f"✅ {ok} done" + (f"  ⚠️ {errors} errors" if errors else ""),
                    parse_mode="HTML")
            except: pass

        await asyncio.sleep(0.3)

    if created:
        await stat.edit_text(
            f"🎉 <b>Pack ready!</b>\n\n✅ <b>{ok}</b> emojis built"
            + (f"\n⚠️ {errors} had errors" if errors else "") +
            f"\n\n🔗 <a href='https://t.me/addemoji/{name}'>t.me/addemoji/{name}</a>",
            parse_mode="HTML", reply_markup=done_kb())
    else:
        await stat.edit_text("❌ Failed to create the pack. Check logs.")


async def main():
    logger.info(f"BASE_DIR   : {BASE_DIR}")
    logger.info(f"LOTTIES_DIR: {LOTTIES_DIR}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
