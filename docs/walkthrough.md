# PFE Timetabling Application Walkthrough

The development of the competitive AI-driven timetabling PFE system is now complete. The codebase seamlessly brings together your Greedy strategy with a Simulated Annealing refiner, wrapped in a polished full-stack application built natively in Streamlit for optimal presentation over your database.

> [!TIP]
> **Getting Started**
> To run the application on your computer:
> 1. Open your terminal natively (Powershell/CMD).
> 2. `cd c:\Users\LENOVO\Desktop\TimeTable App`
> 3. Make sure packages are installed: `pip install streamlit pandas openpyxl plotly fpdf2 qrcode`
> 4. Run: `python -m streamlit run app.py`

## Architecture Highlights

1. **Authentication Engine** ([auth.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/auth.py) & [app.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/app.py)):
    - A custom `sqlite3` authentication flow blocks unauthorized access.
    - Automatic account generation occurs directly from your Excel Sheet (`teacher_{ID}` and `student_{ID}`).
    - Dynamic sidebar provides role-specific pages and the global **Night Mode** feature toggle.
    - **Delegate Signup Security & Approvals**: Student signups now support verification of Section Delegates. By inputting their secure Delegate Matricule, a student registers as a `'delegate'` user linked directly to their section. Furthermore, any reschedule requests proposed by professors for this section are routed to the delegate's dashboard for preliminary approval before being forwarded to the Admin.

2. **Operations Research (OR) AI Core** ([engine](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/engine)):
    - `data_adapter.py`: Acts as the bridge parsing SQLite relations directly onto your required constraints dictionary structure.
    - `greedy.py`: Your robust base heuristic which builds the legally viable foundation.
    - `sa_optimizer.py`: A `multiprocessing`-driven **Simulated Annealing** optimizer. It creates parallel instances of temperature cooling states and returns the global minimum bound of preference penalties (Scores converging to `0`).
    - **Stable Session ID Preservation**: Modified the planning database saving routine to explicitly map each scheduled session's primary key `id` directly to its corresponding `Modules.ID_M`. This guarantees that when the Admin rebuilds/reruns the schedule, the session IDs remain completely stable and unchanged, preventing pending teacher reschedule or swap requests from becoming orphaned.

## Dashboard Views

### ⭐ Admin Dashboard ([admin.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/admin.py))
> [!IMPORTANT]  
> The Admin is your single source of truth for bootstrapping the engine.
- Contains the `Upload Excel` component which seamlessly handles `Donnees_USTHB.xlsx` to feed the database via data cleansing.
- **Section Delegates Matricules Grid**: A data editor panel in the "Students" tab allows the Admin to assign and modify the secure Delegate Matricule for each academic section.
- Includes a primary execution button that fires the Greedy -> SA hybrid algorithm while tracking state via a real-time progress bar.
- Implements an impressive **Gauge Chart** (via Plotly) dynamically calculating the raw percentage of "Perfect" slots (Score equals 0).

# Multi-Objective Optimization Implemented

I have successfully refactored the AI scheduling engine to support multi-objective optimization using a weighted sum approach. 
The system now supports the following objectives:
1. **Minimize Professor Dissatisfaction** (giving them their preferred slots).
2. **Minimize Student Gaps**: Actively penalizes timetables that have empty slots between classes on the same day for any student group.
3. **Minimize Professor Gaps**: Actively penalizes timetables that have empty slots between classes on the same day for any professor.
4. **Student Daily Limits**: Penalizes schedules where a student group has exactly 1 session (less than 2) or more than 4 sessions in a single day.
5. **Professor Daily Limits**: Penalizes schedules where a professor has exactly 1 session or more than 4 sessions in a single day.
6. **Minimize Professor Working Days**: Penalizes the total number of days each professor has to commute to campus to teach.
7. **Minimize Student Working Days**: Penalizes the total number of days students have to commute to campus to attend classes.
8. **Student Format Mix**: Penalizes days where a student group has multiple sessions but they are all of the same format (e.g., only Cours or only TDs), encouraging a balanced variety of teaching formats per day.

## What Was Done

1. **Configuration (`config.json`)**: Added a default `weights` structure to store the configuration for all eight objectives.
2. **Data Pipeline (`engine/data_adapter.py`)**: Modified the database loader to also read and inject the optimization weights from `config.json` into the engine's `data` dictionary.
3. **Engine Refactoring (`engine/sa_optimizer.py`)**:
   - Replaced the simple `calculate_score` with a full weighted-sum function.
   - Calculates the score components for all eight metrics.
   - The final score is the sum of these components multiplied by their respective weights.
4. **Greedy Engine (`engine/greedy.py`)**: Updated the greedy initialization algorithm to multiply the professor preference score by its weight so it respects the new configuration.
5. **Admin Interface (`views/admin.py`)**: Added an **"Optimization Weights"** expander in the "AI Engine & Analytics" tab. The admin can now dynamically adjust the sliders for all eight objectives before running the pipeline.

## Verification

- Try navigating to the **Admin Dashboard** -> **AI Engine & Analytics**.
- You will see a new expandable section: ⚙️ **Optimization Weights (Multi-Objective)**.
- You can adjust the weights. For instance:
  - Setting **Professor Preferences** to `1.0` and the others to `0.0` will reproduce the original behavior (PLAN A).
  - Setting **Student Format Mix** to a high value will force the engine to mix formats (Cours and TD) within the same day for student groups whenever possible.

