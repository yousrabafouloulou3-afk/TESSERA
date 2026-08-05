import streamlit as st
import os
import sys

# Ensure current directory is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from auth import init_auth, login_screen, logout
from database import init_db
from translations import tr

# Load views
import views.admin as admin
import views.teacher as teacher
import views.student as student
import views.settings as settings

from PIL import Image

# Load custom logo for page icon
logo_img = "📅"
logo_path = os.path.join("assets", "tessera_logo.png")
if os.path.exists(logo_path):
    try:
        logo_img = Image.open(logo_path)
    except Exception:
        pass

st.set_page_config(page_title="TESSERA", page_icon=logo_img, layout="wide", initial_sidebar_state="expanded")

# Initialise language setting
if 'language' not in st.session_state:
    st.session_state.language = 'English'

if 'night_mode' not in st.session_state:
    st.session_state.night_mode = False

if st.session_state.night_mode:
    st.markdown("""
        <style>
        /* Comprehensive Dark Mode Injection */
        html, body, .stApp, .stApp > header, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {
            background-color: #0e1117 !important;
            color: #fafafa !important;
        }
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
            background-color: #262730 !important;
        }
        [data-testid="stSidebar"] * {
            color: #fafafa !important;
        }
        /* Fix ALL Icons (SVGs and Material Font Icons like the password eye and select caret) */
        svg, svg *, path, [data-baseweb="icon"], [data-baseweb="icon"] *, .material-symbols-rounded, .material-icons, [data-testid="stIconMaterial"] {
            fill: #fafafa !important;
            stroke: #fafafa !important;
            color: #fafafa !important;
        }
        /* Force everything inside text inputs and selectboxes to be white (including the eye button) */
        [data-baseweb="input"] *, [data-baseweb="select"] * {
            color: #fafafa !important;
            fill: #fafafa !important;
        }
        /* Keep checkbox inner tick visible */
        [data-baseweb="checkbox"] svg, [data-baseweb="checkbox"] path { 
            fill: none !important; 
            stroke: #fafafa !important;
        }
        /* Buttons, forms and all clickable elements */
        .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
            background-color: #262730 !important;
            color: #ffffff !important;
            border-color: #4b4b4b !important;
        }
        .stButton > button *, .stDownloadButton > button *, .stFormSubmitButton > button * {
            color: #ffffff !important;
        }
        .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
            border-color: #ff4b4b !important;
            color: #ff4b4b !important;
        }
        /* Inputs and dropdowns */
        div[data-baseweb="select"] > div, input, div[data-baseweb="input"], textarea {
            background-color: #1e1e1e !important;
            color: #fafafa !important;
            border-color: #4b4b4b !important;
        }
        /* Dropdown popover list items */
        div[data-baseweb="popover"] > div, div[data-baseweb="popover"] ul {
            background-color: #262730 !important;
        }
        div[data-baseweb="popover"] * {
            color: #fafafa !important;
        }
        div[data-baseweb="popover"] li:hover {
            background-color: #4b4b4b !important;
        }
        /* Dataframes */
        [data-testid="stDataFrame"], [data-testid="stDataFrame"] * {
            background-color: #1e1e1e !important;
            color: #fafafa !important;
        }
        </style>
    """, unsafe_allow_html=True)


# Inject minimal modern CSS
st.markdown("""
    <style>
    .stAppDeployButton {display:none !important;}
    .stApp {
        background-color: transparent;
    }
    .main-header {
        font-family: 'Inter', sans-serif;
        color: #2b2b2b;
    }
    
    /* Modern 'Mosaic' Tabs (Red Aesthetic) */
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 2px;
        background-color: transparent;
        padding-bottom: 0px;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        background-color: rgba(128, 128, 128, 0.05) !important;
        border: none !important;
        border-radius: 0 !important;
        clip-path: polygon(10% 0, 100% 0, 90% 100%, 0% 100%);
        margin-left: -10px;
        padding: 10px 25px !important;
        transition: all 0.3s ease;
    }
    [data-testid="stTabs"] [data-baseweb="tab"]:first-child {
        clip-path: polygon(0 0, 100% 0, 90% 100%, 0% 100%);
        margin-left: 0;
    }
    [data-testid="stTabs"] [data-baseweb="tab"]:hover {
        background-color: rgba(128, 128, 128, 0.1) !important;
    }
    [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
        background-color: rgba(214, 47, 58, 0.1) !important;
        border-bottom: 3px solid #D62F3A !important;
        box-shadow: inset 0 -10px 20px -10px rgba(214, 47, 58, 0.4);
    }
    /* Hide Streamlit Default Menu and Footer */
    footer {visibility: hidden !important;}
    </style>
""", unsafe_allow_html=True)

try:
    init_db()
except Exception as e:
    st.error(f"Database initialization error: {e}")

init_auth()

