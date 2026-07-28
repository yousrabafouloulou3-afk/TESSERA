import streamlit as st
import qrcode
from io import BytesIO
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import get_db_connection
from translations import tr

def availability_checker():
    st.subheader(tr("🔍 Availability Checker"))
    col1, col2, col3 = st.columns(3)
    with col1:
        day = st.selectbox(tr("Day"), ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"], format_func=tr)
        day_idx = ["Saturday", "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"].index(day)
    with col2:
        horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
        time_slot = st.selectbox(tr("Time Slot"), horaires)
        time_idx = horaires.index(time_slot)
    with col3:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT ID_S, nameS FROM Salles")
        salles = [{'id': r['ID_S'], 'name': r['nameS']} for r in c.fetchall()]
        conn.close()
        
        salle_name = st.selectbox(tr("Room"), [s['name'] for s in salles] if salles else ["None"])
        salle_id = next((s['id'] for s in salles if s['name'] == salle_name), None)

    if st.button(tr("Check Availability")):
        t = (day_idx * 6) + time_idx + 1
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM Planning WHERE ID_S=? AND t=?", (salle_id, t))
        res = c.fetchone()
        conn.close()
        
        if res:
            st.error(tr("🚫 Occupied"))
        else:
            st.success(tr("✅ Vacant"))

import re

def get_acronym(text):
    if not text:
        return ""
    text_lower = text.strip().lower()
    if text_lower == "algebra and cryptography" or text_lower == "algèbre et cryptographie":
        return "LAC"
    if text_lower == "data science" or text_lower == "science des données":
        return "DS"
    clean_rest = re.sub(r'\b(and|et)\b', '', text, flags=re.IGNORECASE)
    clean_rest = clean_rest.replace('&', '')
    rest_words = clean_rest.split()
    if len(rest_words) >= 2:
        return "".join([w[0].upper() for w in rest_words if w])
    return ""

def format_specialty_with_acronym(text):
    if not text:
        return text
    words = text.split()
    if not words: return text
    if re.match(r'^(L1|L2|L3|M1|M2|ING1|ING2|Master|Licence)', words[0], re.IGNORECASE):
        level = words[0]
        rest = " ".join(words[1:])
        ac = get_acronym(rest)
        if ac:
            return f"{text} ({ac})"
    else:
        ac = get_acronym(text)
        if ac:
            return f"{text} ({ac})"
    return text

@st.cache_data(ttl=60)
def get_specialities_dict():
    try:
        from database import get_db_connection
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT DISTINCT specialite FROM Entities WHERE specialite IS NOT NULL")
        specs = [r['specialite'] for r in c.fetchall()]
        conn.close()
    except Exception:
        return {}
        
    rep = {}
    for s in specs:
        words = s.split()
        if not words: continue
        
        if re.match(r'^(L1|L2|L3|M1|M2|ING1|ING2|Master|Licence)', words[0], re.IGNORECASE):
            level = words[0]
            rest = " ".join(words[1:])
        else:
            level = ""
            rest = s
            
        acronym = get_acronym(rest)
        if acronym:
            new_s = f"{level} {acronym}".strip()
            rep[s] = new_s
    return rep

def format_entity_name(name_e):
    if not name_e:
        return name_e
        
    replacements = get_specialities_dict()
    # Sort replacements by length descending so longer matches are replaced first
    for old, new in sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True):
        if old in name_e:
            name_e = name_e.replace(old, new)
            
    return name_e

