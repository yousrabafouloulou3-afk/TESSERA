import streamlit as st
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection
from translations import tr

def show():
    st.title(tr("⚙️ Account Settings"))
    st.write(tr("Manage your personal login credentials."))
    
    user_id = None
    username = st.session_state.user['username']
    
    # Profile Picture Section
    st.markdown(f"### {tr('Profile Picture')}")
    PROFILE_PICS_DIR = "profile_pics"
    os.makedirs(PROFILE_PICS_DIR, exist_ok=True)
    pic_path = os.path.join(PROFILE_PICS_DIR, f"{username}.png")
    
    col_pic, col_up = st.columns([1, 3])
    with col_pic:
        if os.path.exists(pic_path):
            st.image(pic_path, width=120)
            if st.button(tr("🗑️ Delete"), key="del_pic_btn", use_container_width=True):
                try:
                    os.remove(pic_path)
                    st.success(tr("Profile picture deleted!"))
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error deleting image: {e}")
        else:
            default_path = os.path.join(PROFILE_PICS_DIR, "default_avatar.svg")
            if os.path.exists(default_path):
                import base64
                with open(default_path, "rb") as f:
                    pic_b64 = base64.b64encode(f.read()).decode("utf-8")
                st.markdown(
                    f"""
                    <img src="data:image/svg+xml;base64,{pic_b64}" width="120" height="120" style="object-fit: cover; background-color: #f0f0f0;">
                    """,
                    unsafe_allow_html=True
                )
            else:
                st.info(tr("No profile picture yet."))
            
    with col_up:
        uploaded_file = st.file_uploader(tr("Upload or change profile picture"), type=['png', 'jpg', 'jpeg'])
        if uploaded_file is not None:
            from streamlit_cropper import st_cropper
            from PIL import Image
            
            img = Image.open(uploaded_file)
            st.write(tr("Drag and resize the box to crop your picture. It will be saved as a circle!"))
            cropped_img = st_cropper(img, aspect_ratio=(1, 1), box_color='#D62F3A', return_type='image')
            
            if st.button(tr("Save Cropped Picture"), type="primary"):
                try:
                    cropped_img.thumbnail((300, 300))
                    cropped_img.save(pic_path, "PNG")
                    st.success(tr("Profile picture updated!"))
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving image: {e}")
    st.divider()
    username = st.session_state.user['username']
    
    # Get user ID from database
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM Users WHERE username=?", (username,))
    row = c.fetchone()
    if row:
        user_id = row['id']
    conn.close()

    if not user_id:
        st.error(tr("Error retrieving user profile."))
        return

    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"### {tr('Update Username')}")
        with st.form("change_username"):
            new_username = st.text_input(tr("New Username"), value=username)
            if st.form_submit_button(tr("Update Username"), type="primary"):
                if not new_username:
                    st.error(tr("Username cannot be empty."))
                else:
                    try:
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("UPDATE Users SET username=? WHERE id=?", (new_username, user_id))
                        conn.commit()
                        conn.close()
                        st.session_state.user['username'] = new_username
                        st.success(tr("Username updated successfully!"))
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    with col2:
        st.markdown(f"### {tr('Update Password')}")
        with st.form("change_password"):
            new_password = st.text_input(tr("New Password"), type="password")
            confirm_password = st.text_input(tr("Confirm New Password"), type="password")
            if st.form_submit_button(tr("Update Password"), type="primary"):
                if not new_password:
                    st.error(tr("Password cannot be empty."))
                elif new_password != confirm_password:
                    st.error(tr("Passwords do not match."))
                else:
                    try:
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("UPDATE Users SET password=? WHERE id=?", (new_password, user_id))
                        conn.commit()
                        conn.close()
                        st.success(tr("Password updated successfully!"))
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
