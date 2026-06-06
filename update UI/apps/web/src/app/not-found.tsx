'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

interface ParentSitemap {
  webPages?: Array<{
    id: string;
    name: string;
    filePath: string;
    cleanRoute?: string;
  }>;
}

export default function NotFound() {
  const [siteMap, setSitemap] = useState<ParentSitemap | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const missingPath = pathname.replace(/^\//, '');

  useEffect(() => {
    if (
      typeof window === 'undefined' ||
      !window.parent ||
      window.parent === window
    ) {
      return;
    }

    const handler = (event: MessageEvent) => {
      if (event.data.type === 'sandbox:sitemap') {
        window.removeEventListener('message', handler);
        setSitemap(event.data.sitemap);
      }
    };

    window.parent.postMessage({ type: 'sandbox:sitemap' }, '*');
    window.addEventListener('message', handler);

    return () => {
      window.removeEventListener('message', handler);
    };
  }, []);

  const handleNavigate = (path: string) => {
    router.push(siteMap ? path : `/${path}`);
  };

  const handleCreatePage = useCallback(() => {
    window.parent.postMessage(
      {
        type: 'sandbox:web:create',
        path: missingPath,
        view: 'web',
      },
      '*'
    );
  }, [missingPath]);

  return (
    <div className="flex sm:w-full w-screen sm:min-w-[850px] flex-col">
      <div className="flex w-full items-center gap-2 p-5">
        <button
          type="button"
          onClick={() => router.push('/')}
          className="flex items-center justify-center w-10 h-10 rounded-md"
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 18 18"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            aria-label="Back"
            role="img"
          >
            <path
              d="M8.5957 2.65435L2.25005 9L8.5957 15.3457"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M2.25007 9L15.75 9"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <div className="flex flex-row divide-x divide-gray-200 rounded-[8px] h-8 w-[300px] border border-gray-200 bg-gray-50 text-gray-500">
          <div className="flex items-center px-[14px] py-[5px]">
            <span>/</span>
          </div>
          <div className="flex items-center min-w-0">
            <p
              className="border-0 bg-transparent px-3 py-2 focus:outline-none truncate max-w-[300px]"
              style={{ minWidth: 0 }}
              title={missingPath}
            >
              {missingPath}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-grow flex-col items-center justify-center pt-[100px] text-center gap-[20px]">
        <h1 className="text-4xl font-medium text-gray-900 px-2">
          Uh-oh! This page doesn&apos;t exist (yet).
        </h1>

        <p className="pt-4 pb-12 px-2 text-gray-500">
          Looks like &quot;<span className="font-bold">/{missingPath}</span>
          &quot; isn&apos;t part of your project. But no worries, you&apos;ve
          got options!
        </p>

        <div className="px-[20px] w-full">
          <div className="flex flex-row justify-center items-center w-full max-w-[800px] mx-auto border border-gray-200 rounded-lg p-[20px] mb-[40px] gap-[20px]">
            <div className="flex flex-col gap-[5px] items-start self-start w-1/2">
              <p className="text-sm text-black text-left">
                Build it from scratch
              </p>
              <p className="text-sm text-gray-500 text-left">
                Create a new page to live at &quot;
                <span>/{missingPath}</span>&quot;
              </p>
            </div>
            <div className="flex flex-row items-center justify-end w-1/2">
              <button
                type="button"
                className="bg-black text-white px-[10px] py-[5px] rounded-md"
                onClick={handleCreatePage}
              >
                Create Page
              </button>
            </div>
          </div>
        </div>

        {siteMap?.webPages && siteMap.webPages.length > 0 && (
          <>
            <div className="pb-20 lg:pb-[80px]">
              <p className="flex items-center text-gray-500">
                Check out all your project&apos;s routes here &darr;
              </p>
            </div>

            <div className="flex flex-col justify-center items-center w-full px-[50px]">
              <div className="flex flex-col justify-between items-center w-full max-w-[600px] gap-[10px]">
                <p className="text-sm text-gray-300 pb-[10px] self-start p-4">
                  PAGES
                </p>
                {siteMap.webPages.map((route) => (
                  <button
                    type="button"
                    onClick={() => handleNavigate(route.cleanRoute || '')}
                    key={route.id}
                    className="flex flex-row justify-between text-center items-center p-4 rounded-lg bg-white shadow-sm w-full hover:bg-gray-50"
                  >
                    <h3 className="font-medium text-gray-900">{route.name}</h3>
                    <p className="text-sm text-gray-400">{route.cleanRoute}</p>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
