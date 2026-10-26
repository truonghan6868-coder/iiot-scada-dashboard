from queue import Queue
import datetime
import json
import time
import paho.mqtt.client as mqtt
import pandas as pd
import streamlit as st

# --- CẤU HÌNH GIAO DIỆN STREAMLIT ---
st.set_page_config(
    page_title="IIoT MQTT SCADA Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- CẤU HÌNH MQTT BROKER (Sử dụng cổng bảo mật WSS 8884 trên Cloud) ---
MQTT_BROKER = "broker.hivemq.com"
MQTT_PORT = 8884
MQTT_TELEMETRY_TOPIC = "factory/cuchi/line1/temperature"
MQTT_COMMAND_TOPIC = "factory/cuchi/line1/command"

# Tên file CSV lưu lịch sử
CSV_LOG_FILE = "plant_history_log.csv"

# Tạo Global Queue độc lập để nhận dữ liệu telemetry
global_msg_queue = Queue()

# Khởi tạo Session State
if "temp_1" not in st.session_state:
  st.session_state.temp_1 = 0.0
if "temp_2" not in st.session_state:
  st.session_state.temp_2 = 0.0
if "history_df" not in st.session_state:
  st.session_state.history_df = pd.DataFrame(
      columns=["Time", "Temp_1", "Temp_2"]
  )


# Callback nhận dữ liệu telemetry từ MQTT
def on_message(client, userdata, msg):
  try:
    if msg.topic == MQTT_TELEMETRY_TOPIC:
      payload = json.loads(msg.payload.decode("utf-8"))
      global_msg_queue.put(payload)
  except Exception as e:
    print(f"Lỗi đọc tin nhắn MQTT: {e}")


def on_connect(client, userdata, flags, rc):
  if rc == 0:
    print("✅ Dashboard đã kết nối MQTT Broker qua WSS thành công!")
    client.subscribe(MQTT_TELEMETRY_TOPIC)
  else:
    print(f"⚠️ Kết nối thất bại, mã lỗi: {rc}")


# Khởi tạo MQTT Client chạy ngầm duy nhất với chứng chỉ bảo mật TLS/WSS cho Cloud
@st.cache_resource
def init_mqtt_subscriber():
  client = mqtt.Client(
      client_id="", clean_session=True, transport="websockets"
  )
  client.on_message = on_message
  client.on_connect = on_connect
  client.reconnect_delay_set(min_delay=1, max_delay=60)

  # Kích hoạt SSL/TLS để chạy an toàn trên môi trường HTTPS của Streamlit Cloud
  client.tls_set()

  try:
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
    client.loop_start()
  except Exception as e:
    print(f"Không thể kết nối Broker: {e}")
  return client


mqtt_client = init_mqtt_subscriber()

# --- THIẾT KẾ GIAO DIỆN WEB SCADA ---
st.title("🏭 HỆ THỐNG GIÁM SÁT, ĐIỀU KHIỂN & CẢNH BÁO IIoT")
st.markdown(
    "Giao diện Web SCADA hoàn chỉnh tích hợp giám sát, điều khiển, ghi log và"
    " cảnh báo ngưỡng."
)

# --- SIDEBAR: THÔNG SỐ, ĐIỀU KHIỂN, CẢNH BÁO & BÁO CÁO ---
with st.sidebar:
  st.header("⚙️ Thông số hệ thống")
  st.info(f"Broker: {MQTT_BROKER} (WSS)")
  st.success("Trạng thái: Đang kết nối MQTT ổn định 🟢")

  st.markdown("---")
  st.header("🚨 Cài đặt Ngưỡng Cảnh Báo")
  alarm_limit_1 = st.number_input(
      "Ngưỡng Alarm Temp 1 (°C)", min_value=0.0, max_value=150.0, value=45.0
  )
  alarm_limit_2 = st.number_input(
      "Ngưỡng Alarm Temp 2 (°C)", min_value=0.0, max_value=150.0, value=50.0
  )

  st.markdown("---")
  st.header("🎛️ Bảng điều khiển (Command)")

  with st.form(key="control_form"):
    new_setpoint_1 = st.number_input(
        "Cài đặt Setpoint 1 (°C)",
        min_value=0.0,
        max_value=100.0,
        value=35.0,
        step=0.5,
    )
    submit_button = st.form_submit_button(
        label="🚀 Gửi lệnh xuống PLC", type="primary"
    )

    if submit_button:
      command_payload = json.dumps({"setpoint_1": new_setpoint_1})
      mqtt_client.publish(MQTT_COMMAND_TOPIC, command_payload)
      st.success(f"Đã gửi lệnh Setpoint 1 = {new_setpoint_1} °C tới PLC!")

  st.markdown("---")
  st.header("📊 Quản lý Báo cáo Lịch sử")

  try:
    with open(CSV_LOG_FILE, "rb") as f:
      st.download_button(
          label="📥 Tải xuống Báo cáo CSV",
          data=f,
          file_name=f"SCADA_Report_{datetime.date.today()}.csv",
          mime="text/csv",
      )
  except FileNotFoundError:
    st.info("Chưa có dữ liệu lịch sử để tải xuống.")


# --- PHẦN HIỂN THỊ DỮ LIỆU THỜI GIAN THỰC & CẢNH BÁO ---
@st.fragment(run_every=2)
def render_dashboard():
  while not global_msg_queue.empty():
    payload = global_msg_queue.get()
    st.session_state.temp_1 = payload.get("temp_1", 0.0)
    st.session_state.temp_2 = payload.get("temp_2", 0.0)
    timestamp = payload.get("timestamp", time.strftime("%H:%M:%S"))

    new_data = pd.DataFrame(
        {
            "Time": [timestamp],
            "Temp_1": [st.session_state.temp_1],
            "Temp_2": [st.session_state.temp_2],
        }
    )
    st.session_state.history_df = pd.concat(
        [st.session_state.history_df, new_data], ignore_index=True
    )
    if len(st.session_state.history_df) > 50:
      st.session_state.history_df = st.session_state.history_df.iloc[1:]

    log_record = pd.DataFrame(
        {
            "Timestamp": [
                payload.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S"))
            ],
            "Temp_1": [st.session_state.temp_1],
            "Temp_2": [st.session_state.temp_2],
        }
    )
    try:
      with open(CSV_LOG_FILE, "a", encoding="utf-8") as f:
        log_record.to_csv(
            f, header=f.tell() == 0, index=False, encoding="utf-8-sig"
        )
    except Exception as e:
      print(f"Lỗi ghi log CSV: {e}")

  is_alarm_1 = st.session_state.temp_1 > alarm_limit_1
  is_alarm_2 = st.session_state.temp_2 > alarm_limit_2

  if is_alarm_1 or is_alarm_2:
    alarm_msg = "⚠️ **CẢNH BÁO QUÁ NHIỆT:** "
    if is_alarm_1:
      alarm_msg += f"[Nhiệt độ 1 vượt ngưỡng {alarm_limit_1}°C] "
    if is_alarm_2:
      alarm_msg += f"[Nhiệt độ 2 vượt ngưỡng {alarm_limit_2}°C]"
    st.error(alarm_msg)

  col1, col2 = st.columns(2)
  with col1:
    delta_text = (
        "🔥 VƯỢT NGƯỠNG!" if is_alarm_1 else "Ổn định trong giới hạn"
    )
    st.metric(
        label="🌡️ Nhiệt độ 1 (Temp_1)",
        value=f"{st.session_state.temp_1} °C",
        delta=delta_text,
        delta_color="inverse" if is_alarm_1 else "normal",
    )
  with col2:
    delta_text_2 = (
        "🔥 VƯỢT NGƯỠNG!" if is_alarm_2 else "Ổn định trong giới hạn"
    )
    st.metric(
        label="🌡️ Nhiệt độ 2 (Temp_2)",
        value=f"{st.session_state.temp_2} °C",
        delta=delta_text_2,
        delta_color="inverse" if is_alarm_2 else "normal",
    )

  st.markdown("---")
  st.subheader("📈 Biểu đồ xu hướng trực tuyến từ MQTT Broker")

  if not st.session_state.history_df.empty:
    chart_data = st.session_state.history_df.set_index("Time")
    st.line_chart(chart_data)
  else:
    st.warning("Đang chờ dữ liệu đầu tiên từ MQTT Broker...")


render_dashboard()