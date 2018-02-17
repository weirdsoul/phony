import logging
import mock
import phone_state
import unittest

class TestPhoneState(unittest.TestCase):
  def setUp(self):
    logging.basicConfig(level=logging.INFO)

  def test_BasicStateTest(self):
    m = mock.Mock()
    state_machine = phone_state.PhoneState(
      0, {('a', 0): 1, ('b', 1): 0, ('d', 0): 2},
      {(0, 1): [m.callback01],
       (1, 0): [m.callback10]})
    
    state_machine.ProcessInput('a')
    m.callback01.assert_called_once_with(0, 1)
    m.callback10.assert_not_called()
    self.assertEqual(1, state_machine.GetCurrentState())

    m.reset_mock()
    state_machine.ProcessInput('b')
    m.callback01.assert_not_called()
    m.callback10.assert_called_once_with(1, 0)
    self.assertEqual(0, state_machine.GetCurrentState())

    m.reset_mock()
    # Unknown input symbol, should do nothing.
    state_machine.ProcessInput('c')
    m.callback01.assert_not_called()
    m.callback10.assert_not_called()
    self.assertEqual(0, state_machine.GetCurrentState())

    m.reset_mock()
    # State transition without callbacks.
    state_machine.ProcessInput('d')
    m.callback01.assert_not_called()
    m.callback10.assert_not_called()
    self.assertEqual(2, state_machine.GetCurrentState())

if __name__ == '__main__':
  unittest.main()

