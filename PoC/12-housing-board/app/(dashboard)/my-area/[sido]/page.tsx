import { redirect } from 'next/navigation';
import { regions } from '../../../../lib/home10/policy-907';

type Props = { params: Promise<{ sido: string }> };
export const dynamicParams = false;
export const generateStaticParams = () => regions.map((item) => ({ sido: item.id }));
export default async function MyAreaDetail({ params }: Props) {
  const { sido } = await params;
  redirect(`/area/${sido}`);
}
