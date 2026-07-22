import random
import math
import multiprocessing
import copy
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.greedy import verifier_contraintes_hard, affecter_seance

def calculate_score(planning_final, data):
    weights = data.get('weights', {'prof_prefs': 1.0, 'student_gaps': 1.0})
    
    prof_prefs_score = sum(s['score'] for s in planning_final)
    
    student_gaps_score = 0
    student_limits_score = 0
    student_working_days_score = 0
    student_format_mix_score = 0
    w_gaps = weights.get('student_gaps', 1.0)
    w_limits = weights.get('student_daily_limits', 1.0)
    w_stud_days = weights.get('student_working_days', 1.0)
    w_stud_mix = weights.get('student_format_mix', 1.0)
    
    if w_gaps > 0 or w_limits > 0 or w_stud_days > 0 or w_stud_mix > 0:
        module_types = {s['ID_M']: s['typeM'] for s in data.get('seances', [])}
        group_slots = {}
        if 'hierarchie' in data:
            for sec, groups in data['hierarchie'].items():
                for g in groups:
                    group_slots[g] = [[] for _ in range(6)]
                    
        for s in planning_final:
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
                if num_sessions > 0:
                    student_working_days_score += 100
                    
                if num_sessions > 1:
                    times = [info[0] for info in slots_info]
                    span = max(times) - min(times) + 1
                    student_gaps_score += (span - num_sessions) * 50
                    
                    types_in_day = set(module_types.get(info[1]) for info in slots_info)
                    if len(types_in_day) == 1:
                        student_format_mix_score += 50
                    
                if num_sessions == 1:
                    student_limits_score += 50
                elif num_sessions > 4:
                    student_limits_score += (num_sessions - 4) * 50
                    
    prof_gaps_score = 0
    prof_limits_score = 0
    prof_working_days_score = 0
    w_prof_gaps = weights.get('prof_gaps', 1.0)
    w_prof_limits = weights.get('prof_daily_limits', 1.0)
    w_prof_days = weights.get('prof_working_days', 1.0)
    if w_prof_gaps > 0 or w_prof_limits > 0 or w_prof_days > 0:
        prof_slots = {}
        for s in planning_final:
            p_id = s['ID_P']
            day = (s['t'] - 1) // 6
            if 0 <= day < 6:
                if p_id not in prof_slots:
                    prof_slots[p_id] = [[] for _ in range(6)]
                prof_slots[p_id][day].append(s['t'])
                
        for days in prof_slots.values():
            for slots in days:
                num_sessions = len(slots)
                if num_sessions > 0:
                    prof_working_days_score += 100
                    
                if num_sessions > 1:
                    span = max(slots) - min(slots) + 1
                    prof_gaps_score += (span - num_sessions) * 50
                    
                if num_sessions == 1:
                    prof_limits_score += 50
                elif num_sessions > 4:
                    prof_limits_score += (num_sessions - 4) * 50
                    
    total_score = (weights.get('prof_prefs', 1.0) * prof_prefs_score) + \
                  (w_gaps * student_gaps_score) + \
                  (w_prof_gaps * prof_gaps_score) + \
                  (w_limits * student_limits_score) + \
                  (w_prof_limits * prof_limits_score) + \
                  (w_prof_days * prof_working_days_score) + \
                  (w_stud_days * student_working_days_score) + \
                  (w_stud_mix * student_format_mix_score)
    return total_score

def get_empty_planning_state():
    return {"prof_occupe": {}, "salle_occupee": {}, "entite_occupee": {}, "planning_final": []}

def build_state_from_final(planning_final, data):
    planning = get_empty_planning_state()
    for s in planning_final:
        id_p, id_e, id_s, id_m, t, score = s['ID_P'], s['ID_E'], s['ID_S'], s['ID_M'], s['t'], s['score']
        planning['prof_occupe'][(id_p, t)] = True
        planning['salle_occupee'][(id_s, t)] = True
        planning['entite_occupee'][(id_e, t)] = True
        if id_e in data['hierarchie']:
            for g_id in data['hierarchie'][id_e]:
                planning['entite_occupee'][(g_id, t)] = True
        planning['planning_final'].append(dict(s))
    return planning

