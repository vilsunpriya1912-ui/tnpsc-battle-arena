import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room, emit
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import pandas as pd
import anthropic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_CSV = os.path.join(BASE_DIR, 'data', 'questions.csv')

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def generate_ai_reply(question, user_message):
    if not ai_client:
        if 'note' in user_message.lower():
            return generate_full_notes(question)
        return generate_explanation(question)

    prompt = f"""You are LABI, a friendly TNPSC exam prep assistant.
Question: {question['question']}
Options: A) {question['option_a']}  B) {question['option_b']}  C) {question['option_c']}  D) {question['option_d']}
Correct answer: Option {question['answer']}
Student asked: "{user_message}"

Give a short, clear explanation (3-4 sentences) of why the correct answer is right, useful for a TNPSC exam aspirant. Keep it simple."""

    try:
        response = ai_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=250,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception:
        return generate_explanation(question)
import random
import string

app = Flask(__name__)
app.secret_key = "tnpsc_battle_arena_secret_key"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///battle_arena.db'
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------------- DATABASE MODELS ----------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    dob = db.Column(db.String(20))
    xp = db.Column(db.Integer, default=0)
    coins = db.Column(db.Integer, default=0)
    avatar = db.Column(db.String(10), default="🥷")

class QuizResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.String(50))
    difficulty = db.Column(db.String(20))
    mode = db.Column(db.String(20))
    score = db.Column(db.Float)
    total_questions = db.Column(db.Integer)
    negative_marking = db.Column(db.Boolean, default=False)
    date_taken = db.Column(db.DateTime, default=datetime.utcnow)

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    subject = db.Column(db.String(50))
    question = db.Column(db.Text)
    option_a = db.Column(db.Text)
    option_b = db.Column(db.Text)
    option_c = db.Column(db.Text)
    option_d = db.Column(db.Text)
    answer = db.Column(db.String(5))
    explanation = db.Column(db.Text)
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

class BattleResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    mode = db.Column(db.String(10))
    subject = db.Column(db.String(50))
    opponent_name = db.Column(db.String(100))
    result = db.Column(db.String(10))
    player_score = db.Column(db.Integer)
    opponent_score = db.Column(db.Integer)
    xp_earned = db.Column(db.Integer)
    coins_earned = db.Column(db.Integer)
    date_taken = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ---------------- ACCESS CONTROL ----------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ---------------- HOME / REGISTER / LOGIN / LOGOUT ----------------

@app.route('/', methods=['GET'])
def home():
    logged_in = 'user_id' in session
    username = session.get('username')
    return render_template('landing.html', logged_in=logged_in, username=username)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        dob = request.form['dob']

        if password != confirm_password:
            return render_template('register.html', error="Passwords do not match")

        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            return render_template('register.html', error="Username or Email already exists")

        hashed_password = generate_password_hash(password)
        new_user = User(full_name=full_name, username=username, email=email,
                         password=hashed_password, dob=dob)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form['identifier']
        password = request.form['password']

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.full_name
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid username/email or password")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------- DASHBOARD ----------------

@app.route('/dashboard')
@login_required
def dashboard():
    return redirect(url_for('home'))

# ---------------- TNPSC EXAM SELECT ----------------

@app.route('/exam-select')
@login_required
def exam_select():
    flow = request.args.get('flow', 'battle')
    return render_template('exam_select.html', flow=flow)

# ---------------- SUBJECT SELECT ----------------

SUBJECTS = ["History", "Geography", "Polity", "Economics", "Science", "Aptitude", "Current Affairs"]

@app.route('/subjects/<group>')
@login_required
def subject_select(group):
    flow = request.args.get('flow', 'battle')
    return render_template('subject_select.html', subjects=SUBJECTS, group=group, flow=flow)
    # ---------------- SHARED AI ANALYSIS HELPER ----------------

