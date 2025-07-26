import streamlit as st
import requests

# --- Constants ---
DEFAULT_FIELDS = ["title", "price", "rating", "imageGallery"]
ALL_FIELDS = ["title", "price", "rating", "reviews", "imageGallery"]
API_KEY = "deebcab27baee26c8f8b61e466fde368"

# --- Page config ---
st.set_page_config(page_title="Amazon Product Comparison", layout="wide")
st.title("🛍️ Amazon Product Comparison")

# --- Session State Setup ---
if "product_urls" not in st.session_state:
    st.session_state.product_urls = [""]
if "product_data" not in st.session_state:
    st.session_state.product_data = [{}]
if "visible_fields" not in st.session_state:
    st.session_state.visible_fields = DEFAULT_FIELDS.copy()
if "num_columns" not in st.session_state:
    st.session_state.num_columns = 1

# --- Helper Functions ---
def fetch_product_data(url):
    api_url = f"http://api.scraperapi.com?api_key={API_KEY}&url={url}&autoparse=true"
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        return response.json().get("products", [{}])[0]
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return {}

def paste_from_clipboard():
    try:
        import pyperclip
        return pyperclip.paste()
    except:
        return ""

# --- Field Display Options ---
st.sidebar.subheader("Display Options")
if st.sidebar.button("Show All"):
    st.session_state.visible_fields = ALL_FIELDS.copy()
if st.sidebar.button("Show None"):
    st.session_state.visible_fields = []

for field in ALL_FIELDS:
    checked = field in st.session_state.visible_fields
    if st.sidebar.checkbox(field, value=checked):
        if field not in st.session_state.visible_fields:
            st.session_state.visible_fields.append(field)
    else:
        if field in st.session_state.visible_fields:
            st.session_state.visible_fields.remove(field)

# --- Main UI ---
st.sidebar.markdown("---")
if st.sidebar.button("Add Product Column"):
    st.session_state.product_urls.append("")
    st.session_state.product_data.append({})
    st.session_state.num_columns += 1

# --- Product Rendering ---
def render_product_column(idx, product_data, visible_fields):
    with st.container():
        col = st.columns([1])[0]

        url_row = col.columns([1, 8])
        left_cell, url_cell = url_row[0], url_row[1]

        label = f"[{idx + 1}]"
        with left_cell:
            if st.button(label, key=f"label_{idx}", help="Options: Remove, Move Left, Move Right"):
                option = st.radio("Choose an action", ["Remove", "Move Left", "Move Right"], key=f"radio_{idx}")
                if option == "Remove":
                    st.session_state.product_urls.pop(idx)
                    st.session_state.product_data.pop(idx)
                    st.session_state.num_columns -= 1
                    st.experimental_rerun()
                elif option == "Move Left" and idx > 0:
                    st.session_state.product_urls[idx-1], st.session_state.product_urls[idx] = st.session_state.product_urls[idx], st.session_state.product_urls[idx-1]
                    st.session_state.product_data[idx-1], st.session_state.product_data[idx] = st.session_state.product_data[idx], st.session_state.product_data[idx-1]
                    st.experimental_rerun()
                elif option == "Move Right" and idx < st.session_state.num_columns - 1:
                    st.session_state.product_urls[idx+1], st.session_state.product_urls[idx] = st.session_state.product_urls[idx], st.session_state.product_urls[idx+1]
                    st.session_state.product_data[idx+1], st.session_state.product_data[idx] = st.session_state.product_data[idx], st.session_state.product_data[idx+1]
                    st.experimental_rerun()

        with url_cell:
            url = st.text_input("", value=st.session_state.product_urls[idx], key=f"url_{idx}")
            paste_col, open_col = st.columns([1, 1])
            with paste_col:
                if st.button("📋", key=f"paste_{idx}", help="Paste from clipboard"):
                    st.session_state.product_urls[idx] = paste_from_clipboard()
                    st.experimental_rerun()
            with open_col:
                if url:
                    st.markdown(f"[🔗](https://www.amazon.com/dp/{url.split('/dp/')[-1].split('/')[0]})", unsafe_allow_html=True)

            if url and (not st.session_state.product_data[idx]):
                product = fetch_product_data(url)
                st.session_state.product_data[idx] = product
                product_data = product

        if not product_data:
            return

        if "title" in visible_fields:
            col.subheader(product_data.get("title", "No Title"))

        if "price" in visible_fields:
            price = product_data.get("pricing", {}).get("price", "N/A")
            col.markdown(f"**Price:** {price}")

        if "rating" in visible_fields:
            rating = product_data.get("rating", "N/A")
            col.markdown(f"**Rating:** {rating}")

        if "reviews" in visible_fields:
            reviews = product_data.get("reviews", [{}])[0].get("text", "N/A")
            col.markdown(f"**Review:** {reviews}")

        if "imageGallery" in visible_fields:
            images = product_data.get("imageGallery", [])
            for img_url in images:
                col.image(img_url, use_column_width=True)

# --- Render Columns ---
cols = st.columns(st.session_state.num_columns)
for i in range(st.session_state.num_columns):
    with cols[i]:
        render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)
