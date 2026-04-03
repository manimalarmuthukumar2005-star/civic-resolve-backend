"""
Civic Resolve Backend - Uses only: Flask, PyJWT, scikit-learn, sqlite3 (stdlib)
"""
from flask import Flask, request, jsonify, send_from_directory, g
# Supabase cloud sync (graceful fallback)
def is_supabase_enabled(): return False
import sqlite3, os, json, random, hashlib, hmac, uuid, time, re
from datetime import datetime
import jwt as pyjwt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

# ── Load .env file automatically ──────────────────────────
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        try:
            with open(env_path, encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass
_load_dotenv()


# ─── IST TIMEZONE HELPER ──────────────────────────────────────────────────────
def ist_now():
    """Return current IST datetime string (UTC+5:30)"""
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')

def to_ist(utc_str):
    """Convert stored UTC string to IST for display"""
    if not utc_str: return ''
    try:
        from datetime import timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        dt = datetime.strptime(utc_str, '%Y-%m-%d %H:%M:%S')
        dt_utc = dt.replace(tzinfo=timezone.utc)
        dt_ist = dt_utc.astimezone(IST)
        return dt_ist.strftime('%d %b %Y, %I:%M %p IST')
    except:
        return utc_str

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'civic_issues.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
SECRET_KEY = os.environ.get('SECRET_KEY', 'civic-pulse-secret-2024')
ALLOWED_EXT = {'png','jpg','jpeg','gif','webp'}

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ─── CORS MIDDLEWARE ──────────────────────────────────────────────────────────
@app.after_request
def add_cors(resp):
    allowed = os.environ.get('ALLOWED_ORIGINS', '*')
    origin = request.headers.get('Origin', '')
    if allowed == '*' or origin in allowed.split(','):
        resp.headers['Access-Control-Allow-Origin'] = origin or '*'
    else:
        resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
    return resp

@app.route('/api/<path:p>', methods=['OPTIONS'])
def options(p):
    resp = app.make_response('')
    resp.headers['Access-Control-Allow-Origin']  = '*'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,PATCH,DELETE,OPTIONS'
    resp.status_code = 204
    return resp

# ─── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db: db.close()

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'citizen',
            department TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            description TEXT NOT NULL,
            image_path TEXT,
            latitude REAL,
            longitude REAL,
            address TEXT,
            location_address TEXT,
            category TEXT,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Pending',
            department TEXT,
            department_assigned TEXT,
            ml_confidence REAL DEFAULT 0,
            reopen_count INTEGER DEFAULT 0,
            reopened_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            resolved_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS otp_store (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            otp TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS complaint_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            changed_by TEXT,
            change_type TEXT DEFAULT 'status_update',
            old_value TEXT,
            new_value TEXT,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );
        CREATE TABLE IF NOT EXISTS department_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            department TEXT NOT NULL,
            responder_name TEXT,
            message TEXT NOT NULL,
            image_path TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            avatar_url TEXT,
            address TEXT,
            pincode TEXT,
            city TEXT,
            bio TEXT,
            updated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS feedbacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER,
            comment TEXT,
            sentiment TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (complaint_id) REFERENCES complaints(id)
        );
        """)
        # Seed default users
        def seed_user(name, email, phone, pw, role, dept=None):
            exists = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not exists:
                h = hash_password(pw)
                db.execute("INSERT INTO users (name,email,phone,password_hash,role,department) VALUES (?,?,?,?,?,?)",
                           (name, email, phone, h, role, dept))
        seed_user('System Admin',       'admin@civic.gov',      '0000000000', 'admin123', 'admin')
        seed_user('Roads Officer',      'roads@civic.gov',       '1111111111', 'dept123', 'department', 'Roads/Public Works')
        seed_user('Sanitation Officer', 'sanitation@civic.gov',  '2222222222', 'dept123', 'department', 'Sanitation')
        seed_user('Drainage Officer',   'drainage@civic.gov',    '3333333333', 'dept123', 'department', 'Drainage/Water')
        seed_user('Electrical Officer', 'electrical@civic.gov',  '4444444444', 'dept123', 'department', 'Electrical')
        db.commit()

def migrate_db():
    """Add missing columns to existing databases — safe to run every time"""
    with sqlite3.connect(DB_PATH) as db:
        # Get existing complaints columns
        existing = {row[1] for row in db.execute("PRAGMA table_info(complaints)").fetchall()}
        migrations = [
            ("title",               "ALTER TABLE complaints ADD COLUMN title TEXT DEFAULT ''"),
            ("location_address",    "ALTER TABLE complaints ADD COLUMN location_address TEXT DEFAULT ''"),
            ("department_assigned", "ALTER TABLE complaints ADD COLUMN department_assigned TEXT DEFAULT ''"),
            ("ml_confidence",       "ALTER TABLE complaints ADD COLUMN ml_confidence REAL DEFAULT 0"),
            ("reopened_count",      "ALTER TABLE complaints ADD COLUMN reopened_count INTEGER DEFAULT 0"),
            ("updated_at",          "ALTER TABLE complaints ADD COLUMN updated_at TEXT DEFAULT (datetime('now'))"),
            ("resolved_at",         "ALTER TABLE complaints ADD COLUMN resolved_at TEXT"),
        ]
        for col, sql in migrations:
            if col not in existing:
                try:
                    db.execute(sql)
                    print(f"[Migration] Added column: {col}")
                except Exception as e:
                    print(f"[Migration] Warning for {col}: {e}")
        # Also ensure complaint_history table exists
        db.execute("""
            CREATE TABLE IF NOT EXISTS complaint_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL,
                changed_by TEXT,
                change_type TEXT DEFAULT 'status_update',
                old_value TEXT,
                new_value TEXT,
                note TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (complaint_id) REFERENCES complaints(id)
            )
        """)
        db.commit()


def auto_delete_old_complaints():
    """Soft-delete complaints older than 30 days"""
    try:
        with sqlite3.connect(DB_PATH) as db:
            db.execute("UPDATE complaints SET deleted_at = datetime('now') WHERE deleted_at IS NULL AND created_at < datetime('now', '-30 days')")
            count = db.execute("SELECT changes()").fetchone()[0]
            if count: print(f"[Auto-delete] {count} complaints older than 30 days archived")
            db.commit()
    except Exception as e:
        print(f"[Auto-delete] Warning: {e}")

# ─── AUTH HELPERS ─────────────────────────────────────────────────────────────
def hash_password(pw): return hashlib.sha256(pw.encode()).hexdigest()
def check_password(pw, h): return hmac.compare_digest(hash_password(pw), h)

def make_token(user):
    return pyjwt.encode({'user_id':user['id'],'role':user['role'],'department':user['department'],'exp':int(time.time())+86400}, SECRET_KEY, algorithm='HS256')

def decode_token(token):
    try: return pyjwt.decode(token, SECRET_KEY, algorithms=['HS256'])
    except: return None

def get_current_user(required_roles=None):
    token = request.headers.get('Authorization','').replace('Bearer ','')
    if not token: return None, ('Token required', 401)
    data = decode_token(token)
    if not data: return None, ('Invalid or expired token', 401)
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (data['user_id'],)).fetchone()
    if not row: return None, ('User not found', 401)
    user = dict(row)
    if required_roles and user['role'] not in required_roles:
        return None, ('Insufficient permissions', 403)
    return user, None

def row_to_dict(row): return dict(row) if row else None

# ─── ML ───────────────────────────────────────────────────────────────────────
TRAINING = [
    ("pothole road crack surface broken pavement", "Roads/Public Works"),
    ("road damaged broken footpath pavement", "Roads/Public Works"),
    ("road repair needed highway divider", "Roads/Public Works"),
    ("construction debris blocking road", "Roads/Public Works"),
    ("speed breaker damaged broken road marking", "Roads/Public Works"),
    ("garbage not collected waste overflow", "Sanitation"),
    ("trash bin overflow litter dustbin full", "Sanitation"),
    ("waste dump illegal garbage heap smell", "Sanitation"),
    ("public toilet not cleaned dirty", "Sanitation"),
    ("sweeping not done dead animal removal", "Sanitation"),
    ("drain blocked flooding water logged", "Drainage/Water"),
    ("water pipe leakage burst pipeline", "Drainage/Water"),
    ("drainage overflow sewage sewer choked", "Drainage/Water"),
    ("water supply cut shortage contaminated", "Drainage/Water"),
    ("manhole open uncovered flood stagnant", "Drainage/Water"),
    ("streetlight not working dark lamp broken", "Electrical"),
    ("electric pole fallen wire hanging", "Electrical"),
    ("power outage blackout transformer fault", "Electrical"),
    ("electric shock hazard exposed wire sparking", "Electrical"),
    ("meter tampering electricity theft supply", "Electrical"),
]
_clf = Pipeline([('tfidf', TfidfVectorizer(ngram_range=(1,2))), ('lr', LogisticRegression(max_iter=500, C=5))])
_clf.fit([t[0] for t in TRAINING], [t[1] for t in TRAINING])

PRIORITY_KEYWORDS = {
    'Emergency': ['emergency','urgent','danger','hazard','shock','sparking','fire','collapse','injury','exposed wire','open manhole','gas leak','accident'],
    'High': ['severe','major','serious','critical','blocking','overflow','burst','fallen pole','completely broken','flooding','days','week'],
    'Medium': ['moderate','broken','damaged','leaking','not working','missing','cracked','blocked'],
    'Low': ['minor','small','little','slightly','faded','cosmetic','notice'],
}
POSITIVE_WORDS = {'good','great','excellent','satisfied','happy','resolved','fast','quick','awesome','perfect','thanks','helpful','nice','well'}
NEGATIVE_WORDS = {'bad','poor','terrible','horrible','dissatisfied','slow','not','never','worst','useless','pathetic','delayed','ignored','unresolved','still','pending','disappointed','unacceptable'}

def predict_category(text):
    pred = _clf.predict([text])[0]
    proba = max(_clf.predict_proba([text])[0])
    return pred, float(proba)

def predict_priority(text):
    t = text.lower()
    for p in ['Emergency','High','Medium','Low']:
        if any(k in t for k in PRIORITY_KEYWORDS[p]):
            return p
    return 'Medium'

def analyze_sentiment(text, rating=None):
    words = set(re.findall(r'\b\w+\b', (text or '').lower()))
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    text_sent = 'Positive' if pos > neg else 'Negative' if neg > pos else 'Neutral'
    if rating is not None:
        if rating >= 4: return 'Positive'
        if rating <= 2: return 'Negative'
    return text_sent

def validate_submission(desc, filename):
    if len(desc.strip()) < 20:
        return False, "Description must be at least 20 characters."
    words = re.findall(r'\b[a-zA-Z]{3,}\b', desc)
    if len(words) < 3:
        return False, "Description must contain meaningful words."
    if not filename:
        return False, "Image upload is required."
    ext = filename.rsplit('.',1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_EXT:
        return False, f"Invalid image format. Use: {', '.join(ALLOWED_EXT)}"
    return True, "OK"

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

# ─── OTP EMAIL VERIFICATION ───────────────────────────────────────────────────
@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    d = request.json or {}
    email = d.get('email','').strip().lower()
    if not email or not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'error': 'Valid email is required'}), 400
    # Check if email already registered
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        return jsonify({'error': 'Email already registered'}), 409
    # Generate 6-digit OTP
    otp_code = str(random.randint(100000, 999999))
    expires  = int(time.time()) + 600  # 10 minutes
    # Store OTP (remove old ones for this email)
    db.execute("DELETE FROM otp_store WHERE email=?", (email,))
    db.execute("INSERT INTO otp_store (email, otp, expires_at) VALUES (?,?,?)", (email, otp_code, expires))
    db.commit()
    # Send email using smtplib (Gmail)
    sent = _send_otp_email(email, otp_code)
    dev_mode = os.environ.get('DEV_MODE', 'false').lower() == 'true'
    if sent:
        # Email sent successfully — never show OTP unless DEV_MODE=true
        return jsonify({
            'message': f'OTP sent to {email}. Please check your inbox.',
            'dev_otp': otp_code if dev_mode else None
        })
    else:
        smtp_configured = bool(os.environ.get('SMTP_EMAIL') and os.environ.get('SMTP_PASSWORD') and
                               not os.environ.get('SMTP_EMAIL','').startswith('yourgmail'))
        if smtp_configured:
            # SMTP configured but failed — return error
            return jsonify({'error': 'Failed to send OTP email. Please check your SMTP settings in .env file.'}), 500
        else:
            # SMTP not configured at all — dev mode fallback
            return jsonify({
                'message': 'Email not configured. OTP shown below (dev mode only).',
                'dev_otp': otp_code
            })

@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    d = request.json or {}
    email    = d.get('email','').strip().lower()
    otp_code = d.get('otp','').strip()
    if not email or not otp_code:
        return jsonify({'error': 'Email and OTP are required'}), 400
    db = get_db()
    row = row_to_dict(db.execute(
        "SELECT * FROM otp_store WHERE email=? AND used=0 ORDER BY id DESC LIMIT 1", (email,)
    ).fetchone())
    if not row:
        return jsonify({'error': 'No OTP found. Please request a new one.'}), 400
    if int(time.time()) > row['expires_at']:
        return jsonify({'error': 'OTP has expired. Please request a new one.'}), 400
    if row['otp'] != otp_code:
        return jsonify({'error': 'Incorrect OTP. Please try again.'}), 400
    # Mark OTP as used
    db.execute("UPDATE otp_store SET used=1 WHERE id=?", (row['id'],))
    db.commit()
    return jsonify({'message': 'OTP verified successfully', 'verified': True})

def _send_otp_email(to_email, otp_code):
    """Send OTP via Gmail SMTP. Configure SMTP_EMAIL and SMTP_PASSWORD env vars."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    smtp_email = os.environ.get('SMTP_EMAIL', '')
    smtp_pass  = os.environ.get('SMTP_PASSWORD', '')
    if not smtp_email or not smtp_pass:
        print(f"[OTP] Email not configured. OTP for {to_email}: {otp_code}")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'Your Civic Resolve OTP: {otp_code}'
        msg['From']    = smtp_email
        msg['To']      = to_email
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #eee">
          <div style="background:linear-gradient(135deg,#e53935,#ff6f00);padding:28px 32px;text-align:center">
            <h1 style="color:#fff;margin:0;font-size:1.6rem">🏛️ Civic Resolve</h1>
            <p style="color:rgba(255,255,255,.85);margin:6px 0 0;font-size:.9rem">Government Issue Portal</p>
          </div>
          <div style="padding:36px 32px;text-align:center">
            <p style="color:#333;font-size:1rem;margin-bottom:8px">Your One-Time Password is:</p>
            <div style="font-size:2.8rem;font-weight:800;letter-spacing:12px;color:#e53935;padding:20px;background:#fff5f5;border-radius:10px;margin:16px 0;border:2px dashed #e53935">
              {otp_code}
            </div>
            <p style="color:#888;font-size:.84rem">Valid for <strong>10 minutes</strong>. Do not share this OTP with anyone.</p>
          </div>
          <div style="background:#f9f9f9;padding:16px 32px;text-align:center;border-top:1px solid #eee">
            <p style="color:#aaa;font-size:.75rem;margin:0">Civic Resolve · Government Digital Governance Initiative</p>
          </div>
        </div>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(smtp_email, smtp_pass)
            server.sendmail(smtp_email, to_email, msg.as_string())
        print(f"[OTP] Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"[OTP] Email failed: {e}. OTP for {to_email}: {otp_code}")
        return False

@app.route('/api/auth/register', methods=['POST'])
def register():
    d = request.json or {}
    name = d.get('name','').strip()
    email = d.get('email','').strip().lower()
    phone = d.get('phone','').strip()
    password = d.get('password','')
    if not all([name, email, phone, password]):
        return jsonify({'error':'All fields are required'}), 400
    if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        return jsonify({'error':'Invalid email format'}), 400
    if len(password) < 6:
        return jsonify({'error':'Password must be at least 6 characters'}), 400
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
        return jsonify({'error':'Email already registered'}), 409
    h = hash_password(password)
    cur = db.execute("INSERT INTO users (name,email,phone,password_hash,role,created_at) VALUES (?,?,?,?,'citizen',?)", (name,email,phone,h,ist_now()))
    db.commit()
    user = row_to_dict(db.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify({'message':'Registration successful', 'token':make_token(user), 'user':safe_user(user)}), 201

@app.route('/api/auth/login', methods=['POST'])
def login():
    d = request.json or {}
    email = d.get('email','').strip().lower()
    password = d.get('password','')
    db = get_db()
    user = row_to_dict(db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone())
    if not user or not check_password(password, user['password_hash']):
        return jsonify({'error':'Invalid email or password'}), 401
    return jsonify({'message':'Login successful', 'token':make_token(user), 'user':safe_user(user)})

@app.route('/api/auth/me', methods=['GET'])
def me():
    user, err = get_current_user()
    if err: return jsonify({'error':err[0]}), err[1]
    return jsonify(safe_user(user))

def safe_user(u):
    return {k: u[k] for k in ['id','name','email','phone','role','department'] if k in u}

# ─── COMPLAINT HELPERS ────────────────────────────────────────────────────────
def complaint_to_dict(db, c):
    if not c: return None
    d = dict(c)
    user = row_to_dict(db.execute("SELECT name,email FROM users WHERE id=?", (d['user_id'],)).fetchone())
    d['user_name']  = user['name']  if user else None
    d['user_email'] = user['email'] if user else None
    # Normalise fields so frontend always gets consistent keys
    d['title']               = d.get('title') or d.get('description','')[:60]
    if d.get('image_path','').startswith('https://'):
        d['image_url'] = d['image_path']
    else:
        d['image_url'] = None
    d['location_address']    = d.get('location_address') or d.get('address', '')
    d['department_assigned'] = d.get('department_assigned') or d.get('department', '')
    d['ml_confidence']       = d.get('ml_confidence') or 0
    d['reopened_count']      = d.get('reopened_count') or d.get('reopen_count') or 0
    # Fetch feedbacks
    fb_rows = db.execute("SELECT * FROM feedbacks WHERE complaint_id=?", (d['id'],)).fetchall()
    d['feedbacks'] = [dict(r) for r in fb_rows] if fb_rows else []
    # Fetch history
    try:
        hist = db.execute("SELECT * FROM complaint_history WHERE complaint_id=? ORDER BY created_at ASC", (d['id'],)).fetchall()
        d['history'] = [dict(r) for r in hist] if hist else []
    except:
        d['history'] = []
    # Fetch department responses
    try:
        resp_rows = db.execute("SELECT * FROM department_responses WHERE complaint_id=? ORDER BY created_at ASC", (d['id'],)).fetchall()
        d['dept_responses'] = [dict(r) for r in resp_rows] if resp_rows else []
    except:
        d['dept_responses'] = []
    # Add IST formatted times
    d['created_at_ist'] = to_ist(d.get('created_at',''))
    d['updated_at_ist'] = to_ist(d.get('updated_at',''))
    d['resolved_at_ist'] = to_ist(d.get('resolved_at','')) if d.get('resolved_at') else ''
    return d

# ─── COMPLAINT ROUTES ─────────────────────────────────────────────────────────
@app.route('/api/complaints/submit', methods=['POST'])
def submit_complaint():
    user, err = get_current_user()
    if err: return jsonify({'error':err[0]}), err[1]

    title       = request.form.get('title', '').strip()
    description = request.form.get('description','').strip()
    latitude    = request.form.get('latitude')
    longitude   = request.form.get('longitude')
    address     = request.form.get('location_address', request.form.get('address',''))
    force_priority = request.form.get('force_priority', None)

    image_saved = None
    original_filename = None

    if 'image' in request.files:
        # Fallback: local file upload
        f = request.files['image']
        if f and f.filename:
            original_filename = f.filename
            ext = f.filename.rsplit('.',1)[-1].lower() if '.' in f.filename else ''
            if ext in ALLOWED_EXT:
                fname = f"{uuid.uuid4().hex}.{ext}"
                f.save(os.path.join(UPLOAD_DIR, fname))
                image_saved = fname

    if not description or len(description.split()) < 3:
        return jsonify({'error': 'Please describe the issue in at least 3 words'}), 400

    # Combine title + description for better categorisation
    full_text = f"{title} {description}".strip()
    category, confidence = predict_category(full_text)

    # Keyword override for higher accuracy department routing
    text_lower = full_text.lower()
    KEYWORD_MAP = {
        'Roads/Public Works': ['pothole','road','pavement','footpath','highway','divider','speed breaker','crater','tar','asphalt','street repair','road damage','சாலை','குழி'],
        'Sanitation':         ['garbage','trash','waste','dustbin','litter','sweeping','clean','dirty','smell','stench','animal','dead','குப்பை','கழிவு'],
        'Drainage/Water':     ['drain','flood','water','pipe','sewage','sewer','manhole','leakage','burst','stagnant','overflow','வடிகால்','தண்ணீர்'],
        'Electrical':         ['light','lamp','electric','power','wire','pole','streetlight','transformer','voltage','sparking','blackout','மின்சாரம்','விளக்கு'],
    }
    for dept, keywords in KEYWORD_MAP.items():
        if any(k in text_lower for k in keywords):
            category = dept
            confidence = max(confidence, 0.85)
            break

    priority = force_priority if force_priority else predict_priority(full_text)
    if not title:
        title = description[:60] + ('...' if len(description) > 60 else '')

    # Add history entry on creation
    db = get_db()
    cur = db.execute(
        "INSERT INTO complaints (user_id,title,description,image_path,latitude,longitude,location_address,address,category,priority,status,department,department_assigned,ml_confidence,reopened_count) VALUES (?,?,?,?,?,?,?,?,?,?,'Pending',?,?,?,0)",
        (user['id'], title, description, image_saved,
         float(latitude) if latitude else None,
         float(longitude) if longitude else None,
         address, address, category, priority, category, category, round(confidence, 4))
    )
    new_id = cur.lastrowid
    # Insert creation history entry
    try:
        db.execute(
            "INSERT INTO complaint_history (complaint_id, changed_by, change_type, old_value, new_value, note) VALUES (?,?,?,?,?,?)",
            (new_id, user['name'], 'created', None, 'Pending', 'Complaint submitted and auto-routed by AI')
        )
    except:
        pass
    db.commit()
    complaint = complaint_to_dict(db, db.execute("SELECT * FROM complaints WHERE id=?", (cur.lastrowid,)).fetchone())
    print(f"[Civic Resolve] New complaint #{complaint['id']} → {category} dept, priority={priority}")

    return jsonify({'message':'Complaint submitted successfully', 'complaint':complaint, 'category':category, 'priority':priority, 'confidence':round(confidence*100,1)}), 201

@app.route('/api/complaints/my', methods=['GET'])
def my_complaints():
    user, err = get_current_user()
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    rows = db.execute("SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC", (user['id'],)).fetchall()
    return jsonify([complaint_to_dict(db, r) for r in rows])

@app.route('/api/complaints/<int:cid>', methods=['GET'])
def get_complaint(cid):
    user, err = get_current_user()
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    c = complaint_to_dict(db, db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    if not c: return jsonify({'error':'Not found'}), 404
    if user['role'] in ('user','citizen') and c['user_id'] != user['id']:
        return jsonify({'error':'Unauthorized'}), 403
    # Fetch feedbacks with sentiment
    fbs = []
    for r in db.execute("SELECT * FROM feedbacks WHERE complaint_id=?", (cid,)).fetchall():
        fb = dict(r)
        if 'sentiment' not in fb or not fb['sentiment']:
            fb['sentiment'] = 'Neutral'
        fbs.append(fb)
    c['feedbacks'] = fbs
    # Fetch history timeline
    try:
        hist_rows = db.execute(
            "SELECT * FROM complaint_history WHERE complaint_id=? ORDER BY created_at ASC", (cid,)
        ).fetchall()
        c['history'] = [dict(r) for r in hist_rows]
    except:
        c['history'] = []
    # Add created event to history if empty
    if not c['history']:
        c['history'] = [{
            'id': 0,
            'complaint_id': cid,
            'changed_by': c.get('user_name', 'Citizen'),
            'change_type': 'created',
            'old_value': None,
            'new_value': 'Pending',
            'note': 'Complaint submitted',
            'created_at': c.get('created_at', '')
        }]
    # Wrap in { complaint: ... } as expected by frontend
    return jsonify({'complaint': c})

@app.route('/api/complaints/<int:cid>/feedback', methods=['POST'])
def submit_feedback(cid):
    user, err = get_current_user()
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    c = row_to_dict(db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    if not c: return jsonify({'error':'Not found'}), 404
    if c['user_id'] != user['id']: return jsonify({'error':'Unauthorized'}), 403
    if c['status'] != 'Completed': return jsonify({'error':'Can only give feedback on completed complaints'}), 400

    d = request.json or {}
    rating = int(d.get('rating', 0))
    comment = d.get('comment','')
    sentiment = analyze_sentiment(comment, rating)

    db.execute("INSERT INTO feedbacks (complaint_id,user_id,rating,comment,sentiment) VALUES (?,?,?,?,?)",
               (cid, user['id'], rating, comment, sentiment))

    reopened = rating < 3 or sentiment == 'Negative'
    if reopened:
        db.execute("UPDATE complaints SET status='In Progress', reopen_count=reopen_count+1, resolved_at=NULL WHERE id=?", (cid,))
        msg = 'Feedback submitted. Complaint reopened for re-resolution.'
    else:
        msg = 'Thank you for your feedback!'
    db.commit()
    return jsonify({'message':msg, 'sentiment':sentiment, 'reopened':reopened})

@app.route('/api/complaints/image/<filename>', methods=['GET'])
def serve_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# ─── UNIFIED COMPLAINTS ROUTE (used by frontend) ──────────────────────────────
@app.route('/api/complaints', methods=['GET'])
def get_complaints():
    """Smart route: returns complaints based on user role"""
    user, err = get_current_user()
    if err: return jsonify({'error': err[0]}), err[1]
    db = get_db()
    role = user['role']
    if role in ('citizen', 'user'):
        rows = db.execute("SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC", (user['id'],)).fetchall()
    elif role == 'department':
        rows = db.execute("SELECT * FROM complaints WHERE department=? ORDER BY created_at DESC", (user['department'],)).fetchall()
    else:  # admin
        rows = db.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
    return jsonify({'complaints': [complaint_to_dict(db, r) for r in rows]})

@app.route('/api/complaints', methods=['POST'])
def submit_complaint_unified():
    """Alias for /api/complaints/submit"""
    return submit_complaint()

@app.route('/api/complaints/<int:cid>/status', methods=['PATCH', 'PUT'])
def update_complaint_status(cid):
    """Status update used by frontend — accessible by admin and department"""
    user, err = get_current_user(['department', 'admin'])
    if err: return jsonify({'error': err[0]}), err[1]
    db = get_db()
    c = db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone()
    if not c: return jsonify({'error': 'Not found'}), 404
    d = request.json or {}
    new_status = d.get('status', '').strip()
    note       = d.get('note', '').strip()
    valid = ['Pending', 'In Progress', 'Completed', 'Reopened']
    if new_status not in valid:
        return jsonify({'error': f'Invalid status. Must be one of: {", ".join(valid)}'}), 400
    old_status = dict(c).get('status', '')
    # Use safe parameterised resolved_at
    now_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    resolved_val = now_str if new_status == 'Completed' else None
    try:
        db.execute(
            "UPDATE complaints SET status=?, updated_at=?, resolved_at=? WHERE id=?",
            (new_status, now_str, resolved_val, cid)
        )
    except Exception:
        # Fallback if updated_at/resolved_at columns don't exist yet
        db.execute("UPDATE complaints SET status=? WHERE id=?", (new_status, cid))
    try:
        db.execute(
            "INSERT INTO complaint_history (complaint_id, changed_by, change_type, old_value, new_value, note) VALUES (?,?,?,?,?,?)",
            (cid, user['name'], 'status_update', old_status, new_status, note or '')
        )
    except Exception as e:
        print(f"History insert warning: {e}")
    db.commit()
    try:
        updated = complaint_to_dict(db, db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    except Exception:
        updated = {'id': cid, 'status': new_status}

    return jsonify({'message': 'Status updated successfully', 'complaint': updated})

@app.route('/api/complaints/uploads/<filename>', methods=['GET'])
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)



# --- COMPLAINT REPORT (PDF + bilingual text fallback) ---------------------
@app.route('/api/complaints/<int:cid>/report', methods=['GET'])
def download_complaint_report(cid):
    user, err = get_current_user()
    if err: return jsonify({'error': err[0]}), err[1]
    db = get_db()
    c = complaint_to_dict(db, db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    if not c: return jsonify({'error': 'Not found'}), 404
    if user['role'] in ('citizen','user') and c['user_id'] != user['id']:
        return jsonify({'error': 'Unauthorized'}), 403

    def text_report():
        sep = "=" * 60
        responses = c.get('dept_responses') or []
        resp_text = "\n".join(
            f"[{r.get('created_at','')}] {r.get('responder_name','')} ({r.get('department','')}): {r.get('message','')}"
            for r in responses
        ) or "No responses yet"
        return (
            "CIVIC RESOLVE - GOVERNMENT OF TAMIL NADU\n"
            "\u0ba8\u0b95\u0bb0\u0bbf\u0b95 \u0ba4\u0bc0\u0bb0\u0bcd\u0bb5\u0bc1 - \u0ba4\u0bae\u0bbf\u0bb4\u0bcd\u0ba8\u0bbe\u0b9f\u0bc1 \u0a85\u0bb0\u0b9a\u0bc1\n"
            + sep + "\n"
            "COMPLAINT REPORT / \u0baa\u0bc1\u0b95\u0bbe\u0bb0\u0bcd \u0a85\u0bb1\u0bbf\u0b95\u0bcd\u0b95\u0bc8\n"
            + sep + "\n\n"
            f"Complaint ID   / \u0baa\u0bc1\u0b95\u0bbe\u0bb0\u0bcd \u0b8e\u0ba3\u0bcd : #{cid}\n"
            f"Status         / \u0ba8\u0bbf\u0bb2\u0bc8     : {c.get('status','')}\n"
            f"Priority       / \u0bae\u0bc1\u0ba9\u0bcd\u0ba9\u0bc1\u0bb0\u0bbf\u0bae\u0bc8 : {c.get('priority','')}\n"
            f"Category       / \u0bb5\u0b95\u0bc8     : {c.get('category','')}\n"
            f"Department     / \u0ba4\u0bc1\u0bb1\u0bc8     : {c.get('department_assigned','')}\n"
            f"AI Confidence  :  {float(c.get('ml_confidence',0))*100:.0f}%\n\n"
            f"TITLE / \u0ba4\u0bb2\u0bc8\u0baa\u0bcd\u0baa\u0bc1:\n{c.get('title','')}\n\n"
            f"DESCRIPTION / \u0bb5\u0bbf\u0bb3\u0b95\u0bcd\u0b95\u0bae\u0bcd:\n{c.get('description','')}\n\n"
            f"LOCATION / \u0b87\u0b9f\u0bae\u0bcd:\n"
            f"  Address / \u0bae\u0bc1\u0b95\u0bb5\u0bb0\u0bbf : {c.get('location_address','Not provided')}\n"
            f"  GPS             : {c.get('latitude','')}, {c.get('longitude','')}\n\n"
            f"DATE & TIME (IST) / \u0ba4\u0bc7\u0ba4\u0bbf \u0bae\u0bb1\u0bcd\u0bb1\u0bc1\u0bae\u0bcd \u0ba8\u0bc7\u0bb0\u0bae\u0bcd:\n"
            f"  Submitted    / \u0b9a\u0bae\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bbf\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bcd\u0b9f\u0ba4\u0bc1 : {c.get('created_at_ist', c.get('created_at',''))}\n"
            f"  Last Updated / \u0b95\u0b9f\u0bc8\u0b9a\u0bbf \u0bae\u0bbe\u0bb1\u0bcd\u0bb1\u0bae\u0bcd        : {c.get('updated_at_ist', c.get('updated_at',''))}\n"
            f"  Resolved At  / \u0ba4\u0bc0\u0bb0\u0bcd\u0bb5\u0bc1 \u0ba8\u0bc7\u0bb0\u0bae\u0bcd           : {c.get('resolved_at_ist','Not resolved yet')}\n\n"
            f"CITIZEN / \u0b95\u0bc1\u0b9f\u0bbf\u0bae\u0b95\u0ba9\u0bcd:\n"
            f"  Name  / \u0baa\u0bc6\u0baf\u0bb0\u0bcd : {c.get('user_name','')}\n"
            f"  Email / \u0bae\u0bbf\u0ba9\u0bcd\u0ba9\u0b9e\u0bcd\u0b9a\u0bb2\u0bcd : {c.get('user_email','')}\n\n"
            f"DEPARTMENT RESPONSES / \u0ba4\u0bc1\u0bb1\u0bc8 \u0baa\u0ba4\u0bbf\u0bb2\u0bcd\u0b95\u0bb3\u0bcd:\n{resp_text}\n\n"
            + sep + "\n"
            f"Generated / \u0b89\u0bb0\u0bc1\u0bb5\u0bbe\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bcd\u0b9f\u0ba4\u0bc1 : {ist_now()} IST\n"
            f"Report ID : CR-{cid:04d}\n"
            "Official document from Civic Resolve Portal.\n"
            "\u0b87\u0ba4\u0bc1 Civic Resolve \u0b87\u0ba3\u0bc8\u0baf\u0ba4\u0bb3\u0ba4\u0bcd\u0ba4\u0bbf\u0ba9\u0bcd \u0a85\u0ba4\u0bbf\u0b95\u0bbe\u0bb0\u0baa\u0bc2\u0bb0\u0bcd\u0bb5 \u0b86\u0bb5\u0ba3\u0bae\u0bcd.\n"
            + sep + "\n"
        )

    try:
        from reportlab.pdfgen import canvas as rc
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.colors import HexColor
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import io

        FP = '/usr/share/fonts/truetype/dejavu/'
        try:
            pdfmetrics.registerFont(TTFont('DV', FP + 'DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DVB', FP + 'DejaVuSans-Bold.ttf'))
            F, FB = 'DV', 'DVB'
        except Exception:
            F = FB = 'Helvetica'

        TEAL    = HexColor('#0D4F6C')
        SAFFRON = HexColor('#D4891A')
        IVORY   = HexColor('#E8F4F8')
        DARK    = HexColor('#1A1A2A')
        GRAY    = HexColor('#555555')
        WHITE   = HexColor('#FFFFFF')
        SUCCESS = HexColor('#1D6B3E')
        WARNING_C = HexColor('#8A4A0A')
        DANGER_C  = HexColor('#8B1D1D')

        buf = io.BytesIO()
        W, H = A4
        cv = rc.Canvas(buf, pagesize=A4)
        cv.setTitle(f"Civic Resolve - Complaint #{cid}")

        # Header banner
        cv.setFillColor(TEAL); cv.rect(0, H-82, W, 82, fill=1, stroke=0)
        cv.setFillColor(SAFFRON); cv.rect(0, H-86, W, 4, fill=1, stroke=0)

        # Emblem circle
        cv.setFillColor(SAFFRON); cv.circle(42, H-41, 20, fill=1, stroke=0)
        cv.setFillColor(WHITE); cv.setFont(FB, 11)
        cv.drawCentredString(42, H-46, 'CR')

        # Header text
        cv.setFillColor(WHITE)
        cv.setFont(FB, 15); cv.drawString(72, H-30, 'CIVIC RESOLVE')
        cv.setFont(F, 9);   cv.drawString(72, H-44, 'Government Issue Portal / \u0ba8\u0b95\u0bb0\u0bbf\u0b95 \u0baa\u0bbf\u0bb0\u0b9a\u0bcd\u0b9a\u0bbf\u0ba9\u0bc8 \u0ba4\u0bc0\u0bb0\u0bcd\u0bb5\u0bc1 \u0ba4\u0bb3\u0bae\u0bcd')
        cv.setFont(F, 8);   cv.drawString(72, H-57, 'Government of Tamil Nadu / \u0ba4\u0bae\u0bbf\u0bb4\u0bcd\u0ba8\u0bbe\u0b9f\u0bc1 \u0a85\u0bb0\u0b9a\u0bc1')

        # Top right
        cv.setFont(FB, 9); cv.setFillColor(SAFFRON)
        cv.drawRightString(W-18, H-28, 'OFFICIAL COMPLAINT REPORT')
        cv.setFont(F, 8); cv.setFillColor(WHITE)
        cv.drawRightString(W-18, H-41, f'Report ID: CR-{cid:04d}')
        cv.drawRightString(W-18, H-53, f'Generated: {ist_now()} IST')

        y = H - 100

        # Status badges row
        status = c.get('status','')
        sc = SUCCESS if status=='Completed' else DANGER_C if status=='Reopened' else WARNING_C if status=='Pending' else TEAL
        priority = c.get('priority','Medium')
        pc = DANGER_C if priority=='Emergency' else WARNING_C if priority=='High' else TEAL

        # Complaint ID box
        cv.setFillColor(TEAL); cv.roundRect(18, y-30, 150, 34, 6, fill=1, stroke=0)
        cv.setFillColor(WHITE); cv.setFont(FB, 12)
        cv.drawString(28, y-17, f'Complaint # {cid}')

        # Status box
        cv.setFillColor(sc); cv.roundRect(178, y-30, 110, 34, 6, fill=1, stroke=0)
        cv.setFillColor(WHITE); cv.setFont(FB, 11)
        cv.drawCentredString(233, y-17, status.upper())

        # Priority box
        cv.setFillColor(pc); cv.roundRect(298, y-30, 90, 34, 6, fill=1, stroke=0)
        cv.setFillColor(WHITE); cv.setFont(F, 10)
        cv.drawCentredString(343, y-17, priority)

        # Category
        cv.setFillColor(IVORY); cv.roundRect(398, y-30, 180, 34, 6, fill=1, stroke=0)
        cv.setFillColor(TEAL); cv.setFont(F, 9)
        cv.drawCentredString(488, y-17, c.get('category','') or 'General')

        y -= 50

        # Section helper
        def sec(title, y):
            cv.setFillColor(IVORY); cv.rect(18, y-8, W-36, 26, fill=1, stroke=0)
            cv.setFillColor(TEAL);  cv.rect(18, y-8, 4, 26, fill=1, stroke=0)
            cv.setFont(FB, 10); cv.setFillColor(TEAL)
            cv.drawString(30, y+4, title)
            return y - 34

        def row(lbl, val, y, indent=28):
            cv.setFont(FB, 8); cv.setFillColor(GRAY)
            cv.drawString(indent, y, lbl + ':')
            cv.setFont(F, 9); cv.setFillColor(DARK)
            # simple wrap
            val = str(val) if val else '-'
            max_chars = 85
            lines = [val[i:i+max_chars] for i in range(0, min(len(val), max_chars*3), max_chars)]
            for i, ln in enumerate(lines[:3]):
                cv.drawString(indent + 140, y - i*13, ln)
            return y - max(len(lines), 1)*13 - 8

        y = sec('COMPLAINT DETAILS  /  \u0baa\u0bc1\u0b95\u0bbe\u0bb0\u0bcd \u0bb5\u0bbf\u0bb5\u0bb0\u0b99\u0bcd\u0b95\u0bb3\u0bcd', y)
        y = row('Title / \u0ba4\u0bb2\u0bc8\u0baa\u0bcd\u0baa\u0bc1', c.get('title',''), y)
        y = row('Department / \u0ba4\u0bc1\u0bb1\u0bc8', c.get('department_assigned',''), y)
        y = row('AI Confidence', f"{float(c.get('ml_confidence',0))*100:.0f}%", y)

        y -= 4
        y = sec('DESCRIPTION  /  \u0bb5\u0bbf\u0bb3\u0b95\u0bcd\u0b95\u0bae\u0bcd', y)
        desc = c.get('description','')
        cv.setFillColor(HexColor('#F4F3EE'))
        cv.rect(22, y-52, W-44, 58, fill=1, stroke=0)
        cv.setFont(F, 9); cv.setFillColor(DARK)
        chunk = 95
        lines_d = [desc[i:i+chunk] for i in range(0, min(len(desc), chunk*3), chunk)]
        for i, ln in enumerate(lines_d[:3]):
            cv.drawString(28, y-14-i*14, ln)
        y -= 70

        y = sec('LOCATION  /  \u0b87\u0b9f\u0bae\u0bcd', y)
        y = row('Address / \u0bae\u0bc1\u0b95\u0bb5\u0bb0\u0bbf', c.get('location_address','Not provided'), y)
        y = row('GPS Coordinates', f"{c.get('latitude','N/A')}, {c.get('longitude','N/A')}", y)

        y -= 4
        y = sec('DATE & TIME (IST)  /  \u0ba4\u0bc7\u0ba4\u0bbf \u0bae\u0bb1\u0bcd\u0bb1\u0bc1\u0bae\u0bcd \u0ba8\u0bc7\u0bb0\u0bae\u0bcd', y)
        y = row('Submitted / \u0b9a\u0bae\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bbf\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bcd\u0b9f\u0ba4\u0bc1', c.get('created_at_ist', c.get('created_at','')), y)
        y = row('Last Updated / \u0b95\u0b9f\u0bc8\u0b9a\u0bbf \u0bae\u0bbe\u0bb1\u0bcd\u0bb1\u0bae\u0bcd', c.get('updated_at_ist', c.get('updated_at','')), y)
        if c.get('resolved_at_ist'):
            y = row('Resolved At / \u0ba4\u0bc0\u0bb0\u0bcd\u0bb5\u0bc1 \u0ba8\u0bc7\u0bb0\u0bae\u0bcd', c.get('resolved_at_ist',''), y)

        y -= 4
        y = sec('CITIZEN INFORMATION  /  \u0bae\u0bc1\u0bb1\u0bc8\u0baf\u0bbf\u0b9f\u0bb5\u0bb0\u0bcd \u0bb5\u0bbf\u0bb5\u0bb0\u0bae\u0bcd', y)
        y = row('Name / \u0baa\u0bc6\u0baf\u0bb0\u0bcd', c.get('user_name',''), y)
        y = row('Email / \u0bae\u0bbf\u0ba9\u0bcd\u0ba9\u0b9e\u0bcd\u0b9a\u0bb2\u0bcd', c.get('user_email',''), y)

        # Dept responses
        responses = c.get('dept_responses') or []
        if responses and y > 130:
            y -= 4
            y = sec('DEPARTMENT RESPONSES  /  \u0ba4\u0bc1\u0bb1\u0bc8 \u0baa\u0ba4\u0bbf\u0bb2\u0bcd\u0b95\u0bb3\u0bcd', y)
            for r in responses[:2]:
                if y < 120: break
                cv.setFont(FB, 8); cv.setFillColor(TEAL)
                cv.drawString(28, y, f"{r.get('responder_name','')} ({r.get('department','')}) - {r.get('created_at','')}")
                y -= 12
                cv.setFont(F, 9); cv.setFillColor(DARK)
                msg = str(r.get('message',''))[:100]
                cv.drawString(28, y, msg)
                y -= 18

        # Footer
        cv.setStrokeColor(SAFFRON); cv.setLineWidth(1.5)
        cv.line(18, 65, W-18, 65)
        cv.setFont(FB, 8); cv.setFillColor(TEAL)
        cv.drawString(18, 52, 'Civic Resolve \u2014 Government of Tamil Nadu / \u0ba4\u0bae\u0bbf\u0bb4\u0bcd\u0ba8\u0bbe\u0b9f\u0bc1 \u0a85\u0bb0\u0b9a\u0bc1')
        cv.setFont(F, 7.5); cv.setFillColor(GRAY)
        cv.drawString(18, 38, 'This is an official computer-generated document. / \u0b87\u0ba4\u0bc1 \u0b92\u0bb0\u0bc1 \u0a85\u0ba4\u0bbf\u0b95\u0bbe\u0bb0\u0baa\u0bc2\u0bb0\u0bcd\u0bb5 \u0bae\u0bc6\u0baf\u0bcd\u0ba8\u0bc1\u0bb3\u0bcd \u0b86\u0bb5\u0ba3\u0bae\u0bcd.')
        cv.drawString(18, 25, f'Generated: {ist_now()} IST  |  ID: CR-{cid:04d}  |  Digital Governance / \u0bae\u0bbf\u0ba9\u0bcd\u0ba9\u0bbf\u0baf\u0bb2\u0bcd \u0a86\u0b9f\u0bcd\u0b9a\u0bbf')
        cv.setFont(F, 7.5)
        cv.drawRightString(W-18, 25, 'Page 1 of 1')

        cv.save()
        buf.seek(0)
        from flask import Response as FR
        return FR(
            buf.read(),
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="Civic_Resolve_Complaint_{cid}.pdf"',
                     'Content-Type': 'application/pdf'}
        )

    except Exception as e:
        print(f"[Report] PDF error: {e}")
        txt = text_report()
        from flask import Response as FR
        return FR(txt.encode('utf-8'), mimetype='text/plain; charset=utf-8',
                  headers={'Content-Disposition': f'attachment; filename="Complaint_{cid}_Report.txt"'})


@app.route('/api/complaints/analytics/summary', methods=['GET'])
def analytics_summary():
    user, err = get_current_user(['admin', 'department'])
    if err: return jsonify({'error': err[0]}), err[1]
    db = get_db()

    if user['role'] == 'department':
        base = "WHERE department=?"
        params = (user['department'],)
    else:
        base = ""
        params = ()

    total = db.execute(f"SELECT COUNT(*) FROM complaints {base}", params).fetchone()[0]

    by_status = {}
    for row in db.execute(f"SELECT status, COUNT(*) as cnt FROM complaints {base} GROUP BY status", params).fetchall():
        by_status[row['status']] = row['cnt']

    by_priority = {}
    for row in db.execute(f"SELECT priority, COUNT(*) as cnt FROM complaints {base} GROUP BY priority", params).fetchall():
        by_priority[row['priority']] = row['cnt']

    by_category = {}
    for row in db.execute(f"SELECT category, COUNT(*) as cnt FROM complaints {base} GROUP BY category", params).fetchall():
        if row['category']:
            by_category[row['category']] = row['cnt']

    by_dept = {}
    for row in db.execute(f"SELECT department, COUNT(*) as cnt FROM complaints {base} GROUP BY department", params).fetchall():
        if row['department']:
            by_dept[row['department']] = row['cnt']

    fb = db.execute("SELECT AVG(rating) as avg FROM feedbacks").fetchone()
    avg_rating = round(fb['avg'], 1) if fb and fb['avg'] else None

    return jsonify({
        'total_complaints': total,
        'by_status':        by_status,
        'by_priority':      by_priority,
        'by_category':      by_category,
        'by_department':    by_dept,
        'average_rating':   avg_rating,
    })


# ─── OTP ROUTES (Fast2SMS) ────────────────────────────────────────────────────

@app.route('/api/department/complaints', methods=['GET'])
def dept_complaints():
    user, err = get_current_user(['department','admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    dept = user['department'] if user['role'] == 'department' else request.args.get('department')
    if dept:
        rows = db.execute("SELECT * FROM complaints WHERE department=? ORDER BY created_at DESC", (dept,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM complaints ORDER BY created_at DESC").fetchall()
    priority_order = {'Emergency':0,'High':1,'Medium':2,'Low':3}
    result = [complaint_to_dict(db, r) for r in rows]
    result.sort(key=lambda c: priority_order.get(c.get('priority','Medium'), 99))
    return jsonify(result)

@app.route('/api/department/complaints/<int:cid>/status', methods=['PUT'])
def update_status(cid):
    user, err = get_current_user(['department','admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    c = row_to_dict(db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    if not c: return jsonify({'error':'Not found'}), 404
    if user['role'] == 'department' and c['department'] != user['department']:
        return jsonify({'error':'Unauthorized'}), 403

    new_status = (request.json or {}).get('status')
    if new_status not in ['Pending','In Progress','Completed']:
        return jsonify({'error':'Invalid status'}), 400

    resolved_at = datetime.utcnow().isoformat() if new_status == 'Completed' else None
    db.execute("UPDATE complaints SET status=?, updated_at=datetime('now'), resolved_at=? WHERE id=?",
               (new_status, resolved_at, cid))
    db.commit()
    updated = complaint_to_dict(db, db.execute("SELECT * FROM complaints WHERE id=?", (cid,)).fetchone())
    return jsonify({'message':'Status updated', 'complaint':updated})

@app.route('/api/department/stats', methods=['GET'])
def dept_stats():
    user, err = get_current_user(['department','admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    dept = user['department'] if user['role'] == 'department' else None
    if dept:
        rows = db.execute("SELECT * FROM complaints WHERE department=?", (dept,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM complaints").fetchall()
    rows = [dict(r) for r in rows]
    statuses = {}; priorities = {}
    for c in rows:
        statuses[c['status']] = statuses.get(c['status'],0)+1
        priorities[c['priority']] = priorities.get(c['priority'],0)+1
    resolved = [c for c in rows if c.get('resolved_at') and c.get('created_at')]
    avg_time = None
    if resolved:
        def hours(c):
            try:
                a = datetime.fromisoformat(c['created_at'])
                b = datetime.fromisoformat(c['resolved_at'])
                return (b-a).total_seconds()/3600
            except: return 0
        times = [hours(c) for c in resolved]
        avg_time = round(sum(times)/len(times), 1) if times else None
    return jsonify({'total':len(rows), 'statuses':statuses, 'priorities':priorities, 'avg_resolution_hours':avg_time})

# ─── ADMIN ROUTES ─────────────────────────────────────────────────────────────
@app.route('/api/admin/complaints', methods=['GET'])
def admin_complaints():
    user, err = get_current_user(['admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    wheres = []; params = []
    for k in ['status','category','priority']:
        v = request.args.get(k)
        if v: wheres.append(f"{k}=?"); params.append(v)
    sql = "SELECT * FROM complaints" + (" WHERE " + " AND ".join(wheres) if wheres else "") + " ORDER BY created_at DESC"
    rows = db.execute(sql, params).fetchall()
    result = []
    for r in rows:
        c = complaint_to_dict(db, r)
        c['feedbacks'] = [dict(f) for f in db.execute("SELECT * FROM feedbacks WHERE complaint_id=?", (c['id'],)).fetchall()]
        result.append(c)
    return jsonify(result)

@app.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    user, err = get_current_user(['admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    rows = [dict(r) for r in db.execute("SELECT * FROM complaints").fetchall()]
    total = len(rows)
    by_cat = {}; by_pri = {}; by_st = {}; by_dept = {}
    for c in rows:
        by_cat[c['category']] = by_cat.get(c['category'],0)+1
        by_pri[c['priority']] = by_pri.get(c['priority'],0)+1
        by_st[c['status']] = by_st.get(c['status'],0)+1
        by_dept[c['department']] = by_dept.get(c['department'],0)+1

    completed = by_st.get('Completed',0)
    resolution_rate = round(completed/total*100,1) if total else 0
    resolved = [c for c in rows if c.get('resolved_at') and c.get('created_at')]
    avg_time = None
    if resolved:
        def hrs(c):
            try: return (datetime.fromisoformat(c['resolved_at'])-datetime.fromisoformat(c['created_at'])).total_seconds()/3600
            except: return 0
        avg_time = round(sum(hrs(c) for c in resolved)/len(resolved), 1)

    fbs = db.execute("SELECT rating FROM feedbacks WHERE rating IS NOT NULL").fetchall()
    avg_rating = round(sum(f['rating'] for f in fbs)/len(fbs), 1) if fbs else None

    return jsonify({'total':total,'by_category':by_cat,'by_priority':by_pri,'by_status':by_st,
                    'by_department':by_dept,'resolution_rate':resolution_rate,
                    'avg_resolution_hours':avg_time,'total_feedbacks':len(fbs),'avg_rating':avg_rating})

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    user, err = get_current_user(['admin'])
    if err: return jsonify({'error':err[0]}), err[1]
    db = get_db()
    rows = db.execute("SELECT id,name,email,phone,role,created_at FROM users WHERE role IN ('user','citizen')").fetchall()
    return jsonify([dict(r) for r in rows])

# ─── INIT & RUN ───────────────────────────────────────────────────────────────
with app.app_context():
    init_db()
    migrate_db()
    auto_delete_old_complaints()


if __name__ == '__main__':
    # Supports Railway (PORT), Zoho Catalyst (X_ZOHO_CATALYST_LISTEN_PORT), and local (5000)
    port = int(os.environ.get('X_ZOHO_CATALYST_LISTEN_PORT',
               os.environ.get('PORT', 5000)))
    debug = os.environ.get('FLASK_ENV', 'production') != 'production'
    print(f"🚀 Civic Resolve Backend starting on port {port}")
    # Config check
    smtp_ok = (os.environ.get('SMTP_EMAIL','').strip() and
               not os.environ.get('SMTP_EMAIL','').startswith('your-actual') and
               not os.environ.get('SMTP_EMAIL','').startswith('yourgmail') and
               os.environ.get('SMTP_PASSWORD','').strip() and
               not os.environ.get('SMTP_PASSWORD','').startswith('your-16') and
               not os.environ.get('SMTP_PASSWORD','').startswith('xxxx'))
    dev_mode = os.environ.get('DEV_MODE','false').lower() == 'true'
    print(f"   📧 Email OTP: {'✅ Gmail SMTP configured' if smtp_ok else '⚠️  Not configured — OTP shown on screen (dev mode)'}")
    if dev_mode:
        print("   ⚠️  DEV_MODE=true — OTP shown on screen. Set DEV_MODE=false for production.")
    app.run(debug=debug, host='0.0.0.0', port=port)
