"""M5Stack Core2 + Roller485 Lite x2 / UIFlow2 MicroPython.
Standalone 10-second automatic stand-up photo demonstration.
A: calibrate while upright; place against bumper; A: start.
During running, A: emergency stop. No Wi-Fi or PC needed.
"""
import M5
import time
import math
import gc
from machine import I2C, Pin
from unit import Roller485Unit

KP = 47.2206
KD = 1.5453
PERIOD_US = 10000
RUN_MS = 10000
RISE_LIMIT_MS = 1000
TAU = 0.5
MAX_CURRENT = 200
START_MIN = 5.0
START_MAX = 8.0
RELEASE_ANGLE = 4.5
STOP_ANGLE = 6.0
SAFETY_ANGLE = 10.0
STILL_MS = 400
STILL_GYRO = 2.0
STILL_SPAN = 0.5
WAIT_START_MS = 30000
CAL_SAMPLES = 200

CYAN = 0x00FFFF
YELLOW = 0xFFFF00
GREEN = 0x00FF00
BLUE = 0x0000FF
RED = 0xFF0000
WHITE = 0xFFFFFF

motor1 = None
motor2 = None


def display(color):
    M5.Lcd.fillScreen(color)


def stop_motors():
    for m in (motor1, motor2):
        if m is not None:
            try:
                m.set_motor_max_current(0)
            except Exception as e:
                print('Stop current error:', repr(e))
    for m in (motor1, motor2):
        if m is not None:
            try:
                m.set_motor_output_state(0)
            except Exception as e:
                print('Stop output error:', repr(e))


def button_a():
    M5.update()
    while M5.BtnA.isPressed():
        M5.update()
        time.sleep_ms(20)
    while not M5.BtnA.isPressed():
        M5.update()
        time.sleep_ms(20)
    while M5.BtnA.isPressed():
        M5.update()
        time.sleep_ms(20)
    time.sleep_ms(100)
    M5.update()


def initialize_motors():
    global motor1, motor2
    i2c = I2C(0, scl=Pin(33), sda=Pin(32), freq=100000)
    devices = i2c.scan()
    print('I2C:', devices)
    if 0x64 not in devices or 0x65 not in devices:
        raise RuntimeError('Motor not found: 0x64 / 0x65')
    motor1 = Roller485Unit(i2c, address=0x64,
                           mode=Roller485Unit.I2C_MODE)
    motor2 = Roller485Unit(i2c, address=0x65,
                           mode=Roller485Unit.I2C_MODE)
    for m in (motor1, motor2):
        m.set_motor_output_state(0)
        m.set_motor_mode(3)
        m.set_motor_max_current(0)


def calibrate():
    display(YELLOW)
    total_angle = 0.0
    total_gyro = 0.0
    for _ in range(CAL_SAMPLES):
        ax, ay, az = M5.Imu.getAccel()
        gx, gy, gz = M5.Imu.getGyro()
        total_angle += math.degrees(math.atan2(ay, az))
        total_gyro += gx
        time.sleep_ms(10)
    offsets = total_angle / CAL_SAMPLES, total_gyro / CAL_SAMPLES
    print('Angle offset, gyro bias:', offsets)
    return offsets


def measure_still(angle_offset, gyro_bias):
    angles = []
    max_gyro = 0.0
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < STILL_MS:
        M5.update()
        ax, ay, az = M5.Imu.getAccel()
        gx, gy, gz = M5.Imu.getGyro()
        angles.append(math.degrees(math.atan2(ay, az)) - angle_offset)
        max_gyro = max(max_gyro, abs(gx - gyro_bias))
        time.sleep_ms(10)
    theta = sum(angles) / len(angles)
    still = max_gyro <= STILL_GYRO and max(angles) - min(angles) <= STILL_SPAN
    return theta, still


def wait_start(angle_offset, gyro_bias):
    display(BLUE)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < WAIT_START_MS:
        theta, still = measure_still(angle_offset, gyro_bias)
        if still and START_MIN <= abs(theta) <= START_MAX:
            print('Start angle:', theta)
            return theta
    raise RuntimeError('Start angle/stillness check timeout')


def control(angle_offset, gyro_bias):
    ax, ay, az = M5.Imu.getAccel()
    angle = math.degrees(math.atan2(ay, az))
    released = False
    reason = '10 seconds completed'
    gc.collect()
    gc.disable()
    try:
        motor1.set_motor_max_current(0)
        motor2.set_motor_max_current(0)
        motor1.set_motor_output_state(1)
        motor2.set_motor_output_state(1)
        display(GREEN)
        start_us = time.ticks_us()
        last_us = start_us
        next_us = time.ticks_add(start_us, PERIOD_US)
        while True:
            while time.ticks_diff(next_us, time.ticks_us()) > 0:
                pass
            now = time.ticks_us()
            elapsed_us = time.ticks_diff(now, start_us)
            dt_us = time.ticks_diff(now, last_us)
            last_us = now
            if elapsed_us >= RUN_MS * 1000:
                break
            if dt_us <= 0 or dt_us > 20000:
                reason = 'Control cycle timeout'
                break
            M5.update()
            if M5.BtnA.wasPressed():
                reason = 'Button A emergency stop'
                break
            ax, ay, az = M5.Imu.getAccel()
            gx, gy, gz = M5.Imu.getGyro()
            gx -= gyro_bias
            dt = dt_us / 1000000.0
            accel_angle = math.degrees(math.atan2(ay, az))
            alpha = TAU / (TAU + dt)
            angle = alpha * (angle + gx * dt) + (1.0 - alpha) * accel_angle
            theta = angle - angle_offset
            if abs(theta) >= SAFETY_ANGLE:
                reason = 'Safety angle limit'
                break
            if not released and abs(theta) <= RELEASE_ANGLE:
                released = True
                print('Bumper released at ms:', elapsed_us // 1000)
            if released and abs(theta) >= STOP_ANGLE:
                reason = 'Fall / bumper limit'
                break
            if not released and elapsed_us >= RISE_LIMIT_MS * 1000:
                reason = 'Rise failure'
                break
            u = -KP * theta - KD * gx
            u = max(-MAX_CURRENT, min(MAX_CURRENT, u))
            current = int(u)
            motor1.set_motor_max_current(current)
            motor2.set_motor_max_current(-current)
            next_us = time.ticks_add(next_us, PERIOD_US)
    finally:
        stop_motors()
        gc.enable()
    print('Result:', reason)
    return reason


def run():
    M5.begin()
    display(CYAN)
    initialize_motors()
    print('Hold upright and still. Press A to calibrate.')
    button_a()
    angle_offset, gyro_bias = calibrate()
    print('Calibration completed.')
    print('Place against bumper (5-8 degrees). Press A to start.')
    display(BLUE)
    button_a()
    wait_start(angle_offset, gyro_bias)
    reason = control(angle_offset, gyro_bias)
    display(WHITE if reason == '10 seconds completed' else RED)
    print('Finished:', reason)


try:
    run()
except Exception as e:
    print('Error:', repr(e))
    try:
        display(RED)
    except Exception:
        pass
finally:
    stop_motors()
    gc.enable()
# Program ends here; no automatic restart or repeat.
