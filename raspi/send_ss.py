import time
import smbus2
import json
import paho.mqtt.client as mqtt
import math


# MQTT 配置
broker = "172.20.10.5"
port = 1883
data_topic = "IC.embedded/404BrainNotFound"
control_topic = "IC.embedded/control"

recording = False

def on_message(client, userdata, msg):
    global recording
    try:
        payload_str = msg.payload.decode('utf-8')
        print(f"收到 MQTT 消息: {payload_str}")
        payload = json.loads(payload_str)

        if payload.get("command") == "start":
            print("收到开始信号，开始生成数据")
            recording = True
        elif payload.get("command") == "stop":
            print("收到停止信号，停止生成数据")
            recording = False
    except Exception as e:
        print(f"解析 MQTT 消息失败: {e}")

# 传感器 I2C 地址
CCS811_I2C_ADDRESS = 0x5B
SI7021_I2C_ADDRESS = 0x40
BMP280_I2C_ADDRESS = 0x77

bus = smbus2.SMBus(1)

# 初始化 MQTT 客户端
client = mqtt.Client()
client.on_message = on_message
client.connect(broker, port, keepalive=60)
client.subscribe(control_topic)  # 订阅控制信号
client.loop_start()


# 读取 Si7021 温湿度
def read_si7021_temperature_humidity():
    try:
        cmd_meas_temp = smbus2.i2c_msg.write(SI7021_I2C_ADDRESS, [0xE3])
        read_temp = smbus2.i2c_msg.read(SI7021_I2C_ADDRESS, 2)
        bus.i2c_rdwr(cmd_meas_temp)
        time.sleep(0.1)
        bus.i2c_rdwr(read_temp)

        temp_raw = (read_temp.buf[0][0] << 8) | read_temp.buf[1][0]
        temperature = ((175.72 * temp_raw) / 65536) - 46.85

        cmd_meas_hum = smbus2.i2c_msg.write(SI7021_I2C_ADDRESS, [0xE5])
        read_hum = smbus2.i2c_msg.read(SI7021_I2C_ADDRESS, 2)
        bus.i2c_rdwr(cmd_meas_hum)
        time.sleep(0.1)
        bus.i2c_rdwr(read_hum)

        hum_raw = (read_hum.buf[0][0] << 8) | read_hum.buf[1][0]
        humidity = ((125.0 * hum_raw) / 65536) - 6.0

        return temperature, humidity
    except Exception as e:
        print(f"读取 Si7021 温湿度失败: {e}")
        return None, None

# 读取 BMP280 传感器数据
def i2c_get_data(device_addr, register):
    try:
        return bus.read_byte_data(device_addr, register)
    except Exception as e:
        print(f"I2C 读取 {register:#04x} 失败: {e}")
        return None

def i2c_get_data_multi(device_addr, register, length):
    try:
        return bus.read_i2c_block_data(device_addr, register, length)
    except Exception as e:
        print(f"I2C 读取 {register:#04x} 失败: {e}")
        return None

def i2c_write_data(device_addr, register):
    try:
        bus.write_byte(device_addr, register)
    except Exception as e:
        print(f"I2C 写入 {register:#04x} 失败: {e}")

def i2c_write_data_multi(device_addr, register, data):
    try:
        bus.write_i2c_block_data(device_addr, register, data)
    except Exception as e:
        print(f"I2C 写入 {register:#04x} 失败: {e}")

