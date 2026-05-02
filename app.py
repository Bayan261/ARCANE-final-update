import os
import re
import json
import smtplib
import secrets
import socket
import pandas as pd
import numpy as np
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.utils import secure_filename

from database_mysql import update_user_password
from database_mysql import (
    insert_project, get_sector_id_by_name,
    create_user, get_user_by_email,
    get_project_by_id, verify_user, create_users_table,
    get_projects_by_user, update_project_status,
    save_pipeline_result, get_pipeline_result,
    get_dashboard_stats
)

app = Flask(__name__)
app.secret_key = "arcane_secret_key_2025"

with app.app_context():
    create_users_table()

# =========================
# Email Config (update with real credentials)
# =========================
# =========================
# EMAIL SETUP - REQUIRED STEPS:
# 1. Go to myaccount.google.com -> Security -> 2-Step Verification -> Turn ON
# 2. Then go to: myaccount.google.com/apppasswords
# 3. Create App Password -> choose "Mail" -> copy the 16-char password
# 4. Paste the 16-char password in SMTP_PASS below (spaces are OK)
# =========================
SMTP_HOST    = "smtp.gmail.com"
SMTP_PORT    = 587
SMTP_USER    = "arcane.analytics.platform@gmail.com"  # Your Gmail address
SMTP_PASS    = "abcd efgh ijkl mnop"                  # 16-char Gmail App Password
FRONTEND_URL = "http://127.0.0.1:5000"

# In-memory store for reset tokens  {token: email}
reset_tokens = {}

# =========================
# Sector validation rules
# =========================
# ═══════════════════════════════════════════════════════════════
# SECTOR RULES — aligned with ARCANE project report
# Each sector has:
#   target_keywords  : column names that are good targets (last resort: last col)
#   numeric_required : columns expected to be numeric
#   expected_keywords: at least one should appear (validation)
#   forbidden_keywords: if 2+ appear → sector mismatch
#   preferred_analysis: what analysis type fits this sector
#   description: human-readable
# ═══════════════════════════════════════════════════════════════
SECTOR_RULES = {
    "Healthcare": {
        "description": "Patient clinical data — early deterioration detection and disease outcome prediction",
        "preferred_analysis": "Classification",
        "target_keywords": [
            "deterioration_next_12h","deterioration","outcome","diagnosis","result",
            "disease","condition","diabetic","positive","negative","status","label",
            "mortality","survival","readmission","risk","sepsis","alert"
        ],
        "expected_keywords": [
            "heart_rate","respiratory_rate","spo2","spo2_pct","temperature",
            "systolic_bp","diastolic_bp","blood_pressure","oxygen","lactate",
            "wbc","wbc_count","creatinine","crp","hemoglobin","sepsis_risk_score",
            "comorbidity_index","nurse_alert","mobility_score","hour_from_admission",
            "patient","age","bmi","glucose","blood","pressure","insulin",
            "diagnosis","disease","outcome","symptom","heart","cancer",
            "skin","pregnancies","cholesterol","weight","height","admission_type"
        ],
        "forbidden_keywords": [
            "sales","revenue","profit","inventory","product","price","units_sold",
            "student","grade","gpa","attendance","election","votes","satisfaction",
            "citizen","complaint","service_type","borough","latitude","longitude",
            "G1","G2","G3","studytime","absences","failures","schoolsup","famsup",
            "famsize","pstatus","mjob","fjob","traveltime","paid","activities",
            "romantic","famrel","freetime","goout","dalc","walc","medu","fedu"
        ],
        "min_cols": 3,
        "min_rows": 10,
        "eda_focus": ["heart_rate","respiratory_rate","spo2_pct","sepsis_risk_score","age"],
    },
    "Commerce": {
        "description": "Sales, inventory, customer behaviour, financial forecasting",
        "preferred_analysis": "Regression",
        "target_keywords": [
            "units_sold","sales","revenue","profit","demand","quantity_sold",
            "total_sales","gross_profit","net_profit","orders","conversion"
        ],
        "expected_keywords": [
            "sales","revenue","price","quantity","customer","product","order",
            "profit","cost","inventory","stock","discount","category","units_sold",
            "rating","review","sku","margin","turnover"
        ],
        "forbidden_keywords": [
            "patient","diagnosis","glucose","blood","disease","symptom",
            "student","grade","gpa","attendance","satisfaction","citizen",
            "election","votes","response_time_days","num_complaints",
            "heart_rate","respiratory_rate","spo2_pct","spo2","systolic_bp",
            "diastolic_bp","lactate","creatinine","hemoglobin","sepsis_risk_score",
            "comorbidity_index","deterioration_next_12h","deterioration","nurse_alert",
            "wbc_count","admission_type","hour_from_admission",
            "complaint type","created date","closed date","borough","unique key",
            "G1","G2","G3","studytime","absences","failures","medu","fedu"
        ],
        "min_cols": 3,
        "min_rows": 10,
        "eda_focus": ["price","units_sold","discount_pct","customer_rating"],
    },
    "Education": {
        "description": "Student performance, attendance, grades, engagement",
        "preferred_analysis": "Classification",
        "target_keywords": [
            "performance","result","pass","fail","grade","outcome","label",
            "pass_fail","final_grade","academic_status","achievement","level"
        ],
        "expected_keywords": [
            "student","grade","score","attendance","gpa","course","exam",
            "pass","fail","performance","class","subject","teacher","study",
            "absences","assignment","homework","quiz","tutor","school",
            "study_hours","attendance_pct","assignments_done","prev_grade"
        ],
        "forbidden_keywords": [
            "patient","diagnosis","glucose","revenue","sales","profit",
            "votes","election","citizen","satisfaction","service_type",
            "blood","insulin","bmi",
            "heart_rate","respiratory_rate","spo2_pct","spo2","systolic_bp",
            "diastolic_bp","lactate","creatinine","crp_level","hemoglobin",
            "sepsis_risk_score","comorbidity_index","nurse_alert","mobility_score",
            "hour_from_admission","deterioration_next_12h","deterioration",
            "wbc_count","oxygen_device","admission_type","complaint","borough"
        ],
        "min_cols": 3,
        "min_rows": 10,
        "eda_focus": ["attendance_pct","absences","study_hours","performance"],
    },
    "Government": {
        "description": "311 Service Requests — performance analysis, delay detection, service quality clustering",
        "preferred_analysis": "Clustering",
        "target_keywords": [
            "processing_time","response_time","days_to_close","status",
            "satisfaction","rating","feedback","approval","complaint_type"
        ],
        "expected_keywords": [
            "complaint","complaint_type","created_date","closed_date","status",
            "descriptor","location_type","borough","community_board","due_date",
            "resolution","service","citizen","public","government","policy",
            "infrastructure","rating","survey","feedback","region","department",
            "response_time","digital","income","age_group","processing_time",
            "Complaint Type","Created Date","Closed Date","Status","Borough"
        ],
        "forbidden_keywords": [
            "patient","diagnosis","glucose","revenue","sales","student",
            "grade","gpa","insulin","bmi","blood_pressure","pregnancies",
            "units_sold","profit","inventory","heart_rate","spo2"
        ],
        "min_cols": 3,
        "min_rows": 10,
        "eda_focus": ["Complaint Type","Borough","processing_time","Status"],
    },
}