def get_ai_analysis(user_id):
    all_results = QuizResult.query.filter_by(user_id=user_id).all()
    subject_stats = {}
    for r in all_results:
        if r.subject not in subject_stats:
            subject_stats[r.subject] = {'score': 0, 'total_questions': 0, 'attempts': 0}
        subject_stats[r.subject]['score'] += r.score
        subject_stats[r.subject]['total_questions'] += r.total_questions
        subject_stats[r.subject]['attempts'] += 1

    accuracy_report = []
    for subj, stats in subject_stats.items():
        acc = round((stats['score'] / stats['total_questions']) * 100, 2) if stats['total_questions'] else 0
        accuracy_report.append({
            'subject': subj,
            'accuracy': acc,
            'attempts': stats['attempts']
        })
    accuracy_report.sort(key=lambda x: x['accuracy'])

    weak_areas = [r['subject'] for r in accuracy_report if r['accuracy'] < 50]
    weak_count = len(weak_areas)
    total_subjects_played = len(accuracy_report)

    return accuracy_report, weak_areas, weak_count, total_subjects_played

# ---------------- BATTLE MODE SELECT ----------------

@app.route('/battle-mode/<group>/<subject>')
@login_required
def battle_mode_select(group, subject):
    return render_template('battle_mode.html', group=group, subject=subject)

# ---------------- SOLO PRACTICE (no opponent) ----------------

@app.route('/quiz-setup/<group>/<subject>')
@login_required
def quiz_setup(group, subject):
    return render_template('quiz_setup.html', group=group, subject=subject)

@app.route('/start-quiz')
@login_required
def start_quiz():
    group = request.args.get('group')
    subject = request.args.get('subject')
    mode = request.args.get('mode')
    difficulty = request.args.get('difficulty')

    df = pd.read_csv(os.path.join(BASE_DIR, 'data', 'questions.csv'))
    filtered = df[(df['subject'] == subject) & (df['difficulty'].str.lower() == difficulty.lower())]

    if filtered.empty:
        return f"No questions found for '{subject}' ({difficulty})."

    n = 10 if mode == 'practice' else min(21, len(filtered))
    n = min(n, len(filtered))
    questions = filtered.sample(n=n).to_dict(orient='records')

    session['quiz_questions'] = questions
    session['quiz_subject'] = subject
    session['quiz_group'] = group
    session['quiz_mode'] = mode
    session['quiz_difficulty'] = difficulty
    session['current_q'] = 0
    session['score'] = 0.0
    session['negative_marking'] = request.args.get('negative_marking') == 'yes'

    return redirect(url_for('quiz_page'))

@app.route('/quiz')
@login_required
def quiz_page():
    questions = session.get('quiz_questions')
    current_q = session.get('current_q', 0)

    if not questions or current_q >= len(questions):
        return redirect(url_for('quiz_result'))

    question = questions[current_q]
    return render_template('quiz.html', question=question, current_q=current_q + 1,
                            total=len(questions), username=session.get('username'))

@app.route('/check-answer', methods=['POST'])
@login_required
def check_answer():
    selected = request.form.get('selected_option')
    questions = session.get('quiz_questions')
    current_q = session.get('current_q', 0)
    username = session.get('username')

    question = questions[current_q]
    correct_answer = question['answer']

    negative_marking = session.get('negative_marking', False)

    if selected == correct_answer:
        session['score'] = session.get('score', 0) + 1
        feedback = f"✅ Correct answer, {username}!"
        is_correct = True
    else:
        if negative_marking:
            session['score'] = session.get('score', 0) - 0.25
            feedback = f"❌ Not bad try, {username}! Correct answer: {correct_answer}. (-0.25 for negative marking)"
        else:
            feedback = f"❌ Not bad try, {username}! The correct answer was {correct_answer}."
        is_correct = False

    session['current_q'] = current_q + 1

    return jsonify({"feedback": feedback, "is_correct": is_correct, "next_url": url_for('quiz_page')})

