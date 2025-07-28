# v0.56
import streamlit as st
import requests
from urllib.parse import quote_plus

# ✅ Sidebar starts collapsed, but user can expand it
st.set_page_config(layout="wide", initial_sidebar_state="collapsed")

st.title("🛍️ Amazon Product Comparison")

SCRAPER_API_KEY = "b1cd14dc050586097b7ea4d0d19652c8"

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
    
    col = st.columns([0.15, 0.75, 0.12, 0.1])  # Label, URL, Amazon, Refresh

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

    with col[1]:
        url_input_key = f"url_{idx}"
        default_url = product.get("url", "")

        url = st.text_input(
            "",
            value=default_url,
            placeholder="Paste Amazon product URL here",
            key=url_input_key,
            label_visibility="collapsed"
        )

        # Refresh only if URL changed
        if url != product.get("url"):
            st.session_state.product_data[idx]["url"] = url
            st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)
            st.rerun()

        st.session_state.product_data[idx]["url"] = url

    with col[2]:
        if st.button("🛒", key=f"amazon_{idx}", help="Open in Amazon"):
            if url:
                st.markdown(f'<script>window.open("{url}");</script>', unsafe_allow_html=True)

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
        st.session_state.product_data[idx]["pricing"] = product_data.get("pricing", "N/A")
        st.session_state.product_data[idx]["average_rating"] = product_data.get("average_rating", "N/A")
        st.session_state.product_data[idx]["review_breakdown"] = product_data.get("reviews", [])

        for field in visible_fields:
            all_values = []
            for p in st.session_state.product_data:
                pj = p.get("json", {})
                if field == "title":
                    val = pj.get("name", "")
                elif field == "price":
                    val = pj.get("pricing", "")
                elif field == "rating":
                    val = pj.get("average_rating", "N/A")
                elif field == "customers say":
                    val = pj.get("customers_say", "N/A")
                elif field == "imageGallery":
                    val = pj.get("images", [])
                else:
                    val = pj.get(field, "N/A")
                all_values.append(val)

            value = all_values[idx]

            if field == "title":
                value_str = str(value or "N/A")
                st.markdown(
                    f"<div style='font-size: 14pt; font-weight: bold'>{value_str[:150]}{'...' if len(value_str)>150 else ''}</div>",
                    unsafe_allow_html=True
                )

            elif field == "price":
                price = product_data.get("pricing", "N/A")
                current_price = None
                if price not in (None, "N/A"):
                    try:
                        current_price = float(str(price).replace("$", "").replace(",", ""))
                    except ValueError:
                        pass

                price_md = f"<div>💰<strong>{price}</strong>"

                if current_price is not None and len(st.session_state.product_data) > 1:
                    diffs = []
                    for i, other_product in enumerate(st.session_state.product_data):
                        if i == idx:
                            continue
                        other_price = other_product.get("pricing")
                        if other_price in (None, "N/A"):
                            continue
                        try:
                            other_price_val = float(str(other_price).replace("$", "").replace(",", ""))
                            diff = current_price - other_price_val
                            diff_color = "green" if diff < 0 else "red" if diff > 0 else "gray"
                            diff_sign = "+" if diff > 0 else "-" if diff < 0 else "±"
                            diff_amount = f"${abs(diff):.2f}"
                            diffs.append(
                                f"<br>[{i+1}]<span style='color:{diff_color};'> {diff_sign}{diff_amount}</span>"
                            )
                        except ValueError:
                            continue
                    price_md += "".join(diffs)

                price_md = f"<div>💰<strong>{price}</strong>{product.get('price_diff_html', '')}</div>"
                st.markdown(price_md, unsafe_allow_html=True)

            elif field == "rating":
                rating = product_data.get("average_rating", "N/A")
                raw_count = product_data.get("total_reviews")
                if isinstance(raw_count, int):
                    count_display = f"{(raw_count // 100) * 100}+" if raw_count >= 100 else str(raw_count)
                else:
                    count_display = "N/A"

                rating_str = f"⭐ {rating} [👤 {count_display}]"
                pct_4 = int(product_data.get("4_star_percentage", 0))
                pct_5 = int(product_data.get("5_star_percentage", 0))
                total_pct = pct_4 + pct_5

                if pct_4 or pct_5:
                    rating_str += f" {total_pct}%<br>5⭐ {pct_5}% && 4⭐ {pct_4}%"

                st.markdown(rating_str, unsafe_allow_html=True)

            elif field == "customers_say":
                customer_summary = product_data.get("customers_say", {}).get("summary", "")
                st.markdown(customer_summary)

            elif field == "imageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    # Limit the number of images to display (4-5 per row)
                    img_per_row = 5
                    rows = [imgs[i:i+img_per_row] for i in range(0, len(imgs), img_per_row)]
                    for row in rows:
                        cols = st.columns(len(row))
                        for i, img in enumerate(row):
                            with cols[i]:
                                st.image(img, width=200, use_container_width=True)  # Adjust width as needed

            else:
                st.write(f"**{field.capitalize()}**: {value or 'N/A'}")


# ----------- UPDATE other columns -----------
def update_all_pricing_diffs():
    products = st.session_state.product_data

    # First, extract all float prices
    prices = []
    for product in products:
        price_str = product.get("json", {}).get("pricing", "N/A")
        try:
            price_val = float(str(price_str).replace("$", "").replace(",", ""))
        except:
            price_val = None
        product["pricing_float"] = price_val
        prices.append(price_val)

    # Now, compute comparison HTML per product
    for idx, current_product in enumerate(products):
        current_price = current_product.get("pricing_float")
        if current_price is None:
            current_product["price_diff_html"] = ""
            continue

        diffs_html = ""
        for j, other_product in enumerate(products):
            if j == idx:
                continue
            other_price = other_product.get("pricing_float")
            if other_price is None:
                continue
            diff = current_price - other_price
            diff_color = "green" if diff < 0 else "red" if diff > 0 else "gray"
            diff_sign = "+" if diff > 0 else "-" if diff < 0 else "±"
            diff_amount = f"${abs(diff):.2f}"
            diffs_html += f"<br>[{j+1}]<span style='color:{diff_color};'> {diff_sign}{diff_amount}</span>"

        current_product["price_diff_html"] = diffs_html



# ----------- MAIN -----------
# Note: sidebar is hidden but logic still applies if you expose it
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
        render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)
