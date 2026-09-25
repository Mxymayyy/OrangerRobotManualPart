import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import socket
import time
import math
import os
import urllib.request

# ---------------------------------------------------------------------
# CONFIG — แก้ค่าตรงนี้ให้ตรงกับระบบจริง
# ---------------------------------------------------------------------
ESP32_IP = "192.168.4.1"
ESP32_PORT = 4210   
CAMERA_INDEX = 1

DOOR_HAND = "Left"            # จริงๆคือมือขวา

SEND_RATE_HZ = 15             # ความถี่ในการส่งคำสั่ง

# --- โมเดลสำหรับ HandLandmarker (Tasks API) ---
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
# หมายเหตุ: เดิม hardcode เป็น absolute path ตรงๆ (เช่น
# "/Users/xxx/Desktop/OrangeJuiceRobot/hand_landmarker.task") พอย้าย/เปลี่ยน
# ชื่อโฟลเดอร์โปรเจกต์ (เช่นเป็น OrangeManualRobot) path เดิมจะหาไม่เจอทันที
# เปลี่ยนมาคำนวณจากตำแหน่งไฟล์สคริปต์เองแทน จะได้ไม่พังไม่ว่าจะย้าย/
# เปลี่ยนชื่อโฟลเดอร์ภายหลัง
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)

#ค่าคุมประตู (pinch distance -> servo angle)
# servo แต่ละตัวมีมุม "ปิด"/"เปิด" ของตัวเอง แยกกันตรงๆ ไม่ใช้สูตร mirror
# แบบเดิมแล้ว เพราะทิศทางการหมุนจริงของ servo ทั้งสองตัวไม่สมมาตรกัน
DOOR1_CLOSED_ANGLE = 90   # servo ตัวที่ 1: มุมตอนปิดสนิท
DOOR1_OPEN_ANGLE = 180      # servo ตัวที่ 1: มุมตอนเปิดสุด
DOOR2_CLOSED_ANGLE = 90  # servo ตัวที่ 2: มุมตอนปิดสนิท
DOOR2_OPEN_ANGLE = 0     # servo ตัวที่ 2: มุมตอนเปิดสุด
PINCH_NORM_MIN = 0.1           # ค่า pinch distance (normalized) ต่ำสุดที่ถือว่า "หุบ"
PINCH_NORM_MAX = 1.6           # ค่า pinch distance (normalized) สูงสุดที่ถือว่า "กางเต็มที่"

# --- ค่าคุมทิศทาง (hand-pointing direction) ---
DIRECTION_MIN_VECTOR_LEN = 0.15  # ความยาวขั้นต่ำ (normalized) ของเวกเตอร์ข้อมือ->ปลายนิ้วกลาง
                                   # ก่อนจะยอมรับว่ามือกำลัง "ชี้ทิศ"
DRIVE_SPEED = 250               # ความเร็วตอนเดินหน้า/ถอยหลัง
TURN_SPEED = 100                # ความเร็วตอนหมุนเลี้ยวซ้าย/ขวา

# --- MODE/SRC guard --- from claud code ใส่แล้วใช้ได้
# THIS_SRC คือ "ตัวตน" ของสคริปต์นี้ ใช้แนบไปกับทุกคำสั่งที่ส่ง เพื่อให้
# ESP32 รู้ว่าคำสั่งนี้มาจากสคริปต์ manual จริงหรือเป็นคำสั่งเก่าที่หลุด
# มาจากสคริปต์ auto ที่ยังปิดไม่สนิท ตอนเริ่มโปรแกรมจะส่ง "MODE:MANUAL"
# ไปก่อนหลายครั้ง (กัน UDP หลุดหาย) เพื่อ "ล็อกโหมด" ที่ ESP32
THIS_SRC = "MANUAL"
MODE_ANNOUNCE_REPEATS = 5      # จำนวนครั้งที่ยิง MODE ซ้ำตอนเริ่มโปรแกรม (กัน packet หาย)
MODE_ANNOUNCE_DELAY_S = 0.1    # หน่วงเวลาระหว่างแต่ละครั้งที่ยิง MODE

