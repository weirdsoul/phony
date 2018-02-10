#!/usr/bin/env python
#
# Phony is the main phone application. It is based on
# the linphone Python wrapper library and communicates
# with the hardware through a subprocess.

import ConfigParser
import datetime
import fcntl
import linphone
import logging
import os
import signal
import subprocess
import sys
import time

class Phony:
  ''' Construct Phony instance.

    Args:
      config: config file as an instance of ConfigParser
  '''
  def __init__(self, config):
    self.quit_ = False
    self.config_ = config

    logging.basicConfig(level=logging.INFO)

    signal.signal(signal.SIGINT, self.signal_handler)

    self.initLinphone()
    self.initPhoneIO()

  ''' Run executes the main loop until quit. '''
  def Run(self):
    while not self.quit_:
      self.core_.iterate()
      try:
        # See if the user used a control of the phone
        input_seq = self.phone_controls_.read()
        for i in input_seq:
          self.processUserInput(i)
      except:
        pass

      time_since_last_digit = datetime.datetime.now() - self.current_number_ts_
      if (self.current_number_ and
          time_since_last_digit.total_seconds() > 2 and not self.dialing_):
          logging.info('Dialing outbound number %s' % self.current_number_)
          self.current_call_ = self.core_.invite(
            '{number}@{sip_gateway}'.format(number=self.current_number_,
                                            sip_gateway=self.standard_gateway_))
          
          self.current_number_ = ''
          self.current_number_ts_ = datetime.datetime.now()
      
      time.sleep(0.03)
    
  def initLinphone(self):      
    callbacks = linphone.Factory().get().create_core_cbs()
    callbacks.call_state_changed = self.call_state_changed

    linphone.set_log_handler(self.log_handler)
    self.core_ = linphone.Factory().get().create_core(callbacks,
                                                      None, None)
    self.core_.max_calls = 1
    self.core_.echo_cancellation_enabled = False
    self.core_.video_capture_enabled = False
    self.core_.video_display_enabled = False
    # STUN server should be independent of provider, so we
    # hardcode it here.
    # self.core_.nat_policy.stun_server = 'stun.linphone.org'
    self.core_.nat_policy.stun_server = 'stun.arcor.de'
    self.core_.nat_policy.ice_enabled = True

    self.standard_gateway_ = ''
    for provider in self.config_.sections():
      username = self.config_.get(provider, 'Username')
      password = self.config_.get(provider, 'Password')
      sip_gateway = self.config_.get(provider, 'Gateway')
      is_default = False
      try:
        is_default = self.config_.getboolean(provider, 'default')
      except:
        pass
        
      proxy_config = self.core_.create_proxy_config()
      proxy_config.identity_address = self.core_.create_address(
      'sip:{username}@{sip_gateway}'.format(username=username,
                                            sip_gateway=sip_gateway))
      
      proxy_config.server_addr = 'sip:{sip_gateway}'.format(sip_gateway=sip_gateway)
      proxy_config.register_enabled = True
      self.core_.add_proxy_config(proxy_config)

      if is_default and not self.standard_gateway_:
        # If we have a default, use it. Otherwise, just pick the first one.
        self.core_.default_proxy_config = proxy_config
        self.standard_gateway_ = sip_gateway

      auth_info = self.core_.create_auth_info(username, None, password,
                                              None, None, sip_gateway)
      self.core_.add_auth_info(auth_info)

    # No prospective call yet.
    self.current_call_ = None


  def initPhoneIO(self):
    abs_path = os.path.abspath(sys.argv[0])
    io_binary = os.path.join(
      os.path.dirname(abs_path),
      'phone_io.py')
    print('io binary %s' % io_binary)
    self.phone_IO_ = subprocess.Popen([io_binary],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE)
    self.phone_controls_ = os.fdopen(self.phone_IO_.stdout.fileno(), 'rb', 0)
    flags = fcntl.fcntl(self.phone_IO_.stdout.fileno(), fcntl.F_GETFL)
    fcntl.fcntl(self.phone_IO_.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    # Will track the status of the hook, so we know when a number can
    # be dialed etc.
    self.unhooked_ = False
    # Becomes true while the dial is not in its idle position.
    self.dialing_ = False
    self.current_number_ = ''
    self.current_number_ts_ = datetime.datetime.now()

  ''' Linphone callback updating call state.

    Args:
      core: The linphone core instance.
      call: Details about a call.
      state: The new state.
      message: Message received.
  '''
  def call_state_changed(self, core, call, state, message):
    # Bell management.
    if state == linphone.CallState.IncomingReceived:
      # Ring the bell.
      self.phone_IO_.stdin.write('s')
      # Remember the call, so we can accept or decline it.
      self.current_call_ = call
    elif state in [linphone.CallState.CallEnd,
                   linphone.CallState.CallError,
                   linphone.CallState.CallConnected]:
      # Stop the bell.
      self.phone_IO_.stdin.write('e')

    # Call object management.
    if state in [linphone.CallState.CallEnd,
                 linphone.CallState.CallError]:
      self.current_call_ = None
  

  def log_handler(self, level, msg):
    # Just forward to the appropriate method of the logging
    # framework.
    method = getattr(logging, level)
    method(msg)

  def signal_handler(self, signal, frame):
    self.core_.terminate_all_calls()
    self.phone_IO_.send_signal(signal)
    self.quit_ = True

  def processUserInput(self, input):
    if input == 'l':
      self.unhooked_ = True
      if self.current_call_:
        params = self.core_.create_call_params(self.current_call_)
        self.core_.accept_call_with_params(self.current_call_, params)
      
    elif input == 'd':
      self.unhooked_ = False
      # Reset any (partial) phone number that may have been dialed.
      self.current_number_ = ''
      self.current_number_ts_ = datetime.datetime.now()
      if self.current_call_:
        # Dropping the fork will terminate all calls. We don't want
        # any nasty surprises with connections being kept open in the
        # background.
        self.core_.terminate_all_calls()

    elif input == 's':
      self.dialing_ = True

    elif input == 'e':
      self.dialing_ = False

    elif str.isdigit(input) and self.unhooked_:
      # A new digit has been completed and the phone is unhooked.
      # Add it to the current phone number and update the timestamp.
      self.current_number_ = self.current_number_ + input
      self.current_number_ts_ = datetime.datetime.now()


def main():
  config = ConfigParser.ConfigParser()
  config.read('/etc/phony.conf')
  phony = Phony(config)
  phony.Run()

main()
