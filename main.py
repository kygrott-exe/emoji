"""
Animated Emoji Pack Bot
 
Flow:
1. /start → Select JSON, Text, or SVG
2. Ask new color for BA0047 #stroke color
3. Ask new color for FF4A52 #fill color
4. Send JSON file or text
5. Ask logo color 1 (for animations WITH BA0047/FF4A52) #skip
6. Ask logo color 2 (for animations WITHOUT BA0047/FF4A52) #skip
7. Scale preview (+/- or DONE)
8. Pack is created
"""
 
 
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
 
# FIX: correct usage of os.getenv — first argument must be the env var name
BOT_TOKEN    = os.getenv("8872778735:AAE8C1KkGrVDzxjEcJr3FXb-GcmNY0rcTIs", "8872778735:AAE8C1KkGrVDzxjEcJr3FXb-GcmNY0rcTIs")
LOTTIES_DIR  = Path("lotties")
LOGO_ID      = "mylogo"
COLOR_BA     = "BA0047"
COLOR_FF     = "FF4A52"
ALLOWED_USER = 7196302099 #ADMIN_ID
 
DEFAULT_FONT = str(Path(__file__).parent / "Anton-Regular.ttf")
 
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
 
 
# ── States ────────────────────────────────────────────────────────────────────
class S(StatesGroup):
    select     = State()  # Which animations (numbers or FULL)
    type       = State()  # Select JSON, Text, or SVG
    ask_ba     = State()  # Color for BA0047
    ask_ff     = State()  # Color for FF4A52
    json_file  = State()  # Waiting for JSON file
    text_input = State()  # Waiting for text
    svg_file   = State()  # Waiting for SVG file
    logo_c1    = State()  # Logo color 1 (animations WITH BA/FF)
    logo_c2    = State()  # Logo color 2 (animations WITHOUT BA/FF)
    scale      = State()  # Preview +/- or DONE
 
 
# ── Lottie utils ──────────────────────────────────────────────────────────────
def hex_to_rgba(h: str) -> list:
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(c*2 for c in h)
    if len(h) != 6: raise ValueError
    return [int(h[i:i+2], 16)/255 for i in (0, 2, 4)] + [1.0]
 
 
def rgba_close(a: list, b: list, tol: float = 0.06) -> bool:
    return all(abs(a[i] - b[i]) < tol for i in range(3))
 
 
def color_exists(obj, target: list) -> bool:
    """Recursively checks if the target color exists in the Lottie JSON."""
    if isinstance(obj, dict):
        if obj.get("ty") in ("fl", "st"):
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
        for v in obj.values():
            if color_exists(v, target): return True
    elif isinstance(obj, list):
        for item in obj:
            if color_exists(item, target): return True
    return False
 
 
def replace_color(obj, target: list, new: list):
    """Replaces target color with new color (in both fl and st)."""
    if isinstance(obj, dict):
        if obj.get("ty") in ("fl", "st"):
            k = obj.get("c", {}).get("k")
            if isinstance(k, list):
                if len(k) == 4 and isinstance(k[0], (int, float)):
                    if rgba_close(k, target):
                        obj["c"]["k"] = new
                else:
                    for kf in k:
                        if isinstance(kf, dict):
                            for fld in ("s", "e"):
                                v = kf.get(fld)
                                if isinstance(v, list) and len(v) >= 3:
                                    if rgba_close(v, target):
                                        kf[fld] = new
        for v in obj.values(): replace_color(v, target, new)
    elif isinstance(obj, list):
        for item in obj: replace_color(item, target, new)
 
 
def recolor_logo(obj, new: list):
    """Replaces all fl/st colors inside the mylogo asset."""
    if isinstance(obj, dict):
        if obj.get("ty") in ("fl", "st"):
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
        for v in obj.values(): recolor_logo(v, new)
    elif isinstance(obj, list):
        for i in obj: recolor_logo(i, new)
 
 
