export * from 'expo-font';
export { useFonts } from 'expo-font';

export async function renderToImageAsync(): Promise<{
  uri: string;
  width: number;
  height: number;
}> {
  return { uri: '', width: 0, height: 0 };
}
