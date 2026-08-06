import os
import re
import json
import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
#  PostgreSQL / Supabase compatibility layer
#  Makes psycopg2 behave exactly like sqlite3 for the rest of the codebase:
#    • conn.cursor()  →  returns a cursor that accepts ? placeholders
#    • row['col']     →  works (RealDictCursor)
#    • conn.commit()  →  works
#    • conn.close()   →  works
#    • INSERT OR IGNORE  →  auto-converted to ON CONFLICT DO NOTHING
# ─────────────────────────────────────────────────────────────────────────────

import psycopg2
import psycopg2.extras

_OR_IGNORE_RE  = re.compile(r'\bINSERT\s+OR\s+IGNORE\b', re.IGNORECASE)


class _CompatCursor:
    """Wraps psycopg2 RealDictCursor to transparently accept sqlite3-style SQL."""

    def __init__(self, cur):
        self._cur = cur

    def _adapt(self, q):
        """Convert ? → %s and INSERT OR IGNORE → ON CONFLICT DO NOTHING."""
        q = q.replace('?', '%s')
        if _OR_IGNORE_RE.search(q):
            q = _OR_IGNORE_RE.sub('INSERT', q)
            q = q.rstrip().rstrip(';') + ' ON CONFLICT DO NOTHING'
        return q

    def execute(self, query, params=None):
        q = self._adapt(query)
        self._cur.execute(q, params) if params is not None else self._cur.execute(q)

    def executemany(self, query, params_list):
        self._cur.executemany(self._adapt(query), params_list)

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        # Convert keys to upper case to match original SQLite style (e.g., ID_E)
        return {k.upper(): v for k, v in dict(row).items()}

    def fetchall(self):
        return [{k.upper(): v for k, v in dict(r).items()} for r in self._cur.fetchall()]

    def __iter__(self):
        for row in self._cur:
            yield {k.upper(): v for k, v in dict(row).items()}