def validate_dataset_for_sector(df, sector_name):
    """
    Validate CSV against sector expectations — aligned with ARCANE project report.
    Returns (ok: bool, warnings: list, errors: list)
    """
    rules = SECTOR_RULES.get(sector_name, {})
    if not rules:
        return True, [], []

    errors   = []
    warnings = []
    # Build cols_str with BOTH space and underscore versions for robust matching
    cols_lower = [c.lower() for c in df.columns]
    cols_str   = " ".join(cols_lower) + " " + " ".join(c.lower().replace(" ","_") for c in df.columns)

    # ── 1. Basic size checks ──────────────────────────
    if len(df) < rules["min_rows"]:
        errors.append(
            f"Dataset has only {len(df)} rows. "
            f"Minimum required for reliable analysis: {rules['min_rows']}."
        )
    if len(df.columns) < rules["min_cols"]:
        errors.append(
            f"Dataset has only {len(df.columns)} columns. "
            f"Minimum required: {rules['min_cols']}."
        )

    # ── 2. Must have at least one numeric column ──────
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) == 0:
        errors.append(
            "Dataset must have at least one numeric column for ML analysis."
        )

    # ── 3. Forbidden keyword check (sector mismatch) ──
    forbidden_found = [
        kw for kw in rules.get("forbidden_keywords", [])
        if kw in cols_str
    ]
    if len(forbidden_found) >= 2:
        errors.append(
            f"This dataset does not match the '{sector_name}' sector. "
            f"Detected columns from a different domain "
            f"({', '.join(forbidden_found[:4])}). "
            f"Expected columns related to: {rules['description']}."
        )

    # ── 4. Expected keyword check (soft warning) ──────
    expected_found = [
        kw for kw in rules.get("expected_keywords", [])
        if kw in cols_str
    ]
    if len(expected_found) == 0 and len(forbidden_found) == 0:
        warnings.append(
            f"None of the typical '{sector_name}' column names were detected. "
            f"Please ensure your data is relevant to: {rules['description']}."
        )
    elif len(expected_found) == 0 and len(forbidden_found) > 0:
        pass  # Already reported as error above

    # ── 5. Target column detection hint ───────────────
    target_candidates = [
        col for col in df.columns
        if any(kw in col.lower() for kw in rules.get("target_keywords", []))
    ]
    if not target_candidates and len(errors) == 0:
        warnings.append(
            f"Could not detect a clear target column for '{sector_name}' analysis. "
            f"The last column will be used as the prediction target. "
            f"Expected targets: {', '.join(rules['target_keywords'][:5])}."
        )

    return (len(errors) == 0), warnings, errors

# =========================
# Helpers
# =========================
# Known valid email domains (fast-path — no DNS needed)
# ═══════════════════════════════════════════════════
# WHITELIST: only these domains are accepted
# Any domain NOT in this list → rejected immediately
# ═══════════════════════════════════════════════════
KNOWN_DOMAINS = {
    # Google
    "gmail.com", "googlemail.com", "google.com",
    # Microsoft
    "outlook.com", "hotmail.com", "hotmail.co.uk", "hotmail.fr",
    "hotmail.de", "hotmail.es", "hotmail.it",
    "live.com", "live.co.uk", "live.fr", "live.de",
    "msn.com", "windowslive.com",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # Yahoo
    "yahoo.com", "yahoo.co.uk", "yahoo.fr", "yahoo.de",
    "yahoo.es", "yahoo.it", "yahoo.co.jp", "ymail.com",
    # Privacy / other popular
    "protonmail.com", "protonmail.ch", "pm.me",
    "tutanota.com", "tutanota.de", "tuta.io",
    "zoho.com", "aol.com", "mail.com",
    "gmx.com", "gmx.net", "gmx.de",
    "yandex.com", "yandex.ru", "yandex.kz",
    "163.com", "126.com", "qq.com", "sina.com",
    # Saudi universities & edu
    "edu.sa",
    "kau.edu.sa", "ksu.edu.sa", "kfupm.edu.sa",
    "iau.edu.sa", "taibahu.edu.sa", "ut.edu.sa",
    "uqu.edu.sa", "ksau-hs.edu.sa", "kku.edu.sa",
    "nu.edu.sa", "pnu.edu.sa", "ub.edu.sa",
    "uoh.edu.sa", "su.edu.sa", "nauss.edu.sa",
    # Other common
    "istituto.it", "web.de", "laposte.net",
    "fastmail.com", "hey.com", "duck.com",
}

def _levenshtein(a, b):
    """Calculate edit distance between two strings."""
    if len(a) < len(b): a, b = b, a
    if not b: return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j+1]+1, curr[j]+1, prev[j]+(ca!=cb)))
        prev = curr
    return prev[-1]

def _find_close_domain(domain):
    """
    Find the closest known domain using edit distance.
    Returns suggestion if distance <= 2, else None.
    """
    domain = domain.lower()
    best_match = None
    best_dist  = 3  # threshold: reject if distance > 2

    for known in KNOWN_DOMAINS:
        dist = _levenshtein(domain, known)
        if dist < best_dist:
            best_dist  = dist
            best_match = known
        elif dist == best_dist and best_match is None:
            best_match = known

    return best_match if best_dist <= 2 else None