# ---------------------------------------------------------------------
# landmark index ที่ใช้: 0=ข้อมือ, 4=ปลายนิ้วโป้ง, 8=ปลายนิ้วชี้,
# 9=โคนนิ้วกลาง (ใช้เป็นตัวอ้างอิงสเกลของมือ), 12=ปลายนิ้วกลาง

# เส้นเชื่อมจุด landmark มาตรฐานของมือ 21 จุด ใช้วาด overlay เอง เพราะ
# Tasks API ไม่มีฟังก์ชันวาดสำเร็จรูปแบบ mediapipe.solutions เดิมแล้วเส้า
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index finger
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle finger
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring finger
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky finger
    (0, 17),                                  # palm (wrist-middle finger)
]


def ensure_model_downloaded():
    """ดาวน์โหลดไฟล์โมเดล hand_landmarker.task ถ้ายังไม่มีในเครื่อง"""
    if os.path.exists(MODEL_PATH):
        return
    print(f"กำลังดาวน์โหลดโมเดล HandLandmarker จาก {MODEL_URL} ...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("ดาวน์โหลดโมเดลสำเร็จ")
    except Exception as e:
        raise RuntimeError(
            f"ดาวน์โหลดโมเดลอัตโนมัติไม่สำเร็จ ({e}) "
            f"กรุณาโหลดเองจาก {MODEL_URL} แล้ววางไว้ในโฟลเดอร์เดียวกับสคริปต์นี้ "
            f"ตั้งชื่อไฟล์เป็น '{MODEL_PATH}'"
        )


def compute_pinch_distance(landmarks):
    """
    คำนวณระยะห่างระหว่างปลายนิ้วโป้ง (landmark 4) กับปลายนิ้วชี้
    (landmark 8) แล้ว normalize ด้วยระยะจากข้อมือถึงโคนนิ้วกลาง
    เพื่อให้ค่าที่ได้ไม่ขึ้นกับระยะห่างจากกล้อง

    วิธีคาลิเบรต PINCH_NORM_MIN/MAX เอง:
        1. รันสคริปต์นี้ แล้วหุบนิ้วสนิท ดูค่าที่แสดงบนจอ
           จดค่านั้นไว้เป็น PINCH_NORM_MIN
        2. ลองกางนิ้วให้กว้างที่สุดเท่าที่ต้องการให้ประตูเปิดสุด
           จดค่านั้นไว้เป็น PINCH_NORM_MAX
        3. เอาค่าทั้งสองมาแทนใน config ด้านบน
    """
    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    wrist = landmarks[0]
    middle_mcp = landmarks[9]

    pinch_dist = math.hypot(thumb_tip.x - index_tip.x, thumb_tip.y - index_tip.y)
    hand_scale = math.hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y)

    if hand_scale < 1e-6:
        return 0.0  # กันหารด้วยศูนย์ในกรณีข้อมูล landmark ผิดปกติ

    return pinch_dist / hand_scale


def compute_pinch_ratio(pinch_norm):
    """แปลงค่า pinch distance (normalized) เป็นสัดส่วน 0.0(หุบสนิท) - 1.0(กางสุด)"""
    span = PINCH_NORM_MAX - PINCH_NORM_MIN
    if span <= 0.1:
        return 0.0
    ratio = (pinch_norm - PINCH_NORM_MIN) / span
    return max(0.0, min(1.0, ratio))  # clip ให้อยู่ในช่วง 0.0-1.0


def ratio_to_door_angles(ratio):
    """
    แปลงสัดส่วน 0.0(หุบ)-1.0(กาง) เป็นมุม servo ทั้ง 2 ตัว โดยแต่ละตัวเทียบ
    เส้นตรงระหว่างมุม "ปิด" กับมุม "เปิด" ของตัวเอง (DOOR1_*/DOOR2_* ด้านบน)
    ไม่ได้สมมติว่าทิศทางการหมุนของ servo 2 ตัวสมมาตรกันอีกต่อไป
    """
    angle1 = int(DOOR1_CLOSED_ANGLE + (DOOR1_OPEN_ANGLE - DOOR1_CLOSED_ANGLE) * ratio)
    angle2 = int(DOOR2_CLOSED_ANGLE + (DOOR2_OPEN_ANGLE - DOOR2_CLOSED_ANGLE) * ratio)
    return angle1, angle2


