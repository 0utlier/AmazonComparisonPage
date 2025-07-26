import streamlit as st
import requests
import base64
import json

st.set_page_config(layout="wide")
st.title("🛍️ Amazon Product Comparison")

SCRAPER_API_KEY = "deebcab27baee26c8f8b61e466fde368"

# --- CSS ---
st.markdown("""
    <style>
        .url-box-container {
            display: flex;
            align-items: center;
            width: 100%;
        }
        .product-index {
            font-weight: bold;
            margin-right: 0.5rem;
            white-space: nowrap;
        }
        .scrollable-url input {
            overflow-x: auto;
            white-space: nowrap;
        }
        .paste-button {
            margin-left: -2.5rem;
            z-index: 10;
        }
        .option-menu {
            display: flex;
            justify-content: center;
            align-items: center;
            font-size: 1.1rem;
            margin-right: 0.5rem;
        }
        .field-toggle-section > div {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }
    </style>
""", unsafe_allow_html=True)

# --- Helper functions ---
def fetch_amazon_data(product_url):
    try:
        params = {
            "api_key": SCRAPER_API_KEY,
            "url": product_url
        }
        r = requests.get("http://api.scraperapi.com", params=params)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def parse_product_data(raw_data):
    return {
        "title": raw_data.get("title", "Unknown Title"),
        "price": raw_data.get("price", "N/A"),
        "rating": raw_data.get("rating", "N/A"),
        "reviews": raw_data.get("reviews", []),
        "images": raw_data.get("images", [])
    }

# --- State initialization ---
if "product_data" not in st.session_state:
    st.session_state.product_data = []

if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = {"title": True, "price": True, "rating": True, "images": True}

if "num_columns" not in st.session_state:
    st.session_state.num_columns = 0

# --- Field toggles ---
with st.sidebar:
    st.header("Display Options")
    field_col = st.container()
    with field_col:
        if st.button("Default"):
            st.session_state.visible_fields = {"title": True, "price": True, "rating": True, "images": True}
        if st.button("All"):
            for k in st.session_state.visible_fields:
                st.session_state.visible_fields[k] = True
        if st.button("None"):
            for k in st.session_state.visible_fields:
                st.session_state.visible_fields[k] = False
    for key in st.session_state.visible_fields:
        st.checkbox(f"{key.capitalize()}", key=key, value=st.session_state.visible_fields[key])

# --- Add product button ---
if st.button("➕ Add Product Column", help="Add a new Amazon product URL to compare"):
    st.session_state.product_data.append({"url": "", "fetched": False})
    st.session_state.num_columns += 1

# --- Render product columns ---
cols = st.columns(st.session_state.num_columns) if st.session_state.num_columns > 0 else []

def render_product_column(idx, product, visible_fields):
    with cols[idx]:
        # Row: Product index and Options
        st.markdown(
            f'<div class="url-box-container">'
            f'<span class="product-index">[{idx + 1}]</span>',
            unsafe_allow_html=True
        )

        # Options menu icon
        if st.button("⬅️", key=f"left_{idx}", help="Move Left") and idx > 0:
            st.session_state.product_data[idx - 1], st.session_state.product_data[idx] = \
                st.session_state.product_data[idx], st.session_state.product_data[idx - 1]
            st.experimental_rerun()

        if st.button("❌", key=f"remove_{idx}", help="Remove Product"):
            st.session_state.product_data.pop(idx)
            st.session_state.num_columns -= 1
            st.experimental_rerun()

        if st.button("➡️", key=f"right_{idx}", help="Move Right") and idx < st.session_state.num_columns - 1:
            st.session_state.product_data[idx + 1], st.session_state.product_data[idx] = \
                st.session_state.product_data[idx], st.session_state.product_data[idx + 1]
            st.experimental_rerun()

        st.markdown('</div>', unsafe_allow_html=True)

        # Row: URL input & Paste button
        url_col = st.empty()
        with url_col:
            st.markdown('<div class="scrollable-url">', unsafe_allow_html=True)
            url_input = st.text_input(f"Product URL {idx}", product.get("url", ""), key=f"url_{idx}")
            st.markdown('</div>', unsafe_allow_html=True)

            paste_button = st.button("📋", key=f"paste_{idx}", help="Paste from clipboard")
            if paste_button:
                st.session_state.product_data[idx]["url"] = st.experimental_get_query_params().get("url_clipboard", [""])[0]

        if url_input != product.get("url", ""):
            st.session_state.product_data[idx]["url"] = url_input
            st.session_state.product_data[idx]["fetched"] = False

        # Fetch & display data
        if not product.get("fetched") and url_input.strip():
            raw = fetch_amazon_data(url_input)
            st.session_state.product_data[idx].update(parse_product_data(raw))
            st.session_state.product_data[idx]["fetched"] = True

        # Display info
        if visible_fields.get("title"):
            st.subheader(st.session_state.product_data[idx].get("title", ""))

        if visible_fields.get("price"):
            st.write(f"💲 Price: {st.session_state.product_data[idx].get('price', 'N/A')}")

        if visible_fields.get("rating"):
            st.write(f"⭐ Rating: {st.session_state.product_data[idx].get('rating', 'N/A')}")

        if visible_fields.get("images"):
            images = st.session_state.product_data[idx].get("images", [])
            if images:
                st.image(images, width=150, caption=None, use_column_width="auto")

        if st.button("🛒", key=f"amazon_btn_{idx}", help="Open in Amazon"):
            st.markdown(f"[Open Product on Amazon]({url_input})")

# --- Loop through columns ---
for i in range(st.session_state.num_columns):
    render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)