def _is_known_domain(domain):
    """Check if domain is in whitelist (exact or subdomain match)."""
    domain = domain.lower()
    if domain in KNOWN_DOMAINS:
        return True
    # Allow subdomains of known edu domains (e.g. cs.ksu.edu.sa)
    for known in KNOWN_DOMAINS:
        if domain.endswith("." + known):
            return True
    return False

def is_valid_email(email, check_dns=True):  # check_dns kept for compatibility
    """Full email validation: format + domain existence check."""
    if not email or len(email) < 6 or len(email) > 254:
        return False, "Email is too short or too long."
    email = email.strip().lower()
    if ' ' in email:
        return False, "Email cannot contain spaces."
    parts = email.split('@')
    if len(parts) != 2:
        return False, "Email must contain exactly one @ symbol."
    local, domain = parts
    if not local:
        return False, "Please enter a name before @."
    if len(local) > 64:
        return False, "The part before @ is too long."
    if local[0] in '.+-' or local[-1] in '.+-':
        return False, "Email cannot start or end with . + or -"
    if '..' in local:
        return False, "Email cannot have consecutive dots."
    if not domain or '.' not in domain:
        return False, "Please enter a valid domain (e.g. gmail.com)."
    if domain[0] in '-.' or domain[-1] in '-.':
        return False, "Domain cannot start or end with . or -"
    if '..' in domain:
        return False, "Domain cannot have consecutive dots."
    domain_parts = domain.split('.')
    tld = domain_parts[-1]
    if not re.match(r'^[a-zA-Z]{2,10}$', tld):
        return False, f"'{tld}' is not a valid domain extension (e.g. .com, .net, .org)."
    if any(len(p) == 0 for p in domain_parts):
        return False, "Domain has an empty section."
    full_pattern = re.compile(
        r'^[a-zA-Z0-9][a-zA-Z0-9._+\-]{0,62}[a-zA-Z0-9]?'
        r'@[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*'
        r'\.[a-zA-Z]{2,10}$'
    )
    single_pattern = re.compile(
        r'^[a-zA-Z0-9]@[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.[a-zA-Z]{2,10}$'
    )
    if not (full_pattern.match(email) or single_pattern.match(email)):
        return False, "Please enter a valid email address (e.g. name@gmail.com)."
    # Whitelist check — only known real domains accepted
    if not _is_known_domain(domain):
        # Try to suggest the closest known domain
        suggestion = _find_close_domain(domain)
        if suggestion:
            return False, f"Did you mean '{local}@{suggestion}'? '{domain}' is not a recognized email domain."
        return False, f"'{domain}' is not a recognized email provider. Please use a valid email (e.g. gmail.com, outlook.com, hotmail.com)."
    return True, "OK"

def is_strong_password(pw):
    if not pw or len(pw) < 8: return False
    return all([re.search(r"[a-z]", pw), re.search(r"[A-Z]", pw),
                re.search(r"\d", pw), re.search(r"[^A-Za-z0-9]", pw)])

def _clean(s): return (s or "").strip()
def _is_empty(s): return len(_clean(s)) == 0

def _read_csv_smart(path, **kwargs):
    """Auto-detect CSV encoding — supports UTF-8, Latin-1, CP1252 etc."""
    for enc in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1', 'utf-8-sig']:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, Exception):
            continue
    raise ValueError(f"Cannot read CSV file (unsupported encoding): {path}")

UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_ANALYSIS = {"Classification", "Regression", "Forecasting", "Clustering"}

# =========================
# Pages
# =========================
@app.route("/")
def landing():
    return render_template("arcane_landing_page.html")

@app.route("/auth")
def auth():
    return render_template("arcane_login_signup.html")

@app.route("/sectors")
def sectors():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    return render_template("arcane_sector_selection.html")

@app.route("/setup")
def setup():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    sector = request.args.get("sector", "")
    session["selected_sector"] = sector
    return render_template("new_project_setup.html", sector=sector)

@app.route("/projects")
def projects_page():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    user_projects = get_projects_by_user(session["user_id"])
    return render_template("projects.html", projects=user_projects)

# =========================
# AUTH
# =========================
@app.route("/signup", methods=["POST"])
def signup():
    name     = request.form.get("name", "").strip()
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    if len(name) < 3:
        return jsonify(success=False, field="name", message="Name must be at least 3 characters"), 400
    email_ok, email_msg = is_valid_email(email)
    if not email_ok:
        return jsonify(success=False, field="email", message=email_msg), 400
    if not is_strong_password(password):
        return jsonify(success=False, field="password",
                       message="Password must be 8+ chars with uppercase, lowercase, number & special character"), 400
    if password != confirm:
        return jsonify(success=False, field="confirm_password", message="Passwords do not match"), 400
    # Allow same email if different name (different people sharing email)
    from database_mysql import user_exists
    if user_exists(email, name):
        return jsonify(success=False, field="email",
                       message="An account with this name and email already exists. Please sign in."), 409

    create_user(name, email, password)
    return jsonify(
        success=True, registered=True,
        message=f"🎉 Account created! Welcome, {name}. Please sign in to continue.",
        redirect=url_for("auth") + "?mode=signin&registered=1"), 200


@app.route("/signin", methods=["POST"])
def signin():
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    email_ok, email_msg = is_valid_email(email)
    if not email_ok:
        return jsonify(success=False, field="email", message=email_msg), 400

    name_for_verify = request.form.get("name", "").strip()
    user = verify_user(email, password, name_for_verify if name_for_verify else None)
    if not user:
        return jsonify(success=False, field="password", message="Invalid email or password"), 401

    session.clear()
    session["user_id"]    = user["id"]
    session["user_name"]  = user.get("full_name") or user.get("name", "User")
    session["user_email"] = user.get("email", "")
    return jsonify(success=True, redirect=url_for("dashboard")), 200


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))


