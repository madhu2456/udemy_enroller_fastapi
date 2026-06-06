import React from 'react';
import { TextInput as RNTextInput, type TextInputProps } from 'react-native';

const TextInput = React.forwardRef<RNTextInput, TextInputProps>((props, ref) => {
  return (
    <RNTextInput
      ref={ref}
      placeholderTextColor={props.placeholderTextColor || 'black'}
      {...props}
    />
  );
});

TextInput.displayName = 'TextInput';

export default TextInput;
