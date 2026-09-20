import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { DealsStackParamList } from './types';
import { colors } from '../theme/tokens';
import DealsHomeScreen from '../screens/DealsHomeScreen';
import DealTypePickerScreen from '../screens/DealTypePickerScreen';
import FixedScreen from '../screens/FixedScreen';
import TransferScreen from '../screens/TransferScreen';
import ProfitSplitScreen from '../screens/ProfitSplitScreen';

const Stack = createNativeStackNavigator<DealsStackParamList>();

export default function DealsStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
        headerTintColor: colors.textPrimary,
        headerTitleStyle: { color: colors.textPrimary },
      }}
    >
      <Stack.Screen name="DealsHome" component={DealsHomeScreen} options={{ title: 'Deals' }} />
      <Stack.Screen
        name="DealTypePicker"
        component={DealTypePickerScreen}
        options={({ route }) => ({ title: route.params.player.displayName })}
      />
      <Stack.Screen name="Fixed" component={FixedScreen} options={{ title: 'Fixed' }} />
      <Stack.Screen name="Transfer" component={TransferScreen} options={{ title: 'Transfer' }} />
      <Stack.Screen name="ProfitSplit" component={ProfitSplitScreen} options={{ title: 'Stake and Profit splits' }} />
    </Stack.Navigator>
  );
}
