# coding=utf-8

from __future__ import division

import RPi.GPIO as GPIO
import datetime
import time
import io
import math
import os
import sys

SAMPLE_DURATION = 1/11025

try:
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(25, GPIO.OUT)
  GPIO.setup(24, GPIO.OUT)
  GPIO.setup(23, GPIO.OUT)

  GPIO.output(25, GPIO.LOW)
  GPIO.output(23, GPIO.HIGH)
  GPIO.output(24, GPIO.LOW)
  GPIO.output(25, GPIO.HIGH)
  time.sleep(0.5)
 
  source = os.fdopen(sys.stdin.fileno(),'rb',16384)

  counter = 0
  while True:    
    buf = source.read(16384)
    if not buf:
      break

    for val in buf:
      
      num = ord(val)

      counter = counter +1
   
      GPIO.output(25, GPIO.LOW)
      if (counter / 2) % 2: #num > 127:
        GPIO.output(23, GPIO.HIGH)
        GPIO.output(24, GPIO.LOW)
      else:
        GPIO.output(23, GPIO.LOW)
        GPIO.output(24, GPIO.LOW)
      GPIO.output(25, GPIO.HIGH)
      time.sleep(SAMPLE_DURATION)
      
    
finally:
 GPIO.cleanup()
