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
            with st.spinner("Loading... 🔄 A"):
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

        product_data = st.session_state.product_data[idx].get("json", {})

        for field in visible_fields:
            if field == "title":
                title = product_data.get("name", "N/A")
                st.markdown(f"<div style='font-size: 14pt; font-weight: bold'>{title[:150]}{'...' if len(title)>150 else ''}</div>", unsafe_allow_html=True)

            #//==================================================================================================================================================================================
            #//==================================================================================================================================================================================

            elif field == "price":
                price = product_data.get("pricing", "N/A")
            
                def extract_price(p):
                    try:
                        return float(str(p).replace("$", "").replace(",", ""))
                    except (ValueError, TypeError):
                        return None
            
                current_price = extract_price(price)
                price_md = f"**💰{price}**"
            
                if current_price is not None and len(st.session_state.product_data) > 1:
                    diffs = []
                    for i, other_product in enumerate(st.session_state.product_data):
                        if i == idx:
                            continue
                        other_price_raw = other_product.get("pricing", "N/A")
                        other_price_val = extract_price(other_price_raw)
                        if other_price_val is None:
                            continue
            
                        diff = current_price - other_price_val
                        diff_color = "green" if diff < 0 else "red" if diff > 0 else "gray"
                        diff_sign = "+" if diff > 0 else "-" if diff < 0 else "±"
                        diff_amount = f"${abs(diff):.2f}"
                        diffs.append(f"<span style='color:{diff_color};'>[{i + 1}] {diff_sign}{diff_amount}</span>")
            
                    if diffs:
                        price_md += "<br><br><br>" + "<br>".join(diffs)
            
                st.markdown(price_md, unsafe_allow_html=True)





            #//==================================================================================================================================================================================
            #//==================================================================================================================================================================================


            elif field == "rating":
                rating = product_data.get("average_rating", "N/A")
                
                # Fallback in case average_rating is missing or not correctly set
                if rating == "N/A":
                    reviews = product_data.get("reviews", [])
                    if reviews:
                        rating = reviews[0].get("stars", "N/A")
                    else:
                        rating = "N/A"
                
                count = product_data.get("total_reviews", "N/A")
                st.markdown(f"⭐ {rating} [👤 {count}]")

            elif field == "imageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    st.image(imgs, width=200, caption=None, use_container_width="True")
                else:
                    st.markdown("🖼️ No images found")

            else:
                val = product_data.get(field, "N/A")
                st.write(f"**{field.capitalize()}**: {val}")


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
