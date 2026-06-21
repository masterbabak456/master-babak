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
    user = User.query.filter_by(code=ref).first()
    
    
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
        <center>

    <img src="/static/logo.png" width="220">

    <h1>Cənub Azərbaycan</h1>

    <h2>TKD / Kickboxing / MMA</h2>

    <h3 style="font-size:22px;">
    Master Babak Vosoghi
    <br>
    8-ci Dan, Novxanı
    <br>
    0513909912
    </h3>

    </center>

    <hr>
    <center>

    <video
    controls
    playsinline
    style="
    width:95%;
    height:220px;
    object-fit:contain;
    border-radius:10px;
    ">
    <source src="/static/videomaster.mp4" type="video/mp4">
    </video>
   
    </center>

    <h3>🎁 Endirim Kampaniyası</h3>

    <p>
    Şəxsi linkinizi dostlarınıza göndərin.
    <br><br>

    <b>
    10→10% | 20→20% | 30→30% | 40→40% | 50→50%
    </b>

    <br><br>

    ⚠️ Öz adınızı yazın.
    <br>

    Başqasının adını yazmayın.
    </p>

    <hr>

   

    <input type="hidden" name="parent" value="{ref}">

    <input name="name"
    placeholder="Adınızı yazın"
    style="
    width:95%;
    font-size:30px;
    padding:30px;
    border-radius:12px;
    ">
    <br><br>

    <button style="
    width:95%;
    font-size:30px;
    padding:28px;
    background:#28a745;
    color:white;
    border:none;
    border-radius:12px;
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

    response = make_response(
        redirect(f"/?ref={mycode}")
    )

    response.set_cookie(
        "mycode",
        mycode,
        max_age=60*60*24*365
    )

    return response

@app.route("/stats/<code>")
def stats(code):

    user = User.query.filter_by(code=code).first()

    if not user:
        return "User not found"

    count = User.query.filter_by(parent=code).count()
    views = Visit.query.filter_by(code=code).count()
    count = views
    print("VIEWS =", views)
    if count >= 50:
        discount = "50%"
        next_level = 50

    elif count >= 40:
        discount = "40%"
        next_level = 50

    elif count >= 30:
        discount = "30%"
        next_level = 40

    elif count >= 20:
        discount = "20%"
        next_level = 30

    elif count >= 10:
        discount = "10%"
        next_level = 20

    else:
        discount = "0%"
        next_level = 10

    remaining = next_level - count

    if remaining < 0:
        remaining = 0

    progress = (count / next_level) * 100

    if progress > 100:
        progress = 100

    return f'''
    <body style="font-family:Arial;max-width:700px;margin:auto;">

    <h1>👤 {user.name}</h1>

    <h2>Dəvət sayı: {count}</h2>

    <h2>👀 Baxış sayı: {views}</h2>

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

    <h3>Qalan: {remaining} nəfər</h3>

    <h3>⏰ Kampaniya müddəti: 1 ay</h3>

    <h3>Hər ay yenilənir</h3>

    </body>
    '''
@app.route("/admin")
def admin():
    print("ADMIN OPENED")
    users = User.query.all()
    print("TOTAL USERS =", len(users))

    for u in users:
        print(u.name, u.code)
    total_users = len(users)

    html = f"""
    <html>
    <head>
    <title>Referral Dashboard</title>
    </head>

    <body style="font-family:Arial;background:#111;color:white;">

    <h1>🥋 TKD Referral Dashboard</h1>

    <h2>Total Members: {total_users}</h2>
    <hr>

    

    <form action="/coachsend">

    <input
    name="coachname"
    placeholder="Məşqçi adı"
    style="
    width:300px;
    padding:10px;
    font-size:20px;
    ">

    <button
    style="
    padding:10px;
    font-size:20px;
    background:green;
    color:white;
    ">
    📲 Məşqçi Göndər
    </button>

    </form>

    <hr>

    <table border="1" cellpadding="10"
    style="border-collapse:collapse;width:100%;background:white;color:black;">

    <tr>
    <td> Name </td>
    <td> Code </td>
    <td> Coach </td>
    <td> Stats </td>
    <td> Discount + Progress Bar </td>
    <td> Delete Button </td>
    </tr>
    """

    for user in users:

        count = User.query.filter_by(parent=user.code).count()

        views = Visit.query.filter_by(code=user.code).count()

        children = User.query.filter_by(parent=user.code).all()

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

        child_names = ""

        for child in children:
            child_names += child.name + "<br>"

        html += f"""
        <tr>
        <td>
        <a target="_blank"
        href="/coach/{user.code}">
        {user.name}
        </a>
        </td>

        <td>
        {user.code}
        </td>
        
        <td>
        <a target="_blank"
        href="/coach/{user.code}">
        👨‍🏫 Məşqçi
        </a>
        </td>
        <td>
        Referrals: {count}
        <br>
        Views: {views}

        <br><br>

        {child_names}
        </td>

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

        <td>
        <a href="/deletecoach/{user.code}"
        style="
        background:red;
        color:white;
        padding:8px;
        text-decoration:none;
        border-radius:5px;
        ">
        🗑 Delete
        </a>
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

@app.route("/coach/<code>")
def coach(code):
    return redirect(f"/?ref={code}")

@app.route("/coachsend")
def coachsend():

    coachname = request.args.get(
        "coachname",
        "Coach"
    )

    code = str(uuid.uuid4())[:8]

    new_user = User(
        code=code,
        name=coachname,
        parent="COACH"
    )

    db.session.add(new_user)
    db.session.commit()

    return redirect(
        f"https://wa.me/?text=Salam {coachname}%0A%0ABu sizin şəxsi məşqçi linkinizdir:%0A%0Ahttps://master-babak.onrender.com/?ref={code}"
    )
@app.route("/deletecoach/<code>")
def deletecoach(code):

    user = User.query.filter_by(
        code=code
    ).first()

    if not user:
        return "User not found"

    Visit.query.filter_by(
        code=code
    ).delete()

    db.session.delete(user)

    db.session.commit()

    return redirect("/admin")
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)