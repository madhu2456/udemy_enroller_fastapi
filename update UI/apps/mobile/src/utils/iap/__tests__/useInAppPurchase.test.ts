/**
 * Tests for the useInAppPurchase logic functions.
 *
 * These verify:
 * 1. Original behavior from the inlined documentation.ts code is preserved
 *    (SDK configuration, offerings loading, subscription status, purchasing)
 * 2. Bug fixes over the old inline code:
 *    - Offerings are awaited before isReady is set (was fire-and-forget)
 *    - Retry logic handles TestFlight cold-start failures
 *    - getAvailablePackages returns [] instead of throwing on null offerings
 *    - Purchases.configure() is only called once
 *    - restorePurchases is included (App Store Guideline 3.1.1)
 */

import {
  mockConfigure,
  mockSetLogLevel,
  mockGetOfferings,
  mockPurchasePackage,
  mockRestorePurchases,
} from './__mocks__/react-native-purchases';
import {
  getRevenueCatAPIKey,
  loadOfferings,
  fetchSubscriptionStatus,
  initiatePurchases,
  getAvailablePackagesFromOfferings,
  getSubscriptionsFromOfferings,
  executePurchase,
  executeRestore,
} from '../useInAppPurchase';

// --- Helpers ---

const makeOfferings = (hasCurrent = true) => ({
  current: hasCurrent
    ? {
        availablePackages: [
          {
            identifier: 'lifetime',
            product: {
              priceString: '$1.99',
              productCategory: 'SUBSCRIPTION',
            },
          },
          {
            identifier: 'credits',
            product: {
              priceString: '$4.99',
              productCategory: 'NON_SUBSCRIPTION',
            },
          },
        ],
      }
    : null,
});

function makeStoreCallbacks() {
  return {
    setOfferings: jest.fn(),
    setIsSubscribed: jest.fn(),
    setIsReady: jest.fn(),
    isConfigured: { current: false },
  };
}

// --- Setup ---

beforeEach(() => {
  jest.clearAllMocks();
  jest.useFakeTimers();
  process.env.EXPO_PUBLIC_CREATE_ENV = 'PRODUCTION';
  process.env.EXPO_PUBLIC_REVENUE_CAT_APP_STORE_API_KEY = 'pk_ios_test';
  process.env.EXPO_PUBLIC_REVENUE_CAT_PLAY_STORE_API_KEY = 'pk_android_test';
  process.env.EXPO_PUBLIC_REVENUE_CAT_TEST_STORE_API_KEY = 'pk_test_test';
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: () => Promise.resolve({ hasAccess: false }),
  });
});

afterEach(() => {
  jest.useRealTimers();
});

// --- Tests ---

describe('getRevenueCatAPIKey', () => {
  test('returns iOS key in production', () => {
    expect(getRevenueCatAPIKey()).toBe('pk_ios_test');
  });

  test('returns test store key in DEVELOPMENT', () => {
    process.env.EXPO_PUBLIC_CREATE_ENV = 'DEVELOPMENT';
    expect(getRevenueCatAPIKey()).toBe('pk_test_test');
  });

  test('returns undefined when no keys are set', () => {
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_APP_STORE_API_KEY;
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_PLAY_STORE_API_KEY;
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_TEST_STORE_API_KEY;
    expect(getRevenueCatAPIKey()).toBeUndefined();
  });
});

describe('initiatePurchases', () => {
  test('configures SDK with correct API key', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings());
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    expect(mockConfigure).toHaveBeenCalledWith({ apiKey: 'pk_ios_test' });
  });

  test('sets log level to INFO', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings());
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    expect(mockSetLogLevel).toHaveBeenCalledWith('INFO');
  });

  test('loads offerings and fetches subscription status in parallel', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings());
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    expect(cbs.setOfferings).toHaveBeenCalledWith(makeOfferings());
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/revenue-cat/get-subscription-status',
      { method: 'POST' }
    );
  });

  test('sets isReady true after completion', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings());
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    expect(cbs.setIsReady).toHaveBeenCalledWith(true);
  });

  test('does not configure when no API key is available', async () => {
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_APP_STORE_API_KEY;
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_PLAY_STORE_API_KEY;
    delete process.env.EXPO_PUBLIC_REVENUE_CAT_TEST_STORE_API_KEY;
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    expect(mockConfigure).not.toHaveBeenCalled();
    expect(cbs.setIsReady).toHaveBeenCalledWith(true);
  });

  test('BUG FIX: isReady only set AFTER offerings have loaded (was fire-and-forget)', async () => {
    let resolveOfferings!: Function;
    mockGetOfferings.mockImplementation(
      () => new Promise((resolve) => { resolveOfferings = () => resolve(makeOfferings()); })
    );
    const cbs = makeStoreCallbacks();
    const promise = initiatePurchases(cbs);

    // Before offerings resolve, setIsReady should NOT have been called
    expect(cbs.setIsReady).not.toHaveBeenCalled();

    resolveOfferings();
    await promise;

    // Now it should be called
    expect(cbs.setIsReady).toHaveBeenCalledWith(true);
    expect(cbs.setOfferings).toHaveBeenCalled();
  });

  test('BUG FIX: configure() only called once even if initiate() called multiple times', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings());
    const cbs = makeStoreCallbacks();
    await initiatePurchases(cbs);
    await initiatePurchases(cbs);
    await initiatePurchases(cbs);
    expect(mockConfigure).toHaveBeenCalledTimes(1);
  });
});

