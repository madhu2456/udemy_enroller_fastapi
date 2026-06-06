import type React from "react";
import { Text, View, type ViewStyle } from "react-native";

// Stub for react-native-google-mobile-ads on web.
// Ads are native-only; these render visual placeholders so users can preview
// their layouts in Expo Go without the native module.

export const BannerAdSize = {
	BANNER: "BANNER",
	FULL_BANNER: "FULL_BANNER",
	LARGE_BANNER: "LARGE_BANNER",
	LEADERBOARD: "LEADERBOARD",
	MEDIUM_RECTANGLE: "MEDIUM_RECTANGLE",
	ADAPTIVE_BANNER: "ADAPTIVE_BANNER",
	ANCHORED_ADAPTIVE_BANNER: "ANCHORED_ADAPTIVE_BANNER",
	INLINE_ADAPTIVE_BANNER: "INLINE_ADAPTIVE_BANNER",
	WIDE_SKYSCRAPER: "WIDE_SKYSCRAPER",
};

export const AdEventType = {
	LOADED: "loaded",
	ERROR: "error",
	OPENED: "opened",
	CLICKED: "clicked",
	CLOSED: "closed",
};

export const RewardedAdEventType = {
	LOADED: "loaded",
	EARNED_REWARD: "earned_reward",
};

export const AdsConsentStatus = {
	UNKNOWN: 0,
	REQUIRED: 1,
	NOT_REQUIRED: 2,
	OBTAINED: 3,
};

export const AdsConsentDebugGeography = {
	DISABLED: 0,
	EEA: 1,
	NOT_EEA: 2,
};

export const TestIds = {
	BANNER: "ca-app-pub-3940256099942544/6300978111",
	GAM_BANNER: "ca-app-pub-3940256099942544/6300978111",
	INTERSTITIAL: "ca-app-pub-3940256099942544/1033173712",
	GAM_INTERSTITIAL: "ca-app-pub-3940256099942544/1033173712",
	REWARDED: "ca-app-pub-3940256099942544/5224354917",
	REWARDED_INTERSTITIAL: "ca-app-pub-3940256099942544/5354046379",
	APP_OPEN: "ca-app-pub-3940256099942544/3419835294",
	NATIVE: "ca-app-pub-3940256099942544/2247696110",
	NATIVE_VIDEO: "ca-app-pub-3940256099942544/1044960115",
};

const PLACEHOLDER_BG = "#f5f5f5";
const PLACEHOLDER_BORDER = "#e0e0e0";
const PLACEHOLDER_TEXT = "#999999";
const AD_LABEL_BG = "#fbbc04";
const AD_LABEL_TEXT = "#1a1a1a";

const AdLabel = () => (
	<View
		style={{
			backgroundColor: AD_LABEL_BG,
			paddingHorizontal: 4,
			paddingVertical: 1,
			borderRadius: 2,
		}}
	>
		<Text
			style={{
				fontSize: 9,
				fontWeight: "700",
				color: AD_LABEL_TEXT,
				lineHeight: 11,
			}}
		>
			Ad
		</Text>
	</View>
);

const getBannerStyle = (size: string | undefined): ViewStyle => {
	switch (size) {
		case "FULL_BANNER":
			return { width: 468, height: 60 };
		case "LARGE_BANNER":
			return { width: 320, height: 100 };
		case "LEADERBOARD":
			return { width: 728, height: 90 };
		case "MEDIUM_RECTANGLE":
			return { width: 300, height: 250 };
		case "WIDE_SKYSCRAPER":
			return { width: 160, height: 600 };
		case "ADAPTIVE_BANNER":
		case "ANCHORED_ADAPTIVE_BANNER":
			return { width: "100%", height: 50 };
		case "INLINE_ADAPTIVE_BANNER":
			return { width: "100%", height: 100 };
		default:
			return { width: 320, height: 50 };
	}
};