def remove_session(s, planning, data):
    id_p, id_e, id_s, t = s['ID_P'], s['ID_E'], s['ID_S'], s['t']
    planning['prof_occupe'].pop((id_p, t), None)
    planning['salle_occupee'].pop((id_s, t), None)
    planning['entite_occupee'].pop((id_e, t), None)
    if id_e in data['hierarchie']:
        for g_id in data['hierarchie'][id_e]:
            planning['entite_occupee'].pop((g_id, t), None)
    for idx, sess in enumerate(planning['planning_final']):
        if sess['ID_M'] == s['ID_M'] and sess['ID_E'] == s['ID_E']:
            planning['planning_final'].pop(idx)
            break

def simulated_annealing_worker(args):
    data, initial_planning_final, seed, iters = args
    random.seed(seed)
    
    current_planning = build_state_from_final(initial_planning_final, data)
    best_planning_final = copy.deepcopy(current_planning['planning_final'])
    current_score = calculate_score(current_planning['planning_final'], data)
    best_score = current_score
    
    T = 100.0
    T_min = 1.0
    alpha = 0.95
    
    type_map = {m['ID_M']: m['typeM'] for m in data['seances']}
    
    while T > T_min and best_score > 0:
        for _ in range(iters):
            if len(current_planning['planning_final']) == 0: break
            
            idx = random.randint(0, len(current_planning['planning_final']) - 1)
            session = current_planning['planning_final'][idx]
            original_session = dict(session)
            
            remove_session(session, current_planning, data)
            
            type_m = type_map.get(session['ID_M'], 1)
            salles_dispo = data['salles'].get(type_m, [])
            if not salles_dispo:
                affecter_seance(original_session['ID_P'], original_session['ID_E'], original_session['ID_S'], original_session['ID_M'], original_session['t'], current_planning, data)
                continue
            
            new_t = random.randint(1, 36)
            new_s = random.choice(salles_dispo)
            
            if verifier_contraintes_hard(session['ID_P'], session['ID_E'], new_s, new_t, data, current_planning, session['ID_M']):
                affecter_seance(session['ID_P'], session['ID_E'], new_s, session['ID_M'], new_t, current_planning, data)
                new_score = calculate_score(current_planning['planning_final'], data)
                delta = new_score - current_score
                
                if delta <= 0 or random.random() < math.exp(-delta / T):
                    current_score = new_score
                    if current_score < best_score:
                        best_score = current_score
                        best_planning_final = copy.deepcopy(current_planning['planning_final'])
                else:
                    remove_session({'ID_P': session['ID_P'], 'ID_E': session['ID_E'], 'ID_S': new_s, 'ID_M': session['ID_M'], 't': new_t}, current_planning, data)
                    affecter_seance(original_session['ID_P'], original_session['ID_E'], original_session['ID_S'], original_session['ID_M'], original_session['t'], current_planning, data)
            else:
                affecter_seance(original_session['ID_P'], original_session['ID_E'], original_session['ID_S'], original_session['ID_M'], original_session['t'], current_planning, data)
                
        T = T * alpha
        
    return best_planning_final, best_score

def optimize_with_sa(data, initial_planning_final, num_workers=4, iters_per_temp=100):
    if not initial_planning_final: return []
    
    pool = multiprocessing.Pool(processes=num_workers)
    argsList = [(data, initial_planning_final, random.randint(0, 10000), iters_per_temp) for _ in range(num_workers)]
    
    results = pool.map(simulated_annealing_worker, argsList)
    pool.close()
    pool.join()
    
    best_result = min(results, key=lambda x: x[1])
    return best_result[0]
