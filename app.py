# v0.62 — curl_cffi + BeautifulSoup (no Playwright, no ScraperAPI)
#
# requirements.txt:
#   streamlit
#   curl_cffi
#   beautifulsoup4

import re
import streamlit as st
from curl_cffi import requests as cf_requests
from bs4 import BeautifulSoup

st.set_page_config(layout="wide", initial_sidebar_state="collapsed")
st.title("🛍️ Amazon Product Comparison")

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

if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = DEFAULT_FIELDS.copy()
if "product_data" not in st.session_state:
    st.session_state.product_data = []
if "num_columns" not in st.session_state:
    st.session_state.num_columns = 2
if "show_debug" not in st.session_state:
    st.session_state.show_debug = False


# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
def display_field_selector():
    with st.sidebar.expander("DISPLAY OPTIONS", expanded=True):
        if st.button("✅ Default Options"):
            st.session_state.visible_fields = DEFAULT_FIELDS.copy()

        if st.button("🔁 ALL / NONE"):
            if len(st.session_state.visible_fields) == len(ALL_FIELDS):
                st.session_state.visible_fields = []
            else:
                st.session_state.visible_fields = ALL_FIELDS.copy()

        # Render checkboxes in fixed ALL_FIELDS order and update a set —
        # never append/remove, so the order never drifts.
        new_visible = []
        for field in ALL_FIELDS:
            checked = field in st.session_state.visible_fields
            if st.checkbox(field, value=checked, key=f"chk_{field}"):
                new_visible.append(field)
        st.session_state.visible_fields = new_visible

    with st.sidebar.expander("DEBUG", expanded=False):
        st.session_state.show_debug = st.checkbox(
            "Show debug panel", value=st.session_state.show_debug, key="chk_debug"
        )


# ─────────────────────────────────────────────────────────────
# Star percentage parser
# ─────────────────────────────────────────────────────────────
def _parse_star_percentages(soup: BeautifulSoup) -> dict:
    """
    Each <li> in #histogramTable contains:
      <a aria-label="14 percent of reviews have 4 stars">  → star number
      <div class="a-meter" aria-valuenow="14">             → percentage
    """
    result = {}
    for li in soup.select("#histogramTable li"):
        a     = li.select_one("a[aria-label]")
        meter = li.select_one(".a-meter[aria-valuenow]")
        if not (a and meter):
            continue
        label = a.get("aria-label", "")
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
            url,
            impersonate="chrome120",
            timeout=20,
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        soup = BeautifulSoup(r.text, "html.parser")

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

        matches = re.findall(r'"hiRes":"(https://[^"]+)"', r.text)
        if matches:
            data["images"] = list(dict.fromkeys(matches))
        else:
            imgs = []
            for el in soup.select("#altImages img"):
                src = el.get("src", "")
                large = re.sub(r"\._[A-Z0-9_,]+_\.", "._AC_SL1500_.", src)
                if large.startswith("https"):
                    imgs.append(large)
            if not imgs:
                main = soup.select_one("#landingImage")
                if main and main.get("src"):
                    imgs = [main["src"]]
            data["images"] = imgs

        customers_say = "N/A"
        for sel in (
            "[data-hook='cr-insights-widget-summary']",
            ".cr-lighthouse-summary",
            "[data-hook='cr-insights-widget-aspects']",
        ):
            el = soup.select_one(sel)
            if el:
                customers_say = el.get_text(strip=True)
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
            str(histogram_el)[:3000] if histogram_el
            else "⚠️ #histogramTable not found"
        )

    except Exception as exc:
        data["_error"] = str(exc)

    return data


# ─────────────────────────────────────────────────────────────
# Diff helpers
# ─────────────────────────────────────────────────────────────
def update_all_diffs():
    products = st.session_state.product_data

    # ── Price ──────────────────────────────────────────────
    for p in products:
        try:
            p["pricing_float"] = float(
                str(p.get("json", {}).get("pricing", "")).replace("$", "").replace(",", "")
            )
        except Exception:
            p["pricing_float"] = None

    for idx, cur in enumerate(products):
        cur_price = cur.get("pricing_float")
        html = ""
        if cur_price is not None:
            for j, other in enumerate(products):
                if j == idx:
                    continue
                op = other.get("pricing_float")
                if op is None:
                    continue
                diff = cur_price - op
                color = "green" if diff < 0 else "red" if diff > 0 else "gray"
                sign  = "+" if diff > 0 else "-" if diff < 0 else "±"
                html += f"<br>[{j+1}]<span style='color:{color}'> {sign}${abs(diff):.2f}</span>"
        cur["price_diff_html"] = html

    # ── Rating ─────────────────────────────────────────────
    for p in products:
        try:
            p["rating_float"] = float(p.get("json", {}).get("average_rating", ""))
        except Exception:
            p["rating_float"] = None

    for idx, cur in enumerate(products):
        cur_rating = cur.get("rating_float")
        html = ""
        if cur_rating is not None:
            for j, other in enumerate(products):
                if j == idx:
                    continue
                or_ = other.get("rating_float")
                if or_ is None:
                    continue
                diff = cur_rating - or_
                color = "green" if diff > 0 else "red" if diff < 0 else "gray"
                sign  = "+" if diff > 0 else ""
                html += f"<br>[{j+1}]<span style='color:{color}'> {sign}{diff:+.1f}</span>"
        cur["rating_diff_html"] = html