def make_text_layers(text: str, color: list) -> list:
    r, g, b, a = color
    n = len(text)
    fs = 200 if n<=3 else 170 if n<=4 else 140 if n<=6 else 110 if n<=8 else 85
 
    renderer = RawFontRenderer(DEFAULT_FONT)
 
    # 1. First render at [0, 0] to measure bounding box
    group_measure = renderer.render(text, fs, NVector(0, 0))
    bbox = group_measure.bounding_box()   # lottie BoundingBox: x1,y1,x2,y2
 
    if bbox is not None:
        bx = bbox.x1 if hasattr(bbox, 'x1') else bbox[0]
        by = bbox.y1 if hasattr(bbox, 'y1') else bbox[1]
        bw = (bbox.x2 if hasattr(bbox, 'x2') else bbox[2]) - bx
        bh = (bbox.y2 if hasattr(bbox, 'y2') else bbox[3]) - by
        # Offset to center
        x_pos = 256 - bx - bw / 2
        y_pos = 256 - by - bh / 2
    else:
        # Fallback
        x_pos = max(8, (512 - n * fs * 0.58) / 2)
        y_pos = 256 + fs * 0.35
 
    anim = objects.Animation()
    anim.width = 512; anim.height = 512
    anim.frame_rate = 60; anim.in_point = 0; anim.out_point = 180 # FIX: Telegram 3s limit
    layer = objects.ShapeLayer(); anim.add_layer(layer)
 
    group = renderer.render(text, fs, NVector(x_pos, y_pos))
    fill = Fill(); fill.color.value = Color(r, g, b, a)
    group.add_shape(fill); layer.add_shape(group)
 
    src = anim.to_dict()
    layers = src.get("layers", [])
 
    # Set Anchor Point and Position to the center of the composition
    for lyr in layers:
        ks = lyr.setdefault("ks", {})
        ks["a"] = {"a": 0, "k": [256, 256, 0]}
        ks["p"] = {"a": 0, "k": [256, 256, 0]}
        lyr["ip"] = 0
        lyr["op"] = 180
        lyr["st"] = 0
    return layers
 
 
def make_svg_layers(svg_bytes: bytes) -> list:
    """Converts an SVG file to Lottie layers, centered and fit-scaled."""
    from lottie.parsers.svg import parse_svg_file
    import tempfile
 
    # Write SVG to a temp file and parse it
    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tmp:
        tmp.write(svg_bytes)
        tmp_path = tmp.name
    try:
        anim = parse_svg_file(tmp_path)
    finally:
        os.unlink(tmp_path)
 
    src = anim.to_dict()
    src_layers = src.get("layers", [])
    svg_w = src.get("w") or 512
    svg_h = src.get("h") or 512
    
    comp_w, comp_h = 512, 512
    cx, cy = comp_w / 2, comp_h / 2
 
    # Fit SVG fully into the composition (preserves aspect ratio)
    scale_pct = min(comp_w / svg_w, comp_h / svg_h) * 100
 
    new_layers = []
    for lyr in src_layers:
        l = copy.deepcopy(lyr)
        ks = l.setdefault("ks", {})
        # Anchor: SVG centered at its own origin (shapes drawn from [0,0])
        ks["a"] = {"a": 0, "k": [svg_w / 2, svg_h / 2, 0]}
        # Position: center of the composition
        ks["p"] = {"a": 0, "k": [cx, cy, 0]}
        # Scale: fit
        ks["s"] = {"a": 0, "k": [scale_pct, scale_pct, 100]}
        # FIX: ip/op/st — sync to Telegram limits
        l["ip"] = 0
        l["op"] = 180
        l["st"] = 0
        new_layers.append(l)
    return new_layers
 
 
