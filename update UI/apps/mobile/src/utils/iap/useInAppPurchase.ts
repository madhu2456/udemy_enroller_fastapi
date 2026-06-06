import Purchases, { LOG_LEVEL, PRODUCT_CATEGORY } from 'react-native-purchases';
import { Platform } from 'react-native';
import { useCallback, useRef, useState } from 'react';
import { useInAppPurchaseStore } from './store';

export const RETRY_ATTEMPTS = 3;
export const RETRY_DELAY_MS = 1500;

export const getRevenueCatAPIKey = (): string | undefined => {
  if (process.env.EXPO_PUBLIC_CREATE_ENV === 'DEVELOPMENT') {
    return process.env.EXPO_PUBLIC_REVENUE_CAT_TEST_STORE_API_KEY;
  }
  return Platform.select({
    ios: process.env.EXPO_PUBLIC_REVENUE_CAT_APP_STORE_API_KEY,
    android: process.env.EXPO_PUBLIC_REVENUE_CAT_PLAY_STORE_API_KEY,
    web: process.env.EXPO_PUBLIC_REVENUE_CAT_TEST_STORE_API_KEY,
  });
};

export async function loadOfferings(setOfferings: (o: any) => void) {
  for (let attempt = 0; attempt < RETRY_ATTEMPTS; attempt++) {
    try {
      const result = await Purchases.getOfferings();
      if (result?.current) {
        setOfferings(result);
        return;
      }
      console.warn(
        `RevenueCat offerings loaded but no current offering (attempt ${attempt + 1}/${RETRY_ATTEMPTS})`
      );
    } catch (error) {
      console.warn(
        `Failed to load offerings (attempt ${attempt + 1}/${RETRY_ATTEMPTS}):`,
        error
      );
    }
    if (attempt < RETRY_ATTEMPTS - 1) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAY_MS));
    }
  }
}

export async function fetchSubscriptionStatus(
  setIsSubscribed: (v: boolean) => void
) {
  try {
    const response = await fetch('/api/revenue-cat/get-subscription-status', {
      method: 'POST',
    });
    if (!response.ok) {
      throw new Error('Failed to check subscription status');
    }
    const data = await response.json();
    setIsSubscribed(data.hasAccess);
  } catch (error) {
    console.error('Error fetching subscription status:', error);
    setIsSubscribed(false);
  }
}

export async function initiatePurchases({
  isConfigured,
  setIsReady,
  setOfferings,
  setIsSubscribed,
}: {
  isConfigured: { current: boolean };
  setIsReady: (v: boolean) => void;
  setOfferings: (o: any) => void;
  setIsSubscribed: (v: boolean) => void;
}) {
  if (isConfigured.current) return;
  try {
    void Purchases.setLogLevel(LOG_LEVEL.INFO);
    const apiKey = getRevenueCatAPIKey();
    if (apiKey) {
      Purchases.configure({ apiKey });
      isConfigured.current = true;
      await Promise.allSettled([
        loadOfferings(setOfferings),
        fetchSubscriptionStatus(setIsSubscribed),
      ]);
    } else {
      console.warn('No RevenueCat API key found for platform:', Platform.OS);
    }
  } catch (error) {
    console.warn('Failed to initialize RevenueCat:', error);
  } finally {
    setIsReady(true);
  }
}

export function getAvailablePackagesFromOfferings(offerings: any) {
  const offering = offerings?.current;
  if (!offering) {
    return [];
  }
  return offering.availablePackages;
}

export function getSubscriptionsFromOfferings(offerings: any) {
  return getAvailablePackagesFromOfferings(offerings).filter(
    (pkg: any) =>
      pkg.product.productCategory === PRODUCT_CATEGORY.SUBSCRIPTION
  );
}

export async function executePurchase({
  pkg,
  setIsSubscribed,
}: {
  pkg: any;
  setIsSubscribed: (v: boolean) => void;
}) {
  try {
    const { customerInfo } = await Purchases.purchasePackage(pkg);
    await fetchSubscriptionStatus(setIsSubscribed);
    return { success: true, customerInfo };
  } catch (error: any) {
    if (error.userCancelled) {
      return { success: false, cancelled: true };
    }
    console.error('Failed to purchase:', error);
    return { success: false, cancelled: false };
  }
}

export async function executeRestore(
  setIsSubscribed: (v: boolean) => void
) {
  try {
    const customerInfo = await Purchases.restorePurchases();
    await fetchSubscriptionStatus(setIsSubscribed);
    return {
      success: Object.keys(customerInfo.entitlements.active).length > 0,
      customerInfo,
    };
  } catch (error) {
    console.error('Failed to restore purchases:', error);
    return { success: false };
  }
}

export function useInAppPurchase() {
  const {
    isReady,
    offerings,
    setOfferings,
    setIsSubscribed,
    isSubscribed,
    setIsReady,
  } = useInAppPurchaseStore();
  const [isPurchasing, setIsPurchasing] = useState(false);
  const isConfigured = useRef(false);

  const initiate = useCallback(
    () =>
      initiatePurchases({
        isConfigured,
        setIsReady,
        setOfferings,
        setIsSubscribed,
      }),
    [setIsReady, setOfferings, setIsSubscribed]
  );

  const getAvailablePackages = useCallback(
    () => getAvailablePackagesFromOfferings(offerings),
    [offerings]
  );

  const getAvailableSubscriptions = useCallback(
    () => getSubscriptionsFromOfferings(offerings),
    [offerings]
  );

  const purchasePackage = useCallback(
    async ({ pkg }: { pkg: any }) => {
      setIsPurchasing(true);
      try {
        return await executePurchase({ pkg, setIsSubscribed });
      } finally {
        setIsPurchasing(false);
      }
    },
    [setIsPurchasing, setIsSubscribed]
  );

  const restorePurchases = useCallback(async () => {
    setIsPurchasing(true);
    try {
      return await executeRestore(setIsSubscribed);
    } finally {
      setIsPurchasing(false);
    }
  }, [setIsPurchasing, setIsSubscribed]);

  return {
    isReady,
    offerings,
    isSubscribed,
    isPurchasing,
    initiate,
    getAvailablePackages,
    getAvailableSubscriptions,
    purchasePackage,
    restorePurchases,
  };
}

export default useInAppPurchase;
