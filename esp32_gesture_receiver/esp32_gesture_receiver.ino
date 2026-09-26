#include <WiFi.h>
#include <WiFiUdp.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
// ไลบรารีที่ต้องติดตั้งเพิ่มผ่าน Library Manager: "Adafruit SSD1306" และ
// "Adafruit GFX Library" (ทั้งคู่ค้นหาชื่อตรงๆ ได้เลยใน Arduino IDE)

// --- จอ OLED (I2C, เช่น SSD1306 0.96") ---
// ต่อสาย: SDA -> GPIO21, SCL -> GPIO22 (ขาเริ่มต้นของ Wire บน ESP32 devkit
// ส่วนใหญ่ ถ้าบอร์ดจริงใช้ขาอื่นให้แก้ตอนเรียก Wire.begin() ใน setup())
// ที่อยู่ I2C ปกติคือ 0x3C แต่บางแผงเป็น 0x3D ลองสลับดูถ้าจอไม่ขึ้น
#define OLED_WIDTH 128
#define OLED_HEIGHT 64
#define OLED_I2C_ADDR 0x3C
Adafruit_SSD1306 display(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);



// --- ทางเลือก A: เชื่อมต่อ WiFi เครือข่ายที่มีอยู่เดิม (แนะนำถ้าทั้ง PC
//     และ ESP32 เข้าเครือข่าย/router เดียวกันได้) ---
//const char* WIFI_SSID = "dorm1926 5G";
//const char* WIFI_PASSWORD = "dorm1926";

// --- ทางเลือก B: ให้ ESP32 เป็น Access Point เอง แทนการพึ่ง WiFi
//     สถานที่จัดงาน (uncomment แล้วใช้ WiFi.softAP(...) ใน setup() แทน
//     WiFi.begin(...) ถ้าเลือกใช้ทางนี้) ---
const char* AP_SSID = "ORANGERBOT_AP";
const char* AP_PASSWORD = "pittipiw";

const unsigned int UDP_PORT = 4210;   // ต้องตรงกับ ESP32_PORT ในสคริปต์ PC

// ขามอเตอร์ (แก้ให้ตรงกับการต่อสายจริง / driver board ที่ใช้)
const int LEFT_MOTOR_PWM_PIN = 27 ;
const int LEFT_MOTOR_DIR_PIN = 26;
const int RIGHT_MOTOR_PWM_PIN = 17;
const int RIGHT_MOTOR_DIR_PIN = 16;

// ขา servo ทั้ง 2 ตัว (ประตูบานคู่)
const int DOOR_SERVO_1_PIN = 19;
const int DOOR_SERVO_2_PIN = 33;

// ด้านความปลอดภัย: ถ้าไม่ได้รับคำสั่งที่ถูกต้องภายในเวลานี้ (ms) ให้หยุดหุ่นยนต์
const unsigned long COMMAND_TIMEOUT_MS = 500;

// ---------------------------------------------------------------------

WiFiUDP udp;
Servo doorServo1;
Servo doorServo2;

unsigned long lastCommandMillis = 0;

// currentMode คือโหมดที่ "ล็อก" ไว้ล่าสุด ใช้เทียบกับ SRC ของคำสั่งที่เข้ามา
// เริ่มต้นเป็น "NONE" หมายความว่ายังไม่มีสคริปต์ไหนประกาศ MODE เข้ามาเลย
// (จะยังไม่ยอมรับคำสั่ง M:/D: ใดๆ จนกว่าจะมี MODE: เข้ามาก่อน)
String currentMode = "NONE";

// ค่าล่าสุดที่ใช้แสดงผลบนจอ OLED (อัปเดตทุกครั้งที่มีคำสั่ง M:/D: ที่ผ่าน guard)
int g_leftSpeed = 0;
int g_rightSpeed = 0;
int g_doorAngle1 = 90;   // เริ่มต้นตรงกับมุมปิดสนิทใน setup()
int g_doorAngle2 = 90;
bool g_isStopped = true; // true = อยู่ในสถานะ safety-timeout (ไม่ได้รับคำสั่งมานาน)

unsigned long lastDisplayUpdateMillis = 0;
const unsigned long DISPLAY_UPDATE_INTERVAL_MS = 150; // กันจออัปเดตถี่เกินจนหน่วง loop หลัก

