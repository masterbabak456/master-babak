from flask import Flask, request, redirect, make_response, render_template_string
from flask_sqlalchemy import SQLAlchemy
from markupsafe import escape
import os
import re

app = Flask(__name__)

# تنظیمات دیتابیس (پشتیبانی از PostgreSQL Render)
db_uri = os.environ.get('DATABASE_URL', 'sqlite:///referrals_new.db')
if db_uri.startswith("postgres://"):
    db_uri = db_uri.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'babak1234')

db = SQLAlchemy(app)

# جدول جدید: ذخیره شماره موبایل به عنوان شناسه اصلی
class Referral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False, index=True) # شماره موبایل یکتا
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)   # کد لینک
    
class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, index=True)
    visitor_phone = db.Column(db.String(20), nullable=False) # شناسه بازدیدکننده بر اساس شماره

with app.app_context():
    db.create_all()

def calculate_discount(count):
    thresholds = [(50, "50%"), (40, "40%"), (30, "30%"), (20, "20%"), (10, "10%")]
    for threshold, discount in thresholds:
        if count >= threshold: return discount, threshold
    return "0%", 10

@app.route("/")
def home():
    ref = request.args.get("ref")
    
    # دریافت شماره بازدیدکننده از پارامتر URL (اگر فرستاده شده باشد)
    visitor_phone = request.args.get("vp") 
    
    if ref and visitor_phone:
        # بررسی اینکه آیا این شماره قبلاً روی این لینک کلیک کرده؟
        existing = Visit.query.filter_by(code=ref, visitor_phone=visitor_phone).first()
        if not existing:
            db.session.add(Visit(code=ref, visitor_phone=visitor_phone))
            db.session.commit()
    
    safe_ref = escape(ref) if ref else ""
    
    # صفحه اصلی + فرم ورود شماره موبایل
    return f"""
    <!DOCTYPE html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cənub Azərbaycan</title>
    <style>
        *{{box-sizing:border-box;margin:0;padding:0}}
        body{{font-family:Arial,sans-serif;background:#f8f9fa;color:#333;min-height:100vh}}
        .container{{width:100%;max-width:600px;margin:0 auto;padding:15px;text-align:center}}
        img{{width:140px;height:auto;margin-bottom:8px}}
        h1{{font-size:22px;margin-bottom:4px}}h2{{font-size:15px;color:#555;margin-bottom:4px}}
        h3{{font-size:13px;color:#777;margin-bottom:12px;line-height:1.4}}
        video{{width:100%;height:140px;object-fit:cover;border-radius:10px;margin-bottom:15px;background:#000;display:block}}
        .promo{{font-size:13px;margin-bottom:15px;line-height:1.5;background:#fff;padding:10px;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,0.05)}}
        .input-group{{margin: 20px 0; text-align: right;}}
        .input-group label{{display:block; margin-bottom:5px; font-weight:bold; font-size:14px;}}
        .input-group input{{width:100%; padding:14px; font-size:16px; border:2px solid #ddd; border-radius:10px; direction:ltr; text-align:left;}}
        .btn-main{{width:100%;padding:18px;font-size:20px;font-weight:bold;background:#28a745;color:white;border:none;border-radius:12px;cursor:pointer;box-shadow:0 4px 10px rgba(40,167,69,0.3)}}
    </style></head><body><div class="container">
    <img src="/static/logo.png" alt="Logo"><h1>Cənub Azərbaycan</h1>
    <h2>TKD / Kickboxing / MMA</h2>
    <h3>Master Babak Vosoghi, 8-ci Dan<br>Novxanı, 0513909912</h3>
    <video controls playsinline preload="metadata"><source src="/static/videomaster.mp4" type="video/mp4"></video>
    <div class="promo"><b>Endirim Kampaniyası</b><br>Şəxsi linkinizi dostlarınıza göndərin.<br><b>10→10% | 20→20% | 30→30% | 40→40% | 50→50%</b></div>
    
    <!-- فرم جدید: دریافت شماره موبایل -->
    <form action="/getlink" method="POST">
        <div class="input-group">
            <label>📱 Nömrənizi daxil edin:</label>
            <input type="tel" name="phone" placeholder="+994 50 123 45 67" required pattern="[0-9+ ]{{10,15}}">
        </div>
        <input type="hidden" name="parent" value="{safe_ref}">
        <button type="submit" class="btn-main">Şəxsi Linkimi Al</button>
    </form>
    </div></body></html>"""