describe('loadOfferings', () => {
  test('stores offerings on success', async () => {
    const offerings = makeOfferings();
    mockGetOfferings.mockResolvedValue(offerings);
    const setOfferings = jest.fn();
    await loadOfferings(setOfferings);
    expect(setOfferings).toHaveBeenCalledWith(offerings);
  });

  test('BUG FIX: retries up to 3 times on failure', async () => {
    mockGetOfferings
      .mockRejectedValueOnce(new Error('cold start'))
      .mockRejectedValueOnce(new Error('still loading'))
      .mockResolvedValueOnce(makeOfferings());
    const setOfferings = jest.fn();

    const promise = loadOfferings(setOfferings);
    await jest.advanceTimersByTimeAsync(1500);
    await jest.advanceTimersByTimeAsync(1500);
    await promise;

    expect(mockGetOfferings).toHaveBeenCalledTimes(3);
    expect(setOfferings).toHaveBeenCalledWith(makeOfferings());
  });

  test('BUG FIX: retries when offerings load but current is null', async () => {
    mockGetOfferings
      .mockResolvedValueOnce(makeOfferings(false))
      .mockResolvedValueOnce(makeOfferings(false))
      .mockResolvedValueOnce(makeOfferings(true));
    const setOfferings = jest.fn();

    const promise = loadOfferings(setOfferings);
    await jest.advanceTimersByTimeAsync(1500);
    await jest.advanceTimersByTimeAsync(1500);
    await promise;

    expect(mockGetOfferings).toHaveBeenCalledTimes(3);
    expect(setOfferings).toHaveBeenCalledWith(makeOfferings(true));
  });

  test('BUG FIX: does not call setOfferings when all retries fail', async () => {
    mockGetOfferings.mockRejectedValue(new Error('permanent failure'));
    const setOfferings = jest.fn();

    const promise = loadOfferings(setOfferings);
    await jest.advanceTimersByTimeAsync(3000);
    await promise;

    expect(mockGetOfferings).toHaveBeenCalledTimes(3);
    expect(setOfferings).not.toHaveBeenCalled();
  });

  test('stops retrying early when current offering is found', async () => {
    mockGetOfferings.mockResolvedValue(makeOfferings(true));
    const setOfferings = jest.fn();

    await loadOfferings(setOfferings);

    expect(mockGetOfferings).toHaveBeenCalledTimes(1);
    expect(setOfferings).toHaveBeenCalledTimes(1);
  });
});

describe('fetchSubscriptionStatus', () => {
  test('sets subscribed true when server returns hasAccess true', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ hasAccess: true }),
    });
    const setIsSubscribed = jest.fn();
    await fetchSubscriptionStatus(setIsSubscribed);
    expect(setIsSubscribed).toHaveBeenCalledWith(true);
  });

  test('sets subscribed false when server returns hasAccess false', async () => {
    const setIsSubscribed = jest.fn();
    await fetchSubscriptionStatus(setIsSubscribed);
    expect(setIsSubscribed).toHaveBeenCalledWith(false);
  });

  test('sets subscribed false on network error', async () => {
    (global.fetch as jest.Mock).mockRejectedValue(new Error('network'));
    const setIsSubscribed = jest.fn();
    await fetchSubscriptionStatus(setIsSubscribed);
    expect(setIsSubscribed).toHaveBeenCalledWith(false);
  });

  test('sets subscribed false on non-ok response', async () => {
    (global.fetch as jest.Mock).mockResolvedValue({ ok: false });
    const setIsSubscribed = jest.fn();
    await fetchSubscriptionStatus(setIsSubscribed);
    expect(setIsSubscribed).toHaveBeenCalledWith(false);
  });
});

