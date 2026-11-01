import { LoginForm } from "@/components/LoginForm";

function safeNext(value: string | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/login")) return "/studio";
  return value;
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const params = await searchParams;
  return (
    <main id="content">
      <p className="eyebrow">Private</p>
      <h1>Open the desk</h1>
      <p className="lede">This review is only for the owner. The password is <code>UPW_PASSWORD</code>.</p>
      <LoginForm nextPath={safeNext(params.next)} />
    </main>
  );
}
