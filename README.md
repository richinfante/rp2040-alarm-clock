# RP2040 Alarm Clock

A CircuitPython-based alarm clock built with an RP2040 microcontroller, a 7-segment LED display, a DS3231 real-time clock, and a rotary encoder for navigation and editing.

## Hardware

| Component | Purpose | Connection |
|---|---|---|
| Adafruit KB2040 Board | Microcontroller | — |
| DS3231 RTC module | Battery-backed real-time clock | I2C (default address) |
| Adafruit HT16K33 Seg7x4 display | 4-digit 7-segment LED display | I2C (default address) |
| Adafruit I2C rotary encoder (Seesaw, product 4991) | Navigation & value editing | I2C (address `0x36`) |
| Passive buzzer | Alarm tone output | GPIO D3 (PWM) |

All I2C peripherals share the default I2C bus (`board.I2C()`).

## Features

- **Clock** — Displays current time in 12-hour (with AM/PM dot) or 24-hour format
- **Date display** — View and edit year, month, and day
- **Alarm** — Configurable alarm with snooze and auto-shutoff
- **Adjustable brightness** — 11 brightness levels (0–10)
- **Non-volatile settings** — Military time, alarm on/off, alarm time, and brightness are persisted across reboots via non-volatile memory

## Screens

Rotate the encoder knob to cycle through screens. After 10 seconds of inactivity, the display returns to the clock screen.

| # | Screen | Label | Description |
|---|---|---|---|
| 0 | Clock | *(time)* | Current time with blinking colon |
| 1 | Year | `year` | Four-digit year |
| 2 | Month | *(abbr)* | Three-letter month abbreviation (Jan–Dec) |
| 3 | Day | `day` | Day of the month |
| 4 | Time Format | `12H`/`24H` | Toggle between 12-hour and 24-hour display |
| 5 | Brightness | `bl` + level | Display brightness (0–10, `F` = full) |
| 6 | Alarm On/Off | `A ON`/`A --` | Toggle the alarm |
| 7 | Alarm Time | `at` | View/edit the alarm time |

## User Guide

### Navigating Screens

Turn the rotary encoder knob to cycle through the screens listed above.

### Editing Values

1. **Navigate** to the screen you want to edit (Clock, Year, Month, Day, Brightness, or Alarm Time).
2. **Long-press** the encoder button (hold > 2 seconds) to enter edit mode.
3. **Turn the knob** to change the value. The currently edited field blinks to indicate it is active.
4. **Press the button** to confirm. For screens with two fields (Clock and Alarm Time), the first press advances to the next field (hour → minute); the second press saves.
5. On save, `SET` is displayed briefly and the new values are written to the RTC and persisted to NVM.

### Toggling Time Format (12H / 24H)

Navigate to the **Time Format** screen (`12H` or `24H`) and **long-press** the button (> 2 seconds) to toggle.

### Adjusting Brightness

Navigate to the **Brightness** screen and enter edit mode with a long press. Turn the knob to select a level from 0 to 10 (displayed as `bl 0` through `bl F`). Press the button to save.

### Setting the Alarm

1. Navigate to the **Alarm On/Off** screen (`A ON` / `A --`). Long-press (> 2 seconds) to toggle it on or off.
2. Navigate to the **Alarm Time** screen (`at`). Long-press to enter edit mode.
3. Turn the knob to set the **minute**, press to confirm, then turn the knob to set the **hour**, press to save.

### When the Alarm Goes Off

The buzzer plays a pulsing tone (beeping on/off every 2 seconds with varying pitch).

- **Snooze** — Press and release the encoder button. The display shows `snoz` briefly. The alarm will sound again after 5 minutes.
- **Dismiss** — Hold the encoder button for 4 seconds. A progress animation fills the display segments as you hold. On dismiss, the display shows `0FF` and a confirmation tone plays. The alarm will not sound again until the next matching time.
- **Auto-shutoff** — If not dismissed, the alarm automatically stops after 10 minutes.

## Configuration Constants

These are defined at the top of [code.py](code.py) and can be adjusted:

| Constant | Default | Description |
|---|---|---|
| `ALARM_MAX_DURATION` | `600` (10 min) | Max seconds the alarm will sound before auto-shutoff |
| `SNOOZE_DURATION` | `300` (5 min) | Seconds before a snoozed alarm re-triggers |
| `TONE_FREQ` | C major scale (C4–B4) | Buzzer frequencies used for alarm tones |

## Development

### Deploying to the Board

With the RP2040 mounted as a `CIRCUITPY` USB drive:

```sh
./push.sh    # copy code.py → /Volumes/CIRCUITPY/
```

### Pulling from the Board

```sh
./pull.sh    # copy /Volumes/CIRCUITPY/code.py → ./code.py
```

### Serial Console

Connect to the serial console to see debug output:

```sh
screen /dev/tty.usbmodem2101
```

## Dependencies (CircuitPython Libraries)

- `adafruit_ds3231`
- `adafruit_ht16k33`
- `adafruit_seesaw`

Install these via the [Adafruit CircuitPython Bundle](https://circuitpython.org/libraries).
