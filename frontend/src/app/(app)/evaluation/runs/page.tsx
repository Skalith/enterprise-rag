"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Play } from "lucide-react";
import { toast } from "sonner";
import { evaluationApi } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/client";
import { qk, useEvalDatasets, useEvalRuns } from "@/lib/api/queries";
import { PageHeader } from "@/components/ui/page-header";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { MetricBar, ProxyNote } from "@/components/evaluation/metrics";
import { formatDateTime, formatMs } from "@/lib/utils";

function RunsInner() {
  const qc = useQueryClient();
  const router = useRouter();
  const params = useSearchParams();
  const datasets = useEvalDatasets();
  const runs = useEvalRuns();
  const [dataset, setDataset] = useState(params.get("dataset") ?? "");
  const [topK, setTopK] = useState("5");
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!dataset && datasets.data?.datasets.length) setDataset(datasets.data.datasets.includes("default") ? "default" : datasets.data.datasets[0]);
  }, [datasets.data, dataset]);

  const trigger = useMutation({
    mutationFn: () => evaluationApi.trigger({ dataset_name: dataset, top_k: Math.min(20, Math.max(1, Number(topK) || 5)) }),
    onMutate: () => setNotice(null),
    onSuccess: ({ run }) => {
      toast.success("Evaluation complete", { description: `${run.cases_evaluated ?? 0} cases evaluated` });
      qc.invalidateQueries({ queryKey: qk.evalRuns });
      router.push(`/evaluation/runs/${run.id}`);
    },
    onError: (e: Error) => {
      setNotice(
        e instanceof ApiError && e.status === 409
          ? `${e.message} Upload and index a document you own first.`
          : e instanceof ApiError && e.isRateLimited
            ? `Evaluations are rate limited. Try again${e.retryAfter ? ` in ${e.retryAfter}s` : " shortly"}.`
            : e.message,
      );
    },
  });

  return (
    <>
      <PageHeader title="Evaluation runs" description="Run a dataset against the documents you can access, then compare quality over time." />
      <div className="mb-6"><ProxyNote /></div>

      <Card className="mb-6">
        <CardHeader title="Start a run" description="Runs use the active LLM configuration and can take a while." />
        <CardBody>
          <div className="flex flex-wrap items-end gap-4">
            <Field label="Dataset" htmlFor="dataset" className="w-56">
              <Select id="dataset" value={dataset} onValueChange={setDataset} placeholder="Select a dataset" options={(datasets.data?.datasets ?? []).map((d) => ({ value: d, label: d }))} />
            </Field>
            <Field label="Passages per question" htmlFor="topk" className="w-44">
              <Input id="topk" type="number" min={1} max={20} value={topK} onChange={(e) => setTopK(e.target.value)} />
            </Field>
            <Button onClick={() => trigger.mutate()} loading={trigger.isPending} disabled={!dataset}>
              <Play className="h-4 w-4" /> {trigger.isPending ? "Running…" : "Run evaluation"}
            </Button>
          </div>
          {notice && <p role="alert" className="mt-4 rounded-lg bg-danger-soft p-3 text-[13px] text-danger">{notice}</p>}
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="History" description="The 100 most recent runs." />
        {runs.isLoading ? (
          <TableSkeleton cols={6} />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
        ) : (runs.data ?? []).length === 0 ? (
          <EmptyState icon={<FlaskConical className="h-5 w-5" />} title="No runs yet" description="Start a run above to see metrics here." />
        ) : (
          <Table className="min-w-[900px]">
            <THead><tr><TH>Run</TH><TH>Dataset</TH><TH>Model</TH><TH>Cases</TH><TH>Faithfulness</TH><TH>Relevancy</TH><TH>Precision</TH><TH>Recall</TH><TH>Avg latency</TH></tr></THead>
            <TBody>
              {runs.data!.map((r) => (
                <TR key={r.id}>
                  <TD>
                    <Link href={`/evaluation/runs/${r.id}`} className="font-medium text-accent hover:underline">#{r.id}</Link>
                    <p className="whitespace-nowrap text-xs text-muted">{formatDateTime(r.created_at)}</p>
                  </TD>
                  <TD>{r.dataset_name ?? "—"}</TD>
                  <TD><span className="block max-w-[160px] truncate">{r.model_name ?? "—"}</span><span className="text-xs text-muted">{r.provider}</span></TD>
                  <TD className="tabular">{r.cases_evaluated ?? 0}</TD>
                  <TD><MetricBar value={r.faithfulness} /></TD>
                  <TD><MetricBar value={r.answer_relevancy} /></TD>
                  <TD><MetricBar value={r.context_precision} /></TD>
                  <TD><MetricBar value={r.context_recall} /></TD>
                  <TD className="tabular text-muted">{formatMs(r.avg_latency_ms)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </>
  );
}

export default function RunsPage() {
  return (
    <Suspense fallback={null}>
      <RunsInner />
    </Suspense>
  );
}