type BannerAdProps = {
	size?: string;
	unitId?: string;
	onAdLoaded?: () => void;
	onAdFailedToLoad?: (error: unknown) => void;
	onAdOpened?: () => void;
	onAdClosed?: () => void;
};

const BannerPlaceholder = ({
	size,
	label,
}: { size?: string; label: string }) => {
	const dims = getBannerStyle(size);
	return (
		<View
			style={{
				...dims,
				backgroundColor: PLACEHOLDER_BG,
				borderWidth: 1,
				borderColor: PLACEHOLDER_BORDER,
				borderRadius: 4,
				alignItems: "center",
				justifyContent: "center",
				flexDirection: "row",
				gap: 6,
			}}
		>
			<AdLabel />
			<Text style={{ color: PLACEHOLDER_TEXT, fontSize: 12 }}>{label}</Text>
		</View>
	);
};

export const BannerAd = ({ size }: BannerAdProps) => (
	<BannerPlaceholder size={size} label="Banner Ad" />
);

export const GAMBannerAd = ({ size }: BannerAdProps) => (
	<BannerPlaceholder size={size} label="Ad Manager Banner" />
);

type NativeAdViewProps = {
	children?: React.ReactNode;
	nativeAd?: unknown;
	style?: ViewStyle | ViewStyle[];
};

const DefaultNativeAdContent = () => (
	<View>
		<View
			style={{ flexDirection: "row", alignItems: "center", marginBottom: 10 }}
		>
			<View
				style={{
					width: 40,
					height: 40,
					borderRadius: 8,
					backgroundColor: PLACEHOLDER_BORDER,
					marginRight: 10,
				}}
			/>
			<View style={{ flex: 1 }}>
				<View
					style={{
						height: 12,
						backgroundColor: PLACEHOLDER_BORDER,
						borderRadius: 4,
						marginBottom: 6,
						width: "70%",
					}}
				/>
				<View
					style={{
						height: 10,
						backgroundColor: "#ececec",
						borderRadius: 4,
						width: "40%",
					}}
				/>
			</View>
		</View>
		<View
			style={{
				height: 140,
				backgroundColor: PLACEHOLDER_BORDER,
				borderRadius: 4,
				marginBottom: 10,
				alignItems: "center",
				justifyContent: "center",
			}}
		>
			<Text style={{ color: PLACEHOLDER_TEXT, fontSize: 12 }}>
				Native Ad Media
			</Text>
		</View>
		<View
			style={{
				height: 10,
				backgroundColor: "#ececec",
				borderRadius: 4,
				marginBottom: 6,
			}}
		/>
		<View
			style={{
				height: 10,
				backgroundColor: "#ececec",
				borderRadius: 4,
				width: "80%",
				marginBottom: 12,
			}}
		/>
		<View
			style={{
				alignSelf: "flex-start",
				backgroundColor: "#1a73e8",
				paddingHorizontal: 14,
				paddingVertical: 8,
				borderRadius: 4,
			}}
		>
			<Text style={{ color: "#fff", fontSize: 12, fontWeight: "600" }}>
				Install
			</Text>
		</View>
	</View>
);

export const NativeAdView = ({ children, style }: NativeAdViewProps) => (
	<View
		style={[
			{
				backgroundColor: PLACEHOLDER_BG,
				borderWidth: 1,
				borderColor: PLACEHOLDER_BORDER,
				borderRadius: 8,
				padding: 12,
				position: "relative",
			},
			style as ViewStyle,
		]}
	>
		<View style={{ position: "absolute", top: 8, right: 8, zIndex: 1 }}>
			<AdLabel />
		</View>
		{children ?? <DefaultNativeAdContent />}
	</View>
);

export const NativeAsset = ({
	children,
	style,
}: {
	children?: React.ReactNode;
	assetType?: string;
	style?: ViewStyle | ViewStyle[];
}) => <View style={style as ViewStyle}>{children}</View>;

