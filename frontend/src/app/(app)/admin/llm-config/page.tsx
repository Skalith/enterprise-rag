"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Cpu, Plus } from "lucide-react";
import { toast } from "sonner";
import { adminApi } from "@/lib/api/endpoints";
import { qk, useLlmConfigs, useProviders } from "@/lib/api/queries";
import type { LLMConfigItem } from "@/lib/types";
import { PageHeader } from "@/components/ui/page-header";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, ConfirmDialog } from "@/components/ui/dialog";
import { Field, Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { TableSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { formatDateTime } from "@/lib/utils";

const schema = z.object({
  provider: z.string().min(1, "Choose a provider"),
  model_name: z.string().trim().min(1, "Enter a model name"),
  temperature: z.coerce.number().min(0, "Min 0").max(2, "Max 2"),
  max_tokens: z.coerce.number().int("Whole number").min(1, "Min 1").max(32768, "Max 32,768"),
  is_active: z.boolean(),
  api_key: z.string().optional(),
});
type Values = z.infer<typeof schema>;

function NewConfigDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient();
  const providers = useProviders(open);
  const [apiError, setApiError] = useState<string | null>(null);
  const {
    register, handleSubmit, setValue, watch, reset,
    formState: { errors },
  } = useForm<Values>({
    resolver: zodResolver(schema) as never,
    defaultValues: { provider: "", model_name: "", temperature: 0.2, max_tokens: 1024, is_active: false, api_key: "" },
  });

  const create = useMutation({
    mutationFn: (v: Values) =>
      adminApi.createLlmConfig({ ...v, api_key: v.api_key?.trim() || undefined }),
    onSuccess: () => {
      toast.success("Configuration saved");
      qc.invalidateQueries({ queryKey: qk.llmConfigs });
      reset();
      onOpenChange(false);
    },
    onError: (e: Error) => setApiError(e.message),
  });

  const provider = watch("provider");
  const defaultModel = providers.data?.find((p) => p.name === provider)?.default_model;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setApiError(null); onOpenChange(o); }}>
      <DialogContent title="New LLM configuration" description="Saved configurations can be activated to change the model used by chat.">
        <form onSubmit={handleSubmit((v) => { setApiError(null); create.mutate(v); })} className="space-y-4 p-5" noValidate>
          {apiError && <p role="alert" className="rounded-lg bg-danger-soft p-3 text-[13px] text-danger">{apiError}</p>}
          <Field label="Provider" htmlFor="provider" error={errors.provider?.message}>
            <Select
              id="provider"
              value={provider}
              onValueChange={(v) => {
                setValue("provider", v, { shouldValidate: true });
                const dm = providers.data?.find((p) => p.name === v)?.default_model;
                if (dm && !watch("model_name")) setValue("model_name", dm);
              }}
              placeholder={providers.isLoading ? "Loading…" : "Select a provider"}
              options={(providers.data ?? []).map((p) => ({ value: p.name, label: `${p.name}${p.healthy ? "" : " (unavailable)"}` }))}
            />
          </Field>
          <Field label="Model name" htmlFor="model_name" error={errors.model_name?.message} hint={defaultModel ? `Provider default: ${defaultModel}` : undefined}>
            <Input id="model_name" {...register("model_name")} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Temperature" htmlFor="temperature" error={errors.temperature?.message}>
              <Input id="temperature" type="number" step="0.1" {...register("temperature")} />
            </Field>
            <Field label="Max tokens" htmlFor="max_tokens" error={errors.max_tokens?.message}>
              <Input id="max_tokens" type="number" {...register("max_tokens")} />
            </Field>
          </div>
          <Field label="API key (optional)" htmlFor="api_key" hint="The backend stores only the first characters as a hint. Real provider keys are read from the backend environment.">
            <Input id="api_key" type="password" autoComplete="off" {...register("api_key")} />
          </Field>
          <label className="flex items-center gap-2.5 text-[13px] text-ink">
            <Switch checked={watch("is_active")} onCheckedChange={(v) => setValue("is_active", v)} aria-label="Activate immediately" />
            Activate immediately (replaces the current active configuration)
          </label>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" loading={create.isPending}>Save configuration</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function LlmConfigPage() {
  const qc = useQueryClient();
  const configs = useLlmConfigs();
  const [open, setOpen] = useState(false);
  const [toActivate, setToActivate] = useState<LLMConfigItem | null>(null);

  const activate = useMutation({
    mutationFn: (c: LLMConfigItem) => adminApi.activateLlmConfig(c.id),
    onSuccess: () => {
      toast.success("Configuration activated");
      setToActivate(null);
      qc.invalidateQueries({ queryKey: qk.llmConfigs });
    },
    onError: (e: Error) => toast.error("Could not activate", { description: e.message }),
  });

  const active = configs.data?.find((c) => c.is_active);

  return (
    <>
      <PageHeader
        title="LLM configuration"
        description="Choose which provider and model answers chat questions. With nothing active, the backend falls back to its default local model."
        actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" /> New configuration</Button>}
      />

      {active && (
        <Card className="mb-6 flex items-center gap-4 border-accent/40 bg-accent-soft p-4">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-accent" />
          <div className="min-w-0">
            <p className="text-[13px] text-muted">Active now</p>
            <p className="truncate text-[15px] font-semibold text-ink">{active.provider} · {active.model_name}</p>
          </div>
        </Card>
      )}

      <Card>
        {configs.isLoading ? (
          <TableSkeleton cols={5} />
        ) : configs.isError ? (
          <ErrorState error={configs.error} onRetry={() => configs.refetch()} />
        ) : (configs.data ?? []).length === 0 ? (
          <EmptyState icon={<Cpu className="h-5 w-5" />} title="No saved configurations" description="Create one to choose the provider and model used by chat." action={<Button size="sm" onClick={() => setOpen(true)}>New configuration</Button>} />
        ) : (
          <Table>
            <THead>
              <tr><TH>Provider</TH><TH>Model</TH><TH>Temperature</TH><TH>Max tokens</TH><TH>Created</TH><TH>Status</TH><TH className="w-28"><span className="sr-only">Actions</span></TH></tr>
            </THead>
            <TBody>
              {configs.data!.map((c) => (
                <TR key={c.id}>
                  <TD className="font-medium capitalize">{c.provider}</TD>
                  <TD>{c.model_name}</TD>
                  <TD className="tabular text-muted">{c.temperature ?? "—"}</TD>
                  <TD className="tabular text-muted">{c.max_tokens ?? "—"}</TD>
                  <TD className="whitespace-nowrap text-muted">{formatDateTime(c.created_at)}</TD>
                  <TD>{c.is_active ? <Badge tone="success" dot>Active</Badge> : <Badge>Inactive</Badge>}</TD>
                  <TD>{!c.is_active && <Button variant="secondary" size="sm" onClick={() => setToActivate(c)}>Activate</Button>}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>

      <NewConfigDialog open={open} onOpenChange={setOpen} />
      <ConfirmDialog
        open={!!toActivate}
        onOpenChange={(o) => !o && setToActivate(null)}
        title="Activate this configuration?"
        description={<>Chat will use <strong className="text-ink">{toActivate?.provider} · {toActivate?.model_name}</strong> for everyone from the next question.</>}
        confirmLabel="Activate"
        loading={activate.isPending}
        onConfirm={() => toActivate && activate.mutate(toActivate)}
      />
    </>
  );
}