def render_schedule_grid(planning_list, title="Schedule", pdf_title=None, hide_group_name=False, show_entity=False, mode="default"):
    actual_pdf_title = pdf_title if pdf_title else tr(title)
    # Google Calendar-style rendering using custom HTML tables and Pastel Colors
    st.markdown(f"### {tr(title)}")
    
    jours = ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu"]
    horaires = ["8:00-9:30", "9:40-11:10", "11:20-12:50", "13:00-14:30", "14:40-16:10", "16:20-17:50"]
    
    grid = {j: {h: [] for h in horaires} for j in jours}
    text_grid = {j: {h: [] for h in horaires} for j in jours}
    
    for s in planning_list:
        t = s['t']
        j = (t - 1) // 6
        h = (t - 1) % 6
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT nameM, typeM FROM Modules WHERE ID_M=?", (s['ID_M'],))
        mod = c.fetchone()
        c.execute("SELECT nameS FROM Salles WHERE ID_S=?", (s['ID_S'],))
        sal = c.fetchone()
        c.execute("SELECT nameE, typeE FROM Entities WHERE ID_E=?", (s['ID_E'],))
        ent = c.fetchone()
        c.execute("SELECT nameP FROM Profs WHERE ID_P=?", (s['ID_P'],))
        prof = c.fetchone()
        conn.close()
        
        m_name = mod['nameM'] if mod else "Unknown"
        s_name = sal['nameS'] if sal else ""
        p_name = prof['nameP'] if prof else ""
        
        group_name = ""
        section_name = ""
        
        if ent:
            if ent['typeE'] == 1: # Section
                section_name = format_entity_name(ent['nameE'])
                group_name = ""
            else: # Group
                parts = ent['nameE'].split(' - ')
                group_name = parts[-1].strip() if len(parts) > 1 else ent['nameE']
                section_name = format_entity_name(" - ".join(parts[:-1])) if len(parts) > 1 else ent['nameE']
                
        t_mod = "Cours" if mod and mod['typeM'] == 1 else "TD"
        t_mod_display = tr("Cours") if mod and mod['typeM'] == 1 else tr("TD")
        
        first_line_content = f"{m_name} ({t_mod_display})"
        if t_mod == "TD" and group_name and not hide_group_name:
            if mode != "default" or not show_entity:
                first_line_content += f" {group_name}"
                
        first_line_html = f"<b>{first_line_content}</b>"
        first_line_text = first_line_content
        
        lines = [first_line_html]
        lines_text = [first_line_text]
        
        if mode == "section":
            if s_name:
                lines.append(s_name)
                lines_text.append(s_name)
            if p_name:
                lines.append(p_name)
                lines_text.append(p_name)
        elif mode == "professor":
            if s_name:
                lines.append(s_name)
                lines_text.append(s_name)
            if ent:
                lines.append(format_entity_name(ent['nameE']))
                lines_text.append(format_entity_name(ent['nameE']))
        elif mode == "room":
            if p_name:
                lines.append(p_name)
                lines_text.append(p_name)
            if section_name:
                lines.append(section_name)
                lines_text.append(section_name)
        else: # "default"
            if s_name:
                lines.append(s_name)
                lines_text.append(s_name)
            if show_entity:
                if ent:
                    lines.append(format_entity_name(ent['nameE']))
                    lines_text.append(format_entity_name(ent['nameE']))
            else:
                if p_name:
                    lines.append(p_name)
                    lines_text.append(p_name)
                    
        lines_html = "<br>".join([l for l in lines if l])
        text_content = "\n".join([l for l in lines_text if l])
        
        # Pastel Colors Set3 style
        color = "#ffb3ba" if t_mod == "Cours" else "#baffc9" 
        content = f"<div style='background-color:{color}; padding: 8px; border-radius: 6px; margin-bottom: 4px; color: #1a1a1a; font-size: 0.85em; box-shadow: 0 1px 3px rgba(0,0,0,0.12);'>{lines_html}</div>"
        
        # Protect against bad slots
        if 0 <= j < len(jours) and 0 <= h < len(horaires):
            grid[jours[j]][horaires[h]].append(content)
            text_grid[jours[j]][horaires[h]].append((text_content, t_mod == "Cours"))
        
    html = "<table style='width:100%; border-collapse: separate; border-spacing: 2px;'>"
    html += "<tr><th style='border:none;'></th>" + "".join([f"<th style='text-align:center; padding: 10px; background-color: #f2f2f2; color: #1a1a1a; border-radius: 4px;'>{h}</th>" for h in horaires]) + "</tr>"
    for j in jours:
        html += f"<tr><td style='font-weight: bold; padding: 10px; background-color: #f2f2f2; color: #1a1a1a; border-radius: 4px; text-align: right;'>{tr(j)}</td>"
        for h in horaires:
            cell_content = "".join(grid[j][h])
            html += f"<td style='border: 1px solid #e0e0e0; vertical-align: top; width: 16%; padding: 5px; height: 100px; border-radius: 4px;'>{cell_content}</td>"
        html += "</tr>"
    html += "</table><br>"
    
    st.markdown(html, unsafe_allow_html=True)
    
    import json
    config_path = "config.json"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = {"semester": "2", "college_year": "2025/2026"}
        
    sem = config.get("semester", "2")
    year = config.get("college_year", "2025/2026")
    
    def generate_pdf_bytes():
        try:
            from fpdf import FPDF
            import os
            pdf = FPDF(orientation='L', unit='mm', format='A4')
            pdf.set_auto_page_break(auto=False, margin=0)
            pdf.add_page()
            
            # Draw Logo if exists
            try:
                root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                logo_png = os.path.join(root_dir, "assets", "usthb_logo.png")
                logo_jpg = os.path.join(root_dir, "assets", "usthb_logo.jpg")
                if os.path.exists(logo_png):
                    pdf.image(logo_png, 10, 5, 20)
                elif os.path.exists(logo_jpg):
                    pdf.image(logo_jpg, 10, 5, 20)
            except Exception:
                pass # Continue generating PDF even if logo fails
                
            # Draw App Logo top right
            try:
                app_logo = os.path.join(root_dir, "assets", "tessera_logo_rounded.png")
                if os.path.exists(app_logo):
                    pdf.image(app_logo, 269.5, 5, 15)
                    pdf.set_xy(267, 21)
                    pdf.set_font("helvetica", "B", 8)
                    pdf.cell(20, 4, "TESSERA", align="C")
            except Exception:
                pass
            pdf.set_xy(10, 8)
            pdf.set_font("helvetica", "B", 11)
            pdf.cell(0, 5, "University of Science and Technology Houari Boumediene", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(3)
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(0, 5, actual_pdf_title, new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(3)
            pdf.set_font("helvetica", "B", 9)
            pdf.cell(0, 5, f"{tr('College year:')} {year}      {tr('Semester:')} {sem}", new_x="LMARGIN", new_y="NEXT", align="C")
            pdf.ln(3)
            
            pdf.set_font("helvetica", "B", 10)
            col_w = 277 / 7
            line_h = 4.2
            
            pdf.cell(col_w, line_h, "", border=1)
            for h in horaires:
                pdf.cell(col_w, line_h, h, border=1, align="C")
            pdf.ln()
            
            pdf.set_font("helvetica", "B", 8)
            for j in jours:
                max_lines = 1
                for h in horaires:
                    if text_grid[j][h]:
                        total_lines = 0
                        for item, _ in text_grid[j][h]:
                            total_lines += item.count("\n") + 1
                        # add spacing between items
                        total_lines += (len(text_grid[j][h]) - 1) * 0.5
                        if total_lines > max_lines:
                            max_lines = total_lines
                            
                row_height = max_lines * line_h if max_lines > 1 else line_h * 2
                
                x = pdf.get_x()
                y = pdf.get_y()
                
                # We disabled auto page break, so no manual page break logic needed
                
                pdf.rect(x, y, col_w, row_height)
                pdf.set_xy(x, y + (row_height/2) - (line_h/2))
                pdf.multi_cell(col_w, line_h, j, border=0, align="C")
                pdf.set_xy(x + col_w, y)
                
                for h in horaires:
                    x = pdf.get_x()
                    y = pdf.get_y()
                    
                    if text_grid[j][h]:
                        total_content_height = sum((item.count("\n") + 1) * line_h for item, _ in text_grid[j][h])
                        total_content_height += (len(text_grid[j][h]) - 1) * (line_h / 2)
                        current_y = y + (row_height - total_content_height) / 2
                        
                        for item, is_cours in text_grid[j][h]:
                            text_h = (item.count("\n") + 1) * line_h
                            if is_cours:
                                pdf.set_fill_color(255, 179, 186)
                            else:
                                pdf.set_fill_color(186, 255, 201)
                                
                            # Draw background box with 0.5mm top/bottom padding so it doesn't touch the borders
                            pdf.set_xy(x + 1, current_y + 0.5)
                            pdf.multi_cell(col_w - 2, text_h - 1, "", border=0, align="C", fill=True)
                            
                            pdf.set_xy(x, current_y)
                            pdf.multi_cell(col_w, line_h, item.encode('latin-1', 'replace').decode('latin-1'), border=0, align="C")
                            
                            current_y += text_h + (line_h / 2)
                            
                    # Draw cell border AFTER backgrounds so it overlaps them properly
                    pdf.rect(x, y, col_w, row_height)
                    pdf.set_xy(x + col_w, y)
                pdf.ln(row_height)
            
            return bytes(pdf.output())
        except Exception as e:
            return b"PDF Generation Failed"

    st.download_button(tr("⬇️ Download PDF"), data=generate_pdf_bytes(), file_name=f"{actual_pdf_title.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_{actual_pdf_title}_{title}")
