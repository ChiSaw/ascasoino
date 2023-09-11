#!/usr/bin/python
# -*- coding: UTF-8 -*-

import os
import sys
import time
import logging
import math
from threading import Timer
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as gpio
from lib import LCD_1inch28, Touch_1inch28, EspressoShotSimulator
import yaml
from bluepy.btle import Scanner, DefaultDelegate, Peripheral
import binascii


# Constants
COLORS = {
    "primary_dark": "#012E40",
    "primary_dark_medium": "#024959",
    "primary_medium": "#026773",
    "primary_light": "#3CA6A6",
    "secondary": "#F2E3D5",
    "error": "#D95252",
}
GESTURES = {
    "swipe_up": 0x01,
    "swipe_down": 0x02,
    "swipe_left": 0x03,
    "swipe_right": 0x04,
    "single_click": 0x05,
    "double_click": 0x0B,
    "long_press": 0x0C,
}
SHOT_RELAY = 14
SHOT_AFTER_DRIPPING_WEIGHT_G = 2
SHOT_BUTTON_ASCASO_INT = 21
TP_INT = 5

# Setup Logging
logging.basicConfig(level=logging.DEBUG)

# Global Variables
touch_interrupt_flag = 0
shot_button_interrupt_flag = 0
now = 0.0
shot_started_time = 0.0
shot_time_s = 0.0
shot_current_weight_g = 0
shot_target_weight_g = 35
scale_connected = False
shot_running = False
mode = 1
disp = {}
shot_button_debounce_ms = 300  # debounce time in milliseconds
shot_button_last_interrupt_time = 0

# Initialize Objects
scale = EspressoShotSimulator.EspressoShotSimulator(shot_target_weight_g)
touch = Touch_1inch28.Touch_1inch28()

# Path
path = os.path.dirname(os.path.realpath(__file__))


class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            print(f"Discovered device {dev.addr}")


def initialize_yaml():
    """Initialize the YAML file with default values if it doesn't exist."""
    print(os.path.join(path, "settings.yaml"))
    if not os.path.exists(os.path.join(path, "settings.yaml")):
        with open("./settings.yaml", "w") as file:
            yaml.dump({"shot_target_weight_g": 35}, file)


def read_yaml():
    """Read the variable from the YAML file."""
    with open(os.path.join(path, "settings.yaml"), "r") as file:
        data = yaml.safe_load(file)
        return data.get("shot_target_weight_g", 35)


def write_yaml(value):
    """Write the variable to the YAML file."""
    with open(os.path.join(path, "settings.yaml"), "w") as file:
        yaml.dump({"shot_target_weight_g": value}, file)


def update_shot_target_weight_g(new_value):
    global shot_target_weight_g
    shot_target_weight_g = new_value
    write_yaml(new_value)


def shot_button_callback(pin):
    global shot_button_last_interrupt_time
    current_time = int(round(time.time() * 1000))  # get current time in milliseconds

    # If interrupts come faster than the debounce time, ignore them
    if current_time - shot_button_last_interrupt_time > shot_button_debounce_ms:
        # Your button pressed logic here
        shot_button_interrupt_flag = 1


def touch_interrupt_callback(TP_INT):
    """Handle the interrupt callback."""
    global touch_interrupt_flag
    if mode == 1:
        touch_interrupt_flag = 1
        touch.get_point()
    else:
        touch.Gestures = touch.Touch_Read_Byte(0x01)


def handled_touch_interrupt():
    """Reset the touch interrupt flag."""
    global touch_interrupt_flag
    touch_interrupt_flag = 0
    touch.Gestures = 0


def handled_shot_button_interrupt():
    """Reset the shot button interrupt flag."""
    global shot_button_interrupt_flag
    shot_button_interrupt_flag = 0


def manage_shot(on):
    """Manage the espresso shot."""
    global shot_running, shot_started_time, now
    gpio.output(SHOT_RELAY, True)
    time.sleep(0.1)
    gpio.output(SHOT_RELAY, False)

    if on:
        shot_started_time = now
        scale.start_shot()
        shot_running = True
    else:
        Timer(30, reset_shot).start()
        Timer(3, scale.stop_shot).start()
        shot_running = False


def draw_bluetooth_connection(draw):
    global scale_connected
    thickness = 4
    if scale_connected:
        draw.ellipse(((240 / 2 - thickness / 2), 20, (240 / 2 + thickness / 2, 20 + thickness)), fill=COLORS["primary_light"])
    else:
        draw.ellipse(((240 / 2 - thickness / 2), 20, (240 / 2 + thickness / 2, 20 + thickness)), fill=COLORS["primary_dark_medium"])


def reset_shot():
    """Reset the shot time."""
    global shot_time_s
    shot_time_s = 0.0


