import streamlit as st
import requests
from urllib.parse import urlparse

st.set_page_config(layout="wide")

# Initialize session state
if "product_urls" not in st.session_state:
    st.session_state.product_urls = []
if "product_data" not in st.session_state:
    st.session_state.product_data = []
if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = {
        "title": True,
        "price": True,
        "rating": True,
        "image_gallery": True
    }
if "num_columns" not in st.session_state:
    st.session_state.num_columns = 0

API_KEY = "deebcab27baee26c8f8b61e466fde368"

# Helper to fetch product info
def fetch_product_info(url):
    try:
        domain = urlparse(url).netloc
        asin = None
        parts = url.split("/dp/")
        if len(parts) > 1:
            asin = parts[1].split("/")[0]
        elif "/gp/product/" in url:
            asin = url.split("/gp/product/")[1].split("/")[0]
        if not asin:
            return {}
        api_url = f"https://api.scraperapi.com/structured/amazon/product?api_key={API_KEY}&asin={asin}&domain={domain}"
        res = requests.get(api_url)
        if res.status_code == 200:
            return res.json()
        return {}
    except Exception as e:
        return {}

# Function to render the display toggle
def display_options():
    with st.container():
        st.markdown("**Display Options**")
        st.session_state.visible_fields["image_gallery"] = st.checkbox("Image Gallery", value=st.session_state.visible_fields["image_gallery"])
        st.session_state.visible_fields["title"] = st.checkbox("Title", value=st.session_state.visible_fields["title"])
        st.session_state.visible_fields["price"] = st.checkbox("Price", value=st.session_state.visible_fields["price"])
        st.session_state.visible_fields["rating"] = st.checkbox("Rating", value=st.session_state.visible_fields["rating"])

# Render each product
def render_product_column(idx, product_data, visible_fields):
    col = st.columns([1, 20])[1]
    with col:
        with st.container():
            options_label = f"[{idx + 1}]"
            if st.button(options_label, key=f"options_{idx}", help="Options: Remove, Move Left, Move Right"):
                st.session_state.selected_option = idx

            url_container = st.container()
            with url_container:
                scrollable_url = f"<div style='overflow-x:auto; white-space:nowrap; border:1px solid #ccc; padding:4px;'>{st.session_state.product_urls[idx]}</div>"
                st.markdown(scrollable_url, unsafe_allow_html=True)
                if st.button("📋", key=f"paste_{idx}", help="Paste", use_container_width=True):
                    pasted = st.text_input("Paste URL", key=f"paste_input_{idx}")
                    if pasted:
                        st.session_state.product_urls[idx] = pasted
                        st.session_state.product_data[idx] = fetch_product_info(pasted)

            if visible_fields.get("title"):
                st.markdown(f"**{product_data.get('title', 'No title')}**")

            if visible_fields.get("price"):
                price = product_data.get("pricing", {}).get("price") or product_data.get("price", {}).get("value") or "N/A"
                st.write(f"💲 {price}")

            if visible_fields.get("rating"):
                rating = product_data.get("reviews", [{}])[0].get("rating", "N/A")
                st.write(f"⭐ {rating}")

            if visible_fields.get("image_gallery"):
                images = product_data.get("images", [])
                if images:
                    st.image(images, width=200)

            # Left and right controls
            col1, col2, col3 = st.columns([1,1,1])
            if idx > 0:
                if col1.button("⬅️ Move Left", key=f"left_{idx}", help="Move Left"):
                    st.session_state.product_urls[idx - 1], st.session_state.product_urls[idx] = st.session_state.product_urls[idx], st.session_state.product_urls[idx - 1]
                    st.session_state.product_data[idx - 1], st.session_state.product_data[idx] = st.session_state.product_data[idx], st.session_state.product_data[idx - 1]
            if col2.button("❌ Remove", key=f"remove_{idx}", help="Remove Product"):
                st.session_state.product_urls.pop(idx)
                st.session_state.product_data.pop(idx)
                st.session_state.num_columns -= 1
                st.experimental_rerun()
            if idx < st.session_state.num_columns - 1:
                if col3.button("➡️ Move Right", key=f"right_{idx}", help="Move Right"):
                    st.session_state.product_urls[idx + 1], st.session_state.product_urls[idx] = st.session_state.product_urls[idx], st.session_state.product_urls[idx + 1]
                    st.session_state.product_data[idx + 1], st.session_state.product_data[idx] = st.session_state.product_data[idx], st.session_state.product_data[idx + 1]

# Sidebar section
with st.sidebar:
    st.markdown("### Comparison Settings")
    display_options()

# Main area
st.title("Amazon Product Comparison")
add_col = st.button("➕ Add Product Column")
if add_col:
    st.session_state.product_urls.append("")
    st.session_state.product_data.append({})
    st.session_state.num_columns += 1

# Render product columns if there are any
if st.session_state.num_columns > 0:
    cols = st.columns(st.session_state.num_columns)
    for i in range(st.session_state.num_columns):
        with cols[i]:
            render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)
