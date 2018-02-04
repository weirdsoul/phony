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

import gpio_signal

# After DIGIT_TIMEOUT seconds of being in low state, we
# consider one digit to be done.
DIGIT_TIMEOUT = 0.5

# Sleep time in seconds between state polling iterations.
LOOP_SLEEP_TIME = 0.01

# Ports used for various purposes:
PORT_PULSE = 4 # Receives pulses while dialing a digit.
PORT_IDLE = 17 # Receives dial idle signal.

try:
  GPIO.setmode(GPIO.BCM)

  # Create a file object without buffering, so all output we produce
  # is immediately sent to stdout.
  char_out = os.fdopen(sys.stdout.fileno(), 'wb', 0)
  
  current_number = 0
  start_time = datetime.datetime.now()
  
  pulse_signal = gpio_signal.GpioSignal(PORT_PULSE, start_time)
  idle_signal = gpio_signal.GpioSignal(PORT_IDLE, start_time)
  
  while True:
    new_time = datetime.datetime.now()

    # Check whether we have a complete number and update it upon
    # receiving a new pulse.
    pulse_state, age = pulse_signal.Pump(new_time)    
    if pulse_state == True and age.total_seconds() == 0:
        # The signal state just changed to high, so we are looking
        # at the beginning of a pulse. Increase digit.
        # We use the beginning of a pulse here because the end of
        # the last pulse doesn't align well with the idle signal,
        # which tends to come in quite a bit earlier than the end
        # of the last pulse.
        current_number = current_number + 1
        char_out.write('p')

    # Check whether we are still idle.
    idle_state, age = idle_signal.Pump(new_time)
    if age.total_seconds() == 0:
      if idle_state == True:
        char_out.write('e')
        if current_number != 0:
          # The idle turned to high again, so we know we are done
          # with the current number.
          char_out.write('%d' % (current_number % 10))          
          current_number = 0
      else:
        char_out.write('s')

    time.sleep(LOOP_SLEEP_TIME)

finally:
 GPIO.cleanup()
