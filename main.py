import streamlit as st
st.set_page_config(page_title="Core Integra", page_icon=":office:", layout="wide")
 
import pf_full_code
import bank_full_code
import esic_full_code
import archive_full_code
import base64
from streamlit_cookies_manager import EncryptedCookieManager
 
# ---------- CSS ---------- #
login_css = """
<style>
#MainMenu, header, footer {visibility: hidden;}
.login-box { text-align: center; margin: 0 auto; }
.login-title { color: #004D7C; font-size: 24px; font-weight: 600; margin-bottom: 25px; }
.stTextInput > div > div > input { border-radius: 6px; padding: 10px; border: 1px solid #ccc; }
.stButton > button {
    background-color: #004D7C;
    color: white;
    font-weight: 500;
    padding: 10px 16px;
    border: none;
    border-radius: 6px;
    margin-top: 20px;
}
.stButton > button:hover { background-color: #5F9EA0; }
input[type="password"]::-ms-reveal,
input[type="password"]::-ms-clear {
    display: none;
}
</style>
"""
 
sidebar_css = """
<style>
#MainMenu, header, footer {visibility: hidden;}
.block-container {padding-top: 1rem;}
 
/* ONLY Sidebar Changes - keeps main content untouched */
[data-testid="stSidebar"] {
    position: fixed;
    width: 15rem !important;
    min-width: 15rem !important;
    max-width: 15rem !important;
}
 
/* Remove sidebar resize handle */
[data-testid="stSidebarResizeHandle"] {
    display: none !important;
}
 
/* Remove collapse button */
button[data-testid="baseButton-header"] {
    display: none !important;
}
 
/* Original sidebar styles remain unchanged */
.stButton > button {
    background-color: #004D7C;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 15px;
    margin: 8px 0;
    width: 100%;
}
.stButton > button:hover { background-color: #5F9EA0; }
[data-testid="stSidebar"] .stButton:last-of-type button {
    background-color: navy !important;
    color: white !important;
}
[data-testid="stSidebar"] .stButton:last-of-type button:hover {
    background-color: darkred !important;
}
[data-testid="stRadio"] label {
    font-size: 18px !important;
}
[data-testid="stRadio"] input[type="radio"] {
    transform: scale(1.5);
}
[data-testid="stSidebar"]::-webkit-scrollbar { display: none; }
[data-testid="stSidebar"] { -ms-overflow-style: none; scrollbar-width: none; }
</style>
"""
 
def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()
 
# ---------- Cookie Manager ---------- #
cookies = EncryptedCookieManager(prefix="core_integra_", password="a_very_secret_key")
if not cookies.ready():
    st.stop()
 
# ---------- Session Init ---------- #
if "authenticated" not in st.session_state:
    cookie_auth = cookies.get("authenticated")
    st.session_state.authenticated = cookie_auth == "true"
 
if "selected_section" not in st.session_state:
    st.session_state.selected_section = None
 
# ---------- Main Logic ---------- #
def main():
    if not st.session_state.authenticated:
        show_login_page()
    else:
        st.markdown(sidebar_css, unsafe_allow_html=True)
        show_sidebar()
        show_selected_dashboard()  # No changes to main content area
 
def show_login_page():
    st.markdown(login_css, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        logo_b64 = get_base64_image("C:/Users/Admin/streamlit doc/CORE_SIDEBAR/CORE_SIDEBAR/logo.jpg")
        st.markdown(f"""
        <div class="login-box">
            <img src="data:image/jpeg;base64,{logo_b64}" alt="logo" />
            <div class="login-title">Welcome to File Processing System</div>
        </div>
        """, unsafe_allow_html=True)
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if username == "admin" and password == "password":
                st.session_state.authenticated = True
                cookies["authenticated"] = "true"
                cookies.save()
                st.rerun()
            else:
                st.error("Invalid username or password")
 
def show_sidebar():
    with st.sidebar:
        logo_b64 = get_base64_image("C:/Users/Admin/streamlit doc/CORE_SIDEBAR/CORE_SIDEBAR/logo.jpg")
        st.markdown(
            f'<img src="data:image/jpeg;base64,{logo_b64}" alt="logo" style="width:160px;border-radius:10px;">',
            unsafe_allow_html=True
        )
        st.markdown("---")
 
        options = {
            "PF": "pf",
            "BANK": "bank",
            "ESIC": "esic",
            "ARCHIVE": "archive"
        }
        selected_option = st.radio("Select Section", list(options.keys()))
        st.session_state.selected_section = options[selected_option]
 
        st.markdown("---")
        if st.button("LOGOUT"):
            st.session_state.authenticated = False
            cookies["authenticated"] = "false"
            cookies.save()
            st.rerun()
 
def show_selected_dashboard():
    section = st.session_state.selected_section
    if section == 'pf':
        pf_full_code.run_pf_section()
    elif section == 'bank':
        bank_full_code.run_bank_section()
    elif section == 'esic':
        esic_full_code.run_esic_section()
    elif section == 'archive':
        archive_full_code.run_archive_section()
    else:
        st.subheader("Welcome to Core Integra! Use the sidebar to choose a section.")
 
if __name__ == "__main__":
    main()
 