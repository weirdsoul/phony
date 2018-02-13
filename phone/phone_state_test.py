import logging
import phone_state
import unittest

class TestPhoneState(unittest.TestCase):
  def setUp(self):
    logging.basicConfig(level=logging.INFO)

  def test_BasicStateTest(self):
    state_machine = phone_state.PhoneState(
      0, {('a', 0): 1, ('b', 1): 0, ('d', 0): 2},
      {(0, 1): [self.callback01],
       (1, 0): [self.callback10]})
    
    self.callback01_ = False
    self.callback10_ = False
    state_machine.ProcessInput('a')
    self.assertEqual(True, self.callback01_)
    self.assertEqual(False, self.callback10_)
    self.assertEqual(1, state_machine.GetCurrentState())

    self.callback01_ = False
    self.callback10_ = False
    state_machine.ProcessInput('b')
    self.assertEqual(False, self.callback01_)
    self.assertEqual(True, self.callback10_)
    self.assertEqual(0, state_machine.GetCurrentState())

    self.callback01_ = False
    self.callback10_ = False
    # Unknown input symbol, should do nothing.
    state_machine.ProcessInput('c')
    self.assertEqual(False, self.callback01_)
    self.assertEqual(False, self.callback10_)
    self.assertEqual(0, state_machine.GetCurrentState())
    
    self.callback01_ = False
    self.callback10_ = False
    # State transition without callbacks.
    state_machine.ProcessInput('d')
    self.assertEqual(False, self.callback01_)
    self.assertEqual(False, self.callback10_)
    self.assertEqual(2, state_machine.GetCurrentState())
    
  def callback01(self, previous, next):
    self.assertEqual(0, previous)
    self.assertEqual(1, next)
    self.callback01_ = True

  def callback10(self, previous, next):
    self.assertEqual(1, previous)
    self.assertEqual(0, next)
    self.callback10_ = True

if __name__ == '__main__':
  unittest.main()

