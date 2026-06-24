from flask import Flask, request, redirect, make_response
import uuid
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///referrals.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True)
    name = db.Column(db.String(100))
    parent = db.Column(db.String(20))
class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20))
    visitor = db.Column(db.String(200))
with app.app_context():
    db.create_all()
@app.route("/")
def home():
    
    ref = request.args.get("ref", "ROOT")
    if ref != "ROOT":

        visitor = request.headers.get("User-Agent")

        old_visit = Visit.query.filter_by(
            code=ref,
            visitor=visitor
        ).first()

        if not old_visit:

            visit = Visit(
                code=ref,
                visitor=visitor
            )

            db.session.add(visit)
            db.session.commit()

            print("NEW VIEW:", ref)  
    
    return f"""
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family:Arial;font-size:14px;">
    <center>

    <img src="/static/logo.png" width="220">

    <h1 style="font-size:32px;">Cənub Azərbaycan</h1>

    <h2 style="font-size:20px;">TKD / Kickboxing / MMA</h2>
    <h3 style="font-size:16px;">
    Master Babak Vosoghi, 8-ci Dan, Novxanı, 0513909912
    </h3>
    </center>

    <hr>
    <center>

    <video
    controls
    style="
    width:90%;
    max-width:700px;
    height:120px;
    object-fit:contain;
    ">
        <source src="/static/videomaster.mp4" type="video/mp4">
    </video>

    </center>

    <br>

    <br>
    <h3>🎁 Endirim Kampaniyası</h3>

    <p>
    Şəxsi linkinizi dostlarınıza göndərin.
    <br><br>

    <b>
    10→10% | 20→20% | 30→30% | 40→40% | 50→50%
    </b>

    <br><br>
 
    </p>

    <hr>

    <form action="/getlink">

    <input type="hidden" name="parent" value="{ref}">

    <input type="hidden" name="name" value=""> 
    <button style="
    font-size:28px;
    padding:18px;
    background:#28a745;
    color:white;
    border:none;
    border-radius:10px;
    ">
    🎁 Şəxsi Linkimi Al
    </button>

</form>

    """

@app.route("/getlink")
def getlink():

    parent = request.args.get("parent","ROOT")
    name = request.args.get("name","Unknown")

    existing = User.query.filter_by(name=name).first()
    print("NAME =", name)
    print("EXISTING =", existing)

    if existing:
        mycode = existing.code

    else:
        mycode = str(uuid.uuid4())[:8]

        new_user = User(
            code=mycode,
            name=name,
            parent=parent
        )


        db.session.add(new_user)
        db.session.commit()
        print("USER SAVED:", name, mycode, parent)
    count = Visit.query.filter_by(code=mycode).count()

    if count >= 50:
        discount = "50%"
    elif count >= 40:
        discount = "40%"
    elif count >= 30:
        discount = "30%"
    elif count >= 20:
        discount = "20%"
    elif count >= 10:
        discount = "10%"
    else:
        discount = "0%"

    remaining = 10 - count

    if remaining < 0:
        remaining = 0
    progress = (count / 10) * 100

    if progress > 100:
        progress = 100

     
    response = make_response(f"""
    <html>

    <body style="font-family:Arial;max-width:700px;margin:auto;">

    <h1>👤 {name}</h1>

    <h2>🎁 Şəxsi Linkiniz</h2>

    <input
    value="https://master-babak.onrender.com/?ref={mycode}"
    style="width:100%;padding:10px;font-size:16px;"
    readonly>

    <br><br>

    <a href="https://wa.me/?text=🥋 TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={mycode}">
    <button style="
    padding:15px;
    font-size:20px;
    background:green;
    color:white;
    border:none;
    cursor:pointer;
    ">
    📲 WhatsApp-da Paylaş
    </button>
    </a>

    <br><br>
    <h3>📢 Linki dostlarınıza göndərin</h3>

    <h3>⏰ Kampaniya müddəti: 1 ay</h3>

    <hr>

    <h2>Dəvət sayı: {count}</h2>

    <h2>Endirim: {discount}</h2>

    <div style="
    width:100%;
    height:30px;
    border:1px solid black;
    ">

    <div style="
    width:{progress}%;
    height:30px;
    background:green;
    ">
    </div>

    </div>

    <br>

    <b>Qalan: {remaining} nəfər</b>
    <br><br>

    <b>
    ⚠️ Kampaniya hər ay yenilənir.
    </b>

    <br><br>
    <br><br>


    </body>
    </html>
    """)

    response.set_cookie(
        "mycode",
        mycode,
        max_age=60*60*24*365
    )

    return response

