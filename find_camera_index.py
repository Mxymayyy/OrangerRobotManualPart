"""
สคริปต์ช่วยหา CAMERA_INDEX ที่ถูกต้อง
=========================================
ไล่เปิดกล้องตั้งแต่ index 0 ถึง 4 ทีละตัว แสดงภาพสด ๆ ให้ดูว่า index
ไหนคือกล้องตัวไหน (กล้องในตัว Mac / iPhone ผ่าน Continuity Camera /
webcam เสริมอื่นๆ)

วิธีใช้: กด 'n' เพื่อไปดู index ถัดไป, กด 'q' เพื่อออกจากโปรแกรม
ดูที่ title แถบหน้าต่างและภาพที่เห็น เพื่อจำว่า index ไหนคือกล้องที่ต้องการ
แล้วเอาเลขนั้นไปใส่ใน CAMERA_INDEX ของ pc_gesture_control.py
"""

import cv2

MAX_INDEX_TO_TRY = 5

for index in range(MAX_INDEX_TO_TRY):
    print(f"\nกำลังลองเปิดกล้อง index {index} ...")
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"index {index}: เปิดไม่ได้ (อาจไม่มีกล้องที่ index นี้)")
        cap.release()
        continue

    print(f"index {index}: เปิดสำเร็จ กด 'n' เพื่อดู index ถัดไป, 'q' เพื่อออก")
    while True:
        ok, frame = cap.read()
        if not ok:
            print(f"index {index}: อ่านภาพไม่สำเร็จ ข้ามไป")
            break
        cv2.putText(frame, f"CAMERA_INDEX = {index}  (n=next, q=quit)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Camera Index Finder", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('n'):
            break
        elif key == ord('q'):
            cap.release()
            cv2.destroyAllWindows()
            exit()

    cap.release()

cv2.destroyAllWindows()
print("\nลองครบทุก index แล้ว")
