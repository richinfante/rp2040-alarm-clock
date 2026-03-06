import board
import pwmio
import adafruit_ds3231
import adafruit_ht16k33.segments
from adafruit_seesaw import digitalio, rotaryio, seesaw
import time
import microcontroller

PWM_OFF = 0
PWM_ON = 2**15
ALARM_MAX_DURATION = 60 * 10  # 10 minute max alarm duration to prevent it from going indefinitely
SNOOZE_DURATION = 60 * 5  # 5 minute snooze duration

# init hardware
i2c = board.I2C()
rtc = adafruit_ds3231.DS3231(i2c)
seg = adafruit_ht16k33.segments.Seg7x4(i2c)
seesaw = seesaw.Seesaw(i2c, 0x36)
buzzer = pwmio.PWMOut(board.D3, variable_frequency=True)

# Frequencies for the 7 tones of a C major scale
TONE_FREQ = [
  262,  # C4
  294,  # D4
  330,  # E4
  349,  # F4
  392,  # G4
  440,  # A4
  494   # B4
]

buzzer.duty_cycle = PWM_OFF

# init seesaw and verify product id
seesaw_product = (seesaw.get_version() >> 16) & 0xFFFF
print(f"Found product {seesaw_product}")
if seesaw_product != 4991:
    print("Wrong firmware loaded?  Expected 4991")

# Configure seesaw pin used to read knob button presses
# The internal pull up is enabled to prevent floating input
seesaw.pin_mode(24, seesaw.INPUT_PULLUP)
button = digitalio.DigitalIO(seesaw, 24)

last_ux_dt = None
military_time = False
button_held = False
encoder = rotaryio.IncrementalEncoder(seesaw)
last_position = None
last_screen_transition = time.monotonic()
screen = 0

is_alarming = False
alarm_started_at = None
alarm_on = False
alarm_time = (6, 30)  # hour, minute
snoozed = False
snoozed_at = None

# editing state
edit_start_dt = None
edit_dt = None
edit_value = None
edit_mode = False
edit_encoder_start = None
edit_alarm = None

mon_abbrs = {
  1: 'Jan',
  2: 'Feb',
  3: 'Mar',
  4: 'Apr',
  5: 'May',
  6: 'Jun',
  7: 'Jul',
  8: 'Aug',
  9: 'Sep',
  10: 'Oct',
  11: 'Nov',
  12: 'Dec',
}

SCREEN_CLOCK = 0
SCREEN_YEAR = 1
SCREEN_MON = 2
SCREEN_DAY = 3
SCREEN_MIL = 4
SCREEN_BRIGHTNESS = 5
SCREEN_ALARM = 6
SCREEN_ALARM_TIME = 7

NUM_SCREENS = 8


def nv_save():
  """
    Save global settings to non-volatile memory in a compact format.
     - First byte is a version byte for future compatibility
     - Next bytes are settings values (military_time, alarm_on, edit_alarm hour & minute, brightness)
     - Remaining bytes are padding to fill the 16 byte NVM page
  """
  packed_nv_bytes = bytes([
    0x32,  # version byte for future compatibility
    1 if military_time else 0,
    1 if alarm_on else 0,
    edit_alarm[0],  # alarm hour
    edit_alarm[1],  # alarm minute
    round(seg.brightness * 10),  # brightness
  ]) + bytes(10)  # pad to 16 bytes

  print("Packed NVM bytes: {:x}".format(int.from_bytes(packed_nv_bytes, 'big')))

  microcontroller.nvm[0:16] = packed_nv_bytes
  print("Saved settings to NVM - military_time: {}, alarm_on: {}, edit_alarm: {}, brightness: {}".format(
    military_time, alarm_on, edit_alarm, seg.brightness
  ))