# ─────────────────────────────────────────────────────────────
# Column renderer
# ─────────────────────────────────────────────────────────────
def render_product_column(idx, product, visible_fields):
    col = st.columns([0.15, 0.75, 0.12, 0.1])

    with col[0]:
        with st.popover(f"[{idx + 1}]", use_container_width=True):
            if idx > 0 and st.button("⬅️ Move Left", key=f"move_left_{idx}"):
                (
                    st.session_state.product_data[idx - 1],
                    st.session_state.product_data[idx],
                ) = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx - 1],
                )
                st.rerun()
            if idx < st.session_state.num_columns - 1 and st.button(
                "➡️ Move Right", key=f"move_right_{idx}"
            ):
                (
                    st.session_state.product_data[idx + 1],
                    st.session_state.product_data[idx],
                ) = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx + 1],
                )
                st.rerun()
            if st.button("🗑️ Remove Product", key=f"remove_product_{idx}"):
                st.session_state.product_data.pop(idx)
                st.session_state.num_columns -= 1
                st.rerun()

    with col[1]:
        url = st.text_input(
            "",
            value=product.get("url", ""),
            placeholder="Paste Amazon product URL here",
            key=f"url_{idx}",
            label_visibility="collapsed",
        )
        if url != product.get("url"):
            st.session_state.product_data[idx]["url"] = url
            # Clear stale json so loader shows
            st.session_state.product_data[idx].pop("json", None)
            st.rerun()
        st.session_state.product_data[idx]["url"] = url

    with col[2]:
        if st.button("🛒", key=f"amazon_{idx}", help="Open in Amazon"):
            if url:
                st.markdown(f'<script>window.open("{url}");</script>', unsafe_allow_html=True)

    with col[3]:
        if st.button("🔄", key=f"refresh_{idx}", help="Refresh product"):
            st.cache_data.clear()
            st.session_state.product_data[idx].pop("json", None)
            st.rerun()

    # ── Gate: show nothing below until data is fully loaded ──
    if not url:
        return

    if "json" not in product:
        with st.spinner("🔄 Loading…"):
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()
        return  # spinner shown; next rerun will have json ready

    product_data = product["json"]

    if "_error" in product_data:
        st.warning(f"⚠️ Scrape error: {product_data['_error']}")
        return

    # ── Render fields in stable ALL_FIELDS order ────────────
    # (iterating ALL_FIELDS, not visible_fields, prevents reordering)
    for field in ALL_FIELDS:
        if field not in visible_fields:
            continue

        if field == "Title":
            value_str = str(product_data.get("name") or "N/A")
            st.markdown(
                f"<div style='font-size:14pt;font-weight:bold'>"
                f"{value_str[:150]}{'...' if len(value_str) > 150 else ''}</div>",
                unsafe_allow_html=True,
            )

        elif field == "Price":
            price = product_data.get("pricing", "N/A")
            st.markdown(
                f"<div>💰<strong>{price}</strong>{product.get('price_diff_html','')}</div>",
                unsafe_allow_html=True,
            )

        elif field == "Rating":
            rating     = product_data.get("average_rating", "N/A")
            raw_count  = product_data.get("total_reviews")
            count_display = (
                f"{(raw_count // 100) * 100}+" if isinstance(raw_count, int) and raw_count >= 100
                else str(raw_count) if isinstance(raw_count, int)
                else "N/A"
            )
            pct_4 = int(product_data.get("4_star_percentage", 0))
            pct_5 = int(product_data.get("5_star_percentage", 0))
            rating_str = f"⭐ {rating}{product.get('rating_diff_html','')} [👤 {count_display}]"
            if pct_4 or pct_5:
                rating_str += f"<br>5⭐ {pct_5}%  4⭐ {pct_4}%  ({pct_4 + pct_5}% positive)"
            st.markdown(rating_str, unsafe_allow_html=True)

        elif field == "Customers Say":
            summary = (product_data.get("customers_say") or {}).get("summary", "N/A")
            st.markdown(summary)

        elif field == "ImageGallery":
            imgs = product_data.get("images", [])
            if imgs:
                st.markdown(
                    "<style>"
                    ".scrolling-wrapper{display:flex;overflow-x:auto;padding-bottom:10px}"
                    ".scrolling-wrapper img{height:150px;margin-right:10px;border-radius:8px}"
                    "</style>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    '<div class="scrolling-wrapper">'
                    + "".join(f'<img src="{img}" alt="product image">' for img in imgs)
                    + "</div>",
                    unsafe_allow_html=True,
                )

        else:
            value = product_data.get(field.lower(), "N/A")
            st.write(f"**{field.capitalize()}**: {value or 'N/A'}")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
display_field_selector()

if st.button("➕ Add Product Column", help="Add a new Amazon product for comparison"):
    st.session_state.num_columns += 1
    st.rerun()

update_all_diffs()

cols = st.columns(st.session_state.num_columns)
for i in range(st.session_state.num_columns):
    if i >= len(st.session_state.product_data):
        st.session_state.product_data.append({"url": ""})
    with cols[i]:
        render_product_column(
            i, st.session_state.product_data[i], st.session_state.visible_fields
        )

# ─────────────────────────────────────────────────────────────
# Debug panel — always at bottom, opt-in via sidebar
# ─────────────────────────────────────────────────────────────
if st.session_state.show_debug:
    st.divider()
    st.subheader("🔍 Debug")
    debug_cols = st.columns(st.session_state.num_columns)
    for i, product in enumerate(st.session_state.product_data):
        if i >= st.session_state.num_columns:
            break
        with debug_cols[i]:
            product_data = product.get("json", {})
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
            st.write("**histogram HTML:**")
            st.code(product_data.get("_debug_histogram_html", "not captured"), language="html")
