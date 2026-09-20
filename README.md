# OrangerRobot

หุ่นยนต์ควบคุมด้วยท่าทางมือ (hand gesture)
ผ่านกล้อง webcam บน PC แล้วส่งคำสั่งไปยัง ESP32 ผ่าน WiFi (UDP)

นี้เป็นส่วนโหมด Manual** เท่านั้น (โหมด Auto เพื่อนทำ สู้ๆนะbro)

## โครงสร้างโปรเจกต์

| ไฟล์ | หน้าที่ |
|---|---|
| `pc_manual_control.py` | รันบน PC — เปิดกล้อง ตรวจจับมือด้วย MediaPipe HandLandmarker (Tasks API) แล้วส่งคำสั่งควบคุมผ่าน UDP ไปยัง ESP32 | 
| `esp32_gesture_receiver/esp32_gesture_receiver.ino` | รันบน ESP32 — รับคำสั่ง UDP แล้วขับมอเตอร์ 2 ตัว + servo ประตู 2 ตัว |
| `find_camera_index.py` | เครื่องมือช่วยหาว่า `CAMERA_INDEX` ที่ถูกต้องของกล้องที่ต้องการคือเลขอะไร |
| `hand_landmarker.task` | โมเดล MediaPipe (**ไม่ได้เก็บใน repo** — ดาวน์โหลดอัตโนมัติตอนรันครั้งแรก) |

## วิธีติดตั้ง (ฝั่ง PC)

```bash
pip install opencv-python mediapipe
python find_camera_index.py     # หา CAMERA_INDEX ที่ถูกต้องก่อน
python pc_manual_control.py     # รันตัวควบคุมจริง (ดาวน์โหลดโมเดลอัตโนมัติครั้งแรก)
```

ถ้าดาวน์โหลดโมเดลอัตโนมัติไม่สำเร็จ โหลดเองได้จาก:
https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task
แล้ววางไว้โฟลเดอร์เดียวกับสคริปต์ (ดูชื่อไฟล์ที่ต้องใช้ใน `MODEL_PATH` ในโค้ด)

## วิธีติดตั้ง (ฝั่ง ESP32)

1. เปิด `esp32_gesture_receiver.ino` ด้วย Arduino IDE
2. ติดตั้ง library `ESP32Servo` ผ่าน Library Manager
3. แก้ค่า `AP_SSID` / `AP_PASSWORD` (หรือ `WIFI_SSID` / `WIFI_PASSWORD` ถ้าใช้โหมด join เครือข่ายเดิมแทน)
4. แก้ pin มอเตอร์/servo ให้ตรงกับการต่อสายจริง
5. อัปโหลดโค้ดขึ้นบอร์ด แล้วเปิด Serial Monitor (115200 baud) เพื่อดู IP ที่ได้

## Config สำคัญที่ต้องปรับก่อนใช้จริง

ฝั่ง PC (`pc_manual_control.py`):
- `ESP32_IP` / `ESP32_PORT` — ต้องตรงกับ IP จริงของ ESP32 (ปกติ `192.168.4.1` ถ้าใช้โหมด AP)
- `CAMERA_INDEX` — ใช้ `find_camera_index.py` ช่วยหา
- `DOOR_HAND` ("Left"/"Right") — เลือกว่ามือข้างไหนคุมประตู (**ระวังเรื่อง mirror**
  ดูหัวข้อ "เรื่องที่มักสับสน" ด้านล่าง)
- `PINCH_NORM_MIN` / `PINCH_NORM_MAX` — ต้องคาลิเบรตเองตามมือ/กล้องของผู้ใช้แต่ละคน
- `DRIVE_SPEED` / `TURN_SPEED` — ความเร็วมอเตอร์
- `DOOR_SERVO2_MIRRORED` — true ถ้า servo บานคู่ต้องหมุนสวนทางกัน

ฝั่ง ESP32:
- pin มอเตอร์/servo, `COMMAND_TIMEOUT_MS` (ความปลอดภัย: หยุดอัตโนมัติถ้าไม่ได้รับคำสั่งนานเกินนี้)

## MODE/SRC guard คืออะไร

เพื่อกันไม่ให้คำสั่งจากสคริปต์เก่า (เช่น auto ที่ปิดไม่สนิท) หลุดมาแทรกตอน
สลับโหมด ทุกคำสั่งที่ ESP32 รับต้องมี `SRC:` ตรงกับ `MODE:` ล่าสุดที่ล็อกไว้
ก่อนถึงจะถูกนำไปใช้จริง (ดูรายละเอียดในคอมเมนต์ต้นไฟล์ `.ino`)

## เรื่องที่มักงง(จากการดีบัก👍)

- **กล้อง flip ภาพ** (`cv2.flip(frame, 1)`) ทำให้ label "Left"/"Right" ที่
  MediaPipe ตรวจจับ **สลับข้าง** กับมือจริงของผู้ใช้ — ถ้าคุมประตูผิดข้าง
  ให้ลองสลับค่า `DOOR_HAND` ก่อน
- **Motor driver แบบ L298N ที่มีจัมเปอร์ ENA/ENB ติดอยู่**: ถ้า PWM ไม่ได้
  ต่อเข้าขา ENA จริง คำสั่ง stop (speed=0) อาจไม่ทำให้มอเตอร์หยุดจริง
  ต้องเช็คการต่อสายให้ตรงกับ 3 ขา (IN1/IN2/ENA) ตามจริง
- overlay บนจอ PC ที่เขียนว่า `Door hand (Left/Right)` เป็นการโชว์ค่า
  config ตรงๆ ไม่ใช่ label ที่ตรวจจับได้จริงในเฟรมนั้น

## Known issues
- [ ] Calibration ค่า pinch ยังต้องทำมือทุกครั้งที่เปลี่ยนกล้อง/สภาพแสง
