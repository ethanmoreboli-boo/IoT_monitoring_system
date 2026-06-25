from flask import Flask, request, jsonify, render_template, redirect, session, url_for
import mysql.connector
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import base64
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "hospital_iot_secret_2024"

UPLOAD_FOLDER = "static/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# database connection
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="hospital_db",
        auth_plugin='mysql_native_password'
    )

def init_db():
    db = mysql.connector.connect(host="localhost", user="root", password="root")
    cursor = db.cursor()
    cursor.execute("CREATE DATABASE IF NOT EXISTS hospital_db")
    cursor.close()
    db.close()

    db = get_db()
    cursor = db.cursor()
    # Table created for the users
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) UNIQUE,
        password VARCHAR(255),
        role VARCHAR(20) DEFAULT 'member',
        sensor VARCHAR(20)
    )
    """)
    # DHT22 table to store its data
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dht22(
        id INT AUTO_INCREMENT PRIMARY KEY,
        temperature FLOAT,
        humidity FLOAT,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ldr(
        id INT AUTO_INCREMENT PRIMARY KEY,
        light INT,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pir(
        id INT AUTO_INCREMENT PRIMARY KEY,
        motion INT,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bodytemp(
        id INT AUTO_INCREMENT PRIMARY KEY,
        temperature FLOAT,
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS images(
        id INT AUTO_INCREMENT PRIMARY KEY,
        filename VARCHAR(255),
        time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    db.commit()
    cursor.close()
    db.close()

def fix_database_schema():
    db = get_db()
    cursor = db.cursor(buffered=True)
    for col in ['sensor', 'role']:
        cursor.execute(f"""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME='users' AND COLUMN_NAME='{col}'
        """)
        if not cursor.fetchone():
            if col == 'sensor':
                cursor.execute("ALTER TABLE users ADD COLUMN sensor VARCHAR(20)")
            else:
                cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'member'")
    db.commit()
    cursor.close()
    db.close()

init_db()
fix_database_schema()

# ========================
# GRAPH HELPER
# ========================
def make_graph(x, y, title, xlabel, ylabel, color='#00b4d8'):
    fig, ax = plt.subplots(figsize=(10, 3.5))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#161b22')

    if x and y:
        ax.plot(x, y, color=color, linewidth=2, marker='o', markersize=3)
        ax.fill_between(range(len(y)), y, alpha=0.1, color=color)

    # setting the axis, title etc
    ax.set_title(title, color='#e6edf3', fontsize=13, pad=10)
    ax.set_xlabel(xlabel, color='#8b949e', fontsize=9)
    ax.set_ylabel(ylabel, color='#8b949e', fontsize=9)
    ax.tick_params(colors='#8b949e', labelsize=7)
    ax.spines['bottom'].set_color('#30363d')
    ax.spines['top'].set_color('#30363d')
    ax.spines['left'].set_color('#30363d')
    ax.spines['right'].set_color('#30363d')
    ax.grid(True, color='#30363d', linestyle='--', alpha=0.5)

    # Rotate x-axis labels
    if len(x) > 5:
        plt.xticks(range(len(x)), x, rotation=45, ha='right', fontsize=6)
    else:
        plt.xticks(range(len(x)), x, fontsize=7)

    plt.tight_layout()
    img = BytesIO()
    plt.savefig(img, format='png', dpi=100, bbox_inches='tight')
    img.seek(0)
    graph = base64.b64encode(img.getvalue()).decode()
    plt.close()
    return graph

# ========================
# AUTH ROUTES
# ========================
@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("index.html")

@app.route("/login/<node_type>", methods=["GET", "POST"])
def login(node_type):
    """node_type = 'admin' or 'member'"""
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user:
            # user = (id, username, password, role, sensor)
            user_role = user[3]
            if node_type == 'admin' and user_role != 'admin':
                error = "Not an admin account"
            elif node_type == 'member' and user_role == 'admin':
                error = "Use the Admin node to login as admin"
            else:
                session["user_id"] = user[0]
                session["username"] = user[1]
                session["role"] = user[3]
                session["sensor"] = user[4]
                if user_role == 'admin':
                    return redirect("/admin/dashboard")
                else:
                    return redirect("/member/dashboard")
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error, node_type=node_type)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    success = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        role = request.form.get("role", "member")
        sensor = request.form.get("sensor", None)

        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cursor.fetchone():
                error = "Username already exists"
            else:
                cursor.execute("""
                    INSERT INTO users(username, password, role, sensor)
                    VALUES (%s, %s, %s, %s)
                """, (username, password, role, sensor if role == 'member' else None))
                db.commit()
                success = f"Account '{username}' created! You can now login."
        except Exception as e:
            error = str(e)
        finally:
            cursor.close()
            db.close()

    return render_template("register.html", error=error, success=success)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ========================
# ADMIN ROUTES
# ========================
@app.route("/admin/dashboard")
def admin_dashboard():
    if "username" not in session or session.get("role") != "admin":
        return redirect("/")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Get all members
    cursor.execute("SELECT id, username, sensor FROM users WHERE role='member' ORDER BY username")
    members = cursor.fetchall()

    # Get latest reading per sensor
    stats = {}

    cursor.execute("SELECT temperature, humidity, time FROM dht22 ORDER BY time DESC LIMIT 1")
    r = cursor.fetchone()
    stats['dht22'] = r if r else None

    cursor.execute("SELECT light, time FROM ldr ORDER BY time DESC LIMIT 1")
    r = cursor.fetchone()
    stats['ldr'] = r if r else None

    cursor.execute("SELECT motion, time FROM pir ORDER BY time DESC LIMIT 1")
    r = cursor.fetchone()
    stats['pir'] = r if r else None

    cursor.execute("SELECT temperature, time FROM bodytemp ORDER BY time DESC LIMIT 1")
    r = cursor.fetchone()
    stats['bodytemp'] = r if r else None

    cursor.execute("SELECT COUNT(*) as cnt FROM images")
    r = cursor.fetchone()
    stats['camera'] = r if r else None

    cursor.close()
    db.close()

    return render_template("admin_dashboard.html",
                           username=session["username"],
                           members=members,
                           stats=stats)

@app.route("/admin/members")
def admin_members():
    if "username" not in session or session.get("role") != "admin":
        return redirect("/")
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT id, username, role, sensor FROM users ORDER BY role, username")
    users = cursor.fetchall()
    cursor.close()
    db.close()
    return render_template("admin_members.html", username=session["username"], users=users)

@app.route("/admin/sensor/<sensor_name>")
def admin_sensor(sensor_name):
    if "username" not in session or session.get("role") != "admin":
        return redirect("/")
    return _render_sensor(sensor_name, is_admin=True)

# ========================
# MEMBER ROUTES
# ========================
@app.route("/member/dashboard")
def member_dashboard():
    if "username" not in session or session.get("role") == "admin":
        return redirect("/")
    return render_template("member_dashboard.html",
                           username=session["username"],
                           sensor=session.get("sensor"))

@app.route("/member/sensor")
def member_sensor():
    if "username" not in session or session.get("role") == "admin":
        return redirect("/")
    sensor = session.get("sensor")
    if not sensor:
        return render_template("member_dashboard.html",
                               username=session["username"],
                               sensor=None,
                               error="No sensor assigned to your account")
    return _render_sensor(sensor, is_admin=False)

# ========================
# SHARED SENSOR RENDERER
# ========================
def _render_sensor(sensor_name, is_admin=False):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if sensor_name == 'ldr':

    # GET NEWEST DATA FIRST
        cursor.execute("""
        SELECT * FROM ldr
        ORDER BY id DESC
        LIMIT 100
        """)

        data = cursor.fetchall()

    # REVERSE ONLY FOR GRAPH DISPLAY
        graph_data = list(reversed(data))

        times = [str(r["time"]) for r in graph_data]
        lights = [r["light"] for r in graph_data]

        graph = make_graph(
            times,
            lights,
            "LDR — Light Level",
            "Time",
            "Light Value",
            '#ffd166'
        )

        cursor.close()
        db.close()

        return render_template(
        "sensor_ldr.html",
        data=data,
        graph=graph,
        is_admin=is_admin
      )

    elif sensor_name == 'dht22':

        # GET NEWEST FIRST
        cursor.execute("""
                SELECT * FROM dht22
                ORDER BY id DESC
                LIMIT 100
            """)

        data = cursor.fetchall()

            # reverse ONLY for graph display
        graph_data = list(reversed(data))

        times = [str(r["time"]) for r in graph_data]
        temp = [r["temperature"] for r in graph_data]
        hum = [r["humidity"] for r in graph_data]

        cursor.close()
        db.close()

        return render_template(
                "sensor_dht.html",
                data=data,
                graph_temp=make_graph(times, temp, "DHT22 — Temperature", "Time", "°C", '#ff6b6b'),
                graph_hum=make_graph(times, hum, "DHT22 — Humidity", "Time", "%", '#48cae4'),
                is_admin=is_admin
            )

    elif sensor_name == 'pir':

        # GET NEWEST FIRST
        cursor.execute("""
        SELECT * FROM pir
        ORDER BY id DESC
        LIMIT 100
         """)

        data = cursor.fetchall()

        # reverse ONLY for graph
        graph_data = list(reversed(data))

        times = [str(r["time"]) for r in graph_data]
        motion = [r["motion"] for r in graph_data]

        graph = make_graph(
        times,
        motion,
        "PIR — Motion Events",
        "Time",
        "Motion (0/1)",
        '#06d6a0'
        )

        cursor.close()
        db.close()

        return render_template(
        "sensor_pir.html",
        data=data,
        graph=graph,
        is_admin=is_admin
        )
    elif sensor_name == 'bodytemp':

        cursor.execute("""
            SELECT * FROM bodytemp
            ORDER BY time DESC
            LIMIT 100
        """)

        data = cursor.fetchall()

        data.reverse()

        times = [str(r["time"]) for r in data]
        temp = [float(r["temperature"]) for r in data]

        graph = make_graph(
            times,
            temp,
            "Body Temperature",
            "Time",
            "Temperature (°C)",
            '#ef476f'
        )

        cursor.close()
        db.close()

        return render_template(
            "sensor_bodytemp.html",
            data=data,
            graph=graph,
            is_admin=is_admin
        )
    elif sensor_name == 'camera':
        cursor.execute("SELECT * FROM images ORDER BY time DESC LIMIT 20")
        images = cursor.fetchall()
        cursor.close(); db.close()
        return render_template("sensor_camera.html", images=images, is_admin=is_admin)

    else:
        cursor.close(); db.close()
        return redirect("/")

# ========================
# ESP32 API ENDPOINTS
# ========================
@app.route('/api/ldr', methods=['POST'])
def api_ldr():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data"}), 400
    light = data.get("light", 0)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO ldr(light) VALUES(%s)", (light,))
    db.commit()
    cursor.close(); db.close()
    return jsonify({"status": "ok", "inserted": {"light": light}})

@app.route('/api/dht', methods=['POST'])
def api_dht():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data"}), 400
    temperature = data.get("temperature", 0)
    humidity = data.get("humidity", 0)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO dht22(temperature, humidity) VALUES(%s, %s)", (temperature, humidity))
    db.commit()
    cursor.close(); db.close()
    return jsonify({"status": "ok", "inserted": {"temperature": temperature, "humidity": humidity}})

@app.route('/api/pir', methods=['POST'])
def api_pir():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data"}), 400
    motion = data.get("motion", 0)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO pir(motion) VALUES(%s)", (motion,))
    db.commit()
    cursor.close(); db.close()
    return jsonify({"status": "ok", "inserted": {"motion": motion}})

@app.route('/api/bodytemp', methods=['POST'])
def api_bodytemp():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON data"}), 400
    temperature = data.get("temperature", 0)
    db = get_db()
    cursor = db.cursor()
    cursor.execute("INSERT INTO bodytemp(temperature) VALUES(%s)", (temperature,))
    db.commit()
    cursor.close(); db.close()
    return jsonify({"status": "ok", "inserted": {"temperature": temperature}})

UPLOAD_FOLDER = "static/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
from collections import deque
# keep last 30 images (live stream feel)
images = deque(maxlen=30)

# =========================
# ESP32 CAMERA UPLOAD
# DO NOT CHANGE ESP32 CODE
# =========================
@app.route('/upload', methods=['POST'])
def upload_camera():

    if not request.data:
        return jsonify({"status": "error"}), 400

    filename = f"esp32_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    path = os.path.join(UPLOAD_FOLDER, filename)

    with open(path, "wb") as f:
        f.write(request.data)

    images.appendleft({
        "filename": filename,
        "time": datetime.now().strftime("%H:%M:%S")
    })

    return jsonify({"status": "ok"})


# =========================
# CAMERA PAGE (YOUR TEMPLATE)
# =========================
@app.route('/admin/sensor/camera')
def camera_page():
    return render_template("sensor_camera.html", images=list(images), is_admin=True)


# =========================
# LIVE API (IMPORTANT FOR REFRESH)
# =========================
@app.route('/api/camera/live')
def live_camera():
    return jsonify(list(images))


# ========================
# RUN
# ========================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
