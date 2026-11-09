"use client";

import Link from "next/link";
import { use } from "react";
import { ArrowLeft } from "lucide-react";
import { useEvalRun } from "@/lib/api/queries";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { MetricBar, METRICS, ProxyNote, scoreTone } from "@/components/evaluation/metrics";
import { cn, formatDateTime, formatMs, formatPercent } from "@/lib/utils";

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const run = useEvalRun(Number(id));

  const back = (
    <Button asChild variant="ghost" size="sm" className="mb-3 -ml-2">
      <Link href="/evaluation/runs"><ArrowLeft className="h-4 w-4" /> Evaluation runs</Link>
    </Button>
  );

  if (run.isLoading) return <><Skeleton className="mb-4 h-9 w-64" /><Skeleton className="h-40" /></>;
  if (run.isError || !run.data) return <>{back}<Card><ErrorState title="Could not open this run" error={run.error} onRetry={() => run.refetch()} /></Card></>;

  const r = run.data;
  const cases = r.case_details ?? [];

  return (
    <>
      {back}
      <PageHeader
        title={`Run #${r.id}`}
        description={<span className="flex flex-wrap items-center gap-2">{formatDateTime(r.created_at)} <Badge>{r.dataset_name}</Badge> <Badge tone="accent">{r.provider} · {r.model_name}</Badge></span>}
      />
      <div className="mb-6"><ProxyNote /></div>

      <Card className="mb-6 grid grid-cols-2 divide-x divide-y divide-line sm:grid-cols-3 sm:divide-y-0 lg:grid-cols-6">
        {METRICS.map((m) => (
          <div key={m.key} className="p-4" title={m.help}>
            <p className="text-[13px] text-muted">{m.label}</p>
            <p className="tabular mt-1 font-serif text-3xl font-medium text-ink">{formatPercent(r[m.key])}</p>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-line"><div className={cn("h-full", scoreTone(r[m.key]))} style={{ width: `${(r[m.key] ?? 0) * 100}%` }} /></div>
          </div>
        ))}
        <div className="p-4"><p className="text-[13px] text-muted">Cases</p><p className="tabular mt-1 font-serif text-3xl font-medium text-ink">{r.cases_evaluated ?? 0}</p></div>
        <div className="p-4"><p className="text-[13px] text-muted">Avg latency</p><p className="tabular mt-1 font-serif text-3xl font-medium text-ink">{formatMs(r.avg_latency_ms)}</p></div>
      </Card>

      <Card>
        <CardHeader title="Cases" description="Per-question results." />
        {cases.length === 0 ? (
          <EmptyState title="No case details" description="This run did not store per-case data." />
        ) : (
          <Table className="min-w-[860px]">
            <THead><tr><TH>Question</TH><TH>Chunks</TH><TH>Faithfulness</TH><TH>Relevancy</TH><TH>Precision</TH><TH>Recall</TH><TH>Latency</TH></tr></THead>
            <TBody>
              {cases.map((c) => (
                <TR key={c.id}>
                  <TD className="max-w-[320px]">
                    <p className="font-medium">{c.question ?? c.id}</p>
                    {c.error && <p className="mt-0.5 text-xs text-danger">{c.error}</p>}
                  </TD>
                  <TD className="tabular text-muted">{c.retrieved_chunks ?? "—"}</TD>
                  <TD><MetricBar value={c.faithfulness} /></TD>
                  <TD><MetricBar value={c.answer_relevancy} /></TD>
                  <TD><MetricBar value={c.context_precision} /></TD>
                  <TD><MetricBar value={c.context_recall} /></TD>
                  <TD className="tabular text-muted">{formatMs(c.latency_ms)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}
