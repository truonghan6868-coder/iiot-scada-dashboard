import json
import time
import paho.mqtt.client as mqtt
import snap7
from snap7.util import get_real, set_real

# --- CẤU HÌNH PLC S7-1200 ---
PLC_IP = "192.168.0.1"  # Thay bằng IP thực tế của PLC
RACK = 0
SLOT = 1
DB_NUMBER = 3

# --- CẤU HÌNH MQTT BROKER ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 1883
MQTT_TELEMETRY_TOPIC = "factory/cuchi/line1/temperature"
MQTT_COMMAND_TOPIC = "factory/cuchi/line1/command"  # Topic nhận lệnh điều khiển


# Hàm callback khi nhận được lệnh điều khiển từ Web Dashboard qua MQTT
def on_message(client, userdata, msg):
  try:
    if msg.topic == MQTT_COMMAND_TOPIC:
      payload = json.loads(msg.payload.decode("utf-8"))
      setpoint_1 = payload.get("setpoint_1")

      if setpoint_1 is not None:
        # Chuẩn bị bộ đệm 4 byte kiểu REAL (Float) để ghi vào DB3
        data_to_write = bytearray(4)
        set_real(data_to_write, 0, float(setpoint_1))

        # Ghi vào DB3, offset 8 (tương ứng với ô nhớ viết dữ liệu xuống PLC)
        plc.db_write(DB_NUMBER, 8, data_to_write)
        print(
            f"📥 Đã nhận lệnh từ Web -> Ghi Setpoint 1 = {setpoint_1} xuống"
            f" PLC (DB3.DBD8)"
        )
  except Exception as e:
    print(f"❌ Lỗi ghi dữ liệu xuống PLC: {e}")


# Hàm kết nối MQTT callback
def on_connect(client, userdata, flags, rc):
  print(f"✅ Đã kết nối tới MQTT Broker với mã phản hồi: {rc}")
  client.subscribe(MQTT_COMMAND_TOPIC)  # Đăng ký lắng nghe kênh lệnh điều khiển


def main():
  global plc
  # Khởi tạo kết nối PLC
  plc = snap7.client.Client()
  try:
    plc.connect(PLC_IP, RACK, SLOT)
    print(f"✅ Đã kết nối thành công tới PLC S7-1200 tại IP: {PLC_IP}")
  except Exception as e:
    print(f"❌ Không thể kết nối PLC: {e}")
    return

  # Khởi tạo MQTT Client
  client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
  client.on_connect = on_connect
  client.on_message = on_message

  print(f"Đang kết nối tới MQTT Broker tại {MQTT_BROKER}...")
  client.connect(MQTT_BROKER, MQTT_PORT, 60)
  client.loop_start()  # Chạy tiến trình ngầm cho MQTT

  print("\n🚀 Gateway đang chạy (Đọc dữ liệu & Lắng nghe lệnh điều khiển)...")
  try:
    while True:
      if plc.get_connected():
        # Đọc dữ liệu từ DB3 (Ví dụ đọc từ offset 0 và 4)
        db_data = plc.db_read(DB_NUMBER, 0, 8)
        temp_1 = get_real(db_data, 0)
        temp_2 = get_real(db_data, 4)

        # Tạo gói tin JSON telemetry
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "temp_1": round(temp_1, 2),
            "temp_2": round(temp_2, 2),
        }
        message = json.dumps(payload)

        # Publish lên MQTT Broker
        client.publish(MQTT_TELEMETRY_TOPIC, message)
        print(f"📤 Đã publish lên [{MQTT_TELEMETRY_TOPIC}] -> {message}")

      time.sleep(2)
  except KeyboardInterrupt:
    print("\n🛑 Đã dừng Gateway.")
    plc.disconnect()
    client.loop_stop()


if __name__ == "__main__":
  main()