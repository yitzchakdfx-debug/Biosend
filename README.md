# 🐦 DFX Tester - Component ATE

**Automated Test Equipment Framework for Component Validation**

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![PySide6](https://img.shields.io/badge/UI-PySide6-green.svg)
![SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)

## 📝 About the Project

The **DFX Tester** is an advanced software framework designed for managing and executing automated testing on electronic components (ATE). The system supports dynamic script-based test sequences (`.tst` files), real-time data monitoring, professional engineering reporting, and built-in role-based security.

> **Architecture Note:** This repository serves as the **Core Baseline Framework**. It is designed as a generic, modular foundation. Custom versions and branches will be derived from this core to meet specific hardware requirements, communication protocols, and unique client demands.

---

## 🔐 User Management & Permissions (RBAC)

To ensure operational safety and prevent human error on the production floor, the system features a strict Role-Based Access Control (RBAC) mechanism.

| Feature / Action                    |   Operator    | Engineer | Admin |
| :---------------------------------- | :-----------: | :------: | :---: |
| **Run Test Sequences**              |      ✅       |    ✅    |  ✅   |
| **View Results (Pass/Fail)**        |      ✅       |    ✅    |  ✅   |
| **View Technical Limits (Min/Max)** |      ❌       |    ✅    |  ✅   |
| **Edit Test Scripts (.tst)**        |      ❌       |    ✅    |  ✅   |
| **Export Full Detailed Reports**    | ❌ (Filtered) |    ✅    |  ✅   |
| **User Management**                 |      ❌       |    ❌    |  ✅   |

### Role Breakdown:

- **Operator:** Designed for daily production line use. The UI is simplified to show only final Pass/Fail outcomes. Technical limits (Min/Max) and script editing capabilities are hidden to prevent accidental configuration changes.
- **Engineer:** Granted full access to engineering data. Can view all measurement limits, edit test sequences using the built-in script editor, and analyze comprehensive hardware logs.
- **Admin:** Possesses all Engineer privileges, plus the ability to manage the system. Admins can create new users, modify roles, and enforce password resets via the User Management panel.

---

## ✨ Key Features

- **Script-Driven Execution:** Run dynamic test sequences without altering the application's source code.
- **Dynamic HW Trace Log:** Detailed hardware execution log with real-time command filtering for debugging.
- **Professional Reporting:** Export test results to CSV, JSON, and TXT. All exports include a standardized engineering header (Part Number, Serial Number, User, Timestamp).
- **Security & Integrity:** PBKDF2-HMAC-SHA256 password hashing, forced password resets for new users, and single-instance file locking to prevent database corruption.
- **Smart Metadata Parsing:** Automatically extracts metadata (e.g., `PartNum`) directly from the test script headers into the UI.

---

## 🛠 Tech Stack

- **Core Logic:** Python 3.x
- **GUI / Frontend:** PySide6 (Qt for Python)
- **Database:** SQLite 3
- **Security:** `hashlib`, `secrets`, `ctypes` (for Windows PID locking)
- **Styling:** Qt Style Sheets (QSS) with custom Dark/Light themes

---

## 🚀 Setup and Installation

1. Install the required dependencies:

   ```bash
   pip install PySide6

   Launch the application:
   python src/main.py


   ### Default Credentials (Admin):
   Upon the first run, the database will automatically initialize with a default administrator account:
   ```

- **Username:** `lior`
- **Password:** `XXXXXXX`

---

## 📁 Directory Structure

- `src/logic/`: Core application logic, test engine threads, and database management.
- `src/ui/`: PySide6 views, custom widgets, dialogs, and QSS themes.
- `src/data/`: Test script files (`.tst`) and local database storage.
- `src/assets/`: Application icons and graphical assets.

---
