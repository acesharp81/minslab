import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  Outlet,
  Link,
  createRootRouteWithContext,
  useRouter,
} from "@tanstack/react-router";
import { useEffect } from "react";
import { Toaster } from "sonner";
import { supabase } from "@/integrations/supabase/client";

function NotFoundComponent() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <section className="paper-card max-w-md p-8 text-center">
        <span className="section-kicker">404 · NOT FOUND</span>
        <h1 className="mt-3 text-3xl font-bold">요청한 화면을 찾지 못했습니다.</h1>
        <p className="mt-3 text-sm text-muted-foreground">주소를 확인하거나 업무 현황으로 돌아가 주세요.</p>
        <Link to="/" className="app-primary-link mt-6">업무 현황으로</Link>
      </section>
    </main>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <section className="paper-card max-w-md p-8 text-center">
        <span className="section-kicker">APPLICATION ERROR</span>
        <h1 className="mt-3 text-2xl font-bold">화면을 불러오지 못했습니다.</h1>
        <p className="mt-3 break-words text-sm text-muted-foreground">{error.message}</p>
        <button
          type="button"
          className="app-primary-link mt-6"
          onClick={() => {
            router.invalidate();
            reset();
          }}
        >
          다시 시도
        </button>
      </section>
    </main>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: RootComponent,
  notFoundComponent: NotFoundComponent,
  errorComponent: ErrorComponent,
});

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const router = useRouter();

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(() => {
      router.invalidate();
      queryClient.invalidateQueries();
    });
    return () => subscription.unsubscribe();
  }, [router, queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      <div className="kms-app"><Outlet /></div>
      <Toaster richColors position="top-center" />
    </QueryClientProvider>
  );
}
