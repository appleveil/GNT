import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import DealsStack from './DealsStack';
import HistoryStack from './HistoryStack';
import { DealsTabIcon, HistoryTabIcon } from '../components/icons';
import { colors } from '../theme/tokens';

const Tab = createBottomTabNavigator();

export default function RootTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accentText,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle: { backgroundColor: colors.surface, borderTopColor: colors.border },
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '600' },
      }}
    >
      <Tab.Screen
        name="DealsTab"
        component={DealsStack}
        options={{ title: 'Deals', tabBarIcon: ({ color }) => <DealsTabIcon color={color} /> }}
      />
      <Tab.Screen
        name="HistoryTab"
        component={HistoryStack}
        options={{ title: 'History', tabBarIcon: ({ color }) => <HistoryTabIcon color={color} /> }}
      />
    </Tab.Navigator>
  );
}
