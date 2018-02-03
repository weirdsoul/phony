# Signal class handling a single GPIO pin.
#
# coding=utf-8

import datetime
import time
import RPi.GPIO as GPIO

# Minimum distance between two edges in microseconds.
MIN_SIGNAL_DIST = 1000*20

class GpioSignal:
  """ GpioSignal manages a single GPIO port.
  
  This class has a pump method that will poll the assigned
  pin, do a few sanity checks and then execute code upon
  receiving a state change. What this class does is very similar
  to the event callbacks of RPi.GPIO, but it has a noise filter.
  """
  
  def __init__(self, gpio_port, state_change_cb, current_time):
    """ Construct a signal object.
    
    Args:
      gpio_port: The GPIO port to listen on. This port will be initialized
        with a pull-up resistor.
        state_change_cb: A callback to call when the state changes. The callback
        has to be in the form state_change_cb(signal, old_state, new_state).
      current_time: You must pass the current time here. The main reason why
        we don't poll current time outselves here is to ensure consistency
        among signals.
    """
    self.gpio_port_ = gpio_port
    self.state_change_cb_ = state_change_cb
    GPIO.setup(gpio_port, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    self.previous_state_ = GPIO.input(gpio_port)
    self.previous_state_ts_ = current_time
         
  def GetCurrentState(self, current_time):
    """ Retrieve the current state of the signal.
    
    Args:
      current_time: You must pass the current time here. The main reason why
        we don't poll current time outselves here is to ensure consistency
        among signals.
    Returns:
      A tuple state, age where state is a boolean and age specifies the
      amount of time since the last update.
    """
    return self.previous_state_, current_time - self.previous_state_ts_
      
  def Pump(self, current_time):
    """ Pump reads from its GPIO port and decides whether to execute a callback.

    Args:
      current_time: You must pass the current time here. The main reason why
        we don't poll current time outselves here is to ensure consistency
        among signals.
    """
    time_diff = current_time - self.previous_state_ts_
    current_state = GPIO.input(self.gpio_port_)        
    if (self.previous_state_ != current_state and
        time_diff.microseconds > MIN_SIGNAL_DIST):
      self.state_change_cb_(self, self.previous_state_, current_state)
      self.previous_state_ = current_state
      self.previous_state_ts_ = current_time