class _CompatConn:
    """Wraps psycopg2 connection so existing code works with zero changes."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return _CompatCursor(
            self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        )

    def commit(self):
        self._conn.commit()

    def rollback(self):
        try:
            self._conn.rollback()
        except Exception:
            pass

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@st.cache_resource
def _get_pool():
    """Create a persistent psycopg2 connection pool (cached for the lifetime of the app)."""
    import streamlit as st
    from psycopg2 import pool as pg_pool
    cfg = st.secrets["supabase"]
    return pg_pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        host=cfg["host"],
        port=int(cfg["port"]),
        dbname=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode="require",
        connect_timeout=10,
    )


def get_db_connection():
    """Borrow a connection from the pool and return it wrapped in the compat layer."""
    import streamlit as st
    conn = _get_pool().getconn()
    conn.autocommit = False
    return _PoolCompatConn(conn)


class _PoolCompatConn(_CompatConn):
    """Like _CompatConn but returns the connection to the pool on close()."""
    def close(self):
        try:
            _get_pool().putconn(self._conn)
        except Exception:
            try:
                self._conn.close()
            except Exception:
                pass

    def __exit__(self, *args):
        self.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Schema – PostgreSQL DDL (replaces SQLite schema)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def init_db():
    """Initialize DB schema — runs once per server lifetime (cached by Streamlit)."""
    conn = get_db_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS Users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            linked_id INTEGER,
            linked_level TEXT
        )
    ''')
    c.execute('ALTER TABLE Users ADD COLUMN IF NOT EXISTS linked_level TEXT')

    # Re‑create Entities table with proper SERIAL primary key (ensures auto‑generated IDs)
    # Re‑create Entities table with proper SERIAL primary key (ensures auto‑generated IDs)
    c.execute('DROP TABLE IF EXISTS Entities CASCADE')
    c.execute('''
        CREATE TABLE IF NOT EXISTS Entities (
            ID_E SERIAL PRIMARY KEY,
            typeE INTEGER,
            sectionID INTEGER,
            nameE TEXT,
            specialite TEXT
        )
    ''')


    c.execute('''
        CREATE TABLE IF NOT EXISTS Profs (
            ID_P SERIAL PRIMARY KEY,
            nameP TEXT,
            prof INTEGER,
            specialite TEXT,
            matricule TEXT UNIQUE
        )
    ''')
    c.execute('ALTER TABLE Profs ADD COLUMN IF NOT EXISTS specialite TEXT')
    c.execute('ALTER TABLE Profs ADD COLUMN IF NOT EXISTS matricule TEXT')

    c.execute('''
        CREATE TABLE IF NOT EXISTS Modules (
            ID_M SERIAL PRIMARY KEY,
            typeM INTEGER,
            nameM TEXT,
            ID_P INTEGER,
            ID_E INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS Salles (
            ID_S SERIAL PRIMARY KEY,
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
    c.execute('ALTER TABLE Preferences ADD COLUMN IF NOT EXISTS is_auto INTEGER DEFAULT 0')

    # Planning uses explicit integer IDs (set from module IDs), not auto-increment
    c.execute('''
        CREATE TABLE IF NOT EXISTS Planning (
            id INTEGER PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            username TEXT,
            form_key TEXT,
            draft_data TEXT,
            UNIQUE(username, form_key)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS RescheduleRequests (
            id SERIAL PRIMARY KEY,
            session_id INTEGER,
            ID_P INTEGER,
            new_t INTEGER,
            new_s_id INTEGER,
            status TEXT DEFAULT 'Pending_Delegate'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS SwapRequests (
            ID_SR SERIAL PRIMARY KEY,
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
    c.execute('ALTER TABLE SwapRequests ADD COLUMN IF NOT EXISTS approved_by_delegate1 INTEGER DEFAULT 0')
    c.execute('ALTER TABLE SwapRequests ADD COLUMN IF NOT EXISTS approved_by_delegate2 INTEGER DEFAULT 0')

    c.execute('''
        CREATE TABLE IF NOT EXISTS UnavailabilityRequests (
            id SERIAL PRIMARY KEY,
            ID_P INTEGER,
            t INTEGER,
            reason TEXT,
            status TEXT DEFAULT 'Pending'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS Delegates (
            section_id INTEGER PRIMARY KEY,
            matricule TEXT UNIQUE
        )
    ''')

    conn.commit()
    conn.close()
    seed_default_users()


def seed_default_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO Users (username, password, role, linked_id)
        VALUES ('admin', 'admin123', 'admin', NULL)
        ON CONFLICT (username) DO NOTHING
    """)
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Planning
# ─────────────────────────────────────────────────────────────────────────────