@app.route("/getlink", methods=["POST"])
def getlink():
    phone = request.form.get("phone", "").strip()
    parent = request.form.get("parent", "")
    
    # اعتبارسنجی ساده شماره موبایل
    if not phone or len(phone) < 10:
        return redirect("/")
        
    # پاکسازی شماره (حذف فاصله و +)
    clean_phone = re.sub(r'[^0-9]', '', phone)
    
    # چک کردن اینکه آیا این شماره قبلاً ثبت شده؟
    user = Referral.query.filter_by(phone=clean_phone).first()
    
    if not user:
        # ساخت کد جدید بر اساس ۸ رقم آخر شماره (یا رندوم اگر تکراری بود)
        import uuid
        new_code = str(uuid.uuid4())[:8]
        user = Referral(phone=clean_phone, code=new_code)
        db.session.add(user)
        db.session.commit()
    
    count = Visit.query.filter_by(code=user.code).count()
    discount, next_level = calculate_discount(count)
    remaining = max(0, next_level - count)
    progress = min(100, (count / next_level) * 100) if next_level > 0 else 0
    
    # لینک اشتراک‌گذاری حالا شامل شماره بازدیدکننده هم هست (vp)
    share_text = f"🥋 TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={user.code}&vp={clean_phone}"
    
    return f"""<!DOCTYPE html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Linkiniz Hazırdır</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;background:#fff;color:#333;width:100vw;min-height:100vh;padding:20px;display:flex;flex-direction:column;align-items:center}}.card{{width:100%;max-width:100%;text-align:center}}h1{{font-size:22px;margin-bottom:10px}}h2{{font-size:18px;color:#28a745;margin-bottom:20px}}input{{width:100%;padding:14px;font-size:16px;border:2px solid #eee;border-radius:8px;text-align:center;margin-bottom:20px;background:#f9f9f9}}.btn-wa{{width:100%;padding:16px;font-size:18px;font-weight:bold;background:#25D366;color:white;border:none;border-radius:12px;cursor:pointer;margin-bottom:20px;display:block;text-decoration:none}}.stats{{font-size:14px;color:#666;line-height:1.6}}.progress-bar{{width:100%;height:25px;background:#eee;border-radius:12px;overflow:hidden;margin:10px 0}}.progress-fill{{height:100%;background:#28a745;transition:width 0.3s}}</style>
    </head><body><div class="card"><h1>Şəxsi Linkiniz</h1><h2>Hazırdır!</h2>
    <input value="https://master-babak.onrender.com/?ref={user.code}" readonly onclick="this.select()">
    <a href="https://wa.me/?text={share_text}" class="btn-wa">📲 WhatsApp-da Paylaş</a>
    <div class="stats"><p>Dəvət sayı (Baxış): <b>{count}</b></p><p>Endirim: <b>{discount}</b></p>
    <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
    <p>Qalan: <b>{remaining} nəfər</b></p></div></div></body></html>"""


