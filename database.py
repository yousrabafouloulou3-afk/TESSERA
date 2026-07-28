import sqlite3
import pandas as pd
import os

DB_PATH = "timetabling.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL, -- 'admin', 'teacher', 'student'
            linked_id INTEGER, -- ID_P for teachers, ID_E for students (section or group), null for admin
            linked_level TEXT -- For students who sign up before data is inserted
        )
    ''')
    
    try:
        c.execute("ALTER TABLE Users ADD COLUMN linked_level TEXT")
    except sqlite3.OperationalError:
        pass
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Entities (
            ID_E INTEGER PRIMARY KEY,
            typeE INTEGER,
            sectionID INTEGER,
            nameE TEXT,
            specialite TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Profs (
            ID_P INTEGER PRIMARY KEY,
            nameP TEXT,
            prof INTEGER,
            specialite TEXT,
            matricule TEXT UNIQUE
        )
    ''')
    
    # Ensure columns exist for users updating from older schemas
    try:
        c.execute("ALTER TABLE Profs ADD COLUMN specialite TEXT")
    except sqlite3.OperationalError:
        pass
        
    try:
        c.execute("ALTER TABLE Profs ADD COLUMN matricule TEXT UNIQUE")
    except sqlite3.OperationalError:
        try:
            # SQLite workaround since ADD COLUMN UNIQUE is restricted
            c.execute("ALTER TABLE Profs ADD COLUMN matricule TEXT")
        except sqlite3.OperationalError:
            pass
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Modules (
            ID_M INTEGER PRIMARY KEY,
            typeM INTEGER,
            nameM TEXT,
            ID_P INTEGER,
            ID_E INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Salles (
            ID_S INTEGER PRIMARY KEY,
            typeS INTEGER,
            nameS TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Indisponibilites (
            ID_P INTEGER,
            t INTEGER,
            PRIMARY KEY (ID_P, t)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Preferences (
            ID_P INTEGER,
            ID_M INTEGER,
            t INTEGER,
            score INTEGER,
            is_auto INTEGER DEFAULT 0,
            PRIMARY KEY (ID_P, ID_M, t)
        )
    ''')
    
    try:
        c.execute("ALTER TABLE Preferences ADD COLUMN is_auto INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    
    # Store the actual generated plan
    c.execute('''
        CREATE TABLE IF NOT EXISTS Planning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_P INTEGER,
            ID_E INTEGER,
            ID_S INTEGER,
            ID_M INTEGER,
            t INTEGER,
            score INTEGER
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS SystemSettings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            form_key TEXT,
            draft_data TEXT,
            UNIQUE(username, form_key)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS RescheduleRequests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            ID_P INTEGER,
            new_t INTEGER,
            new_s_id INTEGER,
            status TEXT DEFAULT 'Pending_Delegate'
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS SwapRequests (
            ID_SR INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_P_Requester INTEGER,
            ID_Session_Requester INTEGER,
            ID_P_Target INTEGER,
            ID_Session_Target INTEGER,
            suggested_room_id INTEGER,
            status TEXT DEFAULT 'Pending_Target',
            approved_by_delegate1 INTEGER DEFAULT 0,
            approved_by_delegate2 INTEGER DEFAULT 0
        )
    ''')
    
    try:
        c.execute("ALTER TABLE SwapRequests ADD COLUMN approved_by_delegate1 INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE SwapRequests ADD COLUMN approved_by_delegate2 INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS UnavailabilityRequests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ID_P INTEGER,
            t INTEGER,
            reason TEXT,
            status TEXT DEFAULT 'Pending' -- 'Pending', 'Approved', 'Rejected'
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS Delegates (
            section_id INTEGER PRIMARY KEY,
            matricule TEXT UNIQUE,
            FOREIGN KEY(section_id) REFERENCES Entities(ID_E)
        )
    ''')
    
    conn.commit()
    conn.close()



def upload_csvs_to_db(fichiers):
    """Parses Excel like `charger_donnees` but directly shunts to DB, plus creates user accounts."""
    for s in fichiers: fichiers[s].columns = fichiers[s].columns.str.strip()

    def clean_int(val):
        if pd.isna(val): return 0
        try: return int(float(val))
        except: return 0

    conn = get_db_connection()
    c = conn.cursor()
    
    # Clear old data purely for re-upload functionality
    c.execute("DELETE FROM Entities")
    c.execute("DELETE FROM Profs")
    c.execute("DELETE FROM Modules")
    c.execute("DELETE FROM Salles")
    c.execute("DELETE FROM Indisponibilites")
    # c.execute("DELETE FROM Preferences") # Preferences might be kept if manual
    c.execute("DELETE FROM Planning")
    
    # Also delete dynamically generated teachers and students
    c.execute("DELETE FROM Users WHERE role IN ('teacher', 'student')")
    
    # Populate Profs & Teacher users
    if 'Profs' in fichiers:
        for _, row in fichiers['Profs'].dropna(subset=['ID_P']).iterrows():
            id_p = clean_int(row['ID_P'])
            c.execute("INSERT INTO Profs (ID_P, nameP, prof) VALUES (?, ?, ?)",
                      (id_p, str(row['nameP']), clean_int(row['prof'])))
            # Create user for teacher
            c.execute("INSERT INTO Users (username, password, role, linked_id) VALUES (?, ?, 'teacher', ?)",
                      (f"teacher_{id_p}", "teacher123", id_p))

    # Populate Entities & Student users
    if 'Entites' in fichiers:
        for _, row in fichiers['Entites'].dropna(subset=['ID_E']).iterrows():
            id_e = clean_int(row['ID_E'])
            c.execute("INSERT INTO Entities (ID_E, typeE, sectionID, nameE, specialite) VALUES (?, ?, ?, ?, ?)",
                      (id_e, clean_int(row.get('typeE')), clean_int(row.get('sectionID')), str(row.get('nameE', '')), str(row.get('specialite', ''))))
            # Create user for student group/section
            c.execute("INSERT INTO Users (username, password, role, linked_id) VALUES (?, ?, 'student', ?)",
                      (f"student_{id_e}", "student123", id_e))

    # Populate Modules
    if 'Modules' in fichiers:
        for _, row in fichiers['Modules'].dropna(how='all').iterrows():
            if pd.notna(row.get('ID_M')):
                c.execute("INSERT INTO Modules (ID_M, typeM, nameM, ID_P, ID_E) VALUES (?, ?, ?, ?, ?)",
                          (clean_int(row['ID_M']), clean_int(row['typeM']), str(row['nameM']), clean_int(row['ID_P']), clean_int(row['ID_E'])))

    # Populate Salles
    if 'Salles' in fichiers:
        for _, row in fichiers['Salles'].dropna(subset=['ID_S']).iterrows():
            c.execute("INSERT INTO Salles (ID_S, typeS, nameS) VALUES (?, ?, ?)",
                      (clean_int(row['ID_S']), clean_int(row['typeS']), str(row['nameS'])))

    # Populate AP (Indisponibilites)
    if 'AP' in fichiers:
        for _, row in fichiers['AP'].dropna(subset=['ID_P', 't']).iterrows():
            c.execute("INSERT INTO Indisponibilites (ID_P, t) VALUES (?, ?)",
                      (clean_int(row['ID_P']), clean_int(row['t'])))
                      
    # Optionally load Preferences if they exist in file (Teachers will also be able to overwrite this later)
    if 'Preferences' in fichiers:
        for _, row in fichiers['Preferences'].iterrows():
             c.execute("INSERT OR REPLACE INTO Preferences (ID_P, ID_M, t, score) VALUES (?, ?, ?, ?)",
                      (clean_int(row['ID_P']), clean_int(row['ID_M']), clean_int(row['t']), clean_int(row['score'])))

    conn.commit()
    conn.close()
    return True

def save_planning_to_db(planning):
    """Saves final planning list of dicts to the db, keeping the session ID stable (id = ID_M)."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Planning")
    for session in planning['planning_final']:
        c.execute("""
            INSERT INTO Planning (id, ID_P, ID_E, ID_S, ID_M, t, score) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session['ID_M'], session['ID_P'], session['ID_E'], session['ID_S'], session['ID_M'], session['t'], session['score']))
    conn.commit()
    conn.close()

