// Expo Go-safe stub for react-native-purchases.
//
// The real package's index pulls in @revenuecat/purchases-js-hybrid-mappings
// (a ~15k-line Svelte UMD bundle of browser-only code) which throws on
// module evaluation under Hermes in Expo Go preview. Even importing it from
// a hook that's never called crashes _layout.tsx, which makes expo-router
// silently swallow the throw and warn "Route \"./_layout.tsx\" is missing
// the required default export" — leaving the app stuck on a black/splash
// screen forever.
//
// This polyfill is wired up in metro.config.js for native platforms only
// when EXPO_PUBLIC_CREATE_ENV !== 'PRODUCTION'. Production EAS builds keep
// the real SDK, so paid users hit RevenueCat as normal.

const noopAsync = async () => undefined;

const LOG_LEVEL = {
	VERBOSE: "VERBOSE",
	DEBUG: "DEBUG",
	INFO: "INFO",
	WARN: "WARN",
	ERROR: "ERROR",
	SILENT: "SILENT",
};

const PRODUCT_CATEGORY = {
	SUBSCRIPTION: "SUBSCRIPTION",
	NON_SUBSCRIPTION: "NON_SUBSCRIPTION",
	UNKNOWN: "UNKNOWN",
};

const PURCHASE_TYPE = {
	INAPP: "inapp",
	SUBS: "subs",
};

const PURCHASES_ARE_COMPLETED_BY_TYPE = {
	REVENUECAT: "REVENUECAT",
	MY_APP: "MY_APP",
};

const REFUND_REQUEST_STATUS = {
	SUCCESS: "SUCCESS",
	USER_CANCELLED: "USER_CANCELLED",
	ERROR: "ERROR",
};

const BILLING_FEATURE = {
	SUBSCRIPTIONS: "SUBSCRIPTIONS",
	SUBSCRIPTIONS_UPDATE: "SUBSCRIPTIONS_UPDATE",
	IN_APP_MESSAGING: "IN_APP_MESSAGING",
	PRICE_CHANGE_CONFIRMATION: "PRICE_CHANGE_CONFIRMATION",
};

const STOREKIT_VERSION = {
	DEFAULT: "DEFAULT",
	STOREKIT_1: "STOREKIT_1",
	STOREKIT_2: "STOREKIT_2",
};

const Purchases = {
	configure: noopAsync,
	setLogLevel: () => {},
	setLogHandler: () => {},
	addCustomerInfoUpdateListener: () => () => {},
	removeCustomerInfoUpdateListener: () => {},
	getOfferings: async () => ({ current: null, all: {} }),
	getProducts: async () => [],
	getCustomerInfo: async () => ({
		entitlements: { active: {}, all: {} },
		activeSubscriptions: [],
		allPurchasedProductIdentifiers: [],
		latestExpirationDate: null,
		firstSeen: new Date().toISOString(),
		originalAppUserId: "expo-go-preview",
		requestDate: new Date().toISOString(),
		allExpirationDates: {},
		allPurchaseDates: {},
		originalApplicationVersion: null,
		originalPurchaseDate: null,
		managementURL: null,
		nonSubscriptionTransactions: [],
	}),
	purchasePackage: async () => {
		const error: Error & { userCancelled?: boolean } = new Error(
			"Purchases not available in Expo Go preview. Build a development build or run in TestFlight to test purchases.",
		);
		error.userCancelled = true;
		throw error;
	},
	purchaseProduct: async () => {
		const error: Error & { userCancelled?: boolean } = new Error(
			"Purchases not available in Expo Go preview.",
		);
		error.userCancelled = true;
		throw error;
	},
	restorePurchases: async () => ({
		entitlements: { active: {}, all: {} },
		activeSubscriptions: [],
		allPurchasedProductIdentifiers: [],
		latestExpirationDate: null,
		firstSeen: new Date().toISOString(),
		originalAppUserId: "expo-go-preview",
		requestDate: new Date().toISOString(),
		allExpirationDates: {},
		allPurchaseDates: {},
		originalApplicationVersion: null,
		originalPurchaseDate: null,
		managementURL: null,
		nonSubscriptionTransactions: [],
	}),
	logIn: async (appUserID: string) => ({
		customerInfo: {
			entitlements: { active: {}, all: {} },
			activeSubscriptions: [],
			originalAppUserId: appUserID,
		},
		created: false,
	}),
	logOut: async () => ({
		entitlements: { active: {}, all: {} },
		activeSubscriptions: [],
		originalAppUserId: "expo-go-preview",
	}),
	setAttributes: noopAsync,
	setEmail: noopAsync,
	setDisplayName: noopAsync,
	setPhoneNumber: noopAsync,
	setPushToken: noopAsync,
	setAdjustID: noopAsync,
	setAppsflyerID: noopAsync,
	setFBAnonymousID: noopAsync,
	setMparticleID: noopAsync,
	setOnesignalID: noopAsync,
	setAirshipChannelID: noopAsync,
	setMediaSource: noopAsync,
	setCampaign: noopAsync,
	setAdGroup: noopAsync,
	setAd: noopAsync,
	setKeyword: noopAsync,
	setCreative: noopAsync,
	collectDeviceIdentifiers: () => {},
	syncPurchases: noopAsync,
	syncAttributesAndOfferingsIfNeeded: async () => ({ current: null, all: {} }),
	enableAdServicesAttributionTokenCollection: () => {},
	isAnonymous: async () => true,
	checkTrialOrIntroductoryPriceEligibility: async () => ({}),
	invalidateCustomerInfoCache: () => {},
	presentCodeRedemptionSheet: () => {},
	beginRefundRequestForActiveEntitlement: async () => REFUND_REQUEST_STATUS.ERROR,
	beginRefundRequestForEntitlement: async () => REFUND_REQUEST_STATUS.ERROR,
	beginRefundRequestForProduct: async () => REFUND_REQUEST_STATUS.ERROR,
	showInAppMessages: noopAsync,
	getPromotionalOffer: async () => null,
	purchasePromotionalOffer: async () => {
		const error: Error & { userCancelled?: boolean } = new Error(
			"Purchases not available in Expo Go preview.",
		);
		error.userCancelled = true;
		throw error;
	},
	canMakePayments: async () => false,
	getAppUserID: async () => "expo-go-preview",
	close: () => {},
	configureInUITestMode: () => {},
};

export {
	LOG_LEVEL,
	PRODUCT_CATEGORY,
	PURCHASE_TYPE,
	PURCHASES_ARE_COMPLETED_BY_TYPE,
	REFUND_REQUEST_STATUS,
	BILLING_FEATURE,
	STOREKIT_VERSION,
};

export default Purchases;
