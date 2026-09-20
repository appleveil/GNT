import React from 'react';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

/**
 * Line icons matching the mockup's exact paths — see the artifact's inline
 * SVGs. Kept together in one file since they're all tiny, single-use
 * stroke icons sharing the same props shape.
 */

type IconProps = { color: string; size?: number };

export function DealsTabIcon({ color, size = 21 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Circle cx={9} cy={12} r={7} />
      <Circle cx={15} cy={12} r={7} />
    </Svg>
  );
}

export function HistoryTabIcon({ color, size = 21 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Circle cx={12} cy={12} r={9} />
      <Path d="M12 7v5l3.5 2" />
    </Svg>
  );
}

export function FixedIcon({ color, size = 18 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Path d="M20 6 9 17l-5-5" />
    </Svg>
  );
}

export function TransferIcon({ color, size = 18 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Path d="M7 16V4M7 4 3 8M7 4l4 4M17 8v12m0 0 4-4m-4 4-4-4" />
    </Svg>
  );
}

export function PercentCircleIcon({ color, size = 16 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Circle cx={7} cy={7} r={2} />
      <Circle cx={17} cy={17} r={2} />
      <Path d="M19 5 5 19" />
    </Svg>
  );
}

export function PayoutIcon({ color, size = 16 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Rect x={2} y={6} width={20} height={12} rx={2} />
      <Circle cx={12} cy={12} r={2.5} />
    </Svg>
  );
}

export function ShareIcon({ color, size = 16 }: IconProps) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2}>
      <Circle cx={18} cy={5} r={3} />
      <Circle cx={6} cy={12} r={3} />
      <Circle cx={18} cy={19} r={3} />
      <Path d="M8.6 10.5 15.4 6.5M8.6 13.5l6.8 4" />
    </Svg>
  );
}
