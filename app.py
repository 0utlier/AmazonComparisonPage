import streamlit as st
import requests
from urllib.parse import quote_plus

st.set_page_config(layout="wide")

st.title("🛍️ Amazon Product Comparison")

SCRAPER_API_KEY = "b1cd14dc050586097b7ea4d0d19652c8"

DEFAULT_FIELDS = ["title", "price", "rating", "imageGallery"]
ALL_FIELDS = [
    "title",
    "price",
    "rating",
    "imageGallery",
    "description",
    "brand",
    "availability",
    "features",
    "categories",
]

if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = DEFAULT_FIELDS.copy()

if "product_data" not in st.session_state:
    st.session_state.product_data = []

if "num_columns" not in st.session_state:
    st.session_state.num_columns = 2


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


@st.cache_data(show_spinner=False)
def fetch_amazon_data(url):
    api_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={quote_plus(url)}&autoparse=true"
    try:
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        return r.json()
    except:
        return {}

def render_product_column(idx, product, visible_fields):
    col = st.columns([0.15, 0.55, 0.1, 0.15])  # Label, URL, Amazon, Refresh

# --- Column label and aligned dropdown ---
    with col[0]:
        with st.popover(f"[{idx + 1}]", use_container_width=True):
            if idx > 0 and st.button("⬅️ Move Left", key=f"move_left_{idx}"):
                st.session_state.product_data[idx - 1], st.session_state.product_data[idx] = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx - 1],
                )
                st.rerun()

            if idx < st.session_state.num_columns - 1 and st.button("➡️ Move Right", key=f"move_right_{idx}"):
                st.session_state.product_data[idx + 1], st.session_state.product_data[idx] = (
                    st.session_state.product_data[idx],
                    st.session_state.product_data[idx + 1],
                )
                st.rerun()

            if st.button("🗑️ Remove Product", key=f"remove_product_{idx}"):
                st.session_state.product_data.pop(idx)
                st.session_state.num_columns -= 1
                st.rerun()


    # --- URL input with embedded paste button ---
    with col[1]:
        url_input_key = f"url_{idx}"
        default_url = product.get("url", "")
        input_cols = st.columns([8, 1])
        with input_cols[0]:
            url = st.text_input(
                "",
                value=default_url,
                placeholder="Paste Amazon product URL here",
                key=url_input_key,
                label_visibility="collapsed"
            )
        with input_cols[1]:
            if st.button("📋", key=f"paste_{idx}", help="Paste from clipboard"):
                pasted = st.clipboard_get()
                st.session_state.product_data[idx]["url"] = pasted
                st.rerun()

        st.session_state.product_data[idx]["url"] = url

    # --- Amazon link button ---
    with col[2]:
        if st.button("🛒", key=f"amazon_{idx}", help="Open in Amazon"):
            if url:
                st.markdown(f'<script>window.open("{url}");</script>', unsafe_allow_html=True)

    # --- Refresh button ---
    with col[3]:
        if st.button("🔄", key=f"refresh_{idx}", help="Refresh product"):
            st.cache_data.clear()
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()

        # --- Load data if needed ---
    if url:
        if "json" not in product:
            with st.markdown("<div style='font-size:16px; animation: pulse 1.5s infinite;'>🔃 Fetching details...</div>", unsafe_allow_html=True):
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

        product_data = st.session_state.product_data[idx].get("json", {})
        col_heights = st.session_state.get("field_heights", {})

        for field in visible_fields:
            content = ""
            if field == "title":
                title = product_data.get("name", "N/A")
                short_title = f"{title[:150]}{'...' if len(title)>150 else ''}"
                content = f"<div style='font-size: 14pt; font-weight: bold'>{short_title}</div>"

            elif field == "price":
                def extract_price(p):
                    try:
                        return float(str(p).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        return None

                price = product_data.get("pricing", "N/A")
                current_price = extract_price(price)
                price_md = f"<strong>💰{price}</strong>"

                if current_price is not None and len(st.session_state.product_data) > 1:
                    diffs = []
                    for i, other_product in enumerate(st.session_state.product_data):
                        if i == idx:
                            continue
                        other_price = other_product.get("pricing", "N/A")
                        other_val = extract_price(other_price)
                        if other_val is None:
                            continue
                        diff = current_price - other_val
                        color = "green" if diff < 0 else "red" if diff > 0 else "gray"
                        sign = "+" if diff > 0 else "-" if diff < 0 else "±"
                        amount = f"${abs(diff):.2f}"
                        diffs.append(f"<span style='color:{color};'>[{i+1}] {sign}{amount}</span>")
                    if diffs:
                        price_md += "<br>" + "<br>".join(diffs)
                content = price_md

            elif field == "rating":
                rating = product_data.get("average_rating", "N/A")
                if rating == "N/A":
                    reviews = product_data.get("reviews", [])
                    if reviews:
                        rating = reviews[0].get("stars", "N/A")
                count = product_data.get("total_reviews", "N/A")
                content = f"⭐ {rating} [👤 {count}]"

            elif field == "imageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    st.image(imgs, width=200, use_container_width=True)
                else:
                    content = "🖼️ No images found"

            else:
                val = product_data.get(field, "N/A")
                content = f"<strong>{field.capitalize()}</strong>: {val}"

            # --- Calculate max height for this field across products ---
            col_heights.setdefault(field, [])
            col_heights[field].append(len(content.split("<br>")) + content.count("\n"))

            # --- Store the max line count for each field ---
            max_lines = max(col_heights[field])
            st.session_state.field_heights = col_heights  # Persist

            # --- Pad short rows for alignment ---
            line_count = content.count("<br>") + content.count("\n") + 1
            pad_lines = max_lines - line_count
            pad_html = "<br>" * pad_lines if pad_lines > 0 else ""

            if field != "imageGallery":
                st.markdown(content + pad_html, unsafe_allow_html=True)



# ----------- MAIN -----------
display_field_selector()

if st.button("➕ Add Product Column", help="Add a new Amazon product for comparison"):
    st.session_state.num_columns += 1
    st.rerun()

cols = st.columns(st.session_state.num_columns)

for i in range(st.session_state.num_columns):
    if i >= len(st.session_state.product_data):
        st.session_state.product_data.append({"url": ""})
    with cols[i]:
        render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)
