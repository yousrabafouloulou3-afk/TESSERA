import streamlit as st
import time
import pandas as pd
import plotly.graph_objects as go
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import (
    save_planning_to_db, get_db_connection, clear_table_students, 
    clear_table_professors, clear_table_rooms, clear_table_modules,
    set_preference_deadline, get_preference_deadline, get_preference_submission_stats, auto_assign_missing_preferences,
    get_fallback_count, undo_fallback_preferences,
    save_draft, load_draft, clear_draft,
    get_pending_requests, approve_reschedule_request, reject_reschedule_request,
    get_pending_unavailability_requests, approve_unavailability_request, reject_unavailability_request,
    clear_all_requests, clear_all_preferences
)
from engine.data_adapter import load_data_from_db
from engine.greedy import executer_greedy_priorite
from engine.sa_optimizer import optimize_with_sa
from translations import tr

def sync_student_entities(level, specs_data):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        # Fetch existing specialties for this level in original insertion order
        c.execute("SELECT ID_E, specialite FROM Entities WHERE typeE=1 AND specialite LIKE ? ORDER BY ID_E ASC", (f"{level} %",))
        seen = set()
        existing_specs = []
        for row in c.fetchall():
            spec = row['specialite']
            if spec not in seen:
                seen.add(spec)
                existing_specs.append(spec)
        
        # 1. Update existing and insert new
        for i, spec_data in enumerate(specs_data):
            name = spec_data.get('name', '').strip()
            if not name:
                continue
            new_spec_name = f"{level} {name}"
            
            if i < len(existing_specs):
                old_spec_name = existing_specs[i]
                if old_spec_name != new_spec_name:
                    c.execute("UPDATE Entities SET specialite = ? WHERE specialite = ?", (new_spec_name, old_spec_name))
                    c.execute("UPDATE Entities SET nameE = replace(nameE, ?, ?) WHERE specialite = ?", (old_spec_name, new_spec_name, new_spec_name))
                    c.execute("UPDATE Profs SET specialite = ? WHERE specialite = ?", (new_spec_name, old_spec_name))
            
            target_spec_name = new_spec_name
            c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE=1 AND specialite=? ORDER BY ID_E ASC", (target_spec_name,))
            existing_sections = c.fetchall()
            
            for section_idx, num_groups in enumerate(spec_data['sections']):
                section_label = chr(65 + section_idx)
                section_name = f"{target_spec_name} - Section {section_label}"
                
                if section_idx < len(existing_sections):
                    section_id = existing_sections[section_idx]['ID_E']
                    c.execute("UPDATE Entities SET nameE=? WHERE ID_E=?", (section_name, section_id))
                else:
                    c.execute("INSERT INTO Entities (typeE, sectionID, nameE, specialite) VALUES (?, ?, ?, ?)", (1, 0, section_name, target_spec_name))
                    section_id = c.lastrowid
                    c.execute("INSERT OR IGNORE INTO Users (username, password, role, linked_id) VALUES (?, ?, 'student', ?)", (f"student_{section_id}", "student123", section_id))
                
                c.execute("SELECT ID_E FROM Entities WHERE typeE=0 AND sectionID=? ORDER BY ID_E ASC", (section_id,))
                existing_groups = c.fetchall()
                
                for g in range(num_groups):
                    group_label = f"G{g+1}"
                    group_name = f"{section_name} - {group_label}"
                    if g < len(existing_groups):
                        group_id = existing_groups[g]['ID_E']
                        c.execute("UPDATE Entities SET nameE=? WHERE ID_E=?", (group_name, group_id))
                    else:
                        c.execute("INSERT INTO Entities (typeE, sectionID, nameE, specialite) VALUES (?, ?, ?, ?)", (0, section_id, group_name, target_spec_name))
                        group_id = c.lastrowid
                        c.execute("INSERT OR IGNORE INTO Users (username, password, role, linked_id) VALUES (?, ?, 'student', ?)", (f"student_{group_id}", "student123", group_id))
                
                # Delete excess groups
                for g in range(num_groups, len(existing_groups)):
                    group_id = existing_groups[g]['ID_E']
                    c.execute("DELETE FROM Entities WHERE ID_E=?", (group_id,))
                    c.execute("DELETE FROM Users WHERE role='student' AND linked_id=?", (group_id,))
                    c.execute("DELETE FROM Modules WHERE ID_E=?", (group_id,))
            
            # Delete excess sections
            for section_idx in range(len(spec_data['sections']), len(existing_sections)):
                section_id = existing_sections[section_idx]['ID_E']
                c.execute("SELECT ID_E FROM Entities WHERE typeE=0 AND sectionID=?", (section_id,))
                groups_to_delete = c.fetchall()
                for gd in groups_to_delete:
                    c.execute("DELETE FROM Entities WHERE ID_E=?", (gd['ID_E'],))
                    c.execute("DELETE FROM Users WHERE role='student' AND linked_id=?", (gd['ID_E'],))
                    c.execute("DELETE FROM Modules WHERE ID_E=?", (gd['ID_E'],))
                c.execute("DELETE FROM Entities WHERE ID_E=?", (section_id,))
                c.execute("DELETE FROM Users WHERE role='student' AND linked_id=?", (section_id,))
                c.execute("DELETE FROM Modules WHERE ID_E=?", (section_id,))
                
        # 2. Delete trailing specialties
        for i in range(len(specs_data), len(existing_specs)):
            old_spec_name = existing_specs[i]
            c.execute("SELECT ID_P FROM Profs WHERE specialite=?", (old_spec_name,))
            profs_to_delete = c.fetchall()
            for p in profs_to_delete:
                c.execute("DELETE FROM Users WHERE role='teacher' AND linked_id=?", (p['ID_P'],))
            c.execute("DELETE FROM Profs WHERE specialite=?", (old_spec_name,))
            
            c.execute("SELECT ID_E FROM Entities WHERE specialite=?", (old_spec_name,))
            entities_to_delete = c.fetchall()
            for ent in entities_to_delete:
                ent_id = ent['ID_E']
                c.execute("DELETE FROM Users WHERE role='student' AND linked_id=?", (ent_id,))
                c.execute("DELETE FROM Modules WHERE ID_E=?", (ent_id,))
            c.execute("DELETE FROM Entities WHERE specialite=?", (old_spec_name,))
            
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def save_professors(profs_data):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        departments = [
            "Operational Research",
            "Probability & Statistics",
            "Algebra and Cryptography",
            "Mathematics"
        ]
        
        # Strip and filter keep lists
        keep_names_by_spec = {}
        for p in profs_data:
            name_stripped = p['name'].strip()
            if name_stripped:
                keep_names_by_spec.setdefault(p['specialite'], []).append(name_stripped)
                
        # 1. Handle Deletions for each specialty
        for spec in departments:
            keeps = keep_names_by_spec.get(spec, [])
            c.execute("SELECT ID_P, nameP FROM Profs WHERE specialite = ?", (spec,))
            db_profs = c.fetchall()
            for row in db_profs:
                db_name = row['nameP']
                db_id = row['ID_P']
                if db_name not in keeps:
                    # Delete this professor
                    c.execute("DELETE FROM Profs WHERE ID_P = ?", (db_id,))
                    c.execute("DELETE FROM Users WHERE role = 'teacher' AND linked_id = ?", (db_id,))
                    c.execute("UPDATE Modules SET ID_P = NULL WHERE ID_P = ?", (db_id,))
                    c.execute("DELETE FROM Preferences WHERE ID_P = ?", (db_id,))
                    c.execute("DELETE FROM Indisponibilites WHERE ID_P = ?", (db_id,))
                    c.execute("DELETE FROM SwapRequests WHERE ID_P_Requester = ? OR ID_P_Target = ?", (db_id, db_id))
                    c.execute("DELETE FROM RescheduleRequests WHERE ID_P = ?", (db_id,))
                    c.execute("DELETE FROM UnavailabilityRequests WHERE ID_P = ?", (db_id,))
                    
        # 2. Insert or Update remaining professors
        for p in profs_data:
            name_clean = p['name'].strip()
            if name_clean:
                c.execute("SELECT ID_P FROM Profs WHERE nameP = ? AND specialite = ?", (name_clean, p['specialite']))
                row = c.fetchone()
                if row:
                    prof_id = row['ID_P']
                    c.execute("UPDATE Profs SET prof = ?, matricule = ? WHERE ID_P = ?", (p['is_prof'], p.get('matricule', ''), prof_id))
                else:
                    c.execute("INSERT INTO Profs (nameP, prof, specialite, matricule) VALUES (?, ?, ?, ?)", 
                              (name_clean, p['is_prof'], p['specialite'], p.get('matricule', '')))
                    prof_id = c.lastrowid
                    c.execute("INSERT OR IGNORE INTO Users (username, password, role, linked_id) VALUES (?, ?, 'teacher', ?)", 
                              (f"teacher_{prof_id}", "teacher123", prof_id))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def save_rooms(amphis, tds):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        amphis_keep = [name.strip() for name in amphis if name.strip()]
        tds_keep = [name.strip() for name in tds if name.strip()]
        
        # 1. Handle Amphis deletion
        c.execute("SELECT ID_S, nameS FROM Salles WHERE typeS = 1")
        db_amphis = c.fetchall()
        for row in db_amphis:
            db_name = row['nameS']
            db_id = row['ID_S']
            if db_name not in amphis_keep:
                c.execute("DELETE FROM Salles WHERE ID_S = ?", (db_id,))
                c.execute("UPDATE Planning SET ID_S = NULL WHERE ID_S = ?", (db_id,))
                
        # 2. Handle TDs deletion
        c.execute("SELECT ID_S, nameS FROM Salles WHERE typeS = 0")
        db_tds = c.fetchall()
        for row in db_tds:
            db_name = row['nameS']
            db_id = row['ID_S']
            if db_name not in tds_keep:
                c.execute("DELETE FROM Salles WHERE ID_S = ?", (db_id,))
                c.execute("UPDATE Planning SET ID_S = NULL WHERE ID_S = ?", (db_id,))
                
        # 3. Insert new Amphis
        for name in amphis_keep:
            c.execute("SELECT ID_S FROM Salles WHERE nameS = ? AND typeS = 1", (name,))
            if not c.fetchone():
                c.execute("INSERT INTO Salles (typeS, nameS) VALUES (?, ?)", (1, name))
                
        # 4. Insert new TDs
        for name in tds_keep:
            c.execute("SELECT ID_S FROM Salles WHERE nameS = ? AND typeS = 0", (name,))
            if not c.fetchone():
                c.execute("INSERT INTO Salles (typeS, nameS) VALUES (?, ?)", (0, name))
                
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def save_modules(sessions_data, section_id=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if section_id is not None:
            c.execute("SELECT ID_M FROM Modules WHERE ID_E = ? OR ID_E IN (SELECT ID_E FROM Entities WHERE typeE = 0 AND sectionID = ?)", (section_id, section_id))
            mod_ids = [row['ID_M'] for row in c.fetchall()]
            if mod_ids:
                placeholders = ','.join('?' for _ in mod_ids)
                c.execute(f"DELETE FROM Preferences WHERE ID_M IN ({placeholders})", tuple(mod_ids))
                c.execute(f"DELETE FROM Planning WHERE ID_M IN ({placeholders})", tuple(mod_ids))
            c.execute("DELETE FROM Modules WHERE ID_E = ? OR ID_E IN (SELECT ID_E FROM Entities WHERE typeE = 0 AND sectionID = ?)", (section_id, section_id))
            
        for session in sessions_data:
            if session['nameM'].strip():
                c.execute("INSERT INTO Modules (typeM, nameM, ID_P, ID_E) VALUES (?, ?, ?, ?)", 
                          (session['typeM'], session['nameM'], session['ID_P'], session['ID_E']))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database error: {e}")
        return False
    finally:
        conn.close()

def show_student_data_entry():
    st.markdown(tr("### 🎓 Students Data Entry"))
            
    level = st.selectbox(tr("Select Level"), ["L1", "L2", "L3", "M1", "M2"], key="student_level_sel")
    
    # Pre-fetch existing configurations for this level
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_E, specialite FROM Entities WHERE typeE=1 AND specialite LIKE ? ORDER BY ID_E ASC", (f"{level} %",))
    seen = set()
    existing_specs = []
    for row in c.fetchall():
        if row['specialite'] not in seen:
            seen.add(row['specialite'])
            # Fetch sections
            c.execute("SELECT ID_E FROM Entities WHERE typeE=1 AND specialite=? ORDER BY ID_E ASC", (row['specialite'],))
            sections_data = c.fetchall()
            sec_counts = []
            for s in sections_data:
                c.execute("SELECT COUNT(*) as c FROM Entities WHERE typeE=0 AND sectionID=?", (s['ID_E'],))
                count = c.fetchone()['c']
                sec_counts.append(count)
            existing_specs.append({
                "name": row['specialite'].replace(f"{level} ", "", 1),
                "sections": sec_counts
            })
    conn.close()
    
    SPECIALTIES_MAPPING = {
        "L1": ["Mathematics"],
        "L2": ["Operational Research", "Probability & Statistics", "Algebra and Cryptography", "Mathematics"],
        "L3": ["Operational Research", "Probability & Statistics", "Algebra and Cryptography", "Mathematics"],
        "M1": ["MF", "SPA", "2MIR", "ERO", "MSPRO", "ROMARIN", "EDP", "ACC"],
        "M2": ["MF", "SPA", "2MIR", "ERO", "MSPRO", "ROMARIN", "EDP", "ACC"]
    }
    expected_specs = SPECIALTIES_MAPPING.get(level, [])
    
    existing_dict = {spec['name']: spec for spec in existing_specs}
    
    import pandas as pd
    
    data = []
    for spec_name in expected_specs:
        if spec_name in existing_dict:
            secs = existing_dict[spec_name]['sections']
            num_sections = len(secs)
            groups_per_section = secs[0] if num_sections > 0 else 2
        else:
            num_sections = 1
            groups_per_section = 2
            
        from views.shared import format_specialty_with_acronym
        data.append({
            "Specialty Name": format_specialty_with_acronym(spec_name),
            "Number of Sections": num_sections,
            "Number of Groups per Section": groups_per_section
        })
        
    df = pd.DataFrame(data)
    
    st.markdown(f"**{tr('(Edit the grid below to specify sections and groups for each specialty)')}**")
    st.caption(tr("💡 *Note: The system will automatically label your generated sections alphabetically (Section A, Section B) and your groups sequentially (G1, G2).*"))
    
    config = {
        "Specialty Name": st.column_config.TextColumn(tr("Specialty Name"), disabled=True),
        "Number of Sections": st.column_config.NumberColumn(tr("Number of Sections"), min_value=1, step=1, default=1, required=True),
        "Number of Groups per Section": st.column_config.NumberColumn(tr("Number of Groups per Section"), min_value=1, step=1, default=2, required=True),
    }
    
    st.markdown("""
        <style>
        /* Hide the global toolbar (Download, Search, etc.) */
        [data-testid="stElementToolbar"] {
            display: none !important;
        }
        /* Hide the column menu popover when it contains the 'Copy column name' button */
        [data-testid="stPopover"]:has(button[aria-label="Copy column name"]),
        [data-testid="stPopover"]:has(div[role="menuitem"]),
        .st-emotion-cache-18ni7ap {
            display: none !important;
            visibility: hidden !important;
            pointer-events: none !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
    edited_df = st.data_editor(df, column_config=config, use_container_width=True, hide_index=True, key=f"editor_{level}")
    
    if st.button(f"{tr('Save student entities for ')}{level}", type="primary", key=f"save_stu_btn_{level}"):
        specs_data = []
        import re
        for index, row in edited_df.iterrows():
            name = str(row["Specialty Name"]).strip()
            if not name or name == "None" or name == "nan":
                continue
            name = re.sub(r'\s*\([^)]*\)$', '', name).strip()
            num_sec = int(row["Number of Sections"])
            groups_per_sec = int(row["Number of Groups per Section"])
            sections = [groups_per_sec] * max(1, num_sec)
            specs_data.append({"name": name, "sections": sections})
            
        if not specs_data:
            st.warning(tr("Please provide a name for at least one specialty before saving."))
            return
            
        if sync_student_entities(level, specs_data):
            st.success(f"{tr('Student entities for')} {level} {tr('successfully updated!')}")
            time.sleep(1)
            st.rerun()

    st.divider()
    st.markdown(tr("### Manage Student Data"))
    stu_ver = st.session_state.get('stu_ver', 0)
    conf_stu = st.checkbox(tr("Confirm Student Deletion"), key=f"conf_stu_v{stu_ver}")
    if st.button(tr("Clear Students Table"), disabled=not conf_stu, type="primary", key="btn_clear_stu"):
        clear_table_students()
        st.session_state['stu_ver'] = stu_ver + 1
        st.success(tr("Students table cleared!"))
        time.sleep(1)
        st.rerun()

def show_delegate_matricules_entry():
    st.write("")
    st.markdown(tr("### 🎓 Section Delegates Matricules"))
    st.write(tr("Assign a secure Matricule to the delegate of each section. Delegates will need this Matricule to sign up."))
    
    level = st.session_state.get("student_level_sel", "L1")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT e.ID_E, e.nameE, e.specialite, d.matricule
        FROM Entities e
        LEFT JOIN Delegates d ON e.ID_E = d.section_id
        WHERE e.typeE = 1 AND e.specialite LIKE ?
        ORDER BY e.specialite, e.nameE
    """, (f"{level} %",))
    sections = c.fetchall()
    conn.close()
    
    if not sections:
        st.info(tr("No student sections have been created yet. Please define student entities first."))
        return
        
    import pandas as pd
    from views.shared import format_specialty_with_acronym
    sec_data = []
    for s in sections:
        sec_data.append({
            "Section ID": s['ID_E'],
            "Specialty": format_specialty_with_acronym(s['specialite']),
            "Section Name": s['nameE'].split(' - ')[-1] if ' - ' in s['nameE'] else s['nameE'],
            "Delegate Matricule": s['matricule'] or ""
        })
        
    df = pd.DataFrame(sec_data)
    
    config = {
        "Section ID": st.column_config.NumberColumn(tr("Section ID"), disabled=True),
        "Specialty": st.column_config.TextColumn(tr("Specialty"), disabled=True),
        "Section Name": st.column_config.TextColumn(tr("Section Name"), disabled=True),
        "Delegate Matricule": st.column_config.TextColumn(tr("Delegate Matricule"), required=False),
    }
    
    edited_df = st.data_editor(df, column_config=config, use_container_width=True, hide_index=True, key="delegate_matricules_editor")
    
    if st.button(tr("Save Delegate Matricules"), type="primary"):
        # Check for duplicates inside the current edited_df
        seen = set()
        has_duplicates = False
        new_mats = {}
        for idx, row in edited_df.iterrows():
            val = row["Delegate Matricule"]
            mat = str(val).strip() if pd.notna(val) and val is not None else ""
            if mat:
                if mat in seen:
                    has_duplicates = True
                    break
                seen.add(mat)
                sec_id = int(row["Section ID"])
                new_mats[sec_id] = mat
        
        # Check globally against other levels in database
        if not has_duplicates:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT section_id, matricule FROM Delegates")
            all_db_delegates = c.fetchall()
            conn.close()
            
            current_level_section_ids = set(new_mats.keys())
            for row in all_db_delegates:
                sec_id = row["section_id"]
                mat = row["matricule"]
                if sec_id not in current_level_section_ids and mat:
                    if mat in seen:
                        has_duplicates = True
                        break
        
        if has_duplicates:
            st.error(tr("Error: Each delegate matricule must be unique. You cannot assign the same matricule to multiple delegates."))
        else:
            conn = get_db_connection()
            c = conn.cursor()
            for idx, row in edited_df.iterrows():
                sec_id = int(row["Section ID"])
                val = row["Delegate Matricule"]
                mat = str(val).strip() if pd.notna(val) and val is not None else ""
                if mat:
                    c.execute("INSERT OR REPLACE INTO Delegates (section_id, matricule) VALUES (?, ?)", (sec_id, mat))
                else:
                    c.execute("DELETE FROM Delegates WHERE section_id = ?", (sec_id,))
            conn.commit()
            conn.close()
            st.success(tr("Delegate matricules updated successfully!"))
            time.sleep(1)
            st.rerun()

def show_professor_data_entry():
    st.markdown(tr("### 👨‍🏫 Professors Data Entry"))
    
    username = st.session_state.user['username']
    draft = load_draft(username, 'prof_form')
    
    departments = [
        "Operational Research",
        "Probability & Statistics",
        "Algebra and Cryptography",
        "Mathematics"
    ]
    
    # If the draft is empty, pre-populate it with the professors currently in the database
    if not draft:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT nameP, prof, specialite, matricule FROM Profs ORDER BY ID_P ASC")
        db_profs = c.fetchall()
        conn.close()
        
        # Group by specialty
        profs_by_spec = {}
        for row in db_profs:
            spec = row['specialite']
            profs_by_spec.setdefault(spec, []).append(row)
            
        draft = {}
        for spec in departments:
            spec_profs = profs_by_spec.get(spec, [])
            draft[f"num_profs_{spec}"] = max(1, len(spec_profs))
            for i, p in enumerate(spec_profs):
                draft[f"pname_{spec}_{i}"] = p['nameP']
                draft[f"mat_{spec}_{i}"] = p['matricule'] if p['matricule'] else ""
                draft[f"isprof_{spec}_{i}"] = bool(p['prof'])
                
    current_draft = {}
        
    st.markdown("---")
    profs_data = []
    
    prof_ver = st.session_state.get('prof_ver', 0)
    for spec in departments:
        
        st.markdown(f"#### 🏢 Department: `{tr(spec)}`")
        # stable draft keys, versioned widget keys
        num_prof_draft_key = f"num_profs_{spec}"
        num_prof_widget_key = f"{num_prof_draft_key}_v{prof_ver}"
        num_profs = st.number_input(f"{tr('Number of professors in ')}{tr(spec)}", min_value=0, value=draft.get(num_prof_draft_key, 1), step=1, key=num_prof_widget_key)
        current_draft[num_prof_draft_key] = num_profs
        
        for i in range(int(num_profs)):
            c1, c2, c3 = st.columns([2, 2, 1])
            pname_draft_key = f"pname_{spec}_{i}"
            mat_draft_key = f"mat_{spec}_{i}"
            isprof_draft_key = f"isprof_{spec}_{i}"
            
            pname_widget_key = f"{pname_draft_key}_v{prof_ver}"
            mat_widget_key = f"{mat_draft_key}_v{prof_ver}"
            isprof_widget_key = f"{isprof_draft_key}_v{prof_ver}"
            
            with c1:
                p_name = st.text_input(f"{tr('Professor')} {i+1} - {tr('Name')}", value=draft.get(pname_draft_key, ""), key=pname_widget_key)
                current_draft[pname_draft_key] = p_name
            with c2:
                mat = st.text_input(tr("Matricule"), value=draft.get(mat_draft_key, ""), key=mat_widget_key)
                current_draft[mat_draft_key] = mat
            with c3:
                is_prof = st.checkbox(tr("Grade 'Prof'?"), value=draft.get(isprof_draft_key, False), key=isprof_widget_key)
                current_draft[isprof_draft_key] = is_prof
            
            profs_data.append({
                "name": p_name,
                "matricule": mat,
                "is_prof": 1 if is_prof else 0,
                "specialite": spec
            })
            
    if st.button(tr("Save Professors"), type="primary"):
        filtered_profs = [p for p in profs_data if p["name"].strip()]
        
        # Check for duplicates in non-empty matricules inside inputs
        mat_to_name = {}
        conflict_msg = ""
        has_duplicates = False
        input_mats = []
        for p in filtered_profs:
            mat = p.get('matricule', '').strip()
            name = p['name'].strip().lower()
            if mat:
                if mat in mat_to_name:
                    if mat_to_name[mat] != name:
                        has_duplicates = True
                        conflict_msg = f"Matricule '{mat}' is assigned to both '{mat_to_name[mat].title()}' and '{name.title()}' in your inputs."
                        break
                else:
                    mat_to_name[mat] = name
                input_mats.append(mat)
                
        # Check globally against existing professors in DB
        if not has_duplicates and input_mats:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT nameP, matricule FROM Profs WHERE matricule IS NOT NULL AND matricule != ''")
            db_profs = c.fetchall()
            conn.close()
            
            db_mat_to_names = {}
            for row in db_profs:
                db_name = row['nameP'].strip().lower()
                db_mat = row['matricule'].strip()
                if db_mat:
                    db_mat_to_names.setdefault(db_mat, set()).add(db_name)
            
            for p in filtered_profs:
                name = p["name"].strip().lower()
                mat = p.get("matricule", "").strip()
                if mat and mat in db_mat_to_names:
                    associated_names = db_mat_to_names[mat]
                    if name not in associated_names:
                        has_duplicates = True
                        conflict_name = list(associated_names)[0].title()
                        conflict_msg = f"Matricule '{mat}' is already assigned to an existing professor named '{conflict_name}' in the database. If you are trying to rename them, you must clear the table first."
                        break
                    
        if has_duplicates:
            st.error(f"Error: {conflict_msg}")
        else:
            if save_professors(filtered_profs):
                clear_draft(username, 'prof_form')
                st.session_state['prof_ver'] = prof_ver + 1
                st.success(f"{len(filtered_profs)} {tr('Professors saved. Teacher accounts auto-generated.')}")
                time.sleep(1)
                st.rerun()
    else:
        save_draft(username, 'prof_form', current_draft)

    st.divider()
    st.divider()
    st.markdown(tr("### Manage Professor Data"))
    conf_prof = st.checkbox(tr("Confirm All Professor Deletion"), key=f"conf_prof_v{prof_ver}")
    if st.button(tr("Clear Professors Table"), disabled=not conf_prof, type="primary", key="btn_clear_prof"):
        clear_table_professors()
        clear_draft(st.session_state.user['username'], 'prof_form')
        st.session_state['prof_ver'] = prof_ver + 1
        st.success(tr("Professors table cleared!"))
        time.sleep(1)
        st.rerun()

def show_room_data_entry():
    st.markdown(tr("### 🏢 Rooms Data Entry"))
    
    username = st.session_state.user['username']
    draft = load_draft(username, 'room_form')
    
    # If the draft is empty, pre-populate it with the rooms currently in the database
    if not draft:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT nameS, typeS FROM Salles ORDER BY ID_S ASC")
        db_rooms = c.fetchall()
        conn.close()
        
        amphis_db = [r['nameS'] for r in db_rooms if r['typeS'] == 1]
        tds_db = [r['nameS'] for r in db_rooms if r['typeS'] == 0]
        
        draft = {
            "num_amphis": max(1, len(amphis_db)),
            "num_td": max(1, len(tds_db))
        }
        for i, name in enumerate(amphis_db):
            draft[f"amphi_{i}"] = name
        for i, name in enumerate(tds_db):
            draft[f"td_{i}"] = name
            
    current_draft = {}
    
    room_ver = st.session_state.get('room_ver', 0)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### {tr('Lecture Rooms (Amphis)')}")
        num_amphis_key = f"num_amphis_v{room_ver}"
        # We use stable names for the draft dictionary keys
        num_amphis = st.number_input(tr("Number of Amphis"), min_value=0, value=draft.get("num_amphis", 1), step=1, key=num_amphis_key)
        current_draft["num_amphis"] = num_amphis
        amphis = []
        for i in range(int(num_amphis)):
            akey = f"amphi_{i}_v{room_ver}"
            aval = st.text_input(f"{tr('Amphi')} {i+1} - {tr('Name')}", value=draft.get(f"amphi_{i}", ""), key=akey)
            current_draft[f"amphi_{i}"] = aval
            amphis.append(aval)
    with c2:
        st.markdown(f"#### {tr('Tutorial Rooms (TD)')}")
        num_td_key = f"num_td_v{room_ver}"
        num_td = st.number_input(tr("Number of TD Rooms"), min_value=0, value=draft.get("num_td", 1), step=1, key=num_td_key)
        current_draft["num_td"] = num_td
        td_rooms = []
        for i in range(int(num_td)):
            tkey = f"td_{i}_v{room_ver}"
            tval = st.text_input(f"{tr('TD Room')} {i+1} - {tr('Name')}", value=draft.get(f"td_{i}", ""), key=tkey)
            current_draft[f"td_{i}"] = tval
            td_rooms.append(tval)
            
    if st.button(tr("Save Rooms"), type="primary"):
        if save_rooms(amphis, td_rooms):
            clear_draft(username, 'room_form')
            st.session_state['room_ver'] = room_ver + 1
            st.success(tr("Rooms saved successfully!"))
            time.sleep(1)
            st.rerun()
    else:
        save_draft(username, 'room_form', current_draft)

    st.divider()
    st.markdown(tr("### Manage Room Data"))
    conf_room = st.checkbox(tr("Confirm Room Deletion"), key=f"conf_room_v{room_ver}")
    if st.button(tr("Clear Rooms Table"), disabled=not conf_room, type="primary", key="btn_clear_room"):
        clear_table_rooms()
        clear_draft(st.session_state.user['username'], 'room_form')
        st.session_state['room_ver'] = room_ver + 1
        st.success(tr("Rooms table cleared!"))
        time.sleep(1)
        st.rerun()

def load_draft_from_db_for_section(section_id, level, spec_name, section_name):
    conn = get_db_connection()
    c = conn.cursor()
    # Find all modules associated with this section (ID_E = section_id)
    # or any of its groups (sectionID = section_id)
    c.execute("""
        SELECT m.ID_M, m.typeM, m.nameM, m.ID_P, m.ID_E, e.nameE, e.typeE
        FROM Modules m
        JOIN Entities e ON m.ID_E = e.ID_E
        WHERE m.ID_E = ? 
           OR (e.typeE = 0 AND e.sectionID = ?)
    """, (section_id, section_id))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    
    if not rows:
        return {}
        
    # We want to group by module name
    modules_dict = {}
    for r in rows:
        m_name = r['nameM']
        if m_name not in modules_dict:
            modules_dict[m_name] = {
                "cours_count": 0,
                "td_count_by_group": {},
                "prof_cours": None,
                "prof_td_by_group": {}
            }
        
        if r['typeM'] == 1: # Cours
            modules_dict[m_name]["cours_count"] += 1
            modules_dict[m_name]["prof_cours"] = r['ID_P']
        else: # TD
            grp_id = r['ID_E']
            modules_dict[m_name]["td_count_by_group"][grp_id] = modules_dict[m_name]["td_count_by_group"].get(grp_id, 0) + 1
            modules_dict[m_name]["prof_td_by_group"][grp_id] = r['ID_P']
            
    db_draft = {}
    db_draft["module_level"] = level
    db_draft["module_spec_name"] = spec_name
    db_draft["module_section_name"] = section_name
    db_draft["module_num_modules"] = len(modules_dict)
    
    # We also need to know the list of groups in this section
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_E FROM Entities WHERE typeE = 0 AND sectionID = ?", (section_id,))
    group_ids = [row['ID_E'] for row in c.fetchall()]
    conn.close()
    
    for idx, (m_name, info) in enumerate(modules_dict.items()):
        db_draft[f"m_name_{level}_{spec_name}_{idx}"] = m_name
        db_draft[f"cours_{level}_{spec_name}_{idx}"] = info["cours_count"]
        
        # TD count per group: since it's the same for all groups, take the max from any group
        td_count = 0
        if info["td_count_by_group"]:
            td_count = max(info["td_count_by_group"].values())
        db_draft[f"td_{level}_{spec_name}_{idx}"] = td_count
        
        if info["prof_cours"] is not None:
            db_draft[f"p_c_{level}_{spec_name}_{section_name}_{idx}"] = info["prof_cours"]
        for grp_id in group_ids:
            prof_td = info["prof_td_by_group"].get(grp_id)
            if prof_td is not None:
                db_draft[f"p_t_{level}_{spec_name}_{section_name}_{grp_id}_{idx}"] = prof_td
    return db_draft

def show_module_data_entry():
    # Define layout containers to control visual ordering
    cont_header = st.container()
    cont_level_spec = st.container()
    cont_define_modules = st.container()
    cont_choose_section = st.container()
    cont_assign_sessions = st.container()

    with cont_header:
        st.markdown(tr("### 📚 Modules & Sessions Data Entry"))
    
    username = st.session_state.user['username']
    module_ver = st.session_state.get('module_ver', 0)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT DISTINCT specialite FROM Entities WHERE specialite IS NOT NULL AND specialite != ''")
    all_specs = [row['specialite'] for row in c.fetchall()]
    conn.close()
    
    if not all_specs:
        with cont_level_spec:
            st.warning(tr("Please define student entities first."))
        return

    # 1. Study level and Specialty
    with cont_level_spec:
        level_opts = ["L1", "L2", "L3", "M1", "M2"]
        level_key = f"module_level_v{module_ver}"
        level = st.selectbox(tr("Choose Study Level"), level_opts, key=level_key)
        
        level_specs = [s for s in all_specs if s.startswith(level)]
        if not level_specs:
            st.warning(f"{tr('No specialties found for ')}{level}.")
            return
            
        from views.shared import format_specialty_with_acronym
        spec_name_key = f"module_spec_name_v{module_ver}"
        spec_name = st.selectbox(
            tr("Choose Specialty Name"), 
            level_specs,
            format_func=lambda x: format_specialty_with_acronym(tr(x.replace(f"{level} ", "", 1).strip()) or x),
            key=spec_name_key
        )
    
    # Fetch Sections
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 1 AND specialite = ?", (spec_name,))
    sections = {row['nameE']: row['ID_E'] for row in c.fetchall()}
    
    c.execute("SELECT MIN(ID_P) as ID_P, nameP, specialite FROM Profs GROUP BY nameP, specialite ORDER BY nameP ASC")
    profs = {row['ID_P']: row['nameP'] for row in c.fetchall()}
    conn.close()
    
    if not sections:
        with cont_level_spec:
            st.warning(f"{tr('No sections found for ')}{spec_name}.")
        return
        
    # 2. Choose Section (Rendered in its container after Define Modules)
    with cont_choose_section:
        st.divider()
        sec_name_key = f"module_section_id_v{module_ver}"
        sec_opts_ids = list(sections.values())
        id_to_name = {v: k for k, v in sections.items()}
        from views.shared import format_entity_name
        section_id = st.selectbox(
            tr("Choose Section"), 
            sec_opts_ids, 
            format_func=lambda x: format_entity_name(id_to_name.get(x, "")), 
            key=sec_name_key
        )
        section_name = id_to_name.get(section_id, "")
    
    # 3. Resolve Group Entities for this Section
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 0 AND sectionID = ?", (section_id,))
    section_groups = {row['nameE']: row['ID_E'] for row in c.fetchall()}
    conn.close()
    
    # 4. Load Section-Specific Draft
    draft_key = f"module_form_{section_id}"
    draft = load_draft(username, draft_key)
    if not draft:
        draft = load_draft_from_db_for_section(section_id, level, spec_name, section_name)
        
    current_draft = {}
    current_draft["module_level"] = level
    current_draft["module_spec_name"] = spec_name
    current_draft["module_section_name"] = section_name
    
    # 5. Define Modules (Rendered in its container before Choose Section)
    with cont_define_modules:
        num_mod_key = f"module_num_modules_v{module_ver}"
        default_num_modules = int(draft.get("module_num_modules", 1))
        num_modules = st.number_input(tr("Number of Modules"), min_value=1, value=default_num_modules, step=1, key=num_mod_key)
        current_draft["module_num_modules"] = num_modules
        
        modules_info = []
        # For each module, ask for module name and number of lectures / TD
        st.markdown(f"#### {tr('Define Modules')}")
        for i in range(int(num_modules)):
            c1, c2, c3 = st.columns(3)
            mname_key = f"m_name_{level}_{spec_name}_{i}"
            cours_key = f"cours_{level}_{spec_name}_{i}"
            td_key = f"td_{level}_{spec_name}_{i}"
            
            with c1:
                mname_widget_key = f"m_name_{level}_{spec_name}_{i}_v{module_ver}"
                default_m_name = draft.get(mname_key, "")
                m_name = st.text_input(f"{tr('Module')} {i+1} - {tr('Name')}", value=default_m_name, key=mname_widget_key)
                current_draft[mname_key] = m_name
            with c2:
                cours_widget_key = f"cours_{level}_{spec_name}_{i}_v{module_ver}"
                default_cours = int(draft.get(cours_key, 1))
                num_cours = st.number_input(f"{tr('Lectures (Cours) for ')}{m_name or tr('Module')+' '+str(i+1)}", min_value=0, value=default_cours, step=1, key=cours_widget_key)
                current_draft[cours_key] = num_cours
            with c3:
                td_widget_key = f"td_{level}_{spec_name}_{i}_v{module_ver}"
                default_td = int(draft.get(td_key, 1))
                num_td = st.number_input(f"{tr('Tutorials (TD) for ')}{m_name or tr('Module')+' '+str(i+1)}", min_value=0, value=default_td, step=1, key=td_widget_key)
                current_draft[td_key] = num_td
            
            modules_info.append({
                "name": m_name,
                "cours": int(num_cours),
                "td": int(num_td)
            })
            
    # 6. Assign Sessions (Rendered in its container after Choose Section)
    with cont_assign_sessions:
        from views.shared import format_entity_name
        st.markdown(f"#### {tr('Assign Sessions for ')}{format_entity_name(section_name)}")
        
        if not profs:
            st.warning(tr("No professors available."))
            return
            
        prof_options = list(profs.keys())
        sessions_to_save = []
        
        for m_idx, mod in enumerate(modules_info):
            if not mod['name'].strip():
                continue
                
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, rgba(214, 47, 58, 0.05), rgba(214, 47, 58, 0.01));
                padding: 10px 16px;
                border-left: 4px solid #D62F3A;
                border-radius: 4px 8px 8px 4px;
                margin-top: 22px;
                margin-bottom: 15px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.01);
            ">
                <span style="
                    font-family: 'Inter', sans-serif;
                    color: #555;
                    font-size: 0.8em;
                    text-transform: uppercase;
                    letter-spacing: 1.5px;
                    display: block;
                    font-weight: 600;
                    opacity: 0.8;
                ">Course Module</span>
                <span style="
                    font-family: 'Inter', sans-serif;
                    color: #D62F3A;
                    font-size: 1.25em;
                    font-weight: 700;
                    display: block;
                    margin-top: 2px;
                ">📚 {mod["name"]}</span>
            </div>
            """, unsafe_allow_html=True)
            
            # Lectures (Cours)
            if mod['cours'] > 0:
                pc_key = f"p_c_{level}_{spec_name}_{section_name}_{m_idx}_v{module_ver}"
                pc_draft_key = f"p_c_{level}_{spec_name}_{section_name}_{m_idx}"
                
                default_prof_id = draft.get(pc_draft_key)
                if default_prof_id in prof_options:
                    pc_idx = prof_options.index(default_prof_id)
                else:
                    pc_idx = 0
                    
                label = "Prof for Lectures (Cours)" if mod['cours'] > 1 else "Prof for Lecture (Cours)"
                sel_prof = st.selectbox(tr(label), options=prof_options, index=pc_idx, format_func=lambda x: profs[x], key=pc_key)
                current_draft[pc_draft_key] = sel_prof
                
                for _ in range(mod['cours']):
                    sessions_to_save.append({
                        "nameM": mod['name'],
                        "typeM": 1, 
                        "ID_P": sel_prof,
                        "ID_E": section_id
                    })
            
            # Tutorials (TD)
            if mod['td'] > 0:
                st.markdown(f"*{mod['name']} - {tr('Tutorials (TD) (Assign Prof per Group):')}*")
                if not section_groups:
                    st.error(tr("No groups found in this section!"))
                else:
                    grp_items = list(section_groups.items())
                    num_cols = min(4, len(grp_items))
                    cols = st.columns(num_cols)
                    
                    for i, (grp_name, grp_id) in enumerate(grp_items):
                        with cols[i % num_cols]:
                            base_grp_name = grp_name.split('-')[-1].strip()
                            pt_key = f"p_t_{level}_{spec_name}_{section_name}_{grp_id}_{m_idx}_v{module_ver}"
                            pt_draft_key = f"p_t_{level}_{spec_name}_{section_name}_{grp_id}_{m_idx}"
                            
                            default_pt_id = draft.get(pt_draft_key)
                            if default_pt_id in prof_options:
                                pt_idx = prof_options.index(default_pt_id)
                            else:
                                pt_idx = 0
                                
                            sel_prof = st.selectbox(f"{tr('Prof')} ({base_grp_name})", options=prof_options, index=pt_idx, format_func=lambda x: profs[x], key=pt_key)
                            current_draft[pt_draft_key] = sel_prof
                            
                            for _ in range(mod['td']):
                                sessions_to_save.append({
                                    "nameM": mod['name'],
                                    "typeM": 0,
                                    "ID_P": sel_prof,
                                    "ID_E": grp_id
                                })
        
        if st.button(tr("Save All Sessions"), type="primary"):
            if save_modules(sessions_to_save, section_id=section_id):
                clear_draft(username, draft_key)
                st.session_state['module_ver'] = module_ver + 1
                st.success(tr("Successfully assigned and saved sessions!"))
                time.sleep(1)
                st.rerun()
        else:
            save_draft(username, draft_key, current_draft)

        st.divider()
        st.markdown(tr("### Manage Module Data"))
        conf_mod = st.checkbox(tr("Confirm Module Deletion"), key=f"conf_mod_v{module_ver}")
        if st.button(tr("Clear Modules Table"), disabled=not conf_mod, type="primary", key="btn_clear_mod"):
            clear_table_modules()
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("DELETE FROM Drafts WHERE username=? AND form_key LIKE 'module_form_%'", (username,))
            conn.commit()
            conn.close()
            st.session_state['module_ver'] = module_ver + 1
            st.success(tr("Modules table cleared!"))
            time.sleep(1)
            st.rerun()

def show_timetables_view():
    import sqlite3
    from views.shared import tr, render_schedule_grid
    st.markdown(f"## {tr('🌐 Global Timetables Viewer')}")
    st.info(tr("Browse assigned timetables hierarchically by Level, Speciality, and Section."))
    
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    view_mode = st.radio(
        tr("View Mode:"),
        [tr("By Section"), tr("By Professor"), tr("By Room"), tr("By Module")],
        horizontal=True
    )
    
    st.write("---")

    if view_mode == tr("By Section"):
        c.execute("SELECT DISTINCT specialite FROM Entities WHERE typeE = 1 AND specialite IS NOT NULL")
        all_specs = [r['specialite'] for r in c.fetchall()]
        
        levels = ["L1", "L2", "L3", "M1", "M2"]
        level = st.selectbox(tr("1. Select Level"), levels, index=None, placeholder=tr("Choose Level..."))
        
        if level:
            level_specs = sorted([s for s in all_specs if s.startswith(level + " ") or s == level])
            spec_name = st.selectbox(
                tr("2. Select Speciality"), 
                level_specs, 
                index=None, 
                placeholder=tr("Choose Speciality..."), 
                format_func=lambda x: x.replace(f"{level} ", "", 1).strip() or x
            )
            
            if spec_name:
                c.execute("SELECT ID_E, nameE FROM Entities WHERE typeE = 1 AND specialite = ?", (spec_name,))
                sections_data = c.fetchall()
                sections = {r['nameE']: r['ID_E'] for r in sections_data}
                
                section_name = st.selectbox(tr("3. Select Section"), list(sections.keys()), index=None, placeholder=tr("Choose Section..."))
                
                if section_name:
                    section_id = sections[section_name]
                    c.execute("SELECT ID_E FROM Entities WHERE sectionID=?", (section_id,))
                    section_groups = [r['ID_E'] for r in c.fetchall()]
                    target_section = [section_id] + section_groups
                    
                    s_holders = ','.join('?' * len(target_section))
                    c.execute(f"SELECT * FROM Planning WHERE ID_E IN ({s_holders})", tuple(target_section))
                    planning_list = [dict(r) for r in c.fetchall()]
                    
                    if not planning_list:
                        st.warning(tr("No sessions scheduled yet for this section."))
                    else:
                        render_schedule_grid(planning_list, title=f"{tr('Timetable:')} {section_name}", mode="section")

    elif view_mode == tr("By Professor"):
        c.execute("SELECT DISTINCT nameP FROM Profs ORDER BY nameP")
        profs_data = c.fetchall()
        prof_names = [r['nameP'] for r in profs_data]
        
        prof_name = st.selectbox(tr("Select Professor"), prof_names, index=None, placeholder=tr("Select Professor"))
        
        if prof_name:
            c.execute("SELECT ID_P FROM Profs WHERE nameP=?", (prof_name,))
            prof_ids = [r['ID_P'] for r in c.fetchall()]
            
            if prof_ids:
                p_holders = ','.join('?' * len(prof_ids))
                c.execute(f"SELECT * FROM Planning WHERE ID_P IN ({p_holders})", tuple(prof_ids))
                planning_list = [dict(r) for r in c.fetchall()]
                
                if not planning_list:
                    st.warning(tr("No sessions scheduled yet for this professor."))
                else:
                    render_schedule_grid(planning_list, title=f"{tr('Timetable:')} {prof_name}", mode="professor")
            else:
                st.warning(tr("No sessions scheduled yet for this professor."))

    elif view_mode == tr("By Room"):
        c.execute("SELECT DISTINCT nameS FROM Salles ORDER BY nameS")
        rooms_data = c.fetchall()
        room_names = [r['nameS'] for r in rooms_data]
        
        room_name = st.selectbox(tr("Select Room"), room_names, index=None, placeholder=tr("Select Room"))
        
        if room_name:
            c.execute("SELECT ID_S FROM Salles WHERE nameS=?", (room_name,))
            room_ids = [r['ID_S'] for r in c.fetchall()]
            
            if room_ids:
                s_holders = ','.join('?' * len(room_ids))
                c.execute(f"SELECT * FROM Planning WHERE ID_S IN ({s_holders})", tuple(room_ids))
                planning_list = [dict(r) for r in c.fetchall()]
                
                if not planning_list:
                    st.warning(tr("No sessions scheduled yet for this room."))
                else:
                    render_schedule_grid(planning_list, title=f"{tr('Timetable:')} {room_name}", mode="room")
            else:
                st.warning(tr("No sessions scheduled yet for this room."))

    elif view_mode == tr("By Module"):
        c.execute("SELECT DISTINCT nameM FROM Modules ORDER BY nameM")
        modules_data = c.fetchall()
        mod_names = [r['nameM'] for r in modules_data]
        
        mod_name = st.selectbox(tr("Select Module"), mod_names, index=None, placeholder=tr("Select Module"))
        
        if mod_name:
            c.execute("SELECT ID_M FROM Modules WHERE nameM=?", (mod_name,))
            mod_ids = [r['ID_M'] for r in c.fetchall()]
            
            if mod_ids:
                m_holders = ','.join('?' * len(mod_ids))
                c.execute(f"SELECT * FROM Planning WHERE ID_M IN ({m_holders})", tuple(mod_ids))
                planning_list = [dict(r) for r in c.fetchall()]
                
                if not planning_list:
                    st.warning(tr("No sessions scheduled yet for this module."))
                else:
                    render_schedule_grid(planning_list, title=f"{tr('Timetable:')} {mod_name}", hide_group_name=False, show_entity=True)
            else:
                st.warning(tr("No sessions scheduled yet for this module."))
                    
    conn.close()

def show():
    st.title(tr("Admin Dashboard"))
    
    tab1, tab2, tab3, tab4 = st.tabs([tr("Data Entry"), tr("Approval Dashboard"), tr("AI Engine & Analytics"), tr("Timetables View")])
    
    with tab1:
        import json
        import os
        config_path = "config.json"
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)
        else:
            config = {"semester": "2", "college_year": "2025/2026"}
            
        st.markdown(f"##### {tr('Global Settings')}")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            new_sem = st.selectbox(tr("Semester"), ["1", "2"], index=0 if config.get("semester", "2") == "1" else 1, key="global_sem_selectbox")
        with col_c2:
            try:
                curr_y1 = int(config.get("college_year", "2025/2026").split("/")[0])
            except:
                curr_y1 = 2025
                
            y1 = st.number_input(tr("Start Year"), min_value=2000, max_value=2099, value=curr_y1, step=1, key="global_start_year_input")
            st.caption(f"{tr('College year:')} **{y1}/{y1+1}**")
            new_year = f"{y1}/{y1+1}"
            
        if new_sem != config.get("semester") or new_year != config.get("college_year"):
            config["semester"] = new_sem
            config["college_year"] = new_year
            with open(config_path, "w") as f:
                json.dump(config, f)
                
        st.divider()
        
        st.markdown(f"## {tr('Administrative Data Entry')}")
        sub_tabs = st.tabs([tr("Students"), tr("Professors"), tr("Rooms"), tr("Modules")])
        with sub_tabs[0]:
            show_student_data_entry()
            st.write("")
            show_delegate_matricules_entry()
        with sub_tabs[1]:
            show_professor_data_entry()
        with sub_tabs[2]:
            show_room_data_entry()
        with sub_tabs[3]:
            show_module_data_entry()
        
    with tab2:
        st.markdown(f"## {tr('Approval Dashboard')}")
        
        # --- Fetch Counts for Metrics ---
        u_reqs_all = get_pending_unavailability_requests()
        u_count = len(u_reqs_all) if u_reqs_all else 0

        resched_reqs_all = get_pending_requests()
        resched_count = len(resched_reqs_all) if resched_reqs_all else 0

        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM SwapRequests WHERE status = 'Pending_Admin'")
        swaps_count = c.fetchone()['cnt']
        
        # We also need salles dict for titles and formatting
        c.execute("SELECT ID_S, nameS FROM Salles")
        salles = {row['ID_S']: row['nameS'] for row in c.fetchall()}
        conn.close()
        
        # Display Metrics Row
        k1, k2, k3 = st.columns(3)
        k1.metric(tr("Pending Reschedules"), resched_count)
        k2.metric(tr("Pending Swaps"), swaps_count)
        k3.metric(tr("Pending Unavailability"), u_count)
        
        st.write("")
        
        # Sub-tabs
        app_subtabs = st.tabs([
            tr("📥 Reschedule Requests"), 
            tr("🔄 Swap Requests"), 
            tr("🚫 Unavailability Requests"),
            tr("🧹 System Maintenance")
        ])

        # ----------------------------------------------------
        # SUBTAB 1: RESCHEDULE REQUESTS
        # ----------------------------------------------------
        with app_subtabs[0]:
            st.markdown(f"### {tr('📥 Reschedule Requests')}")
            st.caption(tr("Review requests from teachers requesting to reschedule individual sessions."))
            reqs = get_pending_requests()
            if not reqs:
                st.success(tr("🎉 No pending reschedule requests to review!"))
            else:
                conn = get_db_connection()
                c = conn.cursor()
                
                jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                
                for r in reqs:
                    with st.container(border=True):
                        st.markdown(f"""
                        <div style="background: rgba(214, 47, 58, 0.05); border-left: 4px solid #D62F3A; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;">
                            <strong style="color: var(--text-color); font-size: 1.05em;">{tr('Request from Prof.')} {r['nameP']}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        c.execute("""
                            SELECT p.t, p.ID_S, m.nameM, e.nameE 
                            FROM Planning p 
                            JOIN Modules m ON p.ID_M = m.ID_M
                            LEFT JOIN Entities e ON p.ID_E = e.ID_E
                            WHERE p.id=?
                        """, (r['session_id'],))
                        session_info = c.fetchone()
                        
                        if not session_info:
                            st.warning(tr("Original session no longer exists. It may have been deleted."))
                            if st.button(tr("Dismiss Invalid Request"), key=f"dismiss_{r['id']}"):
                                reject_reschedule_request(r['id'])
                                time.sleep(1)
                                st.rerun()
                            continue
                            
                        old_t = session_info['t']
                        old_day = jours[(old_t - 1) // 6] if 1 <= old_t <= 36 else "Unknown"
                        old_time = horaires[(old_t - 1) % 6] if 1 <= old_t <= 36 else "Unknown"
                        old_room = salles.get(session_info['ID_S'], "Unknown")
                        mod_name = session_info['nameM']
                        ent_name = session_info['nameE'] if session_info['nameE'] else ""
                        
                        new_t = r['new_t']
                        new_day = jours[(new_t - 1) // 6] if 1 <= new_t <= 36 else "Unknown"
                        new_time = horaires[(new_t - 1) % 6] if 1 <= new_t <= 36 else "Unknown"
                        new_room = salles.get(r['new_s_id'], "Unknown")
                        
                        c_orig, c_new = st.columns(2)
                        with c_orig:
                            st.markdown(f"##### {tr('📍 Original Session')}")
                            st.markdown(f"""
                            * **{tr('Module:')}** {mod_name}
                            * **{tr('Group/Section:')}** {ent_name}
                            * **{tr('Time:')}** {tr(old_day)} {tr('at')} {old_time}
                            * **{tr('Room:')}** {old_room}
                            """)
                        with c_new:
                            st.markdown(f"##### {tr('🎯 Requested Session')}")
                            st.markdown(f"""
                            * **{tr('Module:')}** {mod_name}
                            * **{tr('Group/Section:')}** {ent_name}
                            * **{tr('Time:')}** {tr(new_day)} {tr('at')} {new_time}
                            * **{tr('Room:')}** {new_room}
                            """)
                        
                        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
                        with col_btn1:
                            if st.button(tr("✅ Approve"), key=f"approve_{r['id']}", type="primary", use_container_width=True):
                                approve_reschedule_request(r['id'])
                                st.success(tr("Approved and timetable updated."))
                                time.sleep(1)
                                st.rerun()
                        with col_btn2:
                            if st.button(tr("❌ Reject"), key=f"reject_{r['id']}", type="secondary", use_container_width=True):
                                reject_reschedule_request(r['id'])
                                st.warning(tr("Rejected."))
                                time.sleep(1)
                                st.rerun()
                conn.close()
            
            st.write("") # Spacer
            st.divider()
            
            # --- Historical Reschedule Log Table ---
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT r.id, r.session_id, r.status, r.new_t, r.new_s_id,
                       prof.nameP, 
                       p_orig.t as old_t, p_orig.ID_S as old_s_id,
                       m.nameM, m.typeM, e.nameE
                FROM RescheduleRequests r
                JOIN Profs prof ON r.ID_P = prof.ID_P
                LEFT JOIN Planning p_orig ON r.session_id = p_orig.id
                LEFT JOIN Modules m ON p_orig.ID_M = m.ID_M
                LEFT JOIN Entities e ON p_orig.ID_E = e.ID_E
                ORDER BY r.id DESC
            """)
            all_resched = c.fetchall()
            conn.close()
            
            jours_en = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            
            if all_resched:
                resched_log = []
                for row in all_resched:
                    old_t = row['old_t']
                    if old_t:
                        old_day = jours_en[(old_t - 1) // 6] if 1 <= old_t <= 36 else "Unknown"
                        old_time = horaires[(old_t - 1) % 6] if 1 <= old_t <= 36 else "Unknown"
                        old_slot = f"{tr(old_day)} {old_time}"
                    else:
                        old_slot = tr("Unknown (Deleted/Moved)")
                        
                    old_room = salles.get(row['old_s_id'], "Unknown") if row['old_s_id'] else "Unknown"
                    
                    new_t = row['new_t']
                    new_day = jours_en[(new_t - 1) // 6] if 1 <= new_t <= 36 else "Unknown"
                    new_time = horaires[(new_t - 1) % 6] if 1 <= new_t <= 36 else "Unknown"
                    new_slot = f"{tr(new_day)} {new_time}"
                    new_room = salles.get(row['new_s_id'], "Unknown")
                    
                    from views.shared import format_entity_name
                    
                    if row['nameM']:
                        m_type_str = "Cours" if row['typeM'] == 1 else "TD"
                        mod_name_disp = f"{row['nameM']} ({tr(m_type_str)})"
                    else:
                        mod_name_disp = tr("Unknown")

                    resched_log.append({
                        tr("Request ID"): row['id'],
                        tr("Professor"): row['nameP'],
                        tr("Module"): mod_name_disp,
                        tr("Group/Section"): format_entity_name(row['nameE']) if row['nameE'] else tr("Unknown"),
                        tr("Original Slot"): old_slot,
                        tr("Original Room"): tr(old_room),
                        tr("Requested Slot"): new_slot,
                        tr("Requested Room"): tr(new_room),
                        tr("Status"): tr(row['status'])
                    })
                df_resched = pd.DataFrame(resched_log)
                
                def color_status_resched(val):
                    if val in ('Pending', tr('Pending')):
                        color = 'orange'
                    elif val in ('Approved', tr('Approved')):
                        color = 'green'
                    else:
                        color = 'red'
                    return f'color: {color}'
                    
                st.markdown(f"{tr('#### 📜 Reschedule Requests History Log')}")
                st.dataframe(df_resched.style.map(color_status_resched, subset=[tr('Status')]), use_container_width=True)
            else:
                st.info(tr("No reschedule requests history recorded yet."))

        # ----------------------------------------------------
        # SUBTAB 2: SWAP REQUESTS
        # ----------------------------------------------------
        with app_subtabs[1]:
            st.markdown(tr("### 🔄 Pending Session Swaps"))
            st.caption(tr("Swaps already accepted by both professors. Review and finalize here."))
            
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT sr.*, p1.ID_M as m1_id, p1.t as t1, p1.ID_S as s1_id, p1.ID_E as e1_id,
                       p2.ID_M as m2_id, p2.t as t2, p2.ID_S as s2_id, p2.ID_E as e2_id,
                       prof1.nameP as requester_name, prof2.nameP as target_name
                FROM SwapRequests sr
                JOIN Planning p1 ON sr.ID_Session_Requester = p1.id
                JOIN Planning p2 ON sr.ID_Session_Target = p2.id
                JOIN Profs prof1 ON sr.ID_P_Requester = prof1.ID_P
                JOIN Profs prof2 ON sr.ID_P_Target = prof2.ID_P
                WHERE sr.status = 'Pending_Admin'
            """)
            swaps = c.fetchall()
            
            jours_en = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            
            def format_slot(t):
                if not t or t < 1 or t > 36: return f"Slot {t}"
                return f"{tr(jours_en[(t - 1) // 6])} {horaires[(t - 1) % 6]}"
            
            if not swaps:
                st.success(tr("🎉 No pending session swaps to finalize."))
            else:
                for swp in swaps:
                    with st.container(border=True):
                        st.markdown(f"""
                        <div style="background: rgba(214, 47, 58, 0.05); border-left: 4px solid #D62F3A; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;">
                            <strong style="color: var(--text-color); font-size: 1.05em;">{tr('Swap Proposal:')} {swp['requester_name']} ↔ {swp['target_name']}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Fetch Module Names safely
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (swp['m1_id'],))
                        m1 = c.fetchone() or {'nameM': 'Unknown Module', 'typeM': 0}
                        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (swp['m2_id'],))
                        m2 = c.fetchone() or {'nameM': 'Unknown Module', 'typeM': 0}
                        
                        # Fetch Entity Names safely
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (swp['e1_id'],))
                        row_e1 = c.fetchone()
                        e1 = row_e1['nameE'] if row_e1 else "Unknown Entity"
                        
                        c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (swp['e2_id'],))
                        row_e2 = c.fetchone()
                        e2 = row_e2['nameE'] if row_e2 else "Unknown Entity"
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"##### 👤 {tr('Session of')} **{swp['requester_name']}**")
                            m1_type = "Cours" if m1['typeM'] == 1 else "TD"
                            st.write(f"- **{tr('Module:')}** {m1['nameM']} ({tr(m1_type)}) ({e1})")
                            st.write(f"- **{tr('Slot:')}** {format_slot(swp['t1'])}")
                            st.write(f"- **{tr('Room:')}** {salles.get(swp['s1_id'])}")
                        with col2:
                            st.markdown(f"##### 👤 {tr('Session of')} **{swp['target_name']}**")
                            m2_type = "Cours" if m2['typeM'] == 1 else "TD"
                            st.write(f"- **{tr('Module:')}** {m2['nameM']} ({tr(m2_type)}) ({e2})")
                            st.write(f"- **{tr('Slot:')}** {format_slot(swp['t2'])}")
                            st.write(f"- **{tr('Room:')}** {salles.get(swp['s2_id'])}")
                        
                        if swp['suggested_room_id']:
                            st.warning(f"💡 {tr('Alternative Room Suggested for')} {m2['nameM']}: **{salles.get(swp['suggested_room_id'])}**")
                        
                        # AI Conflict Checker
                        st.markdown(f"##### {tr('🔍 AI Conflict Validation')}")
                        
                        def check_conflict(p_id, e_id, s_id, t, exclude_p_id, exclude_e_id, exclude_s_id):
                            cx = get_db_connection()
                            cur = cx.cursor()
                            cur.execute("SELECT id FROM Planning WHERE ID_P=? AND t=? AND ID_P != ?", (p_id, t, exclude_p_id))
                            if cur.fetchone(): return tr("Teacher Conflict")
                            cur.execute("SELECT id FROM Planning WHERE ID_E=? AND t=? AND ID_E != ?", (e_id, t, exclude_e_id))
                            if cur.fetchone(): return tr("Student Conflict")
                            cur.execute("SELECT id FROM Planning WHERE ID_S=? AND t=? AND ID_S != ?", (s_id, t, exclude_s_id))
                            if cur.fetchone(): return tr("Room Conflict")
                            cx.close()
                            return None

                        conf1 = check_conflict(swp['ID_P_Requester'], swp['e1_id'], swp['s2_id'], swp['t2'], swp['ID_P_Requester'], swp['e1_id'], swp['s2_id'])
                        room_2_target = swp['suggested_room_id'] if swp['suggested_room_id'] else swp['s1_id']
                        conf2 = check_conflict(swp['ID_P_Target'], swp['e2_id'], room_2_target, swp['t1'], swp['ID_P_Target'], swp['e2_id'], room_2_target)
                        
                        if not conf1 and not conf2:
                            st.success(tr("✅ No conflicts detected. This swap is legal."))
                            col_b1, col_b2, _ = st.columns([1.5, 1, 3])
                            with col_b1:
                                if st.button(tr("Execute Swap"), key=f"exec_{swp['ID_SR']}", type="primary", use_container_width=True):
                                    c.execute("UPDATE Planning SET t = ?, ID_S = ? WHERE id = ?", (swp['t2'], swp['s2_id'], swp['ID_Session_Requester']))
                                    c.execute("UPDATE Planning SET t = ?, ID_S = ? WHERE id = ?", (swp['t1'], room_2_target, swp['ID_Session_Target']))
                                    c.execute("UPDATE SwapRequests SET status = 'Approved' WHERE ID_SR = ?", (swp['ID_SR'],))
                                    # Auto-cancel other pending requests involving these sessions
                                    c.execute("""
                                        UPDATE SwapRequests 
                                        SET status = 'Auto_Cancelled' 
                                        WHERE ID_SR != ? 
                                          AND status IN ('Pending_Target', 'Pending_Delegate', 'Pending_Admin')
                                          AND (
                                              ID_Session_Requester = ? OR ID_Session_Target = ? OR
                                              ID_Session_Requester = ? OR ID_Session_Target = ?
                                          )
                                    """, (swp['ID_SR'], swp['ID_Session_Requester'], swp['ID_Session_Requester'], swp['ID_Session_Target'], swp['ID_Session_Target']))
                                    conn.commit()
                                    st.success(tr("Timetable updated successfully!"))
                                    time.sleep(1)
                                    st.rerun()
                            with col_b2:
                                if st.button(tr("Reject Swap"), key=f"rej_adm_{swp['ID_SR']}", type="secondary", use_container_width=True):
                                    c.execute("UPDATE SwapRequests SET status = 'Rejected' WHERE ID_SR = ?", (swp['ID_SR'],))
                                    conn.commit()
                                    st.warning(tr("Swap request rejected by Admin."))
                                    time.sleep(1)
                                    st.rerun()
                        else:
                            st.error(f"{tr('❌ Conflict Detected:')} {conf1 if conf1 else conf2}{tr('. Swap might be risky.')}")
                            col_b1, col_b2, _ = st.columns([1.5, 1, 3])
                            with col_b1:
                                if st.button(tr("Force Execute Anyway"), key=f"force_{swp['ID_SR']}", type="primary", use_container_width=True):
                                    c.execute("UPDATE Planning SET t = ?, ID_S = ? WHERE id = ?", (swp['t2'], swp['s2_id'], swp['ID_Session_Requester']))
                                    c.execute("UPDATE Planning SET t = ?, ID_S = ? WHERE id = ?", (swp['t1'], room_2_target, swp['ID_Session_Target']))
                                    c.execute("UPDATE SwapRequests SET status = 'Approved' WHERE ID_SR = ?", (swp['ID_SR'],))
                                    # Auto-cancel other pending requests involving these sessions
                                    c.execute("""
                                        UPDATE SwapRequests 
                                        SET status = 'Auto_Cancelled' 
                                        WHERE ID_SR != ? 
                                          AND status IN ('Pending_Target', 'Pending_Delegate', 'Pending_Admin')
                                          AND (
                                              ID_Session_Requester = ? OR ID_Session_Target = ? OR
                                              ID_Session_Requester = ? OR ID_Session_Target = ?
                                          )
                                    """, (swp['ID_SR'], swp['ID_Session_Requester'], swp['ID_Session_Requester'], swp['ID_Session_Target'], swp['ID_Session_Target']))
                                    conn.commit()
                                    st.success(tr("Timetable updated (Forced)."))
                                    time.sleep(1)
                                    st.rerun()
                            with col_b2:
                                if st.button(tr("Reject Swap"), key=f"rej_adm_{swp['ID_SR']}", type="secondary", use_container_width=True):
                                    c.execute("UPDATE SwapRequests SET status = 'Rejected' WHERE ID_SR = ?", (swp['ID_SR'],))
                                    conn.commit()
                                    st.warning(tr("Swap request rejected by Admin."))
                                    time.sleep(1)
                                    st.rerun()
            conn.close()

            st.write("") # Spacer
            st.divider()

            # --- Historical Swap Log Table ---
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT sr.*, 
                       prof1.nameP as requester_name, prof2.nameP as target_name,
                       p1.t as t1, p1.ID_S as s1_id, p1.ID_E as e1_id, p1.ID_M as m1_id,
                       p2.t as t2, p2.ID_S as s2_id, p2.ID_E as e2_id, p2.ID_M as m2_id
                FROM SwapRequests sr
                JOIN Profs prof1 ON sr.ID_P_Requester = prof1.ID_P
                JOIN Profs prof2 ON sr.ID_P_Target = prof2.ID_P
                LEFT JOIN Planning p1 ON sr.ID_Session_Requester = p1.id
                LEFT JOIN Planning p2 ON sr.ID_Session_Target = p2.id
                WHERE sr.status NOT IN ('Pending_Target', 'Pending_Delegate', 'Rejected_Delegate')
                ORDER BY sr.ID_SR DESC
            """)
            all_swaps = c.fetchall()
            
            jours_en = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            
            def format_slot_hist(t):
                if not t or t < 1 or t > 36: return f"Slot {t}"
                return f"{tr(jours_en[(t - 1) // 6])} {horaires[(t - 1) % 6]}"
                
            if all_swaps:
                swaps_log = []
                for row in all_swaps:
                    # Fetch Module Names safely
                    c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (row['m1_id'],))
                    m1_row = c.fetchone()
                    m1_name = m1_row['nameM'] if m1_row else "Unknown"
                    m1_type = "Cours" if m1_row and m1_row['typeM'] == 1 else "TD"
                    
                    c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M = ?", (row['m2_id'],))
                    m2_row = c.fetchone()
                    m2_name = m2_row['nameM'] if m2_row else "Unknown"
                    m2_type = "Cours" if m2_row and m2_row['typeM'] == 1 else "TD"
                    
                    from views.shared import format_entity_name
                    # Fetch Entity Names safely
                    c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (row['e1_id'],))
                    row_e1 = c.fetchone()
                    e1 = format_entity_name(row_e1['nameE']) if row_e1 else "Unknown"
                    
                    c.execute("SELECT nameE FROM Entities WHERE ID_E = ?", (row['e2_id'],))
                    row_e2 = c.fetchone()
                    e2 = format_entity_name(row_e2['nameE']) if row_e2 else "Unknown"
                    
                    swaps_log.append({
                        tr("Swap ID"): row['ID_SR'],
                        tr("Requester Prof"): row['requester_name'],
                        tr("Requester Session"): f"{m1_name} ({tr(m1_type)}) ({e1}) {tr('at')} {format_slot_hist(row['t1'])} {tr('in')} {salles.get(row['s1_id'], tr('Unknown'))}",
                        tr("Target Prof"): row['target_name'],
                        tr("Target Session"): f"{m2_name} ({tr(m2_type)}) ({e2}) {tr('at')} {format_slot_hist(row['t2'])} {tr('in')} {salles.get(row['s2_id'], tr('Unknown'))}",
                        tr("Status"): tr(row['status'])
                    })
                df_swaps = pd.DataFrame(swaps_log)
                
                def color_status_swap(val):
                    if val in ('Approved', 'Approved_Admin', tr('Approved'), tr('Approved_Admin')): color = 'green'
                    elif val in ('Rejected', 'Cancelled', tr('Rejected'), tr('Cancelled')): color = 'red'
                    else: color = 'orange'
                    return f'color: {color}'
                    
                st.markdown(f"{tr('#### 📜 Swap Requests History Log')}")
                st.dataframe(df_swaps.style.map(color_status_swap, subset=[tr('Status')]), use_container_width=True)
            else:
                st.info(tr("No session swaps history recorded yet."))
            conn.close()

        # ----------------------------------------------------
        # SUBTAB 3: UNAVAILABILITY REQUESTS
        # ----------------------------------------------------
        with app_subtabs[2]:
            st.markdown(tr("### 🚫 Pending Unavailability Requests"))
            st.caption(tr("Review requests from professors claiming unavailability due to personal constraints."))
            u_reqs = get_pending_unavailability_requests()
            if not u_reqs:
                st.success(tr("🎉 No pending unavailability requests to review!"))
            else:
                jours_en = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
                horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
                for r in u_reqs:
                    with st.container(border=True):
                        st.markdown(f"""
                        <div style="background: rgba(214, 47, 58, 0.05); border-left: 4px solid #D62F3A; padding: 8px 12px; border-radius: 4px; margin-bottom: 12px;">
                            <strong style="color: var(--text-color); font-size: 1.05em;">{tr('🚫 Unavailability Request:')} {r['nameP']}</strong>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        day_str = jours_en[(r['t']-1)//6]
                        time_str = horaires[(r['t']-1)%6]
                        
                        st.markdown(f"**{tr('Requested Block Slot:')}** {tr(day_str)} {tr('at')} {time_str}")
                        st.markdown(f"**{tr('Reason:')}** {r['reason']}")
                        
                        col_btn1, col_btn2, _ = st.columns([1, 1, 4])
                        with col_btn1:
                            if st.button(tr("✅ Approve"), key=f"app_u_{r['id']}", type="primary", use_container_width=True):
                                approve_unavailability_request(r['id'])
                                st.success(tr("Unavailability request approved."))
                                time.sleep(1)
                                st.rerun()
                        with col_btn2:
                            if st.button(tr("❌ Reject"), key=f"rej_u_{r['id']}", type="secondary", use_container_width=True):
                                reject_unavailability_request(r['id'])
                                st.warning(tr("Unavailability request rejected."))
                                time.sleep(1)
                                st.rerun()
                                
            st.write("") # Spacer
            st.divider()

            # --- Historical Unavailability Log Table ---
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.t, u.reason, u.status, prof.nameP
                FROM UnavailabilityRequests u
                JOIN Profs prof ON u.ID_P = prof.ID_P
                ORDER BY u.id DESC
            """)
            all_unavail = c.fetchall()
            conn.close()
            
            jours_en = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
            horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
            
            if all_unavail:
                unavail_log = []
                for row in all_unavail:
                    day_str = jours_en[(row['t']-1)//6] if 1 <= row['t'] <= 36 else "Unknown"
                    time_str = horaires[(row['t']-1)%6] if 1 <= row['t'] <= 36 else "Unknown"
                    unavail_log.append({
                        tr("Request ID"): row['id'],
                        tr("Professor"): row['nameP'],
                        tr("Requested Slot"): f"{tr(day_str)} {time_str}",
                        tr("Reason"): row['reason'],
                        tr("Status"): tr(row['status'])
                    })
                df_unavail = pd.DataFrame(unavail_log)
                
                def color_status_unavail(val):
                    if val in ('Pending', tr('Pending')):
                        color = 'orange'
                    elif val in ('Approved', tr('Approved')):
                        color = 'green'
                    else:
                        color = 'red'
                    return f'color: {color}'
                    
                st.markdown(f"{tr('#### 📜 Unavailability Requests History Log')}")
                st.dataframe(df_unavail.style.map(color_status_unavail, subset=[tr('Status')]), use_container_width=True)
            else:
                st.info(tr("No unavailability requests history recorded yet."))

        # ----------------------------------------------------
        # SUBTAB 4: SYSTEM MAINTENANCE
        # ----------------------------------------------------
        with app_subtabs[3]:
            st.markdown(tr("### 🧹 Global Cleanup & History Reset"))
            st.caption(tr("Wipe all active and historical requests and unavailability settings."))
            
            req_ver = st.session_state.get('req_ver', 0)
            conf_clear_reqs = st.checkbox(tr("Confirm Deletion of ALL Requests & Indisponibilities"), key=f"conf_clear_reqs_v{req_ver}")
            if st.button(tr("Clear All Requests & History"), type="primary", disabled=not conf_clear_reqs, use_container_width=True):
                clear_all_requests()
                st.session_state['req_ver'] = req_ver + 1
                st.success(tr("All Swap Requests, Reschedule Requests, and Teacher Indisponibilities have been wiped!"))
                time.sleep(1)
                st.rerun()
        
    with tab3:
        st.markdown(tr("## 📊 AI Scheduling Core & Analytics"))
        ai_subtabs = st.tabs([
            tr("⏱️ Preference Period & Fallbacks"), 
            tr("⚙️ Optimization Weights"), 
            tr("🚀 AI Optimization Engine"), 
            tr("📈 Analytics & Quality Metrics")
        ])
        
        deadline = get_preference_deadline()
        stats = get_preference_submission_stats()
        current_time = time.time()
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as c FROM Modules WHERE ID_P IS NOT NULL")
        mods_exist = c.fetchone()['c'] > 0
        conn.close()
        
        # ----------------------------------------------------
        # SUBTAB 1: PREFERENCE PERIOD & FALLBACKS
        # ----------------------------------------------------
        with ai_subtabs[0]:
            st.markdown(tr("### ⏱️ Preference Submission Phase"))
            if mods_exist:
                c1, c2, c3 = st.columns(3)
                c1.metric(tr("Total Assigned Modules"), stats['total_modules'])
                c2.metric(tr("Preferences Submitted"), stats['submitted_modules'])
                c3.metric(tr("Pending Preferences"), stats['pending_modules'])
                
                st.divider()
                
                if not deadline:
                    st.warning(tr("⚠️ Submission period has NOT been opened yet."))
                    deadline_days = st.number_input(tr("Set Countdown Deadline (in days)"), min_value=1, max_value=30, value=3, step=1, key="start_deadline_days")
                    conf_start = st.checkbox(tr("Confirm starting the {deadline_days}-day countdown").format(deadline_days=deadline_days), key="conf_start")
                    if st.button(tr("Open Preference Period (Start {deadline_days}-day Countdown)").format(deadline_days=deadline_days), disabled=not conf_start, type="primary"):
                        set_preference_deadline(current_time + (deadline_days * 86400))
                        st.success(tr("Preference period opened for {deadline_days} days.").format(deadline_days=deadline_days))
                        time.sleep(1)
                        st.rerun()
                else:
                    if current_time < deadline:
                        rem = deadline - current_time
                        days, rem_sec = divmod(rem, 86400)
                        hours, rem_sec = divmod(rem_sec, 3600)
                        st.info(tr("⏳ Submission period is OPEN. Time remaining: {int(days)}d {int(hours)}h.").replace("{int(days)}", str(int(days))).replace("{int(hours)}", str(int(hours))))
                        
                        if stats['pending_modules'] > 0:
                            st.warning(tr("⚠️ You can override the wait if you wish to run the engine early by forcing fallback."))
                            conf_fb1 = st.checkbox(tr("Confirm Force Fallback"), key="conf_fb1")
                            if st.button(tr("Override & Force Fallback"), type="primary", disabled=not conf_fb1):
                                set_preference_deadline(current_time)
                                assigned = auto_assign_missing_preferences()
                                st.success(tr("Forced fallback for {assigned} missing modules.").format(assigned=assigned))
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.success(tr("✅ All professors have submitted their preferences!"))
                    else:
                        st.error(tr("🚨 Deadline has passed!"))
                        
                        col_fb, col_res = st.columns(2)
                        with col_fb:
                            if stats['pending_modules'] > 0:
                                st.markdown(f"##### {tr('🎲 Auto-assign Fallbacks')}")
                                conf_fb2 = st.checkbox(tr("Confirm Auto-assign Random Slots"), key="conf_fb2")
                                if st.button(tr("Override & Force Fallback (Auto-assign Random Slots)"), type="primary", disabled=not conf_fb2, use_container_width=True):
                                    assigned = auto_assign_missing_preferences()
                                    st.success(tr("Assigned fallback slots to {assigned} missing modules.").format(assigned=assigned))
                                    time.sleep(1)
                                    st.rerun()
                        with col_res:
                            st.markdown(f"##### {tr('🔄 Restart Deadline Countdown')}")
                            restart_days = st.number_input(tr("Set Countdown Deadline (in days)"), min_value=1, max_value=30, value=3, step=1, key="restart_deadline_days")
                            conf_restart = st.checkbox(tr("Confirm restarting the {restart_days}-day countdown").format(restart_days=restart_days), key="conf_restart")
                            if st.button(tr("Restart Preference Period"), type="secondary", disabled=not conf_restart, use_container_width=True):
                                set_preference_deadline(current_time + (restart_days * 86400))
                                fb_count = get_fallback_count()
                                if fb_count > 0:
                                    undo_fallback_preferences()
                                st.success(tr("Preference period restarted/extended for {restart_days} days.").format(restart_days=restart_days))
                                time.sleep(1)
                                st.rerun()
            else:
                st.info(tr("Assign modules and professors first to see preference metrics."))
                
            fb_count = get_fallback_count()
            if fb_count > 0:
                st.divider()
                st.warning(tr("⚠️ There are {fb_count} modules with auto-generated fallbacks.").format(fb_count=fb_count))
                conf_undo = st.checkbox(tr("Confirm Deleting Fallbacks"), key="conf_undo")
                if st.button(tr("Undo Override & Delete Fallbacks"), type="secondary", disabled=not conf_undo):
                    undo_fallback_preferences()
                    st.success(tr("Successfully removed all auto-generated fallbacks. Their status is Pending again."))
                    time.sleep(1)
                    st.rerun()
                    
            st.divider()
            st.markdown(tr("### 🧹 Manage Global Preferences Data"))
            conf_clear_prefs = st.checkbox(tr("Confirm Deletion of All Preferences"), key="conf_clear_prefs")
            if st.button(tr("Clear All Preferences"), type="primary", disabled=not conf_clear_prefs):
                clear_all_preferences()
                st.success(tr("All preferences have been cleared!"))
                time.sleep(1)
                st.rerun()

            st.divider()
            st.markdown(tr("### 🚫 Unavailability Requests Limits"))
            from database import get_max_unavailability_slots, set_max_unavailability_slots
            current_max = get_max_unavailability_slots()
            new_max = st.number_input(tr("Max slots a professor can request as unavailable"), min_value=1, max_value=36, value=current_max, step=1)
            if new_max != current_max:
                if st.button(tr("Update Max Unavailability Slots"), type="primary"):
                    set_max_unavailability_slots(new_max)
                    st.success(tr("Maximum unavailability slots updated successfully!"))
                    time.sleep(1)
                    st.rerun()
                    

        # ----------------------------------------------------
        # SUBTAB 2: OPTIMIZATION WEIGHTS
        # ----------------------------------------------------
        with ai_subtabs[1]:
            st.markdown(f"### {tr('⚙️ Optimization Weights')}")
            st.caption(tr("Configure how the AI evaluates and resolves clashes and gaps. The sliders represent the relative importance of each constraint."))
            
            import json
            config_path = "config.json"
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    try:
                        config_data = json.load(f)
                    except:
                        config_data = {}
            else:
                config_data = {}
                
            weights = config_data.get("weights", {"prof_prefs": 1.0, "student_gaps": 1.0, "prof_gaps": 1.0, "student_daily_limits": 1.0, "prof_daily_limits": 1.0, "prof_working_days": 1.0, "student_working_days": 1.0, "student_format_mix": 1.0})
            
            with st.container(border=True):
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, rgba(214, 47, 58, 0.05), rgba(214, 47, 58, 0.01));
                    padding: 8px 12px;
                    border-left: 4px solid #D62F3A;
                    border-right: 1px solid rgba(214, 47, 58, 0.08);
                    border-top: 1px solid rgba(214, 47, 58, 0.08);
                    border-bottom: 1px solid rgba(214, 47, 58, 0.08);
                    border-radius: 4px;
                    margin-bottom: 16px;
                ">
                    <span style="color: var(--text-color); font-weight: bold; font-size: 1.05em; font-family: 'Inter', sans-serif;">{tr('Academic & Student Quality')}</span>
                </div>
                """, unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1:
                    w_stud = st.slider(tr("Weight: Minimize Student Gaps"), min_value=0.0, max_value=5.0, value=float(weights.get("student_gaps", 1.0)), step=0.1, help=tr("Higher weight means the AI will strictly avoid 'holes' in student timetables."))
                with c2:
                    w_stud_limits = st.slider(tr("Weight: Student Daily Limits"), min_value=0.0, max_value=5.0, value=float(weights.get("student_daily_limits", 1.0)), step=0.1, help=tr("Higher weight penalizes days with exactly 1 session or more than 4 sessions for students."))
                with c3:
                    w_stud_mix = st.slider(tr("Weight: Balanced Session Variety"), min_value=0.0, max_value=5.0, value=float(weights.get("student_format_mix", 1.0)), step=0.1, help=tr("Higher weight penalizes days that consist entirely of identical teaching formats (e.g., all Cours or all TDs)."))
                
            st.write("") # Spacer

            with st.container(border=True):
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, rgba(214, 47, 58, 0.05), rgba(214, 47, 58, 0.01));
                    padding: 8px 12px;
                    border-left: 4px solid #D62F3A;
                    border-right: 1px solid rgba(214, 47, 58, 0.08);
                    border-top: 1px solid rgba(214, 47, 58, 0.08);
                    border-bottom: 1px solid rgba(214, 47, 58, 0.08);
                    border-radius: 4px;
                    margin-bottom: 16px;
                ">
                    <span style="color: var(--text-color); font-weight: bold; font-size: 1.05em; font-family: 'Inter', sans-serif;">{tr('Professor Quality & Preferences')}</span>
                </div>
                """, unsafe_allow_html=True)
                c4, c5, c6 = st.columns(3)
                with c4:
                    w_prof = st.slider(tr("Weight: Professor Preferences"), min_value=0.0, max_value=5.0, value=float(weights.get("prof_prefs", 1.0)), step=0.1, help=tr("Higher weight means the AI will prioritize giving professors their preferred timeslots."))
                with c5:
                    w_prof_gaps = st.slider(tr("Weight: Minimize Professor Gaps"), min_value=0.0, max_value=5.0, value=float(weights.get("prof_gaps", 1.0)), step=0.1, help=tr("Higher weight means the AI will strictly avoid 'holes' in professor timetables."))
                with c6:
                    w_prof_limits = st.slider(tr("Weight: Professor Daily Limits"), min_value=0.0, max_value=5.0, value=float(weights.get("prof_daily_limits", 1.0)), step=0.1, help=tr("Higher weight penalizes days with exactly 1 session or more than 4 sessions for professors."))
                
            st.write("") # Spacer

            with st.container(border=True):
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, rgba(214, 47, 58, 0.05), rgba(214, 47, 58, 0.01));
                    padding: 8px 12px;
                    border-left: 4px solid #D62F3A;
                    border-right: 1px solid rgba(214, 47, 58, 0.08);
                    border-top: 1px solid rgba(214, 47, 58, 0.08);
                    border-bottom: 1px solid rgba(214, 47, 58, 0.08);
                    border-radius: 4px;
                    margin-bottom: 16px;
                ">
                    <span style="color: var(--text-color); font-weight: bold; font-size: 1.05em; font-family: 'Inter', sans-serif;">{tr('Commute Minimization')}</span>
                </div>
                """, unsafe_allow_html=True)
                c7, c8 = st.columns(2)
                with c7:
                    w_stud_days = st.slider(tr("Weight: Min Student Working Days"), min_value=0.0, max_value=5.0, value=float(weights.get("student_working_days", 1.0)), step=0.1, help=tr("Higher weight heavily penalizes the total number of days students have to attend classes."))
                with c8:
                    w_prof_days = st.slider(tr("Weight: Min Professor Working Days"), min_value=0.0, max_value=5.0, value=float(weights.get("prof_working_days", 1.0)), step=0.1, help=tr("Higher weight heavily penalizes the total number of days a professor has to commute to campus."))
                
            if w_prof != weights.get("prof_prefs", 1.0) or w_stud != weights.get("student_gaps", 1.0) or w_prof_gaps != weights.get("prof_gaps", 1.0) or w_stud_limits != weights.get("student_daily_limits", 1.0) or w_prof_limits != weights.get("prof_daily_limits", 1.0) or w_prof_days != weights.get("prof_working_days", 1.0) or w_stud_days != weights.get("student_working_days", 1.0) or w_stud_mix != weights.get("student_format_mix", 1.0):
                config_data["weights"] = {"prof_prefs": w_prof, "student_gaps": w_stud, "prof_gaps": w_prof_gaps, "student_daily_limits": w_stud_limits, "prof_daily_limits": w_prof_limits, "prof_working_days": w_prof_days, "student_working_days": w_stud_days, "student_format_mix": w_stud_mix}
                with open(config_path, "w") as f:
                    json.dump(config_data, f, indent=4)
                st.success(tr("Weights updated! The next run will use these new weights."))

        # ----------------------------------------------------
        # SUBTAB 3: AI OPTIMIZATION ENGINE
        # ----------------------------------------------------
        with ai_subtabs[2]:
            st.markdown(f"### {tr('🚀 AI Optimization Engine')}")
            
            can_run = True
            if stats['pending_modules'] > 0:
                if not deadline or current_time < deadline:
                    st.error(tr("⛔ Cannot start optimization: Preferences are pending and deadline has not passed. Wait or use Override under the Preferences tab."))
                    can_run = False
            
            if st.button(tr("Build Schedule"), type="primary", disabled=not can_run, use_container_width=True):
                start_time = time.time()
                if stats['pending_modules'] > 0 and deadline and current_time >= deadline:
                    auto_assign_missing_preferences()
                    
                data = load_data_from_db()
                if not data['seances']:
                    st.error(tr("No data found for scheduling. Ensure all entities, modules, and professors are inputted."))
                else:
                    cours_modules = sum(1 for s in data['seances'] if int(s['typeM']) == 1)
                    total_modules = len(data['seances'])
                    amphis_count = len(data.get('salles', {}).get(1, []))
                    total_rooms = len(data.get('salles', {}).get(0, []))
                    
                    if cours_modules > amphis_count * 36:
                        st.error(tr("⛔ Impossible to build schedule: Not enough Amphis. You have {cours_modules} Cours sessions but only {amphis_count} Amphis ({cap} slots). Please add more Amphis.").format(cours_modules=cours_modules, amphis_count=amphis_count, cap=amphis_count*36))
                    elif total_modules > total_rooms * 36:
                        st.error(tr("⛔ Impossible to build schedule: Not enough total rooms. You have {total_modules} sessions but only {total_rooms} rooms ({cap} slots). Please add more rooms.").format(total_modules=total_modules, total_rooms=total_rooms, cap=total_rooms*36))
                    else:
                        progress_bar = st.progress(0, text=tr("Generating timetable structure, please wait..."))
                        
                        planning_greedy = executer_greedy_priorite(data)
                        progress_bar.progress(50, text=tr("Optimizing timetable quality, please wait..."))
                        
                        best_planning = optimize_with_sa(data, planning_greedy['planning_final'], num_workers=4, iters_per_temp=100)
                        
                        progress_bar.progress(100, text=tr("Optimization Complete!"))
                        save_planning_to_db({'planning_final': best_planning})
                        elapsed = time.time() - start_time
                        st.success(tr("Timetable generated and saved successfully in {duration:.1f} seconds!").format(duration=elapsed))
                        time.sleep(2)
                        st.rerun()

        # ----------------------------------------------------
        # SUBTAB 4: ANALYTICS & QUALITY METRICS
        # ----------------------------------------------------
        with ai_subtabs[3]:
            st.markdown(f"### {tr('📈 Analytics & Quality Metrics')}")
            
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT score FROM Planning")
            scores = c.fetchall()
            conn.close()
            
            if scores:
                total = len(scores)
                perfect = sum(1 for s in scores if s['score'] == 0)
                high = sum(1 for s in scores if s['score'] == 10)
                normal = sum(1 for s in scores if s['score'] == 20)
                unpreferred = sum(1 for s in scores if s['score'] >= 100)
                score_percent = (perfect / total) * 100 if total > 0 else 0
                
                m_total, m_perf, m_high, m_norm, m_def = st.columns(5)
                m_total.metric(tr("Total Assigned Sessions"), total)
                m_perf.metric(tr("Perfect"), perfect)
                m_high.metric(tr("High"), high)
                m_norm.metric(tr("Normal"), normal)
                m_def.metric(tr("Default / Clash"), unpreferred)
                high_percent = (high / total) * 100 if total > 0 else 0
                normal_percent = (normal / total) * 100 if total > 0 else 0
                
                _, c_chart, _ = st.columns([1, 2, 1])
                
                with c_chart:
                    labels = [tr("Perfect"), tr("High"), tr("Normal"), tr("Default / Clash")]
                    values = [perfect, high, normal, unpreferred]
                    colors = ['#B9F3CD', '#FFF3B0', '#A2D2FF', '#FFADAD']
                    
                    fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.5, marker=dict(colors=colors), sort=False)])
                    fig_pie.update_layout(
                        title={'text': tr("Score Distribution"), 'font': {'size': 18, 'color': 'gray'}, 'x': 0.2},
                        paper_bgcolor="rgba(0,0,0,0)", 
                        font={'color': "gray"}, 
                        margin=dict(t=50, b=30, l=10, r=10),
                        showlegend=True
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                

                
                st.divider()
                
                # --- Per-section quality breakdown ---
                with st.expander(tr("📋 Per-Section Quality Breakdown"), expanded=False):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        SELECT p.score, 
                               COALESCE(parent.specialite, e.specialite) AS specialite, 
                               COALESCE(parent.nameE, e.nameE) AS section_name
                        FROM Planning p
                        JOIN Entities e ON p.ID_E = e.ID_E
                        LEFT JOIN Entities parent ON e.sectionID = parent.ID_E AND e.typeE = 0
                        ORDER BY specialite, section_name
                    """)
                    sec_rows = c.fetchall()
                    conn.close()
                    
                    if sec_rows:
                        from collections import defaultdict
                        sec_stats = defaultdict(lambda: {"total": 0, "perfect": 0, "high": 0, "normal": 0, "clash": 0, "specialite": ""})
                        for row in sec_rows:
                            key = row['section_name']
                            sec_stats[key]["specialite"] = row['specialite']
                            sec_stats[key]["total"] += 1
                            if row['score'] == 0:
                                sec_stats[key]["perfect"] += 1
                            elif row['score'] == 10:
                                sec_stats[key]["high"] += 1
                            elif row['score'] == 20:
                                sec_stats[key]["normal"] += 1
                            elif row['score'] >= 100:
                                sec_stats[key]["clash"] += 1
                        
                        breakdown_data = []
                        for sec_name, stats in sec_stats.items():
                            t = stats["total"]
                            pct = round((stats["perfect"] / t) * 100, 1) if t > 0 else 0.0
                            display_name = sec_name.split(" - ")[-1] if " - " in sec_name else sec_name
                            breakdown_data.append({
                                tr("Specialty"): stats["specialite"],
                                tr("Section"): display_name,
                                tr("Total"): t,
                                tr("Perfect"): stats["perfect"],
                                tr("High"): stats["high"],
                                tr("Normal"): stats["normal"],
                                tr("Default / Clash"): stats["clash"],
                                tr("% Perfect"): pct,
                            })
                        
                        breakdown_df = pd.DataFrame(breakdown_data)
                        st.dataframe(
                            breakdown_df,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                tr("% Perfect"): st.column_config.ProgressColumn(
                                    tr("% Perfect"),
                                    min_value=0,
                                    max_value=100,
                                    format="%.1f%%",
                                ),
                            }
                        )
                    else:
                        st.info(tr("No schedule generated yet. Please run the AI Optimization Pipeline."))
                
                # --- Per-professor quality breakdown ---
                with st.expander(tr("📋 Per-Professor Quality Breakdown"), expanded=False):
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("""
                        SELECT p.score, pr.nameP, pr.prof, pr.specialite
                        FROM Planning p
                        JOIN Profs pr ON p.ID_P = pr.ID_P
                        ORDER BY pr.specialite, pr.nameP
                    """)
                    prof_rows = c.fetchall()
                    conn.close()
                    
                    if prof_rows:
                        from collections import defaultdict
                        prof_stats = defaultdict(lambda: {"total": 0, "perfect": 0, "high": 0, "normal": 0, "clash": 0, "prof": 0, "specialite": ""})
                        for row in prof_rows:
                            key = row['nameP']
                            prof_stats[key]["specialite"] = row['specialite']
                            prof_stats[key]["prof"] = row['prof']
                            prof_stats[key]["total"] += 1
                            if row['score'] == 0:
                                prof_stats[key]["perfect"] += 1
                            elif row['score'] == 10:
                                prof_stats[key]["high"] += 1
                            elif row['score'] == 20:
                                prof_stats[key]["normal"] += 1
                            elif row['score'] >= 100:
                                prof_stats[key]["clash"] += 1
                                
                        breakdown_data_p = []
                        for prof_name, stats in prof_stats.items():
                            t = stats["total"]
                            pct = round((stats["perfect"] / t) * 100, 1) if t > 0 else 0.0
                            is_prof_str = "Prof" if stats["prof"] == 1 else "/"
                            breakdown_data_p.append({
                                tr("Department"): stats["specialite"],
                                tr("Name"): prof_name,
                                tr("Grade"): is_prof_str,
                                tr("Total"): t,
                                tr("Perfect"): stats["perfect"],
                                tr("High"): stats["high"],
                                tr("Normal"): stats["normal"],
                                tr("Default / Clash"): stats["clash"],
                                tr("% Perfect"): pct,
                            })
                            
                        breakdown_df_p = pd.DataFrame(breakdown_data_p)
                        st.dataframe(
                            breakdown_df_p,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                tr("% Perfect"): st.column_config.ProgressColumn(
                                    tr("% Perfect"),
                                    min_value=0,
                                    max_value=100,
                                    format="%.1f%%",
                                ),
                            }
                        )
                    else:
                        st.info(tr("No schedule generated yet. Please run the AI Optimization Pipeline."))
                        
                st.divider()
                st.markdown(f"{tr('#### AI Generation Constraint Metrics')}")
                
                data = load_data_from_db()
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT ID_P, ID_E, ID_M, t FROM Planning")
                planning_records = c.fetchall()
                conn.close()
                
                student_gaps = 0
                prof_gaps = 0
                student_overloaded_days = 0
                prof_overloaded_days = 0
                student_underloaded_days = 0
                prof_underloaded_days = 0
                student_format_mix_violations = 0
                
                module_types = {s['ID_M']: s['typeM'] for s in data.get('seances', [])}
                
                group_slots = {}
                if 'hierarchie' in data:
                    for sec, groups in data['hierarchie'].items():
                        for g in groups:
                            group_slots[g] = [[] for _ in range(6)]
                
                for s in planning_records:
                    e_id = s['ID_E']
                    day = (s['t'] - 1) // 6
                    if 0 <= day < 6:
                        if e_id in group_slots:
                            group_slots[e_id][day].append((s['t'], s['ID_M']))
                        elif 'hierarchie' in data and e_id in data['hierarchie']:
                            for g in data['hierarchie'][e_id]:
                                if g in group_slots:
                                    group_slots[g][day].append((s['t'], s['ID_M']))
                                    
                for days in group_slots.values():
                    for slots_info in days:
                        num_sessions = len(slots_info)
                        if num_sessions > 1:
                            times = [info[0] for info in slots_info]
                            span = max(times) - min(times) + 1
                            student_gaps += (span - num_sessions)
                            
                            types_in_day = set(module_types.get(info[1]) for info in slots_info)
                            if len(types_in_day) == 1:
                                student_format_mix_violations += 1
                                
                        if num_sessions == 1:
                            student_underloaded_days += 1
                        elif num_sessions > 4:
                            student_overloaded_days += 1
                            
                prof_slots = {}
                for s in planning_records:
                    p_id = s['ID_P']
                    day = (s['t'] - 1) // 6
                    if 0 <= day < 6:
                        if p_id not in prof_slots:
                            prof_slots[p_id] = [[] for _ in range(6)]
                        prof_slots[p_id][day].append(s['t'])
                        
                for days in prof_slots.values():
                    for slots in days:
                        num_sessions = len(slots)
                        if num_sessions > 1:
                            span = max(slots) - min(slots) + 1
                            prof_gaps += (span - num_sessions)
                            
                        if num_sessions == 1:
                            prof_underloaded_days += 1
                        elif num_sessions > 4:
                            prof_overloaded_days += 1
                            
                # --- Creative Radar Chart ---
                categories = [
                    tr('Minimize<br>Student Gaps'), tr('Minimize<br>Professor Gaps'), 
                    tr('Student<br>Daily Limits'), tr('Professor<br>Daily Limits'), 
                    tr('Min Student<br>Working Days'), tr('Min Professor<br>Working Days'), 
                    tr('Balanced Session<br>Variety')
                ]
                values = [
                    student_gaps, prof_gaps, 
                    student_overloaded_days, prof_overloaded_days, 
                    student_underloaded_days, prof_underloaded_days, 
                    student_format_mix_violations
                ]
                
                val_plot = values + [values[0]]
                cat_plot = categories + [categories[0]]
                
                c_radar, c_cards = st.columns([1.2, 1])
                
                with c_radar:
                    fig_radar = go.Figure()
                    fig_radar.add_trace(go.Scatterpolar(
                        r=val_plot,
                        theta=cat_plot,
                        fill='toself',
                        fillcolor='rgba(214, 47, 58, 0.2)',
                        line=dict(color='#D62F3A', width=2),
                        marker=dict(color='#D62F3A', size=8)
                    ))
                    
                    fig_radar.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, showticklabels=True, color="gray", gridcolor="rgba(128,128,128,0.2)"),
                            angularaxis=dict(color="gray", tickfont=dict(size=11, weight="bold"), gridcolor="rgba(128,128,128,0.2)")
                        ),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                        margin=dict(t=50, b=50, l=70, r=70)
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)
                    
                with c_cards:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"""
                    <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #D62F3A; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Student Gaps')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{student_gaps} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('holes')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #D62F3A; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Professor Gaps')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{prof_gaps} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('holes')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #ff9800; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Student Daily limits')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{student_overloaded_days} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('days >4')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #ff9800; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Prof Daily Limits')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{prof_overloaded_days} <span style="font-size:14px; color:#666; font-weight:normal;">{tr('days >4')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #00bcd4; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Student Workdays')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{student_underloaded_days} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('days')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; border-left: 4px solid #00bcd4; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Professor Workdays')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{prof_underloaded_days} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('days')}</span></div>
                        </div>
                        <div style="background: linear-gradient(145deg, #fdfdfd, #f0f0f0); padding: 12px; border-radius: 8px; grid-column: span 2; border-left: 4px solid #9c27b0; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                            <div style="color: #666; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; line-height: 1.2;">{tr('Balanced Session Variety')}</div>
                            <div style="color: #1a1a1a; font-size: 22px; font-weight: 700; margin-top: 3px;">{student_format_mix_violations} <span style="font-size:11px; color:#666; font-weight:normal;">{tr('monotonous days')}</span></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info(tr("No schedule generated yet. Please run the AI Optimization Pipeline."))

    with tab4:
        show_timetables_view()
