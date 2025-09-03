#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Version 4.2.2 (core + w9bp) — Visual recreation of W-9 (Rev. 3-2024) with QA/SEC options.

New in v4.2.2:
- --w9bp: "W-9 bypass" mode that ONLY performs metadata + (optional) watermarking on the PDF.
  * No overlay drawing, so existing form fields/annotations are preserved unless --flatten is used.
  * --fontwarp / --fontwarp-aggressive are ignored in this mode.

Recent fixes/features preserved from v4.2.1:
- Corrected call to compose_watermark_page() for pages 2..N.
- Cleanup of temporary PNGs generated in aggressive mode.
- --clean removes temp PDFs (overlay + watermark layer pages).
- Auto output name when --output omitted: {YYYY-MM-DD-HHMMSS}.pdf
"""

import argparse, os, re, random, json, tempfile
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, List, Optional

from PyPDF2 import PdfReader, PdfWriter
from PyPDF2.generic import (
    IndirectObject, NameObject, DecodedStreamObject, DictionaryObject
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader

from PIL import Image, ImageDraw, ImageFont

FONT_MAIN = "Helvetica"
FONT_BOLD  = "Helvetica-Bold"
CHECK_GLYPH = "✓"  # or "X"

# -------------------- tolerant JSON loader --------------------

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            import json5
            return json5.loads(raw)
        except Exception:
            pass
        txt = raw.lstrip("\ufeff")
        txt = re.sub(r"//.*?$|/\*.*?\*/", "", txt, flags=re.M | re.S)
        txt = re.sub(r",\s*(?=[}\]])", "", txt)
        txt = re.sub(r'(?P<prefix>[{,]\s*)(?P<key>[A-Za-z_][A-Za-z0-9_\-]*)\s*:',
                     r'\g<prefix>"\g<key>":', txt)
        return json.loads(txt)

# -------------------- misc helpers --------------------

def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def now_iso_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def pdf_date_now() -> str:
    return datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")

def norm(s: Any) -> str:
    return (s or "").strip()

def split_ssn(ssn: str) -> Tuple[str, str, str]:
    digits = re.sub(r"\D", "", ssn or "")
    if len(digits) == 9:
        return digits[:3], digits[3:5], digits[5:]
    return "", "", ""

def split_ein(ein: str) -> Tuple[str, str]:
    digits = re.sub(r"\D", "", ein or "")
    if len(digits) == 9:
        return digits[:2], digits[2:]
    return "", ""

def get_page_size(reader: PdfReader, page_index: int) -> Tuple[float, float]:
    mb = reader.pages[page_index].mediabox
    try:
        return float(mb.width), float(mb.height)
    except Exception:
        return letter

def get_page_widgets(reader: PdfReader, page_index: int) -> List[Dict[str, Any]]:
    p = reader.pages[page_index]
    annots = p.get("/Annots")
    if isinstance(annots, IndirectObject):
        annots = annots.get_object()
    widgets = []
    if not annots:
        return widgets
    for a in annots:
        an = a.get_object()
        name = str(an.get("/T"))
        rect = list(map(float, an.get("/Rect")))
        ftype = str(an.get("/FT"))
        widgets.append({"name": name, "type": ftype, "rect": rect})
    return widgets

def rect_center(rect: List[float]) -> Tuple[float, float]:
    x0, y0, x1, y1 = rect
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0

# -------------------- font helpers --------------------

def register_fonts_for_overlay() -> Tuple[str, List[str], str]:
    bold_font = FONT_BOLD
    warp_fonts: List[str] = []
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("WarpA", "DejaVuSans.ttf"))
        pdfmetrics.registerFont(TTFont("WarpB", "DejaVuSans.ttf"))
        warp_fonts = ["DejaVuSans", "WarpA", "WarpB"]
        return "DejaVuSans", warp_fonts, bold_font
    except Exception:
        warp_fonts = ["Helvetica", "Courier", "Times-Roman"]
        return "Helvetica", warp_fonts, "Helvetica-Bold"

class FontCycler:
    def __init__(self, fonts: List[str]):
        self.fonts = fonts or [FONT_MAIN]
        self.i = 0
    def next(self) -> str:
        f = self.fonts[self.i % len(self.fonts)]
        self.i += 1
        return f

# -------------------- raster text helpers (aggressive mode) --------------------

def _pil_try_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()

def _tmp_png_path() -> str:
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    path = f.name
    f.close()
    return path

def _save_png(img: Image.Image) -> str:
    path = _tmp_png_path()
    img.save(path, "PNG")
    return path

def _draw_singleline_to_png(text: str, w_pt: float, h_pt: float,
                            font_px: int, align: str = "left",
                            vcenter: bool = True, scale: int = 3) -> str:
    W = max(1, int(w_pt * scale)); H = max(1, int(h_pt * scale))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _pil_try_font(max(6, int(font_px * scale / 0.75)))
    text = norm(text)
    if text:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = 0 if align == "left" else (W - tw) // 2 if align == "center" else max(0, W - tw - 1)
        y = (H - th) // 2 if vcenter else 1
        draw.text((x, y), text, fill=(0, 0, 0, 255), font=font)
    return _save_png(img)

def _wrap_lines(draw, text: str, font, max_w: int) -> List[str]:
    lines = []
    for raw in (text or "").splitlines():
        words = raw.split(" ")
        cur = ""
        for w in words:
            trial = (cur + " " + w).strip()
            tw = draw.textlength(trial, font=font)
            if tw <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur); cur = w
        if cur: lines.append(cur)
    return lines

def _draw_multiline_to_png(text: str, w_pt: float, h_pt: float,
                           font_px: int, leading: float = 1.2,
                           scale: int = 3) -> str:
    W = max(1, int(w_pt * scale)); H = max(1, int(h_pt * scale))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _pil_try_font(max(6, int(font_px * scale / 0.75)))
    max_w = W - 6
    lines = _wrap_lines(draw, norm(text), font, max_w)
    ascent, descent = font.getmetrics()
    lh = int((ascent + descent) * leading)
    y = 2
    for ln in lines:
        draw.text((3, y), ln, fill=(0, 0, 0, 255), font=font)
        y += lh
        if y > H - lh:
            break
    return _save_png(img)

def _draw_digits_grid_to_png(digits: str, w_pt: float, h_pt: float,
                             slots: int, font_px: int, scale: int = 3) -> str:
    W = max(1, int(w_pt * scale)); H = max(1, int(h_pt * scale))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = _pil_try_font(max(6, int(font_px * scale / 0.75)))
    digits = re.sub(r"\D", "", digits or "")
    inset = int(2 * scale)
    cell_w = (W - 2 * inset) / float(slots)
    y = (H) // 2
    for i, ch in enumerate(digits[:slots]):
        cx = int(inset + cell_w * (i + 0.5))
        tw, th = draw.textbbox((0, 0), ch, font=font)[2:]
        draw.text((cx - tw // 2, y - th // 2), ch, fill=(0, 0, 0, 255), font=font)
    return _save_png(img)

def draw_image_into_canvas(c: canvas.Canvas, png_path: str, rect: List[float]):
    if not rect: return
    x0, y0, x1, y1 = rect
    w = max(1, x1 - x0); h = max(1, y1 - y0)
    c.drawImage(ImageReader(png_path), x0, y0, width=w, height=h, mask='auto')

# -------------------- vector drawing helpers --------------------

def draw_text_fit_vec(c: canvas.Canvas, text: str, rect: List[float], font="Helvetica",
                      max_size=10.5, min_size=7.0, inset=2.0, vcenter=True):
    text = norm(text)
    if not text or not rect: return
    x0, y0, x1, y1 = rect
    w = x1 - x0 - 2 * inset
    size = max_size
    while size >= min_size and stringWidth(text, font, size) > w:
        size -= 0.2
    size = max(size, min_size)
    y = y0 + (y1 - y0 - size) / 2.0 + 0.5 if vcenter else (y0 + inset)
    c.setFont(font, size)
    c.drawString(x0 + inset, y, text)

def draw_multiline_fit_vec(c: canvas.Canvas, text: str, rect: List[float], font="Helvetica",
                           max_size=9.5, min_size=7.5, inset=2.0, leading=1.2):
    text = norm(text)
    if not text or not rect: return
    x0, y0, x1, y1 = rect
    max_w = x1 - x0 - 2 * inset
    size = max_size
    while size >= min_size:
        lines = []
        for raw in text.splitlines():
            words = raw.split(" ")
            cur = ""
            for w in words:
                trial = (cur + " " + w).strip()
                if stringWidth(trial, font, size) <= max_w:
                    cur = trial
                else:
                    if cur: lines.append(cur)
                    cur = w
            if cur: lines.append(cur)
        line_h = size * leading
        if len(lines) * line_h <= (y1 - y0 - 2 * inset):
            break
        size -= 0.2
    c.setFont(font, size)
    line_h = size * leading
    y = y1 - inset - size
    for ln in lines:
        c.drawString(x0 + inset, y, ln)
        y -= line_h
        if y < y0 + inset:
            break

def draw_check_vec(c: canvas.Canvas, rect: List[float], glyph=CHECK_GLYPH, size=9.5, font="Helvetica-Bold"):
    if not rect: return
    cx, cy = rect_center(rect)
    c.setFont(font, size)
    c.drawCentredString(cx, cy - size / 3.3, glyph)

def draw_digits_in_cells_vec(c: canvas.Canvas, text: str, rect: List[float], slots: int,
                             font="Helvetica", max_size=12, inset=2.0):
    digits = re.sub(r"\D", "", text or "")
    if not digits or not rect: return
    x0, y0, x1, y1 = rect
    cell_w = (x1 - x0 - 2 * inset) / float(slots)
    size = max_size
    while size > 6.5 and stringWidth("8", font, size) > (cell_w - 1.0):
        size -= 0.2
    y = y0 + (y1 - y0 - size) / 2.0 + 0.5
    c.setFont(font, size)
    for i, ch in enumerate(digits[:slots]):
        cx = x0 + inset + cell_w * (i + 0.5)
        c.drawCentredString(cx, y, ch)

# -------------------- metadata helpers --------------------

def read_template_info(reader: PdfReader) -> Dict[str, str]:
    info = {}
    try:
        meta = reader.metadata or {}
        for k, v in dict(meta).items():
            if isinstance(k, str) and k.startswith("/"):
                info[k] = "" if v is None else str(v)
    except Exception:
        pass
    return info

def build_metadata_dict(user_meta_raw: Dict[str, Any]) -> Dict[str, str]:
    if not user_meta_raw:
        return {}
    out = {}
    mapping = {
        "title": "/Title", "author": "/Author", "subject": "/Subject",
        "keywords": "/Keywords", "creator": "/Creator", "producer": "/Producer",
    }
    for k, v in user_meta_raw.items():
        if k == "custom" and isinstance(v, dict):
            for ck, cv in v.items():
                key = "/" + str(ck).strip().replace(" ", "")
                out[key] = str(cv)
        elif k in mapping and v is not None:
            out[mapping[k]] = str(v)
    return out

def finalize_info(template_info: Dict[str, str], user_info: Dict[str, str]) -> Dict[str, str]:
    out = dict(template_info)
    out.update(user_info or {})
    out.setdefault("/Creator", "Designer 6.5")
    out.setdefault("/Producer", "Designer 6.5")
    out["/CreationDate"] = pdf_date_now()
    out["/ModDate"]       = out["/CreationDate"]
    return out

def build_xmp_packet(info: Dict[str, str]) -> bytes:
    title = info.get("/Title", "")
    author = info.get("/Author", "")
    subject = info.get("/Subject", "")
    keywords = info.get("/Keywords", "")
    producer = info.get("/Producer", "Designer 6.5")
    creatortool = info.get("/Creator", "Designer 6.5")
    create_iso = now_iso_utc()
    modify_iso = create_iso
    def _xml_escape(s: str) -> str:
        return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
    xmp = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
          xmlns:dc="http://purl.org/dc/elements/1.1/"
          xmlns:xmp="http://ns.adobe.com/xap/1.0/"
          xmlns:pdf="http://ns.adobe.com/pdf/1.3/">
  <rdf:Description rdf:about="">
    <dc:title><rdf:Alt><rdf:li xml:lang="x-default">{_xml_escape(title)}</rdf:li></rdf:Alt></dc:title>
    <dc:creator><rdf:Seq>{f"<rdf:li>{_xml_escape(author)}</rdf:li>" if author else ""}</rdf:Seq></dc:creator>
    <dc:description><rdf:Alt><rdf:li xml:lang="x-default">{_xml_escape(subject)}</rdf:li></rdf:Alt></dc:description>
    <pdf:Keywords>{_xml_escape(keywords)}</pdf:Keywords>
    <pdf:Producer>{_xml_escape(producer)}</pdf:Producer>
    <xmp:CreatorTool>{_xml_escape(creatortool)}</xmp:CreatorTool>
    <xmp:CreateDate>{create_iso}</xmp:CreateDate>
    <xmp:ModifyDate>{modify_iso}</xmp:ModifyDate>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""
    return xmp.encode("utf-8")

def attach_xmp(writer: PdfWriter, xmp_bytes: bytes):
    meta_stream = DecodedStreamObject()
    meta_stream.set_data(xmp_bytes)
    meta_stream.update({
        NameObject("/Type"): NameObject("/Metadata"),
        NameObject("/Subtype"): NameObject("/XML"),
    })
    writer._root_object[NameObject("/Metadata")] = writer._add_object(meta_stream)

# -------------------- watermark color helpers --------------------

def _parse_hex_color(s: str) -> Optional[Tuple[float, float, float]]:
    s = s.strip()
    if not s.startswith("#"): return None
    s = s[1:]
    if len(s) == 3:
        r, g, b = (int(ch*2, 16) for ch in s)
    elif len(s) == 6:
        r, g, b = (int(s[i:i+2], 16) for i in (0, 2, 4))
    else:
        return None
    return (r/255.0, g/255.0, b/255.0)

def choose_wm_color(wm_cfg: Optional[Dict[str, Any]], visible: bool) -> Tuple[float, float, float]:
    if not visible:
        return (1.0, 1.0, 1.0)
    if wm_cfg:
        cstr = wm_cfg.get("visible_color")
        if isinstance(cstr, str):
            rgb = _parse_hex_color(cstr)
            if rgb: return rgb
        g = wm_cfg.get("visible_gray")
        try:
            if g is not None:
                g = float(g); g = min(max(g, 0.0), 1.0)
                return (g, g, g)
        except Exception:
            pass
    return (0.82, 0.82, 0.82)

# -------------------- overlay & watermark composers --------------------

def compose_overlay_page1(template_pdf: str, data: Dict[str, Any], overlay_pdf: str,
                          fontwarp: bool, fontwarp_aggr: bool):
    reader = PdfReader(template_pdf)
    w, h = get_page_size(reader, 0)
    widgets = get_page_widgets(reader, 0)

    roles = {
        "name": "f1_01[0]", "business": "f1_02[0]",
        "chk_individual": "c1_1[0]", "chk_c_corp": "c1_1[1]", "chk_s_corp": "c1_1[2]",
        "chk_partnership": "c1_1[3]", "chk_trust_estate": "c1_1[4]", "chk_llc": "c1_1[5]",
        "llc_code": "f1_03[0]", "chk_other": "c1_1[6]", "other_text": "f1_04[0]",
        "chk_3b": "c1_2[0]", "exempt": "f1_05[0]", "fatca": "f1_06[0]",
        "addr1": "f1_07[0]", "addr2": "f1_08[0]",
        "requester": "f1_09[0]", "accounts": "f1_10[0]",
        "ssn_1": "f1_11[0]", "ssn_2": "f1_12[0]", "ssn_3": "f1_13[0]",
        "ein_1": "f1_14[0]", "ein_2": "f1_15[0]",
    }
    rects = {w["name"]: w["rect"] for w in widgets}
    def r(key: str):
        name = roles.get(key); return rects.get(name) if name else None

    main_font, warp_list, bold_font = register_fonts_for_overlay()
    cycler = FontCycler(warp_list if fontwarp else [main_font])

    c = canvas.Canvas(overlay_pdf, pagesize=(w, h))
    tmp_images: List[str] = []

    def draw_text(rect, text, max_size=11, align="left"):
        if fontwarp_aggr:
            png = _draw_singleline_to_png(text, rect[2]-rect[0], rect[3]-rect[1],
                                          font_px=int(max_size), align=align)
            tmp_images.append(png); draw_image_into_canvas(c, png, rect)
        else:
            draw_text_fit_vec(c, text, rect, font=cycler.next(), max_size=max_size)

    def draw_multiline(rect, text, max_size=9.5):
        if fontwarp_aggr:
            png = _draw_multiline_to_png(text, rect[2]-rect[0], rect[3]-rect[1],
                                         font_px=int(max_size))
            tmp_images.append(png); draw_image_into_canvas(c, png, rect)
        else:
            draw_multiline_fit_vec(c, text, rect, font=cycler.next(), max_size=max_size)

    def draw_digits(rect, digits, slots, max_size=12):
        if fontwarp_aggr:
            png = _draw_digits_grid_to_png(digits, rect[2]-rect[0], rect[3]-rect[1],
                                           slots=slots, font_px=int(max_size))
            tmp_images.append(png); draw_image_into_canvas(c, png, rect)
        else:
            draw_digits_in_cells_vec(c, digits, rect, slots, font=cycler.next(), max_size=max_size)

    # Basics
    draw_text(r("name"),              data.get("name",""),              max_size=11)
    draw_text(r("business"),          data.get("business_name",""),     max_size=11)
    draw_text(r("exempt"),            data.get("exempt_payee_code",""), max_size=10)
    draw_text(r("fatca"),             data.get("fatca_code",""),        max_size=10)
    draw_text(r("addr1"),             data.get("address",""),           max_size=10.5)

    city = norm(data.get("city")); state = norm(data.get("state")); zipc = norm(data.get("zip"))
    combined = ", ".join([x for x in [city, state] if x])
    if zipc: combined = (combined + " " + zipc).strip()
    draw_text(r("addr2"), combined, max_size=10.5)

    draw_multiline(r("requester"),    data.get("requester_info",""),    max_size=9.5)
    draw_text(r("accounts"),          data.get("account_numbers",""),   max_size=10)

    # Classification
    cls = (data.get("classification","") or "").lower().strip()
    def ck(role_key, on=True): draw_check_vec(c, r(role_key), font=FONT_BOLD) if on else None
    if cls in ("individual","sole proprietor","sole_proprietor"): ck("chk_individual")
    elif cls in ("c_corp","c corp","c corporation","c"): ck("chk_c_corp")
    elif cls in ("s_corp","s corp","s corporation","s"): ck("chk_s_corp")
    elif cls in ("partnership","p"): ck("chk_partnership")
    elif cls in ("trust_estate","trust","estate"): ck("chk_trust_estate")
    elif cls.startswith("llc"):
        ck("chk_llc")
        code = (data.get("llc_tax_class","") or "").strip().upper()
        draw_text(r("llc_code"), code or "C", max_size=10)
    elif cls == "other":
        ck("chk_other"); draw_text(r("other_text"), norm(data.get("other_text","")), max_size=10)
    if bool(data.get("line3b_foreign_flowthrough", False)): ck("chk_3b")

    # TIN
    ssn = norm(data.get("ssn")); ein = norm(data.get("ein"))
    if ssn and not ein:
        a,b,c3 = split_ssn(ssn)
        draw_digits(r("ssn_1"), a, 3, max_size=12)
        draw_digits(r("ssn_2"), b, 2, max_size=12)
        draw_digits(r("ssn_3"), c3,4, max_size=12)
    elif ein:
        a,b = split_ein(ein)
        draw_digits(r("ein_1"), a, 2, max_size=12)
        draw_digits(r("ein_2"), b, 7, max_size=12)

    # Signature & Date (+72pt)
    SIG_X, SIG_Y  = 115, 125 + 72
    DATE_X, DATE_Y = 470, 125 + 72
    if fontwarp_aggr:
        rect_sig  = [SIG_X,  SIG_Y - 2,  SIG_X + 220, SIG_Y + 16]
        rect_date = [DATE_X, DATE_Y - 2, DATE_X + 120, DATE_Y + 16]
        png = _draw_singleline_to_png(norm(data.get("signature")), rect_sig[2]-rect_sig[0],
                                      rect_sig[3]-rect_sig[1], font_px=11)
        draw_image_into_canvas(c, png, rect_sig)
        png2 = _draw_singleline_to_png(norm(data.get("signature_date")) or today_str(),
                                       rect_date[2]-rect_date[0], rect_date[3]-rect_date[1], font_px=11)
        draw_image_into_canvas(c, png2, rect_date)
    else:
        c.setFont(cycler.next(), 11); c.drawString(SIG_X,  SIG_Y,  norm(data.get("signature")))
        c.setFont(cycler.next(), 11); c.drawString(DATE_X, DATE_Y, norm(data.get("signature_date")) or today_str())

    c.showPage(); c.save()

    return tmp_images

def compose_watermark_page(template_pdf: str, page_index: int, wm_cfg: Dict[str, Any],
                           out_pdf: str, visible: bool):
    reader = PdfReader(template_pdf)
    w, h = get_page_size(reader, page_index)
    c = canvas.Canvas(out_pdf, pagesize=(w, h))
    r, g, b = choose_wm_color(wm_cfg, visible)
    c.setFillColorRGB(r, g, b)

    for it in (wm_cfg.get("items") or []):
        txt = norm(it.get("text")); x=float(it.get("x",0)); y=float(it.get("y",0))
        sz=float(it.get("size",10)); ang=float(it.get("angle",0))
        if not txt: continue
        c.saveState(); c.translate(x,y)
        if ang: c.rotate(ang)
        c.setFont(FONT_MAIN, sz); c.drawString(0,0,txt)
        c.restoreState()

    tile = wm_cfg.get("tile")
    if isinstance(tile, dict):
        ttxt = norm(tile.get("text"))
        if ttxt:
            sz=float(tile.get("size",8)); x0=float(tile.get("x_offset",24)); y0=float(tile.get("y_offset",24))
            xs=float(tile.get("x_step",144)); ys=float(tile.get("y_step",120)); ang=float(tile.get("angle",0))
            c.setFont(FONT_MAIN, sz)
            y=y0
            while y < h:
                x=x0
                while x < w:
                    c.saveState(); c.translate(x,y)
                    if ang: c.rotate(ang)
                    c.drawString(0,0,ttxt)
                    c.restoreState()
                    x += xs
                y += ys
    c.showPage(); c.save()

# -------------------- writer helpers --------------------

def strip_annots(page):
    try:
        if "/Annots" in page:
            del page["/Annots"]
    except Exception:
        pass

def _strip_tounicode_in_resources(res: DictionaryObject):
    if not isinstance(res, DictionaryObject):
        return
    try:
        if "/Font" in res:
            font_dict = res.get("/Font")
            if isinstance(font_dict, DictionaryObject):
                for _, fref in list(font_dict.items()):
                    try:
                        fobj = fref.get_object()
                        if "/ToUnicode" in fobj:
                            del fobj["/ToUnicode"]
                    except Exception:
                        continue
    except Exception:
        pass
    try:
        if "/XObject" in res:
            xo = res.get("/XObject")
            if isinstance(xo, DictionaryObject):
                for _, xref in list(xo.items()):
                    try:
                        xobj = xref.get_object()
                        if "/Resources" in xobj:
                            _strip_tounicode_in_resources(xobj.get("/Resources"))
                    except Exception:
                        continue
    except Exception:
        pass

def apply_fontwarp(writer: PdfWriter):
    try:
        for p in writer.pages:
            res = p.get("/Resources")
            if isinstance(res, IndirectObject):
                res = res.get_object()
            if isinstance(res, DictionaryObject):
                _strip_tounicode_in_resources(res)
    except Exception:
        pass

def build_writer_with_layers(template_pdf: str,
                             overlay_pdf_page1: str,
                             wm_cfg: Optional[Dict[str, Any]],
                             wm_visible: bool) -> Tuple[PdfWriter, List[str]]:
    """Return (writer, temp_files_created). Overlay is merged on page 1."""
    reader = PdfReader(template_pdf)
    n = len(reader.pages)
    writer = PdfWriter()
    temps: List[str] = []

    wm_pages_all = False
    wm_pages_set = set()
    if wm_cfg:
        pages_val = wm_cfg.get("pages")
        if isinstance(pages_val, str) and pages_val.lower() == "all":
            wm_pages_all = True
        elif isinstance(pages_val, list):
            try:
                wm_pages_set = {int(p) for p in pages_val}
            except Exception:
                wm_pages_set = set()

    # Page 1: optional watermark, then template, then overlay
    base_page = None
    if wm_cfg and (wm_pages_all or 1 in wm_pages_set):
        wm_out = os.path.splitext(overlay_pdf_page1)[0] + ".wm_p1.pdf"
        compose_watermark_page(template_pdf, 0, wm_cfg, wm_out, visible=wm_visible)
        temps.append(wm_out)
        wm_reader = PdfReader(wm_out); base_page = wm_reader.pages[0]
    tpl_page0 = reader.pages[0]
    if base_page is None:
        base_page = tpl_page0
    else:
        base_page.merge_page(tpl_page0)
    strip_annots(base_page)
    ov_reader = PdfReader(overlay_pdf_page1)
    base_page.merge_page(ov_reader.pages[0])
    writer.add_page(base_page)

    # Remaining pages
    for i in range(1, n):
        if wm_cfg and (wm_pages_all or (i+1) in wm_pages_set):
            wm_out_i = f"{os.path.splitext(overlay_pdf_page1)[0]}.wm_p{i+1}.pdf"
            compose_watermark_page(template_pdf, i, wm_cfg, wm_out_i, visible=wm_visible)
            temps.append(wm_out_i)
            wm_reader_i = PdfReader(wm_out_i)
            page = wm_reader_i.pages[0]
            page.merge_page(reader.pages[i])
            writer.add_page(page)
        else:
            writer.add_page(reader.pages[i])

    return writer, temps

def build_writer_wm_only(template_pdf: str,
                         wm_cfg: Optional[Dict[str, Any]],
                         wm_visible: bool) -> Tuple[PdfWriter, List[str]]:
    """
    Build a writer that ONLY merges watermark layers (if provided) with the template.
    Does NOT strip annotations or add any overlay. Useful for --w9bp.
    """
    reader = PdfReader(template_pdf)
    n = len(reader.pages)
    writer = PdfWriter()
    temps: List[str] = []

    wm_pages_all = False
    wm_pages_set = set()
    if wm_cfg:
        pages_val = wm_cfg.get("pages")
        if isinstance(pages_val, str) and pages_val.lower() == "all":
            wm_pages_all = True
        elif isinstance(pages_val, list):
            try:
                wm_pages_set = {int(p) for p in pages_val}
            except Exception:
                wm_pages_set = set()

    for i in range(n):
        if wm_cfg and (wm_pages_all or (i+1) in wm_pages_set):
            wm_out_i = f"{os.path.splitext(template_pdf)[0]}.wm_p{i+1}.pdf"
            compose_watermark_page(template_pdf, i, wm_cfg, wm_out_i, visible=wm_visible)
            temps.append(wm_out_i)
            wm_reader_i = PdfReader(wm_out_i)
            page = wm_reader_i.pages[0]
            page.merge_page(reader.pages[i])   # watermark below, template above
            writer.add_page(page)
        else:
            writer.add_page(reader.pages[i])

    return writer, temps

def flatten_all(src_pdf: str, dst_pdf: str):
    r = PdfReader(src_pdf)
    w = PdfWriter()
    for p in r.pages:
        if "/Annots" in p:
            del p["/Annots"]
        w.add_page(p)
    try:
        meta = r.metadata or {}
        if meta:
            w.add_metadata(dict(meta))
    except Exception:
        pass
    try:
        root = r.trailer.get("/Root")
        if root and "/Metadata" in root:
            meta_obj = root["/Metadata"].get_object()
            w._root_object[NameObject("/Metadata")] = w._add_object(meta_obj)
    except Exception:
        pass
    with open(dst_pdf, "wb") as f:
        w.write(f)

# -------------------- CLI --------------------

def main():
    ap = argparse.ArgumentParser(description="Recreate W-9 visually (no form-fill) — v4.2.2 (core + w9bp)")
    ap.add_argument("--template", required=True, help="Your W-9 PDF (e.g., fw9.pdf)")

    # bypass mode
    ap.add_argument("--w9bp", action="store_true",
                    help="Bypass overlay: ONLY apply metadata + (optional) watermark; preserves form fields unless --flatten.")

    # data / profiles (ignored when --w9bp)
    ap.add_argument("--data", help="JSON profile (ignored if --profile-rand is used)")
    ap.add_argument("--profile-rand", action="store_true",
                    help="Pick a random JSON profile from ./profiles/ instead of --data")

    # metadata
    ap.add_argument("--meta", help="Custom metadata JSON file (ignored if --meta-rand is used)")
    ap.add_argument("--meta-rand", action="store_true",
                    help="Pick a random md*.json from ./md/ and embed as PDF metadata")

    # watermark
    ap.add_argument("--wm", help="Watermark JSON file under ./wm/")
    ap.add_argument("--wm-rand", action="store_true",
                    help="Pick a random wm*.json from ./wm/ to add watermark text")
    ap.add_argument("--wm-visible", dest="wm_visible", action="store_true",
                    help="Render watermark visibly (light gray); default is invisible white-on-white")

    # font warp (ignored when --w9bp)
    ap.add_argument("--fontwarp", action="store_true",
                    help="Alternate fonts and strip /ToUnicode to hinder text extraction (QA/SEC testing ONLY)")
    ap.add_argument("--fontwarp-aggressive", action="store_true",
                    help="Rasterize filled fields so they are not selectable text (QA/SEC testing ONLY)")

    # housekeeping
    ap.add_argument("--clean", action="store_true",
                    help="Delete temporary PDFs (overlay + watermark layer files) after writing")

    # output
    ap.add_argument("--output", help="Output PDF name; default is {YYYY-MM-DD-HHMMSS}.pdf")
    ap.add_argument("--flatten", action="store_true", help="Strip any remaining widgets/annots")
    args = ap.parse_args()

    if not args.output:
        args.output = datetime.now().strftime("%Y-%m-%d-%H%M%S.pdf")

    # Resolve metadata (used in both normal and w9bp)
    user_meta = {}
    if args.meta_rand:
        md_dir = os.path.join(os.getcwd(), "md")
        if not os.path.isdir(md_dir):
            raise SystemExit(f"[meta-rand] Directory not found: {md_dir}")
        md_candidates = [f for f in os.listdir(md_dir)
                         if f.lower().endswith(".json") and f.lower().startswith("md")]
        if not md_candidates:
            raise SystemExit(f"[meta-rand] No md*.json files found in {md_dir}")
        md_choice = random.choice(md_candidates)
        md_path = os.path.join(md_dir, md_choice)
        print(f"[meta-rand] Using metadata: {md_path}")
        user_meta = build_metadata_dict(load_json(md_path))
    elif args.meta:
        user_meta = build_metadata_dict(load_json(args.meta))

    # Resolve watermark (used in both modes)
    wm_cfg = None
    if args.wm_rand:
        wm_dir = os.path.join(os.getcwd(), "wm")
        if not os.path.isdir(wm_dir):
            raise SystemExit(f"[wm-rand] Directory not found: {wm_dir}")
        wm_candidates = [f for f in os.listdir(wm_dir)
                         if f.lower().endswith(".json") and f.lower().startswith("wm")]
        if not wm_candidates:
            raise SystemExit(f"[wm-rand] No wm*.json files found in {wm_dir}")
        wm_choice = random.choice(wm_candidates)
        wm_path = os.path.join(wm_dir, wm_choice)
        print(f"[wm-rand] Using watermark: {wm_path}")
        wm_cfg = load_json(wm_path)
    elif args.wm:
        wm_cfg = load_json(args.wm)

    temp_files: List[str] = []

    if args.w9bp:
        # Bypass overlay: only watermark + metadata
        if args.fontwarp or args.fontwarp_aggressive:
            print("[w9bp] Note: --fontwarp / --fontwarp-aggressive are ignored in --w9bp mode.")
        writer, temp_files = build_writer_wm_only(args.template, wm_cfg, wm_visible=args.wm_visible)

    else:
        # Normal path: resolve profile & build overlay
        if args.profile_rand:
            profiles_dir = os.path.join(os.getcwd(), "profiles")
            if not os.path.isdir(profiles_dir):
                raise SystemExit(f"[profile-rand] Directory not found: {profiles_dir}")
            candidates = [f for f in os.listdir(profiles_dir) if f.lower().endswith(".json")]
            if not candidates:
                raise SystemExit(f"[profile-rand] No *.json files found in {profiles_dir}")
            choice = random.choice(candidates)
            chosen_path = os.path.join(profiles_dir, choice)
            print(f"[profile-rand] Using profile: {chosen_path}")
            data = load_json(chosen_path)
        else:
            if not args.data:
                raise SystemExit("Please supply --data <file.json> or use --profile-rand (unless using --w9bp).")
            data = load_json(args.data)

        overlay_path = os.path.splitext(args.output)[0] + ".overlay.pdf"
        tmp_pngs = compose_overlay_page1(args.template, data, overlay_path,
                                         fontwarp=args.fontwarp, fontwarp_aggr=args.fontwarp_aggressive)
        writer, temp_files = build_writer_with_layers(args.template, overlay_path, wm_cfg, wm_visible=args.wm_visible)
        temp_files = [overlay_path] + temp_files  # always consider overlay a temp

    # Metadata
    reader = PdfReader(args.template)
    final_info = finalize_info(read_template_info(reader), user_meta)
    xmp_bytes = build_xmp_packet(final_info)

    # fontwarp stripping only in normal mode
    if not args.w9bp and args.fontwarp:
        apply_fontwarp(writer)

    # Write output
    if final_info:
        writer.add_metadata(final_info)
    if xmp_bytes:
        attach_xmp(writer, xmp_bytes)
    with open(args.output, "wb") as f:
        writer.write(f)

    # Optional flatten
    if args.flatten:
        flat = args.output.replace(".pdf", "_flat.pdf")
        flatten_all(args.output, flat)
        print(f"Recreated & flattened PDF: {flat}")
    else:
        print(f"Recreated PDF: {args.output}")

    # Cleanup temp PDFs
    if args.w9bp:
        # Only watermark temps exist in this mode
        if args.clean:
            for pth in (temp_files or []):
                try:
                    os.remove(pth)
                    print(f"[clean] removed {pth}")
                except Exception:
                    pass
    else:
        # Normal mode: remove overlay always; remove others if --clean
        for pth in (temp_files if args.clean else temp_files[:1]):  # first is overlay
            try:
                os.remove(pth)
                print(f"[clean] removed {pth}")
            except Exception:
                pass
        # remove any aggressive-mode PNGs (already handled inside compose in v4.2.1, kept here just in case)
        try:
            for name in os.listdir("."):
                if name.endswith(".png") and ".overlay" in name:
                    os.remove(name)
        except Exception:
            pass

if __name__ == "__main__":
    main()