def is_point_in_circular_segment(x, y, origin_x, origin_y, start_angle, end_angle, radius):
    """
    Check if a point is inside a circular segment.

    Parameters:
    x, y (float): Coordinates of the point to check.
    origin_x, origin_y (float): Coordinates of the circle's origin.
    start_angle, end_angle (float): Start and end angles of the circular segment (in degrees).
    radius (float): Radius of the circle.

    Returns:
    bool: True if the point is inside the circular segment, False otherwise.
    """
    # Calculate the distance between the point and the circle's origin
    distance = math.sqrt((x - origin_x) ** 2 + (y - origin_y) ** 2)

    # Calculate the angle of the point with respect to the circle's origin (in radians)
    angle = math.degrees(math.atan2(y - origin_y, x - origin_x))

    # Normalize the calculated angle to a value between 0 and 360
    if angle < 0:
        angle += 360

    # Normalize the start and end angles to values between 0 and 360
    start_angle = start_angle % 360
    end_angle = end_angle % 360

    # Check if the distance is less than or equal to the radius
    # and the angle is between the start and end angles
    return distance <= radius and start_angle <= angle <= end_angle


def display_image(image, filepath, position=(0, 0), size=(240, 240)):
    """Load and display an image from the specified file path at the given position and size."""
    try:
        # Open an image file
        with Image.open(filepath) as img:
            # Resize the image to the specified size
            # img = img.resize(size, Image.LANCZOS)
            image.paste(img, position)
    except FileNotFoundError:
        logging.error(f"Image file not found: {filepath}")
    except IOError as e:
        logging.error(f"Error opening image: {e}")


def draw_thick_arc(draw, bounding_box, start_angle, end_angle, thickness=10):
    """Draw a thick arc on the canvas."""
    for i in range(thickness):
        offset = i - thickness // 2
        adjusted_box = (
            bounding_box[0] + offset,
            bounding_box[1] + offset,
            bounding_box[2] - offset,
            bounding_box[3] - offset,
        )
        if end_angle > 360:
            draw.arc(adjusted_box, start_angle, 360, COLORS["primary_light"])
            draw.arc(adjusted_box, start_angle, (end_angle - 360), COLORS["error"])
        else:
            draw.arc(adjusted_box, start_angle, 360, COLORS["primary_dark_medium"])
            draw.arc(adjusted_box, start_angle, end_angle, COLORS["primary_light"])

    # Center of the bounding box
    center_x = (bounding_box[2] + bounding_box[0]) / 2
    center_y = (bounding_box[3] + bounding_box[1]) / 2

    # Radius of the bounding box (average of width and height)
    radius = ((bounding_box[2] - bounding_box[0]) + (bounding_box[3] - bounding_box[1])) / 4

    # Adjusting the start and end angles to match the drawing coordinate system
    start_angle_adj = 360 - start_angle
    end_angle_adj = 360 - end_angle

    # Calculate the coordinates for the rounded ends
    start_x = center_x + radius * math.cos(math.radians(start_angle_adj))
    start_y = center_y - radius * math.sin(math.radians(start_angle_adj))
    end_x = center_x + radius * math.cos(math.radians(end_angle_adj))
    end_y = center_y - radius * math.sin(math.radians(end_angle_adj))

    # Draw rounded ends
    draw.ellipse((start_x - thickness / 2, start_y - thickness / 2, start_x + thickness / 2, start_y + thickness / 2), fill=COLORS["primary_light"])
    draw.ellipse((end_x - thickness / 2, end_y - thickness / 2, end_x + thickness / 2, end_y + thickness / 2), fill=COLORS["primary_light"])
    draw.ellipse((end_x - thickness / 4, end_y - thickness / 4, end_x + thickness / 4, end_y + thickness / 4), fill="white")


def draw_shot_weight_progress(draw):
    """Draw the shot weight progress on the canvas."""
    global shot_target_weight_g
    global shot_current_weight_g
    # Calculate the angle based on the current shot weight
    angle = (shot_current_weight_g / shot_target_weight_g) * 360

    # Draw the circular progress bar
    bounding_box = (10, 10, 230, 230)  # Adjust as necessary
    draw_thick_arc(draw, bounding_box, 0, angle, thickness=10)


def initialize_display():
    """Initialize the display."""
    disp = LCD_1inch28.LCD_1inch28()
    disp.Init()
    disp.clear()
    return disp


def setup_fonts():
    """Setup fonts."""
    fonts = {
        "xs": ImageFont.truetype("./assets/Font00.ttf", 20),
        "s": ImageFont.truetype("./assets/Font00.ttf", 25),
        "m": ImageFont.truetype("./assets/Font00.ttf", 30),
        "l": ImageFont.truetype("./assets/Font00.ttf", 35),
        "xl": ImageFont.truetype("./assets/Font00.ttf", 40),
    }
    return fonts


