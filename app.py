# v1.0 — Full-featured Amazon Product Comparison
#
# requirements.txt:
#   streamlit
#   curl_cffi
#   beautifulsoup4

import csv
import io
import json
import re
from collections import Counter

import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from curl_cffi import requests as cf_requests

st.set_page_config(layout="wide", page_title="Amazon Comparison", initial_sidebar_state="collapsed")
st.title("🛍️ Amazon Product Comparison")

st.markdown(
    """
    <style>
    .field-divider { border-top: 1px solid #2a2a2a; margin: 4px 0 4px 0; }
    div[data-testid="column"] { padding: 4px 8px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# Fields
# ─────────────────────────────────────────────────────────────
DEFAULT_FIELDS = [
    "BestValue", "Title", "Price", "UsedPrices", "PriceHistory",
    "Rating", "Customers Say", "ReviewSentiment",
    "SellerInfo", "Variants", "FrequentlyBoughtTogether",
    "ImageGallery", "ReviewImages",
]
ALL_FIELDS = DEFAULT_FIELDS + ["Description", "Brand", "Availability", "Features", "Categories"]

# ─────────────────────────────────────────────────────────────
# Session state init
# ─────────────────────────────────────────────────────────────
if "visible_fields"   not in st.session_state: st.session_state.visible_fields   = DEFAULT_FIELDS.copy()
if "product_data"     not in st.session_state: st.session_state.product_data     = []
if "num_columns"      not in st.session_state: st.session_state.num_columns      = 2
if "show_debug"       not in st.session_state: st.session_state.show_debug       = False
if "_params_loaded"   not in st.session_state: st.session_state._params_loaded   = False

# ── Load URLs from shareable query params (once per session) ──
if not st.session_state._params_loaded:
    params = st.query_params
    if "urls" in params:
        raw = params["urls"]
        url_list = [u.strip() for u in raw.split("|") if u.strip()]
        if url_list:
            st.session_state.product_data = [{"url": u} for u in url_list]
            st.session_state.num_columns  = len(url_list)
    st.session_state._params_loaded = True


def _sync_checkboxes_to_visible():
    for field in ALL_FIELDS:
        st.session_state[f"chk_{field}"] = field in st.session_state.visible_fields


# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
def display_field_selector():
    with st.sidebar.expander("DISPLAY OPTIONS", expanded=True):
        if st.button("✅ Default Options"):
            st.session_state.visible_fields = DEFAULT_FIELDS.copy()
            _sync_checkboxes_to_visible()
        if st.button("🔁 ALL / NONE"):
            all_sel = len(st.session_state.visible_fields) == len(ALL_FIELDS)
            st.session_state.visible_fields = [] if all_sel else ALL_FIELDS.copy()
            _sync_checkboxes_to_visible()
        new_visible = []
        for field in ALL_FIELDS:
            if f"chk_{field}" not in st.session_state:
                st.session_state[f"chk_{field}"] = field in st.session_state.visible_fields
            if st.checkbox(field, key=f"chk_{field}"):
                new_visible.append(field)
        st.session_state.visible_fields = new_visible

    with st.sidebar.expander("DEBUG", expanded=False):
        st.session_state.show_debug = st.checkbox(
            "Show debug panel", value=st.session_state.show_debug, key="chk_debug"
        )


# ─────────────────────────────────────────────────────────────
# Keyword extractor for review sentiment
# ─────────────────────────────────────────────────────────────
_STOP = {
    "i","me","my","we","our","you","your","he","him","his","she","her","it","its",
    "they","them","their","this","that","these","those","am","is","are","was","were",
    "be","been","being","have","has","had","do","does","did","a","an","the","and",
    "but","if","or","as","of","at","by","for","with","about","to","from","in","out",
    "on","off","so","than","too","very","can","will","just","now","not","no","nor",
    "also","get","got","one","like","would","use","used","using","really","much",
    "many","even","still","way","work","works","worked","product","item","bought",
    "buy","great","good","bad","well","could","should","would","there","here","when",
    "what","which","who","how","all","both","some","more","most","other","same",
    "then","than","up","down","into","s","t","re","ve","ll","d","m",
}

def _keywords(text: str, n: int = 7) -> list:
    words = re.findall(r"\b[a-z]{3,}\b", text.lower())
    freq  = Counter(w for w in words if w not in _STOP)
    return [w for w, _ in freq.most_common(n)]


# ─────────────────────────────────────────────────────────────
# Star percentage parser
# ─────────────────────────────────────────────────────────────
def _parse_star_percentages(soup: BeautifulSoup) -> dict:
    result = {}
    for li in soup.select("#histogramTable li"):
        a     = li.select_one("a[aria-label]")
        meter = li.select_one(".a-meter[aria-valuenow]")
        if not (a and meter):
            continue
        label = a.get("aria-label", "")
        star_m = re.search(r"(\d+)\s+star", label, re.IGNORECASE)
        pct_v  = meter.get("aria-valuenow")
        if star_m and pct_v is not None:
            result[f"{int(star_m.group(1))}_star_percentage"] = int(pct_v)
    return result


# ─────────────────────────────────────────────────────────────
# Price helper
# ─────────────────────────────────────────────────────────────
def _price_float(price_str: str) -> float | None:
    try:
        return float(re.sub(r"[^\d.]", "", str(price_str)))
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Main scraper
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_amazon_data(url: str) -> dict:
    data: dict = {}
    try:
        r    = cf_requests.get(url, impersonate="chrome120", timeout=20,
                               headers={"Accept-Language": "en-US,en;q=0.9"})
        soup = BeautifulSoup(r.text, "html.parser")

        # ── Basic fields ──────────────────────────────────────
        title = soup.select_one("#productTitle")
        data["name"] = title.get_text(strip=True) if title else "N/A"

        price = soup.select_one(".a-price .a-offscreen")
        data["pricing"] = price.get_text(strip=True) if price else "N/A"

        rating = soup.select_one("#acrPopover")
        data["average_rating"] = (
            rating["title"].split()[0] if rating and rating.get("title") else "N/A"
        )
        reviews = soup.select_one("#acrCustomerReviewText")
        data["total_reviews"] = (
            int(re.sub(r"[^\d]", "", reviews.get_text())) if reviews else None
        )
        data.update(_parse_star_percentages(soup))

        # ── Stock images ──────────────────────────────────────
        matches = re.findall(r'"hiRes":"(https://[^"]+)"', r.text)
        if matches:
            data["images"] = list(dict.fromkeys(matches))
        else:
            imgs = []
            for el in soup.select("#altImages img"):
                src   = el.get("src", "")
                large = re.sub(r"\._[A-Z0-9_,]+_\.", "._AC_SL1500_.", src)
                if large.startswith("https"):
                    imgs.append(large)
            if not imgs:
                main = soup.select_one("#landingImage")
                if main and main.get("src"):
                    imgs = [main["src"]]
            data["images"] = imgs

        # ── ASIN ─────────────────────────────────────────────
        asin_m = re.search(r"/(?:dp|product|gp/product)/([A-Z0-9]{10})", url)
        asin   = asin_m.group(1) if asin_m else None
        data["asin"] = asin or ""

        # ── Review images ─────────────────────────────────────
        product_img_set = set(data.get("images", []))

        def _scrape_review_imgs(html_text, soup_obj):
            seen, found = set(), []
            def _add(u):
                if not u: return
                u = u.split("?")[0]
                if "media-amazon.com/images/I/" not in u: return
                u = re.sub(r"\._[A-Z0-9_,]+_\.", "._SL1000_.", u)
                if u not in seen: seen.add(u); found.append(u)
            for el in soup_obj.select("[data-lazyimagesource]"):
                _add(el.get("data-lazyimagesource", ""))
            for el in soup_obj.select("[data-mediaid]"):
                mid = el.get("data-mediaid", "").strip()
                if mid and re.match(r"^[A-Za-z0-9+/]{8,20}$", mid):
                    _add(f"https://m.media-amazon.com/images/I/{mid}.jpg")
            for img in soup_obj.select('img[alt^="Customer Image"]'):
                src = img.get("src") or img.get("data-src") or ""
                if "transparent-pixel" in src or "grey-pixel" in src: continue
                _add(src)
            for img in soup_obj.select("[data-hook='review-image-tile'] img, [data-hook='review'] img, #cm_cr-review_list img"):
                if img.find_parent(class_=re.compile(r"a-profile|avatar", re.I)): continue
                if img.find_parent(attrs={"data-hook": "genome-widget"}): continue
                src = img.get("src") or img.get("data-src") or ""
                if "transparent-pixel" in src or "grey-pixel" in src: continue
                if re.search(r"\._(?:SX|SY|UX|UY)[1-4]\d[_.]", src): continue
                if re.search(r"_UR\d{1,2},\d{1,2}_", src): continue
                _add(src)
            if not found:
                for _t, large in re.findall(
                    r'"thumb"\s*:\s*"(https://[^"]+)"[^}]{0,300}?"large"\s*:\s*"(https://[^"]+)"', html_text
                ):
                    if not re.search(r"\._(?:SX|SY)[1-4]\d[_.]", large): _add(large)
            return found

        rev_imgs = _scrape_review_imgs(r.text, soup)
        if asin:
            try:
                rev_r    = cf_requests.get(
                    f"https://www.amazon.com/product-reviews/{asin}"
                    f"?filterByStar=all_stars&mediaType=media_reviews_only&pageNumber=1",
                    impersonate="chrome120", timeout=15,
                    headers={"Accept-Language": "en-US,en;q=0.9"})
                rev_soup = BeautifulSoup(rev_r.text, "html.parser")
                rev_imgs += _scrape_review_imgs(rev_r.text, rev_soup)
            except Exception:
                pass
        data["review_images"] = [u for u in list(dict.fromkeys(rev_imgs)) if u not in product_img_set]

        # ── Customers Say ─────────────────────────────────────
        customers_say = "N/A"
        for sel in ("[data-testid='overall-summary']",
                    "[data-hook='cr-insights-widget-summary']",
                    ".cr-lighthouse-summary",
                    "[data-hook='cr-insights-widget-aspects']"):
            el = soup.select_one(sel)
            if el:
                text = re.sub(r"^Customers\s+say\s*", "", el.get_text(strip=True), flags=re.IGNORECASE).strip()
                if text: customers_say = text; break
        data["customers_say"] = {"summary": customers_say}

        # ── Seller info ───────────────────────────────────────
        seller_name = "N/A"
        for sel in ("#merchant-info a", "#sellerProfileTriggerId",
                    "#tabular-buybox [tabindex='0']", "#buybox-see-all-buying-choices-announce"):
            el = soup.select_one(sel)
            if el:
                t = el.get_text(strip=True)
                if t and len(t) < 80:
                    seller_name = t; break
        # Check if sold directly by Amazon
        buybox_txt = (soup.select_one("#tabular-buybox-container") or
                      soup.select_one("#merchant-info") or
                      soup.select_one("#desktop_buyBox"))
        sold_by_amazon = "Amazon" in (buybox_txt.get_text() if buybox_txt else "")
        data["seller"] = {"name": seller_name, "is_amazon": sold_by_amazon}

        # ── Arrival / delivery date ───────────────────────────
        arrival = "N/A"
        for sel in ("#mir-layout-DELIVERY_BLOCK span.a-text-bold",
                    "#ddmDeliveryMessage .a-text-bold",
                    "[data-csa-c-delivery-promise-type] .a-text-bold",
                    "#deliveryBlockMessage .a-text-bold"):
            el = soup.select_one(sel)
            if el:
                arrival = el.get_text(strip=True); break
        if arrival == "N/A":
            # Broader fallback — grab first delivery block text
            for sel in ("#mir-layout-DELIVERY_BLOCK", "#ddmDeliveryMessage"):
                el = soup.select_one(sel)
                if el:
                    t = el.get_text(" ", strip=True)[:120]
                    if t: arrival = t; break
        data["arrival_date"] = arrival

        # ── Variants ─────────────────────────────────────────
        variants: dict = {}
        for grp in soup.select("#twister .a-form-group, #variation_color_name, #variation_size_name"):
            label = grp.select_one(".a-form-label, .a-declarative label")
            opts  = [li.get_text(strip=True) for li in grp.select("li")
                     if li.get_text(strip=True) and len(li.get_text(strip=True)) < 50]
            # Fallback: span/option text
            if not opts:
                opts = [s.get_text(strip=True) for s in grp.select("span.selection, option")
                        if s.get_text(strip=True)]
            if label and opts:
                variants[label.get_text(strip=True).rstrip(":")] = opts[:20]
        data["variants"] = variants

        # ── Frequently bought together ────────────────────────
        fbt = []
        for item in soup.select("#frequently-bought-together .a-list-item, "
                                 "#sims-fbt .a-list-item"):
            name_el  = item.select_one(".a-truncate-full, .a-size-small.a-color-base")
            price_el = item.select_one(".a-price .a-offscreen")
            img_el   = item.select_one("img")
            if name_el:
                fbt.append({
                    "name":  name_el.get_text(strip=True)[:80],
                    "price": price_el.get_text(strip=True) if price_el else "N/A",
                    "img":   img_el.get("src", "") if img_el else "",
                })
        data["frequently_bought_together"] = fbt[:4]

        # ── Brand / availability / features / description / categories ──
        brand = soup.select_one("#bylineInfo")
        data["brand"] = brand.get_text(strip=True) if brand else "N/A"

        avail = soup.select_one("#availability span")
        data["availability"] = avail.get_text(strip=True) if avail else "N/A"

        data["features"] = [
            li.get_text(strip=True)
            for li in soup.select("#feature-bullets li span.a-list-item")
            if li.get_text(strip=True)
        ]

        desc = soup.select_one("#productDescription")
        data["description"] = desc.get_text(strip=True) if desc else "N/A"

        crumbs = [c.get_text(strip=True)
                  for c in soup.select("#wayfinding-breadcrumbs_container li span")
                  if c.get_text(strip=True) not in ("", "›")]
        data["categories"] = " > ".join(crumbs) if crumbs else "N/A"

        data["_debug_histogram_html"] = str(soup.select_one("#histogramTable") or "")[:3000]

        # ── Used offers (separate request) ────────────────────
        used_offers = []
        if asin:
            try:
                used_r    = cf_requests.get(
                    f"https://www.amazon.com/gp/offer-listing/{asin}/?f_used=true",
                    impersonate="chrome120", timeout=15,
                    headers={"Accept-Language": "en-US,en;q=0.9"})
                used_soup = BeautifulSoup(used_r.text, "html.parser")
                for offer in used_soup.select(".a-row.olpOffer, [data-asin] .a-section")[:6]:
                    price_el     = offer.select_one(".olpOfferPrice, .a-price .a-offscreen")
                    ship_el      = offer.select_one(".olpShippingPrice")
                    free_ship_el = offer.select_one(".olpFreeShipping, .a-color-success")
                    cond_el      = offer.select_one(".olpCondition, .a-size-medium.a-color-base")
                    seller_el    = offer.select_one(".olpSellerName a, .a-profile-name")
                    if not price_el:
                        continue
                    price_str = price_el.get_text(strip=True)
                    if free_ship_el and "free" in free_ship_el.get_text(strip=True).lower():
                        ship_str = "FREE"
                    elif ship_el:
                        ship_str = ship_el.get_text(strip=True)
                    else:
                        ship_str = "FREE"
                    cond_str   = cond_el.get_text(strip=True)[:40] if cond_el else "Used"
                    seller_str = seller_el.get_text(strip=True)[:40] if seller_el else ""
                    used_offers.append({
                        "price":   price_str,
                        "ship":    ship_str,
                        "cond":    cond_str,
                        "seller":  seller_str,
                    })
            except Exception:
                pass
        data["used_offers"] = used_offers

        # ── Review sentiment (5★ praise + 1★ complaints) ──────
        sentiment = {"positive": [], "negative": []}
        if asin:
            for star, key in (("five_star", "positive"), ("one_star", "negative")):
                try:
                    sr   = cf_requests.get(
                        f"https://www.amazon.com/product-reviews/{asin}?filterByStar={star}&pageNumber=1",
                        impersonate="chrome120", timeout=12,
                        headers={"Accept-Language": "en-US,en;q=0.9"})
                    ss   = BeautifulSoup(sr.text, "html.parser")
                    body = " ".join(
                        el.get_text(" ", strip=True)
                        for el in ss.select('[data-hook="review-body"]')
                    )
                    sentiment[key] = _keywords(body, n=8)
                except Exception:
                    pass
        data["review_sentiment"] = sentiment

    except Exception as exc:
        data["_error"] = str(exc)

    return data


# ─────────────────────────────────────────────────────────────
# Diff helper
# ─────────────────────────────────────────────────────────────
def _diff_html(idx, products, get_val, fmt, higher_is_better=True):
    cur = get_val(products[idx])
    if cur is None:
        return ""
    html = ""
    for j, other in enumerate(products):
        if j == idx: continue
        other = get_val(other)
        if other is None: continue
        diff  = cur - other
        color = ("green" if diff > 0 else "red" if diff < 0 else "gray") if higher_is_better \
                else ("green" if diff < 0 else "red" if diff > 0 else "gray")
        sign  = "+" if diff > 0 else "-" if diff < 0 else "±"
        html += f"<span style='color:{color};font-size:0.82em'> [{j+1}]{sign}{fmt(abs(diff))}</span>"
    return html


# ─────────────────────────────────────────────────────────────
# Best value scorer
# ─────────────────────────────────────────────────────────────
def _compute_best_value(products):
    """Score each product: price (40%) > review count (30%) > rating (20%) > arrival (10%)."""
    def norm(vals, higher_better=True):
        valid = [v for v in vals if v is not None]
        if len(valid) < 2:
            return [0.5 if v is not None else None for v in vals]
        mn, mx = min(valid), max(valid)
        if mx == mn:
            return [0.5 if v is not None else None for v in vals]
        return [((v - mn) / (mx - mn) if higher_better else (mx - v) / (mx - mn))
                if v is not None else None for v in vals]

    prices   = [_price_float(p.get("json", {}).get("pricing", "")) for p in products]
    ratings  = [_price_float(p.get("json", {}).get("average_rating", "")) for p in products]
    rev_cnts = [p.get("json", {}).get("total_reviews") for p in products]

    # Arrival: extract first number (day of month) as a rough proxy for sooner = better
    def _arrival_days(p):
        txt = p.get("json", {}).get("arrival_date", "")
        m   = re.search(r"\b(\d{1,2})\b", txt)
        return int(m.group(1)) if m else None
    arrivals = [_arrival_days(p) for p in products]

    p_norm = norm(prices,   higher_better=False)
    r_norm = norm(ratings,  higher_better=True)
    c_norm = norm(rev_cnts, higher_better=True)
    a_norm = norm(arrivals, higher_better=False)

    scores = []
    for i in range(len(products)):
        parts = [
            (p_norm[i], 0.40),
            (c_norm[i], 0.30),
            (r_norm[i], 0.20),
            (a_norm[i], 0.10),
        ]
        total_w = sum(w for v, w in parts if v is not None)
        if total_w == 0:
            scores.append(None)
        else:
            s = sum(v * w for v, w in parts if v is not None) / total_w
            scores.append(round(s * 100))
    return scores


# ─────────────────────────────────────────────────────────────
# Diffs + best value — called each render
# ─────────────────────────────────────────────────────────────
def update_all_diffs():
    products = st.session_state.product_data

    for p in products:
        p["pricing_float"] = _price_float(p.get("json", {}).get("pricing", ""))
    for idx in range(len(products)):
        products[idx]["price_diff_html"] = _diff_html(
            idx, products, get_val=lambda p: p.get("pricing_float"),
            fmt=lambda v: f"${v:.2f}", higher_is_better=False)

    for p in products:
        p["rating_float"] = _price_float(p.get("json", {}).get("average_rating", ""))
    for idx in range(len(products)):
        products[idx]["rating_diff_html"] = _diff_html(
            idx, products, get_val=lambda p: p.get("rating_float"),
            fmt=lambda v: f"{v:.1f}", higher_is_better=True)

    for p in products:
        pj   = p.get("json", {})
        pct4 = pj.get("4_star_percentage") or 0
        pct5 = pj.get("5_star_percentage") or 0
        p["positive_pct"] = (pct4 + pct5) if (pct4 or pct5) else None
    for idx in range(len(products)):
        products[idx]["positive_pct_diff_html"] = _diff_html(
            idx, products, get_val=lambda p: p.get("positive_pct"),
            fmt=lambda v: f"{int(v)}%", higher_is_better=True)

    # Best value
    scores  = _compute_best_value(products)
    medals  = ["🏆", "🥈", "🥉"]
    ranked  = sorted(
        [(i, s) for i, s in enumerate(scores) if s is not None],
        key=lambda x: -x[1]
    )
    for p in products:
        p["best_value_score"]  = None
        p["best_value_medal"]  = ""
        p["best_value_rank"]   = None
    for rank, (i, s) in enumerate(ranked):
        products[i]["best_value_score"] = s
        products[i]["best_value_medal"] = medals[rank] if rank < 3 else f"#{rank+1}"
        products[i]["best_value_rank"]  = rank + 1


# ─────────────────────────────────────────────────────────────
# CSV export helper
# ─────────────────────────────────────────────────────────────
def _build_csv(products) -> str:
    buf     = io.StringIO()
    writer  = csv.writer(buf)
    headers = ["Field"] + [f"Product {i+1}" for i in range(len(products))]
    writer.writerow(headers)
    fields_map = {
        "Name":         lambda d: d.get("name", ""),
        "Price":        lambda d: d.get("pricing", ""),
        "Rating":       lambda d: d.get("average_rating", ""),
        "Reviews":      lambda d: str(d.get("total_reviews", "")),
        "Brand":        lambda d: d.get("brand", ""),
        "Availability": lambda d: d.get("availability", ""),
        "Seller":       lambda d: (d.get("seller") or {}).get("name", ""),
        "Arrival":      lambda d: d.get("arrival_date", ""),
        "Description":  lambda d: d.get("description", "")[:200],
        "URL":          lambda d: d.get("url", ""),
    }
    for label, fn in fields_map.items():
        row = [label]
        for p in products:
            pdata = p.get("json") or {}
            pdata["url"] = p.get("url", "")
            row.append(fn(pdata))
        writer.writerow(row)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────
# Per-product header
# ─────────────────────────────────────────────────────────────
def render_header(idx, product):
    num_cols  = st.session_state.num_columns
    label_col, url_col = st.columns([1, 6])
    with label_col:
        with st.popover(f" {idx + 1} ", use_container_width=True):
            if idx > 0 and st.button("⬅️ Move Left", key=f"move_left_{idx}"):
                st.session_state.product_data[idx - 1], st.session_state.product_data[idx] = \
                    st.session_state.product_data[idx], st.session_state.product_data[idx - 1]
                st.rerun()
            if idx < num_cols - 1 and st.button("➡️ Move Right", key=f"move_right_{idx}"):
                st.session_state.product_data[idx + 1], st.session_state.product_data[idx] = \
                    st.session_state.product_data[idx], st.session_state.product_data[idx + 1]
                st.rerun()
            if st.button("🗑️ Remove", key=f"remove_{idx}"):
                st.session_state.product_data.pop(idx)
                st.session_state.num_columns -= 1
                st.rerun()

    with url_col:
        url = st.text_input("", value=product.get("url", ""),
                            placeholder="Paste Amazon URL…",
                            key=f"url_{idx}", label_visibility="collapsed")

    if url != product.get("url"):
        st.session_state.product_data[idx]["url"] = url
        st.session_state.product_data[idx].pop("json", None)
        st.rerun()
    st.session_state.product_data[idx]["url"] = url

    btn_l, btn_r = st.columns(2)
    with btn_l:
        if url:
            st.markdown(
                f'<a href="{url}" target="_blank" style="display:flex;align-items:center;'
                f'justify-content:center;height:38px;background:#262730;border:1px solid '
                f'rgba(250,250,250,0.2);border-radius:6px;text-decoration:none;font-size:1.1rem">🛒</a>',
                unsafe_allow_html=True)
        else:
            st.markdown('<div style="height:38px;background:#1a1a1a;border-radius:6px;'
                        'border:1px solid #333;opacity:0.4"></div>', unsafe_allow_html=True)
    with btn_r:
        if st.button("🔄", key=f"refresh_{idx}", use_container_width=True, help="Refresh"):
            st.cache_data.clear()
            st.session_state.product_data[idx].pop("json", None)
            st.rerun()

    if url and "json" not in product:
        with st.spinner("Loading…"):
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()


# ─────────────────────────────────────────────────────────────
# Gallery (lightbox with prev/next)
# ─────────────────────────────────────────────────────────────
_LIGHTBOX_JS = """
function lbOpen(src, allSrcs, startIdx) {
    var par = window.parent;
    var doc = par.document;
    var ov  = doc.getElementById('__lb_ov');
    if (!ov) {
        ov = doc.createElement('div');
        ov.id = '__lb_ov';
        ov.style.cssText = 'display:none;position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:2147483647;align-items:center;justify-content:center;';
        ov.addEventListener('click', function(e){ if(e.target===ov) par.__lbClose(); });
        function mkBtn(id, html, extra) {
            var b = doc.createElement('button');
            b.id = id; b.innerHTML = html;
            b.style.cssText = 'position:fixed;color:#fff;background:rgba(255,255,255,0.13);border:none;border-radius:50%;width:52px;height:52px;font-size:1.5rem;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .18s;' + extra;
            b.onmouseenter = function(){ this.style.background='rgba(255,255,255,0.28)'; };
            b.onmouseleave = function(){ this.style.background='rgba(255,255,255,0.13)'; };
            return b;
        }
        var prev = mkBtn('__lb_prev','&#10094;','left:16px;top:50%;transform:translateY(-50%);');
        var next = mkBtn('__lb_next','&#10095;','right:16px;top:50%;transform:translateY(-50%);');
        var cls  = mkBtn('__lb_cls','&#x2715;','top:14px;right:14px;width:40px;height:40px;font-size:1.1rem;');
        prev.addEventListener('click', function(e){ e.stopPropagation(); par.__lbNav(-1); });
        next.addEventListener('click', function(e){ e.stopPropagation(); par.__lbNav(1); });
        cls.addEventListener('click',  function(e){ e.stopPropagation(); par.__lbClose(); });
        var img = doc.createElement('img');
        img.id = '__lb_img';
        img.style.cssText = 'max-width:86vw;max-height:84vh;border-radius:8px;object-fit:contain;box-shadow:0 8px 60px rgba(0,0,0,0.9);cursor:default;user-select:none;';
        img.addEventListener('click', function(e){ e.stopPropagation(); });
        var ctr = doc.createElement('div');
        ctr.id = '__lb_ctr';
        ctr.style.cssText = 'position:fixed;bottom:18px;left:50%;transform:translateX(-50%);color:rgba(255,255,255,0.75);font-size:0.85rem;font-family:system-ui,sans-serif;background:rgba(0,0,0,0.55);padding:3px 14px;border-radius:20px;pointer-events:none;white-space:nowrap;';
        ov.appendChild(prev); ov.appendChild(img); ov.appendChild(next); ov.appendChild(cls); ov.appendChild(ctr);
        doc.body.appendChild(ov);
        doc.addEventListener('keydown', function(e){
            if (e.key==='Escape') par.__lbClose();
            if (e.key==='ArrowLeft')  par.__lbNav && par.__lbNav(-1);
            if (e.key==='ArrowRight') par.__lbNav && par.__lbNav(1);
        });
    }
    par.__lbImgs = (allSrcs && allSrcs.length) ? allSrcs : [src];
    par.__lbIdx  = (typeof startIdx === 'number') ? startIdx : 0;
    par.__lbClose = function() { var o=doc.getElementById('__lb_ov'); if(o) o.style.display='none'; };
    par.__lbNav   = function(dir) {
        par.__lbIdx = (par.__lbIdx + dir + par.__lbImgs.length) % par.__lbImgs.length;
        var i=doc.getElementById('__lb_img'), c=doc.getElementById('__lb_ctr');
        if(i) i.src = par.__lbImgs[par.__lbIdx];
        if(c) c.textContent = (par.__lbIdx+1)+' / '+par.__lbImgs.length;
    };
    var imgEl=doc.getElementById('__lb_img'), ctrEl=doc.getElementById('__lb_ctr');
    var prvEl=doc.getElementById('__lb_prev'), nxtEl=doc.getElementById('__lb_next');
    if(imgEl) imgEl.src = src;
    if(ctrEl) ctrEl.textContent = (par.__lbIdx+1)+' / '+par.__lbImgs.length;
    var showNav = par.__lbImgs.length > 1;
    if(prvEl) prvEl.style.display = showNav ? 'flex' : 'none';
    if(nxtEl) nxtEl.style.display = showNav ? 'flex' : 'none';
    ov.style.display = 'flex';
}
"""

_GALLERY_CSS = """<style>
* { box-sizing:border-box; margin:0; padding:0; }
body { background:transparent; overflow-x:hidden; }
.gallery { display:flex; overflow-x:auto; gap:8px; padding:4px 2px 10px 2px;
           scrollbar-width:thin; scrollbar-color:#555 transparent; }
.gallery::-webkit-scrollbar { height:5px; }
.gallery::-webkit-scrollbar-thumb { background:#555; border-radius:3px; }
.gallery img { height:130px; border-radius:6px; flex-shrink:0; cursor:zoom-in;
               transition:transform .14s ease, box-shadow .14s ease; display:block; }
.gallery img:hover { transform:scale(1.05); box-shadow:0 4px 18px rgba(0,0,0,.55); }
</style>"""

def _render_gallery(imgs: list, label: str = "Images") -> None:
    if not imgs:
        st.markdown(f"<span style='color:#666;font-size:0.9em'>{label}: <em>not available</em></span>",
                    unsafe_allow_html=True)
        return
    imgs_json = json.dumps(imgs)
    thumbs = "".join(
        f'<img src="{u}" alt="" loading="lazy" onclick="lbOpen(this.src,_imgs,{i})">'
        for i, u in enumerate(imgs)
    )
    components.html(
        _GALLERY_CSS + f'<div class="gallery">{thumbs}</div>'
        + f"<script>var _imgs={imgs_json};\n{_LIGHTBOX_JS}</script>",
        height=162, scrolling=False
    )


# ─────────────────────────────────────────────────────────────
# Field renderer
# ─────────────────────────────────────────────────────────────
def render_field_cell(field, product):
    url          = product.get("url", "")
    product_data = product.get("json")

    if not url:          st.empty(); return
    if product_data is None: st.caption("⏳ Loading…"); return
    if "_error" in product_data: st.warning(f"⚠️ {product_data['_error']}"); return

    def _na(label):
        st.markdown(f"<span style='color:#666;font-size:0.9em'>{label}: <em>not available</em></span>",
                    unsafe_allow_html=True)

    # ── BestValue ─────────────────────────────────────────────
    if field == "BestValue":
        score = product.get("best_value_score")
        medal = product.get("best_value_medal", "")
        rank  = product.get("best_value_rank")
        if score is None:
            _na("Best Value")
            return
        bar_color = "#2ecc71" if rank == 1 else "#f39c12" if rank == 2 else "#95a5a6"
        st.markdown(
            f"<div style='background:{bar_color}22;border:1px solid {bar_color}55;"
            f"border-radius:8px;padding:8px 12px;display:flex;align-items:center;gap:10px'>"
            f"<span style='font-size:1.6rem'>{medal}</span>"
            f"<div><div style='font-size:0.75em;color:#aaa;margin-bottom:2px'>BEST VALUE SCORE</div>"
            f"<div style='font-size:1.3em;font-weight:bold;color:{bar_color}'>{score}/100</div></div>"
            f"<div style='margin-left:auto;font-size:0.7em;color:#888;line-height:1.5'>"
            f"Price&nbsp;40%<br>Reviews&nbsp;30%<br>Rating&nbsp;20%<br>Arrival&nbsp;10%</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    # ── Title ─────────────────────────────────────────────────
    elif field == "Title":
        v = str(product_data.get("name") or "")
        if not v or v == "N/A": _na("Title")
        else:
            st.markdown(f"<div style='font-size:14pt;font-weight:bold'>"
                        f"{v[:150]}{'...' if len(v)>150 else ''}</div>", unsafe_allow_html=True)

    # ── Price ─────────────────────────────────────────────────
    elif field == "Price":
        price = product_data.get("pricing", "")
        diff  = product.get("price_diff_html", "")
        arr   = product_data.get("arrival_date", "")
        if not price or price == "N/A": _na("Price")
        else:
            html = f"💰 <strong>{price}</strong> &nbsp;{diff}"
            if arr and arr != "N/A":
                html += f"<br><span style='font-size:0.82em;color:#aaa'>🚚 {arr}</span>"
            st.markdown(f"<div style='line-height:1.8'>{html}</div>", unsafe_allow_html=True)

    # ── UsedPrices ────────────────────────────────────────────
    elif field == "UsedPrices":
        offers = product_data.get("used_offers", [])
        if not offers:
            _na("Used prices")
            return
        rows = []
        for o in offers:
            item_f = _price_float(o["price"])
            ship_s = o["ship"]
            ship_f = 0.0 if ship_s.upper() == "FREE" else (_price_float(ship_s) or 0.0)
            if item_f is None:
                continue
            total  = item_f + ship_f
            cond   = o.get("cond", "Used")

            if ship_f == 0.0:
                ship_html = "<span style='color:#aaa'>FREE shipping</span>"
            else:
                ship_html = f"+ ${ship_f:.2f} <span style='font-size:1em'>📦</span>"

            rows.append(
                f"<div style='margin-bottom:6px'>"
                f"<span style='font-size:0.78em;color:#888'>{cond}</span><br>"
                f"<span>${item_f:.2f}</span> {ship_html}"
                f" = <strong style='color:#2ecc71'>${total:.2f}</strong>"
                f"</div>"
            )
        if rows:
            st.markdown(
                "<div style='font-size:0.92em'>" + "".join(rows) + "</div>",
                unsafe_allow_html=True
            )
        else:
            _na("Used prices")

    # ── PriceHistory ──────────────────────────────────────────
    elif field == "PriceHistory":
        asin = product_data.get("asin", "")
        if not asin:
            _na("Price history")
            return
        chart_url = f"https://charts.camelcamelcamel.com/us/{asin}/amazon-new-used.png?forceNew=1"
        ccc_url   = f"https://camelcamelcamel.com/product/{asin}"
        st.markdown(
            f'<a href="{ccc_url}" target="_blank">'
            f'<img src="{chart_url}" style="width:100%;border-radius:6px;cursor:pointer" '
            f'alt="Price history chart" title="View on CamelCamelCamel"/></a>',
            unsafe_allow_html=True
        )

    # ── Rating ────────────────────────────────────────────────
    elif field == "Rating":
        rating    = product_data.get("average_rating", "")
        raw_count = product_data.get("total_reviews")
        count_str = (f"{(raw_count//100)*100}+" if isinstance(raw_count, int) and raw_count >= 100
                     else str(raw_count) if isinstance(raw_count, int) else None)
        pct_4 = int(product_data.get("4_star_percentage") or 0)
        pct_5 = int(product_data.get("5_star_percentage") or 0)
        r_diff   = product.get("rating_diff_html", "")
        pos_diff = product.get("positive_pct_diff_html", "")
        if not rating or rating == "N/A": _na("Rating")
        else:
            lines = f"⭐ <strong>{rating}</strong>"
            lines += f" &nbsp; [👤 {count_str}]" if count_str else " &nbsp; [👤 N/A]"
            if r_diff: lines += f"<br><span style='font-size:0.85em'>{r_diff}</span>"
            if pct_4 or pct_5:
                combined = pct_4 + pct_5
                lines += (f"<br><br>[5⭐ &thinsp;{pct_5}%] &nbsp;+&nbsp; [4⭐ &thinsp;{pct_4}%]"
                          f" &nbsp;—&nbsp; <em>({combined}% positive)</em>")
                if pos_diff: lines += f"<br><span style='font-size:0.85em'>{pos_diff}</span>"
            else:
                lines += "<br><span style='color:#666;font-size:0.85em'><em>Star breakdown: N/A</em></span>"
            st.markdown(f"<div style='line-height:1.9'>{lines}</div>", unsafe_allow_html=True)

    # ── Customers Say ─────────────────────────────────────────
    elif field == "Customers Say":
        summary = (product_data.get("customers_say") or {}).get("summary", "")
        if not summary or summary == "N/A": _na("Customers say")
        else: st.markdown(summary)

    # ── ReviewSentiment ───────────────────────────────────────
    elif field == "ReviewSentiment":
        sent = product_data.get("review_sentiment", {})
        pos  = sent.get("positive", [])
        neg  = sent.get("negative", [])
        if not pos and not neg: _na("Review sentiment"); return
        html = ""
        if pos:
            tags = "".join(
                f"<span style='background:#1a3a2a;color:#2ecc71;border-radius:4px;"
                f"padding:2px 7px;margin:2px;font-size:0.82em;display:inline-block'>{w}</span>"
                for w in pos
            )
            html += f"<div style='margin-bottom:6px'><span style='font-size:0.75em;color:#aaa'>👍 PRAISED FOR</span><br>{tags}</div>"
        if neg:
            tags = "".join(
                f"<span style='background:#3a1a1a;color:#e74c3c;border-radius:4px;"
                f"padding:2px 7px;margin:2px;font-size:0.82em;display:inline-block'>{w}</span>"
                for w in neg
            )
            html += f"<div><span style='font-size:0.75em;color:#aaa'>👎 COMPLAINTS ABOUT</span><br>{tags}</div>"
        st.markdown(html, unsafe_allow_html=True)

    # ── SellerInfo ────────────────────────────────────────────
    elif field == "SellerInfo":
        seller = product_data.get("seller") or {}
        name   = seller.get("name", "N/A")
        is_amz = seller.get("is_amazon", False)
        if name == "N/A" and not is_amz: _na("Seller"); return
        badge = ("<span style='background:#ff9900;color:#000;border-radius:4px;"
                 "padding:1px 6px;font-size:0.78em;font-weight:bold'>amazon</span>"
                 if is_amz else
                 "<span style='background:#333;color:#ccc;border-radius:4px;"
                 "padding:1px 6px;font-size:0.78em'>3rd party</span>")
        st.markdown(f"<div>🏪 {badge} &nbsp;<span style='font-size:0.9em'>{name}</span></div>",
                    unsafe_allow_html=True)

    # ── Variants ─────────────────────────────────────────────
    elif field == "Variants":
        variants = product_data.get("variants") or {}
        if not variants: _na("Variants"); return
        html = ""
        for vtype, opts in variants.items():
            pills = "".join(
                f"<span style='background:#1e2a3a;color:#7eb8e8;border-radius:4px;"
                f"padding:2px 8px;margin:2px;font-size:0.82em;display:inline-block'>{o}</span>"
                for o in opts[:12]
            )
            more = f" <span style='color:#666;font-size:0.78em'>+{len(opts)-12} more</span>" if len(opts)>12 else ""
            html += (f"<div style='margin-bottom:6px'>"
                     f"<span style='font-size:0.75em;color:#aaa'>{vtype.upper()}</span><br>"
                     f"{pills}{more}</div>")
        st.markdown(html, unsafe_allow_html=True)

    # ── FrequentlyBoughtTogether ──────────────────────────────
    elif field == "FrequentlyBoughtTogether":
        fbt = product_data.get("frequently_bought_together") or []
        if not fbt: _na("Frequently bought together"); return
        cols = st.columns(len(fbt))
        for col, item in zip(cols, fbt):
            with col:
                if item.get("img"):
                    st.image(item["img"], use_container_width=True)
                st.markdown(
                    f"<div style='font-size:0.78em;line-height:1.3'>{item['name']}</div>"
                    f"<div style='font-size:0.85em;color:#f90;font-weight:bold'>{item['price']}</div>",
                    unsafe_allow_html=True
                )

    # ── ImageGallery ──────────────────────────────────────────
    elif field == "ImageGallery":
        _render_gallery(product_data.get("images", []), "Product images")

    # ── ReviewImages ──────────────────────────────────────────
    elif field == "ReviewImages":
        _render_gallery(product_data.get("review_images", []), "Customer review images")

    # ── Generic fallback ──────────────────────────────────────
    else:
        value = product_data.get(field.lower(), "")
        if isinstance(value, list):
            if value:
                for item in value: st.markdown(f"• {item}")
            else: _na(field)
        elif not value or value == "N/A": _na(field)
        else: st.write(value)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
display_field_selector()

# ── Top toolbar: Add column | Share link | Export CSV ─────────
tb_add, tb_share, tb_csv = st.columns([2, 2, 2])

with tb_add:
    if st.button("➕ Add Product Column", use_container_width=True):
        st.session_state.num_columns += 1
        st.rerun()

with tb_share:
    if st.button("🔗 Copy Share Link", use_container_width=True):
        urls = [p.get("url", "") for p in st.session_state.product_data if p.get("url")]
        if urls:
            st.query_params["urls"] = "|".join(urls)
            st.success("Link updated — copy from your browser's address bar!", icon="✅")
        else:
            st.warning("No URLs loaded yet.")

with tb_csv:
    all_loaded = all("json" in p for p in st.session_state.product_data if p.get("url"))
    csv_data   = _build_csv(st.session_state.product_data) if all_loaded else ""
    st.download_button(
        "📥 Export CSV",
        data=csv_data,
        file_name="amazon_comparison.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not all_loaded,
    )

while len(st.session_state.product_data) < st.session_state.num_columns:
    st.session_state.product_data.append({"url": ""})

update_all_diffs()

num_cols = st.session_state.num_columns
products = st.session_state.product_data

st.markdown("<div class='field-divider'></div>", unsafe_allow_html=True)
header_cols = st.columns(num_cols)
for i in range(num_cols):
    with header_cols[i]:
        render_header(i, products[i])

for field in ALL_FIELDS:
    if field not in st.session_state.visible_fields:
        continue
    st.markdown("<div class='field-divider'></div>", unsafe_allow_html=True)
    row = st.columns(num_cols)
    for i in range(num_cols):
        with row[i]:
            render_field_cell(field, products[i])

# ─────────────────────────────────────────────────────────────
# Debug panel
# ─────────────────────────────────────────────────────────────
if st.session_state.show_debug:
    st.divider()
    st.subheader("🔍 Debug")
    debug_cols = st.columns(num_cols)
    for i in range(num_cols):
        with debug_cols[i]:
            pdata = products[i].get("json", {})
            st.markdown(f"**Column {i + 1}**")
            if not pdata: st.write("No data yet."); continue
            for k in ["name","pricing","average_rating","total_reviews",
                      "5_star_percentage","4_star_percentage","asin","seller","arrival_date"]:
                st.write(f"**{k}:** `{pdata.get(k, 'not found')}`")
            st.write("**histogram HTML:**")
            st.code(pdata.get("_debug_histogram_html", "not captured"), language="html")