def read_bmp280():
    def read_unsigned_short(addr, reg):
        data = bus.read_i2c_block_data(addr, reg, 2)
        return data[0] | (data[1] << 8)
    
    def read_signed_short(addr, reg):
        value = read_unsigned_short(addr, reg)
        return value - 65536 if value > 32767 else value
    
    # 读取 BMP280 校准参数
    dig_T1 = read_unsigned_short(BMP280_I2C_ADDRESS, 0x88)
    dig_T2 = read_signed_short(BMP280_I2C_ADDRESS, 0x8A)
    dig_T3 = read_signed_short(BMP280_I2C_ADDRESS, 0x8C)
    dig_P1 = read_unsigned_short(BMP280_I2C_ADDRESS, 0x8E)
    dig_P2 = read_signed_short(BMP280_I2C_ADDRESS, 0x90)
    dig_P3 = read_signed_short(BMP280_I2C_ADDRESS, 0x92)
    dig_P4 = read_signed_short(BMP280_I2C_ADDRESS, 0x94)
    dig_P5 = read_signed_short(BMP280_I2C_ADDRESS, 0x96)
    dig_P6 = read_signed_short(BMP280_I2C_ADDRESS, 0x98)
    dig_P7 = read_signed_short(BMP280_I2C_ADDRESS, 0x9A)
    dig_P8 = read_signed_short(BMP280_I2C_ADDRESS, 0x9C)
    dig_P9 = read_signed_short(BMP280_I2C_ADDRESS, 0x9E)
    
    # 配置 BMP280
    bus.write_byte_data(BMP280_I2C_ADDRESS, 0xF4, 0x27)
    bus.write_byte_data(BMP280_I2C_ADDRESS, 0xF5, 0xA0)
    time.sleep(0.5)
    
    # 读取原始数据
    data = bus.read_i2c_block_data(BMP280_I2C_ADDRESS, 0xF7, 6)
    raw_pressure = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
    raw_temp = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
    
    # 计算温度
    var1 = (raw_temp / 16384.0 - dig_T1 / 1024.0) * dig_T2
    var2 = ((raw_temp / 131072.0 - dig_T1 / 8192.0) ** 2) * dig_T3
    t_fine = var1 + var2
    temperature = t_fine / 5120.0
    
    # 计算气压
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * dig_P6 / 32768.0
    var2 += var1 * dig_P5 * 2.0
    var2 = var2 / 4.0 + dig_P4 * 65536.0
    var1 = (dig_P3 * var1 * var1 / 524288.0 + dig_P2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * dig_P1
    
    if var1 == 0:
        pressure = 0
    else:
        pressure = 1048576.0 - raw_pressure
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        var1 = dig_P9 * pressure * pressure / 2147483648.0
        var2 = pressure * dig_P8 / 32768.0
        pressure += (var1 + var2 + dig_P7) / 16.0
    
    return temperature, pressure

# 读取 CCS811 eCO₂ 和 TVOC
def read_ccs811():
    try:
        data = bus.read_i2c_block_data(CCS811_I2C_ADDRESS, 0x02, 4)
        eCO2 = (data[0] << 8) | data[1]
        tVOC = (data[2] << 8) | data[3]
        return eCO2, tVOC
    except Exception as e:
        print(f"读取 CCS811 失败: {e}")
        return None, None

def pressure_to_altitude(pressure_hpa, temperature_c):
    R = 287.05  # J/(kg·K) 空气气体常数
    g = 9.80665 # m/s² 重力加速度
    P0 = 1040  # hPa 海平面标准气压

    Tm = temperature_c + 273.15  # 转换为开尔文
    altitude = (R / g) * Tm * math.log(P0 / pressure_hpa)
    
    return altitude

# **主循环**
try:
    while True:
        if recording==True:
            print("读取传感器数据中...")
            
            # 读取温湿度
            temperature, humidity = read_si7021_temperature_humidity()
            if temperature is None or humidity is None:
                print("Si7021 读取失败，跳过此轮循环")
                time.sleep(1)
                continue

            # 读取气压
            bmp_temp, pressure = read_bmp280()
            altitude=pressure_to_altitude(pressure/100,bmp_temp)
            if bmp_temp is None or pressure is None:
                print("BMP280 读取失败，跳过此轮循环")
                time.sleep(1)
                continue

            # 读取 eCO₂ 和 TVOC
            eCO2, tVOC = read_ccs811()
            if eCO2 is None or tVOC is None:
                print("CCS811 读取失败，跳过此轮循环")
                time.sleep(1)
                continue

            # 生成 JSON 数据
            sensor_data = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "environment": {
                    "temperature": round(temperature, 2),
                    "humidity": round(humidity, 2),
                    "pressure": round(pressure, 2),
                    "altitude": round(altitude, 2),
                    "eCO2": eCO2,
                    "TVOC": tVOC
                },
                "sensor_id": "RaspberryPi_Sensors"
            }

            # **打印并发送数据**
            print("准备发送数据:", json.dumps(sensor_data, indent=2))
            client.publish(data_topic, json.dumps(sensor_data))
            print("数据已发送")

            time.sleep(1)

except KeyboardInterrupt:
    print("\n程序终止")
finally:
    bus.close()
