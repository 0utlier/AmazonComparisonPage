# v0.55
import streamlit as st
import requests
from urllib.parse import quote_plus

# Sidebar starts collapsed but can be toggled by the user
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.title("🛍️ Amazon Product Comparison")

SCRAPER_API_KEY = "b1cd14dc050586097b7ea4d0d19652c8"

DEFAULT_FIELDS = ["title", "price", "rating", "imageGallery"]
ALL_FIELDS = [
    "title", "price", "rating", "imageGallery",
    "description", "brand", "availability", "features", "categories",
]

# Initialize session state
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
            st.session_state.visible_fields = (
                [] if len(st.session_state.visible_fields) == len(ALL_FIELDS)
                else ALL_FIELDS.copy()
            )
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
    col = st.columns([0.15, 0.7, 0.15])  # Label, URL + Actions, Spacer

    # --- Column label and dropdown actions ---
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

    # --- URL input + Refresh + Amazon link ---
    with col[1]:
        default_url = product.get("url", "")
        url = st.text_input(
            "", value=default_url,
            placeholder="Paste Amazon product URL here",
            key=f"url_{idx}", label_visibility="collapsed"
        )

        # Check if URL changed and refresh data if needed
        if url != product.get("url", ""):
            st.session_state.product_data[idx]["url"] = url
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()

        col2 = st.columns([1, 1])
        with col2[0]:
            if st.button("🛒 Open on Amazon", key=f"amazon_{idx}"):
                if url:
                    st.markdown(f"[🔗 View Product]({url}){{:target=\"_blank\"}}", unsafe_allow_html=True)
        with col2[1]:
            if st.button("🔄 Refresh", key=f"refresh_{idx}"):
                st.cache_data.clear()
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
                st.rerun()

    # --- Load product data if missing ---
    if url and "json" not in product:
        with st.spinner("🔄 Loading product data..."):
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

    product_data = st.session_state.product_data[idx].get("json", {})

    # --- Update pricing for comparisons ---
    st.session_state.product_data[idx]["pricing"] = product_data.get("pricing", "N/A")

    # --- Render fields ---
    for field in visible_fields:
        all_values = []
        for p in st.session_state.product_data:
            pj = p.get("json", {})
            val = {
                "title": pj.get("name", ""),
                "price": pj.get("pricing", ""),
                "rating": pj.get("average_rating", "N/A"),
                "imageGallery": pj.get("images", []),
            }.get(field, pj.get(field, "N/A"))
            all_values.append(val)

        value = all_values[idx]

        if field == "title":
            st.markdown(f"### {value[:150]}{'...' if len(value) > 150 else ''}")

        elif field == "price":
            current_price = None
            try:
                current_price = float(str(value).replace("$", "").replace(",", ""))
            except:
                pass
            price_md = f"💰 **{value or 'N/A'}**"
            if current_price is not None and len(st.session_state.product_data) > 1:
                diffs = []
                for i, other in enumerate(st.session_state.product_data):
                    if i == idx:
                        continue
                    try:
                        other_price = float(str(other.get("pricing", "N/A")).replace("$", "").replace(",", ""))
                        diff = current_price - other_price
                        color = "green" if diff < 0 else "red" if diff > 0 else "gray"
                        sign = "+" if diff > 0 else "-" if diff < 0 else "±"
                        diffs.append(f"[{i+1}]: <span style='color:{color}'>{sign}${abs(diff):.2f}</span>")
                    except:
                        continue
                if diffs:
                    price_md += "<br>" + " ".join(diffs)
            st.markdown(price_md, unsafe_allow_html=True)

        elif field == "rating":
            rating = product_data.get("average_rating", "N/A")
            total_reviews = product_data.get("total_reviews", "N/A")
            pct_5 = int(product_data.get("5_star_percentage", 0))
            pct_4 = int(product_data.get("4_star_percentage", 0))
            total_pct = pct_4 + pct_5
            rating_md = f"⭐ {rating} [👤 {total_reviews}]"
            if total_pct:
                rating_md += f"<br>Top Ratings: {total_pct}% (5⭐ {pct_5}% / 4⭐ {pct_4}%)"
            st.markdown(rating_md, unsafe_allow_html=True)

        elif field == "imageGallery":
            imgs = product_data.get("images", [])
            if imgs:
                st.image(imgs, width=200, use_column_width="auto")
            else:
                st.markdown("🖼️ No images available")

        else:
            st.write(f"**{field.capitalize()}**: {value or 'N/A'}")


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
