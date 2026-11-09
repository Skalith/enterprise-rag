import { Suspense } from "react";

export default function AuthGroupLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={null}>{children}</Suspense>;
}
