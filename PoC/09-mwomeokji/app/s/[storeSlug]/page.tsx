import { CustomerApp } from "../../../components/customer-app";
export default async function StorePage({
  params,
}: {
  params: Promise<{ storeSlug: string }>;
}) {
  const { storeSlug } = await params;
  return <CustomerApp slug={storeSlug} />;
}