def build_anim(anim_data: dict, logo_layers: list, extra_assets: list,
               scale: float,
               ba_color: list | None, ff_color: list | None,
               logo_c1: list | None, logo_c2: list | None) -> dict:
    """
    ba_color: replacement color for BA0047
    ff_color: replacement color for FF4A52
    logo_c1:  logo color for animations that CONTAIN BA0047/FF4A52
    logo_c2:  logo color for animations that DO NOT contain BA0047/FF4A52
    """
    out = copy.deepcopy(anim_data)
 
    # Actual frame range of the animation
    orig_ip = out.get("ip", 0)
    orig_op = out.get("op", 180)
 
    # 1. Update/Identify logo assets
    logo_asset_ids = set()
    for asset in out.get("assets", []):
        nm = (asset.get("nm") or "").upper()
        aid = (asset.get("id") or "").upper()
        if "LOGO" in nm or "LOGO" in aid or aid == LOGO_ID.upper():
            logo_asset_ids.add(asset.get("id"))
 
    # 2. Check if BA0047/FF4A52 colors are present
    t_ba = hex_to_rgba(COLOR_BA)
    t_ff = hex_to_rgba(COLOR_FF)
    has_special = color_exists(out, t_ba) or color_exists(out, t_ff)
 
    # 3. Logo color selection
    logo_color = logo_c1 if has_special else logo_c2
 
    # 4. Prepare logo layers for asset
    COMP_W = out.get("w", 512)
    COMP_H = out.get("h", 512)
    cx, cy = COMP_W / 2, COMP_H / 2
 
    prepared_logo_layers = []
    for i, lyr in enumerate(copy.deepcopy(logo_layers)):
        ks = lyr.setdefault("ks", {})
        ks["a"] = {"a": 0, "k": [cx, cy, 0]}
        ks["p"] = {"a": 0, "k": [cx, cy, 0]}
        ks["s"] = {"a": 0, "k": [scale, scale, 100]}
        lyr["ip"] = 0
        lyr["op"] = 500 # High enough for asset
        lyr["st"] = 0
        lyr["ind"] = i + 1
        prepared_logo_layers.append(lyr)
    
    if logo_color:
        recolor_logo(prepared_logo_layers, logo_color)
 
    # 5. Inject logo into identified assets
    for asset in out.get("assets", []):
        if asset.get("id") in logo_asset_ids:
            asset["layers"] = copy.deepcopy(prepared_logo_layers)
 
    # 6. Recursive timing fix (Fixes 1-second delay / disappearance)
    def fix_layers_recursive(layers):
        for lyr in layers:
            is_logo_ref = lyr.get("ty") == 0 and lyr.get("refId") in logo_asset_ids
            is_logo_name = "LOGO" in (lyr.get("nm") or "").upper()
            
            if is_logo_ref or is_logo_name:
                # FIX: ip must be 0 to show asset from start, st must match animation start
                lyr["ip"] = 0
                lyr["op"] = 500
                if lyr.get("st", 0) != orig_ip:
                    lyr["st"] = orig_ip
 
            if "layers" in lyr:
                fix_layers_recursive(lyr["layers"])
 
    fix_layers_recursive(out.get("layers", []))
    for asset in out.get("assets", []):
        if "layers" in asset:
            fix_layers_recursive(asset["layers"])
 
    # 7. Extra assets
    if extra_assets:
        ex_ids = {a.get("id") for a in out["assets"]}
        for a in extra_assets:
            if a.get("id") not in ex_ids:
                out["assets"].append(copy.deepcopy(a))
 
    # 8. Replace BA0047 and FF4A52 colors
    if ba_color: replace_color(out, t_ba, ba_color)
    if ff_color: replace_color(out, t_ff, ff_color)
 
    return out
 
 
def protect_json(d: dict) -> dict:
    """Adds invisible fake layer for protection."""
    fake_layer = {
        "ddd": 0, "ind": 999, "ty": 4, "nm": ".", "sr": 1,
        "ks": {
            "o": {"a": 0, "k": 0}, "r": {"a": 0, "k": 0},
            "p": {"a": 0, "k": [0, 0, 0]}, "a": {"a": 0, "k": [0, 0, 0]},
            "s": {"a": 0, "k": [0, 0, 0]}
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
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)
 
 
# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🖼 JSON (Logo)", callback_data="json"),
        InlineKeyboardButton(text="✏️ Text",        callback_data="text"),
        InlineKeyboardButton(text="🎨 SVG",         callback_data="svg"),
    ]])
 
 
def select_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎯 FULL (67 items)", callback_data="full"),
    ]])
 
 
def parse_indices(text: str) -> list[int] | None:
    parts = text.replace(",", ".").replace(" ", ".").split(".")
    result = []
    for p in parts:
        p = p.strip()
        if not p: continue
        try:
            n = int(p)
            if n < 1 or n > 67: return None
            result.append(n)
        except ValueError: return None
    return sorted(set(result)) if result else None
 
 
# ── Handlers ──────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    await state.clear()
    await msg.answer("Select animation type:", reply_markup=main_kb())
 
 
