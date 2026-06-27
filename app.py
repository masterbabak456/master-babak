from flask import Flask, request, redirect, make_response
from flask_sqlalchemy import SQLAlchemy
from markupsafe import escape
import uuid
import os

app = Flask(__name__)

# تنظیمات دیتابیس
db_uri = os.environ.get('DATABASE_URL', 'sqlite:///referrals.db')
app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- خط حیاتی برای حل مشکل شما ---
# اگر فایل دیتابیس وجود داشت، آن را پاک کن تا جدول‌های جدید ساخته شوند
if os.path.exists('referrals.db'):
    os.remove('referrals.db')
    print("✅ Old database deleted to fix column error!")

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    parent = db.Column(db.String(20))

class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False)
    visitor_id = db.Column(db.String(200), nullable=False) # این ستون حالا حتما ساخته می‌شود

with app.app_context():
    db.create_all()

def calculate_discount(count):
    if count >= 50: return "50%", 50
    if count >= 40: return "40%", 40
    if count >= 30: return "30%", 30
    if count >= 20: return "20%", 20
    if count >= 10: return "10%", 10
    return "0%", 10

@app.route("/")
def home():
    ref = request.args.get("ref", None)
    
    if ref:
        try:
            visitor_id = request.headers.get("User-Agent", "Unknown") + "_" + request.remote_addr
            old_visit = Visit.query.filter_by(code=ref, visitor_id=visitor_id).first()
            
            if not old_visit:
                visit = Visit(code=ref, visitor_id=visitor_id)
                db.session.add(visit)
                db.session.commit()
        except Exception as e:
            print(f"Visit Error: {e}")
    
    safe_ref = escape(ref) if ref else ""
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>50% Endirim - Novxanı TKD & MMA</title>
        <meta property="og:title" content="🥋 50% Endirim - Novxanı TKD & MMA">
        <meta property="og:description" content="Bu videonu izləyin! Taekvondo, Kikboksinq və MMA üzrə məşqlərdə 50%-dək endirim qazanın.">
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ font-family: Arial, sans-serif; background: #f8f9fa; color: #333; min-height: 100vh; }}
            .container {{ width: 100%; max-width: 600px; margin: 0 auto; padding: 15px; text-align: center; }}
            img {{ width: 140px; height: auto; margin-bottom: 8px; }}
            h1 {{ font-size: 22px; margin-bottom: 4px; }}
            h2 {{ font-size: 15px; color: #555; margin-bottom: 4px; }}
            h3 {{ font-size: 13px; color: #777; margin-bottom: 12px; line-height: 1.4; }}
            video {{ 
                width: 100%; height: 140px; object-fit: contain; background: #000; 
                display: block; margin-bottom: 15px; border-radius: 8px;
            }}
            .promo {{ font-size: 13px; margin-bottom: 15px; line-height: 1.5; background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            .btn-main {{ 
                width: 100%; padding: 18px; font-size: 20px; font-weight: bold;
                background: #28a745; color: white; border: none; border-radius: 12px;
                cursor: pointer; box-shadow: 0 4px 10px rgba(40, 167, 69, 0.3);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <img src="/static/logo.png" alt="Logo">
            <h1>Cənub Azərbaycan</h1>
            <h2>TKD / Kickboxing / MMA</h2>
            <h3>Master Babak Vosoghi, 8-ci Dan<br>Novxanı, 0513909912</h3>
            
            <video controls playsinline preload="metadata">
                <source src="/static/videomaster.mp4" type="video/mp4">
            </video>

            <div class="promo">
                 <b>Endirim Kampaniyası</b><br>
                Şəxsi linkinizi dostlarınıza göndərin.<br>
                <b>10→10% | 20→20% | 30→30% | 40→40% | 50→50%</b>
            </div>

            <form action="/getlink" style="width:100%">
                <input type="hidden" name="parent" value="{safe_ref}">
                <button type="submit" class="btn-main">🎁 Şəxsi Linkimi Al</button>
            </form>
        </div>
    </body>
    </html>
    """

@app.route("/getlink")
def getlink():
    parent = request.args.get("parent", "")
    
    try:
        mycode = str(uuid.uuid4())[:8]
        
        if parent and parent != "ROOT":
            new_user = User(code=mycode, parent=parent)
            db.session.add(new_user)
            db.session.commit()
        
        count = Visit.query.filter_by(code=mycode).count()
        discount, next_level = calculate_discount(count)
        remaining = max(0, next_level - count)
        progress = min(100, (count / next_level) * 100) if next_level > 0 else 0
        
        response = make_response(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>Linkiniz Hazırdır</title>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ 
                    font-family: Arial, sans-serif; background: #fff; color: #333; 
                    width: 100vw; min-height: 100vh; padding: 20px; 
                    display: flex; flex-direction: column; align-items: center; 
                }}
                .card {{ width: 100%; max-width: 100%; text-align: center; }}
                h1 {{ font-size: 22px; margin-bottom: 10px; }}
                h2 {{ font-size: 18px; color: #28a745; margin-bottom: 20px; }}
                input {{ 
                    width: 100%; padding: 14px; font-size: 16px; border: 2px solid #eee; 
                    border-radius: 8px; text-align: center; margin-bottom: 20px; background: #f9f9f9;
                }}
                .btn-wa {{ 
                    width: 100%; padding: 16px; font-size: 18px; font-weight: bold;
                    background: #25D366; color: white; border: none; border-radius: 12px;
                    cursor: pointer; margin-bottom: 20px; display: block; text-decoration: none;
                }}
                .stats {{ font-size: 14px; color: #666; line-height: 1.6; }}
                .progress-bar {{ width: 100%; height: 25px; background: #eee; border-radius: 12px; overflow: hidden; margin: 10px 0; }}
                .progress-fill {{ height: 100%; background: #28a745; transition: width 0.3s; }}
                .note {{ font-size: 12px; color: #999; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Şəxsi Linkiniz</h1>
                <h2>Hazırdır!</h2>
                
                <input value="https://master-babak.onrender.com/?ref={mycode}" readonly onclick="this.select()">
                
                <a href="https://wa.me/?text=🥋 TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={mycode}" class="btn-wa">
                     WhatsApp-da Paylaş
                </a>

                <div class="stats">
                    <p>Dəvət sayı (Baxış): <b>{count}</b></p>
                    <p>Endirim: <b>{discount}</b></p>
                    <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
                    <p>Qalan: <b>{remaining} nəfər</b></p>
                </div>

                <p class="note">⚠️ Kampaniya hər ay yenilənir.</p>
            </div>
        </body>
        </html>
        """)
        response.set_cookie("mycode", mycode, max_age=60*60*24*365)
        return response
        
    except Exception as e:
        print(f"Getlink Error: {e}")
        return redirect("/")

@app.route("/mylink")
def mylink():
    code = request.cookies.get("mycode")
    if not code:
        return redirect("/")
    
    try:
        count = Visit.query.filter_by(code=code).count()
        discount, next_level = calculate_discount(count)
        remaining = max(0, next_level - count)
        progress = min(100, (count / next_level) * 100) if next_level > 0 else 0
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>Linkim</title>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ 
                    font-family: Arial, sans-serif; background: #fff; color: #333; 
                    width: 100vw; min-height: 100vh; padding: 20px; 
                    display: flex; flex-direction: column; align-items: center; 
                }}
                .card {{ width: 100%; max-width: 100%; text-align: center; }}
                h1 {{ font-size: 22px; margin-bottom: 10px; }}
                h2 {{ font-size: 18px; color: #28a745; margin-bottom: 20px; }}
                input {{ 
                    width: 100%; padding: 14px; font-size: 16px; border: 2px solid #eee; 
                    border-radius: 8px; text-align: center; margin-bottom: 20px; background: #f9f9f9;
                }}
                .btn-wa {{ 
                    width: 100%; padding: 16px; font-size: 18px; font-weight: bold;
                    background: #25D366; color: white; border: none; border-radius: 12px;
                    cursor: pointer; margin-bottom: 20px; display: block; text-decoration: none;
                }}
                .stats {{ font-size: 14px; color: #666; line-height: 1.6; }}
                .progress-bar {{ width: 100%; height: 25px; background: #eee; border-radius: 12px; overflow: hidden; margin: 10px 0; }}
                .progress-fill {{ height: 100%; background: #28a745; transition: width 0.3s; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>Şəxsi Linkiniz</h1>
                <input value="https://master-babak.onrender.com/?ref={code}" readonly onclick="this.select()">
                <a href="https://wa.me/?text= TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={code}" class="btn-wa">
                     WhatsApp-da Paylaş
                </a>
                <div class="stats">
                    <p>Dəvət sayı (Baxış): <b>{count}</b></p>
                    <p>Endirim: <b>{discount}</b></p>
                    <div class="progress-bar"><div class="progress-fill" style="width:{progress}%"></div></div>
                    <p>Qalan: <b>{remaining} nəfər</b></p>
                </div>
            </div>
        </body>
        </html>
        """
    except Exception as e:
        print(f"Mylink Error: {e}")
        return redirect("/")

@app.route("/admin")
def admin():
    stored_key = request.cookies.get("admin_key")
    url_key = request.args.get("key", "")
    
    if stored_key != "babak1234" and url_key != "babak1234":
        return """
        <!DOCTYPE html>
        <html>
        <head><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="font-family:Arial; background:#222; color:white; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
            <div style="text-align:center; padding:30px; border:1px solid #444; border-radius:10px; width:90%; max-width:350px;">
                <h2> Admin Panel</h2>
                <form action="/admin" method="get">
                    <input type="password" name="key" placeholder="Password" 
                           style="padding:12px; font-size:16px; border-radius:5px; border:none; width:100%; margin-bottom:15px;">
                    <button type="submit" style="padding:12px; font-size:16px; background:#28a745; color:white; border:none; border-radius:5px; cursor:pointer; width:100%;">
                        Daxil ol
                    </button>
                </form>
            </div>
        </body>
        </html>
        """

    try:
        users = User.query.all()
        total_links = len(users)
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Admin Dashboard</title>
            <style>
                body {{ font-family:Arial; background:#111; color:white; padding:15px; margin:0; }}
                h1 {{ font-size: 20px; margin-bottom: 10px; }}
                .table-wrap {{ overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 15px; }}
                table {{ border-collapse:collapse; width:100%; min-width: 600px; background:white; color:black; font-size: 14px; }}
                th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f1f1f1; }}
                .bar-bg {{ width:80px; height:15px; background:#eee; border-radius:8px; overflow:hidden; display:inline-block; vertical-align:middle; margin-right:5px; }}
                .bar-fill {{ height:100%; background:green; }}
            </style>
        </head>
        <body>
            <h1> TKD Dashboard ({total_links} Link)</h1>
            <div class="table-wrap">
            <table>
                <tr><th>Code</th><th>Parent</th><th>Subs</th><th>Views</th><th>Discount</th></tr>
        """
        
        for user in users:
            subs_count = User.query.filter_by(parent=user.code).count()
            views_count = Visit.query.filter_by(code=user.code).count()
            
            discount, next_level = calculate_discount(views_count)
            remaining = max(0, next_level - views_count)
            progress = min(100, (views_count / next_level) * 100) if next_level > 0 else 0
            
            html += f"""
            <tr>
                <td>{user.code}</td>
                <td>{user.parent if user.parent else '-'}</td>
                <td><b>{subs_count}</b></td>
                <td>{views_count}</td>
                <td>
                    {discount}<br>
                    <div class="bar-bg"><div class="bar-fill" style="width:{progress}%"></div></div>
                    <small>({remaining} qalıb)</small>
                </td>
            </tr>
            """
        
        html += """
            </table>
            </div>
        </body>
        </html>
        """
        
        response = make_response(html)
        response.set_cookie("admin_key", "babak1234", max_age=60*60*24*7)
        return response
        
    except Exception as e:
        print(f"Admin Error: {e}")
        return "<h1>Admin panelində xəta var.</h1>", 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)