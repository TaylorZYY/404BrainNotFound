from flask import Flask, render_template
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import json

app = Flask(__name__)
socketio = SocketIO(app)

# MQTT 配置
broker = "172.20.10.5"
port = 1883
topic = "IC.embedded/404BrainNotFound"

# MQTT 连接回调
def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)
    client.subscribe(topic)

# MQTT 消息回调
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        print(f"Received message on topic {msg.topic}: {payload}")

        # 尝试解析 JSON 数据
        try:
            data = json.loads(payload)
            socketio.emit('mqtt_message', {'topic': msg.topic, 'payload': data})  # 直接发送 JSON 数据
        except json.JSONDecodeError:
            socketio.emit('mqtt_message', {'topic': msg.topic, 'payload': {"error": "Invalid JSON"}})

    except Exception as e:
        print("Error processing message:", e)

# 创建 MQTT 客户端
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# 连接到 MQTT Broker
mqtt_client.connect(broker, port, keepalive=60)

# 启动 MQTT 监听线程
mqtt_client.loop_start()

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
