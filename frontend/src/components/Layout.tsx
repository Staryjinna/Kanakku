import type { ReactNode } from "react";

export function Page({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-4 py-8">
      <h1 className="mb-1 text-2xl font-semibold text-emerald-800">Kanakku AI</h1>
      <h2 className="mb-6 text-lg text-slate-600">{title}</h2>
      {children}
    </main>
  );
}

export function ErrorText({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
      {message}
    </p>
  );
}

export function Spinner() {
  return <p className="p-8 text-center text-slate-500">Loading…</p>;
}
