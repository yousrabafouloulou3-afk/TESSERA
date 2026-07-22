import streamlit as st
from translations import tr

def init_auth():
    if 'user' not in st.session_state:
        st.session_state.user = None
    if 'night_mode_visual' not in st.session_state:
        st.session_state.night_mode_visual = False

def login_screen():
    import os
    
    logo_path = os.path.join("assets", "tessera_logo.png")
    if os.path.exists(logo_path):
        import base64
        try:
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Use the white text logo with difference blending to automatically adapt to light/dark backgrounds
            logo_file = os.path.join("assets", "tessera_text_logo_dark_cropped.png")
            fallback_logo_file = os.path.join("assets", "tessera_text_logo_cropped.png")
            
            # Load text logo if it exists
            text_logo_html = ""
            if os.path.exists(logo_file):
                with open(logo_file, "rb") as f:
                    text_logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                text_logo_html = f'<img src="data:image/png;base64,{text_logo_b64}" width="220" style="margin: 15px auto 25px auto; display: block; mix-blend-mode: difference;">'
            elif os.path.exists(fallback_logo_file):
                # Fallback to light logo (black text) if dark logo is missing
                with open(fallback_logo_file, "rb") as f:
                    text_logo_b64 = base64.b64encode(f.read()).decode("utf-8")
                text_logo_html = f'<img src="data:image/png;base64,{text_logo_b64}" width="220" style="margin: 15px auto 25px auto; display: block;">'
            else:
                text_logo_html = "<h2 style='margin-top: 10px; margin-bottom: 20px; font-family: \"Inter\", sans-serif; text-align: center;'>TESSERA</h2>"

            st.markdown(
                f"""
                <div style="text-align: center;">
                    <img src="data:image/png;base64,{logo_b64}" width="90" style="margin: 0 auto; display: block; border-radius: 10px; position: relative; left: -10px;">
                    {text_logo_html}
                    <p style="margin-top: -15px; margin-bottom: 25px; color: #888; font-family: 'Inter', sans-serif; font-size: 14px; letter-spacing: 2px;">SMART SCHEDULING</p>
                </div>
                """,
                unsafe_allow_html=True
            )
        except Exception:
            st.markdown(f"<h1 style='text-align: center;'>{tr('Welcome to TESSERA')}</h1><p style='text-align: center; color: gray; letter-spacing: 2px; margin-top: -15px; margin-bottom: 30px;'>SMART SCHEDULING</p>", unsafe_allow_html=True)
    else:
        st.markdown(f"<h1 style='text-align: center;'>{tr('Welcome to TESSERA')}</h1><p style='text-align: center; color: gray; letter-spacing: 2px; margin-top: -15px; margin-bottom: 30px;'>SMART SCHEDULING</p>", unsafe_allow_html=True)
    
    auth_mode = st.radio(tr("Choose Action"), [tr("Login"), tr("Sign Up")], horizontal=True)
    
    if auth_mode == tr("Login"):
        with st.container():
            st.markdown(f"### {tr('Please enter your credentials')}")
            with st.form("login_form"):
                username = st.text_input(tr("Username"))
                password = st.text_input(tr("Password"), type="password")
                submitted = st.form_submit_button(tr("Login"))
                
                if submitted:
                    from database import get_db_connection
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT * FROM Users WHERE username=? AND password=?", (username, password))
                    user_row = c.fetchone()
                    conn.close()
                    
                    if user_row:
                        st.session_state.user = {
                            "username": user_row["username"],
                            "role": user_row["role"],
                            "linked_id": user_row["linked_id"],
                            "linked_level": user_row["linked_level"]
                        }
                        st.success(f"{tr('Welcome back, ')}{username}!")
                        st.rerun()
                    else:
                        st.error(tr("Invalid username or password. Please try again."))
    else:
        st.markdown(f"### {tr('Create an Account')}")
        role = st.selectbox(tr("I am a:"), ["Student", "Professor", "Administration"], index=None, placeholder=tr("Select your role..."), format_func=tr)
        if role:
            from database import get_db_connection
            conn = get_db_connection()
            c = conn.cursor()

            target_id = None
            target_level = None
            is_delegate = False
            is_admin_authorized = False

            if role == "Professor":
                st.info(tr("Professors log in using their Matricule for security."))
                prof_mat = st.text_input(tr("Enter your Professor Matricule (exactly as printed on your card)"))
                if prof_mat:
                    c.execute("SELECT ID_P FROM Profs WHERE matricule = ?", (prof_mat.strip(),))
                    prof_row = c.fetchone()
                    if prof_row:
                        target_id = prof_row['ID_P']
                        c.execute("SELECT id FROM Users WHERE role = 'teacher' AND linked_id = ?", (target_id,))
                        if c.fetchone():
                            st.error(tr("Impossible. An account has already been created for this matricule."))
                            target_id = None
                        else:
                            st.success(tr("Professor identity confirmed."))
                    else:
                        st.error(tr("Invalid Matricule. Please check your card or contact administration."))

            elif role == "Administration":
                st.info(tr("Administrative accounts require a secret university key for security."))
                admin_key = st.text_input(tr("Enter Secret Admin Key"), type="password")
                if admin_key:
                    if admin_key == "PFE2026":
                        st.success(tr("Admin key confirmed. You can now choose your personal login details."))
                        is_admin_authorized = True
                    else:
                        st.error(tr("Invalid Secret Key!"))
                        is_admin_authorized = False
                else:
                    is_admin_authorized = False

            elif role == "Student":
                is_delegate = st.checkbox(tr("I am a Section Delegate"))
                if is_delegate:
                    st.info(tr("Section Delegates must verify their matricule for security."))
                    delegate_mat = st.text_input(tr("Enter your Delegate Matricule (exactly as provided by administration)"))
                    if delegate_mat:
                        c.execute("SELECT section_id FROM Delegates WHERE matricule = ?", (delegate_mat.strip(),))
                        del_row = c.fetchone()
                        if del_row:
                            c.execute("""
                                SELECT id FROM Users 
                                WHERE role = 'delegate' AND linked_id IN (
                                    SELECT ID_E FROM Entities WHERE sectionID = ? OR ID_E = ?
                                )
                            """, (del_row['section_id'], del_row['section_id']))
                            if c.fetchone():
                                st.error(tr("Impossible. An account has already been created for this delegate matricule."))
                                target_id = None
                            else:
                                # Fetch all groups belonging to this section
                                c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 0 AND sectionID = ?", (del_row['section_id'],))
                                groups = c.fetchall()
                                if groups:
                                    if len(groups) == 1:
                                        target_id = groups[0]['ID_E']
                                        st.success(f"{tr('Delegate identity confirmed and automatically linked to group: ')}{groups[0]['nameE']}.")
                                    else:
                                        group_options = {g['ID_E']: g['nameE'] for g in groups}
                                        selected_group_id = st.selectbox(
                                            tr("Select the Group you belong to"), 
                                            options=list(group_options.keys()), 
                                            format_func=lambda x: group_options[x], 
                                            placeholder=tr("Choose Group..."), 
                                            index=None
                                        )
                                        if selected_group_id:
                                            target_id = selected_group_id
                                            st.success(tr("Delegate identity and group confirmed."))
                                        else:
                                            target_id = None
                                else:
                                    target_id = del_row['section_id']
                                    st.success(tr("Delegate identity confirmed (no group found, linked to section directly)."))
                        else:
                            st.error(tr("Invalid Delegate Matricule. Please check with your administration."))
                else:
                    st.info(tr("You can create your account now and select your level/group inside your workspace."))

            # Only show the rest of the form if authorized for restricted roles
            show_form = True
            if role == "Professor" and target_id is None: show_form = False
            if role == "Administration" and not is_admin_authorized: show_form = False
            if role == "Student" and is_delegate and target_id is None: show_form = False

            if show_form:
                with st.form("signup_form"):
                    new_username = st.text_input(tr("Choose Personal Username"))
                    new_password = st.text_input(tr("Choose Personal Password"), type="password")

                    submitted = st.form_submit_button(tr("Sign Up"))

                    if submitted:
                        if not new_username or not new_password:
                            st.error(tr("Username and password are required."))
                        else:
                            target_role = "admin" if role == "Administration" else "teacher" if role == "Professor" else "delegate" if (role == "Student" and is_delegate) else "student"

                            import sqlite3
                            try:
                                c.execute("INSERT INTO Users (username, password, role, linked_id) VALUES (?, ?, ?, ?)", 
                                          (new_username, new_password, target_role, target_id))
                                conn.commit()
                                st.success(tr("Account created successfully! Please switch to Login."))
                            except sqlite3.IntegrityError:
                                st.error(tr("Username already exists. Please choose a different one."))
            conn.close()

def logout():
    st.session_state.user = None
    st.rerun()