def compute_direction_command(landmarks):
    """
    ดูทิศทางที่มือชี้ไป (เวกเตอร์จากข้อมือ [0] ไปปลายนิ้วกลาง [12]) แล้ว
    จำแนกเป็นหนึ่งใน 4 ทิศ หรือ STOP ถ้าเวกเตอร์สั้นเกินไปเพราะกำมือ)

    ใช้ dominant axis ตัดสินถ้าเวกเตอร์เอียงไปทางแนวตั้งมากกว่า 
    ถือว่าเป็นเดินหน้า/ถอยหลัง ถ้าเอียงไปทางแนวนอนมากกว่าถือว่าเป็นเลี้ยวซ้าย/ขวา

    คืนค่า (left_speed, right_speed, label) สำหรับ debug/overlay
    """
    wrist = landmarks[0]
    middle_tip = landmarks[12]

    dx = middle_tip.x - wrist.x          # + = ชี้ไปทางขวาของภาพ
    dy = middle_tip.y - wrist.y          # + = ชี้ลงล่าง (พิกัดภาพ y เพิ่มลงล่าง)

    vector_len = math.hypot(dx, dy)
    #vector น้อยกว่าที่กำหนด -> ถือว่าไม่ชี้ทิศทางใด ให้หยุด
    if vector_len < DIRECTION_MIN_VECTOR_LEN:
        return 0, 0, "STOP"

    if abs(dy) >= abs(dx):
        # แกนตั้งเด่นกว่า -> เดินหน้า/ถอยหลัง
        if dy < 0:
            return DRIVE_SPEED, DRIVE_SPEED, "FORWARD"
        else:
            return -DRIVE_SPEED, -DRIVE_SPEED, "BACKWARD"
    else:
        # แกนนอนเด่นกว่า -> เลี้ยวซ้าย/ขวา (pivot turn)
        if dx < 0:
            return -TURN_SPEED, TURN_SPEED, "TURN LEFT"
        else:
            return TURN_SPEED, -TURN_SPEED, "TURN RIGHT"


def draw_hand(frame, landmarks, width, height):
    """วาด landmark และเส้นเชื่อมของมือลงบนภาพ"""
    points = [(int(lm.x * width), int(lm.y * height)) for lm in landmarks]
    for start_idx, end_idx in HAND_CONNECTIONS:
        cv2.line(frame, points[start_idx], points[end_idx], (0, 200, 0), 2)
    for point in points:
        cv2.circle(frame, point, 4, (0, 255, 0), -1)


def announce_mode(sock):
    """
    ส่งคำสั่ง MODE:MANUAL ไปยัง ESP32 หลายครั้งตอนเริ่มโปรแกรม เพื่อ
    "ล็อกโหมด" ที่ ESP32 ให้รู้ว่าต่อจากนี้ควรเชื่อคำสั่งจาก SRC:MANUAL
    เท่านั้น (ถ้าสคริปต์ auto ตัวเก่ายังไม่ปิดสนิทและมีคำสั่งหลุดมา
    ESP32 จะเมินเพราะ SRC ไม่ตรงกับโหมดที่ล็อกไว้)
    """
    msg = f"MODE:{THIS_SRC}\n"
    for _ in range(MODE_ANNOUNCE_REPEATS):
        try:
            sock.sendto(msg.encode("utf-8"), (ESP32_IP, ESP32_PORT))
        except OSError as e:
            print(f"ส่ง MODE announce ไม่สำเร็จ: {e}")
        time.sleep(MODE_ANNOUNCE_DELAY_S)