@app.route('/quiz-result')
@login_required
def quiz_result():
    score = session.get('score', 0)
    total = len(session.get('quiz_questions', []))
    subject = session.get('quiz_subject')
    difficulty = session.get('quiz_difficulty')
    mode = session.get('quiz_mode')

    result = QuizResult(
        user_id=session['user_id'], subject=subject, difficulty=difficulty,
        mode=mode, score=score, total_questions=total,
        negative_marking=session.get('negative_marking', False)
    )
    db.session.add(result)
    db.session.commit()

    percentage = round((score / total) * 100, 2) if total else 0
    score = round(score, 2)

    # ---- AI weak-area analysis (auto, right after practice) ----
    all_results = QuizResult.query.filter_by(user_id=session['user_id']).all()
    subject_stats = {}
    for r in all_results:
        if r.subject not in subject_stats:
            subject_stats[r.subject] = {'score': 0, 'total': 0}
        subject_stats[r.subject]['score'] += r.score
        subject_stats[r.subject]['total'] += r.total_questions

    accuracy_report = []
    for subj, stats in subject_stats.items():
        acc = round((stats['score'] / stats['total']) * 100, 2) if stats['total'] else 0
        accuracy_report.append({'subject': subj, 'accuracy': acc})
    accuracy_report.sort(key=lambda x: x['accuracy'])
    weak_areas = [r['subject'] for r in accuracy_report if r['accuracy'] < 50]
    weak_count = len(weak_areas)
    total_subjects_played = len(accuracy_report)

    return render_template('quiz_result.html', score=score, total=total,
                            percentage=percentage, subject=subject,
                            accuracy_report=accuracy_report, weak_areas=weak_areas,
                            weak_count=weak_count, total_subjects_played=total_subjects_played,
                            negative_marking=session.get('negative_marking', False))
# ---------------- AI RECOMMENDATIONS ----------------

@app.route('/recommendations')
@login_required
def recommendations():
    accuracy_report, weak_areas, weak_count, total_subjects_played = get_ai_analysis(session['user_id'])
    return render_template('recommendations.html', accuracy_report=accuracy_report,
                            weak_areas=weak_areas, weak_count=weak_count,
                            total_subjects_played=total_subjects_played)

# ---------------- PERFORMANCE ----------------

@app.route('/performance')
@login_required
def performance():
    results = QuizResult.query.filter_by(user_id=session['user_id']).order_by(QuizResult.date_taken.desc()).all()
    return render_template('performance.html', results=results)

# ---------------- PROFILE (with Game Level + Avatar) ----------------

LEVEL_TIERS = [
    (0,    "Rookie",      "🔰"),
    (100,  "Warrior",     "⚔️"),
    (300,  "Champion",    "🏆"),
    (600,  "Legend",      "🌟"),
    (1200, "Grandmaster", "👑"),
]

AVAILABLE_AVATARS = ["🥷", "🧑‍🎓", "👩‍🎓", "🦸", "🦸‍♀️", "🧙", "🧙‍♀️", "🕵️"]

def get_level_info(xp):
    xp = xp or 0
    current = LEVEL_TIERS[0]
    next_tier = None
    for i, tier in enumerate(LEVEL_TIERS):
        if xp >= tier[0]:
            current = tier
            next_tier = LEVEL_TIERS[i + 1] if i + 1 < len(LEVEL_TIERS) else None
    progress = 100
    if next_tier:
        span = next_tier[0] - current[0]
        progress = round(((xp - current[0]) / span) * 100, 1) if span else 100
    return {
        "name": current[1], "icon": current[2], "xp": xp,
        "next_name": next_tier[1] if next_tier else None,
        "next_xp": next_tier[0] if next_tier else None,
        "progress": progress
    }

@app.route('/profile')
def profile():
    user = None
    level_info = None
    battles = 0
    wins = 0
    weak_areas = []
    logged_in = 'user_id' in session
    if logged_in:
        user = User.query.get(session['user_id'])
        level_info = get_level_info(user.xp)
        battles = BattleResult.query.filter_by(user_id=user.id).count()
        wins = BattleResult.query.filter_by(user_id=user.id, result='win').count()
        _, weak_areas, _, _ = get_ai_analysis(session['user_id'])
    return render_template('profile.html', user=user, level_info=level_info,
                            battles=battles, wins=wins, avatars=AVAILABLE_AVATARS,
                            weak_areas=weak_areas, logged_in=logged_in)
# ---------------- PROGRESS ----------------

