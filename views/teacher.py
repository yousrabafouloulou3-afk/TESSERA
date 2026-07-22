import streamlit as st
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    get_db_connection, get_preference_deadline, clear_teacher_preferences, 
    submit_reschedule_request, get_professor_requests,
    submit_unavailability_request, get_professor_unavailability_requests
)
from views.shared import render_schedule_grid, availability_checker
from translations import tr
from engine.data_adapter import load_data_from_db
from engine.greedy import verifier_contraintes_hard, diagnose_contraintes_hard

def show():
    st.title(tr("👨‍🏫 Teacher Workspace"))
    teacher_id = st.session_state.user['linked_id']
    
    tab1, tab3, tab4, tab2, tab6, tab5 = st.tabs([
        tr("📅 My Schedule"), 
        tr("⭐ Top 3 Preferences"), 
        tr("🚫 Unavailability Requests"),
        tr("🔄 Reschedule Sessions"),
        tr("🤝 Session Swaps"),
        tr("🔍 Room Availability")
    ])
    
    with tab1:
        from database import get_preference_submission_stats
        stats = get_preference_submission_stats()
        if stats['total_modules'] > 0 and stats['pending_modules'] > 0:
            st.warning(tr('⏳ The official timetable is not yet available. Please wait until all professors have submitted their preferences.'))
        else:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT * FROM Planning WHERE ID_P=?", (teacher_id,))
            my_sessions_raw = c.fetchall()

            if my_sessions_raw:
                my_sessions = [dict(s) for s in my_sessions_raw]
                render_schedule_grid(my_sessions, title="My Assigned Schedule", show_entity=True)

                st.divider()
                st.markdown(f"### {tr('View Student Timetables')}")
                st.caption(tr("Check the timetable of the sections/groups you teach to find common available slots."))

                my_entities_ids = list(set([s['ID_E'] for s in my_sessions]))
                if my_entities_ids:
                    # Resolve these IDs to their parent sections if they are groups
                    placeholders = ','.join('?' for _ in my_entities_ids)
                    c.execute(f"SELECT ID_E, nameE, typeE, sectionID FROM Entities WHERE ID_E IN ({placeholders})", my_entities_ids)
                    raw_entities = c.fetchall()
                    
                    section_ids = set()
                    for ent in raw_entities:
                        if ent['typeE'] == 1: section_ids.add(ent['ID_E'])
                        elif ent['sectionID']: section_ids.add(ent['sectionID'])
                    
                    if section_ids:
                        placeholders_sec = ','.join('?' for _ in section_ids)
                        c.execute(f"SELECT ID_E, nameE FROM Entities WHERE ID_E IN ({placeholders_sec})", list(section_ids))
                        my_sections = {r['ID_E']: r['nameE'] for r in c.fetchall()}
                        selected_section_id = st.selectbox(tr("Select Student Section to View"), options=list(my_sections.keys()), format_func=lambda x: my_sections[x])
                        
                        if selected_section_id:
                            c.execute("SELECT ID_E FROM Entities WHERE sectionID=?", (selected_section_id,))
                            target_entity_ids = [selected_section_id] + [r['ID_E'] for r in c.fetchall()]

                            placeholders = ','.join('?' for _ in target_entity_ids)
                            c.execute(f"SELECT * FROM Planning WHERE ID_E IN ({placeholders})", target_entity_ids)
                            entity_sessions_raw = c.fetchall()
                            if entity_sessions_raw:
                                entity_sessions = [dict(s) for s in entity_sessions_raw]
                                render_schedule_grid(entity_sessions, title=f"{tr('Schedule for')} {my_sections[selected_section_id]}", show_entity=False)
                            else:
                                st.info(tr("No schedule found for this section."))

            else:
                st.info(tr("System is waiting for Admin phase completion."))
            conn.close()

    with tab2:
        st.markdown(f"### {tr('🔄 Manual Reschedule Engine')}")
        
        
        from database import get_preference_submission_stats
        stats = get_preference_submission_stats()
        if stats['total_modules'] > 0 and stats['pending_modules'] > 0:
            st.warning(tr('⏳ The official timetable is not yet available. Rescheduling is only available once the timetable is published.'))
        else:
            conn = get_db_connection()
            c = conn.cursor()
            
            # We need some helper data for this tab
            c.execute("SELECT * FROM Planning WHERE ID_P=?", (teacher_id,))
            my_sessions = [dict(s) for s in c.fetchall()]
            
            if not my_sessions:
                st.info(tr("No sessions have been assigned to you yet. Rescheduling is only available once the timetable is published."))
            else:
                c.execute("""
                    SELECT m.ID_M, m.nameM, m.typeM, e.nameE 
                    FROM Modules m 
                    LEFT JOIN Entities e ON m.ID_E = e.ID_E 
                    WHERE m.ID_P=?
                """, (teacher_id,))
                my_modules = {}
                rows = c.fetchall()
                counts = {}
                from views.shared import format_entity_name
                for r in rows:
                    m_type = "Cours" if r['typeM'] == 1 else "TD"
                    key = (r['nameM'], r['nameE'], r['typeM'])
                    counts[key] = counts.get(key, 0) + 1
                    total_of_this_type = sum(1 for row in rows if row['nameM'] == r['nameM'] and row['nameE'] == r['nameE'] and row['typeM'] == r['typeM'])
                    m_type_display = f"{m_type} {counts[key]}" if total_of_this_type > 1 else m_type
                    base_name = f"{r['nameM']}: ({m_type_display})"
                    formatted_nameE = format_entity_name(r['nameE']) if r['nameE'] else None
                    my_modules[r['ID_M']] = f"{base_name} - {formatted_nameE}" if formatted_nameE else base_name
    
                c.execute("SELECT ID_S, nameS FROM Salles")
                salles = [{'id': r['ID_S'], 'name': r['nameS']} for r in c.fetchall()]
                jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
    
                def format_session(s):
                    t = s['t']
                    day = jours[(t - 1) // 6] if 1 <= t <= 36 else "Unknown"
                    time_slot = horaires[(t - 1) % 6] if 1 <= t <= 36 else "Unknown"
                    room_name = next((r['name'] for r in salles if r['id'] == s['ID_S']), 'Unknown')
                    mod_name = my_modules.get(s['ID_M'], s['ID_M'])
                    return f"{mod_name} - Time: {tr(day)} {time_slot}, Room: {room_name}"
    
                session_options = [format_session(s) for s in my_sessions]
                selected_session_idx = st.selectbox(tr("Select target session to modify:"), range(len(session_options)), format_func=lambda x: session_options[x])
                selected_session = my_sessions[selected_session_idx]
    
                t_val = selected_session['t']
                default_day_idx = (t_val - 1) // 6 if 1 <= t_val <= 36 else 0
                default_time_idx = (t_val - 1) % 6 if 1 <= t_val <= 36 else 0
    
                col_a, col_b, col_c = st.columns(3)
                with col_a: new_day = st.selectbox(tr("Attempt Day Move"), jours, format_func=tr, index=default_day_idx)
                with col_b: new_time = st.selectbox(tr("Attempt Time Move"), horaires, index=default_time_idx)
                with col_c:
                    salle_name = st.selectbox(tr("Attempt Room Move"), [s['name'] for s in salles])
                    new_s_id = next((s['id'] for s in salles if s['name'] == salle_name))
    
                new_t = (jours.index(new_day) * 6) + horaires.index(new_time) + 1
    
                if st.button(tr("Apply Valid State Reschedule"), type="primary"):
                    data = load_data_from_db()
                    c.execute("SELECT * FROM Planning")
                    all_sessions = [dict(row) for row in c.fetchall()]
                    from engine.sa_optimizer import build_state_from_final, remove_session
                    planning_state = build_state_from_final(all_sessions, data)
                    remove_session(selected_session, planning_state, data)
                    valid = verifier_contraintes_hard(selected_session['ID_P'], selected_session['ID_E'], new_s_id, new_t, data, planning_state, selected_session['ID_M'])
                    if valid:
                        submit_reschedule_request(selected_session['id'], selected_session['ID_P'], new_t, new_s_id)
                        st.success(tr("Reschedule request successfully validated and forwarded to the Administration!"))
                        import time as time_mod
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(tr("🚫 Operation Blocked: Scheduling conflict detected."))
                        reasons = diagnose_contraintes_hard(selected_session['ID_P'], selected_session['ID_E'], new_s_id, new_t, data, planning_state, selected_session['ID_M'])
                        for r_key, extra in reasons:
                            if r_key == 'prof_unavail':
                                st.error(tr("• Professor has declared this time slot as Unavailable."))
                            elif r_key == 'prof_busy':
                                st.error(f"{tr('• Professor is busy teaching')} {extra} {tr('at this slot.')}")
                            elif r_key == 'room_busy':
                                st.error(f"{tr('• Room is occupied by')} {extra} {tr('at this slot.')}")
                            elif r_key == 'entity_busy':
                                st.error(tr("• Class/Section is busy with another session at this slot."))
                            elif r_key == 'parent_busy':
                                st.error(tr("• Group's parent Section is busy with another session at this slot."))
                            elif r_key == 'child_busy':
                                st.error(tr("• Section's child Group is busy with another session at this slot."))
                            elif r_key == 'room_incompatible':
                                type_str = tr("Cours") if extra == 1 else tr("TD")
                                st.error(f"{tr('• Selected room is not compatible with type')} {type_str}.")
    
                st.divider()
                st.markdown(f"### {tr('My Reschedule Requests Log')}")
                reqs = get_professor_requests(teacher_id)
                if reqs:
                    import pandas as pd
                    req_data = []
                    for r in reqs:
                        day = jours[(r['new_t'] - 1) // 6] if 1 <= r['new_t'] <= 36 else "Unknown"
                        time_slot = horaires[(r['new_t'] - 1) % 6] if 1 <= r['new_t'] <= 36 else "Unknown"
                        r_name = next((sal['name'] for sal in salles if sal['id'] == r['new_s_id']), "Unknown")
                        
                        raw_status = r['status']
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
                            
                        req_data.append({
                            tr("Request ID"): r['id'], tr("Session ID"): r['session_id'], 
                            tr("Requested Day"): tr(day), tr("Requested Time"): time_slot, 
                            tr("Requested Room"): r_name, tr("Status"): tr(friendly_status)
                        })
                    def color_status(val):
                        color = 'orange' if 'Pending' in val else 'green' if val == 'Approved' else 'red'
                        return f'color: {color}'
                    st.dataframe(pd.DataFrame(req_data).style.map(color_status, subset=[tr('Status')]), use_container_width=True)
                    
                    # --- CANCEL OPTION ---
                    pending_rescheds = [r for r in reqs if r['status'] in ('Pending_Delegate', 'Pending_Admin')]
                    if pending_rescheds:
                        st.markdown(f"##### {tr('🗑️ Cancel Pending Reschedule Request')}")
                        resched_options = {r['id']: f"Request #{r['id']} (Move Session {r['session_id']} to {tr(jours[(r['new_t']-1)//6])} {horaires[(r['new_t']-1)%6]})" for r in pending_rescheds}
                        selected_cancel_id = st.selectbox(tr("Select pending reschedule request to cancel:"), options=list(resched_options.keys()), format_func=lambda x: resched_options[x], key="cancel_resched_sb")
                        if st.button(tr("Cancel Reschedule Request"), key="btn_cancel_resched", type="secondary", use_container_width=True):
                            conn_cancel = get_db_connection()
                            c_cancel = conn_cancel.cursor()
                            c_cancel.execute("UPDATE RescheduleRequests SET status = 'Cancelled' WHERE id = ?", (selected_cancel_id,))
                            conn_cancel.commit()
                            conn_cancel.close()
                            st.success(f"Request #{selected_cancel_id} has been cancelled successfully!")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.info(tr("No active reschedule requests found."))
            conn.close()

    with tab3:
        st.markdown(f"### {tr('Declare Operating Preferences')}")
        
        # Query teacher's modules/sessions once at the top of the tab
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT m.ID_M, m.nameM, m.typeM, e.nameE 
            FROM Modules m 
            LEFT JOIN Entities e ON m.ID_E = e.ID_E 
            WHERE m.ID_P=?
        """, (teacher_id,))
        rows = c.fetchall()
        
        my_mod_list = []
        counts = {} 
        for r in rows:
            m_type = "Cours" if r['typeM'] == 1 else "TD"
            key = (r['nameM'], r['nameE'], r['typeM'])
            counts[key] = counts.get(key, 0) + 1
            
            total_of_this_type = sum(1 for row in rows if row['nameM'] == r['nameM'] and row['nameE'] == r['nameE'] and row['typeM'] == r['typeM'])
            
            if total_of_this_type > 1:
                m_type_display = f"{m_type} {counts[key]}"
            else:
                m_type_display = m_type
            
            base_name = f"{r['nameM']}: ({m_type_display})"
            from views.shared import format_entity_name
            full_name = f"{base_name} - {format_entity_name(r['nameE'])}" if r['nameE'] else base_name
            my_mod_list.append({'id': r['ID_M'], 'name': full_name})
        conn.close()
        
        deadline = get_preference_deadline()
        import time as time_mod
        current_time = time_mod.time()
        
        allow_prefs = False
        allow_unavailability = True # Allowed even before opening
        
        if not deadline:
            st.warning(tr("⚠️ The preference submission period has not opened yet. However, you can still declare your Unavailability Requests below."))
        elif current_time > deadline:
            st.error(tr("🚨 The deadline has passed. You can no longer submit preferences or unavailability requests."))
            allow_unavailability = False
        else:
            rem = deadline - current_time
            days, rem_sec = divmod(rem, 86400)
            hours, rem_sec = divmod(rem_sec, 3600)
            mins, _ = divmod(rem_sec, 60)
            st.info(f"⏳ **Time remaining to submit:** {int(days)}d {int(hours)}h {int(mins)}m")
            allow_prefs = True
            allow_unavailability = True

        if allow_prefs:
            if not my_mod_list:
                st.warning(tr("No linked modules detected attached to your User ID profile."))
            else:
                from database import load_draft, save_draft, clear_draft
                username = st.session_state.user['username']
                draft = load_draft(username, 'prefs_form')
                current_draft = {}
                
                mod_opts = [m['name'] for m in my_mod_list]
                mod_name_key = "prefs_mod_name"
                mod_idx = mod_opts.index(draft.get(mod_name_key, mod_opts[0])) if draft.get(mod_name_key, mod_opts[0]) in mod_opts else 0
                mod_name = st.selectbox(tr("Select Target Class Identifier"), mod_opts, index=mod_idx, key=mod_name_key)
                current_draft[mod_name_key] = mod_name
                
                mod_id = next(m['id'] for m in my_mod_list if m['name'] == mod_name)
                
                days_opts = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                times_opts = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                
                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.markdown(f"**{tr('Slot 1 (Excellent)')}**")
                    d1_key = "prefs_d1"
                    d1 = st.selectbox(tr("Day 1"), days_opts, format_func=tr, index=draft.get(d1_key, 0), key=d1_key)
                    current_draft[d1_key] = days_opts.index(d1)
                    tm1_key = "prefs_tm1"
                    tm1 = st.selectbox(tr("Time 1"), times_opts, index=draft.get(tm1_key, 0), key=tm1_key)
                    current_draft[tm1_key] = times_opts.index(tm1)
                    t1 = (days_opts.index(d1) * 6) + times_opts.index(tm1) + 1
                    
                with c2:
                    st.markdown(f"**{tr('Slot 2 (High)')}**")
                    d2_key = "prefs_d2"
                    d2 = st.selectbox(tr("Day 2"), days_opts, format_func=tr, index=draft.get(d2_key, 0), key=d2_key)
                    current_draft[d2_key] = days_opts.index(d2)
                    tm2_key = "prefs_tm2"
                    tm2 = st.selectbox(tr("Time 2"), times_opts, index=draft.get(tm2_key, 0), key=tm2_key)
                    current_draft[tm2_key] = times_opts.index(tm2)
                    t2 = (days_opts.index(d2) * 6) + times_opts.index(tm2) + 1
                    
                with c3:
                    st.markdown(f"**{tr('Slot 3 (Normal)')}**")
                    d3_key = "prefs_d3"
                    d3 = st.selectbox(tr("Day 3"), days_opts, format_func=tr, index=draft.get(d3_key, 0), key=d3_key)
                    current_draft[d3_key] = days_opts.index(d3)
                    tm3_key = "prefs_tm3"
                    tm3 = st.selectbox(tr("Time 3"), times_opts, index=draft.get(tm3_key, 0), key=tm3_key)
                    current_draft[tm3_key] = times_opts.index(tm3)
                    t3 = (days_opts.index(d3) * 6) + times_opts.index(tm3) + 1
                
                if st.button(tr("Upload Preferences Logic"), type="primary"):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("DELETE FROM Preferences WHERE ID_P=? AND ID_M=?", (teacher_id, mod_id))
                    c.execute("INSERT OR REPLACE INTO Preferences (ID_P, ID_M, t, score) VALUES (?, ?, ?, ?)", (teacher_id, mod_id, t1, 0))
                    c.execute("INSERT OR REPLACE INTO Preferences (ID_P, ID_M, t, score) VALUES (?, ?, ?, ?)", (teacher_id, mod_id, t2, 10))
                    c.execute("INSERT OR REPLACE INTO Preferences (ID_P, ID_M, t, score) VALUES (?, ?, ?, ?)", (teacher_id, mod_id, t3, 20))
                    conn.commit()
                    conn.close()
                    clear_draft(username, 'prefs_form')
                    st.success(tr("✅ Recorded cleanly. Pending Admin optimization re-run phase."))
                    time.sleep(1)
                    st.rerun()
                else:
                    save_draft(username, 'prefs_form', current_draft)

        # --- My Preferences Table ---
        if my_mod_list:
            st.write("") # Spacer
            st.markdown(f"### {tr('My Declared Preferences Table')}")
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT ID_M, t, score
                FROM Preferences
                WHERE ID_P=?
            """, (teacher_id,))
            pref_rows = c.fetchall()
            conn.close()
            
            prefs_by_mod = {}
            for row in pref_rows:
                m_id = row['ID_M']
                sc = row['score']
                t_val = row['t']
                if m_id not in prefs_by_mod:
                    prefs_by_mod[m_id] = {}
                prefs_by_mod[m_id][sc] = t_val
                
            from collections import defaultdict
            import pandas as pd
            
            jours_pref = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires_pref = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            
            def get_slot_str(t):
                if not t or t < 1 or t > 36: return "Not Set"
                return f"{tr(jours_pref[(t - 1) // 6])} {horaires_pref[(t - 1) % 6]}"
            
            table_data = []
            for mod in my_mod_list:
                m_id = mod['id']
                slots = prefs_by_mod.get(m_id, {})
                table_data.append({
                    tr("Module / Session"): mod['name'],
                    tr("Slot 1 (Excellent)"): get_slot_str(slots.get(0)),
                    tr("Slot 2 (High)"): get_slot_str(slots.get(10)),
                    tr("Slot 3 (Normal)"): get_slot_str(slots.get(20))
                })
            
            st.dataframe(pd.DataFrame(table_data), use_container_width=True)
        else:
            st.info(tr("You haven't declared any top 3 preferences yet."))

        # --- Manage Preferences ---
        if allow_prefs:
            st.divider()
            st.markdown(f"### {tr('Manage Preference Data')}")
            conf_pref = st.checkbox(tr("Confirm Preference Deletion"))
            if st.button(tr("Clear My Preferences"), disabled=not conf_pref, type="primary"):
                from database import clear_draft
                clear_teacher_preferences(teacher_id)
                username = st.session_state.user['username']
                clear_draft(username, 'prefs_form')
                st.success("Your preferences have been cleared!")
                time.sleep(1)
                st.rerun()

    with tab4:
        st.markdown(f"### {tr('🚫 Request Unavailability')}")
        st.write(tr("If you have a constraint (e.g., medical, family), submit a request with a reason for Admin approval."))
        
        from database import get_max_unavailability_slots, get_professor_unavailability_requests
        
        if allow_unavailability:
            with st.form("unavailability_form"):
                max_u = get_max_unavailability_slots()
                existing_reqs = get_professor_unavailability_requests(teacher_id)
                # Count Pending or Approved requests (not Cancelled/Rejected)
                current_count = len([r for r in existing_reqs if r['status'] in ('Pending', 'Approved')])
                remaining = max(0, max_u - current_count)
                
                all_slots = []
                jours_map = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                horaires_map = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                for j in jours_map:
                    for h in horaires_map:
                        all_slots.append(f"{j} {h}")
                
                u_slots = st.multiselect(
                    tr("Select Unavailable Slots"), 
                    all_slots, 
                    placeholder=tr("Choose up to {remaining} slots...").format(remaining=remaining),
                    max_selections=remaining if remaining > 0 else None
                )
                u_reason = st.text_area(tr("Reason for Unavailability (Mandatory)"))
                
                if st.form_submit_button(tr("Submit Requests")):
                    if remaining <= 0:
                        st.error(tr("You have reached the maximum allowed limit of {max_u} unavailability slots.").format(max_u=max_u))
                    elif not u_slots:
                        st.error(tr("Please select at least one slot."))
                    elif len(u_slots) > remaining:
                        st.error(tr("You can only select up to {remaining} additional slots.").format(remaining=remaining))
                    elif u_reason.strip() == "":
                        st.error(tr("Please provide a reason."))
                    else:
                        jours_map = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                        horaires_map = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                        for slot_str in u_slots:
                            day_part, time_part = slot_str.split(' ', 1)
                            u_t = (jours_map.index(day_part) * 6) + horaires_map.index(time_part) + 1
                            submit_unavailability_request(teacher_id, u_t, u_reason)
                        
                        st.success(f"✅ {len(u_slots)} requests submitted successfully and are pending Admin approval.")
                        import time as time_mod
                        time.sleep(1)
                        st.rerun()
        elif deadline and current_time > deadline:
            st.warning(tr("⏱️ The deadline for submitting unavailability requests has passed. You can no longer submit new requests."))
        
        st.markdown(f"#### {tr('My Unavailability Requests Log')}")
        u_reqs = get_professor_unavailability_requests(teacher_id)
        if u_reqs:
            import pandas as pd
            u_data = []
            jours_map = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires_map = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            for r in u_reqs:
                u_data.append({
                    tr("Request ID"): r['id'], tr("Day"): tr(jours_map[(r['t'] - 1) // 6]), tr("Time"): horaires_map[(r['t'] - 1) % 6], tr("Reason"): r['reason'], tr("Status"): tr(r['status'])
                })
            
            def color_u_status(val):
                color = 'orange' if val == 'Pending' else 'green' if val == 'Approved' else 'red'
                return f'color: {color}'
            
            st.dataframe(pd.DataFrame(u_data).style.map(color_u_status, subset=[tr('Status')]), use_container_width=True)
            
            # --- CANCEL OPTION ---
            pending_unavails = [r for r in u_reqs if r['status'] == 'Pending']
            if pending_unavails:
                st.markdown(f"##### {tr('🗑️ Cancel Pending Unavailability Request')}")
                unavail_options = {r['id']: f"Request #{r['id']} (Slot: {tr(jours_map[(r['t']-1)//6])} {horaires_map[(r['t']-1)%6]})" for r in pending_unavails}
                selected_unavail_id = st.selectbox(tr("Select pending unavailability request to cancel:"), options=list(unavail_options.keys()), format_func=lambda x: unavail_options[x], key="cancel_unavail_sb")
                if st.button(tr("Cancel Unavailability Request"), key="btn_cancel_unavail", type="secondary", use_container_width=True):
                    conn_cancel = get_db_connection()
                    c_cancel = conn_cancel.cursor()
                    c_cancel.execute("UPDATE UnavailabilityRequests SET status = 'Cancelled' WHERE id = ?", (selected_unavail_id,))
                    conn_cancel.commit()
                    conn_cancel.close()
                    st.success(f"Request #{selected_unavail_id} has been cancelled successfully!")
                    import time as time_mod
                    time.sleep(1)
                    st.rerun()
        else:
            st.info(tr("You haven't submitted any unavailability requests yet."))

    with tab5:
        availability_checker()

    with tab6:
        st.markdown(f"### {tr('🤝 Session Swap Marketplace')}")
        st.write(tr("Propose a time-slot swap with another professor. Both the peer and the Administrator must approve."))
        
        from database import get_preference_submission_stats
        stats = get_preference_submission_stats()
        if stats['total_modules'] > 0 and stats['pending_modules'] > 0:
            st.warning(tr('⏳ The official timetable is not yet available. Session swapping is only available once the timetable is published.'))
        else:
            conn = get_db_connection()
            c = conn.cursor()
            
            c.execute("""
                SELECT p.id as session_id, p.ID_P, m.nameM, m.typeM, e.nameE, s.nameS
                FROM Planning p
                JOIN Modules m ON p.ID_M = m.ID_M
                JOIN Entities e ON p.ID_E = e.ID_E
                LEFT JOIN Salles s ON p.ID_S = s.ID_S
                ORDER BY p.ID_P, p.ID_M
            """)
            all_pl_sessions = c.fetchall()
            mod_display_types = {}
            room_names = {}
            p_totals = {}
            for s in all_pl_sessions:
                k = (s['ID_P'], s['nameM'], s['nameE'], s['typeM'])
                p_totals[k] = p_totals.get(k, 0) + 1
            
            p_current = {}
            for s in all_pl_sessions:
                k = (s['ID_P'], s['nameM'], s['nameE'], s['typeM'])
                p_current[k] = p_current.get(k, 0) + 1
                m_type = "Cours" if s['typeM'] == 1 else "TD"
                if p_totals[k] > 1:
                    m_type = f"{m_type}{p_current[k]}"
                mod_display_types[s['session_id']] = m_type
                room_names[s['session_id']] = s['nameS'] or 'Unknown Room'
            
            # Shared format slot function
            jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            def format_slot(t):
                if not t or t < 1 or t > 36: return f"Slot {t}"
                return f"{tr(jours[(t - 1) // 6])} {horaires[(t - 1) % 6]}"
    
            # 1. Incoming Requests
            from views.shared import format_entity_name
            swap_tab_propose, swap_tab_incoming, swap_tab_history = st.tabs([
                tr("➕ Propose New Swap"),
                tr("📥 Incoming Requests"),
                tr("📜 My Swap History")
            ])

            with swap_tab_propose:
                st.markdown(f"### {tr('➕ Propose New Swap')}")
            
                # My sessions
                c.execute("""
                    SELECT p.id, m.nameM, m.typeM, e.nameE, p.t, p.ID_S, p.ID_E, p.ID_M
                    FROM Planning p
                    JOIN Modules m ON p.ID_M = m.ID_M
                    JOIN Entities e ON p.ID_E = e.ID_E
                    WHERE p.ID_P = ?
                """, (teacher_id,))
                my_sessions = c.fetchall()
            
                if not my_sessions:
                    st.warning("You have no sessions assigned in the current timetable.")
                else:
                    my_session_opts = {s['id']: f"{s['nameM']} ({mod_display_types.get(s['id'], 'TD')}) ({format_entity_name(s['nameE'])}) - {format_slot(s['t'])} - Room {room_names.get(s['id'], '')}" for s in my_sessions}
                    my_sess_id = st.selectbox(tr("1. Select your session to swap"), options=list(my_session_opts.keys()), format_func=lambda x: my_session_opts[x])
                
                    sub_tab_ai, sub_tab_manual = st.tabs([tr("🤖 AI Smart Match"), tr("🔍 Manual Specialty Search")])
                    with sub_tab_ai:
                        # --- AI SWAP ASSISTANT ---
                        if 'show_ai_assistant' not in st.session_state:
                            st.session_state.show_ai_assistant = False
                
                        if st.button(tr("🤖 Use AI Swap Assistant"), use_container_width=True):
                            st.session_state.show_ai_assistant = not st.session_state.show_ai_assistant
                
                        if st.session_state.show_ai_assistant:
                            with st.spinner("AI is analyzing the timetable for perfect matches..."):
                                data = load_data_from_db()
                                c.execute("SELECT * FROM Planning")
                                all_plannings = [dict(row) for row in c.fetchall()]
                        
                                from engine.sa_optimizer import build_state_from_final
                                state = build_state_from_final(all_plannings, data)
                        
                                # My current session data
                                my_sess = next(s for s in my_sessions if s['id'] == my_sess_id)
                                my_p_id = teacher_id
                                my_e_id = my_sess['ID_E']
                                my_s_id = my_sess['ID_S']
                                my_m_id = my_sess['ID_M']
                                my_t = my_sess['t']
                        
                                # Get my preferences
                                c.execute("SELECT t FROM Preferences WHERE ID_P=? AND score=0", (teacher_id,))
                                my_top_slots = [p['t'] for p in c.fetchall()]
                        
                                if not my_top_slots:
                                    st.info("💡 Tip: Declare your 'Top 3 Preferences' first so the AI knows what you like!")
                        
                                # Find all other sessions
                                c.execute("""
                                    SELECT p.id, p.ID_P, p.ID_E, p.ID_S, p.t, p.ID_M, m.nameM, e.nameE, prof.nameP, m.typeM
                                    FROM Planning p
                                    JOIN Modules m ON p.ID_M = m.ID_M
                                    JOIN Entities e ON p.ID_E = e.ID_E
                                    JOIN Profs prof ON p.ID_P = prof.ID_P
                                    WHERE p.ID_P != ?
                                """, (teacher_id,))
                                others = c.fetchall()
                        
                                results = []
                                for ot in others:
                                    # Remove both temporarily to check swap
                                    from engine.sa_optimizer import remove_session
                                    remove_session({'ID_P': my_p_id, 'ID_E': my_e_id, 'ID_S': my_s_id, 'ID_M': my_m_id, 't': my_t}, state, data)
                                    remove_session({'ID_P': ot['ID_P'], 'ID_E': ot['ID_E'], 'ID_S': ot['ID_S'], 'ID_M': ot['ID_M'], 't': ot['t']}, state, data)
                            
                                    # Check Me -> ot['t']
                                    me_valid = verifier_contraintes_hard(my_p_id, my_e_id, ot['ID_S'], ot['t'], data, state, my_m_id)
                                    # Check Him -> my_t
                                    him_valid = verifier_contraintes_hard(ot['ID_P'], ot['ID_E'], my_s_id, my_t, data, state, ot['ID_M'])
                            
                                    if me_valid and him_valid:
                                        score = 0
                                        if ot['t'] in my_top_slots:
                                            score = 10 # High priority
                                        results.append({
                                            'session': ot,
                                            'score': score
                                        })
                            
                                    # Reset state for next iteration
                                    state = build_state_from_final(all_plannings, data)
    
                                if results:
                                    results = sorted(results, key=lambda x: x['score'], reverse=True)[:5]
                                    st.markdown(f"#### {tr('🎯 AI Recommended Swaps')}")
                                    st.write(tr("The AI found these valid swaps that don't cause any conflicts:"))
                                    for res in results:
                                        s = res['session']
                                        with st.expander(f"{tr('🔥 Excellent Match') if res['score']>0 else tr('✅ Valid Swap')} {tr('with')} {s['nameP']}"):
                                            st.write(f"**{tr('Colleague:')}** {s['nameP']}")
                                            st.write(f"**{tr('Their Session:')}** {s['nameM']} ({mod_display_types.get(s['id'], 'TD')}) ({format_entity_name(s['nameE'])}) - {tr('Room')} {room_names.get(s['id'], '')}")
                                            st.write(f"**{tr('Target Time:')}** {format_slot(s['t'])}")
                                            if st.button(f"{tr('Propose Swap to')} {s['nameP']}", key=f"ai_swap_{s['id']}"):
                                                # Perform insertion
                                                c.execute("""
                                                    INSERT INTO SwapRequests (ID_P_Requester, ID_Session_Requester, ID_P_Target, ID_Session_Target, status)
                                                    VALUES (?, ?, ?, ?, 'Pending_Target')
                                                """, (teacher_id, my_sess_id, s['ID_P'], s['id']))
                                                conn.commit()
                                                st.success(f"Proposal sent to {s['nameP']}!")
                                                st.session_state.show_ai_assistant = False
                                                import time as time_mod
                                                time.sleep(1)
                                                st.rerun()
                                else:
                                    st.error("No valid swaps found. The current timetable is very tight!")
    
                
                    with sub_tab_manual:
                        # --- SPECIALTY-BASED FILTERING ---
                        # 1. Get my specialty
                        c.execute("SELECT specialite FROM Profs WHERE ID_P = ?", (teacher_id,))
                        my_spec_row = c.fetchone()
                        my_speciality = my_spec_row['specialite'] if my_spec_row else None
    
                        # 2. Fetch all other sessions from the SAME specialty
                        c.execute("""
                            SELECT p.id, p.ID_P, p.ID_E, p.ID_S, p.t, p.ID_M, m.nameM, e.nameE, prof.nameP, m.typeM
                            FROM Planning p
                            JOIN Modules m ON p.ID_M = m.ID_M
                            JOIN Entities e ON p.ID_E = e.ID_E
                            JOIN Profs prof ON p.ID_P = prof.ID_P
                            WHERE p.ID_P != ? AND prof.specialite = ?
                        """, (teacher_id, my_speciality))
                        all_other_sessions = [dict(s) for s in c.fetchall()]
    
                        st.write(f"**2. Find target session to swap with** (Specialty: {my_speciality or 'Unknown'})")
                        col_filter1, col_filter2 = st.columns(2)
                
                        with col_filter1:
                            filter_day = st.selectbox("Filter by Day", ["All"] + jours)
                        with col_filter2:
                            prof_names = sorted(list(set(s['nameP'] for s in all_other_sessions)))
                            filter_prof = st.selectbox("Filter by Professor", ["All"] + prof_names)
                
                        # Filter the list
                        filtered_sessions = all_other_sessions
                        if filter_day != "All":
                            d_idx = jours.index(filter_day)
                            filtered_sessions = [s for s in filtered_sessions if (s['t']-1)//6 == d_idx]
                        if filter_prof != "All":
                            filtered_sessions = [s for s in filtered_sessions if s['nameP'] == filter_prof]
                
                        if not filtered_sessions:
                            st.info(f"No sessions from colleagues in your specialty ({my_speciality}) match your filters.")
                            st.stop()
                    
                        other_session_opts = {s['id']: f"{s['nameP']} - {s['nameM']} ({mod_display_types.get(s['id'], 'TD')}) ({format_entity_name(s['nameE'])}) - {format_slot(s['t'])} - Room {room_names.get(s['id'], '')}" for s in filtered_sessions}
                        target_sess_id = st.selectbox("Select specific session", options=list(other_session_opts.keys()), format_func=lambda x: other_session_opts[x])
                
                        # Check Capacity Conflict for suggested room
                        target_session_data = next(s for s in all_other_sessions if s['id'] == target_sess_id)
                        my_session_data = next(s for s in my_sessions if s['id'] == my_sess_id)
                
                        c.execute("SELECT typeS FROM Salles WHERE ID_S = ?", (my_session_data['ID_S'],))
                        row1 = c.fetchone()
                        my_room_type = row1['typeS'] if row1 else 1
                
                        c.execute("SELECT typeS FROM Salles WHERE ID_S = ?", (target_session_data['ID_S'],))
                        row2 = c.fetchone()
                        target_room_type = row2['typeS'] if row2 else 1
                
                        my_mod_type = my_session_data['typeM']
                        target_mod_type = target_session_data['typeM']
                
                        suggested_room_id = None
                        needs_amphi = False
                
                        if target_mod_type == 1 and my_room_type == 0:
                            st.warning(f"⚠️ Capacity Conflict: Your TD room is too small for their Lecture (Cours). Please suggest an available Amphi.")
                            needs_amphi = True
                        elif my_mod_type == 1 and target_room_type == 0:
                            st.warning(f"⚠️ Capacity Conflict: The TD room of {target_session_data['nameP']} is too small for your Lecture (Cours). Please suggest an available Amphi.")
                            needs_amphi = True
                    
                        if needs_amphi:
                            # Suggest an Amphi
                            c.execute("SELECT ID_S, nameS FROM Salles WHERE typeS = 1")
                            available_amphis = {r['ID_S']: r['nameS'] for r in c.fetchall()}
                            if available_amphis:
                                suggested_room_id = st.selectbox(tr("Suggest an alternative available Amphi"), options=list(available_amphis.keys()), format_func=lambda x: available_amphis[x])
                            else:
                                st.error("No suitable Amphis found in the system.")
                
                        if st.button(tr("Send Swap Request"), type="primary"):
                            c.execute("""
                                INSERT INTO SwapRequests (ID_P_Requester, ID_Session_Requester, ID_P_Target, ID_Session_Target, suggested_room_id, status)
                                VALUES (?, ?, ?, ?, ?, 'Pending_Target')
                            """, (teacher_id, my_sess_id, target_session_data['ID_P'], target_sess_id, suggested_room_id))
                            conn.commit()
                            st.success(tr("Request sent successfully!"))
                            import time as time_mod
                            time.sleep(1)
                            st.rerun()
            with swap_tab_incoming:
                st.markdown(f"### {tr('📥 Incoming Swap Requests')}")
                c.execute("""
                    SELECT sr.*, 
                           m1.nameM as my_m_name, m1.typeM as my_m_type, e1.nameE as my_e_name, s1.nameS as my_s_name, p1.t as my_t,
                           m2.nameM as their_m_name, m2.typeM as their_m_type, e2.nameE as their_e_name, s2.nameS as their_s_name, p2.t as their_t,
                           prof.nameP as requester_name
                    FROM SwapRequests sr
                    JOIN Planning p1 ON sr.ID_Session_Target = p1.id
                    JOIN Planning p2 ON sr.ID_Session_Requester = p2.id
                    JOIN Modules m1 ON p1.ID_M = m1.ID_M
                    LEFT JOIN Entities e1 ON p1.ID_E = e1.ID_E
                    LEFT JOIN Salles s1 ON p1.ID_S = s1.ID_S
                    JOIN Modules m2 ON p2.ID_M = m2.ID_M
                    LEFT JOIN Entities e2 ON p2.ID_E = e2.ID_E
                    LEFT JOIN Salles s2 ON p2.ID_S = s2.ID_S
                    JOIN Profs prof ON sr.ID_P_Requester = prof.ID_P
                    WHERE sr.ID_P_Target = ? AND sr.status = 'Pending_Target'
                """, (teacher_id,))
                incoming = c.fetchall()
            
                if not incoming:
                    st.info(tr("No pending requests from other professors."))
                else:
                    for req in incoming:
                        with st.expander(f"Request from {req['requester_name']}"):
                            my_type_str = "Cours" if req['my_m_type'] == 1 else "TD"
                            their_type_str = "Cours" if req['their_m_type'] == 1 else "TD"
                            my_desc = f"{req['my_m_name']} ({my_type_str}) ({format_entity_name(req['my_e_name'])}) - {format_slot(req['my_t'])} - Room {req['my_s_name']}"
                            their_desc = f"{req['their_m_name']} ({their_type_str}) ({format_entity_name(req['their_e_name'])}) - {format_slot(req['their_t'])} - Room {req['their_s_name']}"
                        
                            st.write(f"They want to swap their **{their_desc}** session for your **{my_desc}**.")
                        
                            col1, col2 = st.columns(2)
                            if col1.button(tr("Accept Swap Request"), key=f"acc_{req['ID_SR']}", type="primary"):
                                # Check if the swap affects students (meaning they belong to different groups/sections)
                                c.execute("SELECT ID_E FROM Planning WHERE id = ?", (req['ID_Session_Requester'],))
                                row_req = c.fetchone()
                                e1_id = row_req['ID_E'] if row_req else None
                            
                                c.execute("SELECT ID_E FROM Planning WHERE id = ?", (req['ID_Session_Target'],))
                                row_tar = c.fetchone()
                                e2_id = row_tar['ID_E'] if row_tar else None
                            
                                if e1_id == e2_id:
                                    # No student impact -> Direct to Admin
                                    c.execute("UPDATE SwapRequests SET status = 'Pending_Admin' WHERE ID_SR = ?", (req['ID_SR'],))
                                    st.success(tr("Accepted! Sent directly to Admin (no student impact)."))
                                else:
                                    # Has student impact -> Resolve section IDs
                                    c.execute("SELECT typeE, sectionID FROM Entities WHERE ID_E = ?", (e1_id,))
                                    ent1 = c.fetchone()
                                    sec1 = e1_id if ent1 and ent1['typeE'] == 1 else ent1['sectionID'] if ent1 else None
                                
                                    c.execute("SELECT typeE, sectionID FROM Entities WHERE ID_E = ?", (e2_id,))
                                    ent2 = c.fetchone()
                                    sec2 = e2_id if ent2 and ent2['typeE'] == 1 else ent2['sectionID'] if ent2 else None
                                
                                    # Setup delegate approval flags
                                    if sec1 == sec2:
                                        # Same section -> only 1 delegate needs to approve
                                        c.execute("""
                                            UPDATE SwapRequests 
                                            SET status = 'Pending_Delegate', approved_by_delegate1 = 0, approved_by_delegate2 = 1 
                                            WHERE ID_SR = ?
                                        """, (req['ID_SR'],))
                                    else:
                                        # Different sections -> both delegates must approve
                                        c.execute("""
                                            UPDATE SwapRequests 
                                            SET status = 'Pending_Delegate', approved_by_delegate1 = 0, approved_by_delegate2 = 0 
                                            WHERE ID_SR = ?
                                        """, (req['ID_SR'],))
                                    st.success(tr("Accepted! Sent to Section Delegate(s) for pre-approval."))
                                
                                conn.commit()
                                import time as time_mod
                                time.sleep(1)
                                st.rerun()
                            if col2.button(tr("Reject Swap Request"), key=f"rej_{req['ID_SR']}"):
                                c.execute("UPDATE SwapRequests SET status = 'Rejected' WHERE ID_SR = ?", (req['ID_SR'],))
                                conn.commit()
                                st.info(tr("Request rejected."))
                                time.sleep(1)
                                st.rerun()
    
                # 2. My Reschedule Requests (History)
            with swap_tab_history:
                st.markdown(f"### {tr('My Swap Requests Log')}")
                st.info(tr("History of all swaps you've initiated or participated in."))
            
                c.execute("""
                    SELECT sr.*, 
                           prof1.nameP as requester_name, prof2.nameP as target_name,
                           m1.nameM as mod1_name, m1.typeM as mod1_type, m2.nameM as mod2_name, m2.typeM as mod2_type,
                           e1.nameE as e1_name, e2.nameE as e2_name, p1.ID_E as e1_id, p2.ID_E as e2_id
                    FROM SwapRequests sr
                    JOIN Profs prof1 ON sr.ID_P_Requester = prof1.ID_P
                    JOIN Profs prof2 ON sr.ID_P_Target = prof2.ID_P
                    JOIN Planning p1 ON sr.ID_Session_Requester = p1.id
                    JOIN Planning p2 ON sr.ID_Session_Target = p2.id
                    JOIN Modules m1 ON p1.ID_M = m1.ID_M
                    JOIN Modules m2 ON p2.ID_M = m2.ID_M
                    JOIN Entities e1 ON p1.ID_E = e1.ID_E
                    JOIN Entities e2 ON p2.ID_E = e2.ID_E
                    WHERE sr.ID_P_Requester = ? OR sr.ID_P_Target = ?
                    ORDER BY sr.ID_SR DESC
                """, (teacher_id, teacher_id))
                history = c.fetchall()
            
                if history:
                    # Prepare data for a clean table
                    history_data = []
                    for h in history:
                        role = "Requester" if h['ID_P_Requester'] == teacher_id else "Target"
                        other_party = h['target_name'] if role == "Requester" else h['requester_name']
                    
                        mod1_type_str = "Cours" if h['mod1_type'] == 1 else "TD"
                        mod2_type_str = "Cours" if h['mod2_type'] == 1 else "TD"
                        mod1_full = f"{h['mod1_name']} ({tr(mod1_type_str)})"
                        mod2_full = f"{h['mod2_name']} ({tr(mod2_type_str)})"

                        status_emoji = "⏳" if "Pending" in h['status'] else "✅" if h['status'] == "Approved" else "❌"
                    
                        raw_status = h['status']
                        if raw_status == 'Pending_Target':
                            friendly_status = 'Pending (Partner)'
                        elif raw_status in ('Pending_Delegate', 'Rejected_Delegate'):
                            if h['e1_id'] != h['e2_id']:
                                from views.shared import format_entity_name
                                del1_s = tr("Pending") if h['approved_by_delegate1'] == 0 else tr("Approved") if h['approved_by_delegate1'] == 1 else tr("Rejected")
                                del2_s = tr("Pending") if h['approved_by_delegate2'] == 0 else tr("Approved") if h['approved_by_delegate2'] == 1 else tr("Rejected")
                                friendly_status = f"{del1_s} ({format_entity_name(h['e1_name'])}), {del2_s} ({format_entity_name(h['e2_name'])})"
                            else:
                                friendly_status = 'Pending (Delegate)' if raw_status == 'Pending_Delegate' else 'Rejected by Delegate'
                        elif raw_status == 'Pending_Admin':
                            friendly_status = 'Pending (Admin)'
                        elif raw_status == 'Rejected':
                            friendly_status = 'Rejected by Admin'
                        elif raw_status == 'Auto_Cancelled':
                            friendly_status = 'Auto Cancelled'
                        else:
                            friendly_status = raw_status
                    
                        history_data.append({
                            tr("Swap ID"): h['ID_SR'],
                            tr("Role"): tr(role),
                            tr("Partner"): other_party,
                            tr("My Module"): mod1_full if role == "Requester" else mod2_full,
                            tr("Their Module"): mod2_full if role == "Requester" else mod1_full,
                            tr("Status"): f"{status_emoji} {tr(friendly_status)}"
                        })
                
                    st.table(history_data)
                
                    # --- CANCEL OPTION ---
                    pending_swaps = [h for h in history if h['ID_P_Requester'] == teacher_id and h['status'] in ('Pending_Target', 'Pending_Delegate', 'Pending_Admin')]
                    if pending_swaps:
                        st.markdown(f"##### {tr('🗑️ Cancel Propose Swap')}")
                        swap_options = {h['ID_SR']: f"Swap Request #{h['ID_SR']} (Partner: {h['target_name']}, Status: {h['status']})" for h in pending_swaps}
                        selected_swap_id = st.selectbox(tr("Select swap request to cancel:"), options=list(swap_options.keys()), format_func=lambda x: swap_options[x], key="cancel_swap_sb")
                        if st.button(tr("Cancel Swap Request"), key="btn_cancel_swap", type="secondary", use_container_width=True):
                            c.execute("UPDATE SwapRequests SET status = 'Cancelled' WHERE ID_SR = ?", (selected_swap_id,))
                            conn.commit()
                            st.success(f"Swap Request #{selected_swap_id} has been cancelled successfully!")
                            import time as time_mod
                            time.sleep(1)
                            st.rerun()
                else:
                    st.info(tr("No swap history found."))
                
                conn.close()