### ⭐ Teacher Workplace ([teacher.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/teacher.py))
> [!WARNING]  
> Manual movements are strictly constrained to preserve mathematically valid plans!
- Views distinct schedule rendered in a Google-Calendar style layout, with color distinguishing TD (Pastel green) and Cours (Pastel red). 
- **Strict Block Logic**: Allows teachers to override schedules if, and only if, the move clears strict OR constraints (room/group vacancy checks). 
- Built-in Form to explicitly overwrite their Top 3 desired timeframe instances which translates to the penalties 0, 10, and 20.
- **My Declared Preferences Table**: A structured session-by-session overview shown below the preference declaration form. This table displays a row for every single module session assigned to the teacher, letting them track what slots (Excellent, High, Normal) they've selected or whether they are still "Not Set".

### ⭐ Student Interactive Portal ([student.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/student.py))
- Inherited hierarchical schedule view explicitly matching their Section or unique sub-Group.
- **Availability Checker Utility**: Cross-functional utility attached for easy room occupancy detection manually (Available for Teachers as well).
- Includes the `QR Code Export` button generator ensuring ease of mobile access along with PDF download stubs.
- **Section Reschedule History Log (Delegates only)**: A comprehensive data table inside the approvals tab listing all reschedule requests submitted for the delegate's section (both approved, rejected, and pending at either level), complete with status coloring.

---

> [!NOTE]
> All code logic assumes `typeM` = 1 corresponds to "Cours" and 0 corresponds to "TD", mirroring your underlying implementation assumptions. Database mapping strictly binds logic without intermediate failure points.

## Multi-Language Support (English, French)

We have successfully integrated multi-language support for English and French across the entire application interface, including the Admin dashboard, Student portal, Teacher workspace, and Authentication flows.

### Implementation Details:
1. **Central Translation Engine ([translations.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/translations.py))**:
   - Implemented a unified translations dictionary mapping English text keys to their French equivalents.
   - Created the helper function `tr(text)` that dynamically queries the session-state language to return the appropriate localized text.
2. **Global Language Switcher**:
   - Placed a unified language selector (`Language / Langue`) and theme controls in the sidebar, accessible from all login, signup, and dashboard states.
3. **Translated Elements**:
   - Forms, buttons, placeholders, warning messages, and alerts.
   - Primary dashboard navigation tabs, data tables, metrics cards, and Plotly analytics charts (including the satisfaction gauge and constraints radar chart).

### Verification & Testing:
- Verified that all dashboard components compile successfully.
- Conducted browser testing to confirm that switching between English and French renders all interface headings, metrics, tables, and labels in the selected language instantly.

## Section Delegates Matricules Level Filtering & Global Validation

We have added a level-filtering feature for the Section Delegates Matricules data editor and a global duplicate check validation system.

### Key Changes:
1. **Level-Based Filtering ([admin.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/admin.py))**:
   - The Section Delegates Matricules grid dynamically filters and displays sections that match the level selected in the **Select Level** dropdown (e.g., L1, L2, L3, M1, M2).
2. **Global Duplicate Check Validation ([admin.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/admin.py))**:
   - When saving matricules, the application validates uniqueness inside the current editor grid, and checks globally against all other academic levels saved in the `Delegates` table.
   - If duplicates are found anywhere, a localized error message is shown, and the save action is aborted.
3. **Translations ([translations.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/translations.py))**:
   - Localized messages are provided for the uniqueness validation error.

### Verification:
- Verified using a comprehensive test script ([test_uniqueness_logic.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/scratch/test_uniqueness_logic.py)) checking local, global, null, and self-overwrite scenarios.
- Executed the browser subagent to verify that changing the level selector dynamically changes the list of sections in the grid.
- Recorded browser verification session at [level_filter_delegates_1781451277078.webp](file:///C:/Users/LENOVO/.gemini/antigravity-ide/brain/0b649817-6058-4045-9cc5-81255e5a1f1f/level_filter_delegates_1781451277078.webp).

## Professors Matricules Uniqueness Validation & Update Logic

We have added a Python-side validation check when saving professors to verify that all matricules are unique and prevent database IntegrityErrors. We also improved the check to allow re-saving the same professor's matricule without errors.

### Key Changes:
1. **Uniqueness Validation Checks ([admin.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/admin.py))**:
   - In `show_professor_data_entry()`, before saving, the app verifies that matricules are unique.
   - To prevent blocking normal re-saves or updates when the database already has pre-existing duplicate entries under multiple names, a matricule is only marked as a conflict if the entered name in the form is completely unassociated with that matricule in the database.
   - If a duplicate is assigned to a completely different professor name, the save is blocked and the user-friendly error is shown.
2. **Update instead of Duplicate Insertion ([admin.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/views/admin.py))**:
   - Inside `save_professors()`, the code now checks if a professor with the same name and specialty/department exists. If so, it updates their matricule and title status (`prof`) in place, rather than appending a redundant duplicate row to the database.
3. **Translations ([translations.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/translations.py))**:
   - Added English and French translations for the validation error message.

### Verification:
- Verified with the comprehensive test script ([test_uniqueness_logic.py](file:///c:/Users/LENOVO/Desktop/TimeTable%20App/scratch/test_uniqueness_logic.py)) checking local/global duplicates, blank entries, and same-name re-saves.
- Verified compilation and syntax correctness of `views/admin.py` and `translations.py`.