@app.route('/progress')
@login_required
def progress_page():
    quiz_results = QuizResult.query.filter_by(user_id=session['user_id']).order_by(QuizResult.date_taken.desc()).limit(10).all()
    battle_results = BattleResult.query.filter_by(user_id=session['user_id']).order_by(BattleResult.date_taken.desc()).limit(10).all()

    accuracy_report, weak_areas, weak_count, total_subjects_played = get_ai_analysis(session['user_id'])

    trend_source = QuizResult.query.filter_by(user_id=session['user_id']).order_by(QuizResult.date_taken.asc()).limit(15).all()
    trend_labels = [r.date_taken.strftime('%d-%m') for r in trend_source]
    trend_values = [round((r.score / r.total_questions) * 100, 1) if r.total_questions else 0 for r in trend_source]

    return render_template('progress.html', quiz_results=quiz_results, battle_results=battle_results,
                            accuracy_report=accuracy_report, trend_labels=trend_labels, trend_values=trend_values)

# ---------------- SETTINGS ----------------

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings_page():
    message = None
    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        form_type = request.form.get('form_type')

        if form_type == 'profile':
            full_name = request.form.get('full_name', '').strip()
            if full_name:
                user.full_name = full_name
                session['username'] = full_name
                db.session.commit()
                message = "Profile updated successfully."

        elif form_type == 'password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            if not check_password_hash(user.password, current_password):
                message = "Current password is incorrect."
            else:
                user.password = generate_password_hash(new_password)
                db.session.commit()
                message = "Password updated successfully."

    return render_template('settings.html', message=message, user=user, avatars=AVAILABLE_AVATARS)

@app.route('/profile/set-avatar', methods=['POST'])
@login_required
def set_avatar():
    avatar = request.form.get('avatar')
    if avatar in AVAILABLE_AVATARS:
        user = User.query.get(session['user_id'])
        user.avatar = avatar
        db.session.commit()
    return redirect(url_for('profile'))

# ---------------- NOTES & RESOURCES (with per-subject Q&A) ----------------

BOOK_RECOMMENDATIONS = {
    "History": "Tamil Nadu History Book (11th Std) + Spectrum Modern History",
    "Geography": "TN Geography Textbook + NCERT Geography",
    "Polity": "M. Laxmikanth Indian Polity",
    "Economics": "Ramesh Singh Indian Economy",
    "Science": "Lucent's General Science",
    "Aptitude": "R.S. Aggarwal Quantitative Aptitude",
    "Current Affairs": "Monthly Current Affairs Magazine (TNPSC Focus)"
}

@app.route('/notes')
@login_required
def notes():
    return render_template('notes.html', subjects=SUBJECTS, books=BOOK_RECOMMENDATIONS)

# ---------------- BOOKMARKS ----------------

@app.route('/bookmark-question', methods=['POST'])
@login_required
def bookmark_question():
    questions = session.get('quiz_questions')
    current_q = session.get('current_q', 0)
    if not questions or current_q >= len(questions):
        return jsonify({"success": False})

    q = questions[current_q]
    existing = Bookmark.query.filter_by(
        user_id=session['user_id'], subject=q['subject'], question=q['question']
    ).first()
    if existing:
        return jsonify({"success": True, "already": True})

    bookmark = Bookmark(
        user_id=session['user_id'], subject=q['subject'], question=q['question'],
        option_a=q['option_a'], option_b=q['option_b'], option_c=q['option_c'], option_d=q['option_d'],
        answer=q['answer'], explanation=q.get('explanation', '')
    )
    db.session.add(bookmark)
    db.session.commit()
    return jsonify({"success": True, "already": False})

@app.route('/bookmarks')
@login_required
def bookmarks_page():
    items = Bookmark.query.filter_by(user_id=session['user_id']).order_by(Bookmark.date_added.desc()).all()
    return render_template('bookmarks.html', items=items)

@app.route('/bookmarks/delete/<int:bookmark_id>', methods=['POST'])
@login_required
def delete_bookmark(bookmark_id):
    b = Bookmark.query.get_or_404(bookmark_id)
    if b.user_id == session['user_id']:
        db.session.delete(b)
        db.session.commit()
    return redirect(url_for('bookmarks_page'))

@app.route('/notes/<subject>')
@login_required
def notes_subject(subject):
    df = pd.read_csv(QUESTIONS_CSV)
    subject_qs = df[df['subject'] == subject].to_dict(orient='records')
    return render_template('notes_subject.html', subject=subject, questions=subject_qs,
                            book=BOOK_RECOMMENDATIONS.get(subject, ""))

