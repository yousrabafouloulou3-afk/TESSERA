import streamlit as st
import os
from PIL import Image

logo_img = "📅"
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "tessera_logo.png")
if os.path.exists(logo_path):
    try:
        logo_img = Image.open(logo_path)
    except Exception:
        pass

st.set_page_config(page_title="TESSERA", page_icon=logo_img, layout="wide", initial_sidebar_state="expanded")

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

def main():
    # Initialise language setting
    if 'language' not in st.session_state:
        st.session_state.language = 'English'

    if 'night_mode' not in st.session_state:
        st.session_state.night_mode = False

    import streamlit.components.v1 as components

    if st.session_state.night_mode:
        components.html("""
            <script>
                try {
                    var parentDoc = window.parent.document;
                    parentDoc.documentElement.setAttribute('data-theme', 'dark');
                    parentDoc.body.setAttribute('data-theme', 'dark');
                    var app = parentDoc.querySelector('.stApp');
                    if (app) app.setAttribute('data-theme', 'dark');
                } catch(e) {}
            </script>
        """, height=0, width=0)
        st.markdown("""
            <style>
            :root, html, body, #root, .stApp, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stDataEditor"], [data-testid="stDataFrame"] {
                --background-color: #0e1117 !important;
                --secondary-background-color: #262730 !important;
                --text-color: #ffffff !important;
                --primary-color: #D62F3A !important;
                color-scheme: dark !important;
            }
            html, body, .stApp, [data-testid="stAppViewContainer"] {
                background-color: #0e1117 !important;
                color: #ffffff !important;
            }
            [data-testid="stSidebar"], [data-testid="stSidebar"] > div {
                background-color: #262730 !important;
            }
            [data-testid="stSidebar"] *, [data-testid="stSidebar"] p, [data-testid="stSidebar"] span, [data-testid="stSidebar"] label, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
                color: #ffffff !important;
            }
            h1, h2, h3, h4, h5, h6, p, label, span, .stMarkdown {
                color: #ffffff !important;
            }
            div[data-baseweb="select"] > div, 
            div[data-baseweb="input"], 
            input, 
            textarea {
                background-color: #262730 !important;
                color: #ffffff !important;
                border: 1px solid #31333f !important;
                border-radius: 8px !important;
            }
            div[data-baseweb="popover"] > div, 
            div[data-baseweb="popover"] ul,
            div[data-baseweb="menu"] {
                background-color: #262730 !important;
                border: 1px solid #31333f !important;
                color: #ffffff !important;
            }
            div[data-baseweb="popover"] li,
            div[data-baseweb="menu"] [role="option"] {
                color: #ffffff !important;
                background-color: #262730 !important;
            }
            div[data-baseweb="popover"] li:hover,
            div[data-baseweb="menu"] [role="option"]:hover {
                background-color: #363945 !important;
            }
            [data-testid="stDataFrame"], [data-testid="stDataEditor"], div[data-testid="stDataEditor"] > div {
                background-color: #262730 !important;
                color: #ffffff !important;
            }
            [data-testid="stDataEditor"] *, [data-testid="stDataFrame"] * {
                background-color: #262730 !important;
                color: #ffffff !important;
            }
            div[data-testid="stRadio"] label, div[data-testid="stRadio"] p, div[data-testid="stRadio"] span {
                color: #ffffff !important;
            }
            [data-testid="stTabs"] [data-baseweb="tab-list"] {
                gap: 16px !important;
                background-color: transparent !important;
                border-bottom: 1px solid #31333f !important;
            }
            [data-testid="stTabs"] [data-baseweb="tab"] {
                background-color: transparent !important;
                border: none !important;
                padding: 8px 16px !important;
            }
            [data-testid="stTabs"] [data-baseweb="tab"] * {
                color: #808495 !important;
            }
            [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
                border-bottom: 2px solid #D62F3A !important;
                background-color: transparent !important;
            }
            [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] * {
                color: #D62F3A !important;
                font-weight: 600 !important;
            }
            </style>
        """, unsafe_allow_html=True)
    else:
        components.html("""
            <script>
                try {
                    var parentDoc = window.parent.document;
                    parentDoc.documentElement.setAttribute('data-theme', 'light');
                    parentDoc.body.setAttribute('data-theme', 'light');
                    var app = parentDoc.querySelector('.stApp');
                    if (app) app.setAttribute('data-theme', 'light');
                } catch(e) {}
            </script>
        """, height=0, width=0)

    # Inject minimal modern CSS
    st.markdown("""
        <style>
        /* Completely hide top right header toolbar (Fork, GitHub link, 3 dots menu) in Streamlit 1.61+ */
        header[data-testid="stHeader"],
        [data-testid="stHeader"],
        .stAppHeader,
        [data-testid="stHeaderActionElements"],
        [data-testid="stToolbar"],
        .stAppDeployButton {
            display: none !important;
            height: 0 !important;
            min-height: 0 !important;
            visibility: hidden !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }
        footer {
            visibility: hidden !important;
            display: none !important;
        }
        .stApp {
            background-color: transparent;
        }
        .main-header {
            font-family: 'Inter', sans-serif;
        }
        </style>
    """, unsafe_allow_html=True)

    try:
        init_db()
    except Exception as e:
        st.error(f"Database initialization error: {e}")

    init_auth()

    is_logged_in = st.session_state.get('user') is not None
    nav_page = None  # Will be set in sidebar if logged in

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
            current_lang_idx = languages_options.index(st.session_state.get('language', 'English'))
        except ValueError:
            current_lang_idx = 0
            
        def _on_lang_change():
            st.session_state.language = st.session_state.lang_select_key

        st.selectbox(
            tr("Language / Langue"), 
            languages_options, 
            index=current_lang_idx,
            key="lang_select_key",
            on_change=_on_lang_change
        )
            
        st.markdown("<br>", unsafe_allow_html=True)
        # Beautiful Telegram-style Night Mode Toggle
        col1, col2 = st.columns([8, 2])
        with col1:
            st.markdown(f"**🌙 {tr('Mode Nuit' if st.session_state.language == 'French' else 'Night Mode')}**")
        with col2:
            st.toggle(" ", key="night_mode", label_visibility="collapsed")

        if st.session_state.get('user') is not None:
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
            st.button(tr("🚪 Logout"), type="primary", use_container_width=True, key="sidebar_logout_btn", on_click=logout)

    if st.session_state.get('user') is None:
        login_screen()
    elif nav_page is None:
        # User just logged in on this run — nav_page wasn't set in sidebar yet; rerun to render cleanly
        st.rerun()
    else:
        role = st.session_state.user['role']
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
