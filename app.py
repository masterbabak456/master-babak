from flask import Flask, request, redirect, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from markupsafe import escape
from sqlalchemy import UniqueConstraint, inspect, text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
import os, re, uuid, json
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
    # Default to a known working MP4 structure
    video_url = db.Column(db.String(300), default='/static/videomaster.mp4')
    ad_text = db.Column(db.Text)
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
            ad_text='🥋 Dostlarını dəvət et!\n10 nəfər → 10%\n20 nəfər → 20%',
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
    """
    FIXED: Explicitly force video format to mp4 and resource_type to video
    to ensure the URL serves a playable video file, not just audio or thumbnail.
    """
    try:
        # If it's a video file, force resource_type='video' and format='mp4'
        if resource_type == "video" or (hasattr(file, 'filename') and file.filename.endswith(('.mp4', '.mov', '.avi'))):
             result = cloudinary.uploader.upload(
                file, 
                resource_type="video", 
                format="mp4",  # Force MP4 container
                eager=[{"width": 720, "crop": "scale"}] # Optional: optimize size
            )
        else:
            result = cloudinary.uploader.upload(file, resource_type="image")
            
        return result.get('secure_url')
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

# --- Routes ---

@app.route('/<slug>')
def public_landing(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach: return "Coach not found", 404
        
    ref_code = request.args.get('ref')
    visitor_id = get_visitor_id()
    
    # VIDEO FIX:
    # 1. Added 'controls' so you can verify playback manually.
    # 2. Added 'preload="metadata"' to load video data.
    # 3. Removed 'muted' from HTML (JS handles it on play).
    # 4. Ensured object-fit covers the strip.
    video_html = f"""
    <div style="width:100%; height:8vh; min-height:60px; background:#000; position:relative; margin: 10px 0; border-radius:5px; overflow:hidden;">
        <video id="main-video" 
               src="{coach.video_url}" 
               style="width:100%; height:100%; object-fit:cover;" 
               playsinline 
               preload="metadata"
               poster="{coach.logo_url}">
        </video>
        <div id="play-overlay" onclick="playVideo()" style="position:absolute; top:0; left:0; width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:rgba(0,0,0,0.4); cursor:pointer; z-index:10;">
            <span style="color:white; font-weight:bold; font-size:16px; text-shadow:0 2px 4px rgba(0,0,0,0.5);">▶ PLAY VIDEO</span>
        </div>
    </div>
    """

    resp_html = f"""
    <!DOCTYPE html>
    <html lang="az"><head>
        <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{coach.name}</title>
        <link rel="manifest" href="/manifest.json">
        <style>
            body {{ font-family: sans-serif; margin: 0; padding: 15px; background: #f4f4f4; text-align: center; }}
            .card {{ background: white; padding: 15px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 15px; }}
            input, button {{ padding: 10px; margin: 5px 0; width: 90%; border-radius: 5px; border: 1px solid #ddd; }}
            button {{ background: #25D366; color: white; border: none; font-weight: bold; }}
            .btn-blue {{ background: #007bff; }}
        </style>
    </head><body>
        <div class="card">
            <img src="{coach.logo_url}" style="width:70px; border-radius:50%;">
            <h2>{coach.name}</h2><p>{coach.title}</p><p>📞 {coach.phone}</p>
        </div>
        
        <!-- Video Section -->
        {video_html}

        <div class="card"><h3>🎁 Kampaniya</h3><p style="white-space:pre-line">{coach.ad_text}</p></div>
        <div class="card">
            <form method="POST" action="/{slug}/register">
                <input type="hidden" name="ref" value="{ref_code or ''}">
                <input type="tel" name="phone" required placeholder="Nömrəniz (050...)">
                <button type="submit" class="btn-blue">Şəxsi Linkimi Al</button>
            </form>
        </div>
        <script>
            var vid = document.getElementById("main-video");
            var overlay = document.getElementById("play-overlay");
            var hasTracked = false;

            function playVideo() {{
                // Hide overlay
                overlay.style.display = 'none';
                
                // Ensure video is not muted for user interaction
                vid.muted = false;
                
                // Add controls temporarily so user can see it's playing
                vid.controls = true;
                
                // Play promise handling
                var playPromise = vid.play();
                if (playPromise !== undefined) {{
                    playPromise.then(_ => {{
                        // Playback started successfully
                        console.log("Video playing");
                    }})
                    .catch(error => {{
                        console.log("Autoplay prevented, trying muted:", error);
                        vid.muted = true;
                        vid.play();
                    }});
                }}

                // Fullscreen logic
                if (vid.requestFullscreen) {{ vid.requestFullscreen(); }}
                else if (vid.webkitEnterFullscreen) {{ vid.webkitEnterFullscreen(); }}
                
                // Track View
                if (!hasTracked) {{
                    fetch('/track_view', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{ code: '{ref_code or ""}', slug: '{slug}', vid: '{visitor_id}' }})
                    }});
                    hasTracked = true;
                }}
            }}
            
            // Handle exit fullscreen
            document.addEventListener('fullscreenchange', function() {{
                if (!document.fullscreenElement) {{
                    vid.pause();
                    vid.controls = false; // Hide controls when back in strip
                    overlay.style.display = 'flex';
                    vid.currentTime = 0;
                }}
            }});
            
            if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js');
        </script>
    </body></html>
    """
    
    response = make_response(resp_html)
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

@app.route('/<slug>/user/<code>')
def user_page(slug, code):
    coach = Coach.query.filter_by(slug=slug).first()
    user = Referral.query.filter_by(code=code, coach_id=coach.id).first()
    if not user: return "User not found", 404
    
    views_count = Visit.query.filter_by(referral_code=user.code, coach_id=coach.id).count()
    children_count = Referral.query.filter_by(parent_code=user.code, coach_id=coach.id).count()
    discount, next_lvl, remaining = calculate_discount(views_count, coach.reward_rules)
    progress = min(100, int((views_count / next_lvl) * 100)) if next_lvl > 0 else 100
    
    share_link = f"{BASE_URL}/{slug}?ref={user.code}"
    share_msg = f"🥋 {coach.name}\\n{share_link}"
    
    return f"""
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="manifest" href="/manifest.json"></head>
    <body style="font-family:sans-serif; text-align:center; padding:20px; background:#f4f4f4;">
        <div style="background:white; padding:15px; border-radius:10px; margin-bottom:15px;">
            <img src="{coach.logo_url}" style="width:50px; border-radius:50%;">
            <h3>{coach.name}</h3>
        </div>
        <div style="background:white; padding:15px; border-radius:10px;">
            <h2>Linkiniz Hazırdır!</h2>
            <div style="background:#eee; padding:10px; word-break:break-all; font-size:12px;">{share_link}</div>
            <button onclick="navigator.clipboard.writeText('{share_link}')" style="width:100%; padding:10px; margin:10px 0; background:#007bff; color:white; border:none; border-radius:5px;">📋 Copy</button>
            <a href="https://wa.me/?text={share_msg}" style="display:block; padding:10px; background:#25D366; color:white; text-decoration:none; border-radius:5px;">📲 WhatsApp</a>
            <hr>
            <p>Baxış: <b>{views_count}</b> | Dəvət: <b>{children_count}</b></p>
            <p>Endirim: <b>{discount}</b> ({remaining} qalıb)</p>
            <div style="background:#ddd; height:10px; border-radius:5px;"><div style="background:green; height:100%; width:{progress}%"></div></div>
        </div>
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

# --- Super Admin ---

@app.route('/superadmin', methods=['GET', 'POST'])
def super_admin():
    if request.method == 'POST':
        if request.form.get('password') == SUPER_ADMIN_PASSWORD:
            resp = make_response(redirect('/superadmin/dashboard'))
            resp.set_cookie('admin_auth', SUPER_ADMIN_PASSWORD)
            return resp
        return "Wrong Password"
    if request.cookies.get('admin_auth') != SUPER_ADMIN_PASSWORD:
        return "<form method='POST'><input type='password' name='password'><button>Login</button></form>"
    return redirect('/superadmin/dashboard')

@app.route('/superadmin/dashboard')
def super_admin_dashboard():
    if request.cookies.get('admin_auth') != SUPER_ADMIN_PASSWORD: return redirect('/superadmin')
    coaches = Coach.query.all()
    html = "<h2>Coaches Management</h2><ul>"
    for c in coaches:
        html += f"<li><b>{c.name}</b> (<a href='/{c.slug}' target='_blank'>/{c.slug}</a>) - <a href='/superadmin/edit/{c.id}'>Edit Full Profile</a></li>"
    html += "</ul><br><a href='/superadmin/new' style='background:green; color:white; padding:10px; text-decoration:none;'>➕ Add New Coach</a>"
    return html

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
            # Explicitly pass resource_type video
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
    <h2>New Coach (Permanent Storage)</h2>
    <form method='POST' enctype='multipart/form-data'>
        Slug: <input name='slug' required><br>
        Name: <input name='name' required><br>
        Gym: <input name='gym_name'><br>
        Title: <input name='title'><br>
        Phone: <input name='phone'><br>
        Logo: <input type='file' name='logo'><br>
        Video: <input type='file' name='video' accept='video/*'><br>
        Ad Text: <textarea name='ad_text'></textarea><br>
        Rules (10:10,20:20): <input name='reward_rules'><br>
        Password: <input name='password'><br>
        <button type='submit'>Create Coach</button>
    </form>
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
    <h2>Edit {coach.name}</h2>
    <form method='POST' enctype='multipart/form-data'>
        Name: <input name='name' value='{coach.name}'><br>
        Gym: <input name='gym_name' value='{coach.gym_name}'><br>
        Title: <input name='title' value='{coach.title}'><br>
        Phone: <input name='phone' value='{coach.phone}'><br>
        Current Logo: <img src='{coach.logo_url}' width='50'><br>
        New Logo: <input type='file' name='logo'><br>
        Current Video: <a href='{coach.video_url}' target='_blank'>Watch</a><br>
        New Video: <input type='file' name='video' accept='video/*'><br>
        Ad Text: <textarea name='ad_text'>{coach.ad_text}</textarea><br>
        Rules: <input name='reward_rules' value='{coach.reward_rules}'><br>
        <button type='submit'>Update Coach</button>
    </form>
    """

# --- Coach Panel ---

@app.route('/<slug>/panel', methods=['GET', 'POST'])
def coach_panel(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach: return "Not found", 404
    if request.method == 'POST':
        if request.form.get('password') == coach.password:
            resp = make_response(redirect(f'/{slug}/stats'))
            resp.set_cookie(f'coach_auth_{slug}', coach.password)
            return resp
        return "Wrong Password"
    if request.cookies.get(f'coach_auth_{slug}') != coach.password:
        return f"<h2>{coach.name} Panel</h2><form method='POST'><input type='password' name='password'><button>Login</button></form>"
    return redirect(f'/{slug}/stats')

@app.route('/<slug>/stats')
def coach_stats(slug):
    coach = Coach.query.filter_by(slug=slug).first()
    if not coach or request.cookies.get(f'coach_auth_{slug}') != coach.password: return redirect(f'/{slug}/panel')
    
    total_refs = Referral.query.filter_by(coach_id=coach.id).count()
    total_views = Visit.query.filter_by(coach_id=coach.id).count()
    
    html = f"""
    <html><body style="font-family:sans-serif; padding:20px;">
    <h2>{coach.name} Dashboard</h2>
    <div style="display:flex; gap:10px; margin-bottom:20px;">
        <div style="background:#eee; padding:15px; border-radius:8px; flex:1; text-align:center;">
            <h3>{total_refs}</h3><small>Total Referrals</small>
        </div>
        <div style="background:#eee; padding:15px; border-radius:8px; flex:1; text-align:center;">
            <h3>{total_views}</h3><small>Valid Views</small>
        </div>
    </div>
    
    <h3>Active Students Progress</h3>
    <table border="1" style="width:100%; border-collapse:collapse; text-align:center;">
        <tr style="background:#f2f2f2;"><th>Phone</th><th>Views</th><th>Refs</th><th>Discount</th><th>Status</th></tr>
    """
    
    users = Referral.query.filter_by(coach_id=coach.id).all()
    for u in users:
        v_count = Visit.query.filter_by(referral_code=u.code, coach_id=coach.id).count()
        c_count = Referral.query.filter_by(parent_code=u.code, coach_id=coach.id).count()
        if v_count > 0 or c_count > 0:
            disc, nxt, rem = calculate_discount(v_count, coach.reward_rules)
            status = "🔥 Active" if v_count > 0 else "Registered"
            html += f"<tr><td>{u.phone}</td><td>{v_count}</td><td>{c_count}</td><td>{disc}</td><td>{status}</td></tr>"
            
    html += "</table></body></html>"
    return html

# --- PWA ---

@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Referral Manager", "short_name": "RefManager",
        "start_url": "/superadmin", "display": "standalone",
        "background_color": "#ffffff", "theme_color": "#000000",
        "icons": [{"src": "/static/logo.png", "sizes": "192x192", "type": "image/png"}]
    })

@app.route('/sw.js')
def service_worker():
    return "self.addEventListener('install', e => self.skipWaiting()); self.addEventListener('fetch', e => e.respondWith(fetch(e.request)));", 200, {'Content-Type': 'application/javascript'}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)