# ---------------- LEADERBOARD ----------------

@app.route('/leaderboard')
@login_required
def leaderboard():
    top_users = User.query.order_by(User.xp.desc()).limit(20).all()
    return render_template('leaderboard.html', users=top_users)

# ---------------- LABI CHAT ----------------

@app.route('/labi-chat', methods=['POST'])
@login_required
def labi_chat():
    message = request.form.get('message', '').lower().strip()
    questions = session.get('quiz_questions')
    current_q = session.get('current_q', 0)
    q_index = current_q - 1 if current_q > 0 else 0
    question = questions[q_index] if questions and q_index < len(questions) else None

    if not question:
        return jsonify({"reply": "No active question right now. Start a quiz first."})

    reply = generate_ai_reply(question, message)

    return jsonify({"reply": reply})

def generate_explanation(question):
    explanation_text = question.get('explanation', '')
    return (f"📘 <b>Explanation</b><br>"
            f"<b>Question:</b> {question['question']}<br>"
            f"<b>Correct Answer:</b> Option {question['answer']}<br>"
            f"<b>Subject:</b> {question['subject']} | <b>Difficulty:</b> {question['difficulty']}<br><br>"
            f"{explanation_text if explanation_text else 'This type of question is frequently asked in TNPSC exams.'}")

def generate_full_notes(question):
    exam_name = question.get('exam_name', 'TNPSC Group Exam')
    exam_year = question.get('exam_year', 'Previous Years')
    explanation_text = question.get('explanation', '')
    return (f"📒 <b>Full Notes</b><br>"
            f"<b>Question:</b> {question['question']}<br>"
            f"<b>Subject:</b> {question['subject']}<br>"
            f"<b>Asked in:</b> {exam_name} ({exam_year})<br>"
            f"<b>Correct Answer:</b> Option {question['answer']}<br><br>"
            f"<b>Explanation:</b> {explanation_text}<br><br>"
            f"<b>Key Points:</b><br>"
            f"- Make sure you understand the basics of this topic.<br>"
            f"- Variations of this question can appear in other exams too.")

# ================= BATTLE ARENA CONFIG =================

AI_DIFFICULTY = {
    "beginner": {"accuracy": 0.55, "delay_min": 3000, "delay_max": 6000, "label": "🟢 Beginner Bot"},
    "smart":    {"accuracy": 0.75, "delay_min": 2000, "delay_max": 4000, "label": "🟡 Smart Bot"},
    "master":   {"accuracy": 0.92, "delay_min": 800,  "delay_max": 2000, "label": "🔴 Master Bot"}
}
TIME_PER_QUESTION = 15
BASE_POINTS = 10

POWERUPS = {
    "fifty_fifty": {"name": "50-50", "icon": "🎯"},
    "double_points": {"name": "Double Points", "icon": "⚡"},
    "freeze": {"name": "Freeze", "icon": "❄️"},
    "confuse_ai": {"name": "Confuse AI", "icon": "🌀"}
}

def get_combo_multiplier(combo):
    if combo >= 6:
        return 2.0
    elif combo >= 3:
        return 1.5
    return 1.0

def calculate_score(combo, powerup_active_double=False):
    multiplier = get_combo_multiplier(combo)
    points = int(BASE_POINTS * multiplier)
    if powerup_active_double:
        points *= 2
    return points

def maybe_award_powerup(combo):
    if combo > 0 and combo % 3 == 0:
        return random.choice(list(POWERUPS.keys()))
    return None

battle_rooms = {}

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def get_questions_for_battle(subject, difficulty, count=10):
    df = pd.read_csv(QUESTIONS_CSV)
    filtered = df[(df['subject'] == subject) & (df['difficulty'].str.lower() == difficulty.lower())]
    n = min(count, len(filtered))
    if n == 0:
        return []
    return filtered.sample(n=n).to_dict(orient='records')