def clear_table_students():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Entities")
    c.execute("DELETE FROM Delegates")
    c.execute("DELETE FROM Users WHERE role IN ('student', 'delegate')")
    conn.commit()
    conn.close()

def clear_table_professors():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Profs")
    c.execute("DELETE FROM Users WHERE role = 'teacher'")
    conn.commit()
    conn.close()

def clear_table_rooms():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Salles")
    conn.commit()
    conn.close()

def clear_table_modules():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Modules")
    conn.commit()
    conn.close()

def add_single_professor(name, specialite, is_prof, matricule):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_P FROM Profs WHERE nameP = ? AND specialite = ?", (name, specialite))
    row = c.fetchone()
    if row:
        conn.close()
        return False, "Professor already exists in this specialty."
        
    c.execute("INSERT INTO Profs (nameP, prof, specialite, matricule) VALUES (?, ?, ?, ?)", (name, is_prof, specialite, matricule))
    prof_id = c.lastrowid
    c.execute("INSERT OR IGNORE INTO Users (username, password, role, linked_id) VALUES (?, ?, 'teacher', ?)", (f"teacher_{prof_id}", "teacher123", prof_id))
    conn.commit()
    conn.close()
    return True, "Professor added successfully."
def delete_single_professor(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    # Get professor details to clean up drafts
    c.execute("SELECT nameP, specialite FROM Profs WHERE ID_P = ?", (id_p,))
    prof = c.fetchone()
    if prof:
        prof_name = prof['nameP']
        spec = prof['specialite']
        
        # Delete professor
        c.execute("DELETE FROM Profs WHERE ID_P = ?", (id_p,))
        c.execute("DELETE FROM Users WHERE role = 'teacher' AND linked_id = ?", (id_p,))
        c.execute("UPDATE Modules SET ID_P = NULL WHERE ID_P = ?", (id_p,))
        c.execute("UPDATE Planning SET ID_P = NULL WHERE ID_P = ?", (id_p,))
        c.execute("DELETE FROM Preferences WHERE ID_P = ?", (id_p,))
        c.execute("DELETE FROM Indisponibilites WHERE ID_P = ?", (id_p,))
        c.execute("DELETE FROM SwapRequests WHERE ID_P_Requester = ? OR ID_P_Target = ?", (id_p, id_p))
        c.execute("DELETE FROM RescheduleRequests WHERE ID_P = ?", (id_p,))
        c.execute("DELETE FROM UnavailabilityRequests WHERE ID_P = ?", (id_p,))
        
        # Clean up drafts
        c.execute("SELECT username, draft_data FROM Drafts WHERE form_key = 'prof_form'")
        rows = c.fetchall()
        import json
        for row in rows:
            username = row['username']
            try:
                draft = json.loads(row['draft_data'])
            except:
                continue
            
            num_prof_draft_key = f"num_profs_{spec}"
            if num_prof_draft_key in draft:
                num_profs = draft[num_prof_draft_key]
                profs_list = []
                for i in range(num_profs):
                    p_name = draft.get(f"pname_{spec}_{i}", "")
                    p_mat = draft.get(f"mat_{spec}_{i}", "")
                    p_isprof = draft.get(f"isprof_{spec}_{i}", False)
                    profs_list.append((p_name, p_mat, p_isprof))
                
                # Filter out the deleted professor
                new_profs_list = [p for p in profs_list if p[0] != prof_name]
                if len(new_profs_list) < len(profs_list):
                    draft[num_prof_draft_key] = len(new_profs_list)
                    # delete old keys for this spec
                    for i in range(num_profs):
                        draft.pop(f"pname_{spec}_{i}", None)
                        draft.pop(f"mat_{spec}_{i}", None)
                        draft.pop(f"isprof_{spec}_{i}", None)
                    # write back new keys
                    for i, (p_name, p_mat, p_isprof) in enumerate(new_profs_list):
                        draft[f"pname_{spec}_{i}"] = p_name
                        draft[f"mat_{spec}_{i}"] = p_mat
                        draft[f"isprof_{spec}_{i}"] = p_isprof
                    
                    c.execute("UPDATE Drafts SET draft_data = ? WHERE username = ? AND form_key = 'prof_form'", 
                              (json.dumps(draft), username))
        conn.commit()
    conn.close()
    return True

def delete_single_room(id_s):
    conn = get_db_connection()
    c = conn.cursor()
    # Get room details to clean up drafts
    c.execute("SELECT nameS, typeS FROM Salles WHERE ID_S = ?", (id_s,))
    room = c.fetchone()
    if room:
        room_name = room['nameS']
        room_type = room['typeS']
        
        # Delete room
        c.execute("DELETE FROM Salles WHERE ID_S = ?", (id_s,))
        c.execute("UPDATE Planning SET ID_S = NULL WHERE ID_S = ?", (id_s,))
        
        # Clean up drafts
        c.execute("SELECT username, draft_data FROM Drafts WHERE form_key = 'room_form'")
        rows = c.fetchall()
        import json
        for row in rows:
            username = row['username']
            try:
                draft = json.loads(row['draft_data'])
            except:
                continue
            
            modified = False
            # Check amphis
            if room_type == 1:
                amphis = []
                num_amphis = draft.get('num_amphis', 0)
                for i in range(num_amphis):
                    name = draft.get(f'amphi_{i}', '')
                    if name != room_name:
                        amphis.append(name)
                    else:
                        modified = True
                if modified:
                    draft['num_amphis'] = len(amphis)
                    # delete old keys
                    for k in list(draft.keys()):
                        if k.startswith('amphi_'):
                            del draft[k]
                    # populate new keys
                    for i, name in enumerate(amphis):
                        draft[f'amphi_{i}'] = name
            # Check tds
            elif room_type == 0:
                tds = []
                num_td = draft.get('num_td', 0)
                for i in range(num_td):
                    name = draft.get(f'td_{i}', '')
                    if name != room_name:
                        tds.append(name)
                    else:
                        modified = True
                if modified:
                    draft['num_td'] = len(tds)
                    # delete old keys
                    for k in list(draft.keys()):
                        if k.startswith('td_'):
                            del draft[k]
                    # populate new keys
                    for i, name in enumerate(tds):
                        draft[f'td_{i}'] = name
                        
            if modified:
                c.execute("UPDATE Drafts SET draft_data = ? WHERE username = ? AND form_key = 'room_form'", 
                          (json.dumps(draft), username))
        conn.commit()
    conn.close()
    return True

def add_single_room(name, type_s):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_S FROM Salles WHERE nameS = ?", (name,))
    if c.fetchone():
        conn.close()
        return False, "Room already exists."
    c.execute("INSERT INTO Salles (typeS, nameS) VALUES (?, ?)", (type_s, name))
    conn.commit()
    conn.close()
    return True, "Room added successfully."

def add_single_module(name, type_m, id_p, id_e):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO Modules (typeM, nameM, ID_P, ID_E) VALUES (?, ?, ?, ?)", (type_m, name, id_p, id_e))
    conn.commit()
    conn.close()
    return True

def delete_single_module(id_m):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Modules WHERE ID_M = ?", (id_m,))
    c.execute("DELETE FROM Preferences WHERE ID_M = ?", (id_m,))
    c.execute("DELETE FROM Planning WHERE ID_M = ?", (id_m,))
    conn.commit()
    conn.close()
    return True

def clear_teacher_preferences(teacher_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Preferences WHERE ID_P = ?", (teacher_id,))
    conn.commit()
    conn.close()

def clear_all_preferences():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Preferences")
    c.execute("DELETE FROM SystemSettings WHERE key='preference_deadline'")
    conn.commit()
    conn.close()


def set_preference_deadline(timestamp):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO SystemSettings (key, value) VALUES ('preference_deadline', ?)", (str(timestamp),))
    conn.commit()
    conn.close()

def get_preference_deadline():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM SystemSettings WHERE key='preference_deadline'")
    row = c.fetchone()
    conn.close()
    if row:
        return float(row['value'])
    return None

def set_max_unavailability_slots(max_slots):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM SystemSettings WHERE key='max_unavailability_slots'")
    c.execute("INSERT OR REPLACE INTO SystemSettings (key, value) VALUES ('max_unavailability_slots', ?)", (str(max_slots),))
    conn.commit()
    conn.close()

def get_max_unavailability_slots():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT value FROM SystemSettings WHERE key='max_unavailability_slots'")
    row = c.fetchone()
    conn.close()
    if row:
        return int(row['value'])
    return 6  # Default is 6 slots (1 day)

def get_preference_submission_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT ID_M) as total_modules FROM Modules WHERE ID_P IS NOT NULL")
    row_tot = c.fetchone()
    total_mod = row_tot['total_modules'] if row_tot else 0
    
    c.execute("SELECT COUNT(DISTINCT p.ID_M) as submitted_modules FROM Preferences p JOIN Modules m ON p.ID_M = m.ID_M WHERE m.ID_P IS NOT NULL")
    row_sub = c.fetchone()
    sub_mod = row_sub['submitted_modules'] if row_sub else 0
    conn.close()
    
    return {
        "total_modules": total_mod or 0,
        "submitted_modules": sub_mod or 0,
        "pending_modules": max(0, (total_mod or 0) - (sub_mod or 0))
    }

def auto_assign_missing_preferences():
    import random
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get all module-professor pairs
    c.execute("SELECT ID_M, ID_P FROM Modules WHERE ID_P IS NOT NULL")
    all_pairs = c.fetchall()
    
    # Get modules that already have preferences
    c.execute("SELECT DISTINCT ID_M FROM Preferences")
    existing_modules = {str(r['ID_M']) for r in c.fetchall()}
    
    assigned_count = 0
    for row in all_pairs:
        mod_key = str(row['ID_M'])
        if mod_key not in existing_modules:
            slots = random.sample(range(1, 37), 3)
            # Insert 3 pseudo-preferences
            scores = [0, 10, 20]
            for t, score in zip(slots, scores):
                c.execute("INSERT OR REPLACE INTO Preferences (ID_P, ID_M, t, score, is_auto) VALUES (?, ?, ?, ?, ?)", 
                          (row['ID_P'], row['ID_M'], t, score, 1))
            assigned_count += 1
            
    conn.commit()
    conn.close()
    return assigned_count

def get_fallback_count():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT p.ID_M) as fallback_count FROM Preferences p JOIN Modules m ON p.ID_M = m.ID_M WHERE p.is_auto = 1 AND m.ID_P IS NOT NULL")
    row = c.fetchone()
    conn.close()
    return row['fallback_count'] if row else 0

