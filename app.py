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

    # Inject a persistent red ">>" overlay button that appears when the sidebar is collapsed.
    # components.html runs in a same-origin iframe on Streamlit Cloud, so window.parent.document works.
    import streamlit.components.v1 as components
    components.html("""
        <script>
        (function() {
            var doc;
            try { doc = window.parent.document; var _t = doc.body; }
            catch(e) { return; }  // cross-origin guard

            // Idempotent: reuse button if already exists (Streamlit reruns this on every rerender)
            var btn = doc.getElementById('__tessera_sb__');
            if (!btn) {
                btn = doc.createElement('button');
                btn.id = '__tessera_sb__';
                btn.innerHTML = '&#x276F;&#x276F;';
                btn.title = 'Open sidebar';
                Object.assign(btn.style, {
                    position:'fixed', top:'12px', left:'12px',
                    zIndex:'9999999', background:'#D62F3A', color:'#fff',
                    border:'none', borderRadius:'8px', padding:'6px 12px',
                    fontSize:'15px', fontWeight:'bold', cursor:'pointer',
                    boxShadow:'0 4px 12px rgba(214,47,58,0.5)',
                    lineHeight:'1.2', display:'none',
                    alignItems:'center', justifyContent:'center'
                });
                btn.addEventListener('click', function() {
                    var sels = [
                        '[data-testid="stSidebarCollapseButton"] button',
                        '[data-testid="stSidebarCollapsedControl"] button',
                        '[data-testid="collapsedControl"] button',
                        'button[aria-label="Open sidebar"]',
                        'button[aria-label="open sidebar"]',
                        'button[aria-label*="sidebar"]',
                        'button[aria-label*="Sidebar"]'
                    ];
                    for (var i = 0; i < sels.length; i++) {
                        var target = doc.querySelector(sels[i]);
                        if (target) { target.click(); return; }
                    }
                });
                doc.body.appendChild(btn);
            }

            function isCollapsed() {
                var sb = doc.querySelector('section[data-testid="stSidebar"]');
                if (!sb) return false;
                if (sb.getAttribute('aria-expanded') === 'false') return true;
                var r = sb.getBoundingClientRect();
                return r.width < 30 || r.left < -60;
            }

            function sync() {
                btn.style.display = isCollapsed() ? 'flex' : 'none';
            }

            sync();

            // One-time observer (persists across Streamlit rerenders)
            if (!doc.__tessera_observer__) {
                doc.__tessera_observer__ = new MutationObserver(sync);
                doc.__tessera_observer__.observe(doc.body, {
                    attributes: true, subtree: true, childList: true,
                    attributeFilter: ['aria-expanded', 'style', 'class']
                });
            }
        })();
        </script>
    """, height=0)

    # Inject layout & header removal CSS
    st.markdown("""
        <style>
        /* Transparent Header */
        [data-testid="stHeader"] {
            background-color: transparent !important;
            background: transparent !important;
        }


        /* Ensure sidebar stays visible when expanded */
        section[data-testid="stSidebar"][aria-expanded="true"] {
            display: flex !important;
            visibility: visible !important;
            transform: none !important;
            left: 0 !important;
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
        
        /* ══════════════════════════════════════════════════════
           RED MOSAIC TABS — Polygon Angled Mosaic Aesthetic
           ══════════════════════════════════════════════════════ */

        /* Tab list bar — no gap, overlapping mosaic */
        [data-testid="stTabs"] [data-baseweb="tab-list"],
        div[data-testid="stTabs"] div[data-baseweb="tab-list"] {
            gap: 2px !important;
            background-color: transparent !important;
            padding-bottom: 0px !important;
            border-bottom: none !important;
        }

        /* Individual tabs — angled polygon shape */
        [data-testid="stTabs"] [role="tab"],
        [data-testid="stTabs"] [data-baseweb="tab"] {
            background-color: rgba(214, 47, 58, 0.08) !important;
            border: none !important;
            border-radius: 0 !important;
            clip-path: polygon(10% 0, 100% 0, 90% 100%, 0% 100%) !important;
            -webkit-clip-path: polygon(10% 0, 100% 0, 90% 100%, 0% 100%) !important;
            margin-left: -8px !important;
            padding: 10px 24px !important;
            transition: all 0.2s ease !important;
            cursor: pointer !important;
        }

        /* First tab — flat left edge */
        [data-testid="stTabs"] [role="tab"]:first-child,
        [data-testid="stTabs"] [data-baseweb="tab"]:first-child {
            clip-path: polygon(0 0, 100% 0, 90% 100%, 0% 100%) !important;
            -webkit-clip-path: polygon(0 0, 100% 0, 90% 100%, 0% 100%) !important;
            margin-left: 0 !important;
        }

        /* Hover */
        [data-testid="stTabs"] [role="tab"]:hover,
        [data-testid="stTabs"] [data-baseweb="tab"]:hover {
            background-color: rgba(214, 47, 58, 0.25) !important;
        }

        /* Active / selected tab */
        [data-testid="stTabs"] [role="tab"][aria-selected="true"],
        [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
            background-color: #D62F3A !important;
            border-bottom: 3px solid #D62F3A !important;
            box-shadow: inset 0 -10px 20px -10px rgba(214, 47, 58, 0.6) !important;
        }

        /* Active tab text */
        [data-testid="stTabs"] [role="tab"][aria-selected="true"] *,
        [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p,
        [data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] span {
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
