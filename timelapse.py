import os
import pyautogui as pag
import time

# create folder if not exists
if not os.path.exists("timelapse"):
    os.makedirs("timelapse")

# take screenshot every 10 seconds
while True:
    image = pag.screenshot()
    image.save(f"timelapse/screenshot_{time.time()}.png")
    time.sleep(10)