def undo_fallback_preferences():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Preferences WHERE is_auto = 1")
    conn.commit()
    conn.close()

def save_draft(username, form_key, draft_data):
    import json
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO Drafts (username, form_key, draft_data) VALUES (?, ?, ?)", 
              (username, form_key, json.dumps(draft_data)))
    conn.commit()
    conn.close()

def load_draft(username, form_key):
    import json
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT draft_data FROM Drafts WHERE username=? AND form_key=?", (username, form_key))
    row = c.fetchone()
    conn.close()
    if row:
        try:
            return json.loads(row['draft_data'])
        except Exception:
            return {}
    return {}

def clear_draft(username, form_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Drafts WHERE username=? AND form_key=?", (username, form_key))
    conn.commit()
    conn.close()

def submit_reschedule_request(session_id, id_p, new_t, new_s_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM RescheduleRequests WHERE session_id=? AND status IN ('Pending_Delegate', 'Pending_Admin')", (session_id,))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE RescheduleRequests SET new_t=?, new_s_id=?, status='Pending_Delegate' WHERE id=?", (new_t, new_s_id, existing['id']))
    else:
        c.execute("INSERT INTO RescheduleRequests (session_id, ID_P, new_t, new_s_id, status) VALUES (?, ?, ?, ?, 'Pending_Delegate')", 
                  (session_id, id_p, new_t, new_s_id))
    conn.commit()
    conn.close()

def get_pending_requests():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT r.*, p.nameP FROM RescheduleRequests r JOIN Profs p ON r.ID_P = p.ID_P WHERE r.status='Pending_Admin'")
    requests = [dict(row) for row in c.fetchall()]
    conn.close()
    return requests

def get_professor_requests(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM RescheduleRequests WHERE ID_P=? ORDER BY id DESC", (id_p,))
    requests = [dict(row) for row in c.fetchall()]
    conn.close()
    return requests

def approve_reschedule_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, new_t, new_s_id FROM RescheduleRequests WHERE id=?", (req_id,))
    req = c.fetchone()
    if req:
        c.execute("UPDATE Planning SET t=?, ID_S=? WHERE id=?", (req['new_t'], req['new_s_id'], req['session_id']))
        c.execute("UPDATE RescheduleRequests SET status='Approved' WHERE id=?", (req_id,))
        conn.commit()
    conn.close()

def reject_reschedule_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE RescheduleRequests SET status='Rejected' WHERE id=?", (req_id,))
    conn.commit()
    conn.close()

def clear_all_requests():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM SwapRequests")
    c.execute("DELETE FROM RescheduleRequests")
    c.execute("DELETE FROM Indisponibilites")
    c.execute("DELETE FROM UnavailabilityRequests")
    conn.commit()
    conn.close()

def submit_unavailability_request(id_p, t, reason):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO UnavailabilityRequests (ID_P, t, reason) VALUES (?, ?, ?)", (id_p, t, reason))
    conn.commit()
    conn.close()

def get_pending_unavailability_requests():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT ur.*, p.nameP 
        FROM UnavailabilityRequests ur
        JOIN Profs p ON ur.ID_P = p.ID_P
        WHERE ur.status = 'Pending'
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def approve_unavailability_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE UnavailabilityRequests SET status = 'Approved' WHERE id = ?", (req_id,))
    c.execute("SELECT ID_P, t FROM UnavailabilityRequests WHERE id = ?", (req_id,))
    row = c.fetchone()
    if row:
        c.execute("INSERT OR IGNORE INTO Indisponibilites (ID_P, t) VALUES (?, ?)", (row['ID_P'], row['t']))
    conn.commit()
    conn.close()

def reject_unavailability_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE UnavailabilityRequests SET status = 'Rejected' WHERE id = ?", (req_id,))
    conn.commit()
    conn.close()

def get_professor_unavailability_requests(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM UnavailabilityRequests WHERE ID_P = ?", (id_p,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

if __name__ == "__main__":
    init_db()
    print("Database Initialized")
