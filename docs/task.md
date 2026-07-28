# PFE Timetabling Execution Tasks

- `[x]` **1. Project Setup and Dependencies**
  - `[x]` Initialize project structure (`C:\Users\LENOVO\.gemini\antigravity\scratch\pfe_timetabling`).
  - `[x]` Create and activate a virtual environment.
  - `[x]` Install key libraries (`streamlit`, `pandas`, `openpyxl`, `plotly`, `fpdf2`, `qrcode`).

- `[x]` **2. Core Storage and Auth**
  - `[x]` Implement `database.py` (SQLite schema).
  - `[x]` Create `auth.py` (Simple Role Based Access Control login mechanism).

- `[x]` **3. Backend Engine (AI & OR)**
  - `[x]` Implement `engine/data_adapter.py` (Parsing data from Excel -> SQLite -> Engine format).
  - `[x]` Port user's Greedy algorithm to `engine/greedy.py`.
  - `[x]` Implement Multiprocessing Simulated Annealing in `engine/sa_optimizer.py`.

- `[x]` **4. Frontend Views**
  - `[x]` Implement `app.py` for routing and Night Mode Toggle.
  - `[x]` Implement Admin Dashboard (`views/admin.py`) with Upload, Optimization Trigger, and Gauge Chart.
  - `[x]` Implement Teacher Dashboard (`views/teacher.py`) with strict-block editing and preferences form.
  - `[x]` Implement Student Dashboard (`views/student.py`) focusing on specific Group.
  - `[x]` Implement Shared Utilities (`views/shared.py`) for PDF/QR export and Availability Checker.

- `[x]` **5. UI Polish and Verification**
  - `[x]` Apply modern CSS styling and Pastel palettes matching Google Calendar style.
  - `[x]` End-to-end testing of user constraints and SA optimization limit.
