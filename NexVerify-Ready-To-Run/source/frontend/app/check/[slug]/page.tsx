import CheckView from "@/components/CheckView";

export default async function CheckPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ q?: string }>;
}) {
  const { slug } = await params;
  const { q } = await searchParams;
  const query = (q && q.trim()) || decodeURIComponent(slug).replace(/-/g, " ");
  return <CheckView query={query} />;
}