def save_battle_result(user_id, mode, subject, opponent_name, result, player_score, opponent_score):
    xp_earned = 50 if result == 'win' else (20 if result == 'draw' else 10)
    coins_earned = 30 if result == 'win' else (15 if result == 'draw' else 5)

    battle = BattleResult(
        user_id=user_id, mode=mode, subject=subject, opponent_name=opponent_name,
        result=result, player_score=player_score, opponent_score=opponent_score,
        xp_earned=xp_earned, coins_earned=coins_earned
    )
    db.session.add(battle)

    user = User.query.get(user_id)
    user.xp = (user.xp or 0) + xp_earned
    user.coins = (user.coins or 0) + coins_earned

    db.session.commit()
    return xp_earned, coins_earned

# ---------------- PVP: CREATE / JOIN ROOM ----------------

@app.route('/battle/create/<subject>')
@login_required
def battle_create(subject):
    room_code = generate_room_code()
    while room_code in battle_rooms:
        room_code = generate_room_code()

    battle_rooms[room_code] = {
        "subject": subject,
        "players": {
            session['user_id']: {
                "name": session['username'], "score": 0, "combo": 0,
                "answers": 0, "powerups": [], "ready": False
            }
        },
        "status": "waiting", "questions": [], "current_q": 0
    }
    session['room_code'] = room_code
    return render_template('battle_lobby.html', room_code=room_code, subject=subject, is_host=True)

@app.route('/battle-join-choice/<group>/<subject>', methods=['GET', 'POST'])
@login_required
def battle_join_choice(group, subject):
    if request.method == 'POST':
        room_code = request.form.get('room_code', '').upper().strip()
        if room_code not in battle_rooms:
            return render_template('battle_join.html', error="Room not found. Check the code and try again.")
        room = battle_rooms[room_code]
        if len(room['players']) >= 2:
            return render_template('battle_join.html', error="This room is already full.")
        room['players'][session['user_id']] = {
            "name": session['username'], "score": 0, "combo": 0,
            "answers": 0, "powerups": [], "ready": False
        }
        session['room_code'] = room_code
        return render_template('battle_lobby.html', room_code=room_code, subject=room['subject'], is_host=False)
    return render_template('battle_join.html')

@app.route('/battle-room/<room_code>')
@login_required
def battle_room_page(room_code):
    room = battle_rooms.get(room_code)
    if not room:
        return redirect(url_for('dashboard'))
    return render_template('battle_room.html', room_code=room_code, user_id=session['user_id'])

@app.route('/battle-room-result')
@login_required
def battle_room_result_page():
    return render_template('battle_room_result.html')

# ---------------- SOCKETIO EVENTS ----------------

@socketio.on('join_battle_room')
def handle_join_room(data):
    room_code = data['room_code']
    join_room(room_code)
    room = battle_rooms.get(room_code)
    if not room:
        return
    players_list = [{"id": pid, "name": p["name"]} for pid, p in room['players'].items()]
    emit('room_update', {"players": players_list, "status": room['status']}, room=room_code)
    if len(room['players']) == 2:
        emit('opponent_found', {"players": players_list}, room=room_code)

@socketio.on('player_ready')
def handle_player_ready(data):
    room_code = data['room_code']
    user_id = data['user_id']
    room = battle_rooms.get(room_code)
    if not room:
        return
    room['players'][user_id]['ready'] = True
    all_ready = all(p['ready'] for p in room['players'].values())
    if all_ready and len(room['players']) == 2:
        room['status'] = 'in_progress'
        room['questions'] = get_questions_for_battle(room['subject'], 'medium', count=10)
        room['current_q'] = 0
        emit('battle_start', {"total_questions": len(room['questions']),
                               "time_per_question": TIME_PER_QUESTION}, room=room_code)
        send_next_question(room_code)

def send_next_question(room_code):
    room = battle_rooms.get(room_code)
    if not room:
        return
    idx = room['current_q']
    if idx >= len(room['questions']):
        finish_battle(room_code)
        return
    q = room['questions'][idx]
    emit('new_question', {
        "question_number": idx + 1, "total": len(room['questions']),
        "question": q['question'],
        "options": {"A": q['option_a'], "B": q['option_b'], "C": q['option_c'], "D": q['option_d']},
        "time_limit": TIME_PER_QUESTION
    }, room=room_code)