describe('getAvailablePackagesFromOfferings', () => {
  test('returns packages from current offering', () => {
    const offerings = makeOfferings();
    const packages = getAvailablePackagesFromOfferings(offerings);
    expect(packages).toHaveLength(2);
    expect(packages[0].identifier).toBe('lifetime');
  });

  test('BUG FIX: returns [] when offerings is null (old code threw)', () => {
    expect(() => getAvailablePackagesFromOfferings(null)).not.toThrow();
    expect(getAvailablePackagesFromOfferings(null)).toEqual([]);
  });

  test('BUG FIX: returns [] when current is null (old code threw)', () => {
    expect(() => getAvailablePackagesFromOfferings(makeOfferings(false))).not.toThrow();
    expect(getAvailablePackagesFromOfferings(makeOfferings(false))).toEqual([]);
  });
});

describe('getSubscriptionsFromOfferings', () => {
  test('filters by SUBSCRIPTION category', () => {
    const subs = getSubscriptionsFromOfferings(makeOfferings());
    expect(subs).toHaveLength(1);
    expect(subs[0].identifier).toBe('lifetime');
  });

  test('BUG FIX: returns [] when offerings is null (old code threw)', () => {
    expect(() => getSubscriptionsFromOfferings(null)).not.toThrow();
    expect(getSubscriptionsFromOfferings(null)).toEqual([]);
  });
});

describe('executePurchase', () => {
  test('calls SDK and returns success with customerInfo', async () => {
    const customerInfo = { entitlements: { active: { pro: {} } } };
    mockPurchasePackage.mockResolvedValue({ customerInfo });
    const result = await executePurchase({
      pkg: { identifier: 'test' },
      setIsSubscribed: jest.fn(),
    });
    expect(mockPurchasePackage).toHaveBeenCalledWith({ identifier: 'test' });
    expect(result.success).toBe(true);
    expect(result.customerInfo).toBe(customerInfo);
  });

  test('returns cancelled when user cancels', async () => {
    mockPurchasePackage.mockRejectedValue({ userCancelled: true });
    const result = await executePurchase({
      pkg: { identifier: 'test' },
      setIsSubscribed: jest.fn(),
    });
    expect(result).toEqual({ success: false, cancelled: true });
  });

  test('returns failure on error', async () => {
    mockPurchasePackage.mockRejectedValue(new Error('payment failed'));
    const result = await executePurchase({
      pkg: { identifier: 'test' },
      setIsSubscribed: jest.fn(),
    });
    expect(result).toEqual({ success: false, cancelled: false });
  });

  test('refreshes subscription status after purchase', async () => {
    mockPurchasePackage.mockResolvedValue({
      customerInfo: { entitlements: { active: {} } },
    });
    const setIsSubscribed = jest.fn();
    await executePurchase({ pkg: { identifier: 'test' }, setIsSubscribed });
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/revenue-cat/get-subscription-status',
      { method: 'POST' }
    );
  });
});

describe('executeRestore', () => {
  test('BUG FIX: restorePurchases works (App Store Guideline 3.1.1)', async () => {
    const customerInfo = { entitlements: { active: { premium: {} } } };
    mockRestorePurchases.mockResolvedValue(customerInfo);
    const result = await executeRestore(jest.fn());
    expect(mockRestorePurchases).toHaveBeenCalled();
    expect(result.success).toBe(true);
    expect(result.customerInfo).toBe(customerInfo);
  });

  test('returns success false when no active entitlements', async () => {
    mockRestorePurchases.mockResolvedValue({ entitlements: { active: {} } });
    const result = await executeRestore(jest.fn());
    expect(result.success).toBe(false);
  });

  test('handles errors gracefully', async () => {
    mockRestorePurchases.mockRejectedValue(new Error('network error'));
    const result = await executeRestore(jest.fn());
    expect(result).toEqual({ success: false });
  });

  test('refreshes subscription status after restore', async () => {
    mockRestorePurchases.mockResolvedValue({
      entitlements: { active: { pro: {} } },
    });
    await executeRestore(jest.fn());
    expect(global.fetch).toHaveBeenCalledWith(
      '/api/revenue-cat/get-subscription-status',
      { method: 'POST' }
    );
  });
});
