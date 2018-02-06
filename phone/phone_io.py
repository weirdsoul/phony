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
# Input:
#  's': Start (the configured) ring sequence.
#  'e': End ring sequence.
#
# While l and d can always be triggered, the other outputs
# form a sequence matching this regular expression:
# sp*e[0-9]?
# If you get any other reading from this routine after filtering
# out 'l' and 'd', you are probably dealing with a hardware problem.
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

# Input ports:
PORT_PULSE = 4 # Receives pulses while dialing a digit.
PORT_IDLE = 17 # Receives dial idle signal.
PORT_HOOK = 27 # Receices the hook signal.

# Output ports:
PORT_RING_ENABLE = 25 # Enable / disable ring magnet.
PORT_RING_LEFT = 24   # Enable / disable left bell.
PORT_RING_RIGHT = 23  # Enable / disable right bell.

# Expresses the frequency of the ring signal:
# Frequency = 1 / (2 * RING_PULSE).
RING_PULSE_TIME = 0.05

# Sleep time in seconds between ring sequences.
RING_SLEEP_TIME = 2

# Active time of the bell in seconds.
RING_ACTIVE_TIME = 1

def GetRingState(time_diff):
  ''' GetRingState calculates the status of the bell.

  Args:
    time_diff: The timestamp to use to do the calculation.
  Returns:
    One of three status values:
      0: Bell is off
      1: Left bell
      2: Right bell
  '''
  sequence_duration = RING_ACTIVE_TIME + RING_SLEEP_TIME 
  time_in_seq = time_diff.total_seconds() % sequence_duration
  if time_in_seq > RING_ACTIVE_TIME:
    # Exceeded the active time of the cycle. Bell is off.
    return 0
  # We alternate between 1 and 2 with every ring pulse.
  return int(time_in_seq / RING_PULSE_TIME) % 2 + 1

try:
  GPIO.setmode(GPIO.BCM)

  # Setup out pins for bell.
  GPIO.setup(PORT_RING_ENABLE, GPIO.OUT)
  GPIO.setup(PORT_RING_LEFT, GPIO.OUT)
  GPIO.setup(PORT_RING_RIGHT, GPIO.OUT)

  # Create file objects without buffering, so all I/O we produce
  # or receive is effective immediately.
  char_out = os.fdopen(sys.stdout.fileno(), 'wb', 0)
  char_in = os.fdopen(sys.stdin.fileno(), 'rb', 0)
  
  current_number = 0
  start_time = datetime.datetime.now()
  
  pulse_signal = gpio_signal.GpioSignal(PORT_PULSE, start_time)
  idle_signal = gpio_signal.GpioSignal(PORT_IDLE, start_time)
  hook_signal = gpio_signal.GpioSignal(PORT_HOOK, start_time)

  # Start with the bell off.
  previous_bell_state = 0
  
  while True:
    new_time = datetime.datetime.now()

    new_bell_state = GetRingState(new_time - start_time)
    if new_bell_state != previous_bell_state:
      previous_bell_state = new_bell_state

      # Reconfigure the bell.
      GPIO.output(PORT_RING_ENABLE, GPIO.LOW)
      GPIO.output(PORT_RING_LEFT, GPIO.LOW if new_bell_state == 1 else GPIO.HIGH)
      GPIO.output(PORT_RING_RIGHT, GPIO.HIGH if new_bell_state == 1 else GPIO.LOW)
      GPIO.output(PORT_RING_ENABLE, GPIO.HIGH)
      
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

    # Check hook status.
    hook_state, age = hook_signal.Pump(new_time)
    if age.total_seconds() == 0:
      if hook_state == False:
        char_out.write('d')
      else:
        char_out.write('l')    

    time.sleep(LOOP_SLEEP_TIME)

finally:
 GPIO.cleanup()
