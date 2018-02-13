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
import phone_state
import signal
import subprocess
import sys
import time

# The following defines phone states:
PS_READY = 0           # The phone is idle and ready to be used.
PS_DIALING = 1         # The phone is in dialing mode.
PS_REMOTE_RINGING = 2  # The remote side is ringing.
PS_BUSY = 3            # The phone is signalling busy / error.
PS_RINGING = 4         # The phone is ringing.
PS_TALKING = 5         # The phone is connected to the remote.

# Note that in addition to the symbols produced by phone_io.py,
# we introduce a few more symbols to drive our state machine.
# These are mostly generated by the VoIP / SIP stack and fed
# into the state machine to drive state transitions:
#  'a': Remote side calling / accepting to talk.
#  'c': Remote side cancelling / rejecting the call.
#  'o': Dialing complete. Triggered when INVITE is sent.

class Phony:
  def __init__(self, config):
    ''' Construct Phony instance.

    Args:
      config: config file as an instance of ConfigParser
    '''
    self.quit_ = False
    self.config_ = config

    self.phone_state_ = phone_state.PhoneState(PS_READY,
      # Possible state transitions and their triggers.
      {('l', PS_READY): PS_DIALING,   # Lift handset.
       ('l', PS_RINGING): PS_TALKING,
       
       ('d', PS_DIALING): PS_READY,   # Drop handset.
       ('d', PS_REMOTE_RINGING): PS_READY,
       ('d', PS_BUSY): PS_READY,
       ('d', PS_TALKING): PS_READY,

       ('a', PS_READY): PS_RINGING,  # Incoming call.
       ('a', PS_REMOTE_RINGING): PS_TALKING,

       ('c', PS_REMOTE_RINGING): PS_BUSY, # Caller rejects.
       ('c', PS_RINGING): PS_READY,
       ('c', PS_TALKING): PS_BUSY,

       ('o', PS_DIALING): PS_REMOTE_RINGING},
      # Callbacks triggered by state transitions.
      {})
    
    logging.basicConfig(level=logging.INFO)

    signal.signal(signal.SIGINT, self.signal_handler)

    self.initLinphone()
    self.initPhoneIO()

  def Run(self):
    ''' Run executes the main loop until quit. '''
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
        # Update state machine to say we are done dialing.
        self.phone_state_.ProcessInput('o')
        logging.info('Dialing outbound number %s' % self.current_number_)
        self.current_call_ = self.core_.invite(
          '{number}@{sip_gateway}'.format(number=self.current_number_,
                                          sip_gateway=self.standard_gateway_))
          
        self.current_number_ = ''
        self.current_number_ts_ = datetime.datetime.now()

      # Keep active dial tone going, but don't start a new one.
      self.processDialTone(False)
                
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

    # Manually configure ringback tone, so we can be sure that
    # it is found.
    self.core_.remote_ringback_tone = '/home/pi/coding/phone/remote_ringback.wav'
    self.core_.ringback = '/home/pi/coding/phone/ringback.wav'
    
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
    # Don't play dial tone right now.
    self.dial_tone_ = None
    # Becomes true while the dial is not in its idle position.
    self.dialing_ = False
    self.current_number_ = ''
    self.current_number_ts_ = datetime.datetime.now()

  def call_state_changed(self, core, call, state, message):
    ''' Linphone callback updating call state.

    Args:
      core: The linphone core instance.
      call: Details about a call.
      state: The new state.
      message: Message received.
    '''


    if state in [linphone.CallState.IncomingReceived,
                 linphone.CallState.CallConnected]:
      # Update state machine to say we are seeing an
      # incoming call.
      self.phone_state_.ProcessInput('a')

    if state in [linphone.CallState.CallEnd,
                 linphone.CallState.CallError]:
      # Update state machine to say the remote side
      # cancelled the call.
      self.phone_state_.ProcessInput('c')
    
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
    # method(msg)

  def signal_handler(self, signal, frame):
    self.core_.terminate_all_calls()
    self.phone_IO_.send_signal(signal)
    self.quit_ = True

  def processDialTone(self, start_playing):
    current = datetime.datetime.now()
    diff = None
    if self.dial_tone_:
      diff = current - self.dial_tone_
    # TODO(aeckleder): This is very specific to the dial tone we use.
    # I'm sure we can do better.
    if start_playing or (diff and diff.total_seconds() > 1):
        self.core_.play_local('/home/pi/coding/phone/dial_tone.wav')
        self.dial_tone_ = current

  def processUserInput(self, input):
    # Keep the state machine up to date.
    self.phone_state_.ProcessInput(input)
    if input == 'l':
      self.unhooked_ = True      
      if self.current_call_:
        # An incoming call is already waiting. Accept it.
        params = self.core_.create_call_params(self.current_call_)
        self.core_.accept_call_with_params(self.current_call_, params)
      else:        
        # No incoming call. Play dial tone.
        self.processDialTone(True)
      
    elif input == 'd':
      self.unhooked_ = False
      # Stop any dial tone that may be playing.
      self.dial_tone_ = None
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
      # Stop any dial tone that may be playing.
      self.dial_tone_ = None

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
