# Low level I/O for phone hardware.
#
# This daemon essentially produces status updates on stdout,
# and accepts commands from stdin.
#
# Output:
#  '0' - '9': A single dialed digit
#  'l': Handset has been lifted off the fork
#  'd': Handset has been dropped on the fork
#  's': Dial has been moved from idle position
#  'e': Dial has reached idle position
#  'p': A single dial pulse has been received
#
# coding=utf-8

import datetime
import os
import sys
import time
import RPi.GPIO as GPIO

# Minimum distance between two edges
MIN_SIGNAL_DIST = 1000*20

# After DIGIT_TIMEOUT microseconds  of being in low state, we
# consider one digit to be done.
DIGIT_TIMEOUT = 1000*500

# Sleep time in seconds between state polling iterations.
LOOP_SLEEP_TIME = 0.005

# Ports used for various purposes:
PORT_PULSE = 4 # Receives pulses while dialing a digit.
PORT_IDLE = 17 # Receives dial idle signal.

try:
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(PORT_PULSE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
  GPIO.setup(PORT_IDLE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
  
  # Create a file object without buffering, so all output we produce
  # is immediately sent to stdout.
  char_out = os.fdopen(sys.stdout.fileno(), 'wb', 0)
 
  previous_pulse = False
  previous_pulse_ts = datetime.datetime.now()
  number = 0
  while True:
    new_time = datetime.datetime.now()
    time_diff = new_time - previous_pulse_ts
    if (time_diff.microseconds > DIGIT_TIMEOUT and previous_pulse == False and
        number != 0):
      # Enough time has passed. Print the digit.
      char_out.write('%d' % (number % 10))
      number = 0
        
    is_high = GPIO.input(PORT_PULSE)
    if previous_pulse != is_high and time_diff.microseconds > MIN_SIGNAL_DIST:
      if previous_pulse == True:
        number = number + 1                    
      previous_pulse = is_high
      previous_pulse_ts = new_time

    time.sleep(LOOP_SLEEP_TIME)

finally:
 GPIO.cleanup()
