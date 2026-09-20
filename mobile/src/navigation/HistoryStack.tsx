import React from 'react';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import type { HistoryStackParamList } from './types';
import { colors } from '../theme/tokens';
import HistoryScreen from '../screens/HistoryScreen';
import ProfitSplitDetailScreen from '../screens/ProfitSplitDetailScreen';

const Stack = createNativeStackNavigator<HistoryStackParamList>();

export default function HistoryStack() {
  return (
    <Stack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: colors.bg },
        headerShadowVisible: false,
        headerTintColor: colors.textPrimary,
        headerTitleStyle: { color: colors.textPrimary },
      }}
    >
      <Stack.Screen name="History" component={HistoryScreen} options={{ title: 'History' }} />
      <Stack.Screen
        name="ProfitSplitDetail"
        component={ProfitSplitDetailScreen}
        options={{ title: 'Stake and Profit splits' }}
      />
    </Stack.Navigator>
  );
}