# =========================
# FORGOT PASSWORD
# =========================
@app.route("/forgot_password", methods=["POST"])
def forgot_password():
    email = request.form.get("email", "").strip().lower()

    # Step 1: Basic format check (fast, no DNS)
    email_ok, email_msg = is_valid_email(email)
    if not email_ok:
        return jsonify(success=False, message=email_msg), 400

    # Step 2: Check if this email is registered in our database FIRST
    user = get_user_by_email(email)
    if not user:
        return jsonify(
            success=False,
            message=f"No account found with the email '{email}'. Please check the address or create a new account."
        ), 404

    # Generate secure token
    token = secrets.token_urlsafe(32)
    reset_tokens[token] = email

    reset_link = f"{FRONTEND_URL}/reset_password/{token}"

    # Send email
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "ARCANE — Password Reset Request"
        msg["From"]    = f"ARCANE Platform <{SMTP_USER}>"
        msg["To"]      = email

        user_name = user.get("full_name") or user.get("name", "User")

        html_body = f"""
        <html><body style="font-family:Arial,sans-serif;background:#f5f7fa;padding:20px;">
        <div style="max-width:500px;margin:0 auto;background:white;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
            <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:30px;text-align:center;">
                <h1 style="color:white;margin:0;font-size:24px;">🔐 ARCANE</h1>
                <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;">AI-Powered Analytics Platform</p>
            </div>
            <div style="padding:30px;">
                <h2 style="color:#1e293b;">Hello, {user_name}!</h2>
                <p style="color:#64748b;line-height:1.6;">
                    We received a request to reset your ARCANE account password.<br>
                    Click the button below to set a new password:
                </p>
                <div style="text-align:center;margin:30px 0;">
                    <a href="{reset_link}" style="
                        background:linear-gradient(135deg,#667eea,#764ba2);
                        color:white;padding:14px 32px;border-radius:10px;
                        text-decoration:none;font-weight:600;font-size:16px;
                        display:inline-block;">
                        Reset My Password
                    </a>
                </div>
                <p style="color:#94a3b8;font-size:13px;">
                    This link expires in 1 hour. If you didn't request this, please ignore this email.
                </p>
                <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">
                <p style="color:#94a3b8;font-size:12px;text-align:center;">
                    © 2025 ARCANE Platform — University of Tabuk
                </p>
            </div>
        </div>
        </body></html>
        """
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, email, msg.as_string())

        return jsonify(
            success=True,
            message=f"Password reset link sent to {email}. Please check your inbox and spam folder."
        ), 200

    except smtplib.SMTPAuthenticationError:
        print("Email error: SMTPAuthenticationError — check SMTP_USER and SMTP_PASS in app.py")
        return jsonify(
            success=False,
            message="Email service is not configured yet. Please contact the administrator or set up Gmail App Password in app.py."
        ), 500

    except Exception as e:
        print(f"Email send error: {repr(e)}")
        return jsonify(
            success=False,
            message=f"Failed to send email: {str(e)[:100]}. Please try again later."
        ), 500


@app.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    email = reset_tokens.get(token)
    if not email:
        return "<h2>⚠️ Invalid or expired reset link.</h2><a href='/auth'>Go to Login</a>", 400

    if request.method == "POST":
        new_pw = request.form.get("password", "")
        confirm_pw = request.form.get("confirm_password", "")
        if not is_strong_password(new_pw):
            return render_template("reset_password.html", token=token,
                error="Password must be 8+ chars with uppercase, lowercase, number & special character")
        if new_pw != confirm_pw:
            return render_template("reset_password.html", token=token, error="Passwords do not match")
        try:
            update_user_password(email, new_pw)
        except Exception as e:
            print(f"Password update error: {e}")
            return render_template("reset_password.html", token=token,
                error="Something went wrong. Please try again.")
        del reset_tokens[token]
        return redirect(url_for("auth") + "?mode=signin&reset=1")

    return render_template("reset_password.html", token=token)


# =========================
# Dashboard
# =========================
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    try:
        stats = get_dashboard_stats(session["user_id"])
    except Exception as e:
        print("Dashboard stats error:", e)
        stats = {'total_projects':0,'completed_models':0,'avg_accuracy':0,'sector_dist':[],'recent_projects':[]}
    return render_template("arcane_dashboard.html", **stats)


# =========================
# Workspace
# =========================
@app.route("/workspace/<int:project_id>")
def workspace(project_id):
    if "user_id" not in session:
        return redirect(url_for("auth"))

    project = get_project_by_id(project_id)
    if not project:
        return "Project not found", 404

    result = get_pipeline_result(project_id)
    dataset_uploaded = bool(project.get("dataset_path"))
    chart_labels = result["chart_labels"] if result else None
    chart_data   = result["chart_data"]   if result else None
    chart_column = result["chart_column"] if result else None
    feature_importance = result["feature_importance"] if result else {}
    correlation_data      = result.get("correlation_data", [])      if result else []
    boxplot_data          = result.get("boxplot_data", [])          if result else []
    eda_chart_title       = result.get("eda_chart_title", "Data Distribution Overview") if result else "Data Distribution Overview"
    preprocessing_steps   = result.get("preprocessing_steps", [])   if result else []

    preview_headers, preview_rows = None, None
    if dataset_uploaded and os.path.exists(project["dataset_path"]):
        try:
            df_prev = _read_csv_smart(project["dataset_path"], nrows=5)
            preview_headers = df_prev.columns.tolist()
            # Replace NaN/None with empty string for clean display
            import math
            def _clean_val(v):
                if v is None: return ""
                if isinstance(v, float) and math.isnan(v): return ""
                s = str(v)
                return "" if s in ("nan","NaN","None","NaT") else s
            preview_rows = [
                {k: _clean_val(v) for k, v in row.items()}
                for row in df_prev.to_dict(orient="records")
            ]
        except Exception:
            pass

    user_name  = session.get("user_name", "User")
    user_email = session.get("user_email", "")
    user_initial = user_name[0].upper() if user_name else "U"

    return render_template(
        "Demoarcane_project_workspace.html",
        project_id       = project_id,
        project_name     = project.get("name"),
        sector_name      = project.get("sector"),
        analysis_type    = project.get("analysis_type", "Classification"),
        dataset_uploaded = dataset_uploaded,
        dataset_name     = os.path.basename(project.get("dataset_path", "")) if dataset_uploaded else "—",
        dataset_rows     = result["rows_count"] if result else 0,
        dataset_cols     = result["cols_count"] if result else 0,
        preview_headers  = preview_headers,
        preview_rows     = preview_rows,
        chart_data       = json.dumps(chart_data) if chart_data else None,
        chart_labels     = json.dumps(chart_labels) if chart_labels else None,
        chart_column     = chart_column,
        result           = result,
        feature_importance = json.dumps(feature_importance) if feature_importance else None,
        correlation_data     = correlation_data,
        boxplot_data         = boxplot_data,
        eda_chart_title      = eda_chart_title,
        preprocessing_steps  = preprocessing_steps,
        pipeline_done    = bool(result),
        user_name        = user_name,
        user_email       = user_email,
        user_initial     = user_initial,
        sector_warnings  = result.get("sector_warnings", []) if result else [],
    )