def main():
    """Main function to execute the script."""
    global now, shot_time_s, shot_current_weight_g, shot_target_weight_g, shot_running, disp, scale_connected

    # Initialize YAML and set shot_target_weight_g
    initialize_yaml()
    shot_target_weight_g = read_yaml()

    disp = initialize_display()

    touch.init()
    touch.int_irq(TP_INT, touch_interrupt_callback)
    gpio.setup(SHOT_RELAY, gpio.OUT)
    gpio.output(SHOT_RELAY, 0)

    # Set up the button pin as an input with an internal pull-up resistor
    gpio.setup(SHOT_BUTTON_ASCASO_INT, gpio.IN, pull_up_down=gpio.PUD_UP)

    # Add an interrupt on the falling edge (from HIGH to LOW) of the button pin
    gpio.add_event_detect(SHOT_BUTTON_ASCASO_INT, gpio.FALLING, callback=shot_button_callback, bouncetime=shot_button_debounce_ms)

    fonts = setup_fonts()

    # Create blank image for drawing.
    startup_image = Image.new("RGB", (disp.width, disp.height), COLORS["primary_dark"])
    startup_draw = ImageDraw.Draw(startup_image)
    startup_draw.text((65, 60), "Ascaso", fill=COLORS["secondary"], font=fonts["l"])
    startup_draw.text((20, 100), "Steel DUO PID", fill=COLORS["secondary"], font=fonts["m"])
    disp.ShowImage(startup_image)

    touch.Set_Mode(mode)

    time.sleep(1)

    shot_image = Image.new("RGB", (disp.width, disp.height), COLORS["primary_dark"])
    shot_draw = ImageDraw.Draw(shot_image)

    # https://forums.raspberrypi.com/viewtopic.php?t=329762
    scanner = Scanner().withDelegate(ScanDelegate())
    devices = None  # scanner.scan(10.0)  # 10.0 seconds scan time

    felicita_device = None
    if devices:
        for dev in devices:
            if dev.getValueText(9) == "FELICITA":
                felicita_device = dev
                break

    if felicita_device:
        print(f"Found the Felicita scale with address {felicita_device.addr}")
        peripheral = Peripheral(felicita_device)
        peripheral.setDelegate(ScanDelegate())

        # Connecting to the correct service (replace with correct UUID)
        service = peripheral.getServiceByUUID("FFE0")

        # Connecting to the correct characteristic (replace with correct UUID)
        char = service.getCharacteristics("FEE0")[0]
        scale_connected = True
    else:
        peripheral = None

    while True:
        now = time.time()

        if peripheral and peripheral.waitForNotifications(0.02):
            # Received data
            data = char.read()
            data_array = [int(b) for b in data]

            # Parsing the data
            weight_digits = data_array[3:9]
            weight = "".join(str(x - 48) for x in weight_digits)
            scale_units = "".join(chr(x) for x in data_array[9:11])
            battery = data_array[15] - 129

            shot_current_weight_g = float(weight)

            print(f"Weight: {weight} {scale_units}")
            print(f"Battery Level: {battery}%")
        else:
            shot_current_weight_g = scale.get_current_weight()

        # Prepare screen
        shot_draw.rectangle((0, 0, 240, 240), fill=COLORS["primary_dark"], outline=None, width=1)
        display_image(shot_image, "./assets/elements.png", (0, 0), (240, 240))

        if shot_running:
            shot_time_s = now - shot_started_time
            if (shot_current_weight_g + SHOT_AFTER_DRIPPING_WEIGHT_G) >= shot_target_weight_g:
                manage_shot(False)

        # Evaluate touch
        if touch_interrupt_flag == 1:
            # decrease weight
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 180, 270, 120):
                update_shot_target_weight_g(shot_target_weight_g - 0.5)
                display_image(shot_image, "./assets/left_pressed.png", (0, 0), (240, 240))

            # increase weight
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 270, 359, 120):
                update_shot_target_weight_g(shot_target_weight_g + 0.5)
                display_image(shot_image, "./assets/right_pressed.png", (0, 0), (240, 240))

            # start/stop shot
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 0, 180, 120):
                shot_running = not shot_running
                manage_shot(shot_running)
                display_image(shot_image, "./assets/bottom_pressed.png", (0, 0), (240, 240))

            handled_touch_interrupt()

        # Evaluate shot button
        if shot_button_interrupt_flag == 1:
            shot_running = not shot_running
            manage_shot(shot_running)

        # Draw the main screen
        shot_draw.text((30, 95), f"{shot_current_weight_g:.1f}g", fill=COLORS["secondary"], font=fonts["m"])
        shot_draw.text((135, 95), f"{shot_target_weight_g:.1f}g", fill=COLORS["primary_light"], font=fonts["m"])
        shot_draw.text((80, 150), f"{shot_time_s:.1f}s", fill=COLORS["secondary"], font=fonts["xl"])
        draw_shot_weight_progress(shot_draw)
        draw_bluetooth_connection(shot_draw)
        disp.ShowImage(shot_image)
        time.sleep(0.02)


if __name__ == "__main__":
    try:
        main()
    except IOError as e:
        logging.info(e)
    except KeyboardInterrupt:
        disp.module_exit()
        logging.info("quit:")
        exit()
