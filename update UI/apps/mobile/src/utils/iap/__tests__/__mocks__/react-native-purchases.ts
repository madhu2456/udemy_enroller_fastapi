export const mockConfigure = jest.fn();
export const mockSetLogLevel = jest.fn();
export const mockGetOfferings = jest.fn();
export const mockPurchasePackage = jest.fn();
export const mockRestorePurchases = jest.fn();

const Purchases = {
  configure: (...args: any[]) => mockConfigure(...args),
  setLogLevel: (...args: any[]) => mockSetLogLevel(...args),
  getOfferings: (...args: any[]) => mockGetOfferings(...args),
  purchasePackage: (...args: any[]) => mockPurchasePackage(...args),
  restorePurchases: (...args: any[]) => mockRestorePurchases(...args),
};

export default Purchases;
export const LOG_LEVEL = { INFO: 'INFO' };
export const PRODUCT_CATEGORY = { SUBSCRIPTION: 'SUBSCRIPTION' };