@app.route("/mylink/<code>")
def mylink(code):

    user = User.query.filter_by(code=code).first()

    if not user:
        return redirect("/")

    count = Visit.query.filter_by(code=code).count()

    if count >= 50:
        discount = "50%"
    elif count >= 40:
        discount = "40%"
    elif count >= 30:
        discount = "30%"
    elif count >= 20:
        discount = "20%"
    elif count >= 10:
        discount = "10%"
    else:
        discount = "0%"

    remaining = 10 - count

    if remaining < 0:
        remaining = 0

    progress = (count / 10) * 100

    if progress > 100:
        progress = 100

    return f"""
    <body style="font-family:Arial;max-width:700px;margin:auto;">

    <h1>👤 {user.name}</h1>

    <h2>🎁 Şəxsi Linkiniz</h2>

    <input
    value="https://master-babak.onrender.com/?ref={code}"
    style="width:100%;padding:10px;font-size:16px;"
    readonly>

    <br><br>

    <a href="https://wa.me/?text=🥋 TKD Kampaniyası%0A%0Ahttps://master-babak.onrender.com/?ref={code}">
    <button style="
    padding:15px;
    font-size:20px;
    background:green;
    color:white;
    border:none;
    ">
    📲 WhatsApp-da Paylaş
    </button>
    </a>

    <br><br>

    <h2>Dəvət sayı: {count}</h2>

    <h2>Endirim: {discount}</h2>

    </body>
    """
@app.route("/admin")
def admin():
    print("ADMIN OPENED")
    users = User.query.all()

    total_users = len(users)

    html = f"""
    <html>
    <head>
    <title>Referral Dashboard</title>
    </head>

    <body style="font-family:Arial;background:#111;color:white;">

    <h1>🥋 TKD Referral Dashboard</h1>

    <h2>Total Members: {total_users}</h2>

    <table border="1" cellpadding="10"
    style="border-collapse:collapse;width:100%;background:white;color:black;">

    <tr>
      <th>Name</th>
      <th>Code</th>
      <th>Parent</th>
      <th>Referrals</th>
      <th>Discount</th>  
    </tr>
    """

    for user in users:

        count = User.query.filter_by(parent=user.code).count()

        if count >= 50:
            discount = "50%"
        elif count >= 40:
            discount = "40%"
        elif count >= 30:
            discount = "30%"
        elif count >= 20:
            discount = "20%"
        elif count >= 10:
            discount = "10%"
        else:
            discount = "0%"
        if count < 10:
            next_level = 10
        elif count < 20:
            next_level = 20
        elif count < 30:
            next_level = 30
        elif count < 40:
            next_level = 40
        elif count < 50:
            next_level = 50
        else:
            next_level = 50

        remaining = next_level - count

        progress = (count / 50) * 100

        if progress > 100:
            progress = 100

        html += f"""
        <tr>
            <td>{user.name}</td>
            <td>{user.code}</td>
            <td>{user.parent}</td>
            <td>{count}</td>
            <td>
{discount}
<br><br>

<div style="width:200px;border:1px solid black;">
<div style="
width:{progress}%;
height:20px;
background:green;">
</div>
</div>

Qalan:
{remaining}
</td>
        </tr>
        """

    html += """
    </table>
    </body>
    </html>
    """
    html += """
    <br><br>

    <h2>🎁 Endirim Sistemi</h2>

    10 nəfər = 10% endirim<br>
    20 nəfər = 20% endirim<br>
    30 nəfər = 30% endirim<br>
    40 nəfər = 40% endirim<br>
    50 nəfər = 50% endirim<br>

    """
    return html
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)