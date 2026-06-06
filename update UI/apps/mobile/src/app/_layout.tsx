/**
 * This file is customizable BUT — do not remove:
 *   • `<AuthModal />` render (shipped v2 auth modal; removing it breaks
 *     signin/signup since useAuth().signIn() only flips state, not render)
 *   • `useAuth().initiate()` + `isReady` gate (loads persisted session from
 *     SecureStore — removing causes user to appear signed-out on app launch)
 *
 * Safe to change: the Stack routes, QueryClient config, splash behavior, the
 * wrapping providers, or to add nested providers around <Stack>.
 */
'use client';

import { ErrorBoundary } from "@/__create/ErrorBoundary";
import { useAuth } from "@/utils/auth/useAuth";
import { AuthModal } from "@/utils/auth/useAuthModal";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect, useState } from "react";
import { GestureHandlerRootView } from "react-native-gesture-handler";
void SplashScreen.preventAutoHideAsync();

const SPLASH_TIMEOUT_MS = 10_000;

const queryClient = new QueryClient({
	defaultOptions: {
		queries: {
			staleTime: 1000 * 60 * 5, // 5 minutes
			gcTime: 1000 * 60 * 30, // 30 minutes
			retry: 1,
			refetchOnWindowFocus: false,
		},
	},
});

export default function RootLayout() {
	const { initiate, isReady } = useAuth();
	const [timedOut, setTimedOut] = useState(false);

	useEffect(() => {
		initiate();
	}, [initiate]);

	useEffect(() => {
		const timeout = setTimeout(() => setTimedOut(true), SPLASH_TIMEOUT_MS);
		return () => clearTimeout(timeout);
	}, []);

	useEffect(() => {
		if (isReady || timedOut) {
			void SplashScreen.hideAsync();
		}
	}, [isReady, timedOut]);

	if (!isReady && !timedOut) {
		return null;
	}

	return (
		<ErrorBoundary>
			<QueryClientProvider client={queryClient}>
				<GestureHandlerRootView style={{ flex: 1 }}>
					<Stack screenOptions={{ headerShown: false }} initialRouteName="index">
						<Stack.Screen name="index" />
					</Stack>
					<AuthModal />
				</GestureHandlerRootView>
			</QueryClientProvider>
		</ErrorBoundary>
	);
}