@socketio.on('submit_answer')
def handle_submit_answer(data):
    room_code = data['room_code']
    user_id = data['user_id']
    selected = data['selected_option']
    time_taken = data.get('time_taken', TIME_PER_QUESTION)
    use_double_points = data.get('use_double_points', False)

    room = battle_rooms.get(room_code)
    if not room:
        return

    idx = room['current_q']
    question = room['questions'][idx]
    correct_answer = question['answer']
    player = room['players'][user_id]

    is_correct = (selected == correct_answer)
    if is_correct:
        player['combo'] += 1
        points = calculate_score(player['combo'], powerup_active_double=use_double_points)
        time_bonus = max(0, int((TIME_PER_QUESTION - time_taken) / 2))
        points += time_bonus
        player['score'] += points
        awarded_powerup = maybe_award_powerup(player['combo'])
        if awarded_powerup:
            player['powerups'].append(awarded_powerup)
    else:
        player['combo'] = 0
        points = 0
        awarded_powerup = None

    player['answers'] += 1

    emit('answer_result', {
        "is_correct": is_correct, "correct_answer": correct_answer,
        "points_earned": points, "combo": player['combo'],
        "total_score": player['score'], "powerup_awarded": awarded_powerup
    }, room=room_code, to=request.sid)

    scoreboard = [{"user_id": pid, "name": p["name"], "score": p["score"], "combo": p["combo"]}
                  for pid, p in room['players'].items()]
    emit('live_score_update', {"scoreboard": scoreboard}, room=room_code)

    answered_count = sum(1 for p in room['players'].values() if p['answers'] > idx)
    if answered_count >= len(room['players']):
        room['current_q'] += 1
        socketio.sleep(1.5)
        send_next_question(room_code)

@socketio.on('use_powerup')
def handle_use_powerup(data):
    room_code = data['room_code']
    user_id = data['user_id']
    powerup_key = data['powerup_key']
    room = battle_rooms.get(room_code)
    if not room:
        return
    player = room['players'][user_id]
    if powerup_key not in player['powerups']:
        return
    player['powerups'].remove(powerup_key)

    if powerup_key == "freeze":
        emit('opponent_used_freeze', {"seconds_lost": 5}, room=room_code)
    else:
        emit('powerup_applied', {"type": powerup_key}, room=room_code, to=request.sid)

def finish_battle(room_code):
    room = battle_rooms.get(room_code)
    if not room:
        return
    room['status'] = 'finished'
    players = list(room['players'].items())

    if len(players) == 2:
        (id1, p1), (id2, p2) = players
        if p1['score'] > p2['score']:
            result1, result2 = 'win', 'lose'
        elif p2['score'] > p1['score']:
            result1, result2 = 'lose', 'win'
        else:
            result1, result2 = 'draw', 'draw'

        save_battle_result(id1, 'pvp', room['subject'], p2['name'], result1, p1['score'], p2['score'])
        save_battle_result(id2, 'pvp', room['subject'], p1['name'], result2, p2['score'], p1['score'])

        emit('battle_finished', {
            "results": {
                id1: {"result": result1, "score": p1['score'], "opponent_score": p2['score']},
                id2: {"result": result2, "score": p2['score'], "opponent_score": p1['score']}
            }
        }, room=room_code)

    del battle_rooms[room_code]

# ---------------- PVAI ROUTES ----------------

@app.route('/battle-ai/setup/<subject>')
@login_required
def battle_ai_setup(subject):
    return render_template('battle_ai_setup.html', subject=subject, difficulties=AI_DIFFICULTY)

@app.route('/battle-ai/start', methods=['POST'])
@login_required
def battle_ai_start():
    subject = request.form.get('subject')
    ai_difficulty = request.form.get('ai_difficulty')

    questions = get_questions_for_battle(subject, 'medium', count=10)
    if not questions:
        return "No questions available for this subject."

    session['ai_battle'] = {
        "subject": subject, "ai_difficulty": ai_difficulty, "questions": questions,
        "current_q": 0, "player_score": 0, "ai_score": 0,
        "player_combo": 0, "ai_combo": 0, "player_powerups": [],
        "ai_correct_log": [], "ai_time_log": []
    }
    return redirect(url_for('battle_ai_page'))

