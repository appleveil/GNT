import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { getFocusedRouteNameFromRoute, RouteProp } from '@react-navigation/native';
import DealsStack from './DealsStack';
import HistoryStack from './HistoryStack';
import { DealsTabIcon, HistoryTabIcon } from '../components/icons';
import { colors } from '../theme/tokens';

const Tab = createBottomTabNavigator();

const tabBarStyle = { backgroundColor: colors.surface, borderTopColor: colors.border };

// Hides the tab bar once the Deals tab drills past its home screen — these
// are single-purpose task flows (pick a deal type, fill in a form), not
// peer destinations, so the tab bar is just competing for space; it also
// removes the tab bar's height as a variable the keyboard-avoidance layout
// on Fixed/Transfer/Profit Split otherwise has to account for (see
// PLAN.md's mobile-app entry on the keyboard-covering-input bug).
function dealsTabBarStyle(route: RouteProp<any, any>) {
  const focused = getFocusedRouteNameFromRoute(route) ?? 'DealsHome';
  return focused === 'DealsHome' ? tabBarStyle : { display: 'none' as const };
}

export default function RootTabs() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accentText,
        tabBarInactiveTintColor: colors.textTertiary,
        tabBarStyle,
        tabBarLabelStyle: { fontSize: 10.5, fontWeight: '600' },
      }}
    >
      <Tab.Screen
        name="DealsTab"
        component={DealsStack}
        options={({ route }) => ({
          title: 'Deals',
          tabBarIcon: ({ color }) => <DealsTabIcon color={color} />,
          tabBarStyle: dealsTabBarStyle(route),
        })}
      />
      <Tab.Screen
        name="HistoryTab"
        component={HistoryStack}
        options={{ title: 'History', tabBarIcon: ({ color }) => <HistoryTabIcon color={color} /> }}
      />
    </Tab.Navigator>
  );
}
