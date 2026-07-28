import sqlite3
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection
import json

def load_data_from_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # 1. indisponibles
    indisponibles = set()
    c.execute("SELECT ID_P, t FROM Indisponibilites")
    for row in c.fetchall():
        indisponibles.add((row['ID_P'], row['t']))
        
    # 2. preferences
    preferences = {}
    c.execute("SELECT ID_P, ID_M, t, score FROM Preferences")
    for row in c.fetchall():
        preferences[(row['ID_P'], row['ID_M'], row['t'])] = row['score']
        
    # 3. hierarchie
    hierarchie = {}
    c.execute("SELECT ID_E FROM Entities WHERE typeE = 1")
    sections = [r['ID_E'] for r in c.fetchall()]
    for sec_id in sections:
        c.execute("SELECT ID_E FROM Entities WHERE typeE = 0 AND sectionID = ?", (sec_id,))
        groupes = [r['ID_E'] for r in c.fetchall()]
        hierarchie[sec_id] = groupes
        
    # 4. grades
    grades = {}
    c.execute("SELECT ID_P, prof FROM Profs")
    for row in c.fetchall():
        grades[row['ID_P']] = row['prof']
        
    # 5. salles
    salles = {1: [], 0: []}
    c.execute("SELECT ID_S, typeS FROM Salles")
    for row in c.fetchall():
        if row['typeS'] == 1:
            salles[1].append(row['ID_S'])
            salles[0].append(row['ID_S'])
        elif row['typeS'] == 0:
            salles[0].append(row['ID_S'])
            
    # 6. seances
    seances = []
    c.execute("SELECT ID_M, typeM, ID_P, ID_E FROM Modules")
    for row in c.fetchall():
        seances.append({
            'ID_M': row['ID_M'],
            'ID_P': row['ID_P'],
            'ID_E': row['ID_E'],
            'typeM': row['typeM']
        })
        
    conn.close()
    
    # 7. weights
    weights = {'prof_prefs': 1.0, 'student_gaps': 1.0, 'prof_gaps': 1.0, 'student_daily_limits': 1.0, 'prof_daily_limits': 1.0, 'prof_working_days': 1.0, 'student_working_days': 1.0, 'student_format_mix': 1.0}
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            try:
                config_data = json.load(f)
                if 'weights' in config_data:
                    weights = config_data['weights']
            except:
                pass

    return {
        "seances": seances,
        "indisponibles": indisponibles,
        "preferences": preferences,
        "hierarchie": hierarchie,
        "grades": grades,
        "salles": salles,
        "weights": weights
    }