@app.route('/battle-ai')
@login_required
def battle_ai_page():
    battle = session.get('ai_battle')
    if not battle:
        return redirect(url_for('dashboard'))
    idx = battle['current_q']
    if idx >= len(battle['questions']):
        return redirect(url_for('battle_ai_result'))
    q = battle['questions'][idx]
    ai_info = AI_DIFFICULTY[battle['ai_difficulty']]
    return render_template('battle_ai.html', question=q, current_q=idx + 1, total=len(battle['questions']),
        player_score=battle['player_score'], ai_score=battle['ai_score'],
        player_combo=battle['player_combo'], ai_label=ai_info['label'], time_limit=TIME_PER_QUESTION)

@app.route('/battle-ai/answer', methods=['POST'])
@login_required
def battle_ai_answer():
    battle = session.get('ai_battle')
    if not battle:
        return jsonify({"error": "No active battle"}), 400

    selected = request.form.get('selected_option')
    time_taken = float(request.form.get('time_taken', TIME_PER_QUESTION))
    use_double_points = request.form.get('use_double_points') == 'true'

    idx = battle['current_q']
    question = battle['questions'][idx]
    correct_answer = question['answer']

    player_correct = (selected == correct_answer)
    if player_correct:
        battle['player_combo'] += 1
        points = calculate_score(battle['player_combo'], powerup_active_double=use_double_points)
        points += max(0, int((TIME_PER_QUESTION - time_taken) / 2))
        battle['player_score'] += points
    else:
        battle['player_combo'] = 0
        points = 0

    ai_config = AI_DIFFICULTY[battle['ai_difficulty']]
    ai_correct = random.random() < ai_config['accuracy']
    ai_delay_ms = random.randint(ai_config['delay_min'], ai_config['delay_max'])

    if ai_correct:
        battle['ai_combo'] += 1
        ai_points = calculate_score(battle['ai_combo'])
        battle['ai_score'] += ai_points
    else:
        battle['ai_combo'] = 0
        ai_points = 0

    battle['ai_correct_log'].append(ai_correct)
    battle['ai_time_log'].append(ai_delay_ms)
    battle['current_q'] += 1
    session['ai_battle'] = battle

    return jsonify({
        "player_correct": player_correct, "correct_answer": correct_answer,
        "points_earned": points, "player_combo": battle['player_combo'], "player_total": battle['player_score'],
        "ai_correct": ai_correct, "ai_points_earned": ai_points, "ai_total": battle['ai_score'],
        "ai_delay_ms": ai_delay_ms, "next_url": url_for('battle_ai_page')
    })

@app.route('/battle-ai/result')
@login_required
def battle_ai_result():
    battle = session.get('ai_battle')
    if not battle:
        return redirect(url_for('dashboard'))

    player_score = battle['player_score']
    ai_score = battle['ai_score']

    if player_score > ai_score:
        result = 'win'
    elif ai_score > player_score:
        result = 'lose'
    else:
        result = 'draw'

    ai_label = AI_DIFFICULTY[battle['ai_difficulty']]['label']
    xp_earned, coins_earned = save_battle_result(
        session['user_id'], 'pvai', battle['subject'], ai_label, result, player_score, ai_score)

    ai_correct_count = sum(battle['ai_correct_log'])
    ai_total = len(battle['ai_correct_log'])
    ai_accuracy_actual = round((ai_correct_count / ai_total) * 100, 1) if ai_total else 0
    ai_avg_delay = round(sum(battle['ai_time_log']) / len(battle['ai_time_log']) / 1000, 2) if battle['ai_time_log'] else 0

    analysis = {
        "difficulty": battle['ai_difficulty'].capitalize(), "questions_faced": ai_total,
        "ai_correct": ai_correct_count, "ai_accuracy": ai_accuracy_actual,
        "ai_avg_response_time": ai_avg_delay
    }

    session.pop('ai_battle', None)
    return render_template('battle_ai_result.html', result=result, player_score=player_score,
        ai_score=ai_score, ai_label=ai_label, xp_earned=xp_earned, coins_earned=coins_earned, analysis=analysis)

if __name__ == '__main__':
    socketio.run(app, debug=True)