# =========================
# SAVE PROJECT
# =========================
@app.route("/save_project", methods=["POST"])
def save_project():
    if "user_id" not in session:
        return redirect(url_for("auth"))

    user_id       = session["user_id"]
    sector_name   = _clean(request.form.get("sector_id")) or _clean(session.get("selected_sector"))
    name          = _clean(request.form.get("project_name"))
    description   = _clean(request.form.get("description"))
    analysis_type = _clean(request.form.get("analysis_type"))

    errors = {}
    if _is_empty(sector_name):    errors["sector_error"]        = "Please select a sector first."
    if len(name) < 3:             errors["project_name_error"]  = "Project name must be at least 3 characters."
    if len(description) < 10:     errors["description_error"]   = "Description must be at least 10 characters."
    if analysis_type not in ALLOWED_ANALYSIS:
        errors["analysis_error"] = "Please select a valid analysis type."

    sector_id = get_sector_id_by_name(sector_name)
    if not sector_id:
        errors["sector_error"] = "Invalid sector selected."

    # CSV upload
    dataset_path = None
    file = request.files.get("dataset")
    if not file or not file.filename:
        errors["dataset_error"] = "Please upload a CSV file."
    elif not file.filename.lower().endswith(".csv"):
        errors["dataset_error"] = "Only CSV files are allowed."

    if errors:
        return render_template(
            "new_project_setup.html",
            sector=sector_name, project_name=name,
            description=description, active_step=3, **errors
        )

    # Save file
    filename   = secure_filename(file.filename)
    base, ext  = os.path.splitext(filename)
    counter    = 1
    final_name = filename
    while os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], final_name)):
        final_name = f"{base}_{counter}{ext}"
        counter += 1

    save_path = os.path.join(app.config["UPLOAD_FOLDER"], final_name)
    file.save(save_path)

    # --- Sector validation BEFORE creating project ---
    try:
        df_check = _read_csv_smart(save_path)
        sector_ok, sector_warnings, sector_errors = validate_dataset_for_sector(df_check, sector_name)
        if not sector_ok:
            os.remove(save_path)  # Clean up invalid file

            # Build a clear, sector-specific error message
            sector_examples = {
                "Healthcare":  "e.g. heart_rate, glucose, spo2, deterioration_next_12h",
                "Commerce":    "e.g. Sales, Profit, Quantity, Discount, Category",
                "Education":   "e.g. G1, G2, G3, studytime, absences, performance",
                "Government":  "e.g. Complaint Type, Created Date, Closed Date, Borough",
            }
            hint = sector_examples.get(sector_name, "")
            error_msg = (
                f"⚠️ This file does not match the '{sector_name}' sector. "
                f"Please upload a {sector_name} dataset ({hint})."
            )
            return render_template(
                "new_project_setup.html",
                sector=sector_name, project_name=name,
                description=description, active_step=3,
                dataset_error=error_msg
            )
    except Exception as e:
        sector_warnings = []
        print("Sector validation error:", e)

    dataset_path = save_path

    try:
        project_id = insert_project(
            user_id=user_id, sector_name=sector_name, sector_id=sector_id,
            name=name, description=description,
            dataset_path=dataset_path, analysis_type=analysis_type
        )
    except Exception as e:
        return f"❌ DB ERROR: {repr(e)}", 500

    # Run pipeline
    try:
        run_pipeline_logic(project_id, dataset_path, analysis_type, sector_name, sector_warnings)
    except Exception as e:
        print("⚠️ Pipeline warning:", repr(e))

    return redirect(url_for("workspace", project_id=project_id))


# =========================
# RUN PIPELINE (API)
# =========================
@app.route("/run_pipeline/<int:project_id>", methods=["POST"])
def run_pipeline(project_id):
    if "user_id" not in session:
        return redirect(url_for("auth"))

    project = get_project_by_id(project_id)
    if not project:
        return "Project not found", 404

    try:
        run_pipeline_logic(
            project_id,
            project["dataset_path"],
            project.get("analysis_type", "Classification"),
            project.get("sector", ""),
            []
        )
    except Exception as e:
        print("Pipeline error:", repr(e))

    return redirect(url_for("workspace", project_id=project_id))


# =========================
# PIPELINE LOGIC
# =========================
def _detect_target_column(df, sector_name):
    """
    Intelligently detect the target column based on sector.
    Each sector has explicit priority targets.
    """
    cols = list(df.columns)

    # ── Healthcare: deterioration_next_12h first ──
    if sector_name == "Healthcare":
        for t in ["deterioration_next_12h","deterioration","outcome","result","diagnosis"]:
            if t in cols: return t

    # ── Education: G3 always ──
    if sector_name == "Education":
        if "G3" in cols: return "G3"

    # ── Commerce: Profit preferred ──
    if sector_name == "Commerce":
        for t in ["Profit","profit","Sales","sales","Revenue","revenue"]:
            if t in cols: return t

    # ── Government: processing_time (computed) or Status ──
    if sector_name == "Government":
        if "processing_time" in cols: return "processing_time"
        for t in ["Status","status","Complaint Type","complaint_type"]:
            if t in cols: return t

    # Generic: sector keyword match
    rules      = SECTOR_RULES.get(sector_name, {})
    target_kws = rules.get("target_keywords", [])
    id_patterns = ["id","_id","index","row","no","num","number","#",
                   "key","latitude","longitude","zip","coordinate"]
    non_id_cols = [
        c for c in cols
        if not any(c.lower().strip("_") == p or c.lower().endswith(p)
                   or c.lower() in p for p in id_patterns)
    ]
    for kw in target_kws:
        for col in non_id_cols:
            if kw == col or kw in col.lower():
                return col

    return non_id_cols[-1] if non_id_cols else cols[-1]