def main():
    # Global Settings in Sidebar (always visible)
    with st.sidebar:
        logo_path = os.path.join("assets", "tessera_logo.png")
        if os.path.exists(logo_path):
            import base64
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
            
            text_logo_html = ""
            dark_logo_path = os.path.join("assets", "tessera_text_logo_dark_cropped.png")
            light_logo_path = os.path.join("assets", "tessera_text_logo_cropped.png")
            if os.path.exists(dark_logo_path):
                with open(dark_logo_path, "rb") as f:
                    text_logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                text_logo_html = f'<img src="data:image/png;base64,{text_logo_b64}" width="140" style="margin: 10px auto 0 auto; display: block; mix-blend-mode: difference;">'
            elif os.path.exists(light_logo_path):
                with open(light_logo_path, "rb") as f:
                    text_logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                text_logo_html = f'<img src="data:image/png;base64,{text_logo_b64}" width="140" style="margin: 10px auto 0 auto; display: block;">'
            else:
                text_logo_html = "<h2 style='margin-top: 10px; margin-bottom: 0px; font-family: \"Inter\", sans-serif; text-align: center;'>TESSERA</h2>"

            st.markdown(
                f"""
                <div style="text-align: center; margin-bottom: 20px;">
                    <img src="data:image/png;base64,{logo_b64}" width="80" style="margin: 0 auto; display: block; border-radius: 10px;">
                    {text_logo_html}
                </div>
                """,
                unsafe_allow_html=True
            )
        
        st.markdown(f"### {tr('Global Settings')}")
        
        languages_options = ["English", "French"]
        try:
            current_lang_idx = languages_options.index(st.session_state.language)
        except ValueError:
            current_lang_idx = 0
            
        selected_lang = st.selectbox(
            tr("Language / Langue"), 
            languages_options, 
            index=current_lang_idx
        )
        if selected_lang != st.session_state.language:
            st.session_state.language = selected_lang
            st.rerun()
            
        st.markdown("<br>", unsafe_allow_html=True)
        # Beautiful Telegram-style Night Mode Toggle
        col1, col2 = st.columns([8, 2])
        with col1:
            st.markdown(f"**🌙 {tr('Mode Nuit' if st.session_state.language == 'French' else 'Night Mode')}**")
        with col2:
            night_mode_toggle = st.toggle(" ", value=st.session_state.night_mode, key="night_mode_toggle_ui", label_visibility="collapsed")
            
        if night_mode_toggle != st.session_state.night_mode:
            st.session_state.night_mode = night_mode_toggle
            st.rerun()

        sidebar_slot = st.empty()
        
        if st.session_state.user is None:
            sidebar_slot.empty()
            nav_page = None
        else:
            with sidebar_slot.container():
                st.markdown(f"### {tr('🌐 Portal Navigation')}")
                
                role = st.session_state.user['role']
                pic_path = os.path.join("profile_pics", f"{st.session_state.user['username']}.png")
                default_path = os.path.join("profile_pics", "default_avatar.svg")
                
                import base64
                img_src = ""
                if os.path.exists(pic_path):
                    with open(pic_path, "rb") as f:
                        pic_b64 = base64.b64encode(f.read()).decode("utf-8")
                    img_src = f"data:image/png;base64,{pic_b64}"
                elif os.path.exists(default_path):
                    with open(default_path, "rb") as f:
                        pic_b64 = base64.b64encode(f.read()).decode("utf-8")
                    img_src = f"data:image/svg+xml;base64,{pic_b64}"
                    
                if img_src:
                    st.markdown(
                        f"""
                        <div style="text-align: center; margin-bottom: 10px;">
                            <img src="{img_src}" width="100" height="100" style="border-radius: 50%; object-fit: cover; border: 2px solid #D62F3A; background-color: #f0f0f0;">
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                st.write(f"{tr('Logged in as:')} **{st.session_state.user['username']}**")
                
                role_display = tr(role.capitalize())
                st.caption(f"{tr('Role:')} {role_display}")
                
                nav_dashboard = tr("📊 Dashboard")
                nav_settings = tr("⚙️ Account Settings")
                nav_faq = tr("❓ Help & FAQ")
                
                nav_options = [nav_dashboard, nav_settings]
                if role != 'student':
                    nav_options.append(nav_faq)
                    
                nav_page = st.radio(tr("Go to:"), nav_options)
                
                st.divider()
                if st.button(tr("🚪 Logout"), type="primary", use_container_width=True):
                    logout()

    main_slot = st.empty()

    if st.session_state.user is None:
        main_slot.empty()
        with main_slot.container():
            login_screen()
    else:
        role = st.session_state.user['role']
        main_slot.empty()
        with main_slot.container():
            if nav_page == nav_dashboard:
                if role == 'admin':
                    admin.show()
                elif role == 'teacher':
                    teacher.show()
                elif role in ('student', 'delegate'):
                    student.show()
            elif nav_page == nav_settings:
                settings.show()
            elif nav_page == nav_faq:
                import views.faq
                views.faq.show()

if __name__ == "__main__":
    main()
