import streamlit as st
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection
from views.shared import render_schedule_grid, availability_checker
from translations import tr

def show():
    st.title(tr("🎓 Student Interactive Portal"))
    user_data = st.session_state.user
    student_id = user_data['linked_id']
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Handle accounts without a linked identity
    if student_id is None:
        st.info(f"### {tr('👋 Welcome! Please complete your profile.')}")
        st.markdown(tr("Before you can see your timetable, you need to select your academic level and group."))
        
        # 1. Level
        levels = ["L1", "L2", "L3", "M1", "M2"]
        level = st.selectbox(tr("1. Select your Level"), levels, index=None, placeholder=tr("Choose Level..."))
        
        if level:
            # 2. Specialty
            c.execute("SELECT DISTINCT specialite FROM Entities WHERE typeE = 1 AND specialite LIKE ?", (f"{level}%",))
            level_specs = [row['specialite'] for row in c.fetchall() if row['specialite']]
            
            if not level_specs:
                st.warning(f"⚠️ {tr('The administration has not inserted data for')} **{level}** {tr('specialties yet.')}")
            else:
                spec_name = st.selectbox(tr("2. Select your Specialty"), level_specs, index=None, placeholder=tr("Choose Specialty..."), format_func=lambda x: x.replace(f"{level} ", "", 1).strip() or x)
                
                if spec_name:
                    # 3. Section
                    c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 1 AND specialite = ?", (spec_name,))
                    sections = {row['nameE']: row['ID_E'] for row in c.fetchall()}
                    
                    if not sections:
                        st.warning(f"⚠️ {tr('The administration has not inserted data for')} **{spec_name}** {tr('sections yet.')}")
                    else:
                        section_name = st.selectbox(tr("3. Select your Section"), list(sections.keys()), index=None, placeholder=tr("Choose Section..."))
                        
                        if section_name:
                            # 4. Group
                            section_id = sections[section_name]
                            c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 0 AND sectionID = ?", (section_id,))
                            groups = {row['nameE']: row['ID_E'] for row in c.fetchall()}
                            
                            target_id = None
                            if not groups:
                                st.warning(f"⚠️ {tr('The administration has not inserted data for')} **{section_name}** {tr('groups yet.')}")
                            else:
                                sel_group = st.selectbox(tr("4. Select your Group"), list(groups.keys()), index=None, placeholder=tr("Choose Group..."))
                                if sel_group:
                                    target_id = groups[sel_group]
                            
                            if target_id and st.button(tr("Link My Account & Show Timetable"), type="primary"):
                                c.execute("UPDATE Users SET linked_id = ? WHERE username = ?", (target_id, user_data['username']))
                                conn.commit()
                                st.session_state.user['linked_id'] = target_id
                                st.success(tr("Account linked successfully!"))
                                time.sleep(1)
                                st.rerun()
        conn.close()
        return

    c.execute("SELECT typeE, sectionID, nameE FROM Entities WHERE ID_E=?", (student_id,))
    ent = c.fetchone()
    
    if not ent:
        st.error(tr("Error: Auth Entity Mapping Exception. Your linked entity may have been deleted."))
        if st.button(tr("Reset My Link")):
            c.execute("UPDATE Users SET linked_id = NULL WHERE username = ?", (user_data['username'],))
            conn.commit()
            st.session_state.user['linked_id'] = None
            time.sleep(1)
            st.rerun()
        conn.close()
        return
        
    is_delegate = (user_data['role'] == 'delegate')
    delegate_section_id = None
    if is_delegate:
        delegate_section_id = ent['sectionID'] if ent['typeE'] == 0 else student_id
        tabs_list = [tr("Timetabling Visualization Canvas"), tr("Global Resource Checker"), tr("📥 Approvals Panel")]
    else:
        tabs_list = [tr("Timetabling Visualization Canvas"), tr("Global Resource Checker")]
        
    tabs = st.tabs(tabs_list)
    
    with tabs[0]:
        from database import get_preference_submission_stats
        stats = get_preference_submission_stats()
        if stats['total_modules'] > 0 and stats['pending_modules'] > 0:
            st.warning(tr("⏳ The official timetable is not yet available. Please wait until finalized."))
        else:
            # Determine Section ID and info
            section_id = ent['sectionID'] if ent['typeE'] == 0 else student_id
            c.execute("SELECT nameE, specialite FROM Entities WHERE ID_E=?", (section_id,))
            row_sec = c.fetchone()
            section_full_name = row_sec['nameE'] if row_sec else "Unknown Section"
            section_spec = row_sec['specialite'] if row_sec else "Unknown Specialty"
            
            # Extract just "Section A" from "L3 OR - Section A"
            section_clean = section_full_name.split(' - ')[-1].strip() if ' - ' in section_full_name else section_full_name
            
            # Formatting titles for PDF and Display
            # Target: Schedules of: L3 OR- Section A
            section_title = f"Schedules of: {section_spec}- {section_clean}"
            personal_title = section_title
            
            if ent['typeE'] == 0:
                # Extract just "G1" from "L3 OR - Section A - G1"
                group_clean = ent['nameE'].split(' - ')[-1].strip() if ' - ' in ent['nameE'] else ent['nameE']
                # Target: Schedules of: L3 OR- Section A- G1
                personal_title = f"Schedules of: {section_spec}- {section_clean}- {group_clean}"

            # 1. Personal Schedule (My Section's Cours + My Group's TDs)
            target_personal = [section_id]
            if ent['typeE'] == 0: target_personal.append(student_id)
            
            p_holders = ','.join('?' for _ in target_personal)
            c.execute(f"SELECT * FROM Planning WHERE ID_E IN ({p_holders})", tuple(target_personal))
            sessions_personal = [dict(s) for s in c.fetchall()]

            # 2. Section Overview (All Cours + All TDs of all groups)
            c.execute("SELECT ID_E FROM Entities WHERE sectionID=?", (section_id,))
            all_group_ids = [r['ID_E'] for r in c.fetchall()]
            target_section = [section_id] + all_group_ids
            
            s_holders = ','.join('?' for _ in target_section)
            c.execute(f"SELECT * FROM Planning WHERE ID_E IN ({s_holders})", tuple(target_section))
            sessions_section = [dict(s) for s in c.fetchall()]

            # --- RENDER ---
            if sessions_personal:
                render_schedule_grid(sessions_personal, title="👤 Personal Schedule", pdf_title=personal_title, hide_group_name=(ent['typeE'] == 0))
            else:
                st.info(tr("No personal sessions scheduled yet."))
            
            # Only show Section Overview if there are multiple groups
            if len(all_group_ids) > 1:
                st.divider()
                if sessions_section:
                    st.caption(tr("Includes all lectures and all tutorials for all groups in this section."))
                    render_schedule_grid(sessions_section, title="🏢 Full Section Overview", pdf_title=section_title)
                else:
                    st.info(tr("No section-wide sessions scheduled yet."))

    conn.close()
    with tabs[1]:
        availability_checker()

    if is_delegate:
        with tabs[2]:
            st.markdown(f"### {tr('📥 Approvals Panel')}")
            st.caption(tr("As a Section Delegate, you must review and approve/reject reschedule or swap requests from professors before they are forwarded to the Admin."))
            
            sub_tabs = st.tabs([tr("📅 Reschedule Requests"), tr("🔄 Swap Requests")])
            
            with sub_tabs[0]:
                st.markdown(f"#### {tr('📅 Pending Reschedule Requests')}")
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT r.id as req_id, r.new_t, r.new_s_id, p.nameP, m.nameM, m.typeM, e.nameE, pl.t as old_t, pl.ID_S as old_s_id
                    FROM RescheduleRequests r
                    JOIN Planning pl ON r.session_id = pl.id
                    JOIN Profs p ON r.ID_P = p.ID_P
                    JOIN Modules m ON pl.ID_M = m.ID_M
                    JOIN Entities e ON pl.ID_E = e.ID_E
                    WHERE r.status = 'Pending_Delegate'
                      AND (pl.ID_E = ? OR pl.ID_E IN (SELECT ID_E FROM Entities WHERE sectionID = ?))
                """, (delegate_section_id, delegate_section_id))
                delegate_reqs = c.fetchall()
                
                c.execute("SELECT ID_S, nameS FROM Salles")
                salles_dict = {row['ID_S']: row['nameS'] for row in c.fetchall()}
                conn.close()
                
                if not delegate_reqs:
                    st.success(tr("🎉 No pending reschedule requests for your section to review!"))
                else:
                    st.info(f"{tr('You have pending reschedule requests to review.')} ({len(delegate_reqs)})")
                    jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                    horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                    
                    for req in delegate_reqs:
                        with st.container(border=True):
                            m_type_str = "Cours" if req['typeM'] == 1 else "TD"
                            old_day = jours[(req['old_t'] - 1) // 6] if 1 <= req['old_t'] <= 36 else "Unknown"
                            old_time = horaires[(req['old_t'] - 1) % 6] if 1 <= req['old_t'] <= 36 else "Unknown"
                            old_room = salles_dict.get(req['old_s_id'], "Unknown")
                            
                            new_day = jours[(req['new_t'] - 1) // 6] if 1 <= req['new_t'] <= 36 else "Unknown"
                            new_time = horaires[(req['new_t'] - 1) % 6] if 1 <= req['new_t'] <= 36 else "Unknown"
                            new_room = salles_dict.get(req['new_s_id'], "Unknown")
                            
                            st.markdown(f"**{tr('Professor:')}** {req['nameP']}")
                            from views.shared import format_entity_name
                            st.markdown(f"**{tr('Class:')}** {req['nameM']} ({tr(m_type_str)}) for {format_entity_name(req['nameE'])}")
                            st.markdown(f"**{tr('Current Slot:')}** {tr(old_day)} at {old_time} in {old_room}")
                            st.markdown(f"**{tr('Proposed Slot:')}** {tr(new_day)} at {new_time} in {new_room}")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button(tr("Approve Request"), key=f"del_app_{req['req_id']}", type="primary", use_container_width=True):
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    c.execute("UPDATE RescheduleRequests SET status = 'Pending_Admin' WHERE id = ?", (req['req_id'],))
                                    conn.commit()
                                    conn.close()
                                    st.success(tr("Request approved and forwarded to the Administration!"))
                                    time.sleep(1)
                                    st.rerun()
                            with col2:
                                if st.button(tr("Reject Request"), key=f"del_rej_{req['req_id']}", type="secondary", use_container_width=True):
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    c.execute("UPDATE RescheduleRequests SET status = 'Rejected_Delegate' WHERE id = ?", (req['req_id'],))
                                    conn.commit()
                                    conn.close()
                                    st.warning(tr("Request rejected!"))
                                    time.sleep(1)
                                    st.rerun()

                # --- Reschedule Requests Log ---
                st.divider()
                st.markdown(tr("### 📋 Section Reschedule History Log"))
                st.caption(tr("All reschedule requests and their current validation/approval status."))
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT r.id as req_id, r.new_t, r.new_s_id, r.status, p.nameP, m.nameM, m.typeM, e.nameE, pl.t as old_t, pl.ID_S as old_s_id
                    FROM RescheduleRequests r
                    JOIN Planning pl ON r.session_id = pl.id
                    JOIN Profs p ON r.ID_P = p.ID_P
                    JOIN Modules m ON pl.ID_M = m.ID_M
                    JOIN Entities e ON pl.ID_E = e.ID_E
                    WHERE (pl.ID_E = ? OR pl.ID_E IN (SELECT ID_E FROM Entities WHERE sectionID = ?))
                    ORDER BY r.id DESC
                """, (delegate_section_id, delegate_section_id))
                history_rows = c.fetchall()
                
                c.execute("SELECT ID_S, nameS FROM Salles")
                salles_dict = {row['ID_S']: row['nameS'] for row in c.fetchall()}
                conn.close()
                
                if not history_rows:
                    st.info(tr("No reschedule requests have been logged for this section yet."))
                else:
                    import pandas as pd
                    jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                    horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                    
                    log_data = []
                    for row in history_rows:
                        m_type_str = "Cours" if row['typeM'] == 1 else "TD"
                        old_day = jours[(row['old_t'] - 1) // 6] if 1 <= row['old_t'] <= 36 else "Unknown"
                        old_time = horaires[(row['old_t'] - 1) % 6] if 1 <= row['old_t'] <= 36 else "Unknown"
                        old_room = salles_dict.get(row['old_s_id'], "Unknown")
                        
                        new_day = jours[(row['new_t'] - 1) // 6] if 1 <= row['new_t'] <= 36 else "Unknown"
                        new_time = horaires[(row['new_t'] - 1) % 6] if 1 <= row['new_t'] <= 36 else "Unknown"
                        new_room = salles_dict.get(row['new_s_id'], "Unknown")
                        
                        raw_status = row['status']
                        if raw_status == 'Pending_Delegate':
                            friendly_status = 'Pending (Delegate)'
                        elif raw_status == 'Pending_Admin':
                            friendly_status = 'Pending (Admin)'
                        elif raw_status == 'Rejected_Delegate':
                            friendly_status = 'Rejected by Delegate'
                        elif raw_status == 'Rejected':
                            friendly_status = 'Rejected by Admin'
                        elif raw_status == 'Auto_Cancelled':
                            friendly_status = 'Auto Cancelled'
                        else:
                            friendly_status = raw_status
                            
                        from views.shared import format_entity_name
                        log_data.append({
                            tr("Request ID"): row['req_id'],
                            tr("Professor"): row['nameP'],
                            tr("Class"): f"{row['nameM']} ({tr(m_type_str)}) - {format_entity_name(row['nameE'])}",
                            tr("Original Slot"): f"{tr(old_day)} {old_time} ({old_room})",
                            tr("Proposed Slot"): f"{tr(new_day)} {new_time} ({new_room})",
                            tr("Status"): tr(friendly_status)
                        })
                        
                    def color_log_status(val):
                        if 'Pending' in val or 'attente' in val or 'معلق' in val:
                            return 'color: orange'
                        elif val == 'Approved' or val == 'Approuvé' or val == 'مقبول':
                            return 'color: green'
                        elif 'Rejected' in val or 'Rejeté' in val or 'مرفوض' in val:
                            return 'color: red'
                        return ''
                        
                    st.dataframe(
                        pd.DataFrame(log_data).style.map(color_log_status, subset=[tr('Status')]),
                        use_container_width=True
                    )

            with sub_tabs[1]:
                st.markdown(f"#### {tr('🔄 Pending Swap Requests')}")
                conn = get_db_connection()
                c = conn.cursor()
                
                def get_parent_section(entity_id, cursor):
                    cursor.execute("SELECT typeE, sectionID FROM Entities WHERE ID_E = ?", (entity_id,))
                    row = cursor.fetchone()
                    if not row:
                        return None
                    return entity_id if row['typeE'] == 1 else row['sectionID']
                
                # Fetch all pending swap requests
                c.execute("""
                    SELECT sr.*, 
                           p1.t as t1, p1.ID_S as s1_id, p1.ID_E as e1_id, p1.ID_M as m1_id,
                           p2.t as t2, p2.ID_S as s2_id, p2.ID_E as e2_id, p2.ID_M as m2_id,
                           prof1.nameP as requester_name, prof2.nameP as target_name
                    FROM SwapRequests sr
                    JOIN Planning p1 ON sr.ID_Session_Requester = p1.id
                    JOIN Planning p2 ON sr.ID_Session_Target = p2.id
                    JOIN Profs prof1 ON sr.ID_P_Requester = prof1.ID_P
                    JOIN Profs prof2 ON sr.ID_P_Target = prof2.ID_P
                    WHERE sr.status = 'Pending_Delegate'
                """)
                all_pending = c.fetchall()
                
                # Filter for swaps where this delegate has action
                delegate_swaps = []
                for s in all_pending:
                    sec1 = get_parent_section(s['e1_id'], c)
                    sec2 = get_parent_section(s['e2_id'], c)
                    
                    is_del1 = (delegate_section_id == sec1 and s['approved_by_delegate1'] == 0)
                    is_del2 = (delegate_section_id == sec2 and s['approved_by_delegate2'] == 0)
                    
                    if is_del1 or is_del2:
                        delegate_swaps.append((s, sec1, sec2, is_del1, is_del2))
                
                c.execute("SELECT ID_S, nameS FROM Salles")
                salles_dict = {row['ID_S']: row['nameS'] for row in c.fetchall()}
                conn.close()
                
                if not delegate_swaps:
                    st.success(tr("🎉 No pending swap requests for your section to review!"))
                else:
                    st.info(f"{tr('You have pending swap requests to review.')} ({len(delegate_swaps)})")
                    jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                    horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                    
                    for row_tuple in delegate_swaps:
                        req, sec1, sec2, is_del1, is_del2 = row_tuple
                        req_id = req['ID_SR']
                        
                        conn = get_db_connection()
                        c = conn.cursor()
                        # Fetch Modules
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (req['m1_id'],))
                        m1 = c.fetchone() or {'nameM': 'Unknown Module', 'typeM': 1}
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (req['m2_id'],))
                        m2 = c.fetchone() or {'nameM': 'Unknown Module', 'typeM': 1}
                        
                        # Fetch Entities
                        from views.shared import format_entity_name
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (req['e1_id'],))
                        e1 = c.fetchone()
                        e1_name = format_entity_name(e1['nameE']) if e1 else "Unknown"
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (req['e2_id'],))
                        e2 = c.fetchone()
                        e2_name = format_entity_name(e2['nameE']) if e2 else "Unknown"
                        conn.close()
                        
                        with st.container(border=True):
                            st.markdown(f"**{tr('Swap Proposal #')}{req_id}**")
                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown(f"##### 👤 **{req['requester_name']}**'s {tr('Session')}")
                                st.write(f"- **{tr('Module:')}** {m1['nameM']} ({tr('Cours') if m1['typeM'] == 1 else tr('TD')})")
                                st.write(f"- **{tr('Student Entity:')}** {e1_name}")
                                st.write(f"- **{tr('Slot:')}** {tr(jours[(req['t1'] - 1) // 6])} {horaires[(req['t1'] - 1) % 6]}")
                                st.write(f"- **{tr('Room:')}** {salles_dict.get(req['s1_id'], 'Unknown')}")
                            with col2:
                                st.markdown(f"##### 👤 **{req['target_name']}**'s {tr('Session')}")
                                st.write(f"- **{tr('Module:')}** {m2['nameM']} ({tr('Cours') if m2['typeM'] == 1 else tr('TD')})")
                                st.write(f"- **{tr('Student Entity:')}** {e2_name}")
                                st.write(f"- **{tr('Slot:')}** {tr(jours[(req['t2'] - 1) // 6])} {horaires[(req['t2'] - 1) % 6]}")
                                st.write(f"- **{tr('Room:')}** {salles_dict.get(req['s2_id'], 'Unknown')}")
                                
                            if req['suggested_room_id']:
                                st.warning(f"💡 {tr('Alternative Room Suggested for')} {m2['nameM']}: **{salles_dict.get(req['suggested_room_id'], 'Unknown')}**")
                                
                            # Show status details
                            if sec1 == sec2:
                                st.info(tr("This swap request is entirely within your section."))
                            else:
                                app1 = f"✅ {tr('Approved')}" if req['approved_by_delegate1'] == 1 else f"⏳ {tr('Pending')}"
                                app2 = f"✅ {tr('Approved')}" if req['approved_by_delegate2'] == 1 else f"⏳ {tr('Pending')}"
                                
                                conn_n = get_db_connection()
                                c_n = conn_n.cursor()
                                c_n.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (sec1,))
                                name_sec1 = c_n.fetchone()
                                name_sec1 = name_sec1['nameE'] if name_sec1 else "Section 1"
                                c_n.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (sec2,))
                                name_sec2 = c_n.fetchone()
                                name_sec2 = name_sec2['nameE'] if name_sec2 else "Section 2"
                                conn_n.close()
                                
                                st.markdown(f"""
                                **{tr('Approval Status per Section:')}**
                                - {name_sec1}: {app1}
                                - {name_sec2}: {app2}
                                """)
                                
                            col_b1, col_b2 = st.columns(2)
                            with col_b1:
                                if st.button(tr("Approve Swap Request"), key=f"del_swp_app_{req_id}", type="primary", use_container_width=True):
                                    conn_app = get_db_connection()
                                    c_app = conn_app.cursor()
                                    
                                    # Perform approval updates
                                    if is_del1:
                                        c_app.execute("UPDATE SwapRequests SET approved_by_delegate1 = 1 WHERE ID_SR = ?", (req_id,))
                                    if is_del2:
                                        c_app.execute("UPDATE SwapRequests SET approved_by_delegate2 = 1 WHERE ID_SR = ?", (req_id,))
                                        
                                    # Fetch updated values to see if both are approved
                                    c_app.execute("SELECT approved_by_delegate1, approved_by_delegate2 FROM SwapRequests WHERE ID_SR = ?", (req_id,))
                                    chk = c_app.fetchone()
                                    if chk and chk['approved_by_delegate1'] == 1 and chk['approved_by_delegate2'] == 1:
                                        c_app.execute("UPDATE SwapRequests SET status = 'Pending_Admin' WHERE ID_SR = ?", (req_id,))
                                        
                                    conn_app.commit()
                                    conn_app.close()
                                    st.success(tr("Swap Request approved!"))
                                    time.sleep(1)
                                    st.rerun()
                                    
                            with col_b2:
                                if st.button(tr("Reject Swap Request"), key=f"del_swp_rej_{req_id}", type="secondary", use_container_width=True):
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    if is_del1:
                                        c.execute("UPDATE SwapRequests SET approved_by_delegate1 = -1 WHERE ID_SR = ?", (req_id,))
                                    if is_del2:
                                        c.execute("UPDATE SwapRequests SET approved_by_delegate2 = -1 WHERE ID_SR = ?", (req_id,))
                                    c.execute("UPDATE SwapRequests SET status = 'Rejected_Delegate' WHERE ID_SR = ?", (req_id,))
                                    conn.commit()
                                    conn.close()
                                    st.warning(tr("Swap Request rejected!"))
                                    time.sleep(1)
                                    st.rerun()

                # --- Swap Requests Log ---
                st.divider()
                st.markdown(tr("### 📋 Section Swap History Log"))
                st.caption(tr("All session swap requests and their current validation/approval status."))
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT sr.*, 
                           p1.t as t1, p1.ID_S as s1_id, p1.ID_E as e1_id, p1.ID_M as m1_id,
                           p2.t as t2, p2.ID_S as s2_id, p2.ID_E as e2_id, p2.ID_M as m2_id,
                           prof1.nameP as requester_name, prof2.nameP as target_name
                    FROM SwapRequests sr
                    JOIN Planning p1 ON sr.ID_Session_Requester = p1.id
                    JOIN Planning p2 ON sr.ID_Session_Target = p2.id
                    JOIN Profs prof1 ON sr.ID_P_Requester = prof1.ID_P
                    JOIN Profs prof2 ON sr.ID_P_Target = prof2.ID_P
                    WHERE 
                      (p1.ID_E = ? 
                       OR p1.ID_E IN (SELECT ID_E FROM Entities WHERE sectionID = ?)
                       OR p2.ID_E = ?
                       OR p2.ID_E IN (SELECT ID_E FROM Entities WHERE sectionID = ?))
                      AND sr.status != 'Pending_Target'
                      AND p1.ID_E != p2.ID_E
                    ORDER BY sr.ID_SR DESC
                """, (delegate_section_id, delegate_section_id, delegate_section_id, delegate_section_id))
                history_swaps = c.fetchall()
                
                c.execute("SELECT ID_S, nameS FROM Salles")
                salles_dict = {row['ID_S']: row['nameS'] for row in c.fetchall()}
                conn.close()
                
                if not history_swaps:
                    st.info(tr("No swap requests have been logged for this section yet."))
                else:
                    import pandas as pd
                    jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                    horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                    
                    log_data = []
                    for row in history_swaps:
                        # Fetch Module Names safely
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (row['m1_id'],))
                        m1_row = c.fetchone()
                        if m1_row:
                            m1_type = "Cours" if m1_row['typeM'] == 1 else "TD"
                            m1_name = f"{m1_row['nameM']} ({tr(m1_type)})"
                        else:
                            m1_name = "Unknown"
                        
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (row['m2_id'],))
                        m2_row = c.fetchone()
                        if m2_row:
                            m2_type = "Cours" if m2_row['typeM'] == 1 else "TD"
                            m2_name = f"{m2_row['nameM']} ({tr(m2_type)})"
                        else:
                            m2_name = "Unknown"
                        
                        # Fetch Entity Names safely
                        from views.shared import format_entity_name
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (row['e1_id'],))
                        row_e1 = c.fetchone()
                        e1 = format_entity_name(row_e1['nameE']) if row_e1 else "Unknown"
                        
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (row['e2_id'],))
                        row_e2 = c.fetchone()
                        e2 = format_entity_name(row_e2['nameE']) if row_e2 else "Unknown"
                        conn.close()
                        
                        # Format slot
                        slot1 = f"{tr(jours[(row['t1'] - 1) // 6])} {horaires[(row['t1'] - 1) % 6]} ({salles_dict.get(row['s1_id'], 'Unknown')})"
                        slot2 = f"{tr(jours[(row['t2'] - 1) // 6])} {horaires[(row['t2'] - 1) % 6]} ({salles_dict.get(row['s2_id'], 'Unknown')})"
                        
                        raw_status = row['status']
                        if raw_status == 'Pending_Target':
                            friendly_status = 'Pending (Partner)'
                        elif raw_status == 'Pending_Delegate':
                            friendly_status = 'Pending (Delegate)'
                        elif raw_status == 'Pending_Admin':
                            friendly_status = 'Pending (Admin)'
                        elif raw_status == 'Rejected_Delegate':
                            friendly_status = 'Rejected by Delegate'
                        elif raw_status == 'Rejected':
                            friendly_status = 'Rejected by Admin'
                        elif raw_status == 'Auto_Cancelled':
                            friendly_status = 'Auto Cancelled'
                        else:
                            friendly_status = raw_status
                            
                        log_data.append({
                            tr("Swap ID"): row['ID_SR'],
                            tr("Requester Session"): f"{row['requester_name']}: {m1_name} ({e1}) at {slot1}",
                            tr("Target Session"): f"{row['target_name']}: {m2_name} ({e2}) at {slot2}",
                            tr("Status"): tr(friendly_status)
                        })
                        
                    def color_log_status(val):
                        if 'Pending' in val or 'attente' in val or 'معلق' in val:
                            return 'color: orange'
                        elif val == 'Approved' or val == 'Approuvé' or val == 'مقبول':
                            return 'color: green'
                        elif 'Rejected' in val or 'Rejeté' in val or 'مرفوض' in val or val == 'Cancelled':
                            return 'color: red'
                        return ''
                        
                    st.dataframe(
                        pd.DataFrame(log_data).style.map(color_log_status, subset=[tr('Status')]),
                        use_container_width=True
                    )
