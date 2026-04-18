# v0.66 — curl_cffi + BeautifulSoup (no Playwright, no ScraperAPI)
# Adds: variant selector (color / size / style) per product column
#
# requirements.txt:
#   streamlit
#   curl_cffi
#   beautifulsoup4

import json
import re
import streamlit as st
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
st.title("🛍️ Amazon Product Comparison")

# ── Row divider style injected once ───────────────────────────
st.markdown(
    """
    <style>
    .field-divider { border-top: 1px solid #2a2a2a; margin: 4px 0 4px 0; }
    div[data-testid="column"] { padding: 4px 8px !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

DEFAULT_FIELDS = ["Title", "Price", "Rating", "Customers Say", "ImageGallery"]
ALL_FIELDS = [
    "Title",
    "Price",
    "Rating",
    "Customers Say",
    "ImageGallery",
    "Description",
    "Brand",
    "Availability",
    "Features",
    "Categories",
]

if "visible_fields"  not in st.session_state: st.session_state.visible_fields  = DEFAULT_FIELDS.copy()
if "product_data"    not in st.session_state: st.session_state.product_data    = []
if "num_columns"     not in st.session_state: st.session_state.num_columns     = 2
if "show_debug"      not in st.session_state: st.session_state.show_debug      = False


# ─────────────────────────────────────────────────────────────
# Checkbox sync helper
# ─────────────────────────────────────────────────────────────
def _sync_checkboxes_to_visible():
    """Push visible_fields into the individual chk_ keys so widgets reflect state."""
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
            all_selected = len(st.session_state.visible_fields) == len(ALL_FIELDS)
            st.session_state.visible_fields = [] if all_selected else ALL_FIELDS.copy()
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
# Variant parser helpers
# ─────────────────────────────────────────────────────────────
def _extract_balanced_braces(text: str, marker: str) -> str | None:
    """Locate marker in text, then return the balanced {...} object that follows it."""
    idx = text.find(marker)
    if idx == -1:
        return None
    brace_start = text.find("{", idx + len(marker))
    if brace_start == -1:
        return None
    depth = 0
    for i, ch in enumerate(text[brace_start:], brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start : i + 1]
    return None


def _parse_variants(raw_html: str) -> list[dict]:
    """
    Extract variant options from Amazon's embedded JSON blobs.

    Strategy 1 — dimensionValuesDisplayData
        Maps ASIN → [dimension values], e.g. {"B001": ["Black", "128 GB"], ...}
        This is the most reliable source; present on the majority of multi-variant listings.

    Strategy 2 — twister-js-init-dpx-data P.register block
        Falls back to a different schema used by some listings where
        dimensionValuesDisplayData is absent.

    Returns a list of {"asin": str, "label": str} dicts, or [] if none found.
    """
    variants = []

    # ── Strategy 1 ────────────────────────────────────────────
    raw_obj = _extract_balanced_braces(raw_html, '"dimensionValuesDisplayData"')
    if raw_obj:
        try:
            dd = json.loads(raw_obj)
            for asin, values in dd.items():
                # ASINs are always 10 alphanumeric chars; skip malformed keys
                if not isinstance(values, list) or len(asin) != 10:
                    continue
                label = " / ".join(str(v) for v in values if v)
                if label:
                    variants.append({"asin": asin, "label": label})
        except Exception:
            pass

    # ── Strategy 2: scan P.register('twister-js-init-dpx-data', ...) ────────
    if not variants:
        register_match = re.search(
            r"P\.register\(['\"]twister-js-init-dpx-data['\"],\s*(\{)",
            raw_html,
        )
        if register_match:
            # Extract the full JSON object starting at the matched brace
            brace_start = register_match.start(1)
            depth = 0
            end = brace_start
            for i, ch in enumerate(raw_html[brace_start:], brace_start):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            try:
                obj = json.loads(raw_html[brace_start : end + 1])
                # Look for a "variants" or "dimensionToAsinMap" sub-key
                for key in ("variants", "dimensionToAsinMap"):
                    sub = obj.get(key)
                    if isinstance(sub, dict):
                        for asin, meta in sub.items():
                            if len(asin) != 10:
                                continue
                            if isinstance(meta, dict):
                                label_parts = [
                                    str(meta.get(k, ""))
                                    for k in ("color", "size", "style", "edition")
                                    if meta.get(k)
                                ]
                                label = " / ".join(label_parts) or asin
                            else:
                                label = str(meta)
                            variants.append({"asin": asin, "label": label})
                        break
            except Exception:
                pass

    # De-duplicate by ASIN while preserving order
    seen = set()
    deduped = []
    for v in variants:
        if v["asin"] not in seen:
            seen.add(v["asin"])
            deduped.append(v)

    return deduped


def _asin_from_url(url: str) -> str | None:
    """Extract the 10-char ASIN from an Amazon product URL."""
    m = re.search(r"/dp/([A-Z0-9]{10})", url)
    return m.group(1) if m else None


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
        label      = a.get("aria-label", "")
        star_match = re.search(r"(\d+)\s+star", label, re.IGNORECASE)
        pct_val    = meter.get("aria-valuenow")
        if star_match and pct_val is not None:
            result[f"{int(star_match.group(1))}_star_percentage"] = int(pct_val)
    return result


# ─────────────────────────────────────────────────────────────
# Scraper
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_amazon_data(url: str) -> dict:
    data: dict = {}
    try:
        r = cf_requests.get(
            url, impersonate="chrome120", timeout=20,
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        soup = BeautifulSoup(r.text, "html.parser")

        title  = soup.select_one("#productTitle")
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

        # ── Customers Say ──────────────────────────────────────
        customers_say = "N/A"
        for sel in (
            "[data-testid='overall-summary']",
            "[data-hook='cr-insights-widget-summary']",
            ".cr-lighthouse-summary",
            "[data-hook='cr-insights-widget-aspects']",
        ):
            el = soup.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                text = re.sub(r"^Customers\s+say\s*", "", text, flags=re.IGNORECASE).strip()
                if text:
                    customers_say = text
                    break
        data["customers_say"] = {"summary": customers_say}

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

        crumbs = [
            c.get_text(strip=True)
            for c in soup.select("#wayfinding-breadcrumbs_container li span")
            if c.get_text(strip=True) not in ("", "›")
        ]
        data["categories"] = " > ".join(crumbs) if crumbs else "N/A"

        histogram_el = soup.select_one("#histogramTable")
        data["_debug_histogram_html"] = (
            str(histogram_el)[:3000] if histogram_el else "⚠️ #histogramTable not found"
        )

        # ── Variants ───────────────────────────────────────────
        data["variants"] = _parse_variants(r.text)

    except Exception as exc:
        data["_error"] = str(exc)

    return data


# ─────────────────────────────────────────────────────────────
# Diff helper
# ─────────────────────────────────────────────────────────────
def _diff_html(idx, products, get_val, fmt, higher_is_better=True):
    cur_val = get_val(products[idx])
    if cur_val is None:
        return ""
    html = ""
    for j, other in enumerate(products):
        if j == idx:
            continue
        other_val = get_val(other)
        if other_val is None:
            continue
        diff  = cur_val - other_val
        color = (
            ("green" if diff > 0 else "red" if diff < 0 else "gray")
            if higher_is_better
            else ("green" if diff < 0 else "red" if diff > 0 else "gray")
        )
        sign = "+" if diff > 0 else "-" if diff < 0 else "±"
        html += (
            f"<span style='color:{color};font-size:0.82em'>"
            f" [{j+1}]{sign}{fmt(abs(diff))}</span>"
        )
    return html


def update_all_diffs():
    products = st.session_state.product_data

    for p in products:
        try:
            p["pricing_float"] = float(
                str(p.get("json", {}).get("pricing", "")).replace("$", "").replace(",", "")
            )
        except Exception:
            p["pricing_float"] = None
    for idx in range(len(products)):
        products[idx]["price_diff_html"] = _diff_html(
            idx, products,
            get_val=lambda p: p.get("pricing_float"),
            fmt=lambda v: f"${v:.2f}",
            higher_is_better=False,
        )

    for p in products:
        try:
            p["rating_float"] = float(p.get("json", {}).get("average_rating", ""))
        except Exception:
            p["rating_float"] = None
    for idx in range(len(products)):
        products[idx]["rating_diff_html"] = _diff_html(
            idx, products,
            get_val=lambda p: p.get("rating_float"),
            fmt=lambda v: f"{v:.1f}",
            higher_is_better=True,
        )

    for p in products:
        pj   = p.get("json", {})
        pct4 = pj.get("4_star_percentage") or 0
        pct5 = pj.get("5_star_percentage") or 0
        p["positive_pct"] = (pct4 + pct5) if (pct4 or pct5) else None
    for idx in range(len(products)):
        products[idx]["positive_pct_diff_html"] = _diff_html(
            idx, products,
            get_val=lambda p: p.get("positive_pct"),
            fmt=lambda v: f"{int(v)}%",
            higher_is_better=True,
        )


# ─────────────────────────────────────────────────────────────
# Per-product header (URL bar + controls)
# ─────────────────────────────────────────────────────────────
def render_header(idx, product):
    num_cols = st.session_state.num_columns

    label_col, url_col = st.columns([1, 6])
    with label_col:
        with st.popover(f" {idx + 1} ", use_container_width=True):
            if idx > 0 and st.button("⬅️ Move Left", key=f"move_left_{idx}"):
                (st.session_state.product_data[idx - 1],
                 st.session_state.product_data[idx]) = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx - 1],
                )
                st.rerun()
            if idx < num_cols - 1 and st.button("➡️ Move Right", key=f"move_right_{idx}"):
                (st.session_state.product_data[idx + 1],
                 st.session_state.product_data[idx]) = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx + 1],
                )
                st.rerun()
            if st.button("🗑️ Remove", key=f"remove_{idx}"):
                st.session_state.product_data.pop(idx)
                st.session_state.num_columns -= 1
                st.rerun()

    with url_col:
        url = st.text_input(
            "", value=product.get("url", ""),
            placeholder="Paste Amazon URL…",
            key=f"url_{idx}", label_visibility="collapsed",
        )

    if url != product.get("url"):
        st.session_state.product_data[idx]["url"]      = url
        st.session_state.product_data[idx].pop("json",     None)
        st.session_state.product_data[idx].pop("variants", None)   # reset variants on new URL
        st.rerun()
    st.session_state.product_data[idx]["url"] = url

    btn_l, btn_r = st.columns(2)
    with btn_l:
        if url:
            st.markdown(
                f'<a href="{url}" target="_blank" style="'
                f'display:flex;align-items:center;justify-content:center;'
                f'height:38px;background:#262730;border:1px solid rgba(250,250,250,0.2);'
                f'border-radius:6px;text-decoration:none;font-size:1.1rem;cursor:pointer">'
                f'🛒</a>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="height:38px;background:#1a1a1a;border-radius:6px;'
                'border:1px solid #333;opacity:0.4"></div>',
                unsafe_allow_html=True,
            )
    with btn_r:
        if st.button("🔄", key=f"refresh_{idx}", use_container_width=True, help="Refresh"):
            st.cache_data.clear()
            st.session_state.product_data[idx].pop("json",     None)
            st.session_state.product_data[idx].pop("variants", None)
            st.rerun()

    # Trigger load if URL present but data missing
    if url and "json" not in product:
        with st.spinner("Loading…"):
            fetched = fetch_amazon_data(url)
            st.session_state.product_data[idx]["json"] = fetched
            # Store variants at product level so they survive variant-URL switches.
            # Only set on first load (or if currently empty) so the list doesn't
            # disappear while the new variant page is being fetched.
            if fetched.get("variants"):
                st.session_state.product_data[idx]["variants"] = fetched["variants"]
            st.rerun()


# ─────────────────────────────────────────────────────────────
# Variant selector row
# ─────────────────────────────────────────────────────────────
def render_variant_selector(idx: int, product: dict) -> None:
    """
    Render a selectbox listing all variants for this product column.
    Selecting a different variant swaps the URL to amazon.com/dp/{ASIN}
    and clears the cached product data so it re-fetches automatically.
    The variants list itself is preserved at the product level so it
    doesn't vanish while the new page loads.
    """
    variants = product.get("variants", [])
    if len(variants) <= 1:
        # Nothing to show — render a subtle placeholder so column heights stay aligned
        st.markdown(
            "<span style='color:#555;font-size:0.8em'>no variants detected</span>",
            unsafe_allow_html=True,
        )
        return

    labels = [v["label"] for v in variants]
    asins  = [v["asin"]  for v in variants]

    # Determine which variant is currently active based on the URL's ASIN
    current_asin = _asin_from_url(product.get("url", ""))
    try:
        current_index = asins.index(current_asin) if current_asin in asins else 0
    except ValueError:
        current_index = 0

    selected_index = st.selectbox(
        "Variant",
        options=range(len(labels)),
        format_func=lambda i: labels[i],
        index=current_index,
        key=f"variant_sel_{idx}",
        label_visibility="collapsed",
    )

    selected_asin = asins[selected_index]
    if selected_asin != current_asin:
        variant_url = f"https://www.amazon.com/dp/{selected_asin}"
        st.session_state.product_data[idx]["url"]  = variant_url
        st.session_state.product_data[idx].pop("json", None)
        # Keep "variants" so the dropdown doesn't disappear mid-load
        st.rerun()


# ─────────────────────────────────────────────────────────────
# Single field renderer for one product cell
# ─────────────────────────────────────────────────────────────
def render_field_cell(field, product):
    url          = product.get("url", "")
    product_data = product.get("json")

    if not url:
        st.empty()
        return
    if product_data is None:
        st.caption("⏳ Loading…")
        return
    if "_error" in product_data:
        st.warning(f"⚠️ {product_data['_error']}")
        return

    def _na(label):
        st.markdown(
            f"<span style='color:#666;font-size:0.9em'>{label}: "
            f"<em>not available</em></span>",
            unsafe_allow_html=True,
        )

    if field == "Title":
        value_str = str(product_data.get("name") or "")
        if not value_str or value_str == "N/A":
            _na("Title")
        else:
            st.markdown(
                f"<div style='font-size:14pt;font-weight:bold'>"
                f"{value_str[:150]}{'...' if len(value_str) > 150 else ''}</div>",
                unsafe_allow_html=True,
            )

    elif field == "Price":
        price     = product_data.get("pricing", "")
        diff_html = product.get("price_diff_html", "")
        if not price or price == "N/A":
            _na("Price")
        else:
            st.markdown(
                f"<div>💰 <strong>{price}</strong> &nbsp;{diff_html}</div>",
                unsafe_allow_html=True,
            )

    elif field == "Rating":
        rating      = product_data.get("average_rating", "")
        raw_count   = product_data.get("total_reviews")
        count_str   = (
            f"{(raw_count // 100) * 100}+" if isinstance(raw_count, int) and raw_count >= 100
            else str(raw_count) if isinstance(raw_count, int)
            else None
        )
        pct_4    = int(product_data.get("4_star_percentage") or 0)
        pct_5    = int(product_data.get("5_star_percentage") or 0)
        combined = pct_4 + pct_5

        r_diff   = product.get("rating_diff_html", "")
        pos_diff = product.get("positive_pct_diff_html", "")

        if not rating or rating == "N/A":
            _na("Rating")
        else:
            lines = f"⭐ <strong>{rating}</strong>"
            lines += f" &nbsp; [👤 {count_str}]" if count_str else " &nbsp; [👤 not available]"
            if r_diff:
                lines += f"<br><span style='font-size:0.85em'>{r_diff}</span>"
            if pct_4 or pct_5:
                lines += (
                    f"<br><br>"
                    f"[5⭐ &thinsp;{pct_5}%] &nbsp;+&nbsp; [4⭐ &thinsp;{pct_4}%]"
                    f" &nbsp;—&nbsp; <em>({combined}% positive)</em>"
                )
                if pos_diff:
                    lines += f"<br><span style='font-size:0.85em'>{pos_diff}</span>"
            else:
                lines += f"<br><span style='color:#666;font-size:0.85em'><em>Star breakdown: not available</em></span>"

            st.markdown(
                f"<div style='line-height:1.9'>{lines}</div>",
                unsafe_allow_html=True,
            )

    elif field == "Customers Say":
        summary = (product_data.get("customers_say") or {}).get("summary", "")
        if not summary or summary == "N/A":
            _na("Customers say")
        else:
            st.markdown(summary)

    elif field == "ImageGallery":
        imgs = product_data.get("images", [])
        if imgs:
            st.markdown(
                "<style>"
                ".scrolling-wrapper{display:flex;overflow-x:auto;padding-bottom:8px}"
                ".scrolling-wrapper img{height:140px;margin-right:8px;border-radius:6px}"
                "</style>"
                '<div class="scrolling-wrapper">'
                + "".join(f'<img src="{img}" alt="">' for img in imgs)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            _na("Images")

    else:
        value = product_data.get(field.lower(), "")
        if isinstance(value, list):
            if value:
                for item in value:
                    st.markdown(f"• {item}")
            else:
                _na(field)
        elif not value or value == "N/A":
            _na(field)
        else:
            st.write(value)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
display_field_selector()

if st.button("➕ Add Product Column"):
    st.session_state.num_columns += 1
    st.rerun()

while len(st.session_state.product_data) < st.session_state.num_columns:
    st.session_state.product_data.append({"url": ""})

update_all_diffs()

num_cols = st.session_state.num_columns
products = st.session_state.product_data

# ── Header row ────────────────────────────────────────────────
st.markdown("<div class='field-divider'></div>", unsafe_allow_html=True)
header_cols = st.columns(num_cols)
for i in range(num_cols):
    with header_cols[i]:
        render_header(i, products[i])

# ── Variant selector row ──────────────────────────────────────
# Only render the row if at least one column has variants available
any_variants = any(len(p.get("variants", [])) > 1 for p in products)
if any_variants:
    st.markdown("<div class='field-divider'></div>", unsafe_allow_html=True)
    variant_cols = st.columns(num_cols)
    for i in range(num_cols):
        with variant_cols[i]:
            render_variant_selector(i, products[i])

# ── Field rows ────────────────────────────────────────────────
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
            product_data = products[i].get("json", {})
            st.markdown(f"**Column {i + 1}**")
            if not product_data:
                st.write("No data yet.")
                continue
            for k in [
                "name", "pricing", "average_rating", "total_reviews",
                "5_star_percentage", "4_star_percentage",
                "3_star_percentage", "2_star_percentage", "1_star_percentage",
            ]:
                st.write(f"**{k}:** `{product_data.get(k, 'not found')}`")
            st.write("**Variants detected:**")
            st.json(products[i].get("variants", []))
            st.write("**histogram HTML:**")
            st.code(product_data.get("_debug_histogram_html", "not captured"), language="html")
