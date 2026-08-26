import { Text, View } from 'react-native';

export function IconAvatar({
  emoji,
  bgClass,
  size = 38,
  fontSize = 19,
}: {
  emoji: string;
  bgClass: string;
  size?: number;
  fontSize?: number;
}) {
  return (
    <View
      style={{ width: size, height: size, borderRadius: size / 2 }}
      className={`items-center justify-center ${bgClass}`}>
      <Text style={{ fontSize }}>{emoji}</Text>
    </View>
  );
}