def save_planning_to_db(planning):
    """Saves final planning list of dicts to the db."""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Planning")
    for session in planning['planning_final']:
        c.execute("""
            INSERT INTO Planning (id, ID_P, ID_E, ID_S, ID_M, t, score)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session['ID_M'], session['ID_P'], session['ID_E'], session['ID_S'],
              session['ID_M'], session['t'], session['score']))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Clear tables
# ─────────────────────────────────────────────────────────────────────────────

def clear_table_students():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Entities")
    c.execute("DELETE FROM Delegates")
    c.execute("DELETE FROM Users WHERE role IN ('student', 'delegate')")
    conn.commit()
    conn.close()
    seed_default_users()

def clear_table_professors():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Profs")
    c.execute("DELETE FROM Users WHERE role = 'teacher'")
    conn.commit()
    conn.close()
    seed_default_users()

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


# ─────────────────────────────────────────────────────────────────────────────
#  Professors
# ─────────────────────────────────────────────────────────────────────────────

def add_single_professor(name, specialite, is_prof, matricule):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_P FROM Profs WHERE nameP = %s AND specialite = %s", (name, specialite))
    row = c.fetchone()
    if row:
        conn.close()
        return False, "Professor already exists in this specialty."
    c.execute("INSERT INTO Profs (nameP, prof, specialite, matricule) VALUES (%s, %s, %s, %s)",
              (name, is_prof, specialite, matricule))
    conn.commit()
    conn.close()
    return True, "Professor added successfully."


def delete_single_professor(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nameP, specialite FROM Profs WHERE ID_P = %s", (id_p,))
    prof = c.fetchone()
    if prof:
        prof_name = prof['nameP']
        spec = prof['specialite']

        c.execute("DELETE FROM Profs WHERE ID_P = %s", (id_p,))
        c.execute("DELETE FROM Users WHERE role = 'teacher' AND linked_id = %s", (id_p,))
        c.execute("UPDATE Modules SET ID_P = NULL WHERE ID_P = %s", (id_p,))
        c.execute("UPDATE Planning SET ID_P = NULL WHERE ID_P = %s", (id_p,))
        c.execute("DELETE FROM Preferences WHERE ID_P = %s", (id_p,))
        c.execute("DELETE FROM Indisponibilites WHERE ID_P = %s", (id_p,))
        c.execute("DELETE FROM SwapRequests WHERE ID_P_Requester = %s OR ID_P_Target = %s", (id_p, id_p))
        c.execute("DELETE FROM RescheduleRequests WHERE ID_P = %s", (id_p,))
        c.execute("DELETE FROM UnavailabilityRequests WHERE ID_P = %s", (id_p,))

        c.execute("SELECT username, draft_data FROM Drafts WHERE form_key = 'prof_form'")
        rows = c.fetchall()
        for row in rows:
            username = row['username']
            try:
                draft = json.loads(row['draft_data'])
            except Exception:
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

                new_profs_list = [p for p in profs_list if p[0] != prof_name]
                if len(new_profs_list) < len(profs_list):
                    draft[num_prof_draft_key] = len(new_profs_list)
                    for i in range(num_profs):
                        draft.pop(f"pname_{spec}_{i}", None)
                        draft.pop(f"mat_{spec}_{i}", None)
                        draft.pop(f"isprof_{spec}_{i}", None)
                    for i, (p_name, p_mat, p_isprof) in enumerate(new_profs_list):
                        draft[f"pname_{spec}_{i}"] = p_name
                        draft[f"mat_{spec}_{i}"] = p_mat
                        draft[f"isprof_{spec}_{i}"] = p_isprof
                    c.execute(
                        "UPDATE Drafts SET draft_data = %s WHERE username = %s AND form_key = 'prof_form'",
                        (json.dumps(draft), username)
                    )
        conn.commit()
    conn.close()
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Rooms
# ─────────────────────────────────────────────────────────────────────────────

def delete_single_room(id_s):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nameS, typeS FROM Salles WHERE ID_S = %s", (id_s,))
    room = c.fetchone()
    if room:
        room_name = room['nameS']
        room_type = room['typeS']

        c.execute("DELETE FROM Salles WHERE ID_S = %s", (id_s,))
        c.execute("UPDATE Planning SET ID_S = NULL WHERE ID_S = %s", (id_s,))

        c.execute("SELECT username, draft_data FROM Drafts WHERE form_key = 'room_form'")
        rows = c.fetchall()
        for row in rows:
            username = row['username']
            try:
                draft = json.loads(row['draft_data'])
            except Exception:
                continue

            modified = False
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
                    for k in list(draft.keys()):
                        if k.startswith('amphi_'):
                            del draft[k]
                    for i, name in enumerate(amphis):
                        draft[f'amphi_{i}'] = name
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
                    for k in list(draft.keys()):
                        if k.startswith('td_'):
                            del draft[k]
                    for i, name in enumerate(tds):
                        draft[f'td_{i}'] = name

            if modified:
                c.execute(
                    "UPDATE Drafts SET draft_data = %s WHERE username = %s AND form_key = 'room_form'",
                    (json.dumps(draft), username)
                )
        conn.commit()
    conn.close()
    return True


def add_single_room(name, type_s):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT ID_S FROM Salles WHERE nameS = %s", (name,))
    if c.fetchone():
        conn.close()
        return False, "Room already exists."
    c.execute("INSERT INTO Salles (typeS, nameS) VALUES (%s, %s)", (type_s, name))
    conn.commit()
    conn.close()
    return True, "Room added successfully."


# ─────────────────────────────────────────────────────────────────────────────
#  Modules
# ─────────────────────────────────────────────────────────────────────────────

def add_single_module(name, type_m, id_p, id_e):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT INTO Modules (typeM, nameM, ID_P, ID_E) VALUES (%s, %s, %s, %s)",
              (type_m, name, id_p, id_e))
    conn.commit()
    conn.close()
    return True


def delete_single_module(id_m):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Modules WHERE ID_M = %s", (id_m,))
    c.execute("DELETE FROM Preferences WHERE ID_M = %s", (id_m,))
    c.execute("DELETE FROM Planning WHERE ID_M = %s", (id_m,))
    conn.commit()
    conn.close()
    return True


# ─────────────────────────────────────────────────────────────────────────────
#  Preferences
# ─────────────────────────────────────────────────────────────────────────────

def clear_teacher_preferences(teacher_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Preferences WHERE ID_P = %s", (teacher_id,))
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
    c.execute("""
        INSERT INTO SystemSettings (key, value) VALUES ('preference_deadline', %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (str(timestamp),))
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
    c.execute("""
        INSERT INTO SystemSettings (key, value) VALUES ('max_unavailability_slots', %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, (str(max_slots),))
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
    return 6


def get_preference_submission_stats():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT ID_M) as total_modules FROM Modules WHERE ID_P IS NOT NULL")
    row_tot = c.fetchone()
    total_mod = row_tot['total_modules'] if row_tot else 0

    c.execute("""
        SELECT COUNT(DISTINCT p.ID_M) as submitted_modules
        FROM Preferences p JOIN Modules m ON p.ID_M = m.ID_M
        WHERE m.ID_P IS NOT NULL
    """)
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

    c.execute("SELECT ID_M, ID_P FROM Modules WHERE ID_P IS NOT NULL")
    all_pairs = c.fetchall()

    c.execute("SELECT DISTINCT ID_M FROM Preferences")
    existing_modules = {str(r['ID_M']) for r in c.fetchall()}

    assigned_count = 0
    for row in all_pairs:
        mod_key = str(row['ID_M'])
        if mod_key not in existing_modules:
            slots = random.sample(range(1, 37), 3)
            scores = [0, 10, 20]
            for t, score in zip(slots, scores):
                c.execute("""
                    INSERT INTO Preferences (ID_P, ID_M, t, score, is_auto) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (ID_P, ID_M, t) DO UPDATE SET score = EXCLUDED.score, is_auto = EXCLUDED.is_auto
                """, (row['ID_P'], row['ID_M'], t, score, 1))
            assigned_count += 1

    conn.commit()
    conn.close()
    return assigned_count


def get_fallback_count():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(DISTINCT p.ID_M) as fallback_count
        FROM Preferences p JOIN Modules m ON p.ID_M = m.ID_M
        WHERE p.is_auto = 1 AND m.ID_P IS NOT NULL
    """)
    row = c.fetchone()
    conn.close()
    return row['fallback_count'] if row else 0


def undo_fallback_preferences():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("DELETE FROM Preferences WHERE is_auto = 1")
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Drafts
# ─────────────────────────────────────────────────────────────────────────────

def save_draft(username, form_key, draft_data):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO Drafts (username, form_key, draft_data) VALUES (%s, %s, %s)
        ON CONFLICT (username, form_key) DO UPDATE SET draft_data = EXCLUDED.draft_data
    """, (username, form_key, json.dumps(draft_data)))
    conn.commit()
    conn.close()


def load_draft(username, form_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT draft_data FROM Drafts WHERE username=%s AND form_key=%s", (username, form_key))
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
    c.execute("DELETE FROM Drafts WHERE username=%s AND form_key=%s", (username, form_key))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Reschedule requests
# ─────────────────────────────────────────────────────────────────────────────

def submit_reschedule_request(session_id, id_p, new_t, new_s_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id FROM RescheduleRequests WHERE session_id=%s AND status IN ('Pending_Delegate', 'Pending_Admin')",
        (session_id,)
    )
    existing = c.fetchone()
    if existing:
        c.execute(
            "UPDATE RescheduleRequests SET new_t=%s, new_s_id=%s, status='Pending_Delegate' WHERE id=%s",
            (new_t, new_s_id, existing['id'])
        )
    else:
        c.execute(
            "INSERT INTO RescheduleRequests (session_id, ID_P, new_t, new_s_id, status) VALUES (%s, %s, %s, %s, 'Pending_Delegate')",
            (session_id, id_p, new_t, new_s_id)
        )
    conn.commit()
    conn.close()


def get_pending_requests():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT r.*, p.nameP FROM RescheduleRequests r JOIN Profs p ON r.ID_P = p.ID_P WHERE r.status='Pending_Admin'")
    requests = c.fetchall()
    conn.close()
    return requests


def get_professor_requests(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM RescheduleRequests WHERE ID_P=%s ORDER BY id DESC", (id_p,))
    requests = c.fetchall()
    conn.close()
    return requests


def approve_reschedule_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT session_id, new_t, new_s_id FROM RescheduleRequests WHERE id=%s", (req_id,))
    req = c.fetchone()
    if req:
        c.execute("UPDATE Planning SET t=%s, ID_S=%s WHERE id=%s", (req['new_t'], req['new_s_id'], req['session_id']))
        c.execute("UPDATE RescheduleRequests SET status='Approved' WHERE id=%s", (req_id,))
        conn.commit()
    conn.close()


def reject_reschedule_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE RescheduleRequests SET status='Rejected' WHERE id=%s", (req_id,))
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


# ─────────────────────────────────────────────────────────────────────────────
#  Unavailability requests
# ─────────────────────────────────────────────────────────────────────────────

def submit_unavailability_request(id_p, t, reason):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO UnavailabilityRequests (ID_P, t, reason) VALUES (%s, %s, %s)",
        (id_p, t, reason)
    )
    conn.commit()
    conn.close()


def get_pending_unavailability_requests():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT ur.*,
               COALESCE(p.nameP, u.username, 'Prof #' || ur.ID_P::text) AS nameP
        FROM UnavailabilityRequests ur
        LEFT JOIN Profs p ON ur.ID_P = p.ID_P
        LEFT JOIN Users u ON u.linked_id = ur.ID_P AND u.role = 'teacher'
        WHERE ur.status = 'Pending'
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def approve_unavailability_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE UnavailabilityRequests SET status = 'Approved' WHERE id = %s", (req_id,))
    c.execute("SELECT ID_P, t FROM UnavailabilityRequests WHERE id = %s", (req_id,))
    row = c.fetchone()
    if row:
        c.execute("""
            INSERT INTO Indisponibilites (ID_P, t) VALUES (%s, %s)
            ON CONFLICT DO NOTHING
        """, (row['ID_P'], row['t']))
    conn.commit()
    conn.close()


def reject_unavailability_request(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE UnavailabilityRequests SET status = 'Rejected' WHERE id = %s", (req_id,))
    conn.commit()
    conn.close()


def get_professor_unavailability_requests(id_p):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM UnavailabilityRequests WHERE ID_P = %s", (id_p,))
    rows = c.fetchall()
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()
    print("Database Initialized")
