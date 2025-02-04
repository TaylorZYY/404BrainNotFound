import time
import json
import paho.mqtt.client as mqtt

broker = "172.20.10.5"  
port = 1883
data_topic = "IC.embedded/404BrainNotFound"
control_topic = "IC.embedded/control"

client = mqtt.Client()
client.connect(broker, port, keepalive=60)

recording = False

def on_message(client, userdata, msg):
    global recording
    payload = json.loads(msg.payload.decode('utf-8'))
    if payload.get("command") == "start":
        print("收到开始信号，开始生成数据")
        recording = True
    elif payload.get("command") == "stop":
        print("收到停止信号，停止生成数据")
        recording = False

client.subscribe(control_topic)
client.on_message = on_message
client.loop_start()

while True:
    if recording:
        sensor_data = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "environment": {
                "temperature": round(20 + 10 * time.time() % 1, 2),  # 模拟温度
                "humidity": round(30 + 20 * time.time() % 1, 2),     # 模拟湿度
                "pressure": round(1000 + 10 * time.time() % 1, 2)    # 模拟气压
            },
            "motion": {
                "acceleration": {
                    "x": round(-1 + 2 * time.time() % 1, 2),  # 模拟X轴加速度
                    "y": round(-1 + 2 * time.time() % 1, 2),  # 模拟Y轴加速度
                    "z": round(0 + 1 * time.time() % 1, 2)    # 模拟Z轴加速度
                }
            },
            "sensor_id": "SimulatedSensor"
        }
        client.publish(data_topic, json.dumps(sensor_data))
    time.sleep(1)
