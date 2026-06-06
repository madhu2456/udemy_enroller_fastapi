import { create } from 'zustand';

interface InAppPurchaseState {
	isReady: boolean;
	offerings: any | null;
	isSubscribed: boolean;
	setIsSubscribed: (isSubscribed: boolean) => void;
	setOfferings: (offerings: any | null) => void;
	setIsReady: (isReady: boolean) => void;
}

export const useInAppPurchaseStore = create<InAppPurchaseState>((set) => ({
  isReady: false,
  offerings: null,
  isSubscribed: false,
  setIsSubscribed: (isSubscribed) => set({ isSubscribed }),
  setOfferings: (offerings) => set({ offerings }),
  setIsReady: (isReady) => set({ isReady }),
}));