def _determine_analysis_type(y, requested_type, sector_name):
    """
    Validate and possibly override the analysis type based on:
    - The actual target column data type
    - The sector's preferred analysis
    Returns the final analysis_type string and a note if it was overridden.
    """
    rules      = SECTOR_RULES.get(sector_name, {})
    preferred  = rules.get("preferred_analysis", requested_type)
    unique_cnt = y.nunique()
    n          = len(y)

    # For Classification/Forecasting/Clustering — check target suitability
    if requested_type == "Classification":
        # Target is continuous (too many unique values) → switch to Regression
        if unique_cnt > 20 or (unique_cnt / n > 0.5 and y.dtype in [float, "float64"]):
            return "Regression", f"Target has {unique_cnt} unique values — switched to Regression."
        return "Classification", None

    elif requested_type == "Regression":
        # Target is categorical (few unique string values) → switch to Classification
        if unique_cnt <= 10 and y.dtype == object:
            return "Classification", f"Target is categorical ({unique_cnt} classes) — switched to Classification."
        return "Regression", None

    elif requested_type == "Clustering":
        return "Clustering", None

    elif requested_type == "Forecasting":
        # Forecasting needs numeric target
        if y.dtype == object:
            return "Regression", "Target is categorical — Forecasting switched to Regression."
        return "Forecasting", None

    return requested_type, None


def _get_eda_chart(df, sector_name, target_col):
    """
    Build EDA chart data focused on the most meaningful column for the sector.
    IMPORTANT: Uses ORIGINAL df (before encoding) so labels are readable strings.
    Returns (chart_col, chart_labels, chart_data_vals)
    """
    rules     = SECTOR_RULES.get(sector_name, {})
    eda_focus = rules.get("eda_focus", [])

    # ── Priority: exact column name match from eda_focus ──
    chart_col = None
    for focus_kw in eda_focus:
        # Exact match first
        if focus_kw in df.columns and focus_kw != target_col:
            chart_col = focus_kw
            break
        # Partial match
        for col in df.columns:
            if focus_kw.lower() in col.lower() and col != target_col:
                chart_col = col
                break
        if chart_col:
            break

    # ── Fallback: first categorical (text) column with manageable unique values ──
    if not chart_col:
        for col in df.columns:
            if col == target_col: continue
            if any(p in col.lower() for p in ["id","key","_id","index","lat","lon","zip","coordinate","date"]): continue
            if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == object:
                if df[col].nunique() <= 30:
                    chart_col = col
                    break

    # ── Fallback: first numeric non-ID, non-target ──
    if not chart_col:
        for col in df.columns:
            if col == target_col: continue
            if any(p in col.lower() for p in ["id","_id","index","lat","lon","zip","coordinate"]): continue
            if pd.api.types.is_numeric_dtype(df[col]):
                chart_col = col
                break

    if not chart_col:
        return None, [], []

    col_data = df[chart_col].dropna()
    if col_data.empty:
        return chart_col, [], []

    # ── Categorical / Text column → value_counts sorted by frequency ──
    if pd.api.types.is_string_dtype(col_data) or col_data.dtype == object:
        vc = col_data.value_counts().head(10)  # top 10
        return chart_col, [str(x) for x in vc.index.tolist()], [int(x) for x in vc.values.tolist()]

    # ── Few unique numeric values → bar chart ──
    if col_data.nunique() <= 20:
        vc = col_data.value_counts().sort_index()
        return chart_col, [str(x) for x in vc.index.tolist()], [int(x) for x in vc.values.tolist()]

    # ── Many unique numeric values → histogram ──
    counts, bin_edges = np.histogram(col_data, bins=10)
    labels = [f"{bin_edges[i]:.1f}–{bin_edges[i+1]:.1f}" for i in range(len(bin_edges)-1)]
    return chart_col, labels, counts.tolist()


