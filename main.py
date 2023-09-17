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
from lib import LCD_1inch28, Touch_1inch28
import yaml

import pexpect, subprocess

import cProfile
import pstats

# Constants
COLORS = {
    "primary_dark": "#012E40",
    "primary_dark_medium": "#024959",
    "primary_medium": "#026773",
    "primary_light": "#3CA6A6",
    "secondary": "#F2E3D5",
    "error": "#D95252",
}

FELICITA = {
    "command_handle": "0x25",
    "start_timer": "52",
    "stop_timer": "53",
    "reset_timer": "43",
    "toggle_timer": "44",
    "tare": "54",
}

SHOT_RELAY_PIN = 14
SHOT_BUTTON_ASCASO_INT_PIN = 21
TP_INT_PIN = 5
BLUETOOTH_CONNECT_S = 1.0
SHOT_AFTER_DRIPPING_WEIGHT_G = 3

# Change to your own BLE scale MAC address
# use 'sudo hcitool lescan'
BLE_MAC_ADDRESS = "64:33:DB:AD:C5:FD"

# Setup Logging
logging.basicConfig(level=logging.DEBUG)
pil_logger = logging.getLogger("PIL")
pil_logger.setLevel(logging.INFO)

# Global Variables
touch_interrupt_flag = 0
shot_button_interrupt_flag = 0
now = 0.0
shot_started_time = 0.0
shot_time_s = 0.0
shot_current_weight_g = 0
shot_target_weight_g = 35
scale_connected = False
gattinst = None
ble_scale = "FELICITA"
shot_running = False
mode = 1
disp = {}
shot_button_debounce_ms = 300  # debounce time in milliseconds
shot_button_last_interrupt_time = 0

# Initialize Objects
touch = Touch_1inch28.Touch_1inch28()

profiler = cProfile.Profile()

# Path
path = os.path.dirname(os.path.realpath(__file__))


