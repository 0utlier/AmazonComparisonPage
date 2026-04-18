# v0.58 — curl_cffi + BeautifulSoup (no Playwright, no ScraperAPI)
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

        for field in ALL_FIELDS:
            checked = field in st.session_state.visible_fields
            if st.checkbox(field, value=checked, key=f"chk_{field}"):
                if field not in st.session_state.visible_fields:
                    st.session_state.visible_fields.append(field)
            else:
                if field in st.session_state.visible_fields:
                    st.session_state.visible_fields.remove(field)


# ─────────────────────────────────────────────────────────────
# Scraper
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def fetch_amazon_data(url: str) -> dict:
    """Fetch and parse an Amazon product page using curl_cffi (Chrome TLS impersonation)."""
    data: dict = {}
    try:
        r = cf_requests.get(
            url,
            impersonate="chrome120",
            timeout=20,
            headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        soup = BeautifulSoup(r.text, "html.parser")

        # ── Title ──────────────────────────────────────────
        title = soup.select_one("#productTitle")
        data["name"] = title.get_text(strip=True) if title else "N/A"

        # ── Price ──────────────────────────────────────────
        price = soup.select_one(".a-price .a-offscreen")
        data["pricing"] = price.get_text(strip=True) if price else "N/A"

        # ── Rating ─────────────────────────────────────────
        rating = soup.select_one("#acrPopover")
        data["average_rating"] = (
            rating["title"].split()[0]
            if rating and rating.get("title")
            else "N/A"
        )

        # ── Total Reviews ──────────────────────────────────
        reviews = soup.select_one("#acrCustomerReviewText")
        if reviews:
            data["total_reviews"] = int(re.sub(r"[^\d]", "", reviews.get_text()))
        else:
            data["total_reviews"] = None

        # ── Star Percentages ───────────────────────────────
        for row in soup.select("table#histogramTable tr"):
            label = row.select_one("td:first-child a")
            pct = row.select_one("td:last-child")
            if label and pct:
                star = re.search(r"\d+", label.get_text())
                pct_val = pct.get_text(strip=True).replace("%", "")
                if star and pct_val.isdigit():
                    data[f"{star.group()}_star_percentage"] = int(pct_val)

        # ── Images ─────────────────────────────────────────
        matches = re.findall(r'"hiRes":"(https://[^"]+)"', r.text)
        if matches:
            data["images"] = list(dict.fromkeys(matches))
        else:
            # Fallback: thumbnail strip src → upscale URL
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

        # ── Customers Say (AI summary) ─────────────────────
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

        # ── Brand ──────────────────────────────────────────
        brand = soup.select_one("#bylineInfo")
        data["brand"] = brand.get_text(strip=True) if brand else "N/A"

        # ── Availability ───────────────────────────────────
        avail = soup.select_one("#availability span")
        data["availability"] = avail.get_text(strip=True) if avail else "N/A"

        # ── Features ───────────────────────────────────────
        data["features"] = [
            li.get_text(strip=True)
            for li in soup.select("#feature-bullets li span.a-list-item")
            if li.get_text(strip=True)
        ]

        # ── Description ────────────────────────────────────
        desc = soup.select_one("#productDescription")
        data["description"] = desc.get_text(strip=True) if desc else "N/A"

        # ── Categories ─────────────────────────────────────
        crumbs = [
            c.get_text(strip=True)
            for c in soup.select("#wayfinding-breadcrumbs_container li span")
            if c.get_text(strip=True) not in ("", "›")
        ]
        data["categories"] = " > ".join(crumbs) if crumbs else "N/A"

    except Exception as exc:
        data["_error"] = str(exc)

    return data


# ─────────────────────────────────────────────────────────────
# Price diff helper
# ─────────────────────────────────────────────────────────────
def update_all_pricing_diffs():
    products = st.session_state.product_data

    for product in products:
        price_str = product.get("json", {}).get("pricing", "N/A")
        try:
            product["pricing_float"] = float(
                str(price_str).replace("$", "").replace(",", "")
            )
        except Exception:
            product["pricing_float"] = None

    for idx, cur in enumerate(products):
        cur_price = cur.get("pricing_float")
        if cur_price is None:
            cur["price_diff_html"] = ""
            continue

        diffs_html = ""
        for j, other in enumerate(products):
            if j == idx:
                continue
            other_price = other.get("pricing_float")
            if other_price is None:
                continue
            diff = cur_price - other_price
            color = "green" if diff < 0 else "red" if diff > 0 else "gray"
            sign = "+" if diff > 0 else "-" if diff < 0 else "±"
            diffs_html += (
                f"<br>[{j+1}]<span style='color:{color};'> {sign}${abs(diff):.2f}</span>"
            )
        cur["price_diff_html"] = diffs_html


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
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()
        st.session_state.product_data[idx]["url"] = url

    with col[2]:
        if st.button("🛒", key=f"amazon_{idx}", help="Open in Amazon"):
            if url:
                st.markdown(
                    f'<script>window.open("{url}");</script>',
                    unsafe_allow_html=True,
                )

    with col[3]:
        if st.button("🔄", key=f"refresh_{idx}", help="Refresh product"):
            st.cache_data.clear()
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()

    if url:
        if "json" not in product:
            with st.spinner("🔄 Loading product data..."):
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

        product_data = st.session_state.product_data[idx].get("json", {})

        if "_error" in product_data:
            st.warning(f"⚠️ Scrape error: {product_data['_error']}")

        st.session_state.product_data[idx]["pricing"] = product_data.get("pricing", "N/A")
        st.session_state.product_data[idx]["average_rating"] = product_data.get(
            "average_rating", "N/A"
        )

        for field in visible_fields:
            if field == "Title":
                value = product_data.get("name", "")
            elif field == "Price":
                value = product_data.get("pricing", "")
            elif field == "Rating":
                value = product_data.get("average_rating", "N/A")
            elif field == "Customers Say":
                value = product_data.get("customers_say", {})
            elif field == "ImageGallery":
                value = product_data.get("images", [])
            else:
                value = product_data.get(field.lower(), "N/A")

            # ── Render each field ──────────────────────────
            if field == "Title":
                value_str = str(value or "N/A")
                st.markdown(
                    f"<div style='font-size:14pt;font-weight:bold'>"
                    f"{value_str[:150]}{'...' if len(value_str) > 150 else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            elif field == "Price":
                price = product_data.get("pricing", "N/A")
                price_md = (
                    f"<div>💰<strong>{price}</strong>"
                    f"{product.get('price_diff_html', '')}</div>"
                )
                st.markdown(price_md, unsafe_allow_html=True)

            elif field == "Rating":
                rating = product_data.get("average_rating", "N/A")
                raw_count = product_data.get("total_reviews")
                if isinstance(raw_count, int):
                    count_display = (
                        f"{(raw_count // 100) * 100}+"
                        if raw_count >= 100
                        else str(raw_count)
                    )
                else:
                    count_display = "N/A"

                rating_str = f"⭐ {rating} [👤 {count_display}]"
                pct_4 = int(product_data.get("4_star_percentage", 0))
                pct_5 = int(product_data.get("5_star_percentage", 0))
                if pct_4 or pct_5:
                    rating_str += f" {pct_4 + pct_5}%<br>5⭐ {pct_5}%     4⭐ {pct_4}%"
                st.markdown(rating_str, unsafe_allow_html=True)

            elif field == "Customers Say":
                summary = (value or {}).get("summary", "N/A")
                st.markdown(summary)

            elif field == "ImageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    st.markdown(
                        """
                        <style>
                        .scrolling-wrapper {
                            display: flex;
                            overflow-x: auto;
                            padding-bottom: 10px;
                        }
                        .scrolling-wrapper img {
                            height: 150px;
                            margin-right: 10px;
                            border-radius: 8px;
                        }
                        </style>
                        """,
                        unsafe_allow_html=True,
                    )
                    image_html = '<div class="scrolling-wrapper">'
                    for img in imgs:
                        image_html += f'<img src="{img}" alt="product image">'
                    image_html += "</div>"
                    st.markdown(image_html, unsafe_allow_html=True)

            else:
                st.write(f"**{field.capitalize()}**: {value or 'N/A'}")


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
display_field_selector()

if st.button("➕ Add Product Column", help="Add a new Amazon product for comparison"):
    st.session_state.num_columns += 1
    st.rerun()

update_all_pricing_diffs()

cols = st.columns(st.session_state.num_columns)
for i in range(st.session_state.num_columns):
    if i >= len(st.session_state.product_data):
        st.session_state.product_data.append({"url": ""})
    with cols[i]:
        render_product_column(
            i, st.session_state.product_data[i], st.session_state.visible_fields
        )