export const NativeMediaView = ({
	style,
}: { style?: ViewStyle | ViewStyle[] }) => (
	<View
		style={[
			{
				height: 180,
				backgroundColor: PLACEHOLDER_BORDER,
				borderRadius: 4,
				alignItems: "center",
				justifyContent: "center",
			},
			style as ViewStyle,
		]}
	>
		<Text style={{ color: PLACEHOLDER_TEXT, fontSize: 12 }}>
			Ad Media (native only)
		</Text>
	</View>
);

export const NativeAd = {
	createForAdRequest: async (_unitId?: string, _requestOptions?: unknown) => ({
		headline: "Sample Ad Headline",
		body: "Native ads only render on a real device.",
		advertiser: "Sample Advertiser",
		callToAction: "Install",
		icon: null,
		images: [],
		starRating: null,
		store: null,
		price: null,
		addAdEventListener: () => () => {},
		removeAllListeners: () => {},
		destroy: () => {},
	}),
};

const createFullScreenAdStub = () => ({
	loaded: false,
	load: () => {},
	show: () => Promise.resolve(),
	addAdEventListener: () => () => {},
	addAdEventsListener: () => () => {},
	removeAllListeners: () => {},
});

export const InterstitialAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const RewardedAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const RewardedInterstitialAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const AppOpenAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const GAMInterstitialAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const GAMRewardedAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

export const GAMRewardedInterstitialAd = {
	createForAdRequest: () => createFullScreenAdStub(),
};

const baseHookResult = {
	isLoaded: false,
	isOpened: false,
	isClicked: false,
	isClosed: false,
	error: null as unknown,
	load: () => {},
	show: () => {},
};

export const useInterstitialAd = () => ({ ...baseHookResult });
export const useAppOpenAd = () => ({ ...baseHookResult });
export const useRewardedAd = () => ({
	...baseHookResult,
	isEarnedReward: false,
	reward: null,
});
export const useRewardedInterstitialAd = () => ({
	...baseHookResult,
	isEarnedReward: false,
	reward: null,
});

export const AdsConsent = {
	requestInfoUpdate: async () => ({
		status: AdsConsentStatus.NOT_REQUIRED,
		isConsentFormAvailable: false,
	}),
	showForm: async () => ({ status: AdsConsentStatus.OBTAINED }),
	loadAndShowConsentFormIfRequired: async () => ({
		status: AdsConsentStatus.NOT_REQUIRED,
	}),
	gatherConsent: async () => ({ status: AdsConsentStatus.NOT_REQUIRED }),
	reset: () => {},
	getConsentInfo: async () => ({
		status: AdsConsentStatus.NOT_REQUIRED,
		canRequestAds: true,
		isConsentFormAvailable: false,
		privacyOptionsRequirementStatus: "NOT_REQUIRED",
	}),
	getUserChoices: async () => ({}),
	getTCString: async () => "",
	getGdprApplies: async () => false,
	getPurposeConsents: async () => "",
	getPurposeLegitimateInterests: async () => "",
};

const mobileAdsInstance = {
	initialize: async () => [],
	setRequestConfiguration: async () => {},
	openAdInspector: async () => {},
	openDebugMenu: () => {},
	setAppMuted: () => {},
	setAppVolume: () => {},
};

const mobileAds = () => mobileAdsInstance;

const defaultExport = Object.assign(mobileAds, {
	BannerAd,
	GAMBannerAd,
	BannerAdSize,
	InterstitialAd,
	RewardedAd,
	RewardedInterstitialAd,
	AppOpenAd,
	GAMInterstitialAd,
	GAMRewardedAd,
	GAMRewardedInterstitialAd,
	NativeAd,
	NativeAdView,
	NativeAsset,
	NativeMediaView,
	AdEventType,
	RewardedAdEventType,
	AdsConsent,
	AdsConsentStatus,
	AdsConsentDebugGeography,
	TestIds,
});

export { mobileAds };
export default defaultExport;
