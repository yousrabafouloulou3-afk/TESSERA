# PFE Timetabling AI Application

This plan outlines the architecture and execution steps to build a high-end, competitive, and modern Streamlit-based AI timetabling system for your graduation project (PFE). It incorporates your core Greedy logic and extends it with Simulated Annealing via multiprocessing, a persistent SQLite database with role-based access, and a premium UI.

## User Review Required

> [!IMPORTANT]
> - **Data Entry Paradigm**: The system will use a strict hierarchical manual data entry system for the Admin (No Excel uploads). The admin must structurally define Students (Levels -> Specialties -> Sections -> Groups), Professors, Modules (Lectures & Tutorials), and Rooms. Is the outlined structure for modules (assigning specific professor and target entity for each session type) fully aligned with your model's requirement before generating the schedule? yes
> - **Simulated Annealing (SA) Logic**: The greedy algorithm minimizes the "score". The SA will attempt to find a better global optima by applying random valid permutations without breaking hard constraints. Do you have any specific requirements for the SA "neighborhood" functions (the way it mutates schedules)? No
> - **Workflow Dynamics**: All teacher-originated modifications (time/room changes, permutations, indisponibilities) require preliminary constraint validation and Admin approval before taking effect. 
> - **Workspace Directory**: I will initialize the codebase in `C:\Users\LENOVO\.gemini\antigravity\scratch\pfe_timetabling`.

## Proposed Changes

### 1. Core Architecture & Database Setup
Initialize the project structure in the target directory with a strict separation of concerns:
- **`database.py`**: SQLite schema handling CRUD operations. Tables: `Users` (Role-based), `Entities` (Sections/Groups), `Profs`, `Modules`, `Rooms`, `Indisponibilites`, `Preferences`, `PlanningFinal`, and newly added `Requests` (for the approval workflow).
- **`auth.py`**: Session state management for login forms and role-based access control (RBAC) ensuring Teachers can only see/edit their own data, and Students only their group's data.

### 2. Backend Engine (AI & OR)
- **`engine/data_adapter.py`**: Connects SQLite data to the shape required by the algorithm (a dictionary mirroring your `charger_donnees` logic).
- **`engine/greedy.py`**: Refactoring your provided code logic so that it natively outputs to our standard schedule dictionary structure.
- **`engine/sa_optimizer.py`**: An object-oriented Simulated Annealing class. By default, it will:
    - Receive the greedy solution as the initial state.
    - Use `multiprocessing.Pool` to run multiple SA chains in parallel with different random seeds.
    - Return the schedule with the lowest (best) penalty preference score.

### 3. Frontend Application (Streamlit)
- **`app.py`**: Main Streamlit driver. Incorporates the "Night Mode Toggle" and modern styling via custom CSS injection.
- **`views/admin.py`**: 
    - **Administrative Manual Data Entry Forms**:
        - *Students*: Select Level (L1, L2, L3, M1, M2) -> Define Specialties (count and names) -> Define Sections (automatically labeled A, B, C...) -> Define Groups per section (automatically labeled G1, G2...).
        - *Professors*: For each specialty, input count, names, and a categorical 'Prof' grade toggle/checkbox.
        - *Modules*: For each level/specialty, input count and names. For each module, specify weekly Lectures (Cours) for a section and Tutorials (TD) for a group. Assign specific Professor and target Student Entity per session type.
        - *Rooms*: Input available Lecture Rooms (Amphis) count/names and TD Rooms count/names.
    - **Approval Dashboard**: Interface to review, approve, or reject pending requests (Changes, Permutations, Indisponibilities) from the faculty.
    - **Restricted Analytics**: Dashboard displaying the Satisfaction Gauge Chart and percentage charts for teachers' preferences (Strictly visible ONLY to the Administrator).
    - **AI Engine Runner**: Triggers the optimization pipeline (Greedy -> parallel SA) accompanied by a dynamic progress bar.
- **`views/teacher.py`**: 
    - **Availability & Preferences**: Professors start with an empty timetable to select slots where they are unavailable (Indisponibilities). They must provide a mandatory comment/justification. These selections are submitted as requests requiring Admin approval. They can also input their top 3 preferred time slots.
    - **Request Workflow**: Select a session to request a manual change (time/room) or swap (permutation) with another professor. The system performs automated conflict-checks first. If valid, the request is sent to the Admin for approval.
    - **Notifications**: Real-time alerts indicating the Admin's decision (accept/refuse) on every request submitted.
    - A personal Google Calendar-style view (colored by Module type using Pastel palettes).
- **`views/student.py`**:
    - A clean, read-only personal schedule view covering their specific Section/Group.
- **`views/shared.py`**:
    - **Availability Checker**: Select a Time + Room -> Returns "Vacant" or "Occupied".
    - **Export**: Buttons linked to PDF generation (via `fpdf2`) and QR Codes (via `qrcode` library).

## Open Questions

> [!WARNING]
> - **Preference Score Range**: Your greedy code uses basic scoring (50=normal, 100=default, 0="Très bien"). Should the percentage charts reflect the "Percentage of total courses placed in the target 0 (Très bien) preference slots"?(50=normal, 20=bien, 0=tres bien, 100=default)
> - **Change Requests**: If a teacher's change/swap request is submitted, should the affected slots be placed in a "locked/pending" state so no other operations can conflict with them while waiting for Admin approval? no

## Verification Plan

### Automated Tests
- Validate that the hierarchical data entry pipeline successfully maps to SQLite and generates the exact dictionaries needed for the greedy engine.
- Verify `multiprocessing` SA does not violate your predefined hard constraints (`verifier_contraintes_hard`) during random neighbor generation. 
- Verify the conflict-check algorithm correctly validates or rejects invalid permutation and time change requests before they reach the Admin dashboard.

### Manual Verification
- Start the Streamlit app.
- Login as Admin, manually populate a minimal subset of data across the required hierarchy (1 Level, 1 Spec, etc.).
- Ensure that ONLY the Admin has access to the Satisfaction Gauge and teacher preference performance charts.
- Login as Teacher, define indisponibilities (with a mandatory comment), and submit a change request.
- Back in Admin Dashboard, act on the requests (approve one, deny another).
- Switch to Teacher to verify the real-time notification was received and the schedule reflects approved changes.
- Export schedule to PDF and confirm the QR Code points to a valid file text/link.