def nv_load():
  """
    Initialize global settings from non-volatile memory.
    If magic first byte doesn't match expected value, assume NVM is uninitialized and use defaults.
  """
  global military_time, alarm_on, edit_alarm

  packed_nv_bytes = microcontroller.nvm[0:16]
  print("Loaded packed NVM bytes: {:x}".format(int.from_bytes(packed_nv_bytes, 'big')))

  version = packed_nv_bytes[0]
  if version != 0x32:
    print("NVM version mismatch or uninitialized NVM, using defaults")
    return

  military_time = bool(packed_nv_bytes[1])
  alarm_on = bool(packed_nv_bytes[2])
  edit_alarm = [packed_nv_bytes[3], packed_nv_bytes[4]]
  seg.brightness = packed_nv_bytes[5] / 10

  print("Loaded settings - military_time: {}, alarm_on: {}, edit_alarm: {}, brightness: {}".format(
    military_time, alarm_on, edit_alarm, seg.brightness
  ))

# load nonvolatile settings on boot
# on first init, the magic won't be found and defaults will be used, on subsequent boots settings will be loaded from NVM
nv_load()

# main loop
while True:
  if edit_mode and edit_dt:
    t = edit_dt
  else:
    t = rtc.datetime

  just_pressed = False
  just_released = False

  if not button.value and not button_held:
    print("Button was just pressed")
    just_pressed = True
    button_held = True
    last_ux_dt = time.monotonic()
  elif button.value and button_held:
    print("Button was just released")
    button_held = False
    just_released = True
    last_ux_dt = time.monotonic()

  elif button_held:
    press_duration = time.monotonic() - last_ux_dt
    print("Button has been held for {:.1f} seconds".format(press_duration))
  else:
    press_duration = 0


  #
  # ALARM
  #

  # # when alarm is on and current time matches alarm time, start alarming
  if not is_alarming and alarm_on and not edit_mode and (t.tm_hour, t.tm_min) == alarm_time and not snoozed:
    print("Alarm time reached! Starting alarm.")
    is_alarming = True
    alarm_started_at = time.monotonic()
    buzzer.frequency = TONE_FREQ[4]
    buzzer.duty_cycle = PWM_ON
    snoozed = False
    snoozed_at = None

  # if snoozed, and it's been more than SNOOZE_DURATION since snooze started, resound the alarm
  elif snoozed and (time.monotonic() - snoozed_at) > SNOOZE_DURATION: # 5 minute snooze
    print("Snooze duration ended, resounding alarm.")
    is_alarming = True
    alarm_started_at = time.monotonic()
    buzzer.frequency = TONE_FREQ[4]
    buzzer.duty_cycle = PWM_ON
    snoozed = False
    snoozed_at = None

  # pulse the buzzer every 2 seconds to make a beeping sound when alarming
  if is_alarming and alarm_started_at and int(time.monotonic() - alarm_started_at) % 2 == 0:
    # change tone every 2 seconds
    if button_held:
      buzzer.duty_cycle = PWM_OFF
    else:
      buzzer.duty_cycle = PWM_ON

  elif is_alarming:
    buzzer.duty_cycle = PWM_OFF

  # stop alarming after ALARM_MAX_DURATION to prevent it from going indefinitely
  if is_alarming and alarm_started_at and (time.monotonic() - alarm_started_at) > ALARM_MAX_DURATION:
    print("Alarm time ended. Stopping alarm.")
    is_alarming = False
    buzzer.duty_cycle = PWM_OFF

  # single press to snooze (on release)
  # snooze is for SNOOZE_DURATION, after which the alarm will sound again if not snoozed again or turned off
  if is_alarming and just_released:
    print("Alarm snoozed by button press.")
    is_alarming = False
    snoozed = True
    snoozed_at = time.monotonic()
    buzzer.duty_cycle = PWM_OFF
    seg.print('sno2')
    seg.colon = False
    time.sleep(1)

  # long press, stops the alarm entirely
  if (snoozed or is_alarming) and button_held:
    d1 = 0x0
    d2 = 0x0
    d3 = 0x0
    d4 = 0x0

    if press_duration > 0.25:
      d1 = d1 | 0b00000001

    if press_duration > 0.5:
      d2 = d2 | 0b00000001

    if press_duration > 0.75:
      d3 = d3 | 0b00000001

    if press_duration > 1.0:
      d4 = d4 | 0b00000001

    if press_duration > 1.25:
      d4 = d4 | 0b00000010

    if press_duration > 1.5:
      d4 = d4 | 0b00000100

    if press_duration > 1.75:
      d4 = d4 | 0b00001000

    if press_duration > 2.0:
      d3 = d3 | 0b00001000

    if press_duration > 2.25:
      d2 = d2 | 0b00001000

    if press_duration > 2.5:
      d1 = d1 | 0b00001000

    if press_duration > 3.0:
      d1 = d1 | 0b00010000

    if press_duration > 3.5:
      d1 = d1 | 0b00100000

    seg.set_digit_raw(0, d1)
    seg.set_digit_raw(1, d2)
    seg.set_digit_raw(2, d3)
    seg.set_digit_raw(3, d4)
    seg.colon = True

    # 4 sec long press -> alarm silenced until next time
    if press_duration > 4:
      # shut off alarm entirely
      is_alarming = False
      snoozed = False
      snoozed_at = None
      press_duration = 0
      last_ux_dt = time.monotonic()
      print("Alarm silenced for good by long button press.")
      seg.print('0FF ')
      seg.colon = False
      buzzer.frequency = TONE_FREQ[0]
      buzzer.duty_cycle = PWM_ON
      time.sleep(0.25)
      buzzer.duty_cycle = PWM_OFF
      time.sleep(0.75)

    continue # skip screen rendering

  position = encoder.position
  if last_position is None or position != last_position and not edit_mode:
    print("Encoder position: {}".format(position))
    last_position = position
    screen = position % NUM_SCREENS
    last_screen_transition = time.monotonic()
    last_ux_dt = time.monotonic()

  # Enter edit mode if button is held for more than 2 seconds on certain screens
  if press_duration > 2 and edit_mode == False and screen not in [SCREEN_MIL, SCREEN_ALARM]:
    print("Entering edit mode")
    edit_start_dt = rtc.datetime
    edit_dt = rtc.datetime
    edit_mode = True
    edit_encoder_start = encoder.position
    edit_alarm = list(alarm_time)

    if screen in [SCREEN_CLOCK, SCREEN_ALARM_TIME]:
      remaining_edits = 2  # hour, minute
    else:
      remaining_edits = 1

  # Save edits and exit edit mode on button release
  elif edit_mode and just_pressed:
    remaining_edits -= 1

    if remaining_edits <= 0:
      if screen not in [SCREEN_BRIGHTNESS, SCREEN_ALARM, SCREEN_ALARM_TIME]:
        print("Saving edited time: {}".format(edit_dt))
        edit_dt = time.struct_time((
          edit_dt.tm_year,
          edit_dt.tm_mon,
          edit_dt.tm_mday,
          edit_dt.tm_hour,
          edit_dt.tm_min,
          0,  # reset seconds to 0 on save
          edit_dt.tm_wday,
          edit_dt.tm_yday,
          edit_dt.tm_isdst,
        ))

        rtc.datetime = edit_dt
      edit_mode = False
      last_ux_dt = time.monotonic()
      last_position = encoder.position  # reset encoder position to prevent jumps on next edit
      alarm_time = tuple(edit_alarm)  # save edited alarm time

      nv_save()

      if screen not in [SCREEN_MIL, SCREEN_ALARM, SCREEN_BRIGHTNESS, SCREEN_ALARM_TIME]:
        seg.print(' SET')
        time.sleep(1)
    else:
      edit_start_dt = edit_dt  # persist current edit
      edit_encoder_start = encoder.position  # reset encoder position for next edit


  #
  # Screen timeout
  #

  since_last_ux = time.monotonic() - last_ux_dt
  if since_last_ux > 10:
    print("No user interaction for {:.1f} seconds, resetting screen to 0".format(since_last_ux))
    screen = 0
    last_screen_transition = time.monotonic()
    last_ux_dt = time.monotonic()



  #
  # Screens
  #

  if screen == SCREEN_CLOCK:
    seg.colon = t.tm_sec % 2 == 0
    if not edit_mode:
      if military_time:
        seg.print("{: 2d}{:02d}".format(t.tm_hour, t.tm_min))
      else:
        seg.print("{: 2d}{:02d}{}".format(t.tm_hour % 12 or 12, t.tm_min, '.' if t.tm_hour >= 12 else ''))

    elif edit_mode and remaining_edits == 1:
      # minute edit
      edit_dt = time.struct_time((
        edit_start_dt.tm_year,
        edit_start_dt.tm_mon,
        edit_start_dt.tm_mday,
        edit_start_dt.tm_hour,
        (edit_start_dt.tm_min + (encoder.position - edit_encoder_start)) % 60,
        edit_start_dt.tm_sec,
        edit_start_dt.tm_wday,
        edit_start_dt.tm_yday,
        edit_start_dt.tm_isdst,
      ))

      if int(time.monotonic() * 2) % 2 == 0:
        seg.print("{: 2d}{:02d}{}".format(t.tm_hour % 12 or 12, edit_dt.tm_min, '.' if t.tm_hour >= 12 else ''))
      else:
        seg.print("{: 2d}  ".format(t.tm_hour % 12 or 12))
    elif edit_mode and remaining_edits == 2:
      # hour edit
      edit_dt = time.struct_time((
        edit_start_dt.tm_year,
        edit_start_dt.tm_mon,
        edit_start_dt.tm_mday,
        (edit_start_dt.tm_hour + (encoder.position - edit_encoder_start)) % 24,
        edit_start_dt.tm_min,
        edit_start_dt.tm_sec,
        edit_start_dt.tm_wday,
        edit_start_dt.tm_yday,
        edit_start_dt.tm_isdst,
      ))

      if int(time.monotonic() * 2) % 2 == 0:
        seg.print("{: 2d}{:02d}{}".format(edit_dt.tm_hour % 12 or 12, t.tm_min, '.' if edit_dt.tm_hour >= 12 else ''))
      else:
        seg.print("   {:02d}{}".format(t.tm_min, '.' if t.tm_hour >= 12 else ''))

  # year
  elif screen == SCREEN_YEAR:
    seg.colon = False

    if edit_mode:
      last_ux_dt = time.monotonic()
      edit_dt = time.struct_time((
        edit_start_dt.tm_year + (encoder.position - edit_encoder_start),
        edit_start_dt.tm_mon,
        edit_start_dt.tm_mday,
        edit_start_dt.tm_hour,
        edit_start_dt.tm_min,
        edit_start_dt.tm_sec,
        edit_start_dt.tm_wday,
        edit_start_dt.tm_yday,
        edit_start_dt.tm_isdst,
      ))

    if time.monotonic() - last_screen_transition < 1.5:
      seg.print('year')
    elif edit_mode:
      # quick flash
      if int(time.monotonic() * 2) % 2 == 0:
        seg.print("{:04d}".format(edit_dt.tm_year))
      else:
        seg.print("    ")
    else:
      seg.print("{:04d}".format(t.tm_year))

  # month
  elif screen == SCREEN_MON:
    seg.colon = False

    if edit_mode:
      last_ux_dt = time.monotonic()
      edit_dt = time.struct_time((
        edit_start_dt.tm_year,
        (edit_start_dt.tm_mon + (encoder.position - edit_encoder_start) - 1) % 12 + 1,
        edit_start_dt.tm_mday,
        edit_start_dt.tm_hour,
        edit_start_dt.tm_min,
        edit_start_dt.tm_sec,
        edit_start_dt.tm_wday,
        edit_start_dt.tm_yday,
        edit_start_dt.tm_isdst,
      ))

      if int(time.monotonic() * 2) % 2 == 0:
        abbr = mon_abbrs.get(edit_dt.tm_mon, '    ')
        seg.print(abbr + ' ' * (4 - len(abbr)))
      else:
        seg.print("    ")

    else:
      abbr = mon_abbrs.get(t.tm_mon, '    ')
      seg.print(abbr + ' ' * (4 - len(abbr)))

  # day
  elif screen == SCREEN_DAY:
    seg.colon = False
    if time.monotonic() - last_screen_transition < 1.5:
      seg.print('day ')
    elif not edit_mode:
      seg.print("d {:02d}".format(t.tm_mday))
    elif edit_mode:
      last_ux_dt = time.monotonic()
      edit_dt = time.struct_time((
        edit_start_dt.tm_year,
        edit_start_dt.tm_mon,
        (edit_start_dt.tm_mday + (encoder.position - edit_encoder_start) - 1) % 31 + 1,
        edit_start_dt.tm_hour,
        edit_start_dt.tm_min,
        edit_start_dt.tm_sec,
        edit_start_dt.tm_wday,
        edit_start_dt.tm_yday,
        edit_start_dt.tm_isdst,
      ))

      # quick flash
      if int(time.monotonic() * 2) % 2 == 0:
        seg.print("d {:02d}".format(edit_dt.tm_mday))
      else:
        seg.print("    ")

  # military time setting
  elif screen == SCREEN_MIL:
    seg.colon = False
    if military_time:
      seg.print("24H ")
    else:
      seg.print("12H ")

    if button_held and press_duration > 2:
      military_time = not military_time
      print("Toggled military time to {}".format(military_time))
      last_ux_dt = time.monotonic()
      nv_save()

  elif screen == SCREEN_BRIGHTNESS:
    if edit_mode:
      brightness = (encoder.position - edit_encoder_start) % 11
      new_brt = brightness / 10
      if new_brt > 1:
        new_brt = 1

      print("Setting brightness to {:.1f}".format(new_brt))
      seg.brightness = new_brt
      last_ux_dt = time.monotonic()

    seg.colon = False
    if seg.brightness == 1:
      seg.print('bl F')
    else:
      seg.print('bl{: 2d}'.format(round(seg.brightness * 10)))

  elif screen == SCREEN_ALARM:
    seg.colon = False
    if alarm_on:
      seg.print('A ON')
    else:
      seg.print('A --')

    if button_held and press_duration > 2:
      alarm_on = not alarm_on
      nv_save()
      print("Toggled alarm to {}".format(alarm_on))
      last_ux_dt = time.monotonic()

      if alarm_on:
        seg.print('A ON')
      else:
        seg.print('A --')

  elif screen == SCREEN_ALARM_TIME:
    if time.monotonic() - last_screen_transition < 1.5:
      seg.print('at  ')
    elif not edit_mode:
      seg.colon = False
      seg.print("{: 2d}{:02d}{}".format(edit_alarm[0] % 12 or 12, edit_alarm[1], '.' if edit_alarm[0] >= 12 else ''))
    elif edit_mode:
      last_ux_dt = time.monotonic()

      # edit time based on remaining edit position & encoder movement
      if remaining_edits == 1:
        edit_alarm[0] = (alarm_time[0] + (encoder.position - edit_encoder_start) % 24) % 24
      elif remaining_edits == 2:
        edit_alarm[1] = (alarm_time[1] + (encoder.position - edit_encoder_start) % 60) % 60

      # flash the currently edited value
      if int(time.monotonic() * 2) % 2 == 0:
        if remaining_edits == 2:
          seg.print("{: 2d}  ".format(edit_alarm[0]))
        elif remaining_edits == 1:
          seg.print("   {:02d}".format(edit_alarm[1]))

      # print total value with dot if pm
      else:
        if military_time:
          seg.print("{: 2d}{:02d}".format(edit_alarm[0], edit_alarm[1]))
        else:
          seg.print("{: 2d}{:02d}{}".format(edit_alarm[0] % 12 or 12, edit_alarm[1], '.' if edit_alarm[0] >= 12 else ''))

  time.sleep(0.05)