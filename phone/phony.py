#!/usr/bin/env python
#
# Phony is the main phone application. It is based on
# the linphone Python wrapper library and communicates
# with the hardware through a subprocess.

from __future__ import division

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

# The dial timeout determines the number of seconds to wait
# until a number is presumed to be complete.
DIAL_TIMEOUT = 2

# Use the ring back sound from linphone.
# TODO(aeckleder): Make this configurable.
RING_BACK = '/usr/local/lib/python2.7/dist-packages/linphone/share/sounds/linphone/ringback.wav'

# The following defines phone states:
PS_READY = 0           # The phone is idle and ready to be used.
PS_DIAL_TONE = 1       # The phone is ready to dial (dial tone).
PS_DIAL_MOVING = 2     # The phone dial is moving.
PS_DIALING = 3         # The phone is in dialing mode.
PS_REMOTE_RINGING = 4  # The remote side is ringing.
PS_BUSY = 5            # The phone is signalling busy / error.
PS_RINGING = 6         # The phone is ringing.
PS_TALKING = 7         # The phone is connected to the remote.

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
      {('l', PS_READY): PS_DIAL_TONE,   # Lift handset.
       ('l', PS_RINGING): PS_TALKING,
       
       ('d', PS_DIAL_TONE): PS_READY,  # Drop handset.
       ('d', PS_DIALING): PS_READY,
       ('d', PS_DIAL_MOVING): PS_READY,
       ('d', PS_REMOTE_RINGING): PS_READY,
       ('d', PS_BUSY): PS_READY,
       ('d', PS_TALKING): PS_READY,

       ('s', PS_DIAL_TONE): PS_DIAL_MOVING, # Dial moved from idle.
       ('s', PS_DIALING): PS_DIAL_MOVING,

       ('1234567890', # Any digit marking the end of a dial cycle.
        PS_DIAL_MOVING): PS_DIALING, # Dial produced a digit.

       ('p', PS_DIAL_MOVING): PS_DIAL_MOVING, # Pulse generator.

       ('a', PS_READY): PS_RINGING,  # Incoming call.
       ('a', PS_REMOTE_RINGING): PS_TALKING,

       ('c', PS_REMOTE_RINGING): PS_BUSY, # Caller rejects.
       ('c', PS_RINGING): PS_READY,
       ('c', PS_TALKING): PS_BUSY,

       ('o', PS_DIALING): PS_REMOTE_RINGING},
      {(PS_READY, PS_DIAL_TONE): [self.startDialTone],
       (PS_READY, PS_RINGING): [self.startBell],
       
       (PS_DIAL_TONE, PS_DIAL_MOVING): [self.startDialing],
       (PS_DIAL_MOVING, PS_DIALING): [self.processDigit],
       (PS_DIAL_MOVING, PS_DIAL_MOVING): [self.playPulse],
       (PS_DIALING, PS_REMOTE_RINGING): [self.dialNumber],
       
       (PS_REMOTE_RINGING, PS_READY): [self.cancelCall],
       (PS_REMOTE_RINGING, PS_BUSY): [self.startBusyTone],
       
       (PS_RINGING, PS_TALKING): [self.stopBell,
                                  self.acceptCall],
       (PS_RINGING, PS_READY): [self.stopBell],
       
       (PS_TALKING, PS_READY): [self.cancelCall],
       (PS_TALKING, PS_BUSY): [self.startBusyTone]
      })
    
    logging.basicConfig(level=logging.INFO)

    signal.signal(signal.SIGINT, self.signal_handler)

    self.initLinphone()
    self.initPhoneIO()

  def Run(self):
    ''' Run executes the main loop until quit. '''
    while not self.quit_:
      self.core_.iterate()
      input_seq = ''
      try:
        # See if the user used a control of the phone
        input_seq = self.phone_controls_.read()
      except:
        pass
      for i in input_seq:
        # Keep the state machine up to date.
        self.phone_state_.ProcessInput(i)

      # Dialing mode has a timeout. We don't model timeouts in our state machine,
      # so we have to keep track of time manually here.
      if self.phone_state_.GetCurrentState() == PS_DIALING:
        time_since_last_digit = datetime.datetime.now() - self.current_number_ts_
        if time_since_last_digit.total_seconds() > DIAL_TIMEOUT:
          # Update state machine to say we are done dialing.
          self.phone_state_.ProcessInput('o')

      elif self.phone_state_.GetCurrentState() in [PS_DIAL_TONE, PS_BUSY]:
        # Keep active dial tone going, but don't start a new one.
        self.processTone()
                
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
    self.core_.remote_ringback_tone = RING_BACK
    self.core_.ringback = RING_BACK

    logging.info('Setting up SIP configuration.')
    self.standard_gateway_ = ''
    # We keep track of usernames configured for the various gateways,
    # and accept incoming calls only if there is a match.
    self.accepted_usernames_ = set()

    for provider in self.config_.sections():
      username = self.config_.get(provider, 'Username')
      self.accepted_usernames_.add(username)

      password = self.config_.get(provider, 'Password')
      sip_gateway = self.config_.get(provider, 'Gateway')
      is_default = False
      try:
        is_default = self.config_.getboolean(provider, 'default')
      except:
        pass
      user_id = None
      try:
        user_id = self.config_.get(provider, 'Userid')
      except:
        pass

      proxy_config = self.core_.create_proxy_config()
      proxy_config.identity_address = self.core_.create_address(
      'sip:{username}@{sip_gateway}'.format(username=username,
                                            sip_gateway=sip_gateway))
      
      proxy_config.server_addr = 'sip:{sip_gateway}'.format(sip_gateway=sip_gateway)
      proxy_config.register_enabled = True
      self.core_.add_proxy_config(proxy_config)

      logging.info('Registering {username}@{sip_gateway},default={is_default}'.format(
        username=username,
        sip_gateway=sip_gateway,
        is_default=is_default))
   
      if is_default or not self.standard_gateway_:
        # If we have a default, use it. Otherwise, just pick the first one.
        self.core_.default_proxy_config = proxy_config
        self.standard_gateway_ = sip_gateway

      auth_info = self.core_.create_auth_info(username, user_id, password,
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

  def call_state_changed(self, core, call, state, message):
    ''' Linphone callback updating call state.

    Args:
      core: The linphone core instance.
      call: Details about a call.
      state: The new state.
      message: Message received.
    '''
    if (state == linphone.CallState.IncomingReceived and
        self.phone_state_.GetCurrentState() != PS_READY):
      # Incoming call, but we are not in state ready.
      # Tell the other side that we are busy and otherwise
      # ignore the incoming call.
      logging.info('Declining incoming call while busy.')      
      self.core_.decline_call(call, linphone.Reason.Busy)
      return

    if (state == linphone.CallState.IncomingReceived and
        not call.call_log.to_address.username in
        self.accepted_usernames_):
      # Incoming call, but not for one of the whitelisted
      # usernames. Ignore the incoming call.
      logging.info('Declining incoming call, unknown target %s' %
                   call.call_log.to_address.username)
      self.core_.decline_call(call, linphone.Reason.Busy)
      return


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
    
    # Call object management.
    if state == linphone.CallState.IncomingReceived:
      # Remember the call, so we can accept or decline it.
      self.current_call_ = call
    elif state in [linphone.CallState.CallEnd,
                 linphone.CallState.CallError]:
      # Clear the call object. We no longer need it.
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

  def processTone(self, tone_file=None):
    ''' Process a tone (e.g. dial tone, busy tone).

    Args:
      tone_file: Tone to play. Can be None for repeated
                 calls to repeat the tone. Must be a 16 bit
                 8kHz Mono WAV file.
    '''
    current = datetime.datetime.now()
    if tone_file:
      self.tone_start_ = current
      self.tone_file_ = tone_file
      s = os.stat(tone_file)
      self.tone_duration_ = s.st_size / (8000 * 2)

    diff = current - self.tone_start_
    if tone_file or diff.total_seconds() > self.tone_duration_:
        self.core_.play_local(self.tone_file_)
        self.tone_start_ = current

  def startDialTone(self, previous_state, next_state, input):
    ''' Start playing the dial tone.'''
    self.processTone('/home/pi/coding/phony/phone/dial_tone.wav')

  def startBusyTone(self, previous_state, next_state, input):
    ''' Start playing the busy tone.'''
    self.processTone('/home/pi/coding/phony/phone/busy_tone.wav')

  def playPulse(self, previous_state, next_state, input):
    ''' Play a single dialing pulse.'''
    self.core_.play_local('/home/pi/coding/phony/phone/pulse.wav')    

  def startDialing(self, previous_state, next_state, input):
    self.current_number_ = ''
    self.current_number_ts_ = datetime.datetime.now()
    
  def startBell(self, previous_state, next_state, input):
    ''' Start ringing the bell.'''
    self.phone_IO_.stdin.write('s')

  def stopBell(self, previous_state, next_state, input):
    ''' Stop ringing the bell.'''
    self.phone_IO_.stdin.write('e')

  def dialNumber(self, previous_state, next_state, input):
    ''' Dial the current number.'''
    logging.info('Dialing outbound number %s' % self.current_number_)
    self.current_call_ = self.core_.invite(
      '{number}@{sip_gateway}'.format(number=self.current_number_,
                                      sip_gateway=self.standard_gateway_))
    
  def cancelCall(self, previous_state, next_state, input):
    ''' Cancel all active calls.'''
    logging.info('Cancelling active calls.')
    # Just terminate all calls. We don't want any nasty surprises with
    # connections being kept open in the background.    
    self.core_.terminate_all_calls()
    self.current_call_ = None

  def acceptCall(self, previous_state, next_state, input):
    ''' Accept incoming call.'''
    logging.info('Accepting incoming call.')
    if self.current_call_:
      # An incoming call is already waiting. Accept it.
      params = self.core_.create_call_params(self.current_call_)
      self.core_.accept_call_with_params(self.current_call_, params)
    else:
      logging.warning('acceptCall in wrong state ignored.')

  def processDigit(self, previous_state, next_state, input):
    ''' A new digit has been completed.
    Add it to the current phone number and update the timestamp.'''
    self.current_number_ = self.current_number_ + input
    self.current_number_ts_ = datetime.datetime.now()


def main():
  config = ConfigParser.ConfigParser()
  config.read('/etc/phony.conf')
  phony = Phony(config)
  phony.Run()

main()
