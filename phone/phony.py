#!/usr/bin/env python
#
# Phony is the main phone application. It is based on
# the linphone Python wrapper library and communicates
# with the hardware through a subprocess.

import ConfigParser
import fcntl
import linphone
import logging
import os
import signal
import subprocess
import time

class Phony:
  ''' Construct Phony instance.

    Args:
      username: The user name on the SIP gateway.
      password: The password for username.
      sip_gateway: Gateway server to be used.
  '''
  def __init__(self, username, password, sip_gateway):
    self.quit_ = False
    
    self.username_ = username
    self.password_ = password
    self.sip_gateway_ = sip_gateway

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
    self.core_.nat_policy.stun_server = 'stun.linphone.org'
    self.core_.nat_policy.ice_enabled = True

    proxy_config = self.core_.create_proxy_config()
    proxy_config.identity_address = self.core_.create_address(
      'sip:{username}@{sip_gateway}'.format(username=self.username_,
                                            sip_gateway=self.sip_gateway_))
    proxy_config.server_addr = 'sip:{sip_gateway}'.format(
      sip_gateway=self.sip_gateway_)
    proxy_config.register_enabled = True
    self.core_.add_proxy_config(proxy_config)

    auth_info = self.core_.create_auth_info(self.username_, None, self.password_,
                                            None, None, self.sip_gateway_)
    self.core_.add_auth_info(auth_info)

    # No prospective call yet.
    self.call_ = None


  def initPhoneIO(self):
    self.phone_IO_ = subprocess.Popen(['./phone_io.py'],
                                      stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE)
    self.phone_controls_ = os.fdopen(self.phone_IO_.stdout.fileno(), 'rb', 0)
    flags = fcntl.fcntl(self.phone_IO_.stdout.fileno(), fcntl.F_GETFL)
    fcntl.fcntl(self.phone_IO_.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)

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
    if self.current_call_:
      if input == 'l':
        params = self.core_.create_call_params(self.current_call_)
        self.core_.accept_call_with_params(self.current_call_, params)
      elif input == 'd':
        # Dropping the fork will terminate all calls. We don't want
        # any nasty surprises with connections being kept open in the
        # background.
        self.core_.terminate_all_calls()


def main():
  config = ConfigParser.ConfigParser()
  config.read('phony.conf')
  phony = Phony(config.get('DEFAULT', 'Username'),
                config.get('DEFAULT', 'Password'),
                config.get('DEFAULT', 'Gateway'))
  phony.Run()

main()