def main():
    ensure_model_downloaded()

    #สร้าง HandLandmarker ด้วย Tasks API
    base_options = mp_python.BaseOptions(model_asset_path=MODEL_PATH)
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        num_hands=2,
        running_mode=mp_vision.RunningMode.IMAGE,  # โหมดประมวลผลทีละภาพ
    )
    landmarker = mp_vision.HandLandmarker.create_from_options(options)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # ล็อกโหมดที่ ESP32 ก่อนเริ่ม loop ควบคุมจริง
    announce_mode(sock)

    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("ERROR: เปิดกล้องไม่ได้ ตรวจสอบค่า CAMERA_INDEX")
        return

    last_send_time = 0.0
    send_interval = 1.0 / SEND_RATE_HZ

    # ค่าล่าสุดที่ใช้งานได้ (เผื่อกรณีมือหลุดจากเฟรมไปชั่วขณะ) เริ่มต้นที่ตำแหน่งปิดสนิทของแต่ละตัว
    last_door_angle_1 = DOOR1_CLOSED_ANGLE
    last_door_angle_2 = DOOR2_CLOSED_ANGLE

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("WARNING: อ่านภาพจากกล้องไม่สำเร็จ")
                break

            frame = cv2.flip(frame, 1)  # กลับภาพซ้าย-ขวาให้เหมือนมองกระจก ควบคุมง่ายขึ้น
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width = frame.shape[:2]

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(mp_image)

            drive_hand_landmarks = None
            door_hand_landmarks = None

            if result.hand_landmarks:
                for hand_landmarks, handedness in zip(result.hand_landmarks, result.handedness):
                    label = handedness[0].category_name
                    draw_hand(frame, hand_landmarks, width, height)

                    if label == DOOR_HAND:
                        door_hand_landmarks = hand_landmarks
                    else:
                        drive_hand_landmarks = hand_landmarks

            # คำสั่งประตู
            if door_hand_landmarks is not None:
                pinch_norm = compute_pinch_distance(door_hand_landmarks)
                ratio = compute_pinch_ratio(pinch_norm)
                door_angle_1, door_angle_2 = ratio_to_door_angles(ratio)
                last_door_angle_1, last_door_angle_2 = door_angle_1, door_angle_2
            else:
                pinch_norm = None
                door_angle_1, door_angle_2 = last_door_angle_1, last_door_angle_2  # fixค่าเดิมถ้าไม่เห็นมือ

            #คำสั่งขับเคลื่อน (จากทิศทางที่มือชี้)
            if drive_hand_landmarks is not None:
                left_speed, right_speed, direction_label = compute_direction_command(drive_hand_landmarks)
            else:
                # ถ้ามือขับหายไปจากเฟรม ให้หยุด
                left_speed, right_speed, direction_label = 0, 0, "STOP (ไม่พบมือขับ)"

            # ส่งคำสั่งผ่าน WiFi
            now = time.time()
            if now - last_send_time >= send_interval:
                msg = f"SRC:{THIS_SRC};M:{left_speed},{right_speed};D:{door_angle_1},{door_angle_2}\n"
                try:
                    sock.sendto(msg.encode("utf-8"), (ESP32_IP, ESP32_PORT))
                except OSError as e:
                    print(f"ส่งคำสั่ง UDP ไม่สำเร็จ: {e}")
                last_send_time = now

            # แสดงผล overlay สถานะ
            pinch_text = f"{pinch_norm:.2f}" if pinch_norm is not None else "N/A"
            cv2.putText(frame, f"Door hand (right): pinch={pinch_text} angles={door_angle_1},{door_angle_2}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 6)
            cv2.putText(frame, f"Drive: {direction_label}  L={left_speed} R={right_speed}",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 6)

            cv2.imshow("Gesture Control - press 'q' to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        # ตอนปิดโปรแกรม ส่งคำสั่งหยุดครั้งสุดท้าย พร้อมสั่งประตูไปมุม "ปิดสนิท"
        # จริงของแต่ละ servo (ไม่ใช่ 0,0 ตรงๆ อีกต่อไป เพราะมุมปิดของ servo
        # แต่ละตัวตอนนี้ไม่เท่ากับ 0)
        try:
            stop_msg = f"SRC:{THIS_SRC};M:0,0;D:{DOOR1_CLOSED_ANGLE},{DOOR2_CLOSED_ANGLE}\n"
            sock.sendto(stop_msg.encode("utf-8"), (ESP32_IP, ESP32_PORT))
        except OSError:
            pass

        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()


if __name__ == "__main__":
    main()