def send_ble_command(mac_address, handle, command):
    try:
        subprocess.run(["gatttool", "-b", f"{mac_address}", "--char-write-req", "-a", f"{handle}", "-n", f"{command}"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to send BLE command: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def restart_ble_interface():
    try:
        subprocess.run(["sudo", "hciconfig", "hci0", "down"], check=True)
        subprocess.run(["sudo", "hciconfig", "hci0", "up"], check=True)
        print("BLE interface restarted successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to restart BLE interface: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


def connect_and_parse_data(mac_address):
    global scale_connected, gattinst
    gattinst = pexpect.spawn(f"gatttool -b {mac_address} -I")
    gattinst.sendline("connect")
    try:
        index = gattinst.expect(["Connection successful", pexpect.TIMEOUT, pexpect.EOF], timeout=0.1)
        return gattinst, True
    except pexpect.TIMEOUT:
        gattinst.close()
        return gattinst, False
    except pexpect.EOF:
        gattinst.close()
        return gattinst, False


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


def touch_interrupt_callback(TP_INT_PIN):
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
    global shot_current_weight_g, shot_running, shot_started_time, now, scale_connected, gattinst

    print(f"Turn shot to {on} with current weight of {shot_current_weight_g}")
    # We need to tare first
    if on and shot_current_weight_g > 1.0:
        gattinst.sendline(f"char-write-cmd {FELICITA['command_handle']} {FELICITA['tare']}")
        print(f"Taring scale...")
        Timer(2, manage_shot, [True]).start()
        return

    if on:
        shot_started_time = now
        shot_running = True
        if scale_connected:
            gattinst.sendline(f"char-write-cmd {FELICITA['command_handle']} {FELICITA['reset_timer']}")
            time.sleep(0.1)
            gattinst.sendline(f"char-write-cmd {FELICITA['command_handle']} {FELICITA['start_timer']}")
            time.sleep(0.1)
    else:
        Timer(30, reset_shot).start()
        shot_running = False
        if scale_connected:
            gattinst.sendline(f"char-write-cmd {FELICITA['command_handle']} {FELICITA['stop_timer']}")

    gpio.output(SHOT_RELAY_PIN, True)
    time.sleep(0.1)
    gpio.output(SHOT_RELAY_PIN, False)


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
    global now, shot_time_s, shot_current_weight_g, shot_target_weight_g, shot_running, disp, scale_connected, gattinst

    # Initialize YAML and set shot_target_weight_g
    initialize_yaml()
    shot_target_weight_g = read_yaml()

    disp = initialize_display()

    touch.init()
    touch.int_irq(TP_INT_PIN, touch_interrupt_callback)
    gpio.setup(SHOT_RELAY_PIN, gpio.OUT)
    gpio.output(SHOT_RELAY_PIN, 0)

    # Set up the button pin as an input with an internal pull-up resistor
    gpio.setup(SHOT_BUTTON_ASCASO_INT_PIN, gpio.IN, pull_up_down=gpio.PUD_UP)

    # Add an interrupt on the falling edge (from HIGH to LOW) of the button pin
    gpio.add_event_detect(SHOT_BUTTON_ASCASO_INT_PIN, gpio.FALLING, callback=shot_button_callback, bouncetime=shot_button_debounce_ms)

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

    ble_timeout_count = 0
    last_bluetooth_connect_time_s = 0
    clear_all = True
    clear_upper_right = False
    clear_upper_left = False
    clear_lower_half = False

    # profiler.enable()
    while True:
        now = time.time()

        draw_all = False
        if clear_all:
            draw_all = True
            clear_all = False
        draw_upper_left = False
        draw_upper_right = False
        draw_lower_half = False
        if clear_upper_left:
            draw_upper_left = True
            clear_upper_left = False
        if clear_upper_right:
            draw_upper_right = True
            clear_upper_right = False
        if clear_lower_half:
            draw_lower_half = True
            clear_lower_half = False
        draw_seconds = False
        draw_current_weight = False
        draw_target_weight = False
        draw_bluetooth = False

        if scale_connected == False and BLE_MAC_ADDRESS != "" and (now - last_bluetooth_connect_time_s) > BLUETOOTH_CONNECT_S:
            _, scale_connected = connect_and_parse_data(BLE_MAC_ADDRESS)
            ble_timeout_count = 0
            last_bluetooth_connect_time_s = now
            draw_bluetooth = True
        if scale_connected:
            try:
                gattinst.read_nonblocking(size=40000, timeout=0.1)
                index = gattinst.expect(["Notification handle = 0x0025 value: ", pexpect.TIMEOUT, pexpect.EOF], timeout=0.2)
                if index == 0:
                    line = gattinst.before
                elif index == 1:
                    # In case of timeout, flush the buffer to force reading newer data
                    gattinst.read_nonblocking(size=40000, timeout=0.1)
                    continue
                else:
                    continue

                input_string = line.decode("utf-8")

                if "connect" in input_string:
                    continue

                position = input_string.find("\r")
                hex_numbers_string = input_string[:position].strip()
                hex_numbers_array = hex_numbers_string.split(" ")
                data = [int(hex_number, 16) for hex_number in hex_numbers_array if hex_number]
                # Example data from Felicita Arc
                # data_array [1, 2, 43, 48, 48, 49, 49, 50, 48, 32, 103, 67, 249, 64, 34, 136, 13, 10] = 11.2g

                if len(data) < 16:
                    continue

                # Parsing the Felicita Arc data
                weight_digits = data[3:7]
                weight_deminals = data[7:9]
                weight = "".join(str(x - 48) for x in weight_digits) + "." + "".join(str(x - 48) for x in weight_deminals)
                weight = weight.lstrip("0")
                scale_units = "".join(chr(x) for x in data[9:11])
                battery = ((data[15] - 129) / 29) * 100

                if float(weight) != shot_current_weight_g:
                    draw_current_weight = True
                shot_current_weight_g = float(weight)

                print(f"Weight: {weight} {scale_units} | Battery Level: {battery:.1f}%")

            except pexpect.TIMEOUT:
                ble_timeout_count += 1
                if ble_timeout_count > 10:
                    print("BLE scale disconnected.")
                    gattinst.close()
                    scale_connected = False
                    draw_bluetooth = True

        # Prepare screen
        shot_draw.rectangle((0, 0, 240, 240), fill=COLORS["primary_dark"], outline=None, width=1)
        display_image(shot_image, "./assets/elements.png", (0, 0), (240, 240))

        if shot_running:
            shot_time_s = now - shot_started_time
            draw_seconds = True
            print(f"Running: {shot_current_weight_g}/{shot_target_weight_g}g | {shot_time_s}s | ")
            if (shot_current_weight_g + SHOT_AFTER_DRIPPING_WEIGHT_G) >= shot_target_weight_g:
                manage_shot(False)

        # Evaluate touch
        if touch_interrupt_flag == 1:
            # decrease weight
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 180, 270, 120):
                update_shot_target_weight_g(shot_target_weight_g - 0.5)
                display_image(shot_image, "./assets/left_pressed.png", (0, 0), (240, 240))
                draw_upper_left = True
                draw_target_weight = True
                clear_upper_left = True

            # increase weight
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 270, 359, 120):
                update_shot_target_weight_g(shot_target_weight_g + 0.5)
                display_image(shot_image, "./assets/right_pressed.png", (0, 0), (240, 240))
                draw_upper_right = True
                draw_target_weight = True
                clear_upper_right = True

            # start/stop shot
            if is_point_in_circular_segment(touch.X_point, touch.Y_point, 120, 120, 0, 180, 120):
                print("Shot button pressed")
                display_image(shot_image, "./assets/bottom_pressed.png", (0, 0), (240, 240))
                manage_shot(not shot_running)
                draw_lower_half = True
                clear_lower_half = True

            handled_touch_interrupt()

        # Evaluate shot button
        if shot_button_interrupt_flag == 1:
            manage_shot(not shot_running)

        # Draw the main screen
        shot_draw.text((30, 95), f"{shot_current_weight_g:.1f}g", fill=COLORS["secondary"], font=fonts["m"])
        shot_draw.text((135, 95), f"{shot_target_weight_g:.1f}g", fill=COLORS["primary_light"], font=fonts["m"])
        shot_draw.text((80, 150), f"{shot_time_s:.1f}s", fill=COLORS["secondary"], font=fonts["xl"])
        draw_shot_weight_progress(shot_draw)
        draw_bluetooth_connection(shot_draw)

        if draw_all:
            disp.ShowImage(shot_image)
        else:
            if draw_upper_left:
                disp.ShowImage_Windows(1, 1, 120, 120, shot_image)
            if draw_upper_right:
                disp.ShowImage_Windows(120, 1, 239, 120, shot_image)
            if draw_lower_half:
                disp.ShowImage_Windows(1, 140, 238, 238, shot_image)
            if draw_seconds:
                disp.ShowImage_Windows(30, 150, 200, 200, shot_image)
            if draw_current_weight:
                disp.ShowImage_Windows(30, 95, 60, 120, shot_image)
            if draw_target_weight:
                disp.ShowImage_Windows(120, 1, 239, 150, shot_image)
            if draw_bluetooth:
                disp.ShowImage_Windows(118, 20, 122, 24, shot_image)
        # time.sleep(0.01)


if __name__ == "__main__":
    try:
        main()
        profiler.disable()
        # Print stats
        stats = pstats.Stats(profiler).sort_stats("cumtime")
        stats.print_stats()
    except IOError as e:
        logging.info(e)
    except KeyboardInterrupt:
        profiler.disable()
        # Print stats
        stats = pstats.Stats(profiler).sort_stats("cumtime")
        stats.print_stats()
        disp.module_exit()
        logging.info("quit:")
        exit()