void updateDisplay() {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);

  display.print("MODE: ");
  display.println(currentMode);

  display.println(g_isStopped ? "STATUS: STOPPED (timeout)" : "STATUS: RUNNING");

  display.println("");
  display.print("Motor L: ");
  display.println(g_leftSpeed);
  display.print("Motor R: ");
  display.println(g_rightSpeed);

  display.println("");
  display.print("Door1: ");
  display.print(g_doorAngle1);
  display.println((char)247); // ตัวอักษรองศา (°) โดยประมาณบนฟอนต์เริ่มต้น
  display.print("Door2: ");
  display.print(g_doorAngle2);
  display.println((char)247);

  display.display();
}

void setMotor(int pinIN1, int pinIN2, int speed) {
  // speed อยู่ในช่วง [-255, 255] (โค้ดส่งมาช่วง -150 ถึง 150)
  int magnitude = constrain(abs(speed), 0, 255);

  if (speed == 0) {
    // หยุดหมุน (Coast / Standby): ป้อน LOW ทั้งสองขา
    analogWrite(pinIN1, 0);
    analogWrite(pinIN2, 0);
  } else if (speed > 0) {
    // เดินหน้า: IN1 = PWM, IN2 = LOW
    analogWrite(pinIN1, magnitude);
    analogWrite(pinIN2, 0);
  } else {
    // ถอยหลัง: IN1 = LOW, IN2 = PWM
    analogWrite(pinIN1, 0);
    analogWrite(pinIN2, magnitude);
  }
}

void stopRobot() {
  setMotor(LEFT_MOTOR_PWM_PIN, LEFT_MOTOR_DIR_PIN, 0);
  setMotor(RIGHT_MOTOR_PWM_PIN, RIGHT_MOTOR_DIR_PIN, 0);
}

// แยกวิเคราะห์ข้อความที่รับมา รองรับ 2 รูปแบบ:
//   "MODE:MANUAL"                          -> ล็อกโหมดใหม่ + หยุดรถทันที
//   "SRC:MANUAL;M:150,150;D:45,45"         -> คำสั่งควบคุมปกติ (ต้อง SRC ตรง currentMode)
// คืนค่า true ถ้า parse และนำไปใช้สำเร็จ
bool parseAndApplyCommand(const String& msg) {

  // --- กรณีเป็นคำสั่งล็อกโหมด ---
  if (msg.startsWith("MODE:")) {
    currentMode = msg.substring(5);
    currentMode.trim();
    stopRobot();  // หยุดรถทุกครั้งที่มีการสลับโหมด กันความเร็วเดิมค้างข้ามโหมด
    g_leftSpeed = 0;
    g_rightSpeed = 0;
    Serial.print("MODE locked to: ");
    Serial.println(currentMode);
    return true;
  }

  // --- กรณีเป็นคำสั่งควบคุมปกติ ต้องมี SRC guard ก่อน ---
  int srcIndex = msg.indexOf("SRC:");
  if (srcIndex == -1) return false;  // ไม่มี SRC guard -> ไม่ยอมรับ ทิ้งคำสั่งนี้

  int srcEnd = msg.indexOf(';', srcIndex);
  if (srcEnd == -1) return false;
  String src = msg.substring(srcIndex + 4, srcEnd);
  src.trim();

  // ถ้า SRC ของคำสั่งนี้ไม่ตรงกับโหมดที่ล็อกไว้ล่าสุด -> เมินคำสั่งนี้ทิ้ง
  // (นี่คือจุดที่ป้องกันคำสั่งเก่าจากสคริปต์ auto/manual ที่ยังปิดไม่สนิท
  // ไม่ให้หลุดเข้ามาสั่งงานซ้อนกับสคริปต์ปัจจุบัน)
  if (src != currentMode) {
    return false;
  }

  int mIndex = msg.indexOf("M:");
  int dIndex = msg.indexOf("D:");
  if (mIndex == -1 || dIndex == -1) return false;

  // --- แยกส่วน M:left,right ---
  String mPart = msg.substring(mIndex + 2, msg.indexOf(';', mIndex));
  int mCommaIndex = mPart.indexOf(',');
  if (mCommaIndex == -1) return false;

  int leftSpeed = mPart.substring(0, mCommaIndex).toInt();
  int rightSpeed = mPart.substring(mCommaIndex + 1).toInt();

  // --- แยกส่วน D:angle1,angle2 ---
  String dPart = msg.substring(dIndex + 2);
  int dCommaIndex = dPart.indexOf(',');
  if (dCommaIndex == -1) return false;

  int doorAngle1 = dPart.substring(0, dCommaIndex).toInt();
  int doorAngle2 = dPart.substring(dCommaIndex + 1).toInt();
  doorAngle1 = constrain(doorAngle1, 0, 180);
  doorAngle2 = constrain(doorAngle2, 0, 180);

  setMotor(LEFT_MOTOR_PWM_PIN, LEFT_MOTOR_DIR_PIN, leftSpeed);
  setMotor(RIGHT_MOTOR_PWM_PIN, RIGHT_MOTOR_DIR_PIN, rightSpeed);
  doorServo1.write(doorAngle1);
  doorServo2.write(doorAngle2);

  // เก็บค่าล่าสุดไว้แสดงผลบนจอ OLED
  g_leftSpeed = leftSpeed;
  g_rightSpeed = rightSpeed;
  g_doorAngle1 = doorAngle1;
  g_doorAngle2 = doorAngle2;
  g_isStopped = false;

  return true;
}

