import streamlit as st
import requests
from urllib.parse import quote_plus
import time

st.set_page_config(layout="wide")

st.title("🛍️ Amazon Product Comparison")

# ----------- SETTINGS -----------
SCRAPER_API_KEY = "35f8598646ada9354f674b49850216b4"  # Replace with your key if different

DEFAULT_FIELDS = ["title", "price", "rating"]
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

# ----------- SESSION STATE -----------
if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = DEFAULT_FIELDS.copy()

if "product_data" not in st.session_state:
    st.session_state.product_data = []

# ----------- DISPLAY OPTIONS DROPDOWN -----------
def display_field_selector():
    with st.sidebar.expander("🧰 DISPLAY OPTIONS", expanded=True):
        col1, col2 = st.columns([1, 1])
        if col1.button("✅ Default Options"):
            st.session_state.visible_fields = DEFAULT_FIELDS.copy()

        if col2.button("🔁 ALL / NONE"):
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

# ----------- SCRAPER API FETCH -----------
@st.cache_data(show_spinner=False)
def fetch_amazon_data(url):
    api_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={quote_plus(url)}&autoparse=true"
    try:
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        return r.json()
    except:
        return {}

# ----------- PRODUCT COLUMN -----------
def render_product_column(idx, product, visible_fields):
    st.markdown(f"### [ {idx + 1} ]")
    url_col, btn_col, refresh_col = st.columns([6, 1, 1])

    with url_col:
        url = st.text_input(f"Product URL {idx + 1}", product.get("url", ""), key=f"url_{idx}")
    with btn_col:
        if st.button("📋", key=f"paste_{idx}"):
            st.session_state.product_data[idx]["url"] = st.clipboard_get()

    if url:
        with refresh_col:
            if st.button("🔄", key=f"refresh_{idx}"):
                st.cache_data.clear()
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
                st.rerun()

        if "json" not in product:
            with st.spinner("Loading... 🔄 A"):
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

        product_data = st.session_state.product_data[idx]["json"]

        for field in visible_fields:
            if field == "title":
                title = product_data.get("title", "N/A")
                st.markdown(f"<div style='font-size: 14pt; font-weight: bold'>{title[:150]}{'...' if len(title)>150 else ''}</div>", unsafe_allow_html=True)

            elif field == "price":
                price = product_data.get("pricing", {}).get("price", "N/A")
                st.markdown(f"💰 **{price}**")

            elif field == "rating":
                rating = product_data.get("reviews", [{}])[0].get("rating", "N/A")
                count = product_data.get("reviews", [{}])[0].get("count", "N/A")
                st.markdown(f"⭐ {rating} [👤 {count}]")

            elif field == "imageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    st.image(imgs, width=200, caption=None, use_column_width="auto")
                else:
                    st.markdown("🖼️ No images found")

            else:
                val = product_data.get(field, "N/A")
                st.write(f"**{field.capitalize()}**: {val}")

# ----------- RENDER PAGE -----------
display_field_selector()

# Add product columns
if "num_columns" not in st.session_state:
    st.session_state.num_columns = 2

st.markdown("### Products:")

cols = st.columns(st.session_state.num_columns)

for i in range(st.session_state.num_columns):
    if i >= len(st.session_state.product_data):
        st.session_state.product_data.append({"url": ""})
    with cols[i]:
        render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)

# Add button to insert a new column
if st.button("➕ Add Product Column"):
    st.session_state.num_columns += 1
    st.rerun()