def run_pipeline_logic(project_id, dataset_path, analysis_type, sector_name="", sector_warnings=None):
    """
    Main ML pipeline — sector-aware, report-aligned.
    Steps: Load → Preprocess → Smart Target Detection → ML → EDA → Save
    """
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.cluster import KMeans
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        r2_score, mean_squared_error, mean_absolute_error,
        silhouette_score, davies_bouldin_score
    )

    if sector_warnings is None:
        sector_warnings = []

    # ─── 1. Load ────────────────────────────────────────
    df = _read_csv_smart(dataset_path)
    rows_before    = len(df)
    cols_count     = len(df.columns)
    missing_before = int(df.isnull().sum().sum())

    # ─── 2. Sector-specific preprocessing ──────────────
    # Healthcare: sample large datasets for speed
    if sector_name == "Healthcare" and len(df) > 10000:
        # Stratified sample to keep class balance
        try:
            target_tmp = df.columns[-1]
            df = df.groupby(target_tmp, group_keys=False).apply(
                lambda x: x.sample(min(len(x), 5000), random_state=42)
            ).reset_index(drop=True)
        except Exception:
            df = df.sample(10000, random_state=42).reset_index(drop=True)

    # Government: compute processing_time from dates
    if sector_name == "Government":
        if "Created Date" in df.columns and "Closed Date" in df.columns:
            try:
                df["created_dt"] = pd.to_datetime(df["Created Date"], errors="coerce")
                df["closed_dt"]  = pd.to_datetime(df["Closed Date"],  errors="coerce")
                df["processing_time"] = (df["closed_dt"] - df["created_dt"]).dt.days
                df["processing_time"] = df["processing_time"].clip(lower=0)
                df = df.drop(columns=["Created Date","Closed Date","Due Date",
                                       "created_dt","closed_dt",
                                       "Resolution Action Updated Date"], errors="ignore")
            except Exception as e:
                print(f"Gov date processing error: {e}")
        # Drop text/geo columns that don't help ML
        drop_cols = ["Unique Key","Incident Address","Street Name","Cross Street 1",
                     "Cross Street 2","Resolution Description","Descriptor",
                     "X Coordinate (State Plane)","Y Coordinate (State Plane)",
                     "Incident Zip","Latitude","Longitude","Park Borough",
                     "Community Board","Unnamed: 23","Location Type","City"]
        df = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
        # Sample if too large
        if len(df) > 15000:
            df = df.sample(15000, random_state=42).reset_index(drop=True)

    # ─── Standard Preprocessing ─────────────────────────
    dups_before = df.duplicated().sum()
    df = df.drop_duplicates()
    duplicates_removed = int(dups_before - df.duplicated().sum())

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            df[col] = df[col].fillna(df[col].median())
        else:
            if df[col].isnull().any():
                fill_val = df[col].mode()[0] if not df[col].mode().empty else "Unknown"
                df[col] = df[col].fillna(fill_val)

    missing_after = int(df.isnull().sum().sum())
    rows_count    = len(df)

    # ─── 3. Smart Target Detection ──────────────────────
    target_col   = _detect_target_column(df, sector_name)
    feature_cols = [c for c in df.columns if c != target_col]

    # Remove ID, date, free-text cols that don't help ML
    STRIP_EXACT = {
        "row id","order id","customer id","product id","postal code",
        "customer name","product name","order date","ship date",
        "country","city","state","row_id","order_id","customer_id","product_id"
    }
    feature_cols = [
        c for c in feature_cols
        if c.lower() not in STRIP_EXACT
        and not c.lower().endswith(("_id","_name","_date","_no","_code"))
        and c != target_col
    ]
    if not feature_cols:
        feature_cols = [c for c in df.columns
                        if c != target_col and c.lower() not in STRIP_EXACT]

    # ─── 4. Encode & prepare ────────────────────────────
    # Save original df for EDA (before encoding — preserves readable labels)
    df_original = df.copy()

    df_model = df[feature_cols + [target_col]].copy()

    # ── Encode FEATURES only (not target) ──────────────────
    # pd.api.types.is_string_dtype handles ALL string types including pandas StringDtype
    for col in feature_cols:
        if pd.api.types.is_string_dtype(df_model[col]) or pd.api.types.is_object_dtype(df_model[col]):
            le = LabelEncoder()
            df_model[col] = le.fit_transform(df_model[col].astype(str).values).astype(float)
        else:
            df_model[col] = pd.to_numeric(df_model[col], errors='coerce').fillna(0).astype(float)

    # ── Encode TARGET separately ────────────────────────────
    # Always try numeric first; if fails, use LabelEncoder
    le_target = LabelEncoder()
    if pd.api.types.is_string_dtype(df_model[target_col]) or pd.api.types.is_object_dtype(df_model[target_col]):
        y = pd.Series(le_target.fit_transform(df_model[target_col].astype(str).values).astype(float))
    else:
        y = pd.to_numeric(df_model[target_col], errors='coerce').fillna(0)

    X = df_model[feature_cols].astype(float)

    # ─── 5. Validate analysis type vs actual data ───────
    analysis_type, auto_note = _determine_analysis_type(y, analysis_type, sector_name)
    if auto_note:
        sector_warnings = list(sector_warnings) + [f"ℹ️ {auto_note}"]

    # ─── Preprocessing steps log ────────────────────────
    preprocessing_steps = [
        {"step": "Load Dataset",         "status": "done", "detail": f"{rows_before} rows, {cols_count} columns loaded"},
        {"step": "Remove Duplicates",     "status": "done", "detail": f"{duplicates_removed} duplicate rows removed"},
        {"step": "Handle Missing Values", "status": "done", "detail": f"{missing_before} missing → {missing_after} after fill (median/mode)"},
        {"step": "Encode Categorical",    "status": "done", "detail": "Label encoding applied to text columns"},
        {"step": "Target Detection",      "status": "done", "detail": f"Target column: {target_col}"},
    ]

    result_data = {
        "rows_count":           rows_count,
        "cols_count":           cols_count,
        "missing_before":       missing_before,
        "missing_after":        missing_after,
        "duplicates_removed":   duplicates_removed,
        "target_column":        target_col,
        "analysis_type":        analysis_type,
        "sector_name":          sector_name,
        "sector_warnings":      sector_warnings,
        "features_used":        feature_cols,
        "preprocessing_steps":  preprocessing_steps,
    }

    if len(X) < 10:
        raise ValueError("Dataset too small — need at least 10 rows for analysis.")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # ═══════════════════════════════════════════════════
    # ── 6A. Classification ───────────────────────────
    # ═══════════════════════════════════════════════════
    if analysis_type == "Classification":
        model = RandomForestClassifier(
            n_estimators=150, max_depth=None,
            random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        acc  = float(accuracy_score(y_test, y_pred))
        prec = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
        rec  = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
        f1   = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))

        # Class distribution for context
        class_counts = y.value_counts().to_dict()

        result_data.update({
            "model_accuracy":   round(acc, 4),
            "model_precision":  round(prec, 4),
            "model_recall":     round(rec, 4),
            "model_f1":         round(f1, 4),
            "class_distribution": {str(k): int(v) for k,v in class_counts.items()},
            "n_classes":        int(y.nunique()),
            "model_name":       "Random Forest Classifier",
        })

    # ═══════════════════════════════════════════════════
    # ── 6B. Regression ───────────────────────────────
    # ═══════════════════════════════════════════════════
    elif analysis_type == "Regression":
        model = RandomForestRegressor(
            n_estimators=150, random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2  = float(r2_score(y_test, y_pred))
        mse = float(mean_squared_error(y_test, y_pred))
        mae = float(mean_absolute_error(y_test, y_pred))

        result_data.update({
            "model_r2":     round(r2, 4),
            "model_mse":    round(mse, 4),
            "model_mae":    round(mae, 4),
            "target_mean":  round(float(y.mean()), 4),
            "target_std":   round(float(y.std()), 4),
            "model_name":   "Random Forest Regressor",
        })

    # ═══════════════════════════════════════════════════
    # ── 6C. Clustering ───────────────────────────────
    # ═══════════════════════════════════════════════════
    elif analysis_type == "Clustering":
        # Auto-select best k (2–8) using Silhouette Score
        best_k, best_score = 2, -999
        max_k = min(8, len(X) - 1)
        for k in range(2, max_k + 1):
            km  = KMeans(n_clusters=k, random_state=42, n_init=10)
            lbl = km.fit_predict(X)
            if len(set(lbl)) > 1:
                sc = silhouette_score(X, lbl)
                if sc > best_score:
                    best_score, best_k = sc, k

        model          = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        cluster_labels = model.fit_predict(X)
        db_score       = davies_bouldin_score(X, cluster_labels)

        # Cluster size distribution
        unique, counts = np.unique(cluster_labels, return_counts=True)
        cluster_dist   = {f"Cluster {int(u)+1}": int(c) for u, c in zip(unique, counts)}

        result_data.update({
            "model_clusters":       best_k,
            "model_silhouette":     round(float(best_score), 4),
            "model_davies_bouldin": round(float(db_score), 4),
            "cluster_distribution": cluster_dist,
            "model_name":           f"K-Means (k={best_k})",
        })
        # KMeans has no feature_importances_ — use variance as proxy
        fi = {col: round(float(X[col].std()), 4) for col in feature_cols}
        fi = dict(sorted(fi.items(), key=lambda x: x[1], reverse=True)[:8])
        result_data["feature_importance"] = fi

    # ═══════════════════════════════════════════════════
    # ── 6D. Forecasting ──────────────────────────────
    # ═══════════════════════════════════════════════════
    elif analysis_type == "Forecasting":
        model = RandomForestRegressor(
            n_estimators=150, random_state=42, n_jobs=-1
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2  = float(r2_score(y_test, y_pred))
        mse = float(mean_squared_error(y_test, y_pred))
        mae = float(mean_absolute_error(y_test, y_pred))

        result_data.update({
            "model_r2":        round(r2, 4),
            "model_mse":       round(mse, 4),
            "model_mae":       round(mae, 4),
            "forecast_points": int(len(y_pred)),
            "forecast_mean":   round(float(np.mean(y_pred)), 4),
            "forecast_std":    round(float(np.std(y_pred)), 4),
            "target_mean":     round(float(y.mean()), 4),
            "model_name":      "Random Forest Regressor (Forecasting)",
        })

    # ─── 7. Feature Importance ──────────────────────────
    if "feature_importance" not in result_data:
        fi = {}
        if hasattr(model, "feature_importances_"):
            fi = {
                col: round(float(imp), 4)
                for col, imp in zip(feature_cols, model.feature_importances_)
            }
            fi = dict(sorted(fi.items(), key=lambda x: x[1], reverse=True)[:8])
        result_data["feature_importance"] = fi

    # ─── 8. EDA Chart (sector-focused) ──────────────────
    chart_col, chart_labels_list, chart_data_vals = _get_eda_chart(df_original, sector_name, target_col)
    result_data["chart_column"] = chart_col or ""
    result_data["chart_labels"] = chart_labels_list
    result_data["chart_data"]   = chart_data_vals

    # ─── 8A. EDA Chart title per sector ─────────────────
    _eda_titles = {
        "Healthcare":  "Patient Clinical Indicators — Distribution Overview",
        "Commerce":    "Sales & Revenue Metrics — Distribution Overview",
        "Education":   "Student Performance Indicators — Distribution Overview",
        "Government":  "Service Requests Analysis — Distribution Overview",
    }
    result_data["eda_chart_title"] = _eda_titles.get(sector_name, "Data Distribution Overview")

    # ─── 8A2. Box Plot Data ─────────────────────────────
    try:
        rules_bp    = SECTOR_RULES.get(sector_name, {})
        eda_focus   = rules_bp.get("eda_focus", [])
        numeric_cols = df_original.select_dtypes(include=[np.number]).columns.tolist()
        # pick up to 4 cols from eda_focus first, then fallback to any numeric
        bp_candidates = []
        for kw in eda_focus:
            for c in numeric_cols:
                if kw.lower() in c.lower() and c != target_col and c not in bp_candidates:
                    bp_candidates.append(c)
        for c in numeric_cols:
            if c not in bp_candidates and c != target_col:
                bp_candidates.append(c)
        bp_cols = bp_candidates[:4]
        boxplot_data = []
        for c in bp_cols:
            vals = df_original[c].dropna().tolist()
            if len(vals) >= 5:
                q1  = float(np.percentile(vals, 25))
                med = float(np.percentile(vals, 50))
                q3  = float(np.percentile(vals, 75))
                iqr = q3 - q1
                lo  = float(max(min(vals), q1 - 1.5 * iqr))
                hi  = float(min(max(vals), q3 + 1.5 * iqr))
                boxplot_data.append({"col": c, "min": lo, "q1": q1, "median": med, "q3": q3, "max": hi})
        result_data["boxplot_data"] = boxplot_data
    except Exception:
        result_data["boxplot_data"] = []

    # ─── 8B. Correlation Analysis ────────────────────────
    try:
        numeric_df = df_original.select_dtypes(include=[np.number])
        if len(numeric_df.columns) >= 2:
            corr_matrix = numeric_df.corr().round(4)
            top_corr = []
            cols = corr_matrix.columns.tolist()
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    val = corr_matrix.iloc[i, j]
                    if not np.isnan(val):
                        top_corr.append({
                            "col1": cols[i],
                            "col2": cols[j],
                            "value": round(float(val), 4)
                        })
            top_corr = sorted(top_corr, key=lambda x: abs(x["value"]), reverse=True)[:10]
            result_data["correlation_data"] = top_corr
        else:
            result_data["correlation_data"] = []
    except Exception:
        result_data["correlation_data"] = []


    # ─── 9. Save ────────────────────────────────────────
    save_pipeline_result(project_id, result_data)
    update_project_status(project_id, "completed")
    return result_data

if __name__ == "__main__":
    app.run(debug=True)
