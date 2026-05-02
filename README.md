# ARCANE — Analytics Real-time Cross-sector AI Network Engine

> AI-Powered Analytics Platform | University of Tabuk 2025

---

## Requirements

- Python 3.11+
- XAMPP (for MySQL)
- Git

---

## Setup Instructions (Windows)

### Step 1 — Install Required Software

| Software | Download Link |
|----------|--------------|
| Python 3.11 | https://www.python.org/downloads/ |
| XAMPP | https://www.apachefriends.org/ |
| Git | https://git-scm.com/downloads/ |

> ⚠️ When installing Python, check **"Add Python to PATH"**

---

### Step 2 — Clone the Project

```bash
git clone https://github.com/YOUR_USERNAME/arcane_updated.git
cd arcane_updated
```

---

### Step 3 — Install Python Libraries

```bash
pip install flask pandas numpy scikit-learn werkzeug
```

---

### Step 4 — Setup Database

1. Open **XAMPP Control Panel**
2. Click **Start** next to **Apache** and **MySQL**
3. Open your browser → go to `http://localhost/phpmyadmin`
4. Click **New** → type database name: `arcane_db` → click **Create**
5. Click **Import** → choose `arcane_db.sql` from the project folder
6. Click **Go**

---

### Step 5 — Configure Email (for Password Reset)

Open `app.py` and update these lines:

```python
SMTP_USER = "your_gmail@gmail.com"    # Your Gmail address
SMTP_PASS = "xxxx xxxx xxxx xxxx"     # Gmail App Password (16 characters)
```

**How to get Gmail App Password:**
1. Go to myaccount.google.com/security
2. Enable **2-Step Verification**
3. Go to myaccount.google.com/apppasswords
4. Create new → name it "ARCANE" → copy the 16-character password

---

### Step 6 — Run the Project

```bash
python app.py
```

Open your browser → `http://127.0.0.1:5000`

---

## Project Structure

```
arcane_updated/
├── app.py                  ← Main Flask application
├── database_mysql.py       ← Database functions
├── arcane_db.sql           ← Database schema
├── requirements.txt        ← Python dependencies
├── static/
│   ├── logo.jpg
│   └── uploads/            ← Uploaded CSV files
└── templates/
    ├── arcane_landing_page.html
    ├── arcane_login_signup.html
    ├── arcane_dashboard.html
    ├── arcane_sector_selection.html
    ├── new_project_setup.html
    └── Demoarcane_project_workspace.html
```

---

## Supported Sectors

| Sector | Analysis Type | Target |
|--------|--------------|--------|
| Healthcare | Classification | Disease outcome |
| Commerce | Regression | Units sold |
| Education | Classification | Pass/Fail |
| Government | Classification | Citizen satisfaction |

---

## Tech Stack

- **Backend:** Python, Flask
- **Database:** MySQL (XAMPP)
- **ML:** Scikit-learn (Random Forest, K-Means)
- **Frontend:** HTML5, CSS3, JavaScript
- **Languages:** Arabic / English

---

## Team

- Beedor Awad
- Asaalah Hummdi  
- Mashael Alqahtani
- Raghad Suleman Alatawi

**Supervisor:** Dr. Sarah Tawfiq  
**Department of Computer Science — University of Tabuk**
