import subprocess
import sys

subprocess.check_call([sys.executable, "-m", "pip", "install", "flask", "google-genai", "gunicorn"])

app = Flask(__name__)
app.secret_key = "solace-super-secret-key-2025"

# =============================================
# SETUP: Put your Google AI Studio API key here
# Get it free from: https://aistudio.google.com/
# =============================================
GOOGLE_API_KEY = "AIzaSyD5Ad3Fi1bkKbe0CmXjybC247CPw43qE-Q"

client = genai.Client(api_key=GOOGLE_API_KEY)

# ══════════════════════════════════════════════
# DATABASE SETUP (SQLite)
# ══════════════════════════════════════════════
DB_FILE = "solace.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        name TEXT,
        gender TEXT,
        language TEXT DEFAULT 'both',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS mood_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        mood INTEGER,
        note TEXT,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        entry TEXT,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        timestamp TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        last_date TEXT,
        count INTEGER DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )''')

    conn.commit()
    conn.close()
    print("✅ Database ready!")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_id():
    return session.get("user_id")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_user_id():
            return jsonify({"error": "Not logged in"}), 401
    return decorated

# ══════════════════════════════════════════════
# CONTENT DATA
# ══════════════════════════════════════════════
JOURNAL_PROMPTS = [
    "আজকে একটা ছোট্ট জিনিস কী ছিল যেটা তোমাকে শান্তি দিয়েছে? / What small thing brought you comfort today?",
    "সম্প্রতি কোন মুহূর্তে তুমি শান্তি অনুভব করেছিলে? / Describe a moment you felt at peace recently.",
    "কোন নেতিবাচক চিন্তাটাকে একটু ভালোভাবে দেখতে পারো? / What negative thought can you challenge with kindness?",
    "আজকে তোমার শরীর তোমার জন্য কী কী করেছে? / List 3 things your body did for you today.",
    "তোমার মতো অনুভব করছে এমন বন্ধুকে কী বলতে? / What would you say to a friend feeling like you?",
    "আগামীকাল ভালো থাকার জন্য একটা ছোট পদক্ষেপ কী হতে পারে? / What tiny step could you take tomorrow?",
    "কোন স্মৃতিটা তোমাকে নিরাপদ ও ভালোবাসা অনুভব করায়? / Describe a memory that makes you feel safe.",
]

AFFIRMATIONS = [
    "তুমি ঠিক যেমন আছো, তেমনভাবেই ভালোবাসা ও সম্মানের যোগ্য। / You are worthy of love exactly as you are.",
    "এই অনুভূতি সাময়িক। তুমি আগেও কঠিন দিন পার করেছো। / This feeling is temporary. You've survived hard days before.",
    "নিখুঁত হওয়া জরুরি নয়। এগিয়ে যাওয়াটাই যথেষ্ট। / You don't have to be perfect. Progress is enough.",
    "সাহায্য চাওয়া দুর্বলতা নয়, এটা সাহস। / Asking for help is courage, not weakness.",
    "তোমার অনুভূতিগুলো বৈধ। তুমি একা নও। / Your feelings are valid. You are not alone.",
    "ছোট পদক্ষেপও তোমাকে এগিয়ে নিয়ে যায়। / Small steps still move you forward.",
    "তুমি যতটা ভাবো তার চেয়ে অনেক বেশি গুরুত্বপূর্ণ। / You matter more than you know.",
]

# ══════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════
@app.route("/")
def index():
    if not get_user_id():
        return render_template("auth.html")
    return render_template("index.html",
        journal_prompt=JOURNAL_PROMPTS[datetime.now().day % len(JOURNAL_PROMPTS)],
        affirmation=AFFIRMATIONS[datetime.now().day % len(AFFIRMATIONS)]
    )

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    name = data.get("name", "").strip()
    gender = data.get("gender", "other")
    language = data.get("language", "both")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO users (username, password, name, gender, language) VALUES (?,?,?,?,?)",
            (username, hash_password(password), name, gender, language)
        )
        conn.commit()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        session["user_id"] = user["id"]
        session["username"] = username
        session["name"] = name
        session["gender"] = gender
        session["language"] = language
        return jsonify({"success": True, "name": name})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already taken! Try another."}), 400


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (username, hash_password(password))
    ).fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "ভুল username বা password / Wrong username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["name"] = user["name"]
    session["gender"] = user["gender"]
    session["language"] = user["language"]
    return jsonify({"success": True, "name": user["name"], "gender": user["gender"], "language": user["language"]})


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/get_session")
def get_session_info():
    if not get_user_id():
        return jsonify({"logged_in": False})
    return jsonify({
        "logged_in": True,
        "name": session.get("name"),
        "gender": session.get("gender"),
        "language": session.get("language"),
        "username": session.get("username")
    })

# ══════════════════════════════════════════════
# STREAK
# ══════════════════════════════════════════════
def update_streak(user_id):
    conn = get_db()
    today = str(date.today())
    yesterday = str(date.fromordinal(date.today().toordinal() - 1))
    row = conn.execute("SELECT * FROM streaks WHERE user_id=?", (user_id,)).fetchone()

    if not row:
        conn.execute("INSERT INTO streaks (user_id, last_date, count) VALUES (?,?,1)", (user_id, today))
        count = 1
    elif row["last_date"] == today:
        count = row["count"]
    elif row["last_date"] == yesterday:
        count = row["count"] + 1
        conn.execute("UPDATE streaks SET last_date=?, count=? WHERE user_id=?", (today, count, user_id))
    else:
        count = 1
        conn.execute("UPDATE streaks SET last_date=?, count=1 WHERE user_id=?", (today, user_id))

    conn.commit()
    conn.close()
    return count

@app.route("/get_streak")
def get_streak():
    uid = get_user_id()
    if not uid:
        return jsonify({"count": 0})
    count = update_streak(uid)
    return jsonify({"count": count})

# ══════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════
@app.route("/chat", methods=["POST"])
def chat():
    uid = get_user_id()
    if not uid:
        return jsonify({"reply": "Please log in first."}), 401

    req = request.json
    user_message = req.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty"}), 400

    gender = session.get("gender", "")
    language = session.get("language", "both")
    name = session.get("name", "friend")

    # Get recent chat history from DB
    conn = get_db()
    history = conn.execute(
        "SELECT role, content FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT 10",
        (uid,)
    ).fetchall()
    conn.close()

    history_text = ""
    if history:
        history_text = "Recent conversation:\n" + "\n".join(
            [f"{h['role'].upper()}: {h['content']}" for h in reversed(history)]
        )

    # Language instruction
    if language == "bengali":
        lang_inst = "সবসময় বাংলায় উত্তর দাও।"
    elif language == "both":
        lang_inst = "বাংলা এবং ইংরেজি উভয়ে উত্তর দাও।"
    else:
        lang_inst = "Always respond in English."

    # Gender instruction
    if gender == "male":
        gender_inst = f"User is male. Call them '{name} ভাই' warmly."
    elif gender == "female":
        gender_inst = f"User is female. Call them '{name} আপু' warmly."
    else:
        gender_inst = f"Call the user '{name}'."

    system_prompt = f"""You are Solace, a compassionate mental health AI companion.
{gender_inst}
{lang_inst}
- Listen with deep empathy, no judgment
- Use past conversation to give personalized, improving advice over time
- Offer gentle CBT/mindfulness strategies
- Never diagnose or prescribe
- Auto-understand typos and spelling mistakes silently
- If suicidal thoughts expressed, immediately recommend crisis helpline
- Keep responses warm, 2-4 sentences

{history_text}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=f"{system_prompt}\n\nUser: {user_message}"
        )
        reply = response.text

        # Save to DB
        conn = get_db()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?,?,?,?)",
                     (uid, "user", user_message, now))
        conn.execute("INSERT INTO chat_history (user_id, role, content, timestamp) VALUES (?,?,?,?)",
                     (uid, "solace", reply, now))
        conn.commit()
        conn.close()
        return jsonify({"reply": reply})

    except Exception as e:
        print("Chat error:", e)
        return jsonify({"reply": "আমি এখানে আছি। / I'm here with you. Please try again. 💙"})


@app.route("/get_chat_history")
def get_chat_history():
    uid = get_user_id()
    if not uid:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content, timestamp FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT 30",
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])

# ══════════════════════════════════════════════
# MOOD
# ══════════════════════════════════════════════
@app.route("/log_mood", methods=["POST"])
def log_mood():
    uid = get_user_id()
    if not uid:
        return jsonify({"error": "Not logged in"}), 401

    req = request.json
    mood_value = req.get("mood", 5)
    note = req.get("note", "")
    language = session.get("language", "both")

    conn = get_db()
    conn.execute("INSERT INTO mood_log (user_id, mood, note, timestamp) VALUES (?,?,?,?)",
                 (uid, mood_value, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

    ctx = "very low / অনেক খারাপ" if mood_value <= 3 else ("okay / মোটামুটি" if mood_value <= 6 else "good / ভালো")
    lang_note = "Respond in Bengali and English." if language == "both" else ("Respond in Bengali." if language == "bengali" else "Respond in English.")

    try:
        prompt = f"Someone rated mood {mood_value}/10 ({ctx}). Give one warm, practical 1-2 sentence coping tip. {lang_note}"
        response = client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)
        tip = response.text
    except Exception as e:
        print("Mood error:", e)
        tip = "নিজের প্রতি সদয় হও। / Be gentle with yourself today. 💙"

    return jsonify({"tip": tip, "logged": True})


@app.route("/get_mood_data")
def get_mood_data():
    uid = get_user_id()
    if not uid:
        return jsonify([])
    conn = get_db()
    rows = conn.execute(
        "SELECT mood, note, timestamp FROM mood_log WHERE user_id=? ORDER BY id DESC LIMIT 14",
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])

# ══════════════════════════════════════════════
# JOURNAL
# ══════════════════════════════════════════════
@app.route("/save_journal", methods=["POST"])
def save_journal():
    uid = get_user_id()
    if not uid:
        return jsonify({"error": "Not logged in"}), 401

    req = request.json
    entry_text = req.get("entry", "").strip()
    if not entry_text:
        return jsonify({"feedback": ""}), 200

    language = session.get("language", "both")
    lang_note = "Respond in Bengali and English." if language == "both" else ("Respond in Bengali." if language == "bengali" else "Respond in English.")

    conn = get_db()
    conn.execute("INSERT INTO journal_entries (user_id, entry, timestamp) VALUES (?,?,?)",
                 (uid, entry_text, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

    try:
        prompt = f"""Journal entry from someone on a mental health journey:
"{entry_text}"
Write 2-3 warm therapeutic sentences: acknowledge, gentle reframe, encouragement. {lang_note}"""
        response = client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)
        return jsonify({"feedback": response.text, "saved": True})
    except Exception as e:
        print("Journal error:", e)
        return jsonify({"feedback": "লেখার জন্য সাহস দেখিয়েছো। / You showed up for yourself today. 🌱", "saved": True})

# ══════════════════════════════════════════════
# COPING
# ══════════════════════════════════════════════
@app.route("/get_coping_tip", methods=["POST"])
def get_coping_tip():
    req = request.json
    category = req.get("category", "general")
    language = session.get("language", "both")
    lang_note = "Respond in Bengali and English." if language == "both" else ("Respond in Bengali." if language == "bengali" else "Respond in English.")

    prompts = {
        "breathing": f"Simple breathing/grounding exercise for anxiety. {lang_note}",
        "sleep": f"One practical sleep tip for depression. {lang_note}",
        "movement": f"One gentle low-effort activity for low-energy depression. {lang_note}",
        "social": f"One tiny social connection step for isolated person with depression. {lang_note}",
        "general": f"One evidence-based coping technique for depression. {lang_note}"
    }
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-lite",
            contents=prompts.get(category, prompts["general"])
        )
        return jsonify({"tip": response.text})
    except Exception as e:
        print("Coping error:", e)
        return jsonify({"tip": "৪ গুণে শ্বাস নাও, ৪ ধরো, ৬ গুণে ছাড়ো। / Breathe in 4, hold 4, out 6. 💙"})

# ══════════════════════════════════════════════
# ASSESSMENT
# ══════════════════════════════════════════════
@app.route("/assessment", methods=["POST"])
def assessment():
    req = request.json
    answers = req.get("answers", {})
    assessment_type = req.get("type", "anxiety")
    language = session.get("language", "both")
    lang_note = "Respond in Bengali and English." if language == "both" else ("Respond in Bengali." if language == "bengali" else "Respond in English.")

    try:
        prompt = f"""Based on {assessment_type} assessment answers: {json.dumps(answers)}
Provide: 1) gentle score interpretation (mild/moderate/severe), 2) 2-3 personalized recommendations, 3) whether professional help is advised.
Warm, non-clinical tone. {lang_note}"""
        response = client.models.generate_content(model="gemini-2.0-flash-lite", contents=prompt)
        return jsonify({"result": response.text})
    except Exception as e:
        print("Assessment error:", e)
        return jsonify({"result": "তোমার উত্তরগুলো গুরুত্বপূর্ণ। / Your answers matter. Please consider speaking to a professional. 💙"})


# ══════════════════════════════════════════════
# RUN
# ══════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    print("\n🌿 Solace v3 - Mental Wellness App")
    print("=" * 45)
    print("⚠️  Add your Google API key in app.py!")
    print("📌 Get free key: https://aistudio.google.com/")
    print("=" * 45)
    print("🚀 Open browser: http://localhost:5000\n")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
