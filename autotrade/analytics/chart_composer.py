"""
Institutional Chart Compositor.
Combines MT4 clean price charts with the SmartAutoTrade EA HUD telemetry
and Multi-Timeframe Confluence Matrix into a single, unified high-resolution image.
Ensures price candles and telemetry panels are both completely visible with zero obstruction.
"""

import os
import logging
from typing import Any, Dict, Optional
from PIL import Image, ImageDraw, ImageFont
from PIL.PngImagePlugin import PngInfo

logger = logging.getLogger("autotrade.analytics.chart_composer")

# Palette definitions
BG_CANVAS = (18, 20, 26)         # Deep institutional dark canvas
BG_CARD = (22, 25, 32)           # HUD panel card background
BORDER_CARD = (65, 75, 90)       # Sleek card outline
BORDER_DIVIDER = (45, 52, 65)    # Divider line
COLOR_GOLD = (255, 195, 0)       # Section titles & headers
COLOR_LABEL = (190, 200, 215)    # Metric description labels
COLOR_VALUE_WHITE = (245, 245, 245)
COLOR_GREEN = (40, 190, 80)      # Bullish / Active / Buy
COLOR_RED = (235, 65, 65)        # Bearish / Sell / Warning
COLOR_BLUE = (0, 180, 255)       # Session info / Neutral accent
COLOR_GRAY = (110, 115, 125)     # Inactive / Neutral badge
COLOR_CYAN = (80, 220, 240)      # Instrument tag accent


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Load system TTF fonts with graceful fallbacks."""
    font_candidates = [
        "/usr/share/fonts/TTF/Roboto-Bold.ttf" if bold else "/usr/share/fonts/TTF/Roboto-Regular.ttf",
        "/usr/share/fonts/TTF/Roboto-Medium.ttf",
        "/usr/share/fonts/Adwaita/AdwaitaMono-Bold.ttf" if bold else "/usr/share/fonts/Adwaita/AdwaitaMono-Regular.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def compose_chart_screenshot(chart_image_path: str, data: Dict[str, Any]) -> str:
    """
    Composites the clean MT4 chart image with the Telemetry HUD Dashboard.
    The resulting image displays:
      - Top section: Dedicated HUD and MTF Confluence telemetry panels
      - Bottom section: 100% clean, unobstructed MT4 price chart with candles
    Saves back into chart_image_path and returns the path.
    """
    if not os.path.exists(chart_image_path):
        logger.warning(f"Chart image not found for composition: {chart_image_path}")
        return chart_image_path

    try:
        chart_img = Image.open(chart_image_path).convert("RGB")
        cw, ch = chart_img.size
        # Idempotency check 1: check PNG metadata
        if chart_img.info.get("composed") == "true":
            logger.debug(f"Image {chart_image_path} already composited (PNG metadata). Skipping.")
            return chart_image_path
        # Idempotency check 2: check if canvas header already exists at top coordinates
        if ch > 800 and chart_img.getpixel((25, 20)) == BG_CARD and chart_img.getpixel((cw - 25, 20)) == BG_CARD:
            logger.debug(f"Image {chart_image_path} already composited (pixel match). Skipping.")
            return chart_image_path
    except Exception as ex:
        logger.warning(f"Failed to open chart image: {ex}")
        return chart_image_path

    # Extract telemetry dictionary or fallback to top-level fields
    telem = data.get("telemetry", {})
    if not isinstance(telem, dict):
        telem = {}

    raw_sym = str(data.get("symbol", telem.get("symbol", "CHART")))
    sym = raw_sym.replace("_min", "")
    tf = str(data.get("timeframe", telem.get("timeframe", "H1"))).replace("PERIOD_", "")
    bid = data.get("bid", telem.get("bid", 0.0))
    ask = data.get("ask", telem.get("ask", 0.0))
    srv_time = data.get("server_time", telem.get("server_time", ""))

    # Load fonts
    f_h2 = _load_font(15, bold=True)
    f_txt = _load_font(13, bold=False)
    f_bold = _load_font(13, bold=True)
    f_small = _load_font(11, bold=False)
    f_badge = _load_font(12, bold=True)

    header_h = 248
    canvas = Image.new("RGB", (cw, ch + header_h), color=BG_CANVAS)
    draw = ImageDraw.Draw(canvas)

    # Calculate card dimensions
    gap = 14
    margin_x = 15
    margin_y = 10
    card_w = (cw - (2 * margin_x) - gap) // 2
    card_h = header_h - (2 * margin_y)

    c1_x1, c1_y1 = margin_x, margin_y
    c1_x2, c1_y2 = c1_x1 + card_w, c1_y1 + card_h

    c2_x1, c2_y1 = c1_x2 + gap, margin_y
    c2_x2, c2_y2 = cw - margin_x, c2_y1 + card_h

    # Draw rounded background cards
    draw.rounded_rectangle([c1_x1, c1_y1, c1_x2, c1_y2], radius=8, fill=BG_CARD, outline=BORDER_CARD, width=1)
    draw.rounded_rectangle([c2_x1, c2_y1, c2_x2, c2_y2], radius=8, fill=BG_CARD, outline=BORDER_CARD, width=1)

    # -------------------------------------------------------------
    # CARD 1: SMARTAUTOTRADE EA HUD PANEL
    # -------------------------------------------------------------
    draw.text((c1_x1 + 14, c1_y1 + 10), "=== SMARTAUTOTRADE EA HUD ===", font=f_h2, fill=COLOR_GOLD)

    # Asset & timeframe badge on Card 1 top-right
    asset_badge = f"[{sym} • {tf}]"
    b_box = draw.textbbox((0, 0), asset_badge, font=f_bold)
    bw = b_box[2] - b_box[0]
    draw.text((c1_x2 - 14 - bw, c1_y1 + 12), asset_badge, font=f_bold, fill=COLOR_CYAN)

    # Row 1: Trend Regime & Last Signal
    trend = telem.get("trend", "STRONG BULLISH")
    trend_col = COLOR_GREEN if "BULL" in trend.upper() else (COLOR_RED if "BEAR" in trend.upper() else COLOR_GOLD)
    trend_lbl = "Trend Regime: "
    draw.text((c1_x1 + 14, c1_y1 + 36), trend_lbl, font=f_txt, fill=COLOR_LABEL)
    tl_w = draw.textbbox((0, 0), trend_lbl, font=f_txt)[2]
    draw.text((c1_x1 + 14 + tl_w, c1_y1 + 36), trend, font=f_bold, fill=trend_col)

    # Signal on right side (guaranteed no card overflow)
    signal = telem.get("signal", "Evaluating: Active")
    sig_col = COLOR_GREEN if "BUY" in signal.upper() else (COLOR_RED if "SELL" in signal.upper() else COLOR_VALUE_WHITE)
    sig_lbl = "Signal: "
    sl_w = draw.textbbox((0, 0), sig_lbl, font=f_txt)[2]
    sv_w = draw.textbbox((0, 0), signal, font=f_bold)[2]
    total_sig_w = sl_w + sv_w
    sig_start_x = max(c1_x1 + (card_w // 2) + 10, c1_x2 - 14 - total_sig_w)
    draw.text((sig_start_x, c1_y1 + 36), sig_lbl, font=f_txt, fill=COLOR_LABEL)
    draw.text((sig_start_x + sl_w, c1_y1 + 36), signal, font=f_bold, fill=sig_col)

    # Row 2: Confluence Points Breakdown
    points = telem.get("points", "Pts: Trend(3/0) Mom(0/0) SR(1/1) Cndl(2/0)")
    draw.text((c1_x1 + 14, c1_y1 + 60), points, font=f_small, fill=(160, 172, 188))

    # Row 3: Technical Oscillators Data
    osc = telem.get("osc", "RSI: 50.0  |  MACD: +0.00000  |  ADX: 25.0")
    draw.text((c1_x1 + 14, c1_y1 + 82), osc, font=f_txt, fill=COLOR_VALUE_WHITE)

    # Row 4: Session, Spread & Volatility (Deduplicate ATR)
    spread = str(telem.get("spread", "0 pts (Max: 50)"))
    session = telem.get("session", "London/NY Overlap")
    if "ATR" in spread.upper():
        session_line = f"Session: {session}  |  Spread: {spread}"
    else:
        atr = telem.get("atr", "")
        if atr:
            session_line = f"Session: {session}  |  Spread: {spread}  |  ATR: {atr}"
        else:
            session_line = f"Session: {session}  |  Spread: {spread}"
    draw.text((c1_x1 + 14, c1_y1 + 106), session_line, font=f_txt, fill=COLOR_BLUE)

    # Row 5: Financial Overview
    bal = telem.get("balance", "10000.00")
    eq = telem.get("equity", "10000.00")
    pnl = telem.get("daily_pnl", "$0.00 (0.00%)")
    fin_line = f"Balance: ${bal}  |  Equity: ${eq}  |  Daily P&L: {pnl}"
    draw.text((c1_x1 + 14, c1_y1 + 130), fin_line, font=f_txt, fill=COLOR_VALUE_WHITE)

    # Row 6: Position & Bot Execution State (Measured dynamic positioning)
    pos = telem.get("positions", "0/1")
    bot_st = telem.get("bot_status", "ACTIVE [RUNNING]")
    st_col = COLOR_GREEN if "ACTIVE" in bot_st.upper() else COLOR_RED
    pos_lbl = f"Position: {pos}  |  Bot: "
    draw.text((c1_x1 + 14, c1_y1 + 154), pos_lbl, font=f_txt, fill=COLOR_LABEL)
    pos_lbl_w = draw.textbbox((0, 0), pos_lbl, font=f_txt)[2]
    draw.text((c1_x1 + 14 + pos_lbl_w, c1_y1 + 154), bot_st, font=f_bold, fill=st_col)

    # Row 7: Ultra Quant Metrics, Candlestick Pattern & Extended Indicators
    pattern = telem.get("pattern", "None")
    quant = telem.get("quant", "KER: 0.35 | Squeeze: None")
    ext = telem.get("ext_ind", "CCI: 100.0 | %B: 0.50 | VSA: Normal")
    footer_line = f"{quant}  |  Pattern: {pattern}  |  {ext}"
    draw.text((c1_x1 + 14, c1_y1 + 178), footer_line, font=f_small, fill=COLOR_GOLD)

    # -------------------------------------------------------------
    # CARD 2: MULTI-TIMEFRAME CONFLUENCE MATRIX & QUICK CONTROLS
    # -------------------------------------------------------------
    draw.text((c2_x1 + 14, c2_y1 + 10), "=== MTF CONFLUENCE MATRIX ===", font=f_h2, fill=COLOR_GOLD)

    # Server quote on Card 2 top-right
    if bid and ask:
        quote_text = f"Bid: {bid} / Ask: {ask}"
        qb_box = draw.textbbox((0, 0), quote_text, font=f_small)
        qw = qb_box[2] - qb_box[0]
        draw.text((c2_x2 - 14 - qw, c2_y1 + 12), quote_text, font=f_small, fill=COLOR_LABEL)

    # Timeframe pills
    mtf_dict = telem.get("mtf", {})
    if not isinstance(mtf_dict, dict):
        mtf_dict = {}

    tf_list = ["M5", "M15", "M30", "H1", "H4", "D1"]
    pill_w = (card_w - 28 - (5 * 8)) // 6
    pill_h = 28
    px = c2_x1 + 14
    py = c2_y1 + 38

    up_count = 0
    total_valid_tfs = 0
    for tf_name in tf_list:
        status = str(mtf_dict.get(tf_name, "--")).upper()
        if "UP" in status:
            fill_col = (40, 167, 69)
            text_col = (255, 255, 255)
            badge_text = f"{tf_name} UP"
            up_count += 1
            total_valid_tfs += 1
        elif "DN" in status or "DOWN" in status:
            fill_col = (220, 53, 69)
            text_col = (255, 255, 255)
            badge_text = f"{tf_name} DN"
            total_valid_tfs += 1
        else:
            fill_col = (75, 82, 92)
            text_col = (210, 215, 220)
            badge_text = f"{tf_name} --"

        draw.rounded_rectangle([px, py, px + pill_w, py + pill_h], radius=4, fill=fill_col)
        bbox = draw.textbbox((0, 0), badge_text, font=f_badge)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = px + max(2, (pill_w - tw) // 2)
        ty = py + max(2, (pill_h - th) // 2) - 1
        draw.text((tx, ty), badge_text, font=f_badge, fill=text_col)
        px += pill_w + 8

    # Gauge & Confluence Power (Dynamically computed from telemetry or pills)
    draw.text((c2_x1 + 14, c2_y1 + 78), "Trend Confluence Index:", font=f_txt, fill=COLOR_LABEL)

    computed_pct = (up_count / (total_valid_tfs or 6)) * 100.0
    power_val = float(telem.get("power_pct", computed_pct))
    bull_power = telem.get("bull_power", f"{power_val:.1f}% ({up_count}/6 TFs)")
    pwr_col = COLOR_GREEN if power_val >= 66.0 else (COLOR_RED if power_val <= 33.0 else COLOR_GOLD)
    draw.text((c2_x1 + 14, c2_y1 + 102), f"Bullish Power: {bull_power}", font=f_bold, fill=pwr_col)

    advice = telem.get("mtf_advice", "Action: Evaluating Alignment")
    draw.text((c2_x1 + 14, c2_y1 + 126), advice, font=f_txt, fill=COLOR_VALUE_WHITE)

    # Interactive Chart Controls Display
    btn_y = c2_y1 + 160
    btn_w = (card_w - 28 - 20) // 3
    btn_h = 32

    # CLOSE ALL button
    draw.rounded_rectangle([c2_x1 + 14, btn_y, c2_x1 + 14 + btn_w, btn_y + btn_h], radius=4, fill=(140, 35, 35))
    bbox = draw.textbbox((0, 0), "CLOSE ALL", font=f_bold)
    draw.text((c2_x1 + 14 + (btn_w - (bbox[2] - bbox[0])) // 2, btn_y + 7), "CLOSE ALL", font=f_bold, fill=(255, 255, 255))

    # BE ALL button
    bx2 = c2_x1 + 14 + btn_w + 10
    draw.rounded_rectangle([bx2, btn_y, bx2 + btn_w, btn_y + btn_h], radius=4, fill=(35, 95, 140))
    bbox = draw.textbbox((0, 0), "BE ALL", font=f_bold)
    draw.text((bx2 + (btn_w - (bbox[2] - bbox[0])) // 2, btn_y + 7), "BE ALL", font=f_bold, fill=(255, 255, 255))

    # PAUSE EA button
    bx3 = bx2 + btn_w + 10
    draw.rounded_rectangle([bx3, btn_y, bx3 + btn_w, btn_y + btn_h], radius=4, fill=(35, 125, 55))
    bbox = draw.textbbox((0, 0), "PAUSE EA", font=f_bold)
    draw.text((bx3 + (btn_w - (bbox[2] - bbox[0])) // 2, btn_y + 7), "PAUSE EA", font=f_bold, fill=(255, 255, 255))

    # -------------------------------------------------------------
    # BOTTOM SECTION: 100% CLEAN MT4 PRICE CHART
    # -------------------------------------------------------------
    canvas.paste(chart_img, (0, header_h))

    # Sleek border between header and chart
    draw.line([(0, header_h - 1), (cw, header_h - 1)], fill=BORDER_CARD, width=2)

    # Save composite image back to chart_image_path with metadata
    png_info = PngInfo()
    png_info.add_text("composed", "true")
    png_info.add_text("header_h", str(header_h))
    canvas.save(chart_image_path, "PNG", optimize=True, pnginfo=png_info)
    logger.info(f"Composed institutional chart screenshot saved at: {chart_image_path}")
    return chart_image_path
