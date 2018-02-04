# Signal class handling a single GPIO pin.
#
# coding=utf-8

import datetime
import time
import RPi.GPIO as GPIO

# Minimum distance between two edges in seconds.
DEFAULT_SIGNAL_DIST = 0.005

class GpioSignal:
  """ GpioSignal manages a single GPIO port.
  
  This class has a pump method that will poll the assigned
  pin, do a few sanity checks and then signal to the call whether
  there was a state change. What this class does is very similar
  to the event callbacks of RPi.GPIO, but it has a noise filter.
  """
  
  def __init__(self, gpio_port, current_time,
               min_signal_dist=DEFAULT_SIGNAL_DIST):
    """ Construct a signal object.
    
    Args:
      gpio_port: The GPIO port to listen on. This port will be initialized
        with a pull-up resistor.
      current_time: You must pass the current time here. The main reason why
        we don't poll current time outselves here is to ensure consistency
        among signals.
      min_signal_dist: Minimum distance between edges in seconds.
    """
    self.gpio_port_ = gpio_port
    GPIO.setup(gpio_port, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    self.previous_state_ = GPIO.input(gpio_port)
    self.previous_state_ts_ = current_time
    self.min_signal_dist_ = min_signal_dist
         
  def Pump(self, current_time):
    """ Pump reads from its GPIO port and returns the current state.

    Args:
      current_time: You must pass the current time here. The main reason why
        we don't poll current time outselves here is to ensure consistency
        among signals.
    Returns:
      A tuple state, age where state is a boolean and age specifies the
      amount of time since the last update. An age of zero means that the
      state just changed.
    """
    time_diff = current_time - self.previous_state_ts_
    current_state = GPIO.input(self.gpio_port_)        
    if (self.previous_state_ != current_state and
        time_diff.total_seconds() > self.min_signal_dist_):
      self.previous_state_ = current_state
      self.previous_state_ts_ = current_time
    return self.previous_state_, current_time - self.previous_state_ts_
