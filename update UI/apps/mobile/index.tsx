import ExceptionsManager from "react-native/Libraries/Core/ExceptionsManager";

if (__DEV__) {
	ExceptionsManager.handleException = (_error, _isFatal) => {
		// no-op
	};
}

import "react-native-url-polyfill/auto";
import "./src/__create/polyfills";
global.Buffer = require("buffer").Buffer;

import "@expo/metro-runtime";
import { AppRegistry, LogBox } from "react-native";
import { initSentry } from "./__create/sentry";
import { initTestFlightLogger } from "./__create/testflight-logger";
import { renderRootComponent } from "expo-router/build/renderRootComponent";
import App from "./entrypoint";

initSentry();
initTestFlightLogger();

if (__DEV__ || process.env.EXPO_PUBLIC_CREATE_ENV === "DEVELOPMENT") {
	LogBox.ignoreAllLogs();
	LogBox.uninstall();
	AppRegistry.setWrapperComponentProvider(() => ({ children }) => {
		return <>{children}</>;
	});
}
renderRootComponent(App);