void setup() {
  Serial.begin(115200);

  Wire.begin(); // SDA=21, SCL=22 (ค่า default บน ESP32 devkit ส่วนใหญ่)
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDR)) {
    Serial.println("[OLED] ERROR: หาจอไม่เจอ เช็คสาย SDA/SCL และที่อยู่ I2C (0x3C/0x3D)");
  } else {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(SSD1306_WHITE);
    display.setCursor(0, 0);
    display.println("GEMBOT booting...");
    display.display();
  }

  pinMode(LEFT_MOTOR_DIR_PIN, OUTPUT);
  pinMode(RIGHT_MOTOR_DIR_PIN, OUTPUT);
  pinMode(LEFT_MOTOR_PWM_PIN, OUTPUT);
  pinMode(RIGHT_MOTOR_PWM_PIN, OUTPUT);

  doorServo1.attach(DOOR_SERVO_1_PIN);
  doorServo2.attach(DOOR_SERVO_2_PIN);
  doorServo1.write(0);  // เริ่มต้นให้ประตูปิด
  doorServo2.write(0);

  // --- ทางเลือก A: เชื่อมต่อ WiFi เครือข่ายเดิม ---
  /*WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("Connected. IP address: ");
  Serial.println(WiFi.localIP()); */ // <-- เอา IP นี้ไปใส่ ESP32_IP ในสคริปต์ PC

  // --- ทางเลือก B: ให้ ESP32 เป็น AP เอง (ถ้าใช้ทางนี้ ให้ comment
  //     ทางเลือก A ด้านบนออกด้วย) ---
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  Serial.print("AP IP address: ");
  Serial.println(WiFi.softAPIP());  // ปกติจะเป็น 192.168.4.1

  udp.begin(UDP_PORT);
  lastCommandMillis = millis();
}

void loop() {
  int packetSize = udp.parsePacket();
  if (packetSize > 0) {
    char buffer[128];
    int len = udp.read(buffer, sizeof(buffer) - 1);
    if (len > 0) {
      buffer[len] = '\0';
      String msg = String(buffer);
      if (parseAndApplyCommand(msg)) {
        // นับเวลาปลอดภัย (timeout) เฉพาะตอนที่เป็นคำสั่งที่ผ่าน guard
        // จริงๆ เท่านั้น (คำสั่ง MODE: ก็ถือว่านับด้วย เพราะแปลว่ายังมี
        // สคริปต์ที่ยังทำงานอยู่ฝั่ง PC)
        lastCommandMillis = millis();
      }
    }
  }

  // ด้านความปลอดภัย: ถ้าไม่ได้รับคำสั่งที่ผ่าน guard มาสักพัก (WiFi หลุด,
  // สคริปต์ PC ค้าง ฯลฯ) ให้หยุดหุ่นยนต์ทันที
  if (millis() - lastCommandMillis > COMMAND_TIMEOUT_MS) {
    stopRobot();
    g_isStopped = true;
  }

  // วาดจอ OLED เป็นระยะ (ไม่ทุก loop เพราะ I2C ช้ากว่า loop หลักมาก จะทำให้หน่วง)
  if (millis() - lastDisplayUpdateMillis > DISPLAY_UPDATE_INTERVAL_MS) {
    updateDisplay();
    lastDisplayUpdateMillis = millis();
  }
}