@dp.callback_query(F.data.in_(["json", "text", "svg"]))
async def cb_type(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    await state.update_data(mode=call.data)
    await call.message.edit_text("Which animations to modify?", reply_markup=select_kb())
    await state.set_state(S.select)
 
 
@dp.callback_query(S.select, F.data == "full")
async def cb_select_full(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ALLOWED_USER: return
    await call.answer()
    await state.update_data(selected=list(range(1, 67)))
    await call.message.edit_text(f"🎨 Enter color for <b>BA0047</b>:\n<i>skip → no change</i>", parse_mode="HTML")
    await state.set_state(S.ask_ba)
 
 
@dp.message(S.select)
async def select_indices(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    indices = parse_indices(msg.text)
    if indices is None:
        await msg.answer("⚠️ Invalid format. Example: <code>1.9.43.54</code>", parse_mode="HTML")
        return
    await state.update_data(selected=indices)
    await msg.answer(f"🎨 Enter color for <b>BA0047</b>:\n<i>skip → no change</i>", parse_mode="HTML")
    await state.set_state(S.ask_ba)
 
 
@dp.message(S.ask_ba)
async def got_ba(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    t = msg.text.strip(); color = None
    if t.lower() != "skip":
        try: color = hex_to_rgba(t)
        except:
            await msg.answer("⚠️ Invalid HEX or <code>skip</code>", parse_mode="HTML")
            return
    await state.update_data(ba_color=color)
    await msg.answer(f"🎨 Enter color for <b>FF4A52</b>:\n<i>skip → no change</i>", parse_mode="HTML")
    await state.set_state(S.ask_ff)
 
 
@dp.message(S.ask_ff)
async def got_ff(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    t = msg.text.strip(); color = None
    if t.lower() != "skip":
        try: color = hex_to_rgba(t)
        except:
            await msg.answer("⚠️ Invalid HEX or <code>skip</code>", parse_mode="HTML")
            return
    await state.update_data(ff_color=color)
    d = await state.get_data()
    if d["mode"] == "json":
        await msg.answer("📁 Send logo <b>.json</b> file:", parse_mode="HTML")
        await state.set_state(S.json_file)
    elif d["mode"] == "svg":
        await msg.answer("🎨 Send logo <b>.svg</b> file:", parse_mode="HTML")
        await state.set_state(S.svg_file)
    else:
        await msg.answer("✏️ Enter emoji text:\n<i>Example: KXALIL</i>", parse_mode="HTML")
        await state.set_state(S.text_input)
 
 
@dp.message(S.json_file, F.document)
async def got_json(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    if not (msg.document.file_name or "").endswith(".json"):
        await msg.answer("⚠️ Only <b>.json</b> files!", parse_mode="HTML"); return
    try:
        f = await bot.get_file(msg.document.file_id)
        buf = io.BytesIO(); await bot.download_file(f.file_path, buf); buf.seek(0)
        data = json.load(buf)
    except Exception as e:
        await msg.answer(f"❌ JSON error: <code>{e}</code>", parse_mode="HTML"); return
    layers = data.get("layers", [])
    extra  = [a for a in data.get("assets", []) if a.get("id") != LOGO_ID]
    await state.update_data(layers=layers, extra=extra)
    await ask_logo_c1(msg, state)
 
 
@dp.message(S.svg_file, F.document)
async def got_svg(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    try:
        f = await bot.get_file(msg.document.file_id)
        buf = io.BytesIO(); await bot.download_file(f.file_path, buf); buf.seek(0)
        layers = await asyncio.get_running_loop().run_in_executor(None, lambda: make_svg_layers(buf.read()))
    except Exception as e:
        await msg.answer(f"❌ File error: <code>{e}</code>", parse_mode="HTML"); return
    await state.update_data(layers=layers, extra=[])
    await ask_logo_c1(msg, state)
 
 
@dp.message(S.text_input)
async def got_text(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    await state.update_data(user_text=msg.text.strip(), layers=None, extra=[])
    await ask_logo_c1(msg, state)
 
 
async def ask_logo_c1(msg: Message, state: FSMContext):
    await msg.answer(f"🎨 Enter <b>Logo Color 1</b>:\n<i>For animations WITH special colors\nskip → no change</i>", parse_mode="HTML")
    await state.set_state(S.logo_c1)
 
 
@dp.message(S.logo_c1)
async def got_logo_c1(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    t = msg.text.strip(); color = None
    if t.lower() != "skip":
        try: color = hex_to_rgba(t)
        except:
            await msg.answer("⚠️ Invalid HEX", parse_mode="HTML")
            return
    await state.update_data(logo_c1=color)
    await msg.answer(f"🎨 Enter <b>Logo Color 2</b>:\n<i>For animations WITHOUT special colors\nskip → no change</i>", parse_mode="HTML")
    await state.set_state(S.logo_c2)
 
 
@dp.message(S.logo_c2)
async def got_logo_c2(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    t = msg.text.strip(); color = None
    if t.lower() != "skip":
        try: color = hex_to_rgba(t)
        except:
            await msg.answer("⚠️ Invalid HEX", parse_mode="HTML")
            return
    await state.update_data(logo_c2=color)
    d = await state.get_data()
    if d.get("layers") is None:
        logo_c1 = d.get("logo_c1") or color or hex_to_rgba("FFFFFF")
        layers = await asyncio.get_running_loop().run_in_executor(None, lambda: make_text_layers(d["user_text"], logo_c1))
        await state.update_data(layers=layers)
    await state.update_data(scale=100.0)
    await send_preview(msg, state)
    await state.set_state(S.scale)
 
 
async def send_preview(msg: Message, state: FSMContext):
    d = await state.get_data()
    anim = get_001()
    if not anim:
        await msg.answer("❌ JSON not found!"); return
    modified = build_anim(anim, d["layers"], d.get("extra", []), d.get("scale", 100.0), d.get("ba_color"), d.get("ff_color"), d.get("logo_c1"), d.get("logo_c2"))
    await msg.answer_document(BufferedInputFile(to_tgs(modified), filename="preview.tgs"), caption=f"👆 <b>Preview</b> — scale: <b>{d.get('scale', 100.0):g}%</b>\n\n✏️ Change: <code>+10</code>, <code>-5</code>, <code>120</code>\n✅ Confirm: <code>DONE</code>", parse_mode="HTML")
 
 
@dp.message(S.scale)
async def scale_input(msg: Message, state: FSMContext):
    if msg.from_user.id != ALLOWED_USER: return
    t = msg.text.strip()
    if t.upper() == "DONE":
        d = await state.get_data(); await run_pack(msg, d); await state.clear(); return
    d = await state.get_data(); cur = d.get("scale", 100.0)
    try:
        if t.startswith("+"): new_s = cur + float(t[1:])
        elif t.startswith("-"): new_s = cur - float(t[1:])
        else: new_s = float(t)
    except:
        await msg.answer("⚠️ Error"); return
    await state.update_data(scale=new_s); await send_preview(msg, state)
 
 
async def run_pack(msg: Message, d: dict):
    uid, me = msg.from_user.id, await bot.get_me()
    suf = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    name, titl = f"pk{suf}_by_{me.username}", f"Pack {suf.upper()}"
    stat = await msg.answer(f"⚙️ Processing..."); all_files = sorted(LOTTIES_DIR.glob("*.json"))
    selected = set(d.get("selected", list(range(1, 66))))
    files = [fp for fp in all_files if fp.stem.isdigit() and int(fp.stem) in selected]
    created, ok = False, 0
    for i, fp in enumerate(files):
        try:
            with open(fp, encoding="utf-8") as f: anim = json.load(f)
            modified = build_anim(anim, d["layers"], d.get("extra", []), d.get("scale", 100.0), d.get("ba_color"), d.get("ff_color"), d.get("logo_c1"), d.get("logo_c2"))
            sd = {"sticker": BufferedInputFile(to_tgs(modified), filename=f"e{i+1:03d}.tgs"), "emoji_list": ["⭐️"], "format": "animated"}
            if not created:
                await bot.create_new_sticker_set(user_id=uid, name=name, title=titl, stickers=[sd], sticker_type="custom_emoji")
                created = True
            else: await bot.add_sticker_to_set(user_id=uid, name=name, sticker=sd)
            ok += 1
            if (i + 1) % 10 == 0: await stat.edit_text(f"⚙️ {i+1}/{len(files)} ✅")
            await asyncio.sleep(0.1)
        except Exception as e: logger.error(f"{fp.name}: {e}")
    if created: await stat.edit_text(f"✅ <b>Done!</b>\n🔗 https://t.me/addemoji/{name}", parse_mode="HTML")
    else: await stat.edit_text("❌ Error.")
 
 
async def main():
    await dp.start_polling(bot)
 
if __name__ == "__main__":
    asyncio.run(main())
