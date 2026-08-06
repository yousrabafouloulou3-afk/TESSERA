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

    # Restore sidebar auto-expand overlay JS (CSS-only approach was unreliable on Streamlit Cloud)
    st.html("""
        <script>
        (function() {
            function reactClick(el) {
                ['mousedown', 'mouseup', 'click'].forEach(function(t) {
                    el.dispatchEvent(new MouseEvent(t, {bubbles: true, cancelable: true}));
                });
            }
            function findExpandBtn() {
                var sels = [
                    '[data-testid="stSidebarCollapsedControl"] button',
                    'button[aria-label="Open sidebar"]',
                    'button[aria-label="open sidebar"]',
                    'button[aria-label*="sidebar"]',
                    'button[aria-label*="Sidebar"]'
                ];
                for (var i = 0; i < sels.length; i++) {
                    var el = document.querySelector(sels[i]);
                    if (el) return el;
                }
                return null;
            }
            function createOverlayBtn() {
                var b = document.getElementById('__tessera_sb__');
                if (b) return b;
                b = document.createElement('button');
                b.id = '__tessera_sb__';
                b.innerHTML = '&#x276F;&#x276F;';
                b.title = 'Open sidebar';
                Object.assign(b.style, {
                    position:'fixed', top:'12px', left:'12px',
                    zIndex:'9999999', background:'#D62F3A', color:'#fff',
                    border:'none', borderRadius:'8px', padding:'6px 12px',
                    fontSize:'15px', fontWeight:'bold', cursor:'pointer',
                    display:'none', boxShadow:'0 4px 12px rgba(214,47,58,0.5)',
                    lineHeight:'1.2'
                });
                b.addEventListener('click', function() {
                    var nb = findExpandBtn();
                    if (nb) reactClick(nb);
                });
                document.body.appendChild(b);
                return b;
            }
            function isCollapsed() {
                var s = document.querySelector('[data-testid="stSidebar"]');
                if (!s) return false;
                var r = s.getBoundingClientRect();
                return r.width < 20 || r.left < -50;
            }
            function sync() {
                var b = createOverlayBtn();
                b.style.display = isCollapsed() ? 'flex' : 'none';
            }
            function autoExpand() {
                if (isCollapsed()) {
                    var nb = findExpandBtn();
                    if (nb) reactClick(nb);
                }
            }
            function init() {
                document.documentElement.setAttribute('data-theme','dark');
                document.body.setAttribute('data-theme','dark');
                var a = document.querySelector('.stApp');
                if (a) a.setAttribute('data-theme','dark');
                createOverlayBtn();
                new MutationObserver(sync).observe(document.body, {attributes:true, subtree:true, childList:true});
                sync();
                // Auto-expand sidebar on first load
                setTimeout(autoExpand, 400);
                setTimeout(autoExpand, 1200);
                setTimeout(sync, 400);
                setTimeout(sync, 1200);
                window.addEventListener('resize', sync);
            }
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
            else init();
        })();
        </script>
    """)

    # Inject layout & header removal CSS
    st.markdown("""
        <style>
        /* Transparent Header */
        [data-testid="stHeader"] {
            background-color: transparent !important;
            background: transparent !important;
        }


        /* ── Sidebar Collapse button (<<) ── */
        [data-testid="stSidebarHeader"] button,
        section[data-testid="stSidebar"] button[kind="header"] {
            visibility: visible !important;
            opacity: 1 !important;
            display: flex !important;
            pointer-events: auto !important;
        }

        /* ── Sidebar Expand button (>>) — shown when sidebar is collapsed ── */
        /* Streamlit renders this div only when collapsed; we pin it top-left and style it red */
        [data-testid="stSidebarCollapsedControl"],
        div[data-testid="stSidebarCollapsedControl"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: fixed !important;
            top: 10px !important;
            left: 10px !important;
            z-index: 9999999 !important;
            pointer-events: auto !important;
        }

        [data-testid="stSidebarCollapsedControl"] button {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            background-color: #D62F3A !important;
            color: #ffffff !important;
            border: none !important;
            border-radius: 8px !important;
            padding: 6px 12px !important;
            font-size: 15px !important;
            font-weight: bold !important;
            cursor: pointer !important;
            box-shadow: 0 4px 12px rgba(214,47,58,0.5) !important;
            pointer-events: auto !important;
        }

        [data-testid="stSidebarCollapsedControl"] button svg,
        [data-testid="stSidebarCollapsedControl"] button path {
            fill: #ffffff !important;
            stroke: #ffffff !important;
            color: #ffffff !important;
        }


        /* Hide ONLY top-right action buttons (Fork app, Deploy button, GitHub link) */
        .stAppDeployButton,
        [data-testid="stToolbar"],
        [data-testid="stHeader"] a[href*="github"] {
            display: none !important;
            visibility: hidden !important;
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
        
        /* High specificity Red Mosaic Tabs Styling for Streamlit 1.61 */
        [data-testid="stTabs"] [data-baseweb="tab-list"],
        div[data-testid="stTabs"] div[data-baseweb="tab-list"] {
            gap: 6px !important;
            background-color: transparent !important;
            padding-bottom: 2px !important;
            border-bottom: 2px solid rgba(214, 47, 58, 0.3) !important;
        }

        div[data-testid="stTabs"] button,
        div[data-testid="stTabs"] button[role="tab"], 
        div[data-testid="stTabs"] [data-baseweb="tab"],
        [data-testid="stTabs"] button[id*="tab"] {
            background-color: rgba(128, 128, 128, 0.15) !important;
            border: 1px solid rgba(128, 128, 128, 0.25) !important;
            border-bottom: none !important;
            border-radius: 6px 6px 0 0 !important;
            margin-right: 4px !important;
            padding: 8px 20px !important;
            transition: all 0.2s ease-in-out !important;
        }

        div[data-testid="stTabs"] button *,
        div[data-testid="stTabs"] button[role="tab"] *, 
        div[data-testid="stTabs"] [data-baseweb="tab"] * {
            color: #a0a5b5 !important;
        }

        div[data-testid="stTabs"] button:hover,
        div[data-testid="stTabs"] button[role="tab"]:hover, 
        div[data-testid="stTabs"] [data-baseweb="tab"]:hover {
            background-color: rgba(214, 47, 58, 0.25) !important;
            border-color: rgba(214, 47, 58, 0.5) !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"],
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"], 
        div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"],
        [data-testid="stTabs"] button[id*="tab"][aria-selected="true"] {
            background-color: #D62F3A !important;
            border-color: #D62F3A !important;
            box-shadow: 0 4px 12px rgba(214, 47, 58, 0.5) !important;
        }

        div[data-testid="stTabs"] button[aria-selected="true"] *,
        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] *, 
        div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] *,
        div[data-testid="stTabs"] button[aria-selected="true"] p,
        div[data-testid="stTabs"] button[aria-selected="true"] span {
            color: #ffffff !important;
            font-weight: 700 !important;
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