@app.route("/mylink")
def mylink():
    # حالا کاربر باید شماره‌اش را وارد کند تا لینکش را ببیند
    phone = request.args.get("phone")
    if not phone:
        return """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;">
        <form action="/mylink" method="get" style="text-align:center;padding:20px;border:1px solid #ddd;border-radius:10px;">
        <h2>Linkinizi görmək üçün nömrənizi yazın</h2>
        <input type="tel" name="phone" placeholder="+994..." required style="padding:10px;margin:10px 0;width:100%;">
        <button type="submit" style="padding:10px 20px;background:#28a745;color:white;border:none;border-radius:5px;">Axtar</button>
        </form></body></html>"""
        
    clean_phone = re.sub(r'[^0-9]', '', phone)
    user = Referral.query.filter_by(phone=clean_phone).first()
    
    if not user:
        return "<h3 style='text-align:center;margin-top:50px;'>Bu nömrə ilə qeydiyyat tapılmadı.</h3>"
        
    count = Visit.query.filter_by(code=user.code).count()
    discount, next_level = calculate_discount(count)
    remaining = max(0, next_level - count)
    progress = min(100, (count / next_level) * 100) if next_level > 0 else 0
    
    share_text = f"🥋 TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={user.code}&vp={clean_phone}"
    
    return f"""<!DOCTYPE html>
    <html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Linkim</title>
    <style>*{{box-sizing:border-box;margin:0;padding:0}}body{{font-family:Arial,sans-serif;background:#fff;color:#333;width:100vw;min-height:100vh;padding:20px;display:flex;flex-direction:column;align-items:center}}.card{{width:100%;max-width:100%;text-align:center}}h1{{font-size:22px;margin-bottom:10px}}h2{{font-size:18px;color:#28a745;margin-bottom:20px}}input{{width:100%;padding:14px;font-size:16px;border:2px solid #eee;border-radius:8px;text-align:center;margin-bottom:20px;background:#f9f9f9}}.btn-wa{{width:100%;padding:16px;font-size:18px;font-weight:bold;background:#25D366;color:white;border:none;border-radius:12px;cursor:pointer;margin-bottom:20px;display:block;text-decoration:none}}.stats{{font-size:14px;color:#666;line-height:1.6}}.progress-bar{{width:100%;height:25px;background:#eee;border-radius:12px;overflow:hidden;margin:10px 0}}.progress-fill{{height:100%;background:#28a745;transition:width 0.3s}}</style>
    </head><body><div class="card"><h1>Şəxsi Linkiniz</h1>
    <input value="https://master-babak.onrender.com/?ref={user.code}" readonly onclick="this.select()">
    <a href="https://wa.me/?text={share_text}" class="btn-wa">WhatsApp-da Paylaş</a>
    <div class="stats"><p>Dəvət sayı (Baxış): <b>{count}</b></p><p>Endirim: <b>{discount}</b></p>
    <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
    <p>Qalan: <b>{remaining} nəfər</b></p></div></div></body></html>"""


@app.route("/admin")
def admin():
    stored_key = request.cookies.get("admin_key")
    url_key = request.args.get("key", "")
    
    if stored_key != ADMIN_PASSWORD and url_key != ADMIN_PASSWORD:
        return """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family:Arial;background:#222;color:white;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
        <div style="text-align:center;padding:30px;border:1px solid #444;border-radius:10px;width:90%;max-width:350px;">
        <h2>Admin Panel</h2><form action="/admin" method="get">
        <input type="password" name="key" placeholder="Password" style="padding:12px;font-size:16px;border-radius:5px;border:none;width:100%;margin-bottom:15px;">
        <button type="submit" style="padding:12px;font-size:16px;background:#28a745;color:white;border:none;border-radius:5px;cursor:pointer;width:100%;">Daxil ol</button>
        </form></div></body></html>"""

    from sqlalchemy import func
    results = db.session.query(Referral.phone, Referral.code, func.count(Visit.id).label('view_count')).outerjoin(Visit, Referral.code == Visit.code).group_by(Referral.id).all()
    total_links = len(results)
    
    html = f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Dashboard</title>
    <style>body{{font-family:Arial;background:#111;color:white;padding:15px;margin:0}}h1{{font-size:20px;margin-bottom:10px}}.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch;margin-top:15px}}table{{border-collapse:collapse;width:100%;min-width:500px;background:white;color:black;font-size:14px}}th,td{{padding:10px;border:1px solid #ddd;text-align:left}}th{{background:#f1f1f1}}.bar-bg{{width:100px;height:15px;background:#eee;border-radius:8px;overflow:hidden;display:inline-block;vertical-align:middle;margin-right:5px}}.bar-fill{{height:100%;background:green}}</style>
    </head><body><h1>TKD Dashboard ({total_links} Link)</h1><div class="table-wrap"><table>
    <tr><th>Phone</th><th>Code</th><th>Views</th><th>Discount</th></tr>"""
    
    for phone, code, count in results:
        discount, next_level = calculate_discount(count)
        remaining = max(0, next_level - count)
        progress = min(100, (count / next_level) * 100) if next_level > 0 else 0
        
        html += f"""<tr><td>{phone}</td><td>{code}</td><td>{count}</td><td>
        {discount}<br><div class="bar-bg"><div class="bar-fill" style="width:{progress}%"></div></div>
        <small>({remaining} qalıb)</small></td></tr>"""
    
    html += """</table></div></body></html>"""
    
    response = make_response(html)
    response.set_cookie("admin_key", ADMIN_PASSWORD, max_age=60*60*24*7, httponly=True, samesite='Strict')
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)