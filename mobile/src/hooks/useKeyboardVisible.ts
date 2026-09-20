import { useEffect, useState } from 'react';
import { Keyboard, Platform } from 'react-native';

/**
 * True exactly while the on-screen keyboard is up — nothing more. Layout
 * that only needs to make room for the keyboard (extra scroll slack, a
 * scrollable region temporarily ceding space to it) should key off this,
 * not off which field happens to be focused: focus/blur only fires for the
 * field itself, so a layout gated on it can restore before the keyboard is
 * actually gone (e.g. tabbing between fields with no gap) or, worse, stay
 * "expanded" after the keyboard is dismissed some other way (the Cancel
 * button, tapping outside, the hardware back gesture) since nothing ever
 * blurs the field in that case. Keyboard show/hide events always match
 * what's actually on screen.
 */
export function useKeyboardVisible(): boolean {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const showEvent = Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow';
    const hideEvent = Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide';
    const showSub = Keyboard.addListener(showEvent, () => setVisible(true));
    const hideSub = Keyboard.addListener(hideEvent, () => setVisible(false));
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  return visible;
}
