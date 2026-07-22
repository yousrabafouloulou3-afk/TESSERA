def verifier_contraintes_hard(id_p, id_e, id_s, t, data, planning, id_m=None):
    if (id_p, t) in data['indisponibles']: return False
    
    if (id_p, t) in planning['prof_occupe']: return False
    
    if (id_s, t) in planning['salle_occupee']: return False
    
    if (id_e, t) in planning['entite_occupee']: return False
    
    # If entity is a Group, check if parent Section is busy
    for sec_id, groupes in data['hierarchie'].items():
        if id_e in groupes:
            if (sec_id, t) in planning['entite_occupee']: return False

    # If entity is a Section, check if ANY of its Groups are busy
    if id_e in data['hierarchie']:
        for g_id in data['hierarchie'][id_e]:
            if (g_id, t) in planning['entite_occupee']: return False
    if id_m is not None:
        type_m = next((int(s['typeM']) for s in data.get('seances', []) if int(s['ID_M']) == int(id_m)), 1)
        if int(id_s) not in data.get('salles', {}).get(type_m, []):
            return False
            
    return True

def diagnose_contraintes_hard(id_p, id_e, id_s, t, data, planning, id_m=None):
    reasons = []
    if (id_p, t) in data['indisponibles']:
        reasons.append(('prof_unavail', None))
        
    if (id_p, t) in planning['prof_occupe']:
        sess_name = "another session"
        for s in planning['planning_final']:
            if s['ID_P'] == id_p and s['t'] == t:
                for m in data.get('seances', []):
                    if int(m['ID_M']) == int(s['ID_M']):
                        sess_name = m.get('nameM', "another session")
                        break
        reasons.append(('prof_busy', sess_name))
        
    if (id_s, t) in planning['salle_occupee']:
        sess_name = "another session"
        for s in planning['planning_final']:
            if s['ID_S'] == id_s and s['t'] == t:
                for m in data.get('seances', []):
                    if int(m['ID_M']) == int(s['ID_M']):
                        sess_name = m.get('nameM', "another session")
                        break
        reasons.append(('room_busy', sess_name))
        
    if (id_e, t) in planning['entite_occupee']:
        reasons.append(('entity_busy', None))
        
    for sec_id, groupes in data['hierarchie'].items():
        if id_e in groupes:
            if (sec_id, t) in planning['entite_occupee']:
                reasons.append(('parent_busy', None))
                
    if id_e in data['hierarchie']:
        for g_id in data['hierarchie'][id_e]:
            if (g_id, t) in planning['entite_occupee']:
                reasons.append(('child_busy', None))
                
    if id_m is not None:
        type_m = next((int(s['typeM']) for s in data.get('seances', []) if int(s['ID_M']) == int(id_m)), 1)
        if int(id_s) not in data.get('salles', {}).get(type_m, []):
            reasons.append(('room_incompatible', type_m))
            
    return reasons
    
def affecter_seance(id_p, id_e, id_s, id_m, t, planning, data):
    planning['prof_occupe'][(id_p, t)] = True
    planning['salle_occupee'][(id_s, t)] = True
    planning['entite_occupee'][(id_e, t)] = True
    
    if id_e in data['hierarchie']:
        for g_id in data['hierarchie'][id_e]:
            planning['entite_occupee'][(g_id, t)] = True
            
    score = data['preferences'].get((id_p, id_m, t), 100)
    
    planning['planning_final'].append({
        'ID_P': id_p, 'ID_E': id_e, 'ID_S': id_s, 'ID_M': id_m, 't': t, 'score': score
    })

def executer_greedy_priorite(data):
    planning = {"prof_occupe": {}, "salle_occupee": {}, "entite_occupee": {}, "planning_final": []}
    
    seances_ordonnees = sorted(data['seances'], 
                               key=lambda x: (-int(x['typeM']), -data['grades'].get(int(x['ID_P']), 0)))
    
    for seance in seances_ordonnees:
        id_m, id_p, id_e, type_m = int(seance['ID_M']), int(seance['ID_P']), int(seance['ID_E']), int(seance['typeM'])
        
        meilleur_t, meilleure_s, min_score = None, None, float('inf')
        
        for t in range(1, 37):
            for id_s in data['salles'][type_m]:
                if verifier_contraintes_hard(id_p, id_e, id_s, t, data, planning, id_m):
                    weights = data.get('weights', {'prof_prefs': 1.0})
                    score_actuel = data['preferences'].get((id_p, id_m, t), 100) * weights.get('prof_prefs', 1.0)
                    if score_actuel < min_score:
                        min_score = score_actuel
                        meilleur_t, meilleure_s = t, id_s
            if min_score == 0: break 
        if meilleur_t:
            affecter_seance(id_p, id_e, meilleure_s, id_m, meilleur_t, planning, data)
            
    return planning
