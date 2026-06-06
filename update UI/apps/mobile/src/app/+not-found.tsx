import { Ionicons } from '@expo/vector-icons';
import {
  type RelativePathString,
  type SitemapType,
  Stack,
  useGlobalSearchParams,
  useRouter,
  useSitemap,
} from 'expo-router';
import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

interface ParentSitemap {
  expoPages?: Array<{
    id: string;
    name: string;
    filePath: string;
    cleanRoute?: string;
  }>;
}

function NotFoundScreen() {
  const router = useRouter();
  const params = useGlobalSearchParams();
  const expoSitemap = useSitemap();
  const [sitemap, setSitemap] = useState<SitemapType | ParentSitemap | null>(expoSitemap);

  useEffect(() => {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
      const handler = (event: MessageEvent) => {
        if (event.data.type === 'sandbox:sitemap') {
          window.removeEventListener('message', handler);
          setSitemap(event.data.sitemap);
        }
      };

      window.parent.postMessage(
        {
          type: 'sandbox:sitemap',
        },
        '*'
      );
      window.addEventListener('message', handler);

      return () => {
        window.removeEventListener('message', handler);
      };
    }
  }, []);

  const isExpoSitemap = sitemap === expoSitemap;
  const missingPath = params['not-found']?.[0] || '';

  const availableRoutes = useMemo(() => {
    return (
      expoSitemap?.children?.filter(
        (child) =>
          child.href &&
          child.contextKey !== './auth.jsx' &&
          child.contextKey !== './auth.web.jsx' &&
          child.contextKey !== './+not-found.tsx' &&
          child.contextKey !== 'expo-router/build/views/Sitemap.js'
      ) || []
    );
  }, [expoSitemap]);

  const handleBack = () => {
    if (router.canGoBack()) {
      router.back();
    } else {
      const hasTabsIndex = expoSitemap?.children?.some(
        (child) =>
          child.contextKey === './(tabs)/_layout.jsx' &&
          child.children.some((child) => child.contextKey === './(tabs)/index.jsx')
      );
      if (isExpoSitemap) {
        if (hasTabsIndex) {
          router.replace('../(tabs)/index.jsx');
        } else {
          router.replace('../');
        }
      } else {
        router.replace('..');
      }
    }
  };

  const handleNavigate = (url: string) => {
    try {
      if (url) {
        router.push(url as RelativePathString);
      }
    } catch (error) {
      console.error('Navigation error:', error);
    }
  };

  const handleCreatePage = useCallback(() => {
    if (typeof window !== 'undefined' && window.parent && window.parent !== window) {
      window.parent.postMessage(
        {
          type: 'sandbox:web:create',
          path: missingPath,
          view: 'mobile',
        },
        '*'
      );
    }
  }, [missingPath]);
  return (
    <>
      <Stack.Screen options={{ title: 'Page Not Found', headerShown: false }} />
      <SafeAreaView style={styles.safeArea}>
        <ScrollView style={styles.container} contentContainerStyle={styles.contentContainer}>
          <View style={styles.header}>
            <TouchableOpacity onPress={handleBack} style={styles.backButton}>
              <Ionicons name="arrow-back" size={18} color="#666" />
            </TouchableOpacity>
            <View style={styles.pathContainer}>
              <View style={styles.pathPrefix}>
                <Text style={styles.pathPrefixText}>/</Text>
              </View>
              <View style={styles.pathContent}>
                <Text style={styles.pathText} numberOfLines={1}>
                  {missingPath}
                </Text>
              </View>
            </View>
          </View>

          <View style={styles.mainContent}>
            <Text style={styles.title}>Uh-oh! This screen doesn't exist (yet).</Text>

            <Text style={styles.subtitle}>
              Looks like "<Text style={styles.boldText}>/{missingPath}</Text>" isn't part of your
              project. But no worries, you've got options!
            </Text>

            {typeof window !== 'undefined' && window.parent && window.parent !== window && (
              <View style={styles.createPageContainer}>
                <View style={styles.createPageContent}>
                  <View style={styles.createPageTextContainer}>
                    <Text style={styles.createPageTitle}>Build it from scratch</Text>
                    <Text style={styles.createPageDescription}>
                      Create a new screen to live at "/{missingPath}"
                    </Text>
                  </View>
                  <View style={styles.createPageButtonContainer}>
                    <TouchableOpacity
                      onPress={() => handleCreatePage()}
                      style={styles.createPageButton}
                    >
                      <Text style={styles.createPageButtonText}>Create Screen</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            )}

            <Text style={styles.routesLabel}>Check out all your project's routes here ↓</Text>
            {!isExpoSitemap && sitemap ? (
              <View style={styles.pagesContainer}>
                <View style={styles.pagesListContainer}>
                  <Text style={styles.pagesLabel}>MOBILE</Text>
                  {((sitemap as ParentSitemap).expoPages || []).map((route, _index: number) => (
                    <TouchableOpacity
                      key={route.id}
                      onPress={() => handleNavigate(route.cleanRoute || '')}
                      style={styles.pageButton}
                    >
                      <Text style={styles.routeName}>{route.name}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ) : (
              <View style={styles.pagesContainer}>
                <View style={styles.pagesListContainer}>
                  <Text style={styles.pagesLabel}>MOBILE</Text>
                  {(availableRoutes as SitemapType[]).map((route: SitemapType, _index: number) => {
                    const url =
                      typeof route.href === 'string' ? route.href : route.href?.pathname || '/';

                    if (url === '/(tabs)' && route.children) {
                      return route.children.map((childRoute: SitemapType) => {
                        const childUrl =
                          typeof childRoute.href === 'string'
                            ? childRoute.href
                            : childRoute.href.pathname || '/';
                        const displayPath =
                          childUrl === '/(tabs)'
                            ? 'Homepage'
                            : childUrl.replace(/^\//, '').replace(/^\(tabs\)\//, '');
                        return (
                          <TouchableOpacity
                            key={childRoute.contextKey}
                            onPress={() => handleNavigate(childUrl)}
                            style={styles.pageButton}
                          >
                            <Text style={styles.routeName}>{displayPath}</Text>
                          </TouchableOpacity>
                        );
                      });
                    }

                    const displayPath = url === '/' ? 'Homepage' : url.replace(/^\//, '');

                    return (
                      <TouchableOpacity
                        key={route.contextKey}
                        onPress={() => handleNavigate(url)}
                        style={styles.pageButton}
                      >
                        <Text style={styles.routeName}>{displayPath}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#fff',
  },
  container: {
    flex: 1,
    backgroundColor: '#fff',
  },
  contentContainer: {
    flexGrow: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 20,
    gap: 8,
  },
  backButton: {
    width: 40,
    height: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pathContainer: {
    flexDirection: 'row',
    height: 32,
    width: 300,
    borderWidth: 1,
    borderColor: '#e5e5e5',
    borderRadius: 8,
    backgroundColor: '#f9f9f9',
    overflow: 'hidden',
  },
  pathPrefix: {
    paddingHorizontal: 14,
    paddingVertical: 5,
    justifyContent: 'center',
    borderRightWidth: 1,
    borderRightColor: '#e5e5e5',
  },
  pathPrefixText: {
    color: '#666',
  },
  pathContent: {
    flex: 1,
    paddingHorizontal: 12,
    justifyContent: 'center',
  },
  pathText: {
    color: '#666',
  },
  mainContent: {
    flex: 1,
    alignItems: 'center',
    paddingTop: 40,
    paddingHorizontal: 20,
  },
  title: {
    fontSize: 32,
    fontWeight: '500',
    color: '#111',
    marginBottom: 16,
    textAlign: 'center',
  },
  subtitle: {
    paddingTop: 16,
    paddingBottom: 48,
    color: '#666',
    textAlign: 'center',
    fontSize: 16,
    lineHeight: 24,
  },
  boldText: {
    fontWeight: 'bold',
  },
  routesLabel: {
    color: '#666',
    marginBottom: 80,
    textAlign: 'center',
  },
  createPageContainer: {
    width: '100%',
    maxWidth: 800,
    marginBottom: 40,
    paddingHorizontal: 20,
  },
  createPageContent: {
    flexDirection: 'column',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#e5e5e5',
    borderRadius: 8,
    padding: 20,
    backgroundColor: '#fff',
    gap: 15,
  },
  createPageTextContainer: {
    gap: 10,
  },
  createPageTitle: {
    fontSize: 14,
    color: '#000',
    fontWeight: '500',
    textAlign: 'center',
  },
  createPageDescription: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
  },
  createPageButtonContainer: {
    alignItems: 'flex-start',
    justifyContent: 'center',
  },
  createPageButton: {
    backgroundColor: '#000',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 6,
  },
  createPageButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
  },

  pagesContainer: {
    width: '100%',
    alignItems: 'center',
    paddingHorizontal: 20,
  },
  pagesLabel: {
    fontSize: 14,
    color: '#ccc',
    alignSelf: 'flex-start',
    marginBottom: 10,
    paddingHorizontal: 16,
  },
  pagesListContainer: {
    width: '100%',
    maxWidth: 600,
    gap: 10,
  },
  pageButton: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 8,
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#e5e5e5',
    boxShadow: '0px 1px 2px rgba(0, 0, 0, 0.05)',
    elevation: 1,
  },
  routeName: {
    fontSize: 16,
    fontWeight: '500',
    color: '#111',
  },
  routePath: {
    fontSize: 14,
    color: '#999',
  },

  routesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    width: '100%',
    paddingHorizontal: 20,
    paddingBottom: 20,
    gap: 40,
  },
  routeCard: {
    width: '100%',
    maxWidth: 300,
    minWidth: 150,
    alignItems: 'center',
    marginBottom: 12,
  },
  routeButton: {
    width: '100%',
    aspectRatio: 1.4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e5e5e5',
    overflow: 'hidden',
  },
  routePreview: {
    flex: 1,
    backgroundColor: '#f9f9f9',
  },
  routeLabel: {
    paddingTop: 12,
    color: '#666',
    textAlign: 'left',
    width: '100%',
  },
});

export default () => {
  return (
      <NotFoundScreen />
  );
};
