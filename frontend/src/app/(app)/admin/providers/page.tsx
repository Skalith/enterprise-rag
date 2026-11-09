"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { useLlmConfigs, useProviders } from "@/lib/api/queries";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";

export default function ProvidersPage() {
  const providers = useProviders();
  const configs = useLlmConfigs();
  const active = configs.data?.find((c) => c.is_active);

  return (
    <>
      <PageHeader
        title="Providers"
        description="Live reachability of each LLM provider, checked by the backend. A provider needs its API key set in the backend environment to be healthy."
        actions={
          <>
            <Button variant="secondary" onClick={() => providers.refetch()} loading={providers.isFetching}>
              {!providers.isFetching && <RefreshCw className="h-4 w-4" />} Re-check
            </Button>
            <Button asChild><Link href="/admin/llm-config">Configure model</Link></Button>
          </>
        }
      />
      {providers.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-32" />)}</div>
      ) : providers.isError ? (
        <Card><ErrorState error={providers.error} onRetry={() => providers.refetch()} /></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {providers.data!.map((p) => {
            const isActive = active?.provider === p.name;
            return (
              <Card key={p.name} className="p-5">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="text-[15px] font-semibold capitalize text-ink">{p.name}</h2>
                  <Badge tone={p.healthy ? "success" : "danger"} dot>{p.healthy ? "Reachable" : "Unavailable"}</Badge>
                </div>
                <dl className="mt-4 space-y-2 text-[13px]">
                  <div className="flex justify-between gap-3"><dt className="text-muted">Default model</dt><dd className="truncate font-medium text-ink">{p.default_model ?? "—"}</dd></div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">In use</dt>
                    <dd className="font-medium text-ink">{isActive ? <Badge tone="accent">Active · {active?.model_name}</Badge> : "No"}</dd>
                  </div>
                </dl>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
