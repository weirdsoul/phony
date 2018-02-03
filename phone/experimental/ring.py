# coding=utf-8

import RPi.GPIO as GPIO
import datetime
import time

RING_PULSE = 0.05

try:
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(25, GPIO.OUT)
  GPIO.setup(24, GPIO.OUT)
  GPIO.setup(23, GPIO.OUT)

  while True:
    for i in range(10):
      time.sleep(RING_PULSE)

      GPIO.output(25, GPIO.LOW)
      GPIO.output(23, GPIO.LOW)
      GPIO.output(24, GPIO.HIGH)
      GPIO.output(25, GPIO.HIGH)
    
      time.sleep(RING_PULSE)
      
      GPIO.output(25, GPIO.LOW)
      GPIO.output(23, GPIO.HIGH)
      GPIO.output(24, GPIO.LOW)
      GPIO.output(25, GPIO.HIGH)

    time.sleep(2)

    
finally:
 GPIO.cleanup()
