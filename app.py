from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import paho.mqtt.client as mqtt
import pymysql
import json
import time

# AWS RDS Configuration
DB_HOST = "iot-db.cvikaa66a5si.eu-north-1.rds.amazonaws.com"
DB_USER = "Jordon"
DB_PASS = "x2dwlx2d"
DB_NAME = "exercise_db"

app = Flask(__name__)
CORS(app)  # 允许跨域请求
socketio = SocketIO(app)

# 连接 MySQL
app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = 'your_secret_key'  # 需要更改为安全的密钥

db = SQLAlchemy(app)
jwt = JWTManager(app)

# 用户表
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# 运动记录表
class ExerciseRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)  # 确保有 username
    timestamp = db.Column(db.String(64))
    exercise_type = db.Column(db.String(32))
    total_time = db.Column(db.Float)
    total_steps = db.Column(db.Integer)
    total_distance = db.Column(db.Float)
    avg_speed = db.Column(db.Float)
    calories_burned = db.Column(db.Float)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "timestamp": self.timestamp,
            "exercise_type": self.exercise_type,
            "total_time": self.total_time,
            "total_steps": self.total_steps,
            "total_distance": self.total_distance,
            "avg_speed": self.avg_speed,
            "calories_burned": self.calories_burned
        }


# 创建数据库表
with app.app_context():
    db.create_all()

# MQTT 配置
broker = "localhost"
port = 1883
data_topic = "IC.embedded/404BrainNotFound"
control_topic = "IC.embedded/control"
heartbeat_topic = "IC.embedded/heartbeat"

# 设备状态
listening = False
last_heartbeat = 0
HEARTBEAT_TIMEOUT = 10
start_time = None
current_sensor_data = None
current_exercise_type = None

# MQTT 回调函数
def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(control_topic)
    client.subscribe(heartbeat_topic)

def on_disconnect(client, userdata, rc):
    print("MQTT disconnected with result code", rc)

def on_message(client, userdata, msg):
    global last_heartbeat, current_sensor_data, listening
    try:
        if msg.topic == heartbeat_topic:
            last_heartbeat = time.time()
            print("Heartbeat received, updated timestamp:", last_heartbeat)
        elif msg.topic == data_topic:
            payload_str = msg.payload.decode('utf-8')
            data = json.loads(payload_str)
            if listening:
                current_sensor_data = data
            socketio.emit('mqtt_message', {'topic': msg.topic, 'payload': data})
    except Exception as e:
        print("Error processing message:", e)

# 配置 MQTT 客户端
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message = on_message
mqtt_client.connect(broker, port, keepalive=60)
mqtt_client.loop_start()

@app.route('/')
def index():
    return render_template('index.html')

# 用户注册
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"message": "Username and password required"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"message": "Username already exists"}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({"message": "User registered successfully"}), 201

# 用户登录
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        access_token = create_access_token(identity=username)
        return jsonify(access_token=access_token), 200
    else:
        return jsonify({"message": "Invalid credentials"}), 401

# 获取设备状态
@app.route('/device_status', methods=['GET'])
def device_status():
    current_time = time.time()
    connected = (current_time - last_heartbeat) < HEARTBEAT_TIMEOUT
    return jsonify({"device_connected": connected})

# 开始运动（需要登录）
@app.route('/start', methods=['POST'])
@jwt_required()
def start_recording():
    global listening, start_time, current_sensor_data, current_exercise_type
    data = request.get_json()
    exercise_type = data.get("exercise_type", "walking")
    current_exercise_type = exercise_type
    listening = True
    start_time = time.time()
    current_sensor_data = None
    mqtt_client.subscribe(data_topic)
    mqtt_client.publish(control_topic, json.dumps({"command": "start", "exercise_type": exercise_type}))

    return jsonify({"message": f"Started recording exercise data, type: {exercise_type}"})

# 停止运动（需要登录）
@app.route('/stop', methods=['POST'])
@jwt_required()
def stop_recording():
    global listening, start_time, current_sensor_data, current_exercise_type
    listening = False
    stop_time = time.time()
    total_time = stop_time - start_time if start_time else 0

    username = get_jwt_identity()  # 获取当前登录用户

    step_count = current_sensor_data.get("step_count", 0) if current_sensor_data else 0
    total_distance = current_sensor_data.get("total_distance", 0) if current_sensor_data else 0
    avg_speed = current_sensor_data.get("avg_speed", 0) if current_sensor_data else 0
    calories_burned = round(total_distance * 0.05, 2)

    # 记录数据
    record = ExerciseRecord(
        username=username,  # 这里要存入用户名
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stop_time)),
        exercise_type=current_exercise_type,
        total_time=round(total_time, 2),
        total_steps=step_count,
        total_distance=total_distance,
        avg_speed=round(avg_speed, 2),
        calories_burned=calories_burned
    )

    db.session.add(record)
    db.session.commit()

    return jsonify(record.to_dict())


# 获取历史记录（需要登录）
@app.route('/history', methods=['GET'])
@jwt_required()
def history():
    username = get_jwt_identity()
    records = ExerciseRecord.query.filter_by(username=username).order_by(ExerciseRecord.id.desc()).all()
    return jsonify({"records": [rec.to_dict() for rec in records]})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=4000)
