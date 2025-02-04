from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
import paho.mqtt.client as mqtt
import json

app = Flask(__name__)
socketio = SocketIO(app)

broker = "172.20.10.5"
port = 1883
data_topic = "IC.embedded/404BrainNotFound"
control_topic = "IC.embedded/control"

listening = False

def on_connect(client, userdata, flags, rc):
    print("Connected with result code", rc)

def on_message(client, userdata, msg):
    global listening
    if listening:
        try:
            payload = msg.payload.decode('utf-8')
            print(f"Received message: {payload}")
            data = json.loads(payload)
            socketio.emit('mqtt_message', {'topic': msg.topic, 'payload': data})
        except Exception as e:
            print("Error processing message:", e)

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(broker, port, keepalive=60)
mqtt_client.loop_start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_recording():
    global listening
    listening = True
    mqtt_client.subscribe(data_topic)
    mqtt_client.publish(control_topic, json.dumps({"command": "start"}))
    return jsonify({"message": "开始记录数据"})

@app.route('/stop', methods=['POST'])
def stop_recording():
    global listening
    listening = False
    mqtt_client.unsubscribe(data_topic)
    mqtt_client.publish(control_topic, json.dumps({"command": "stop"}))
    return jsonify({"message": "停止记录数据"})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)
