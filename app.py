from flask import Flask, request, redirect, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text, UniqueConstraint, inspect
from sqlalchemy.exc import IntegrityError
import os, re, uuid, json, time
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_secret_key_change_in_render')

# --- Database Settings ---
db_uri = os.environ.get('DATABASE_URL', 'sqlite:///referrals_multi.db')
if db_uri and db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Cloudinary Settings ---
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET')
)

SUPER_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'babak1234')
BASE_URL = os.environ.get('BASE_URL', 'https://master-babak.onrender.com')

db = SQLAlchemy(app)

# --- Models ---

class Coach(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    gym_name = db.Column(db.String(100))
    title = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    logo_url = db.Column(db.String(300), default='/static/logo.png')
    video_url = db.Column(db.String(300), default='/static/videomaster.mp4')
    ad_text = db.Column(Text)
    reward_rules = db.Column(db.Text) 
    password = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach.id'), nullable=True, index=True)
    phone = db.Column(db.String(20), nullable=False, index=True)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    parent_code = db.Column(db.String(20), nullable=True, index=True)
    owner_vid = db.Column(db.String(50), nullable=True)
    
    __table_args__ = (
        UniqueConstraint('coach_id', 'phone', name='uq_coach_phone'),
    )

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coach_id = db.Column(db.Integer, db.ForeignKey('coach.id'), nullable=True, index=True)
    referral_code = db.Column(db.String(20), nullable=False, index=True)
    visitor_id = db.Column(db.String(50), nullable=False, index=True)
    __table_args__ = (
        UniqueConstraint('coach_id', 'referral_code', 'visitor_id', name='uq_visit_coach_code_visitor'),
    )

# --- Helpers & Migration ---

def ensure_schema():
    insp = inspect(db.engine)
    tables = insp.get_table_names()
    db.create_all()
    
    default_coach = Coach.query.filter_by(slug='babak').first()
    if not default_coach:
        default_coach = Coach(
            slug='babak', name='Master Babak Vosoghi', gym_name='Cənub Azərbaycan',
            title='8th Dan - TKD / Kickboxing / MMA', phone='0513909912',
            ad_text='10 nəfər → 10% endirim\n20 nəfər → 20% endirim\n30 nəfər → 30% endirim',
            reward_rules='10:10,20:20,30:30,40:40,50:50', password='coach123'
        )
        db.session.add(default_coach)
        db.session.commit()
    
    default_coach_id = default_coach.id

    with db.engine.begin() as conn:
        if 'referral' in tables:
            cols = {c['name'] for c in insp.get_columns('referral')}
            if 'coach_id' not in cols:
                conn.execute(text('ALTER TABLE referral ADD COLUMN coach_id INTEGER'))
                conn.execute(text(f'UPDATE referral SET coach_id = {default_coach_id} WHERE coach_id IS NULL'))
        
        if 'visit' in tables:
            cols = {c['name'] for c in insp.get_columns('visit')}
            if 'coach_id' not in cols:
                conn.execute(text('ALTER TABLE visit ADD COLUMN coach_id INTEGER'))
                conn.execute(text(f'UPDATE visit SET coach_id = {default_coach_id} WHERE coach_id IS NULL'))

with app.app_context():
    ensure_schema()

# FIX: Discount is based on VIEWS (Play button clicks), NOT referrals
def calculate_discount(count, rules_str):
    rules = {}
    if rules_str:
        try:
            for part in rules_str.split(','):
                k, v = part.split(':')
                rules[int(k)] = int(v)
        except: pass
    if not rules: rules = {10:10, 20:20, 30:30, 40:40, 50:50}

    sorted_thresholds = sorted(rules.keys())
    current_pct = 0
    next_lvl = sorted_thresholds[0] if sorted_thresholds else 50
    
    for t in sorted_thresholds:
        if count >= t:
            current_pct = rules[t]
            idx = sorted_thresholds.index(t)
            if idx + 1 < len(sorted_thresholds): next_lvl = sorted_thresholds[idx+1]
            else: next_lvl = t
            
    remaining = max(0, next_lvl - count)
    if count >= sorted_thresholds[-1]: remaining = 0
    return f"{current_pct}%", next_lvl, remaining

def clean_phone_number(phone):
    digits = re.sub(r'\D', '', phone)
    return digits

def get_visitor_id():
    vid = request.cookies.get('tkd_visitor_id')
    if not vid: vid = uuid.uuid4().hex
    return vid

def new_unique_code():
    while True:
        code = uuid.uuid4().hex[:6].upper()
        if not Referral.query.filter_by(code=code).first():
            return code

def upload_to_cloudinary(file, resource_type="auto"):
    try:
        if resource_type == "video" or (hasattr(file, 'filename') and file.filename.endswith(('.mp4', '.mov', '.avi'))):
             result = cloudinary.uploader.upload(file, resource_type="video", format="mp4")
        else:
            result = cloudinary.uploader.upload(file, resource_type="image")
        return result.get('secure_url')
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

# --- PAGE 1: Public Landing (Anti-Cache + Azerbaijani Text + Button Higher) ---

@app.route('/<slug>')
def public_landing(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach: return "Coach not found", 404
        
    ref_code = request.args.get('ref')
    visitor_id = get_visitor_id()
    
    # Anti-cache timestamps for static assets
    ts = int(time.time())
    logo_src = f"/static/logo.png?v={ts}"
    video_src = f"/static/videomaster.mp4?v={ts}"
    
    resp_html = f"""
    <!DOCTYPE html>
    <html lang="az"><head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <title>{coach.name}</title>
        <link rel="manifest" href="/manifest.json">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                height: 100vh; 
                overflow: hidden; 
                display: flex; 
                flex-direction: column; 
                background: #0b0f19;
                color: white;
            }}
            
            /* Section 1: Logo (25%) */
            .sec-logo {{ 
                height: 25vh; 
                background: transparent; 
                display: flex; 
                flex-direction: column; 
                align-items: center; 
                justify-content: center;
                padding: 10px;
            }}
            .sec-logo img {{ 
                height: 60%; 
                width: auto;
                max-width: 75%;
                object-fit: contain; 
                filter: drop-shadow(0 0 15px rgba(255,255,255,0.1));
            }}
            .sec-logo h2 {{ 
                margin: 8px 0 4px 0; 
                font-size: 22px; 
                text-align: center;
                color: #ffffff;
                font-weight: 800;
                letter-spacing: 0.5px;
            }}
            .sec-logo p {{ 
                margin: 0; 
                font-size: 13px; 
                color: #94a3b8; 
                text-align: center;
                font-weight: 500;
            }}
            
            /* Section 2: Video (15%) */
            .sec-video {{ 
                height: 15vh; 
                background: #000; 
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
                overflow: hidden;
                border-top: 1px solid #1e293b;
                border-bottom: 1px solid #1e293b;
            }}
            .sec-video video {{ 
                width: 100%; 
                height: 100%; 
                object-fit: cover; 
                opacity: 0.8;
            }}
            .play-btn {{ 
                position: absolute; 
                top: 50%; 
                left: 50%; 
                transform: translate(-50%, -50%); 
                background: rgba(255,255,255,0.15); 
                backdrop-filter: blur(8px);
                padding: 10px 30px; 
                border-radius: 30px; 
                font-weight: bold; 
                cursor: pointer; 
                z-index: 10;
                font-size: 15px;
                color: white;
                border: 1px solid rgba(255,255,255,0.2);
                box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            }}
            
            /* Section 3: Rewards (32%) - AZERBAIJANI TEXT */
            .sec-rewards {{ 
                height: 32vh; 
                margin: 6px 12px;
                border-radius: 18px;
                padding: 12px; 
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                background: linear-gradient(145deg, #171d35, #10243b);
                border: 1px solid #2563eb;
                box-shadow: 0 8px 20px rgba(0,0,0,0.35);
            }}
            .sec-rewards h3 {{
                margin: 0 0 8px 0;
                font-size: 18px;
                color: #fbbf24;
                font-weight: 800;
                display: flex;
                align-items: center;
                gap: 8px;
                justify-content: center;
            }}
            .reward-subtitle {{
                font-size: 13px;
                color: #e2e8f0;
                margin-bottom: 12px;
                font-weight: 500;
            }}
            .reward-row {{
                width: 100%;
                display: flex;
                justify-content: space-around;
                align-items: center;
                gap: 4px;
                border-top: 1px solid rgba(255,255,255,0.1);
                padding-top: 12px;
            }}
            .reward-item {{
                flex: 1;
                text-align: center;
                color: white;
                font-weight: 700;
                font-size: 13px;
                line-height: 1.4;
            }}
            .reward-item strong {{
                display: block;
                color: #fbbf24;
                font-size: 16px;
                margin-bottom: 2px;
            }}
            
            /* Section 4: Phone Input (28%) - BUTTON HIGHER */
            .sec-phone {{ 
                height: 28vh; 
                background: #0b0f19; 
                padding: 8px 16px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start; /* Changed from center to push button up */
                padding-top: 15px;
            }}
            .sec-phone form {{
                width: 100%;
                max-width: 450px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .input-group {{
                position: relative;
                width: 100%;
                background: #1e293b;
                border-radius: 15px;
                border: 1px solid #334155;
                display: flex;
                align-items: center;
                transition: all 0.3s;
            }}
            .input-group:focus-within {{
                border-color: #3b82f6;
                box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
            }}
            .input-icon {{
                padding-left: 20px;
                color: #3b82f6;
                font-size: 20px;
            }}
            .input-group input {{ 
                width: 100%; 
                padding: 14px 20px; 
                border-radius: 15px; 
                border: none; 
                font-size: 17px; 
                text-align: left; 
                outline: none;
                background: transparent;
                color: white;
                font-weight: 500;
            }}
            .input-group input::placeholder {{ color: #64748b; }}
            
            .sec-phone button {{ 
                width: 100%; 
                padding: 12px; 
                background: linear-gradient(to right, #2563eb, #1d4ed8);
                color: white; 
                border: none; 
                border-radius: 15px; 
                font-size: 18px; 
                font-weight: bold; 
                cursor: pointer; 
                box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                transition: transform 0.2s;
            }}
            .sec-phone button:active {{ transform: scale(0.98); }}
        </style>
    </head><body>
        
        <!-- Section 1: Logo -->
        <div class="sec-logo">
            <img src="{logo_src}" alt="Logo">
            <h2>{coach.name}</h2>
            <p>{coach.title}</p>
        </div>

        <!-- Section 2: Video -->
        <div class="sec-video">
            <video id="main-video" src="{video_src}" playsinline preload="metadata"></video>
            <div id="play-overlay" class="play-btn" onclick="playVideo()">▶ PLAY</div>
        </div>

        <!-- Section 3: Rewards (AZERBAIJANI) -->
        <div class="sec-rewards">
            <h3> Dostlarınızı dəvət edin və mükafat qazanın!</h3>
            <div class="reward-subtitle">Dostlarınızı dəvət edin, hədiyyə və endirim əldə edin!</div>
            <div class="reward-row">
                <div class="reward-item">
                    <strong>10 nəfər</strong>
                    10% endirim
                </div>
                <div class="reward-item">
                    <strong>20 nəfər</strong>
                    20% endirim
                </div>
                <div class="reward-item">
                    <strong>30 nəfər</strong>
                    30% endirim
                </div>
            </div>
        </div>

        <!-- Section 4: Phone Input (Button Higher) -->
        <div class="sec-phone">
            <form method="POST" action="/{slug}/register">
                <input type="hidden" name="ref" value="{ref_code or ''}">
                <div class="input-group">
                    <span class="input-icon"></span>
                    <input type="tel" name="phone" required placeholder="Nömrənizi daxil edin (05XXXXXXXX)">
                </div>
                <button type="submit">
                    <span>Davam et</span>
                    <span>➤</span>
                </button>
            </form>
        </div>

        <script>
            var vid = document.getElementById("main-video");
            var overlay = document.getElementById("play-overlay");
            var hasTracked = false;

            function playVideo() {{
                overlay.style.display = 'none';
                vid.controls = true;
                vid.muted = false;
                
                var playPromise = vid.play();
                if (playPromise !== undefined) {{
                    playPromise.catch(error => {{ vid.muted = true; vid.play(); }});
                }}

                if (vid.requestFullscreen) vid.requestFullscreen();
                else if (vid.webkitEnterFullscreen) vid.webkitEnterFullscreen();
                
                if (!hasTracked) {{
                    fetch('/track_view', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ code: '{ref_code or ""}', slug: '{slug}', vid: '{visitor_id}' }})
                    }});
                    hasTracked = true;
                }}
            }}
            
            document.addEventListener('fullscreenchange', function() {{
                if (!document.fullscreenElement) {{
                    vid.pause();
                    vid.controls = false;
                    overlay.style.display = 'block';
                    vid.currentTime = 0;
                }}
            }});
            
            if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
        </script>
    </body></html>
    """
    
    response = make_response(resp_html)
    # Disable caching for the HTML page itself
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    if not request.cookies.get('tkd_visitor_id'):
        response.set_cookie('tkd_visitor_id', visitor_id, max_age=60*60*24*365)
    return response

@app.route('/<slug>/register', methods=['POST'])
def register_user(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach: return "Not found", 404
    
    phone = request.form.get('phone')
    parent_ref = request.form.get('ref')
    clean_phone = clean_phone_number(phone)
    
    if len(clean_phone) < 9: return redirect(f'/{slug}')
    
    user = Referral.query.filter_by(coach_id=coach.id, phone=clean_phone).first()
    
    if not user:
        new_code = new_unique_code()
        valid_parent = None
        if parent_ref:
            p = Referral.query.filter_by(code=parent_ref, coach_id=coach.id).first()
            if p and p.phone != clean_phone: valid_parent = parent_ref
        
        user = Referral(coach_id=coach.id, phone=clean_phone, code=new_code, parent_code=valid_parent)
        db.session.add(user)
        db.session.commit()
    
    resp = make_response(redirect(f'/{slug}/user/{user.code}'))
    resp.set_cookie('tkd_user_code', user.code, max_age=60*60*24*30)
    return resp

# --- PAGE 2: Student Personal Page (FIXED: Discount based on VIEWS) ---

@app.route('/<slug>/user/<code>')
def user_page(slug, code):
    coach = Coach.query.filter_by(slug=slug).first()
    user = Referral.query.filter_by(code=code, coach_id=coach.id).first()
    if not user: return "User not found", 404
    
    views_count = Visit.query.filter_by(referral_code=user.code, coach_id=coach.id).count()
    children_count = Referral.query.filter_by(parent_code=user.code, coach_id=coach.id).count()
    
    # FIX: Discount is calculated based on VIEWS (plays), as requested
    discount, next_lvl, remaining = calculate_discount(views_count, coach.reward_rules)
    progress = min(100, int((views_count / next_lvl) * 100)) if next_lvl > 0 else 100
    
    share_link = f"{BASE_URL}/{slug}?ref={user.code}"
    share_msg = f" {coach.name}\\n{share_link}"
    
    return f"""
    <html><head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
        <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <link rel="manifest" href="/manifest.json">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ 
                font-family: 'Segoe UI', sans-serif; 
                background: #0b0f19;
                color: white;
                height: 100dvh;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                padding: 8px;
                gap: 7px;
            }}
            
            /* Card Styles */
            .card {{ 
                background: #111827; 
                border: 1px solid #334155;
                border-radius: 16px; 
                padding: 10px; 
                box-shadow: 0 6px 18px rgba(0,0,0,0.35); 
            }}
            
            /* 1. Share Link Section */
            .share-section {{ flex: 0 0 auto; }}
            .share-title {{ font-size: 16px; font-weight: bold; margin-bottom: 8px; display: flex; align-items: center; justify-content: center; gap: 8px; color: #f8fafc; }}
            .link-box {{
                background: #0f172a;
                padding: 10px;
                border-radius: 10px;
                font-size: 12px;
                margin-bottom: 10px;
                color: #94a3b8;
                word-break: break-all;
                border: 1px dashed #334155;
                text-align: center;
            }}
            .btn-row {{ display: flex; gap: 8px; }}
            .btn {{ 
                flex: 1;
                padding: 12px; 
                border-radius: 10px; 
                text-decoration: none; 
                color: white; 
                font-weight: bold; 
                font-size: 14px; 
                text-align: center;
                border: none;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
            }}
            .wa {{ background: #16a34a; }}
            .copy {{ background: #2563eb; }}
            
            /* 2. Stats Section */
            .stats-section {{ 
                flex: 0 0 12%; 
                display: flex; 
                justify-content: space-between; 
                padding: 8px 15px;
                background: linear-gradient(145deg, #1e293b, #172033);
            }}
            .stat-item {{ text-align: center; flex: 1; }}
            .stat-num {{
                font-size: 24px; 
                font-weight: 900; 
                display: block;
                line-height: 1.2;
            }}
            .stat-lbl {{ font-size: 12px; color: #94a3b8; margin-top: 2px; font-weight: 600; }}
            .c-blue {{ color: #60a5fa; }}
            .c-green {{ color: #4ade80; }}
            .c-gold {{ color: #fbbf24; }}
            
            /* 3. Progress Section */
            .progress-section {{ 
                flex: 0 0 40%; 
                display: flex; 
                flex-direction: column; 
                justify-content: center;
                background: linear-gradient(145deg, #1e293b, #172033);
            }}
            .prog-header {{ font-size: 14px; font-weight: bold; margin-bottom: 10px; text-align: center; color: #e2e8f0; display: flex; align-items: center; justify-content: center; gap: 6px; }}
            .timeline {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: relative;
                padding: 0 2px;
                margin-bottom: 10px;
            }}
            .timeline::before {{
                content: '';
                position: absolute;
                top: 50%;
                left: 15px;
                right: 15px;
                height: 2px;
                background: #334155;
                z-index: 0;
            }}
            .node {{
                width: 30px;
                height: 30px;
                border-radius: 50%;
                background: #0f172a;
                border: 2px solid #334155;
                z-index: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 11px;
                font-weight: bold;
                color: #64748b;
                flex-direction: column;
                line-height: 1;
            }}
            .node.active {{
                background: #1e293b;
                border-color: #4ade80;
                color: #4ade80;
                box-shadow: 0 0 10px rgba(74, 222, 128, 0.2);
            }}
            .node.current {{
                width: 40px;
                height: 40px;
                font-size: 13px;
                border-color: #4ade80;
                background: #1e293b;
                color: white;
                box-shadow: 0 0 15px rgba(74, 222, 128, 0.3);
            }}
            .node-sub {{ font-size: 8px; color: #94a3b8; margin-top: 2px; font-weight: normal; }}
            
            .prog-footer {{ font-size: 12px; text-align: center; color: #94a3b8; font-weight: 500; }}
            
            /* 4. Info Section (Bottom) */
            .info-section {{ 
                flex: 0 0 20%; 
                background: linear-gradient(135deg, #064e3b 0%, #065f46 100%);
                border: 1px solid #059669;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                text-align: center;
                padding: 10px;
                border-radius: 16px;
            }}
            .info-title {{ font-size: 15px; font-weight: bold; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; color: #ecfdf5; }}
            .info-text {{ font-size: 12px; line-height: 1.4; color: #d1fae5; }}
            .highlight {{ color: #4ade80; font-weight: bold; }}
            
        </style>
    </head>
    <body>
        <!-- 1. Share Link -->
        <div class="card share-section">
            <div class="share-title"> Linkinizi Paylaşın</div>
            <div class="link-box">{share_link}</div>
            <div class="btn-row">
                <button class="btn copy" onclick="navigator.clipboard.writeText('{share_link}'); this.innerText='✅ Kopyalandı!'; setTimeout(() => this.innerText=' Copy Link', 2000);"> Copy Link</button>
                <a href="https://wa.me/?text={share_msg}" class="btn wa">WhatsApp ilə Paylaş</a>
            </div>
        </div>

        <!-- 2. Stats Row -->
        <div class="card stats-section">
            <div class="stat-item">
                <span class="stat-num c-blue">{views_count}</span>
                <div class="stat-lbl">Baxış</div>
            </div>
            <div style="width: 1px; background: #334155; height: 25px;"></div>
            <div class="stat-item">
                <span class="stat-num c-green">{children_count}</span>
                <div class="stat-lbl">Dəvət</div>
            </div>
            <div style="width: 1px; background: #334155; height: 25px;"></div>
            <div class="stat-item">
                <span class="stat-num c-gold">{discount}</span>
                <div class="stat-lbl">Endirim</div>
            </div>
        </div>

        <!-- 3. Progress Timeline -->
        <div class="card progress-section">
            <div class="prog-header"> {remaining} nəfər qalıb növbəti səviyyəyə</div>
            <div class="timeline">
                <div class="node current">
                    <span>{views_count}</span>
                    <span class="node-sub">nəfər</span>
                </div>
                <div class="node {'active' if views_count >= 10 else ''}">10<div class="node-sub">10%</div></div>
                <div class="node {'active' if views_count >= 20 else ''}">20<div class="node-sub">20%</div></div>
                <div class="node {'active' if views_count >= 30 else ''}">30<div class="node-sub">30%</div></div>
                <div class="node {'active' if views_count >= 40 else ''}">40<div class="node-sub">40%</div></div>
                <div class="node {'active' if views_count >= 50 else ''}">50<div class="node-sub">50%</div></div>
            </div>
            <div class="prog-footer">Hər 10 nəfər = 10% endirim</div>
        </div>

        <!-- 4. Bottom Info -->
        <div class="card info-section">
            <div class="info-title">📅 Dəvətiniz hər 1 ayda yenilənir</div>
            <div class="info-text">
                Hər 1 ay fəaliyyətiniz sıfırlanır və yenidən 0-dan başlayırsınız.<br>
                <span class="highlight">Daha çox dəvət edin, daha çox qazanın!</span>
            </div>
        </div>
        
        <script>
            if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
        </script>
    </body></html>
    """

@app.route('/track_view', methods=['POST'])
def track_view():
    data = request.get_json() or {}
    code = data.get('code')
    slug = data.get('slug')
    vid_id = data.get('vid')
    
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach or not code or not vid_id: return jsonify(status='invalid')
    
    owner = Referral.query.filter_by(code=code, coach_id=coach.id).first()
    if not owner: return jsonify(status='invalid')
    
    if request.cookies.get('tkd_user_code') == code: return jsonify(status='self')
    
    existing = Visit.query.filter_by(coach_id=coach.id, referral_code=code, visitor_id=vid_id).first()
    if existing: return jsonify(status='duplicate')
    
    try:
        db.session.add(Visit(coach_id=coach.id, referral_code=code, visitor_id=vid_id))
        db.session.commit()
        return jsonify(status='ok')
    except IntegrityError:
        db.session.rollback()
        return jsonify(status='duplicate')

# --- Super Admin & Coach Panel Routes (Unchanged logic) ---

@app.route('/superadmin', methods=['GET', 'POST'])
def super_admin():
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == SUPER_ADMIN_PASSWORD:
            resp = make_response(redirect('/superadmin/dashboard'))
            resp.set_cookie('admin_auth', SUPER_ADMIN_PASSWORD)
            return resp
        error = "Yanlış Parol!"
        
    if request.cookies.get('admin_auth') == SUPER_ADMIN_PASSWORD:
        return redirect('/superadmin/dashboard')
        
    return f"""
    <html><body style="font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#222; color:white;">
        <h1>Super Admin</h1>
        <form method="POST" style="width:80%; max-width:300px;">
            <input type="password" name="password" placeholder="Parol" style="width:100%; padding:20px; font-size:20px; margin-bottom:10px; border-radius:10px; border:none; text-align:center;">
            <button type="submit" style="width:100%; padding:20px; font-size:20px; background:#007bff; color:white; border:none; border-radius:10px;">Daxil Ol</button>
        </form>
        <p style="color:red; margin-top:10px;">{error}</p>
    </body></html>
    """

@app.route('/superadmin/dashboard')
def super_admin_dashboard():
    if request.cookies.get('admin_auth') != SUPER_ADMIN_PASSWORD: return redirect('/superadmin')
    
    coaches = Coach.query.all()
    html = """
    <html><body style="font-family:sans-serif; padding:20px; background:#f4f4f4;">
        <h2>Coaches Management</h2>
        <div style="display:flex; flex-direction:column; gap:10px;">
    """
    for c in coaches:
        html += f"""
        <div style="background:white; padding:15px; border-radius:10px; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
            <strong>{c.name}</strong> (<a href='/{c.slug}' target='_blank'>/{c.slug}</a>)<br>
            <a href='/superadmin/edit/{c.id}' style="display:inline-block; margin-top:5px; padding:8px 15px; background:#007bff; color:white; text-decoration:none; border-radius:5px;">Edit Settings</a>
        </div>
        """
    html += """
        </div>
        <br>
        <a href='/superadmin/new' style="display:block; text-align:center; padding:15px; background:#28a745; color:white; text-decoration:none; border-radius:10px; font-size:18px;"> Add New Coach</a>
        <br><br>
        <a href='/superadmin/logout' style="display:block; text-align:center; color:red;">Logout</a>
    </body></html>
    """
    return html

@app.route('/superadmin/logout')
def super_admin_logout():
    resp = make_response(redirect('/superadmin'))
    resp.delete_cookie('admin_auth')
    return resp

@app.route('/superadmin/new', methods=['GET', 'POST'])
def super_admin_new():
    if request.cookies.get('admin_auth') != SUPER_ADMIN_PASSWORD: return redirect('/superadmin')
    if request.method == 'POST':
        slug = request.form.get('slug')
        logo_url = '/static/logo.png'
        video_url = '/static/videomaster.mp4'
        
        if 'logo' in request.files and request.files['logo'].filename:
            url = upload_to_cloudinary(request.files['logo'], "image")
            if url: logo_url = url
            
        if 'video' in request.files and request.files['video'].filename:
            url = upload_to_cloudinary(request.files['video'], "video")
            if url: video_url = url

        db.session.add(Coach(
            slug=slug, name=request.form.get('name'), gym_name=request.form.get('gym_name'),
            title=request.form.get('title'), phone=request.form.get('phone'),
            logo_url=logo_url, video_url=video_url, ad_text=request.form.get('ad_text'),
            reward_rules=request.form.get('reward_rules'), password=request.form.get('password')
        ))
        db.session.commit()
        return redirect('/superadmin/dashboard')
    
    return """
    <html><body style="font-family:sans-serif; padding:20px;">
        <h2>New Coach</h2>
        <form method='POST' enctype='multipart/form-data' style="display:flex; flex-direction:column; gap:10px;">
            <input name='slug' placeholder='Slug (URL)' required style="padding:15px; font-size:16px;">
            <input name='name' placeholder='Name' required style="padding:15px; font-size:16px;">
            <input name='gym_name' placeholder='Gym Name' style="padding:15px; font-size:16px;">
            <input name='title' placeholder='Title' style="padding:15px; font-size:16px;">
            <input name='phone' placeholder='Phone' style="padding:15px; font-size:16px;">
            <label>Logo:</label><input type='file' name='logo' style="padding:10px;">
            <label>Video:</label><input type='file' name='video' style="padding:10px;">
            <textarea name='ad_text' placeholder='Ad Text' style="padding:15px; font-size:16px; height:100px;"></textarea>
            <input name='reward_rules' placeholder='Rules (10:10,20:20)' style="padding:15px; font-size:16px;">
            <input name='password' placeholder='Coach Password' style="padding:15px; font-size:16px;">
            <button type='submit' style="padding:15px; background:#28a745; color:white; border:none; font-size:18px; border-radius:10px;">Create Coach</button>
        </form>
    </body></html>
    """

@app.route('/superadmin/edit/<int:id>', methods=['GET', 'POST'])
def super_admin_edit(id):
    if request.cookies.get('admin_auth') != SUPER_ADMIN_PASSWORD: return redirect('/superadmin')
    coach = Coach.query.get_or_404(id)
    
    if request.method == 'POST':
        coach.name = request.form.get('name')
        coach.gym_name = request.form.get('gym_name')
        coach.title = request.form.get('title')
        coach.phone = request.form.get('phone')
        coach.ad_text = request.form.get('ad_text')
        coach.reward_rules = request.form.get('reward_rules')
        
        if 'logo' in request.files and request.files['logo'].filename:
            url = upload_to_cloudinary(request.files['logo'], "image")
            if url: coach.logo_url = url
            
        if 'video' in request.files and request.files['video'].filename:
            url = upload_to_cloudinary(request.files['video'], "video")
            if url: coach.video_url = url
            
        db.session.commit()
        return redirect('/superadmin/dashboard')

    return f"""
    <html><body style="font-family:sans-serif; padding:20px;">
        <h2>Edit {coach.name}</h2>
        <form method='POST' enctype='multipart/form-data' style="display:flex; flex-direction:column; gap:10px;">
            <input name='name' value='{coach.name}' style="padding:15px; font-size:16px;">
            <input name='gym_name' value='{coach.gym_name}' style="padding:15px; font-size:16px;">
            <input name='title' value='{coach.title}' style="padding:15px; font-size:16px;">
            <input name='phone' value='{coach.phone}' style="padding:15px; font-size:16px;">
            <label>Current Logo:</label><img src='{coach.logo_url}' width='100'>
            <label>New Logo:</label><input type='file' name='logo' style="padding:10px;">
            <label>Current Video:</label><a href='{coach.video_url}' target='_blank'>Watch</a>
            <label>New Video:</label><input type='file' name='video' style="padding:10px;">
            <textarea name='ad_text' style="padding:15px; font-size:16px; height:100px;">{coach.ad_text}</textarea>
            <input name='reward_rules' value='{coach.reward_rules}' style="padding:15px; font-size:16px;">
            <button type='submit' style="padding:15px; background:#007bff; color:white; border:none; font-size:18px; border-radius:10px;">Update Coach</button>
        </form>
    </body></html>
    """

@app.route('/<slug>/panel', methods=['GET', 'POST'])
def coach_panel(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach: return "Not found", 404
    
    error = ""
    if request.method == 'POST':
        if request.form.get('password') == coach.password:
            resp = make_response(redirect(f'/{slug}/stats'))
            resp.set_cookie(f'coach_auth_{slug}', coach.password)
            return resp
        error = "Yanlış Parol!"
        
    if request.cookies.get(f'coach_auth_{slug}') == coach.password:
        return redirect(f'/{slug}/stats')
        
    return f"""
    <html><body style="font-family:sans-serif; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; background:#333; color:white;">
        <h1>{coach.name} Panel</h1>
        <form method="POST" style="width:80%; max-width:300px;">
            <input type="password" name="password" placeholder="Parol" style="width:100%; padding:20px; font-size:20px; margin-bottom:10px; border-radius:10px; border:none; text-align:center;">
            <button type="submit" style="width:100%; padding:20px; font-size:20px; background:#28a745; color:white; border:none; border-radius:10px;">Daxil Ol</button>
        </form>
        <p style="color:red; margin-top:10px;">{error}</p>
    </body></html>
    """

@app.route('/<slug>/stats')
def coach_stats(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach or request.cookies.get(f'coach_auth_{slug}') != coach.password: return redirect(f'/{slug}/panel')
    
    total_refs = Referral.query.filter_by(coach_id=coach.id).count()
    total_views = Visit.query.filter_by(coach_id=coach.id).count()
    
    html = f"""
    <html><body style="font-family:sans-serif; padding:20px; background:#f4f4f4;">
        <h2>{coach.name} Dashboard</h2>
        <div style="display:flex; gap:10px; margin-bottom:20px;">
            <div style="background:white; padding:15px; border-radius:10px; flex:1; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
                <h3>{total_refs}</h3><small>Total Referrals</small>
            </div>
            <div style="background:white; padding:15px; border-radius:10px; flex:1; text-align:center; box-shadow:0 2px 5px rgba(0,0,0,0.1);">
                <h3>{total_views}</h3><small>Valid Views</small>
            </div>
        </div>
        
        <h3>Active Students (Min 1 View)</h3>
        <div style="display:flex; flex-direction:column; gap:5px;">
    """
    
    users = Referral.query.filter_by(coach_id=coach.id).all()
    for u in users:
        v_count = Visit.query.filter_by(referral_code=u.code, coach_id=coach.id).count()
        c_count = Referral.query.filter_by(parent_code=u.code, coach_id=coach.id).count()
        if v_count > 0: 
            disc, _, _ = calculate_discount(v_count, coach.reward_rules)
            html += f"""
            <div style="background:white; padding:10px; border-radius:5px; display:flex; justify-content:space-between;">
                <span>{u.phone}</span>
                <span> {v_count} | 🎁 {disc}</span>
            </div>
            """
            
    html += """
        </div>
        <br>
        <a href='/{slug}/panel/logout' style="display:block; text-align:center; color:red;">Logout</a>
    </body></html>
    """.replace("{slug}", slug)
    return html

@app.route('/<slug>/panel/logout')
def coach_logout(slug):
    resp = make_response(redirect(f'/{slug}/panel'))
    resp.delete_cookie(f'coach_auth_{slug}')
    return resp

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Referral Manager", "short_name": "RefManager",
        "start_url": "/superadmin", "display": "standalone",
        "background_color": "#0b0f19", "theme_color": "#0b0f19",
        "icons": [{"src": "/static/logo.png", "sizes": "192x192", "type": "image/png"}]
    })

@app.route('/sw.js')
def service_worker():
    return "self.addEventListener('install', e => self.skipWaiting()); self.addEventListener('fetch', e => e.respondWith(fetch(e.request)));", 200, {'Content-Type': 'application/javascript'}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)