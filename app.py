# v0.52
import streamlit as st
import streamlit.components.v1 as components
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
            with st.spinner("🔄 Loading product data..."):
                st.session_state.product_data[idx]["json"] = fetch_amazon_data(url)

        product_data = st.session_state.product_data[idx].get("json", {})

        # Attach basic fields for cross-reference
        st.session_state.product_data[idx]["pricing"] = product_data.get("pricing", "N/A")
        st.session_state.product_data[idx]["average_rating"] = product_data.get("average_rating", "N/A")
        st.session_state.product_data[idx]["review_breakdown"] = product_data.get("reviews", [])

        for field in visible_fields:
            # Collect all products' values for this field
            all_values = []
            for p in st.session_state.product_data:
                pj = p.get("json", {})
                if field == "title":
                    val = pj.get("name", "")
                elif field == "price":
                    val = pj.get("pricing", "")
                elif field == "rating":
                    val = pj.get("average_rating", "N/A")
                elif field == "imageGallery":
                    val = pj.get("images", [])
                else:
                    val = pj.get(field, "N/A")
                all_values.append(val)

            # Get current product's value
            value = all_values[idx]

            # Title
            if field == "title":
                value_str = str(value or "N/A")
                st.markdown(
                    f"<div style='font-size: 14pt; font-weight: bold'>{value_str[:150]}{'...' if len(value_str)>150 else ''}</div>",
                    unsafe_allow_html=True
                )

            # Price
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
            
                price_md += "</div>"
                st.markdown(price_md, unsafe_allow_html=True)

            # Rating with 4-star/5-star counts
            elif field == "rating":
                product_data = st.session_state.product_data[idx].get("json", {})
                rating = product_data.get("average_rating", "N/A")
            
                # Format total review count
                raw_count = product_data.get("total_reviews")
                if isinstance(raw_count, int):
                    if raw_count < 100:
                        count_display = str(raw_count)
                    else:
                        rounded = (raw_count // 100) * 100
                        count_display = f"{rounded}+"
                else:
                    count_display = "N/A"
            
                # Start rating line
                rating_str = f"⭐ {rating} [👤 {count_display}]"
            
                # Pull 4-star and 5-star percentages from correct keys
                pct_4 = int(product_data.get("4_star_percentage", 0))
                pct_5 = int(product_data.get("5_star_percentage", 0))
                total_pct = pct_4 + pct_5
            
                if pct_4 or pct_5:
                    rating_str += f" {total_pct}%<br>5⭐ {pct_5}% - 4⭐ {pct_4}%"
            
                st.markdown(rating_str, unsafe_allow_html=True)
            
            # Image Gallery
            elif field == "imageGallery":
                imgs = product_data.get("images", [])
                if imgs:
                    st.image(imgs, width=200, caption=None, use_container_width="True")
                else:
                    st.markdown("🖼️ No images found")

            # Generic field
            else:
                st.write(f"**{field.capitalize()}**: {value or 'N/A'}")




# ----------- MAIN -----------
display_field_selector()

button_cols = st.columns([0.5, 0.5])

with button_cols[0]:
    if st.button("➕ Add Product Column", help="Add a new Amazon product for comparison"):
        st.session_state.num_columns += 1
        st.rerun()

with button_cols[1]:
    if st.button("🛠 Dev Mode"):
        components.html(
            """
            <style>
            #dev-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.2);
                z-index: 9999;
                cursor: crosshair;
            }
            #dev-banner {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background: #333;
                color: white;
                padding: 10px 15px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                font-family: sans-serif;
                z-index: 10000;
            }
            </style>
    
            <div id="dev-overlay"></div>
            <div id="dev-banner">🛠 Dev Mode: Click any element to give feedback...</div>
    
            <script>
            const overlay = document.getElementById("dev-overlay");
            const banner = document.getElementById("dev-banner");
    
            overlay.addEventListener("click", function(e) {
                e.preventDefault();
                e.stopPropagation();
                let el = document.elementFromPoint(e.clientX, e.clientY);
                if (!el) return;
    
                const outerHTML = el.outerHTML;
                const body = encodeURIComponent("Feedback on element:\\n\\n" + outerHTML);
                const gmailUrl = "https://mail.google.com/mail/?view=cm&fs=1&to=youremail@example.com&su=Dev Feedback&body=" + body;
    
                window.open(gmailUrl, "_blank");
    
                overlay.remove();
                banner.remove();
            }, { once: true });
            </script>
            """,
            height=0
        )


cols = st.columns(st.session_state.num_columns)

for i in range(st.session_state.num_columns):
    if i >= len(st.session_state.product_data):
        st.session_state.product_data.append({"url": ""})
    with cols[i]:
        render_product_column(i, st.session_state.product_data[i], st.session_state.visible_fields)

# ----------- RIGHT CLICK TO DEV -----------

components.html("""
<style>
#devbar {
  position: fixed;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  background: #333;
  color: white;
  padding: 6px 12px;
  border-radius: 5px;
  cursor: pointer;
  font-family: sans-serif;
  font-size: 14px;
  z-index: 9999;
  display: none;
}
#devpanel {
  position: fixed;
  top: 50px;
  left: 50%;
  transform: translateX(-50%);
  width: 300px;
  background: white;
  padding: 15px;
  box-shadow: 0 0 10px rgba(0,0,0,0.3);
  font-family: sans-serif;
  display: none;
  z-index: 9999;
}
#devpanel textarea {
  width: 100%;
  height: 60px;
  margin-bottom: 8px;
}
#devpanel input {
  width: 100%;
  margin-bottom: 8px;
  padding: 6px;
}
</style>

<div id="devbar">Right Click to Dev</div>
<div id="devpanel">
  <textarea id="devMessage" placeholder="Describe what you'd like to suggest..."></textarea>
  <input id="devEmail" type="email" placeholder="Your email">
  <button onclick="sendDev()">Send</button>
  <button onclick="cancelDev()">Cancel</button>
</div>

<script>
document.addEventListener('contextmenu', function(e) {
  e.preventDefault();
  document.getElementById('devbar').style.display = 'block';
});

document.getElementById('devbar').addEventListener('click', function() {
  this.style.display = 'none';
  document.getElementById('devpanel').style.display = 'block';
});

function sendDev() {
  const msg = document.getElementById('devMessage').value;
  const email = document.getElementById('devEmail').value;
  if (!msg || !email) {
    alert("Please fill in both the message and email.");
    return;
  }

  const pageInfo = "Page element context: " + document.activeElement.outerHTML;
  const body = encodeURIComponent(msg + "\\n\\n---\\n" + pageInfo);
  const mailto = `https://mail.google.com/mail/?view=cm&fs=1&to=${email}&su=Dev Feedback&body=${body}`;
  window.open(mailto, '_blank');
  document.getElementById('devpanel').style.display = 'none';
}

function cancelDev() {
  if (confirm("Are you sure you want to cancel?")) {
    document.getElementById('devpanel').style.display = 'none';
  }
}
</script>
""", height=0)

