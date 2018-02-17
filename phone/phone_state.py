# Phone state
#
# A simple state machine supporting callbacks for state changes.
#

import logging

class PhoneState:
  ''' PhoneState is a simple state machine. It is configured with
    - a set of states
    - a set of state transitions, which are dictionaries of
      {(input, previous_state) : next_state}.
    - Callbacks that are triggered during state
      transitions: {(previous_state, next_state) : [callbacks]}.
  '''
  
  def __init__(self, initial_state, transitions, callbacks):
    ''' Construct PhoneState instance
   
    Args:
      initial_state: The initial state the state
                     machine should be in.
      transitions:   {(input, previous_state) : next_state}
                     Input can be a string of symbols, each of
                     which will cause the described state
                     transition.
      callbacks:     {(previous_state, next_state) : [callbacks]}.
                     Signature: callback(previous, next, input).                     
    '''
    self.current_state_ = initial_state
    self.transitions_ = {}
    for t in transitions.items():
      # Create a separate entry for all permitted inputs.
      # This effectively disassembles the key of the input
      # dictionary and creates a separate key for each
      # possible input symbol.
      for i in t[0][0]:
        self.transitions_[(i,t[0][1])] = t[1]
    self.callbacks_ = callbacks    

  def ProcessInput(self, input):
    ''' ProcessInput performs state transitions according to
    the specified input. It will determine next state from
    current state and call callbacks as appropriate.

     Args:
       input: The input symbol to be processed.
    '''
    try:
      previous_state = self.current_state_
      # Apply the new state. If we don't have a transition for the
      # combination of input and symbol, we just fall through with
      # a KeyError. No point in calling any callbacks then.
      self.current_state_ = self.transitions_[(input,previous_state)]
      logging.info('TR: ({input}, {prev}): {next}'.format(
        input=input, prev=previous_state, next=self.current_state_))

      callbacks = self.callbacks_[(previous_state, self.current_state_)]
      for c in callbacks:
        c(previous_state, self.current_state_, input)
    except KeyError:
      # Simply fall through if either we don't have a state transition
      # or a list of callbacks. This is not an error.
      pass

  def GetCurrentState(self):
    ''' GetCurrentState returns the current state of the state machine.'''
    return self.current_state_

