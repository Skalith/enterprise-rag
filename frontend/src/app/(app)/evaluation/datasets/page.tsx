"use client";

import Link from "next/link";
import { BookOpenCheck, Play } from "lucide-react";
import { useEvalDatasets } from "@/lib/api/queries";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

export default function DatasetsPage() {
  const ds = useEvalDatasets();
  return (
    <>
      <PageHeader title="Evaluation datasets" description="Question sets used to measure retrieval and answer quality against the documents you can access." />
      {ds.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1].map((i) => <Skeleton key={i} className="h-28" />)}</div>
      ) : ds.isError ? (
        <Card><ErrorState error={ds.error} onRetry={() => ds.refetch()} /></Card>
      ) : (ds.data?.datasets ?? []).length === 0 ? (
        <Card><EmptyState icon={<BookOpenCheck className="h-5 w-5" />} title="No datasets available" description="The backend did not report any evaluation datasets." /></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ds.data!.datasets.map((name) => (
            <Card key={name} className="flex flex-col p-5">
              <BookOpenCheck className="h-5 w-5 text-accent" />
              <h2 className="mt-3 text-[15px] font-semibold text-ink">{name}</h2>
              <p className="mt-1 flex-1 text-[13px] text-muted">The API lists dataset names only; its questions are defined on the backend.</p>
              <Button asChild variant="secondary" size="sm" className="mt-4 self-start">
                <Link href={`/evaluation/runs?dataset=${encodeURIComponent(name)}`}><Play className="h-3.5 w-3.5" /> Run this dataset</Link>
              </Button>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
